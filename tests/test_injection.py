"""Phase 2 (P1): live injection, scenarios, declarative state (reset / no compounding)."""
import numpy as np
import pandas as pd
import pytest

from facility.data.injection import inject_anomaly
from facility.data.scenarios import SCENARIOS, apply_scenario
from facility.data.state import add_injection, build_working_df


def test_original_unchanged(fixture_df):
    before = fixture_df.copy(deep=True)
    new, ev = inject_anomaly(fixture_df, "energy_kwh")
    pd.testing.assert_frame_equal(fixture_df, before)
    assert new is not fixture_df


def test_spike_changes_only_window(fixture_df):
    new, ev = inject_anomaly(fixture_df, "water_kl", hours=4, magnitude=3.0)
    diff = new.ne(fixture_df)
    assert diff["water_kl"].sum() == 4 and not diff[["energy_kwh", "waste_kg"]].any().any()
    assert np.allclose(new.water_kl.iloc[-4:], fixture_df.water_kl.iloc[-4:] * 3.0)
    assert ev.start == fixture_df.index[-4] and ev.hours == 4 and ev.kind == "spike"


def test_drop_and_drift(fixture_df):
    d, _ = inject_anomaly(fixture_df, "energy_kwh", hours=5, magnitude=2.0, kind="drop")
    assert np.allclose(d.energy_kwh.iloc[-5:], fixture_df.energy_kwh.iloc[-5:] / 2.0)
    r, _ = inject_anomaly(fixture_df, "waste_kg", hours=5, magnitude=2.0, kind="drift")
    ratio = (r.waste_kg.iloc[-5:] / fixture_df.waste_kg.iloc[-5:]).values
    assert np.allclose(ratio, np.linspace(1, 2, 5))


def test_explicit_start(fixture_df):
    s = fixture_df.index[200]
    new, ev = inject_anomaly(fixture_df, "energy_kwh", hours=3, start=s)
    assert new.ne(fixture_df).energy_kwh.sum() == 3 and ev.start == s


@pytest.mark.parametrize("kw", [dict(metric="gas"), dict(metric="energy_kwh", kind="boom"),
                                dict(metric="energy_kwh", hours=0), dict(metric="energy_kwh", magnitude=0),
                                dict(metric="energy_kwh", start="1999-01-01")])
def test_invalid_injection(fixture_df, kw):
    with pytest.raises(ValueError):
        inject_anomaly(fixture_df, **kw)


def test_recipe_is_idempotent(fixture_df):
    inj = add_injection((), "energy_kwh")
    a, _ = build_working_df(fixture_df, None, inj)
    b, _ = build_working_df(fixture_df, None, inj)   # a "rerun"
    pd.testing.assert_frame_equal(a, b)


def test_reinjecting_same_metric_replaces_not_compounds(fixture_df):
    once = add_injection((), "energy_kwh", magnitude=2.5)
    twice = add_injection(once, "energy_kwh", magnitude=2.5)
    assert once == twice
    a, _ = build_working_df(fixture_df, None, twice)
    assert np.allclose(a.energy_kwh.iloc[-6:], fixture_df.energy_kwh.iloc[-6:] * 2.5)


def test_different_metrics_coexist(fixture_df):
    inj = add_injection(add_injection((), "energy_kwh"), "water_kl")
    df, events = build_working_df(fixture_df, None, inj)
    assert len(events) == 2 and df.ne(fixture_df)[["energy_kwh", "water_kl"]].any().all()


def test_reset_restores_base(fixture_df):
    df, _ = build_working_df(fixture_df, "heatwave", add_injection((), "water_kl"))
    assert not df.equals(fixture_df)
    reset, events = build_working_df(fixture_df, None, ())
    pd.testing.assert_frame_equal(reset, fixture_df)
    assert events == []


@pytest.mark.parametrize("sid, metric", [("heatwave", "energy_kwh"), ("pipe_leak", "water_kl"),
                                         ("missed_pickup", "waste_kg")])
def test_scenarios_touch_only_their_metric(fixture_df, sid, metric):
    before = fixture_df.copy(deep=True)
    new = apply_scenario(fixture_df, sid)
    pd.testing.assert_frame_equal(fixture_df, before)
    changed = new.ne(fixture_df)
    assert changed[metric].sum() > 0
    assert not changed.drop(columns=[metric]).any().any()
    assert (new[metric] >= fixture_df[metric] - 1e-9).all()


def test_scenario_hours():
    idx = pd.date_range("2026-07-01", periods=21 * 24, freq="h", name="timestamp")
    base = pd.DataFrame({"energy_kwh": 100.0, "water_kl": 10.0, "waste_kg": 5.0}, index=idx)
    hw = apply_scenario(base, "heatwave")
    hot = hw.energy_kwh.ne(base.energy_kwh)
    assert set(hw.index[hot].hour) == set(range(12, 18)) and hot.sum() == 18
    leak = apply_scenario(base, "pipe_leak").water_kl.ne(base.water_kl)
    assert set(base.index[leak].hour) == set(range(0, 6)) and leak.sum() == 12


def test_unknown_scenario(fixture_df):
    with pytest.raises(ValueError):
        apply_scenario(fixture_df, "earthquake")
    assert set(SCENARIOS) == {"heatwave", "pipe_leak", "missed_pickup"}
