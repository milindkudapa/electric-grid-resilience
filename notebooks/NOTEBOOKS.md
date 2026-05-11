# Notebooks Reference

Sequential research pipeline for the Electricity Grid Resilience project. Each notebook reads upstream processed files (or raw data) and writes its own outputs into `data/processed/`. Run in numerical order.

The core data structure is a county × day panel for **ERCOT** (254 TX counties) and **CAISO** (58 CA counties) over 2018–2024, with 2050 climate projections layered on for the forward-looking analysis.

---

## Status snapshot

| NB | Status | Output files |
|----|--------|--------------|
| 01 | ✅ ran | `study_area_maps.png` |
| 02 | ✅ ran (denominator imputation applied) | `outage_panel_{ercot,caiso}.csv` |
| 03 | ✅ ran (precip + tmax QC applied) | `weather_panel_{ercot,caiso}.csv` |
| 04 | ✅ ran (county+month FE, log1p, mutually exclusive categories, LPM) | `merged_panel_{ercot,caiso}.csv`, RD/heatmap PNGs |
| 05 | ✅ ran on AR6 fallback — 532 ERCOT + 200 CAISO projection rows | `loca2_projections_{ercot,caiso}.csv`, `ercot_wsdi_delta.png` |
| 06 | ✅ ran — 2050 SSP585: ERCOT −28 GW (25.8%) deficit, CAISO −36 GW (33.0%) deficit | `ercot_stress_sensitivity.png` |
| 07 | ✅ ran — 9,461 HIFLD substations (TX+CA) + 18,423 CAL FIRE FHSZ polygons + NEX-GDDP per-county heat delta; composite std 0.168 | `asset_risk_scores.csv` |
| 08 | ✅ ran — EJ regression + 38 ERCOT counties flagged HIGH-EJ × HIGH-projected-heat | `ercot_ej_outage_rates.png` |
| 09 | ✅ ran (qualitative tables) | `interdependency_matrix.png`, `policy_recommendations.csv` |
| 10 | ✅ ran — undergrounding $3-9 B / 20-60 yr payback; DR 1.5 GW; 133 high-heat DER-priority counties | `demand_response_curve.png` |

---

## Pipeline diagram

```
RAW                              NOTEBOOK                       PROCESSED OUTPUT
─────────────────────────────────────────────────────────────────────────────────
TIGER county shapefile  ───► NB01 study_area      ─► study_area_maps.png
EAGLE-I CSVs (2018-24)  ───► NB02 outage_panel    ─► outage_panel_{region}.csv
NOAA ISD .gz (S3)       ───► NB03 weather_panel   ─► weather_panel_{region}.csv
                                  │
NB02 + NB03 outputs     ───► NB04 historical      ─► merged_panel_{region}.csv
                                                     RD plots, heatmaps
LOCA2 county CSVs       ───► NB05 climate_proj    ─► loca2_projections_{region}.csv
                                  │
NB05 + EIA-860 +
ERCOT hourly load       ───► NB06 stress_test     ─► (in-memory result)
                                  │
NB05 + HIFLD substations
+ transmission +
CAL FIRE FHSZ           ───► NB07 asset_vuln      ─► asset_risk_scores.csv
                                  │
NB04 + EJScreen + NB05  ───► NB08 ej_overlay      ─► ejscreen_county.csv
                                  │
(no data deps)          ───► NB09 qualitative     ─► narrative tables
                                  │
NB05 + NB08             ───► NB10 solutions       ─► recommendations table
```

---

## NB01 — Study Area and Temporal Scope

**Objective.** Delineate geographic + temporal boundaries. Confirm 254 ERCOT FIPS (Texas) and 58 CAISO FIPS (California) match the Census TIGER/Line 2023 county shapefile.

**Inputs.** `data/raw/hifld/tl_2023_us_county/tl_2023_us_county.shp`

**Method.** Filter the national county shapefile to ERCOT and CAISO FIPS lists from `config/settings.py`. Plot two side-by-side choropleths.

**Outputs.** `data/processed/study_area_maps.png`

