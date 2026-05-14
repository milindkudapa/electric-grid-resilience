# Electricity Grid Resilience — U.S. Regional Grid Stress

A bottom-up physical-climate risk assessment for two contrasting U.S. balancing authorities: **ERCOT** (Texas, 254 counties) and **CAISO** (California, 58 counties). The pipeline builds a 2018–2024 county-by-day panel of power-outage and weather observations, fits two-way fixed-effects and regression-discontinuity models on the historical record, projects 2050 climate-amplified grid stress under SSP2-4.5 / SSP5-8.5, and overlays the projection on infrastructure, environmental-justice, and adaptation layers to identify priority counties and policy levers.

---

## Research questions

1. How much do compound weather events (heat × wind × precipitation) amplify the probability and severity of power outages relative to baseline?
2. Is there a causal effect of crossing grid emergency-alert temperature thresholds on outage hours (ERCOT Conservation Appeal at 36 °C; CAISO Flex Alert at 38 °C)?
3. How does mid-century heat under SSP2-4.5 / SSP5-8.5 stress generation capacity and transmission assets?
4. Does climate-amplified outage risk disproportionately fall on environmental-justice-burdened communities?

---

## Headline results

| Finding | Value |
|---|---|
| Triple-compound day outage probability vs. baseline (ERCOT LPM) | **+54.8 percentage points** |
| Triple-compound day customer-hours (ERCOT panel OLS) | exp(2.585) ≈ **13× normal** |
| CAISO Flex Alert program effect (RD at 38 °C) | **−3,212 customer-hours per alert day**, robust across all bandwidths |
| ERCOT 2050 SSP5-8.5 capacity margin | **−28 GW deficit (−25.8%)**, ~3.2 M customers affected |
| CAISO 2050 SSP5-8.5 capacity margin | **−36 GW deficit (−33.0%)**, ~4.6 M customers affected (electrification-conditional) |
| AR6 vs NEX-GDDP-CMIP6 99th-pct TXx agreement | **0.5 °C** at regional aggregate, 2.73 °C RMSE per county |
| Asset-vulnerability top-priority counties | LA, San Diego, Contra Costa, Galveston, Houston (Harris), Camp-Fire-corridor Butte |
| Environmental-justice interaction (triple × high_EJ_burden) | +0.374 log-units, p = 0.226 (null at county scale) |

---

## Repository layout

