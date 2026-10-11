"""Phase 1-2 (P2): anomaly detector, forecaster, compound days, risk events, scorecard, engine."""
import numpy as np
import pandas as pd
import pytest

from facility.analytics.anomaly import COLUMNS, detect_anomalies
from facility.analytics.compound import find_compound_days
from facility.analytics.forecasting import forecast_metric, robust_sigma
from facility.analytics.risk_events import build_risk_events, group_incidents
from facility.analytics.scorecard import compute_scorecard, metric_score
from facility.contracts import EVIDENCE_KEYS, METRICS, RiskType, Severity
from facility.data.generator import generate_facility_data
from facility.data.injection import inject_anomaly


def _clean(days=21, seed=7):
    return generate_facility_data(days=days, seed=seed, schedule=[])[0]


# ------------------------------------------------------------------ anomaly detection
def test_detector_schema(fixture_df):
    a = detect_anomalies(fixture_df)
    assert list(a.columns) == COLUMNS and len(a) == len(fixture_df) * 3
    assert a.is_anomaly.dtype == bool


def test_first_week_has_no_baseline(fixture_df):
    a = detect_anomalies(fixture_df, exclude_flagged=False)
    first = a[a.timestamp < fixture_df.index[0] + pd.Timedelta(days=7)]
    assert first.z_score.isna().all() and not first.is_anomaly.any()


def test_current_point_excluded():
    """A spike must not be part of its own baseline (shift(1))."""
    df = _clean()
    t = df.index[-10]
    spiked = df.copy(); spiked.loc[t, "water_kl"] *= 3
    a = detect_anomalies(spiked, exclude_flagged=False, weekday_adjust=False, pool_h=0)
    b = detect_anomalies(df, exclude_flagged=False, weekday_adjust=False, pool_h=0)
    row = lambda x: x[(x.metric == "water_kl") & (x.timestamp == t)].iloc[0]
    assert row(a).baseline_mean == pytest.approx(row(b).baseline_mean)
    assert row(a).is_anomaly


def test_clean_data_has_few_false_positives():
    df = _clean(days=28)
    a = detect_anomalies(df, z_threshold=4.0)
    scored = a.z_score.notna().sum()
    assert a.is_anomaly.sum() / scored < 0.01


def test_hour_of_day_beats_plain_rolling():
    """Why hour-of-day matters: a plain 168 h rolling std is dominated by the daily cycle,
    so the threshold becomes insensitive and a night-time leak hides inside it."""
    df = _clean(days=21)
    leak_t = df.index[-24 * 2 + 3]                        # 03:00, two days ago
    df.loc[leak_t:leak_t + pd.Timedelta(hours=2), "water_kl"] *= 1.8
    s = df["water_kl"]
    m, sd = s.shift(1).rolling(168).mean(), s.shift(1).rolling(168).std()
    plain = ((s - m) / sd).abs() >= 3
    hod = detect_anomalies(df, z_threshold=4.0)
    hod_w = hod[hod.metric == "water_kl"].set_index("timestamp").is_anomaly
    leak = slice(leak_t, leak_t + pd.Timedelta(hours=2))
    assert hod_w[leak].all()                                  # hour-of-day: whole leak caught
    assert plain[leak].sum() < 3                              # plain: part of the leak missed


def test_std_floor_prevents_explosion():
    idx = pd.date_range("2026-07-01", periods=14 * 24, freq="h", name="timestamp")
    df = pd.DataFrame({m: 100.0 for m in METRICS}, index=idx)          # zero variance
    df.iloc[-1, 0] = 101.0                                              # +1%
    a = detect_anomalies(df, weekday_adjust=False, pool_h=0, exclude_flagged=False)
    z = a[(a.metric == "energy_kwh")].z_score.iloc[-1]
    assert np.isfinite(z) and abs(z) == pytest.approx(0.5, rel=0.01)   # 1 / (2% of 100)


def test_exclude_flagged_unmasks_repeat_incident():
    """A spike 3 days earlier at the same hour inflates the plain baseline; excluding
    flagged hours restores detection of the new incident."""
    df = _clean(days=21)
    t_old = df.index[-24 * 3 - 10]; t_new = df.index[-10]
    for t in (t_old, t_new):
        df.loc[t:t + pd.Timedelta(hours=2), "energy_kwh"] *= 2.2
    win = slice(t_new, t_new + pd.Timedelta(hours=2))
    def flags(**kw):
        a = detect_anomalies(df, z_threshold=4.0, **kw)
        return a[a.metric == "energy_kwh"].set_index("timestamp").is_anomaly[win]
    assert flags(exclude_flagged=True).all()
    assert flags(exclude_flagged=True).sum() >= flags(exclude_flagged=False).sum()


