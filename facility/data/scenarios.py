"""Pre-defined what-if scenarios (PRD §6.2). Each returns a NEW frame built from the
input; scenarios never stack because the app always applies them to the base data."""
import numpy as np
import pandas as pd

SCENARIOS = {
    "heatwave": {
        "label": "Heatwave",
        "description": "Cooling load pushes energy up 30% from 12:00 to 17:00 for the last 3 days.",
        "expect": "energy_spike (high) + likely forecast_peak for energy",
    },
    "pipe_leak": {
        "label": "Night pipe leak",
        "description": "Water use rises 60% between 00:00 and 05:00 for the last 2 nights.",
        "expect": "water_surge during night hours (a leak signature: flow when wards are asleep)",
    },
    "missed_pickup": {
        "label": "Missed waste pickup",
        "description": "Waste arriving at the storage point ramps up to 2.2x over 36 hours "
                       "(collection skipped, bins from wards consolidated).",
        "expect": "waste_buildup, severity rising towards the end of the window",
    },
}


def apply_scenario(df, scenario_id):
    new = df.copy()
    last = new.index[-1]
    if scenario_id == "heatwave":
        m = (new.index > last - pd.Timedelta(days=3)) & (new.index.hour >= 12) & (new.index.hour <= 17)
        new.loc[m, "energy_kwh"] = new.loc[m, "energy_kwh"] * 1.3
    elif scenario_id == "pipe_leak":
        m = (new.index > last - pd.Timedelta(days=2)) & (new.index.hour <= 5)
        new.loc[m, "water_kl"] = new.loc[m, "water_kl"] * 1.6
    elif scenario_id == "missed_pickup":
        m = new.index > last - pd.Timedelta(hours=36)
        new.loc[m, "waste_kg"] = new.loc[m, "waste_kg"].values * np.linspace(1.0, 2.2, int(m.sum()))
    else:
        raise ValueError(f"Unknown scenario {scenario_id!r}")
    return new
