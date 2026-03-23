"""
Scenario Tool
=============
Runs full rate-scenario analysis for individual pools or the portfolio.
Scenarios: Base, Up/Down 100/200/300 bps, Flattener (+2s10s), Steepener.

For each scenario the tool:
1. Shocks the SOFR curve.
2. Regenerates 256 rate paths via the BGM/Hull-White model.
3. Runs the prepayment model on each path.
4. Prices the pool via the OAS solver.
5. Reports price, OAS, OAD, convexity deltas vs. base.
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "run_scenario_analysis",
            "description": (
                "Run rate-scenario analysis for a single MBS pool.  "
                "Returns price, OAS, OAD, and convexity for each scenario.  "
                "Standard scenarios: Base, Up 100/200/300, Down 100/200/300 bps, "
                "Flattener (+50 short / −50 long), Steepener (−50 short / +50 long)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id":       {"type": "string", "description": "Pool identifier or CUSIP."},
                    "market_price":  {"type": "number", "description": "Market price % par."},
                    "coupon":        {"type": "number"},
                    "wac":           {"type": "number"},
                    "wala":          {"type": "integer"},
                    "wam":           {"type": "integer"},
                    "ltv":           {"type": "number"},
                    "fico":          {"type": "integer"},
                    "pct_ca":        {"type": "number"},
                    "pct_purchase":  {"type": "number"},
                    "product_type":  {"type": "string"},
                    "scenarios": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Subset of scenarios to run.  "
                            "Valid: Base | Up 100 | Up 200 | Up 300 | "
                            "Down 100 | Down 200 | Down 300 | Flattener | Steepener.  "
                            "Default: all."
                        ),
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
            "name": "run_what_if",
            "description": (
                "Reprice a pool with modified characteristics and compare analytics vs. base.  "
                "Supports WAC, WALA, LTV, FICO, CPR override, PSA override."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id":    {"type": "string"},
                    "base_price": {"type": "number", "description": "Base market price % par."},
                    "modifications": {
                        "type": "object",
                        "description": (
                            "Characteristic overrides: coupon, wac, wala, wam, ltv, fico, "
                            "pct_ca, pct_purchase, cpr_override (%), psa_override (PSA multiple)."
                        ),
                    },
                    "as_of_date": {"type": "string"},
                },
                "required": ["base_price"],
            },
        },
    },
]


# ── Standard scenario definitions ─────────────────────────────────────────────

def _standard_scenarios() -> dict[str, dict]:
    """Return map of scenario_name → {short_shock_bps, long_shock_bps}."""
    return {
        "Base":      {"short": 0,    "long": 0},
        "Up 100":    {"short": 100,  "long": 100},
        "Up 200":    {"short": 200,  "long": 200},
        "Up 300":    {"short": 300,  "long": 300},
        "Down 100":  {"short": -100, "long": -100},
        "Down 200":  {"short": -200, "long": -200},
        "Down 300":  {"short": -300, "long": -300},
        "Flattener": {"short": 50,   "long": -50},
        "Steepener": {"short": -50,  "long": 50},
    }


def _build_pool_chars(inp: dict):
    from analytics.prepay import PoolCharacteristics

    base: dict[str, Any] = dict(
        coupon=0.060, wac=0.065, wala=24, wam=336,
        loan_size=400_000, ltv=0.75, fico=750,
        pct_ca=0.15, pct_purchase=0.65,
        product_type="CC30", pool_id="", current_balance=1_000_000,
    )

    pid = inp.get("pool_id", "")
    if pid:
        try:
            from data.universe_1000 import get_universe_1000
            univ = get_universe_1000()
            row = univ[(univ["pool_id"] == pid) | (univ["cusip"] == pid)]
            if not row.empty:
                r = row.iloc[0]
                c, w = float(r["coupon"]), float(r["wac"])
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
                    pool_id=pid,
                    current_balance=float(r["original_balance"]),
                )
        except Exception:
            try:
                from data.pool_universe import get_pool_universe
                univ = get_pool_universe()
                row = univ[univ["pool_id"] == pid]
                if not row.empty:
                    r = row.iloc[0]
                    base.update(
                        coupon=float(r["coupon"]), wac=float(r["wac"]),
                        wala=int(r["wala"]), wam=int(r["wam"]),
                        loan_size=float(r["loan_size"]), ltv=float(r["ltv"]),
                        fico=int(r["fico"]), pct_ca=float(r["pct_ca"]),
                        pct_purchase=float(r["pct_purchase"]),
                        product_type=str(r["product_type"]),
                        pool_id=pid, current_balance=float(r["current_balance"]),
                    )
            except Exception:
                pass
        base["pool_id"] = pid

    for f in ["coupon", "wac", "wala", "wam", "ltv", "fico",
              "pct_ca", "pct_purchase", "product_type"]:
        if f in inp:
            base[f] = inp[f]

    return PoolCharacteristics(**base)


def _price_under_scenario(
    pool_chars,
    market_price: float,
    short_shock: int,
    long_shock: int,
    base_curve,
    n_paths: int,
    as_of,
) -> dict[str, Any]:
    from analytics.rate_paths import generate_rate_paths, TermStructure
    from data.intex_client import MockIntexClient
    from analytics.prepay import PrepayModel
    from analytics.oas_solver import compute_analytics
    import numpy as np

    curve = base_curve
    if short_shock or long_shock:
        # Apply different shock to short end vs long end
        tenors = curve.tenors
        shocked_rates = curve.rates.copy()
        for i, t in enumerate(tenors):
            # Blend: ≤2yr gets full short_shock, ≥10yr gets full long_shock
            blend = min(max((t - 2.0) / 8.0, 0.0), 1.0)
            bps_t = short_shock + blend * (long_shock - short_shock)
            shocked_rates[i] += bps_t / 10_000.0
        curve = TermStructure(tenors=tenors, rates=shocked_rates)

    rp = generate_rate_paths(curve=curve, n_paths=n_paths, n_periods=360, seed=42)
    a  = compute_analytics(
        pool_id=pool_chars.pool_id or "tmp",
        pool_chars=pool_chars,
        market_price=market_price,
        settlement_date=as_of,
        rate_paths=rp,
        intex_client=MockIntexClient(),
        prepay_model=PrepayModel(),
    )
    return {
        "oas_bps":       a.oas,
        "oad_years":     a.oad,
        "convexity":     a.convexity,
        "model_price":   a.model_price,
        "model_cpr_pct": a.model_cpr,
    }


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_run_scenario_analysis(inp: dict) -> str:
    from datetime import datetime, date as date_type
    from data.market_data import load_market_data

    pool_chars   = _build_pool_chars(inp)
    market_price = float(inp.get("market_price", 100.0))
    date_str     = inp.get("as_of_date", "")
    as_of        = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date_type.today()

    md           = load_market_data(as_of)
    all_scenarios = _standard_scenarios()
    requested    = inp.get("scenarios") or list(all_scenarios.keys())
    n_paths      = 64  # faster for scenario sweeps

    results: dict[str, Any] = {}
    base_res: dict[str, Any] = {}

    for name in requested:
        if name not in all_scenarios:
            continue
        scen = all_scenarios[name]
        try:
            res = _price_under_scenario(
                pool_chars, market_price,
                scen["short"], scen["long"],
                md.sofr_curve, n_paths, as_of,
            )
            if name == "Base":
                base_res = res
            results[name] = res
        except Exception as exc:
            results[name] = {"error": str(exc)}

    # Add deltas vs base
    if base_res:
        for name, res in results.items():
            if name != "Base" and "error" not in res:
                res["price_delta"]   = round(res["model_price"] - base_res.get("model_price", market_price), 4)
                res["oas_delta_bps"] = round(res["oas_bps"]     - base_res.get("oas_bps", 0),     2)
                res["oad_delta"]     = round(res["oad_years"]    - base_res.get("oad_years", 0),   3)

    return json.dumps({
        "pool_id":        pool_chars.pool_id,
        "market_price":   market_price,
        "as_of_date":     as_of.isoformat(),
        "scenarios":      results,
    }, default=str)


def _handle_run_what_if(inp: dict) -> str:
    from datetime import datetime, date as date_type
    from data.market_data import load_market_data
    from data.intex_client import MockIntexClient
    from analytics.rate_paths import generate_rate_paths
    from analytics.prepay import PrepayModel, PoolCharacteristics
    from analytics.oas_solver import compute_analytics

    base_chars   = _build_pool_chars(inp)
    base_price   = float(inp.get("base_price", 100.0))
    mods         = inp.get("modifications", {})
    date_str     = inp.get("as_of_date", "")
    as_of        = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date_type.today()

    # Build modified characteristics
    import dataclasses
    mod_dict = dataclasses.asdict(base_chars)
    modifiable = {"coupon", "wac", "wala", "wam", "loan_size", "ltv",
                  "fico", "pct_ca", "pct_purchase", "product_type"}
    for k, v in mods.items():
        if k in modifiable:
            mod_dict[k] = v
    mod_chars = PoolCharacteristics(**mod_dict)

    md = load_market_data(as_of)
    rp = generate_rate_paths(curve=md.sofr_curve, n_paths=64, n_periods=360, seed=42)

    intex  = MockIntexClient()
    prepay = PrepayModel()

    base_a = compute_analytics(
        pool_id=base_chars.pool_id or "base", pool_chars=base_chars,
        market_price=base_price, settlement_date=as_of,
        rate_paths=rp, intex_client=intex, prepay_model=prepay,
    )
    mod_a = compute_analytics(
        pool_id=(base_chars.pool_id or "base") + "_mod", pool_chars=mod_chars,
        market_price=base_price, settlement_date=as_of,
        rate_paths=rp, intex_client=intex, prepay_model=prepay,
    )

    return json.dumps({
        "pool_id":     base_chars.pool_id,
        "modifications": mods,
        "base": {
            "oas_bps":       base_a.oas,
            "oad_years":     base_a.oad,
            "convexity":     base_a.convexity,
            "yield_pct":     base_a.yield_,
            "model_cpr_pct": base_a.model_cpr,
            "model_price":   base_a.model_price,
        },
        "modified": {
            "oas_bps":       mod_a.oas,
            "oad_years":     mod_a.oad,
            "convexity":     mod_a.convexity,
            "yield_pct":     mod_a.yield_,
            "model_cpr_pct": mod_a.model_cpr,
            "model_price":   mod_a.model_price,
        },
        "delta": {
            "oas_bps":   round(mod_a.oas      - base_a.oas,       2),
            "oad_years": round(mod_a.oad       - base_a.oad,       3),
            "convexity": round(mod_a.convexity - base_a.convexity, 4),
            "yield_pct": round(mod_a.yield_    - base_a.yield_,    4),
            "model_price": round(mod_a.model_price - base_a.model_price, 4),
        },
    }, default=str)


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "run_scenario_analysis": _handle_run_scenario_analysis,
    "run_what_if":           _handle_run_what_if,
}
