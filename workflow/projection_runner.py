"""
workflow/projection_runner.py

ProjectionRunner — for each portfolio position, uses the prepayment model
(PrepayModel.predict) and Hull-White rate paths to compute 30-year monthly
cash-flow projections, then persists results to DuckDB.

Called automatically at the end of each WorkflowRunner.run().
"""
from __future__ import annotations

import logging
from datetime import date

import numpy as np

logger = logging.getLogger("nexus.workflow.projection")


def run_projections(
    as_of_date: date | None = None,
    n_paths: int = 64,
) -> bool:
    """
    Compute 30-year monthly projections for all portfolio positions.

    Parameters
    ----------
    as_of_date : date | None
        Projection start date (defaults to today).
    n_paths : int
        Monte Carlo paths for Hull-White model.

    Returns
    -------
    bool — True on success.
    """
    from datetime import date as date_cls
    from dateutil.relativedelta import relativedelta

    if as_of_date is None:
        as_of_date = date_cls.today()

    try:
        from data.position_data import get_position_data
        from data.market_data import get_current_market_data
        from analytics.prepay import PrepayModel, PoolCharacteristics
        from analytics.rate_paths import generate_rate_paths
        from db.projections import write_portfolio_projections, write_pool_projections
    except ImportError as e:
        logger.error("Projection runner import error: %s", e)
        return False

    positions = get_position_data(as_of_date)
    if positions.empty:
        logger.warning("No position data for %s — skipping projections", as_of_date)
        return False

    # ── Rate paths ────────────────────────────────────────────────────────────
    try:
        md = get_current_market_data()
        rp = generate_rate_paths(
            md.sofr_curve, n_paths=n_paths, n_periods=360, seed=42
        )
        current_mortgage_rate = md.sofr_curve.zero_rate(5.0) * 100 + 1.5
    except Exception as e:
        logger.warning("Market data unavailable (%s) — using fallback rates", e)
        # Fallback: create stub rate paths with flat 4.5% short rate
        from analytics.rate_paths import RatePaths
        sr = np.full((n_paths, 360), 0.045, dtype=float)
        rp = RatePaths(short_rates=sr, dt=1 / 12)
        current_mortgage_rate = 6.0

    prepay_model = PrepayModel()
    n_periods = 360

    pool_cashflows: dict[str, dict] = {}

    for _, pos in positions.iterrows():
        pool_id = pos["pool_id"]
        try:
            chars = PoolCharacteristics(
                coupon=float(pos["coupon"]) / 100,   # decimal
                wac=(float(pos["coupon"]) + 0.5) / 100,
                wala=int(pos.get("wala", 24)),
                wam=int(pos.get("wam", 336)),
                loan_size=float(pos.get("loan_size", 300_000)),
                ltv=float(pos.get("ltv", 0.75)),
                fico=int(pos.get("fico", 750)),
                pct_ca=float(pos.get("pct_ca", 0.25)),
                pct_purchase=float(pos.get("pct_purchase", 0.60)),
                product_type=str(pos["product_type"]),
                pool_id=pool_id,
                original_balance=float(pos["par_value"]),
                current_balance=float(pos["current_balance"]),
            )

            # CPR vectors: shape (n_paths, n_periods), values in [0, 1]
            cpr_vectors = prepay_model.predict(chars, rp)

            current_bal = np.full(n_paths, float(pos["current_balance"]))
            coupon_monthly = float(pos["coupon"]) / 100 / 12

            interest_arr   = np.zeros(n_periods)
            principal_arr  = np.zeros(n_periods)
            balance_arr    = np.zeros(n_periods)
            cpr_arr        = np.zeros(n_periods)

            for t in range(n_periods):
                monthly_int = current_bal * coupon_monthly
                wam_t = max(1, int(pos.get("wam", 360)) - t)
                sched_prin = current_bal / wam_t
                cpr_t = cpr_vectors[:, t] if t < cpr_vectors.shape[1] else np.full(n_paths, 0.06)
                smm = 1.0 - (1.0 - cpr_t) ** (1.0 / 12.0)
                prepay_prin = current_bal * smm
                total_prin = np.minimum(sched_prin + prepay_prin, current_bal)
                current_bal = np.maximum(0.0, current_bal - total_prin)

                interest_arr[t]  = monthly_int.mean()
                principal_arr[t] = total_prin.mean()
                balance_arr[t]   = current_bal.mean()
                cpr_arr[t]       = cpr_t.mean()

            pool_cashflows[pool_id] = {
                "interest":   interest_arr,
                "principal":  principal_arr,
                "balance":    balance_arr,
                "cpr":        cpr_arr,
                "oas_bps":    float(pos.get("oas_bps", 50)),
                "oad_years":  float(pos.get("oad_years", 4.5)),
                "book_yield": float(pos.get("book_yield", 5.8)),
                "market_price": float(pos.get("market_price", 100.0)),
            }

        except Exception as ex:
            logger.warning("Projection failed for %s: %s", pool_id, ex)

    if not pool_cashflows:
        logger.error("All pool projections failed")
        return False

    # ── Aggregate to portfolio level ─────────────────────────────────────────
    portfolio_interest  = sum(v["interest"]  for v in pool_cashflows.values())
    portfolio_principal = sum(v["principal"] for v in pool_cashflows.values())

    # Pool index for fast lookup of market_price
    pos_index = {row["pool_id"]: row for _, row in positions.iterrows()}

    portfolio_nav   = np.zeros(n_periods)
    portfolio_oad   = np.zeros(n_periods)
    portfolio_oas   = np.zeros(n_periods)
    portfolio_yield = np.zeros(n_periods)

    for t in range(n_periods):
        nav_t = oad_wt = oas_wt = yld_wt = 0.0
        for pid, cf in pool_cashflows.items():
            bal_t = cf["balance"][t]
            if bal_t <= 0:
                continue
            p = pos_index.get(pid, {})
            mkt_px = p.get("market_price", 100.0) if hasattr(p, "get") else 100.0
            mv_t   = bal_t * float(mkt_px) / 100.0
            nav_t   += mv_t
            oad_wt  += cf["oad_years"] * mv_t
            oas_wt  += cf["oas_bps"]   * mv_t
            yld_wt  += cf["book_yield"] * mv_t
        portfolio_nav[t]   = nav_t
        if nav_t > 0:
            portfolio_oad[t]   = oad_wt / nav_t
            portfolio_oas[t]   = oas_wt / nav_t
            portfolio_yield[t] = yld_wt / nav_t

    # ── Build date list ───────────────────────────────────────────────────────
    proj_dates = [as_of_date + relativedelta(months=t + 1) for t in range(n_periods)]

    # ── Write portfolio projections ───────────────────────────────────────────
    portfolio_rows = [
        {
            "run_date":           as_of_date,
            "month_offset":       t + 1,
            "projection_date":    proj_dates[t],
            "portfolio_nav":      float(portfolio_nav[t]),
            "interest_income":    float(portfolio_interest[t]),
            "principal_cashflow": float(portfolio_principal[t]),
            "total_cashflow":     float(portfolio_interest[t] + portfolio_principal[t]),
            "book_yield":         float(portfolio_yield[t] * 100 if portfolio_yield[t] < 1.0 else portfolio_yield[t]),
            "oad":                float(portfolio_oad[t]),
            "oas":                float(portfolio_oas[t]),
        }
        for t in range(n_periods)
    ]

    pool_rows = [
        {
            "run_date":           as_of_date,
            "pool_id":            pid,
            "month_offset":       t + 1,
            "projection_date":    proj_dates[t],
            "balance":            float(cf["balance"][t]),
            "interest_income":    float(cf["interest"][t]),
            "principal_cashflow": float(cf["principal"][t]),
            "cpr":                float(cf["cpr"][t]),
        }
        for pid, cf in pool_cashflows.items()
        for t in range(n_periods)
    ]

    write_portfolio_projections(portfolio_rows)
    write_pool_projections(pool_rows)

    logger.info(
        "Projections stored: run_date=%s, pools=%d, periods=%d",
        as_of_date, len(pool_cashflows), n_periods,
    )
    return True
