"""
Portfolio-level risk analytics.

Computes EVE (Economic Value of Equity) across rate shock scenarios.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import numpy as np

from analytics.rate_paths import TermStructure, generate_rate_paths
from analytics.oas_solver import price_from_oas, solve_oas
from analytics.prepay import project_prepay_speeds, PrepayModel
from analytics.cashflows import get_cash_flows


def _compute_portfolio_eve_at_shock(
    portfolio_positions: list[dict],
    shocked_curve: TermStructure,
    n_paths: int = 64,
    n_periods: int = 360,
    seed: int = 42,
    intex_client=None,
    prepay_model=None,
) -> float:
    """
    Compute total PV of all portfolio cash flows under a given rate curve.

    Parameters
    ----------
    portfolio_positions : list[dict]
        Each dict: {pool_id, pool_chars, face_amount, book_price, ...}
    shocked_curve : TermStructure
    n_paths, n_periods, seed : simulation params
    intex_client, prepay_model : optional overrides

    Returns
    -------
    float
        Total present value ($).
    """
    if prepay_model is None:
        prepay_model = PrepayModel()

    if intex_client is None:
        from data.intex_client import get_intex_client
        intex_client = get_intex_client()

    # Generate rate paths once for all positions
    rate_paths = generate_rate_paths(
        curve=shocked_curve,
        n_paths=n_paths,
        n_periods=n_periods,
        seed=seed,
    )

    total_pv = 0.0

    for position in portfolio_positions:
        pool_id = position["pool_id"]
        pool_chars = position["pool_chars"]
        face_amount = position.get("face_amount", 1_000_000)
        book_price = position.get("book_price", 100.0)

        # Get OAS for this position (stored or compute from book price)
        oas_bps = position.get("oas_bps", None)

        try:
            # Project prepayment speeds
            cpr_vectors = project_prepay_speeds(pool_chars, rate_paths, model=prepay_model)

            # Get cash flows
            cash_flows = get_cash_flows(
                pool_id=pool_id,
                cpr_vectors=cpr_vectors,
                settlement_date=date.today(),
                face_amount=face_amount,
                intex_client=intex_client,
            )

            if oas_bps is None:
                # Solve OAS from book price
                oas_result = solve_oas(cash_flows, rate_paths, book_price)
                oas_bps = oas_result.oas_bps

            # Price at OAS
            price_pct = price_from_oas(cash_flows, rate_paths, oas_bps)
            position_pv = (price_pct / 100.0) * face_amount
            total_pv += position_pv

        except Exception:
            # Fallback: use book value
            total_pv += (book_price / 100.0) * face_amount

    return total_pv


def compute_eve(
    portfolio_positions: list[dict],
    base_curve: TermStructure,
    shocks_bps: list = None,
    n_paths: int = 64,
    n_periods: int = 360,
    seed: int = 42,
    intex_client=None,
    prepay_model=None,
) -> dict:
    """
    Compute EVE profile across rate shock scenarios.

    EVE = sum of PV of all future cash flows across portfolio.

    Parameters
    ----------
    portfolio_positions : list[dict]
        Each: {pool_id, pool_chars, face_amount, book_price}
    base_curve : TermStructure
    shocks_bps : list[int]
        Rate shocks to compute. Default: [-300, -200, -100, 0, 100, 200, 300].
    n_paths, n_periods, seed : simulation params
    intex_client, prepay_model : optional overrides

    Returns
    -------
    dict
        {shock_bps: {"eve": float, "delta_eve": float, "pct_change": float}}
    """
    if shocks_bps is None:
        shocks_bps = [-300, -200, -100, 0, 100, 200, 300]

    results = {}

    # Compute base EVE (shock = 0)
    base_eve = None
    for shock in shocks_bps:
        if shock == 0:
            base_eve = _compute_portfolio_eve_at_shock(
                portfolio_positions=portfolio_positions,
                shocked_curve=base_curve,
                n_paths=n_paths,
                n_periods=n_periods,
                seed=seed,
                intex_client=intex_client,
                prepay_model=prepay_model,
            )
            break

    # If 0 not in shocks, compute it separately
    if base_eve is None:
        base_eve = _compute_portfolio_eve_at_shock(
            portfolio_positions=portfolio_positions,
            shocked_curve=base_curve,
            n_paths=n_paths,
            n_periods=n_periods,
            seed=seed,
            intex_client=intex_client,
            prepay_model=prepay_model,
        )

    for shock in shocks_bps:
        if shock == 0:
            eve = base_eve
        else:
            shocked_curve = base_curve.shifted(parallel_shift_bps=float(shock))
            eve = _compute_portfolio_eve_at_shock(
                portfolio_positions=portfolio_positions,
                shocked_curve=shocked_curve,
                n_paths=n_paths,
                n_periods=n_periods,
                seed=seed,
                intex_client=intex_client,
                prepay_model=prepay_model,
            )

        delta_eve = eve - base_eve
        pct_change = (delta_eve / base_eve * 100.0) if base_eve != 0 else 0.0

        results[shock] = {
            "eve": round(eve, 2),
            "delta_eve": round(delta_eve, 2),
            "pct_change": round(pct_change, 4),
        }

    return results
