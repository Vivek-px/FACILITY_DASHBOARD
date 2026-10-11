"""Bhubaneswar Zone A | Facility Intelligence Dashboard.

Launch from project root:
    python -m streamlit run app.py

Reads data_monthly/facility_zone_a_unified.csv. Never writes any source data.
Scenario injection affects a copy in Streamlit session state, not the CSV.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from zone_ui.home import render_home

st.set_page_config(page_title="Zone A · Intelligence", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data_monthly" / "facility_zone_a_unified.csv"

BG = "#0B0E13"
PANEL = "#161B23"
MUTED = "#A6ADB8"
INK = "#F6F6F2"
CYAN = "#F4C430"
GREEN = "#54BE93"
AMBER = "#FF9E57"
RED = "#EF6872"
PURPLE = "#9BA8B8"

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&family=Manrope:wght@400;500;600;700;800&display=swap');
:root {color-scheme:dark;}
html,body,[class*="css"],.stApp {font-family:'DM Sans',sans-serif;color:#F6F6F2;}
.stApp {background:#0B0E13;color:#F6F6F2;}
h1,h2,h3,h4 {font-family:'Manrope',sans-serif!important;letter-spacing:-.025em;color:#F6F6F2!important;}
p,li,label,[data-testid="stCaptionContainer"] {color:#C0C5CD;}
[data-testid="stSidebar"] {background:#12161C;border-right:1px solid #2B3038;}
[data-testid="stSidebar"] * {color:#E5E7EB;}
[data-testid="stHeader"] {background:#0B0E13;}
.block-container {padding-top:1.35rem;padding-bottom:3rem;max-width:1450px;}
[data-testid="stMetric"] {background:#171C23;border:1px solid #303640;border-radius:12px;padding:18px;}
[data-testid="stMetricLabel"] {color:#C6CAD1!important;}
[data-testid="stMetricValue"] {color:#F8F8F4!important;font-family:'Manrope',sans-serif;font-weight:750;}
[data-testid="stMetricDelta"] {color:#D9B64E!important;}
[data-testid="stTabs"] [data-baseweb="tab-list"] {gap:8px;flex-wrap:wrap;border-bottom:1px solid #303640;}
[data-testid="stTabs"] [data-baseweb="tab"] {background:#171C23;border:1px solid #303640;border-radius:8px 8px 0 0;padding:12px 15px;color:#C9CDD3!important;font-weight:700;}
[data-testid="stTabs"] [aria-selected="true"] {color:#F4C430!important;background:#24251F;border-color:#A88D30;border-bottom:2px solid #F4C430;}
[data-testid="stDataFrame"] {border-radius:10px;overflow:hidden;}
[data-baseweb="select"]>div,[data-baseweb="input"]>div,[data-baseweb="textarea"]>div {background:#20262F!important;border:1px solid #535A64!important;border-radius:8px!important;}
[data-baseweb="select"] *,[data-baseweb="input"] input,[data-baseweb="textarea"] textarea {color:#F6F6F2!important;fill:#F4C430!important;}
[data-baseweb="popover"],[data-baseweb="menu"],[role="listbox"],[role="option"] {background:#20262F!important;color:#F6F6F2!important;}
[role="option"]:hover {background:#39404A!important;}
[data-testid="stMultiSelect"] [data-baseweb="tag"] {background:#66551D!important;color:#FFF8DC!important;}
[data-testid="stSlider"] [role="slider"] {background:#F4C430!important;}
[data-testid="stSlider"] [data-baseweb="slider"] div {accent-color:#F4C430;}
.stButton button[kind="primary"],.stDownloadButton button[kind="primary"] {background:#F4C430;color:#12151A;border:0;}
.stButton button,.stDownloadButton button {background:#252A32!important;border:1px solid #77704D!important;color:#F7F7F2!important;border-radius:9px!important;font-weight:700;}
.stButton button:hover,.stDownloadButton button:hover {border-color:#F4C430!important;color:#F4C430!important;}
.topbar {display:flex;justify-content:space-between;align-items:flex-end;gap:16px;padding:6px 0 14px;border-bottom:1px solid #303640;margin-bottom:10px;}
.topbar-title {font-family:'Manrope',sans-serif;font-size:clamp(24px,2.4vw,32px);font-weight:800;color:#F6F6F2;margin-top:4px;}
.topbar-note {color:#AEB4BE;font-size:13px;}
.hero {border:1px solid #60532C;border-left:5px solid #F4C430;border-radius:13px;padding:28px 30px;background:linear-gradient(110deg,#25251D 0%,#1A1E25 58%,#141820);margin-bottom:20px;}
.eyebrow {color:#F4C430;font-size:11px;letter-spacing:.14em;font-weight:800;text-transform:uppercase;}
.hero h1 {font-size:clamp(27px,3vw,42px);font-weight:800;margin:10px 0 14px;line-height:1.16;}
.hero p {color:#C9CDD2;margin:0;font-size:14px;max-width:850px;line-height:1.6;}
.section-label {font-size:12px;letter-spacing:.08em;font-weight:800;text-transform:uppercase;color:#F4C430;margin:13px 0 17px;}
.note {background:#1B2027;border:1px solid #514B32;border-radius:9px;padding:14px 17px;color:#E0D9BA;font-size:13px;line-height:1.65;}
.domain-box {border:1px solid #343B46;background:#171C23;border-radius:12px;padding:18px 19px;min-height:145px;margin-bottom:8px;}
.domain-box .d-title {font-weight:700;color:#E6F1FC;margin-bottom:11px;font-size:14px;}
.domain-box .d-value {font-family:'Manrope',sans-serif;font-size:26px;font-weight:700;color:#F7FCFF;white-space:nowrap;}
.domain-box .d-caption {font-size:12px;color:#BBC0C8;margin-top:9px;}
hr {border-color:#343B46;}
</style>
""", unsafe_allow_html=True)

