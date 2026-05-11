"""Paginated download of CAL FIRE State Responsibility Area Fire Hazard Severity Zones."""
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import shape

URL = "https://socogis.sonomacounty.ca.gov/map/rest/services/CALFIREPublic/State_Responsibility_Area_Fire_Hazard_Severity_Zones/FeatureServer/0"
OUT_DIR = Path("data/raw/hifld/cal_fire_fhsz")
OUT_DIR.mkdir(parents=True, exist_ok=True)
PAGE_SIZE = 1000


def fetch_page(offset: int):
    params = {
        "where": "1=1",
        "outFields": "OBJECTID,SRA,FHSZ,FHSZ_Description",
        "f": "geojson",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "returnGeometry": "true",
        "outSR": 4326,
        "orderByFields": "OBJECTID",
    }
    r = requests.get(f"{URL}/query", params=params, timeout=120)
    r.raise_for_status()
    return r.json().get("features", [])


def count() -> int:
    r = requests.get(
        f"{URL}/query",
        params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        timeout=30,
    )
    return r.json().get("count", 0)


def main():
    total = count()
    print(f"Total polygons: {total:,}")
    feats = []
    offset = 0
    while offset < total:
        batch = fetch_page(offset)
        if not batch:
            break
        feats.extend(batch)
        offset += PAGE_SIZE
        print(f"  fetched {min(offset,total):,}/{total:,}", flush=True)
        time.sleep(0.3)

    rows = []
    geoms = []
    for f in feats:
        props = f.get("properties", {})
        geom = f.get("geometry")
        if geom is None:
            continue
        rows.append(props)
        geoms.append(shape(geom))

    df = pd.DataFrame(rows)
    gdf = gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")
    print(f"\nrows: {len(gdf):,}")
    print(f"FHSZ classes: {gdf['FHSZ_Description'].value_counts().to_dict()}")

    out_path = OUT_DIR / "FHSZ_SRA.shp"
    gdf.to_file(out_path)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
