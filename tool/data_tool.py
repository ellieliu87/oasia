"""
Data Tool
=========
Query the 1000-CUSIP universe, retrieve pool details, load 6-month snapshot
history, and access market data (SOFR/Treasury curves, cohort OAS levels).
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "screen_securities",
            "description": (
                "Screen the 1000-CUSIP MBS universe for pools matching specified criteria.  "
                "Returns pool characteristics and latest-snapshot analytics (price, CPR, OAS, OAD)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Product types: CC30 | CC15 | GN30 | GN15.",
                    },
                    "coupon_min": {"type": "number", "description": "Min coupon (%, e.g. 5.5)."},
                    "coupon_max": {"type": "number", "description": "Max coupon (%)."},
                    "oas_min_bps": {"type": "number", "description": "Min OAS (bps)."},
                    "oas_max_bps": {"type": "number", "description": "Max OAS (bps)."},
                    "oad_min": {"type": "number", "description": "Min OAD (years)."},
                    "oad_max": {"type": "number", "description": "Max OAD (years)."},
                    "fico_min": {"type": "integer", "description": "Min FICO score."},
                    "fico_max": {"type": "integer", "description": "Max FICO score."},
                    "ltv_max":  {"type": "number",  "description": "Max LTV (decimal, e.g. 0.80)."},
                    "ltv_min":  {"type": "number",  "description": "Min LTV."},
                    "issuer":   {"type": "string",  "description": "FNMA | FHLMC | GNMA."},
                    "wala_min": {"type": "integer", "description": "Min WALA (months)."},
                    "wala_max": {"type": "integer", "description": "Max WALA (months)."},
                    "top_n":    {"type": "integer", "description": "Max results (default 20)."},
                    "sort_by":  {
                        "type": "string",
                        "description": "Sort field: oas_bps | oad_years | cpr | market_price | coupon.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_pool_details",
            "description": (
                "Get full characteristics and 6-month snapshot history for a specific pool.  "
                "Includes static features (WAC, WALA, LTV, FICO, geography) and "
                "monthly time series (price, CPR, OAS, OAD, convexity, balance)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_id": {
                        "type": "string",
                        "description": "Pool identifier or CUSIP.",
                    },
                },
                "required": ["pool_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_data",
            "description": (
                "Get SOFR swap curve, US Treasury curve, and agency MBS cohort OAS levels.  "
                "Also returns current mortgage rates (30yr / 15yr)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD (default: today)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_universe_summary",
            "description": (
                "Return high-level summary statistics for the 1000-CUSIP universe: "
                "count by product/coupon, average OAS/OAD, balance distribution."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": {"type": "string"},
                },
                "required": [],
            },
        },
    },
]


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_screen_securities(inp: dict) -> str:
    from data.universe_1000 import screen_universe, get_universe_snapshots

    filters: dict[str, Any] = {}
    if "product_types" in inp:
        filters["product_type"] = inp["product_types"]
    if "issuer" in inp:
        filters["issuer"] = inp["issuer"]

    # Numeric range filters
    for field, key in [
        ("coupon", "coupon"), ("fico", "fico"),
        ("ltv", "ltv"), ("wala_at_issue", "wala"),
    ]:
        lo_key = f"{key}_min"
        hi_key = f"{key}_max"
        if lo_key in inp or hi_key in inp:
            lo = inp.get(lo_key, -1e9)
            hi = inp.get(hi_key,  1e9)
            filters[field] = (lo, hi)

    univ_df = screen_universe(filters)

    # Merge latest snapshot for OAS/OAD/price
    snaps = get_universe_snapshots()
    latest = (
        snaps.sort_values("snapshot_date")
        .groupby("pool_id")
        .last()
        .reset_index()
        [["pool_id", "market_price", "cpr", "oas_bps", "oad_years", "convexity",
          "current_balance", "snapshot_date"]]
    )
    merged = univ_df.merge(latest, on="pool_id", how="left")

    # Apply OAS / OAD filters on snapshot data
    if "oas_min_bps" in inp:
        merged = merged[merged["oas_bps"] >= inp["oas_min_bps"]]
    if "oas_max_bps" in inp:
        merged = merged[merged["oas_bps"] <= inp["oas_max_bps"]]
    if "oad_min" in inp:
        merged = merged[merged["oad_years"] >= inp["oad_min"]]
    if "oad_max" in inp:
        merged = merged[merged["oad_years"] <= inp["oad_max"]]

    top_n   = int(inp.get("top_n", 20))
    sort_by = inp.get("sort_by", "oas_bps")
    if sort_by in merged.columns:
        merged = merged.sort_values(sort_by, ascending=False)

    merged = merged.head(top_n)

    cols = ["pool_id", "cusip", "issuer", "product_type", "coupon", "wac",
            "wala_at_issue", "original_wam", "ltv", "fico", "loan_size",
            "pct_ca", "pct_purchase", "original_balance",
            "market_price", "cpr", "oas_bps", "oad_years", "convexity",
            "current_balance", "snapshot_date"]
    available = [c for c in cols if c in merged.columns]

    return json.dumps({
        "count": len(merged),
        "pools": merged[available].to_dict("records"),
        "message": f"Found {len(merged)} pools matching criteria.",
    }, default=str)


def _handle_get_pool_details(inp: dict) -> str:
    from data.universe_1000 import get_universe_1000, get_pool_history, get_pool_snapshot

    pid = inp["pool_id"]
    univ = get_universe_1000()
    row = univ[(univ["pool_id"] == pid) | (univ["cusip"] == pid)]

    static: dict[str, Any] = {}
    if not row.empty:
        static = row.iloc[0].to_dict()
        # Convert numpy scalars
        static = {k: (float(v) if hasattr(v, "item") else v) for k, v in static.items()}
    else:
        static = {"error": f"Pool '{pid}' not found in universe."}

    history_df = get_pool_history(pid if not row.empty else pid)
    history: list[dict] = []
    if not history_df.empty:
        history = history_df.to_dict("records")

    return json.dumps({
        "pool_id":  pid,
        "static":   static,
        "history":  history,
        "n_snapshots": len(history),
    }, default=str)


def _handle_get_market_data(inp: dict) -> str:
    from datetime import datetime
    from data.market_data import load_market_data

    date_str = inp.get("as_of_date", "")
    as_of    = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
    md       = load_market_data(as_of)

    tenors = md.sofr_curve.tenors.tolist()
    return json.dumps({
        "as_of_date": md.as_of_date.isoformat(),
        "sofr_curve": {
            "tenors": tenors,
            "rates_pct": [round(r * 100, 3) for r in md.sofr_curve.rates.tolist()],
            "2y":  round(float(md.sofr_curve.zero_rate(2.0))  * 100, 3),
            "5y":  round(float(md.sofr_curve.zero_rate(5.0))  * 100, 3),
            "10y": round(float(md.sofr_curve.zero_rate(10.0)) * 100, 3),
            "30y": round(float(md.sofr_curve.zero_rate(30.0)) * 100, 3),
        },
        "treasury_curve": {
            "tenors": tenors,
            "rates_pct": [round(r * 100, 3) for r in md.treasury_curve.rates.tolist()],
            "2y":  round(float(md.treasury_curve.zero_rate(2.0))  * 100, 3),
            "10y": round(float(md.treasury_curve.zero_rate(10.0)) * 100, 3),
            "30y": round(float(md.treasury_curve.zero_rate(30.0)) * 100, 3),
        },
        "cohort_oas_bps": md.cohort_oas,
        "implied_mortgage_rates": {
            "30yr_pct": round(float(md.sofr_curve.zero_rate(10.0)) * 100 + 1.70, 3),
            "15yr_pct": round(float(md.sofr_curve.zero_rate(7.0))  * 100 + 1.30, 3),
        },
    }, default=str)


def _handle_get_universe_summary(inp: dict) -> str:
    import numpy as np
    from data.universe_1000 import get_universe_1000, get_universe_snapshots

    univ  = get_universe_1000()
    snaps = get_universe_snapshots()
    latest = (
        snaps.sort_values("snapshot_date")
        .groupby("pool_id")
        .last()
        .reset_index()
    )
    merged = univ.merge(latest, on="pool_id", how="left")

    by_product: list[dict] = []
    for pt in ["CC30", "CC15", "GN30", "GN15"]:
        sub = merged[merged["product_type"] == pt]
        if sub.empty:
            continue
        by_product.append({
            "product_type": pt,
            "count": len(sub),
            "total_balance_bn": round(float(sub["original_balance"].sum()) / 1e9, 2),
            "avg_coupon_pct":   round(float(sub["coupon"].mean()), 3),
            "avg_oas_bps":      round(float(sub["oas_bps"].mean()), 1),
            "avg_oad_years":    round(float(sub["oad_years"].mean()), 2),
            "avg_cpr_pct":      round(float(sub["cpr"].mean()) * 100 if sub["cpr"].mean() < 1 else float(sub["cpr"].mean()), 2),
            "avg_wala_months":  round(float(sub["wala_at_issue"].mean()), 1),
            "avg_fico":         round(float(sub["fico"].mean()), 0),
            "avg_ltv":          round(float(sub["ltv"].mean()), 3),
        })

    by_issuer: list[dict] = []
    for iss in ["FNMA", "FHLMC", "GNMA"]:
        sub = merged[merged["issuer"] == iss]
        if sub.empty:
            continue
        by_issuer.append({
            "issuer": iss,
            "count": len(sub),
            "total_balance_bn": round(float(sub["original_balance"].sum()) / 1e9, 2),
        })

    return json.dumps({
        "total_pools":         len(univ),
        "total_balance_bn":    round(float(univ["original_balance"].sum()) / 1e9, 2),
        "by_product":          by_product,
        "by_issuer":           by_issuer,
        "snapshot_dates":      sorted(snaps["snapshot_date"].astype(str).unique().tolist()),
    }, default=str)


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "screen_securities":    _handle_screen_securities,
    "get_pool_details":     _handle_get_pool_details,
    "get_market_data":      _handle_get_market_data,
    "get_universe_summary": _handle_get_universe_summary,
}
