import streamlit as st

from facility.contracts import LABELS, METRICS
from facility.viz.charts import plot_anomaly_timeline, plot_forecast


def render(v):
    c1, c2 = st.columns([2, 1])
    metric = c1.radio("Metric", METRICS, format_func=lambda m: LABELS[m], horizontal=True, key="fc_metric")
    days = c2.select_slider("History shown", options=[3, 5, 7, 14], value=5, format_func=lambda d: f"{d} days",
                            key="fc_days")
    st.plotly_chart(plot_forecast(v.df, v.result, metric, days, v.base_df), width="stretch")
    fc = v.result.forecasts[v.result.forecasts.metric == metric]
    top = fc.loc[fc.yhat.idxmax()]
    st.caption(f"Forecast peak {top.yhat:.1f} (band {top.yhat_lower:.1f}-{top.yhat_upper:.1f}) at "
               f"{top.timestamp:%d %b %H:%M}. Method: {v.result.params['forecast']} "
               f"({v.result.params['forecast_method_used'][metric]}). Band: {v.result.params['band']}.")
    st.plotly_chart(plot_anomaly_timeline(v.result), width="stretch", config={"displayModeBar": False})
    a = v.result.anomalies
    recent = a[a.is_anomaly & (a.metric == metric)].tail(10).sort_values("timestamp", ascending=False)
    with st.expander(f"Latest flagged hours for {LABELS[metric]} ({len(recent)})"):
        if recent.empty:
            st.write("None.")
        else:
            st.dataframe(recent.assign(z_score=recent.z_score.round(1), value=recent.value.round(1),
                                       baseline_mean=recent.baseline_mean.round(1),
                                       baseline_std=recent.baseline_std.round(2)),
                         hide_index=True, width="stretch")
