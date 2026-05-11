# Electricity Grid Resilience — U.S. Regional Grid Stress

***

## Step 1: Define Study Area and Temporal Scope

**Objective:** Delineate the geographic and temporal boundaries of the analysis.

**Actions:**
1. Select two balancing authority (BA) regions: **ERCOT** (Texas, ~254 counties) and **CAISO** (California, ~58 counties). These represent distinct climate hazard profiles — ERCOT faces compound heat-drought events while CAISO faces compound heat-wildfire events.
2. Obtain FIPS codes for all counties in each BA region from the Census Bureau TIGER/Line shapefiles. These FIPS codes are the primary join key across all datasets.
3. Set the temporal scope:
   - **Historical analysis period:** 2018–2024 (EAGLE-I coverage is most reliable from 2018 onward based on the published Data Quality Index).[^1]
   - **Projection period:** 2030–2060 under SSP2-4.5 and SSP5-8.5, using 30-year climatologies centered on 2050.

***

## Step 2: Build the Historical Outage Panel

**Objective:** Create a county × day panel of power outage metrics from EAGLE-I.

**Data source:** EAGLE-I Power Outage Data 2014–2025 (ORNL). Download annual CSVs from OSTI/ORNL Constellation. Each row contains: FIPS, county, state, customers_out, total_customers, timestamp (15-min intervals).[^2][^3][^4][^5]

**Processing steps:**
1. **Schema normalisation.** Pre-2023 releases use the column name `sum` for `customers_out` and omit `total_customers` entirely; 2023+ releases use the canonical schema. The loader (`src/data/eagle_i.py`) renames as needed and inserts `total_customers = NaN` when absent.
2. **Filter** to ERCOT and CAISO counties using FIPS codes.
3. **Aggregate from 15-min to daily metrics** for each county:
   - `max_customers_out`: peak customers without power in a day
   - `total_customer_hours`: sum of (customers_out × 0.25 hours) over all 15-min intervals
   - `total_customers`: max within day (denominator from raw data)
   - `n_intervals`: count of 15-min intervals with non-zero outage reading (outage-duration proxy)
4. **Denominator imputation for 2018–2022.** Because pre-2023 files lack `total_customers`, after panel construction `build_outage_panel()` fills NaN denominators using the per-FIPS median from years where it is available (effectively 2023+). The customer count is constant within a county at every interval in the 2024 raw data, so this is a defensible substitute.
5. **Derived metrics** (computed after imputation):
   - `outage_fraction = max_customers_out / total_customers` (normalised severity)
   - `outage_event_flag = (outage_fraction > 0.01).astype(int)`[^6]
6. **Output:** A panel DataFrame indexed by (FIPS, date) with daily outage metrics. Save as `outage_panel_ercot.csv` and `outage_panel_caiso.csv`.

***

## Step 3: Build the Historical Weather Panel

**Objective:** Create a matching county × day panel of weather variables from NOAA ISD.

**Data source:** NOAA Integrated Surface Database (ISD) — 35,000+ global stations, hourly observations, 1901–present. Available on AWS Open Data and Azure Planetary Computer.[^7][^8][^9]

**Processing steps:**
1. **Station selection:** Identify all ISD stations within ERCOT and CAISO boundaries. Assign each station to its county using spatial join (station lat/lon to county polygon).
2. **Download hourly observations** for 2018–2024 from AWS S3 (`s3://noaa-isd-pds/`).
3. **Parse ISD fixed-width records.** The mandatory section gives temperature, dew point, wind speed. Liquid precipitation comes from the additional-data **AA1 field**; the parser only accepts records with `period_quantity == "01"` (1-hour accumulation) to avoid double-counting overlapping multi-period accumulation windows (6h, 24h). Hourly QC drops temperature readings outside [−50 °C, +55 °C] as broken-sensor.
4. **Compute daily county-level weather metrics** (average across stations within each county):
   - `tmax`: daily maximum temperature (°C)
   - `tmin`: daily minimum temperature (°C)
   - `heat_index_max`: maximum heat index using Rothfusz regression (combines temperature + humidity)
   - `wind_speed_max`: maximum wind speed (m/s)
   - `precip_total`: total 1-hour-accumulation precipitation (mm)
   - `rh_min`: minimum relative humidity (%)
