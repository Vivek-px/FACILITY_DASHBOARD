"""Deterministic recommendation templates - the offline safety net (A9).

One entry per RiskType, plus `BELOW` variants for incidents where the value DROPPED
(z < 0). Text may use these placeholders, filled from RiskEvent.evidence by `render()`:
    {label} {observed} {expected} {ratio} {unit} {hours} {when} {peak} {peak_at} {metrics}
Missing values render as "n/a", so a template can never raise.
"""
from facility.contracts import LABELS, RiskType

TEMPLATES = {
    RiskType.ENERGY_SPIKE: {
        "title": "Unusual electricity demand",
        "action": "Electricity is {ratio}x normal ({observed} vs {expected} {unit}) {when}. Check chillers, "
                  "AC units and non-critical loads in the affected blocks now; switch off anything not needed for care.",
        "assumption": "The extra load is not an emergency surge in critical-care equipment.",
        "roles": ("ops", "admin")},
    RiskType.WATER_SURGE: {
        "title": "Water use above normal",
        "action": "Water flow is {ratio}x normal ({observed} vs {expected} {unit}) {when}. Inspect ward blocks "
                  "and the laundry line for leaks; isolate the affected zone valve if flow continues at night.",
        "assumption": "No tank cleaning, fire drill or plumbing work was scheduled in this window.",
        "roles": ("ops", "sustainability")},
    RiskType.WASTE_BUILDUP: {
        "title": "Waste accumulating faster than normal",
        "action": "Waste is {ratio}x normal ({observed} vs {expected} {unit}) {when}. Request an extra "
                  "collection today and check segregation bins on the busiest floors before they overflow.",
        "assumption": "The regular pickup schedule was followed and the readings are not a weighing error.",
        "roles": ("ops", "sustainability")},
    RiskType.FORECAST_PEAK: {
        "title": "{label} peak expected in the next 24 hours",
        "action": "{label} is forecast to peak at {peak} {unit} around {peak_at}, above a typical daily peak "
                  "of {expected} {unit}. Move non-urgent laundry, sterilisation or pumping out of that window.",
        "assumption": "Current levels persist; if today's excess is resolved, this peak should not occur.",
        "roles": ("ops", "admin")},
    RiskType.COMPOUND: {
        "title": "Several systems abnormal on the same day",
        "action": "{metrics} were abnormal on the same day ({hours} anomalous hours in total). Hold a 10-minute "
                  "facilities huddle this shift to check for a shared cause (e.g. a block running at full load).",
        "assumption": "The anomalies may share a cause; verify each one before acting on all of them.",
        "roles": ("admin", "ops", "sustainability")},
}

BELOW = {
    RiskType.ENERGY_SPIKE: {
        "title": "Unusual drop in electricity use",
        "action": "Electricity is {ratio}x normal ({observed} vs {expected} {unit}) {when}. Confirm the main "
                  "supply and DG changeover, and check that critical equipment and cold chain are still powered.",
        "assumption": "No planned shutdown or maintenance explains the drop."},
    RiskType.WATER_SURGE: {
        "title": "Unusual drop in water supply",
        "action": "Water flow is {ratio}x normal ({observed} vs {expected} {unit}) {when}. Check the overhead "
                  "tank level and pump status now, before wards run short.",
        "assumption": "The meter is working; the drop is not a planned supply cut."},
    RiskType.WASTE_BUILDUP: {
        "title": "Waste recorded below normal",
        "action": "Recorded waste is {ratio}x normal ({observed} vs {expected} {unit}) {when}. Check that ward "
                  "waste is being weighed and logged, not stored uncounted on the floors.",
        "assumption": "Patient load was normal, so less waste means a recording gap."},
}


class _Safe(dict):
    def __missing__(self, key):
        return "n/a"


def _fmt(x, nd=1):
    return "n/a" if x is None else f"{x:,.{nd}f}"


def context_for(event):
    ev = event.evidence
    obs, exp = ev.get("observed"), ev.get("expected")
    ratio = (obs / exp) if (obs is not None and exp) else None
    hours = ev.get("hours")
    when = (f"for {hours} h since {event.start:%d %b %H:%M}" if hours and hours > 1
            else f"at {event.start:%d %b %H:%M}")
    peak_at = ev.get("forecast_peak_at")
    return _Safe(
        label=LABELS.get(ev.get("metric"), "Usage"), observed=_fmt(obs), expected=_fmt(exp),
        ratio=_fmt(ratio, 2), unit=ev.get("unit") or "", hours=hours if hours is not None else "n/a",
        when=when, peak=_fmt(ev.get("forecast_peak")),
        peak_at=f"{peak_at:%d %b %H:%M}" if peak_at is not None else "n/a",
        metrics=" and ".join(LABELS.get(m, m) for m in event.metrics))


def template_for(event):
    """Return dict(title, action, assumption, roles) with placeholders filled."""
    t = dict(TEMPLATES[event.risk_type])
    if event.evidence.get("direction") == "below" and event.risk_type in BELOW:
        t.update(BELOW[event.risk_type])
    ctx = context_for(event)
    return {k: (v.format_map(ctx) if isinstance(v, str) else v) for k, v in t.items()}
