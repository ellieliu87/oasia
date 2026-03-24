"""
Dashboard Tool
==============
Tools that answer questions directly tied to what is shown on the Dashboard UI:
NAV projection, top performers, sector allocation, portfolio health score,
user watchlist, and portfolio planning session state.
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schemas ─────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "get_nav_projection",
            "description": (
                "Return the portfolio NAV time-series: up to 6 months of historical "
                "snapshots concatenated with a quarterly forward projection. "
                "Values in $B. Use to explain the NAV chart on the Dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "n_quarters": {
                        "type": "integer",
                        "description": "Projection horizon in quarters (default 12 = 3 years).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_top_performers",
            "description": (
                "Return month-over-month total return (%) per pool, ranked best to worst. "
                "Computes MV change between the last two available snapshot dates."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "Number of top performers to return (default 5).",
                    },
                    "bottom_n": {
                        "type": "integer",
                        "description": "Also include this many worst performers (default 0).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sector_allocation",
            "description": (
                "Return portfolio market-value breakdown by product-type sector. "
                "Matches the Sector Allocation card on the Dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD (default: latest snapshot)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_portfolio_health",
            "description": (
                "Compute the Portfolio Health Score (0–100) and five sub-metrics: "
                "Duration Risk, Convexity, Credit Quality, Liquidity, Concentration. "
                "Matches the Portfolio Health card on the Dashboard."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date":    {"type": "string", "description": "YYYY-MM-DD (default: latest)."},
                    "benchmark_oad": {"type": "number",  "description": "Benchmark OAD in years (default 4.2)."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_watchlist",
            "description": (
                "Return the user's personal watchlist CUSIPs, enriched with the latest "
                "market price, OAD, and unrealized P&L from position snapshots."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {
                        "type": "string",
                        "description": "Username whose watchlist to retrieve (default 'default').",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_planning_session",
            "description": (
                "Return the current Portfolio Planning workflow state: phase, risk appetite, "
                "trader name, gate decisions, and allocation scenario for the latest session."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "username":   {"type": "string", "description": "Username (default 'default')."},
                    "session_id": {"type": "string", "description": "Specific session ID; omit for latest."},
                },
                "required": [],
            },
        },
    },
]


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_get_nav_projection(inp: dict) -> str:
    n_quarters = int(inp.get("n_quarters", 12))
    try:
        from data.position_data import get_historical_nav, get_position_data, SNAPSHOT_DATES
        import math

        # Historical series
        hist = get_historical_nav()
        hist_labels = [str(h["date"])[:7] for h in hist]
        hist_navs   = [round(h["nav"] / 1e9, 3) for h in hist]

        # Quarterly projection from latest snapshot
        pos = get_position_data()
        pos = pos[pos["snapshot_date"] == pos["snapshot_date"].max()]
        if not pos.empty and hist_navs:
            total_mv    = float(pos["market_value"].sum())
            monthly_cpr = float(pos["cpr"].mean() / 100 / 12) if "cpr" in pos.columns else 0.005
            start       = max(SNAPSHOT_DATES)
            y, m        = start.year, start.month
            balance     = total_mv
            proj_labels, proj_navs = [], []
            for _ in range(n_quarters):
                for _ in range(3):
                    balance *= (1 - monthly_cpr)
                m += 3
                if m > 12:
                    m -= 12
                    y += 1
                proj_labels.append(f"{y}-{m:02d}")
                proj_navs.append(round(balance / 1e9, 3))
        else:
            proj_labels, proj_navs = [], []

        return json.dumps({
            "hist_labels":   hist_labels,
            "hist_navs_B":   hist_navs,
            "proj_labels":   proj_labels,
            "proj_navs_B":   proj_navs,
            "current_nav_B": hist_navs[-1] if hist_navs else 0.0,
            "monthly_cpr_pct": round(float(pos["cpr"].mean()), 2) if not pos.empty else 0.0,
        }, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)})


def _handle_get_top_performers(inp: dict) -> str:
    top_n    = int(inp.get("top_n", 5))
    bottom_n = int(inp.get("bottom_n", 0))
    try:
        from data.position_data import get_position_data
        df = get_position_data()  # all snapshots
        dates = sorted(df["snapshot_date"].unique())
        if len(dates) < 2:
            return json.dumps({"error": "Need at least 2 snapshot dates to compute MTD returns.",
                                "available_dates": [str(d) for d in dates]})
        latest_dt, prev_dt = dates[-1], dates[-2]
        latest = df[df["snapshot_date"] == latest_dt]
        prev   = df[df["snapshot_date"] == prev_dt]

        rows = []
        for _, lr in latest.iterrows():
            pr = prev[prev["pool_id"] == lr["pool_id"]]
            if pr.empty:
                continue
            mv_now  = float(lr["market_value"])
            mv_prev = float(pr["market_value"].iloc[0])
            ret     = (mv_now - mv_prev) / mv_prev * 100 if mv_prev else 0.0
            base    = ret / 6
            rows.append({
                "pool_id":      lr["pool_id"],
                "cusip":        lr["cusip"],
                "product_type": lr["product_type"],
                "ret_pct":      round(ret, 3),
                "mv_now":       round(mv_now),
                "mv_prev":      round(mv_prev),
                "spark":        [round(base * j, 3) for j in range(7)],
            })
        rows.sort(key=lambda x: x["ret_pct"], reverse=True)

        top    = [{"rank": i + 1, **r} for i, r in enumerate(rows[:top_n])]
        bottom = [{"rank": len(rows) - i, **r} for i, r in enumerate(reversed(rows[-bottom_n:]))] if bottom_n else []

        return json.dumps({
            "as_of_date":   str(latest_dt),
            "prev_date":    str(prev_dt),
            "top":          top,
            "bottom":       bottom,
        }, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)})


def _handle_get_sector_allocation(inp: dict) -> str:
    date_str = inp.get("as_of_date", "")
    try:
        from datetime import datetime, date as date_type
        as_of = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None

        from data.position_data import get_position_data
        pos = get_position_data(as_of)
        if as_of is None:
            pos = pos[pos["snapshot_date"] == pos["snapshot_date"].max()]
        if pos.empty:
            return json.dumps({"error": "No position data available"})

        sector_map = {
            "CC30": "Conv 30-yr",   "CC15": "Conv 15-yr",
            "GN30": "GNMA 30-yr",   "GN15": "GNMA 15-yr",
            "ARM":  "ARM",          "TSY":  "Agency Debt",
            "CMBS": "CMBS",         "CMO":  "CMO",
            "CDBT": "Callable Debt",
        }
        total_mv = float(pos["market_value"].sum())
        sectors = []
        for ptype, label in sector_map.items():
            mv = float(pos[pos["product_type"] == ptype]["market_value"].sum())
            if mv > 0:
                sectors.append({
                    "product_type": ptype,
                    "label":        label,
                    "mv":           round(mv),
                    "pct":          round(mv / total_mv * 100, 1),
                })
        sectors.sort(key=lambda x: x["mv"], reverse=True)

        return json.dumps({
            "as_of_date":  str(pos["snapshot_date"].iloc[0]),
            "total_mv":    round(total_mv),
            "total_mv_B":  round(total_mv / 1e9, 3),
            "sectors":     sectors,
        }, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)})


def _handle_get_portfolio_health(inp: dict) -> str:
    date_str      = inp.get("as_of_date", "")
    benchmark_oad = float(inp.get("benchmark_oad", 4.2))
    try:
        from datetime import datetime
        as_of = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None

        from data.position_data import get_position_data, get_portfolio_summary
        pos     = get_position_data(as_of)
        if as_of is None:
            pos = pos[pos["snapshot_date"] == pos["snapshot_date"].max()]
        summary = get_portfolio_summary(as_of)
        if pos.empty or not summary:
            return json.dumps({"error": "No position data available"})

        total_mv = float(pos["market_value"].sum())

        # Duration Risk
        oad = float(summary.get("oad", benchmark_oad))
        dur_score = max(40, round(95 - abs(oad - benchmark_oad) * 20))
        dur_color = "#059669" if dur_score >= 80 else "#D97706" if dur_score >= 60 else "#E5484D"

        # Convexity
        avg_conv  = float(pos["convexity"].mean())
        conv_score = max(40, min(100, round(85 + avg_conv * 15)))
        conv_color = "#3B6FD4" if conv_score >= 70 else "#D97706" if conv_score >= 55 else "#E5484D"

        # Liquidity
        tba_mv  = float(pos[pos["product_type"].isin({"CC30","CC15","GN30","GN15"})]["market_value"].sum())
        liq_pct = tba_mv / total_mv * 100 if total_mv else 0.0
        liq_score = max(40, min(100, round(liq_pct)))
        liq_color = "#059669" if liq_score >= 80 else "#D97706" if liq_score >= 60 else "#E5484D"

        # Concentration
        def _issuer(pid: str) -> str:
            return pid.split("_")[0] if "_" in str(pid) else str(pid)
        tmp = pos.copy()
        tmp["_iss"] = tmp["pool_id"].apply(_issuer)
        top_pct = tmp.groupby("_iss")["market_value"].sum().max() / total_mv * 100 if total_mv else 0.0
        conc_score = max(40, min(100, round(100 - max(0, top_pct - 20) * 2)))
        conc_color = "#059669" if conc_score >= 80 else "#D97706" if conc_score >= 60 else "#E5484D"

        metrics = [
            {"name": "Duration Risk",  "score": dur_score,  "color": dur_color,
             "desc": f"OAD {oad:.2f} yr vs benchmark {benchmark_oad:.1f} yr"},
            {"name": "Convexity",      "score": conv_score, "color": conv_color,
             "desc": f"Avg convexity {avg_conv:.2f}"},
            {"name": "Credit Quality", "score": 100,        "color": "#059669",
             "desc": "Agency / GSE only"},
            {"name": "Liquidity",      "score": liq_score,  "color": liq_color,
             "desc": f"TBA-eligible {liq_pct:.0f}%"},
            {"name": "Concentration",  "score": conc_score, "color": conc_color,
             "desc": f"Top issuer {top_pct:.0f}%"},
        ]
        health_score = round(sum(m["score"] for m in metrics) / len(metrics))

        return json.dumps({
            "as_of_date":    str(pos["snapshot_date"].iloc[0]),
            "health_score":  health_score,
            "sub_metrics":   metrics,
        }, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)})


def _handle_get_watchlist(inp: dict) -> str:
    username = inp.get("username", "default")
    try:
        from data.watchlist_store import load_watchlist
        items = load_watchlist(username)
        if not items:
            return json.dumps({"username": username, "count": 0, "items": []})

        # Enrich with latest snapshot data
        try:
            from data.position_data import get_position_data
            pos = get_position_data()
            pos = pos[pos["snapshot_date"] == pos["snapshot_date"].max()]
        except Exception:
            pos = None

        enriched = []
        for item in items:
            cusip   = item.get("cusip", "")
            pool_id = item.get("pool_id", cusip)
            entry: dict[str, Any] = {
                "cusip":      cusip,
                "pool_id":    pool_id,
                "notes":      item.get("notes", ""),
                "added_at":   item.get("added_at", ""),
                "market_price":      None,
                "oad_years":         None,
                "oas_bps":           None,
                "product_type":      None,
                "unrealized_pnl_pct": None,
            }
            if pos is not None and not pos.empty:
                row = pos[pos["cusip"] == cusip]
                if not row.empty:
                    r = row.iloc[0]
                    entry.update({
                        "market_price":       round(float(r["market_price"]), 4),
                        "oad_years":          round(float(r["oad_years"]), 3),
                        "oas_bps":            round(float(r["oas_bps"]), 1),
                        "product_type":       r["product_type"],
                        "unrealized_pnl_pct": round(float(r["unrealized_pnl_pct"]), 3),
                    })
            enriched.append(entry)

        return json.dumps({"username": username, "count": len(enriched), "items": enriched}, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)})


def _handle_get_planning_session(inp: dict) -> str:
    username   = inp.get("username", "default")
    session_id = inp.get("session_id", "")
    try:
        from workflow.persistence.state_manager import StateManager
        sm = StateManager(username=username)

        if session_id:
            # Load a specific session synchronously
            path = sm._path(session_id)
            if not path.exists():
                return json.dumps({"found": False, "error": f"Session {session_id!r} not found"})
            import json as _json
            with open(path) as f:
                raw = _json.load(f)
        else:
            # Load latest via synchronous list_sessions + read
            sessions = sm.list_sessions()
            if not sessions:
                return json.dumps({"found": False, "message": "No planning sessions found for this user."})
            latest_meta = sorted(sessions, key=lambda s: s.get("updated_at", ""), reverse=True)[0]
            path = sm._path(latest_meta["session_id"])
            import json as _json
            with open(path) as f:
                raw = _json.load(f)

        # Return key fields; omit full purchase_schedule (can be large)
        schedule = raw.get("purchase_schedule", [])
        return json.dumps({
            "found":                   True,
            "session_id":              raw.get("session_id"),
            "phase":                   raw.get("phase"),
            "trader_name":             raw.get("trader_name"),
            "risk_appetite":           raw.get("risk_appetite"),
            "created_at":              raw.get("created_at"),
            "updated_at":              raw.get("updated_at"),
            "next_12m_new_volume_mm":  raw.get("next_12m_new_volume_mm"),
            "selected_scenario":       raw.get("selected_scenario"),
            "gate_decisions":          raw.get("gate_decisions", []),
            "purchase_schedule_count": len(schedule) if isinstance(schedule, list) else 0,
        }, default=str)
    except Exception as ex:
        return json.dumps({"error": str(ex)})


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "get_nav_projection":    _handle_get_nav_projection,
    "get_top_performers":    _handle_get_top_performers,
    "get_sector_allocation": _handle_get_sector_allocation,
    "get_portfolio_health":  _handle_get_portfolio_health,
    "get_watchlist":         _handle_get_watchlist,
    "get_planning_session":  _handle_get_planning_session,
}
