"""Generate descriptive figures from processed panels."""
import os
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LogNorm

ROOT = Path("/burg-archive/home/mck2199/electric-grid-resilience")
PROC = ROOT / "data" / "processed"
OUT = PROC  # write figs alongside existing PNGs

ercot = pd.read_csv(PROC / "merged_panel_ercot.csv", parse_dates=["date"])
caiso = pd.read_csv(PROC / "merged_panel_caiso.csv", parse_dates=["date"])
ercot["fips"] = ercot["fips"].astype(str).str.zfill(5)
caiso["fips"] = caiso["fips"].astype(str).str.zfill(5)

# Outage panel for full ERCOT (254 counties — used in county map; weather merge drops to 133)
ercot_out = pd.read_csv(PROC / "outage_panel_ercot.csv", parse_dates=["date"])
caiso_out = pd.read_csv(PROC / "outage_panel_caiso.csv", parse_dates=["date"])
ercot_out["fips"] = ercot_out["fips"].astype(str).str.zfill(5)
caiso_out["fips"] = caiso_out["fips"].astype(str).str.zfill(5)

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.titleweight": "bold",
    "axes.titlesize": 12,
    "axes.labelsize": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


# =============================================================================
# Fig A. Annual customer-hours of outage — ERCOT + CAISO
# =============================================================================
e_yr = ercot_out.assign(year=ercot_out["date"].dt.year).groupby("year")["total_customer_hours"].sum()
c_yr = caiso_out.assign(year=caiso_out["date"].dt.year).groupby("year")["total_customer_hours"].sum()
years = sorted(set(e_yr.index) | set(c_yr.index))

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5), sharey=False)
ax1.bar(e_yr.index, e_yr.values / 1e6, color="#c0392b", edgecolor="white")
ax1.set_title("ERCOT — annual cumulative customer-hours of outage")
ax1.set_ylabel("Customer-hours (millions)")
ax1.set_xticks(years)
for x, y in zip(e_yr.index, e_yr.values):
    ax1.text(x, y / 1e6 * 1.01, f"{y/1e6:.1f}M", ha="center", va="bottom", fontsize=8)

ax2.bar(c_yr.index, c_yr.values / 1e6, color="#2c3e50", edgecolor="white")
ax2.set_title("CAISO — annual cumulative customer-hours of outage")
ax2.set_ylabel("Customer-hours (millions)")
ax2.set_xticks(years)
for x, y in zip(c_yr.index, c_yr.values):
    ax2.text(x, y / 1e6 * 1.01, f"{y/1e6:.1f}M", ha="center", va="bottom", fontsize=8)

fig.suptitle("Cumulative grid outage burden by year, 2018–2024", fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "annual_outage_burden.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote annual_outage_burden.png")


# =============================================================================
# Fig B. Uri (Feb 2021) + Beryl (Jul 2024) ERCOT daily customer-hours
# =============================================================================
daily_e = ercot_out.groupby("date")["total_customer_hours"].sum().sort_index()

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5))
uri = daily_e["2021-02-10":"2021-03-05"]
ax1.fill_between(uri.index, uri.values / 1e6, color="#2980b9", alpha=0.85)
ax1.plot(uri.index, uri.values / 1e6, color="#1b4f72", linewidth=1)
ax1.set_title("Winter Storm Uri — February 2021")
ax1.set_ylabel("Customer-hours of outage (millions)")
ax1.axvline(pd.Timestamp("2021-02-15"), color="black", linestyle="--", linewidth=0.8)
ax1.text(pd.Timestamp("2021-02-15"), ax1.get_ylim()[1] * 0.9, "  rolling blackouts begin",
         fontsize=8, va="top")
ax1.xaxis.set_major_locator(mdates.DayLocator(interval=5))
ax1.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

beryl = daily_e["2024-07-05":"2024-08-05"]
ax2.fill_between(beryl.index, beryl.values / 1e6, color="#c0392b", alpha=0.85)
ax2.plot(beryl.index, beryl.values / 1e6, color="#641e16", linewidth=1)
ax2.set_title("Hurricane Beryl — July 2024")
ax2.set_ylabel("Customer-hours of outage (millions)")
ax2.axvline(pd.Timestamp("2024-07-08"), color="black", linestyle="--", linewidth=0.8)
ax2.text(pd.Timestamp("2024-07-08"), ax2.get_ylim()[1] * 0.9, "  landfall",
         fontsize=8, va="top")
