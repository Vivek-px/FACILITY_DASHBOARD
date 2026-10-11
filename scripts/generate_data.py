"""Write data/facility_data.csv, data/injected_anomalies.csv and the 21-day test fixture.

Run from anywhere:  python scripts/generate_data.py
"""
import _path  # noqa: F401  (must be first)

import os

import facility.config as C
from facility.data.generator import generate_facility_data

os.makedirs("data", exist_ok=True)
df, log = generate_facility_data(days=C.DAYS, seed=C.SEED, start=C.START_DATE)
df.to_csv(C.DATA_PATH)
log.to_csv(C.GROUND_TRUTH_PATH, index=False)
print(f"saved {C.DATA_PATH} {df.shape}  from {df.index[0]} to {df.index[-1]}")
print(f"saved {C.GROUND_TRUTH_PATH} ({len(log)} injected windows)")

os.makedirs("tests/fixtures", exist_ok=True)
fx, fx_log = generate_facility_data(days=21, seed=C.SEED, start=C.START_DATE)
fx.to_csv("tests/fixtures/sample_facility_data.csv")
fx_log.to_csv("tests/fixtures/sample_injected_anomalies.csv", index=False)
print(f"saved tests/fixtures/sample_facility_data.csv {fx.shape}")
