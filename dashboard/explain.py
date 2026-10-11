"""'How this works' - everything a technically curious judge may ask, from live values."""
import pandas as pd
import streamlit as st

from facility.contracts import LABELS
from facility.recommendations.prompts import SYSTEM
import facility.config as cfg


def render(v):
    p, sc = v.result.params, v.result.scorecard
    t1, t2, t3, t4, t5 = st.tabs(["Data", "Detection & forecast", "Risk rules", "Scorecard", "Recommendations"])
    with t1:
        st.markdown(f"**Source:** {v.profile['data_note']}")
        st.markdown(f"**Window:** {p['data_window']}. Units: "
                    + ", ".join(f"{LABELS[m]} = {u}" for m, u in v.profile["units"].items()) + ".")
        st.markdown("**Active modifications:** " + (", ".join(v.mods) if v.mods else "none (original data)"))
        if len(v.ground_truth):
            st.markdown("**Ground truth - anomalies deliberately injected by the generator:**")
            st.dataframe(v.ground_truth, hide_index=True, width="stretch")
    with t2:
        q = v.quality
        st.markdown(f"**Anomaly detection:** {p['anomaly_method']}; anomalous if |z| >= {p['z_threshold']}; "
                    f"std floor {p['std_floor']}.")
        st.markdown("Why hour-of-day: energy at 13:00 is ~60% higher than at 03:00. A plain rolling z-score "
                    "mixes night and day; its spread is dominated by the daily cycle, so a night-time leak "
                    "that nearly doubles flow still looks normal. Comparing each hour only with the same hour on previous days removes "
                    "the daily cycle.")
        if q:
            st.markdown(f"**Measured on the original data vs ground truth:** recall {q['recall']:.0%} "
                        f"({q['windows_hit']}/{q['windows']} injected windows caught), hour-level precision "
                        f"{q['precision']:.0%}, {q['false_positive_hours']} false-positive hours out of "
                        f"{len(v.base_df) * 3:,} scored hours.")
        st.markdown(f"**Forecast:** {p['forecast']}, fitted on the last {p['forecast_fit_days']} days, "
                    f"horizon {p['horizon_h']} h. Band: {p['band']}. Sigma per metric: {p['band_sigma']}.")
        st.markdown(f"**Compute time (last run):** {p['timing_ms']} ms.")
    with t3:
        st.markdown(f"- **Incident:** {p['incident_rule']}; only incidents ending in the last "
                    f"{p['active_window_h']} h are active risks.\n"
                    f"- **Forecast risk:** {p['forecast_risk_rule']}.\n"
                    f"- **Compound risk:** {p['compound_rule']}.\n"
                    "- **Severity (anomaly):** high if |z| >= 5 or >= 4 hours; medium if |z| >= 4 or >= 2 hours.")
    with t4:
        st.markdown(f"**{sc['method']}**")
        rows = [{"Metric": LABELS[m], "Anomaly hours 7d": d["anomaly_hours_7d"], "Anomaly penalty": d["anomaly_penalty"],
                 "Vs baseline %": d["vs_baseline_pct"], "Trend penalty": d["trend_penalty"], "Score": d["score"]}
                for m, d in sc["metrics"].items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.markdown(f"Mean {sc['metric_mean']} - compound penalty {sc['compound_penalty']} = "
                    f"**{sc['overall']}** / 100.")
    with t5:
        st.markdown(f"Model: `{cfg.LLM_MODEL}`, timeout {cfg.LLM_TIMEOUT_S} s, at most {cfg.MAX_LLM_CALLS} AI calls "
                    "per refresh (the most urgent risks), results cached. Every other card, and any failure, uses "
                    "the deterministic template, labelled as such.")
        st.dataframe(pd.DataFrame([{"Risk": r.title, "Source": "AI-written" if r.source == "llm" else "Template",
                                    "Fallback reason": r.fallback_reason, "Assumption": r.assumption}
                                   for r in v.recs]), hide_index=True, width="stretch")
        with st.expander("System prompt sent to Claude"):
            st.code(SYSTEM, language=None, wrap_lines=True)
    st.caption("Limitations: synthetic data; rules-based compound risk, not a learned correlation model; "
               "a drop is typed with the same risk type as a rise (direction shown on the card); "
               "forecast band is approximate and constant-width. Decision support, not official measurement.")