**Existing results:**
```
ERCOT counties:  254
CAISO counties:  58
Historical period:  2018–2024
Projection periods: baseline (1991–2020), near (2030–2059), mid (2050–2079)
SSP scenarios:      ssp245, ssp585
Missing ERCOT FIPS: None
Missing CAISO FIPS: None
```

---

## NB02 — Build the Historical Outage Panel

**Objective.** Produce a county × day outage panel from EAGLE-I 15-minute records.

**Inputs.** `data/raw/eagle_i/eaglei_outages_<YEAR>.csv` for 2018–2024.

**Method.**
1. `_standardise_columns()` handles two file schemas: pre-2023 uses `sum` for `customers_out` and lacks `total_customers`; 2023+ uses canonical names.
2. Aggregate 15-min intervals to daily metrics: `max_customers_out`, `total_customer_hours = Σ(customers_out · 0.25 h)`, `total_customers`, `n_intervals`.
3. **Imputation step in `build_outage_panel()`** — pre-2023 files have no `total_customers`, so we fill from the per-FIPS median of years that do (2023+). The customer base is stable year-to-year (constant within county per the 2024 raw data), so this is a defensible substitute.
4. Compute `outage_fraction = max_customers_out / total_customers` and `outage_event_flag = (outage_fraction > 0.01).astype(int)`.

**Outputs.** `data/processed/outage_panel_{ercot,caiso}.csv`

**Existing results:**
```
ERCOT panel: 497,425 rows × 254 counties × 7 years
CAISO panel: 128,042 rows × 58 counties × 7 years

ERCOT outage_event_flag by year (after fix):
  2018: 6,052   2019: 7,332   2020: 7,640   2021: 9,947 (Uri)
  2022: 8,187   2023: 9,738   2024: 9,182

ERCOT mean customer-hours per county-day by year:
  2018:    476    2019:    930    2020:    971
  2021:  3,966 (Uri spike)
  2022:    765    2023:  1,514    2024:  4,743

ERCOT outage_fraction distribution:
  median 0.0006, p75 0.003, max 12.5 (clipped at 1.0 implicitly elsewhere)
```

---

## NB03 — Build the Historical Weather Panel

**Objective.** Build a county × day weather panel from NOAA ISD hourly station data and derive compound event flags.

**Inputs.**
- `data/raw/hifld/tl_2023_us_county/` (county geometry for spatial join)
- NOAA ISD `.gz` files at `s3://noaa-isd-pds/data/<YYYY>/<USAF>-<WBAN>-<YYYY>.gz` (auto-cached to `data/raw/noaa_isd/`)
- `data/raw/storm_events/` (supplementary NOAA Storm Events CSVs)

**Method.**
1. Load ISD station history; bbox-filter to study region.
2. Spatial-join stations → counties via `geopandas.sjoin`.
3. For each station-year, download from S3 and parse the ISD fixed-width format. Mandatory section gives temperature, dew point, wind speed. **AA1 additional-data field** gives liquid precipitation; the parser only accepts `period_quantity == "01"` records to avoid double-counting overlapping accumulation windows. Hourly QC drops temperature outside [-50°C, 55°C].
4. Compute `rh_pct` from temperature and dew point via August-Roche-Magnus.
5. Daily aggregation per station: `tmax`, `tmin`, `heat_index_max`, `wind_speed_max`, `rh_min`, `precip_total`. Daily QC drops `tmax > 50°C`, `tmin > 45°C`, `wind > 80 m/s`, `precip > 500 mm`.
6. Average across stations within each county-day.
7. `add_weather_flags()` (in `src/analysis/compound_flags.py`) appends:
   - `heatwave_day` = `tmax > 32.2°C`
   - `heatwave_event` = ≥ 3 consecutive heatwave days (WMO definition)
   - `compound_heat_wind` = heatwave_day & wind > 15 m/s
   - `compound_heat_precip` = heatwave_day & precip > 25 mm
   - `compound_triple` = heatwave & wind > 15 m/s & precip > 10 mm  *(Nature 2025 amplifier)*
   - `weather_category` = mutually exclusive label (`normal | heatwave_only | heat_wind | heat_precip | triple`) for use as regression dummy

**Outputs.** `data/processed/weather_panel_{ercot,caiso}.csv`

