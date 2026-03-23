"""
Pool universe management.

Provides a synthetic universe of agency MBS pools with realistic characteristics.
Includes screening/filtering functionality.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional


# ---------------------------------------------------------------------------
# Synthetic universe generation
# ---------------------------------------------------------------------------

def _build_synthetic_universe() -> pd.DataFrame:
    """Build a synthetic pool universe with ~80 pools."""
    rng = np.random.default_rng(42)

    records = []

    # Product types with typical characteristics
    product_configs = {
        "CC30": {
            "wam_range": (300, 360),
            "coupon_range": (4.5, 7.5),
            "wac_add": 0.005,       # WAC typically 50bp above coupon
            "ltv_range": (0.65, 0.85),
            "fico_range": (680, 780),
            "loan_size_range": (300_000, 600_000),
            "count": 25,
        },
        "CC15": {
            "wam_range": (150, 180),
            "coupon_range": (4.0, 6.5),
            "wac_add": 0.004,
            "ltv_range": (0.60, 0.80),
            "fico_range": (700, 800),
            "loan_size_range": (250_000, 500_000),
            "count": 20,
        },
        "GN30": {
            "wam_range": (300, 360),
            "coupon_range": (4.5, 7.0),
            "wac_add": 0.005,
            "ltv_range": (0.90, 0.97),   # FHA/VA loans have higher LTV
            "fico_range": (620, 720),
            "loan_size_range": (200_000, 400_000),
            "count": 20,
        },
        "GN15": {
            "wam_range": (150, 180),
            "coupon_range": (4.0, 6.5),
            "wac_add": 0.004,
            "ltv_range": (0.85, 0.97),
            "fico_range": (640, 740),
            "loan_size_range": (180_000, 350_000),
            "count": 15,
        },
        "ARM": {
            "wam_range": (60, 120),
            "coupon_range": (5.0, 7.5),
            "wac_add": 0.003,
            "ltv_range": (0.70, 0.85),
            "fico_range": (680, 760),
            "loan_size_range": (400_000, 800_000),
            "count": 10,
            "pct_ca_override": (0.15, 0.35),
            "pct_purchase_override": (0.30, 0.60),
        },
        "TSY": {
            "wam_range": (60, 120),
            "coupon_range": (3.5, 5.5),
            "wac_add": 0.0,
            "ltv_range": (0.0, 0.0),
            "fico_range": (0, 1),
            "loan_size_range": (1_000_000, 10_000_000),
            "count": 8,
            "pct_ca_override": (0.0, 0.0),
            "pct_purchase_override": (0.0, 0.0),
            "oas_override": (0, 15),
            "price_par": True,
        },
        "CMBS": {
            "wam_range": (60, 120),
            "coupon_range": (4.0, 7.0),
            "wac_add": 0.01,
            "ltv_range": (0.55, 0.75),
            "fico_range": (0, 1),
            "loan_size_range": (2_000_000, 20_000_000),
            "count": 8,
            "pct_ca_override": (0.05, 0.25),
            "pct_purchase_override": (0.0, 0.0),
        },
        "CMO": {
            "wam_range": (120, 300),
            "coupon_range": (4.0, 6.5),
            "wac_add": 0.005,
            "ltv_range": (0.65, 0.85),
            "fico_range": (680, 760),
            "loan_size_range": (300_000, 600_000),
            "count": 8,
            "pct_ca_override": (0.10, 0.30),
            "pct_purchase_override": (0.35, 0.65),
        },
        "CDBT": {
            "wam_range": (24, 120),
            "coupon_range": (3.0, 6.0),
            "wac_add": 0.0,
            "ltv_range": (0.0, 0.0),
            "fico_range": (0, 1),
            "loan_size_range": (5_000_000, 50_000_000),
            "count": 6,
            "pct_ca_override": (0.0, 0.0),
            "pct_purchase_override": (0.0, 0.0),
            "oas_override": (0, 15),
            "price_par": True,
        },
    }

    pool_num = 1
    for product_type, cfg in product_configs.items():
        for i in range(cfg["count"]):
            coupon = rng.uniform(*cfg["coupon_range"])
            coupon = round(coupon * 2) / 2 / 100  # round to 0.5%, convert to decimal

            wam = int(rng.integers(*[int(x) for x in cfg["wam_range"]]))
            wala = int(rng.integers(0, 60))
            ltv_lo, ltv_hi = cfg["ltv_range"]
            ltv = rng.uniform(ltv_lo, max(ltv_hi, ltv_lo + 1e-9))
            fico_lo, fico_hi = cfg["fico_range"]
            fico = int(rng.integers(fico_lo, max(fico_hi, fico_lo + 1)))
            loan_size = rng.uniform(*cfg["loan_size_range"])
            if "pct_ca_override" in cfg:
                lo, hi = cfg["pct_ca_override"]
                pct_ca = rng.uniform(lo, max(hi, lo + 1e-9))
            else:
                pct_ca = rng.uniform(0.05, 0.35)
            if "pct_purchase_override" in cfg:
                lo, hi = cfg["pct_purchase_override"]
                pct_purchase = rng.uniform(lo, max(hi, lo + 1e-9))
            else:
                pct_purchase = rng.uniform(0.40, 0.85)

            # Market price: near par, adjusted for coupon vs current rates
            if cfg.get("price_par"):
                market_price = round(100.0 + rng.uniform(0.0, 1.0), 4)
            else:
                current_rate = 0.047
                price_adjustment = (coupon - current_rate) * 8  # rough duration effect
                market_price = 100.0 + price_adjustment + rng.uniform(-2.0, 2.0)
                market_price = round(market_price, 4)

            # OAS: synthetic but consistent with product type
            _base_oas_map = {
                "CC30": 52, "CC15": 34, "GN30": 47, "GN15": 30,
                "ARM": 80, "TSY": 0, "CMBS": 110, "CMO": 65, "CDBT": 5,
            }
            if "oas_override" in cfg:
                oas_lo, oas_hi = cfg["oas_override"]
                oas = rng.uniform(oas_lo, oas_hi)
            else:
                base_oas = _base_oas_map.get(product_type, 50)
                oas = base_oas + rng.uniform(-15, 20)

            # OAD: typical values by product
            _base_oad_map = {
                "CC30": 4.5, "CC15": 3.2, "GN30": 4.2, "GN15": 3.0,
                "ARM": 2.5, "TSY": 5.0, "CMBS": 5.5, "CMO": 4.0, "CDBT": 3.5,
            }
            base_oad = _base_oad_map.get(product_type, 4.0)
            oad = base_oad + rng.uniform(-0.8, 0.8)

            # Current balance
            original_balance = rng.uniform(500_000, 50_000_000)
            factor = rng.uniform(0.50, 1.00)  # pool factor
            current_balance = original_balance * factor

            # Model CPR — zero for non-mortgage product types
            if product_type in ("TSY", "CDBT", "CMBS"):
                model_cpr = 0.0
            elif product_type == "ARM":
                model_cpr = rng.uniform(15.0, 30.0)
            else:
                model_cpr = rng.uniform(5.0, 20.0)

            # 1M realized CPR
            market_cpr_1m = model_cpr + rng.uniform(-3.0, 3.0) if model_cpr > 0 else 0.0

            # CUSIP: generate synthetic 9-char alphanumeric
            _pt_prefix = {"CC30": "31", "CC15": "31", "GN30": "36", "GN15": "36",
                          "ARM": "31", "TSY": "91", "CMBS": "CM", "CMO": "17", "CDBT": "CD"}
            prefix = _pt_prefix.get(product_type, "00")
            cusip = prefix + "".join(str(rng.integers(0, 10)) for _ in range(7))

            pool_id = f"{product_type}-{str(pool_num).zfill(4)}"
            pool_num += 1

            _issuer_map = {
                "CC30": "FNMA", "CC15": "FNMA", "GN30": "GNMA", "GN15": "GNMA",
                "ARM": "FNMA", "TSY": "UST", "CMBS": "PRIVATE", "CMO": "FNMA", "CDBT": "FHLB",
            }
            records.append({
                "pool_id": pool_id,
                "cusip": cusip,
                "product_type": product_type,
                "coupon": coupon,
                "wac": coupon + cfg["wac_add"],
                "wala": wala,
                "wam": wam,
                "ltv": round(ltv, 4),
                "fico": fico,
                "loan_size": round(loan_size, 0),
                "pct_ca": round(pct_ca, 4),
                "pct_purchase": round(pct_purchase, 4),
                "original_balance": round(original_balance, 0),
                "current_balance": round(current_balance, 0),
                "pool_factor": round(factor, 4),
                "market_price": market_price,
                "oas_bps": round(oas, 1),
                "oad_years": round(oad, 2),
                "model_cpr": round(model_cpr, 1),
                "market_cpr_1m": round(market_cpr_1m, 1),
                "issuer": _issuer_map.get(product_type, "OTHER"),
                "program": product_type,
            })

    df = pd.DataFrame(records)
    return df


# ---------------------------------------------------------------------------
# Cached universe (module-level singleton)
# ---------------------------------------------------------------------------
_universe_cache: Optional[pd.DataFrame] = None


def get_pool_universe(product_types: list[str] = None) -> pd.DataFrame:
    """
    Returns DataFrame of available pools with characteristics.

    Parameters
    ----------
    product_types : list[str], optional
        Filter by product types (e.g., ["CC30", "GN30"]).
        If None, returns all product types.

    Returns
    -------
    pd.DataFrame
        Pool universe with columns: pool_id, product_type, coupon, wac, wala,
        wam, ltv, fico, loan_size, pct_ca, pct_purchase, market_price, oas_bps, etc.
    """
    global _universe_cache
    if _universe_cache is None:
        _universe_cache = _build_synthetic_universe()

    universe = _universe_cache.copy()

    if product_types is not None:
        universe = universe[universe["product_type"].isin(product_types)]

    return universe.reset_index(drop=True)


def screen_pools(
    universe: pd.DataFrame,
    filters: dict,
) -> pd.DataFrame:
    """
    Apply filter dict to universe DataFrame.

    Supported filter keys:
    - product_type: str or list[str]
    - coupon_min, coupon_max: float (decimal, e.g. 0.05)
    - wala_min, wala_max: int
    - wam_min, wam_max: int
    - fico_min, fico_max: int
    - ltv_min, ltv_max: float
    - oas_min_bps, oas_max_bps: float
    - oad_min, oad_max: float
    - loan_size_min, loan_size_max: float
    - pct_ca_max: float
    - pool_id: str (exact match)

    Parameters
    ----------
    universe : pd.DataFrame
    filters : dict

    Returns
    -------
    pd.DataFrame
        Filtered universe.
    """
    mask = pd.Series([True] * len(universe), index=universe.index)

    if "product_type" in filters:
        pt = filters["product_type"]
        if isinstance(pt, str):
            pt = [pt]
        mask &= universe["product_type"].isin(pt)

    if "coupon_min" in filters:
        mask &= universe["coupon"] >= filters["coupon_min"]
    if "coupon_max" in filters:
        mask &= universe["coupon"] <= filters["coupon_max"]

    if "wala_min" in filters:
        mask &= universe["wala"] >= filters["wala_min"]
    if "wala_max" in filters:
        mask &= universe["wala"] <= filters["wala_max"]

    if "wam_min" in filters:
        mask &= universe["wam"] >= filters["wam_min"]
    if "wam_max" in filters:
        mask &= universe["wam"] <= filters["wam_max"]

    if "fico_min" in filters:
        mask &= universe["fico"] >= filters["fico_min"]
    if "fico_max" in filters:
        mask &= universe["fico"] <= filters["fico_max"]

    if "ltv_min" in filters:
        mask &= universe["ltv"] >= filters["ltv_min"]
    if "ltv_max" in filters:
        mask &= universe["ltv"] <= filters["ltv_max"]

    if "oas_min_bps" in filters:
        mask &= universe["oas_bps"] >= filters["oas_min_bps"]
    if "oas_max_bps" in filters:
        mask &= universe["oas_bps"] <= filters["oas_max_bps"]

    if "oad_min" in filters:
        mask &= universe["oad_years"] >= filters["oad_min"]
    if "oad_max" in filters:
        mask &= universe["oad_years"] <= filters["oad_max"]

    if "loan_size_min" in filters:
        mask &= universe["loan_size"] >= filters["loan_size_min"]
    if "loan_size_max" in filters:
        mask &= universe["loan_size"] <= filters["loan_size_max"]

    if "pct_ca_max" in filters:
        mask &= universe["pct_ca"] <= filters["pct_ca_max"]

    if "pool_id" in filters:
        mask &= universe["pool_id"] == filters["pool_id"]

    return universe[mask].copy().reset_index(drop=True)
