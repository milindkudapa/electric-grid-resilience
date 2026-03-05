"""
Data download helper for the Electricity Grid Resilience project.

Run:  python scripts/download_data.py

The script prints the exact download URL and/or shell command for every
dataset required by the project.  For datasets that can be fetched
programmatically it performs the download directly; for datasets that
require a manual browser download it prints the URL and target path.

Usage:
    python scripts/download_data.py              # show all datasets
    python scripts/download_data.py --dataset eagle_i   # one dataset only
    python scripts/download_data.py --auto       # auto-download where possible
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import RAW

# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------
DATASETS = {
    # ── EAGLE-I ────────────────────────────────────────────────────────────
    "eagle_i": {
        "description": "EAGLE-I Power Outage Data 2014–2024 (ORNL)",
        "target_dir":  RAW["eagle_i"],
        "auto":        False,
        "notes": [
            "Annual CSV files — one per year.",
            "Download 2018–2024 from the ORNL Constellation portal:",
            "  2024: https://doi.ccs.ornl.gov/dataset/2be78213-ef9e-5433-b1b0-9762d051146c",
            "  2018-2022: https://www.osti.gov/dataexplorer/biblio/dataset/1975202",
            "  Legacy (pre-2023): https://smc-datachallenge.ornl.gov/eagle/",
            "File naming convention expected: eaglei_outages_<YEAR>.csv",
        ],
    },

    # ── NOAA ISD ────────────────────────────────────────────────────────────
    "noaa_isd": {
        "description": "NOAA Integrated Surface Database (ISD) — hourly weather",
        "target_dir":  RAW["noaa_isd"],
        "auto":        True,
        "notes": [
            "Station files are downloaded automatically from AWS S3 by noaa_isd.py",
            "  bucket: s3://noaa-isd-pds/data/<YYYY>/<USAF>-<WBAN>-<YYYY>.gz",
            "  (No AWS account required — public bucket, unsigned access)",
            "ISD station history is also auto-downloaded from:",
            "  https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv",
            "Run Notebook 03 to trigger the download.",
        ],
    },

    # ── TIGER/Line county shapefiles ────────────────────────────────────────
    "tiger": {
        "description": "Census TIGER/Line 2023 county shapefile (national)",
        "target_dir":  RAW["hifld"] / "tl_2023_us_county",
        "auto":        True,
        "url":         "https://www2.census.gov/geo/tiger/TIGER2023/COUNTY/tl_2023_us_county.zip",
        "notes": [
            "Unzip into data/raw/hifld/tl_2023_us_county/",
        ],
    },

    # ── LOCA2 ───────────────────────────────────────────────────────────────
    "loca2": {
        "description": "USGS CMIP6-LOCA2 county spatial summaries (27 GCMs, 1950–2100)",
        "target_dir":  RAW["loca2"],
        "auto":        False,
        "notes": [
            "Download from USGS ScienceBase:",
            "  https://data.usgs.gov/datacatalog/data/USGS:673d0719d34e6b795de6b593",
            "Choose 'Download' -> select the SSP2-4.5 and SSP5-8.5 county CSV archives.",
            "Extract and save CSVs to data/raw/loca2/.",
            "File naming: files should contain 'ssp245' or 'ssp585' in their name.",
        ],
    },

    # ── NOAA Storm Events ────────────────────────────────────────────────────
    "storm_events": {
        "description": "NOAA Storm Events Database — extreme weather events 2018–2024",
        "target_dir":  RAW["storm_events"],
        "auto":        True,
        "notes": [
            "Bulk CSV download from NCEI FTP:",
            "  https://www.ncei.noaa.gov/stormevents/ftp.jsp",
            "Download 'Details' files for each year (2018–2024).",
            "File pattern: StormEvents_details-ftp_v1.0_d<YEAR>_c*.csv.gz",
        ],
    },

    # ── EIA-860 ─────────────────────────────────────────────────────────────
    "eia860": {
        "description": "EIA Form 860 — annual electric generator inventory",
        "target_dir":  RAW["eia860"],
        "auto":        False,
        "notes": [
            "Download the most recent annual release from EIA:",
            "  https://www.eia.gov/electricity/data/eia860/",
            "Download the 'ZIP' file for the current year.",
            "Extract Excel workbooks into data/raw/eia860/.",
            "Key sheet: '3_1_Generator_Y<year>.xlsx'",
        ],
    },

    # ── HIFLD ───────────────────────────────────────────────────────────────
    "hifld_substations": {
        "description": "HIFLD Electric Substations (point data)",
        "target_dir":  RAW["hifld"],
        "auto":        False,
        "notes": [
            "Download shapefile from Data.gov:",
            "  https://catalog.data.gov/dataset/electric-substations",
            "Click 'Download' -> Shapefile.",
            "Extract to data/raw/hifld/Electric_Substations.shp (and related files).",
        ],
    },

    "hifld_transmission": {
        "description": "HIFLD US Electric Power Transmission Lines (line data)",
        "target_dir":  RAW["hifld"],
        "auto":        False,
        "notes": [
            "Download shapefile from FWS Open Data:",
            "  https://gis-fws.opendata.arcgis.com/datasets/fws::us-electric-power-transmission-lines/about",
            "Click 'Download' -> Shapefile.",
            "Extract to data/raw/hifld/Electric_Power_Transmission_Lines.shp.",
        ],
    },

    # ── EJScreen ────────────────────────────────────────────────────────────
    "ejscreen": {
        "description": "EPA EJScreen 2024 — census block group EJ indicators",
        "target_dir":  RAW["ejscreen"],
        "auto":        False,
        "notes": [
            "Option A (preferred): Download the CSV from EPA directly:",
            "  https://www.epa.gov/ejscreen/technical-information-and-data-downloads",
            "  Click '2024 EJSCREEN Data' -> CSV format.",
            "",
            "Option B: Download from Zenodo archive:",
            "  https://zenodo.org/records/14767363",
            "",
            "Save the CSV to data/raw/ejscreen/.",
            "Expected filename contains 'EJSCREEN' and has a 'ID' column (12-digit GEOID).",
        ],
    },

    # ── ERCOT historical load ────────────────────────────────────────────────
    "ercot_load": {
        "description": "ERCOT historical hourly load data",
        "target_dir":  RAW["eagle_i"].parent / "ercot_load",
        "auto":        False,
        "notes": [
            "Download from ERCOT:",
            "  https://www.ercot.com/gridinfo/load/load_hist",
            "Download the 'Hourly Load Data Archive' CSV for each year (2018–2024).",
            "Save to data/raw/ercot_load/.",
        ],
    },

    # ── CAL FIRE FHSZ ───────────────────────────────────────────────────────
    "cal_fire_fhsz": {
        "description": "CAL FIRE Fire Hazard Severity Zones (CAISO wildfire risk)",
        "target_dir":  RAW["hifld"] / "cal_fire_fhsz",
        "auto":        False,
        "notes": [
            "Download from CAL FIRE:",
            "  https://osfm.fire.ca.gov/divisions/wildfire-prevention-planning-research/",
            "  wildland-hazards-building-codes/fire-hazard-severity-zones-maps/",
            "Download the statewide FHSZ shapefile.",
            "Extract to data/raw/hifld/cal_fire_fhsz/.",
        ],
    },
}


# ---------------------------------------------------------------------------
# Auto-download helpers
# ---------------------------------------------------------------------------
def _download_url(url: str, dest: Path, chunk_size: int = 1 << 20) -> None:
    """Download a URL to dest with a progress bar."""
    import requests
    from tqdm import tqdm

    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, stream=True, timeout=120)
    r.raise_for_status()
    total = int(r.headers.get("content-length", 0))
    with open(dest, "wb") as f, tqdm(total=total, unit="B", unit_scale=True, desc=dest.name) as bar:
        for chunk in r.iter_content(chunk_size):
            f.write(chunk)
            bar.update(len(chunk))


def _unzip(zip_path: Path, dest_dir: Path) -> None:
    """Extract a zip archive."""
    import zipfile
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(dest_dir)
    print(f"  Extracted to {dest_dir}")


def download_tiger(dataset: dict) -> None:
    url     = dataset["url"]
    dest    = dataset["target_dir"]
    zip_path = dest.parent / "tl_2023_us_county.zip"
    if (dest / "tl_2023_us_county.shp").exists():
        print("  TIGER county shapefile already present.")
        return
    print(f"  Downloading from {url} …")
    _download_url(url, zip_path)
    _unzip(zip_path, dest)
    zip_path.unlink(missing_ok=True)


def download_storm_events(dataset: dict, years: range = range(2018, 2025)) -> None:
    """Download NOAA Storm Events 'details' CSVs for each year from NCEI FTP."""
    import gzip
    import shutil

    base_url = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"
    target_dir = dataset["target_dir"]
    target_dir.mkdir(parents=True, exist_ok=True)

    import requests
    # List available files
    resp = requests.get(base_url, timeout=30)
    resp.raise_for_status()

    for year in years:
        pattern = f"StormEvents_details-ftp_v1.0_d{year}_"
        matching = [line for line in resp.text.split('"') if pattern in line and line.endswith(".gz")]
        if not matching:
            print(f"  No Storm Events file found for {year}")
            continue
        filename = matching[-1]   # most recent version
        url      = base_url + filename
        gz_path  = target_dir / filename
        csv_path = target_dir / filename.replace(".gz", "")
        if csv_path.exists():
            print(f"  Storm Events {year}: already present.")
            continue
        print(f"  Downloading Storm Events {year}: {filename}")
        _download_url(url, gz_path)
        with gzip.open(gz_path, "rb") as f_in, open(csv_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
        gz_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Main print / execute routine
# ---------------------------------------------------------------------------
def print_dataset(name: str, info: dict) -> None:
    print(f"\n{'='*60}")
    print(f"Dataset: {name}")
    print(f"  Description : {info['description']}")
    print(f"  Target dir  : {info['target_dir']}")
    print(f"  Auto-download: {'Yes' if info.get('auto') else 'Manual (see notes)'}")
    for note in info.get("notes", []):
        print(f"  {note}")


def run_auto_downloads(selected: str | None = None) -> None:
    targets = {selected: DATASETS[selected]} if selected and selected in DATASETS else DATASETS

    for name, info in targets.items():
        if not info.get("auto"):
            continue
        print(f"\n[AUTO] {name}: {info['description']}")
        info["target_dir"].mkdir(parents=True, exist_ok=True)
        if name == "tiger":
            download_tiger(info)
        elif name == "storm_events":
            download_storm_events(info)
        else:
            print("  (Auto-download triggered at runtime by the relevant module.)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Grid Resilience project data download helper")
    parser.add_argument("--dataset", default=None, help="Name of a specific dataset to process")
    parser.add_argument("--auto",    action="store_true", help="Perform auto-downloads where possible")
    args = parser.parse_args()

    print("\nElectricity Grid Resilience — Data Download Guide")
    print("=" * 60)

    selected_datasets = (
        {args.dataset: DATASETS[args.dataset]}
        if args.dataset and args.dataset in DATASETS
        else DATASETS
    )

    for name, info in selected_datasets.items():
        print_dataset(name, info)

    if args.auto:
        print("\n\nStarting auto-downloads …")
        run_auto_downloads(args.dataset)
        print("\nAuto-downloads complete. Manual datasets still require browser downloads.")

    print(f"\n{'='*60}")
    print("After downloading, verify data by running the notebooks in order:")
    print("  01_study_area.ipynb  ->  02_outage_panel.ipynb  -> ...")
    print("All notebooks live in the notebooks/ directory.")


if __name__ == "__main__":
    main()
