"""Additional figures: asset vulnerability map + NEX-GDDP heat delta map."""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path("/burg-archive/home/mck2199/electric-grid-resilience")
sys.path.insert(0, str(ROOT))
from config.settings import ERCOT_FIPS, CAISO_FIPS

PROC = ROOT / "data" / "processed"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.titleweight": "bold",
    "axes.titlesize": 12,
    "axes.labelsize": 10,
})


# Load county shapefile
shp = gpd.read_file(ROOT / "data/raw/hifld/tl_2023_us_county/tl_2023_us_county.shp")
shp["fips"] = shp["GEOID"].astype(str).str.zfill(5)

# ---------- Fig: asset vulnerability composite choropleth ----------
risk = pd.read_csv(PROC / "asset_risk_scores.csv", dtype={"fips": str})
ercot_gdf = shp[shp["fips"].isin(ERCOT_FIPS)].merge(risk, on="fips", how="left")
caiso_gdf = shp[shp["fips"].isin(CAISO_FIPS)].merge(risk, on="fips", how="left")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6.5))
vmin = risk["composite_risk_score"].min()
vmax = risk["composite_risk_score"].max()

ercot_gdf.plot(
    column="composite_risk_score", ax=ax1, cmap="YlOrRd",
    vmin=vmin, vmax=vmax,
    edgecolor="white", linewidth=0.3,
    legend=True,
    legend_kwds={"label": "Composite risk score", "shrink": 0.6},
    missing_kwds={"color": "lightgrey", "label": "no data"},
)
ax1.set_title("ERCOT — asset vulnerability composite (heat + density)")
ax1.axis("off")

caiso_gdf.plot(
    column="composite_risk_score", ax=ax2, cmap="YlOrRd",
    vmin=vmin, vmax=vmax,
    edgecolor="white", linewidth=0.3,
    legend=True,
    legend_kwds={"label": "Composite risk score", "shrink": 0.6},
    missing_kwds={"color": "lightgrey", "label": "no data"},
)
ax2.set_title("CAISO — asset vulnerability composite (heat + fire + density)")
ax2.axis("off")

fig.suptitle("Asset vulnerability priority counties (0.4·heat + 0.3·fire + 0.3·density)",
             fontsize=13, fontweight="bold")
plt.tight_layout()
plt.savefig(PROC / "asset_vulnerability_map.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote asset_vulnerability_map.png")


# ---------- Fig: NEX-GDDP per-county TXx delta map ----------
proj_e = pd.read_csv(PROC / "loca2_projections_ercot.csv", dtype={"fips": str})
proj_c = pd.read_csv(PROC / "loca2_projections_caiso.csv", dtype={"fips": str})
mid_e = proj_e[(proj_e["scenario"] == "ssp585") & (proj_e["period_label"] == "mid")]
mid_c = proj_c[(proj_c["scenario"] == "ssp585") & (proj_c["period_label"] == "mid")]

both = pd.concat([
    mid_e[["fips", "TXx_nex_delta"]].assign(region="ERCOT"),
    mid_c[["fips", "TXx_nex_delta"]].assign(region="CAISO"),
], ignore_index=True)
both["fips"] = both["fips"].astype(str).str.zfill(5)

ercot_g2 = shp[shp["fips"].isin(ERCOT_FIPS)].merge(
    both[both["region"] == "ERCOT"], on="fips", how="left"
)
caiso_g2 = shp[shp["fips"].isin(CAISO_FIPS)].merge(
    both[both["region"] == "CAISO"], on="fips", how="left"
)

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6.5))
vmin2 = both["TXx_nex_delta"].quantile(0.02)
vmax2 = both["TXx_nex_delta"].quantile(0.98)

ercot_g2.plot(
    column="TXx_nex_delta", ax=ax1, cmap="RdYlBu_r",
    vmin=vmin2, vmax=vmax2,
    edgecolor="white", linewidth=0.3,
    legend=True,
    legend_kwds={"label": "TXx delta (°C, NEX-GDDP)", "shrink": 0.6},
    missing_kwds={"color": "lightgrey", "label": "no data"},
)
ax1.set_title("ERCOT — projected change in annual max Tmax")
ax1.axis("off")

caiso_g2.plot(
    column="TXx_nex_delta", ax=ax2, cmap="RdYlBu_r",
    vmin=vmin2, vmax=vmax2,
    edgecolor="white", linewidth=0.3,
    legend=True,
    legend_kwds={"label": "TXx delta (°C, NEX-GDDP)", "shrink": 0.6},
    missing_kwds={"color": "lightgrey", "label": "no data"},
)
ax2.set_title("CAISO — projected change in annual max Tmax")
ax2.axis("off")

fig.suptitle("NEX-GDDP-CMIP6 ACCESS-CM2 SSP5-8.5 mid-century TXx delta (vs 2018–2024 baseline)",
             fontsize=12, fontweight="bold")
plt.tight_layout()
plt.savefig(PROC / "nex_gddp_txx_delta_map.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote nex_gddp_txx_delta_map.png")