def test_ground_truth_recall(full, full_result):
    from facility.pipeline import evaluate_detection
    q = evaluate_detection(full_result.anomalies, full[1])
    assert q["recall"] >= 0.8 and q["precision"] >= 0.6


# ------------------------------------------------------------------ forecasting
def test_forecast_shape_and_start(fixture_df):
    f = forecast_metric(fixture_df["energy_kwh"])
    assert list(f.columns) == ["timestamp", "yhat", "yhat_lower", "yhat_upper"] and len(f) == 24
    assert f.timestamp.iloc[0] == fixture_df.index[-1] + pd.Timedelta(hours=1)
    assert (f.yhat_lower <= f.yhat).all() and (f.yhat <= f.yhat_upper).all() and (f.yhat_lower >= 0).all()
    assert f.attrs["method"] == "holt_winters"


def test_forecast_follows_daily_cycle(full):
    df = full[0]
    f = forecast_metric(df["energy_kwh"]).set_index("timestamp").yhat
    assert f[f.index.hour == 13].iloc[0] > 1.3 * f[f.index.hour == 3].iloc[0]


def test_forecast_needs_two_seasons():
    s = _clean(days=21)["energy_kwh"].iloc[:30]
    with pytest.raises(ValueError):
        forecast_metric(s)


def test_forecast_fallback_on_fit_failure(monkeypatch, fixture_df):
    import facility.analytics.forecasting as F
    def boom(*a, **k): raise np.linalg.LinAlgError("singular")
    monkeypatch.setattr(F, "ExponentialSmoothing", boom)
    f = forecast_metric(fixture_df["water_kl"])
    assert f.attrs["method"] == "seasonal_naive_fallback" and len(f) == 24 and f.yhat.notna().all()


def test_robust_sigma_ignores_outliers():
    r = np.r_[np.random.default_rng(0).normal(0, 1, 500), [60, -80, 90]]
    assert 0.8 < robust_sigma(r) < 1.2 and np.std(r) > 4


# ------------------------------------------------------------------ compound + risk events
def _anoms(rows):
    return pd.DataFrame([{"timestamp": pd.Timestamp(t), "metric": m, "value": 1.0, "baseline_mean": 1.0,
                          "baseline_std": 0.1, "z_score": z, "is_anomaly": True} for t, m, z in rows])


def test_compound_day():
    a = _anoms([("2026-08-01 03:00", "energy_kwh", 5), ("2026-08-01 20:00", "water_kl", 6),
                ("2026-08-02 03:00", "energy_kwh", 5)])
    c = find_compound_days(a)
    assert len(c) == 1 and c.iloc[0].date == pd.Timestamp("2026-08-01")
    assert c.iloc[0].metrics == ["energy_kwh", "water_kl"] and c.iloc[0].severity == "medium"
    assert find_compound_days(a.iloc[:0]).empty


def test_compound_three_metrics_is_high():
    a = _anoms([("2026-08-01 03:00", m, 5) for m in METRICS])
    assert find_compound_days(a).iloc[0].severity == "high"


def test_incident_grouping_one_card_per_incident():
    rows = [(f"2026-08-01 {h:02d}:00", "water_kl", 6) for h in (10, 11, 12, 13, 14)]
    rows += [("2026-08-01 16:00", "water_kl", 5)]           # 1 h gap -> bridged
    rows += [("2026-08-01 22:00", "water_kl", 5)]           # 7 h gap -> new incident
    groups = list(group_incidents(_anoms(rows), gap_tolerance_h=2))
    assert [len(g) for g in groups] == [6, 1]


def _events_for(df):
    from facility.analytics.engine import run_analytics
    return run_analytics(df).risk_events


def test_risk_events_from_live_injection():
    df = _clean(days=21)
    new, _ = inject_anomaly(df, "energy_kwh", hours=5, magnitude=2.5)
    ev = [e for e in _events_for(new) if e.risk_type == RiskType.ENERGY_SPIKE]
    assert len(ev) == 1, "5 consecutive anomalous hours must be ONE event"
    e = ev[0]
    assert e.severity == Severity.HIGH and e.evidence["hours"] == 5 and e.evidence["direction"] == "above"
    assert e.start == new.index[-5] and e.end == new.index[-1]