```
electric-grid-resilience/
├── README.md, CLAUDE.md, pyproject.toml, uv.lock
│
├── config/
│   └── settings.py              # All thresholds, FIPS lists, paths — single source of truth
│
├── data/
│   ├── raw/                     # Input data (11 GB; .gitignored)
│   │   ├── eagle_i/             #   EAGLE-I 15-min outage CSVs (2018–2024)
│   │   ├── noaa_isd/            #   NOAA ISD hourly station files (auto-downloaded)
│   │   ├── loca2/               #   USGS CMIP6-LOCA2 (optional; AR6 fallback otherwise)
│   │   ├── nex_gddp/            #   NEX-GDDP-CMIP6 cache (anonymous AWS S3)
│   │   ├── eia860/              #   EIA-860 generator inventory
│   │   ├── hifld/               #   HIFLD substations + transmission + CAL FIRE FHSZ
│   │   ├── storm_events/        #   NOAA Storm Events Database
│   │   ├── ercot_load/          #   ERCOT Hourly Load Archives
│   │   └── ejscreen/            #   EPA EJScreen 2024
│   └── processed/               # Pipeline outputs (committed to git for reproducibility)
│
├── src/
│   ├── data/
│   │   ├── eagle_i.py           # EAGLE-I loader; schema-normalises and imputes denominator
│   │   ├── noaa_isd.py          # ISD S3 downloader, fixed-width parser, county aggregator + QC
│   │   ├── loca2.py             # LOCA2 NetCDF/CSV loader; falls back to AR6 synthesis
│   │   ├── loca2_ar6_synthesis.py  # AR6 WGI regional-delta synthesis (CNA + WNA)
│   │   ├── nex_gddp_loader.py   # NEX-GDDP-CMIP6 AWS S3 streamer + county zonal stats
│   │   └── ejscreen.py          # EJScreen 2024 loader + population-weighted aggregation
│   ├── analysis/
│   │   ├── compound_flags.py    # Heatwave + compound + mutually-exclusive weather_category
│   │   ├── panel_regression.py  # PanelOLS (county+month FE, log1p) + LPM wrappers
│   │   ├── rd_analysis.py       # IK-bandwidth RD estimator + bandwidth-sensitivity table
│   │   └── stress_test.py       # Load model + heat-derating + capacity-margin sensitivity
│   └── viz/
│       └── maps.py              # Choropleths, RD bin-scatter, sensitivity heatmaps, etc.
│
├── notebooks/                   # Pipeline notebooks (run in order 01 → 10)
│   ├── 01_study_area.ipynb         01 — FIPS selection + spatial maps
│   ├── 02_outage_panel.ipynb       02 — EAGLE-I county-day panel
│   ├── 03_weather_panel.ipynb      03 — NOAA ISD county-day panel + compound flags
│   ├── 04_historical_analysis.ipynb 04 — Merge + regression + RD
│   ├── 05_climate_projections.ipynb 05 — LOCA2 / AR6 fallback projection panel
│   ├── 06_stress_test.ipynb        06 — 2050 worst-week capacity stress test
│   ├── 07_asset_vulnerability.ipynb 07 — HIFLD assets × heat × wildfire composite
│   ├── 08_ej_overlay.ipynb         08 — EPA EJScreen overlay + double-exposure flag
│   ├── 09_qualitative.ipynb        09 — Cascading-failure matrix + regulatory gaps
│   ├── 10_solutions.ipynb          10 — Hardening / DR / DER cost-benefit + policy table
│   └── NOTEBOOKS.md                Per-notebook objectives, methods, current results
│
├── scripts/
│   └── download_data.py         # Print URLs / auto-download orchestration
│
├── figures/                     # Standalone scripts that build figures
│   ├── 01_build_descriptive_figures.py   # Annual escalation, Uri/Beryl, dose-response, etc.
│   ├── 02_build_asset_and_climate_figures.py  # Asset map, TXx delta map, cross-validation
│   ├── 04_inject_nex_gddp_delta.py       # Adds TXx_nex_delta column to projection CSVs
│   ├── 05_download_hifld_substations.py  # ArcGIS REST paginator for HIFLD substations
│   ├── 06_download_cal_fire_fhsz.py      # ArcGIS REST paginator for CAL FIRE FHSZ
│   └── README.md
│
├── docs/
│   ├── Methodology.md           # Full step-by-step methodology (NB01–NB10)
│   ├── data.md                  # Dataset download guide (sources, paths, schemas)
│   ├── variable_metadata_and_description.txt  # Column-level metadata for processed panels
│   └── README.md
│
```

---

## Methodology summary

| Step | What it does | Key output |
|------|-------------|------------|
| 1 | Define ERCOT (TX) + CAISO (CA) study area; historical 2018–2024, projection 2030–2079 | County FIPS lists, spatial maps |
| 2 | Aggregate EAGLE-I 15-min outage data → county-day panel; impute denominator for 2018–2022 | `outage_panel_{ercot,caiso}.csv` |
| 3 | Download NOAA ISD → county-day weather + AA1 1-hour-only precip + hourly/daily QC + compound flags | `weather_panel_{ercot,caiso}.csv` |
| 4 | Merge panels; county+month FE OLS on log1p(customer_hours); LPM with county FE on event flag; RD on heat alerts | Coefficient tables, RD estimates |
| 5 | LOCA2 climatologies + Δ change factors; **falls back to AR6 regional deltas + NEX-GDDP cross-validation** | `loca2_projections_{ercot,caiso}.csv` |
| 6 | 2050 worst-week stress test: project demand, derate supply, compute capacity margin | Margin (MW), sensitivity heatmap |
| 7 | HIFLD substations + transmission + CAL FIRE FHSZ + NEX-GDDP heat → composite asset risk | `asset_risk_scores.csv` + maps |
| 8 | EJScreen 2024 → population-weighted county EJ index → disparate-impact regression + double-exposure flag | EJ × outage tables |
| 9 | Cascading interdependency matrix, regulatory gap analysis, stakeholder map (qualitative) | Narrative tables |
| 10 | Adaptation evaluation: undergrounding + DR + DERs + policy recommendations | `policy_recommendations.csv` |

