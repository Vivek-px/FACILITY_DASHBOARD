"""Overview tab for non-technical users: answer first, numbers on request.

Layer 1 (always visible): one-sentence verdict, status counts, what needs attention + what to do.
Layer 2 (one click):      "Details" popover per card - 2-year chart, the exact numbers, the rule used.
Layer 3 (opt-in):         "How we judge each area" expander and the other tabs.
"""
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from zone_ui.plain_language import GUIDES, HOME_KEYS, STATUS, assess_all, friendly_value, headline_parts, summary_counts

GOLD, INK, MUTED, PANEL, LINE = "#F4C430", "#F6F6F2", "#AEB4BE", "#171C23", "#303640"

CSS = """
<style>
.pl-head {display:flex;justify-content:space-between;align-items:flex-end;gap:16px;margin:2px 0 6px;}
.pl-verdict {border:1px solid #303640;border-left:6px solid var(--c);border-radius:14px;padding:22px 26px;
  background:#171C23;margin:6px 0 14px;}
.pl-verdict .k {font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:#AEB4BE;font-weight:700;}
.pl-verdict .t {font-family:'Manrope',sans-serif;font-size:clamp(21px,2.2vw,28px);font-weight:780;color:#F6F6F2;
  line-height:1.3;margin-top:6px;}
.pl-verdict .s {color:#D5D9DF;font-size:15.5px;margin-top:8px;line-height:1.5;}
.pl-counts {display:flex;flex-wrap:wrap;gap:10px;margin:0 0 22px;}
.pl-count {display:flex;align-items:center;gap:8px;background:#171C23;border:1px solid #303640;border-radius:999px;
  padding:7px 14px;font-size:14px;color:#E5E7EB;}
.pl-count b {font-size:17px;color:#F6F6F2;}
.pl-dot {width:10px;height:10px;border-radius:50%;background:var(--c);display:inline-block;}
.pl-h2 {font-family:'Manrope',sans-serif;font-size:19px;font-weight:750;color:#F6F6F2;margin:8px 0 4px;}
.pl-sub {color:#AEB4BE;font-size:14px;margin:0 0 14px;}
.pl-chip {display:inline-flex;align-items:center;gap:6px;border-radius:999px;padding:3px 11px;font-size:12.5px;
  font-weight:700;color:#0B0E13;background:var(--c);white-space:nowrap;}
.pl-chip .i {display:inline-flex;align-items:center;justify-content:center;width:15px;height:15px;border-radius:50%;
  background:rgba(11,14,19,.18);font-size:10.5px;}
.pl-alert {border:1px solid #303640;border-left:6px solid var(--c);border-radius:14px;background:#171C23;
  padding:20px 24px;margin-bottom:6px;}
.pl-row {display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
.pl-icon {font-size:22px;line-height:1;}
.pl-title {font-family:'Manrope',sans-serif;font-weight:750;font-size:17px;color:#F6F6F2;margin-right:auto;}
.pl-big {font-family:'Manrope',sans-serif;font-size:30px;font-weight:800;color:#F6F6F2;margin:12px 0 2px;}
.pl-band {font-size:16px;font-weight:700;color:var(--c);margin-left:6px;}
.pl-cmp {color:#D5D9DF;font-size:14.5px;margin:2px 0 10px;}
.pl-do {background:#1F252E;border-radius:10px;padding:12px 14px;color:#F1F1EC;font-size:14.5px;line-height:1.55;}
.pl-do b {color:#F4C430;}
.pl-what {color:#AEB4BE;font-size:13px;margin-top:10px;line-height:1.5;}
.pl-card {border:1px solid #303640;border-top:4px solid var(--c);border-radius:12px;background:#171C23;
  padding:16px 18px 14px;min-height:150px;}
.pl-card .pl-title {font-size:15px;}
.pl-card .pl-chiprow {margin-top:10px;}
.pl-card .pl-big {font-size:clamp(19px,1.75vw,24px);margin:10px 0 4px;white-space:nowrap;}
.pl-card {min-height:172px;}
.pl-card .pl-cmp {font-size:13.5px;margin:0;color:#C9CDD3;}
</style>
"""


