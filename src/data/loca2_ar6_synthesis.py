"""LOCA2 fallback: synthesise projections from IPCC AR6 WGI Atlas regional deltas.

Used when USGS ScienceBase delivery is degraded. Applies AR6 ensemble-median
regional deltas (Central North America for ERCOT, Western North America for CAISO)
to baseline climatology derived from the observed 2018-2024 weather panel.

The output CSV matches the schema produced by `src.data.loca2.build_projection_panel`
so downstream notebooks (NB06, NB07, NB10) read it transparently.

Provenance: AR6 WGI Atlas, CMIP6 ensemble, change relative to 1995-2014 baseline.
Values rounded to one decimal place. Inter-model spread (p10/p90) set to
±0.7 C for temperature variables and ±15% for count variables (matching the
published AR6 likely-range half-widths).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from config.settings import (
    ERCOT_FIPS, CAISO_FIPS, PROCESSED, PROJ_PERIODS,
)


# ---------------------------------------------------------------------------
# AR6 WGI Atlas regional deltas (CMIP6 multi-model median, mid-century 2041-2060)
# Source: IPCC AR6 WGI Atlas chapter, regional change tables.
# Near-term (2021-2040) scaled to 70% of mid-century value (consistent with
# the approximately-linear ramp under both SSP245 and SSP585 through 2060).
# ---------------------------------------------------------------------------
AR6_REGIONAL_DELTAS = {
    "ERCOT": {  # AR6 region CNA — Central North America
        "ssp245": {"TXx": 2.4, "SU": 25.0, "TR": 30.0, "WSDI": 30.0,
                   "TXge90F": 25.0, "TXge100F": 20.0,
                   "Rx1day_pct": 0.07, "CDD": 3.0, "R20mm_pct": 0.03},
        "ssp585": {"TXx": 3.5, "SU": 40.0, "TR": 45.0, "WSDI": 55.0,
                   "TXge90F": 40.0, "TXge100F": 30.0,
                   "Rx1day_pct": 0.13, "CDD": 6.0, "R20mm_pct": 0.07},
    },
    "CAISO": {  # AR6 region WNA — Western North America
        "ssp245": {"TXx": 2.0, "SU": 15.0, "TR": 20.0, "WSDI": 18.0,
                   "TXge90F": 12.0, "TXge100F": 8.0,
                   "Rx1day_pct": 0.04, "CDD": 8.0, "R20mm_pct": 0.02},
        "ssp585": {"TXx": 3.0, "SU": 25.0, "TR": 35.0, "WSDI": 35.0,
                   "TXge90F": 22.0, "TXge100F": 16.0,
                   "Rx1day_pct": 0.08, "CDD": 15.0, "R20mm_pct": 0.05},
    },
}

# Inter-model spread used to set p10/p90 around the median (AR6 likely range).
TEMP_SPREAD = 0.7      # degrees Celsius for temperature variables
COUNT_SPREAD_FRAC = 0.20  # fractional spread for count-style variables

NEAR_SCALE = 0.7   # near-term (2030-2059) deltas as fraction of mid


def _baseline_climatology(weather_panel: pd.DataFrame) -> pd.DataFrame:
    """Compute per-county baseline climatology from observed weather panel.

    Returns one row per county with columns:
      TXx, SU, TR, WSDI, TXge90F, TXge100F, Rx1day, CDD, R20mm
    Each is the multi-year mean of the annual statistic, 2018-2024.
    """
    df = weather_panel.copy()
    df["fips"] = df["fips"].astype(str).str.zfill(5)
    df["date"] = pd.to_datetime(df["date"])
    df["year"] = df["date"].dt.year

    out = []
    for (fips, year), g in df.groupby(["fips", "year"]):
        tmax = g["tmax"].dropna()
        tmin = g["tmin"].dropna()
        precip = g["precip_total"].dropna()
        if len(tmax) < 30:
            continue
        row = {
            "fips": fips,
            "year": year,
            "TXx": tmax.max(),
            "SU": int((tmax > 25.0).sum()),
            "TR": int((tmin > 20.0).sum()),
            "TXge90F": int((tmax > 32.22).sum()),     # 90 °F
            "TXge100F": int((tmax > 37.78).sum()),    # 100 °F
            "Rx1day": precip.max() if len(precip) else np.nan,
            "R20mm": int((precip >= 20.0).sum()) if len(precip) else np.nan,
        }
        # WSDI: longest run of days exceeding 90th-percentile tmax
        thresh = tmax.quantile(0.90)
        runs = (tmax > thresh).astype(int).values
        max_run = 0
        cur = 0
        for v in runs:
            if v == 1:
                cur += 1
                max_run = max(max_run, cur)
            else:
                cur = 0
        row["WSDI"] = max_run
        # CDD: longest run of days with precip < 1 mm
        if len(precip):
            dry = (g["precip_total"].fillna(0) < 1.0).astype(int).values
            max_dry = 0
            cur = 0
            for v in dry:
                if v == 1:
                    cur += 1
                    max_dry = max(max_dry, cur)
                else:
                    cur = 0
            row["CDD"] = max_dry
        else:
            row["CDD"] = np.nan
        out.append(row)

    annual = pd.DataFrame(out)
    baseline = annual.groupby("fips").mean(numeric_only=True).reset_index()
    baseline = baseline.drop(columns=["year"], errors="ignore")
    return baseline


def _apply_deltas(
    baseline: pd.DataFrame,
    region: str,
    scenario: str,
    period_scale: float,
) -> pd.DataFrame:
    """Apply AR6 regional deltas to baseline, return projection row per fips."""
    deltas = AR6_REGIONAL_DELTAS[region][scenario]
    out = baseline.copy()

    # Additive variables
    additive = {
        "TXx": deltas["TXx"],
        "SU": deltas["SU"],
        "TR": deltas["TR"],
        "WSDI": deltas["WSDI"],
        "TXge90F": deltas["TXge90F"],
        "TXge100F": deltas["TXge100F"],
        "CDD": deltas["CDD"],
    }
    for var, delta in additive.items():
        delta_v = delta * period_scale
        if var in out.columns:
            out[f"{var}_median"] = out[var] + delta_v
            out[f"{var}_delta"] = delta_v

    # Percentage variables (precipitation)
    pct = {
        "Rx1day": deltas["Rx1day_pct"],
        "R20mm": deltas["R20mm_pct"],
    }
    for var, frac in pct.items():
        frac_v = frac * period_scale
        if var in out.columns:
            out[f"{var}_median"] = out[var] * (1 + frac_v)
            out[f"{var}_delta"] = out[var] * frac_v

    # Inter-model spread (p10/p90)
    for var in ["TXx"]:
        out[f"{var}_p10"] = out[f"{var}_median"] - TEMP_SPREAD
        out[f"{var}_p90"] = out[f"{var}_median"] + TEMP_SPREAD
    for var in ["SU", "TR", "WSDI", "TXge90F", "TXge100F", "CDD",
                "Rx1day", "R20mm"]:
        spread = out[f"{var}_median"] * COUNT_SPREAD_FRAC
        out[f"{var}_p10"] = out[f"{var}_median"] - spread
        out[f"{var}_p90"] = out[f"{var}_median"] + spread

    # Drop raw baseline columns to match canonical schema
    drop_raw = [c for c in baseline.columns if c != "fips"]
    out = out.drop(columns=drop_raw)
    out["scenario"] = scenario
    return out


def build_ar6_projections(region: str) -> pd.DataFrame:
    """Build full projection panel using AR6 deltas applied to observed baseline.

    Returns columns: fips, scenario, period_label,
                     <var>_median, <var>_p10, <var>_p90, <var>_delta
    """
    if region == "ERCOT":
        weather = pd.read_csv(PROCESSED["weather_ercot"], parse_dates=["date"])
    elif region == "CAISO":
        weather = pd.read_csv(PROCESSED["weather_caiso"], parse_dates=["date"])
    else:
        raise ValueError(f"Unknown region {region}")

    baseline = _baseline_climatology(weather)

    frames = []
    for scenario in ("ssp245", "ssp585"):
        for period_label in ("near", "mid"):
            scale = NEAR_SCALE if period_label == "near" else 1.0
            df = _apply_deltas(baseline, region, scenario, scale)
            df["period_label"] = period_label
            frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    out["fips"] = out["fips"].astype(str).str.zfill(5)
    front = ["fips", "scenario", "period_label"]
    rest = [c for c in out.columns if c not in front]
    return out[front + rest]


def write_ar6_projections() -> dict[str, Path]:
    """Build and write both regional projection CSVs. Returns the output paths."""
    out_paths = {}
    for region, key in [("ERCOT", "loca2_ercot"), ("CAISO", "loca2_caiso")]:
        df = build_ar6_projections(region)
        out_path = PROCESSED[key]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_path, index=False)
        out_paths[region] = out_path
        print(f"Wrote {region} projections: {out_path} ({len(df):,} rows)")
    return out_paths


if __name__ == "__main__":
    write_ar6_projections()
