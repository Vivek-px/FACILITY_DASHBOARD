# BUILD SPEC — Facility Intelligence Dashboard MVP

This is the execution guide for the repository it ships with. **The code in the repo is the "exact code"**: every
file path below exists, runs and is tested (140 tests, ~30 s, offline). This document tells you, phase by phase,
what each file does, how the files connect, the commands to run and their expected output, how to verify, what
breaks and how to debug it, the acceptance gate, and the git flow.

Source hierarchy used: **PRD (scope) > Phase Procedures PDF (implementation baseline) > engineering judgment.**
No PRD scope was changed. Every place the implementation departs from the PDF is listed in §1 with the reason and
the measured effect.

Owners follow the team plan: **P1** data, scenarios & integration · **P2** risk intelligence engine ·
**P3** decision & delivery layer.

---

## 0. Quick start and status

```bash
python -m venv .venv && .venv\Scripts\activate      # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest                                              # expect: 140 passed
python scripts/benchmark.py                         # expect: every line < 3 s (typically 0.8-0.9 s)
streamlit run app.py                                # http://localhost:8501
```

| Item | Status |
|---|---|
| Phases 0-3 (all modules, tests, UI) | Complete and verified |
| Phase 4 (README, screenshots, CI, rehearsal sheet, deployment notes) | Complete; **rehearsals and the backup video are yours to do** |
| Claude API live call | Code and every failure path tested with fakes. **Not yet run against the real API** (no key in the build environment). Run `python scripts/smoke_llm.py` with your key — §5.9. |

Tested with Python 3.12, pandas 3.0.2, numpy 2.4.4, statsmodels 0.15.0, streamlit 1.64.0, plotly 7.1.0,
anthropic 1.9.0, pytest 9.1.1 (pinned in `requirements.txt`). Python 3.11+ is required (pandas 3).

---

## 1. Deviations from the Phase Procedures PDF

Each change was made because a test or a measurement showed the PDF version failing on the demo data. None
changes the PRD's scope or its core decisions (hour-of-day z-score, Holt-Winters, rules-based compound risk,
Claude + template fallback, Streamlit + Plotly, local-first).