def test_drop_is_marked_below():
    df = _clean(days=21)
    new, _ = inject_anomaly(df, "energy_kwh", hours=4, magnitude=2.5, kind="drop")
    e = next(e for e in _events_for(new) if e.risk_type == RiskType.ENERGY_SPIKE)
    assert e.evidence["direction"] == "below" and e.evidence["z_score"] < 0


def test_old_incidents_are_not_active():
    df = _clean(days=21)
    old = df.index[-24 * 5]
    new, _ = inject_anomaly(df, "energy_kwh", hours=4, magnitude=2.5, start=old)
    assert not [e for e in _events_for(new) if e.risk_type == RiskType.ENERGY_SPIKE]


def test_forecast_peak_event():
    df = _clean(days=21)
    new, _ = inject_anomaly(df, "waste_kg", hours=8, magnitude=2.5)
    ev = [e for e in _events_for(new) if e.risk_type == RiskType.FORECAST_PEAK]
    assert ev and ev[0].evidence["forecast_peak"] > ev[0].evidence["threshold"]
    assert ev[0].start > new.index[-1]


def test_clean_data_has_no_active_risks():
    assert _events_for(_clean(days=21, seed=11)) == [] or all(
        e.severity == Severity.LOW for e in _events_for(_clean(days=21, seed=11)))


def test_every_event_has_all_evidence_keys(full_result):
    assert full_result.risk_events
    for e in full_result.risk_events:
        assert set(e.evidence) == set(EVIDENCE_KEYS)
        assert e.risk_id.startswith(e.risk_type.value + ":")


def test_events_sorted_by_severity(full_result):
    ranks = [{"high": 3, "medium": 2, "low": 1}[e.severity.value] for e in full_result.risk_events]
    assert ranks == sorted(ranks, reverse=True)


def test_demo_anomaly_detected(full_result):
    """The water spike in the last 24 h (the on-stage 'catch') is a HIGH risk."""
    w = [e for e in full_result.risk_events if e.risk_type == RiskType.WATER_SURGE]
    assert w and w[0].severity == Severity.HIGH and w[0].evidence["hours"] == 5


# ------------------------------------------------------------------ scorecard
@pytest.mark.parametrize("hours, pct, expected", [(0, 0, 100), (12, 0, 80), (24, 0, 60), (48, 0, 60),
                                                  (0, 15, 70), (0, 30, 40), (0, -20, 100), (24, 30, 0)])
def test_metric_score_formula(hours, pct, expected):
    assert metric_score(hours, pct) == pytest.approx(expected)


def test_scorecard_structure_and_compound_penalty():
    idx = pd.date_range("2026-07-01", periods=28 * 24, freq="h", name="timestamp")
    df = pd.DataFrame({m: 10.0 for m in METRICS}, index=idx)
    a = pd.DataFrame({"timestamp": idx.repeat(3), "metric": list(METRICS) * len(idx), "value": 10.0,
                      "baseline_mean": 10.0, "baseline_std": 1.0, "z_score": 0.0, "is_anomaly": False})
    comp = pd.DataFrame({"date": [idx[-1].normalize()], "metrics": [["energy_kwh", "water_kl"]],
                         "n_metrics": [2], "severity": ["medium"]})
    sc = compute_scorecard(df, a, comp)
    assert sc["overall"] == 90 and sc["compound_penalty"] == 10 and sc["compound_days_7d"] == 1
    for m in METRICS:
        assert sc["metrics"][m] == {"score": 100, "anomaly_hours_7d": 0, "vs_baseline_pct": 0.0,
                                    "anomaly_penalty": 0.0, "trend_penalty": 0.0}
    assert "not a certified rating" in sc["method"]


def test_scorecard_clipped_at_zero():
    idx = pd.date_range("2026-07-01", periods=28 * 24, freq="h", name="timestamp")
    df = pd.DataFrame({m: 10.0 for m in METRICS}, index=idx)
    a = pd.DataFrame(columns=["timestamp", "metric", "value", "baseline_mean", "baseline_std", "z_score",
                              "is_anomaly"])
    comp = pd.DataFrame({"date": [idx[-1].normalize() - pd.Timedelta(days=d) for d in range(15)],
                         "metrics": [["a", "b"]] * 15, "n_metrics": 2, "severity": "medium"})
    assert compute_scorecard(df, a.astype({"is_anomaly": bool}), comp)["overall"] >= 0


def test_engine_params_expose_explainability(full_result):
    p = full_result.params
    for k in ("anomaly_method", "z_threshold", "baseline_days", "forecast", "band", "compound_rule",
              "forecast_risk_rule", "incident_rule", "scorecard", "timing_ms", "data_window"):
        assert k in p
