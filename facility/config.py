"""Shared tunables. SHARED FILE: change via PR approved by all three owners.

Values marked (tuned) were chosen with `python scripts/tune_threshold.py`; the results
table is in README.md. Change them only with a new tuning run.
"""
# --- data -------------------------------------------------------------------
SEED = 42
START_DATE = "2026-07-01"
DAYS = 60
MIN_DAYS = 14                      # validator: 7-day baseline + Holt-Winters warm-up
DATA_PATH = "data/facility_data.csv"
GROUND_TRUTH_PATH = "data/injected_anomalies.csv"

# --- anomaly detection (A3) ---------------------------------------------------
BASELINE_DAYS = 7
Z_THRESHOLD = 4.5                  # (tuned; PDF default 3.0, see README results table)
STD_FLOOR_FRAC = 0.02              # std floor = 2% of |baseline mean|
ROBUST_BASELINE = False            # median/MAD instead of mean/std
WEEKDAY_ADJUST = True              # (tuned) deviation D2
POOL_HOURS = 1                     # (tuned) deviation D2
EXCLUDE_FLAGGED = True             # (tuned) deviation D3

# --- forecasting (A2) ---------------------------------------------------------
HORIZON_H = 24
SEASONAL_PERIODS = 24
FIT_DAYS = 28
FORECAST_MARGIN = 1.10             # deviation D5: peak > 1.10 x median daily peak of last 7 days

# --- risk events (A4) ---------------------------------------------------------
RECENT_HOURS = 72                  # only incidents ending in the last 72 h are active
COMPOUND_MIN_METRICS = 2
COMPOUND_MIN_HOURS = 1
INCIDENT_GAP_H = 2                 # bridge gaps of <= 2 unflagged hours inside one incident

# --- recommendations (A9, A12) ---------------------------------------------------
import os
USE_LLM = os.getenv("FACILITY_USE_LLM", "1") != "0"   # tests/CI set FACILITY_USE_LLM=0
LLM_MODEL = "claude-haiku-4-5-20251001"
LLM_TIMEOUT_S = 4.0
LLM_MAX_TOKENS = 300
MAX_LLM_CALLS = 3
PRECOMPUTE_SCENARIOS = True       # warm the analytics cache for the 3 scenarios at app start