| # | PDF does | Change | Why (evidence) | PRD impact | Added complexity | Worth it? |
|---|---|---|---|---|---|---|
| D1 | Keeps the mutated DataFrame in `st.session_state`; scenarios applied to base, injections to current frame | Session state holds a **recipe** `(scenario, injections)`; the frame is rebuilt from the untouched base each run (`facility/data/state.py`); analytics cached on the recipe | Makes "never compound on rerun" and "Reset restores exactly" true by construction; the recipe is a tiny, perfect cache key | None | Low (30 lines) | Yes |
| D2 | Plain hour-of-day mean/std over 7 days | Same, plus **weekday adjustment** and **spread pooled over ±1 h** | Sunday OPD is closed, so a 7-day window holds one Sunday and Sunday afternoons scored as "drops"; a std from only 7 samples is noisy. Measured with `scripts/tune_threshold.py` (5 seeds) at z = 4.0: the PDF detector reaches precision 0.71 but flags only **6 %** of the heatwave scenario hours; this detector reaches 0.76 precision and flags **72 %** | None (still hour-of-day z, 7-day baseline, current point excluded, std floor) | Medium | Yes - an invisible scenario fails the demo |
| D3 | Baseline includes past anomalies | **Flagged hours are removed from later baselines** (iterate until flags stop changing) | A spike days earlier at the same hour inflated the baseline and masked the next incident at that hour (`test_exclude_flagged_unmasks_repeat_incident`); D2 + D3 together produce the heatwave improvement above | None | Medium | Yes |
| D4 | Band = ± 1.96 × std(residuals) | ± 1.96 × **robust σ = 1.4826 × MAD(residuals)**; seasonal-naive fallback if Holt-Winters fails | Past anomalies in the fit window inflate the plain residual std: energy 24.3 kWh vs robust 9.3 kWh (water 1.79 vs 0.74 kL) on the demo data | None | Low | Yes |
| D5 | Forecast risk if peak > 1.05 × p95 of last 168 h | Peak > **1.10 × median of the last 7 daily maxima** | p95 of all hours sits close to the normal daily peak. On 5 anomaly-free datasets the PDF rule raised 3 false forecast risks; this rule raised 0 | None (A5 wording refined) | Low | Yes |
| D6 | z threshold 3.0 | **4.5**, chosen by `scripts/tune_threshold.py` (the PDF's step 3.4 asks you to tune) | At 3.0 precision is 0.32 (91 false-positive hours). Rule: recall ≥ 0.8 and every demo scenario ≥ 70 % visible, then best precision | None | None | Yes |
| D7 | Strictly consecutive hours form an incident | Gaps of ≤ 2 unflagged hours are bridged | A leak whose z dips for one hour otherwise became two cards | None | Low | Yes |
| D8 | LLM text parsed by stripping fences; cache keyed on (type, metrics, severity); templates static | Regex JSON extraction + **field/type/length validation**; typed error mapping; **fallback reason on every card**; cache keyed on the **evidence numbers**; templates filled with real numbers; `below` variants for drops; ranking live > compound > forecast | The PDF cache served advice quoting another incident's numbers; the brief requires JSON validation and visible source; a static template was generic | None (strengthens §7.2 fallback) | Medium | Yes |
| D9 | Contract | **Additive** fields: evidence `direction`, `hours`, `detail`; `Recommendation.severity`, `fallback_reason`; `UNITS`, `LABELS`, `EVIDENCE_KEYS`, `SEVERITY_RANK` | UI and explainability need them | None | Low | Yes |
| D10 | Role filter falls back to "all" if empty | Role's actions first, other teams' in a collapsed section (nothing hidden); **Admin also owns every high-severity risk** | Admin previously did not see the highest risk (a water surge assigned to Ops) | None (PRD: same data, filtered differently) | Low | Yes |
| D11 | Explainability inside the Recommendations tab | Full-width "How this works" expander under the 3 tabs, plus a "Why this appeared" expander on every card | Keeps the PRD's 3 tabs while making explanations reachable from any tab | None | Low | Yes |
| D12 | Generator: base profile + white noise | Adds day-to-day level variation, AR(1) meter noise, a 4 % pre-summer energy trend, an evening water peak; **same anomaly schedule** | White noise looks synthetic on a chart; judges notice | None | Low | Yes |
| D13 | Manual UI checks | `tests/test_app.py` drives the real app headlessly (`streamlit.testing.v1.AppTest`); CI workflow runs pytest on every push | "Streamlit opens" is not a test | None | Low | Yes |

---

## 2. Architecture

```
                     facility/config.py  (shared tunables)       facility/contracts.py  (shared vocabulary)
                                   │                                         │
 P1  facility/data/ ───────────────┼─────────────────────────────────────────┤
     generator.py  → df + ground-truth log                                   │
     loader.py     → validate_facility_data / load_facility_data / load_ground_truth
     injection.py  → inject_anomaly (pure)      scenarios.py → apply_scenario (pure)
     state.py      → add_injection / build_working_df (recipe → frame)       │
     profile.py    → FACILITY_PROFILE          facility/pipeline.py → run_pipeline, evaluate_detection
                                   │ validated DataFrame                     │
 P2  facility/analytics/ ──────────▼─────────────────────────────────────────┤
     anomaly.py → forecasting.py → compound.py → risk_events.py → scorecard.py
     engine.py: run_analytics(df) → AnalyticsResult                           │
                                   │ AnalyticsResult                          │
 P3  facility/recommendations/ ────▼──────────────────────────────────────────┘
     templates.py → prompts.py → generator.py: recommend / recommend_all → [Recommendation]
     facility/viz/charts.py      dashboard/ (style, insights, roles, tabs, explain)      app.py
```

Runtime loop on a click (target < 3 s): callback edits the recipe → Streamlit reruns → `analyse(recipe)` (cached) →
`build_working_df` → `run_pipeline` (~0.85 s) → `recommend_all` (templates instant; ≤ 3 concurrent Claude calls,
4 s cap, cached) → tabs render.

**Development vs runtime dependency.** P2 develops against `tests/fixtures/sample_facility_data.csv`; P3 develops
against `facility/mocks.py::mock_analytics_result()`. At runtime everything depends on everything except the
Claude call, which is optional.

### 2.1 Contracts (`facility/contracts.py`, shared, all-three approval)

| Object | Fields | Produced by → consumed by |
|---|---|---|
| Facility DataFrame | `DatetimeIndex` named `timestamp`, hourly, continuous, tz-naive; float columns `energy_kwh`, `water_kl`, `waste_kg`; no NaN, no negatives; ≥ 14 days | P1 → P2, P3 charts |
| Ground truth | `metric, start, end, kind, magnitude` | P1 → P2 tuning, explainability |
| `anomalies` | `timestamp, metric, value, baseline_mean, baseline_std, z_score, is_anomaly` | P2 → P3 |
| `forecasts` | `timestamp, metric, yhat, yhat_lower, yhat_upper` (first row = last data hour + 1 h) | P2 → P3 |
| `compound_days` | `date, metrics, n_metrics, severity` | P2 → P3 |
| `RiskEvent` | `risk_id, risk_type, metrics, start, end, severity, source, evidence` | P2 → P3 |
| evidence | exactly `EVIDENCE_KEYS`: `metric, observed, expected, z_score, threshold, forecast_peak, forecast_peak_at, unit, direction, hours, detail` (None if n/a) | P2 → P3 |
| `AnalyticsResult` | the above + `scorecard` dict + `params` dict (all explainability values + timings) | P2 → P3 |
| `Recommendation` | `risk_id, title, action, assumption, priority, roles, source ("llm"/"template"), severity, fallback_reason` | P3 → UI |

Contract changes: PR labelled `contract-change`, all three approve, fixtures regenerated in the same PR,
`pytest` green. Additive only; never rename.

---

## 3. Phase 0 — Foundation (hours 0-3, whole team)

| # | Item | Specification |
|---|---|---|
| 1 | Objective | Repo, environment, contracts and decisions fixed so three people can work in parallel |
| 2 | Architecture | §2 |
| 3-4 | Files / folders | `facility/{data,analytics,recommendations,viz}/`, `dashboard/`, `scripts/`, `tests/fixtures/`, `docs/`, `.streamlit/`, `.github/workflows/`, `notebooks/`, `data/` (git-ignored CSVs). Every package folder has `__init__.py`. Shared files: `facility/contracts.py`, `facility/config.py`, `.gitignore`, `.github/CODEOWNERS`, `.env.example`, `.streamlit/config.toml`, `.streamlit/secrets.toml.example`, `pytest.ini`, `requirements.txt` |
| 5 | Dependencies | `requirements.txt` (pinned). Only P1 edits it |
| 6-8 | Code / placement / links | `contracts.py` defines the vocabulary everyone imports — never type a metric name, import `METRICS`. `config.py` holds every tunable; `engine.DEFAULTS` reads it; `FACILITY_USE_LLM=0` env var forces templates (tests set it) |
| 9 | Commands | `python -c "from facility.mocks import mock_analytics_result as m; print(m().scorecard['overall'])"` |
| 10 | Expected output | `72` |
| 11 | Verification | All three run the command above from the repo root on their own machines |
| 12-13 | Tests | `pytest tests/test_pipeline.py::test_mock_matches_contract` |
| 14-15 | Failure modes | `ModuleNotFoundError: facility` → run from the repo root / missing `__init__.py`. Wrong interpreter in VS Code → *Python: Select Interpreter* → `.venv` |
| 16 | Acceptance | contracts, config, fixture, mock merged to `main`; branch protection on; CODEOWNERS handles filled in |
| 17 | Git | `main` protected (PR + 1 approval). Branch `team/foundation`; tag nothing |
| 18 | Gate | Nobody starts Phase 1 until the exit command works for all three |

Write the design decisions A1-A12 into the README (already done in this repo — adjust if you disagree).

---

## 4. Phase 1 — Core modules (hours 3-14)

### 4.1 P1 · Synthetic data — `facility/data/generator.py`

**Objective.** Believable hourly data for a 200-bed district hospital with known anomalies, identical on every
machine.

**Algorithm.** `value(t) = profile(hour, weekday) × day_level × trend + AR(1) noise`, then the `SCHEDULE`
windows are multiplied and logged.

| Component | Energy | Water | Waste |
|---|---|---|---|
| Base + peaks | 200 + 120·exp(−((h−13)/4)²) (OPD) | 8 + 6·peak 07:30 (bathing) + 5·peak 13:00 (laundry/kitchen) + 2·peak 19:00 | 4 + 3·peak 11:00 (rounds) + 2·peak 19:00 (meals) |
| Weekday | Sat × 0.9, Sun × 0.8 | Sun × 0.85 | Sun × 0.8 |
| Noise σ | 8 kWh | 0.6 kL | 0.4 kg |
| Extra | +4 % trend over 60 days (pre-summer cooling) | — | — |

AR(1) noise (φ = 0.5) is scaled so its marginal σ equals the table value: real meters drift, they do not jump
independently every hour. `default_rng(seed)` + a fixed metric order ⇒ reproducible.

Ground-truth schedule (day index from 1 July 2026): energy spike d20, energy **drop** d27, night water spike d33,
waste spike d41, **compound day d47** (energy + water), energy spike d52, **water spike d59 14:00-18:00** (inside
the last 24 h — the on-stage catch).

`scripts/generate_data.py` writes `data/facility_data.csv`, `data/injected_anomalies.csv` and the 21-day fixture.

```text
$ python scripts/generate_data.py
saved data/facility_data.csv (1440, 3)  from 2026-07-01 00:00:00 to 2026-08-29 23:00:00
saved data/injected_anomalies.csv (8 injected windows)
saved tests/fixtures/sample_facility_data.csv (504, 3)
```

Tests (`tests/test_data.py`): `test_reproducible_same_seed`, `test_different_seed_differs`, `test_schema`,
`test_ground_truth_log` (last anomaly inside the final 24 h), `test_daily_and_weekly_pattern`,
`test_injected_window_is_multiplied`.

### 4.2 P1 · Validation and loading — `facility/data/loader.py`

`validate_facility_data(df)` raises `ValueError` with a specific message for: not a DataFrame, missing columns,
non-DatetimeIndex, tz-aware index, wrong index name, non-numeric column, NaN, negatives, duplicate timestamps,
unsorted index, **gaps** (compares with `pd.date_range(first, last, freq="h")`), fewer than 14 days.
`load_facility_data(path, regenerate_if_missing=True)` regenerates when the CSV is missing — the demo never dies
on a fresh clone. `load_ground_truth()` returns an empty frame if the log is absent.

Tests: `test_validator_rejects` (11 parametrised cases incl. timezone, gaps, NaN, missing columns, invalid index),
`test_loader_regenerates_when_missing`, `test_loader_raises_when_missing_and_no_regenerate`,
`test_csv_roundtrip_matches_generator`.

### 4.3 P2 · Anomaly detection — `facility/analytics/anomaly.py` (hard part)

**Why hour-of-day normalisation matters.** Energy at 13:00 is ~60 % above 03:00. A plain rolling window over all
hours mixes those regimes: its mean is wrong for every hour and its std is dominated by the daily cycle, so the
threshold becomes insensitive. `test_hour_of_day_beats_plain_rolling` proves it on data: a 3-hour night leak at
1.8 × flow is fully caught by the hour-of-day baseline and mostly missed by a 168 h rolling z-score.

**Algorithm**, per metric:

1. `factor = weekday_factors(series)` — median ratio of each weekday's daily total to the centred 7-day mean.
   `s = series / factor` removes the Saturday/Sunday effect (D2).
2. For each hour of day `h`: `mean = s[h].shift(1).rolling(7).mean()`, `std = …rolling(7).std()` —
   `shift(1)` excludes the current point so an anomaly cannot hide inside its own baseline.
3. `pool_spread`: the variance at hour *h* is averaged with hours *h±1* on the same day (21 samples instead of 7)
   — the **mean stays strictly hour-of-day**, only the spread estimate is stabilised (D2).
4. Std floor: `std = max(std, 0.02 × |mean|)` — z cannot explode when seven past values are nearly identical.
5. `z = (s − mean) / std`; anomalous if `|z| ≥ Z_THRESHOLD` (4.5).
6. `exclude_flagged`: recompute mean/std with flagged hours masked, repeat until flags stop changing (≤ 5 passes)
   so an old spike cannot mask a new incident at the same hour (D3).
7. Report `baseline_mean`/`baseline_std` × factor, i.e. in real units, so the UI's "expected" value is correct.

First 7 days: no baseline, `z = NaN`, never anomalous.

```text
$ python scripts/evaluate_detection.py
| z_threshold | recall | precision | flagged_hours | false_positive_hours | selected |
| 3.0 | 1 | 0.316 | 133 | 91 |    |
| 4.5 | 1 | 0.913 |  46 |  4 | <- |
```

Tests (`tests/test_analytics.py`): `test_detector_schema`, `test_first_week_has_no_baseline`,
`test_current_point_excluded`, `test_clean_data_has_few_false_positives` (< 1 %),
`test_hour_of_day_beats_plain_rolling`, `test_std_floor_prevents_explosion`,
`test_exclude_flagged_unmasks_repeat_incident`, `test_ground_truth_recall`.

### 4.4 P2 · Forecasting — `facility/analytics/forecasting.py` (hard part)

`forecast_metric(series, horizon_h=24, seasonal_periods=24, fit_days=28)`:

* `y = series.iloc[-28*24:].asfreq("h")` — Holt-Winters needs an explicit frequency and ≥ 2 full seasons.
* `ExponentialSmoothing(y, trend="add", damped_trend=True, seasonal="add", seasonal_periods=24).fit()` inside
  `warnings.catch_warnings()` (ConvergenceWarnings are normal).
* Band: `yhat ± 1.96 × 1.4826 × MAD(resid)` (D4). Approximate, constant width — the UI says so.
* Any exception or non-finite output → seasonal-naive fallback (mean daily profile of the last week);
  `out.attrs["method"]` records which one ran and is shown in the UI.
* Output starts exactly one hour after the last data row; values clipped at 0.

Tests: `test_forecast_shape_and_start`, `test_forecast_follows_daily_cycle`, `test_forecast_needs_two_seasons`,
`test_forecast_fallback_on_fit_failure`, `test_robust_sigma_ignores_outliers`.

### 4.5 P3 · Templates — `facility/recommendations/templates.py`

One entry per `RiskType` (+ `BELOW` variants for drops). Placeholders `{observed} {expected} {ratio} {unit}
{hours} {when} {peak} {peak_at} {metrics} {label}` are filled from the evidence with a `format_map` that returns
`"n/a"` for anything missing, so a template can never raise. Each carries a concrete action, a stated
assumption and responsible roles. Tests: `test_every_template_renders` (5 types × 2 directions),
`test_template_uses_evidence_numbers`, `test_below_variant`, `test_template_survives_missing_evidence`,
`test_all_risk_types_have_templates`.

### 4.6 P3 · UI skeleton on the mock

`app.py` + `dashboard/` render `mock_analytics_result()` first; the swap to real data is §6.1.
`.streamlit/config.toml` sets the teal theme and headless server.

### Phase 1 gate

| Check | Command | Expected |
|---|---|---|
| P1 | `pytest tests/test_data.py` | all pass |
| P2 | `pytest tests/test_analytics.py -k "detector or forecast or baseline or floor"` | all pass |
| P3 | `streamlit run app.py` on the mock | 3 tabs render, no traceback |

Git: `p1/generator`, `p2/anomaly`, `p2/forecast`, `p3/templates`, `p3/ui-skeleton` → PRs to `main`.

---

## 5. Phase 2 — Full features (hours 14-28)

### 5.1 P1 · Live injection — `facility/data/injection.py`

`inject_anomaly(df, metric, hours=6, magnitude=2.5, kind="spike", start=None)` → `(new_df, InjectionEvent)`.
`df.copy()` first — the input is **never** modified. `spike` ×m, `drop` ÷m, `drift` ramps ×1 → ×m.
`start=None` means the last `hours` rows ("happening now"). Validates metric, kind, hours, magnitude, start.

### 5.2 P1 · Declarative state — `facility/data/state.py` (hard part, D1)

```python
add_injection(injections, metric, kind, magnitude, hours)   # returns a NEW tuple; replaces that metric's entry
build_working_df(base, scenario=None, injections=())       # base -> scenario -> each injection
```

Why: Streamlit reruns the whole script on every interaction. If the mutated frame lived in session state, a
second click (or a stale reference) would multiply the spike again, and Reset would depend on having kept a clean
copy. With a recipe: the same recipe always gives the same frame, clicking Inject twice on the same metric
*replaces* the injection, different metrics coexist (a live compound demo), and Reset is `recipe = (None, ())`.

Tests (`tests/test_injection.py`): `test_original_unchanged`, `test_spike_changes_only_window`,
`test_drop_and_drift`, `test_explicit_start`, `test_invalid_injection`, `test_recipe_is_idempotent`,
`test_reinjecting_same_metric_replaces_not_compounds`, `test_different_metrics_coexist`,
`test_reset_restores_base`.

### 5.3 P1 · Scenarios — `facility/data/scenarios.py`

Measured on the demo data (`python scripts/benchmark.py` and the scenario tests):

| Scenario | Data changed | Why realistic | Detector sees | Risk that appears | Recommendation | Score |
|---|---|---|---|---|---|---|
| Heatwave | `energy_kwh` × 1.3, 12:00-17:00, last 3 days | Cooling load peaks in the afternoon in Indian summers | 3 afternoon incidents (72 % of changed hours) | 3 × energy_spike HIGH + compound (energy + water) MEDIUM | "Unusual electricity demand" — check chillers/AC, cut non-critical load | 96 → 77 |
| Night pipe leak | `water_kl` × 1.6, 00:00-05:00, last 2 nights | Flow while wards sleep is the classic leak signature | 2 night incidents (75 %) | 2 × water_surge HIGH | "Water use above normal" — inspect, isolate zone valve at night | 96 → 89 (water 89 → 67) |
| Missed pickup | `waste_kg` ramps × 1.0 → 2.2 over 36 h | Skipped collection: waste keeps accumulating with no reset | Ramp flagged once it passes ~1.5 × (74 %) | waste_buildup HIGH + forecast_peak (waste) HIGH + compound | "Waste accumulating" — extra collection, check segregation bins | 96 → 68 (waste 44) |

Scenarios are always applied to the base, so they never stack; injections apply on top of the active scenario.
Tests: `test_scenarios_touch_only_their_metric`, `test_scenario_hours`, `test_unknown_scenario`,
`test_each_scenario_produces_its_risk`.

### 5.4 P2 · Compound days — `facility/analytics/compound.py`

Flagged hours → `date` → hours per (date, metric) → keep metrics with ≥ `COMPOUND_MIN_HOURS` → days with
≥ `COMPOUND_MIN_METRICS` metrics. Severity: 3 metrics high, 2 medium. Stated in the UI as a rules-based stand-in
for a learned correlation model (PRD §7.2). Tests: `test_compound_day`, `test_compound_three_metrics_is_high`.

### 5.5 P2 · Risk events — `facility/analytics/risk_events.py` (hard part, the P2 → P3 handoff)

1. **Incidents.** Per metric, sort flagged hours; a new incident starts when the gap exceeds `1 + INCIDENT_GAP_H`
   hours. One incident → one `RiskEvent`, evidence from the peak-|z| hour, `hours` = span, `direction` from the
   sign of z. Active only if it **ends** within the last 72 h (older ones stay on the charts).
   Severity: high if |z| ≥ 5 or ≥ 4 h; medium if |z| ≥ 4 or ≥ 2 h; else low.
2. **Forecast peak.** `ref = median of the last 7 daily maxima`; event if `max(yhat) > 1.10 × ref`; severity by
   ratio (> 1.3 high, > 1.15 medium).
3. **Compound.** Each compound day inside the window; `detail` holds hours and max |z| per metric.
4. Sort by severity then recency. Every evidence dict has exactly `EVIDENCE_KEYS`.

Tests: `test_incident_grouping_one_card_per_incident`, `test_risk_events_from_live_injection` (5 anomalous
hours = 1 event), `test_drop_is_marked_below`, `test_old_incidents_are_not_active`, `test_forecast_peak_event`,
`test_every_event_has_all_evidence_keys`, `test_events_sorted_by_severity`, `test_demo_anomaly_detected`.

### 5.6 P2 · Scorecard — `facility/analytics/scorecard.py`

PDF formula, unchanged (A6):
`metric = 100 − 40·min(1, anomaly_hours_7d/24) − 60·min(1, max(0, vs_baseline_pct)/30)`,
`vs_baseline_pct = mean(last 7 d)/mean(previous 21 d) − 1`,
`overall = mean(metrics) − 10 × compound days (7 d)`, clipped 0-100.
Exposes per metric `score, anomaly_hours_7d, vs_baseline_pct, anomaly_penalty, trend_penalty` and overall
`metric_mean, compound_days_7d, compound_penalty, method`. `method` starts with "MVP decision-support score, not a
certified rating". Tests: `test_metric_score_formula` (8 cases), `test_scorecard_structure_and_compound_penalty`,
`test_scorecard_clipped_at_zero`.

### 5.7 P2 · Engine — `facility/analytics/engine.py`

`run_analytics(df, config=None)` runs 5.3 → 5.6 and fills `params` with every value the explainability panel
shows (method strings, thresholds, rules, band σ per metric, forecast method used, timings in ms).
Test: `test_engine_params_expose_explainability`.

### 5.8 P3 · Recommendation engine — `facility/recommendations/` (hard part)

```
recommend(event) ─ template_for(event) ──────────────────────────► Recommendation(source="template", reason)
                 └ use_llm? ─ cache hit? ─ _call_llm(SYSTEM, prompt, 4 s) ─ parse_llm_json ─► source="llm"
                                   any LLMUnavailable / Exception ──► template + fallback_reason
```

* `prompts.py`: a **system prompt** fixing output to `{"action", "assumption"}` JSON, word limits, "never invent
  readings"; the user message is JSON: facility, risk type, what that risk means, severity, window, evidence,
  the template action as a reference, responsible roles.
* `_call_llm`: key from env (the app copies `st.secrets` into env); `anthropic.Anthropic(timeout=4, max_retries=0)`;
  maps `APITimeoutError → "timeout"`, `APIConnectionError → "network error"`, `AuthenticationError → "invalid API
  key"`, other `APIError` → "API error (…)"; empty text → "empty response". Model `claude-haiku-4-5-20251001`.
* `parse_llm_json`: finds the `{…}` object even inside prose or code fences, `json.loads`, requires both fields as
  non-empty strings, normalises whitespace, rejects > 60 / > 35 words. Failures raise with a precise reason.
* Cache: key = risk type, metrics, severity, **rounded evidence**, model; thread-safe lock; failures are not
  cached (next refresh retries).
* `recommend_all`: rank (severity, then live > compound > forecast, then newest), only the top `MAX_LLM_CALLS`
  use Claude, concurrently in a thread pool, so worst-case added latency ≈ one timeout, not three.
* `recommend()` never raises — even a broken template returns a generic card with the reason.

| Required case | Test |
|---|---|
| Template path | `test_template_path_when_llm_disabled` |
| Successful LLM path | `test_successful_llm_path`, `test_real_call_llm_success_with_fake_client` |
| JSON wrapped in prose/fences | `test_llm_json_wrapped_in_prose_is_accepted` |
| Invalid JSON (7 variants) | `test_invalid_json_falls_back` |
| Missing API key | `test_missing_api_key_falls_back` |
| Timeout / network / auth / unexpected | `test_failures_fall_back`, `test_sdk_error_mapping` |
| Caching | `test_cache_hit_avoids_second_call`, `test_cache_misses_when_evidence_changes`, `test_failures_are_not_cached`, `test_thread_safety_of_cache` |
| Ranking, cap, concurrency | `test_recommend_all_ranks_and_caps_llm`, `test_llm_calls_run_concurrently` |
| Never raises | `test_recommend_never_raises_even_if_template_breaks` |

### 5.9 P3 · Live Claude check (do this once you have a key)

```bash
# PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."    macOS/Linux: export ANTHROPIC_API_KEY=sk-ant-...
python scripts/smoke_llm.py
```

Expected: pass 1 prints `source=llm` for the top risks with plain-language actions quoting the evidence numbers;
pass 2 is near-instant with `cache_hits` > 0. If a line says `source=template reason=…`, the reason is the
diagnosis (`invalid API key`, `network error`, `timeout`, `invalid JSON (...)`). If JSON is rejected often, read
the raw text in a debugger and tighten `SYSTEM` — never loosen the validator.

### 5.10 P3 · Charts and dashboard

`facility/viz/charts.py` — charts only draw: `plot_forecast` (actual, faint "before modification" line,
expected same-hour baseline, 24 h forecast with band, anomaly markers with z on hover, amber now-line via
`add_shape`), `plot_anomaly_timeline` (dot per flagged hour, colour = |z|), `plot_scorecard`.
`dashboard/`: `style.py` (CSS, cards; **all dynamic text is HTML-escaped**, including Claude output),
`insights.py` (headline, status, "why" text — pure, tested), `roles.py`, `tab_*.py`, `explain.py`.

### Phase 2 gate

`pytest` green; `python scripts/benchmark.py` under 3 s per line; app still runs on the mock. Git:
`p1/injection-state`, `p1/scenarios`, `p2/risk-events`, `p2/scorecard`, `p3/llm`, `p3/charts`.

---

## 6. Phase 3 — Integration (hours 28-38)

### 6.1 Swap mock for the real pipeline

In `app.py`, `analyse(scenario, injections)` calls `build_working_df` + `run_pipeline`. If anything breaks here,
it is a contract mismatch: open a `contract-change` PR, do not edit another person's folder.

### 6.2 `app.py` — state, caching, callbacks (hard part)

| Mechanism | Implementation | Why |
|---|---|---|
| Base data | `@st.cache_data get_base()` | Loaded once per server |
| Analytics | `@st.cache_data(max_entries=64) analyse(scenario, injections)` | The recipe is the key: repeat views are instant; cached objects are copies, so nothing can be mutated |
| Warm-up | first run precomputes the 3 scenarios (`PRECOMPUTE_SCENARIOS`) | Scenario toggles feel instant (PRD "pre-computed toggles") |
| State | `session_state.scenario`, `.injections`, `.flash` | Only the recipe is stored |
| Buttons | `on_click` callbacks edit the recipe **before** the rerun | The page renders the new state on the same click; no double rerun |
| Reset | callback sets `(None, ())`; disabled when nothing is modified | Exact restore (`test_reset_restores_identical_results`) |
| API key | `st.secrets` copied to env if present; toggle disabled without a key | Offline-first; cards say "Template - no API key" |
| Error states | data load failure → `st.error` + fix instruction + `st.stop()`; analysis failure of a modification → warning + fall back to original; LLM failures → templates | No traceback ever reaches the screen |

### 6.3 Role-based views (`dashboard/roles.py`)

One `AnalyticsResult`, three lenses. Each template names responsible roles; `split_for_role` returns
(role's actions, others). Admin additionally owns every high-severity risk (escalation). Others' actions stay
visible in a collapsed section. Each role gets its own question and an overview panel: Admin = score breakdown
with penalties, Operations = next-24 h peaks and totals, Sustainability = change vs baseline. Tests:
`test_role_split_is_a_partition`, `test_admin_sees_every_high_risk`, `test_roles_render`.

### 6.4 Explainability — where each judge question is answered

| Question | Where |
|---|---|
| What data, what is synthetic? | How this works → Data (source note, window, units, active modifications, ground-truth table) |
| Threshold, baseline method? | → Detection & forecast (method string, \|z\| threshold, std floor, measured recall/precision) |
| How was the forecast made? | → Detection & forecast; caption under the forecast chart (method actually used, band σ) |
| Why was a risk created, on what evidence? | "Why this appeared" under every card (rule + numbers + evidence JSON); → Risk rules |
| Why this recommendation, AI or template, which assumption? | Card badges (AI-written / Template - reason) + assumption line; → Recommendations tab of the panel (table + system prompt) |
| How is the score computed? | → Scorecard (formula, per-metric penalties, arithmetic of the overall) |

### 6.5 Threshold tuning (P2)

```text
$ python scripts/tune_threshold.py      # ~3-4 min: 40 configurations x 5 seeds + 6 demo cases
Selected: {'wkday': True, 'pool': 1, 'excl': True, 'z': 4.5, 'recall': 1.0, 'precision': 0.86, 'fp_%': 0.16}
```

Rule: recall ≥ 0.8, every scenario/injection ≥ 70 % of modified hours flagged, then highest precision. Change
`Z_THRESHOLD` only through an all-three PR and update the README table.

### 6.6 Integration tests (`tests/test_pipeline.py`, `tests/test_app.py`)

data → analytics → risk → recommendation → scorecard: `test_full_chain_fixture_under_3s`,
`test_live_injection_loop_under_3s_on_full_data`, `test_injection_changes_everything_the_judge_sees`
(detection, one risk event, its recommendation, lower score, higher forecast), `test_reset_restores_identical_results`,
`test_each_scenario_produces_its_risk`, `test_ground_truth_evaluation`, `test_contract_between_p2_and_p3`,
`test_pipeline_rejects_bad_data`. UI: `test_first_screen`, `test_inject_updates_and_reset_restores`,
`test_scenario_toggle`, `test_roles_render`, `test_offline_labels_are_visible`.

### Phase 3 gate

Click Inject → forecast chart, risk card, recommendation and score change in under 3 s; role switch changes the
cards; Reset restores the original numbers; `pytest` green. Freeze scope after this.

---

## 7. Phase 4 — Polish, rehearsal, freeze (hours 38-48, bug fixes only)

### 7.1 UI checklist (verified in `docs/screenshots/`)

Headline + score + top action visible at 1280×720 · teal/amber/red used consistently · units on axes · now-line ·
dashed forecast with band · every card has title, action, assumption, priority, roles, source · buttons give a
toast · empty state "No active risks in the last 72 hours" · 1024×768 works (collapse the sidebar on a
projector).

### 7.2 Demo run sheet (3 minutes)

| Time | Click | Say |
|---|---|---|
| 0:00 | Overview (original data) | "A water surge started at 14:00 — 2.8× normal for this hour — and the forecast says tomorrow's 07:00 peak will be high too. The manager sees it now, not from a complaint." |
| 0:40 | Sidebar → Energy, spike, Inject | "Something happens right now." Point at score 96 → 81, risks 2 → 5, new energy card, headline |
| 1:10 | Forecast & Anomalies → Energy | Red markers, faint "before" line, forecast carried forward, band |
| 1:30 | Role → Operations, then Sustainability | Same analytics, different action queue |
| 1:50 | Reset; scenario "Night pipe leak" | Night-only incidents: "flow while wards sleep = leak" |
| 2:15 | Card → Why this appeared; How this works | Rule, z-score, threshold, recall 100 % / precision 91 %, AI vs template |
| 2:40 | Close | Limits: synthetic data, rules-based compound risk. Next: real meters, many facilities |

### 7.3 Rehearsals

1. Online, full run, timed. 2. **Wi-Fi off**: every card says "Template - …", nothing crashes — present it as
"works without the cloud". 3. Fresh clone on another laptop using only the README. 4. Second screen / projector.
5. Record the 2-minute backup video (OBS), keep it outside git (`recordings/` is ignored) and on a USB stick.

### 7.4 Deployment (optional, after the judged demo)

Streamlit Community Cloud → New app → repo, branch `main`, file `app.py`, Python 3.12 → Secrets:
`ANTHROPIC_API_KEY = "…"`. The dataset regenerates on first start. Keep the local run as the primary demo
(PRD §7.1).

### 7.5 Freeze

```bash
git checkout main && git pull && pytest && git tag demo-v1 && git push origin demo-v1
```

---

## 8. Debugging additions to the PDF's error toolkit

| Symptom | Cause | Fix |
|---|---|---|
| Inject click changes nothing | Recipe unchanged (same metric/kind/magnitude/hours already injected) | Expected: injections replace per metric. Change magnitude or metric |
| Every card says "Template - no API key" | Key not in env/secrets for the process running Streamlit | Set the env var in the **same terminal** before `streamlit run`, or use `.streamlit/secrets.toml` |
| "Template - invalid JSON (...)" | Model returned prose or overlong text | Tighten `SYSTEM`; keep the validator strict |
| "Template - timeout" on venue Wi-Fi | Slow network | Expected; the 4 s cap protects the demo. Turn the AI toggle off before presenting if the network is bad |
| First load ~4-5 s | Scenario warm-up | Expected once per server start; set `PRECOMPUTE_SCENARIOS = False` to trade it for slower first toggles |
| Too many anomaly markers after editing the generator | Threshold tuned for the old data | Re-run `scripts/tune_threshold.py` |
| Precision/recall text missing | `data/injected_anomalies.csv` absent | `python scripts/generate_data.py` |
| `width="stretch"` TypeError | Older Streamlit | `pip install -r requirements.txt` (pinned 1.64) |

---

## 9. Known limitations (state them before a judge finds them)

Synthetic data (real facility data is not public; injected anomalies make accuracy measurable) · compound risk is
a rule, not a learned correlation · a drop keeps the metric's risk type (the card title and direction say
"drop") · the forecast band is an approximate constant-width band · the missed-pickup ramp is detected once it
passes ~1.5 × normal and may appear as two incidents · the live Claude path must be smoke-tested with your key
(§5.9).
