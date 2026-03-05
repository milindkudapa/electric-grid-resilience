"""
Central configuration for the Electricity Grid Resilience project.
All other modules import from here so that thresholds and paths are
defined in one place.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Project root
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Data paths
# ---------------------------------------------------------------------------
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"

RAW = {
    "eagle_i":      DATA_RAW / "eagle_i",
    "noaa_isd":     DATA_RAW / "noaa_isd",
    "loca2":        DATA_RAW / "loca2",
    "eia860":       DATA_RAW / "eia860",
    "hifld":        DATA_RAW / "hifld",
    "storm_events": DATA_RAW / "storm_events",
    "ejscreen":     DATA_RAW / "ejscreen",
}

PROCESSED = {
    "outage_ercot":   DATA_PROCESSED / "outage_panel_ercot.csv",
    "outage_caiso":   DATA_PROCESSED / "outage_panel_caiso.csv",
    "weather_ercot":  DATA_PROCESSED / "weather_panel_ercot.csv",
    "weather_caiso":  DATA_PROCESSED / "weather_panel_caiso.csv",
    "loca2_ercot":    DATA_PROCESSED / "loca2_projections_ercot.csv",
    "loca2_caiso":    DATA_PROCESSED / "loca2_projections_caiso.csv",
    "merged_ercot":   DATA_PROCESSED / "merged_panel_ercot.csv",
    "merged_caiso":   DATA_PROCESSED / "merged_panel_caiso.csv",
    "ejscreen_county": DATA_PROCESSED / "ejscreen_county.csv",
    "asset_risk":     DATA_PROCESSED / "asset_risk_scores.csv",
}

# ---------------------------------------------------------------------------
# Temporal scope
# ---------------------------------------------------------------------------
HIST_START_YEAR = 2018
HIST_END_YEAR   = 2024

PROJ_PERIODS = {
    "baseline": (1991, 2020),
    "near":     (2030, 2059),
    "mid":      (2050, 2079),
}

SSP_SCENARIOS = ["ssp245", "ssp585"]

# ---------------------------------------------------------------------------
# Weather / outage thresholds  (Step 2–3)
# ---------------------------------------------------------------------------
# Outage event flag: fraction of customers without power
OUTAGE_FRACTION_THRESHOLD = 0.01   # 1 % of customers

# Heatwave definition (Nature 2025 EAGLE-I study)
HEATWAVE_TMAX_C = 32.2             # 90 °F

# Consecutive heatwave days needed to qualify as a heatwave event (WMO)
HEATWAVE_MIN_CONSECUTIVE_DAYS = 3

# Compound event thresholds
COMPOUND_WIND_MS  = 15.0           # m/s  — used in heat × wind flag
COMPOUND_PRECIP_MM = 25.0          # mm   — used in heat × precip flag
COMPOUND_TRIPLE_PRECIP_MM = 10.0   # mm   — lower precip bar for triple flag

# ---------------------------------------------------------------------------
# Regression discontinuity thresholds  (Step 4)
# ---------------------------------------------------------------------------
RD_THRESHOLD_ERCOT_C = 36.0        # ~97 °F  Conservation Appeal trigger
RD_THRESHOLD_CAISO_C = 38.0        # ~100 °F Flex Alert trigger

# ---------------------------------------------------------------------------
# Stress-test scenario  (Step 6)
# ---------------------------------------------------------------------------
STRESS_TEST_DURATION_DAYS = 7
STRESS_TEST_SSP            = "ssp585"
STRESS_TEST_YEAR           = 2050
# Heat derating factor for thermal plants (fractional efficiency loss per °C above design)
HEAT_DERATING_PER_C = 0.007        # 0.7 % per °C

# ---------------------------------------------------------------------------
# Asset vulnerability weights  (Step 7)
# ---------------------------------------------------------------------------
ASSET_RISK_WEIGHTS = {
    "heat_exposure_rank":    0.40,
    "wildfire_exposure_rank": 0.30,   # CAISO only; zero for ERCOT
    "asset_density_rank":    0.30,
}

# ---------------------------------------------------------------------------
# ERCOT: all 254 Texas county FIPS codes
# ---------------------------------------------------------------------------
ERCOT_FIPS = [
    "48001","48003","48005","48007","48009","48011","48013","48015","48017","48019",
    "48021","48023","48025","48027","48029","48031","48033","48035","48037","48039",
    "48041","48043","48045","48047","48049","48051","48053","48055","48057","48059",
    "48061","48063","48065","48067","48069","48071","48073","48075","48077","48079",
    "48081","48083","48085","48087","48089","48091","48093","48095","48097","48099",
    "48101","48103","48105","48107","48109","48111","48113","48115","48117","48119",
    "48121","48123","48125","48127","48129","48131","48133","48135","48137","48139",
    "48141","48143","48145","48147","48149","48151","48153","48155","48157","48159",
    "48161","48163","48165","48167","48169","48171","48173","48175","48177","48179",
    "48181","48183","48185","48187","48189","48191","48193","48195","48197","48199",
    "48201","48203","48205","48207","48209","48211","48213","48215","48217","48219",
    "48221","48223","48225","48227","48229","48231","48233","48235","48237","48239",
    "48241","48243","48245","48247","48249","48251","48253","48255","48257","48259",
    "48261","48263","48265","48267","48269","48271","48273","48275","48277","48279",
    "48281","48283","48285","48287","48289","48291","48293","48295","48297","48299",
    "48301","48303","48305","48307","48309","48311","48313","48315","48317","48319",
    "48321","48323","48325","48327","48329","48331","48333","48335","48337","48339",
    "48341","48343","48345","48347","48349","48351","48353","48355","48357","48359",
    "48361","48363","48365","48367","48369","48371","48373","48375","48377","48379",
    "48381","48383","48385","48387","48389","48391","48393","48395","48397","48399",
    "48401","48403","48405","48407","48409","48411","48413","48415","48417","48419",
    "48421","48423","48425","48427","48429","48431","48433","48435","48437","48439",
    "48441","48443","48445","48447","48449","48451","48453","48455","48457","48459",
    "48461","48463","48465","48467","48469","48471","48473","48475","48477","48479",
    "48481","48483","48485","48487","48489","48491","48493","48495","48497","48499",
    "48501","48503","48505","48507",
]

# ---------------------------------------------------------------------------
# CAISO: all 58 California county FIPS codes
# ---------------------------------------------------------------------------
CAISO_FIPS = [
    "06001","06003","06005","06007","06009","06011","06013","06015","06017","06019",
    "06021","06023","06025","06027","06029","06031","06033","06035","06037","06039",
    "06041","06043","06045","06047","06049","06051","06053","06055","06057","06059",
    "06061","06063","06065","06067","06069","06071","06073","06075","06077","06079",
    "06081","06083","06085","06087","06089","06091","06093","06095","06097","06099",
    "06101","06103","06105","06107","06109","06111","06113","06115",
]

# FIPS → human-readable name (subset of key counties for labelling maps)
COUNTY_LABELS = {
    # ERCOT
    "48113": "Dallas",
    "48201": "Harris (Houston)",
    "48029": "Bexar (San Antonio)",
    "48453": "Travis (Austin)",
    "48141": "El Paso",
    # CAISO
    "06037": "Los Angeles",
    "06073": "San Diego",
    "06059": "Orange",
    "06065": "Riverside",
    "06071": "San Bernardino",
    "06085": "Santa Clara",
    "06001": "Alameda",
}