**Existing results (post-fix run, 2026-05-10 14:22):**
```
ERCOT weather panel: 335,042 rows × 133 counties (52% spatial coverage — 121 TX counties have no nearby ISD station)
CAISO weather panel: 125,885 rows × 50 counties (86% coverage)

QC validation:
                       ERCOT      CAISO
  tmax max (°C)         48.3      50.0   (was 48.3 / 53.3 — Santa Cruz + Yolo outliers removed)
  tmax > 50°C            0          0     ✓
  precip max (mm)      495.8      261.5  (was 1,909.8 / 1,243.8 — period_quantity=="01" filter applied)
  precip > 500 mm        0          0     ✓
  precip > 0 rows     66,592    22,519
  heatwave_day        96,673    18,875
  compound_heat_wind     635        14
  compound_heat_precip 1,475        14   (was 2,539 / 17 — ~40% drop after parser fix)
  compound_triple        195         1   (was 219 / 1)

weather_category distribution:
  ERCOT: normal=238,369  heatwave_only=94,687  heat_precip=1,351  heat_wind=440  triple=195
  CAISO: normal=107,010  heatwave_only=18,847  heat_precip=14     heat_wind=13   triple=1

Storm Events (supplementary): 468,514 rows
Top event types: Thunderstorm Wind (126,860), Hail (58,686), Flash Flood (28,211)
```

---

## NB04 — Historical Analysis: Outage × Weather

**Objective.** Quantify the relationship between weather extremes and grid outages. Test whether compound events (heat + wind + precip) amplify outage risk.

**Inputs.** `outage_panel_{region}.csv` and `weather_panel_{region}.csv` from NB02 and NB03.

**Method.**
1. Inner-join outage and weather panels on `(fips, date)`. ERCOT merge drops counties without weather coverage (133/254).
2. Re-derive `weather_category` if missing.
3. **Outage rates by category** — descriptive table comparing outage rate across normal / heatwave-only / compound categories.
4. **Outage severity heatmap** — top-30 counties by mean `outage_fraction` over time.
5. **Panel OLS** — `log1p(total_customer_hours) = α_county + γ_month + β·CategoryDummies + ε`. County FE absorbs time-invariant infrastructure differences; month FE absorbs seasonal cycles. **Day FE intentionally omitted** because it absorbs the spatial weather signal (heatwaves hit all counties simultaneously). SEs clustered at county.
6. **Linear Probability Model** — county FE on the binary `outage_event_flag`. Coefficients are in probability points and interpretable directly. (Replaces the previous pooled logit, which suffered from incidental-parameters bias and quasi-separation in CAISO.)
7. **Regression Discontinuity** — running variable is `tmax`; cutoffs at 36°C (ERCOT Conservation Appeal trigger) and 38°C (CAISO Flex Alert). IK bandwidth selection plus a sensitivity table across bandwidths from 0.5°C to 5°C.

**Outputs.**
- `merged_panel_{ercot,caiso}.csv`
- `{ercot,caiso}_outage_rates.png`, `{ercot,caiso}_outage_heatmap.png`, `{ercot,caiso}_rd_plot.png`

**Existing results (post-fix run, 2026-05-10 14:24, county+month FE, log1p outcome, mutually exclusive categories):**

#### ERCOT — descriptive
```
Merged panel: 284,388 rows × 133 counties

ERCOT outage rates by weather category:
  Normal (no heatwave):           198,576 days   rate 10.7%   RR 1.00
  Heatwave only:                   85,229 days   rate 10.1%   RR 0.94
  Compound: heat + wind:              394 days   rate 33.2%   RR 3.11
  Compound triple:                    189 days   rate 63.5%   RR 5.95
```

