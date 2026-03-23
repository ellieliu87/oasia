"""
Book yield computation for MBS positions.

Book yield = IRR of cash flows at purchase (book) price.
Accounts for prepayment speeds under the base rate scenario.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np
from scipy.optimize import brentq

from analytics.rate_paths import RatePaths
from analytics.prepay import project_prepay_speeds, PrepayModel, PoolCharacteristics
from analytics.cashflows import get_cash_flows
from data.intex_client import CashFlows


def _irr_monthly(cash_flows_arr: np.ndarray, price_dollars: float) -> float:
    """
    Compute monthly IRR (annualized) from a cash flow array.

    Parameters
    ----------
    cash_flows_arr : np.ndarray
        Monthly cash flows (mean across paths).
    price_dollars : float
        Initial investment (negative cash flow at time 0).

    Returns
    -------
    float
        Annualized yield (decimal).
    """
    n = len(cash_flows_arr)

    def npv(monthly_rate: float) -> float:
        if monthly_rate <= -1.0:
            return -price_dollars
        periods = np.arange(1, n + 1)
        discount = (1.0 + monthly_rate) ** (-periods)
        return np.sum(cash_flows_arr * discount) - price_dollars

    try:
        # Try to find bracket
        r_lo, r_hi = -0.01, 0.05  # monthly rates: -12% to 60% annual
        f_lo, f_hi = npv(r_lo), npv(r_hi)

        if f_lo * f_hi > 0:
            # Try wider bracket
            r_lo, r_hi = -0.02, 0.10
            f_lo, f_hi = npv(r_lo), npv(r_hi)

        if f_lo * f_hi > 0:
            # Fallback: use WAC-based estimate
            return 0.06

        monthly_rate = brentq(npv, r_lo, r_hi, xtol=1e-10, maxiter=200)
        return float(monthly_rate * 12.0)
    except Exception:
        return 0.06


def compute_book_yield(
    pool_id: str,
    pool_chars: PoolCharacteristics,
    book_price: float,
    face_amount: float,
    settlement_date: date,
    rate_paths: RatePaths,
    intex_client=None,
    prepay_model=None,
) -> float:
    """
    Compute book yield (IRR at purchase price) for an MBS position.

    Parameters
    ----------
    pool_id : str
    pool_chars : PoolCharacteristics
    book_price : float
        Purchase price as % par.
    face_amount : float
        Face amount in dollars.
    settlement_date : date
    rate_paths : RatePaths
    intex_client : optional
    prepay_model : optional

    Returns
    -------
    float
        Annualized book yield (decimal).
    """
    if prepay_model is None:
        prepay_model = PrepayModel()

    if intex_client is None:
        from data.intex_client import get_intex_client
        intex_client = get_intex_client()

    # Project prepayment speeds
    cpr_vectors = project_prepay_speeds(pool_chars, rate_paths, model=prepay_model)

    # Get cash flows
    cash_flows = get_cash_flows(
        pool_id=pool_id,
        cpr_vectors=cpr_vectors,
        settlement_date=settlement_date,
        face_amount=face_amount,
        intex_client=intex_client,
    )

    # Use mean cash flows across paths
    mean_cf = np.mean(cash_flows.total_cash_flow, axis=0)

    # Investment at book price
    price_dollars = (book_price / 100.0) * face_amount

    return _irr_monthly(mean_cf, price_dollars)


def compute_portfolio_book_yields(
    positions: list[dict],
    settlement_date: date,
    rate_paths: RatePaths,
    cutoff_date: date = None,
    intex_client=None,
    prepay_model=None,
) -> dict:
    """
    Compute portfolio-level book yields, broken down by existing vs new purchases.

    Parameters
    ----------
    positions : list[dict]
        Each: {pool_id, pool_chars, face_amount, book_price, purchase_date, ...}
    settlement_date : date
    rate_paths : RatePaths
    cutoff_date : date, optional
        If provided, split positions into existing (before cutoff) and new (after/on cutoff).
        If None, treat all as "total" without split.
    intex_client : optional
    prepay_model : optional

    Returns
    -------
    dict
        Keys: existing_yield, new_yield, total_yield, pickup_bps
        Values are annualized yields in decimal (not %).
    """
    if not positions:
        return {
            "existing_yield": 0.0,
            "new_yield": 0.0,
            "total_yield": 0.0,
            "pickup_bps": 0.0,
        }

    existing_positions = []
    new_positions = []

    for pos in positions:
        purchase_date = pos.get("purchase_date")
        if cutoff_date is None:
            existing_positions.append(pos)
        elif purchase_date is not None and purchase_date >= cutoff_date:
            new_positions.append(pos)
        else:
            existing_positions.append(pos)

    def _weighted_yield(pos_list: list[dict]) -> float:
        """Compute market-value-weighted yield for a list of positions."""
        if not pos_list:
            return 0.0

        total_mv = 0.0
        mv_yields = []

        for pos in pos_list:
            pool_id = pos["pool_id"]
            pool_chars = pos.get("pool_chars")
            face = pos.get("face_amount", 1_000_000)
            book_price = pos.get("book_price", 100.0)
            mv = (book_price / 100.0) * face
            total_mv += mv

            try:
                if pool_chars is not None:
                    y = compute_book_yield(
                        pool_id=pool_id,
                        pool_chars=pool_chars,
                        book_price=book_price,
                        face_amount=face,
                        settlement_date=settlement_date,
                        rate_paths=rate_paths,
                        intex_client=intex_client,
                        prepay_model=prepay_model,
                    )
                else:
                    # Fallback using stored book_yield field
                    y = pos.get("book_yield", 0.06)
                mv_yields.append((mv, y))
            except Exception:
                mv_yields.append((mv, 0.06))

        if total_mv <= 0:
            return 0.0

        return sum(mv * y for mv, y in mv_yields) / total_mv

    existing_yield = _weighted_yield(existing_positions)
    new_yield = _weighted_yield(new_positions) if new_positions else existing_yield
    total_yield = _weighted_yield(positions)

    pickup_bps = (new_yield - existing_yield) * 10_000 if new_positions else 0.0

    return {
        "existing_yield": round(existing_yield, 6),
        "new_yield": round(new_yield, 6),
        "total_yield": round(total_yield, 6),
        "pickup_bps": round(pickup_bps, 2),
    }
