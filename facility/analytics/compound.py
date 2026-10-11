"""Rules-based compound risk (PRD §7.2, decision A4).

A metric is 'anomalous on a day' if it has >= min_hours anomalous hours that day.
A day with >= min_metrics anomalous metrics is a compound day - a stated stand-in for
a learned multivariate correlation model (PRD scope decision, not a hidden shortcut).
"""
import numpy as np
import pandas as pd

COLUMNS = ["date", "metrics", "n_metrics", "severity"]


def find_compound_days(anomalies, min_metrics=2, min_hours=1):
    a = anomalies[anomalies.is_anomaly]
    if a.empty:
        return pd.DataFrame(columns=COLUMNS)
    a = a.assign(date=a.timestamp.dt.normalize())
    per = a.groupby(["date", "metric"]).size().reset_index(name="hours")
    per = per[per.hours >= min_hours]
    out = (per.groupby("date")
              .agg(metrics=("metric", lambda s: sorted(s)), n_metrics=("metric", "nunique"))
              .reset_index())
    out = out[out.n_metrics >= min_metrics].copy()
    if out.empty:
        return pd.DataFrame(columns=COLUMNS)
    out["severity"] = np.where(out.n_metrics >= 3, "high", "medium")
    return out[COLUMNS].reset_index(drop=True)
