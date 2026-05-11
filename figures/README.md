# Figure / paper-build scripts

Self-contained scripts used to build the figures embedded in `Methods_and_Results.docx`
and the data products feeding them. Run in numerical order; each is idempotent.

| # | Script | Purpose | Outputs |
|---|---|---|---|
| 05 | `05_download_hifld_substations.py` | Paginated download of HIFLD national substations layer for TX + CA via ArcGIS REST (9,461 records). Reprojects to EPSG:4326. | `data/raw/hifld/Electric_Substations.shp,csv` |
| 06 | `06_download_cal_fire_fhsz.py` | Paginated download of CAL FIRE Fire Hazard Severity Zones, State Responsibility Area (18,423 polygons). | `data/raw/hifld/cal_fire_fhsz/FHSZ_SRA.shp` |
| 04 | `04_inject_nex_gddp_delta.py` | Compute per-county NEX-GDDP-CMIP6 mid-century TXx delta (vs observed 2018–2024 baseline) and inject into the LOCA2 projection CSVs as `TXx_nex_delta`. | updates `data/processed/loca2_projections_{ercot,caiso}.csv` |
| 01 | `01_build_descriptive_figures.py` | Annual escalation, Uri/Beryl event timeseries, heat dose-response, compound wind×precip scatter, seasonal heatmap, county burden choropleth, heatwave duration histogram. | 7 PNGs in `data/processed/` |
| 02 | `02_build_asset_and_climate_figures.py` | Asset vulnerability map, NEX-GDDP TXx delta map, top-15 composite component breakdown, AR6 vs NEX-GDDP TXx scatter. | 4 PNGs in `data/processed/` |
| 03 | `03_build_paper_docx.py` | Assemble `Methods_and_Results.docx` from text + embedded figures + tables. | `Methods_and_Results.docx` |

## Re-running

```bash
# Pipeline-feeding downloads (rarely change)
uv run python figures/05_download_hifld_substations.py
uv run python figures/06_download_cal_fire_fhsz.py

# Climate-projection injection (after the AR6 synthesis writes loca2_projections_*.csv)
uv run python figures/04_inject_nex_gddp_delta.py

# Figures + paper
uv run python figures/01_build_descriptive_figures.py
uv run python figures/02_build_asset_and_climate_figures.py
uv run python figures/03_build_paper_docx.py
```

## Data dependencies

- `data/processed/merged_panel_{ercot,caiso}.csv` — from NB04
- `data/processed/outage_panel_{ercot,caiso}.csv` — from NB02
- `data/processed/weather_panel_{ercot,caiso}.csv` — from NB03
- `data/processed/asset_risk_scores.csv` — from NB07
- `data/processed/nex_gddp_poc_txx.csv` — from `src/data/nex_gddp_loader.py`
- `data/processed/loca2_projections_{ercot,caiso}.csv` — from NB05 (AR6 synthesis fallback)
