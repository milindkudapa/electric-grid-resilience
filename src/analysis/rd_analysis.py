"""
Regression Discontinuity (RD) analysis for grid-stress alert thresholds.

Design:
    Running variable : daily maximum temperature (tmax, °C)
    Threshold        : ERCOT Conservation Appeal (~36 °C) or CAISO Flex Alert (~38 °C)
    Outcome          : customer-hours of outage (total_customer_hours)

The RD identifies the causal effect of crossing the emergency alert threshold
on outage severity, controlling for the smooth temperature-outage relationship.

Estimation approach:
    - Local linear regression on each side of the cutoff
    - Triangular kernel weighting
    - Optimal bandwidth via Imbens-Kalyanaraman (IK) rule-of-thumb
      (manual implementation — avoids R dependency)
    - Confidence intervals via HC3 robust SEs

Main entry point:
    run_rd(df, cutoff, running_var, outcome) -> RDResult
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class RDResult:
    """Container for RD estimation output."""
    cutoff: float
    bandwidth: float
    n_left: int
    n_right: int
    tau: float           # RD estimate (difference at threshold)
    se: float            # robust standard error
    t_stat: float
    p_value: float
    ci_lower: float
    ci_upper: float
    running_var: str
    outcome: str

    def summary(self) -> str:
        return (
            f"RD Estimate (outcome={self.outcome}, running={self.running_var})\n"
            f"  Cutoff:    {self.cutoff:.1f} °C\n"
            f"  Bandwidth: {self.bandwidth:.2f} °C\n"
            f"  N (left):  {self.n_left}\n"
            f"  N (right): {self.n_right}\n"
            f"  τ:         {self.tau:.4f}  (SE={self.se:.4f})\n"
            f"  t-stat:    {self.t_stat:.3f}\n"
            f"  p-value:   {self.p_value:.4f}\n"
            f"  95% CI:    [{self.ci_lower:.4f}, {self.ci_upper:.4f}]\n"
        )


# ---------------------------------------------------------------------------
# Bandwidth selection: IK rule-of-thumb (simplified)
# ---------------------------------------------------------------------------
def imbens_kalyanaraman_bandwidth(
    x: np.ndarray,
    y: np.ndarray,
    c: float,
    kernel: str = "triangular",
) -> float:
    """
    Simplified Imbens–Kalyanaraman (2012) MSE-optimal bandwidth selector.

    Uses a pilot bandwidth of 1.84 * std(x) * n^(-1/5) and then computes
    the regularised IK bandwidth from local variance and density estimates.

    Reference: Imbens & Kalyanaraman (2012), Review of Economic Studies.
    """
    n = len(x)
    if n < 20:
        return 1.84 * np.std(x) * n ** (-1 / 5)

    x_c = x - c
    left  = x_c[x_c <  0]
    right = x_c[x_c >= 0]

    pilot_h = 1.84 * np.std(x) * n ** (-0.2)

    # Variance estimates near the cutoff
    def _local_var(xc_side: np.ndarray, yc: np.ndarray) -> float:
        mask = np.abs(xc_side) < pilot_h
        if mask.sum() < 3:
            return np.var(yc) + 1e-6
        return np.var(yc[mask]) + 1e-6

    y_c = y - np.median(y)
    var_left  = _local_var(x_c[x_c < 0],  y_c[x_c < 0])
    var_right = _local_var(x_c[x_c >= 0], y_c[x_c >= 0])

    # Density estimate at cutoff
    density = (
        ((np.abs(left)  < pilot_h).sum() / (2 * pilot_h * len(left)  + 1e-9)) +
        ((np.abs(right) < pilot_h).sum() / (2 * pilot_h * len(right) + 1e-9))
    ) / 2.0

    sigma2 = (var_left + var_right) / 2.0
    regularisation = (var_left + var_right) * (np.log(n) ** 2) / n

    h_ik = (sigma2 / (density * n * regularisation + 1e-9)) ** 0.2
    # Clamp to a reasonable range
    h_ik = np.clip(h_ik, 0.5, 10.0)
    return float(h_ik)


# ---------------------------------------------------------------------------
# Kernel weight
# ---------------------------------------------------------------------------
def _kernel_weights(xc: np.ndarray, h: float, kernel: str = "triangular") -> np.ndarray:
    u = np.abs(xc) / h
    if kernel == "triangular":
        return np.maximum(1 - u, 0)
    if kernel == "uniform":
        return (u <= 1).astype(float)
    raise ValueError(f"Unknown kernel: {kernel}")


# ---------------------------------------------------------------------------
# Local linear regression on one side of the cutoff
# ---------------------------------------------------------------------------
def _local_linear(
    x: np.ndarray,
    y: np.ndarray,
    w: np.ndarray,
) -> tuple[float, float, float]:
    """
    Weighted local linear regression: y ~ a + b*x.

    Returns (intercept, slope, residual_variance).
    """
    W    = np.diag(w)
    X_mat = np.column_stack([np.ones(len(x)), x])
    XtW  = X_mat.T @ W
    XtWX = XtW @ X_mat
    XtWy = XtW @ y

    try:
        beta = np.linalg.solve(XtWX, XtWy)
    except np.linalg.LinAlgError:
        return np.nan, np.nan, np.nan

    resid = y - X_mat @ beta
    # HC3-like residual variance
    hat = X_mat @ np.linalg.pinv(XtWX) @ XtW
    h_ii = np.diag(hat).clip(0, 0.99)
    sigma2 = np.mean(w * (resid / (1 - h_ii)) ** 2)
    return float(beta[0]), float(beta[1]), float(sigma2)


# ---------------------------------------------------------------------------
# Main RD estimator
# ---------------------------------------------------------------------------
def run_rd(
    df: pd.DataFrame,
    cutoff: float,
    running_var: str = "tmax",
    outcome: str = "total_customer_hours",
    bandwidth: float | None = None,
    kernel: str = "triangular",
) -> RDResult:
    """
    Estimate the RD treatment effect at `cutoff` on the `outcome` variable.

    Parameters
    ----------
    df          : county × day panel (must contain running_var and outcome columns)
    cutoff      : temperature threshold (°C)
    running_var : column for the running variable
    outcome     : column for the outcome variable
    bandwidth   : half-window around cutoff; if None, uses IK selector
    kernel      : 'triangular' (default) or 'uniform'

    Returns
    -------
    RDResult dataclass
    """
    from scipy import stats

    df_clean = df[[running_var, outcome]].dropna()
    x_all = df_clean[running_var].values
    y_all = df_clean[outcome].values
    xc    = x_all - cutoff

    if bandwidth is None:
        bandwidth = imbens_kalyanaraman_bandwidth(x_all, y_all, cutoff, kernel)

    mask = np.abs(xc) <= bandwidth
    xc_w = xc[mask]
    y_w  = y_all[mask]

    left_mask  = xc_w <  0
    right_mask = xc_w >= 0
    n_left  = int(left_mask.sum())
    n_right = int(right_mask.sum())

    if n_left < 5 or n_right < 5:
        raise ValueError(
            f"Insufficient observations within bandwidth ±{bandwidth:.2f}: "
            f"left={n_left}, right={n_right}. Try increasing the bandwidth."
        )

    w_all  = _kernel_weights(xc_w, bandwidth, kernel)
    w_left  = w_all[left_mask]
    w_right = w_all[right_mask]

    a_left,  _, var_left  = _local_linear(xc_w[left_mask],  y_w[left_mask],  w_left)
    a_right, _, var_right = _local_linear(xc_w[right_mask], y_w[right_mask], w_right)

    tau  = a_right - a_left
    se   = np.sqrt(var_left / n_left + var_right / n_right)
    t_s  = tau / se if se > 0 else np.nan
    df_t = n_left + n_right - 4   # two local regressions, each with 2 params
    pval = 2 * stats.t.sf(np.abs(t_s), df=df_t) if not np.isnan(t_s) else np.nan
    t_crit = stats.t.ppf(0.975, df=df_t)

    return RDResult(
        cutoff=cutoff,
        bandwidth=bandwidth,
        n_left=n_left,
        n_right=n_right,
        tau=tau,
        se=se,
        t_stat=t_s,
        p_value=pval,
        ci_lower=tau - t_crit * se,
        ci_upper=tau + t_crit * se,
        running_var=running_var,
        outcome=outcome,
    )


# ---------------------------------------------------------------------------
# Sensitivity: vary bandwidth
# ---------------------------------------------------------------------------
def rd_bandwidth_sensitivity(
    df: pd.DataFrame,
    cutoff: float,
    bandwidths: list[float] | None = None,
    running_var: str = "tmax",
    outcome: str = "total_customer_hours",
) -> pd.DataFrame:
    """
    Run RD at multiple bandwidths and return a comparison DataFrame.
    Useful for robustness checks in the paper.
    """
    if bandwidths is None:
        bandwidths = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]

    rows = []
    for h in bandwidths:
        try:
            res = run_rd(df, cutoff, running_var, outcome, bandwidth=h)
            rows.append({
                "bandwidth": h,
                "tau":       res.tau,
                "se":        res.se,
                "p_value":   res.p_value,
                "ci_lower":  res.ci_lower,
                "ci_upper":  res.ci_upper,
                "n_left":    res.n_left,
                "n_right":   res.n_right,
            })
        except ValueError:
            pass

    return pd.DataFrame(rows)
