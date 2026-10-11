"""Phase 1 (P1): generator, ground truth, validator, loader."""
import numpy as np
import pandas as pd
import pytest

from facility.contracts import INDEX_NAME, METRICS
from facility.data.generator import SCHEDULE, generate_facility_data
from facility.data.loader import load_facility_data, validate_facility_data


def test_reproducible_same_seed():
    a, la = generate_facility_data(days=21)
    b, lb = generate_facility_data(days=21)
    pd.testing.assert_frame_equal(a, b)
    pd.testing.assert_frame_equal(la, lb)


def test_different_seed_differs():
    a, _ = generate_facility_data(days=21, seed=1)
    b, _ = generate_facility_data(days=21, seed=2)
    assert not a.equals(b)


def test_schema(full):
    df, log = full
    assert list(df.columns) == list(METRICS)
    assert df.index.name == INDEX_NAME and df.index.tz is None
    assert len(df) == 60 * 24 and (df.dtypes == float).all()
    assert (df > 0).all().all()
    validate_facility_data(df)


def test_ground_truth_log(full):
    df, log = full
    assert len(log) == len(SCHEDULE)
    assert list(log.columns) == ["metric", "start", "end", "kind", "magnitude"]
    last = log.sort_values("end").iloc[-1]
    assert last.end > df.index[-1] - pd.Timedelta(hours=24), "demo needs an anomaly in the last 24 h"


def test_daily_and_weekly_pattern(full):
    df, _ = full
    e = df["energy_kwh"]
    by_hour = e.groupby(e.index.hour).median()
    assert by_hour.loc[13] > 1.4 * by_hour.loc[3]              # OPD peak vs night
    by_dow = e.groupby(e.index.dayofweek).median()
    assert by_dow.loc[6] < 0.9 * by_dow.loc[2]                 # Sunday < Wednesday


def test_injected_window_is_multiplied():
    clean, _ = generate_facility_data(days=60, schedule=[])
    dirty, log = generate_facility_data(days=60)
    r = log.iloc[0]
    ratio = dirty.loc[r.start:r.end, r.metric] / clean.loc[r.start:r.end, r.metric]
    assert np.allclose(ratio, r.magnitude, rtol=1e-3)


@pytest.mark.parametrize("mutate, msg", [
    (lambda d: d.drop(columns=["water_kl"]), "Missing columns"),
    (lambda d: d.reset_index(), "DatetimeIndex"),
    (lambda d: d.tz_localize("Asia/Kolkata"), "timezone-naive"),
    (lambda d: d.rename_axis("time"), "named"),
    (lambda d: d.assign(energy_kwh=d.energy_kwh.where(d.index != d.index[50])), "NaN"),
    (lambda d: d.drop(d.index[100]), "continuous"),
    (lambda d: d.iloc[::-1], "sorted"),
    (lambda d: pd.concat([d, d.iloc[[5]]]).sort_index(), "Duplicate"),
    (lambda d: d.iloc[: 10 * 24], "at least"),
    (lambda d: d.assign(waste_kg=-1.0), "Negative"),
    (lambda d: d.assign(energy_kwh="x"), "numeric"),
])
def test_validator_rejects(fixture_df, mutate, msg):
    with pytest.raises(ValueError, match=msg):
        validate_facility_data(mutate(fixture_df.copy()))


def test_loader_regenerates_when_missing(tmp_path):
    p = tmp_path / "data" / "facility_data.csv"
    df = load_facility_data(str(p))
    assert p.exists() and (tmp_path / "data" / "injected_anomalies.csv").exists()
    assert len(df) == 60 * 24


def test_loader_raises_when_missing_and_no_regenerate(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_facility_data(str(tmp_path / "nope.csv"), regenerate_if_missing=False)


def test_csv_roundtrip_matches_generator(tmp_path, full):
    p = tmp_path / "d.csv"
    full[0].to_csv(p)
    back = load_facility_data(str(p), regenerate_if_missing=False)
    pd.testing.assert_frame_equal(back, full[0], check_freq=False)
