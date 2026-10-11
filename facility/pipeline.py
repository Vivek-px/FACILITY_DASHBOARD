"""Integration layer (P1): data -> analytics, plus detection evaluation vs ground truth."""
import pandas as pd

from facility.analytics.engine import run_analytics
from facility.data.loader import validate_facility_data


def run_pipeline(df, config=None):
    validate_facility_data(df)
    return run_analytics(df, config)


def evaluate_detection(anomalies, log):
    """Window recall + hour precision against the injected ground truth.

    recall    = injected windows with >= 1 flagged hour / all windows   (generous by design)
    precision = flagged hours inside some injected window / all flagged hours (strict)
    Only windows that have a baseline (after the first 7 days) are counted.
    """
    flagged = anomalies[anomalies.is_anomaly]
    first_scored = anomalies.loc[anomalies.z_score.notna(), "timestamp"].min()
    log = log[log.start >= first_scored] if len(log) else log
    hits = 0
    for r in log.itertuples():
        hits += bool(((flagged.metric == r.metric) & (flagged.timestamp >= r.start)
                      & (flagged.timestamp <= r.end)).any())
    inside = pd.Series(False, index=flagged.index)
    for r in log.itertuples():
        inside |= (flagged.metric == r.metric) & (flagged.timestamp >= r.start) & (flagged.timestamp <= r.end)
    return {"recall": round(hits / max(1, len(log)), 3),
            "precision": round(float(inside.sum()) / max(1, len(flagged)), 3),
            "windows": int(len(log)), "windows_hit": int(hits), "flagged_hours": int(len(flagged)),
            "false_positive_hours": int((~inside).sum())}
