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
1. **Filter** to ERCOT and CAISO counties using FIPS codes.
2. **Aggregate from 15-min to daily metrics** for each county:
   - `max_customers_out`: peak customers without power in a day
   - `total_customer_hours`: sum of (customers_out × 0.25 hours) over all 15-min intervals
   - `outage_fraction`: max_customers_out / total_customers (normalized severity)
   - `outage_event_flag`: binary indicator if outage_fraction > threshold (e.g., >1% of customers)[^6]
   - `duration_hours`: continuous hours above a minimum outage threshold
3. **Quality control:** Use the published state-level EAGLE-I coverage percentages to flag and potentially exclude county-years with known low coverage.[^1]
4. **Output:** A panel DataFrame indexed by (FIPS, date) with daily outage metrics. Save as `outage_panel_ercot.csv` and `outage_panel_caiso.csv`.

***

## Step 3: Build the Historical Weather Panel

**Objective:** Create a matching county × day panel of weather variables from NOAA ISD.

**Data source:** NOAA Integrated Surface Database (ISD) — 35,000+ global stations, hourly observations, 1901–present. Available on AWS Open Data and Azure Planetary Computer.[^7][^8][^9]

**Processing steps:**
1. **Station selection:** Identify all ISD stations within ERCOT and CAISO boundaries. Assign each station to its county using spatial join (station lat/lon to county polygon).
2. **Download hourly observations** for 2018–2024 from AWS S3 (`s3://noaa-isd-pds/`).
3. **Compute daily county-level weather metrics** (average across stations within each county):
   - `tmax`: daily maximum temperature (°C)
   - `tmin`: daily minimum temperature (°C)
   - `heat_index_max`: maximum heat index using Rothfusz regression (combines temperature + humidity)
   - `wind_gust_max`: maximum wind gust speed (m/s)
   - `precip_total`: total precipitation (mm)
   - `rh_min`: minimum relative humidity (%)
4. **Derive compound event flags:**
   - `heatwave_day`: 1 if tmax > 32.2°C (90°F) — the threshold used in the Nature 2025 EAGLE-I study[^10]
   - `heatwave_event`: 1 if ≥3 consecutive heatwave_days (standard WMO definition)
   - `compound_heat_wind`: 1 if heatwave_day AND wind_gust_max > 15 m/s
   - `compound_heat_precip`: 1 if heatwave_day AND precip_total > 25 mm
   - `compound_triple`: 1 if heatwave_day AND wind_gust_max > 15 m/s AND precip_total > 10 mm (this is the 52× risk amplifier from the literature)[^10]
5. **Supplement with NOAA Storm Events Database** (CSV bulk download) to flag county-days with officially reported extreme heat, wildfire, hurricane/tropical storm, or ice storm events. Join by FIPS and date.[^11]
6. **Output:** `weather_panel_ercot.csv`, `weather_panel_caiso.csv`, indexed by (FIPS, date).

***

## Step 4: Join Outage and Weather Panels — Historical Analysis

**Objective:** Quantify the statistical relationship between weather extremes and power outages.

**Methods:**
1. **Merge** outage and weather panels on (FIPS, date).
2. **Exploratory analysis:**
   - Compute outage rates (fraction of days with outage_event_flag = 1) by weather category: normal days, heatwave-only days, compound heat-wind days, compound triple days.
   - Replicate the key finding from the literature: compute the relative risk ratio comparing outage probability on compound triple days vs. normal days.[^10]
   - Visualize with heatmaps: counties on y-axis, days on x-axis, color = outage severity.
3. **Regression model — fixed effects panel:**

   $$\text{OutageSeverity}_{ct} = \beta_1 \text{HeatwaveDay}_{ct} + \beta_2 \text{CompoundHeatWind}_{ct} + \beta_3 \text{CompoundTriple}_{ct} + \gamma X_{ct} + \alpha_c + \delta_t + \varepsilon_{ct}$$

   Where $c$ = county, $t$ = day, $\alpha_c$ = county fixed effects (absorbs time-invariant infrastructure differences), $\delta_t$ = day fixed effects (absorbs region-wide temporal shocks), and $X_{ct}$ = additional controls (weekend indicator, holiday indicator).

   Use `linearmodels` Python package (`PanelOLS`). Cluster standard errors at the county level.

4. **Nonlinear analysis:** Estimate a logistic regression for binary outage events. Test for interaction effects between temperature and wind speed to quantify the compound amplification factor.

5. **Causal inference extension — Regression Discontinuity (RD):**
   - **Running variable:** Daily max temperature.
   - **Threshold:** The temperature at which ERCOT issues Conservation Appeals (~36°C / 97°F) or CAISO issues Flex Alerts (~38°C / 100°F).
   - **Outcome:** Customer-hours of outage.
   - **Estimate** using `rdrobust` (R) or manual bandwidth selection. This identifies the causal effect of crossing the emergency threshold on grid performance, controlling for the smooth relationship between temperature and outages.

***

## Step 5: Build the Climate Projection Panel

**Objective:** Project future extreme heat frequency for ERCOT and CAISO counties under CMIP6 scenarios.