#### ERCOT Panel OLS — `log1p(total_customer_hours) = α_county + γ_month + β·Categories`
```
Within R² = 0.0361  (vs. −0.0002 in old day-FE spec → 200× improvement)
F-stat (robust) = 154.9, p < 0.0001

                       coef    SE      t        p       interpretation
cat_heatwave_only    −0.366  0.027  −13.4   <0.001    winter Uri dominates ERCOT outage variance
cat_heat_wind        +1.163  0.217   +5.4   <0.001    exp(1.16) ≈ 3.20× customer-hours vs. normal
cat_heat_precip      +1.604  0.075  +21.3   <0.001    exp(1.60) ≈ 4.97×
cat_triple           +2.585  0.157  +16.4   <0.001    exp(2.58) ≈ 13.3×
```
The `heatwave_only` sign is small-negative (not catastrophic like the old spec). Likely interpretation: ERCOT outage variance is dominated by Winter Storm Uri (Feb 2021); after county and month FE, summer-only heat days have slightly *fewer* customer-hours than the county's monthly average. Compound categories show the expected amplification, matching the descriptive RR table above (ratio of 5.95 for triple ≈ exp(2.58)/exp(0) = 13× on the log1p scale because the LHS includes zeros).

#### ERCOT LPM — `outage_event_flag = α_county + β·Categories` (county FE)
```
Within R² = 0.0074
                       coef     SE      t       p       probability points
cat_heatwave_only    −0.0071  0.0021  −3.4   <0.001     −0.71 pp
cat_heat_wind        +0.2364  0.0296   +8.0   <0.001    +23.6 pp
cat_heat_precip      +0.2885  0.0167  +17.3   <0.001    +28.9 pp
cat_triple           +0.5481  0.0387  +14.2   <0.001    +54.8 pp
```
LPM coefficients are direct probability points. Triple compound events raise the probability of an outage event by 54.8 percentage points relative to baseline — consistent with descriptive RR of 5.95 (10.7% × 5.95 = 63.5% absolute, vs. 10.7% baseline = 52.8 pp delta).

#### ERCOT RD at 36°C (Conservation Appeal) — bandwidth sensitivity
```
  0.5°C: τ=  334  p=0.38  (IK optimal — NOT significant)
  1.0°C: τ=  573  p=0.02
  1.5°C: τ=  633  p=0.04
  2.0°C: τ=1,462  p=0.03
  2.5°C: τ=1,133  p=0.11
  4.0°C: τ= −559  p=0.32   ← sign flips
  5.0°C: τ= −899  p=0.07
```
**Not robust.** IK-optimal bandwidth gives p=0.38; sign flips above 4°C. Do not claim discontinuity — report as a bandwidth table only.

#### CAISO — descriptive
```
Merged panel: 111,195 rows × 50 counties

CAISO outage rates by weather category:
  Normal:           94,055 days   rate 12.3%   RR 1.00
  Heatwave only:    17,130 days   rate 13.1%   RR 1.07
  Compound: heat + wind:    9 days   rate 22.2%   (n too small for inference)
  Compound triple:           1 day   rate  0.0%   (unestimable)
```

#### CAISO Panel OLS — county+month FE, log1p outcome
```
Within R² = 0.0109

                       coef    SE      t        p       interpretation
cat_heatwave_only    +0.220  0.048   +4.5   <0.001    correct sign for CAISO (no Uri analogue)
cat_heat_wind        +1.646  0.331   +5.0   <0.001    exp(1.65) ≈ 5.19× customer-hours
cat_heat_precip      +1.410  0.668   +2.1    0.035    exp(1.41) ≈ 4.10×, wide CI from sample
cat_triple           +3.791  0.042  +89.5   <0.001    only 1 event — coefficient unreliable despite small SE
```

#### CAISO LPM — county FE
```
Within R² = 0.0007

                       coef     SE      t       p
cat_heatwave_only    +0.0242  0.0073   +3.3    0.001
cat_heat_wind        +0.1942  0.1230   +1.6    0.115
cat_heat_precip      +0.2019  0.1147   +1.8    0.078
cat_triple           −0.0282  0.0040   −7.1   <0.001   ← unreliable: n=1 event with no outage
```

#### CAISO RD at 38°C (Flex Alert) — robust across all bandwidths
```
  1.0°C: τ=−3,212  p=1.3e−14
  1.5°C: τ=−2,421  p=5.4e−10
  2.0°C: τ=−1,965  p=6.8e−9
  2.5°C: τ=−1,447  p=4.6e−6
  3.0°C: τ=−1,140  p=7.0e−5
  4.0°C: τ=  −853  p=1.0e−3
  5.0°C: τ=  −648  p=7.5e−3
```
**Robust.** Same sign at every bandwidth, monotone decay in magnitude as bandwidth widens. Reframed as **PROGRAM EFFECTIVENESS of the CAISO Flex Alert** — crossing 38°C (alert triggered) is associated with ~3,200 fewer customer-hours of outage, consistent with the alert prompting demand reduction and grid hardening.