@dataclass(frozen=True)
class Metric:
    key: str
    name: str
    unit: str
    mode: str = "number"  # number, percent, index
    desc: str = ""

DOMAINS: dict[str, list[Metric]] = {
    "Energy": [Metric("electricity_kwh", "Electricity", "kWh"), Metric("peak_demand_kw", "Peak demand", "kW"), Metric("hvac_kwh", "HVAC", "kWh"), Metric("lighting_kwh", "Lighting", "kWh")],
    "Water": [Metric("water_consumption_l", "Modelled consumption", "L"), Metric("leakage_probability_pct", "Leakage probability", "%", "percent")],
    "Air Quality": [Metric("pm25_ug_m3", "PM2.5 · Palasuni", "µg/m³"), Metric("pm10_ug_m3", "PM10 · workbook", "µg/m³")],
    "Mobility": [Metric("vehicle_count", "Vehicle-event index", "index", "index"), Metric("avg_speed_kmph", "Average speed", "km/h"), Metric("congestion_index_pct", "Congestion index", "%", "percent"), Metric("parking_occupancy_pct", "Parking occupancy", "%", "percent")],
    "Buildings & Assets": [Metric("building_occupancy_pct", "Building occupancy", "%", "percent"), Metric("asset_utilisation_pct", "Asset utilisation · base", "%", "percent"), Metric("asset_utilization_pct", "Asset utilization · workbook", "%", "percent")],
    "Waste": [Metric("waste_kg", "Waste generated", "kg"), Metric("organic_waste_kg", "Organic waste", "kg"), Metric("plastic_waste_kg", "Plastic waste", "kg"), Metric("paper_waste_kg", "Paper waste", "kg")],
    "Carbon": [Metric("co2e_kg", "Prototype CO₂e estimate", "kg CO₂e")],
    "Climate & Resilience": [Metric("flood_risk_pct", "Flood risk", "%", "percent"), Metric("heat_risk_pct", "Heat risk", "%", "percent"), Metric("rainfall_mm", "Rainfall", "mm"), Metric("avg_temp_c", "Temperature", "°C"), Metric("humidity_pct", "Humidity", "%", "percent")],
}
ALL_METRICS = {m.key: m for metrics in DOMAINS.values() for m in metrics}
DEFAULT_KEYS = ["electricity_kwh", "water_consumption_l", "pm25_ug_m3", "vehicle_count", "building_occupancy_pct", "waste_kg", "co2e_kg", "flood_risk_pct"]

