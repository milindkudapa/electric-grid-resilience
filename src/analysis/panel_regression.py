"""
Panel regression wrappers for the grid resilience analysis.

Specifications:
1. PanelOLS with county FE + month-of-year FE (NOT day FE — day FE absorbs
   the spatial weather signal because heatwaves hit all counties at once).
   Outcome defaults to log1p(total_customer_hours) since the raw outcome is
   heavily zero-inflated and right-skewed.

2. Conditional logit (FE absorbed) for binary outage_event_flag, using
   linearmodels.PanelOLS as a linear probability model with county FE
   when full conditional logit is infeasible (250k+ rows).

3. Mutually exclusive category dummies (normal | heatwave_only | heat_wind |
   heat_precip | triple) avoid the multicollinearity from nested flags.

All regressions cluster standard errors at the county level.
"""

from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

CATEGORY_LEVELS = ["normal", "heatwave_only", "heat_wind", "heat_precip", "triple"]


def _prep_panel(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if not isinstance(df.index, pd.MultiIndex):
        if "fips" in df.columns and "date" in df.columns:
            df = df.set_index(["fips", "date"])
        else:
            raise ValueError("DataFrame needs (fips, date) MultiIndex or columns.")
    df.index.names = ["fips", "date"]
    return df


def _category_dummies(df: pd.DataFrame, base: str = "normal") -> tuple[pd.DataFrame, list[str]]:
    """Build mutually exclusive category dummies from `weather_category` column.
    Drop the base category to avoid collinearity. Returns (df, dummy_col_names)."""
    if "weather_category" not in df.columns:
        raise KeyError("weather_category column missing — run add_weather_flags first.")
    cats_present = [c for c in CATEGORY_LEVELS if c in df["weather_category"].unique()]
    if base in cats_present:
        cats_present.remove(base)
    dummies = pd.DataFrame(index=df.index)
    for c in cats_present:
        dummies[f"cat_{c}"] = (df["weather_category"] == c).astype(int)
    return pd.concat([df, dummies], axis=1), list(dummies.columns)


def _add_month_dummies(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Append month-of-year dummies (drop January as base)."""
    df = df.copy()
    if isinstance(df.index, pd.MultiIndex):
        dates = df.index.get_level_values("date")
    else:
        dates = pd.to_datetime(df["date"])
    months = pd.Series(dates.month, index=df.index)
    cols = []
    for m in range(2, 13):
        col = f"month_{m}"
        df[col] = (months == m).astype(int)
        cols.append(col)
    return df, cols


# ---------------------------------------------------------------------------
# 1. Fixed-effects panel OLS (continuous outcome, log1p transform)
# ---------------------------------------------------------------------------
def run_panel_ols(
    df: pd.DataFrame,
    outcome: str = "total_customer_hours",
    weather_vars: list[str] | None = None,
    use_categories: bool = True,
    log_outcome: bool = True,
    controls: list[str] | None = None,
    entity_effects: bool = True,
    time_effects: bool = False,
    add_month_fe: bool = True,
) -> Any:
    """Two-way FE PanelOLS with county FE + month-of-year FE by default.

    Day-level time FE (`time_effects=True`) absorbs common weather shocks across
    all counties on the same day, leaving only spatial residual variation. This
    is rarely what we want for a regional weather-on-outage model — keep False.

    use_categories=True replaces nested flags with mutually exclusive
    category dummies (normal/heatwave_only/heat_wind/heat_precip/triple).
    log_outcome=True applies log(1 + outcome) to handle zero-inflation.
    """
    try:
        from linearmodels.panel import PanelOLS
    except ImportError as e:
        raise ImportError("linearmodels required: pip install linearmodels") from e

    df = _prep_panel(df)

    if use_categories:
        df, regressors = _category_dummies(df)
    else:
        if weather_vars is None:
            weather_vars = [
                c for c in ["heatwave_day", "compound_heat_wind", "compound_triple"]
                if c in df.columns
            ]
        regressors = list(weather_vars)

    if add_month_fe and not time_effects:
        df, month_cols = _add_month_dummies(df)
        regressors = regressors + month_cols

    regressors = regressors + (controls or [])

    cols_needed = [outcome] + regressors
    df_model = df[cols_needed].dropna()
    if len(df_model) == 0:
        raise ValueError("No rows after dropping NaN.")

    y_raw = df_model[outcome].astype(float)
    if log_outcome:
        endog = np.log1p(y_raw.clip(lower=0)).to_frame(name=f"log1p_{outcome}")
    else:
        endog = y_raw.to_frame(name=outcome)

    exog = df_model[regressors].astype(float)

    model = PanelOLS(
        endog,
        exog,
        entity_effects=entity_effects,
        time_effects=time_effects,
        drop_absorbed=True,
    )
    return model.fit(cov_type="clustered", cluster_entity=True)


# ---------------------------------------------------------------------------
# 2. Conditional logit / linear probability model with county FE
# ---------------------------------------------------------------------------
def run_logit(
    df: pd.DataFrame,
    outcome: str = "outage_event_flag",
    weather_vars: list[str] | None = None,
    use_categories: bool = True,
    controls: list[str] | None = None,
    method: str = "lpm",
) -> Any:
    """Binary outcome regression with county FE.

    method='lpm': Linear Probability Model via PanelOLS with county FE +
        clustered SE. Fast, handles 250k+ rows, gives marginal effects in
        probability units. Recommended for this dataset.

    method='clogit': Conditional logit via statsmodels (slow with many
        counties, may not converge).

    method='pooled_logit': Pooled logit ignoring county structure.
        Provided only for comparison — biased.
    """
    df = _prep_panel(df)

    if use_categories:
        df, regressors = _category_dummies(df)
    else:
        if weather_vars is None:
            weather_vars = [
                c for c in ["heatwave_day", "compound_heat_wind", "compound_triple"]
                if c in df.columns
            ]
        regressors = list(weather_vars)
    regressors = regressors + (controls or [])

    df_model = df[[outcome] + regressors].dropna()

    if method == "lpm":
        from linearmodels.panel import PanelOLS
        endog = df_model[[outcome]].astype(float)
        exog = df_model[regressors].astype(float)
        model = PanelOLS(endog, exog, entity_effects=True, drop_absorbed=True)
        return model.fit(cov_type="clustered", cluster_entity=True)

    if method == "pooled_logit":
        import statsmodels.api as sm
        df_flat = df_model.reset_index()
        X = sm.add_constant(df_flat[regressors].astype(float))
        y = df_flat[outcome].astype(int)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return sm.Logit(y, X).fit(maxiter=200, disp=False)

    if method == "clogit":
        # Drop counties with no within-variation in outcome (clogit requires it).
        df_flat = df_model.reset_index()
        var_per_fips = df_flat.groupby("fips")[outcome].nunique()
        keep_fips = var_per_fips[var_per_fips > 1].index
        df_flat = df_flat[df_flat["fips"].isin(keep_fips)]
        from statsmodels.discrete.conditional_models import ConditionalLogit
        X = df_flat[regressors].astype(float)
        y = df_flat[outcome].astype(int)
        groups = df_flat["fips"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return ConditionalLogit(y, X, groups=groups).fit(maxiter=200, disp=False)

    raise ValueError(f"Unknown method: {method}")


# ---------------------------------------------------------------------------
# 3. Interaction model
# ---------------------------------------------------------------------------
def run_interaction_model(
    df: pd.DataFrame,
    outcome: str = "total_customer_hours",
    base_var: str = "heatwave_day",
    moderator: str = "wind_speed_max",
    log_outcome: bool = True,
) -> Any:
    df = _prep_panel(df).copy().reset_index()
    interaction_col = f"{base_var}_x_{moderator}"
    df[interaction_col] = df[base_var] * df[moderator]
    return run_panel_ols(
        df.set_index(["fips", "date"]),
        outcome=outcome,
        weather_vars=[base_var, moderator, interaction_col],
        use_categories=False,
        log_outcome=log_outcome,
    )


# ---------------------------------------------------------------------------
# 4. Result helpers
# ---------------------------------------------------------------------------
def summarise_results(result) -> pd.DataFrame:
    try:
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
        return pd.DataFrame({
            "coef":     result.params,
            "std_err":  result.bse,
            "t_stat":   result.tvalues,
            "p_value":  result.pvalues,
            "ci_lower": result.conf_int().iloc[:, 0],
            "ci_upper": result.conf_int().iloc[:, 1],
        })
