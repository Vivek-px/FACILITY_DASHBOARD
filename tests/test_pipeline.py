"""Phase 3 (P1): end-to-end integration - data -> analytics -> risk -> recommendation -> scorecard."""
import time

import pandas as pd
import pytest

from dashboard.insights import headline, status, why
from dashboard.roles import split_for_role
from facility.contracts import EVIDENCE_KEYS, ROLES, RiskType
from facility.data.profile import FACILITY_PROFILE
from facility.data.state import add_injection, build_working_df
from facility.mocks import mock_analytics_result
from facility.pipeline import evaluate_detection, run_pipeline
from facility.recommendations.generator import recommend_all


def _loop(base, scenario=None, injections=()):
    df, _ = build_working_df(base, scenario, injections)
    res = run_pipeline(df)
    recs = recommend_all(res.risk_events, FACILITY_PROFILE, use_llm=False)
    return df, res, recs


def test_full_chain_fixture_under_3s(fixture_df):
    t = time.perf_counter()
    df, res, recs = _loop(fixture_df)
    assert time.perf_counter() - t < 3
    assert len(recs) == len(res.risk_events) and all(r.assumption for r in recs)


def test_live_injection_loop_under_3s_on_full_data(full):
    base = full[0]
    t = time.perf_counter()
    df, res, recs = _loop(base, injections=add_injection((), "energy_kwh"))
    elapsed = time.perf_counter() - t
    assert elapsed < 3, f"recompute took {elapsed:.2f}s"


def test_injection_changes_everything_the_judge_sees(full, full_result):
    base = full[0]
    df, res, recs = _loop(base, injections=add_injection((), "energy_kwh"))
    # detection
    new = res.anomalies[(res.anomalies.metric == "energy_kwh") & res.anomalies.is_anomaly]
    assert (new.timestamp >= base.index[-6]).sum() == 6
    # risk event + recommendation
    spikes = [e for e in res.risk_events if e.risk_type == RiskType.ENERGY_SPIKE and e.end == base.index[-1]]
    assert len(spikes) == 1 and spikes[0].severity.value == "high"
    assert any(r.risk_id == spikes[0].risk_id and "Electricity" in r.action for r in recs)
    # scorecard
    assert res.scorecard["metrics"]["energy_kwh"]["score"] < full_result.scorecard["metrics"]["energy_kwh"]["score"]
    assert res.scorecard["overall"] < full_result.scorecard["overall"]
    # forecast (chart input)
    f_new = res.forecasts[res.forecasts.metric == "energy_kwh"].yhat.max()
    f_old = full_result.forecasts[full_result.forecasts.metric == "energy_kwh"].yhat.max()
    assert f_new > f_old


def test_reset_restores_identical_results(full, full_result):
    base = full[0]
    _loop(base, "heatwave", add_injection((), "water_kl"))
    df, res, _ = _loop(base)
    pd.testing.assert_frame_equal(df, base)
    assert [e.risk_id for e in res.risk_events] == [e.risk_id for e in full_result.risk_events]
    assert res.scorecard == full_result.scorecard


@pytest.mark.parametrize("sid, rt, metric", [
    ("heatwave", RiskType.ENERGY_SPIKE, "energy_kwh"),
    ("pipe_leak", RiskType.WATER_SURGE, "water_kl"),
    ("missed_pickup", RiskType.WASTE_BUILDUP, "waste_kg"),
])
def test_each_scenario_produces_its_risk(full, full_result, sid, rt, metric):
    df, res, recs = _loop(full[0], sid)
    new_ids = {e.risk_id for e in res.risk_events} - {e.risk_id for e in full_result.risk_events}
    assert any(e.risk_type == rt and e.risk_id in new_ids for e in res.risk_events)
    assert res.scorecard["metrics"][metric]["score"] < full_result.scorecard["metrics"][metric]["score"]


def test_ground_truth_evaluation(full, full_result):
    q = evaluate_detection(full_result.anomalies, full[1])
    assert q["windows"] == 8 and q["recall"] == 1.0 and q["precision"] >= 0.7


def test_contract_between_p2_and_p3(full_result):
    for e in full_result.risk_events:
        assert set(e.evidence) == set(EVIDENCE_KEYS)
    for col in ("timestamp", "metric", "yhat", "yhat_lower", "yhat_upper"):
        assert col in full_result.forecasts


def test_mock_matches_contract():
    m = mock_analytics_result()
    recs = recommend_all(m.risk_events, FACILITY_PROFILE, use_llm=False)
    assert recs and set(m.risk_events[0].evidence) == set(EVIDENCE_KEYS)


def test_pipeline_rejects_bad_data(fixture_df):
    with pytest.raises(ValueError):
        run_pipeline(fixture_df.drop(columns=["waste_kg"]))


# ------------------------------------------------------------------ UI logic (pure functions)
def test_headline_and_status(full_result):
    h = headline(full_result.risk_events)
    assert h.startswith("Water is") and "forecast to peak" in h
    assert status(full_result.risk_events)[0] == "Action needed"
    assert "No active risks" in headline([]) and status([])[0] == "Normal"


def test_why_text_for_every_event_type(full):
    _, res, _ = _loop(full[0], "heatwave")
    kinds = {e.source for e in res.risk_events}
    assert kinds == {"anomaly", "forecast", "compound"}
    for e in res.risk_events:
        assert len(why(e, res.params)) > 40


@pytest.mark.parametrize("role", ROLES)
def test_role_split_is_a_partition(full, role):
    _, _, recs = _loop(full[0], "heatwave")
    mine, others = split_for_role(recs, role)
    assert len(mine) + len(others) == len(recs) and mine
    assert all(role in r.roles or (role == "admin" and r.severity == "high") for r in mine)


def test_admin_sees_every_high_risk(full):
    _, _, recs = _loop(full[0])
    mine, _ = split_for_role(recs, "admin")
    assert {r.risk_id for r in recs if r.severity == "high"} <= {r.risk_id for r in mine}
