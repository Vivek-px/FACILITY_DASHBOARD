"""Plain-language layer: turns monthly numbers into statements a non-technical manager understands.

No Streamlit here - pure functions, so the wording and the status rules are unit-tested.

How a month is judged (shown to users under "How we judge each area"):
  * Compare with the SAME month in earlier years (December with past Decembers), because most
    indicators are seasonal: winter air is dirtier, monsoon brings flood risk.
  * Totals and concentrations: change in %   -> under 10 % normal, 10-25 % keep an eye, over 25 % needs attention.
  * Percentages (occupancy, risk %):  change in percentage points -> under 5 normal, 5-15 keep an eye, over 15 attention.
  * Direction matters: lower electricity is good news, lower speed is not; some indicators have no good/bad side.
  * Air quality is judged by its health band (CPCB PM2.5 scale), not by the change: clean air that got
    slightly less clean is still fine, and "Very poor" air is flagged even if last year was as bad.
  * Modelled estimates (water) are shown but never judged.
"""
from dataclasses import dataclass, field
import math

import pandas as pd

LOWER_BETTER, HIGHER_BETTER, NEUTRAL = "lower_better", "higher_better", "neutral"

# Status -> (label, colour, icon). Colours are reserved for status and always shown with icon + label.
STATUS = {
    "attention": ("Needs attention", "#d03b3b", "!"),
    "watch": ("Keep an eye", "#fab219", "◔"),
    "normal": ("Normal", "#0ca30c", "✓"),
    "better": ("Better than usual", "#0ca30c", "✓"),
    "unusual": ("Unusual", "#fab219", "◔"),
    "estimate": ("Estimate only", "#9BA8B8", "i"),
    "no_data": ("Not enough history", "#9BA8B8", "–"),
}
STATUS_ORDER = ["attention", "watch", "unusual", "better", "normal", "estimate", "no_data"]

# CPCB National AQI breakpoints for PM2.5 (24-hour average, µg/m³). Applied to monthly averages as an
# indicative band only - this is not an official AQI.
PM25_BANDS = [(30, "Good"), (60, "Satisfactory"), (90, "Moderate"), (120, "Poor"), (250, "Very poor"),
              (math.inf, "Severe")]


@dataclass(frozen=True)
class Guide:
    key: str
    title: str                 # what the card is called
    icon: str
    kind: str                  # "total" | "percent" | "concentration" | "estimate"
    direction: str
    unit_words: str            # unit as a person would say it
    meaning: str               # one line: what is this?
    actions: dict = field(default_factory=dict)   # "up"/"down" -> what to do when it needs attention


GUIDES = {g.key: g for g in [
    Guide("electricity_kwh", "Electricity", "⚡", "total", LOWER_BETTER, "units (kWh)",
          "Electricity used across the zone in the month. 1 unit = 1 kWh, as on an electricity bill.",
          {"up": "Check AC/chiller timers and switch off equipment left running after hours."}),
    Guide("water_consumption_l", "Water", "💧", "estimate", LOWER_BETTER, "litres",
          "Estimated water demand: 1,000 people × 135 litres a day. Not a meter reading."),
    Guide("pm25_ug_m3", "Air quality", "🌫️", "concentration", LOWER_BETTER, "µg/m³ PM2.5",
          "Fine dust in the air (PM2.5) at the Palasuni monitoring station. Lower is healthier.",
          {"up": "Limit outdoor work in the morning and evening, keep windows shut, run air purifiers "
                 "in occupied rooms and warn people with breathing problems."}),
    Guide("waste_kg", "Waste", "🗑️", "total", LOWER_BETTER, "kg",
          "Total waste generated in the month.",
          {"up": "Request an extra collection and check that bins are not overflowing."}),
    Guide("building_occupancy_pct", "Building use", "🏢", "percent", NEUTRAL, "% of capacity",
          "How full the buildings were on average.",
          {"up": "Busier than usual - check cleaning, water and cooling can keep up.",
           "down": "Quieter than usual - switch off cooling and lights in empty areas."}),
    Guide("vehicle_count", "Traffic", "🚗", "total", NEUTRAL, "vehicle movements (index)",
          "Relative amount of vehicle traffic (an index, not an exact count).",
          {"up": "Heavier traffic - check parking and entry gates at peak hours.",
           "down": "Lighter traffic than usual - no action needed unless roads were closed."}),
    Guide("co2e_kg", "Carbon footprint", "🌍", "total", LOWER_BETTER, "kg CO₂e",
          "Estimated greenhouse-gas emissions (prototype estimate, not certified).",
          {"up": "Emissions rose with energy use - see the electricity card for savings."}),
    Guide("flood_risk_pct", "Flood risk", "🌊", "percent", LOWER_BETTER, "% risk",
          "Chance of water-logging, driven mainly by rainfall.",
          {"up": "Clear drains and check sump pumps before heavy rain."}),
    Guide("heat_risk_pct", "Heat risk", "🌡️", "percent", LOWER_BETTER, "% risk",
          "Chance of heat stress for people on site.",
          {"up": "Arrange shade and drinking water, shift outdoor work away from 12-4 pm, check AC capacity."}),
]}
# Fixed order, so every card stays in the same place from month to month.
HOME_KEYS = ["electricity_kwh", "water_consumption_l", "pm25_ug_m3", "waste_kg", "building_occupancy_pct",
             "vehicle_count", "co2e_kg", "flood_risk_pct", "heat_risk_pct"]


