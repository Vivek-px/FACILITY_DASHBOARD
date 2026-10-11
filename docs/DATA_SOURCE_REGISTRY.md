# Facility Intelligence Dashboard — Data Source Registry

**Version:** 1.0  
**Status:** Source verification pending  
**Region:** Bhubaneswar Zone A, Odisha  
**Reference period:** January 2023 – December 2025  
**Data strategy:** Hybrid evidence-based dataset

## 1. Primary and supporting data

| Domain | Variable | Data status | Intended source or method |
|---|---|---|---|
| Energy | electricity_kwh | Existing, simulated | Preserve current monthly reference |
| Water | water_consumption_l | Missing | Search public sources; simulate facility usage if unavailable |
| Waste | waste_kg | Existing, simulated | Preserve current monthly reference |
| Air quality | pm25_ug_m3 | Missing | CPCB historical monitoring records; assess station coverage |
| Traffic | vehicle_count | Existing, simulated; definition unresolved | Verify whether value represents count or index |
| Asset utilisation | asset_utilisation_pct | Existing, simulated; definition unresolved | Define asset population and usage calculation |
| Emissions | co2e_kg | Missing, calculated | Calculate from applicable activity data and documented emission factors |
| Climate resilience | flood_risk_pct, heat_risk_pct | Missing, derived | Develop documented hazard and vulnerability assessment methods |
| Temperature | avg_temp_c | Existing, labelled real; source unverified | Verify against historical IMD or other documented archive |
| Rainfall | rainfall_mm | Missing | IMD historical rainfall data or another documented archive |
| Occupancy | building_occupancy_pct | Missing | Facility-specific simulation if necessary |

## 1A. Validated historical weather source — ERA5

**Source provider:** Open-Meteo Historical Weather API  
**Underlying dataset:** ERA5 reanalysis  
**Source classification:** Modelled historical weather (reanalysis), not direct station observations  
**Verification status:** Technically validated for the requested location and period  
**Verification date:** 2026-10-10

### Request configuration

| Property | Value |
|---|---|
| Requested location | Bhubaneswar, Odisha |
| Requested latitude | 20.2724 |
| Requested longitude | 85.8338 |
| Start date | 2023-01-01 |
| End date | 2025-12-31 |
| Historical model | ERA5 |
| Timezone | Asia/Kolkata |
| Daily temperature | temperature_2m_mean |
| Daily precipitation | precipitation_sum |
| Temperature unit | °C |
| Precipitation unit | mm |

**API URL:**

https://archive-api.open-meteo.com/v1/archive?latitude=20.2724&longitude=85.8338&start_date=2023-01-01&end_date=2025-12-31&daily=temperature_2m_mean,precipitation_sum&timezone=Asia%2FKolkata&models=era5

**Documentation:** https://open-meteo.com/en/docs/historical-weather-api

### Validation results

| Test | Result |
|---|---|
| Expected daily records | 1,096 — PASS |
| Continuous calendar dates | PASS |
| Complete temperature series | PASS |
| Complete precipitation series | PASS |
| Latitude within 0.1° tolerance | PASS |
| Longitude within 0.1° tolerance | PASS |
| Timezone Asia/Kolkata | PASS |
| Temperature unit °C | PASS |
| Precipitation unit mm | PASS |

### Approved potential uses

- Candidate source for monthly temperature averages.
- Candidate source for monthly accumulated precipitation.
- Weather context for synthetic facility operations.
- Input to later heat and flood hazard modelling, subject to approval of suitable risk methods.

### Remaining limitations and verification requirements

1. ERA5 is a modelled/reanalysis dataset, not a direct observation at a facility.
2. The returned grid coordinates must be recorded when the source data is ingested.
3. The 0.1-degree coordinate tolerance is a sanity check, not proof of spatial representativeness.
4. Compare derived monthly temperature averages against the existing monthly reference before replacing or reconciling any values.
5. Verify dataset licensing, usage conditions and attribution before deployment.
6. No historical weather data has been written into the local project as part of this verification.
7. This approval covers the technical suitability of the API response, not the final scientific suitability of downstream risk calculations.

**Status:** SOURCE REQUEST VALIDATED — INGESTION NOT YET APPROVED.

## 2. Candidate public data providers

These are candidate sources, not yet verified matches for the dataset.

- India Meteorological Department (IMD): https://mausam.imd.gov.in/
- Central Pollution Control Board (CPCB): https://cpcb.nic.in/
- Government Open Data Platform India: https://www.data.gov.in/
- Open-Meteo historical weather: https://open-meteo.com/en/docs/historical-weather-api

## 3. Source verification requirements

For every public dataset, record:

- Provider and exact dataset URL
- Download or retrieval date
- Spatial coverage, coordinates or monitoring station
- Temporal coverage and measurement frequency
- Parameter definition and original units
- Observed, modelled or calculated status
- Missing observations and quality flags
- Applicable licence and redistribution conditions

## 4. Synthetic data requirements

For every simulated parameter, document:

- Original monthly reference values, if applicable
- Facility type and operating assumptions
- Hourly generation method
- Random seed and generator version
- Monthly reconciliation and physical constraints
- Known limitations

Synthetic values must never be presented as directly measured public observations.

## 5. Calculated indicators

Emissions must have documented activity inputs, boundaries and emission factors.

Heat and flood risks must have documented hazard, exposure and vulnerability inputs, calculations and score interpretations.

Do not treat calculated indicators as independent ground-truth measurements.

## 6. Open verification tasks

- [ ] Identify the exact historical temperature archive behind existing values
- [ ] Identify suitable rainfall records for 2023–2025
- [ ] Identify suitable PM2.5 records and monitor coverage
- [ ] Resolve monthly traffic count versus index
- [ ] Define asset utilisation denominator
- [ ] Establish water simulation assumptions
- [ ] Approve emissions calculation methodology
- [ ] Approve climate-risk calculation methodology

**Implementation gate:** Public source suitability and operational simulation assumptions must be reviewed before hourly dataset generation.
