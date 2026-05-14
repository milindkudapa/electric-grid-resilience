# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

Project uses [uv](https://docs.astral.sh/uv/) for dependency management with Python 3.11 (pinned via `.python-version`).

```bash
uv sync                                              # install deps into .venv
uv run python scripts/download_data.py --auto        # auto-download TIGER + Storm Events
uv run python figures/05_download_hifld_substations.py  # HIFLD substations for TX+CA
uv run python figures/06_download_cal_fire_fhsz.py      # CAL FIRE Fire Hazard Severity Zones
uv run python scripts/download_data.py               # print URLs for manual downloads
uv run jupyter lab notebooks/                        # launch notebooks
```

Run any script or module with `uv run <command>`.

## Architecture

Research pipeline producing a county × day panel for **ERCOT** (254 TX counties) and **CAISO** (58 CA counties) over 2018–2024, then econometric analysis + 2050 climate projections + adaptation evaluation.

**Data flow (notebooks 01–10, run in order):**
1. Raw inputs (`data/raw/`) → processed CSVs and PNGs (`data/processed/`).
2. Each notebook reads upstream processed files and writes its own outputs.
3. The core data structure is a county × day panel indexed by `(fips, date)`.

All 10 notebooks currently execute end-to-end without errors.

## Repository layout

```
electric-grid-resilience/
├── config/settings.py     # Single source of truth: thresholds, FIPS lists, paths
├── data/raw/              # Inputs (11 GB; .gitignored)
├── data/processed/        # Pipeline outputs (committed for reproducibility)
├── src/                   # data + analysis + viz modules
├── notebooks/             # 01–10 + NOTEBOOKS.md reference
├── scripts/               # Download helpers
├── figures/               # Standalone figure scripts
└── docs/                  # Long-form methodology + data guide
```

## Source modules in `src/`

### Data loaders + climate projection
- `src/data/eagle_i.py` — EAGLE-I 15-min CSV loader. Handles two file schemas (pre-2023 `sum`-column vs 2023+ canonical). **Imputes missing `total_customers` for 2018–2022 from per-FIPS 2023+ medians** in `build_outage_panel()`. Customer counts are stable within a county per the 2024 raw data, making this a defensible substitute.
- `src/data/noaa_isd.py` — Downloads NOAA ISD `.gz` files from `s3://noaa-isd-pds/` (auto-cached). Parses fixed-width format with QC (drops hourly temp outside [−50, 55]°C; daily Tmax > 50°C, Tmin > 45°C, wind > 80 m s⁻¹, precip > 500 mm). **Parses AA1 liquid precipitation only when `period_quantity == "01"`** (1-hour accumulation) to avoid double-counting overlapping multi-period reports.
- `src/data/loca2.py` — USGS LOCA2 NetCDF/CSV loader with defensive coordinate-dimension detection. Computes climatologies and Δ change factors for SSP2-4.5 / SSP5-8.5. **Falls back to AR6 regional synthesis** in `build_projection_panel()` when no raw LOCA2 files are present.
- `src/data/loca2_ar6_synthesis.py` — IPCC AR6 WGI Atlas regional-delta synthesis. Applies CMIP6 ensemble-median deltas (Central North America for ERCOT: TXx +2.4 °C SSP245 / +3.5 °C SSP585 mid-century; Western North America for CAISO: +2.0 / +3.0 °C) to the observed 2018–2024 weather baseline. Produces the canonical projection schema with `<var>_median`, `<var>_p10`, `<var>_p90`, `<var>_delta` columns. Inter-model spread: ±0.7 °C for temperature, ±20% for count variables.
- `src/data/nex_gddp_loader.py` — NASA NEX-GDDP-CMIP6 downscaled daily tasmax loader. Streams annual NetCDFs from anonymous AWS S3 (`s3://nex-gddp-cmip6/<GCM>/<scenario>/<variant>/tasmax/...nc`), subsets to a North-America bounding box, computes annual TXx, applies representative-point-in-polygon zonal statistics to TIGER county geometry. Proof-of-concept run: ACCESS-CM2, SSP5-8.5, 2055–2059 → 1,545 county-year observations.
- `src/data/ejscreen.py` — Population-weighted county aggregation of EPA EJScreen 2024 block-group indicators. **Schema constants reflect the 2024 release:** `COL_EJ_INDEX = "DEMOGIDX_2"`, `COL_PCT_MINORIY = "PEOPCOLORPCT"`, `COL_PM25 = "P_D2_PM25"`, `COL_OZONE = "P_OZONE"`.

### Analysis
- `src/analysis/compound_flags.py` — Derives `heatwave_day`, `heatwave_event`, `compound_heat_wind`, `compound_heat_precip`, `compound_triple`, AND a **mutually exclusive `weather_category` column** (`normal | heatwave_only | heat_wind | heat_precip | triple`) used as the regression dummy. All thresholds from `config/settings.py`.
- `src/analysis/panel_regression.py` — `run_panel_ols` uses **county FE + month-of-year FE** (NOT day FE — day FE absorbs the spatial weather signal because heatwaves hit all counties at once); default outcome is `log1p(total_customer_hours)` to handle zero-inflation; uses mutually exclusive category dummies. `run_logit` defaults to `method="lpm"` (linear probability model with county FE via PanelOLS) — also supports `clogit` and `pooled_logit` for robustness comparisons. SEs clustered at county.
- `src/analysis/rd_analysis.py` — Regression discontinuity estimator with Imbens-Kalyanaraman bandwidth selection plus a bandwidth-sensitivity table (0.5 °C to 5 °C). Running variable is daily Tmax with cutoffs at 36 °C (ERCOT) and 38 °C (CAISO). The CAISO RD is interpreted as **Flex Alert program effectiveness** (negative τ above cutoff = alert reduces outages).
- `src/analysis/stress_test.py` — 2050 worst-week capacity-margin model: load-temperature quadratic regression, supply derating (0.7% per °C above design temperature), capacity deficit (MW) and customer-impact estimate. Sensitivity heatmap across temperature × demand-growth grid.

### Visualisation
- `src/viz/maps.py` — Choropleths, heatmaps, RD bin-scatter plots, sensitivity-grid heatmap, outage-rate bar charts.

## Figure build pipeline (`figures/`)

Standalone scripts that consume `data/processed/` and produce figures. Run in any order after the notebooks; idempotent.

- `figures/01_build_descriptive_figures.py` — Annual outage burden, Uri/Beryl event timeseries, heat dose-response curve, compound wind×precip scatter, seasonal heatmap, county-burden choropleth, heatwave duration histogram (7 PNGs).
- `figures/02_build_asset_and_climate_figures.py` — Asset vulnerability map, NEX-GDDP TXx delta map, top-15 composite breakdown, AR6 vs NEX-GDDP scatter (4 PNGs).
- `figures/04_inject_nex_gddp_delta.py` — Computes per-county NEX-GDDP TXx delta vs observed baseline, writes `TXx_nex_delta` column into the projection CSVs.
- `figures/05_download_hifld_substations.py` — Paginated download of HIFLD substations (TX + CA, 9,461 records) from ArcGIS REST. Reprojects from Web Mercator to EPSG:4326.
- `figures/06_download_cal_fire_fhsz.py` — Paginated download of CAL FIRE State Responsibility Area FHSZ (18,423 polygons). Renames `FHSZ_Description` → `HAZ_CLASS` to match NB07 expectations.

## Processed file naming convention

| Key in `config.settings.PROCESSED` | File |
|---|---|
| `outage_ercot` / `outage_caiso` | `outage_panel_{region}.csv` |
| `weather_ercot` / `weather_caiso` | `weather_panel_{region}.csv` |
| `loca2_ercot` / `loca2_caiso` | `loca2_projections_{region}.csv` |
| `merged_ercot` / `merged_caiso` | `merged_panel_{region}.csv` |
| `asset_risk` | `asset_risk_scores.csv` |
| `ejscreen_county` | `ejscreen_county.csv` |

Always access paths via `config.settings.PROCESSED["key"]` rather than constructing them manually.

## Key thresholds (from `config/settings.py`)

- Heatwave: Tmax > 32.2 °C (Amin et al. 2025); ≥ 3 consecutive days for `heatwave_event` (WMO).
- Compound triple (52× risk amplifier from Amin et al. 2025): heatwave + wind gust > 15 m s⁻¹ + precip > 10 mm.
- Outage event flag: `outage_fraction` > 1% of customers (NREL).
- RD cutoffs: 36 °C (ERCOT Conservation Appeal), 38 °C (CAISO Flex Alert).
- Heat derating: 0.7% per °C above design temperature (Brockway & Dunn 2020).
- Asset risk weights: heat 0.40 / wildfire 0.30 / density 0.30.

## Regression specification (Step 4)

```
log1p(total_customer_hours)_ct = α_c + γ_month(t) + β·CategoryDummies_ct + ε_ct
```

- α_c = county fixed effects (absorbs time-invariant infrastructure heterogeneity)
- γ_month(t) = month-of-year fixed effects (NOT day-of-sample)
- CategoryDummies ∈ {heatwave_only, heat_wind, heat_precip, triple} with `normal` as the omitted baseline
- SEs clustered at county

Binary `outage_event_flag` modelled via a Linear Probability Model (PanelOLS with county FE). Coefficients are in probability-point units, read directly.

## Climate-projection fallback chain (Step 5)

The pipeline does not require raw LOCA2 data. `src/data/loca2.py::build_projection_panel` tries three sources in order:

1. **USGS LOCA2 NetCDF** at `data/raw/loca2/*.nc` (preferred).
2. **USGS LOCA2 per-scenario CSVs** at `data/raw/loca2/*.csv`.
3. **AR6 regional-delta synthesis** via `src/data/loca2_ar6_synthesis.py` (operational fallback).

A parallel **NEX-GDDP-CMIP6 fidelity check** runs out of `src/data/nex_gddp_loader.py` and writes per-county TXx deltas into the projection CSVs via `figures/04_inject_nex_gddp_delta.py`. NB07 uses `TXx_nex_delta` when available, falling back to `WSDI_delta` otherwise.

## Notebook execution status

All 10 notebooks ✅ ran end-to-end on the AR6 fallback path. See `notebooks/NOTEBOOKS.md` for per-notebook objectives, methods, inputs, outputs, and current numerical results (regression coefficients, RD bandwidth tables, stress-test deficits, asset-risk top-counties).

## Common pitfalls

- **`data/processed/` is committed** — do not add it to `.gitignore`. `.gitignore` defaults to ignoring `*.csv` and `*.parquet`, then explicitly un-ignores `data/processed/**` to whitelist pipeline outputs.
- **HIFLD substations from data.gov returns the wrong dataset** (a 19-record Maryland CAD layer). Use `figures/05_download_hifld_substations.py` instead.
- **ArcGIS REST returns Web Mercator coordinates** even when EPSG:4326 is declared in the response — `figures/05_download_hifld_substations.py` explicitly reprojects.
- **EJScreen 2024 schema differs from earlier releases**: the composite index is `DEMOGIDX_2` (not `EJ_SCORE`), and `MINORPCT` was renamed to `PEOPCOLORPCT`.
- **AR6 fallback assigns a uniform delta to every county within a region** — the NEX-GDDP track is the per-county fidelity check. Bay-Area "cooling" deltas under NEX-GDDP are an artefact of the short (2018–2024) observed baseline including the 2020 and 2022 heat domes, not a real projection.
- **NEX-GDDP grid cells are 0.25°** — Mariposa County's +14.8 °C delta is a sampling artefact from a Sierra Nevada centroid falling into a Central Valley grid point.
