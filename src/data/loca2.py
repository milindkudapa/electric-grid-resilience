"""
USGS CMIP6-LOCA2 county spatial summaries loader.

Dataset: "CMIP6-LOCA2 spatial summaries of counties (TIGER 2023)" (Alder, 2025)
DOI:     10.5066/P1N9IRWC
ScienceBase: https://www.sciencebase.gov/catalog/item/673d0719d34e6b795de6b593

The published distribution is NetCDF (not CSV as earlier docs suggested).
The annual thresholds file `CMIP6-LOCA2_Thresholds_1950-2100_County2023_annual.nc`
contains 36 annual Climdex extreme-event metrics for every CONUS county, for 27
GCMs under SSP2-4.5, SSP3-7.0, and SSP5-8.5, 1950–2100. Total ~1.87 GB.

Variables, scenarios, and GCMs are all dimensions or coordinates inside the
NetCDF. We load via xarray, subset to the requested region FIPS and scenarios,
and return a long-form DataFrame for the rest of the pipeline.

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

# Climdex variables exposed by the LOCA2 thresholds file we need for the project
LOCA2_VARIABLES = {
    "SU":      "Summer days — annual count of days with Tmax > 25 °C",
    "TR":      "Tropical nights — annual count of days with Tmin > 20 °C",
    "TXx":     "Hottest day of the year (max Tmax, °C)",
    "WSDI":    "Warm Spell Duration Index — max consecutive days Tmax > 90th percentile",
    "TXge90F": "Days with Tmax ≥ 90 °F",
    "TXge100F":"Days with Tmax ≥ 100 °F",
    "Rx1day":  "Max 1-day precipitation (mm)",
    "Rx5day":  "Max 5-day precipitation (mm)",
    "CDD":     "Consecutive Dry Days — max run of days with precip < 1 mm",
    "R20mm":   "Annual count of very-heavy rain days (precip ≥ 20 mm)",
}

# Subset that downstream notebooks actually consume. Loader picks all available
# from this list to keep memory manageable.
DEFAULT_VARIABLES = list(LOCA2_VARIABLES.keys())

# Scenario name normalisation
_SCENARIO_ALIASES = {
    "ssp245": "ssp245", "ssp2-4.5": "ssp245", "SSP245": "ssp245", "ssp2_45": "ssp245",
    "ssp370": "ssp370", "ssp3-7.0": "ssp370", "SSP370": "ssp370", "ssp3_70": "ssp370",
    "ssp585": "ssp585", "ssp5-8.5": "ssp585", "SSP585": "ssp585", "ssp5_85": "ssp585",
}


def _normalise_scenario(scenario: str) -> str:
    return _SCENARIO_ALIASES.get(scenario, scenario.lower().replace("-", "").replace(".", ""))


# ---------------------------------------------------------------------------
# NetCDF loader (preferred path for USGS distribution)
# ---------------------------------------------------------------------------
def _find_nc(data_dir: Path, kind: str = "annual") -> Path | None:
    """Find the LOCA2 thresholds NetCDF for the given temporal resolution."""
    patterns = [
        f"*Thresholds*{kind}*.nc",
        f"*thresholds*{kind}*.nc",
        f"*LOCA2*{kind}*.nc",
    ]
    for pat in patterns:
        hits = sorted(data_dir.glob(pat))
        if hits:
            return hits[0]
    return None


def _county_dim_to_fips(da, coord_candidates=("GEOID", "geoid", "fips", "county")) -> str:
    """Identify which coordinate holds the 5-digit county FIPS code."""
    for c in coord_candidates:
        if c in da.coords:
            return c
        if c in da.dims:
            return c
    raise KeyError(
        f"Cannot find county FIPS coordinate in {list(da.coords) + list(da.dims)}"
    )


def _scenario_dim_name(ds) -> str | None:
    """Find scenario/experiment dimension in a LOCA2 NetCDF."""
    for c in ("scenario", "experiment_id", "experiment", "ssp"):
        if c in ds.dims or c in ds.coords:
            return c
    return None


def _gcm_dim_name(ds) -> str | None:
    """Find GCM dimension in a LOCA2 NetCDF."""
    for c in ("source_id", "gcm", "model", "ensemble"):
        if c in ds.dims or c in ds.coords:
            return c
    return None


def load_loca2_netcdf(
    region_fips: list[str],
    scenarios: list[str] | None = None,
    variables: list[str] | None = None,
    nc_path: Path | None = None,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """Load LOCA2 annual county Climdex metrics from the published NetCDF.

    Returns a long-form DataFrame:
        fips, year, gcm, scenario, <variable columns>

    The function is defensive about coordinate naming because the published
    file uses a mix of CF and CMIP6 conventions. If your file has different
    dimension names, override via the helpers in this module.
    """
    try:
        import xarray as xr
    except ImportError as e:
        raise ImportError("xarray is required to load LOCA2 NetCDF: pip install xarray netcdf4") from e

    data_dir = data_dir or RAW["loca2"]
    nc_path = nc_path or _find_nc(data_dir, kind="annual")
    if nc_path is None or not nc_path.exists():
        raise FileNotFoundError(
            f"LOCA2 annual thresholds NetCDF not found in {data_dir}.\n"
            "Download CMIP6-LOCA2_Thresholds_1950-2100_County2023_annual.nc from\n"
            "https://www.sciencebase.gov/catalog/item/673d0719d34e6b795de6b593"
        )

    log.info("Opening LOCA2 NetCDF: %s", nc_path)
    ds = xr.open_dataset(nc_path, decode_times=False, mask_and_scale=True)

    scenarios = [_normalise_scenario(s) for s in (scenarios or SSP_SCENARIOS)]
    requested_vars = variables or DEFAULT_VARIABLES
    avail = [v for v in requested_vars if v in ds.data_vars]
    if not avail:
        raise RuntimeError(
            f"None of the requested variables {requested_vars} are in the file. "
            f"Available data_vars: {list(ds.data_vars)[:40]}"
        )
    log.info("Loading %d/%d variables: %s", len(avail), len(requested_vars), avail)

    ds_sub = ds[avail]

    scenario_dim = _scenario_dim_name(ds_sub)
    if scenario_dim is not None:
        raw_scen = [str(x) for x in ds_sub[scenario_dim].values]
        normed   = [_normalise_scenario(s) for s in raw_scen]
        keep_idx = [i for i, s in enumerate(normed) if s in scenarios]
        if keep_idx:
            ds_sub = ds_sub.isel({scenario_dim: keep_idx})
            ds_sub = ds_sub.assign_coords({scenario_dim: [normed[i] for i in keep_idx]})

    fips_dim = _county_dim_to_fips(ds_sub)
    raw_fips = [str(x).zfill(5) for x in ds_sub[fips_dim].values]
    keep_idx = [i for i, f in enumerate(raw_fips) if f in set(region_fips)]
    if not keep_idx:
        raise RuntimeError(
            f"No requested FIPS found in NetCDF (found {len(raw_fips)} counties; "
            f"requested {len(region_fips)}). Check FIPS format."
        )
    ds_sub = ds_sub.isel({fips_dim: keep_idx})
    ds_sub = ds_sub.assign_coords({fips_dim: [raw_fips[i] for i in keep_idx]})

    df = ds_sub.to_dataframe().reset_index()

    rename = {}
    if fips_dim != "fips":
        rename[fips_dim] = "fips"
    if scenario_dim is not None and scenario_dim != "scenario":
        rename[scenario_dim] = "scenario"
    gcm_dim = _gcm_dim_name(ds_sub)
    if gcm_dim is not None and gcm_dim != "gcm":
        rename[gcm_dim] = "gcm"
    if "time" in df.columns and "year" not in df.columns:
        rename["time"] = "year"
    df = df.rename(columns=rename)

    if "fips" in df.columns:
        df["fips"] = df["fips"].astype(str).str.zfill(5)
    if "year" in df.columns:
        df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
        df = df.dropna(subset=["year"])

    if "scenario" not in df.columns and scenario_dim is None:
        log.warning("No scenario dimension — assuming single scenario; not filtering")

    log.info("Loaded LOCA2 long-form: %d rows × %d cols", len(df), len(df.columns))
    return df


# ---------------------------------------------------------------------------
# CSV / parquet fallback (for synthesised data)
# ---------------------------------------------------------------------------
def load_loca2_tabular(
    region_fips: list[str],
    scenario: str,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """Fallback loader for synthesised CSV/parquet LOCA2 substitutes.

    Used when the NetCDF is unavailable and a county-year-scenario table
    has been generated from another source (e.g., IPCC AR6 deltas applied
    to the historical weather panel).
    """
    scenario = _normalise_scenario(scenario)
    data_dir = data_dir or RAW["loca2"]

    files = list(data_dir.glob(f"*{scenario}*.csv")) + \
            list(data_dir.glob(f"*{scenario}*.parquet")) + \
            list(data_dir.glob("loca2_county_metrics*.csv")) + \
            list(data_dir.glob("loca2_county_metrics*.parquet"))
    files = list(set(files))
    if not files:
        raise FileNotFoundError(f"No tabular LOCA2 files for '{scenario}' in {data_dir}")

    frames = []
    for f in files:
        df = pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f, dtype={"fips": str})
        df.columns = df.columns.str.strip()
        if "fips" not in df.columns and "FIPS" in df.columns:
            df = df.rename(columns={"FIPS": "fips"})
        df["fips"] = df["fips"].astype(str).str.zfill(5)
        df = df[df["fips"].isin(set(region_fips))].copy()
        if "scenario" not in df.columns:
            df["scenario"] = scenario
        frames.append(df)

    if not frames:
        raise RuntimeError("Tabular LOCA2 files matched no requested FIPS.")
    combined = pd.concat(frames, ignore_index=True)
    if "scenario" in combined.columns:
        combined = combined[combined["scenario"].apply(_normalise_scenario) == scenario]
    return combined


# ---------------------------------------------------------------------------
# Unified loader — NetCDF first, tabular fallback
# ---------------------------------------------------------------------------
def load_loca2(
    region_fips: list[str],
    scenario: str,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """Load LOCA2 county metrics. Tries NetCDF first, then CSV/parquet."""
    data_dir = data_dir or RAW["loca2"]
    nc = _find_nc(data_dir, kind="annual")
    if nc is not None:
        try:
            return load_loca2_netcdf([scenario], region_fips, nc_path=nc, data_dir=data_dir) \
                if False else load_loca2_netcdf(region_fips, [scenario], nc_path=nc, data_dir=data_dir)
        except Exception as e:
            log.warning("NetCDF load failed (%s); trying tabular fallback.", e)
    return load_loca2_tabular(region_fips, scenario, data_dir)


# ---------------------------------------------------------------------------
# Climatology + change factors (unchanged from prior tabular version)
# ---------------------------------------------------------------------------
def compute_climatology(
    df: pd.DataFrame,
    period: tuple[int, int],
    variables: list[str] | None = None,
    groupby: list[str] | None = None,
) -> pd.DataFrame:
    """Multi-model ensemble statistics for a given period.

    Returns columns: fips, scenario, <var>_median, <var>_p10, <var>_p90.
    """
    period_df = df[(df["year"] >= period[0]) & (df["year"] <= period[1])].copy()
    if variables is None:
        skip = {"fips", "year", "gcm", "scenario", "variant_label", "ensemble"}
        variables = [c for c in df.columns if c not in skip and pd.api.types.is_numeric_dtype(df[c])]

    group_cols = groupby or ["fips", "scenario"]
    gcm_col = "gcm" if "gcm" in period_df.columns else None
    extra = [gcm_col] if gcm_col else []

    gcm_mean = period_df.groupby(group_cols + extra)[variables].mean()
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
    base = compute_climatology(df, baseline_period, variables)
    future = compute_climatology(df, future_period, variables)
    base   = base.set_index(["fips", "scenario"])
    future = future.set_index(["fips", "scenario"])

    base_cols   = [c for c in base.columns   if c.endswith("_median")]
    future_cols = [c for c in future.columns if c.endswith("_median")]
    shared = sorted(set(base_cols) & set(future_cols))

    delta = future[shared] - base[shared]
    delta.columns = [c.replace("_median", "_delta") for c in delta.columns]
    return delta.reset_index()


def build_projection_panel(
    region_fips: list[str],
    scenarios: list[str] = SSP_SCENARIOS,
    periods: dict[str, tuple[int, int]] = PROJ_PERIODS,
    data_dir: Path | None = None,
) -> pd.DataFrame:
    """Build the full LOCA2 projection panel for a region.

    Returns: fips, scenario, period_label, <var>_{median,p10,p90,delta}.

    Fallback order:
      1. NetCDF in raw/loca2/
      2. Per-scenario CSVs in raw/loca2/
      3. AR6 synthesis from observed weather baseline (when raw data absent)
    """
    data_dir = data_dir or RAW["loca2"]
    nc = _find_nc(data_dir, kind="annual")

    # Prefer single combined-NetCDF load (fast: all scenarios at once)
    if nc is not None:
        try:
            raw = load_loca2_netcdf(region_fips, scenarios, nc_path=nc, data_dir=data_dir)
        except Exception as e:
            log.warning("Combined NetCDF load failed: %s — falling back to per-scenario tabular.", e)
            raw = None
    else:
        raw = None

    if raw is None:
        per_scenario = []
        for scenario in scenarios:
            try:
                per_scenario.append(load_loca2_tabular(region_fips, scenario, data_dir))
            except (FileNotFoundError, RuntimeError) as exc:
                log.warning("Skipping %s: %s", scenario, exc)
        if not per_scenario:
            # Final fallback: AR6 regional synthesis from observed baseline
            log.warning("No raw LOCA2 data found — falling back to AR6 regional deltas.")
            from src.data.loca2_ar6_synthesis import build_ar6_projections
            from config.settings import ERCOT_FIPS, CAISO_FIPS
            if set(region_fips) <= set(ERCOT_FIPS):
                return build_ar6_projections("ERCOT")
            if set(region_fips) <= set(CAISO_FIPS):
                return build_ar6_projections("CAISO")
            raise RuntimeError(
                "No LOCA2 data and region_fips matches neither ERCOT nor CAISO."
            )
        raw = pd.concat(per_scenario, ignore_index=True)

    if "scenario" not in raw.columns:
        raise RuntimeError("LOCA2 data has no 'scenario' column.")
    raw["scenario"] = raw["scenario"].apply(_normalise_scenario)
    raw = raw[raw["scenario"].isin([_normalise_scenario(s) for s in scenarios])]

    all_frames = []
    for scenario in scenarios:
        scen_norm = _normalise_scenario(scenario)
        sub = raw[raw["scenario"] == scen_norm].copy()
        if len(sub) == 0:
            log.warning("No rows for scenario %s — skipping.", scen_norm)
            continue
        for label, period in periods.items():
            if label == "baseline":
                continue
            clim = compute_climatology(sub, period)
            clim["period_label"] = label
            delta = compute_change_factors(sub, periods["baseline"], period)
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
