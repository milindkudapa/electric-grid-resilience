"""
USGS CMIP6-LOCA2 county spatial summaries loader.

Dataset: "CMIP6-LOCA2 spatial summaries of counties (TIGER 2023)"
URL:     https://data.usgs.gov/datacatalog/data/USGS:673d0719d34e6b795de6b593

The dataset provides annual Climdex extreme-event metrics for every US county,
for 27 GCMs under SSP2-4.5, SSP3-7.0, and SSP5-8.5, 1950–2100.

Expected raw structure after manual download:
    data/raw/loca2/
        <GCM>_<scenario>_county_metrics.csv   (one file per GCM × scenario)
    OR a single combined NetCDF / parquet file if the USGS distributes it that way.

Main entry points:
    load_loca2(region_fips, scenario) -> pd.DataFrame
    compute_climatology(df, period) -> pd.DataFrame
    compute_change_factors(df, baseline_period, future_period) -> pd.DataFrame
    build_projection_panel(region_fips, scenarios, periods) -> pd.DataFrame
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import (
    RAW,
    SSP_SCENARIOS,
    PROJ_PERIODS,
    ERCOT_FIPS,
    CAISO_FIPS,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Climdex variable definitions (subset used in this project)
# ---------------------------------------------------------------------------
LOCA2_VARIABLES = {
    "SU":      "Summer days — annual count of days with Tmax > 25 °C",
    "TR":      "Tropical nights — annual count of days with Tmin > 20 °C",
    "TXx":     "Hottest day of the year (max Tmax, °C)",
    "WSDI":    "Warm Spell Duration Index — max consecutive days with Tmax > 90th percentile",
    "CDD":     "Cooling Degree Days — sum of (Tmax - base) when Tmax > base",
    "Rx1day":  "Max 1-day precipitation (mm)",
    "Rx5day":  "Max 5-day precipitation (mm)",
    "CDD_dry": "Consecutive Dry Days — max run of days with precip < 1 mm",
}

# Scenario name normalisation
_SCENARIO_ALIASES = {
    "ssp245": "ssp245", "ssp2-4.5": "ssp245", "SSP245": "ssp245",
    "ssp585": "ssp585", "ssp5-8.5": "ssp585", "SSP585": "ssp585",
    "ssp370": "ssp370", "ssp3-7.0": "ssp370", "SSP370": "ssp370",
}


def _normalise_scenario(scenario: str) -> str:
    return _SCENARIO_ALIASES.get(scenario, scenario.lower().replace("-", "").replace(".", ""))


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def load_loca2(
    region_fips: list[str],
    scenario: str,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Load LOCA2 annual county metrics for a given scenario and subset of FIPS codes.

    The function tries to find CSV or Parquet files matching the scenario name
    in data/raw/loca2/.  It concatenates all GCM files found.

    Returns a DataFrame with columns:
        fips, year, gcm, <variable columns…>
    """
    scenario = _normalise_scenario(scenario)
    data_dir = data_dir or RAW["loca2"]

    # Look for files that contain the scenario name in the filename
    patterns = [f"*{scenario}*.csv", f"*{scenario}*.parquet", f"*{scenario}*.nc"]
    files: list[Path] = []
    for pat in patterns:
        files.extend(data_dir.glob(pat))

    # Also accept a single combined file
    combined = list(data_dir.glob("loca2_county_metrics*.parquet")) + \
               list(data_dir.glob("loca2_county_metrics*.csv"))
    files = list(set(files + combined))

    if not files:
        raise FileNotFoundError(
            f"No LOCA2 files found for scenario '{scenario}' in {data_dir}.\n"
            "Download from: https://data.usgs.gov/datacatalog/data/USGS:673d0719d34e6b795de6b593"
        )

    frames = []
    for f in files:
        log.info("Loading LOCA2 file: %s", f)
        if f.suffix == ".parquet":
            df = pd.read_parquet(f)
        elif f.suffix == ".csv":
            df = pd.read_csv(f, dtype={"fips": str})
        else:
            log.warning("Unsupported format %s, skipping.", f)
            continue

        df.columns = df.columns.str.strip()
        if "fips" not in df.columns:
            if "FIPS" in df.columns:
                df = df.rename(columns={"FIPS": "fips"})
            else:
                log.warning("No fips column in %s, skipping.", f)
                continue

        df["fips"] = df["fips"].astype(str).str.zfill(5)
        df = df[df["fips"].isin(set(region_fips))].copy()

        # Attach scenario name if not already present
        if "scenario" not in df.columns:
            df["scenario"] = scenario

        frames.append(df)

    if not frames:
        raise RuntimeError("LOCA2 files found but no data matched the region FIPS codes.")

    combined_df = pd.concat(frames, ignore_index=True)
    # Filter to scenario in case a combined file was loaded
    if "scenario" in combined_df.columns:
        combined_df = combined_df[
            combined_df["scenario"].apply(_normalise_scenario) == scenario
        ]

    return combined_df