### Regression model (Step 4)

$$
\log(1+\text{TotalCustomerHours}_{ct}) = \alpha_c + \gamma_{m(t)} + \sum_{k\in\mathcal{K}} \beta_k\,\mathbb{1}[\text{Category}_{ct}=k] + \varepsilon_{ct}
$$

- $\alpha_c$ = county fixed effects (absorbs time-invariant infrastructure heterogeneity)
- $\gamma_{m(t)}$ = month-of-year fixed effects (absorbs the seasonal cycle). **Day-of-sample FE intentionally omitted** — heatwaves hit all counties simultaneously, so day FE would absorb the very signal we want to identify.
- $\mathcal{K} = \{$heatwave_only, heat_wind, heat_precip, triple$\}$; `normal` is the omitted baseline. Mutually exclusive categories avoid multicollinearity from nested flags.
- $\log(1+\cdot)$ handles the zero-inflated right-skewed outcome.
- SEs clustered at county.
- Binary `outage_event_flag` is modelled with a Linear Probability Model (PanelOLS with county FE); coefficients are direct probability-point readings.
- Triple threshold (heat + wind > 15 m s⁻¹ + precip > 10 mm) is the 52× risk amplifier from Amin et al. 2025 *Scientific Reports*.

### Regression discontinuity (Step 4)

- Running variable: daily Tmax. Cutoffs: 36 °C (ERCOT Conservation Appeal), 38 °C (CAISO Flex Alert).
- ERCOT is bandwidth-unstable — sign flips at wider bandwidths. Reported as sensitivity table only, no discontinuity claim.
- CAISO is robust — same sign, monotone decay across every bandwidth, all p < 0.01. Reinterpreted as **Flex Alert program effectiveness**: alert triggers ~3,200 fewer customer-hours of outage.

### Climate-projection fallbacks (Step 5)

| Priority | Source | Coverage | When used |
|---|---|---|---|
| 1 | USGS CMIP6-LOCA2 (NetCDF or CSV) | 27 GCMs × 3 SSPs × 36 indices × all US counties | When raw files present in `data/raw/loca2/` |
| 2 | AR6 WGI Atlas regional deltas | CMIP6 ensemble median for CNA + WNA regions | Fallback when raw LOCA2 missing — `src/data/loca2_ar6_synthesis.py` |
| 3 | NEX-GDDP-CMIP6 on AWS S3 (`s3://nex-gddp-cmip6/`) | 35 GCMs × 3 SSPs × daily tasmax, 1950–2100, anonymous | Cross-validation track — `src/data/nex_gddp_loader.py` |

The AR6 synthesis is the operational primary fallback. The NEX-GDDP track is an independent fidelity check: it preserves per-county spatial heterogeneity that AR6 uniform-delta synthesis cannot. The two agree to within 0.5 °C at the regional 99th-percentile TXx.

---

## Data sources

| Dataset | Source | Access | Used in |
|---------|--------|--------|---------|
| EAGLE-I Power Outage Data 2018–2024 | ORNL / OSTI / DOE-CESER | Manual download (browser) | NB02, NB04 |
| NOAA Integrated Surface Database | NOAA / AWS S3 | Auto by `src/data/noaa_isd.py` | NB03 |
| Census TIGER/Line 2023 county shapefile | US Census Bureau | Auto by `scripts/download_data.py --auto` | NB01, NB07 |
| NOAA Storm Events Database | NOAA NCEI | Auto by `scripts/download_data.py --auto` | NB03 |
| USGS CMIP6-LOCA2 county summaries | USGS ScienceBase | Manual download (server-degraded — use fallback) | NB05 (primary) |
| **IPCC AR6 WGI Atlas regional deltas** | Encoded in `loca2_ar6_synthesis.py` | Built-in | NB05 (fallback) |
| **NEX-GDDP-CMIP6 daily tasmax** | NASA / AWS S3 (`s3://nex-gddp-cmip6/`) | Anonymous via `nex_gddp_loader.py` | NB05 cross-check |
| ERCOT Historical Hourly Load 2018–2024 | ERCOT | Manual download | NB06 |
| EIA Form 860 generator inventory | EIA | Manual download | NB06 |
| HIFLD electric substations + transmission lines | DHS HIFLD / ArcGIS REST | Auto by `figures/05_download_hifld_substations.py` | NB07 |
| CAL FIRE Fire Hazard Severity Zones (SRA) | CAL FIRE FRAP / ArcGIS REST | Auto by `figures/06_download_cal_fire_fhsz.py` | NB07 |
| EPA EJScreen 2024 (block-group CSV) | EPA / Zenodo | Manual download | NB08 |

