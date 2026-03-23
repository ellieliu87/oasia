"""
Prepayment Model Tool
=====================
Forecasts conditional prepayment rates (CPR) for MBS pools over 30 years
on a monthly basis across 256 simulated rate paths.

The prepayment model accounts for:
  - Refinancing incentive  (WAC vs. current mortgage rate — S-curve)
  - Seasoning ramp         (PSA-style linear ramp over first 30 months)
  - Burnout                (cumulative excess refi incentive)
  - Credit/geography       (LTV, FICO, CA concentration, purchase %)
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "forecast_prepayment",
            "description": (
                "Forecast conditional prepayment rates (CPR, % annualized) for an MBS pool "
                "over 30 years (360 monthly periods) across 256 simulated interest-rate paths.  "
                "Returns mean CPR by year, path-level statistics, and lifetime CPR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {
                        "type": "string",
                        "description": "Pool identifier or CUSIP from the universe.",
                    },
                    "wac": {
                        "type": "number",
                        "description": "Weighted average coupon (decimal, e.g. 0.065).  "
                                       "Overrides the pool record if provided.",
                    },
                    "wala": {
                        "type": "integer",
                        "description": "Weighted average loan age in months.  "
                                       "Overrides the pool record if provided.",
                    },
                    "wam": {
                        "type": "integer",
                        "description": "Weighted average maturity in months remaining.  "
                                       "Overrides the pool record if provided.",
                    },
                    "ltv": {
                        "type": "number",
                        "description": "Loan-to-value ratio (decimal).  Override.",
                    },
                    "fico": {
                        "type": "integer",
                        "description": "FICO score.  Override.",
                    },
                    "pct_ca": {
                        "type": "number",
                        "description": "California concentration (decimal).  Override.",
                    },
                    "pct_purchase": {
                        "type": "number",
                        "description": "Purchase-loan fraction (decimal).  Override.",
                    },
                    "cpr_override": {
                        "type": "number",
                        "description": "Constant CPR assumption (%, e.g. 10 for 10 CPR).  "
                                       "Overrides the model entirely.",
                    },
                    "psa_override": {
                        "type": "number",
                        "description": "PSA multiple (e.g. 150 for 150 PSA).  "
                                       "Overrides the model.",
                    },
                    "rate_shock_bps": {
                        "type": "integer",
                        "description": "Parallel rate shock applied before simulation (bps, default 0).",
                    },
                    "as_of_date": {
                        "type": "string",
                        "description": "YYYY-MM-DD (default: today).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_prepayment_scenarios",
            "description": (
                "Run the prepayment model under multiple rate scenarios "
                "(base, up 100/200/300, down 100/200/300 bps) and return CPR by scenario.  "
                "Useful for quantifying prepayment sensitivity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {"type": "string"},
                    "as_of_date": {"type": "string"},
                },
                "required": [],
            },
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_pool_chars(inp: dict):
    """Return PoolCharacteristics, using pool_id lookup with field overrides."""
    from analytics.prepay import PoolCharacteristics

    # Start from defaults or pool lookup
    base: dict[str, Any] = dict(
        coupon=0.060, wac=0.065, wala=24, wam=336,
        loan_size=400_000, ltv=0.75, fico=750,
        pct_ca=0.15, pct_purchase=0.65,
        product_type="CC30", pool_id="", current_balance=1_000_000,
    )

    pool_id = inp.get("pool_id", "")
    if pool_id:
        try:
            from data.universe_1000 import get_universe_1000, screen_universe
            univ = get_universe_1000()
            row = univ[
                (univ["pool_id"] == pool_id) | (univ["cusip"] == pool_id)
            ]
            if not row.empty:
                r = row.iloc[0]
                base.update(
                    coupon=float(r["coupon"]) / 100.0 if float(r["coupon"]) > 1 else float(r["coupon"]),
                    wac=float(r["wac"]) / 100.0 if float(r["wac"]) > 1 else float(r["wac"]),
                    wala=int(r["wala_at_issue"]),
                    wam=int(r["original_wam"]) - int(r["wala_at_issue"]),
                    loan_size=float(r["loan_size"]),
                    ltv=float(r["ltv"]),
                    fico=int(r["fico"]),
                    pct_ca=float(r["pct_ca"]),
                    pct_purchase=float(r["pct_purchase"]),
                    product_type=str(r["product_type"]),
                    pool_id=pool_id,
                    current_balance=float(r["original_balance"]),
                )
        except Exception:
            # Fall back to legacy pool_universe
            try:
                from data.pool_universe import get_pool_universe
                univ = get_pool_universe()
                row = univ[univ["pool_id"] == pool_id]
                if not row.empty:
                    r = row.iloc[0]
                    base.update(
                        coupon=float(r["coupon"]), wac=float(r["wac"]),
                        wala=int(r["wala"]), wam=int(r["wam"]),
                        loan_size=float(r["loan_size"]), ltv=float(r["ltv"]),
                        fico=int(r["fico"]), pct_ca=float(r["pct_ca"]),
                        pct_purchase=float(r["pct_purchase"]),
                        product_type=str(r["product_type"]),
                        pool_id=pool_id, current_balance=float(r["current_balance"]),
                    )
            except Exception:
                pass
        base["pool_id"] = pool_id

    # Apply explicit overrides
    for field in ["wac", "wala", "wam", "ltv", "fico", "pct_ca", "pct_purchase"]:
        if field in inp:
            base[field] = inp[field]

    return PoolCharacteristics(**base)


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_forecast_prepayment(inp: dict) -> str:
    import numpy as np
    from datetime import datetime, date as date_type
    from data.market_data import load_market_data
    from analytics.rate_paths import generate_rate_paths, TermStructure
    from analytics.prepay import PrepayModel, project_prepay_speeds
    from db.cache import read_prepay, write_prepay

    pool_chars  = _resolve_pool_chars(inp)
    date_str    = inp.get("as_of_date", "")
    as_of       = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date_type.today()
    shock_bps   = int(inp.get("rate_shock_bps", 0))
    n_paths     = 256
    pool_id     = pool_chars.pool_id or "custom"

    # Skip cache if explicit overrides are in play
    use_cache = (
        inp.get("cpr_override") is None
        and inp.get("psa_override") is None
        and pool_id != "custom"
    )

    # ── Cache check ────────────────────────────────────────────────────────
    if use_cache:
        cached = read_prepay(pool_id, as_of, shock_bps, n_paths)
        if cached:
            cached["message"] = (
                f"CPR forecast for {pool_id}: "
                f"lifetime {cached['lifetime_cpr_pct']:.1f}% (from cache)."
            )
            return json.dumps(cached, default=str)

    # ── Compute ────────────────────────────────────────────────────────────
    md    = load_market_data(as_of)
    curve = md.sofr_curve
    if shock_bps:
        curve = TermStructure(
            tenors=curve.tenors,
            rates=curve.rates + shock_bps / 10_000.0,
        )

    rp = generate_rate_paths(curve=curve, n_paths=n_paths, n_periods=360, seed=42)

    cpr_override = inp.get("cpr_override")
    psa_override = inp.get("psa_override")
    if cpr_override is not None:
        cpr_override = float(cpr_override) / 100.0
    if psa_override is not None:
        psa_override = float(psa_override)

    cpr_paths = project_prepay_speeds(
        pool=pool_chars, rate_paths=rp, model=PrepayModel(),
        cpr_override=cpr_override, psa_override=psa_override,
    )

    mean_cpr = np.mean(cpr_paths, axis=0)
    annual_cpr: list[dict] = []
    for yr in range(1, 31):
        s, e = (yr - 1) * 12, yr * 12
        if s < len(mean_cpr):
            annual_cpr.append({
                "year":        yr,
                "mean_cpr_pct": round(float(np.mean(mean_cpr[s:e])) * 100, 2),
                "p10_cpr_pct":  round(float(np.mean(np.percentile(cpr_paths[:, s:e], 10, axis=0))) * 100, 2),
                "p90_cpr_pct":  round(float(np.mean(np.percentile(cpr_paths[:, s:e], 90, axis=0))) * 100, 2),
            })

    lifetime_cpr = float(np.mean(cpr_paths)) * 100.0
    peak_cpr_yr  = int(np.argmax([r["mean_cpr_pct"] for r in annual_cpr])) + 1

    out = {
        "pool_id":          pool_id,
        "wac_pct":          round(pool_chars.wac * 100, 3),
        "wala_months":      pool_chars.wala,
        "wam_months":       pool_chars.wam,
        "shock_bps":        shock_bps,
        "n_paths":          n_paths,
        "n_periods":        360,
        "lifetime_cpr_pct": round(lifetime_cpr, 2),
        "peak_cpr_year":    peak_cpr_yr,
        "annual_cpr":       annual_cpr,
        "message": (
            f"CPR forecast for {pool_id or 'custom pool'}: "
            f"lifetime {lifetime_cpr:.1f}%, peaks in year {peak_cpr_yr}."
        ),
    }

    # ── Write to cache ─────────────────────────────────────────────────────
    if use_cache:
        try:
            write_prepay(pool_id, as_of, shock_bps, n_paths, out)
        except Exception:
            pass

    return json.dumps(out, default=str)


def _handle_compare_prepayment_scenarios(inp: dict) -> str:
    import numpy as np
    from datetime import datetime
    from data.market_data import load_market_data
    from analytics.rate_paths import generate_rate_paths, TermStructure
    from analytics.prepay import PrepayModel, project_prepay_speeds

    pool_chars = _resolve_pool_chars(inp)
    date_str   = inp.get("as_of_date", "")
    as_of      = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
    md         = load_market_data(as_of)
    shocks     = [-300, -200, -100, 0, 100, 200, 300]
    results: dict[str, Any] = {
        "pool_id":    pool_chars.pool_id,
        "scenarios":  {},
    }

    for shock in shocks:
        curve = md.sofr_curve
        if shock:
            curve = TermStructure(
                tenors=curve.tenors,
                rates=curve.rates + shock / 10_000.0,
            )
        rp = generate_rate_paths(curve=curve, n_paths=128, n_periods=360, seed=42)
        cpr = project_prepay_speeds(pool=pool_chars, rate_paths=rp, model=PrepayModel())
        mean_cpr = np.mean(cpr, axis=0)
        results["scenarios"][str(shock)] = {
            "lifetime_cpr_pct": round(float(np.mean(mean_cpr)) * 100, 2),
            "yr1_cpr_pct":      round(float(np.mean(mean_cpr[:12]))  * 100, 2),
            "yr3_cpr_pct":      round(float(np.mean(mean_cpr[:36]))  * 100, 2),
            "yr5_cpr_pct":      round(float(np.mean(mean_cpr[:60]))  * 100, 2),
            "yr10_cpr_pct":     round(float(np.mean(mean_cpr[:120])) * 100, 2),
        }

    return json.dumps(results, default=str)


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "forecast_prepayment":            _handle_forecast_prepayment,
    "compare_prepayment_scenarios":   _handle_compare_prepayment_scenarios,
}
