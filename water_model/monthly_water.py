"""
Standalone monthly water-demand model.

The model is independent of the original Facility Intelligence Dashboard.

All generated consumption is hypothetical, benchmark-based demand.
It must not be represented as observed Bhubaneswar water consumption.

Importing this module does not load data, calculate water consumption,
create files or modify the existing MVP.
"""

import calendar
import json
import math
from datetime import date
from pathlib import Path

import pandas as pd


MODEL_VERSION = "water_monthly_v1"

OUTPUT_COLUMNS = [
    "date",
    "water_consumption_l",
    "water_data_status",
    "water_model_version",
    "water_population_equivalent",
    "water_demand_lpcd",
    "water_operating_days",
    "water_additional_use_l",
    "water_benchmark_source",
]


def load_water_config(config_path):
    """Read an existing JSON configuration without changing it."""
    path = Path(config_path)

    with path.open("r", encoding="utf-8") as file:
        config = json.load(file)

    validate_water_config(config)
    return config


def validate_water_config(config):
    """Reject unsupported or inconsistent water-model settings."""

    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")

    def require(*keys):
        value = config
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                raise ValueError(
                    "Missing configuration field: " + ".".join(keys)
                )
            value = value[key]
        return value

    if require("model_id") != "BBSR_ZONE_A_DEMO":
        raise ValueError("Unexpected demonstration model ID")

    if require("model_version") != MODEL_VERSION:
        raise ValueError("Unsupported water model version")

    if require("facility_type") != "general_configurable":
        raise ValueError("Unsupported facility type")

    if require("population", "classification") != "HYPOTHETICAL":
        raise ValueError("Population must be labelled hypothetical")

    population = require("population", "equivalent_users")

    if type(population) is not int or population <= 0:
        raise ValueError("Equivalent users must be a positive integer")

    rate = require("demand", "litres_per_person_per_day")

    if (
        type(rate) not in (int, float)
        or not math.isfinite(rate)
        or rate <= 0
    ):
        raise ValueError("Daily demand rate must be finite and positive")

    operational_use = require(
        "demand", "additional_operational_use_l"
    )

    if (
        type(operational_use) not in (int, float)
        or not math.isfinite(operational_use)
        or operational_use < 0
    ):
        raise ValueError(
            "Additional operational use must be finite and nonnegative"
        )

    source = require("demand", "benchmark_source")

    if not isinstance(source, str) or not source.strip():
        raise ValueError("Benchmark source must be documented")

    if (
        require("demand", "benchmark_interpretation")
        != "SIMULATION_ASSUMPTION_NOT_MEASURED_CONSUMPTION"
    ):
        raise ValueError("Benchmark interpretation is incorrect")

    if (
        require("calendar", "operating_schedule")
        != "calendar_based"
    ):
        raise ValueError("Unsupported operating schedule")

    if (
        require("calendar", "day_count_method")
        != "actual_days_in_month"
    ):
        raise ValueError("Unsupported day-count method")

    if require("reference_period", "frequency") != "monthly":
        raise ValueError("Frequency must be monthly")

    start = require("reference_period", "start_month")
    end = require("reference_period", "end_month")

    if start != "2023-01" or end != "2025-12":
        raise ValueError("Unexpected reference period")

    if require("output", "monthly_field") != "water_consumption_l":
        raise ValueError("Unexpected water output field")

    if require("output", "monthly_unit") != "litres":
        raise ValueError("Water output must use litres")

    if require("output", "existing_mvp_field") != "water_kl":
        raise ValueError("Unexpected existing MVP water field")

    if require("output", "litres_per_kl") != 1000:
        raise ValueError("Expected 1000 litres per kL")

    if (
        require("output", "data_status")
        != "SYNTHETIC_BENCHMARK_BASED"
    ):
        raise ValueError("Synthetic provenance must be explicit")

    return True


def build_monthly_water(config):
    """
    Calculate monthly benchmark-based water demand in memory.

    This function performs no file writes.

    Calculation is performed only when this function is explicitly
    invoked. Creating or importing this module does not invoke it.
    """
    validate_water_config(config)

    population = config["population"]["equivalent_users"]
    rate = config["demand"]["litres_per_person_per_day"]
    additional = config["demand"]["additional_operational_use_l"]

    start_year, start_month = map(
        int, config["reference_period"]["start_month"].split("-")
    )
    end_year, end_month = map(
        int, config["reference_period"]["end_month"].split("-")
    )

    rows = []
    year, month = start_year, start_month

    while (year, month) <= (end_year, end_month):
        operating_days = calendar.monthrange(year, month)[1]

        # Additional operational use is interpreted as litres per month.
        monthly_litres = (
            population * rate * operating_days + additional
        )

        if not math.isfinite(monthly_litres) or monthly_litres < 0:
            raise ValueError("Invalid monthly water demand")

        rows.append({
            "date": f"{year:04d}-{month:02d}",
            "water_consumption_l": monthly_litres,
            "water_data_status": config["output"]["data_status"],
            "water_model_version": config["model_version"],
            "water_population_equivalent": population,
            "water_demand_lpcd": rate,
            "water_operating_days": operating_days,
            "water_additional_use_l": additional,
            "water_benchmark_source": (
                config["demand"]["benchmark_source"]
            ),
        })

        if month == 12:
            year += 1
            month = 1
        else:
            month += 1

    result = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)

    if len(result) != 36:
        raise ValueError("Expected exactly 36 monthly records")

    if result["date"].duplicated().any():
        raise ValueError("Duplicate reporting months")

    if result["water_consumption_l"].isna().any():
        raise ValueError("Missing monthly water values")

    return result
