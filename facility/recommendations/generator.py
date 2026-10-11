"""Recommendation engine: deterministic template first, Claude rewrite second.

    RiskEvent --template_for()--> Recommendation(source="template")      always succeeds
              --Claude (optional)--> validated JSON --> Recommendation(source="llm")

The LLM is never a single point of failure. Every failure mode - LLM disabled, missing
API key, anthropic SDK missing, timeout, network error, API/auth error, invalid or
incomplete JSON, over-long text - returns the template with `fallback_reason` set.
`recommend()` and `recommend_all()` never raise.
"""
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import facility.config as cfg
from facility.contracts import Recommendation, Severity
from facility.recommendations.prompts import SYSTEM, build_prompt
from facility.recommendations.templates import template_for

PRIORITY = {Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
MAX_ACTION_WORDS, MAX_ASSUMPTION_WORDS = 60, 35

_CACHE: dict = {}
_LOCK = threading.Lock()
STATS = {"llm_calls": 0, "cache_hits": 0, "fallbacks": 0}


class LLMUnavailable(Exception):
    """Raised inside this module for any reason the LLM output cannot be used."""


# ----------------------------------------------------------------------------- LLM I/O
def _call_llm(system, prompt, timeout_s):
    """Network call only. Returns raw text. Monkeypatched in tests."""
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise LLMUnavailable("no API key")
    try:
        import anthropic
    except ImportError as exc:
        raise LLMUnavailable("anthropic package not installed") from exc
    client = anthropic.Anthropic(api_key=key, timeout=timeout_s, max_retries=0)
    try:
        msg = client.messages.create(model=cfg.LLM_MODEL, max_tokens=cfg.LLM_MAX_TOKENS, system=system,
                                     messages=[{"role": "user", "content": prompt}])
    except anthropic.APITimeoutError as exc:
        raise LLMUnavailable("timeout") from exc
    except anthropic.APIConnectionError as exc:
        raise LLMUnavailable("network error") from exc
    except anthropic.AuthenticationError as exc:
        raise LLMUnavailable("invalid API key") from exc
    except anthropic.APIError as exc:
        raise LLMUnavailable(f"API error ({type(exc).__name__})") from exc
    text = "".join(getattr(b, "text", "") for b in msg.content)
    if not text.strip():
        raise LLMUnavailable("empty response")
    return text


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def parse_llm_json(text):
    """Extract and validate {"action": str, "assumption": str}. Raises LLMUnavailable."""
    m = _JSON_OBJ.search(text or "")
    if not m:
        raise LLMUnavailable("invalid JSON (no object found)")
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("invalid JSON") from exc
    if not isinstance(data, dict):
        raise LLMUnavailable("invalid JSON (not an object)")
    out = {}
    for field, limit in (("action", MAX_ACTION_WORDS), ("assumption", MAX_ASSUMPTION_WORDS)):
        v = data.get(field)
        if not isinstance(v, str) or not v.strip():
            raise LLMUnavailable(f"invalid JSON (missing '{field}')")
        v = " ".join(v.split())
        if len(v.split()) > limit:
            raise LLMUnavailable(f"invalid JSON ('{field}' too long)")
        out[field] = v
    return out


# ----------------------------------------------------------------------------- engine
def _cache_key(event):
    """Same risk + same evidence (rounded) -> same advice. Different numbers -> new call."""
    ev = event.evidence
    sig = tuple(round(ev[k], 1) if isinstance(ev.get(k), float) else str(ev.get(k))
                for k in ("observed", "expected", "forecast_peak", "hours", "direction"))
    return (event.risk_type.value, event.metrics, event.severity.value, sig, cfg.LLM_MODEL)


def _template_rec(event, t, reason):
    return Recommendation(event.risk_id, t["title"], t["action"], t["assumption"], PRIORITY[event.severity],
                          tuple(t["roles"]), "template", event.severity.value, reason)


def recommend(event, profile, use_llm=True, timeout_s=None):
    """Return one Recommendation. Never raises."""
    try:
        t = template_for(event)
    except Exception as exc:  # defensive: a template bug must not take the app down
        t = {"title": event.risk_type.value.replace("_", " ").capitalize(),
             "action": "Review this risk with the facilities team today.",
             "assumption": "Evidence could not be formatted.", "roles": ("admin",)}
        return _template_rec(event, t, f"template error: {exc}")
    if not use_llm:
        return _template_rec(event, t, "AI disabled")
    key = _cache_key(event)
    with _LOCK:
        cached = _CACHE.get(key)
    if cached:
        STATS["cache_hits"] += 1
        return Recommendation(event.risk_id, t["title"], cached["action"], cached["assumption"],
                              PRIORITY[event.severity], tuple(t["roles"]), "llm", event.severity.value, "")
    try:
        STATS["llm_calls"] += 1
        text = _call_llm(SYSTEM, build_prompt(event, profile, t), timeout_s or cfg.LLM_TIMEOUT_S)
        out = parse_llm_json(text)
    except LLMUnavailable as exc:
        STATS["fallbacks"] += 1
        return _template_rec(event, t, str(exc))
    except Exception as exc:  # anything unexpected (SDK bug, etc.)
        STATS["fallbacks"] += 1
        return _template_rec(event, t, f"unexpected error ({type(exc).__name__})")
    with _LOCK:
        _CACHE[key] = out
    return Recommendation(event.risk_id, t["title"], out["action"], out["assumption"],
                          PRIORITY[event.severity], tuple(t["roles"]), "llm", event.severity.value, "")


SOURCE_ORDER = {"anomaly": 0, "compound": 1, "forecast": 2}  # happening now > shared cause > predicted


def rank_events(events):
    """Most severe first; within a severity: live incidents, then compound, then forecasts; newest first."""
    return sorted(events, key=lambda e: (PRIORITY[e.severity], SOURCE_ORDER.get(e.source, 3), -e.start.value))


def recommend_all(events, profile, max_llm=None, use_llm=True, timeout_s=None):
    """Recommendations in priority order. Only the top `max_llm` events use the LLM,
    concurrently, so the worst-case added latency is ~one timeout, not N timeouts."""
    max_llm = cfg.MAX_LLM_CALLS if max_llm is None else max_llm
    ranked = rank_events(events)
    if not ranked:
        return []
    with ThreadPoolExecutor(max_workers=max(1, min(max_llm, len(ranked)))) as ex:
        futs = [ex.submit(recommend, e, profile, use_llm and i < max_llm, timeout_s)
                for i, e in enumerate(ranked)]
        out = []
        for e, f in zip(ranked, futs):
            try:
                out.append(f.result())
            except Exception as exc:  # pragma: no cover - recommend() already never raises
                out.append(_template_rec(e, template_for(e), f"unexpected error ({type(exc).__name__})"))
    return out


def clear_cache():
    with _LOCK:
        _CACHE.clear()
    for k in STATS:
        STATS[k] = 0