Run `uv run python scripts/download_data.py` for the full list of URLs and target paths.

---

## Setup

**Prerequisites:** [uv](https://docs.astral.sh/uv/). Python 3.11 (pinned via `.python-version`).

```bash
# 1. Install dependencies into .venv
uv sync

# 2. Auto-download what can be fetched programmatically
uv run python scripts/download_data.py --auto

# 3. Download HIFLD assets + CAL FIRE FHSZ (figures dir convenience scripts)
uv run python figures/05_download_hifld_substations.py
uv run python figures/06_download_cal_fire_fhsz.py

# 4. Print URLs for remaining manual datasets
uv run python scripts/download_data.py

# 5. Run the pipeline
uv run jupyter lab notebooks/
```

Notebooks 01–10 execute end-to-end without raw LOCA2 (the AR6 fallback kicks in at NB05). For per-notebook objectives, methods, dependencies, and current results, see `notebooks/NOTEBOOKS.md`.

---

## Reproducing the figures

`data/processed/` is committed to the repo so figures can be rebuilt from a fresh clone without re-running the heavy notebooks:

```bash
git clone https://github.com/milindkudapa/electric-grid-resilience.git
cd electric-grid-resilience
uv sync
uv run python figures/01_build_descriptive_figures.py
uv run python figures/02_build_asset_and_climate_figures.py
```

To regenerate the climate-projection panel under the AR6 fallback:

```bash
uv run python -m src.data.loca2_ar6_synthesis
uv run python figures/04_inject_nex_gddp_delta.py
```

---

## Key thresholds (from `config/settings.py`)

| Parameter | Value | Source |
|-----------|-------|--------|
| Heatwave threshold | Tmax > 32.2 °C (90 °F) | Amin et al. 2025 |
| Outage event flag | outage_fraction > 1% | NREL EAGLE-I resilience framework |
| Compound wind cutoff | wind gust > 15 m s⁻¹ | Amin et al. 2025 |
| Compound triple precip cutoff | precip > 10 mm | Amin et al. 2025 |
| RD threshold — ERCOT | 36 °C | ERCOT Conservation Appeal trigger |
| RD threshold — CAISO | 38 °C | CAISO Flex Alert trigger |
| Heat derating rate | 0.7% per °C above design temp | Brockway & Dunn 2020 |
| Asset risk weights | heat 0.40 / wildfire 0.30 / density 0.30 | `ASSET_RISK_WEIGHTS` |

---

## Requirements

- Python 3.11+ (see `.python-version`)
- Dependencies and exact versions: `pyproject.toml` + `uv.lock` (`uv sync` to install)
- Key packages: `pandas`, `geopandas`, `linearmodels`, `statsmodels`, `scipy`, `xarray`, `h5netcdf`, `h5py`, `dask`, `s3fs`, `matplotlib`, `boto3`, `scikit-learn`, `python-docx`

---

## Documentation map

- `README.md` (this file) — project entry point + reproduction steps
- `CLAUDE.md` — agent-readable architecture summary
- `notebooks/NOTEBOOKS.md` — per-notebook reference + current run results
- `docs/Methodology.md` — long-form step-by-step methodology
- `docs/data.md` — dataset download guide + schema notes
- `docs/variable_metadata_and_description.txt` — column-level metadata
- `figures/README.md` — figure-build scripts catalog
