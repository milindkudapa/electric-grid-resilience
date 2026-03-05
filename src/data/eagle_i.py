"""
EAGLE-I Power Outage Data loader and aggregator.

Raw data format (per annual CSV):
    fips_code, county_name, state, customers_out, total_customers, run_start_time

Each row represents a 15-minute observation interval.

Main entry point:
    build_outage_panel(region_fips, year_range) -> pd.DataFrame
        Returns a county × day panel indexed by (fips, date) with daily metrics.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import (
    RAW,
    OUTAGE_FRACTION_THRESHOLD,
    ERCOT_FIPS,
    CAISO_FIPS,
    HIST_START_YEAR,
    HIST_END_YEAR,
)

log = logging.getLogger(__name__)

# Column names as they appear in EAGLE-I CSVs (may vary slightly by year).
# Adjust if the actual download uses different names.
_COL_FIPS      = "fips_code"
_COL_COUNTY    = "county_name"
_COL_STATE     = "state"
_COL_OUT       = "customers_out"
_COL_TOTAL     = "total_customers"
_COL_TIMESTAMP = "run_start_time"

INTERVAL_HOURS = 0.25   # 15-minute intervals


def _load_annual_csv(year: int) -> pd.DataFrame:
    """Load a single annual EAGLE-I CSV from data/raw/eagle_i/."""
    data_dir = RAW["eagle_i"]
    candidates = list(data_dir.glob(f"*{year}*.csv")) + list(data_dir.glob(f"*{year}*.parquet"))
    if not candidates:
        raise FileNotFoundError(
            f"No EAGLE-I file found for year {year} in {data_dir}. "
            "Run scripts/download_data.py to fetch raw data."
        )
    path = candidates[0]
    log.info("Loading EAGLE-I %d from %s", year, path)
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


def _standardise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise column names to the expected schema."""
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    # Some releases use slightly different names — map them here.
    renames = {
        "fipscode":      _COL_FIPS,
        "fips":          _COL_FIPS,
        "customersout":  _COL_OUT,
        "totalcustomers": _COL_TOTAL,
        "runstarttime":  _COL_TIMESTAMP,
        "timestamp":     _COL_TIMESTAMP,
    }
    df = df.rename(columns={k: v for k, v in renames.items() if k in df.columns})
    return df


def _to_five_digit_fips(series: pd.Series) -> pd.Series:
    """Zero-pad FIPS codes to 5 characters ('6037' -> '06037')."""
    return series.astype(str).str.zfill(5)


def load_raw(year: int, region_fips: list[str]) -> pd.DataFrame:
    """
    Load and filter raw EAGLE-I data for a given year and list of FIPS codes.

    Returns a DataFrame with columns:
        fips_code, customers_out, total_customers, run_start_time (datetime)
    """
    df = _load_annual_csv(year)
    df = _standardise_columns(df)

    required = {_COL_FIPS, _COL_OUT, _COL_TOTAL, _COL_TIMESTAMP}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"EAGLE-I CSV for {year} is missing columns: {missing}")

    df[_COL_FIPS] = _to_five_digit_fips(df[_COL_FIPS])
    df = df[df[_COL_FIPS].isin(set(region_fips))].copy()

    df[_COL_TIMESTAMP] = pd.to_datetime(df[_COL_TIMESTAMP], utc=True, errors="coerce")
    df = df.dropna(subset=[_COL_TIMESTAMP])

    # Ensure numeric
    df[_COL_OUT]   = pd.to_numeric(df[_COL_OUT],   errors="coerce").fillna(0).clip(lower=0)
    df[_COL_TOTAL] = pd.to_numeric(df[_COL_TOTAL], errors="coerce")

    return df[[_COL_FIPS, _COL_OUT, _COL_TOTAL, _COL_TIMESTAMP]]


def aggregate_to_daily(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate 15-minute EAGLE-I observations to daily county-level metrics.

    Output columns (per fips × date):
        max_customers_out        peak customers without power
        total_customer_hours     sum(customers_out * 0.25 h) across all intervals
        total_customers          max total_customers recorded that day
        outage_fraction          max_customers_out / total_customers
        outage_event_flag        1 if outage_fraction > threshold
        n_intervals              number of 15-min intervals with data (data quality proxy)
    """
    df = df.copy()
    df["date"] = df[_COL_TIMESTAMP].dt.date

    daily = (
        df.groupby([_COL_FIPS, "date"])
        .agg(
            max_customers_out=(_COL_OUT,   "max"),
            total_customer_hours=(_COL_OUT, lambda x: x.sum() * INTERVAL_HOURS),
            total_customers=(_COL_TOTAL,   "max"),
            n_intervals=(_COL_OUT,         "count"),
        )
        .reset_index()
    )

    daily["date"] = pd.to_datetime(daily["date"])
    daily["outage_fraction"] = daily["max_customers_out"] / daily["total_customers"].replace(0, np.nan)
    daily["outage_event_flag"] = (daily["outage_fraction"] > OUTAGE_FRACTION_THRESHOLD).astype(int)

    # Data coverage flag: full day = 96 intervals (24h × 4)
    daily["low_coverage_flag"] = (daily["n_intervals"] < 80).astype(int)

    return daily.rename(columns={_COL_FIPS: "fips"})


def build_outage_panel(
    region_fips: list[str],
    year_range: tuple[int, int] = (HIST_START_YEAR, HIST_END_YEAR),
) -> pd.DataFrame:
    """
    Build a complete county × day outage panel for the given FIPS list and year range.

    Parameters
    ----------
    region_fips : list of str
        Five-digit FIPS codes to include (e.g. ERCOT_FIPS or CAISO_FIPS).
    year_range : (start_year, end_year) inclusive

    Returns
    -------
    pd.DataFrame indexed by (fips, date)
    """
    frames = []
    for year in range(year_range[0], year_range[1] + 1):
        try:
            raw = load_raw(year, region_fips)
            daily = aggregate_to_daily(raw)
            frames.append(daily)
            log.info("Year %d: %d county-day rows", year, len(daily))
        except FileNotFoundError as exc:
            log.warning(str(exc))

    if not frames:
        raise RuntimeError(
            "No EAGLE-I data loaded. Download raw files first via scripts/download_data.py."
        )

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["fips", "date"])
    panel = panel.set_index(["fips", "date"])
    return panel


def build_ercot_panel() -> pd.DataFrame:
    """Convenience wrapper for the ERCOT region."""
    return build_outage_panel(ERCOT_FIPS)


def build_caiso_panel() -> pd.DataFrame:
    """Convenience wrapper for the CAISO region."""
    return build_outage_panel(CAISO_FIPS)
