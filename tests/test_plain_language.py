"""Plain-language overview: status rules and wording (no Streamlit needed)."""
from pathlib import Path

import pandas as pd
import pytest

from zone_ui.plain_language import (assess, assess_all, friendly_value, headline, headline_parts,
                                    indian_number, pm25_band)

DATA = Path(__file__).resolve().parents[1] / "data_monthly" / "facility_zone_a_unified.csv"


def series(values, start="2023-12-01", step_months=12):
    """Same calendar month in consecutive years."""
    idx = pd.date_range(start, periods=len(values), freq=f"{step_months}MS")
    return pd.Series(values, index=idx, dtype=float)


@pytest.fixture(scope="module")
def df():
    d = pd.read_csv(DATA, parse_dates=["date"])
    d["date"] = d.date.dt.to_period("M").dt.to_timestamp()
    return d


def test_indian_number_grouping():
    assert indian_number(999) == "999"
    assert indian_number(28935) == "28,935"
    assert indian_number(418500) == "4,18,500"
    assert indian_number(12345678) == "1,23,45,678"


def test_friendly_units():
    assert friendly_value("water_consumption_l", 4185000) == "41.9 lakh litres"
    assert friendly_value("electricity_kwh", 28935) == "28,935 units"
    assert friendly_value("waste_kg", 5455) == "5.5 tonnes"
    assert friendly_value("building_occupancy_pct", 53.3) == "53%"


@pytest.mark.parametrize("value, band", [(25, "Good"), (60, "Satisfactory"), (75, "Moderate"), (110, "Poor"),
                                         (161, "Very poor"), (300, "Severe")])
def test_pm25_bands(value, band):
    assert pm25_band(value) == band


@pytest.mark.parametrize("values, status", [
    ([100, 100, 105], "normal"),        # +5 %
    ([100, 100, 115], "watch"),         # +15 %, more electricity is worse
    ([100, 100, 130], "attention"),     # +30 %
    ([100, 100, 80], "better"),         # -20 %, less electricity is good news
])
def test_direction_aware_status_for_totals(values, status):
    assert assess(series(values), "electricity_kwh").status == status


def test_neutral_indicator_is_unusual_not_bad():
    assert assess(series([50, 50, 70]), "building_occupancy_pct").status == "unusual"   # +20 points


def test_percent_indicators_use_points():
    a = assess(series([30, 30, 33]), "flood_risk_pct")
    assert a.change == pytest.approx(3) and a.change_unit == "points" and a.status == "normal"


def test_air_is_judged_by_health_band_not_by_change():
    assert assess(series([17, 23]), "pm25_ug_m3").status == "normal"         # +35 % but still Good air
    assert assess(series([150, 161]), "pm25_ug_m3").status == "attention"    # same as last year, but Very poor
    assert assess(series([60, 80]), "pm25_ug_m3").status == "watch"          # Moderate


def test_water_estimate_is_never_judged():
    assert assess(series([100, 100, 300]), "water_consumption_l").status == "estimate"


def test_first_year_has_no_comparison():
    a = assess(series([100]), "electricity_kwh")
    assert a.status == "no_data" and "No earlier year" in a.comparison


def test_comparison_wording():
    a = assess(series([100, 120, 130]), "electricity_kwh")   # vs average of 100 and 120
    assert a.comparison == "18% higher than an average December (2023–24)"


def test_real_december_2025(df):
    found = {a.key: a for a in assess_all(df)}
    assert found["pm25_ug_m3"].status == "attention" and found["pm25_ug_m3"].band == "Very poor"
    assert found["electricity_kwh"].status == "normal"            # 3 % lower: not a warning any more
    assert found["water_consumption_l"].status == "estimate"
    main, more = headline_parts(assess_all(df))
    assert main == "1 area needs attention: air quality is very poor."
    assert "on track" in more


def test_first_year_month_headline(df):
    assert "first year of data" in headline(assess_all(df, "2023-06-01"))


def test_every_month_renders_without_error(df):
    for month in df.date:
        assert headline(assess_all(df, month))
