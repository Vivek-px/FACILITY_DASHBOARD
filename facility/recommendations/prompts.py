"""Prompt construction for the Claude recommendation layer (one template per risk type)."""
import json

from facility.contracts import LABELS, RiskType

SYSTEM = (
    "You write operational recommendations for the facility manager of an Indian public hospital. "
    "You receive one detected risk with numeric evidence. Reply with ONLY a JSON object, no prose, "
    'no code fences: {"action": "...", "assumption": "..."}. '
    "action: ONE concrete step the team can take this shift, max 35 words, plain English, "
    "mention the key number from the evidence. "
    "assumption: the single assumption your action depends on, max 20 words. "
    "Never invent readings, equipment names or costs that are not in the evidence. "
    "This is decision support, not an official measurement."
)

FOCUS = {
    RiskType.ENERGY_SPIKE: "electricity demand that deviates from the same hour on previous days",
    RiskType.WATER_SURGE: "water flow that deviates from the same hour on previous days (leaks, pumps, tanks)",
    RiskType.WASTE_BUILDUP: "waste generation that deviates from normal (collection, segregation, overflow)",
    RiskType.FORECAST_PEAK: "a forecast peak in the next 24 hours - the goal is to act BEFORE it happens",
    RiskType.COMPOUND: "several utilities abnormal on the same day - look for a shared cause",
}


def _clean(v):
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, float):
        return round(v, 2)
    return v


def build_prompt(event, profile, template):
    evidence = {k: _clean(v) for k, v in event.evidence.items() if v is not None}
    payload = {
        "facility": {"type": profile.get("type"), "beds": profile.get("beds"), "shifts": profile.get("shifts")},
        "risk_type": event.risk_type.value, "about": FOCUS[event.risk_type],
        "severity": event.severity.value,
        "metrics": [LABELS.get(m, m) for m in event.metrics],
        "window": f"{event.start:%Y-%m-%d %H:%M} to {event.end:%Y-%m-%d %H:%M}",
        "evidence": evidence,
        "baseline_action_for_reference": template["action"],
        "responsible_roles": list(template["roles"]),
    }
    return json.dumps(payload, ensure_ascii=False, default=str)