# ---------- Fig: contribution of each component to composite (stacked bar top counties) ----------
risk["w_heat"] = 0.40 * risk["heat_exposure_rank"]
risk["w_fire"] = 0.30 * risk["wildfire_exposure_rank"]
risk["w_dens"] = 0.30 * risk["asset_density_rank"]

top15 = risk.nlargest(15, "composite_risk_score").reset_index(drop=True)

# Attach county name from shp
top15 = top15.merge(shp[["fips", "NAME"]], on="fips", how="left")
top15["label"] = top15["NAME"] + " (" + top15["region"] + ")"

fig, ax = plt.subplots(figsize=(11, 6))
ax.barh(top15["label"][::-1], top15["w_heat"][::-1], label="Heat (0.40)", color="#c0392b")
ax.barh(top15["label"][::-1], top15["w_fire"][::-1], left=top15["w_heat"][::-1],
        label="Wildfire (0.30)", color="#e67e22")
ax.barh(top15["label"][::-1], top15["w_dens"][::-1],
        left=(top15["w_heat"] + top15["w_fire"])[::-1],
        label="Asset density (0.30)", color="#34495e")
ax.set_xlabel("Composite risk score (weighted)")
ax.set_title("Top 15 priority counties — composite breakdown by component")
ax.legend(loc="lower right", framealpha=0.9)
ax.grid(True, alpha=0.25, axis="x")
plt.tight_layout()
plt.savefig(PROC / "asset_top15_breakdown.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote asset_top15_breakdown.png")


# ---------- Fig: AR6 vs NEX-GDDP TXx scatter (cross-validation) ----------
ar6_e = mid_e[["fips", "TXx_median", "TXx_nex_delta"]].copy()
ar6_c = mid_c[["fips", "TXx_median", "TXx_nex_delta"]].copy()
ar6_combined = pd.concat([
    ar6_e.assign(region="ERCOT"),
    ar6_c.assign(region="CAISO"),
], ignore_index=True)

# Need baseline TXx to back out AR6 vs NEX absolute
w_e = pd.read_csv(PROC / "weather_panel_ercot.csv", parse_dates=["date"])
w_c = pd.read_csv(PROC / "weather_panel_caiso.csv", parse_dates=["date"])
w_e["fips"] = w_e["fips"].astype(str).str.zfill(5)
w_c["fips"] = w_c["fips"].astype(str).str.zfill(5)
w_e["year"] = w_e["date"].dt.year
w_c["year"] = w_c["date"].dt.year
base_e_series = w_e.groupby(["fips", "year"])["tmax"].max().groupby("fips").mean()
base_c_series = w_c.groupby(["fips", "year"])["tmax"].max().groupby("fips").mean()
base_combined = pd.concat([base_e_series, base_c_series]).rename("baseline_TXx")

ar6_combined = ar6_combined.merge(
    base_combined.reset_index(), on="fips", how="left"
)
ar6_combined["AR6_future_TXx"] = ar6_combined["TXx_median"]
ar6_combined["NEX_future_TXx"] = ar6_combined["baseline_TXx"] + ar6_combined["TXx_nex_delta"]

fig, ax = plt.subplots(figsize=(7, 7))
for region, color in [("ERCOT", "#c0392b"), ("CAISO", "#2c3e50")]:
    sub = ar6_combined[ar6_combined["region"] == region].dropna()
    ax.scatter(sub["AR6_future_TXx"], sub["NEX_future_TXx"],
               color=color, alpha=0.6, s=35, label=region, edgecolor="white", linewidth=0.5)
lo = min(ar6_combined["AR6_future_TXx"].min(), ar6_combined["NEX_future_TXx"].min()) - 1
hi = max(ar6_combined["AR6_future_TXx"].max(), ar6_combined["NEX_future_TXx"].max()) + 1
ax.plot([lo, hi], [lo, hi], "k--", alpha=0.5, label="1:1 line")
ax.set_xlabel("AR6 synthesis — projected TXx (°C)")
ax.set_ylabel("NEX-GDDP-CMIP6 — projected TXx (°C)")
ax.set_title("AR6 vs NEX-GDDP-CMIP6 mid-century TXx (SSP5-8.5, per county)")
ax.legend()
ax.grid(True, alpha=0.25)
plt.tight_layout()
plt.savefig(PROC / "ar6_vs_nex_gddp_txx.png", dpi=160, bbox_inches="tight")
plt.close()
print("Wrote ar6_vs_nex_gddp_txx.png")

# Print agreement statistics for the report
diff = (ar6_combined["AR6_future_TXx"] - ar6_combined["NEX_future_TXx"]).dropna()
print(f"\nAR6 vs NEX-GDDP TXx agreement (per county):")
print(f"  mean diff:   {diff.mean():.2f} °C")
print(f"  median diff: {diff.median():.2f} °C")
print(f"  RMSE:        {(diff**2).mean()**0.5:.2f} °C")
print(f"  abs<1°C:     {(diff.abs()<1).mean()*100:.0f}%")
print(f"  abs<2°C:     {(diff.abs()<2).mean()*100:.0f}%")
