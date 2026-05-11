"""Paginated download of HIFLD substations via ArcGIS REST API.

Filters to ERCOT (TX) + CAISO (CA) states to keep file size small while
covering everything the analysis needs.
"""
import json
import time
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry import Point

URL = "https://services6.arcgis.com/OO2s4OoyCZkYJ6oE/arcgis/rest/services/Substations/FeatureServer/0"
OUT_DIR = Path("data/raw/hifld")
OUT_DIR.mkdir(parents=True, exist_ok=True)

PAGE_SIZE = 2000
STATE_FILTER = "STATE IN ('TX','CA')"
FIELDS = "ID,NAME,CITY,STATE,COUNTY,COUNTYFIPS,TYPE,STATUS,LATITUDE,LONGITUDE,MAX_VOLT,MIN_VOLT,LINES"


def fetch_page(offset: int) -> list[dict]:
    params = {
        "where": STATE_FILTER,
        "outFields": FIELDS,
        "f": "json",
        "resultOffset": offset,
        "resultRecordCount": PAGE_SIZE,
        "returnGeometry": "true",
        "orderByFields": "OBJECTID",
    }
    r = requests.get(f"{URL}/query", params=params, timeout=60)
    r.raise_for_status()
    return r.json().get("features", [])


def fetch_count() -> int:
    r = requests.get(
        f"{URL}/query",
        params={"where": STATE_FILTER, "returnCountOnly": "true", "f": "json"},
        timeout=30,
    )
    return r.json().get("count", 0)


def main():
    total = fetch_count()
    print(f"Total TX+CA substations: {total:,}")

    rows = []
    offset = 0
    while offset < total:
        features = fetch_page(offset)
        if not features:
            break
        for f in features:
            attrs = f["attributes"]
            geom = f.get("geometry") or {}
            lon = geom.get("x") or attrs.get("LONGITUDE")
            lat = geom.get("y") or attrs.get("LATITUDE")
            if lon is None or lat is None:
                continue
            attrs["_geom_lon"] = lon
            attrs["_geom_lat"] = lat
            rows.append(attrs)
        offset += PAGE_SIZE
        print(f"  fetched {min(offset,total):,}/{total:,}", flush=True)
        time.sleep(0.2)

    df = pd.DataFrame(rows)
    print(f"\nDownloaded {len(df):,} rows")
    print(f"States: {df['STATE'].value_counts().to_dict()}")

    # Build geopandas frame
    gdf = gpd.GeoDataFrame(
        df.drop(columns=["_geom_lon", "_geom_lat"]),
        geometry=[Point(x, y) for x, y in zip(df["_geom_lon"], df["_geom_lat"])],
        crs="EPSG:4326",
    )

    csv_path = OUT_DIR / "electric_substations.csv"
    shp_path = OUT_DIR / "Electric_Substations.shp"

    # Save CSV (drop geometry for CSV)
    df.drop(columns=["_geom_lon", "_geom_lat"]).to_csv(csv_path, index=False)
    print(f"Wrote {csv_path}")

    # Replace old shapefile with new one
    if shp_path.exists():
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            p = shp_path.with_suffix(ext)
            if p.exists():
                p.unlink()
    gdf.to_file(shp_path)
    print(f"Wrote {shp_path}")


if __name__ == "__main__":
    main()
