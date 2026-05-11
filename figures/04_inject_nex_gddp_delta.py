"""Compute per-county NEX-GDDP TXx delta and inject into loca2_projections CSVs.

Baseline: observed 2018-2024 annual max Tmax per county (weather panels).
Future:   NEX-GDDP-CMIP6 (ACCESS-CM2, SSP585) mean annual TXx, 2055-2059.
Delta:    future - baseline, per county.

Writes a new column `TXx_nex_delta` into loca2_projections_{ercot,caiso}.csv
for the mid-century SSP5-8.5 rows. Counties missing NEX-GDDP coverage get NaN.
"""
import pandas as pd
import numpy as np
from pathlib import Path

PROC = Path("data/processed")

# --- baseline from observed weather panels --------------------------------
def baseline_txx(weather_path: Path) -> pd.Series:
    w = pd.read_csv(weather_path, parse_dates=["date"])
    w["fips"] = w["fips"].astype(str).str.zfill(5)
    w["year"] = w["date"].dt.year
    annual = w.groupby(["fips", "year"])["tmax"].max()
    return annual.groupby("fips").mean()

base_e = baseline_txx(PROC / "weather_panel_ercot.csv")
base_c = baseline_txx(PROC / "weather_panel_caiso.csv")
print(f"baseline counties: ercot {len(base_e)}, caiso {len(base_c)}")

# --- future from NEX-GDDP-CMIP6 ------------------------------------------
nex = pd.read_csv(PROC / "nex_gddp_poc_txx.csv", dtype={"fips": str})
nex_mean = nex.groupby("fips")["TXx"].mean()
print(f"nex-gddp counties: {len(nex_mean)}")

# --- merge into both projection CSVs --------------------------------------
for key, base in [("loca2_projections_ercot.csv", base_e),
                  ("loca2_projections_caiso.csv", base_c)]:
    p = PROC / key
    df = pd.read_csv(p, dtype={"fips": str})
    # Project per county for mid-SSP5-8.5 only (NEX POC is mid-585)
    mask = (df["scenario"] == "ssp585") & (df["period_label"] == "mid")
    delta_per_fips = (nex_mean - base).rename("TXx_nex_delta")
    df["TXx_nex_delta"] = df["fips"].map(delta_per_fips)
    # For non-mid-585 rows we still write the value (mainly used by NB07)
    df.to_csv(p, index=False)
    nz = df.loc[mask, "TXx_nex_delta"].notna().sum()
    print(f"  {key}: wrote TXx_nex_delta — {nz}/{mask.sum()} mid-585 rows have value")
    print(f"    range: {df['TXx_nex_delta'].min():.2f} to {df['TXx_nex_delta'].max():.2f} °C")
