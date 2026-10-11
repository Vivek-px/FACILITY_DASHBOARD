"""MVP decision-support score (decision A6). NOT a validated sustainability rating.

metric score = 100 - 40*min(1, anomaly_hours_7d/24) - 60*min(1, max(0, vs_baseline_pct)/30)
vs_baseline_pct = mean(last 7 days) / mean(the 21 days before) - 1, in %
overall = mean(metric scores) - 10 * compound days in last 7 days, clipped to 0..100
"""
import pandas as pd

from facility.contracts import METRICS

METHOD = ("MVP decision-support score, not a certified rating. "
          "Metric score = 100 - 40 x min(1, anomaly hours in last 7 days / 24) "
          "- 60 x min(1, max(0, % change of last 7 days vs the 21 days before) / 30). "
          "Overall = mean of metric scores - 10 per compound day in the last 7 days, clipped to 0-100.")


def metric_score(anomaly_hours, vs_pct):
    return 100 - 40 * min(1.0, anomaly_hours / 24) - 60 * min(1.0, max(0.0, vs_pct) / 30)


def compute_scorecard(df, anomalies, compound):
    now = df.index[-1]
    week = now - pd.Timedelta(days=7)
    metrics = {}
    for m in METRICS:
        n = int(((anomalies.metric == m) & anomalies.is_anomaly & (anomalies.timestamp > week)).sum())
        last7 = df[m].iloc[-168:].mean()
        prev = df[m].iloc[-168 - 504:-168].mean()
        vs = float((last7 / prev - 1) * 100) if prev > 0 else 0.0
        metrics[m] = {"score": round(metric_score(n, vs)), "anomaly_hours_7d": n,
                      "vs_baseline_pct": round(vs, 1),
                      "anomaly_penalty": round(40 * min(1.0, n / 24), 1),
                      "trend_penalty": round(60 * min(1.0, max(0.0, vs) / 30), 1)}
    ncomp = int((compound.date > week.normalize()).sum()) if len(compound) else 0
    mean_score = sum(v["score"] for v in metrics.values()) / len(metrics)
    overall = max(0.0, min(100.0, mean_score - 10 * ncomp))
    return {"overall": round(overall), "metric_mean": round(mean_score, 1), "compound_days_7d": ncomp,
            "compound_penalty": 10 * ncomp, "metrics": metrics, "method": METHOD}