@st.cache_data(show_spinner=False)
def read_data(path: str, modification_ns: int) -> pd.DataFrame:
    df = pd.read_csv(path)
    needed = {"date", "zone"}
    if not needed.issubset(df.columns):
        raise ValueError(f"Missing required columns: {sorted(needed - set(df.columns))}")
    df["date"] = pd.to_datetime(df["date"], errors="raise").dt.to_period("M").dt.to_timestamp()
    if df[["date", "zone"]].duplicated().any():
        raise ValueError("Duplicate month/zone keys. Dashboard stopped to protect data interpretation.")
    if df["date"].isna().any():
        raise ValueError("Invalid dates in dataset")
    for col in ALL_METRICS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def fmt(num: float, unit: str = "", short: bool = True) -> str:
    if not np.isfinite(num):
        return "—"
    v = float(num)
    if short and abs(v) >= 1_000_000:
        result = f"{v/1_000_000:,.2f}M"
    elif short and abs(v) >= 10_000:
        result = f"{v/1_000:,.1f}k"
    elif abs(v) >= 100:
        result = f"{v:,.0f}"
    elif abs(v) >= 10:
        result = f"{v:,.1f}"
    else:
        result = f"{v:,.2f}"
    return f"{result} {unit}".strip()


def layout(fig: go.Figure, height: int = 340) -> go.Figure:
    fig.update_layout(height=height, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="DM Sans", color="#CFD2D7", size=12), margin=dict(t=24, b=30, l=8, r=18),
        hovermode="x unified", legend=dict(orientation="h", y=1.16, x=0),
        xaxis=dict(showgrid=False, zeroline=False), yaxis=dict(gridcolor="#333842", zeroline=False))
    return fig


def series_chart(df: pd.DataFrame, key: str, observed=None, forecast_base=None, forecast_shock=None) -> go.Figure:
    fig = go.Figure()
    hist = df.dropna(subset=[key])
    if not hist.empty:
        fig.add_trace(go.Scatter(x=hist.date, y=hist[key], mode="lines+markers", name="Historical baseline",
            line=dict(color=CYAN, width=3), marker=dict(size=5), fill="tozeroy", fillcolor="rgba(244,196,48,0.07)"))
    if observed is not None:
        fig.add_trace(go.Scatter(x=[observed[0]], y=[observed[1]], mode="markers", name="Injected observation · simulation",
            marker=dict(color=AMBER, size=14, symbol="diamond", line=dict(color="#FFFFFF", width=1))))
    if forecast_base is not None:
        fig.add_trace(go.Scatter(x=forecast_base.index, y=forecast_base.values, mode="lines+markers", name="Baseline forecast",
            line=dict(color=PURPLE, width=2, dash="dash")))
    if forecast_shock is not None:
        fig.add_trace(go.Scatter(x=forecast_shock.index, y=forecast_shock.values, mode="lines+markers", name="Scenario forecast · simulation",
            line=dict(color=AMBER, width=3)))
    return layout(fig)


