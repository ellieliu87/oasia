"""
universe_1000.py
================
Simulated universe of 1000 agency MBS CUSIP pools with full prepayment model
features and 6 months of monthly historical snapshots (Sep 2025 – Feb 2026).

Pool counts
-----------
CC30 = 400, CC15 = 250, GN30 = 200, GN15 = 150

Usage
-----
from data.universe_1000 import get_universe_1000, get_universe_snapshots, \
    get_pool_snapshot, get_pool_history, screen_universe
"""

from __future__ import annotations

import string
from datetime import date
from functools import reduce
from typing import Optional

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RNG_SEED: int = 1234

SNAPSHOT_DATES: list[date] = [
    date(2025, 9, 30),
    date(2025, 10, 31),
    date(2025, 11, 28),
    date(2025, 12, 31),
    date(2026, 1, 31),
    date(2026, 2, 28),
]

RATES_10Y: list[float] = [0.0485, 0.0492, 0.0478, 0.0465, 0.0472, 0.0488]
SOFR_RATES: list[float] = [0.0530, 0.0520, 0.0510, 0.0500, 0.0510, 0.0515]

PRODUCT_COUNTS: dict[str, int] = {
    "CC30": 400,
    "CC15": 250,
    "GN30": 200,
    "GN15": 150,
}

COUPONS: dict[str, list[float]] = {
    "CC30": [4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 7.5],
    "CC15": [4.5, 5.0, 5.5, 6.0, 6.5, 7.0],
    "GN30": [4.5, 5.0, 5.5, 6.0, 6.5, 7.0],
    "GN15": [4.5, 5.0, 5.5, 6.0, 6.5],
}

SERVICERS: list[str] = [
    "Wells Fargo",
    "JPMorgan",
    "PennyMac",
    "Mr. Cooper",
    "United Wholesale",
    "Freedom Mortgage",
]

US_STATES: list[str] = [
    "CA", "TX", "FL", "NY", "IL", "PA", "OH", "GA", "NC", "MI",
    "NJ", "VA", "WA", "AZ", "MA", "TN", "IN", "MO", "MD", "WI",
]