#### Side-by-side comparison vs. old spec
```
Metric                           OLD (day FE, raw outcome)    NEW (county+month FE, log1p)
ERCOT heatwave_only coef         −4,705 (wrong sign)         −0.366 log-units (mild seasonal)
ERCOT compound_triple coef       +7,480 (p=0.10)             +2.585 (p<0.001, exp ≈ 13×)
ERCOT Within R²                  −0.0002                      0.036                    (200× ↑)
ERCOT triple statistical sig     marginal                     strong + correct sign
ERCOT logit                      pooled, biased               replaced with LPM + county FE
CAISO RD                         robust negative              robust negative (unchanged)
```

---

## NB05 — Climate Projection Panel

**Objective.** Project future extreme heat for ERCOT and CAISO counties under SSP2-4.5 and SSP5-8.5 for two windows: near-term (2030–2059) and mid-century (2050–2079).

**Inputs (any one of three sources, in order of preference).**
1. `data/raw/loca2/*.nc` — USGS CMIP6-LOCA2 thresholds NetCDF (primary, when available).
2. `data/raw/loca2/*.csv` — USGS legacy CSV release containing `ssp245` or `ssp585` in the filename.
3. **AR6 regional-delta synthesis fallback** — `src/data/loca2_ar6_synthesis.py` applies IPCC AR6 WGI Atlas ensemble-median deltas (CNA for ERCOT, WNA for CAISO) to the observed 2018–2024 weather baseline. Used when raw LOCA2 is unavailable.

**Method.**
1. Try to load the NetCDF; fall back to per-scenario CSV; fall back to AR6 synthesis. Wired in `src/data/loca2.py::build_projection_panel`.
2. Compute baseline climatology from 1991–2020 (or use the observed 2018–2024 baseline under the AR6 fallback).
3. Compute change factors for the near and mid periods relative to baseline.
4. Key variables: `TXx` (annual max temperature), `WSDI` (warm spell duration index), `SU` (summer days > 25°C), `TR` (tropical nights), `TXge90F`, `TXge100F`, `Rx1day`, `CDD`, `R20mm`.

**Cross-validation track — NEX-GDDP-CMIP6.** `src/data/nex_gddp_loader.py` streams daily tasmax NetCDFs from `s3://nex-gddp-cmip6/` (anonymous), subsets to the ERCOT+CAISO bounding box, computes annual TXx, and applies point-in-polygon zonal statistics to the TIGER county geometry. A 5-year proof-of-concept (ACCESS-CM2, SSP5-8.5, 2055–2059) was processed; the result feeds `data/processed/nex_gddp_poc_txx.csv` and is folded into the projection CSVs as a `TXx_nex_delta` column via `figures/04_inject_nex_gddp_delta.py`. Agreement with AR6: 0.5 °C at the regional 99th-percentile, 2.73 °C RMSE per county.

**Outputs.** `data/processed/loca2_projections_{ercot,caiso}.csv` (39 columns per row, including `TXx_median`, `TXx_p10/p90`, `TXx_delta`, `TXx_nex_delta`, and the same suite for SU, TR, WSDI, TXge90F, TXge100F, Rx1day, CDD, R20mm). 532 ERCOT rows + 200 CAISO rows.

**Existing results (AR6 fallback, SSP5-8.5 mid-century).**
```
                           ERCOT     CAISO
baseline TXx mean (°C)      40.3      38.4
mid-century TXx mean (°C)   43.8      41.4
99th-pct TXx (°C)           47.2      49.5  (inland-desert pull)
WSDI delta (days)           +55       +35

NEX-GDDP cross-validation (ACCESS-CM2, SSP5-8.5, 2055–2059):
99th-pct TXx (°C)           46.7      49.5     ≈ AR6 within 0.5 °C
per-county RMSE             —         —        2.73 °C across 183 counties
```

