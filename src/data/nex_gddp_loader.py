"""NEX-GDDP-CMIP6 alternative loader (anonymous AWS S3 access).

Companion to `loca2_ar6_synthesis.py`. Where the AR6 path applies a single
regional delta to every county, this path uses raw daily tasmax from the
NASA NEX-GDDP-CMIP6 ensemble (downscaled 0.25 deg grid, 1950-2100) and
computes per-county annual extremes by zonal statistics.

Bucket: s3://nex-gddp-cmip6/NEX-GDDP-CMIP6/<GCM>/<scenario>/<variant>/<var>/
File: <var>_day_<GCM>_<scenario>_<variant>_gn_<year>.nc  (~ 50 MB compressed)

For proof-of-concept we fetch 1 GCM, 1 scenario, a 5-year mid-century window,
compute annual TXx, then zonal-aggregate to ERCOT + CAISO counties.

Usage:
    uv run python -m src.data.nex_gddp_loader
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
import s3fs

from config.settings import ERCOT_FIPS, CAISO_FIPS, PROCESSED

BUCKET = "nex-gddp-cmip6"
ROOT_PREFIX = f"{BUCKET}/NEX-GDDP-CMIP6"

# Minimal proof-of-concept slice
GCM = "ACCESS-CM2"
VARIANT = "r1i1p1f1"
VARIABLE = "tasmax"
SCENARIO = "ssp585"
YEARS = list(range(2055, 2060))     # 5 years, mid-century

# Bounding box covering both ERCOT (TX) and CAISO (CA), with margin.
# Longitudes use 0-360 convention (NEX-GDDP).
LON_MIN, LON_MAX = 234.0, 270.0
LAT_MIN, LAT_MAX = 24.0, 43.0

CACHE_DIR = Path("data/raw/nex_gddp")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _annual_file_url(year: int, scenario: str = SCENARIO, gcm: str = GCM) -> str:
    return (
        f"s3://{ROOT_PREFIX}/{gcm}/{scenario}/{VARIANT}/{VARIABLE}/"
        f"{VARIABLE}_day_{gcm}_{scenario}_{VARIANT}_gn_{year}.nc"
    )


def load_subset(year: int) -> xr.DataArray:
    """Open one NEX-GDDP-CMIP6 annual file from S3 with lazy access.

    Returns the tasmax field already subset to the North-America bounding box.
    """
    fs = s3fs.S3FileSystem(anon=True)
    url = _annual_file_url(year)
    fobj = fs.open(url, mode="rb", cache_type="readahead")
    ds = xr.open_dataset(fobj, engine="h5netcdf", chunks={"time": 30})
    sub = ds[VARIABLE].sel(
        lon=slice(LON_MIN, LON_MAX),
        lat=slice(LAT_MIN, LAT_MAX),
    )
    return sub


def annual_txx_field(year: int) -> xr.DataArray:
    """Compute annual maximum daily Tmax (TXx) over the N. America subset.

    Returns a 2-D DataArray in degrees Celsius.
    """
    da = load_subset(year)
    # tasmax in Kelvin → degrees C
    txx = da.max(dim="time") - 273.15
    txx = txx.compute()
    txx.attrs["units"] = "degC"
    txx.attrs["year"] = year
    return txx


def zonal_county_mean(field: xr.DataArray, county_gdf, fips_col: str = "fips"):
    """Compute area-mean of `field` for each county polygon.

    Uses rasterstats-style point sampling (centroid of each county cell)
    rather than full rasterio overlay, to keep deps minimal.
    """
    import geopandas as gpd
    from shapely.geometry import box

    lats = field["lat"].values
    lons = field["lon"].values
    # Build sample grid points
    sample_lat, sample_lon = np.meshgrid(lats, lons, indexing="ij")
    flat_pts = gpd.GeoDataFrame(
        {
            "val": field.values.ravel(),
            "lat": sample_lat.ravel(),
            "lon": sample_lon.ravel() - 360.0,  # back to -180..180 for joining
        },
        geometry=gpd.points_from_xy(sample_lon.ravel() - 360.0, sample_lat.ravel()),
        crs="EPSG:4326",
    )
    flat_pts = flat_pts.dropna(subset=["val"])
    joined = gpd.sjoin(flat_pts, county_gdf[[fips_col, "geometry"]], predicate="within")
    return joined.groupby(fips_col)["val"].mean()


def run_proof_of_concept() -> pd.DataFrame:
    """Build a tiny NEX-GDDP-CMIP6 TXx panel for ERCOT + CAISO."""
    import geopandas as gpd
    counties = gpd.read_file("data/raw/hifld/tl_2023_us_county/tl_2023_us_county.shp")
    counties["fips"] = counties["GEOID"].astype(str).str.zfill(5)
    keep = counties[counties["fips"].isin(set(ERCOT_FIPS + CAISO_FIPS))]

    rows = []
    for year in YEARS:
        print(f"[{year}] downloading + computing TXx ...")
        try:
            txx = annual_txx_field(year)
        except Exception as exc:
            print(f"  year {year} failed: {exc}")
            continue
        county_means = zonal_county_mean(txx, keep)
        for fips, val in county_means.items():
            rows.append(dict(fips=fips, year=year, scenario=SCENARIO,
                             gcm=GCM, TXx=float(val)))
        print(f"  -> {len(county_means)} counties this year")

    if not rows:
        raise RuntimeError("No NEX-GDDP-CMIP6 data downloaded.")

    df = pd.DataFrame(rows)
    out_path = PROCESSED["loca2_ercot"].parent / "nex_gddp_poc_txx.csv"
    df.to_csv(out_path, index=False)
    print(f"\nWrote {out_path}: {len(df):,} rows")
    return df


if __name__ == "__main__":
    run_proof_of_concept()