# Module-level cache
_universe_df: Optional[pd.DataFrame] = None
_snapshots_df: Optional[pd.DataFrame] = None


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _logistic(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def _logistic_arr(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


def _gen_cusip(rng: np.random.Generator, prefix: str, suffix_len: int, existing: set[str]) -> str:
    alphanum = string.ascii_uppercase + string.digits
    while True:
        suffix = "".join(rng.choice(list(alphanum), size=suffix_len))
        cusip = prefix + suffix
        if cusip not in existing:
            existing.add(cusip)
            return cusip


def _compute_price(coupon: float, wam_t: int, current_mortgage_rate: float, oas_bps: float) -> float:
    """Level-pay present value price as % of par."""
    monthly_rate = coupon / 100.0 / 12.0
    market_monthly_rate = (current_mortgage_rate + oas_bps / 10000.0) / 12.0
    n = max(wam_t, 1)
    if abs(monthly_rate - market_monthly_rate) < 1e-8:
        price = 100.0
    else:
        numerator = monthly_rate / market_monthly_rate * (1.0 - (1.0 + market_monthly_rate) ** (-n))
        denominator = 1.0 - (1.0 + monthly_rate) ** (-n)
        price = numerator / denominator * 100.0
    return price


# ---------------------------------------------------------------------------
# Universe builder
# ---------------------------------------------------------------------------

def _build_universe() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(RNG_SEED)

    # ------------------------------------------------------------------
    # 1. Build static pool table
    # ------------------------------------------------------------------
    rows: list[dict] = []
    used_cusips: set[str] = set()

    for product_type, count in PRODUCT_COUNTS.items():
        is_15y = product_type.endswith("15")
        is_gn = product_type.startswith("GN")
        original_wam = 180 if is_15y else 360

        for seq in range(1, count + 1):
            # Issuer
            if is_gn:
                issuer = "GNMA"
            else:
                issuer = "FNMA" if rng.random() < 0.60 else "FHLMC"

            # CUSIP
            if issuer == "FNMA":
                cusip = _gen_cusip(rng, "3140X", 5, used_cusips)
            elif issuer == "FHLMC":
                cusip = _gen_cusip(rng, "3132D", 5, used_cusips)
            else:
                cusip = _gen_cusip(rng, "36179M", 4, used_cusips)

            # Coupon
            coupon_list = COUPONS[product_type]
            coupon = float(rng.choice(coupon_list))

            # WAC = coupon + gross servicing spread ~50-62 bps
            wac = coupon + rng.uniform(0.375, 0.875)

            # WALA at issue: weighted toward 12-36
            wala_weights = np.array([
                max(0.0, 1.0 - abs(w - 24) / 24.0) + 0.1 for w in range(61)
            ])
            wala_weights /= wala_weights.sum()
            wala_at_issue = int(rng.choice(np.arange(61), p=wala_weights))

            # Original balance ranges
            if product_type == "CC30":
                orig_bal = rng.uniform(50e6, 2000e6)
            elif product_type == "CC15":
                orig_bal = rng.uniform(30e6, 800e6)
            elif product_type == "GN30":
                orig_bal = rng.uniform(20e6, 500e6)
            else:  # GN15
                orig_bal = rng.uniform(10e6, 300e6)

            # LTV: higher for GN
            if is_gn:
                ltv = rng.uniform(0.75, 0.95)
            else:
                ltv = rng.uniform(0.60, 0.90)

            # FICO: lower for GN
            if is_gn:
                fico = int(np.clip(rng.normal(710, 45), 580, 800))
            else:
                fico = int(np.clip(rng.normal(745, 38), 620, 820))

            # Loan size
            if product_type == "CC30":
                loan_size = rng.uniform(200_000, 900_000)
            elif product_type == "CC15":
                loan_size = rng.uniform(150_000, 700_000)
            elif product_type == "GN30":
                loan_size = rng.uniform(100_000, 500_000)
            else:
                loan_size = rng.uniform(80_000, 400_000)

            pct_ca = rng.uniform(0.05, 0.40)
            pct_purchase = rng.uniform(0.30, 0.90)

            if is_gn:
                pct_30day_dq = rng.uniform(0.005, 0.035)
            else:
                pct_30day_dq = rng.uniform(0.001, 0.010)

            servicer = str(rng.choice(SERVICERS))

            # Top-3 states by concentration
            state_sample = rng.choice(US_STATES, size=3, replace=False)
            raw_pcts = rng.dirichlet(np.ones(3) * 2.0)
            # Bias CA if pct_ca > 0.15
            if pct_ca > 0.15 and "CA" not in state_sample:
                state_sample[0] = "CA"
                raw_pcts = rng.dirichlet(np.ones(3) * 2.0)
            # Scale so they sum to pct_ca + remaining
            scaled = raw_pcts / raw_pcts.sum()
            # First state share ≈ pct_ca if CA present
            state_top3 = [
                {"state": str(state_sample[i]), "pct": round(float(scaled[i]), 4)}
                for i in range(3)
            ]

            pool_id = f"{issuer}_{product_type}_{int(coupon*10):02d}_{seq:03d}"

            # Pool-specific OAS spread (fixed)
            oas_pool_spread = float(rng.normal(0, 5))

            rows.append({
                "cusip": cusip,
                "pool_id": pool_id,
                "issuer": issuer,
                "product_type": product_type,
                "coupon": coupon,
                "wac": round(wac, 4),
                "wala_at_issue": wala_at_issue,
                "original_wam": original_wam,
                "original_balance": round(orig_bal, 2),
                "ltv": round(ltv, 4),
                "fico": fico,
                "loan_size": round(loan_size, 2),
                "pct_ca": round(pct_ca, 4),
                "pct_purchase": round(pct_purchase, 4),
                "pct_30day_dq": round(pct_30day_dq, 6),
                "servicer": servicer,
                "state_top3": state_top3,
                "burnout": 0.0,
                "oas_pool_spread": round(oas_pool_spread, 4),
            })

    universe_df = pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # 2. Build monthly snapshots
    # ------------------------------------------------------------------
    snap_rows: list[dict] = []

    # Precompute rate environment for each snapshot
    noise_30y = rng.normal(0, 0.001, size=6)
    noise_15y = rng.normal(0, 0.001, size=6)
    rates_30y = np.array(RATES_10Y) + 0.0170 + noise_30y
    rates_15y = np.array(RATES_10Y) + 0.0130 + noise_15y
    rates_10y_arr = np.array(RATES_10Y)
    sofr_arr = np.array(SOFR_RATES)

    for _, pool in universe_df.iterrows():
        product_type: str = pool["product_type"]
        coupon: float = pool["coupon"]
        wac: float = pool["wac"]
        wala_at_issue: int = pool["wala_at_issue"]
        original_wam: int = pool["original_wam"]
        original_balance: float = pool["original_balance"]
        ltv: float = pool["ltv"]
        fico: int = pool["fico"]
        pct_ca: float = pool["pct_ca"]
        pct_purchase: float = pool["pct_purchase"]
        oas_pool_spread: float = pool["oas_pool_spread"]
        is_15y: bool = product_type.endswith("15")

        # Pre-compute pool-level factors (constant across months)
        geo_factor = 1.0 + 0.10 * pct_ca
        ltv_factor = float(np.clip(1.0 - 0.5 * (ltv - 0.70), 0.70, 1.20))
        fico_normalized = (fico - 680) / 100.0
        fico_factor = 1.0 + 0.10 * float(np.clip(fico_normalized, -1.0, 1.5))
        purchase_factor = 1.0 - 0.10 * pct_purchase

        # Cohort OAS base (depends on coupon)
        if product_type == "CC30":
            cohort_oas_base = 35.0 + max(0.0, (coupon - 5.5) * 20.0)
        elif product_type == "CC15":
            cohort_oas_base = 28.0 + max(0.0, (coupon - 5.0) * 15.0)
        elif product_type == "GN30":
            cohort_oas_base = 22.0 + max(0.0, (coupon - 5.5) * 18.0)
        else:
            cohort_oas_base = 18.0 + max(0.0, (coupon - 5.0) * 12.0)

        # Rate-sensitivity noise for cohort OAS (one per pool, same shape as snapshots)
        cohort_oas_noise = rng.normal(0, 2, size=6)
        cpr_noise = rng.normal(0, 0.05, size=6)
        price_noise = rng.normal(0, 0.001, size=6)
        oas_time_noise = rng.normal(0, 2, size=6)

        # Track running balance & burnout
        current_balance = original_balance
        burnout_accum = 0.0
        prev_rate_10y = rates_10y_arr[0]

        for snap_idx in range(6):
            rate_10y = rates_10y_arr[snap_idx]
            sofr = sofr_arr[snap_idx]
            current_mortgage_rate = rates_15y[snap_idx] if is_15y else rates_30y[snap_idx]

            wala_t = wala_at_issue + snap_idx + 1
            wam_t = max(original_wam - wala_t, 1)

            # Refi incentive (wac in %, mortgage rate in decimal → convert)
            refi_incentive = wac / 100.0 - current_mortgage_rate

            # Seasoning ramp
            seasoning_ramp = min(wala_t / 30.0, 1.0)

            # CPR base
            base_cpr_min = 0.03
            base_cpr_max = 0.40
            cpr_base = base_cpr_min + (base_cpr_max - base_cpr_min) * _logistic(8.0 * refi_incentive)

            # CPR with pool factors
            cpr_t = cpr_base * seasoning_ramp * geo_factor * ltv_factor * fico_factor * purchase_factor
            cpr_t = float(np.clip(cpr_t, 0.01, 0.60))

            # Add random noise
            cpr_t *= (1.0 + cpr_noise[snap_idx])
            cpr_t = float(np.clip(cpr_t, 0.005, 0.65))

            # SMM
            smm_t = 1.0 - (1.0 - cpr_t) ** (1.0 / 12.0)

            # Scheduled amortization rate (approximate)
            scheduled_amort_rate = 1.0 / max(wam_t, 1)

            # Monthly balance decay
            decay = (1.0 - smm_t) * (1.0 - scheduled_amort_rate)
            current_balance = current_balance * decay

            # Burnout
            burnout_accum += max(0.0, refi_incentive)

            # OAS
            rate_10y_delta_bps = (rate_10y - prev_rate_10y) * 10000.0
            cohort_oas_t = (
                cohort_oas_base
                + 0.5 * rate_10y_delta_bps
                + cohort_oas_noise[snap_idx]
            )
            oas_bps = cohort_oas_t + oas_pool_spread + oas_time_noise[snap_idx]

            # OAD
            if product_type in ("CC30", "GN30"):
                denom_wam = 360.0
                oad = 3.0 + (wam_t / denom_wam) * 3.0 - cpr_t * 15.0 - refi_incentive * 5.0
            else:
                denom_wam = 180.0
                oad = 1.5 + (wam_t / denom_wam) * 2.5 - cpr_t * 10.0
            oad = float(np.clip(oad, 0.5, 8.0))

            # Convexity
            convexity = -0.5 - refi_incentive * 3.0 + rng.normal(0, 0.1)
            convexity = float(np.clip(convexity, -3.0, 0.5))

            # Price
            price = _compute_price(coupon, wam_t, current_mortgage_rate, oas_bps)
            price = max(85.0, min(115.0, price * (1.0 + price_noise[snap_idx])))

            # Book yield (simplified)
            price_diff = 100.0 - price
            book_yield = wac / 100.0 + price_diff / (max(price, 1.0) * wam_t / 12.0)

            prev_rate_10y = rate_10y

            snap_rows.append({
                "cusip": pool["cusip"],
                "pool_id": pool["pool_id"],
                "snapshot_date": SNAPSHOT_DATES[snap_idx],
                "wala": wala_t,
                "wam": wam_t,
                "current_balance": round(current_balance, 2),
                "market_price": round(price, 6),
                "cpr": round(cpr_t, 6),
                "oas_bps": round(oas_bps, 4),
                "oad_years": round(oad, 4),
                "convexity": round(convexity, 4),
                "book_yield": round(book_yield, 6),
                "refi_incentive": round(refi_incentive, 6),
                "burnout": round(burnout_accum, 6),
                "current_mortgage_rate": round(current_mortgage_rate, 6),
                "rate_10y": round(rate_10y, 6),
                "sofr_rate": round(sofr, 6),
            })

    snapshots_df = pd.DataFrame(snap_rows)
    snapshots_df["snapshot_date"] = pd.to_datetime(snapshots_df["snapshot_date"])

    # Drop internal helper column from universe before returning
    universe_public = universe_df.drop(columns=["oas_pool_spread"])

    return universe_public, snapshots_df


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_universe_1000() -> pd.DataFrame:
    """Return the full 1000-CUSIP universe as a DataFrame (static pool characteristics)."""
    global _universe_df, _snapshots_df
    if _universe_df is None:
        _universe_df, _snapshots_df = _build_universe()
    return _universe_df.copy()


def get_universe_snapshots() -> pd.DataFrame:
    """Return the 6-month history as a DataFrame with columns:
    cusip, pool_id, snapshot_date, wala, wam, current_balance, market_price,
    cpr, oas_bps, oad_years, convexity, book_yield, refi_incentive, burnout,
    current_mortgage_rate, rate_10y, sofr_rate
    """
    global _universe_df, _snapshots_df
    if _snapshots_df is None:
        _universe_df, _snapshots_df = _build_universe()
    return _snapshots_df.copy()


def get_pool_snapshot(pool_id: str, as_of_date: Optional[date] = None) -> dict:
    """Get the most recent snapshot for a pool, or on a specific date.

    Parameters
    ----------
    pool_id:
        The pool identifier string, e.g. ``"FNMA_CC30_60_001"``.
    as_of_date:
        If provided, return the snapshot for this exact date.  If ``None``,
        return the most recent available snapshot.

    Returns
    -------
    dict
        A dictionary of snapshot fields, or an empty dict if not found.
    """
    snaps = get_universe_snapshots()
    pool_snaps = snaps[snaps["pool_id"] == pool_id]
    if pool_snaps.empty:
        return {}
    if as_of_date is not None:
        target = pd.Timestamp(as_of_date)
        row = pool_snaps[pool_snaps["snapshot_date"] == target]
        if row.empty:
            return {}
        return row.iloc[0].to_dict()
    return pool_snaps.sort_values("snapshot_date").iloc[-1].to_dict()


def get_pool_history(pool_id: str) -> pd.DataFrame:
    """Get full 6-month history for a specific pool.

    Parameters
    ----------
    pool_id:
        The pool identifier string.

    Returns
    -------
    pd.DataFrame
        All snapshot rows for the pool, sorted by date.
    """
    snaps = get_universe_snapshots()
    result = snaps[snaps["pool_id"] == pool_id].sort_values("snapshot_date").reset_index(drop=True)
    return result


def screen_universe(filters: Optional[dict] = None) -> pd.DataFrame:
    """Screen the universe with filters, returns latest snapshot for each pool with static features.

    Parameters
    ----------
    filters:
        Optional dict of column→value or column→(min, max) range filters.
        Supported filter forms:
          - ``{"product_type": "CC30"}``         exact match
          - ``{"coupon": (5.0, 6.5)}``           inclusive range
          - ``{"issuer": ["FNMA", "FHLMC"]}``    list membership

    Returns
    -------
    pd.DataFrame
        Latest-snapshot columns merged with static pool features.
    """
    universe = get_universe_1000()
    snaps = get_universe_snapshots()

    # Latest snapshot per pool
    latest = (
        snaps.sort_values("snapshot_date")
        .groupby("pool_id", as_index=False)
        .last()
    )
    merged = universe.merge(latest, on=["cusip", "pool_id"], how="inner")

    if filters:
        for col, criterion in filters.items():
            if col not in merged.columns:
                continue
            if isinstance(criterion, tuple) and len(criterion) == 2:
                lo, hi = criterion
                merged = merged[(merged[col] >= lo) & (merged[col] <= hi)]
            elif isinstance(criterion, list):
                merged = merged[merged[col].isin(criterion)]
            else:
                merged = merged[merged[col] == criterion]

    return merged.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Main — summary stats
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    print("Building universe (seed=1234) …")
    univ = get_universe_1000()
    snaps = get_universe_snapshots()

    print("\n=== Universe Summary ===")
    print(f"Total pools     : {len(univ):,}")
    print(f"Unique CUSIPs   : {univ['cusip'].nunique():,}")
    print(f"Product counts  :")
    for pt, cnt in univ["product_type"].value_counts().sort_index().items():
        print(f"  {pt}: {cnt}")
    print(f"\nIssuer counts   :")
    for issuer, cnt in univ["issuer"].value_counts().sort_index().items():
        print(f"  {issuer}: {cnt}")
    print(f"\nCoupon distribution:")
    print(univ["coupon"].value_counts().sort_index().to_string())
    print(f"\nOriginal balance ($ M):")
    bal = univ["original_balance"] / 1e6
    print(f"  min={bal.min():.1f}  median={bal.median():.1f}  max={bal.max():.1f}")
    print(f"\nLTV  : mean={univ['ltv'].mean():.3f}  std={univ['ltv'].std():.3f}")
    print(f"FICO : mean={univ['fico'].mean():.1f}  std={univ['fico'].std():.1f}")

    print("\n=== Snapshot Summary ===")
    print(f"Total snapshot rows : {len(snaps):,}")
    print(f"Snapshot dates      : {sorted(snaps['snapshot_date'].unique())}")
    latest = snaps[snaps["snapshot_date"] == snaps["snapshot_date"].max()]
    print(f"\nLatest snapshot ({latest['snapshot_date'].iloc[0].date()}):")
    print(f"  CPR  : mean={latest['cpr'].mean():.4f}  std={latest['cpr'].std():.4f}")
    print(f"  OAS  : mean={latest['oas_bps'].mean():.2f}  std={latest['oas_bps'].std():.2f} bps")
    print(f"  OAD  : mean={latest['oad_years'].mean():.3f}  std={latest['oad_years'].std():.3f}")
    print(f"  Price: mean={latest['market_price'].mean():.3f}  std={latest['market_price'].std():.3f}")

    print("\n=== screen_universe example: CC30, coupon in [5.0, 6.0] ===")
    screened = screen_universe({"product_type": "CC30", "coupon": (5.0, 6.0)})
    print(f"  Pools matching: {len(screened)}")
    print(screened[["pool_id", "coupon", "cpr", "oas_bps", "market_price"]].head(5).to_string(index=False))

    print("\n=== get_pool_history example ===")
    sample_pool = univ["pool_id"].iloc[0]
    hist = get_pool_history(sample_pool)
    print(hist[["snapshot_date", "wala", "cpr", "market_price", "burnout"]].to_string(index=False))

    sys.exit(0)