# ---------------------------------------------------------------------------
# Climatology computation
# ---------------------------------------------------------------------------
def compute_climatology(
    df: pd.DataFrame,
    period: tuple[int, int],
    variables: list[str] | None = None,
    groupby: list[str] | None = None,
) -> pd.DataFrame:
    """
    Compute multi-model ensemble statistics for a given period.

    Parameters
    ----------
    df        : LOCA2 DataFrame (fips, year, gcm, scenario, <vars>)
    period    : (start_year, end_year) inclusive
    variables : list of variable names to aggregate (default: all numeric)
    groupby   : additional groupby columns (default: ['fips', 'scenario'])

    Returns a DataFrame with columns:
        fips, scenario, <var>_median, <var>_p10, <var>_p90
    """
    period_df = df[(df["year"] >= period[0]) & (df["year"] <= period[1])].copy()

    if variables is None:
        variables = [c for c in df.columns if c not in ("fips", "year", "gcm", "scenario")]

    group_cols = groupby or ["fips", "scenario"]

    # First: annual mean per GCM (within the period)
    gcm_mean = period_df.groupby(group_cols + ["gcm"])[variables].mean()

    # Then: ensemble stats across GCMs
    result = gcm_mean.groupby(level=group_cols)[variables].agg(
        ["median", lambda x: x.quantile(0.10), lambda x: x.quantile(0.90)]
    )
    result.columns = ["_".join([v, s]) for v, s in result.columns]
    result.columns = result.columns.str.replace("<lambda_0>", "p10").str.replace("<lambda_1>", "p90")

    return result.reset_index()


def compute_change_factors(
    df: pd.DataFrame,
    baseline_period: tuple[int, int] = PROJ_PERIODS["baseline"],
    future_period: tuple[int, int] = PROJ_PERIODS["mid"],
    variables: list[str] | None = None,
) -> pd.DataFrame:
    """
    Compute Δ = future_median − baseline_median for each variable.

    Returns a DataFrame with fips, scenario, and delta columns.
    """
    base = compute_climatology(df, baseline_period, variables)
    future = compute_climatology(df, future_period, variables)

    base   = base.set_index(["fips", "scenario"])
    future = future.set_index(["fips", "scenario"])

    median_cols_base   = [c for c in base.columns   if c.endswith("_median")]
    median_cols_future = [c for c in future.columns if c.endswith("_median")]
    shared = list(set(median_cols_base) & set(median_cols_future))

    delta = future[shared] - base[shared]
    delta.columns = [c.replace("_median", "_delta") for c in delta.columns]
    return delta.reset_index()


# ---------------------------------------------------------------------------
# Full panel builder
# ---------------------------------------------------------------------------
def build_projection_panel(
    region_fips: list[str],
    scenarios: list[str] = SSP_SCENARIOS,
    periods: dict[str, tuple[int, int]] = PROJ_PERIODS,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Build the full LOCA2 projection panel for a region.

    Returns a single DataFrame with:
        fips, scenario, period_label, <variable>_median, <variable>_p10,
        <variable>_p90, <variable>_delta  (vs. baseline)
    """
    all_frames = []
    for scenario in scenarios:
        try:
            raw = load_loca2(region_fips, scenario, data_dir)
        except (FileNotFoundError, RuntimeError) as exc:
            log.warning("Skipping %s: %s", scenario, exc)
            continue

        base_clim = compute_climatology(raw, periods["baseline"])
        base_clim["period_label"] = "baseline"

        for label, period in periods.items():
            if label == "baseline":
                continue
            clim = compute_climatology(raw, period)
            clim["period_label"] = label

            delta = compute_change_factors(raw, periods["baseline"], period)
            # Merge delta into climatology frame
            merged = clim.merge(delta, on=["fips", "scenario"], suffixes=("", "_dup"))
            merged = merged[[c for c in merged.columns if not c.endswith("_dup")]]
            all_frames.append(merged)

    if not all_frames:
        raise RuntimeError("No LOCA2 projection data loaded.")

    return pd.concat(all_frames, ignore_index=True)


def build_ercot_projections() -> pd.DataFrame:
    return build_projection_panel(ERCOT_FIPS)


def build_caiso_projections() -> pd.DataFrame:
    return build_projection_panel(CAISO_FIPS)
