"""
Generates realistic fake MBS/CMBS/Treasury portfolio DataFrames.

Two outputs:
  - pool_universe_df : (cusip × month) pool-level projections and characteristics
  - portfolio_df     : monthly portfolio-level target vs predicted-existing vs new_volume
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import List


# ---------------------------------------------------------------------------
# Pool seed definition
# ---------------------------------------------------------------------------

@dataclass
class PoolSeed:
    cusip: str
    product_type: str          # MBS | CMBS | TREASURY
    agency: str                # FNMA | FHLMC | GNMA | PRIVATE | N/A
    term: str                  # 30YR | 15YR | 10YR | 5YR | 2YR | N/A
    rate_type: str             # FIXED | ARM
    arm_reset: str             # "5/1" | "7/1" | "10/1" | N/A
    coupon: float              # annual coupon rate %
    wac: float                 # weighted avg coupon of underlying loans %
    wam_initial: int           # remaining maturity in months at t=0
    wala_initial: int          # loan age in months at t=0
    original_balance: float    # $MM face value at origination
    current_factor: float      # outstanding / original at t=0 (0–1)
    cpr_base: float            # base conditional prepayment rate (annual %)
    cdr_base: float            # base conditional default rate (annual %)
    oas_base: float            # option-adjusted spread, basis points
    duration_initial: float    # effective duration (years) at t=0
    convexity_initial: float   # convexity at t=0
    price_initial: float       # clean price per $100 face
    credit_rating: str         # AAA | AA | A | BBB | N/A
    liquidity_score: float     # 1 (illiquid) – 10 (most liquid)


def _pool(
    cusip, product_type, agency, term, rate_type, arm_reset,
    coupon, wac, wam, wala, orig_bal, factor,
    cpr, cdr, oas, duration, convexity, price, rating, liquidity
) -> PoolSeed:
    """Thin convenience wrapper to keep seed tables readable."""
    return PoolSeed(
        cusip=cusip, product_type=product_type, agency=agency,
        term=term, rate_type=rate_type, arm_reset=arm_reset,
        coupon=coupon, wac=wac, wam_initial=wam, wala_initial=wala,
        original_balance=orig_bal, current_factor=factor,
        cpr_base=cpr, cdr_base=cdr, oas_base=oas,
        duration_initial=duration, convexity_initial=convexity,
        price_initial=price, credit_rating=rating, liquidity_score=liquidity,
    )


# ---------------------------------------------------------------------------
# Seed catalogue
# Fields: cusip, type, agency, term, rt, reset, cpn, wac, wam, wala, orig,
#         fac, cpr, cdr, oas, dur, cvx, px, rtg, liq
# ---------------------------------------------------------------------------

def _build_pool_seeds() -> List[PoolSeed]:
    return [
        # ── FNMA Fixed 30YR ──────────────────────────────────────────────
        _pool("FN30A001","MBS","FNMA","30YR","FIXED","N/A",  2.50,3.10,320,40, 350,0.82,  8.0,0.0, 55,6.9,-1.8, 97.5,"AAA",9.0),
        _pool("FN30A002","MBS","FNMA","30YR","FIXED","N/A",  3.00,3.65,300,60, 425,0.75, 10.0,0.0, 65,6.4,-1.6, 96.8,"AAA",9.0),
        _pool("FN30A003","MBS","FNMA","30YR","FIXED","N/A",  3.50,4.10,280,80, 500,0.68, 12.0,0.0, 75,5.9,-1.4, 97.2,"AAA",9.0),
        _pool("FN30A004","MBS","FNMA","30YR","FIXED","N/A",  4.00,4.60,260,100,600,0.60, 15.0,0.0, 85,5.4,-1.2, 98.5,"AAA",9.0),
        _pool("FN30A005","MBS","FNMA","30YR","FIXED","N/A",  4.50,5.10,240,120,700,0.52, 18.0,0.0, 95,4.9,-1.0,100.0,"AAA",9.0),
        _pool("FN30A006","MBS","FNMA","30YR","FIXED","N/A",  5.00,5.65,220,140,800,0.45, 22.0,0.0,105,4.4,-0.8,101.5,"AAA",9.0),
        _pool("FN30A007","MBS","FNMA","30YR","FIXED","N/A",  5.50,6.15,200,160,900,0.38, 25.0,0.0,115,3.9,-0.6,103.0,"AAA",9.0),
        _pool("FN30A008","MBS","FNMA","30YR","FIXED","N/A",  6.00,6.65,180,180,750,0.32, 28.0,0.0,125,3.5,-0.4,104.5,"AAA",9.0),

        # ── FHLMC Fixed 15YR ─────────────────────────────────────────────
        _pool("FR15B001","MBS","FHLMC","15YR","FIXED","N/A", 2.50,3.05,160,20, 300,0.88, 10.0,0.0, 45,4.2,-0.9, 98.0,"AAA",8.5),
        _pool("FR15B002","MBS","FHLMC","15YR","FIXED","N/A", 3.00,3.55,140,40, 375,0.80, 12.0,0.0, 55,3.8,-0.7, 97.5,"AAA",8.5),
        _pool("FR15B003","MBS","FHLMC","15YR","FIXED","N/A", 3.50,4.05,120,60, 450,0.72, 14.0,0.0, 65,3.4,-0.5, 98.2,"AAA",8.5),
        _pool("FR15B004","MBS","FHLMC","15YR","FIXED","N/A", 4.00,4.55,100,80, 525,0.63, 16.0,0.0, 75,3.0,-0.4, 99.5,"AAA",8.5),
        _pool("FR15B005","MBS","FHLMC","15YR","FIXED","N/A", 4.50,5.05, 80,100,600,0.55, 18.0,0.0, 85,2.7,-0.3,101.0,"AAA",8.5),

        # ── GNMA Fixed 30YR ──────────────────────────────────────────────
        _pool("GN30C001","MBS","GNMA","30YR","FIXED","N/A",  3.00,3.50,310,50, 400,0.78,  8.0,0.0, 40,6.7,-1.7, 97.0,"AAA",8.8),
        _pool("GN30C002","MBS","GNMA","30YR","FIXED","N/A",  3.50,4.00,290,70, 480,0.70,  9.5,0.0, 50,6.2,-1.5, 97.5,"AAA",8.8),
        _pool("GN30C003","MBS","GNMA","30YR","FIXED","N/A",  4.00,4.50,270,90, 560,0.62, 11.0,0.0, 60,5.7,-1.3, 98.8,"AAA",8.8),
        _pool("GN30C004","MBS","GNMA","30YR","FIXED","N/A",  4.50,5.00,250,110,640,0.54, 13.5,0.0, 70,5.2,-1.1,100.2,"AAA",8.8),
        _pool("GN30C005","MBS","GNMA","30YR","FIXED","N/A",  5.00,5.55,230,130,720,0.47, 16.0,0.0, 80,4.7,-0.9,101.5,"AAA",8.8),

        # ── ARM Pools (FNMA) ──────────────────────────────────────────────
        _pool("FN5A_D001","MBS","FNMA","30YR","ARM","5/1",   3.25,3.80,300,24, 550,0.85, 18.0,0.0, 80,4.5, 0.3,100.5,"AAA",7.5),
        _pool("FN7A_D002","MBS","FNMA","30YR","ARM","7/1",   3.75,4.30,310,12, 625,0.90, 15.0,0.0, 90,5.0, 0.2, 99.8,"AAA",7.5),
        _pool("FN10AD003","MBS","FNMA","30YR","ARM","10/1",  4.25,4.85,320, 6, 700,0.95, 12.0,0.0, 95,5.5, 0.1, 99.2,"AAA",7.5),

        # ── CMBS Conduit ──────────────────────────────────────────────────
        _pool("CM_AAA_01","CMBS","PRIVATE","10YR","FIXED","N/A", 4.50,5.00,114, 6, 800,0.95, 2.5,1.0, 90,6.2, 0.4,101.0,"AAA",7.0),
        _pool("CM_AAA_02","CMBS","PRIVATE","10YR","FIXED","N/A", 5.00,5.60,108,12, 900,0.92, 2.8,1.2,100,5.8, 0.3,101.5,"AAA",7.0),
        _pool("CM_AA__01","CMBS","PRIVATE","10YR","FIXED","N/A", 5.25,5.85,102,18, 600,0.88, 3.0,1.5,130,5.5, 0.2,100.5,"AA", 6.0),
        _pool("CM_A___01","CMBS","PRIVATE","10YR","FIXED","N/A", 5.50,6.10, 96,24, 500,0.84, 3.2,1.8,170,5.2, 0.1, 99.8,"A",  5.5),
        _pool("CM_BBB_01","CMBS","PRIVATE","10YR","FIXED","N/A", 5.75,6.40, 90,30, 400,0.80, 3.5,2.0,220,4.9, 0.0, 98.5,"BBB",4.5),
        _pool("CM_AAA_03","CMBS","PRIVATE","10YR","FIXED","N/A", 4.75,5.30,120, 0,1000,1.00, 2.2,0.8, 85,6.5, 0.5,100.0,"AAA",7.0),
        _pool("CM_AA__02","CMBS","PRIVATE","10YR","FIXED","N/A", 5.00,5.60,114, 6, 700,0.96, 2.5,1.0,115,5.9, 0.3,100.8,"AA", 6.0),
        _pool("CM_A___02","CMBS","PRIVATE","10YR","FIXED","N/A", 5.50,6.15,108,12, 550,0.93, 2.8,1.3,155,5.6, 0.2, 99.5,"A",  5.5),

        # ── US Treasuries ─────────────────────────────────────────────────
        _pool("TSY_02YR","TREASURY","N/A","2YR","FIXED","N/A",  4.85,4.85, 24,0,2000,1.00,0.0,0.0,  0, 1.9, 0.04, 99.8,"N/A",10.0),
        _pool("TSY_05YR","TREASURY","N/A","5YR","FIXED","N/A",  4.50,4.50, 60,0,2000,1.00,0.0,0.0,  0, 4.4, 0.19, 99.1,"N/A",10.0),
        _pool("TSY_10YR","TREASURY","N/A","10YR","FIXED","N/A", 4.25,4.25,120,0,2500,1.00,0.0,0.0,  0, 8.0, 0.68, 98.5,"N/A",10.0),
        _pool("TSY_20YR","TREASURY","N/A","20YR","FIXED","N/A", 4.35,4.35,240,0,1500,1.00,0.0,0.0,  0,13.5, 1.92, 99.0,"N/A",10.0),
        _pool("TSY_30YR","TREASURY","N/A","30YR","FIXED","N/A", 4.38,4.38,360,0,1500,1.00,0.0,0.0,  0,18.0, 3.50, 98.2,"N/A",10.0),
    ]


# ---------------------------------------------------------------------------
# Projection engine
# ---------------------------------------------------------------------------

def _project_pool(seed: PoolSeed, n_months: int, rng: np.random.Generator) -> pd.DataFrame:
    """Simulate month-by-month balance runoff for a single pool."""
    dates = pd.date_range(start="2025-01-01", periods=n_months, freq="MS")

    monthly_cpr = seed.cpr_base / 100 / 12
    monthly_cdr = seed.cdr_base / 100 / 12
    monthly_rate = seed.wac / 100 / 12

    factor = seed.current_factor
    wam = seed.wam_initial
    wala = seed.wala_initial

    rows = []
    for i, dt in enumerate(dates):
        balance_mm = seed.original_balance * factor  # $MM

        # Scheduled principal (simplified constant-payment amortisation)
        if monthly_rate > 0 and wam > 0:
            # Payment = P × r / (1 - (1+r)^-n)
            pmt_rate = monthly_rate / (1 - (1 + monthly_rate) ** (-wam))
            sched_principal_rate = pmt_rate - monthly_rate   # interest subtracted
        else:
            sched_principal_rate = 1.0 / max(wam, 1)

        # Unscheduled prepayment (CPR with S-curve seasoning ramp over 30 months)
        ramp = min(1.0, wala / 30.0)
        effective_monthly_cpr = max(0.0, monthly_cpr * ramp * (1 + rng.normal(0, 0.05)))

        sched_prin = factor * sched_principal_rate
        prepay     = (factor - sched_prin) * effective_monthly_cpr
        default    = factor * monthly_cdr

        # Mild random-walk for market metrics over time
        noise_scale = i / n_months
        oas      = seed.oas_base      + rng.normal(0, 2.0) * noise_scale
        duration = seed.duration_initial * (1 - 0.003 * i) + rng.normal(0, 0.02)
        convexity = seed.convexity_initial + rng.normal(0, 0.01)
        price    = seed.price_initial + rng.normal(0, 0.05)

        rows.append({
            "date":                          dt,
            "cusip":                         seed.cusip,
            "product_type":                  seed.product_type,
            "agency":                        seed.agency,
            "term":                          seed.term,
            "rate_type":                     seed.rate_type,
            "arm_reset":                     seed.arm_reset,
            "coupon":                        seed.coupon,
            "wac":                           seed.wac,
            "wam":                           max(0, wam),
            "wala":                          wala,
            "original_balance_mm":           seed.original_balance,
            "current_factor":                round(factor, 6),
            "predicted_existing_balance_mm": round(seed.original_balance * factor, 4),
            "cpr_annual_pct":                round(effective_monthly_cpr * 12 * 100, 2),
            "cdr_annual_pct":                round(monthly_cdr * 12 * 100, 2),
            "oas_bps":                       round(oas, 1),
            "effective_duration":            round(max(0.1, duration), 3),
            "convexity":                     round(convexity, 4),
            "price":                         round(price, 4),
            "yield_pct":                     round(seed.coupon + oas / 100, 3),
            "credit_rating":                 seed.credit_rating,
            "liquidity_score":               seed.liquidity_score,
        })

        # Advance factor
        factor = max(0.0, factor - sched_prin - prepay - default)
        wam    = max(0, wam - 1)
        wala  += 1

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Portfolio-level projection
# ---------------------------------------------------------------------------

def _build_portfolio_df(pool_df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate pool-level predicted balances and add a strategic target balance.
    new_volume = target - predicted_existing.
    """
    dates = sorted(pool_df["date"].unique())
    n = len(dates)

    existing = (
        pool_df.groupby("date")["predicted_existing_balance_mm"]
        .sum()
        .reset_index()
    )

    # S-curve growth: target starts 5% above initial existing balance and
    # grows 45% over 10 years, so new_volume is always positive from month 1.
    existing = existing.sort_values("date").reset_index(drop=True)
    initial_existing = float(existing.iloc[0]["predicted_existing_balance_mm"])
    target_start = initial_existing * 1.05   # 5% above existing at t=0
    target_end   = initial_existing * 1.50   # 50% growth over 10 years

    t = np.linspace(0, 1, n)
    target = target_start + (target_end - target_start) * (3 * t**2 - 2 * t**3)

    existing["target_total_balance_mm"]      = np.round(target, 2)
    existing["new_volume_mm"]                = np.round(
        existing["target_total_balance_mm"] - existing["predicted_existing_balance_mm"], 2
    )
    existing["new_volume_12m_rolling_mm"] = (
        existing["new_volume_mm"].rolling(12, min_periods=1).sum().round(2)
    )

    return existing[[
        "date", "target_total_balance_mm",
        "predicted_existing_balance_mm", "new_volume_mm",
        "new_volume_12m_rolling_mm",
    ]]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_sample_data(
    n_months: int = 120,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Returns:
        pool_universe_df  : (cusip × month) DataFrame  — shape ≈ 4080 × 23
        portfolio_df      : monthly portfolio projections — shape 120 × 5
    """
    rng = np.random.default_rng(seed)
    pool_seeds = _build_pool_seeds()

    pool_frames = [_project_pool(s, n_months, rng) for s in pool_seeds]
    pool_df = pd.concat(pool_frames, ignore_index=True)
    pool_df = pool_df.sort_values(["date", "cusip"]).reset_index(drop=True)

    portfolio_df = _build_portfolio_df(pool_df)
    return pool_df, portfolio_df


def get_pool_summary(pool_df: pd.DataFrame, as_of_date=None) -> pd.DataFrame:
    """Return the most-recent snapshot of each CUSIP."""
    if as_of_date is None:
        as_of_date = pool_df["date"].max()
    return pool_df[pool_df["date"] == as_of_date].copy().reset_index(drop=True)


if __name__ == "__main__":
    pool_df, portfolio_df = generate_sample_data()
    print("=== Pool Universe (first 5 rows) ===")
    print(pool_df.head())
    print(f"\nShape: {pool_df.shape}  |  CUSIPs: {pool_df['cusip'].nunique()}")
    print("\n=== Portfolio Projections (first 12 months) ===")
    print(portfolio_df.head(12).to_string(index=False))