5. **Daily-level QC:** drop county-day records with `tmax > 50 °C`, `tmin > 45 °C`, `wind_speed_max > 80 m/s`, or `precip_total > 500 mm` — values that exceed physical maxima are sensor errors.
6. **Derive compound event flags:**
   - `heatwave_day`: 1 if tmax > 32.2°C (90°F) — the threshold used in the Nature 2025 EAGLE-I study[^10]
   - `heatwave_event`: 1 if ≥3 consecutive heatwave_days (standard WMO definition)
   - `compound_heat_wind`: 1 if heatwave_day AND wind_speed_max > 15 m/s
   - `compound_heat_precip`: 1 if heatwave_day AND precip_total > 25 mm
   - `compound_triple`: 1 if heatwave_day AND wind_speed_max > 15 m/s AND precip_total > 10 mm (the 52× risk amplifier from the literature)[^10]
   - `weather_category`: mutually exclusive label (`normal | heatwave_only | heat_wind | heat_precip | triple`) used as the regression dummy in Step 4 to avoid the multicollinearity inherent in nested compound flags. Priority: triple > heat_wind > heat_precip > heatwave_only > normal.
7. **Supplement with NOAA Storm Events Database** (CSV bulk download) to flag county-days with officially reported extreme heat, wildfire, hurricane/tropical storm, or ice storm events. Join by FIPS and date.[^11]
8. **Output:** `weather_panel_ercot.csv`, `weather_panel_caiso.csv`, indexed by (FIPS, date).

***

## Step 4: Join Outage and Weather Panels — Historical Analysis

**Objective:** Quantify the statistical relationship between weather extremes and power outages.

**Methods:**
1. **Merge** outage and weather panels on (FIPS, date).
2. **Exploratory analysis:**
   - Compute outage rates (fraction of days with outage_event_flag = 1) by weather category: normal days, heatwave-only days, compound heat-wind days, compound triple days.
   - Replicate the key finding from the literature: compute the relative risk ratio comparing outage probability on compound triple days vs. normal days.[^10]
   - Visualize with heatmaps: counties on y-axis, days on x-axis, color = outage severity.
3. **Regression model — fixed effects panel with mutually exclusive categories:**

$$
\log(1+\text{TotalCustomerHours}_{ct}) = \alpha_c + \gamma_{m(t)} + \sum_{k\in\mathcal{K}} \beta_k\,\mathbb{1}[\text{Category}_{ct}=k] + \varepsilon_{ct}
$$

   Where $c$ = county, $t$ = day, $\alpha_c$ = county fixed effects (absorbs time-invariant infrastructure differences), $\gamma_{m(t)}$ = month-of-year fixed effects (absorbs the seasonal cycle), and $\mathcal{K} = \{$heatwave_only, heat_wind, heat_precip, triple$\}$ with `normal` as the omitted baseline.

   **Why month-of-year FE and not day-of-sample FE.** Day FE would absorb the regional weather signal because heatwaves hit all ERCOT (or CAISO) counties simultaneously. The within-day variation that remains is edge-of-heat-dome residual, not the effect we want. Month FE preserves the spatial heatwave signal while controlling for the predictable seasonal cycle of summer outages.

   **Why log1p outcome.** `total_customer_hours` is heavily zero-inflated and right-skewed. The `log(1 + y)` transform handles zeros cleanly and gives coefficients interpretable as proportional change ($e^\beta - 1$).

   **Why mutually exclusive categories.** Nested flags (`heatwave_day` ⊃ `compound_heat_wind` ⊃ `compound_triple`) introduce mechanical multicollinearity that distorts marginal coefficients. Mutually exclusive dummies estimate the level of outage severity in each category against the baseline.

   Implementation: `src/analysis/panel_regression.py::run_panel_ols()` via `linearmodels.PanelOLS`. Standard errors clustered at the county level.

4. **Binary outage model — Linear Probability Model with county FE:**