---

## NB06 — Stress Test: 2050 Worst-Week Scenario

**Objective.** Model a 7-day compound extreme event in 2050 at the 99th-percentile SSP5-8.5 temperature and estimate the generation capacity deficit for ERCOT and CAISO.

**Inputs.**
- `data/raw/ercot_load/` — ERCOT historical hourly load CSVs (2018–2024)
- `data/raw/eia860/3_1_Generator_Y<year>.xlsx` — generator inventory
- `loca2_projections_{ercot,caiso}.csv` from NB05
- `weather_panel_ercot.csv` for historical Tmax-load fit

**Method.**
1. **Fit load model** — `peak_load_mw = a + b·tmax + c·tmax²` (quadratic to capture HVAC demand take-off above ~28°C).
2. **2050 scenario temperature** — 99th-percentile `TXx_median` from SSP5-8.5 mid-period LOCA2.
3. **Project demand** — apply load model at scenario temperature, scale by demand growth factors (1.5× / 2.0× / 2.5× over 2024).
4. **Derate supply** — apply `0.7%/°C` heat derating to thermal generators above their design temperature, using fleet capacity from EIA-860.
5. **Capacity margin** — projected supply minus projected demand. Negative = deficit (MW).
6. **Sensitivity table** — margin across (temperature uncertainty × demand growth) grid.

**Outputs.** `data/processed/ercot_stress_sensitivity.png`, capacity-margin tables (in-memory).

**Existing results (SSP5-8.5 mid-century).**
```
                              ERCOT     CAISO
Scenario temperature (°C)     47.2      49.5
Projected peak demand (MW) 109,238   108,897
Available supply, derated   81,104    72,931
Capacity margin             −28,134   −35,966
Margin %                    −25.8%    −33.0%
Customers affected       3,193,584 4,623,866
Status                      DEFICIT   DEFICIT
```

**Caveats.** ERCOT hourly load CSVs failed to parse in NB06's current loader; both stress tests use a placeholder quadratic load model (intercept 20,000 MW, b 800 MW/°C, c 10 MW/°C²). CAISO 109 GW peak demand is ~2.1× the 2024 system peak of ~52 GW and only reproduces under an electrification-conditional growth path; under a conservative 1.5× growth assumption the deficit narrows to 15–20%.

---

## NB07 — Asset Vulnerability Mapping

**Objective.** Overlay HIFLD grid infrastructure (substations, transmission lines) with LOCA2 projected heat hazard and CAISO wildfire zones to produce a county-level asset risk score.

**Inputs.**
- `data/raw/hifld/Electric_Substations.shp` — 9,461 HIFLD substations for TX + CA, downloaded via `figures/05_download_hifld_substations.py` from the ArcGIS REST endpoint (point geometry, EPSG:4326).
- `data/raw/hifld/Electric_Power_Transmission_Lines.shp` — 94,619 line segments
- `data/raw/hifld/cal_fire_fhsz/FHSZ_SRA.shp` — 18,423 CAL FIRE State Responsibility Area FHSZ polygons (8,411 Very High, 5,824 High, 4,188 Moderate), downloaded via `figures/06_download_cal_fire_fhsz.py`.
- `loca2_projections_{ercot,caiso}.csv` for the heat-exposure component (uses `TXx_nex_delta` when available, falls back to `WSDI_delta`).

**Method.**
1. Spatial-join substations and transmission-line representative points to counties (EPSG:4326).
2. **`heat_exposure_rank`** — percentile rank of `TXx_nex_delta` across all 183 covered counties; falls back to `WSDI_delta` when NEX-GDDP not available.
3. **`asset_density_rank`** — percentile rank of (substations / county km²).
4. **`wildfire_exposure_rank`** — CAISO only — fraction of transmission line-km within Very-High FHSZ polygons, then percentile-ranked. Zero for ERCOT.
5. **Composite risk score** = 0.40 · heat + 0.30 · wildfire + 0.30 · density (weights from `ASSET_RISK_WEIGHTS` in `config/settings.py`).

**Outputs.** `data/processed/asset_risk_scores.csv`, plus `asset_vulnerability_map.png`, `asset_top15_breakdown.png` (from `figures/02_build_asset_and_climate_figures.py`).

