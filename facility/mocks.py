"""Mock AnalyticsResult so the UI can be built before analytics exist (P2, Phase 0)."""
import numpy as np
import pandas as pd

from facility.analytics.risk_events import evidence
from facility.contracts import METRICS, UNITS, AnalyticsResult, RiskEvent, RiskType, Severity


def mock_analytics_result():
    now = pd.Timestamp("2026-08-29 23:00")
    fut = pd.date_range(now + pd.Timedelta(hours=1), periods=24, freq="h", name="timestamp")
    rows = []
    for m, base in zip(METRICS, (250, 12, 6)):
        y = base * (1 + 0.3 * np.sin(np.arange(24) / 24 * 2 * np.pi))
        rows.append(pd.DataFrame({"timestamp": fut, "metric": m, "yhat": y,
                                  "yhat_lower": y * 0.9, "yhat_upper": y * 1.1}))
    ev = RiskEvent("water_surge:water_kl:2026082914", RiskType.WATER_SURGE, ("water_kl",),
                   now - pd.Timedelta(hours=9), now - pd.Timedelta(hours=5), Severity.HIGH, "anomaly",
                   evidence(metric="water_kl", observed=30.1, expected=12.4, z_score=9.2, threshold=3.0,
                            unit=UNITS["water_kl"], direction="above", hours=5))
    sc = {"overall": 72, "metric_mean": 72.0, "compound_days_7d": 0, "compound_penalty": 0, "method": "mock",
          "metrics": {m: {"score": 72, "anomaly_hours_7d": 5, "vs_baseline_pct": 8.0,
                          "anomaly_penalty": 8.3, "trend_penalty": 16.0} for m in METRICS}}
    an = pd.DataFrame(columns=["timestamp", "metric", "value", "baseline_mean", "baseline_std",
                               "z_score", "is_anomaly"])
    cd = pd.DataFrame(columns=["date", "metrics", "n_metrics", "severity"])
    return AnalyticsResult(an, pd.concat(rows, ignore_index=True), cd, [ev], sc,
                           {"z_threshold": 3.0, "baseline_days": 7, "horizon_h": 24, "mock": True})
