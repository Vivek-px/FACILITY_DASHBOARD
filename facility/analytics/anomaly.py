"""Hour-of-day rolling z-score anomaly detection (PRD §7.2, decision A3).

Why hour-of-day? Hospital energy at 13:00 is naturally ~60% higher than at 03:00.
A plain rolling window over all hours mixes those regimes: its mean sits between
night and day and its std is dominated by the daily cycle, so the threshold becomes
insensitive - a night-time leak that nearly doubles flow still sits inside the band
(tests/test_analytics.py::test_hour_of_day_beats_plain_rolling), and the "expected"
value shown to the manager is wrong for every hour. Comparing each hour only
with the *same hour* on the previous `baseline_days` days removes the daily cycle.

For value x at day d, hour h:
    baseline_mean = mean(x[d-7..d-1, h])        (shift(1) => current point excluded)
    baseline_std  = max(std(x[d-7..d-1, h]), floor_frac * |baseline_mean|)
    z = (x - baseline_mean) / baseline_std,   anomalous if |z| >= z_threshold

The std floor stops z from exploding when the 7 past values happen to be almost
identical. The first `baseline_days` days have no baseline: z is NaN, not anomalous.

Weekday adjustment (BUILD_SPEC deviation D2): hospitals run a half-day OPD on
Saturday and none on Sunday, so a 7-day same-hour window contains only one Sunday and
every Sunday afternoon scores as a "drop" (it produced most false positives in
testing). With weekday_adjust=True each value is first divided by its day-of-week
factor (median ratio of that weekday's total to the centred 7-day mean), z is
computed on the adjusted series, and baseline_mean is scaled back to real units.

robust=True swaps mean/std for median and 1.4826*MAD, which is not pulled up by a
spike that sits inside the baseline window (see BUILD_SPEC deviation D3).
"""
import numpy as np
import pandas as pd

from facility.contracts import METRICS

COLUMNS = ["timestamp", "metric", "value", "baseline_mean", "baseline_std", "z_score", "is_anomaly"]


def _mad(w):
    med = np.median(w)
    return 1.4826 * np.median(np.abs(w - med))


def _baseline(s, baseline_days, robust, min_periods=None):
    mp = min_periods or baseline_days
    g = s.groupby(s.index.hour)
    if robust:
        mean = g.transform(lambda x: x.shift(1).rolling(baseline_days, min_periods=mp).median())
        std = g.transform(lambda x: x.shift(1).rolling(baseline_days, min_periods=mp)
                          .apply(lambda w: _mad(w[~np.isnan(w)]), raw=True))
    else:
        mean = g.transform(lambda x: x.shift(1).rolling(baseline_days, min_periods=mp).mean())
        std = g.transform(lambda x: x.shift(1).rolling(baseline_days, min_periods=mp).std())
    return mean, std


def weekday_factors(s):
    """Day-of-week multiplicative factors (Mon=0 .. Sun=6), ~1.0 on normal weekdays."""
    daily = s.resample("D").sum()
    if len(daily) < 14:
        return pd.Series(1.0, index=range(7))
    ratio = daily / daily.rolling(7, center=True, min_periods=7).mean()
    f = ratio.groupby(ratio.index.dayofweek).median().reindex(range(7)).fillna(1.0)
    return f / f.mean()


def pool_spread(std, pool_h):
    """Average the variance of neighbouring hours (h-pool_h .. h+pool_h, same day).

    A std estimated from only 7 values is itself very noisy: roughly 1 in 40 normal
    hours gets |z| > 3 purely because its 7-sample std came out small (Student-t tails).
    Pooling the spread of adjacent hours triples the sample (21 values) while the
    *mean* stays strictly hour-of-day. See BUILD_SPEC deviation D2.
    """
    if pool_h <= 0:
        return std
    var = (std ** 2).to_frame("v")
    var["date"], var["hour"] = std.index.normalize(), std.index.hour
    grid = var.pivot_table(index="date", columns="hour", values="v", dropna=False)
    grid = grid.reindex(columns=range(24))
    shifted = [grid.reindex(columns=[(h + k) % 24 for h in range(24)]).set_axis(range(24), axis=1)
               for k in range(-pool_h, pool_h + 1)]          # circular: 23h neighbours 0h
    pooled = sum(shifted) / len(shifted)
    out = pooled.stack(future_stack=True).rename("v")
    out.index = out.index.get_level_values(0) + pd.to_timedelta(out.index.get_level_values(1), unit="h")
    return np.sqrt(out.reindex(std.index))


def _score(s, baseline_days, robust, pool_h, std_floor_frac, min_periods=None):
    mean, std = _baseline(s, baseline_days, robust, min_periods)
    std = pool_spread(std, pool_h)
    std = std.clip(lower=std_floor_frac * mean.abs() + 1e-9)
    return mean, std, (s - mean) / std


def detect_anomalies(df, baseline_days=7, z_threshold=3.0, std_floor_frac=0.02, robust=False,
                     weekday_adjust=True, pool_h=1, exclude_flagged=True, max_passes=5):
    """Return a long DataFrame with COLUMNS, one row per (timestamp, metric).

    exclude_flagged=True (deviation D3): further passes recompute the baseline with
    previously flagged hours removed (until the flags stop changing, <= max_passes), so a past spike cannot inflate the mean/std
    of the following week and hide a new incident at the same hour (a 5-hour spike on
    22 Aug otherwise masked the heatwave scenario at 14:00-17:00 for a whole week).
    """
    frames = []
    for m in METRICS:
        raw = df[m].astype(float)
        factor = (weekday_factors(raw).reindex(raw.index.dayofweek).values if weekday_adjust
                  else np.ones(len(raw)))
        s = raw / factor
        mean, std, z = _score(s, baseline_days, robust, pool_h, std_floor_frac)
        if exclude_flagged:
            # Fixed-point iteration: an incident masked by an older spike in pass 1 is
            # found in pass 2, then removed from *its* successors' baselines in pass 3...
            flagged = (z.abs() >= z_threshold).to_numpy()
            for _ in range(max_passes):
                clean = s.where(~flagged)
                m2, s2, _ = _score(clean, baseline_days, robust, pool_h, std_floor_frac,
                                   min_periods=max(3, baseline_days - 2))
                mean, std = m2.fillna(mean), s2.fillna(std)
                z = (s - mean) / std
                new_flags = flagged | (z.abs() >= z_threshold).to_numpy()
                if (new_flags == flagged).all():
                    break
                flagged = new_flags
        s, mean, std = raw, mean * factor, std * factor  # report in real units
        frames.append(pd.DataFrame({
            "timestamp": s.index, "metric": m, "value": s.values,
            "baseline_mean": mean.values, "baseline_std": std.values, "z_score": z.values,
            "is_anomaly": (z.abs() >= z_threshold).fillna(False).values.astype(bool),
        }))
    return pd.concat(frames, ignore_index=True)[COLUMNS]
