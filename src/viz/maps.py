"""
Visualisation helpers for the Grid Resilience project.

Functions:
    choropleth_county(gdf, value_col, ...)    — county choropleth map
    outage_heatmap(panel_df, ...)             — county × time heatmap
    rd_plot(df, rd_result, ...)               — RD bin-scatter plot
    sensitivity_heatmap(sensitivity_df, ...) — stress-test sensitivity grid
    projection_bar(loca2_df, metric, ...)     — bar chart of projected changes
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import seaborn as sns


# ---------------------------------------------------------------------------
# Style defaults
# ---------------------------------------------------------------------------
_PALETTE  = "YlOrRd"
_FIG_SIZE = (12, 7)

plt.rcParams.update({
    "figure.dpi": 120,
    "axes.spines.top":    False,
    "axes.spines.right":  False,
    "font.size": 11,
})


# ---------------------------------------------------------------------------
# 1. County choropleth
# ---------------------------------------------------------------------------
def choropleth_county(
    gdf,                        # geopandas.GeoDataFrame with 'fips' and geometry
    value_col: str,
    title: str = "",
    cmap: str = _PALETTE,
    vmin: float | None = None,
    vmax: float | None = None,
    figsize: tuple = (14, 9),
    missing_color: str = "#cccccc",
    legend_label: str = "",
    ax=None,
) -> plt.Axes:
    """
    Plot a choropleth map of county-level values.

    Parameters
    ----------
    gdf        : GeoDataFrame with a column matching value_col
    value_col  : column to use for colouring
    title      : plot title
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)

    gdf_plot = gdf.copy()
    gdf_plot[value_col] = pd.to_numeric(gdf_plot[value_col], errors="coerce")

    gdf_plot.plot(
        column=value_col,
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        legend=True,
        legend_kwds={"label": legend_label, "shrink": 0.6},
        missing_kwds={"color": missing_color, "label": "No data"},
        ax=ax,
    )
    ax.set_title(title, fontsize=14, pad=12)
    ax.axis("off")
    return ax


