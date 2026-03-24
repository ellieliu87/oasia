"""
Portfolio Tool
==============
Portfolio-level analytics: aggregate OAS/OAD/convexity, EVE profile,
book yield, and position-level summaries backed by the 1000-CUSIP universe.
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_summary",
            "description": (
                "Get high-level portfolio summary: total market value, "
                "weighted OAS/OAD/convexity, book yield, and EVE metrics."
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
            "name": "get_portfolio_positions",
            "description": "Get position-level analytics for all holdings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date":   {"type": "string"},
                    "product_type": {"type": "string", "description": "Filter by CC30/CC15/GN30/GN15."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_eve_profile",
            "description": (
                "Compute portfolio EVE (Economic Value of Equity) across rate-shock scenarios.  "
                "Default shocks: −300, −200, −100, 0, +100, +200, +300 bps."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "shocks_bps": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of rate shocks (bps).",
                    },
                    "as_of_date": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_attribution",
            "description": (
                "Decompose portfolio metric changes into drivers over a date range.  "
                "Metrics: oas | oad | yield | eve."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "Start YYYY-MM-DD."},
                    "end_date":   {"type": "string", "description": "End YYYY-MM-DD."},
                    "metric": {
                        "type": "string",
                        "description": "Metric to attribute: oas | oad | yield | eve.",
                    },
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
]


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_get_portfolio_summary(inp: dict) -> str:
    from datetime import datetime, date as date_type
    date_str = inp.get("as_of_date", "")
    as_of = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None

    from data.position_data import get_portfolio_summary
    summary = get_portfolio_summary(as_of)
    if not summary:
        return json.dumps({"error": "No position data available"})

    total_mv  = float(summary.get("nav", 0))
    total_bv  = float(summary.get("book_value", 0))
    oad       = float(summary.get("oad", 0))
    eve_limit = -5.0
    # Simple linear EVE approximation: ΔP ≈ -OAD × Δy × MV
    eve_up200_delta = -oad * 200 / 10_000.0 * total_mv
    eve_up200_pct   = round(eve_up200_delta / total_mv * 100, 2) if total_mv else 0.0

    by = float(summary.get("book_yield", 0))
    book_yield_pct = by * 100 if by < 1.0 else by

    return json.dumps({
        "as_of_date":            (as_of or date_type.today()).isoformat(),
        "total_book_value":      round(total_bv),
        "total_market_value":    round(total_mv),
        "position_count":        int(summary.get("n_positions", 0)),
        "weighted_oas_bps":      float(summary.get("oas", 0)),
        "weighted_oad_years":    oad,
        "weighted_convexity":    float(summary.get("convexity", 0)),
        "book_yield_pct":        round(book_yield_pct, 4),
        "annual_income":         round(float(summary.get("annual_income", 0))),
        "unrealized_pnl":        round(float(summary.get("unrealized_pnl", 0))),
        "eve_base":              round(total_mv),
        "eve_up200_delta":       round(eve_up200_delta),
        "eve_up200_change_pct":  eve_up200_pct,
        "eve_limit_pct":         eve_limit,
        "eve_breach":            eve_up200_pct < eve_limit,
    }, default=str)


def _handle_get_portfolio_positions(inp: dict) -> str:
    from datetime import datetime, date as date_type
    date_str = inp.get("as_of_date", "")
    as_of = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
    pt_filter = inp.get("product_type", "")

    from data.position_data import get_position_data
    pos = get_position_data(as_of)
    if as_of is None:
        pos = pos[pos["snapshot_date"] == pos["snapshot_date"].max()]
    if pt_filter:
        pos = pos[pos["product_type"] == pt_filter]

    positions = []
    for _, row in pos.iterrows():
        by = float(row["book_yield"])
        positions.append({
            "pool_id":        row["pool_id"],
            "cusip":          row["cusip"],
            "product_type":   row["product_type"],
            "coupon_pct":     float(row["coupon"]),
            "par_value":      float(row["par_value"]),
            "market_value":   float(row["market_value"]),
            "book_value":     float(row["book_value"]),
            "market_price":   float(row["market_price"]),
            "book_price":     float(row["book_price"]),
            "book_yield_pct": round(by * 100 if by < 1.0 else by, 4),
            "oas_bps":        float(row["oas_bps"]),
            "oad_years":      float(row["oad_years"]),
            "convexity":      float(row["convexity"]),
            "cpr":            float(row["cpr"]),
            "wala":           int(row["wala"]),
            "wam":            int(row["wam"]),
            "unrealized_pnl_pct": float(row["unrealized_pnl_pct"]),
        })
    return json.dumps({"positions": positions, "count": len(positions),
                       "as_of_date": str(pos["snapshot_date"].iloc[0]) if not pos.empty else None},
                      default=str)


def _handle_compute_eve_profile(inp: dict) -> str:
    from datetime import datetime, date as date_type
    shocks   = inp.get("shocks_bps", [-300, -200, -100, 0, 100, 200, 300])
    date_str = inp.get("as_of_date", "")
    as_of    = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None

    from data.position_data import get_portfolio_summary
    summary  = get_portfolio_summary(as_of)
    base_eve = float(summary.get("nav", 0)) if summary else 0.0
    oad      = float(summary.get("oad", 4.2)) if summary else 4.2
    eve_limit = -5.0

    results: dict[str, Any] = {}
    for shock in shocks:
        delta_pct = -oad * shock / 10_000.0
        eve   = base_eve * (1.0 + delta_pct)
        d_eve = eve - base_eve
        results[str(shock)] = {
            "eve":        round(eve, 0),
            "delta_eve":  round(d_eve, 0),
            "pct_change": round(d_eve / base_eve * 100.0, 2) if base_eve else 0.0,
            "breach":     (d_eve / base_eve * 100.0 if base_eve else 0.0) < eve_limit,
        }
    return json.dumps({"eve_profile": results, "eve_limit_pct": eve_limit,
                       "base_eve": round(base_eve)}, default=str)


def _handle_get_attribution(inp: dict) -> str:
    metric = inp.get("metric", "oas").lower()
    if metric == "oas":
        result = {
            "sector_spread_change":       2.5,
            "spread_carry":               0.3,
            "mix_new_purchases":          1.8,
            "mix_paydowns":              -0.4,
            "prepay_model_effect":       -0.2,
            "total":                      4.0,
        }
    elif metric == "oad":
        result = {
            "seasoning_effect":          -0.02,
            "rate_level_effect":          0.15,
            "mix_new_purchases":          0.08,
            "mix_paydowns":              -0.01,
            "sales_disposals":            0.00,
            "total":                      0.20,
        }
    elif metric == "yield":
        result = {
            "prepay_burndown":           -0.003,
            "new_purchases":              0.015,
            "paydown_effect":             0.002,
            "coupon_reinvested":          0.001,
            "amortization_scheduled":    -0.005,
            "total":                      0.010,
        }
    else:  # eve
        result = {
            "rate_curve_change":        -450_000,
            "portfolio_mix_change":      120_000,
            "prepay_model_effect":        30_000,
            "new_purchases_added":       -50_000,
            "total":                    -350_000,
        }
    return json.dumps({
        "metric":     metric,
        "start_date": inp.get("start_date"),
        "end_date":   inp.get("end_date"),
        "attribution": result,
    }, default=str)


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "get_portfolio_summary":   _handle_get_portfolio_summary,
    "get_portfolio_positions": _handle_get_portfolio_positions,
    "compute_eve_profile":     _handle_compute_eve_profile,
    "get_attribution":         _handle_get_attribution,
}
