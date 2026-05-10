# Data Download Guide

All raw data lives under `data/raw/`. Processed outputs are written to `data/processed/` by the notebooks and should not be downloaded manually.

---

## Quick start

```bash
# Auto-download TIGER county shapefile + NOAA Storm Events (2018–2024)
uv run python scripts/download_data.py --auto

# Print URLs and target paths for all datasets
uv run python scripts/download_data.py

# Print instructions for one dataset only
uv run python scripts/download_data.py --dataset eagle_i
```

NOAA ISD station files are downloaded automatically when you run Notebook 03 — no manual step required.

---

## Datasets

### Auto-downloaded

| Dataset | Target path | Triggered by |
|---------|-------------|--------------|
| Census TIGER/Line 2023 county shapefile | `data/raw/hifld/tl_2023_us_county/` | `scripts/download_data.py --auto` |
| NOAA Storm Events 2018–2024 | `data/raw/storm_events/` | `scripts/download_data.py --auto` |
| NOAA ISD hourly station files | `data/raw/noaa_isd/` | Notebook 03 (via `src/data/noaa_isd.py`) |

---

### Manual downloads

#### EAGLE-I Power Outage Data (ORNL) — **required for Notebooks 02, 04**

Download one annual CSV per year for **2018–2024** and place them in `data/raw/eagle_i/`.

Expected filename convention: `eaglei_outages_<YEAR>.csv`

| Years | URL |
|-------|-----|
| 2024 | https://doi.ccs.ornl.gov/dataset/2be78213-ef9e-5433-b1b0-9762d051146c |
| 2018–2022 | https://www.osti.gov/dataexplorer/biblio/dataset/1975202 |
| Legacy (pre-2023) | https://smc-datachallenge.ornl.gov/eagle/ |

Each CSV row is a 15-minute observation with columns: `fips_code`, `county_name`, `state`, `customers_out`, `total_customers`, `run_start_time`.

---

#### USGS CMIP6-LOCA2 county summaries — **required for Notebook 05**

Target path: `data/raw/loca2/`

1. Go to: https://data.usgs.gov/datacatalog/data/USGS:673d0719d34e6b795de6b593
2. Click **Download** and select the **SSP2-4.5** and **SSP5-8.5** county CSV archives.
3. Extract CSVs into `data/raw/loca2/`.

Files must contain `ssp245` or `ssp585` in their filename. The dataset covers 27 GCMs, 1950–2100, with 36 annual Climdex metrics per county (key variables: `SU`, `TR`, `TXx`, `WSDI`, `CDD`, `Rx1day`, `CDD`).

---

#### EIA Form 860 generator inventory — **required for Notebook 06**

Target path: `data/raw/eia860/`

1. Go to: https://www.eia.gov/electricity/data/eia860/
2. Download the **ZIP** file for the most recent annual release.
3. Extract Excel workbooks into `data/raw/eia860/`.

Key sheet: `3_1_Generator_Y<year>.xlsx` (fuel type, capacity, location, design temperature).

---

#### HIFLD Electric Substations — **required for Notebook 07**

Target path: `data/raw/hifld/Electric_Substations.shp` (plus sidecar files)

1. Go to: https://catalog.data.gov/dataset/electric-substations
2. Click **Download** → Shapefile.
3. Extract into `data/raw/hifld/`.

---

#### HIFLD Transmission Lines — **required for Notebook 07**

Target path: `data/raw/hifld/Electric_Power_Transmission_Lines.shp` (plus sidecar files)

1. Go to: https://gis-fws.opendata.arcgis.com/datasets/fws::us-electric-power-transmission-lines/about
2. Click **Download** → Shapefile.
3. Extract into `data/raw/hifld/`.

---

#### EPA EJScreen 2024 — **required for Notebook 08**

Target path: `data/raw/ejscreen/`

**Option A (preferred):**
1. Go to: https://www.epa.gov/ejscreen/technical-information-and-data-downloads
2. Click **2024 EJSCREEN Data** → CSV format.

**Option B (Zenodo mirror):**
1. Go to: https://zenodo.org/records/14767363

Save the CSV to `data/raw/ejscreen/`. The file must have a 12-digit `ID` column (census block group GEOID).

---

#### ERCOT Historical Hourly Load — **required for Notebook 06**

Target path: `data/raw/ercot_load/`

1. Go to: https://www.ercot.com/gridinfo/load/load_hist
2. Download the **Hourly Load Data Archive** CSV for each year (2018–2024).
3. Save to `data/raw/ercot_load/`.

---

#### CAL FIRE Fire Hazard Severity Zones (CAISO only) — **required for Notebook 07**

Target path: `data/raw/hifld/cal_fire_fhsz/`

1. Go to: https://osfm.fire.ca.gov/divisions/wildfire-prevention-planning-research/wildland-hazards-building-codes/fire-hazard-severity-zones-maps/
2. Download the statewide FHSZ shapefile.
3. Extract into `data/raw/hifld/cal_fire_fhsz/`.

Used to compute the fraction of CAISO transmission line-km within "Very High" fire hazard zones for asset vulnerability scoring.

---

## Processed outputs

Notebooks write the following files to `data/processed/` (do not edit manually):

| File | Written by | Used by |
|------|-----------|---------|
| `outage_panel_ercot.csv` | Notebook 02 | 04, 08 |
| `outage_panel_caiso.csv` | Notebook 02 | 04, 08 |
| `weather_panel_ercot.csv` | Notebook 03 | 04 |
| `weather_panel_caiso.csv` | Notebook 03 | 04 |
| `merged_panel_ercot.csv` | Notebook 04 | 08 |
| `merged_panel_caiso.csv` | Notebook 04 | 08 |
| `loca2_projections_ercot.csv` | Notebook 05 | 06, 07 |
| `loca2_projections_caiso.csv` | Notebook 05 | 06, 07 |
| `asset_risk_scores.csv` | Notebook 07 | — |
| `ejscreen_county.csv` | Notebook 08 | — |