**Data source:** USGS CMIP6-LOCA2 county spatial summaries. This pre-computed dataset provides time series of 36 annual and 4 monthly Climdex extreme event metrics, spatially averaged to every US county, for 27 GCMs under SSP2-4.5, SSP3-7.0, and SSP5-8.5, 1950–2100.[^12][^13][^14]

**Key variables from LOCA2 county summaries:**[^15][^16]

| Variable | Definition | Relevance |
|----------|-----------|-----------|
| SU (Summer Days) | Days with Tmax > 25°C | Baseline heat exposure |
| TR (Tropical Nights) | Days with Tmin > 20°C | Nighttime heat stress (grid doesn't cool) |
| TXx (Max Tmax) | Hottest day of the year | Peak stress scenario |
| WSDI (Warm Spell Duration) | Max consecutive days where Tmax > 90th percentile | Heatwave duration — critical for cascading grid stress |
| CDD (Cooling Degree Days) | Cumulative degrees above base temp | Proxy for cooling demand |
| Rx1day (Max 1-day precip) | Wettest day of year | Flood/storm risk to infrastructure |
| Rx5day (Max 5-day precip) | Wettest 5-day period | Compound flooding |
| CDD (Consecutive Dry Days) | Max consecutive dry days | Drought indicator |

**Processing steps:**
1. **Download** LOCA2 county time series for ERCOT and CAISO FIPS codes from USGS ScienceBase.[^12]
2. **Compute climatologies** for:
   - Historical baseline: 1991–2020
   - Near-term: 2030–2059
   - Mid-century: 2050–2079
3. **Compute multi-model ensemble statistics** (median, 10th–90th percentile) for each county and each metric.
4. **Calculate change factors:** Δ = Future_value − Historical_baseline for each metric and scenario.
5. **Key output metrics:**
   - How many additional summer days (SU) per year by 2050?
   - How much longer do heatwaves last (WSDI change)?
   - How do tropical nights (TR) change — these drive overnight electricity demand because AC can't be turned off?
   - How do compound heat-drought indicators (WSDI × CDD) change?
6. **Output:** `loca2_projections_ercot.csv`, `loca2_projections_caiso.csv`.

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

**Objective:** Map grid infrastructure against projected climate hazards.

**Data sources:**
- HIFLD electric substations (point data), transmission lines (line data)[^20][^21]
- EIA-860 power plants (point data with generator specs)[^19]
- LOCA2 projected extreme heat layers (gridded → county)
- MTBS wildfire perimeters (for CAISO, historical burn severity)
- CAL FIRE FHSZ maps (for CAISO, fire hazard zones)

**Processing steps:**
1. **Spatial overlay** in Python (geopandas) or QGIS:
   - Count substations and transmission line-km within each county.
   - For each county, attach the LOCA2 projected change in SU, WSDI, TXx.
   - For CAISO counties, overlay FHSZ "Very High" zones and compute fraction of transmission line-km within fire-prone areas.
2. **Asset risk score:** For each county, compute a composite score:
   - Heat exposure (LOCA2 WSDI change, percentile rank)
   - Wildfire exposure (fraction in FHSZ Very High, for CAISO)
   - Asset density (substations + line-km per km²)
   - Weighted combination → priority ranking of most-at-risk counties.
3. **Produce maps** (choropleth) showing the spatial distribution of asset vulnerability.

***

## Step 8: Environmental Justice Overlay

**Objective:** Test whether climate-amplified outage risk disproportionately affects disadvantaged communities.

**Data source:** EPA EJScreen 2024 (census block group level).[^22][^23][^24]

**Processing steps:**
1. **Download EJScreen geodatabase** from EPA or Zenodo archive.[^23][^24]
2. **Aggregate to county level:** For each county, compute population-weighted average EJ index, % minority, % low-income, linguistic isolation index.
3. **Join to outage panel:** Merge county-level EJ metrics to the historical outage panel.
4. **Test for disparate impact:**
   - Regression: Does outage severity increase in high-EJ-burden counties, controlling for weather and infrastructure?
   - Interaction: Is the compound-weather × outage relationship stronger in high-EJ counties (i.e., do vulnerable communities suffer more from the same weather event)?
5. **Forward projection:** Overlay EJScreen data on the LOCA2 projected heat increase maps. Identify counties that are both high-EJ-burden AND high-projected-heat-increase.

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
1. **Grid hardening:** Estimate the fraction of at-risk transmission line-km that could benefit from undergrounding. Compare costs (~$1–3M/mile) against projected avoided outage damages.
2. **DERs and microgrids:** Identify high-vulnerability counties where distributed solar + storage could serve as resilience assets during grid emergencies.
3. **Demand response:** Using the temperature-to-load regression from Step 6, estimate the MW reduction achievable through demand response at each temperature threshold. The June 2025 heatwave showed PJM relied on nearly 4,000 MW of demand response to stabilize the system.[^28]
4. **Policy recommendations:** Performance-based regulation that ties utility incentives to resilience metrics (SAIDI/SAIFI during extreme events).

---
