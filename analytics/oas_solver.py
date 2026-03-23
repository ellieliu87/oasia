"""
OAS (Option-Adjusted Spread) solver and bond analytics.

Implements:
- price_from_oas: price a bond given OAS by discounting cash flows on each path
- solve_oas: find OAS that matches market price using Brent's method
- compute_z_spread: Z-spread (no path dependency)
- compute_analytics: full BondAnalytics computation
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np
from scipy.optimize import brentq

from analytics.rate_paths import RatePaths, TermStructure, generate_rate_paths
from data.intex_client import CashFlows


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OASResult:
    oas_bps: float
    model_price: float
    iterations: int
    converged: bool


@dataclass
class BondAnalytics:
    pool_id: str
    oas: float           # bps
    z_spread: float      # bps
    oad: float           # years
    mod_duration: float  # years
    convexity: float
    yield_: float        # % annualized
    model_price: float   # % par
    market_price: float  # % par
    model_cpr: float     # % annualized (mean across paths)
    market_cpr_1m: float # % annualized, 1-month realized


# ---------------------------------------------------------------------------
# Core pricing function
# ---------------------------------------------------------------------------

def price_from_oas(
    cash_flows: CashFlows,
    rate_paths: RatePaths,
    oas_bps: float,
) -> float:
    """
    Price an MBS given OAS by discounting cash flows on each rate path.

    The OAS is added to the SHORT RATE on each path (not a parallel yield curve shift).
    Price = mean over paths of [sum(CF_t * df(t, oas)) for t in periods]

    Parameters
    ----------
    cash_flows : CashFlows
        Cash flows of shape (n_paths, n_periods).
    rate_paths : RatePaths
        Short rates and discount factors of shape (n_paths, n_periods).
    oas_bps : float
        OAS in basis points.

    Returns
    -------
    float
        Price as % of par (face amount = sum of all principal flows).
    """
    oas = oas_bps / 10_000.0
    dt = rate_paths.dt

    # Compute discount factors with OAS added to short rate
    # df(i, t) = exp(-sum_{s=0}^{t} (r(i,s) + oas) * dt)
    # = exp(-sum(r*dt) - oas*dt*t)
    # = discount_factors[i,t] * exp(-oas * dt * (t+1))
    n_paths, n_periods = rate_paths.short_rates.shape
    period_indices = np.arange(1, n_periods + 1)  # 1-indexed periods
    oas_discount = np.exp(-oas * dt * period_indices)  # shape (n_periods,)

    # Modified discount factors
    mod_df = rate_paths.discount_factors * oas_discount[np.newaxis, :]  # (n_paths, n_periods)

    # Total cash flows per period per path
    total_cf = cash_flows.total_cash_flow  # (n_paths, n_periods)

    # PV on each path
    pv_per_path = np.sum(total_cf * mod_df, axis=1)  # (n_paths,)

    # Average across paths
    mean_pv = np.mean(pv_per_path)

    # Express as % of face amount (initial balance)
    face = np.sum(cash_flows.total_principal[0, :])
    if face <= 0:
        # Try to infer from balance
        face = cash_flows.balance[0, 0]
    if face <= 0:
        return 0.0

    return (mean_pv / face) * 100.0


def solve_oas(
    cash_flows: CashFlows,
    rate_paths: RatePaths,
    market_price: float,
    tolerance_bps: float = 0.01,
) -> OASResult:
    """
    Find the OAS that equates the model price to the market price.

    Uses Brent's method with bracket [-200, 2000] bps.

    Parameters
    ----------
    cash_flows : CashFlows
    rate_paths : RatePaths
    market_price : float
        Market price as % of par.
    tolerance_bps : float
        Convergence tolerance in bps.

    Returns
    -------
    OASResult
    """
    iterations = [0]

    def objective(oas_bps: float) -> float:
        iterations[0] += 1
        model_p = price_from_oas(cash_flows, rate_paths, oas_bps)
        return model_p - market_price

    try:
        oas_lo, oas_hi = -200.0, 2000.0

        # Verify bracket
        f_lo = objective(oas_lo)
        f_hi = objective(oas_hi)

        # If no sign change, try wider bracket
        if f_lo * f_hi > 0:
            oas_lo, oas_hi = -500.0, 5000.0
            f_lo = objective(oas_lo)
            f_hi = objective(oas_hi)

        if f_lo * f_hi > 0:
            # Still no bracket — return best guess
            # Higher price → lower OAS, use -100 as fallback
            oas_guess = -100.0 if f_lo < 0 else 500.0
            return OASResult(
                oas_bps=oas_guess,
                model_price=price_from_oas(cash_flows, rate_paths, oas_guess),
                iterations=iterations[0],
                converged=False,
            )

        oas_bps = brentq(
            objective,
            oas_lo,
            oas_hi,
            xtol=tolerance_bps,
            rtol=1e-8,
            maxiter=100,
            full_output=False,
        )
        model_price = price_from_oas(cash_flows, rate_paths, oas_bps)
        return OASResult(
            oas_bps=float(oas_bps),
            model_price=float(model_price),
            iterations=iterations[0],
            converged=True,
        )

    except Exception as e:
        warnings.warn(f"OAS solver failed: {e}")
        return OASResult(
            oas_bps=0.0,
            model_price=market_price,
            iterations=iterations[0],
            converged=False,
        )


# ---------------------------------------------------------------------------
# Z-spread
# ---------------------------------------------------------------------------

def compute_z_spread(
    cash_flows: CashFlows,
    curve: TermStructure,
    market_price: float,
) -> float:
    """
    Compute Z-spread: parallel spread to zero curve that matches market price.

    Unlike OAS, Z-spread discounts using the zero-coupon curve (no path dependency).
    Uses a single path's cash flows (mean across paths) for efficiency.

    Parameters
    ----------
    cash_flows : CashFlows
    curve : TermStructure
    market_price : float
        Market price as % of par.

    Returns
    -------
    float
        Z-spread in basis points.
    """
    dt = 1.0 / 12.0

    # Use mean cash flows across paths
    total_cf = cash_flows.total_cash_flow  # (n_paths, n_periods)
    mean_cf = np.mean(total_cf, axis=0)  # (n_periods,)
    n_periods = len(mean_cf)

    # Compute time grid
    times = np.arange(1, n_periods + 1) * dt  # months to years

    # Zero rates at each period
    zero_rates = np.array([curve.zero_rate(t) for t in times])

    # Face amount
    total_principal = cash_flows.total_principal
    face = np.mean(np.sum(total_principal, axis=1))
    if face <= 0:
        face = cash_flows.balance[0, 0]

    def objective(z_bps: float) -> float:
        z = z_bps / 10_000.0
        discount_factors = np.exp(-(zero_rates + z) * times)
        pv = np.sum(mean_cf * discount_factors)
        return (pv / face) * 100.0 - market_price

    try:
        f_lo = objective(-500.0)
        f_hi = objective(5000.0)
        if f_lo * f_hi > 0:
            return 0.0

        z_bps = brentq(objective, -500.0, 5000.0, xtol=0.01, maxiter=100)
        return float(z_bps)
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Modified duration and yield
# ---------------------------------------------------------------------------

def compute_yield(cash_flows: CashFlows, market_price: float) -> float:
    """
    Compute yield-to-maturity (IRR) of cash flows at market price.

    Uses mean cash flows across paths.

    Parameters
    ----------
    cash_flows : CashFlows
    market_price : float
        Market price as % of par.

    Returns
    -------
    float
        Annualized yield (decimal, e.g. 0.065 for 6.5%).
    """
    dt = 1.0 / 12.0
    total_cf = cash_flows.total_cash_flow
    mean_cf = np.mean(total_cf, axis=0)
    n_periods = len(mean_cf)
    times = np.arange(1, n_periods + 1) * dt

    total_principal = cash_flows.total_principal
    face = np.mean(np.sum(total_principal, axis=1))
    if face <= 0:
        face = cash_flows.balance[0, 0]

    target_pv = market_price / 100.0 * face

    def npv(annual_rate: float) -> float:
        monthly_rate = annual_rate / 12.0
        if monthly_rate <= -1.0:
            return np.inf
        discount = (1.0 + monthly_rate) ** (-np.arange(1, n_periods + 1))
        return np.sum(mean_cf * discount) - target_pv

    try:
        f_lo = npv(0.001)
        f_hi = npv(0.30)
        if f_lo * f_hi > 0:
            # Try different bracket
            f_lo = npv(-0.10)
            f_hi = npv(0.50)
            if f_lo * f_hi > 0:
                return 0.06  # fallback
        yield_rate = brentq(npv, -0.10, 0.50, xtol=1e-8, maxiter=200)
        return float(yield_rate)
    except Exception:
        return 0.06


def compute_mod_duration(cash_flows: CashFlows, yield_rate: float) -> float:
    """
    Compute modified duration (yield-based, no option adjustment).

    Parameters
    ----------
    cash_flows : CashFlows
    yield_rate : float
        Annual yield (decimal).

    Returns
    -------
    float
        Modified duration in years.
    """
    mean_cf = np.mean(cash_flows.total_cash_flow, axis=0)
    n_periods = len(mean_cf)
    times = np.arange(1, n_periods + 1) / 12.0  # in years

    monthly_rate = yield_rate / 12.0
    discount = (1.0 + monthly_rate) ** (-np.arange(1, n_periods + 1))

    pv_cf = mean_cf * discount
    total_pv = np.sum(pv_cf)
    if total_pv <= 0:
        return 0.0

    # Macaulay duration
    mac_duration = np.sum(pv_cf * times) / total_pv

    # Modified duration = Macaulay / (1 + y/12)
    mod_duration = mac_duration / (1.0 + monthly_rate)
    return float(mod_duration)


# ---------------------------------------------------------------------------
# Full analytics computation
# ---------------------------------------------------------------------------

def compute_analytics(
    pool_id: str,
    pool_chars,
    market_price: float,
    settlement_date: date,
    rate_paths: RatePaths,
    intex_client=None,
    prepay_model=None,
    market_cpr_1m: float = 0.0,
) -> BondAnalytics:
    """
    Compute full set of bond analytics for an MBS pool.

    Parameters
    ----------
    pool_id : str
    pool_chars : PoolCharacteristics
    market_price : float
        Market price as % of par.
    settlement_date : date
    rate_paths : RatePaths
        Base rate paths.
    intex_client : optional
    prepay_model : optional
    market_cpr_1m : float
        1-month realized CPR (% annualized).

    Returns
    -------
    BondAnalytics
    """
    from analytics.prepay import project_prepay_speeds, PrepayModel
    from analytics.cashflows import get_cash_flows

    if intex_client is None:
        from data.intex_client import get_intex_client
        intex_client = get_intex_client()

    if prepay_model is None:
        prepay_model = PrepayModel()

    # Project prepayment speeds
    cpr_vectors = project_prepay_speeds(pool_chars, rate_paths, model=prepay_model)
    model_cpr = float(np.mean(cpr_vectors)) * 100.0

    # Get cash flows
    cash_flows = get_cash_flows(
        pool_id=pool_id,
        cpr_vectors=cpr_vectors,
        settlement_date=settlement_date,
        face_amount=pool_chars.current_balance if pool_chars.current_balance > 0 else 1_000_000,
        intex_client=intex_client,
    )

    # Solve OAS
    oas_result = solve_oas(cash_flows, rate_paths, market_price)

    # Z-spread (use base SOFR-like curve from rate paths — approximate)
    # We'll need the curve — create a flat curve from the average rate path
    avg_rate = float(np.mean(rate_paths.short_rates))
    tenors_flat = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    rates_flat = np.full_like(tenors_flat, avg_rate)
    flat_curve = TermStructure(tenors=tenors_flat, rates=rates_flat)
    z_spread = compute_z_spread(cash_flows, flat_curve, market_price)

    # Yield
    yield_rate = compute_yield(cash_flows, market_price)

    # Modified duration
    mod_dur = compute_mod_duration(cash_flows, yield_rate)

    # OAD: bump rate paths by ±1bp, reprice
    # We reuse the passed rate paths with small modifications
    oad = _compute_oad(cash_flows, rate_paths, oas_result.oas_bps, market_price)

    # Convexity: bump ±100bp
    convexity = _compute_convexity(cash_flows, rate_paths, oas_result.oas_bps, market_price)

    return BondAnalytics(
        pool_id=pool_id,
        oas=round(oas_result.oas_bps, 2),
        z_spread=round(z_spread, 2),
        oad=round(oad, 3),
        mod_duration=round(mod_dur, 3),
        convexity=round(convexity, 4),
        yield_=round(yield_rate * 100.0, 4),
        model_price=round(oas_result.model_price, 4),
        market_price=round(market_price, 4),
        model_cpr=round(model_cpr, 2),
        market_cpr_1m=round(market_cpr_1m, 2),
    )


def _bump_discount_factors(
    rate_paths: RatePaths,
    bump_bps: float,
) -> RatePaths:
    """
    Return new RatePaths with short rates bumped by bump_bps.

    Rather than regenerating paths, we directly add the bump to all short rates
    and recompute discount factors. This is appropriate for OAD computation.
    """
    bump = bump_bps / 10_000.0
    new_short_rates = rate_paths.short_rates + bump
    dt = rate_paths.dt
    new_cumulative = np.cumsum(new_short_rates, axis=1) * dt
    new_df = np.exp(-new_cumulative)
    return RatePaths(
        short_rates=new_short_rates,
        discount_factors=new_df,
        dt=dt,
    )


def _compute_oad(
    cash_flows: CashFlows,
    rate_paths: RatePaths,
    oas_bps: float,
    base_price: float,
) -> float:
    """
    Compute OAD by bumping short rates ±1bp.

    OAD = -(P(+1bp) - P(-1bp)) / (2 * P * 0.0001)
    """
    rp_up = _bump_discount_factors(rate_paths, 1.0)
    rp_dn = _bump_discount_factors(rate_paths, -1.0)

    p_up = price_from_oas(cash_flows, rp_up, oas_bps)
    p_dn = price_from_oas(cash_flows, rp_dn, oas_bps)

    if base_price <= 0:
        return 0.0

    oad = -(p_up - p_dn) / (2.0 * base_price * 0.0001)
    return float(oad)


def _compute_convexity(
    cash_flows: CashFlows,
    rate_paths: RatePaths,
    oas_bps: float,
    base_price: float,
) -> float:
    """
    Compute convexity by bumping short rates ±100bp.

    Convexity = (P(+100bp) + P(-100bp) - 2*P) / (P * (0.01)^2)
    """
    rp_up = _bump_discount_factors(rate_paths, 100.0)
    rp_dn = _bump_discount_factors(rate_paths, -100.0)

    p_up = price_from_oas(cash_flows, rp_up, oas_bps)
    p_dn = price_from_oas(cash_flows, rp_dn, oas_bps)
    p_base = price_from_oas(cash_flows, rate_paths, oas_bps)

    if p_base <= 0:
        return 0.0

    convexity = (p_up + p_dn - 2.0 * p_base) / (p_base * (0.01) ** 2)
    return float(convexity)