# ---------------------------------------------------------------------------
# 2. County × day outage heatmap
# ---------------------------------------------------------------------------
def outage_heatmap(
    panel_df: pd.DataFrame,
    value_col: str = "outage_fraction",
    top_n_counties: int = 40,
    date_range: tuple[str, str] | None = None,
    cmap: str = "Reds",
    figsize: tuple = (16, 10),
    title: str = "Outage severity heatmap (county × day)",
    ax=None,
) -> plt.Axes:
    """
    Plot a heatmap with counties on the y-axis and dates on the x-axis.

    Counties are sorted by total outage severity (most affected at top).
    """
    df = panel_df.copy()
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()

    if date_range:
        df = df[(df["date"] >= date_range[0]) & (df["date"] <= date_range[1])]

    # Select top N most-affected counties
    county_totals = df.groupby("fips")[value_col].sum().nlargest(top_n_counties)
    df = df[df["fips"].isin(county_totals.index)]

    # Pivot to (county, date) matrix
    pivot = df.pivot_table(index="fips", columns="date", values=value_col, aggfunc="mean")
    pivot = pivot.loc[county_totals.index]   # sort by severity

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)

    sns.heatmap(
        pivot,
        cmap=cmap,
        ax=ax,
        xticklabels=max(1, pivot.shape[1] // 20),
        yticklabels=True,
        cbar_kws={"label": value_col, "shrink": 0.6},
    )
    ax.set_title(title, fontsize=14, pad=12)
    ax.set_xlabel("Date")
    ax.set_ylabel("County FIPS")
    plt.xticks(rotation=45, ha="right")
    return ax


# ---------------------------------------------------------------------------
# 3. RD bin-scatter plot
# ---------------------------------------------------------------------------
def rd_plot(
    df: pd.DataFrame,
    rd_result,           # RDResult dataclass from rd_analysis.py
    running_var: str = "tmax",
    outcome: str = "total_customer_hours",
    n_bins: int = 40,
    figsize: tuple = _FIG_SIZE,
    title: str | None = None,
    ax=None,
) -> plt.Axes:
    """
    Produce a standard RD bin-scatter plot:
      - x-axis: running variable (centred at cutoff)
      - y-axis: outcome variable
      - vertical line at cutoff
      - fitted local linear lines on each side
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)

    df_plot = df[[running_var, outcome]].dropna().copy()
    df_plot["xc"] = df_plot[running_var] - rd_result.cutoff

    # Bin means within bandwidth
    bw = rd_result.bandwidth
    df_plot = df_plot[np.abs(df_plot["xc"]) <= bw]
    bin_edges = np.linspace(-bw, bw, n_bins + 1)
    df_plot["bin"] = pd.cut(df_plot["xc"], bins=bin_edges)
    bin_means = df_plot.groupby("bin")[outcome].mean()
    bin_centers = [(b.left + b.right) / 2 for b in bin_means.index]

    left_mask  = np.array(bin_centers) <  0
    right_mask = np.array(bin_centers) >= 0

    ax.scatter(np.array(bin_centers)[left_mask],  bin_means.values[left_mask],
               color="steelblue", s=30, zorder=3, label="Left of cutoff")
    ax.scatter(np.array(bin_centers)[right_mask], bin_means.values[right_mask],
               color="firebrick", s=30, zorder=3, label="Right of cutoff")

    # Fit lines
    for mask, colour in [(left_mask, "steelblue"), (right_mask, "firebrick")]:
        xv = np.array(bin_centers)[mask]
        yv = bin_means.values[mask]
        if len(xv) > 1:
            coef = np.polyfit(xv, yv, 1)
            x_line = np.linspace(xv.min(), xv.max(), 100)
            ax.plot(x_line, np.polyval(coef, x_line), color=colour, linewidth=2)

    ax.axvline(0, color="black", linestyle="--", linewidth=1.5, label=f"Cutoff = {rd_result.cutoff:.1f} °C")

    if title is None:
        title = (
            f"RD: τ = {rd_result.tau:.2f}  "
            f"(SE={rd_result.se:.2f}, p={rd_result.p_value:.3f})"
        )
    ax.set_title(title, fontsize=13)
    ax.set_xlabel(f"{running_var} − {rd_result.cutoff:.1f} °C (centred)")
    ax.set_ylabel(outcome)
    ax.legend()
    return ax


# ---------------------------------------------------------------------------
# 4. Stress-test sensitivity heatmap
# ---------------------------------------------------------------------------
def sensitivity_heatmap(
    sensitivity_df: pd.DataFrame,
    value_col: str = "capacity_margin_mw",
    row_var: str = "temp_delta_c",
    col_var: str = "demand_growth_rate",
    figsize: tuple = (10, 6),
    title: str = "Capacity margin sensitivity (MW)",
    ax=None,
) -> plt.Axes:
    """
    Plot the stress-test sensitivity table as a colour-coded heatmap.
    Negative margins (deficits) are shown in red.
    """
    pivot = sensitivity_df.pivot(index=row_var, columns=col_var, values=value_col)

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)

    # Diverging colormap centred at 0
    vmax = np.abs(pivot.values).max()
    norm = mcolors.TwoSlopeNorm(vmin=-vmax, vcenter=0, vmax=vmax)

    sns.heatmap(
        pivot,
        cmap="RdYlGn",
        norm=norm,
        annot=True,
        fmt=".0f",
        ax=ax,
        cbar_kws={"label": value_col},
    )
    ax.set_title(title, fontsize=13)
    ax.set_xlabel(f"{col_var} (annual)")
    ax.set_ylabel(f"{row_var} (°C offset)")
    return ax


# ---------------------------------------------------------------------------
# 5. LOCA2 projected change bar chart
# ---------------------------------------------------------------------------
def projection_bar(
    loca2_summary: pd.DataFrame,
    metric_delta: str = "WSDI_delta",
    groupby: str = "scenario",
    top_n: int = 20,
    figsize: tuple = _FIG_SIZE,
    title: str | None = None,
    ax=None,
) -> plt.Axes:
    """
    Bar chart of projected metric change (Δ) across counties, grouped by scenario.

    Parameters
    ----------
    loca2_summary : DataFrame with 'fips', 'scenario', and delta column(s)
    metric_delta  : column to plot (e.g. 'WSDI_delta', 'SU_delta')
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)

    if metric_delta not in loca2_summary.columns:
        raise KeyError(f"Column '{metric_delta}' not found in LOCA2 summary.")

    # Aggregate to mean across counties per scenario
    summary = (
        loca2_summary.groupby(["fips", groupby])[metric_delta]
        .mean()
        .reset_index()
        .sort_values(metric_delta, ascending=False)
        .head(top_n * loca2_summary[groupby].nunique())
    )

    scenarios = summary[groupby].unique()
    x = np.arange(len(summary["fips"].unique()))
    width = 0.8 / len(scenarios)

    for i, sc in enumerate(scenarios):
        sub = summary[summary[groupby] == sc].set_index("fips")
        fips_order = summary["fips"].unique()
        vals = [sub.loc[f, metric_delta] if f in sub.index else 0 for f in fips_order]
        ax.bar(x + i * width, vals, width=width, label=sc)

    ax.set_xticks(x + width * (len(scenarios) - 1) / 2)
    ax.set_xticklabels(summary["fips"].unique(), rotation=90, fontsize=7)
    ax.set_ylabel(f"Δ {metric_delta}")
    ax.set_title(title or f"Projected change in {metric_delta} by county", fontsize=13)
    ax.legend(title=groupby)
    ax.axhline(0, color="black", linewidth=0.8)
    return ax


# ---------------------------------------------------------------------------
# 6. Outage rate by weather category bar chart
# ---------------------------------------------------------------------------
def outage_rate_bar(
    rates_df: pd.DataFrame,
    figsize: tuple = (9, 5),
    title: str = "Outage event rates by weather category",
    ax=None,
) -> plt.Axes:
    """
    Plot relative risk ratios from compound_flags.outage_rates_by_category().
    """
    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)

    colors = ["#4CAF50", "#FFC107", "#FF5722", "#B71C1C"]
    bars = ax.bar(
        rates_df["category"],
        rates_df["relative_risk"],
        color=colors[: len(rates_df)],
        edgecolor="white",
    )
    ax.bar_label(bars, fmt="%.1fx", padding=3)
    ax.axhline(1, color="black", linewidth=0.8, linestyle="--")
    ax.set_ylabel("Relative risk vs. normal days")
    ax.set_title(title, fontsize=13)
    ax.set_xticklabels(rates_df["category"], rotation=20, ha="right")
    return ax
