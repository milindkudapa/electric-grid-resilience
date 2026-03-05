# Electricity Grid Resilience — U.S. Regional Grid Stress

Quantitative analysis of how compound climate extremes (heat, drought, wildfire) amplify power outage risk in two U.S. balancing authority regions — **ERCOT** (Texas, 254 counties) and **CAISO** (California, 58 counties) — with projections to 2050 under CMIP6 scenarios.

---

## Research Questions

1. How much do compound weather events (heat + wind + precipitation) amplify power outage probability relative to normal days?
2. Is there a causal effect of crossing grid emergency alert thresholds on outage severity?
3. How will future heat extremes (SSP2-4.5, SSP5-8.5) stress generation capacity by mid-century?
4. Do climate-amplified outages disproportionately affect Environmental Justice communities?

---

## Project Structure

```
project/
├── config/
│   └── settings.py          # All thresholds, FIPS lists, paths, scenario params
├── data/
│   ├── raw/
│   │   ├── eagle_i/         # EAGLE-I 15-min outage CSVs (2018–2024)
│   │   ├── noaa_isd/        # NOAA ISD hourly station files (auto-downloaded)
│   │   ├── loca2/           # USGS CMIP6-LOCA2 county Climdex summaries
│   │   ├── eia860/          # EIA-860 generator inventory
│   │   ├── hifld/           # Substations + transmission lines shapefiles
│   │   ├── storm_events/    # NOAA Storm Events Database
│   │   └── ejscreen/        # EPA EJScreen 2024
│   └── processed/           # Output CSVs produced by notebooks
├── src/
│   ├── data/
│   │   ├── eagle_i.py       # Load + aggregate EAGLE-I → county-day panel
│   │   ├── noaa_isd.py      # Download ISD from S3, parse, aggregate to county-day
│   │   ├── loca2.py         # Load LOCA2, compute climatologies + change factors
│   │   └── ejscreen.py      # Load EJScreen, population-weighted county aggregation
│   ├── analysis/
│   │   ├── compound_flags.py   # Heatwave, compound heat-wind, compound triple flags
│   │   ├── panel_regression.py # Two-way FE PanelOLS + logistic regression wrappers
│   │   ├── rd_analysis.py      # RD estimator with IK bandwidth selection
│   │   └── stress_test.py      # 2050 demand/supply/capacity margin model
│   └── viz/
│       └── maps.py             # Choropleth, heatmap, RD bin-scatter, sensitivity plots
├── notebooks/
│   ├── 01_study_area.ipynb          # Step 1: FIPS selection, spatial maps
│   ├── 02_outage_panel.ipynb        # Step 2: Build EAGLE-I county-day panel
│   ├── 03_weather_panel.ipynb       # Step 3: Build NOAA ISD county-day panel + flags
│   ├── 04_historical_analysis.ipynb # Step 4: Merge, regression, RD analysis
│   ├── 05_climate_projections.ipynb # Step 5: LOCA2 climatologies + change factors
│   ├── 06_stress_test.ipynb         # Step 6: 2050 worst-week capacity stress test
│   ├── 07_asset_vulnerability.ipynb # Step 7: HIFLD asset risk scoring + maps
│   ├── 08_ej_overlay.ipynb          # Step 8: EJScreen disparate impact analysis
│   ├── 09_qualitative.ipynb         # Step 9: Dependency matrix, regulatory gaps
│   └── 10_solutions.ipynb           # Step 10: Hardening, DERs, demand response
├── scripts/
│   └── download_data.py     # Prints URLs + auto-downloads datasets
├── requirements.txt
└── Methodolgy.md            # Full step-by-step methodology
```

---

## Methodology Summary

