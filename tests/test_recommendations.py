"""Phase 2 (P3): templates, Claude path, every failure path, JSON validation, cache, ranking."""
import json
import threading
import time

import pandas as pd
import pytest

import facility.recommendations.generator as G
from facility.contracts import RiskEvent, RiskType, Severity
from facility.data.profile import FACILITY_PROFILE
from facility.recommendations.templates import TEMPLATES, template_for
from facility.analytics.risk_events import evidence

T0 = pd.Timestamp("2026-08-29 14:00")


def ev(rt=RiskType.WATER_SURGE, sev=Severity.HIGH, direction="above", start=T0, source="anomaly", **kw):
    metric = {"energy_spike": "energy_kwh", "water_surge": "water_kl", "waste_buildup": "waste_kg",
              "forecast_peak": "energy_kwh", "compound": "energy_kwh"}[rt.value]
    e = evidence(metric=metric, observed=30.9, expected=11.0, z_score=26.0, threshold=4.0, unit="kL",
                 direction=direction, hours=5, **kw)
    if rt == RiskType.FORECAST_PEAK:
        e.update(forecast_peak=590.0, forecast_peak_at=T0 + pd.Timedelta(hours=20), observed=None, z_score=None)
        source = "forecast"
    if rt == RiskType.COMPOUND:
        e.update(detail={"energy_kwh": {"hours": 6, "max_abs_z": 11.0}, "water_kl": {"hours": 5, "max_abs_z": 26.0}})
        source = "compound"
    ms = ("energy_kwh", "water_kl") if rt == RiskType.COMPOUND else (metric,)
    return RiskEvent(f"{rt.value}:{'+'.join(ms)}:{start:%Y%m%d%H}", rt, ms, start, start + pd.Timedelta(hours=4),
                     sev, source, e)


GOOD = '{"action": "Close the ward B valve and check the laundry line; flow is 2.8x normal.", ' \
       '"assumption": "No scheduled tank cleaning today."}'


@pytest.fixture
def llm(monkeypatch):
    """Replace the network call. Usage: llm(text) or llm(exception)."""
    calls = []

    def install(result):
        def fake(system, prompt, timeout_s):
            calls.append(json.loads(prompt))
            if isinstance(result, BaseException):
                raise result
            return result
        monkeypatch.setattr(G, "_call_llm", fake)
        return calls
    return install


# ------------------------------------------------------------------ templates
@pytest.mark.parametrize("rt", list(RiskType))
@pytest.mark.parametrize("direction", ["above", "below"])
def test_every_template_renders(rt, direction):
    t = template_for(ev(rt, direction=direction))
    assert t["title"] and t["action"] and t["assumption"] and t["roles"]
    assert "{" not in t["action"] + t["title"]


def test_template_uses_evidence_numbers():
    t = template_for(ev())
    assert "2.81x" in t["action"] and "30.9" in t["action"] and "kL" in t["action"]


def test_below_variant():
    assert template_for(ev(RiskType.WATER_SURGE, direction="below"))["title"] == "Unusual drop in water supply"


def test_template_survives_missing_evidence():
    e = RiskEvent("x", RiskType.ENERGY_SPIKE, ("energy_kwh",), T0, T0, Severity.LOW, "anomaly", evidence())
    assert "n/a" in template_for(e)["action"]


def test_all_risk_types_have_templates():
    assert set(TEMPLATES) == set(RiskType)


# ------------------------------------------------------------------ paths
def test_template_path_when_llm_disabled(llm):
    calls = llm(RuntimeError("must not be called"))
    r = G.recommend(ev(), FACILITY_PROFILE, use_llm=False)
    assert r.source == "template" and r.fallback_reason == "AI disabled" and not calls
    assert r.priority == 1 and r.severity == "high" and r.roles == ("ops", "sustainability")


def test_successful_llm_path(llm):
    calls = llm(GOOD)
    r = G.recommend(ev(), FACILITY_PROFILE)
    assert r.source == "llm" and r.fallback_reason == ""
    assert r.action.startswith("Close the ward B valve") and r.assumption == "No scheduled tank cleaning today."
    assert r.title == "Water use above normal" and r.priority == 1
    p = calls[0]
    assert p["risk_type"] == "water_surge" and p["evidence"]["observed"] == 30.9 and p["facility"]["beds"] == 200


@pytest.mark.parametrize("text", [
    "```json\n" + GOOD + "\n```",
    "Here is the recommendation:\n" + GOOD + "\nThanks!",
])
def test_llm_json_wrapped_in_prose_is_accepted(llm, text):
    llm(text)
    assert G.recommend(ev(), FACILITY_PROFILE).source == "llm"


@pytest.mark.parametrize("text, reason", [
    ("Sorry, I cannot help.", "invalid JSON (no object found)"),
    ('{"action": "x", "assumption": }', "invalid JSON"),
    ('{"action": "Do it."}', "invalid JSON (missing 'assumption')"),
    ('{"action": "", "assumption": "y"}', "invalid JSON (missing 'action')"),
    ('{"action": 5, "assumption": "y"}', "invalid JSON (missing 'action')"),
    ('{"action": "' + "word " * 80 + '", "assumption": "y"}', "invalid JSON ('action' too long)"),
    ('[1, 2]', "invalid JSON (no object found)"),
])
def test_invalid_json_falls_back(llm, text, reason):
    llm(text)
    r = G.recommend(ev(), FACILITY_PROFILE)
    assert r.source == "template" and r.fallback_reason == reason
    assert r.action == template_for(ev())["action"]