ax2.xaxis.set_major_locator(mdates.DayLocator(interval=5))
ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))

fig.suptitle("ERCOT extreme-event signatures: cold-storm vs hurricane",
             fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "uri_beryl_timeseries.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote uri_beryl_timeseries.png")


# =============================================================================
# Fig C. Heat dose-response curve — outage rate vs daily tmax
# =============================================================================
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
for ax, df, label, color in [
    (ax1, ercot, "ERCOT", "#c0392b"),
    (ax2, caiso, "CAISO", "#2c3e50"),
]:
    d = df.dropna(subset=["tmax", "outage_event_flag"]).copy()
    d["tmax_bin"] = pd.cut(d["tmax"], bins=np.arange(-10, 50, 2))
    g = d.groupby("tmax_bin").agg(
        rate=("outage_event_flag", "mean"),
        n=("outage_event_flag", "size"),
    ).reset_index()
    g["mid"] = g["tmax_bin"].apply(lambda x: x.mid)
    g = g[g["n"] >= 50]
    ax.plot(g["mid"], g["rate"], color=color, linewidth=2.5, marker="o", markersize=5)
    ax.fill_between(g["mid"], g["rate"], color=color, alpha=0.15)
    ax.axvline(32.2, color="orange", linestyle="--", linewidth=0.8, label="Heatwave 32.2 °C")
    cutoff = 36 if label == "ERCOT" else 38
    ax.axvline(cutoff, color="red", linestyle="--", linewidth=0.8, label=f"Alert {cutoff} °C")
    ax.set_title(f"{label} — outage rate vs daily Tmax")
    ax.set_xlabel("Daily Tmax (°C)")
    ax.set_ylabel("Mean outage event rate")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.25)

fig.suptitle("Heat dose-response curve: outage probability as a function of daily Tmax",
             fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "heat_dose_response.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote heat_dose_response.png")


# =============================================================================
# Fig D. Compound event scatter — wind × precip on heatwave days (ERCOT)
# =============================================================================
hw = ercot[ercot["heatwave_day"] == 1].dropna(subset=["wind_speed_max", "precip_total"]).copy()
hw["of_pos"] = hw["outage_fraction"].clip(lower=1e-4)
fig, ax = plt.subplots(figsize=(8.5, 6))
sc = ax.scatter(
    hw["wind_speed_max"], hw["precip_total"],
    c=hw["of_pos"], cmap="YlOrRd",
    norm=LogNorm(vmin=1e-4, vmax=1.0),
    s=8, alpha=0.55, edgecolor="none",
)
ax.axvline(15, color="black", linestyle="--", linewidth=0.8)
ax.axhline(10, color="black", linestyle="--", linewidth=0.8)
ax.text(15.2, ax.get_ylim()[1] * 0.95, "wind > 15 m s⁻¹", fontsize=9)
ax.text(ax.get_xlim()[1] * 0.5, 10.5, "precip > 10 mm", fontsize=9)
ax.set_xlabel("Daily maximum wind speed (m s⁻¹)")
ax.set_ylabel("Daily precipitation (mm)")
ax.set_title("ERCOT heatwave-day compound space: wind vs precipitation, coloured by outage fraction")
cb = plt.colorbar(sc, ax=ax, label="Outage fraction (log scale)")
ax.grid(True, alpha=0.25)
plt.tight_layout()
plt.savefig(OUT / "compound_scatter_ercot.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote compound_scatter_ercot.png")


# =============================================================================
# Fig E. Seasonal month × year heatmap — mean outage fraction
# =============================================================================
fig, axes = plt.subplots(1, 2, figsize=(12, 5))
for ax, df, label in [(axes[0], ercot_out, "ERCOT"), (axes[1], caiso_out, "CAISO")]:
    d = df.dropna(subset=["outage_fraction"]).copy()
    d["year"] = d["date"].dt.year
    d["month"] = d["date"].dt.month
    pivot = d.groupby(["year", "month"])["outage_fraction"].mean().unstack()
    pivot = pivot.reindex(columns=range(1, 13))
    im = ax.imshow(pivot.values * 100, aspect="auto", cmap="YlOrRd",
                   vmin=0, vmax=np.nanpercentile(pivot.values * 100, 95))
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xticks(range(12))
    ax.set_xticklabels(["J","F","M","A","M","J","J","A","S","O","N","D"])
    ax.set_title(f"{label} — mean outage fraction (%) by month × year")
    cb = plt.colorbar(im, ax=ax, label="% customers out (mean)")