def forecast_monthly(history: pd.Series, horizon: int = 6) -> pd.Series:
    """Transparent, deterministic seasonal-trend projection; NOT a trained ML model."""
    s = pd.to_numeric(history, errors="coerce").dropna().sort_index()
    if len(s) < 3:
        return pd.Series(dtype=float)
    vals = s.to_numpy(dtype=float)
    x = np.arange(len(vals), dtype=float)
    # Recent-weighted linear trend with robust slope restriction, to avoid explosions.
    n = min(len(vals), 18)
    fit_x = x[-n:]
    fit_y = vals[-n:]
    weights = np.linspace(0.6, 1.4, n)
    slope = float(np.polyfit(fit_x, fit_y, deg=1, w=weights)[0])
    avg = max(abs(float(np.nanmean(vals[-min(len(vals), 12):]))), 1e-9)
    slope = float(np.clip(slope, -0.12 * avg, 0.12 * avg))
    base = float(np.nanmean(vals[-min(len(vals), 3):]))
    trend_values = base + slope * np.arange(1, horizon + 1)
    # Only model seasonality when >2 years available; shrink seasonal deviations.
    if len(s) >= 24:
        monthly = s.groupby(s.index.month).mean()
        seasonal_reference = float(s.mean())
        month_effect = np.array([monthly.get(d.month, seasonal_reference) - seasonal_reference
            for d in pd.date_range(s.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")])
        trend_values = trend_values + 0.35 * month_effect
    future = pd.date_range(s.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    return pd.Series(np.maximum(trend_values, 0), index=future)


def scenario_projection(baseline: pd.Series, delta: float, persistence: float) -> pd.Series:
    # A user-defined what-if perturbation; the historical baseline never changes.
    impact = delta * np.power(persistence, np.arange(1, len(baseline) + 1))
    return pd.Series(np.maximum(0, baseline.to_numpy() + impact), index=baseline.index)


def robust_anomaly(history: pd.Series) -> tuple[float, str, float]:
    s = pd.to_numeric(history, errors="coerce").dropna()
    if len(s) < 7:
        return (0.0, "Insufficient history", np.nan)
    latest = float(s.iloc[-1])
    reference = s.iloc[:-1].tail(18)
    med = float(reference.median())
    mad = float((reference - med).abs().median())
    scale = 1.4826 * mad if mad > 1e-8 else float(reference.std(ddof=0))
    if not np.isfinite(scale) or scale <= 1e-8:
        return (0.0, "Stable reference", med)
    z = (latest - med) / scale
    return (z, "High deviation" if abs(z) >= 3 else "Watch" if abs(z) >= 2 else "Within typical variation", med)


def risk_note(metric_key: str, delta_pct: float) -> str:
    if delta_pct == 0:
        return "Baseline scenario: no injected change."
    direction = "higher" if delta_pct > 0 else "lower"
    name = ALL_METRICS[metric_key].name.lower()
    if metric_key == "pm25_ug_m3":
        return f"Simulated {direction} PM2.5: review air-quality exposure and station-level alerts. No regulatory compliance conclusion is implied."
    if metric_key in ("water_consumption_l", "leakage_probability_pct"):
        return f"Simulated {direction} water-system value: investigate operational demand assumptions and possible leakage indicators."
    if metric_key in ("electricity_kwh", "peak_demand_kw", "hvac_kwh"):
        return f"Simulated {direction} energy demand: consider load scheduling, HVAC diagnostics and peak-period monitoring."
    if metric_key in ("co2e_kg",):
        return "The carbon values are legacy prototype CO₂e estimates; scenario movement is not verified emissions accounting."
    return f"Simulated {direction} {name}: investigate operational context before using this scenario in decisions."


if not DATA_PATH.exists():
    st.error(f"Unified monthly dataset not found: {DATA_PATH}")
    st.info("Keep this app.py in the project root, next to the data_monthly folder. The CSV is never generated or modified by this app.")
    st.stop()

try:
    df_all = read_data(str(DATA_PATH), DATA_PATH.stat().st_mtime_ns)
except Exception as exc:
    st.error(f"Could not load monthly dataset: {exc}")
    st.stop()

if df_all.empty:
    st.error("Unified dataset contains no rows")
    st.stop()

available_metrics = {k: v for k, v in ALL_METRICS.items() if k in df_all.columns and df_all[k].notna().any()}
zones = sorted(df_all.zone.dropna().astype(str).unique().tolist())
with st.sidebar:
    st.markdown("### ▰  ZONE A")
    st.caption("FACILITY INTELLIGENCE / BHUBANESWAR")
    st.divider()
    zone = st.selectbox("Geographic scope", zones, index=0)
    df_zone = df_all.loc[df_all.zone.astype(str) == zone].copy()
    year_options = sorted(df_zone.date.dt.year.unique().tolist())
    picked_years = st.multiselect("Historical years", year_options, default=year_options)
    st.caption("Date filters affect historical views; forecasting always uses the complete available monthly history for the selected zone.")
    st.divider()
    st.markdown("**Data assurance**")
    st.caption("● Source CSV: read only")
    st.caption("● Scenario: session only")
    st.caption("● Forecast: explanatory projection")
    st.caption("● Frequency: monthly")
    st.divider()
    st.caption("Palasuni PM2.5 is station-specific. Modelled water and legacy carbon estimates are not observed readings.")

view = df_zone.loc[df_zone.date.dt.year.isin(picked_years)].sort_values("date")
hist = df_zone.sort_values("date")
if view.empty:
    st.warning("Select at least one year to display historical data.")
    st.stop()

st.markdown(f"""<div class="topbar"><div>
<div class="topbar-title">Zone A <span style="color:{CYAN}">monthly report</span></div></div>
<div class="topbar-note">Data up to {hist.date.max():%B %Y}</div></div>""", unsafe_allow_html=True)

tabs = st.tabs(["Overview", "Explore by topic", "What-if planner", "Alerts & actions", "About the data"])

with tabs[0]:
    render_home(hist)

with tabs[1]:
    st.markdown('<div class="section-label">Detailed resource and resilience intelligence</div>', unsafe_allow_html=True)
    domain = st.selectbox("Domain", list(DOMAINS), key="domain_detail")
    domain_metrics = [m for m in DOMAINS[domain] if m.key in available_metrics]
    if not domain_metrics:
        st.info("No values were available for this domain.")
    else:
        key = st.selectbox("Indicator", [m.key for m in domain_metrics], format_func=lambda k: ALL_METRICS[k].name, key="metric_detail")
        vals = view[key].dropna()
        k1, k2, k3 = st.columns(3)
        k1.metric("Last selected reading", fmt(float(vals.iloc[-1]), ALL_METRICS[key].unit) if len(vals) else "—")
        k2.metric("Selected-period average", fmt(float(vals.mean()), ALL_METRICS[key].unit) if len(vals) else "—")
        k3.metric("Observed range", f"{fmt(float(vals.min()))} – {fmt(float(vals.max()))}" if len(vals) else "—")
        st.plotly_chart(series_chart(view, key), width="stretch", config={"displayModeBar": False}, key=f"domain_chart_{key}")
        if domain == "Carbon":
            st.warning("Prototype workbook CO₂e estimates only. Methodology, boundary and factors are unverified; do not describe as verified Scope 2 emissions.")
        if domain == "Air Quality":
            st.info("Palasuni PM2.5 preserves reconciled station measurements and verification metadata. Workbook PM10 is a separate source, not a substitute for station measurements.")
        if domain == "Water":
            st.info("Water consumption is based on the approved hypothetical monthly demand model, not water-quality tests or metered consumption.")
        if domain == "Mobility":
            st.info("vehicle_count is a synthetic monthly vehicle-event index, not an observed traffic census.")
        if domain == "Buildings & Assets":
            st.info("asset_utilisation_pct (integrated base) and asset_utilization_pct (workbook) are kept as separate fields, without silently reconciling their methodologies.")
        st.dataframe(view[["date", key]].sort_values("date", ascending=False), width="stretch", hide_index=True)

with tabs[2]:
    st.markdown('<div class="section-label">Interactive simulation / No source-file mutations</div>', unsafe_allow_html=True)
    st.markdown("#### Live scenario injection · monthly forecast")
    st.caption("Adjust the controls below. Changes instantly rerun the simulation and forecast. Injection changes the final *scenario observation* only; original monthly measurements remain intact.")
    left, right = st.columns([1, 2.2], gap="large")
    with left:
        scenario_domain = st.selectbox("Injection domain", list(DOMAINS), index=0, key="scenario_domain")
        domain_keys = [m.key for m in DOMAINS[scenario_domain] if m.key in available_metrics]
        if not domain_keys:
            st.info("No indicators available in this domain.")
            st.stop()
        scenario_key = st.selectbox("Parameter", domain_keys, format_func=lambda k: ALL_METRICS[k].name, key="scenario_key")
        if st.session_state.pop("reset_injection_pending", False):
            st.session_state["inject_delta"] = 0
        delta_pct = st.slider("Live injected change (%)", -80, 200, 0, 5, key="inject_delta", help="Change relative to the latest historical month's baseline, not a change to stored CSV values.")
        persistence = st.slider("Shock carryover each month (%)", 0, 100, 80, 5, help="100% = full persistence; 0% = no effect from forecast month 1.") / 100.0
        horizon = st.slider("Forecast horizon (months)", 3, 12, 6, 1)
        if st.button("↺ Reset injection", width="stretch"):
            st.session_state["reset_injection_pending"] = True
            st.session_state["scenario_export_ready"] = False
            st.rerun()
        st.markdown('<div class="note">LIVE MODE<br>Injected readings are simulated, not measured. No file writes, model retraining or external feeds occur. Results are recalculated on every input change.</div>', unsafe_allow_html=True)
    with right:
        metric = ALL_METRICS[scenario_key]
        s = hist.set_index("date")[scenario_key].dropna()
        if len(s) < 3:
            st.warning("At least three valid historical monthly readings are needed for this forecast.")
        else:
            initial = float(s.iloc[-1])
            injected = max(0.0, initial * (1 + delta_pct / 100.0))
            shock = injected - initial
            baseline = forecast_monthly(s, horizon)
            simulation = scenario_projection(baseline, shock, persistence)
            a,b,c = st.columns(3)
            a.metric("Latest recorded baseline", fmt(initial, metric.unit))
            b.metric("Injected scenario reading", fmt(injected, metric.unit), f"{delta_pct:+d}% simulated", delta_color="off")
            c.metric("Forecast month 1 · scenario", fmt(float(simulation.iloc[0]), metric.unit))
            st.plotly_chart(series_chart(hist, scenario_key, (s.index[-1], injected), baseline, simulation), width="stretch", config={"displayModeBar": False}, key=f"scenario_forecast_{scenario_key}")
            forecast_table = pd.DataFrame({"Forecast month": baseline.index.strftime("%b %Y"),
                "Baseline projection": baseline.values, "Scenario projection": simulation.values,
                "Scenario difference": simulation.values - baseline.values})
            st.dataframe(forecast_table.style.format({"Baseline projection":"{:,.2f}","Scenario projection":"{:,.2f}","Scenario difference":"{:+,.2f}"}), width="stretch", hide_index=True)
            st.info(risk_note(scenario_key, delta_pct))
            if st.button("Download this scenario comparison as CSV", width="stretch"):
                st.session_state["scenario_export_ready"] = True
            if st.session_state.get("scenario_export_ready"):
                st.download_button("Save comparison", data=forecast_table.to_csv(index=False).encode(),
                    file_name="zone_a_scenario_projection.csv", mime="text/csv")
    st.caption("Forecast method: recent weighted linear trend with a shrunk month-of-year correction when enough history is present. Scenario forecast = baseline projection + injected last-month difference × chosen monthly persistence. This is an exploratory projection, not a validated forecasting model.")

with tabs[3]:
    st.markdown('<div class="section-label">Transparent anomaly screening / decision prompts</div>', unsafe_allow_html=True)
    findings = []
    for key in DEFAULT_KEYS:
        if key not in available_metrics:
            continue
        s = hist.set_index("date")[key]
        score, level, med = robust_anomaly(s)
        findings.append({"Domain indicator": ALL_METRICS[key].name,
            "Latest value": fmt(float(s.dropna().iloc[-1]), ALL_METRICS[key].unit) if s.notna().any() else "—",
            "Robust deviation": f"{score:+.2f}", "Screening result": level,
            "Reference median": fmt(med, ALL_METRICS[key].unit), "_score": abs(score)})
    findings.sort(key=lambda item: item["_score"], reverse=True)
    count_high = sum(f["Screening result"] == "High deviation" for f in findings)
    count_watch = sum(f["Screening result"] == "Watch" for f in findings)
    a,b,c = st.columns(3)
    a.metric("High deviations", count_high)
    b.metric("Watch indicators", count_watch)
    c.metric("Domains screened", len(findings))
    st.dataframe(pd.DataFrame([{k:v for k,v in f.items() if k != "_score"} for f in findings]),
        hide_index=True, width="stretch")
    st.markdown("#### Administrator action queue")
    if count_high + count_watch == 0:
        st.success("No screened indicator exceeded the chosen robust-deviation thresholds. This does not establish regulatory or operational compliance.")
    for f in findings:
        if f["Screening result"] in ("High deviation", "Watch"):
            st.markdown(f"**{f['Domain indicator']} — {f['Screening result']}:** confirm source quality and operational context before taking action; inspect the last three months and related indicators.")
    st.caption("Rule: absolute robust z-score ≥ 3 = high deviation; ≥ 2 = watch. Median and median absolute deviation use up to 18 prior months; a standard-deviation fallback is used when MAD is zero. These are descriptive thresholds, not certified alerts.")

with tabs[4]:
    st.markdown('<div class="section-label">Provenance, constraints and audit-friendly access</div>', unsafe_allow_html=True)
    st.caption(f"{len(view)} monthly records selected · {hist.date.min():%b %Y}–{hist.date.max():%b %Y} complete history · {len(available_metrics)} available indicators")
    st.markdown("#### Source hierarchy")
    st.markdown("**Authoritative 2023–2025 monthly base:** `facility_monthly_with_water.csv` — original 26 columns preserved. **Added historical fields:** original 120-month workbook, joined on exact `date` + `zone`. **Unified file:** `facility_zone_a_unified.csv`, read-only in this app.")
    st.markdown("**Air quality:** Bhubaneswar Zone A is the dashboard's facility geography. Palasuni Water Works is the reference station for the PM2.5 time series, not a claim of zone-wide measurement. Verified records and provenance fields are kept intact. PM2.5 concentration is not the same as official AQI.")
    st.markdown("**Water:** 135 LPCD × 1,000 hypothetical equivalent users × calendar-month operating days, with model metadata. This is demand simulation rather than observed water consumption, and it is not water-quality measurement.")
    st.markdown("**Carbon:** original workbook `co2e_kg` is prototype-calculated, with unknown factor and boundary methodology. Not independently verified CO₂e or Scope 2.")
    st.markdown("**Traffic and assets:** original prototype fields may be synthetic; vehicle_count denotes a vehicle-event index, not a field-verified traffic count. The base and workbook asset utilisation fields retain distinct spellings and provenance.")
    st.markdown("**Forecast and anomaly models:** exploratory statistical tools only; not physically calibrated, regulatory-compliance evaluations or production-grade alerting.")
    st.divider()
    st.markdown("#### Dataset inspection")
    provenance_cols = [c for c in ["date", "zone", "pm25_ug_m3", "pm25_station", "pm25_source_status", "pm25_source_url", "pm25_source_notes", "pm25_verification_notes", "water_consumption_l", "water_data_status", "water_model_version", "water_population_equivalent", "water_demand_lpcd", "water_benchmark_source", "co2e_kg", "data_quality_note"] if c in view]
    st.dataframe(view[provenance_cols].sort_values("date", ascending=False), hide_index=True, width="stretch")
    st.download_button("Download selected historical records (read-only export)", data=view.to_csv(index=False).encode("utf-8"),
        file_name="zone_a_historical_selected.csv", mime="text/csv")
    st.caption(f"Local source: {DATA_PATH.name} · SHA256: {hashlib.sha256(DATA_PATH.read_bytes()).hexdigest()[:20]}… · source remains unchanged")
