"""Plotly figures. Charts only DRAW; every number comes from AnalyticsResult or the data."""
import pandas as pd
import plotly.graph_objects as go

from facility.contracts import LABELS, METRICS, UNITS

TEAL, RED, AMBER, GREY, INK, BLUE = "#0E7C7B", "#C0392B", "#B87A00", "#8A9BA5", "#10242E", "#2E6DA4"


def _style(fig, title, height=380):
    fig.update_layout(title=dict(text=title, x=0, font=dict(size=15)), template="simple_white",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Arial", size=12, color=INK), margin=dict(l=10, r=10, t=46, b=10),
                      legend=dict(orientation="h", y=-0.18), hovermode="x unified", height=height)
    return fig


def plot_forecast(df, result, metric, history_days=5, base_df=None):
    """History + baseline band + 24 h forecast with band + anomaly markers + now line.

    base_df (optional): the unmodified data, drawn faintly so a judge sees what the
    injection/scenario changed.
    """
    unit = UNITS[metric]
    hist = df[metric].iloc[-history_days * 24:]
    fc = result.forecasts[result.forecasts.metric == metric]
    a = result.anomalies
    a = a[(a.metric == metric) & (a.timestamp >= hist.index[0])]
    flagged = a[a.is_anomaly]
    fig = go.Figure()
    if len(a):
        fig.add_scatter(x=a.timestamp, y=a.baseline_mean, name="Expected (same hour, prior 7 days)",
                        line=dict(color=BLUE, width=1, dash="dot"),
                        hovertemplate="expected %{y:.1f}<extra></extra>")
    if base_df is not None and not base_df[metric].iloc[-len(hist):].equals(hist):
        b = base_df[metric].iloc[-len(hist):]
        fig.add_scatter(x=b.index, y=b.values, name="Before modification", line=dict(color=GREY, width=2),
                        opacity=0.8, hovertemplate="before %{y:.1f}<extra></extra>")
    fig.add_scatter(x=hist.index, y=hist.values, name="Actual", line=dict(color=INK, width=2),
                    hovertemplate="actual %{y:.1f} " + unit + "<extra></extra>")
    if len(fc):
        fig.add_scatter(x=fc.timestamp, y=fc.yhat_upper, line=dict(width=0), showlegend=False, hoverinfo="skip")
        fig.add_scatter(x=fc.timestamp, y=fc.yhat_lower, fill="tonexty", fillcolor="rgba(14,124,123,0.15)",
                        line=dict(width=0), name="Forecast band (~95%)", hoverinfo="skip")
        fig.add_scatter(x=fc.timestamp, y=fc.yhat, name="Forecast next 24 h",
                        line=dict(color=TEAL, width=2.5, dash="dash"),
                        hovertemplate="forecast %{y:.1f}<extra></extra>")
    if len(flagged):
        fig.add_scatter(x=flagged.timestamp, y=flagged.value, mode="markers", name="Anomaly",
                        marker=dict(color=RED, size=9, line=dict(color="white", width=1)),
                        customdata=flagged.z_score,
                        hovertemplate="anomaly z=%{customdata:.1f}<extra></extra>")
    now = hist.index[-1]
    fig.add_scatter(x=[now], y=[hist.iloc[-1]], mode="markers", name="Now",
                    marker=dict(color=AMBER, size=11, symbol="diamond"), hoverinfo="skip")
    fig.add_shape(type="line", x0=now, x1=now, y0=0, y1=1, yref="paper", line=dict(color=AMBER, dash="dot"))
    fig.add_annotation(x=now, y=1.02, yref="paper", text="now", showarrow=False, font=dict(color=AMBER))
    fig.update_yaxes(title=f"{LABELS[metric]} ({unit} per hour)", rangemode="tozero")
    return _style(fig, f"{LABELS[metric]}: last {history_days} days and next 24 h")


def plot_anomaly_timeline(result, days=14):
    """One row per metric; each flagged hour is a dot coloured by |z|."""
    a = result.anomalies
    if len(a):
        a = a[a.is_anomaly & (a.timestamp >= a.timestamp.max() - pd.Timedelta(days=days))]
    fig = go.Figure()
    if len(a):
        fig.add_scatter(x=a.timestamp, y=[LABELS[m] for m in a.metric], mode="markers",
                        marker=dict(size=10, color=a.z_score.abs(), colorscale=[[0, AMBER], [1, RED]],
                                    cmin=3, cmax=12, colorbar=dict(title="|z|", thickness=10)),
                        customdata=a[["value", "z_score"]].values,
                        hovertemplate="%{x}<br>value %{customdata[0]:.1f}, z=%{customdata[1]:.1f}<extra></extra>",
                        showlegend=False)
    else:
        fig.add_annotation(text="No anomalous hours in this window", showarrow=False, x=0.5, y=0.5,
                           xref="paper", yref="paper")
    fig.update_yaxes(categoryorder="array", categoryarray=[LABELS[m] for m in METRICS][::-1])
    fig.update_layout(hovermode="closest")
    return _style(fig, f"Anomalous hours, last {days} days", height=240)


def plot_scorecard(scorecard):
    names = list(scorecard["metrics"])
    vals = [scorecard["metrics"][m]["score"] for m in names]
    cols = [TEAL if v >= 80 else AMBER if v >= 60 else RED for v in vals]
    fig = go.Figure(go.Bar(x=vals, y=[LABELS[n] for n in names], orientation="h", marker_color=cols,
                           text=vals, textposition="inside", insidetextanchor="end",
                           hovertemplate="%{y}: %{x}/100<extra></extra>"))
    fig.update_xaxes(range=[0, 100], title="score (MVP decision-support, 0-100)")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(hovermode="closest")
    return _style(fig, "Score by metric", height=220)
