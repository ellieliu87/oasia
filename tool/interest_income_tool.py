"""
Interest Income Tool
====================
Calculates projected interest income for MBS pools under:
  - BAU (Business-As-Usual): current term structure, no shock
  - Rate shock scenarios: parallel shifts ±100, ±200, ±300 bps

Interest income is derived from the cash-flow projections (coupon payments
on the outstanding balance) across the prepayment-model-driven amortization
schedule.  Both total interest income and net interest income (after financing
cost) can be reported.
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "compute_interest_income",
            "description": (
                "Calculate projected interest income for an MBS pool under the BAU "
                "rate scenario and optional rate-shock scenarios.  "
                "Reports annual and cumulative income, net interest margin, and "
                "income sensitivity across shocks."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {
                        "type": "string",
                        "description": "Pool identifier or CUSIP.  "
                                       "If omitted, use inline characteristics.",
                    },
                    "face_amount": {
                        "type": "number",
                        "description": "Face / par amount ($).  Overrides pool record.",
                    },
                    "coupon": {
                        "type": "number",
                        "description": "Pass-through coupon (decimal, e.g. 0.06).",
                    },
                    "wac": {"type": "number", "description": "Gross WAC (decimal)."},
                    "wala": {"type": "integer", "description": "Loan age (months)."},
                    "wam":  {"type": "integer", "description": "Remaining maturity (months)."},
                    "ltv":  {"type": "number"},
                    "fico": {"type": "integer"},
                    "pct_ca": {"type": "number"},
                    "pct_purchase": {"type": "number"},
                    "product_type": {"type": "string"},
                    "financing_rate": {
                        "type": "number",
                        "description": (
                            "Short-term financing rate (decimal, e.g. 0.053).  "
                            "Used to compute net interest income = interest - financing cost.  "
                            "Default: SOFR overnight."
                        ),
                    },
                    "shock_scenarios_bps": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Rate shocks for sensitivity analysis.  Default: [0, 100, 200, 300, -100, -200, -300].",
                    },
                    "horizon_years": {
                        "type": "integer",
                        "description": "Projection horizon in years (default 10, max 30).",
                    },
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_portfolio_interest_income",
            "description": (
                "Aggregate projected interest income across all portfolio holdings "
                "under BAU and rate-shock scenarios.  "
                "Returns income by position and portfolio totals."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "shock_scenarios_bps": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "Rate shocks (bps).  Default: [-300, -200, -100, 0, 100, 200, 300].",
                    },
                    "horizon_years": {
                        "type": "integer",
                        "description": "Projection horizon in years (default 5).",
                    },
                    "as_of_date": {"type": "string"},
                },
                "required": [],
            },
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_pool_chars(inp: dict):
    from analytics.prepay import PoolCharacteristics

    base: dict[str, Any] = dict(
        coupon=0.060, wac=0.065, wala=24, wam=336,
        loan_size=400_000, ltv=0.75, fico=750,
        pct_ca=0.15, pct_purchase=0.65,
        product_type="CC30", pool_id="", current_balance=1_000_000,
    )

    pool_id = inp.get("pool_id", "")
    if pool_id:
        try:
            from data.universe_1000 import get_universe_1000
            univ = get_universe_1000()
            row = univ[(univ["pool_id"] == pool_id) | (univ["cusip"] == pool_id)]
            if not row.empty:
                r = row.iloc[0]
                c = float(r["coupon"])
                w = float(r["wac"])
                base.update(
                    coupon=c / 100.0 if c > 1 else c,
                    wac=w / 100.0 if w > 1 else w,
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
            pass

    # Inline overrides
    for f in ["coupon", "wac", "wala", "wam", "ltv", "fico",
              "pct_ca", "pct_purchase", "product_type"]:
        if f in inp:
            base[f] = inp[f]
    if "face_amount" in inp:
        base["current_balance"] = float(inp["face_amount"])
    base["pool_id"] = pool_id

    return PoolCharacteristics(**base)


def _income_for_shock(pool_chars, shock_bps: int, horizon_years: int,
                      financing_rate: float, as_of,
                      use_cache: bool = True) -> dict[str, Any]:
    """Run cash flows for a single shock and return income summary."""
    import numpy as np
    from data.market_data import load_market_data
    from analytics.rate_paths import generate_rate_paths, TermStructure
    from analytics.prepay import PrepayModel, project_prepay_speeds
    from analytics.cashflows import get_cash_flows
    from data.intex_client import MockIntexClient
    from datetime import date

    if as_of is None:
        as_of = date.today()

    pool_id = pool_chars.pool_id or ""

    # ── Cache check ────────────────────────────────────────────────────────
    if use_cache and pool_id:
        from db.cache import read_interest_income
        cached = read_interest_income(pool_id, as_of, shock_bps, horizon_years)
        if cached:
            return cached

    md    = load_market_data(as_of)
    curve = md.sofr_curve
    if shock_bps:
        curve = TermStructure(
            tenors=curve.tenors,
            rates=curve.rates + shock_bps / 10_000.0,
        )

    n_periods = min(horizon_years * 12, pool_chars.wam)
    rp  = generate_rate_paths(curve=curve, n_paths=64, n_periods=n_periods, seed=42)
    cpr = project_prepay_speeds(pool=pool_chars, rate_paths=rp, model=PrepayModel())

    cfs = get_cash_flows(
        pool_id=pool_chars.pool_id or "tmp",
        cpr_vectors=cpr,
        settlement_date=as_of,
        face_amount=pool_chars.current_balance if pool_chars.current_balance > 0 else 1_000_000,
        intex_client=MockIntexClient(),
    )

    # Interest income = mean across paths of sum of interest CF
    mean_int  = np.mean(cfs.interest, axis=0)  # (n_periods,)
    mean_bal  = np.mean(cfs.balance,  axis=0)
    fwd_rates = np.mean(rp.short_rates, axis=0)  # proxy for short rate

    # Financing cost = balance × short_rate × dt
    dt = rp.dt
    financing_cost = mean_bal * fwd_rates * dt

    annual_income: list[dict] = []
    for yr in range(1, horizon_years + 1):
        s, e = (yr - 1) * 12, yr * 12
        if s >= n_periods:
            break
        e = min(e, n_periods)
        gross_int = float(np.sum(mean_int[s:e]))
        fin_cost  = float(np.sum(financing_cost[s:e]))
        net_int   = gross_int - fin_cost
        avg_bal   = float(np.mean(mean_bal[s:e]))
        nim       = (net_int / avg_bal * 12 / (e - s)) * 100 if avg_bal > 0 else 0.0
        annual_income.append({
            "year":                  yr,
            "gross_interest":        round(gross_int, 0),
            "financing_cost":        round(fin_cost, 0),
            "net_interest_income":   round(net_int, 0),
            "avg_balance":           round(avg_bal, 0),
            "net_interest_margin_pct": round(nim, 4),
        })

    result = {
        "shock_bps":               shock_bps,
        "total_gross_interest":    round(float(np.sum(mean_int)), 0),
        "total_financing_cost":    round(float(np.sum(financing_cost)), 0),
        "total_net_income":        round(float(np.sum(mean_int)) - float(np.sum(financing_cost)), 0),
        "annual": annual_income,
    }

    # ── Write to cache ─────────────────────────────────────────────────────
    if use_cache and pool_id:
        try:
            from db.cache import write_interest_income
            write_interest_income(
                pool_id, as_of, shock_bps, horizon_years,
                financing_rate * 100, result
            )
        except Exception:
            pass

    return result


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_compute_interest_income(inp: dict) -> str:
    from datetime import datetime, date

    pool_chars      = _build_pool_chars(inp)
    date_str        = inp.get("as_of_date", "")
    as_of           = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    horizon_years   = min(int(inp.get("horizon_years", 10)), 30)
    shocks          = inp.get("shock_scenarios_bps", [0, 100, 200, 300, -100, -200, -300])

    # Financing rate: use SOFR + small credit spread if not provided
    if "financing_rate" in inp:
        financing_rate = float(inp["financing_rate"])
    else:
        try:
            from data.market_data import load_market_data
            md = load_market_data(as_of)
            financing_rate = float(md.sofr_curve.zero_rate(0.25))
        except Exception:
            financing_rate = 0.053

    results: dict[str, Any] = {
        "pool_id":         pool_chars.pool_id,
        "face_amount":     pool_chars.current_balance,
        "coupon_pct":      round(pool_chars.coupon * 100, 3),
        "wac_pct":         round(pool_chars.wac * 100, 3),
        "financing_rate_pct": round(financing_rate * 100, 3),
        "horizon_years":   horizon_years,
        "scenarios":       {},
    }

    for shock in shocks:
        try:
            results["scenarios"][str(shock)] = _income_for_shock(
                pool_chars, shock, horizon_years, financing_rate, as_of
            )
        except Exception as exc:
            results["scenarios"][str(shock)] = {"error": str(exc)}

    # Add BAU sensitivity summary
    base = results["scenarios"].get("0", {})
    sens: dict[str, Any] = {}
    for shock in shocks:
        if shock != 0:
            scen = results["scenarios"].get(str(shock), {})
            base_ni = base.get("total_net_income", 0)
            scen_ni = scen.get("total_net_income", 0)
            if base_ni:
                sens[f"{shock:+d}bps"] = {
                    "net_income_change":   round(scen_ni - base_ni, 0),
                    "net_income_change_pct": round((scen_ni - base_ni) / abs(base_ni) * 100, 2),
                }
    results["income_sensitivity"] = sens
    return json.dumps(results, default=str)


def _handle_compute_portfolio_interest_income(inp: dict) -> str:
    """Aggregate interest income across demo portfolio positions."""
    shocks        = inp.get("shock_scenarios_bps", [-300, -200, -100, 0, 100, 200, 300])
    horizon_years = min(int(inp.get("horizon_years", 5)), 30)

    # Demo portfolio (matches existing mock positions)
    from analytics.prepay import PoolCharacteristics
    from datetime import datetime, date

    date_str = inp.get("as_of_date", "")
    as_of    = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()

    positions = [
        PoolCharacteristics(coupon=0.060, wac=0.065, wala=12, wam=348, loan_size=500_000,
                            ltv=0.72, fico=760, pct_ca=0.20, pct_purchase=0.65,
                            product_type="CC30", pool_id="TEST-POOL-30YR",
                            current_balance=5_000_000),
        PoolCharacteristics(coupon=0.055, wac=0.059, wala=6,  wam=174, loan_size=450_000,
                            ltv=0.68, fico=755, pct_ca=0.15, pct_purchase=0.70,
                            product_type="CC15", pool_id="TEST-POOL-15YR",
                            current_balance=3_000_000),
        PoolCharacteristics(coupon=0.065, wac=0.070, wala=24, wam=336, loan_size=350_000,
                            ltv=0.85, fico=700, pct_ca=0.10, pct_purchase=0.60,
                            product_type="GN30", pool_id="TEST-POOL-GN30",
                            current_balance=4_000_000),
    ]

    try:
        from data.market_data import load_market_data
        financing_rate = float(load_market_data(as_of).sofr_curve.zero_rate(0.25))
    except Exception:
        financing_rate = 0.053

    portfolio_results: dict[str, Any] = {
        "horizon_years":   horizon_years,
        "positions":       [],
        "portfolio_totals": {},
    }

    for pos in positions:
        pos_res: dict[str, Any] = {"pool_id": pos.pool_id, "face_amount": pos.current_balance, "scenarios": {}}
        for shock in shocks:
            try:
                pos_res["scenarios"][str(shock)] = _income_for_shock(
                    pos, shock, horizon_years, financing_rate, as_of
                )
            except Exception as exc:
                pos_res["scenarios"][str(shock)] = {"error": str(exc)}
        portfolio_results["positions"].append(pos_res)

    # Aggregate totals
    for shock in shocks:
        total_gross = sum(
            p["scenarios"].get(str(shock), {}).get("total_gross_interest", 0)
            for p in portfolio_results["positions"]
        )
        total_net = sum(
            p["scenarios"].get(str(shock), {}).get("total_net_income", 0)
            for p in portfolio_results["positions"]
        )
        portfolio_results["portfolio_totals"][str(shock)] = {
            "total_gross_interest":  round(total_gross, 0),
            "total_net_income":      round(total_net,   0),
        }

    return json.dumps(portfolio_results, default=str)


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "compute_interest_income":            _handle_compute_interest_income,
    "compute_portfolio_interest_income":  _handle_compute_portfolio_interest_income,
}
