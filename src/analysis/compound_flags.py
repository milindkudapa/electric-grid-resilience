"""
Derive compound weather event flags for the county × day panel.

All flag definitions follow the Nature 2025 EAGLE-I study thresholds
and standard WMO definitions referenced in the methodology.

Main entry point:
    add_weather_flags(weather_df) -> pd.DataFrame
        Accepts the daily weather panel (indexed by (fips, date) or with
        those as columns) and appends boolean flag columns in-place.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from config.settings import (
    HEATWAVE_TMAX_C,
    HEATWAVE_MIN_CONSECUTIVE_DAYS,
    COMPOUND_WIND_MS,
    COMPOUND_PRECIP_MM,
    COMPOUND_TRIPLE_PRECIP_MM,
)


# ---------------------------------------------------------------------------
# Single-column flags
# ---------------------------------------------------------------------------
def flag_heatwave_day(tmax: pd.Series) -> pd.Series:
    """1 if daily Tmax > HEATWAVE_TMAX_C (32.2 °C / 90 °F)."""
    return (tmax > HEATWAVE_TMAX_C).astype(int)


def flag_heatwave_event(
    heatwave_day: pd.Series,
    fips: pd.Series | None = None,
    date: pd.Series | None = None,
    min_consecutive: int = HEATWAVE_MIN_CONSECUTIVE_DAYS,
) -> pd.Series:
    """
    1 if the county is in the middle of ≥ min_consecutive consecutive heatwave days.

    Parameters
    ----------
    heatwave_day  : binary series (1/0)
    fips          : county FIPS series (required if data is not already grouped by county)
    date          : date series (required for proper consecutive-day counting)
    min_consecutive : minimum number of consecutive heatwave days to qualify

    When fips/date are None the series is assumed to be a single county already
    sorted by date.
    """
    if fips is None or date is None:
        return _consecutive_event(heatwave_day, min_consecutive)

    df = pd.DataFrame({"fips": fips, "date": date, "hw": heatwave_day})
    df = df.sort_values(["fips", "date"])
    result = df.groupby("fips")["hw"].transform(
        lambda s: _consecutive_event(s, min_consecutive)
    )
    return result.rename("heatwave_event")


def _consecutive_event(binary: pd.Series, min_run: int) -> pd.Series:
    """
    Given a binary series, return a series that is 1 for every element
    that belongs to a run of at least `min_run` consecutive 1s.
    """
    arr   = binary.values.astype(int)
    result = np.zeros_like(arr)
    n = len(arr)
    i = 0
    while i < n:
        if arr[i] == 1:
            j = i
            while j < n and arr[j] == 1:
                j += 1
            run_len = j - i
            if run_len >= min_run:
                result[i:j] = 1
            i = j
        else:
            i += 1
    return pd.Series(result, index=binary.index)


# ---------------------------------------------------------------------------
# Compound flags
# ---------------------------------------------------------------------------
def flag_compound_heat_wind(
    heatwave_day: pd.Series,
    wind_gust_max: pd.Series,
    wind_threshold: float = COMPOUND_WIND_MS,
) -> pd.Series:
    """1 if heatwave_day AND wind gust > wind_threshold (m/s)."""
    return ((heatwave_day == 1) & (wind_gust_max > wind_threshold)).astype(int)


def flag_compound_heat_precip(
    heatwave_day: pd.Series,
    precip_total: pd.Series,
    precip_threshold: float = COMPOUND_PRECIP_MM,
) -> pd.Series:
    """1 if heatwave_day AND precip > precip_threshold (mm)."""
    return ((heatwave_day == 1) & (precip_total > precip_threshold)).astype(int)


def flag_compound_triple(
    heatwave_day: pd.Series,
    wind_gust_max: pd.Series,
    precip_total: pd.Series,
    wind_threshold: float = COMPOUND_WIND_MS,
    precip_threshold: float = COMPOUND_TRIPLE_PRECIP_MM,
) -> pd.Series:
    """
    1 if all three conditions hold simultaneously:
        heatwave_day AND wind > wind_threshold AND precip > precip_threshold

    This is the '52× risk amplifier' combination from the Nature 2025 study.
    """
    return (
        (heatwave_day == 1) &
        (wind_gust_max > wind_threshold) &
        (precip_total > precip_threshold)
    ).astype(int)


# ---------------------------------------------------------------------------
# Master convenience function
# ---------------------------------------------------------------------------
def add_weather_flags(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add all compound weather event flags to the daily weather panel.

    Expected input columns (from noaa_isd.py output):
        tmax, wind_speed_max, (optionally precip_total)

    The function works whether (fips, date) are the index or columns.

    Returns a copy of the DataFrame with added columns:
        heatwave_day, heatwave_event,
        compound_heat_wind, compound_heat_precip, compound_triple
    """
    df = df.copy()

    # Promote index to columns if needed
    index_was_set = False
    if isinstance(df.index, pd.MultiIndex) and df.index.names == ["fips", "date"]:
        df = df.reset_index()
        index_was_set = True

    # Required column checks
    if "tmax" not in df.columns:
        raise KeyError("Column 'tmax' not found. Ensure weather panel includes daily Tmax.")

    df["heatwave_day"] = flag_heatwave_day(df["tmax"])

    if "fips" in df.columns and "date" in df.columns:
        df["heatwave_event"] = flag_heatwave_event(
            df["heatwave_day"], df["fips"], df["date"]
        )
    else:
        df["heatwave_event"] = flag_heatwave_event(df["heatwave_day"])

    wind_col   = "wind_speed_max" if "wind_speed_max" in df.columns else None
    precip_col = "precip_total"   if "precip_total"   in df.columns else None

    if wind_col:
        df["compound_heat_wind"] = flag_compound_heat_wind(df["heatwave_day"], df[wind_col])
    else:
        df["compound_heat_wind"] = np.nan

    if precip_col:
        df["compound_heat_precip"] = flag_compound_heat_precip(df["heatwave_day"], df[precip_col])
    else:
        df["compound_heat_precip"] = np.nan

    if wind_col and precip_col:
        df["compound_triple"] = flag_compound_triple(
            df["heatwave_day"], df[wind_col], df[precip_col]
        )
    else:
        df["compound_triple"] = np.nan

    if index_was_set:
        df = df.set_index(["fips", "date"])

    return df