fig.suptitle("Seasonal-temporal heatmap of outage intensity", fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(OUT / "seasonal_heatmap.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote seasonal_heatmap.png")


# =============================================================================
# Fig F. County choropleth — cumulative customer-hours (both regions)
# =============================================================================
try:
    import sys
    sys.path.insert(0, str(ROOT))
    import geopandas as gpd
    from config.settings import ERCOT_FIPS, CAISO_FIPS
    shp = gpd.read_file(ROOT / "data/raw/hifld/tl_2023_us_county/tl_2023_us_county.shp")
    shp["fips"] = shp["GEOID"].astype(str).str.zfill(5)

    e_tot = ercot_out.groupby("fips")["total_customer_hours"].sum().reset_index()
    c_tot = caiso_out.groupby("fips")["total_customer_hours"].sum().reset_index()

    e_gdf = shp[shp["fips"].isin(ERCOT_FIPS)].merge(e_tot, on="fips", how="left")
    c_gdf = shp[shp["fips"].isin(CAISO_FIPS)].merge(c_tot, on="fips", how="left")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))
    e_gdf.plot(column="total_customer_hours", ax=ax1, cmap="YlOrRd",
               edgecolor="white", linewidth=0.3, legend=True,
               legend_kwds={"label": "Cumulative customer-hours, 2018–2024", "shrink": 0.6},
               missing_kwds={"color": "lightgrey", "label": "no data"})
    ax1.set_title("ERCOT — cumulative outage burden by county")
    ax1.axis("off")

    c_gdf.plot(column="total_customer_hours", ax=ax2, cmap="YlOrRd",
               edgecolor="white", linewidth=0.3, legend=True,
               legend_kwds={"label": "Cumulative customer-hours, 2018–2024", "shrink": 0.6},
               missing_kwds={"color": "lightgrey", "label": "no data"})
    ax2.set_title("CAISO — cumulative outage burden by county")
    ax2.axis("off")
    fig.suptitle("Spatial concentration of outage burden across the seven-year window",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()
    plt.savefig(OUT / "county_burden_choropleth.png", dpi=160, bbox_inches="tight")
    plt.close()
    print("Wrote county_burden_choropleth.png")
except Exception as e:
    print(f"choropleth skipped: {e}")


# =============================================================================
# Fig G. Heatwave event duration distribution — ERCOT
# =============================================================================
def heatwave_run_lengths(df):
    runs = []
    for fips, g in df.sort_values(["fips", "date"]).groupby("fips"):
        flag = g["heatwave_day"].values
        run = 0
        for v in flag:
            if v == 1:
                run += 1
            else:
                if run >= 3:
                    runs.append(run)
                run = 0
        if run >= 3:
            runs.append(run)
    return np.array(runs)

e_runs = heatwave_run_lengths(ercot)
c_runs = heatwave_run_lengths(caiso)

fig, ax = plt.subplots(figsize=(9, 5))
bins = np.arange(3, 25)
ax.hist([e_runs, c_runs], bins=bins, label=[f"ERCOT (n={len(e_runs):,})",
                                            f"CAISO (n={len(c_runs):,})"],
        color=["#c0392b", "#2c3e50"], edgecolor="white")
ax.set_xlabel("Heatwave run length (consecutive days, ≥ 3)")
ax.set_ylabel("Count of heatwave events")
ax.set_title("Distribution of heatwave-event durations, 2018–2024 (WMO ≥ 3-day definition)")
ax.legend()
ax.grid(True, alpha=0.25, axis="y")
plt.tight_layout()
plt.savefig(OUT / "heatwave_duration_dist.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote heatwave_duration_dist.png")

print("\nAll figures saved to", OUT)
