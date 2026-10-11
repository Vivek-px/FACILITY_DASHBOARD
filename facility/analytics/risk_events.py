"""Turn anomalies, forecasts and compound days into typed RiskEvents (the P2 -> P3 handoff).

1. Anomaly incidents: consecutive anomalous hours of one metric (gaps of up to
   gap_tolerance_h unflagged hours are bridged, so a leak whose z dips below the
   threshold for an hour stays one incident) form ONE incident -> one card, not one card per hour. Only incidents
   that end inside the last `recent_hours` are active risks; older ones stay on charts.
2. Forecast peaks (A5, deviation D5): forecast max > FORECAST_MARGIN x the median of the
   last 7 daily maxima ("tomorrow's peak is >10% above a typical day's peak"). The PDF's
   p95-of-all-hours reference sits right at the normal daily peak, so ordinary days
   crossed it and produced noise cards.
3. Compound days (A4) inside the recent window.
Every evidence dict carries exactly EVIDENCE_KEYS.
"""
import pandas as pd

from facility.contracts import (EVIDENCE_KEYS, METRICS, SEVERITY_RANK, UNITS, RiskEvent,
                                RiskType, Severity)

TYPE_BY_METRIC = {"energy_kwh": RiskType.ENERGY_SPIKE, "water_kl": RiskType.WATER_SURGE,
                  "waste_kg": RiskType.WASTE_BUILDUP}


def risk_id(rt, metrics, start):
    return f"{rt.value}:{'+'.join(metrics)}:{pd.Timestamp(start):%Y%m%d%H}"


def evidence(**kw):
    unknown = set(kw) - set(EVIDENCE_KEYS)
    if unknown:
        raise KeyError(f"Unknown evidence keys {unknown}")
    return {k: kw.get(k) for k in EVIDENCE_KEYS}


def severity_for_anomaly(z, hours):
    a = abs(z)
    if a >= 5 or hours >= 4:
        return Severity.HIGH
    if a >= 4 or hours >= 2:
        return Severity.MEDIUM
    return Severity.LOW


def group_incidents(flagged, gap_tolerance_h=2):
    """Yield DataFrames, one per incident, for a single metric's flagged rows."""
    ts = flagged.sort_values("timestamp")
    new_run = ts.timestamp.diff() > pd.Timedelta(hours=1 + gap_tolerance_h)
    for _, g in ts.groupby(new_run.cumsum()):
        yield g


def _anomaly_events(anomalies, cutoff, z_threshold, gap_tolerance_h):
    events = []
    flagged = anomalies[anomalies.is_anomaly]
    for metric, sub in flagged.groupby("metric"):
        for g in group_incidents(sub, gap_tolerance_h):
            s, e = g.timestamp.min(), g.timestamp.max()
            if e <= cutoff:
                continue
            peak = g.loc[g.z_score.abs().idxmax()]
            hours = int((e - s) / pd.Timedelta(hours=1)) + 1
            rt = TYPE_BY_METRIC[metric]
            events.append(RiskEvent(
                risk_id(rt, (metric,), s), rt, (metric,), s, e,
                severity_for_anomaly(peak.z_score, hours), "anomaly",
                evidence(metric=metric, observed=float(peak.value), expected=float(peak.baseline_mean),
                         z_score=float(peak.z_score), threshold=float(z_threshold), unit=UNITS[metric],
                         direction="above" if peak.z_score > 0 else "below", hours=hours)))
    return events


def typical_daily_peak(series, days=7):
    """Median of the last `days` daily maxima."""
    return float(series.iloc[-days * 24:].resample("D").max().median())


def _forecast_events(forecasts, df, margin):
    events = []
    for metric in METRICS:
        fc = forecasts[forecasts.metric == metric]
        if fc.empty:
            continue
        ref = typical_daily_peak(df[metric])
        top = fc.loc[fc.yhat.idxmax()]
        ratio = float(top.yhat) / ref if ref > 0 else 0.0
        if ratio > margin:
            sev = Severity.HIGH if ratio > 1.3 else Severity.MEDIUM if ratio > 1.15 else Severity.LOW
            ts = pd.Timestamp(top.timestamp)
            events.append(RiskEvent(
                risk_id(RiskType.FORECAST_PEAK, (metric,), ts), RiskType.FORECAST_PEAK, (metric,), ts, ts,
                sev, "forecast",
                evidence(metric=metric, expected=round(ref, 3), threshold=round(ref * margin, 3),
                         forecast_peak=float(top.yhat), forecast_peak_at=ts, unit=UNITS[metric],
                         direction="above")))
    return events


def _compound_events(anomalies, compound, cutoff):
    events = []
    if compound is None or compound.empty:
        return events
    flagged = anomalies[anomalies.is_anomaly]
    for r in compound[compound.date >= cutoff.normalize()].itertuples():
        ms = tuple(sorted(r.metrics))
        day = flagged[flagged.timestamp.dt.normalize() == r.date]
        detail = {m: {"hours": int((day.metric == m).sum()),
                      "max_abs_z": round(float(day[day.metric == m].z_score.abs().max()), 2)} for m in ms}
        events.append(RiskEvent(
            risk_id(RiskType.COMPOUND, ms, r.date), RiskType.COMPOUND, ms, r.date,
            r.date + pd.Timedelta(hours=23), Severity.HIGH if r.n_metrics >= 3 else Severity.MEDIUM,
            "compound", evidence(hours=int(sum(d["hours"] for d in detail.values())), detail=detail)))
    return events


def build_risk_events(anomalies, forecasts, compound, df, recent_hours=72, z_threshold=4.0,
                      margin=1.10, gap_tolerance_h=2):
    now = df.index[-1]
    cutoff = now - pd.Timedelta(hours=recent_hours)
    events = (_anomaly_events(anomalies, cutoff, z_threshold, gap_tolerance_h)
              + _forecast_events(forecasts, df, margin)
              + _compound_events(anomalies, compound, cutoff))
    events.sort(key=lambda e: (SEVERITY_RANK[e.severity], e.start), reverse=True)
    return events
