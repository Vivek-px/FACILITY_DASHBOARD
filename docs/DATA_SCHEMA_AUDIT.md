# Facility Intelligence — Data Schema Audit v1

**Status:** Proposed; pending approval  
**Source:** BPUT_Hackathon_Bhubaneswar_ZoneA_2016_2025_Hybrid_Dataset.xlsx  
**Existing MVP:** Preserve original generator, contracts, analytics and Streamlit UI.

## 1. Dataset inventory

- Workbook sheets: `120_Month_Dataset`, `Data_Dictionary`, `Sources`, `Summary`
- Actual populated records: 36
- Actual coverage: 2023-01 to 2025-12
- Zone: Bhubaneswar Zone A
- Five populated numerical fields: `avg_temp_c`, `electricity_kwh`, `waste_kg`, `vehicle_count`, `asset_utilisation_pct`
- Summary discrepancy: 120 records claimed; only 36 present
- Provenance: Public-archive weather is claimed; operational values are simulated; emissions and risk indicators are documented as derived

## 2. Eight-domain target schema

| Domain | Field | Status | Intended processing |
|---|---|---|---|
| Energy | electricity_kwh | Present, simulated | Monthly-total-constrained hourly synthesis |
| Water | water_consumption_l | Missing | Obtain or simulate explicitly |
| Waste | waste_kg | Present, simulated | Monthly-total-constrained hourly synthesis |
| Air quality | pm25_ug_m3 | Missing | Obtain or simulate explicitly; preserve concentration semantics |
| Traffic | vehicle_count | Present, simulated | Clarify whether count or index before hourly generation |
| Asset utilisation | asset_utilisation_pct | Present, simulated | Clarify asset definition; bounded hourly percentages |
| Emissions | co2e_kg | Missing, documented as calculated | Calculate from documented activity data and factors |
| Climate resilience | flood_risk_pct, heat_risk_pct | Missing, documented as derived | Calculate from documented hazard inputs and risk methodology |

## 3. Supporting context

- `avg_temp_c`: Present; public-weather archive attribution requires traceability
- `rainfall_mm`: Documented but missing
- `building_occupancy_pct`: Documented but missing
- `operational_anomaly`: Documented synthetic label but missing
- `sustainability_score`: Documented calculated indicator but missing

## 4. Rules

1. Never label synthetic hourly values as actual hourly observations.
2. Preserve the original monthly data and source attribution.
3. Use separate generation methods for totals, averages, concentrations and indices.
4. Store calculation methods and emission factors with their versions.
5. Do not invent missing historical observations and label them as public data.
6. Keep the existing hospital MVP intact until the extended pipeline passes validation.
7. Keep facility profiles configurable; do not hardcode a hospital or campus.
8. Treat geographical coordinates and Mapbox overlays as a separate future integration.

## 5. Open decisions

- Confirm exact meaning and unit of the traffic index.
- Define assets included in utilisation.
- Verify public-weather source records.
- Determine sources or simulation assumptions for water, PM2.5, rainfall and occupancy.
- Approve emissions and climate-risk calculation methodologies.
- Decide how the extended facility model maps to the existing three-metric analytics contract.

**Next gate:** Resolve missing metrics and ambiguous definitions before implementing hourly synthesis.
