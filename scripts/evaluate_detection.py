"""Measure the detector against the injected ground truth (paste the table into README).

Run from anywhere:  python scripts/evaluate_detection.py
"""
import _path  # noqa: F401

import pandas as pd

import facility.config as C
from facility.analytics.engine import DEFAULTS
from facility.analytics.anomaly import detect_anomalies
from facility.data.loader import load_facility_data, load_ground_truth
from facility.pipeline import evaluate_detection

df, log = load_facility_data(), load_ground_truth()
rows = []
for z in (3.0, 3.5, 4.0, 4.5, 5.0):
    a = detect_anomalies(df, C.BASELINE_DAYS, z, C.STD_FLOOR_FRAC, C.ROBUST_BASELINE, C.WEEKDAY_ADJUST,
                         C.POOL_HOURS, C.EXCLUDE_FLAGGED)
    q = evaluate_detection(a, log)
    rows.append({"z_threshold": z, "recall": q["recall"], "precision": q["precision"],
                 "flagged_hours": q["flagged_hours"], "false_positive_hours": q["false_positive_hours"],
                 "selected": "<-" if z == C.Z_THRESHOLD else ""})
t = pd.DataFrame(rows)
try:
    print(t.to_markdown(index=False))      # needs the optional 'tabulate' package
except ImportError:
    print(t.to_string(index=False))
