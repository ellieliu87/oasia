"""
Analytics Tool
==============
Computes OAS, OAD, convexity, Z-spread, and yield for MBS pools using
256 simulated rate paths from the term structure model.

OAS   — Option-Adjusted Spread (bps): spread added to each short-rate path
        such that the discounted mean cash flow equals the market price.
OAD   — Option-Adjusted Duration (years): price sensitivity to a ±1 bp rate bump.
Convexity — second-order rate sensitivity; negative for agency MBS due to
            prepayment optionality.
Z-spread  — parallel shift to the zero curve that matches market price (no
            path dependency).
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "compute_bond_analytics",
            "description": (
                "Compute full OAS/OAD/convexity/Z-spread/yield analytics for a single "
                "MBS pool using 256 simulated interest-rate paths.  "
                "Pool can be specified by pool_id (looked up from the 1000-CUSIP universe) "
                "or by providing characteristics inline."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {"type": "string", "description": "Pool identifier or CUSIP."},
                    "market_price": {
                        "type": "number",
                        "description": "Market price as % of par (e.g. 101.25).",
                    },
                    "coupon":       {"type": "number", "description": "Pass-through coupon (decimal)."},
                    "wac":          {"type": "number", "description": "WAC (decimal)."},
                    "wala":         {"type": "integer"},
                    "wam":          {"type": "integer"},
                    "ltv":          {"type": "number"},
                    "fico":         {"type": "integer"},
                    "pct_ca":       {"type": "number"},
                    "pct_purchase": {"type": "number"},
                    "product_type": {"type": "string"},
                    "face_amount":  {"type": "number", "description": "Face value ($)."},
                    "n_paths": {
                        "type": "integer",
                        "description": "Monte Carlo paths (default 256, min 32).",
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
            "name": "batch_compute_analytics",
            "description": (
                "Compute OAS/OAD/convexity for a list of pools in the universe.  "
                "Filters can be applied (product_type, coupon range, etc.).  "
                "Uses market prices from the latest snapshot."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of pool_ids to compute analytics for (max 20).",
                    },
                    "product_type": {
                        "type": "string",
                        "description": "Filter by product type (CC30/CC15/GN30/GN15).",
                    },
                    "coupon_min": {"type": "number", "description": "Min coupon (decimal)."},
                    "coupon_max": {"type": "number", "description": "Max coupon (decimal)."},
                    "top_n": {
                        "type": "integer",
                        "description": "Maximum number of pools to compute (default 10).",
                    },
                    "as_of_date": {"type": "string"},
                },
                "required": [],
            },
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_pool_chars(inp: dict, pool_id: str = ""):
    from analytics.prepay import PoolCharacteristics

    base: dict[str, Any] = dict(
        coupon=0.060, wac=0.065, wala=24, wam=336,
        loan_size=400_000, ltv=0.75, fico=750,
        pct_ca=0.15, pct_purchase=0.65,
        product_type="CC30", pool_id=pool_id, current_balance=1_000_000,
    )

    pid = inp.get("pool_id", pool_id)
    if pid:
        # Try 1000-CUSIP universe first
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
            # Fall back to legacy 80-pool universe
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
    if "face_amount" in inp:
        base["current_balance"] = float(inp["face_amount"])

    return PoolCharacteristics(**base)


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_compute_bond_analytics(inp: dict) -> str:
    from datetime import datetime, date
    from data.market_data import load_market_data
    from data.intex_client import MockIntexClient
    from analytics.rate_paths import generate_rate_paths
    from analytics.prepay import PrepayModel
    from analytics.oas_solver import compute_analytics
    from db.cache import read_risk_metrics, write_risk_metrics

    pool_chars   = _build_pool_chars(inp)
    market_price = float(inp.get("market_price", 100.0))
    n_paths      = max(32, min(int(inp.get("n_paths", 256)), 512))
    date_str     = inp.get("as_of_date", "")
    as_of        = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    pool_id      = pool_chars.pool_id or "custom"

    # ── Cache check ────────────────────────────────────────────────────────
    cached = read_risk_metrics(pool_id, as_of, market_price, 0, n_paths)
    if cached:
        cached.update({"as_of_date": as_of.isoformat(), "n_paths": n_paths})
        return json.dumps(cached, default=str)

    # ── Compute ────────────────────────────────────────────────────────────
    md = load_market_data(as_of)
    rp = generate_rate_paths(curve=md.sofr_curve, n_paths=n_paths, n_periods=360, seed=42)

    result = compute_analytics(
        pool_id=pool_id,
        pool_chars=pool_chars,
        market_price=market_price,
        settlement_date=as_of,
        rate_paths=rp,
        intex_client=MockIntexClient(),
        prepay_model=PrepayModel(),
    )

    out = {
        "pool_id":       result.pool_id,
        "market_price":  result.market_price,
        "model_price":   result.model_price,
        "oas_bps":       result.oas,
        "z_spread_bps":  result.z_spread,
        "oad_years":     result.oad,
        "mod_duration":  result.mod_duration,
        "convexity":     result.convexity,
        "yield_pct":     result.yield_,
        "model_cpr_pct": result.model_cpr,
        "n_paths":       n_paths,
        "as_of_date":    as_of.isoformat(),
    }

    # ── Write to cache ─────────────────────────────────────────────────────
    try:
        write_risk_metrics(pool_id, as_of, market_price, 0, n_paths, out)
    except Exception:
        pass  # cache write failure is non-fatal

    return json.dumps(out, default=str)


def _handle_batch_compute_analytics(inp: dict) -> str:
    import numpy as np
    from datetime import datetime, date
    from data.market_data import load_market_data
    from data.intex_client import MockIntexClient
    from analytics.rate_paths import generate_rate_paths
    from analytics.prepay import PrepayModel
    from analytics.oas_solver import compute_analytics

    date_str = inp.get("as_of_date", "")
    as_of    = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()
    top_n    = min(int(inp.get("top_n", 10)), 20)

    md = load_market_data(as_of)
    rp = generate_rate_paths(curve=md.sofr_curve, n_paths=64, n_periods=360, seed=42)

    # Resolve pool list
    pool_ids = list(inp.get("pool_ids") or [])
    if not pool_ids:
        try:
            from data.universe_1000 import screen_universe
            filters: dict[str, Any] = {}
            if "product_type" in inp:
                filters["product_type"] = inp["product_type"]
            if "coupon_min" in inp:
                filters["coupon_min"] = float(inp["coupon_min"]) * 100  # stored as %
            if "coupon_max" in inp:
                filters["coupon_max"] = float(inp["coupon_max"]) * 100
            df = screen_universe(filters).head(top_n)
            pool_ids = df["pool_id"].tolist()
        except Exception:
            from data.pool_universe import get_pool_universe, screen_pools
            univ = get_pool_universe()
            filt: dict[str, Any] = {}
            if "product_type" in inp:
                filt["product_type"] = [inp["product_type"]]
            if "coupon_min" in inp:
                filt["coupon_min"] = inp["coupon_min"]
            if "coupon_max" in inp:
                filt["coupon_max"] = inp["coupon_max"]
            pool_ids = screen_pools(univ, filt).head(top_n)["pool_id"].tolist()

    results: list[dict] = []
    for pid in pool_ids[:top_n]:
        try:
            chars = _build_pool_chars({}, pool_id=pid)
            # get latest snapshot price if available
            market_price = 100.0
            try:
                from data.universe_1000 import get_pool_snapshot
                snap = get_pool_snapshot(pid)
                if snap:
                    market_price = float(snap.get("market_price", 100.0))
            except Exception:
                pass

            a = compute_analytics(
                pool_id=pid, pool_chars=chars, market_price=market_price,
                settlement_date=as_of, rate_paths=rp,
                intex_client=MockIntexClient(), prepay_model=PrepayModel(),
            )
            results.append({
                "pool_id":      a.pool_id,
                "market_price": a.market_price,
                "oas_bps":      a.oas,
                "oad_years":    a.oad,
                "convexity":    a.convexity,
                "yield_pct":    a.yield_,
                "model_cpr_pct": a.model_cpr,
            })
        except Exception as exc:
            results.append({"pool_id": pid, "error": str(exc)})

    return json.dumps({
        "count": len(results),
        "as_of_date": as_of.isoformat(),
        "pools": results,
    }, default=str)


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "compute_bond_analytics":    _handle_compute_bond_analytics,
    "batch_compute_analytics":   _handle_batch_compute_analytics,
}
