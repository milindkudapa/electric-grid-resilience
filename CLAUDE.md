# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for dependency management with Python 3.11 (pinned via `.python-version`).

```bash
uv sync                                        # install deps into .venv
uv run python scripts/download_data.py --auto  # auto-download TIGER shapefiles + Storm Events
uv run python scripts/download_data.py         # print URLs for manual downloads (EAGLE-I, LOCA2, EIA-860, HIFLD, EJScreen)
uv run jupyter lab notebooks/                  # launch notebooks
```

Run any script or module with `uv run <command>` to use the managed environment.

## Architecture

The project is a research pipeline that produces a county × day panel for **ERCOT** (254 TX counties) and **CAISO** (58 CA counties), then performs econometric analysis and climate projections.

**Data flow (notebooks 01–10, run in order):**
1. Raw data (`data/raw/`) → processed CSVs (`data/processed/`) — each notebook reads upstream processed files and writes its own outputs.
2. The county × day panel is the core data structure, indexed by `(fips, date)`.

**Key modules in `src/`:**
- `src/data/eagle_i.py` — loads EAGLE-I 15-min CSVs, aggregates to daily `outage_fraction` + `outage_event_flag`
- `src/data/noaa_isd.py` — downloads NOAA ISD from AWS S3, aggregates to county-day weather
- `src/data/loca2.py` — loads USGS CMIP6-LOCA2 summaries, computes climatologies and Δ change factors for SSP2-4.5 / SSP5-8.5
- `src/data/ejscreen.py` — population-weighted county aggregation of EPA EJScreen indicators
- `src/analysis/compound_flags.py` — derives `heatwave_day`, `heatwave_event`, `compound_heat_wind`, `compound_triple` flags from weather columns; all thresholds from `config/settings.py`
- `src/analysis/panel_regression.py` — two-way fixed-effects PanelOLS (county + day FEs, SEs clustered by county) and logistic regression wrappers using `linearmodels`
- `src/analysis/rd_analysis.py` — regression discontinuity estimator with IK bandwidth selection; running variable is daily Tmax with cutoffs at 36 °C (ERCOT) and 38 °C (CAISO)
- `src/analysis/stress_test.py` — 2050 worst-week capacity margin model projecting demand growth, supply derating (0.7% per °C above design temp), and capacity deficit (MW)
- `src/viz/maps.py` — choropleth maps, heatmaps, RD bin-scatter plots, sensitivity tables

**Single source of truth:** `config/settings.py` defines all thresholds, FIPS lists, file paths, SSP scenarios, and temporal scopes. All other modules import from here — do not hardcode these values elsewhere.

## Processed file naming convention

| Key | File |
|-----|------|
| `outage_ercot` / `outage_caiso` | `outage_panel_{region}.csv` |
| `weather_ercot` / `weather_caiso` | `weather_panel_{region}.csv` |
| `loca2_ercot` / `loca2_caiso` | `loca2_projections_{region}.csv` |
| `merged_ercot` / `merged_caiso` | `merged_panel_{region}.csv` |

Access paths via `config.settings.PROCESSED["key"]` rather than constructing them manually.

## Key thresholds

All sourced from `config/settings.py` and the Nature 2025 EAGLE-I study:
- Heatwave: Tmax > 32.2 °C; ≥ 3 consecutive days (WMO)
- Compound triple (52× risk amplifier): heatwave + wind gust > 15 m/s + precip > 10 mm
- Outage event flag: `outage_fraction` > 1% of customers
- RD cutoffs: 36 °C (ERCOT Conservation Appeal), 38 °C (CAISO Flex Alert)
