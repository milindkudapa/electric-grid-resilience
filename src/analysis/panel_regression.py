"""
Panel regression wrappers for the grid resilience analysis.

Implements:
1. Fixed-effects OLS panel regression (PanelOLS via linearmodels)
   OutageSeverity_ct = β1*HeatwaveDay + β2*CompoundHeatWind + β3*CompoundTriple
                     + γ*X_ct + α_c + δ_t + ε_ct

2. Logistic regression for binary outage event flag (via statsmodels).

3. Interaction model to test compound amplification factors.

All regressions cluster standard errors at the county (fips) level.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd


def _prep_panel(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure the DataFrame has a proper MultiIndex (entity, time) required
    by linearmodels PanelOLS.

    Accepts either:
    - A DataFrame with (fips, date) as columns, or
    - A DataFrame already indexed by (fips, date).
    """
    df = df.copy()
    if not isinstance(df.index, pd.MultiIndex):
        if "fips" in df.columns and "date" in df.columns:
            df = df.set_index(["fips", "date"])
        else:
            raise ValueError(
                "DataFrame must have a (fips, date) MultiIndex or 'fips' and 'date' columns."
            )
    df.index.names = ["fips", "date"]
    return df


# ---------------------------------------------------------------------------
# 1. Fixed-effects panel OLS (continuous outcome)
# ---------------------------------------------------------------------------
def run_panel_ols(
    df: pd.DataFrame,
    outcome: str = "total_customer_hours",
    weather_vars: list[str] | None = None,
    controls: list[str] | None = None,
    entity_effects: bool = True,
    time_effects: bool = True,
) -> Any:
    """
    Estimate a two-way fixed effects panel OLS model using linearmodels.

    Parameters
    ----------
    df           : merged outage + weather panel
    outcome      : dependent variable name
    weather_vars : main regressors (default: heatwave + compound flags)
    controls     : additional control columns (e.g. weekend indicator)
    entity_effects : include county fixed effects
    time_effects   : include day fixed effects

    Returns
    -------
    linearmodels PanelEffectsResults object (call .summary on it)
    """
    try:
        from linearmodels.panel import PanelOLS
    except ImportError as e:
        raise ImportError("linearmodels is required: pip install linearmodels") from e

    df = _prep_panel(df)

    if weather_vars is None:
        weather_vars = [
            c for c in ["heatwave_day", "compound_heat_wind", "compound_triple"]
            if c in df.columns
        ]

    regressors = weather_vars + (controls or [])

    # Drop rows with missing outcome or any regressor
    cols_needed = [outcome] + regressors
    df_model = df[cols_needed].dropna()

    if len(df_model) == 0:
        raise ValueError("No rows remain after dropping NaN values in model columns.")

    exog = df_model[regressors]
    endog = df_model[[outcome]]

    model = PanelOLS(
        endog,
        exog,
        entity_effects=entity_effects,
        time_effects=time_effects,
        drop_absorbed=True,
    )
    result = model.fit(cov_type="clustered", cluster_entity=True)
    return result


# ---------------------------------------------------------------------------
# 2. Logistic regression for binary outage event flag
# ---------------------------------------------------------------------------
def run_logit(
    df: pd.DataFrame,
    outcome: str = "outage_event_flag",
    weather_vars: list[str] | None = None,
    controls: list[str] | None = None,
    county_fe: bool = False,
) -> Any:
    """
    Logistic regression for a binary outage event.

    County fixed effects are included as dummy variables when county_fe=True
    (note: standard logit with many dummies is subject to incidental parameters
    bias — use only for exploratory analysis or with small county sets).

    Returns a statsmodels LogitResults object.
    """
    try:
        import statsmodels.api as sm
    except ImportError as e:
        raise ImportError("statsmodels is required: pip install statsmodels") from e

    df = df.copy()
    if isinstance(df.index, pd.MultiIndex):
        df = df.reset_index()

    if weather_vars is None:
        weather_vars = [
            c for c in ["heatwave_day", "compound_heat_wind", "compound_triple"]
            if c in df.columns
        ]

    regressors = weather_vars + (controls or [])

    if county_fe and "fips" in df.columns:
        dummies = pd.get_dummies(df["fips"], prefix="fe", drop_first=True)
        df = pd.concat([df, dummies], axis=1)
        regressors = regressors + list(dummies.columns)

    cols_needed = [outcome] + regressors
    df_model = df[cols_needed].dropna()

    X = sm.add_constant(df_model[regressors].astype(float))
    y = df_model[outcome].astype(int)

    model = sm.Logit(y, X)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = model.fit(maxiter=200, disp=False)
    return result


# ---------------------------------------------------------------------------
# 3. Interaction model — compound amplification
# ---------------------------------------------------------------------------
def run_interaction_model(
    df: pd.DataFrame,
    outcome: str = "total_customer_hours",
    base_var: str = "heatwave_day",
    moderator: str = "wind_speed_max",
) -> Any:
    """
    Test whether the effect of heatwave on outages is amplified by wind speed
    (i.e., compound amplification factor).

    Adds an interaction term base_var × moderator and runs two-way FE OLS.

    Returns PanelEffectsResults.
    """
    df = _prep_panel(df).copy().reset_index()

    interaction_col = f"{base_var}_x_{moderator}"
    df[interaction_col] = df[base_var] * df[moderator]

    return run_panel_ols(
        df.set_index(["fips", "date"]),
        outcome=outcome,
        weather_vars=[base_var, moderator, interaction_col],
    )


# ---------------------------------------------------------------------------
# 4. Result summary helpers
# ---------------------------------------------------------------------------
def summarise_results(result) -> pd.DataFrame:
    """
    Extract a clean coefficient table from a linearmodels or statsmodels result.

    Returns a DataFrame with columns: coef, std_err, t_stat, p_value, ci_lower, ci_upper
    """
    try:
        # linearmodels
        params  = result.params
        pvalues = result.pvalues
        std_err = result.std_errors
        ci      = result.conf_int()
        tstat   = result.tstats
        return pd.DataFrame({
            "coef":     params,
            "std_err":  std_err,
            "t_stat":   tstat,
            "p_value":  pvalues,
            "ci_lower": ci.iloc[:, 0],
            "ci_upper": ci.iloc[:, 1],
        })
    except AttributeError:
        # statsmodels
        return pd.DataFrame({
            "coef":     result.params,
            "std_err":  result.bse,
            "t_stat":   result.tvalues,
            "p_value":  result.pvalues,
            "ci_lower": result.conf_int().iloc[:, 0],
            "ci_upper": result.conf_int().iloc[:, 1],
        })