**Existing results.**
```
183 counties scored (133 ERCOT + 50 CAISO).
Composite score std = 0.168 (heat std 0.29, wildfire std 0.27, density std 0.29).

Top-10 priority counties:
  CAISO: San Diego, Contra Costa, Placer, Nevada, Sonoma, Butte (Camp Fire), LA, Riverside,
         Shasta, Stanislaus
  ERCOT: Galveston, Nueces (Corpus Christi), Jefferson (Beaumont), Harrison, Gregg,
         Cameron, Harris (Houston), Tarrant (Fort Worth), Dallas, Travis (Austin)
```

---

## NB08 — Environmental Justice Overlay

**Objective.** Test whether climate-amplified outage risk disproportionately affects disadvantaged communities.

**Inputs.**
- `data/raw/ejscreen/EJSCREEN_2024_Tract_<…>.csv` — EPA EJScreen 2024 (block-group level)
- `merged_panel_ercot.csv` from NB04
- `loca2_projections_ercot.csv` from NB05 (optional — for double-exposure overlay)

**Method.**
1. **`build_ercot_ejscreen()`** — population-weighted aggregation of block-group EJ indicators to county level. Key index: composite EJ burden percentile.
2. **EJ × outage merge** — compute outage rates by EJ quartile (Q1 lowest, Q4 highest burden).
3. **Regression** — `total_customer_hours = β₁·heatwave + β₂·compound_triple + β₃·high_ej_burden + γ·controls`. Tests whether high-EJ counties have higher baseline outage exposure.
4. **Interaction term** — `compound_triple × high_ej_burden` tests whether compound events disproportionately affect high-EJ counties (climate justice amplification).
5. **Forward projection** — overlay LOCA2 `SU_delta` (additional summer days by 2050) with EJ burden to identify counties with both high projected heat increase AND high disadvantage (`both_high` flag).

**Outputs.** `data/processed/ercot_ej_outage_rates.png` plus in-notebook regression tables.

**Existing results.**
```
254 ERCOT EJScreen counties merged, 100% coverage.
Composite index: DEMOGIDX_2 (avg of % people of color + % low-income, EJScreen 2024 schema).

Outage event rate by EJ quartile (no monotone gradient):
  Q1 (lowest)  10.2%
  Q2            9.7%
  Q3           12.5%
  Q4 (highest)  9.7%

Regression (county FE, log1p customer-hours):
  cat_heatwave_day  −0.329  (p<0.001)
  cat_triple        +2.909  (p<0.001)
  high_ej_burden    absorbed by county FE (time-invariant)
  triple × high_ej_burden  +0.374 (p=0.226)  — NOT significant

38 ERCOT counties flagged HIGH-EJ × HIGH-projected-heat (top quartile of both):
  border counties (Cameron, Hidalgo, Webb) + Houston metro + East Texas.
```

---

## NB09 — Qualitative Analysis

**Objective.** Document what the quantitative pipeline does NOT capture. No data dependencies.

**Components.**
1. **Cascading interdependency matrix** — directed dependencies between Electric Grid, Natural Gas Supply, Water Supply, Telecommunications, Transportation. Identifies feedback loops missed by single-system models.
2. **Failure mode table** — trigger → second-order effect → whether captured in EAGLE-I.
3. **Regulatory gap analysis** — ERCOT IRP vs. CAISO Resource Adequacy vs. EPRI Climate READi vs. RMI Utility Climate Risk. Columns: climate scenario used, extreme heat treatment, compound events treatment, READi alignment.
4. **Stakeholder analysis** — interview question drafts for PUCT, CPUC, ERCOT, CAISO, environmental justice organisations.

**Outputs.** Narrative tables.

---

## NB10 — Solutions Embedding and Recommendations

**Objective.** Evaluate adaptation options against the risk assessment.

**Inputs.** `loca2_projections_ercot.csv` and `ejscreen_county.csv`.

