"""
Portfolio aggregation engine.

Computes market-value-weighted analytics, contributions, and portfolio-level metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from analytics.oas_solver import BondAnalytics


# ---------------------------------------------------------------------------
# Portfolio dataclass
# ---------------------------------------------------------------------------

@dataclass
class Portfolio:
    """Container for portfolio positions and analytics."""
    positions: list[dict]    # list of position dicts
    as_of_date: date
    analytics: dict[str, BondAnalytics] = field(default_factory=dict)
    summary: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_portfolio(
    positions: list[dict],
    analytics: dict[str, BondAnalytics],
) -> dict:
    """
    Compute market-value-weighted portfolio analytics.

    Parameters
    ----------
    positions : list[dict]
        Each: {pool_id, face_amount, book_price, ...}
    analytics : dict[str, BondAnalytics]
        Analytics keyed by pool_id.

    Returns
    -------
    dict
        Portfolio-level analytics including:
        - total_book_value: sum of face * book_price/100
        - total_market_value: sum of face * market_price/100
        - total_face: sum of face amounts
        - weighted_oas: market-value-weighted OAS (bps)
        - weighted_oad: market-value-weighted OAD (years)
        - weighted_convexity: market-value-weighted convexity
        - weighted_yield: market-value-weighted yield (%)
        - position_count: number of positions
        - contributions: list of per-position contribution dicts
    """
    if not positions:
        return _empty_portfolio_summary()

    total_face = 0.0
    total_book_value = 0.0
    total_market_value = 0.0
    contributions = []

    # Compute market values
    mv_list = []
    for pos in positions:
        pool_id = pos["pool_id"]
        face = pos.get("face_amount", 0.0)
        book_price = pos.get("book_price", 100.0)
        book_value = face * book_price / 100.0

        # Market value: use model price from analytics, fallback to book
        if pool_id in analytics:
            mkt_price = analytics[pool_id].market_price
        else:
            mkt_price = book_price
        market_value = face * mkt_price / 100.0

        total_face += face
        total_book_value += book_value
        total_market_value += market_value
        mv_list.append(market_value)

    # Compute weighted averages
    total_mv = sum(mv_list)
    if total_mv <= 0:
        return _empty_portfolio_summary()

    mv_weights = np.array(mv_list) / total_mv

    weighted_oas = 0.0
    weighted_oad = 0.0
    weighted_convexity = 0.0
    weighted_yield = 0.0
    weighted_model_cpr = 0.0

    for i, pos in enumerate(positions):
        pool_id = pos["pool_id"]
        w = mv_weights[i]

        if pool_id in analytics:
            a = analytics[pool_id]
            weighted_oas += w * a.oas
            weighted_oad += w * a.oad
            weighted_convexity += w * a.convexity
            weighted_yield += w * a.yield_
            weighted_model_cpr += w * a.model_cpr

            contributions.append({
                "pool_id": pool_id,
                "face_amount": pos.get("face_amount", 0.0),
                "book_price": pos.get("book_price", 100.0),
                "market_price": a.market_price,
                "market_value": mv_list[i],
                "mv_weight": round(w * 100.0, 2),  # %
                "oas_bps": a.oas,
                "oad_years": a.oad,
                "convexity": a.convexity,
                "yield_pct": a.yield_,
                "oas_contribution": round(w * a.oas, 3),
                "oad_contribution": round(w * a.oad, 4),
            })
        else:
            contributions.append({
                "pool_id": pool_id,
                "face_amount": pos.get("face_amount", 0.0),
                "book_price": pos.get("book_price", 100.0),
                "market_price": pos.get("book_price", 100.0),
                "market_value": mv_list[i],
                "mv_weight": round(w * 100.0, 2),
                "oas_bps": None,
                "oad_years": None,
                "convexity": None,
                "yield_pct": None,
                "oas_contribution": None,
                "oad_contribution": None,
            })

    return {
        "total_face": round(total_face, 2),
        "total_book_value": round(total_book_value, 2),
        "total_market_value": round(total_market_value, 2),
        "position_count": len(positions),
        "weighted_oas": round(weighted_oas, 2),
        "weighted_oad": round(weighted_oad, 3),
        "weighted_convexity": round(weighted_convexity, 4),
        "weighted_yield": round(weighted_yield, 4),
        "weighted_model_cpr": round(weighted_model_cpr, 2),
        "contributions": contributions,
    }


def _empty_portfolio_summary() -> dict:
    """Return empty portfolio summary."""
    return {
        "total_face": 0.0,
        "total_book_value": 0.0,
        "total_market_value": 0.0,
        "position_count": 0,
        "weighted_oas": 0.0,
        "weighted_oad": 0.0,
        "weighted_convexity": 0.0,
        "weighted_yield": 0.0,
        "weighted_model_cpr": 0.0,
        "contributions": [],
    }


def build_portfolio_from_snapshot(snapshot: pd.DataFrame) -> Portfolio:
    """
    Build Portfolio object from a snapshot DataFrame.

    Parameters
    ----------
    snapshot : pd.DataFrame
        Output of SnapshotStore.get_snapshot().

    Returns
    -------
    Portfolio
    """
    if snapshot.empty:
        return Portfolio(positions=[], as_of_date=date.today())

    # Extract as_of_date
    if "snapshot_date" in snapshot.columns:
        snapshot_dates = snapshot["snapshot_date"].dropna()
        as_of_date = snapshot_dates.iloc[0] if len(snapshot_dates) > 0 else date.today()
    else:
        as_of_date = date.today()

    # Convert rows to position dicts
    positions = snapshot.to_dict("records")

    return Portfolio(positions=positions, as_of_date=as_of_date)
