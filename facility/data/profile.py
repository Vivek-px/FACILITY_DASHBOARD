"""Facility framing used by prompts and the UI header. Swap this (plus templates)
to target a college or municipal facility - the analytics do not change (PRD §5)."""
FACILITY_PROFILE = {
    "name": "District Government Hospital (demo)",
    "type": "district government hospital",
    "beds": 200,
    "shifts": "3 shifts: 06-14, 14-22, 22-06",
    "units": {"energy_kwh": "kWh per hour", "water_kl": "kL per hour", "waste_kg": "kg generated per hour"},
    "data_note": "Synthetic hourly data (60 days) with known injected anomalies. Decision support, not official measurement.",
}
