"""Single entry point for analytics: validated DataFrame -> AnalyticsResult."""
import time

import pandas as pd

import facility.config as C
from facility.analytics.anomaly import detect_anomalies
from facility.analytics.compound import find_compound_days
from facility.analytics.forecasting import forecast_metric
from facility.analytics.risk_events import build_risk_events
from facility.analytics.scorecard import compute_scorecard
from facility.contracts import METRICS, AnalyticsResult

DEFAULTS = {
    "z_threshold": C.Z_THRESHOLD, "baseline_days": C.BASELINE_DAYS, "std_floor_frac": C.STD_FLOOR_FRAC,
    "robust": C.ROBUST_BASELINE, "weekday_adjust": C.WEEKDAY_ADJUST, "pool_h": C.POOL_HOURS, "exclude_flagged": C.EXCLUDE_FLAGGED, "horizon_h": C.HORIZON_H, "seasonal_periods": C.SEASONAL_PERIODS,
    "fit_days": C.FIT_DAYS, "recent_hours": C.RECENT_HOURS, "compound_min_metrics": C.COMPOUND_MIN_METRICS,
    "compound_min_hours": C.COMPOUND_MIN_HOURS, "forecast_margin": C.FORECAST_MARGIN,
    "incident_gap_h": C.INCIDENT_GAP_H,
}


def run_analytics(df, config=None):
    cfg = {**DEFAULTS, **(config or {})}
    t0 = time.perf_counter()
    an = detect_anomalies(df, cfg["baseline_days"], cfg["z_threshold"], cfg["std_floor_frac"], cfg["robust"],
                          cfg["weekday_adjust"], cfg["pool_h"], cfg["exclude_flagged"])
    t1 = time.perf_counter()
    parts, methods, sigmas = [], {}, {}
    for m in METRICS:
        f = forecast_metric(df[m], cfg["horizon_h"], cfg["seasonal_periods"], cfg["fit_days"])
        methods[m], sigmas[m] = f.attrs.get("method"), round(f.attrs.get("sigma", 0.0), 3)
        parts.append(f.assign(metric=m))
    fc = pd.concat(parts, ignore_index=True)[["timestamp", "metric", "yhat", "yhat_lower", "yhat_upper"]]
    t2 = time.perf_counter()
    comp = find_compound_days(an, cfg["compound_min_metrics"], cfg["compound_min_hours"])
    events = build_risk_events(an, fc, comp, df, cfg["recent_hours"], cfg["z_threshold"],
                               cfg["forecast_margin"], cfg["incident_gap_h"])
    sc = compute_scorecard(df, an, comp)
    t3 = time.perf_counter()
    params = {
        "data_window": f"{df.index[0]:%d %b %Y %H:%M} to {df.index[-1]:%d %b %Y %H:%M} (hourly, {len(df)} rows)",
        "anomaly_method": ("median/MAD" if cfg["robust"] else "mean/std")
                          + f" of the same hour over the previous {cfg['baseline_days']} days (current hour excluded)"
                          + ("; weekday-adjusted" if cfg["weekday_adjust"] else "")
                          + (f"; spread pooled over +/-{cfg['pool_h']} h" if cfg["pool_h"] else "")
                          + ("; flagged hours excluded from later baselines" if cfg["exclude_flagged"] else ""),
        "z_threshold": cfg["z_threshold"], "baseline_days": cfg["baseline_days"],
        "std_floor": f"{cfg['std_floor_frac']:.0%} of baseline mean",
        "forecast": "Holt-Winters: additive level, damped additive trend, additive 24 h season",
        "forecast_fit_days": cfg["fit_days"], "horizon_h": cfg["horizon_h"],
        "forecast_method_used": methods,
        "band": "yhat +/- 1.96 x robust residual sigma (1.4826 x MAD); approximate, constant width",
        "band_sigma": sigmas,
        "compound_rule": f">= {cfg['compound_min_metrics']} metrics with >= {cfg['compound_min_hours']} "
                         f"anomalous hour(s) on the same calendar day",
        "forecast_risk_rule": f"next-24 h forecast peak > {cfg['forecast_margin']:.2f} x the median daily "
                              f"peak of the last 7 days",
        "incident_rule": f"consecutive anomalous hours of one metric form one incident "
                         f"(gaps up to {cfg['incident_gap_h']} h bridged)",
        "active_window_h": cfg["recent_hours"],
        "scorecard": sc["method"],
        "timing_ms": {"anomaly": round((t1 - t0) * 1000), "forecast": round((t2 - t1) * 1000),
                      "risk_and_score": round((t3 - t2) * 1000)},
    }
    return AnalyticsResult(an, fc, comp, events, sc, params)
