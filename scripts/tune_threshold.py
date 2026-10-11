"""Tune the anomaly detector against ground truth AND the demo scenarios.

Run from repo root:  python scripts/tune_threshold.py
For every configuration it reports:
  recall / precision / false-positive rate - averaged over 5 generator seeds
      (guards against tuning to one lucky dataset),
  cov_*  - share of the modified hours flagged for each demo scenario / live injection
      on the demo dataset (seed 42). A detector that misses the heatwave is useless on stage.
Selection rule: recall >= 0.8 and every cov_* >= 0.7 (a scenario must be clearly visible
on stage, not borderline), then highest precision.
"""
import _path  # noqa: F401

import itertools

import numpy as np
import pandas as pd

import facility.config as C
from facility.analytics.anomaly import detect_anomalies
from facility.data.generator import generate_facility_data
from facility.data.injection import inject_anomaly
from facility.data.scenarios import apply_scenario
from facility.pipeline import evaluate_detection

SEEDS = (42, 1, 2, 3, 4)


def demo_cases(base):
    """name -> (modified df, metric, boolean mask of modified hours)"""
    cases = {}
    for sid, metric in (("heatwave", "energy_kwh"), ("pipe_leak", "water_kl"), ("missed_pickup", "waste_kg")):
        df = apply_scenario(base, sid)
        cases[sid] = (df, metric, (df[metric] != base[metric]).to_numpy())
    for metric in ("energy_kwh", "water_kl", "waste_kg"):
        df = inject_anomaly(base, metric)[0]
        cases[f"inject_{metric.split('_')[0]}"] = (df, metric, (df[metric] != base[metric]).to_numpy())
    return cases


def coverage(cases, kw):
    out = {}
    for name, (df, metric, mask) in cases.items():
        a = detect_anomalies(df, **kw)
        flags = a[a.metric == metric].is_anomaly.to_numpy()
        # the missed-pickup ramp starts at x1.0, so only count hours changed by > 25%
        out[f"cov_{name}"] = round(float(flags[mask].mean()), 2) if mask.any() else 0.0
    return out


def main():
    data = {s: generate_facility_data(days=C.DAYS, seed=s, start=C.START_DATE) for s in SEEDS}
    cases = demo_cases(data[42][0])
    rows = []
    grid = itertools.product((False, True), (0, 1), (False, True), (3.0, 3.5, 4.0, 4.5, 5.0))
    for wa, pool, ex, z in grid:
        kw = dict(baseline_days=C.BASELINE_DAYS, z_threshold=z, weekday_adjust=wa, pool_h=pool,
                  exclude_flagged=ex)
        evs = [evaluate_detection(detect_anomalies(df, **kw), log) for df, log in data.values()]
        cov = coverage(cases, kw)
        rows.append({"wkday": wa, "pool": pool, "excl": ex, "z": z,
                     "recall": round(np.mean([e["recall"] for e in evs]), 3),
                     "precision": round(np.mean([e["precision"] for e in evs]), 3),
                     "fp_%": round(np.mean([100 * e["false_positive_hours"] / (C.DAYS * 72) for e in evs]), 2),
                     **cov})
    t = pd.DataFrame(rows)
    covcols = [c for c in t if c.startswith("cov_")]
    t["ok"] = (t.recall >= 0.8) & (t[covcols] >= 0.7).all(axis=1)
    pd.set_option("display.width", 250)
    print(t.to_string(index=False))
    ok = t[t.ok]
    if len(ok):
        best = ok.sort_values(["precision", "z"], ascending=[False, True]).iloc[0]
        print("\nSelected:", best[["wkday", "pool", "excl", "z", "recall", "precision", "fp_%"]].to_dict())
    else:
        print("\nNo configuration meets the rule - raise scenario magnitudes or revisit the detector.")


if __name__ == "__main__":
    main()