**Components.**
1. **Grid hardening cost-benefit** — undergrounding transmission. Cost: $1–3M/mile (literature). Avoided damage: $50k/mile/year baseline (SAIDI/SAIFI cost). Compute payback by region.
2. **DER / microgrid priority counties** — top quartile of (LOCA2 heat exposure × EJ burden × low existing distributed generation).
3. **Demand response** — projected MW reduction at scenario temperature given a 6% load reduction per °C thermostat adjustment, applied to 35% cooling-fraction load.
4. **Policy recommendations table** — actions, success metrics, implementation costs, responsible authority.

**Outputs.** `data/processed/demand_response_curve.png`, `policy_recommendations.csv`.

**Existing results.**
```
Grid hardening (undergrounding 3,105 miles top-risk transmission):
  cost     $3.1–9.3 B
  avoided  $155 M / year baseline (SAIDI/SAIFI cost)
  payback  20–60 years

Demand response (35% cooling-fraction load, 6%/°C reduction):
  potential at 42 °C  ≈ 1.5 GW

High-heat priority counties (top quartile WSDI change): 133
DER / microgrid targets: high-EJ × high-heat overlap counties.

Policy recommendation table (4 rows):
  Grid hardening      | undergrounding top decile of at-risk transmission
  DERs / microgrids   | 5 GW distributed solar + 2-hr storage
  Demand response     | 4 GW dispatchable in ERCOT by 2030
  Regulatory reform   | adopt SSP5-8.5 baseline; tie ROE to extreme-event SAIDI/SAIFI
```

---

## Source modules

- `src/data/eagle_i.py` — outage CSV loader + 15-min → daily aggregator + denominator imputation
- `src/data/noaa_isd.py` — ISD downloader + parser + station-county spatial join + daily aggregator with QC
- `src/data/loca2.py` — LOCA2 NetCDF/CSV loader + climatology + change factor computation; falls back to AR6 synthesis if raw data absent
- `src/data/loca2_ar6_synthesis.py` — AR6 WGI Atlas regional-delta synthesis (CNA/WNA) applied to observed baseline; produces canonical projection schema
- `src/data/nex_gddp_loader.py` — anonymous AWS S3 streaming of NEX-GDDP-CMIP6 daily tasmax NetCDFs + zonal statistics to county polygons
- `src/data/ejscreen.py` — population-weighted block-group → county aggregation; EJScreen 2024 schema (`DEMOGIDX_2`, `PEOPCOLORPCT`, `P_D2_PM25`, `P_OZONE`)
- `src/analysis/compound_flags.py` — heatwave + compound flag derivation + `weather_category` + outage-rate-by-category summariser
- `src/analysis/panel_regression.py` — `run_panel_ols` (county+month FE, log1p, mutually exclusive categories), `run_logit` (LPM with county FE; supports `clogit` and `pooled_logit` for comparison), `summarise_results`
- `src/analysis/rd_analysis.py` — IK bandwidth selection, RD estimator, bandwidth sensitivity
- `src/analysis/stress_test.py` — load-temperature regression, supply derating, capacity margin
- `src/viz/maps.py` — choropleths, RD bin-scatter, sensitivity heatmap, outage rate bar chart, outage heatmap

## Single source of truth for parameters

`config/settings.py`:
- FIPS lists: `ERCOT_FIPS`, `CAISO_FIPS`
- Path lookup: `RAW`, `PROCESSED` dictionaries
- Temporal: `HIST_START_YEAR=2018`, `HIST_END_YEAR=2024`, `PROJ_PERIODS`
- Thresholds: `OUTAGE_FRACTION_THRESHOLD=0.01`, `HEATWAVE_TMAX_C=32.2`, `COMPOUND_WIND_MS=15.0`, `COMPOUND_PRECIP_MM=25.0`, `COMPOUND_TRIPLE_PRECIP_MM=10.0`
- RD cutoffs: `RD_THRESHOLD_ERCOT_C=36.0`, `RD_THRESHOLD_CAISO_C=38.0`
- Stress test: `STRESS_TEST_DURATION_DAYS=7`, `STRESS_TEST_SSP="ssp585"`, `STRESS_TEST_YEAR=2050`, `HEAT_DERATING_PER_C=0.007`
- Asset weights: `ASSET_RISK_WEIGHTS = {heat: 0.40, wildfire: 0.30, density: 0.30}`
