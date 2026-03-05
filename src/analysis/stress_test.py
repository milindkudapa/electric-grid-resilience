"""
2050-Era Worst-Week Stress Test (Step 6 of the methodology).

Model:
    1. Fit a temperature → peak load regression from historical ERCOT/CAISO data.
    2. Apply 2050 SSP5-8.5 TXx temperatures to project future peak demand.
    3. Apply heat derating to current generation capacity (EIA-860).
    4. Compute capacity margin = Available Supply − Peak Demand.
    5. Sensitivity analysis over temperature uncertainty and demand growth.

Main entry point:
    run_stress_test(region, loca2_df, eia860_df, historical_load_df) -> StressTestResult
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config.settings import (
    HEAT_DERATING_PER_C,
    STRESS_TEST_DURATION_DAYS,
    STRESS_TEST_SSP,
    STRESS_TEST_YEAR,
)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------
@dataclass
class GeneratorFleet:
    """Simplified representation of a BA region's generator fleet."""
    total_capacity_mw: float
    thermal_fraction:  float   # fraction of capacity that can be heat-derated
    design_temp_c:     float   # typical design operating temperature


@dataclass
class StressTestResult:
    region: str
    scenario_temp_c: float
    peak_demand_mw: float
    available_supply_mw: float
    capacity_margin_mw: float
    capacity_margin_pct: float
    customer_shortfall: float | None  # estimated customers affected if margin < 0
    sensitivity_table: pd.DataFrame  = field(default_factory=pd.DataFrame)

    def is_deficient(self) -> bool:
        return self.capacity_margin_mw < 0

    def summary(self) -> str:
        status = "DEFICIT" if self.is_deficient() else "Adequate"
        lines = [
            f"Stress Test — {self.region} ({STRESS_TEST_YEAR}, {STRESS_TEST_SSP})",
            f"  Scenario temp:      {self.scenario_temp_c:.1f} °C",
            f"  Peak demand:        {self.peak_demand_mw:,.0f} MW",
            f"  Available supply:   {self.available_supply_mw:,.0f} MW",
            f"  Capacity margin:    {self.capacity_margin_mw:,.0f} MW  ({self.capacity_margin_pct:.1f}%)",
            f"  Status:             {status}",
        ]
        if self.is_deficient() and self.customer_shortfall is not None:
            lines.append(f"  Est. customers affected: {self.customer_shortfall:,.0f}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 1: Temperature → load regression
# ---------------------------------------------------------------------------
def fit_load_model(
    load_df: pd.DataFrame,
    temp_col: str = "tmax",
    load_col: str = "peak_load_mw",
) -> dict:
    """
    Fit a quadratic OLS regression: Peak_Load = a + b*Tmax + c*Tmax^2

    Parameters
    ----------
    load_df   : DataFrame with columns for temperature and peak load.
                Must include 'month' and 'day_of_week' for controls.

    Returns a dict with fitted coefficients and R².
    """
    import statsmodels.api as sm

    df = load_df[[temp_col, load_col]].dropna().copy()
    df["tmax2"] = df[temp_col] ** 2

    # Add month and day-of-week dummies if available
    extra_cols = []
    if "month" in load_df.columns:
        month_dummies = pd.get_dummies(load_df["month"], prefix="m", drop_first=True)
        df = pd.concat([df, month_dummies.reindex(df.index)], axis=1)
        extra_cols += list(month_dummies.columns)
    if "day_of_week" in load_df.columns:
        dow_dummies = pd.get_dummies(load_df["day_of_week"], prefix="dow", drop_first=True)
        df = pd.concat([df, dow_dummies.reindex(df.index)], axis=1)
        extra_cols += list(dow_dummies.columns)

    df = df.dropna()
    X = sm.add_constant(df[[temp_col, "tmax2"] + extra_cols])
    y = df[load_col]

    result = sm.OLS(y, X).fit()
    return {
        "result":        result,
        "intercept":     result.params.get("const", 0),
        "coef_tmax":     result.params.get(temp_col, 0),
        "coef_tmax2":    result.params.get("tmax2", 0),
        "r2":            result.rsquared,
        "mean_load_mw":  y.mean(),
    }


def predict_peak_load(
    model: dict,
    scenario_temp_c: float,
    demand_growth_rate: float = 0.01,
    years_ahead: int = STRESS_TEST_YEAR - 2024,
) -> float:
    """
    Project peak load under a scenario temperature, accounting for demand growth.

    Parameters
    ----------
    model           : dict returned by fit_load_model
    scenario_temp_c : projected 2050 temperature (°C)
    demand_growth_rate : annual compound growth in baseline demand (default 1%/yr)
    years_ahead     : number of years from calibration to projection

    Returns
    -------
    Projected peak load in MW.
    """
    result = model["result"]
    base_load = (
        model["intercept"]
        + model["coef_tmax"]  * scenario_temp_c
        + model["coef_tmax2"] * scenario_temp_c ** 2
    )
    # Apply growth
    projected = base_load * (1 + demand_growth_rate) ** years_ahead
    return float(max(projected, 0))


# ---------------------------------------------------------------------------
# Step 2: Capacity derating
# ---------------------------------------------------------------------------
def compute_available_supply(
    fleet: GeneratorFleet,
    scenario_temp_c: float,
    forced_outage_rate: float = 0.05,
) -> float:
    """
    Estimate available generation after heat derating and forced outages.

    Thermal plants lose HEAT_DERATING_PER_C fractional efficiency per °C
    above design temperature.  Non-thermal (renewables, hydro) capacity
    is not derated by temperature but may face curtailment risk.

    Parameters
    ----------
    fleet              : GeneratorFleet description
    scenario_temp_c    : projected peak temperature (°C)
    forced_outage_rate : fraction of capacity unavailable for random maintenance

    Returns available capacity in MW.
    """
    thermal_cap    = fleet.total_capacity_mw * fleet.thermal_fraction
    non_thermal_cap = fleet.total_capacity_mw * (1 - fleet.thermal_fraction)

    excess_temp  = max(scenario_temp_c - fleet.design_temp_c, 0)
    derate_factor = 1 - HEAT_DERATING_PER_C * excess_temp
    derate_factor = max(derate_factor, 0)   # cannot go below 0

    thermal_available    = thermal_cap    * derate_factor
    non_thermal_available = non_thermal_cap  # conservative: no wind/solar derating here

    total_available = (thermal_available + non_thermal_available) * (1 - forced_outage_rate)
    return float(total_available)


# ---------------------------------------------------------------------------
# Step 3: Customer impact estimate
# ---------------------------------------------------------------------------
def estimate_customer_shortfall(
    shortfall_mw: float,
    total_customers: int,
    peak_load_mw: float,
) -> float:
    """
    Translate a generation shortfall (MW) into an estimated customer count.

    Uses a proportional load-shedding assumption:
        customers_affected = (shortfall_mw / peak_load_mw) * total_customers
    """
    if shortfall_mw <= 0:
        return 0.0
    fraction_shed = min(shortfall_mw / peak_load_mw, 1.0)
    return fraction_shed * total_customers


# ---------------------------------------------------------------------------
# Step 4: Sensitivity analysis
# ---------------------------------------------------------------------------
def run_sensitivity(
    fleet: GeneratorFleet,
    model: dict,
    base_temp_c: float,
    total_customers: int,
    temp_deltas: list[float] | None = None,
    growth_rates: list[float] | None = None,
) -> pd.DataFrame:
    """
    Grid search over temperature uncertainty and demand growth assumptions.

    Returns a DataFrame with one row per (temp_delta, growth_rate) combination.
    """
    if temp_deltas is None:
        temp_deltas = [-2.0, -1.0, 0.0, +1.0, +2.0]
    if growth_rates is None:
        growth_rates = [0.005, 0.010, 0.015, 0.020]

    rows = []
    for dt in temp_deltas:
        for gr in growth_rates:
            t = base_temp_c + dt
            demand = predict_peak_load(model, t, demand_growth_rate=gr)
            supply = compute_available_supply(fleet, t)
            margin = supply - demand
            rows.append({
                "temp_delta_c":      dt,
                "demand_growth_rate": gr,
                "scenario_temp_c":   t,
                "peak_demand_mw":    demand,
                "available_supply_mw": supply,
                "capacity_margin_mw": margin,
                "capacity_margin_pct": 100 * margin / demand if demand > 0 else np.nan,
                "customer_shortfall": estimate_customer_shortfall(
                    max(-margin, 0), total_customers, demand
                ) if margin < 0 else 0,
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def run_stress_test(
    region: str,
    scenario_temp_c: float,
    fleet: GeneratorFleet,
    load_model: dict,
    total_customers: int = 10_000_000,
    demand_growth_rate: float = 0.01,
) -> StressTestResult:
    """
    Run the full 2050 worst-week stress test.

    Parameters
    ----------
    region           : 'ERCOT' or 'CAISO'
    scenario_temp_c  : 99th-percentile TXx from LOCA2 SSP5-8.5 for 2050
    fleet            : GeneratorFleet object for the region
    load_model       : dict from fit_load_model()
    total_customers  : approximate number of electric customers in the region
    demand_growth_rate : annual demand growth

    Returns
    -------
    StressTestResult dataclass
    """
    peak_demand = predict_peak_load(
        load_model, scenario_temp_c, demand_growth_rate=demand_growth_rate
    )
    available   = compute_available_supply(fleet, scenario_temp_c)
    margin      = available - peak_demand

    shortfall = estimate_customer_shortfall(
        max(-margin, 0), total_customers, peak_demand
    ) if margin < 0 else None

    sensitivity = run_sensitivity(
        fleet, load_model, scenario_temp_c, total_customers
    )

    return StressTestResult(
        region=region,
        scenario_temp_c=scenario_temp_c,
        peak_demand_mw=peak_demand,
        available_supply_mw=available,
        capacity_margin_mw=margin,
        capacity_margin_pct=100 * margin / peak_demand if peak_demand > 0 else np.nan,
        customer_shortfall=shortfall,
        sensitivity_table=sensitivity,
    )


# ---------------------------------------------------------------------------
# Convenience: default fleet parameters from EIA data
# ---------------------------------------------------------------------------
FLEET_DEFAULTS = {
    "ERCOT": GeneratorFleet(
        total_capacity_mw=90_000,
        thermal_fraction=0.60,     # ~60% thermal (gas + coal)
        design_temp_c=35.0,
    ),
    "CAISO": GeneratorFleet(
        total_capacity_mw=80_000,
        thermal_fraction=0.35,     # lower thermal share due to high solar/wind
        design_temp_c=33.0,
    ),
}
