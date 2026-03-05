"""
NOAA Integrated Surface Database (ISD) downloader and county-level aggregator.

Workflow:
1. Download ISD station history (isd-history.csv) to identify stations within
   ERCOT / CAISO boundaries.
2. Download hourly observation files for each station from AWS S3
   (s3://noaa-isd-pds/data/<YYYY>/<USAF>-<WBAN>-<YYYY>.gz).
3. Parse mandatory hourly fields (temperature, dew point, wind speed, precip).
4. Spatial-join each station to its county polygon using geopandas.
5. Average across stations within each county to produce daily county metrics.

Main entry point:
    build_weather_panel(region_fips, county_shp, year_range) -> pd.DataFrame
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ISD station history
# ---------------------------------------------------------------------------
ISD_HISTORY_URL = (
    "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
)
S3_BUCKET = "noaa-isd-pds"


def load_station_history(cache_dir: Path) -> pd.DataFrame:
    """
    Download (or load from cache) the ISD station history CSV.

    Returns a DataFrame with columns:
        usaf, wban, station_name, ctry, state, lat, lon, elev, begin, end
    """
    cache_path = cache_dir / "isd-history.csv"
    if cache_path.exists():
        log.info("Loading ISD history from cache: %s", cache_path)
        df = pd.read_csv(cache_path, dtype=str)
    else:
        import requests
        log.info("Downloading ISD history from NOAA …")
        r = requests.get(ISD_HISTORY_URL, timeout=60)
        r.raise_for_status()
        cache_path.write_bytes(r.content)
        df = pd.read_csv(io.BytesIO(r.content), dtype=str)

    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    return df


def filter_stations_by_bbox(
    station_history: pd.DataFrame,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    active_after: int = 2017,
) -> pd.DataFrame:
    """Return stations within a bounding box that were active after `active_after`."""
    df = station_history.copy()
    df["end_year"] = pd.to_numeric(df["end"].str[:4], errors="coerce")
    mask = (
        (df["lat"] >= lat_min) & (df["lat"] <= lat_max) &
        (df["lon"] >= lon_min) & (df["lon"] <= lon_max) &
        (df["end_year"] >= active_after)
    )
    return df[mask].reset_index(drop=True)


def assign_stations_to_counties(
    stations: pd.DataFrame,
    county_gdf,       # geopandas.GeoDataFrame with 'fips' column
) -> pd.DataFrame:
    """
    Spatial join: assign each ISD station to a county FIPS code.

    Parameters
    ----------
    stations    : DataFrame with 'lat', 'lon' columns
    county_gdf  : GeoDataFrame (EPSG:4326) with 'fips' geometry column

    Returns the stations DataFrame with an added 'fips' column.
    """
    try:
        import geopandas as gpd
        from shapely.geometry import Point
    except ImportError as e:
        raise ImportError("geopandas and shapely are required for spatial join.") from e

    gdf = gpd.GeoDataFrame(
        stations,
        geometry=[Point(lon, lat) for lon, lat in zip(stations["lon"], stations["lat"])],
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(gdf, county_gdf[["fips", "geometry"]], how="left", predicate="within")
    return pd.DataFrame(joined.drop(columns=["geometry", "index_right"], errors="ignore"))


# ---------------------------------------------------------------------------
# ISD hourly file parser
# ---------------------------------------------------------------------------
def s3_key(usaf: str, wban: str, year: int) -> str:
    return f"data/{year}/{usaf}-{wban}-{year}.gz"


def download_station_year(
    usaf: str, wban: str, year: int, cache_dir: Path
) -> Path | None:
    """
    Download a single station-year gz file from the NOAA ISD S3 bucket.
    Returns the local path, or None if the file doesn't exist on S3.
    """
    import boto3
    from botocore import UNSIGNED
    from botocore.config import Config

    local = cache_dir / f"{usaf}-{wban}-{year}.gz"
    if local.exists():
        return local

    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    key = s3_key(usaf, wban, year)
    try:
        s3.download_file(S3_BUCKET, key, str(local))
        return local
    except Exception:
        return None


def parse_isd_gz(path: Path) -> pd.DataFrame:
    """
    Parse a single ISD fixed-width .gz file.

    Extracts the mandatory data section fields:
        datetime, air_temp_c, dew_point_c, wind_speed_ms, wind_gust_ms, precip_mm, rh_pct

    ISD fixed-width format reference:
        https://www.ncei.noaa.gov/data/global-hourly/doc/isd-format-document.pdf
    """
    import gzip

    records = []
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            if len(line) < 60:
                continue
            try:
                year  = int(line[15:19])
                month = int(line[19:21])
                day   = int(line[21:23])
                hour  = int(line[23:25])
                dt    = pd.Timestamp(year=year, month=month, day=day, hour=hour)

                # Air temperature (scaled by 10, °C)
                temp_raw = line[87:92].strip()
                temp_c = int(temp_raw) / 10.0 if temp_raw not in ("+9999", "9999", "") else np.nan

                # Dew point (scaled by 10, °C)
                dew_raw = line[93:98].strip()
                dew_c = int(dew_raw) / 10.0 if dew_raw not in ("+9999", "9999", "") else np.nan

                # Wind speed (scaled by 10, m/s)
                wind_raw = line[65:69].strip()
                wind_ms = int(wind_raw) / 10.0 if wind_raw not in ("9999", "") else np.nan

                records.append({
                    "datetime": dt,
                    "air_temp_c": temp_c,
                    "dew_point_c": dew_c,
                    "wind_speed_ms": wind_ms,
                })
            except (ValueError, IndexError):
                continue

    df = pd.DataFrame(records)
    if df.empty:
        return df

    # Relative humidity via August-Roche-Magnus approximation
    df["rh_pct"] = 100 * np.exp(
        17.625 * df["dew_point_c"] / (243.04 + df["dew_point_c"])
    ) / np.exp(
        17.625 * df["air_temp_c"] / (243.04 + df["air_temp_c"])
    )
    return df


# ---------------------------------------------------------------------------
# Daily county aggregation
# ---------------------------------------------------------------------------
def _heat_index(t_c: pd.Series, rh: pd.Series) -> pd.Series:
    """
    Rothfusz regression for heat index.
    Returns NaN when temperature < 27 °C (HI not meaningful below that).
    """
    t_f = t_c * 9 / 5 + 32
    hi = (
        -42.379
        + 2.04901523 * t_f
        + 10.14333127 * rh
        - 0.22475541 * t_f * rh
        - 0.00683783 * t_f**2
        - 0.05481717 * rh**2
        + 0.00122874 * t_f**2 * rh
        + 0.00085282 * t_f * rh**2
        - 0.00000199 * t_f**2 * rh**2
    )
    hi_c = (hi - 32) * 5 / 9
    return hi_c.where(t_c >= 27)


def aggregate_station_to_daily(hourly_df: pd.DataFrame) -> pd.DataFrame:
    """Reduce hourly station observations to daily summary statistics."""
    df = hourly_df.copy()
    df["date"] = df["datetime"].dt.date
    df["heat_index_c"] = _heat_index(df["air_temp_c"], df["rh_pct"])

    daily = (
        df.groupby("date")
        .agg(
            tmax=("air_temp_c",    "max"),
            tmin=("air_temp_c",    "min"),
            heat_index_max=("heat_index_c", "max"),
            wind_speed_max=("wind_speed_ms","max"),
            rh_min=("rh_pct",     "min"),
        )
        .reset_index()
    )
    daily["date"] = pd.to_datetime(daily["date"])
    return daily


def aggregate_county_daily(
    station_daily_frames: list[pd.DataFrame],
) -> pd.DataFrame:
    """
    Average daily metrics across all stations assigned to a county.

    Parameters
    ----------
    station_daily_frames : list of DataFrames, each with 'date' + metric columns

    Returns a single DataFrame with one row per date.
    """
    if not station_daily_frames:
        return pd.DataFrame()
    combined = pd.concat(station_daily_frames, ignore_index=True)
    county_daily = combined.groupby("date").mean(numeric_only=True).reset_index()
    return county_daily


def build_weather_panel(
    region_fips: list[str],
    county_gdf,           # geopandas.GeoDataFrame  (must have 'fips' and 'geometry')
    cache_dir: Path,
    year_range: tuple[int, int],
) -> pd.DataFrame:
    """
    Build a county × day weather panel for the given region.

    Steps:
    1. Load ISD station history and find stations inside each county.
    2. For each station × year, download from S3 and parse.
    3. Aggregate to county-day level.

    Returns a DataFrame indexed by (fips, date).
    """
    station_history = load_station_history(cache_dir)

    # Broad bounding box from the county GDF
    bounds = county_gdf.total_bounds   # minx, miny, maxx, maxy
    stations = filter_stations_by_bbox(
        station_history,
        lat_min=bounds[1], lat_max=bounds[3],
        lon_min=bounds[0], lon_max=bounds[2],
    )
    stations = assign_stations_to_counties(stations, county_gdf)
    stations = stations[stations["fips"].isin(set(region_fips))].copy()
    log.info("Found %d ISD stations in region", len(stations))

    panel_rows = []
    for _, row in stations.iterrows():
        usaf, wban, fips = str(row.get("usaf", "999999")), str(row.get("wban", "99999")), row["fips"]
        for year in range(year_range[0], year_range[1] + 1):
            path = download_station_year(usaf, wban, year, cache_dir)
            if path is None:
                continue
            hourly = parse_isd_gz(path)
            if hourly.empty:
                continue
            hourly = hourly[
                hourly["datetime"].dt.year == year
            ]
            daily = aggregate_station_to_daily(hourly)
            daily["fips"] = fips
            panel_rows.append(daily)

    if not panel_rows:
        raise RuntimeError("No ISD data loaded — check station list and cache directory.")

    panel = pd.concat(panel_rows, ignore_index=True)
    # Average across multiple stations per county-day
    panel = (
        panel.groupby(["fips", "date"])
        .mean(numeric_only=True)
        .reset_index()
        .set_index(["fips", "date"])
    )
    return panel
