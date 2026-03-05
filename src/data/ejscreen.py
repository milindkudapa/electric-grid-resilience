"""
EPA EJScreen 2024 data loader and county-level aggregator.

Source: https://www.epa.gov/ejscreen/technical-information-and-data-downloads
        https://zenodo.org/records/14767363

EJScreen is at census block group (CBG) level.  This module:
1. Loads the geodatabase or CSV.
2. Aggregates to county level using population-weighted averages.
3. Returns a clean county-level DataFrame ready to merge with the outage panel.

Main entry point:
    build_ejscreen_county(region_fips) -> pd.DataFrame
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import RAW, ERCOT_FIPS, CAISO_FIPS

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EJScreen column definitions (2024 release)
# ---------------------------------------------------------------------------
# Block-group identifier
COL_GEOID   = "ID"
COL_STATE   = "ST_ABBREV"
COL_POP     = "ACSTOTPOP"   # ACS total population

# Environmental Justice Index scores
COL_EJ_INDEX    = "EJ_SCORE"       # composite EJ index
COL_PCT_MINORIY = "MINORPCT"       # % minority population
COL_PCT_LOWINC  = "LOWINCPCT"      # % low income
COL_LING_ISO    = "LINGISOPCT"     # % linguistic isolation
COL_LESS_HS     = "LESSHSPCT"      # % less than high school education

# Environmental burden indicators (percentile ranks within US)
COL_PM25        = "PM25_D2_PCTILE"
COL_OZONE       = "OZONE_D2_PCTILE"
COL_HEATSTRESS  = "HEATSTRESS_SCORE"  # may not exist in all releases

EJ_INDICATOR_COLS = [
    COL_EJ_INDEX, COL_PCT_MINORIY, COL_PCT_LOWINC,
    COL_LING_ISO, COL_LESS_HS, COL_PM25, COL_OZONE,
]


def _load_ejscreen_raw(data_dir: Path) -> pd.DataFrame:
    """
    Load EJScreen from geodatabase, CSV, or GDB in data/raw/ejscreen/.

    Priority:
        1. CSV  (fastest, preferred if pre-exported)
        2. GDB  (requires fiona / geopandas)
    """
    csv_files = list(data_dir.glob("*.csv"))
    gdb_files = list(data_dir.glob("*.gdb")) + list(data_dir.glob("*.gpkg"))

    if csv_files:
        path = sorted(csv_files)[-1]   # most recent by name
        log.info("Loading EJScreen CSV: %s", path)
        return pd.read_csv(path, dtype={COL_GEOID: str}, low_memory=False)

    if gdb_files:
        try:
            import geopandas as gpd
        except ImportError as e:
            raise ImportError("geopandas required to read GDB format.") from e
        path = sorted(gdb_files)[-1]
        log.info("Loading EJScreen GDB: %s", path)
        gdf = gpd.read_file(path)
        return pd.DataFrame(gdf.drop(columns="geometry", errors="ignore"))

    raise FileNotFoundError(
        f"No EJScreen file found in {data_dir}.\n"
        "Download from: https://www.epa.gov/ejscreen/technical-information-and-data-downloads\n"
        "or:            https://zenodo.org/records/14767363"
    )


def _derive_fips_from_geoid(geoid: pd.Series) -> pd.Series:
    """Extract the 5-digit county FIPS from a 12-digit census block group ID."""
    return geoid.astype(str).str.zfill(12).str[:5]


def _population_weighted_mean(group: pd.DataFrame, value_col: str, weight_col: str) -> float:
    """Compute population-weighted average of a column within a group."""
    w = group[weight_col].fillna(0)
    v = group[value_col]
    valid = v.notna() & (w > 0)
    if valid.sum() == 0:
        return np.nan
    return np.average(v[valid], weights=w[valid])


def aggregate_to_county(df: pd.DataFrame, region_fips: list[str]) -> pd.DataFrame:
    """
    Aggregate block-group EJScreen data to county level via population weighting.

    Returns a DataFrame indexed by fips with columns:
        ej_index_mean, pct_minority, pct_lowinc, ling_iso_pct,
        less_hs_pct, pm25_pctile, ozone_pctile, total_pop
    """
    df = df.copy()
    df.columns = df.columns.str.strip()

    # Derive county FIPS
    df["fips"] = _derive_fips_from_geoid(df[COL_GEOID])
    df = df[df["fips"].isin(set(region_fips))].copy()

    # Ensure population column is numeric
    df[COL_POP] = pd.to_numeric(df[COL_POP], errors="coerce").fillna(0).clip(lower=0)

    # Only keep columns that exist in this release
    available_indicators = [c for c in EJ_INDICATOR_COLS if c in df.columns]
    if not available_indicators:
        raise ValueError(
            f"None of the expected EJScreen indicator columns were found. "
            f"Available: {list(df.columns[:20])}"
        )

    rows = []
    for fips_code, group in df.groupby("fips"):
        row = {"fips": fips_code, "total_pop": group[COL_POP].sum()}
        for col in available_indicators:
            row[col.lower()] = _population_weighted_mean(group, col, COL_POP)
        rows.append(row)

    county_df = pd.DataFrame(rows)

    # Rename to clean names
    rename_map = {
        COL_EJ_INDEX.lower():    "ej_index",
        COL_PCT_MINORIY.lower(): "pct_minority",
        COL_PCT_LOWINC.lower():  "pct_lowinc",
        COL_LING_ISO.lower():    "ling_iso_pct",
        COL_LESS_HS.lower():     "less_hs_pct",
        COL_PM25.lower():        "pm25_pctile",
        COL_OZONE.lower():       "ozone_pctile",
    }
    county_df = county_df.rename(columns=rename_map)

    # High-EJ-burden flag: top quartile of EJ index
    if "ej_index" in county_df.columns:
        threshold = county_df["ej_index"].quantile(0.75)
        county_df["high_ej_burden"] = (county_df["ej_index"] >= threshold).astype(int)

    return county_df.set_index("fips")


def build_ejscreen_county(
    region_fips: list[str],
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Full pipeline: load EJScreen and return county-level EJ indicators
    for the given region.

    Parameters
    ----------
    region_fips : list of 5-digit FIPS codes
    data_dir    : override for raw data directory

    Returns a DataFrame indexed by 'fips'.
    """
    data_dir = data_dir or RAW["ejscreen"]
    raw = _load_ejscreen_raw(data_dir)
    return aggregate_to_county(raw, region_fips)


def build_ercot_ejscreen() -> pd.DataFrame:
    return build_ejscreen_county(ERCOT_FIPS)


def build_caiso_ejscreen() -> pd.DataFrame:
    return build_ejscreen_county(CAISO_FIPS)
