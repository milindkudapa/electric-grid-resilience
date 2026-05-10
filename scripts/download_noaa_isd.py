"""
Standalone script to download NOAA ISD station files for ERCOT and CAISO.

Usage:
    uv run python scripts/download_noaa_isd.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import geopandas as gpd

from config.settings import (
    RAW,
    ERCOT_FIPS,
    CAISO_FIPS,
    HIST_START_YEAR,
    HIST_END_YEAR,
)
from src.data.noaa_isd import build_weather_panel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

TIGER_SHP = RAW["hifld"] / "tl_2023_us_county" / "tl_2023_us_county.shp"
CACHE_DIR = RAW["noaa_isd"]
YEAR_RANGE = (HIST_START_YEAR, HIST_END_YEAR)


def load_county_gdf(fips_list: list[str]):
    gdf = gpd.read_file(TIGER_SHP)[["GEOID", "geometry"]].rename(columns={"GEOID": "fips"})
    return gdf[gdf["fips"].isin(set(fips_list))].to_crs("EPSG:4326")


def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    for region, fips_list in [("ERCOT", ERCOT_FIPS), ("CAISO", CAISO_FIPS)]:
        log.info("=== %s: loading county geometries ===", region)
        county_gdf = load_county_gdf(fips_list)
        log.info("%s: %d counties", region, len(county_gdf))

        log.info("=== %s: downloading ISD station files (%d–%d) ===", region, *YEAR_RANGE)
        try:
            build_weather_panel(fips_list, county_gdf, CACHE_DIR, YEAR_RANGE)
            log.info("=== %s: done ===", region)
        except RuntimeError as exc:
            log.error("%s failed: %s", region, exc)

    log.info("All ISD files are cached in %s", CACHE_DIR)


if __name__ == "__main__":
    main()
