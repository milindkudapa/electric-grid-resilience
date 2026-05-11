# Data Download Guide

All raw data lives under `data/raw/`. Processed outputs in `data/processed/` are produced by the pipeline and should not be downloaded manually. Raw inputs total roughly 11 GB and are excluded from git (`data/raw/` is `.gitignore`d); processed outputs are checked in so figures and tables can be regenerated from a fresh clone.

---

## Quick start

```bash
# 1. Auto-download what we can fetch programmatically
uv run python scripts/download_data.py --auto

# 2. HIFLD substations + CAL FIRE FHSZ via ArcGIS REST (correct sources)
uv run python figures/05_download_hifld_substations.py
uv run python figures/06_download_cal_fire_fhsz.py

# 3. Print URLs for everything else (EAGLE-I, EJScreen, EIA-860, ERCOT load)
uv run python scripts/download_data.py

# 4. Single-dataset instructions
uv run python scripts/download_data.py --dataset eagle_i
```

NOAA ISD station files are pulled automatically when Notebook 03 runs (`src/data/noaa_isd.py` caches them under `data/raw/noaa_isd/`).

---

## Auto-downloaded datasets

| Dataset | Target path | Triggered by |
|---------|-------------|--------------|
| Census TIGER/Line 2023 county shapefile | `data/raw/hifld/tl_2023_us_county/` | `scripts/download_data.py --auto` |
| NOAA Storm Events 2018–2024 | `data/raw/storm_events/` | `scripts/download_data.py --auto` |
| NOAA ISD hourly station files | `data/raw/noaa_isd/` | Notebook 03 (via `src/data/noaa_isd.py`) |
| HIFLD electric substations (TX + CA) | `data/raw/hifld/Electric_Substations.{shp,csv}` | `figures/05_download_hifld_substations.py` |
| CAL FIRE State Responsibility Area FHSZ | `data/raw/hifld/cal_fire_fhsz/FHSZ_SRA.shp` | `figures/06_download_cal_fire_fhsz.py` |
| NEX-GDDP-CMIP6 daily tasmax (POC slice) | `data/raw/nex_gddp/` (streaming cache via s3fs) | `src/data/nex_gddp_loader.py` |

---

## Manual downloads

### EAGLE-I Power Outage Data (ORNL) — required for NB02, NB04

Download one annual CSV per year for **2018–2024** to `data/raw/eagle_i/`. Expected filenames: `eaglei_outages_<YEAR>.csv`.

| Year(s) | URL |
|---------|-----|
| 2024 | https://doi.ccs.ornl.gov/dataset/2be78213-ef9e-5433-b1b0-9762d051146c |
| 2018–2022 | https://www.osti.gov/dataexplorer/biblio/dataset/1975202 |
| Legacy (pre-2018) | https://smc-datachallenge.ornl.gov/eagle/ |

**Two schemas to be aware of:**
- **Pre-2023 (2018–2022 + legacy):** columns `fips_code, county_name, state, sum (= customers_out), run_start_time`. **No `total_customers` column.**
- **2023+:** canonical schema `fips_code, county_name, state, customers_out, total_customers, run_start_time`.

`src/data/eagle_i.py` handles both transparently. For pre-2023 records, the missing `total_customers` is imputed at panel-construction time from the per-FIPS median of years where it is present (effectively 2024). Customer counts are stable within a county across 15-min intervals in the 2024 raw data, so this is a defensible substitute. Without this imputation, `outage_fraction` and `outage_event_flag` would be `NaN` for 2018–2022 and the historical regression would collapse to a single year.

---

### USGS CMIP6-LOCA2 county summaries — needed for NB05 (primary path)

Target path: `data/raw/loca2/`

1. Go to: https://data.usgs.gov/datacatalog/data/USGS:673d0719d34e6b795de6b593
2. Click **Download** → select the **annual** thresholds NetCDF (and/or per-SSP CSV archives if available).
3. Save NetCDF as `data/raw/loca2/CMIP6-LOCA2_Thresholds_1950-2100_County2023_annual.nc`, or extract CSVs.

**Fallback if USGS is unavailable.** The pipeline ships an operational fallback (`src/data/loca2_ar6_synthesis.py`) that applies IPCC AR6 WGI Atlas regional ensemble-median deltas to the observed 2018–2024 weather baseline. The fallback is invoked automatically by `src/data/loca2.py::build_projection_panel` when no NetCDF or CSV is found. The pipeline does not block on USGS availability.

**Independent fidelity check.** `src/data/nex_gddp_loader.py` streams NEX-GDDP-CMIP6 daily tasmax from `s3://nex-gddp-cmip6/` (anonymous AWS access) and computes per-county TXx deltas as an alternative to AR6 uniform-delta synthesis. Run via `uv run python -m src.data.nex_gddp_loader`. POC slice: ACCESS-CM2, SSP5-8.5, 2055–2059 — produces 1,545 county-year observations in roughly 10 minutes.

---

### EIA Form 860 generator inventory — required for NB06

Target path: `data/raw/eia860/`

1. https://www.eia.gov/electricity/data/eia860/
2. Download the most recent annual ZIP release.
3. Extract Excel workbooks. Key sheet: `3_1_Generator_Y<year>.xlsx`.

---

### HIFLD electric substations and transmission lines — required for NB07

**Substations.** **Do not** use the `data.gov` "Electric Substations" entry — it returns a 19-record Maryland CAD layer in EPSG:26985, not the national HIFLD layer. Instead run:

```bash
uv run python figures/05_download_hifld_substations.py
```

This paginates the ArcGIS REST endpoint `https://services6.arcgis.com/OO2s4OoyCZkYJ6oE/arcgis/rest/services/Substations/FeatureServer/0`, filters to TX + CA (`STATE IN ('TX','CA')`), reprojects from Web Mercator (the REST response declares EPSG:4326 but ships Web Mercator coordinates) and saves both shapefile and CSV. Result: 9,461 substations (5,196 TX + 4,265 CA).

**Transmission lines.** Manual download to `data/raw/hifld/`:
- https://gis-fws.opendata.arcgis.com/datasets/fws::us-electric-power-transmission-lines/about
- Click Download → Shapefile.

Result expected: ~94,619 line segments with `OBJECTID_1, ID, TYPE, STATUS, NAICS_CODE, ...` columns.

---

### CAL FIRE Fire Hazard Severity Zones (CAISO only) — required for NB07

Run:

```bash
uv run python figures/06_download_cal_fire_fhsz.py
```

Paginates the CAL FIRE FRAP ArcGIS REST mirror and saves to `data/raw/hifld/cal_fire_fhsz/FHSZ_SRA.shp` with column `HAZ_CLASS` (renamed from `FHSZ_Description` for compatibility with NB07's existing code). Result: 18,423 polygons (8,411 Very High, 5,824 High, 4,188 Moderate).

Manual alternative: https://osfm.fire.ca.gov/divisions/wildfire-prevention-planning-research/wildland-hazards-building-codes/fire-hazard-severity-zones-maps/ → download statewide FHSZ shapefile → extract to `data/raw/hifld/cal_fire_fhsz/`.

---

### EPA EJScreen 2024 — required for NB08

Target path: `data/raw/ejscreen/`

**Option A (preferred):** https://www.epa.gov/ejscreen/technical-information-and-data-downloads → 2024 EJSCREEN Data → CSV format.

**Option B (Zenodo mirror):** https://zenodo.org/records/14767363

Expected filename: `EJSCREEN_2024_BG_with_AS_CNMI_GU_VI.csv`. The 2024 release renames several core fields — `src/data/ejscreen.py` uses the new column names: `DEMOGIDX_2` (composite demographic index, replacing `EJ_SCORE`), `PEOPCOLORPCT` (replacing `MINORPCT`), `P_D2_PM25` (replacing `PM25_D2_PCTILE`), `P_OZONE`. The 12-digit `ID` column is the census block-group GEOID; the first 5 digits give the county FIPS.

---

### ERCOT Historical Hourly Load — needed for NB06 (currently uses placeholder)

Target path: `data/raw/ercot_load/`

1. https://www.ercot.com/gridinfo/load/load_hist
2. Download Hourly Load Data Archive for each year (2018–2024) as `Native_Load_<YEAR>.xlsx`.

NB06 currently falls back to a placeholder quadratic load model because the existing loader does not parse the ERCOT XLSX format. Fitting the real model is left as a refinement; it would tighten demand-side uncertainty in the 2050 stress test but is unlikely to change the qualitative conclusion.

---

## Processed outputs

Notebooks write the following files to `data/processed/`. These are committed to git so figures + tables in the paper can be regenerated from a fresh clone without re-running the heavy notebooks.

### County panels

| File | Written by | Used by |
|------|-----------|---------|
| `outage_panel_ercot.csv` | NB02 | NB04, NB08 |
| `outage_panel_caiso.csv` | NB02 | NB04 |
| `weather_panel_ercot.csv` | NB03 | NB04, NB05 (AR6 baseline), figures/04 |
| `weather_panel_caiso.csv` | NB03 | NB04, NB05, figures/04 |
| `merged_panel_ercot.csv` | NB04 | NB08, figures/01 |
| `merged_panel_caiso.csv` | NB04 | figures/01 |
| `loca2_projections_ercot.csv` | NB05 | NB06, NB07, NB08, NB10 |
| `loca2_projections_caiso.csv` | NB05 | NB06, NB07, NB10 |
| `nex_gddp_poc_txx.csv` | `src/data/nex_gddp_loader.py` | figures/04 (injects `TXx_nex_delta`) |
| `asset_risk_scores.csv` | NB07 | NB10, figures/02 |
| `failure_mode_analysis.csv` | NB09 | (qualitative) |
| `regulatory_gap_analysis.csv` | NB09 | (qualitative) |
| `policy_recommendations.csv` | NB10 | (paper) |

### Figures (PNGs, all in `data/processed/`)

22 figures total, see `figures/README.md` for the build-script mapping. Key examples:

- `study_area_maps.png` — NB01
- `{ercot,caiso}_outage_rates.png`, `{ercot,caiso}_outage_heatmap.png`, `{ercot,caiso}_rd_plot.png` — NB04
- `annual_outage_burden.png`, `uri_beryl_timeseries.png`, `seasonal_heatmap.png`, `heatwave_duration_dist.png`, `heat_dose_response.png`, `compound_scatter_ercot.png`, `county_burden_choropleth.png` — `figures/01`
- `ercot_wsdi_delta.png` — NB05
- `ercot_stress_sensitivity.png` — NB06
- `asset_vulnerability_map.png`, `asset_top15_breakdown.png`, `nex_gddp_txx_delta_map.png`, `ar6_vs_nex_gddp_txx.png` — `figures/02`
- `ercot_ej_outage_rates.png` — NB08
- `interdependency_matrix.png` — NB09
- `demand_response_curve.png` — NB10
