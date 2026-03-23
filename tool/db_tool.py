"""
Database Query Tool
===================
Lets the agent (and users) query cached model results directly from DuckDB
without re-running any computation.

Covers:
  • Risk metrics  (OAS, OAD, convexity, yield)
  • Prepayment speeds (CPR by pool/scenario)
  • Interest income    (by pool/scenario/horizon)
  • Cache health       (row counts, coverage stats)
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "query_risk_metrics",
            "description": (
                "Query cached OAS, OAD, convexity, yield, and Z-spread from the results database.  "
                "Filters by product type, coupon, pool_id, date, or shock scenario.  "
                "Returns results instantly from DuckDB — no recomputation."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of pool_ids to retrieve (optional).",
                    },
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD filter."},
                    "shock_bps": {
                        "type": "integer",
                        "description": "Rate shock scenario (bps, default 0 = base).",
                    },
                    "oas_min_bps": {"type": "number"},
                    "oas_max_bps": {"type": "number"},
                    "oad_min":     {"type": "number"},
                    "oad_max":     {"type": "number"},
                    "sort_by": {
                        "type": "string",
                        "description": "Column to sort by: oas_bps | oad_years | convexity | yield_pct.",
                    },
                    "top_n": {"type": "integer", "description": "Max rows (default 20)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_prepay_speeds",
            "description": (
                "Query cached prepayment speed forecasts from the database.  "
                "Returns lifetime CPR and annual CPR by year for each pool/scenario."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_ids":   {"type": "array", "items": {"type": "string"}},
                    "as_of_date": {"type": "string"},
                    "shock_bps":  {"type": "integer", "description": "Default 0."},
                    "top_n":      {"type": "integer", "description": "Max rows (default 20)."},
                    "sort_by": {
                        "type": "string",
                        "description": "lifetime_cpr_pct | yr1_cpr_pct | yr5_cpr_pct | yr10_cpr_pct.",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_interest_income",
            "description": (
                "Query cached interest income projections from the database.  "
                "Compares BAU vs rate-shock scenarios."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pool_ids":      {"type": "array", "items": {"type": "string"}},
                    "as_of_date":    {"type": "string"},
                    "shock_bps":     {"type": "integer"},
                    "horizon_years": {"type": "integer"},
                    "top_n":         {"type": "integer"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_cache_status",
            "description": (
                "Return the current state of the results database: row counts per table, "
                "coverage statistics, and last-computed timestamps.  "
                "Use this to check whether warm-cache has been run."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql_query",
            "description": (
                "Execute a read-only SQL query directly against the Oasia results database.  "
                "Tables: risk_metrics_cache, prepay_cache, interest_income_cache, rate_path_cache.  "
                "Views: latest_risk_metrics, latest_prepay.  "
                "Use for ad-hoc analysis, cross-pool comparisons, or custom aggregations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "Read-only SQL SELECT statement.",
                    },
                },
                "required": ["sql"],
            },
        },
    },
]


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_query_risk_metrics(inp: dict) -> str:
    from db.cache import query

    conditions: list[str] = []
    params: list[Any] = []

    pool_ids = inp.get("pool_ids") or []
    if pool_ids:
        placeholders = ",".join(["?"] * len(pool_ids))
        conditions.append(f"pool_id IN ({placeholders})")
        params.extend(pool_ids)

    if "as_of_date" in inp:
        conditions.append("as_of_date = ?")
        params.append(inp["as_of_date"])

    shock = inp.get("shock_bps", 0)
    conditions.append("shock_bps = ?")
    params.append(shock)

    if "oas_min_bps" in inp:
        conditions.append("oas_bps >= ?")
        params.append(inp["oas_min_bps"])
    if "oas_max_bps" in inp:
        conditions.append("oas_bps <= ?")
        params.append(inp["oas_max_bps"])
    if "oad_min" in inp:
        conditions.append("oad_years >= ?")
        params.append(inp["oad_min"])
    if "oad_max" in inp:
        conditions.append("oad_years <= ?")
        params.append(inp["oad_max"])

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sort_col = inp.get("sort_by", "oas_bps")
    allowed_sorts = {"oas_bps", "oad_years", "convexity", "yield_pct", "computed_at"}
    if sort_col not in allowed_sorts:
        sort_col = "oas_bps"
    top_n = int(inp.get("top_n", 20))

    sql = f"""
        SELECT pool_id, as_of_date, market_price_rounded AS market_price,
               shock_bps, n_paths, oas_bps, z_spread_bps, oad_years,
               mod_duration, convexity, yield_pct, model_price, model_cpr_pct,
               computed_at
        FROM   risk_metrics_cache
        {where}
        ORDER  BY {sort_col} DESC
        LIMIT  {top_n}
    """
    rows = query(sql, params)
    return json.dumps({
        "count": len(rows),
        "shock_bps": shock,
        "results": rows,
        "_source": "cache",
    }, default=str)


def _handle_query_prepay_speeds(inp: dict) -> str:
    from db.cache import query

    conditions: list[str] = []
    params: list[Any] = []

    pool_ids = inp.get("pool_ids") or []
    if pool_ids:
        placeholders = ",".join(["?"] * len(pool_ids))
        conditions.append(f"pool_id IN ({placeholders})")
        params.extend(pool_ids)

    if "as_of_date" in inp:
        conditions.append("as_of_date = ?")
        params.append(inp["as_of_date"])

    shock = inp.get("shock_bps", 0)
    conditions.append("shock_bps = ?")
    params.append(shock)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    sort_col = inp.get("sort_by", "lifetime_cpr_pct")
    allowed = {"lifetime_cpr_pct", "yr1_cpr_pct", "yr5_cpr_pct", "yr10_cpr_pct"}
    if sort_col not in allowed:
        sort_col = "lifetime_cpr_pct"
    top_n = int(inp.get("top_n", 20))

    sql = f"""
        SELECT pool_id, as_of_date, shock_bps, n_paths, wac_pct, wala_months, wam_months,
               lifetime_cpr_pct, yr1_cpr_pct, yr3_cpr_pct, yr5_cpr_pct,
               yr10_cpr_pct, yr20_cpr_pct, yr30_cpr_pct, peak_cpr_year,
               computed_at
        FROM   prepay_cache
        {where}
        ORDER  BY {sort_col} DESC
        LIMIT  {top_n}
    """
    rows = query(sql, params)
    return json.dumps({
        "count": len(rows),
        "results": rows,
        "_source": "cache",
    }, default=str)


def _handle_query_interest_income(inp: dict) -> str:
    from db.cache import query

    conditions: list[str] = []
    params: list[Any] = []

    pool_ids = inp.get("pool_ids") or []
    if pool_ids:
        placeholders = ",".join(["?"] * len(pool_ids))
        conditions.append(f"pool_id IN ({placeholders})")
        params.extend(pool_ids)

    if "as_of_date" in inp:
        conditions.append("as_of_date = ?")
        params.append(inp["as_of_date"])
    if "shock_bps" in inp:
        conditions.append("shock_bps = ?")
        params.append(inp["shock_bps"])
    if "horizon_years" in inp:
        conditions.append("horizon_years = ?")
        params.append(inp["horizon_years"])

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    top_n  = int(inp.get("top_n", 20))

    sql = f"""
        SELECT pool_id, as_of_date, shock_bps, horizon_years, financing_rate_pct,
               total_gross_interest, total_financing_cost, total_net_income, computed_at
        FROM   interest_income_cache
        {where}
        ORDER  BY total_net_income DESC
        LIMIT  {top_n}
    """
    rows = query(sql, params)
    return json.dumps({
        "count": len(rows),
        "results": rows,
        "_source": "cache",
    }, default=str)


def _handle_get_cache_status(inp: dict) -> str:
    from db.connection import cache_stats, DB_PATH
    from db.cache import query
    import os

    stats = cache_stats()

    # Last computed timestamps
    last_computed: dict[str, Any] = {}
    for tbl in ["risk_metrics_cache", "prepay_cache",
                "interest_income_cache", "rate_path_cache"]:
        try:
            row = query(f"SELECT MAX(computed_at) FROM {tbl}")
            last_computed[tbl] = str(row[0]["max(computed_at)"] or "never")
        except Exception:
            last_computed[tbl] = "unknown"

    # Coverage: how many of 1000 pools have base risk metrics
    try:
        covered = query(
            "SELECT COUNT(DISTINCT pool_id) AS n FROM risk_metrics_cache WHERE shock_bps = 0"
        )
        coverage_pct = round(covered[0]["n"] / 1000 * 100, 1)
    except Exception:
        coverage_pct = 0.0

    db_size_mb = round(os.path.getsize(str(DB_PATH)) / 1e6, 2) if DB_PATH.exists() else 0.0

    return json.dumps({
        "db_path":       str(DB_PATH),
        "db_size_mb":    db_size_mb,
        "row_counts":    stats,
        "last_computed": last_computed,
        "pool_coverage": {
            "risk_metrics_base_scenario": coverage_pct,
            "message": (
                f"{coverage_pct:.0f}% of 1000 pools have cached base-scenario risk metrics.  "
                "Run `python scripts/warm_cache.py` to pre-compute all pools."
                if coverage_pct < 100 else
                "All 1000 pools have cached base-scenario risk metrics."
            ),
        },
    }, default=str)


def _handle_run_sql_query(inp: dict) -> str:
    from db.cache import query

    sql = str(inp.get("sql", "")).strip()

    # Basic safety: only allow SELECT statements
    if not sql.upper().lstrip().startswith("SELECT"):
        return json.dumps({"error": "Only SELECT statements are permitted."})

    try:
        rows = query(sql)
        return json.dumps({
            "count":   len(rows),
            "results": rows,
            "_source": "cache",
        }, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "query_risk_metrics":    _handle_query_risk_metrics,
    "query_prepay_speeds":   _handle_query_prepay_speeds,
    "query_interest_income": _handle_query_interest_income,
    "get_cache_status":      _handle_get_cache_status,
    "run_sql_query":         _handle_run_sql_query,
}
