"""Live check of the Claude path (needs ANTHROPIC_API_KEY and internet).

Run:  python scripts/smoke_llm.py
Expected: 'source=llm' lines with plain-language actions; a second pass served from cache.
If you see 'source=template reason=...', the reason tells you exactly what failed.
"""
import _path  # noqa: F401

import time

from facility.data.loader import load_facility_data
from facility.data.profile import FACILITY_PROFILE
from facility.pipeline import run_pipeline
from facility.recommendations import generator as G

res = run_pipeline(load_facility_data())
for attempt in (1, 2):
    t = time.perf_counter()
    recs = G.recommend_all(res.risk_events, FACILITY_PROFILE, use_llm=True)
    print(f"--- pass {attempt}: {time.perf_counter() - t:.2f} s  stats={G.STATS}")
    for r in recs:
        print(f"source={r.source:8s} reason={r.fallback_reason or '-':18s} {r.title}\n    action: {r.action}\n"
              f"    assumption: {r.assumption}")