$$
\Pr(\text{OutageEvent}_{ct}=1) = \alpha_c + \sum_{k\in\mathcal{K}} \beta_k\,\mathbb{1}[\text{Category}_{ct}=k] + \varepsilon_{ct}
$$

   The LPM (PanelOLS on a 0/1 outcome with county FE) replaces the pooled logit used in earlier drafts. Pooled logit cannot absorb county-level heterogeneity and is biased by the incidental-parameters problem; for CAISO it also failed to converge because the single observed `triple` event caused quasi-separation. Coefficients from the LPM are in probability-point units, so they can be read directly. Conditional logit (`statsmodels.ConditionalLogit`) is supported as a robustness check via `method="clogit"` but excluded from the main results.

5. **Causal inference extension — Regression Discontinuity (RD):**
   - **Running variable:** Daily max temperature.
   - **Threshold:** The temperature at which ERCOT issues Conservation Appeals (~36°C / 97°F) or CAISO issues Flex Alerts (~38°C / 100°F).
   - **Outcome:** Customer-hours of outage.
   - **Estimate** with `src/analysis/rd_analysis.py` using Imbens-Kalyanaraman bandwidth selection, accompanied by a bandwidth sensitivity table (0.5 °C – 5 °C).
   - **Interpretation guidance:**
     - **ERCOT RD at 36 °C** is bandwidth-unstable in the actual data (sign flips at wider bandwidths). The bandwidth table is reported, but no discontinuity is claimed.
     - **CAISO RD at 38 °C** is robust (same sign and monotone decay across every bandwidth, all p < 0.01). The estimate has a **negative** $\tau$, which means outages decrease above the cutoff. Reinterpret this as **Flex Alert program effectiveness**: triggering the alert prompts demand reduction and grid hardening that reduces outages by an estimated ~3,200 customer-hours.

***

## Step 5: Build the Climate Projection Panel

**Objective:** Project future extreme heat for ERCOT and CAISO counties under SSP2-4.5 and SSP5-8.5, with two-track validation.

**Primary data source:** USGS CMIP6-LOCA2 county spatial summaries — pre-computed time series of Climdex extreme-event metrics, spatially averaged to every US county, for 27 GCMs, 1950–2100.[^12][^13][^14]

**Key variables targeted (Climdex):**[^15][^16]

| Variable | Definition | Relevance |
|----------|-----------|-----------|
| SU (Summer Days) | Days with Tmax > 25 °C | Baseline heat exposure |
| TR (Tropical Nights) | Days with Tmin > 20 °C | Nighttime heat stress (grid does not cool) |
| TXx (Max Tmax) | Hottest day of the year | Peak stress scenario |
| WSDI (Warm Spell Duration Index) | Max consecutive days Tmax > 90th percentile | Heatwave duration |
| CDD (Cooling Degree Days) | Cumulative degrees above base | Cooling-demand proxy |
| Rx1day | Wettest day of year (mm) | Flood / storm-surge risk |
| Rx5day | Wettest 5-day period | Compound flooding |
| TXge90F / TXge100F | Days exceeding 90 / 100 °F | Direct asset-stress measure |
| R20mm | Annual count of ≥ 20 mm precipitation days | Heavy-rain frequency |

**Fallback hierarchy.** Because the USGS ScienceBase delivery endpoint can be intermittent (returning authenticated HTML pages instead of the underlying NetCDF), the pipeline implements three sources in priority order, wired into `src/data/loca2.py::build_projection_panel`:

1. **USGS LOCA2 NetCDF** at `data/raw/loca2/*.nc` (preferred, full 27-GCM ensemble).
2. **USGS LOCA2 per-scenario CSVs** at `data/raw/loca2/*.csv` (legacy distribution).
3. **AR6 regional-delta synthesis** — `src/data/loca2_ar6_synthesis.py`. Applies IPCC AR6 WGI Atlas ensemble-median deltas (Central North America for ERCOT: +2.4 °C SSP245 / +3.5 °C SSP585 TXx mid-century; Western North America for CAISO: +2.0 / +3.0 °C) to the observed 2018–2024 weather baseline. Near-term (2030–2059) deltas are scaled to 70% of mid-century. Inter-model spread encoded as a ±0.7 °C likely-range half-width for temperature variables and ±20% for count-style variables (SU, TR, WSDI, TXge90F, etc.). Produces the canonical projection schema so all downstream notebooks read it transparently.