| Step | What it does | Key output |
|------|-------------|------------|
| 1 | Select ERCOT (TX) + CAISO (CA), set 2018–2024 historical and 2030–2060 projection periods | County FIPS lists, spatial maps |
| 2 | Aggregate EAGLE-I 15-min outage data → county-day panel | `outage_panel_ercot.csv`, `outage_panel_caiso.csv` |
| 3 | Download NOAA ISD stations → county-day weather; derive compound event flags | `weather_panel_ercot/caiso.csv` |
| 4 | Merge panels; two-way FE OLS; logistic regression; RD on heat alert thresholds | Coefficient tables, RD estimate |
| 5 | Load USGS LOCA2 (27 GCMs); compute climatologies and Δ change factors | `loca2_projections_ercot/caiso.csv` |
| 6 | 2050 worst-week stress test: project demand, derate supply, compute capacity margin | Capacity deficit (MW), sensitivity table |
| 7 | Overlay HIFLD substations + lines with LOCA2 heat and CAISO wildfire zones | Asset risk scores, choropleth maps |
| 8 | Merge EJScreen with outage panel; test disparate impact regressions | EJ interaction coefficients |
| 9 | Cascading failure matrix, regulatory gap analysis, stakeholder question drafts | Qualitative outputs |
| 10 | Evaluate grid hardening, DERs, demand response; policy recommendations | Cost-benefit table, DR curve |

**Regression model (Step 4):**

$$\text{OutageSeverity}_{ct} = \beta_1\,\text{HeatwaveDay} + \beta_2\,\text{CompoundHeatWind} + \beta_3\,\text{CompoundTriple} + \gamma X_{ct} + \alpha_c + \delta_t + \varepsilon_{ct}$$

- $\alpha_c$ = county fixed effects; $\delta_t$ = day fixed effects; SEs clustered at county level
- Compound triple threshold (heat + wind > 15 m/s + precip > 10 mm) is the 52× risk amplifier from the Nature 2025 EAGLE-I study

**RD design (Step 4):**
- Running variable: daily Tmax; cutoffs: 36 °C (ERCOT Conservation Appeal), 38 °C (CAISO Flex Alert)
- Identifies causal effect of crossing emergency threshold on customer-hours of outage

---

## Data Sources

| Dataset | Source | Access |
|---------|--------|--------|
| EAGLE-I Power Outage Data 2018–2024 | ORNL / OSTI | Manual download |
| NOAA Integrated Surface Database (ISD) | NOAA / AWS S3 | Auto-downloaded by `noaa_isd.py` |
| Census TIGER/Line county shapefiles | US Census Bureau | Auto-downloaded by `download_data.py` |
| USGS CMIP6-LOCA2 county summaries | USGS ScienceBase | Manual download |
| NOAA Storm Events Database | NCEI | Auto-downloaded by `download_data.py` |
| EIA Form 860 generator inventory | EIA | Manual download |
| HIFLD substations + transmission lines | DHS / FWS Open Data | Manual download |
| EPA EJScreen 2024 | EPA / Zenodo | Manual download |

Run `python scripts/download_data.py` for exact URLs and instructions for each dataset.

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Download the TIGER county shapefile and Storm Events (automated)**
```bash
python scripts/download_data.py --auto
```

**3. Download remaining datasets manually** (EAGLE-I, LOCA2, EIA-860, HIFLD, EJScreen)
```bash
python scripts/download_data.py   # prints URLs and target paths for each
```

**4. Run notebooks in order**
```bash
jupyter lab notebooks/
```
Start with `01_study_area.ipynb` and proceed sequentially. Each notebook reads from `data/raw/` and writes outputs to `data/processed/`.

---

## Key Thresholds (from `config/settings.py`)

| Parameter | Value | Source |
|-----------|-------|--------|
| Heatwave threshold | Tmax > 32.2 °C (90 °F) | Nature 2025 EAGLE-I study |
| Outage event flag | outage_fraction > 1% | NREL resilience framework |
| Compound wind cutoff | wind gust > 15 m/s | Nature 2025 EAGLE-I study |
| Compound triple precip cutoff | precip > 10 mm | Nature 2025 EAGLE-I study |
| RD threshold — ERCOT | 36 °C (97 °F) | ERCOT Conservation Appeal |
| RD threshold — CAISO | 38 °C (100 °F) | CAISO Flex Alert |
| Heat derating rate | 0.7% efficiency loss per °C above design temp | Engineering literature |

---

## Requirements

- Python 3.11+
- See `requirements.txt` for full dependency list
- Key packages: `pandas`, `geopandas`, `linearmodels`, `statsmodels`, `scipy`, `matplotlib`, `seaborn`, `boto3`, `scikit-learn`