# ---------------------------------------------------------------- number formatting (Indian style)
def indian_number(x, decimals=0):
    """28935 -> '28,935'; 418500 -> '4,18,500' (lakh grouping)."""
    neg, x = x < 0, abs(x)
    whole, frac = f"{x:.{decimals}f}".split(".") if decimals else (f"{x:.0f}", "")
    head, tail = whole[:-3], whole[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    out = ",".join(groups + [tail]) if groups else tail
    return ("-" if neg else "") + out + (f".{frac}" if frac else "")


def friendly_value(key, value):
    """Number + unit the way a person would say it: '41.9 lakh litres', '5.5 tonnes', '53% of capacity'."""
    if value is None or not math.isfinite(value):
        return "—"
    g = GUIDES.get(key)
    if key == "electricity_kwh":
        return f"{indian_number(value)} units"
    if key == "water_consumption_l":
        return f"{value / 1e5:,.1f} lakh litres"
    if key in ("waste_kg", "co2e_kg"):
        return f"{value / 1000:,.1f} tonnes" + (" CO₂e" if key == "co2e_kg" else "")
    if key == "vehicle_count":
        return f"{value / 1e5:,.2f} lakh"
    if key == "pm25_ug_m3":
        return f"{value:,.0f} µg/m³"
    if g and g.kind == "percent":
        return f"{value:,.0f}%"
    if value >= 1e7:
        return f"{value / 1e7:,.2f} crore"
    if value >= 1e5:
        return f"{value / 1e5:,.2f} lakh"
    return indian_number(value, 1 if value < 100 else 0)


def pm25_band(value):
    for upper, name in PM25_BANDS:
        if value <= upper:
            return name
    return "Severe"


# ---------------------------------------------------------------- judging a month
@dataclass
class Assessment:
    key: str
    title: str
    icon: str
    month: pd.Timestamp
    value: float
    value_text: str
    status: str
    status_label: str
    color: str
    status_icon: str
    comparison: str            # e.g. "87% higher than an average December (2023-24)"
    meaning: str
    action: str
    reference: float | None
    change: float | None       # % (totals) or percentage points (percent kinds)
    change_unit: str
    band: str | None = None    # PM2.5 band


def _same_month_reference(series, month):
    """Average of the same calendar month in earlier years (e.g. Dec 2023 + Dec 2024)."""
    prior = series[(series.index.month == month.month) & (series.index < month)].dropna()
    return (float(prior.mean()), sorted(prior.index.year.tolist())) if len(prior) else (None, [])


def _status_from_change(direction, kind, change):
    small, big = (5, 15) if kind == "percent" else (10, 25)
    size = abs(change)
    if size < small:
        return "normal"
    level = "attention" if size >= big else "watch"
    if direction == NEUTRAL:
        return "unusual"
    worse = change > 0 if direction == LOWER_BETTER else change < 0
    return level if worse else "better"


def assess(series, key, month=None):
    """Judge one indicator for one month. `series` is indexed by month-start dates."""
    g = GUIDES[key]
    s = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    month = s.index[-1] if month is None else pd.Timestamp(month)
    value = float(s.loc[month]) if month in s.index else float("nan")
    ref, years = _same_month_reference(s, month)
    month_name = f"{month:%B}"
    since = f"{years[0]}" if len(years) == 1 else (f"{years[0]}–{str(years[-1])[-2:]}" if years else "")
    comparison_target = (f"{month_name} {years[0]}" if len(years) == 1 else f"an average {month_name} ({since})")

    change, change_unit, comparison = None, "", "No earlier year to compare with yet."
    if ref is not None and math.isfinite(value):
        if g.kind == "percent":
            change, change_unit = value - ref, "points"
            if abs(change) < 0.5:
                comparison = f"About the same as {comparison_target}"
            else:
                comparison = f"{abs(change):.0f} points {'higher' if change > 0 else 'lower'} than {comparison_target}"
        elif ref > 0:
            change, change_unit = 100 * (value / ref - 1), "%"
            if abs(change) < 0.5:
                comparison = f"About the same as {comparison_target}"
            else:
                comparison = f"{abs(change):.0f}% {'higher' if change > 0 else 'lower'} than {comparison_target}"

    if g.kind == "estimate":
        status = "estimate"
    elif change is None:
        status = "no_data"
    else:
        status = _status_from_change(g.direction, g.kind, change)

    band = None
    if key == "pm25_ug_m3" and math.isfinite(value):
        band = pm25_band(value)             # health band decides; the change is only context
        status = ("attention" if band in ("Poor", "Very poor", "Severe") else
                  "watch" if band == "Moderate" else
                  "better" if status == "better" else "normal")

    label, color, icon = STATUS[status]
    if status == "attention":
        action = g.actions.get("up" if (change or 0) >= 0 or band else "down", "Look into the cause this week.")
    elif status == "unusual":
        action = g.actions.get("up" if (change or 0) > 0 else "down", "Check what was different this month.")
    elif status == "watch":
        action = "No action yet - check again next month. " + g.actions.get("up", "")
    elif status == "better":
        action = "Good result - note what worked so it can be repeated."
    elif status == "estimate":
        action = "Modelled from a planning benchmark, so it cannot show leaks or savings. Install a meter for real readings."
    else:
        action = "No action needed."

    return Assessment(key, g.title, g.icon, month, value, friendly_value(key, value), status, label, color, icon,
                      comparison, g.meaning, action.strip(), ref, change, change_unit, band)


def assess_all(df, month=None, keys=HOME_KEYS):
    """df has a 'date' column (month starts) and indicator columns."""
    s = df.set_index("date").sort_index()
    out = [assess(s[k], k, month) for k in keys if k in s.columns and s[k].notna().any()]
    return sorted(out, key=lambda a: STATUS_ORDER.index(a.status))      # most urgent first


def headline_parts(assessments):
    """(main sentence, supporting sentence) - the main one is shown large on the overview."""
    text = headline(assessments, with_month=False)
    first, _, rest = text.partition(". ")
    return first.rstrip(".") + ".", rest


def headline(assessments, with_month=True):
    """One or two sentences that answer 'How are we doing this month?'"""
    if not assessments:
        return "No data available for this month."
    month = assessments[0].month
    attention = [a for a in assessments if a.status == "attention"]
    better = [a for a in assessments if a.status == "better"]
    parts = []
    if attention:
        first = attention[0]
        detail = f"{first.title.lower()} is {first.band.lower()}" if first.band else \
            f"{first.title.lower()} is {first.comparison.lower()}"
        parts.append(f"{len(attention)} {'area needs' if len(attention) == 1 else 'areas need'} attention: {detail}.")
    else:
        parts.append("Nothing needs urgent attention.")
    if better:
        names = " and ".join(a.title.lower() for a in better[:2])
        parts.append(f"Good news: {names} {'is' if len(better[:2]) == 1 else 'are'} better than usual.")
    judged = [a for a in assessments if a.reference is not None and a.status != "estimate"]
    if not judged:
        text = (f"This is the first year of data, so there is no earlier {month:%B} to compare with yet. "
                f"Comparisons start from {month:%B} {month.year + 1}.")
        return f"{month:%B %Y}: {text}" if with_month else text
    ok = sum(a.status in ("normal", "better") for a in judged)
    parts.append(f"{ok} of {len(judged)} {'area is' if len(judged) == 1 else 'areas are'} on track.")
    return (f"{month:%B %Y}: " if with_month else "") + " ".join(parts)


def summary_counts(assessments):
    return {k: sum(a.status == k for a in assessments) for k in STATUS_ORDER}