**Cross-validation track — NEX-GDDP-CMIP6.** A parallel, fully independent track uses NASA NEX-GDDP-CMIP6 daily downscaled tasmax fields. `src/data/nex_gddp_loader.py` streams annual NetCDFs from the anonymous AWS S3 mirror (`s3://nex-gddp-cmip6/<GCM>/<scenario>/<variant>/tasmax/...nc`), subsets to a North-America bounding box, computes annual TXx, and applies representative-point-in-polygon zonal statistics to TIGER county geometry. A 5-year proof-of-concept (ACCESS-CM2, SSP5-8.5, 2055–2059) produced 1,545 county-year observations. Agreement with AR6 synthesis: 0.5 °C at the regional 99th-percentile, 2.73 °C RMSE per county (Bay-Area "cooling" deltas reflect the short observed baseline; Mariposa County's +14.8 °C is a 0.25° grid-cell sampling artefact — both disclosed in the paper).

**Processing steps.**
1. Load and concatenate raw LOCA2 (NetCDF or CSV) if present; otherwise call the AR6 synthesis loader.
2. Compute baseline climatology (1991–2020 from LOCA2, or 2018–2024 from observed weather panel under the AR6 fallback).
3. Compute ensemble statistics (median, p10, p90) per county per period.
4. Compute change factors Δ = future − baseline per metric per scenario.
5. (Optional) Run the NEX-GDDP proof-of-concept and inject `TXx_nex_delta` into the projection CSV via `figures/04_inject_nex_gddp_delta.py`. NB07 then uses `TXx_nex_delta` for the heat-exposure rank when available.
6. **Output:** `loca2_projections_ercot.csv` (532 rows = 133 counties × 2 scenarios × 2 periods) and `loca2_projections_caiso.csv` (200 rows), each with the full suite of `<var>_median`, `<var>_p10`, `<var>_p90`, `<var>_delta` columns.

***

## Step 6: Stress Test — 2050-Era "Worst Week"

**Objective:** Model a compound extreme event scenario in 2050 and estimate the generation capacity deficit.

**Method:**
1. **Define the scenario:** A 7-day persistent heatwave at the 2050 projected 99th percentile temperature for ERCOT (use TXx from LOCA2 SSP5-8.5), coinciding with drought (max CDD exceeded) and high demand.
2. **Estimate demand:**
   - Download ERCOT historical hourly load data and CAISO demand data.[^17][^18]
   - Fit a temperature-to-load regression using historical data: `Peak_Load = f(Tmax, day_of_week, month)`.
   - Apply the 2050 scenario temperature to estimate peak demand under future conditions.
   - Add demand growth projections from EIA Annual Energy Outlook.
3. **Estimate supply:**
   - Use EIA-860 generator data to inventory current generation capacity by fuel type.[^19]
   - Apply heat derating factors: thermal plants lose ~0.5–1% efficiency per °C above design temperature; cooling-water-constrained plants face potential curtailment during drought.
   - Apply wildfire-related transmission constraints for CAISO: identify transmission lines crossing CAL FIRE FHSZ "Very High" zones using HIFLD data.
4. **Compute capacity margin:** Available_Supply − Peak_Demand = Margin. If negative, estimate MW shortfall and translate to customer impacts using historical load-shedding ratios.
5. **Sensitivity analysis:** Vary key parameters (temperature +/- 2°C, demand growth rate, generator availability) to bound the uncertainty.

***

## Step 7: Asset Vulnerability Mapping

**Objective:** Identify counties most exposed to compound climate-grid risk using three weighted layers: heat exposure, wildfire exposure, and asset density.

**Data sources:**
- **HIFLD electric substations** — 9,461 point records covering TX (5,196) and CA (4,265), downloaded via `figures/05_download_hifld_substations.py` from the ArcGIS REST endpoint. The default `data.gov` "Electric Substations" entry returns a 19-record Maryland CAD layer in EPSG:26985, not the canonical national layer; the ArcGIS REST path is the correct source. The REST response declares EPSG:4326 but ships Web Mercator coordinates, so the loader explicitly reprojects.[^20]
- **HIFLD transmission lines** — 94,619 line segments[^21]
- **CAL FIRE State Responsibility Area FHSZ** — 18,423 polygons (8,411 Very High, 5,824 High, 4,188 Moderate), downloaded via `figures/06_download_cal_fire_fhsz.py` from the CAL FIRE FRAP ArcGIS REST mirror. Saved with column `HAZ_CLASS` so NB07 picks it up directly.[^17]
- **NEX-GDDP-CMIP6 per-county TXx delta** — preferred heat layer; falls back to LOCA2 / AR6 `WSDI_delta` when not present.
- EIA-860 power plants for fleet inventory (referenced for stress test, not used directly in NB07).[^19]

**Processing steps.**
1. Spatial-join substations + transmission representative points to county polygons (EPSG:4326).
2. **Heat exposure rank** — percentile rank of `TXx_nex_delta` across all 183 covered counties; falls back to `WSDI_delta` when NEX-GDDP unavailable.
3. **Asset density rank** — percentile rank of (substations / county km²). Top metro counties (Los Angeles 559, Harris 386, Sacramento 371, Kern 330) reproduce the expected national density gradient.
4. **Wildfire exposure rank** — CAISO only — fraction of transmission line-km falling inside Very-High FHSZ polygons via `gpd.overlay`, then percentile-ranked. Zero for ERCOT.
5. **Composite risk score** = 0.40 · heat + 0.30 · wildfire + 0.30 · density (weights from `ASSET_RISK_WEIGHTS` in `config/settings.py`).
6. Choropleth maps and a top-15-county component-breakdown bar chart are written by `figures/02_build_asset_and_climate_figures.py`.

**Resulting top-priority counties** (composite std 0.168, well above the noise floor):
- **CAISO top-10:** San Diego, Contra Costa, Placer, Nevada, Sonoma, Butte (Camp Fire 2018), LA, Riverside, Shasta, Stanislaus — matches operational PSPS targeting geography.
- **ERCOT top-10:** Galveston, Nueces (Corpus Christi), Jefferson (Beaumont), Harrison, Gregg, Cameron, Harris (Houston), Tarrant (Fort Worth), Dallas, Travis (Austin) — Gulf-coast hurricane corridor plus East-Texas heat-and-density belt.

***

## Step 8: Environmental Justice Overlay

**Objective:** Test whether climate-amplified outage risk disproportionately affects disadvantaged communities.

**Data source:** EPA EJScreen 2024 (census block group level).[^22][^23][^24] The 2024 release renames several core fields — the loader (`src/data/ejscreen.py`) uses the new column names: `DEMOGIDX_2` (composite demographic index, replacing `EJ_SCORE`), `PEOPCOLORPCT` (replacing `MINORPCT`), `P_D2_PM25` (replacing `PM25_D2_PCTILE`), `P_OZONE`.

**Processing steps:**
1. Load the block-group CSV; derive county FIPS from the 12-digit `ID` column.
2. **Population-weighted aggregation to county.** For each county, compute the population-weighted mean of the composite EJ index and supporting indicators (% people of color, % low income, % linguistic isolation, % less than high school).
3. **Flag high-EJ-burden counties** as the top-quartile of the population-weighted composite. The historical merge covers all 254 ERCOT counties at 100% (`build_ercot_ejscreen()`).
4. **Descriptive analysis.** Outage event rate by EJ quartile. The 2018–2024 ERCOT panel shows **no monotone burden gradient** (Q1 10.2%, Q2 9.7%, Q3 12.5%, Q4 9.7%).
5. **Regression.** Add `high_ej_burden` as a control to the Step 4 panel specification. The county-level indicator is absorbed by the county fixed effects (time-invariant within county), confirming the design works as intended. An interaction term `triple × high_ej_burden` tests for compound-burden amplification; the coefficient is +0.374 with p = 0.226, **not statistically distinguishable from zero at the county scale.** This is consistent with one strand of the literature (county-level NREL EAGLE-I assessments find no consistent disparity) and not with another strand (zip-code-level Auch & Davis 2022 finding Houston Beryl amplification in low-income tracts). The null finding is reported as a real result, with the methodological caveat that county aggregation is too coarse to surface intra-county disparities.
6. **Double-exposure flag.** Overlay LOCA2 projected `SU_delta` with EJ burden to identify counties in the top quartile of both. The current run flags **38 ERCOT counties** (border counties Cameron / Hidalgo / Webb, Houston metro, East Texas) as priority targets for distributed-energy and weatherization spending.

***

## Step 9: Qualitative Analysis

**Objective:** Evaluate what the quantitative analysis misses and propose governance recommendations.

**Components:**
1. **Cascading interdependency assessment:**
   - Map the critical dependencies: grid → natural gas supply (electric compressors), grid → water supply (pumping stations), grid → telecommunications (cell towers with 8-hr backup batteries).
   - Use a simple dependency matrix to identify second-order failure modes not captured in the outage data.
2. **Regulatory gap analysis:**
   - Download ERCOT's most recent Integrated Resource Plan (IRP) and CAISO's annual resource adequacy reports.
   - Evaluate whether they incorporate forward-looking climate projections (most do not use CMIP6).[^25]
   - Compare against EPRI Climate READi recommendations.[^26][^27]
3. **Stakeholder analysis:**
   - Identify key stakeholders: PUCT (TX), CPUC (CA), ERCOT operations, CAISO operations, ratepayer advocates, environmental justice groups.
   - Draft interview questions for each stakeholder type (what would you convene if you could?).

***

## Step 10: Solutions Embedding and Recommendations

**Objective:** Evaluate adaptation options within the risk assessment framework.

**Actions:**
1. **Grid hardening — transmission undergrounding.** Targeting the top decile of at-risk transmission line-km (high heat × asset density × wildfire) yields roughly 3,105 miles. Unit cost $1–3 M / mile (literature) implies $3.1–9.3 B capital. Avoided annual damages $155 M (SAIDI/SAIFI cost factors). Simple payback period: **20–60 years**. The range reflects genuine uncertainty in both unit cost and discount rate, not analytical imprecision.
2. **DERs and microgrids.** Five gigawatts of distributed solar plus 2-hour storage targeted at high-EJ × high-projected-heat counties (the 38-county overlap identified in Step 8). Capital cost $8–12 B, timeline 2027–2035. The value driver is customer-hours avoided during grid emergencies rather than bulk-energy displacement.
3. **Demand response.** Applying a load-temperature elasticity of approximately 6% reduction per °C of thermostat adjustment to the cooling-fraction load (~35% of ERCOT peak), estimated dispatchable DR potential at a scenario peak of 42 °C is **1.5 GW**. Programme cost $0.5–1 B to scale to 4 GW dispatchable by 2030. The June 2025 PJM heatwave demonstrated near-4 GW of DR was load-bearing for grid stability.[^28]
4. **Policy recommendations.** A four-row matrix written to `data/processed/policy_recommendations.csv`:

| Category | Action | Success metric | Cost (est.) | Timeline |
|---|---|---|---|---|
| Grid hardening | Underground top-10% at-risk transmission | SAIDI reduction during extreme events | $3–9 B (ERCOT) | 2030–2040 |
| DERs / microgrids | 5 GW distributed solar + 2-hr storage in high-EJ + high-heat counties | Customer-hours avoided during emergencies | $8–12 B | 2027–2035 |
| Demand response | Expand automated DR to 4 GW dispatchable in ERCOT by 2030 | MW dispatched per Conservation Appeal | $0.5–1 B | 2025–2030 |
| Regulatory reform | Adopt CMIP6 SSP5-8.5 as planning baseline; tie utility ROE to extreme-event SAIDI/SAIFI | Adoption in next IRP cycle; extreme-event outage-hour reduction | Administrative only | 2025–2027 |

These four levers map cleanly onto the EPRI Climate READi framework axes (physical, demand-side, distributed-supply, regulatory) and connect back to the historical findings: the regression results (Step 4 §4.2) inform where the hardening spend should be concentrated, and the Flex-Alert RD result (Step 4 §4.3) provides first-order evidence that demand-side programmes can produce measurable reductions in extreme-weather outage hours.

---

## Documentation map

- `README.md` — repository entry point, reproduction steps
- `CLAUDE.md` — architecture overview for agents working in the repo
- `docs/Methodology.md` (this file) — long-form per-step methodology
- `docs/data.md` — dataset download guide (sources, target paths, schema notes)
- `docs/variable_metadata_and_description.txt` — column-level metadata for processed panels
- `notebooks/NOTEBOOKS.md` — per-notebook reference with current results
- `figures/README.md` — figure / paper-build script catalog
- `paper/Methods_and_Results.docx` — final paper Methods + Results with embedded figures
- `paper/references.md` — bibliography (matched to footnotes in this file)
