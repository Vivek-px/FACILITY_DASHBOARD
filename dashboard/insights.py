"""Pure text helpers for the UI (no Streamlit import -> unit-testable)."""
from facility.contracts import LABELS, RiskType, Severity

STATUS = {"high": ("Action needed", "#C0392B"), "medium": ("Watch", "#B87A00"), "low": ("Normal", "#0E7C7B")}


def status(events):
    sev = {e.severity for e in events}
    if Severity.HIGH in sev:
        return STATUS["high"]
    if Severity.MEDIUM in sev:
        return STATUS["medium"]
    return STATUS["low"]


def _ratio(ev):
    o, x = ev.get("observed"), ev.get("expected")
    return o / x if (o is not None and x) else None


def headline(events):
    """One sentence a facility manager understands in five seconds."""
    if not events:
        return "All three utilities are within their normal hourly pattern. No active risks in the last 72 hours."
    anomaly = next((e for e in events if e.source == "anomaly"), None)
    forecast = next((e for e in events if e.risk_type == RiskType.FORECAST_PEAK), None)
    parts = []
    if anomaly:
        ev = anomaly.evidence
        r = _ratio(ev)
        word = "above" if ev.get("direction") != "below" else "below"
        span = f"for {ev['hours']} h since {anomaly.start:%d %b %H:%M}" if (ev.get("hours") or 0) > 1 \
            else f"at {anomaly.start:%d %b %H:%M}"
        parts.append(f"{LABELS[ev['metric']]} is {r:.1f}x the normal level for this hour {span}"
                     if (r and word == "above") else
                     f"{LABELS[ev['metric']]} is unusually {word} normal {span}")
    if forecast:
        ev = forecast.evidence
        parts.append(f"{LABELS[ev['metric']].lower() if parts else LABELS[ev['metric']]} is forecast to peak at "
                     f"{ev['forecast_peak']:.1f} {ev['unit']} around {ev['forecast_peak_at']:%d %b %H:%M}")
    if not parts:
        top = events[0]
        return f"{len(events)} active risk(s); top: {top.risk_type.value.replace('_', ' ')} ({top.severity.value})."
    text = "; ".join(parts)
    return text[0].upper() + text[1:] + "."


def why(event, params):
    """Plain-language explanation of the rule and evidence that created a risk."""
    ev = event.evidence
    if event.source == "anomaly":
        return (f"Observed {ev['observed']:.1f} {ev['unit']} vs {ev['expected']:.1f} {ev['unit']} expected for this "
                f"hour (same hour on the previous {params.get('baseline_days', 7)} days). z = {ev['z_score']:.1f}, "
                f"threshold |z| >= {ev['threshold']:.1f}. {ev['hours']} anomalous hour(s) between "
                f"{event.start:%d %b %H:%M} and {event.end:%H:%M} were grouped into this one incident.")
    if event.source == "forecast":
        return (f"Holt-Winters forecast peaks at {ev['forecast_peak']:.1f} {ev['unit']} at "
                f"{ev['forecast_peak_at']:%d %b %H:%M}. A typical daily peak over the last 7 days is "
                f"{ev['expected']:.1f} {ev['unit']}; the rule fires above {ev['threshold']:.1f} "
                f"({params.get('forecast_risk_rule', '')}).")
    detail = ev.get("detail") or {}
    bits = ", ".join(f"{LABELS.get(m, m)} {d['hours']} h (max |z| {d['max_abs_z']})" for m, d in detail.items())
    return (f"On {event.start:%d %b}: {bits}. Rule: {params.get('compound_rule', '2+ metrics anomalous same day')}. "
            "This is a rules-based overlay, not a learned correlation model.")
