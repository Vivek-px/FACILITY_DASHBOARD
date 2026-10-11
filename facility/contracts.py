"""Shared vocabulary for the whole project.

SHARED FILE: change only through a PR labelled `contract-change` approved by all three owners.
Additive changes (new optional field / new evidence key) are allowed; renames are not.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

METRICS: tuple[str, ...] = ("energy_kwh", "water_kl", "waste_kg")
UNITS: dict[str, str] = {"energy_kwh": "kWh", "water_kl": "kL", "waste_kg": "kg"}
LABELS: dict[str, str] = {"energy_kwh": "Energy", "water_kl": "Water", "waste_kg": "Waste"}
INDEX_NAME, FREQ = "timestamp", "h"
ROLES: tuple[str, ...] = ("admin", "ops", "sustainability")
ROLE_LABELS: dict[str, str] = {"admin": "Admin", "ops": "Operations", "sustainability": "Sustainability"}

# Every RiskEvent.evidence dict carries exactly these keys (value None when not applicable).
EVIDENCE_KEYS: tuple[str, ...] = (
    "metric", "observed", "expected", "z_score", "threshold",
    "forecast_peak", "forecast_peak_at", "unit",
    "direction",   # "above" | "below" | None          (additive to PDF contract)
    "hours",       # anomalous hours in the incident     (additive)
    "detail",      # compound only: {metric: {"hours", "max_abs_z"}}  (additive)
)


class RiskType(str, Enum):
    ENERGY_SPIKE = "energy_spike"
    WATER_SURGE = "water_surge"
    WASTE_BUILDUP = "waste_buildup"
    FORECAST_PEAK = "forecast_peak"   # forecast peak > p95 of last 168 h (+ margin)
    COMPOUND = "compound"             # >= 2 metrics anomalous on the same day


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


SEVERITY_RANK = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}


@dataclass(frozen=True)
class InjectionEvent:
    metric: str
    start: pd.Timestamp
    hours: int
    magnitude: float
    kind: str  # "spike" | "drop" | "drift"


@dataclass(frozen=True)
class RiskEvent:
    risk_id: str                # f"{risk_type}:{'+'.join(metrics)}:{start:%Y%m%d%H}"
    risk_type: RiskType
    metrics: tuple
    start: pd.Timestamp
    end: pd.Timestamp
    severity: Severity
    source: str                 # "anomaly" | "forecast" | "compound"
    evidence: dict


@dataclass
class AnalyticsResult:
    anomalies: pd.DataFrame      # timestamp, metric, value, baseline_mean, baseline_std, z_score, is_anomaly
    forecasts: pd.DataFrame      # timestamp, metric, yhat, yhat_lower, yhat_upper
    compound_days: pd.DataFrame  # date, metrics, n_metrics, severity
    risk_events: list            # list[RiskEvent], most severe / most recent first
    scorecard: dict
    params: dict                 # everything the explainability panel shows


@dataclass(frozen=True)
class Recommendation:
    risk_id: str
    title: str
    action: str
    assumption: str
    priority: int                # 1 = act first
    roles: tuple
    source: str                  # "llm" | "template"
    severity: str = "medium"     # additive: copied from the RiskEvent for display
    fallback_reason: str = ""    # additive: why the template was used ("" when llm)
