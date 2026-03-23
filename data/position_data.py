"""
data/position_data.py

Historical portfolio position data — 8 agency MBS pools from universe_1000.
Six monthly snapshots aligned with universe_1000 dates:
  2025-09-30, 2025-10-31, 2025-11-28, 2025-12-31, 2026-01-31, 2026-02-28

Snapshot columns:
  snapshot_date, cusip, pool_id, product_type, coupon,
  par_value, current_balance, pool_factor,
  market_price, market_value, book_value, book_price,
  book_yield, oas_bps, oad_years, convexity,
  unrealized_pnl, unrealized_pnl_pct, monthly_income, cpr,
  wala, wam, ltv, fico, pct_ca, pct_purchase, loan_size
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from datetime import date

# ── Portfolio composition (8 pools, total par ~$3.0B) ─────────────────────────
# Each tuple: (cusip, pool_id, product_type, coupon_pct, par_value_$)
PORTFOLIO_POOLS = [
    ("3140X7GK4", "FNMA_CC30_6.0_A",  "CC30", 6.0, 600_000_000),
    ("3132DXXX1", "FHLMC_CC30_5.5_B", "CC30", 5.5, 550_000_000),
    ("36179MFD3", "GNMA_GN30_6.0_C",  "GN30", 6.0, 460_000_000),
    ("3140XTTT9", "FNMA_CC15_5.5_D",  "CC15", 5.5, 400_000_000),
    ("3132DYYY2", "FHLMC_CC15_6.0_E", "CC15", 6.0, 310_000_000),
    ("36179MHH1", "GNMA_GN30_5.5_F",  "GN30", 5.5, 270_000_000),
    ("3140XZZZ3", "FNMA_CC30_6.5_G",  "CC30", 6.5, 230_000_000),
    ("3132DAAA4", "GNMA_GN15_5.5_H",  "GN15", 5.5, 200_000_000),
    ("3140XARM1", "FNMA_ARM_5.5_I",   "ARM",  5.5, 150_000_000),
    ("91282CJX5", "UST_TSY_4.5_J",    "TSY",  4.5, 200_000_000),
    ("CM0000001", "CMBS_AAA_5.0_K",   "CMBS", 5.0, 120_000_000),
    ("17000CMO1", "FNMA_CMO_5.5_L",   "CMO",  5.5, 100_000_000),
    ("CD0000001", "FHLB_CDBT_4.0_M",  "CDBT", 4.0, 180_000_000),
]

SNAPSHOT_DATES = [
    date(2025, 9, 30),
    date(2025, 10, 31),
    date(2025, 11, 28),
    date(2025, 12, 31),
    date(2026, 1, 31),
    date(2026, 2, 28),
]

# 10Y Treasury rate for each snapshot (bps shift from baseline 4.60%)
_RATE_10Y = {
    date(2025, 9,  30): 4.62,
    date(2025, 10, 31): 4.41,
    date(2025, 11, 28): 4.22,
    date(2025, 12, 31): 4.55,
    date(2026, 1,  31): 4.37,
    date(2026, 2,  28): 4.46,
}

# Pool-level fixed characteristics (wala at first snapshot, etc.)
_POOL_CHARS = {
    "FNMA_CC30_6.0_A":  dict(wala_0=18, wam_0=342, ltv=0.72, fico=762, pct_ca=0.28, pct_purchase=0.58, loan_size=385_000),
    "FHLMC_CC30_5.5_B": dict(wala_0=22, wam_0=338, ltv=0.75, fico=748, pct_ca=0.22, pct_purchase=0.62, loan_size=320_000),
    "GNMA_GN30_6.0_C":  dict(wala_0=14, wam_0=346, ltv=0.95, fico=700, pct_ca=0.18, pct_purchase=0.72, loan_size=280_000),
    "FNMA_CC15_5.5_D":  dict(wala_0=20, wam_0=160, ltv=0.68, fico=780, pct_ca=0.30, pct_purchase=0.52, loan_size=410_000),
    "FHLMC_CC15_6.0_E": dict(wala_0=16, wam_0=164, ltv=0.70, fico=758, pct_ca=0.26, pct_purchase=0.55, loan_size=360_000),
    "GNMA_GN30_5.5_F":  dict(wala_0=26, wam_0=334, ltv=0.96, fico=695, pct_ca=0.15, pct_purchase=0.75, loan_size=260_000),
    "FNMA_CC30_6.5_G":  dict(wala_0=10, wam_0=350, ltv=0.74, fico=755, pct_ca=0.24, pct_purchase=0.60, loan_size=340_000),
    "GNMA_GN15_5.5_H":  dict(wala_0=30, wam_0=150, ltv=0.94, fico=705, pct_ca=0.12, pct_purchase=0.70, loan_size=250_000),
    "FNMA_ARM_5.5_I":   dict(wala_0=12, wam_0=84,  ltv=0.78, fico=740, pct_ca=0.25, pct_purchase=0.45, loan_size=550_000),
    "UST_TSY_4.5_J":    dict(wala_0=0,  wam_0=96,  ltv=0.0,  fico=0,   pct_ca=0.0,  pct_purchase=0.0,  loan_size=5_000_000),
    "CMBS_AAA_5.0_K":   dict(wala_0=6,  wam_0=114, ltv=0.65, fico=0,   pct_ca=0.15, pct_purchase=0.0,  loan_size=10_000_000),
    "FNMA_CMO_5.5_L":   dict(wala_0=24, wam_0=180, ltv=0.72, fico=740, pct_ca=0.20, pct_purchase=0.50, loan_size=400_000),
    "FHLB_CDBT_4.0_M":  dict(wala_0=0,  wam_0=60,  ltv=0.0,  fico=0,   pct_ca=0.0,  pct_purchase=0.0,  loan_size=20_000_000),
}

# Book prices at initial purchase (Sep 2025)
_BOOK_PRICE_0 = {
    "FNMA_CC30_6.0_A":  101.25,
    "FHLMC_CC30_5.5_B":  99.50,
    "GNMA_GN30_6.0_C":  101.75,
    "FNMA_CC15_5.5_D":  100.80,
    "FHLMC_CC15_6.0_E": 101.20,
    "GNMA_GN30_5.5_F":   99.00,
    "FNMA_CC30_6.5_G":  102.50,
    "GNMA_GN15_5.5_H":  100.40,
    "FNMA_ARM_5.5_I":   100.25,
    "UST_TSY_4.5_J":     99.80,
    "CMBS_AAA_5.0_K":   100.50,
    "FNMA_CMO_5.5_L":   100.75,
    "FHLB_CDBT_4.0_M":   99.90,
}

# OAS baseline (bps) for each pool
_OAS_BASE = {
    "FNMA_CC30_6.0_A":  52, "FHLMC_CC30_5.5_B": 47, "GNMA_GN30_6.0_C": 38,
    "FNMA_CC15_5.5_D":  41, "FHLMC_CC15_6.0_E": 43, "GNMA_GN30_5.5_F": 36,
    "FNMA_CC30_6.5_G":  55, "GNMA_GN15_5.5_H":  34,
    "FNMA_ARM_5.5_I":   80, "UST_TSY_4.5_J":     5, "CMBS_AAA_5.0_K": 110,
    "FNMA_CMO_5.5_L":   65, "FHLB_CDBT_4.0_M":   8,
}

_DURATION_BASE = {
    "CC30": 4.8, "GN30": 4.5, "CC15": 3.2, "GN15": 3.0,
    "ARM": 2.5, "TSY": 5.0, "CMBS": 5.5, "CMO": 4.0, "CDBT": 3.5,
}


def _build_snapshot_rows() -> list[dict]:
    rng = np.random.default_rng(42)
    rows = []
    baseline_10y = _RATE_10Y[SNAPSHOT_DATES[0]]

    for cusip, pool_id, ptype, coupon, par_value in PORTFOLIO_POOLS:
        chars = _POOL_CHARS[pool_id]
        book_price_0 = _BOOK_PRICE_0[pool_id]
        oas_base = _OAS_BASE[pool_id]
        dur_base = _DURATION_BASE[ptype]
        book_yield_base = coupon * 0.97 + rng.uniform(-0.03, 0.03)  # book yield ≈ coupon - amort adj

        for i, snap_date in enumerate(SNAPSHOT_DATES):
            rate_10y = _RATE_10Y[snap_date]
            rate_delta = rate_10y - baseline_10y

            # Pool factor: ~0.4%/month amortization + prepayments
            monthly_decay = 0.004 + rng.uniform(0, 0.001)
            pool_factor = max(0.80, 1.0 - i * monthly_decay)
            current_balance = par_value * pool_factor

            # WALA / WAM at snapshot
            wala = chars["wala_0"] + i
            wam  = max(1, chars["wam_0"] - i)

            # Market price: price = book_price_0 - duration * rate_change
            market_price = (book_price_0 - dur_base * rate_delta
                            + rng.uniform(-0.12, 0.12))

            market_value = current_balance * market_price / 100

            # Book value: amortize premium/discount toward par slowly
            amort_frac = i / (len(SNAPSHOT_DATES) - 1) * 0.12
            book_price = book_price_0 + (100.0 - book_price_0) * amort_frac
            book_value = current_balance * book_price / 100

            unrealized_pnl = market_value - book_value
            unrealized_pnl_pct = unrealized_pnl / book_value * 100 if book_value else 0.0

            # CPR: zero for non-prepaying product types
            if ptype in ("TSY", "CDBT", "CMBS"):
                cpr = 0.0
            elif ptype == "ARM":
                refi = coupon - (rate_10y + 1.0)
                cpr = max(5.0, min(30.0, 15.0 + max(0.0, refi) * 4.0 + rng.uniform(-1.0, 1.0)))
            else:
                refi = coupon - (rate_10y + 1.5)  # net coupon vs mortgage rate
                cpr = max(3.0, min(38.0, 8.0 + max(0.0, refi) * 5.5 + rng.uniform(-0.8, 0.8)))

            # OAS / OAD
            oas_bps  = oas_base + rate_delta * 2.5 + rng.uniform(-4, 4)
            oad_years = dur_base - rate_delta * 0.3 + rng.uniform(-0.08, 0.08)

            convexity = -0.80 + rng.uniform(-0.15, 0.15)
            book_yield = book_yield_base + rng.uniform(-0.02, 0.02)
            monthly_income = current_balance * book_yield / 100 / 12

            rows.append({
                "snapshot_date":      snap_date,
                "cusip":              cusip,
                "pool_id":            pool_id,
                "product_type":       ptype,
                "coupon":             coupon,
                "par_value":          par_value,
                "current_balance":    round(current_balance),
                "pool_factor":        round(pool_factor, 4),
                "market_price":       round(market_price, 4),
                "market_value":       round(market_value),
                "book_value":         round(book_value),
                "book_price":         round(book_price, 4),
                "book_yield":         round(book_yield, 4),
                "oas_bps":            round(oas_bps, 1),
                "oad_years":          round(oad_years, 3),
                "convexity":          round(convexity, 3),
                "unrealized_pnl":     round(unrealized_pnl),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 3),
                "monthly_income":     round(monthly_income),
                "cpr":                round(cpr, 2),
                "wala":               wala,
                "wam":                wam,
                "ltv":                chars["ltv"],
                "fico":               chars["fico"],
                "pct_ca":             chars["pct_ca"],
                "pct_purchase":       chars["pct_purchase"],
                "loan_size":          chars["loan_size"],
            })
    return rows


_DF_CACHE: pd.DataFrame | None = None


def _get_df() -> pd.DataFrame:
    global _DF_CACHE
    if _DF_CACHE is None:
        _DF_CACHE = pd.DataFrame(_build_snapshot_rows())
    return _DF_CACHE


def get_position_data(as_of_date: date | None = None) -> pd.DataFrame:
    """
    Return portfolio position data.

    Parameters
    ----------
    as_of_date : date | None
        If None, returns all 6 historical snapshots.
        If provided, returns the latest snapshot on or before that date.
    """
    df = _get_df().copy()
    if as_of_date is not None:
        valid = [d for d in SNAPSHOT_DATES if d <= as_of_date]
        use_date = max(valid) if valid else SNAPSHOT_DATES[0]
        df = df[df["snapshot_date"] == use_date].copy()
    return df


def get_portfolio_summary(as_of_date: date | None = None) -> dict:
    """Compute portfolio-level summary from position data."""
    pos = get_position_data(as_of_date)
    if pos.empty:
        return {}
    if as_of_date is None:
        pos = pos[pos["snapshot_date"] == pos["snapshot_date"].max()].copy()

    total_mv   = pos["market_value"].sum()
    total_bv   = pos["book_value"].sum()
    total_inc  = pos["monthly_income"].sum() * 12

    def wavg(col: str) -> float:
        w = pos["market_value"]
        return float((pos[col] * w).sum() / w.sum()) if w.sum() > 0 else 0.0

    # Month-over-month NAV change
    df_all = _get_df()
    dates  = sorted(df_all["snapshot_date"].unique())
    nav_prev = None
    if as_of_date is None or max(d for d in SNAPSHOT_DATES if d <= as_of_date) != dates[0]:
        cur_date = pos["snapshot_date"].iloc[0]
        prev_dates = [d for d in dates if d < cur_date]
        if prev_dates:
            prev = df_all[df_all["snapshot_date"] == max(prev_dates)]
            nav_prev = prev["market_value"].sum()

    nav_chg_pct = ((total_mv - nav_prev) / nav_prev * 100) if nav_prev else 0.0

    return {
        "nav":           total_mv,
        "nav_chg":       round(nav_chg_pct, 2),
        "book_value":    total_bv,
        "book_yield":    round(wavg("book_yield"), 4),
        "book_yield_chg": 0.0,  # can be computed if needed
        "oad":           round(wavg("oad_years"), 2),
        "oad_chg":       0.0,
        "oas":           round(wavg("oas_bps")),
        "oas_chg":       0,
        "convexity":     round(wavg("convexity"), 2),
        "annual_income": total_inc,
        "unrealized_pnl": pos["unrealized_pnl"].sum(),
        "n_positions":   len(pos),
    }


def get_historical_nav() -> list[dict]:
    """Return portfolio NAV for each historical snapshot date."""
    df = _get_df()
    result = []
    for snap_date in SNAPSHOT_DATES:
        d = df[df["snapshot_date"] == snap_date]
        if d.empty:
            continue
        result.append({
            "date":  snap_date,
            "nav":   d["market_value"].sum(),
            "book":  d["book_value"].sum(),
            "income": d["monthly_income"].sum(),
        })
    return result
