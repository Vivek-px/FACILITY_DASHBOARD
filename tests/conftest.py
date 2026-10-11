import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ["FACILITY_USE_LLM"] = "0"

from facility.data.generator import generate_facility_data  # noqa: E402
from facility.data.loader import load_facility_data  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "sample_facility_data.csv")


@pytest.fixture(scope="session")
def fixture_df():
    return load_facility_data(FIXTURE, regenerate_if_missing=False)


@pytest.fixture(scope="session")
def full():
    """(df, ground_truth_log) - the 60-day demo dataset, generated in memory."""
    return generate_facility_data(days=60, seed=42, start="2026-07-01")


@pytest.fixture(scope="session")
def full_result(full):
    from facility.pipeline import run_pipeline
    return run_pipeline(full[0])


@pytest.fixture(autouse=True)
def _clean_llm_cache():
    from facility.recommendations import generator
    generator.clear_cache()
    yield
    generator.clear_cache()


def flat_series(days=21, value=100.0, start="2026-07-01"):
    idx = pd.date_range(start, periods=days * 24, freq="h", name="timestamp")
    return idx, value
