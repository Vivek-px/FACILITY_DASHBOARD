"""Time the live loop the judge sees: inject -> analytics -> recommendations (templates).

Run:  python scripts/benchmark.py        (target: every line < 3 s, typically ~1 s)
"""
import _path  # noqa: F401

import time

from facility.data.loader import load_facility_data
from facility.data.profile import FACILITY_PROFILE
from facility.data.scenarios import SCENARIOS
from facility.data.state import add_injection, build_working_df
from facility.pipeline import run_pipeline
from facility.recommendations.generator import recommend_all

base = load_facility_data()
cases = [("original", None, ())] + [(f"scenario {s}", s, ()) for s in SCENARIOS] + \
        [(f"inject {m}", None, add_injection((), m)) for m in ("energy_kwh", "water_kl", "waste_kg")]
for name, sid, inj in cases:
    t = time.perf_counter()
    df, _ = build_working_df(base, sid, inj)
    res = run_pipeline(df)
    recs = recommend_all(res.risk_events, FACILITY_PROFILE, use_llm=False)
    dt = time.perf_counter() - t
    print(f"{name:28s} {dt:5.2f} s  risks={len(res.risk_events):2d}  score={res.scorecard['overall']:3d}  "
          f"timing_ms={res.params['timing_ms']}")
