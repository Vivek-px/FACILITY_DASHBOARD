import pandas as pd
import streamlit as st

from dashboard.insights import headline, status
from dashboard.roles import ROLE_VIEWS, split_for_role
from dashboard.style import card, hero
from facility.contracts import LABELS, METRICS, ROLE_LABELS, UNITS
from facility.viz.charts import plot_scorecard


def _panel(v):
    sc, kind = v.result.scorecard, ROLE_VIEWS[v.role]["panel"]
    if kind == "score_breakdown":
        rows = [{"Metric": LABELS[m], "Score": d["score"], "Anomaly hours (7d)": d["anomaly_hours_7d"],
                 "Anomaly penalty": d["anomaly_penalty"], "Vs baseline %": d["vs_baseline_pct"],
                 "Trend penalty": d["trend_penalty"]} for m, d in sc["metrics"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption(f"Compound days in last 7 days: {sc['compound_days_7d']} (penalty -{sc['compound_penalty']}).")
    elif kind == "next_24h":
        fc = v.result.forecasts
        rows = []
        for m in METRICS:
            f = fc[fc.metric == m]
            top = f.loc[f.yhat.idxmax()]
            rows.append({"Metric": LABELS[m], "Forecast peak": f"{top.yhat:.1f} {UNITS[m]}",
                         "When": f"{top.timestamp:%d %b %H:%M}",
                         "Next-24 h total": f"{f.yhat.sum():,.0f} {UNITS[m]}"})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        rows = [{"Metric": LABELS[m], "Last 7 days vs previous 21 days": f"{d['vs_baseline_pct']:+.1f}%",
                 "Anomalous hours (7d)": d["anomaly_hours_7d"]} for m, d in sc["metrics"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")


def render(v):
    events, recs = v.result.risk_events, v.recs
    label, color = status(events)
    hero(f"Status: {label}  |  data up to {v.df.index[-1]:%d %b %Y %H:%M}", headline(events), color)

    c1, c2, c3, c4 = st.columns(4)
    sc = v.result.scorecard
    c1.metric("Overall score", f"{sc['overall']}/100",
              delta=None if v.base_score is None else sc["overall"] - v.base_score, help=sc["method"])
    c2.metric("Active risks (72 h)", len(events),
              delta=None if v.base_events is None else len(events) - v.base_events, delta_color="inverse")
    c3.metric("High severity", sum(e.severity.value == "high" for e in events))
    c4.metric("AI-written actions", f"{sum(r.source == 'llm' for r in recs)}/{len(recs)}")

    left, right = st.columns([3, 2], gap="large")
    with left:
        mine, others = split_for_role(recs, v.role)
        st.markdown(f"**Top actions for {ROLE_LABELS[v.role]}** - {ROLE_VIEWS[v.role]['question']}")
        top = (mine or others)[:3]
        if not top:
            st.success("No active risks in the last 72 hours. Keep monitoring the forecast.")
        for r in top:
            card(r)
        if len(recs) > len(top):
            st.caption(f"{len(recs) - len(top)} more in the Recommendations tab.")
    with right:
        st.plotly_chart(plot_scorecard(sc), width="stretch", config={"displayModeBar": False})
        st.caption("MVP decision-support score, not a certified sustainability rating. Formula in 'How this works'.")
        _panel(v)