def _e(text):
    return html.escape(str(text))


def _chip(a):
    return f'<span class="pl-chip" style="--c:{a.color}"><span class="i">{_e(a.status_icon)}</span>{_e(a.status_label)}</span>'


def _history_chart(series, a):
    """Last 24 months; this month and the same month in earlier years are marked."""
    s = series.dropna().sort_index()
    s = s[s.index <= a.month].tail(24)
    same = s[s.index.month == a.month.month]
    fig = go.Figure()
    fig.add_scatter(x=s.index, y=s.values, mode="lines", line=dict(color=GOLD, width=2), name=a.title,
                    hovertemplate="%{x|%b %Y}: %{y:,.1f}<extra></extra>")
    fig.add_scatter(x=same.index[:-1], y=same.values[:-1], mode="markers", name=f"Earlier {a.month:%B}s",
                    marker=dict(size=9, color=PANEL, line=dict(color=GOLD, width=2)),
                    hovertemplate="%{x|%b %Y}: %{y:,.1f}<extra></extra>")
    fig.add_scatter(x=[a.month], y=[a.value], mode="markers", name=f"{a.month:%B %Y}",
                    marker=dict(size=13, color=a.color, line=dict(color="#0B0E13", width=2)),
                    hovertemplate="%{x|%b %Y}: %{y:,.1f}<extra></extra>")
    fig.update_layout(height=230, margin=dict(t=8, b=8, l=4, r=8), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="DM Sans, Segoe UI, Arial, sans-serif", color="#CFD2D7", size=12),
                      showlegend=True, legend=dict(orientation="h", y=-0.22, x=0, font=dict(size=11)),
                      hovermode="closest", xaxis=dict(showgrid=False), yaxis=dict(gridcolor="#2B3038", zeroline=False))
    return fig


def _details(series, a):
    g = GUIDES[a.key]
    with st.popover("Details", width="stretch"):
        st.markdown(f"**{a.icon} {a.title}** — {g.meaning}")
        st.plotly_chart(_history_chart(series, a), width="stretch", config={"displayModeBar": False},
                        key=f"pl_hist_{a.key}_{a.month:%Y%m}")
        rows = [("This month", a.value_text)]
        if a.reference is not None:
            rows.append((f"Usual for {a.month:%B} (earlier years)", friendly_value(a.key, a.reference)))
            if a.change is not None:
                rows.append(("Change", f"{a.change:+.1f} {'points' if a.change_unit == 'points' else '%'}"))
        if a.band:
            rows.append(("Air quality band (CPCB PM2.5 scale, indicative)", a.band))
        rows.append(("Exact value", f"{a.value:,.2f} {g.unit_words}"))
        st.table(pd.DataFrame(rows, columns=["", "Value"]).set_index(""))
        st.caption("Status rule: see “How we judge each area” at the bottom of this page.")


