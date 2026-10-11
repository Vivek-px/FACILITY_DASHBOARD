"""Load, validate and (if missing) regenerate the facility dataset.

The validator is the contract guard between P1 and P2: any drift in schema fails
loudly here with a readable message instead of producing wrong analytics later.
"""
import os

import pandas as pd

import facility.config as cfg
from facility.contracts import INDEX_NAME, METRICS
from facility.data.generator import generate_facility_data


def validate_facility_data(df, min_days=cfg.MIN_DAYS):
    """Raise ValueError with a specific message if df breaks the data contract."""
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Expected a pandas DataFrame")
    missing = set(METRICS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {sorted(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("Index must be a DatetimeIndex")
    if df.index.tz is not None:
        raise ValueError("Index must be timezone-naive")
    if df.index.name != INDEX_NAME:
        raise ValueError(f"Index must be named '{INDEX_NAME}'")
    for m in METRICS:
        if not pd.api.types.is_numeric_dtype(df[m]):
            raise ValueError(f"Column {m} must be numeric")
    if df[list(METRICS)].isna().any().any():
        raise ValueError("NaN values found")
    if (df[list(METRICS)] < 0).any().any():
        raise ValueError("Negative values found")
    if df.index.has_duplicates:
        raise ValueError("Duplicate timestamps found")
    if not df.index.is_monotonic_increasing:
        raise ValueError("Index not sorted")
    expected = pd.date_range(df.index[0], df.index[-1], freq="h")
    if len(expected) != len(df) or not (df.index == expected).all():
        raise ValueError("Index is not continuous hourly (gap found)")
    if len(df) < min_days * 24:
        raise ValueError(f"Need at least {min_days} days of data, got {len(df) / 24:.1f}")


def _write_dataset(path):
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    df, log = generate_facility_data(days=cfg.DAYS, seed=cfg.SEED, start=cfg.START_DATE)
    df.to_csv(path)
    log.to_csv(os.path.join(folder, "injected_anomalies.csv"), index=False)


def load_facility_data(path=None, regenerate_if_missing=True):
    path = path or cfg.DATA_PATH
    if not os.path.exists(path):
        if not regenerate_if_missing:
            raise FileNotFoundError(path)
        _write_dataset(path)
    df = pd.read_csv(path, index_col=INDEX_NAME, parse_dates=True)
    df = df[list(METRICS)].astype(float)
    df.index.freq = "h"
    validate_facility_data(df)
    return df


def load_ground_truth(path=None):
    """Ground-truth log of injected anomalies (empty frame if unavailable)."""
    path = path or cfg.GROUND_TRUTH_PATH
    cols = ["metric", "start", "end", "kind", "magnitude"]
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)
    return pd.read_csv(path, parse_dates=["start", "end"])