# ---------------------------------------------------------------------------
# Outage rate summary by weather category
# ---------------------------------------------------------------------------
def outage_rates_by_category(merged_df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute outage event rates for each compound weather category.

    Parameters
    ----------
    merged_df : merged outage + weather panel with columns
                outage_event_flag, heatwave_day, compound_heat_wind, compound_triple

    Returns a summary DataFrame with columns:
        category, n_days, n_outage_days, outage_rate, relative_risk
    """
    df = merged_df.copy()
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()

    required = ["outage_event_flag", "heatwave_day", "compound_heat_wind", "compound_triple"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise KeyError(f"Missing columns for outage rate analysis: {missing}")

    def _rate(mask):
        sub = df[mask]
        n = len(sub)
        n_out = sub["outage_event_flag"].sum()
        return n, int(n_out), float(n_out / n) if n > 0 else 0.0

    n_norm, out_norm, rate_norm   = _rate(df["heatwave_day"] == 0)
    n_hw,   out_hw,   rate_hw     = _rate((df["heatwave_day"] == 1) & (df["compound_heat_wind"] == 0) & (df["compound_triple"] == 0))
    n_chw,  out_chw,  rate_chw    = _rate((df["compound_heat_wind"] == 1) & (df["compound_triple"] == 0))
    n_ct,   out_ct,   rate_ct     = _rate(df["compound_triple"] == 1)

    baseline = rate_norm if rate_norm > 0 else 1e-9
    rows = [
        {"category": "Normal (no heatwave)",          "n_days": n_norm, "n_outage_days": out_norm, "outage_rate": rate_norm, "relative_risk": 1.0},
        {"category": "Heatwave only",                 "n_days": n_hw,   "n_outage_days": out_hw,   "outage_rate": rate_hw,   "relative_risk": rate_hw   / baseline},
        {"category": "Compound: heat + wind",         "n_days": n_chw,  "n_outage_days": out_chw,  "outage_rate": rate_chw,  "relative_risk": rate_chw  / baseline},
        {"category": "Compound triple (heat+wind+precip)", "n_days": n_ct,  "n_outage_days": out_ct,  "outage_rate": rate_ct,  "relative_risk": rate_ct   / baseline},
    ]
    return pd.DataFrame(rows)