def test_missing_api_key_falls_back(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = G.recommend(ev(), FACILITY_PROFILE)
    assert r.source == "template" and r.fallback_reason == "no API key"


@pytest.mark.parametrize("exc, reason", [
    (G.LLMUnavailable("timeout"), "timeout"),
    (G.LLMUnavailable("network error"), "network error"),
    (G.LLMUnavailable("invalid API key"), "invalid API key"),
    (ValueError("sdk exploded"), "unexpected error (ValueError)"),
    (KeyError("content"), "unexpected error (KeyError)"),
])
def test_failures_fall_back(llm, exc, reason):
    llm(exc)
    r = G.recommend(ev(), FACILITY_PROFILE)
    assert r.source == "template" and r.fallback_reason == reason


def test_sdk_error_mapping(monkeypatch):
    """Exercise the real _call_llm with a fake anthropic client (no network)."""
    import anthropic
    try:
        import httpx
    except ImportError:  # some environments ship the SDK on an httpx fork
        httpx = pytest.importorskip("httpx2")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")

    class FakeMessages:
        def __init__(self, exc): self.exc = exc
        def create(self, **kw): raise self.exc

    for exc, reason in [(anthropic.APITimeoutError(request=req), "timeout"),
                        (anthropic.APIConnectionError(request=req), "network error")]:
        monkeypatch.setattr(anthropic, "Anthropic",
                            lambda **kw: type("C", (), {"messages": FakeMessages(exc)})())
        with pytest.raises(G.LLMUnavailable, match=reason):
            G._call_llm("s", "p", 1.0)


def test_real_call_llm_success_with_fake_client(monkeypatch):
    import anthropic
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    seen = {}

    class Msg:
        content = [type("B", (), {"text": GOOD})()]

    class FakeMessages:
        def create(self, **kw):
            seen.update(kw)
            return Msg()

    def fake_client(**kw):
        seen["client"] = kw
        return type("C", (), {"messages": FakeMessages()})()
    monkeypatch.setattr(anthropic, "Anthropic", fake_client)
    r = G.recommend(ev(), FACILITY_PROFILE)
    assert r.source == "llm"
    assert seen["client"]["max_retries"] == 0 and seen["client"]["timeout"] == G.cfg.LLM_TIMEOUT_S
    assert seen["model"] == G.cfg.LLM_MODEL and "ONLY a JSON object" in seen["system"]


def test_cache_hit_avoids_second_call(llm):
    calls = llm(GOOD)
    a = G.recommend(ev(), FACILITY_PROFILE)
    b = G.recommend(ev(start=T0 + pd.Timedelta(hours=1)), FACILITY_PROFILE)   # same evidence, new id
    assert len(calls) == 1 and a.action == b.action and b.risk_id != a.risk_id
    assert G.STATS["cache_hits"] == 1


def test_cache_misses_when_evidence_changes(llm):
    calls = llm(GOOD)
    G.recommend(ev(), FACILITY_PROFILE)
    e2 = ev()
    e2.evidence["observed"] = 45.0
    G.recommend(e2, FACILITY_PROFILE)
    assert len(calls) == 2


def test_failures_are_not_cached(llm):
    llm(G.LLMUnavailable("timeout"))
    G.recommend(ev(), FACILITY_PROFILE)
    calls = llm(GOOD)
    assert G.recommend(ev(), FACILITY_PROFILE).source == "llm" and len(calls) == 2   # retried, not cached


# ------------------------------------------------------------------ recommend_all
def test_recommend_all_ranks_and_caps_llm(llm):
    calls = llm(GOOD)
    events = [ev(RiskType.FORECAST_PEAK, Severity.HIGH), ev(RiskType.WATER_SURGE, Severity.HIGH),
              ev(RiskType.WASTE_BUILDUP, Severity.LOW), ev(RiskType.COMPOUND, Severity.MEDIUM),
              ev(RiskType.ENERGY_SPIKE, Severity.MEDIUM)]
    recs = G.recommend_all(events, FACILITY_PROFILE, max_llm=2)
    assert [r.priority for r in recs] == [1, 1, 2, 2, 3]
    assert recs[0].title == "Water use above normal"          # live incident before forecast
    assert [r.source for r in recs] == ["llm", "llm", "template", "template", "template"]
    assert len(calls) == 2
    assert all(r.assumption for r in recs)


def test_recommend_all_empty():
    assert G.recommend_all([], FACILITY_PROFILE) == []


def test_llm_calls_run_concurrently(monkeypatch):
    def slow(system, prompt, timeout_s):
        time.sleep(0.5)
        return GOOD
    monkeypatch.setattr(G, "_call_llm", slow)
    events = [ev(start=T0 + pd.Timedelta(hours=i), sev=Severity.HIGH) for i in range(3)]
    for i, e in enumerate(events):
        e.evidence["observed"] = 30.0 + i                      # distinct cache keys
    t = time.perf_counter()
    recs = G.recommend_all(events, FACILITY_PROFILE, max_llm=3)
    assert time.perf_counter() - t < 1.2 and all(r.source == "llm" for r in recs)


def test_recommend_never_raises_even_if_template_breaks(monkeypatch):
    monkeypatch.setattr(G, "template_for", lambda e: (_ for _ in ()).throw(RuntimeError("bad template")))
    r = G.recommend(ev(), FACILITY_PROFILE)
    assert r.source == "template" and r.fallback_reason.startswith("template error")


def test_thread_safety_of_cache(llm):
    llm(GOOD)
    errs = []

    def worker():
        try:
            for _ in range(20):
                G.recommend(ev(), FACILITY_PROFILE)
        except Exception as exc:  # pragma: no cover
            errs.append(exc)
    th = [threading.Thread(target=worker) for _ in range(8)]
    [t.start() for t in th]
    [t.join() for t in th]
    assert not errs