def render_home(hist):
    """hist: monthly DataFrame with 'date' (month start) and indicator columns, full history."""
    st.markdown(CSS, unsafe_allow_html=True)
    months = sorted(hist["date"].dropna().unique(), reverse=True)
    series = hist.set_index("date").sort_index()

    left, right = st.columns([3, 1], vertical_alignment="bottom")
    with right:
        month = st.selectbox("Report month", months, index=0, format_func=lambda d: f"{pd.Timestamp(d):%B %Y}",
                             key="home_month")
    month = pd.Timestamp(month)
    found = assess_all(hist, month)
    with left:
        st.markdown(f'<div class="pl-h2">Monthly report · {month:%B %Y}</div>'
                    '<div class="pl-sub">How the zone is doing this month, compared with the same month in earlier years.</div>',
                    unsafe_allow_html=True)

    worst = found[0].color if found else STATUS["normal"][1]
    if found and found[0].status in ("normal", "better", "estimate", "no_data"):
        worst = STATUS["normal"][1]
    main, more = headline_parts(found)
    st.markdown(f'<div class="pl-verdict" style="--c:{worst}"><div class="k">The short answer</div>'
                f'<div class="t">{_e(main)}</div>' + (f'<div class="s">{_e(more)}</div>' if more else "") +
                '</div>', unsafe_allow_html=True)

    c = summary_counts(found)
    chips = [("attention", c["attention"], "need attention"), ("watch", c["watch"] + c["unusual"], "to keep an eye on"),
             ("normal", c["normal"] + c["better"], "on track"), ("estimate", c["estimate"], "estimate only")]
    st.markdown('<div class="pl-counts">' + "".join(
        f'<span class="pl-count"><span class="pl-dot" style="--c:{STATUS[k][1]}"></span><b>{n}</b> {_e(t)}</span>'
        for k, n, t in chips if n or k in ("attention", "normal")) + "</div>", unsafe_allow_html=True)

    flagged = [a for a in found if a.status in ("attention", "watch", "unusual")]
    if flagged:
        st.markdown('<div class="pl-h2">What needs your attention</div>'
                    '<div class="pl-sub">Most important first. Each card says what is happening and what to do.</div>',
                    unsafe_allow_html=True)
        for a in flagged:
            band = f'<span class="pl-band">{_e(a.band)} air</span>' if a.band else ""
            st.markdown(
                f'<div class="pl-alert" style="--c:{a.color}"><div class="pl-row"><span class="pl-icon">{a.icon}</span>'
                f'<span class="pl-title">{_e(a.title)}</span>{_chip(a)}</div>'
                f'<div class="pl-big">{_e(a.value_text)}{band}</div><div class="pl-cmp">{_e(a.comparison)}</div>'
                f'<div class="pl-do"><b>What to do:</b> {_e(a.action)}</div>'
                f'<div class="pl-what">What is this? {_e(a.meaning)}</div></div>', unsafe_allow_html=True)
            _details(series[a.key], a)
    else:
        st.success(f"Nothing needs attention in {month:%B %Y}.", icon="✅")

    st.markdown('<div class="pl-h2" style="margin-top:22px">Everything at a glance</div>'
                '<div class="pl-sub">Click “Details” on any card for the chart and the exact numbers.</div>',
                unsafe_allow_html=True)
    rest = sorted((a for a in found if a not in flagged), key=lambda a: HOME_KEYS.index(a.key))
    for start in range(0, len(rest), 3):
        cols = st.columns(3)
        for col, a in zip(cols, rest[start:start + 3]):
            with col:
                st.markdown(
                    f'<div class="pl-card" style="--c:{a.color}"><div class="pl-row"><span class="pl-icon">{a.icon}</span>'
                    f'<span class="pl-title">{_e(a.title)}</span></div><div class="pl-chiprow">{_chip(a)}</div>'
                    f'<div class="pl-big">{_e(a.value_text)}</div><div class="pl-cmp">{_e(a.comparison)}</div></div>',
                    unsafe_allow_html=True)
                _details(series[a.key], a)

    with st.expander("How we judge each area"):
        st.markdown(
            "- Each month is compared with the **same month in earlier years** (this December vs. past Decembers), "
            "because most things here change with the season.\n"
            "- **Totals** (electricity, waste, traffic, carbon): under 10 % change = normal, 10–25 % = keep an eye, "
            "over 25 % = needs attention.\n"
            "- **Percentages** (building use, flood and heat risk): under 5 points = normal, 5–15 = keep an eye, "
            "over 15 = needs attention.\n"
            "- **Direction matters:** using *less* electricity is good news. Building use and traffic have no good or "
            "bad side, so a big change is marked *Unusual*.\n"
            "- **Air quality** is judged by its health band on the CPCB PM2.5 scale (Good ≤ 30, Satisfactory ≤ 60, "
            "Moderate ≤ 90, Poor ≤ 120, Very poor ≤ 250). This uses monthly averages, so it is an indication, not an "
            "official AQI.\n"
            "- **Water** is an estimate from a planning benchmark (1,000 people × 135 litres/day), so it is shown but "
            "never judged.\n"
            "- The first year of data has nothing to compare with, so comparisons start one year later.")
