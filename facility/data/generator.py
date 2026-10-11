"""Synthetic hourly data for a 200-bed district government hospital.

value(t) = daily_profile(hour) x weekday_factor x day_level x trend + AR(1) noise

* daily_profile  : energy peaks with OPD hours (~13:00); water peaks at morning
                   bathing (07:30), laundry/kitchen (13:00) and evening (19:00);
                   waste peaks after morning rounds (11:00) and evening meals (19:00).
* weekday_factor : Saturday OPD is half-day, Sunday OPD closed.
* day_level      : day-to-day variation (occupancy, weather) ~ N(1, 2.5%).
* trend          : energy creeps up ~4% over 60 days (pre-summer cooling load).
* AR(1) noise    : meter readings are correlated hour to hour, not white noise.

Known anomalies are multiplied in from SCHEDULE and returned as a ground-truth log,
so detection quality can be *measured* (recall/precision), not just claimed.
"""
import numpy as np
import pandas as pd

from facility.contracts import INDEX_NAME, METRICS

# (metric, day_index, start_hour, hours, factor, kind) - factor < 1 is a drop
SCHEDULE = [
    ("energy_kwh", 20, 13, 5, 2.0, "spike"),
    ("energy_kwh", 27, 10, 4, 0.4, "drop"),
    ("water_kl", 33, 2, 6, 2.5, "spike"),
    ("waste_kg", 41, 8, 10, 2.2, "spike"),
    ("energy_kwh", 47, 12, 4, 2.2, "spike"),   # compound day 47 (energy + water)
    ("water_kl", 47, 6, 4, 2.5, "spike"),
    ("energy_kwh", 52, 14, 4, 1.8, "spike"),
    ("water_kl", 59, 14, 5, 2.5, "spike"),     # inside the last 24 h: the demo catch
]

NOISE_SD = {"energy_kwh": 8.0, "water_kl": 0.6, "waste_kg": 0.4}
AR_PHI = 0.5
DAY_LEVEL_SD = 0.025


def _energy(h, dow):
    weekday = np.where(dow == 6, 0.8, np.where(dow == 5, 0.9, 1.0))
    return (200 + 120 * np.exp(-((h - 13) / 4.0) ** 2)) * weekday


def _water(h, dow):
    base = (8 + 6 * np.exp(-((h - 7.5) / 1.5) ** 2) + 5 * np.exp(-((h - 13) / 1.5) ** 2)
            + 2 * np.exp(-((h - 19) / 1.5) ** 2))
    return base * np.where(dow == 6, 0.85, 1.0)


def _waste(h, dow):
    base = 4 + 3 * np.exp(-((h - 11) / 3.0) ** 2) + 2 * np.exp(-((h - 19) / 2.0) ** 2)
    return base * np.where(dow == 6, 0.8, 1.0)


PROFILES = {"energy_kwh": _energy, "water_kl": _water, "waste_kg": _waste}


def _ar1(rng, n, phi, sd):
    """AR(1) noise whose *marginal* standard deviation is `sd`."""
    eps = rng.normal(0.0, sd * np.sqrt(1 - phi ** 2), n)
    out = np.empty(n)
    out[0] = rng.normal(0.0, sd)
    for i in range(1, n):
        out[i] = phi * out[i - 1] + eps[i]
    return out


def generate_facility_data(days=60, seed=42, start="2026-07-01", schedule=None):
    """Return (df, ground_truth_log).

    df  : DatetimeIndex 'timestamp' (hourly, tz-naive), float columns METRICS.
    log : DataFrame[metric, start, end, kind, magnitude] - one row per injected window.
    """
    if days < 1:
        raise ValueError("days must be >= 1")
    schedule = SCHEDULE if schedule is None else schedule
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days * 24, freq="h", name=INDEX_NAME)
    h, dow = idx.hour.values, idx.dayofweek.values
    day_no = np.arange(len(idx)) // 24

    df = pd.DataFrame(index=idx)
    for m in METRICS:  # fixed order => reproducible random stream
        day_level = rng.normal(1.0, DAY_LEVEL_SD, days)[day_no]
        trend = 1.0 + (0.04 * day_no / max(days - 1, 1) if m == "energy_kwh" else 0.0)
        df[m] = PROFILES[m](h, dow) * day_level * trend + _ar1(rng, len(idx), AR_PHI, NOISE_SD[m])
    df = df.clip(lower=0.1)

    log = []
    for metric, day, hour, hours, factor, kind in schedule:
        if day >= days:
            continue
        s = idx[0] + pd.Timedelta(days=day, hours=hour)
        e = s + pd.Timedelta(hours=hours - 1)
        df.loc[s:e, metric] = df.loc[s:e, metric] * factor
        log.append({"metric": metric, "start": s, "end": e, "kind": kind, "magnitude": factor})

    log_df = pd.DataFrame(log, columns=["metric", "start", "end", "kind", "magnitude"])
    return df.round(3).astype(float), log_df
