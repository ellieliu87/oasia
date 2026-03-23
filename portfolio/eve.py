"""
Portfolio-level EVE (Economic Value of Equity) computation.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

from analytics.rate_paths import TermStructure
from analytics.risk import compute_eve, _compute_portfolio_eve_at_shock
from portfolio.aggregator import Portfolio


def compute_portfolio_eve(
    portfolio: Portfolio,
    base_curve: TermStructure,
    shocks_bps: list = None,
    n_paths: int = 64,
    n_periods: int = 360,
    seed: int = 42,
    intex_client=None,
    prepay_model=None,
) -> dict:
    """
    Compute portfolio EVE across rate shock scenarios.

    Parameters
    ----------
    portfolio : Portfolio
    base_curve : TermStructure
    shocks_bps : list[int]
        Rate shocks. Default: [-300, -200, -100, 0, 100, 200, 300].
    n_paths, n_periods, seed : simulation params
    intex_client, prepay_model : optional overrides

    Returns
    -------
    dict
        {shock_bps: {"eve": float, "delta_eve": float, "pct_change": float}}
    """
    if shocks_bps is None:
        shocks_bps = [-300, -200, -100, 0, 100, 200, 300]

    # Build position list for risk.compute_eve
    positions = _build_risk_positions(portfolio)

    return compute_eve(
        portfolio_positions=positions,
        base_curve=base_curve,
        shocks_bps=shocks_bps,
        n_paths=n_paths,
        n_periods=n_periods,
        seed=seed,
        intex_client=intex_client,
        prepay_model=prepay_model,
    )


def compute_eve_contribution_by_position(
    portfolio: Portfolio,
    shock_bps: int,
    base_curve: TermStructure,
    n_paths: int = 64,
    n_periods: int = 360,
    seed: int = 42,
    intex_client=None,
    prepay_model=None,
) -> pd.DataFrame:
    """
    Compute EVE contribution at position level for a given rate shock.

    Parameters
    ----------
    portfolio : Portfolio
    shock_bps : int
        Rate shock in basis points.
    base_curve : TermStructure
    n_paths, n_periods, seed : simulation params
    intex_client, prepay_model : optional overrides

    Returns
    -------
    pd.DataFrame
        Columns: pool_id, face_amount, eve_base, eve_shocked, delta_eve, pct_change
    """
    from analytics.prepay import project_prepay_speeds, PrepayModel
    from analytics.oas_solver import price_from_oas, solve_oas
    from analytics.cashflows import get_cash_flows
    from analytics.rate_paths import generate_rate_paths

    if prepay_model is None:
        prepay_model = PrepayModel()

    if intex_client is None:
        from data.intex_client import get_intex_client
        intex_client = get_intex_client()

    shocked_curve = base_curve.shifted(parallel_shift_bps=float(shock_bps))

    records = []

    for pos in portfolio.positions:
        pool_id = pos["pool_id"]
        face = pos.get("face_amount", 1_000_000)
        book_price = pos.get("book_price", 100.0)

        try:
            # Generate paths for base
            rate_paths_base = generate_rate_paths(
                curve=base_curve,
                n_paths=n_paths,
                n_periods=n_periods,
                seed=seed,
            )

            # Get pool_chars
            pool_chars = pos.get("pool_chars")
            if pool_chars is None:
                records.append({
                    "pool_id": pool_id,
                    "face_amount": face,
                    "eve_base": (book_price / 100.0) * face,
                    "eve_shocked": (book_price / 100.0) * face,
                    "delta_eve": 0.0,
                    "pct_change": 0.0,
                })
                continue

            # Prepay speeds
            cpr_base = project_prepay_speeds(pool_chars, rate_paths_base, model=prepay_model)

            # Cash flows
            cf_base = get_cash_flows(
                pool_id=pool_id,
                cpr_vectors=cpr_base,
                settlement_date=date.today(),
                face_amount=face,
                intex_client=intex_client,
            )

            # Solve OAS at base
            oas_result = solve_oas(cf_base, rate_paths_base, book_price)
            oas_bps = oas_result.oas_bps

            # Base EVE
            eve_base = (price_from_oas(cf_base, rate_paths_base, oas_bps) / 100.0) * face

            # Shocked paths
            rate_paths_shock = generate_rate_paths(
                curve=shocked_curve,
                n_paths=n_paths,
                n_periods=n_periods,
                seed=seed,
            )

            # New CPR vectors under shocked rates
            cpr_shock = project_prepay_speeds(pool_chars, rate_paths_shock, model=prepay_model)

            cf_shock = get_cash_flows(
                pool_id=pool_id,
                cpr_vectors=cpr_shock,
                settlement_date=date.today(),
                face_amount=face,
                intex_client=intex_client,
            )

            eve_shocked = (price_from_oas(cf_shock, rate_paths_shock, oas_bps) / 100.0) * face
            delta_eve = eve_shocked - eve_base
            pct_change = (delta_eve / eve_base * 100.0) if eve_base != 0 else 0.0

            records.append({
                "pool_id": pool_id,
                "face_amount": face,
                "book_price": book_price,
                "oas_bps": round(oas_bps, 2),
                "eve_base": round(eve_base, 2),
                "eve_shocked": round(eve_shocked, 2),
                "delta_eve": round(delta_eve, 2),
                "pct_change": round(pct_change, 4),
            })

        except Exception:
            book_value = (book_price / 100.0) * face
            records.append({
                "pool_id": pool_id,
                "face_amount": face,
                "book_price": book_price,
                "oas_bps": None,
                "eve_base": book_value,
                "eve_shocked": book_value,
                "delta_eve": 0.0,
                "pct_change": 0.0,
            })

    return pd.DataFrame(records)


def _build_risk_positions(portfolio: Portfolio) -> list[dict]:
    """Convert Portfolio positions to the format expected by risk.compute_eve."""
    from analytics.prepay import PoolCharacteristics

    result = []
    for pos in portfolio.positions:
        risk_pos = pos.copy()

        # Ensure pool_chars is present
        if "pool_chars" not in risk_pos or risk_pos["pool_chars"] is None:
            # Try to reconstruct from available fields
            try:
                risk_pos["pool_chars"] = PoolCharacteristics(
                    coupon=pos.get("coupon", 0.06),
                    wac=pos.get("wac", 0.065),
                    wala=int(pos.get("wala", 0)),
                    wam=int(pos.get("wam", 360)),
                    loan_size=pos.get("loan_size", 400_000),
                    ltv=pos.get("ltv", 0.75),
                    fico=int(pos.get("fico", 750)),
                    pct_ca=pos.get("pct_ca", 0.15),
                    pct_purchase=pos.get("pct_purchase", 0.65),
                    product_type=pos.get("product_type", "CC30"),
                    pool_id=pos.get("pool_id", ""),
                    current_balance=pos.get("face_amount", 1_000_000),
                )
            except Exception:
                pass

        result.append(risk_pos)

    return result
