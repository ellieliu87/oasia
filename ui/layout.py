"""
PortfolioCopilot — Main Gradio Blocks layout.

Three-column design matching magnifi_dashboard.html:
  left (220 px)  — sidebar nav
  centre (flex)  — main content tabs (Dashboard · Security Selection · What-If · Analytics · Attribution)
  right (360 px) — inline NEXUS Agent chat panel

The dashboard tab is rendered as pure HTML via build_full_dashboard() and
Chart.js (CDN).  All other tabs use the existing Gradio feature modules.
"""
from __future__ import annotations

from ui.theme import CUSTOM_CSS, get_theme

import gradio as gr


# ─────────────────────────────────────────────────────────────────────────────
# Portfolio demo data (three scenarios)
# ─────────────────────────────────────────────────────────────────────────────

PORTFOLIO_STATE = {
    "default": {
        "nav":          2_847_320_000,
        "nav_chg":      +0.34,
        "book_yield":   5.82,
        "book_yield_chg": +0.08,
        "oad":          4.21,
        "oad_chg":      -0.12,
        "oas":          48,
        "oas_chg":      +3,
        "health_score": 84,
        "health_metrics": [
            {"name": "Duration Risk",    "desc": "OAD within ±0.5 of benchmark", "score": 91, "color": "#059669"},
            {"name": "Convexity",        "desc": "Negative convexity exposure",  "score": 76, "color": "#3B6FD4"},
            {"name": "Credit Quality",   "desc": "Agency / GSE only",            "score": 100,"color": "#059669"},
            {"name": "Liquidity",        "desc": "TBA-eligible ≥ 85 %",          "score": 88, "color": "#059669"},
            {"name": "Concentration",    "desc": "Single-issuer cap 35 %",       "score": 72, "color": "#D97706"},
        ],
        "holdings": [
            {"pool":"FNMA CC30 6.0", "cusip":"3140X7GK4", "par":  420_000_000, "price":101.14, "oad":4.8, "oas":52, "chg":+0.18},
            {"pool":"FHLMC CC30 5.5","cusip":"3132DXXX1", "par":  385_000_000, "price": 99.22, "oad":5.2, "oas":47, "chg":+0.09},
            {"pool":"GNMA GN30 6.0", "cusip":"36179MFD3", "par":  310_000_000, "price":101.56, "oad":4.3, "oas":38, "chg":-0.05},
            {"pool":"FNMA CC15 5.5", "cusip":"3140XTTT9", "par":  275_000_000, "price":100.88, "oad":3.1, "oas":41, "chg":+0.22},
            {"pool":"FHLMC CC15 6.0","cusip":"3132DYYY2", "par":  210_000_000, "price":101.34, "oad":3.4, "oas":43, "chg":-0.11},
        ],
        "sectors": [
            {"name":"Conv 30-yr",   "pct":38, "color":"#3B6FD4"},
            {"name":"Conv 15-yr",   "pct":17, "color":"#059669"},
            {"name":"GNMA 30-yr",   "pct":12, "color":"#D97706"},
            {"name":"GNMA 15-yr",   "pct":5,  "color":"#94A3B8"},
            {"name":"ARM",          "pct":8,  "color":"#8B5CF6"},
            {"name":"Agency Debt",  "pct":7,  "color":"#0891B2"},
            {"name":"CMBS",         "pct":6,  "color":"#F59E0B"},
            {"name":"CMO",          "pct":4,  "color":"#E5484D"},
            {"name":"Callable Debt","pct":3,  "color":"#64748B"},
        ],
        "performers": [
            {"rank":1, "name":"FNMA CC15 5.5",  "type":"Conv 15-yr", "ret":+2.14, "spark":[1.0,1.3,1.1,1.5,1.9,2.1,2.14]},
            {"rank":2, "name":"FHLMC CC30 5.5", "type":"Conv 30-yr", "ret":+1.87, "spark":[0.5,0.8,1.2,1.4,1.6,1.8,1.87]},
            {"rank":3, "name":"GNMA GN30 6.0",  "type":"GNMA 30-yr", "ret":+1.52, "spark":[0.3,0.6,0.9,1.1,1.3,1.5,1.52]},
            {"rank":4, "name":"FNMA CC30 6.0",  "type":"Conv 30-yr", "ret":+1.23, "spark":[0.2,0.4,0.6,0.8,0.9,1.1,1.23]},
            {"rank":5, "name":"FHLMC CC15 6.0", "type":"Conv 15-yr", "ret":+0.98, "spark":[0.1,0.2,0.4,0.6,0.7,0.9,0.98]},
        ],
        "watchlist": [
            {"name":"FNMA CC30 7.0","meta":"30-yr · 4.6 OAD","price":103.44,"chg":+0.28,"up":True},
            {"name":"FHLMC CC30 7.5","meta":"30-yr · 4.1 OAD","price":104.12,"chg":-0.15,"up":False},
            {"name":"GNMA GN15 6.5","meta":"15-yr · 3.0 OAD","price":102.34,"chg":+0.09,"up":True},
            {"name":"FNMA CC15 6.0","meta":"15-yr · 3.2 OAD","price":101.66,"chg":+0.34,"up":True},
        ],
        "chart_data": [2780,2795,2810,2803,2822,2835,2847],
        "chart_labels": ["Mon","Tue","Wed","Thu","Fri","Sat","Today"],
    },
    "stressed": {
        "nav":          2_691_000_000,
        "nav_chg":      -5.49,
        "book_yield":   6.14,
        "book_yield_chg": +0.32,
        "oad":          4.87,
        "oad_chg":      +0.66,
        "oas":          74,
        "oas_chg":      +26,
        "health_score": 61,
        "health_metrics": [
            {"name": "Duration Risk",    "desc": "OAD outside ±0.5 of benchmark","score": 54, "color": "#E5484D"},
            {"name": "Convexity",        "desc": "Negative convexity exposure",   "score": 48, "color": "#E5484D"},
            {"name": "Credit Quality",   "desc": "Agency / GSE only",             "score": 100,"color": "#059669"},
            {"name": "Liquidity",        "desc": "TBA-eligible ≥ 85 %",           "score": 71, "color": "#D97706"},
            {"name": "Concentration",    "desc": "Single-issuer cap 35 %",        "score": 60, "color": "#D97706"},
        ],
        "holdings": [
            {"pool":"FNMA CC30 6.0", "cusip":"3140X7GK4", "par":  420_000_000, "price": 97.80, "oad":5.4, "oas":78, "chg":-2.34},
            {"pool":"FHLMC CC30 5.5","cusip":"3132DXXX1", "par":  385_000_000, "price": 95.10, "oad":5.9, "oas":72, "chg":-3.12},
            {"pool":"GNMA GN30 6.0", "cusip":"36179MFD3", "par":  310_000_000, "price": 98.22, "oad":4.8, "oas":64, "chg":-1.78},
            {"pool":"FNMA CC15 5.5", "cusip":"3140XTTT9", "par":  275_000_000, "price": 97.44, "oad":3.6, "oas":66, "chg":-2.44},
            {"pool":"FHLMC CC15 6.0","cusip":"3132DYYY2", "par":  210_000_000, "price": 98.02, "oad":3.9, "oas":70, "chg":-2.01},
        ],
        "sectors": [
            {"name":"Conv 30-yr", "pct":54, "color":"#3B6FD4"},
            {"name":"Conv 15-yr", "pct":24, "color":"#059669"},
            {"name":"GNMA 30-yr", "pct":15, "color":"#D97706"},
            {"name":"GNMA 15-yr", "pct":7,  "color":"#94A3B8"},
        ],
        "performers": [
            {"rank":1, "name":"GNMA GN30 6.0",  "type":"GNMA 30-yr", "ret":-1.78, "spark":[0.2,-0.1,-0.5,-0.9,-1.2,-1.6,-1.78]},
            {"rank":2, "name":"FNMA CC15 5.5",   "type":"Conv 15-yr", "ret":-2.44, "spark":[0.1,-0.3,-0.8,-1.3,-1.8,-2.2,-2.44]},
            {"rank":3, "name":"FHLMC CC30 5.5",  "type":"Conv 30-yr", "ret":-3.12, "spark":[0.0,-0.4,-0.9,-1.5,-2.2,-2.7,-3.12]},
            {"rank":4, "name":"FNMA CC30 6.0",   "type":"Conv 30-yr", "ret":-3.55, "spark":[0.0,-0.5,-1.1,-1.8,-2.5,-3.1,-3.55]},
            {"rank":5, "name":"FHLMC CC15 6.0",  "type":"Conv 15-yr", "ret":-3.89, "spark":[0.0,-0.6,-1.2,-2.0,-2.7,-3.4,-3.89]},
        ],
        "watchlist": [
            {"name":"FNMA CC30 7.0","meta":"30-yr · 4.6 OAD","price": 99.12,"chg":-2.88,"up":False},
            {"name":"FHLMC CC30 7.5","meta":"30-yr · 4.1 OAD","price": 99.44,"chg":-3.44,"up":False},
            {"name":"GNMA GN15 6.5","meta":"15-yr · 3.0 OAD","price":100.10,"chg":-1.10,"up":False},
            {"name":"FNMA CC15 6.0","meta":"15-yr · 3.2 OAD","price": 98.88,"chg":-1.78,"up":False},
        ],
        "chart_data": [2847,2820,2790,2750,2710,2695,2691],
        "chart_labels": ["Mon","Tue","Wed","Thu","Fri","Sat","Today"],
    },
    "cheapPools": {
        "nav":          2_912_000_000,
        "nav_chg":      +2.27,
        "book_yield":   6.08,
        "book_yield_chg": +0.26,
        "oad":          4.05,
        "oad_chg":      -0.16,
        "oas":          62,
        "oas_chg":      +14,
        "health_score": 91,
        "health_metrics": [
            {"name": "Duration Risk",    "desc": "OAD within ±0.5 of benchmark","score": 95, "color": "#059669"},
            {"name": "Convexity",        "desc": "Negative convexity exposure",  "score": 88, "color": "#059669"},
            {"name": "Credit Quality",   "desc": "Agency / GSE only",            "score": 100,"color": "#059669"},
            {"name": "Liquidity",        "desc": "TBA-eligible ≥ 85 %",          "score": 92, "color": "#059669"},
            {"name": "Concentration",    "desc": "Single-issuer cap 35 %",       "score": 85, "color": "#059669"},
        ],
        "holdings": [
            {"pool":"FNMA CC30 6.0", "cusip":"3140X7GK4", "par":  420_000_000, "price":101.88, "oad":4.6, "oas":65, "chg":+0.74},
            {"pool":"FHLMC CC30 5.5","cusip":"3132DXXX1", "par":  385_000_000, "price":100.02, "oad":4.9, "oas":60, "chg":+0.80},
            {"pool":"GNMA GN30 6.0", "cusip":"36179MFD3", "par":  310_000_000, "price":102.14, "oad":4.0, "oas":51, "chg":+0.58},
            {"pool":"FNMA CC15 5.5", "cusip":"3140XTTT9", "par":  275_000_000, "price":101.44, "oad":2.9, "oas":55, "chg":+0.56},
            {"pool":"FHLMC CC15 6.0","cusip":"3132DYYY2", "par":  210_000_000, "price":102.00, "oad":3.2, "oas":57, "chg":+0.66},
        ],
        "sectors": [
            {"name":"Conv 30-yr", "pct":54, "color":"#3B6FD4"},
            {"name":"Conv 15-yr", "pct":24, "color":"#059669"},
            {"name":"GNMA 30-yr", "pct":15, "color":"#D97706"},
            {"name":"GNMA 15-yr", "pct":7,  "color":"#94A3B8"},
        ],
        "performers": [
            {"rank":1, "name":"FHLMC CC30 5.5", "type":"Conv 30-yr","ret":+0.80, "spark":[0.2,0.3,0.4,0.5,0.6,0.72,0.80]},
            {"rank":2, "name":"FNMA CC30 6.0",  "type":"Conv 30-yr","ret":+0.74, "spark":[0.1,0.2,0.35,0.45,0.56,0.68,0.74]},
            {"rank":3, "name":"GNMA GN30 6.0",  "type":"GNMA 30-yr","ret":+0.58, "spark":[0.1,0.2,0.3,0.38,0.45,0.52,0.58]},
            {"rank":4, "name":"FNMA CC15 5.5",  "type":"Conv 15-yr","ret":+0.41, "spark":[0.0,0.1,0.2,0.28,0.34,0.38,0.41]},
            {"rank":5, "name":"GNMA GN15 6.0",  "type":"GNMA 15-yr","ret":+0.27, "spark":[0.0,0.05,0.1,0.16,0.21,0.24,0.27]},
        ],
        "watchlist": [
            {"name":"FNMA CC30 7.0","meta":"30-yr · 4.6 OAD","price":104.20,"chg":+0.76,"up":True},
            {"name":"FHLMC CC30 7.5","meta":"30-yr · 4.1 OAD","price":105.00,"chg":+0.88,"up":True},
            {"name":"GNMA GN15 6.5","meta":"15-yr · 3.0 OAD","price":103.10,"chg":+0.76,"up":True},
            {"name":"FNMA CC15 6.0","meta":"15-yr · 3.2 OAD","price":102.44,"chg":+0.78,"up":True},
        ],
        "chart_data": [2847,2858,2870,2883,2896,2904,2912],
        "chart_labels": ["Mon","Tue","Wed","Thu","Fri","Sat","Today"],
    },
}


# ── Real data loaders ────────────────────────────────────────────────────────

def _get_all_positions_df():
    try:
        from data.position_data import _get_df
        return _get_df()
    except Exception:
        return None


def _load_watchlist_for_display() -> list[dict]:
    try:
        from data.watchlist_store import load_watchlist
        items = load_watchlist()
        try:
            from data.position_data import get_position_data
            pos = get_position_data()
        except Exception:
            pos = None
        result = []
        for item in items:
            cusip   = item.get("cusip", "")
            pool_id = item.get("pool_id", cusip)
            meta    = f"Added {item.get('added_at', '')}"
            price, chg, up = 100.0, 0.0, True
            if pos is not None and not pos.empty:
                row = pos[pos["cusip"] == cusip]
                if not row.empty:
                    r     = row.iloc[-1]
                    price = float(r["market_price"])
                    chg   = float(r["unrealized_pnl_pct"])
                    up    = chg >= 0
                    meta  = f"{r['product_type']} · {r['oad_years']:.1f} OAD"
            result.append({"name": pool_id, "meta": meta,
                           "price": price, "chg": round(chg, 2), "up": up})
        return result
    except Exception:
        return []


def _no_run_state() -> dict:
    """Empty state returned when no portfolio run has been performed."""
    return {
        "source":         "no_run",
        "nav":            None,
        "nav_chg":        None,
        "book_yield":     None,
        "book_yield_chg": None,
        "oad":            None,
        "oad_chg":        None,
        "oas":            None,
        "oas_chg":        None,
        "health_score":   None,
        "health_metrics": [],
        "holdings":       [],
        "sectors":        [],
        "performers":     [],
        "watchlist":      _load_watchlist_for_display(),
        "hist_labels":    [],
        "hist_navs":      [],
        "proj_labels":    [],
        "proj_navs":      [],
    }


def _load_dashboard_data(run_date: str = "Latest") -> dict:
    """Load real portfolio data from DB run. Returns no_run state if no run exists."""
    try:
        from db.projections import get_latest_portfolio_kpis, get_portfolio_projections

        # Check if a portfolio run exists in the DB
        kpis = get_latest_portfolio_kpis()
        if kpis is None:
            return _no_run_state()

        from data.position_data import (
            get_portfolio_summary, get_position_data, get_historical_nav
        )

        as_of = None
        if run_date and run_date != "Latest":
            try:
                from datetime import date as _date
                p = run_date.split("-")
                as_of = _date(int(p[0]), int(p[1]), int(p[2]))
            except Exception:
                pass

        summary = get_portfolio_summary(as_of)
        pos_df  = get_position_data(as_of)
        hist    = get_historical_nav()
        projs   = get_portfolio_projections(run_date=as_of, n_months=36)

        if not summary or pos_df.empty:
            raise ValueError("no position data")

        # Holdings from position data
        holdings = []
        for _, row in pos_df.sort_values("market_value", ascending=False).head(8).iterrows():
            name = (row["pool_id"].replace("_", " ")
                    .replace(".0 A", "").replace(".0 B", "").replace(".0 C", "")
                    .replace(".0 D", "").replace(".0 E", "").replace(".0 F", "")
                    .replace(".0 G", "").replace(".0 H", ""))
            holdings.append({
                "pool":  name,
                "cusip": row["cusip"],
                "par":   float(row["par_value"]),
                "price": float(row["market_price"]),
                "oad":   float(row["oad_years"]),
                "oas":   float(row["oas_bps"]),
                "chg":   float(row["unrealized_pnl_pct"]),
            })

        # Sector allocation
        sector_map = {
            "CC30": ("Conv 30-yr",   "#3B6FD4"),
            "GN30": ("GNMA 30-yr",   "#D97706"),
            "CC15": ("Conv 15-yr",   "#059669"),
            "GN15": ("GNMA 15-yr",   "#94A3B8"),
            "ARM":  ("ARM",          "#8B5CF6"),
            "TSY":  ("Agency Debt",  "#0891B2"),
            "CMBS": ("CMBS",         "#F59E0B"),
            "CMO":  ("CMO",          "#E5484D"),
            "CDBT": ("Callable Debt","#64748B"),
        }
        total_mv = pos_df["market_value"].sum()
        sectors = []
        for ptype, (sname, scolor) in sector_map.items():
            mv = pos_df[pos_df["product_type"] == ptype]["market_value"].sum()
            if mv > 0:
                sectors.append({"name": sname, "pct": max(1, round(mv / total_mv * 100)), "color": scolor})

        # Performers from MoM change
        performers = []
        all_df = _get_all_positions_df()
        if all_df is not None:
            dates = sorted(all_df["snapshot_date"].unique())
            if len(dates) >= 2:
                latest = all_df[all_df["snapshot_date"] == dates[-1]]
                prev   = all_df[all_df["snapshot_date"] == dates[-2]]
                perf_rows = []
                for _, lr in latest.iterrows():
                    pr = prev[prev["pool_id"] == lr["pool_id"]]
                    if pr.empty:
                        continue
                    mv_now  = float(lr["market_value"])
                    mv_prev = float(pr["market_value"].iloc[0])
                    ret     = (mv_now - mv_prev) / mv_prev * 100 if mv_prev else 0.0
                    perf_rows.append({
                        "name": str(lr["pool_id"]).replace("_", " "),
                        "type": str(lr["product_type"]),
                        "ret":  round(ret, 2),
                    })
                perf_rows.sort(key=lambda x: x["ret"], reverse=True)
                for i, p in enumerate(perf_rows[:3], 1):
                    base  = p["ret"] / 6
                    spark = [round(base * j, 3) for j in range(7)]
                    performers.append({"rank": i, **p, "spark": spark})
        if not performers:
            performers = []

        # Health metrics — all computed from real position data
        oad = float(summary.get("oad", 4.2))
        dur_score = max(40, round(95 - abs(oad - 4.2) * 20))
        dur_color = "#059669" if dur_score >= 80 else "#D97706" if dur_score >= 60 else "#E5484D"

        # Convexity score: higher (less negative) convexity = better
        avg_convexity = float(pos_df["convexity"].mean()) if not pos_df.empty else 0.0
        conv_score = max(40, min(100, round(85 + avg_convexity * 15)))
        conv_color = "#3B6FD4" if conv_score >= 70 else "#D97706" if conv_score >= 55 else "#E5484D"

        # Liquidity: % of MV in TBA-eligible product types
        tba_types = {"CC30", "CC15", "GN30", "GN15"}
        tba_mv  = pos_df[pos_df["product_type"].isin(tba_types)]["market_value"].sum() if not pos_df.empty else 0
        liq_pct = tba_mv / total_mv * 100 if total_mv > 0 else 0.0
        liq_score = max(40, min(100, round(liq_pct)))
        liq_color = "#059669" if liq_score >= 80 else "#D97706" if liq_score >= 60 else "#E5484D"

        # Concentration: largest single issuer by MV %
        if not pos_df.empty:
            def _issuer(pid: str) -> str:
                return pid.split("_")[0] if "_" in str(pid) else str(pid)
            issuer_mv = pos_df.copy()
            issuer_mv["issuer_key"] = issuer_mv["pool_id"].apply(_issuer)
            top_issuer_pct = issuer_mv.groupby("issuer_key")["market_value"].sum().max() / total_mv * 100 if total_mv > 0 else 0.0
        else:
            top_issuer_pct = 0.0
        conc_score = max(40, min(100, round(100 - max(0, top_issuer_pct - 20) * 2)))
        conc_color = "#059669" if conc_score >= 80 else "#D97706" if conc_score >= 60 else "#E5484D"

        health_metrics = [
            {"name": "Duration Risk",  "desc": f"OAD {oad:.2f} vs bench 4.2",
             "score": dur_score, "color": dur_color},
            {"name": "Convexity",      "desc": f"Avg convexity {avg_convexity:.2f}",
             "score": conv_score, "color": conv_color},
            {"name": "Credit Quality", "desc": "Agency / GSE only",
             "score": 100, "color": "#059669"},
            {"name": "Liquidity",      "desc": f"TBA-eligible {liq_pct:.0f}%",
             "score": liq_score, "color": liq_color},
            {"name": "Concentration",  "desc": f"Top issuer {top_issuer_pct:.0f}%",
             "score": conc_score, "color": conc_color},
        ]
        health_score = round(sum(m["score"] for m in health_metrics) / len(health_metrics))

        # Historical chart data
        hist_labels = [str(h["date"])[:7] for h in hist]
        hist_navs   = [round(h["nav"] / 1e9, 3) for h in hist]

        # Projection chart data (next 36 months)
        proj_labels = [str(p.get("projection_date", ""))[:7] for p in projs[:36]]
        proj_navs   = [round(float(p.get("portfolio_nav", 0)) / 1e9, 3) for p in projs[:36]]

        # KPI from projections (already loaded above — kpis is guaranteed non-None here)
        book_yield = float(summary.get("book_yield", 5.5))
        oas_val    = round(float(summary.get("oas", 48)))
        if kpis:
            if kpis.get("book_yield"):
                by = float(kpis["book_yield"])
                # Normalise: decimal (0.054) → %, already-% (5.44) → keep, stale ×100 bug (544) → divide
                if by > 50:
                    book_yield = by / 100
                elif by > 1.0:
                    book_yield = by
                else:
                    book_yield = by * 100
            if kpis.get("oad"):
                oad = float(kpis["oad"])
            if kpis.get("oas"):
                oas_val = round(float(kpis["oas"]))

        return {
            "source":         "real",
            "nav":            float(summary.get("nav", 0)),
            "nav_chg":        float(summary.get("nav_chg", 0.0)),
            "book_yield":     book_yield,
            "book_yield_chg": (lambda v: v * 100 if abs(v) < 0.5 else v)(float(summary.get("book_yield_chg", 0.0))),
            "oad":            oad,
            "oad_chg":        float(summary.get("oad_chg", 0.0)),
            "oas":            oas_val,
            "oas_chg":        int(summary.get("oas_chg", 0)),
            "health_score":   health_score,
            "health_metrics": health_metrics,
            "holdings":       holdings,
            "sectors":        sectors,
            "performers":     performers,
            "watchlist":      _load_watchlist_for_display(),
            "chart_data":     hist_navs,
            "chart_labels":   hist_labels,
            "hist_navs":      hist_navs,
            "hist_labels":    hist_labels,
            "proj_navs":      proj_navs,
            "proj_labels":    proj_labels,
        }
    except Exception as _ex:
        import logging
        logging.getLogger("nexus").warning("_load_dashboard_data error: %s", _ex)
        # Return zero/empty state — never use hardcoded demo numbers for the default view
        return {
            "source":         "empty",
            "nav":            0.0,
            "nav_chg":        0.0,
            "book_yield":     0.0,
            "book_yield_chg": 0.0,
            "oad":            0.0,
            "oad_chg":        0.0,
            "oas":            0,
            "oas_chg":        0,
            "health_score":   0,
            "health_metrics": [],
            "holdings":       [],
            "sectors":        [],
            "performers":     [],
            "watchlist":      _load_watchlist_for_display(),
            "hist_labels":    [],
            "hist_navs":      [],
            "proj_labels":    [],
            "proj_navs":      [],
        }


# ─────────────────────────────────────────────────────────────────────────────
# HTML builders
# ─────────────────────────────────────────────────────────────────────────────

def build_run_needed_banner() -> str:
    """Banner shown on the dashboard when no portfolio run data exists in the DB."""
    return (
        '<div style="display:flex;align-items:center;gap:12px;padding:14px 20px;'
        'background:#FEF3C7;border:1px solid #D97706;border-radius:8px;margin-bottom:16px;">'
        '<span style="font-size:20px;">⚠️</span>'
        '<div>'
        '<div style="font-weight:700;color:#92400E;font-size:13px;">No portfolio run data found</div>'
        '<div style="color:#B45309;font-size:12px;margin-top:2px;">'
        'Dashboard metrics are unavailable. Go to the <strong>Portfolio Analytics</strong> tab '
        'and click <strong>Run</strong> to generate a portfolio run, then return here to view results.'
        '</div>'
        '</div>'
        '</div>'
    )


def _fmt_nav(v: float) -> str:
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.0f}M"
    return f"${v:,.0f}"


def _badge(val, unit=""):
    sign = "+" if val > 0 else ""
    cls  = "badge-up" if val >= 0 else "badge-down"
    arrow = "▲" if val >= 0 else "▼"
    return f'<span class="badge {cls}">{arrow} {sign}{val}{unit}</span>'


def build_kpi_cards(data: dict) -> str:
    def kpi(label, value, sub_html, accent_color):
        return (
            f'<div class="card kpi-card">'
            f'  <div class="kpi-label">{label}</div>'
            f'  <div class="kpi-value">{value}</div>'
            f'  <div class="kpi-sub">{sub_html}</div>'
            f'  <div class="kpi-accent" style="background:{accent_color};"></div>'
            f'</div>'
        )

    no_data = data.get("source") in ("no_run", "empty") or data.get("nav") is None

    if no_data:
        blank = '<span style="color:#94A3B8;">--</span>'
        na    = '<span style="color:#94A3B8;font-size:11px;">no run data</span>'
        return (
            f'<div class="kpi-grid">'
            + kpi("Total Portfolio NAV",  blank, na, "#3B6FD4")
            + kpi("Book Yield",           blank, na, "#059669")
            + kpi("OA Duration",          blank, na, "#D97706")
            + kpi("Avg OAS",              blank, na, "#E5484D")
            + '</div>'
        )

    chg_nav = _badge(round(data["nav_chg"], 2), "%")
    chg_by  = _badge(round(data["book_yield_chg"], 2), "%")
    chg_oad = _badge(round(data["oad_chg"], 2))
    chg_oas = _badge(data["oas_chg"], " bps")
    return (
        f'<div class="kpi-grid">'
        + kpi("Total Portfolio NAV",  _fmt_nav(data["nav"]),            f'{chg_nav} vs last close',     "#3B6FD4")
        + kpi("Book Yield",           f'{data["book_yield"]:.2f}%',     f'{chg_by} from last month',    "#059669")
        + kpi("OA Duration",          f'{data["oad"]:.2f}',             f'{chg_oad} vs benchmark',      "#D97706")
        + kpi("Avg OAS",              f'{data["oas"]} bps',             f'{chg_oas} WTD',               "#E5484D")
        + '</div>'
    )


def _compute_proj_mv(n_quarters: int = 12) -> tuple[list, list]:
    """Quarterly projected market value ($B) from the latest position snapshot."""
    try:
        from data.position_data import get_position_data, SNAPSHOT_DATES
        df  = get_position_data()
        pos = df[df["snapshot_date"] == df["snapshot_date"].max()]
        if pos.empty:
            return [], []
        total_mv    = float(pos["market_value"].sum())
        monthly_cpr = float(pos["cpr"].mean() / 100 / 12) if "cpr" in pos.columns else 0.005
        start = max(SNAPSHOT_DATES)
        y, m  = start.year, start.month
        balance = total_mv
        labels, navs = [], []
        for _ in range(n_quarters):
            for _ in range(3):
                balance *= (1 - monthly_cpr)
            m += 3
            if m > 12:
                m -= 12
                y += 1
            labels.append(f"{y}-{m:02d}")
            navs.append(round(balance / 1e9, 3))
        return labels, navs
    except Exception:
        return [], []


def _build_mv_svg(
    all_labels: list,
    h_pts: list,
    p_pts: list,
    has_proj: bool,
    n_hist: int,
) -> str:
    """Pure-SVG line chart — no JavaScript, no CDN dependency."""
    W, H = 760, 178
    ML, MR, MT, MB = 62, 16, 16, 38
    pw, ph = W - ML - MR, H - MT - MB
    n = len(all_labels)
    if n == 0:
        return '<text x="50%" y="50%" text-anchor="middle" fill="#94A3B8" font-size="12">No data</text>'

    all_vals = [v for v in h_pts + p_pts if v is not None]
    if not all_vals:
        return '<text x="50%" y="50%" text-anchor="middle" fill="#94A3B8" font-size="12">No data</text>'

    min_v = min(all_vals) * 0.993
    max_v = max(all_vals) * 1.007
    span  = max(max_v - min_v, 1e-9)

    def px(i):  return ML + (i / max(n - 1, 1)) * pw
    def py(v):  return MT + ph * (1.0 - (v - min_v) / span)

    def make_path(pts):
        segs, cur = [], []
        for i, v in enumerate(pts):
            if v is None:
                if cur: segs.append(cur); cur = []
            else: cur.append(f"{px(i):.1f},{py(v):.1f}")
        if cur: segs.append(cur)
        return " ".join("M " + " L ".join(s) for s in segs if s)

    hist_path = make_path(h_pts)
    proj_path = make_path(p_pts) if has_proj else ""

    # Filled area under hist line
    h_coords = [(px(i), py(v)) for i, v in enumerate(h_pts) if v is not None]
    area_svg = ""
    if h_coords:
        pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in h_coords)
        area_svg = (
            f'<polygon points="{pts_str} {h_coords[-1][0]:.1f},{MT+ph:.1f} '
            f'{h_coords[0][0]:.1f},{MT+ph:.1f}" fill="#05996912"/>'
        )

    # Y-axis grid + labels (5 ticks)
    grid_svg = ylbl_svg = ""
    for k in range(5):
        v  = min_v + span * k / 4
        yy = py(v)
        grid_svg += f'<line x1="{ML}" y1="{yy:.1f}" x2="{W-MR}" y2="{yy:.1f}" stroke="#E2E8F0" stroke-width="0.6"/>'
        ylbl_svg += (f'<text x="{ML-4}" y="{yy+4:.1f}" text-anchor="end" font-size="10" '
                     f'fill="#94A3B8" font-family="JetBrains Mono,monospace">${v:.2f}B</text>')

    # X-axis labels (≤ 8)
    xlbl_svg = ""
    step = max(1, n // 8)
    for i in range(0, n, step):
        xi = px(i)
        xlbl_svg += (f'<text x="{xi:.1f}" y="{MT+ph+16}" text-anchor="middle" font-size="9" '
                     f'fill="#94A3B8" font-family="JetBrains Mono,monospace">{all_labels[i]}</text>')

    # Dashed vertical divider at hist/proj boundary
    div_svg = ""
    if has_proj and n_hist > 0:
        xd = px(n_hist - 1)
        div_svg = f'<line x1="{xd:.1f}" y1="{MT}" x2="{xd:.1f}" y2="{MT+ph}" stroke="#CBD5E1" stroke-width="1" stroke-dasharray="3,3"/>'

    proj_svg = ""
    if has_proj and proj_path:
        proj_svg = (f'<path d="{proj_path}" fill="none" stroke="#3B6FD4" stroke-width="2" '
                    f'stroke-dasharray="6,4" stroke-linecap="round" stroke-linejoin="round"/>')

    legend_svg = ""
    if has_proj:
        lx = W - MR - 195
        legend_svg = (
            f'<line x1="{lx}" y1="9" x2="{lx+18}" y2="9" stroke="#059669" stroke-width="2"/>'
            f'<text x="{lx+22}" y="13" font-size="10" fill="#64748B" font-family="DM Sans,sans-serif">Historical</text>'
            f'<line x1="{lx+92}" y1="9" x2="{lx+110}" y2="9" stroke="#3B6FD4" stroke-width="2" stroke-dasharray="5,3"/>'
            f'<text x="{lx+114}" y="13" font-size="10" fill="#64748B" font-family="DM Sans,sans-serif">Projected</text>'
        )

    return (
        f'<svg viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;">'
        + grid_svg + area_svg
        + f'<path d="{hist_path}" fill="none" stroke="#059669" stroke-width="2.5" '
          f'stroke-linecap="round" stroke-linejoin="round"/>'
        + proj_svg + div_svg + ylbl_svg + xlbl_svg + legend_svg
        + '</svg>'
    )


def build_projection_chart(data: dict) -> str:
    """Portfolio Market Value chart: historical snapshots + 3-year projected MV (pure SVG)."""
    nav_b     = round(data["nav"] / 1e9, 3)
    chg       = data["nav_chg"]
    chg_cls   = "badge-up" if chg >= 0 else "badge-down"
    chg_arrow = "▲" if chg >= 0 else "▼"
    chg_sign  = "+" if chg >= 0 else ""

    hist_labels = data.get("hist_labels", data.get("chart_labels", []))
    hist_navs   = data.get("hist_navs",   data.get("chart_data",  []))
    proj_labels = data.get("proj_labels", [])
    proj_navs   = data.get("proj_navs",   [])

    # Normalise demo chart_data (stored as $M × 1000 → convert to $B)
    if hist_navs and max(v for v in hist_navs if v) > 100:
        hist_navs = [round(v / 1000, 3) for v in hist_navs]

    # Build combined axis
    extra_proj = [l for l in proj_labels if l not in hist_labels]
    all_labels = hist_labels + extra_proj
    n          = len(all_labels)
    n_hist     = len(hist_navs)

    h_pts: list = [float(v) for v in hist_navs] + [None] * len(extra_proj)
    has_proj = bool(proj_navs)
    if has_proj:
        p_pts: list = [None] * (n_hist - 1) + [float(hist_navs[-1])] + [float(v) for v in proj_navs]
        p_pts = p_pts[:n] + [None] * max(0, n - len(p_pts))
    else:
        p_pts = [None] * n

    svg = _build_mv_svg(all_labels, h_pts, p_pts, has_proj, n_hist)
    proj_legend_html = (
        '<span style="font-size:11px;color:#94A3B8;margin-left:8px;">— projected</span>'
    ) if has_proj else ""

    return f"""
<div class="card portfolio-chart-card">
  <div class="card-header">
    <span class="card-title-serif">Portfolio Market Value &amp; 3-Year Projection</span>
    <div style="display:flex;align-items:center;gap:12px;">
      <span style="font-family:var(--serif);font-size:22px;color:var(--navy);">${nav_b}B</span>
      <span class="badge {chg_cls}">{chg_arrow} {chg_sign}{chg}%</span>
      {proj_legend_html}
    </div>
  </div>
  <div class="chart-wrap">
    {svg}
  </div>
</div>
"""


def build_sector_chart(data: dict) -> str:
    s = data
    if not s.get("sectors"):
        return ('<div class="card sector-card"><div class="card-header">'
                '<span class="card-title-serif">Sector Allocation</span></div>'
                '<div style="padding:24px;text-align:center;color:#94A3B8;font-size:13px;">No position data</div></div>')
    rows = ""
    for sec in s["sectors"]:
        rows += (
            f'<div class="sector-row">'
            f'  <div class="sector-color" style="background:{sec["color"]};"></div>'
            f'  <span class="sector-name">{sec["name"]}</span>'
            f'  <div class="sector-bar-wrap"><div class="sector-bar" style="width:{sec["pct"]}%;background:{sec["color"]};"></div></div>'
            f'  <span class="sector-pct">{sec["pct"]}%</span>'
            f'</div>'
        )
    return f"""
<div class="card sector-card">
  <div class="card-header">
    <span class="card-title-serif">Sector Allocation</span>
  </div>
  <div class="sector-list">{rows}</div>
</div>
"""


def build_health_card(data: dict) -> str:
    s = data
    metrics_html = ""
    for m in s["health_metrics"]:
        bar_w = m["score"]
        metrics_html += f"""
        <div class="health-metric">
          <div class="hm-left">
            <div class="hm-name">{m["name"]}</div>
            <div class="hm-desc">{m["desc"]}</div>
          </div>
          <div class="hm-right">
            <div class="hm-bar-wrap"><div class="hm-bar" style="width:{bar_w}%;background:{m["color"]};"></div></div>
            <span class="hm-score" style="color:{m["color"]};">{m["score"]}</span>
          </div>
        </div>"""
    return f"""
<div class="card health-card" style="display:flex;flex-direction:column;">
  <div class="card-header">
    <span class="card-title-serif">Portfolio Health</span>
    <span class="card-action">Details →</span>
  </div>
  <div class="health-metrics">{metrics_html}</div>
</div>
"""


def build_holdings_card(data: dict) -> str:
    s = data
    if not s.get("holdings"):
        return ('<div class="card"><div class="card-header">'
                '<span class="card-title-serif">Top Holdings</span></div>'
                '<div style="padding:24px;text-align:center;color:#94A3B8;font-size:13px;">No position data</div></div>')
    rows = ""
    for h in s["holdings"][:5]:
        chg_cls = "delta-pos" if h["chg"] >= 0 else "delta-neg"
        sign    = "+" if h["chg"] >= 0 else ""
        par_m   = h["par"] / 1e6
        rows += f"""
        <tr>
          <td><div class="pool-name">{h["pool"]}</div><div class="pool-sub">{h["cusip"]}</div></td>
          <td>${par_m:.0f}M</td>
          <td>{h["price"]:.2f}</td>
          <td>{h["oad"]:.1f}</td>
          <td>{h["oas"]}</td>
          <td class="{chg_cls}">{sign}{h["chg"]:.2f}</td>
        </tr>"""
    return f"""
<div class="card">
  <div class="card-header">
    <span class="card-title-serif">Top Holdings</span>
    <span class="card-action">View all →</span>
  </div>
  <div style="padding:0 4px 4px;overflow-x:auto;">
    <table class="holdings-table">
      <thead><tr>
        <th>Pool</th><th>Par ($)</th><th>Price</th><th>OAD</th><th>OAS</th><th>Chg</th>
      </tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
</div>
"""


def _spark_script(cid: str, spark_js: str, color: str) -> str:
    """Return a <script> block that renders a sparkline Chart.js chart (no f-string nesting)."""
    return (
        "<script>(function(){"
        "var c=document.getElementById('" + cid + "');"
        "if(!c)return;"
        "new Chart(c,{type:'line',data:{labels:" + spark_js + ",datasets:[{data:" + spark_js + ","
        "borderColor:'" + color + "',borderWidth:1.5,tension:0.4,pointRadius:0,fill:false}]},"
        "options:{responsive:false,plugins:{legend:{display:false},tooltip:{enabled:false}},"
        "scales:{x:{display:false},y:{display:false}}}});"
        "})();</script>"
    )


def build_performers_card(data: dict) -> str:
    s = data
    if not s.get("performers"):
        return ('<div class="card"><div class="card-header">'
                '<span class="card-title-serif">Top Performers</span>'
                '<span class="card-action">This month</span></div>'
                '<div style="padding:24px;text-align:center;color:#94A3B8;font-size:13px;">Insufficient snapshot history</div></div>')
    rows = ""
    for p in s["performers"][:5]:
        pos         = p["ret"] >= 0
        rcls        = "performer-return" + ("" if pos else " neg")
        sign        = "+" if pos else ""
        spark_color = "#059669" if pos else "#E5484D"
        spark_js    = str(p["spark"])
        cid         = f"spark-{p['rank']}-live"
        rows += (
            f'<div class="performer-row">'
            f'  <span class="performer-rank">#{p["rank"]}</span>'
            f'  <div class="performer-info">'
            f'    <div class="performer-name">{p["name"]}</div>'
            f'    <div class="performer-type">{p["type"]}</div>'
            f'  </div>'
            f'  <canvas class="performer-chart" id="{cid}" width="60" height="28"></canvas>'
            f'  <span class="{rcls}">{sign}{p["ret"]:.2f}%</span>'
            f'</div>'
            + _spark_script(cid, spark_js, spark_color)
        )
    col_hdr = (
        '<div class="performer-col-hdr">'
        '  <span class="performer-col-rank">Rank</span>'
        '  <span class="performer-col-pool">Pool · Sector</span>'
        '  <span class="performer-col-trend">Trend</span>'
        '  <span class="performer-col-ret">MTD Return</span>'
        '</div>'
    )
    return (
        '<div class="card">'
        '<div class="card-header">'
        '<span class="card-title-serif">Top Performers</span>'
        '<span class="card-action">This month</span>'
        '</div>'
        f'{col_hdr}'
        f'<div class="performer-list">{rows}</div>'
        '</div>'
    )


def build_watchlist_card(data: dict, username: str = "default") -> str:
    s = data
    # Load real watchlist for this user; fall back to demo data if empty
    try:
        from data.watchlist_store import load_watchlist
        store_items = load_watchlist(username)
        # Also try "default" as a fallback so demo data is visible on first run
        if not store_items and username != "default":
            store_items = load_watchlist("default")
    except Exception:
        store_items = []

    if store_items:
        watchlist_items = []
        for item in store_items:
            cusip   = item.get("cusip", "")
            pool_id = item.get("pool_id", cusip)
            added   = item.get("added_at", "")
            meta    = f"Added {added[:10]}" if added else pool_id
            watchlist_items.append({
                "name":  pool_id or cusip,
                "meta":  meta,
                "price": "--",
                "chg":   "--",
                "up":    True,
            })
    else:
        watchlist_items = s.get("watchlist", [])

    rows = ""
    for w in watchlist_items:
        price_val = f"{w['price']:.2f}" if isinstance(w["price"], float) else str(w["price"])
        chg_val   = f"+{w['chg']:.2f}" if (isinstance(w["chg"], float) and w["up"]) else (
                    f"{w['chg']:.2f}" if isinstance(w["chg"], float) else str(w["chg"]))
        chg_cls   = "watch-price-chg" + (" delta-pos" if w["up"] else " delta-neg")
        rows += f"""
        <div class="watch-row">
          <span class="watch-star">★</span>
          <div class="watch-info">
            <div class="watch-name">{w["name"]}</div>
            <div class="watch-meta">{w["meta"]}</div>
          </div>
          <div class="watch-price">
            <div class="watch-price-val">{price_val}</div>
            <div class="{chg_cls}">{chg_val}</div>
          </div>
        </div>"""
    return f"""
<div class="card holdings-card">
  <div class="card-header">
    <span class="card-title-serif">Watchlist</span>
    <span class="card-action" onclick="document.querySelectorAll('#nexus-main-tabs button[role=tab]')[4]?.click()" style="cursor:pointer;">Manage →</span>
  </div>
  <div class="watch-list">{rows}</div>
</div>
"""


def build_full_dashboard(run_date: str = "Latest", scenario: str = "default",
                         username: str = "default") -> str:
    if scenario and scenario != "default":
        data = dict(PORTFOLIO_STATE.get(scenario, PORTFOLIO_STATE["default"]))
        data["source"]      = "demo"
        data["hist_labels"] = list(data.get("chart_labels", []))
        data["hist_navs"]   = [round(v / 1000, 3) for v in data.get("chart_data", [])]
        data["proj_labels"] = []
        data["proj_navs"]   = []
        data["watchlist"]   = _load_watchlist_for_display()
    else:
        data = _load_dashboard_data(run_date)
    # Compute projected MV only when real data is present (not for no_run/empty states)
    if not data.get("proj_navs") and data.get("source") not in ("no_run", "empty"):
        data["proj_labels"], data["proj_navs"] = _compute_proj_mv()

    is_no_run  = data.get("source") in ("no_run", "empty")
    run_banner = build_run_needed_banner() if is_no_run else ""

    kpis       = build_kpi_cards(data)
    chart      = build_projection_chart(data)
    health     = build_health_card(data)
    holdings   = build_holdings_card(data)
    sector     = build_sector_chart(data)
    performers = build_performers_card(data)
    watchlist  = build_watchlist_card(data, username=username)
    src_badge  = '' if data.get("source") == "real" else '<span style="font-size:10px;color:#94A3B8;margin-left:8px;">[demo data]</span>'
    date_label = f"Data as of {run_date}" if run_date and run_date != "Latest" else "Latest data"

    return f"""
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<div class="nexus-tab-content fade-up">

  {run_banner}

  <!-- KPIs -->
  {kpis}

  <!-- Main dashboard grid: chart + health/sector left, watchlist right -->
  <div class="dashboard-grid">
    {chart}
    {health}
    {watchlist}
    {sector}
  </div>

  <!-- Bottom row: top performers + top holdings -->
  <div class="bottom-grid">
    {performers}
    {holdings}
  </div>

</div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Static HTML fragments
# ─────────────────────────────────────────────────────────────────────────────

def _get_market_pills_html() -> str:
    try:
        from data.market_data import get_current_market_data
        md       = get_current_market_data()
        tsy_10y  = md.treasury_curve.zero_rate(10.0) * 100
        tsy_2y   = md.treasury_curve.zero_rate(2.0)  * 100
        sofr_5y  = md.sofr_curve.zero_rate(5.0)      * 100
        oas_cc30 = md.cohort_oas.get("CC30_6.0", 55)
    except Exception:
        tsy_10y, tsy_2y, sofr_5y, oas_cc30 = 4.60, 4.45, 4.65, 55

    def pill(label, val, val_color="var(--text)"):
        return (
            f'<div class="market-pill">'
            f'<span class="pill-label">{label}</span>'
            f'<span class="pill-val" style="color:{val_color}">{val}</span>'
            f'</div>'
        )

    live = (
        '<div class="market-pill" style="background:#ECFDF5;">'
        '<span style="width:6px;height:6px;border-radius:50%;background:#059669;'
        'display:inline-block;margin-right:4px;"></span>'
        '<span class="pill-val" style="color:#059669;">LIVE</span>'
        '</div>'
    )
    return (
        pill("10Y",     f"{tsy_10y:.3f}%") +
        pill("2Y",      f"{tsy_2y:.3f}%") +
        pill("SOFR",    f"{sofr_5y:.3f}%") +
        pill("CC30 OAS",f"{oas_cc30} bps", "var(--blue)") +
        live
    )


TOPBAR_HTML = """
<div id="nexus-topbar">
  <div class="logo">
    <div class="logo-dot"></div>
    Oasia
  </div>
  <div class="topbar-search">
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
         fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
      <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
    </svg>
    <input type="text" placeholder="Search pools, CUSIPs, analytics…" id="nexus-search">
  </div>
  <div id="nexus-topbar-market" style="display:flex;align-items:center;gap:8px;"></div>
  <div class="topbar-right">
    <div id="nexus-topbar-date"
         style="font-family:'JetBrains Mono',monospace;font-size:12px;color:#64748B;white-space:nowrap;"></div>
    <div class="avatar-wrap" id="nexus-avatar-wrap">
      <div class="avatar" id="nexus-avatar">N</div>
      <div class="avatar-menu" id="nexus-avatar-menu">
        <div class="avatar-menu-header">
          <div id="nexus-avatar-name" style="font-size:13px;font-weight:600;color:#0F172A;"></div>
          <div style="font-size:11px;color:#64748B;margin-top:2px;">Agency MBS Trading</div>
        </div>
        <div class="avatar-menu-divider"></div>
        <form method="POST" action="/logout" style="margin:0;">
          <button type="submit" class="avatar-menu-item avatar-menu-logout">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24"
                 fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
              <polyline points="16 17 21 12 16 7"/>
              <line x1="21" y1="12" x2="9" y2="12"/>
            </svg>
            Sign out
          </button>
        </form>
      </div>
    </div>
  </div>
</div>
"""

SIDEBAR_HTML = """
<div id="nexus-sidebar-inner">
  <div class="nav-section">
    <div class="nav-label">Main</div>
    <div class="nav-item active" id="nav-0" data-idx="0">
      <span class="nav-icon">⊡</span> Dashboard
    </div>
    <div class="nav-item" id="nav-1" data-idx="1">
      <span class="nav-icon">▣</span> Portfolio Analytics
    </div>
    <div class="nav-item" id="nav-2" data-idx="2">
      <span class="nav-icon">⊞</span> Security Analytics
    </div>
    <div class="nav-item" id="nav-3" data-idx="3">
      <span class="nav-icon">↑↓</span> Attribution
    </div>
    <div class="nav-item" id="nav-5" data-idx="5">
      <span class="nav-icon">⚡</span> Portfolio Planning
    </div>
  </div>
  <div class="sidebar-footer">
    <div class="nav-item" id="nav-4" data-idx="4" style="margin-bottom:12px;">
      <span class="nav-icon">★</span> Watchlist
    </div>
    <div id="nexus-user-card-placeholder"></div>
  </div>
</div>
"""

_FAB_AND_POPUP_HTML = """
<button id="nexus-agent-fab" aria-label="Open Oasia Agent">✦</button>

<div id="nexus-agent-popup" role="dialog" aria-label="Oasia Agent">
  <div style="background:linear-gradient(135deg,#0F1F3D 0%,#1A3060 100%);padding:16px 20px;display:flex;align-items:center;gap:12px;flex-shrink:0;">
    <div style="width:36px;height:36px;border-radius:50%;background:rgba(255,255,255,0.15);display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;color:white;">✦</div>
    <div style="flex:1;min-width:0;overflow:hidden;">
      <div style="font-size:14px;font-weight:700;color:white;font-family:system-ui,sans-serif;line-height:1.2;">Oasia Agent</div>
      <div style="font-size:11px;color:rgba(255,255,255,0.65);display:flex;align-items:center;gap:5px;font-family:system-ui,sans-serif;margin-top:3px;"><span class="live-dot"></span>7 agents · OpenAI SDK</div>
    </div>
    <button id="nexus-popup-close"
            style="flex-shrink:0;background:rgba(255,255,255,0.12);border:none;
                   color:white;width:28px;height:28px;border-radius:50%;cursor:pointer;
                   font-size:14px;display:flex;align-items:center;justify-content:center;
                   transition:background 0.15s;">✕</button>
  </div>
  <div id="nexus-agent-chat-mount" style="flex:1;display:flex;flex-direction:column;overflow:hidden;"></div>
</div>
"""

# ── All JavaScript — injected via gr.Blocks(js=_INIT_JS) ─────────────────────
# Gradio 6.x strips onclick/script from gr.HTML(); gr.Blocks(js=...) is reliable.
_INIT_JS = """
(function () {
  'use strict';

  // ── Topbar date ─────────────────────────────────────────────────────────
  function setupDate() {
    var el = document.getElementById('nexus-topbar-date');
    if (!el) return;
    var d = new Date();
    var DAYS   = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
    var MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    el.textContent = DAYS[d.getDay()] + ', ' + MONTHS[d.getMonth()] + ' ' + d.getDate() + ' ' + d.getFullYear();
  }

  // ── Market pill sync ────────────────────────────────────────────────────
  function setupPillSync() {
    function syncPills() {
      var src = document.getElementById('nexus-market-pills-src');
      var dst = document.getElementById('nexus-topbar-market');
      if (!src || !dst) return;
      var c = src.innerHTML.trim();
      if (c && c !== dst.innerHTML) dst.innerHTML = c;
    }
    syncPills();
    var obs = new MutationObserver(syncPills);
    obs.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  // ── Sidebar navigation ──────────────────────────────────────────────────
  function setupSidebar() {
    document.addEventListener('click', function (e) {
      var item = e.target.closest('#nexus-sidebar-inner .nav-item[data-idx]');
      if (!item) return;
      var idx = parseInt(item.getAttribute('data-idx'), 10);
      document.querySelectorAll('#nexus-sidebar-inner .nav-item').forEach(function (el) {
        el.classList.remove('active');
      });
      item.classList.add('active');
      function trySwitch() {
        var tabs = document.getElementById('nexus-main-tabs');
        if (!tabs) return false;
        var btns = tabs.querySelectorAll('button[role="tab"]');
        if (!btns || !btns.length) btns = tabs.querySelectorAll('.tab-nav button');
        if (btns && btns[idx]) { btns[idx].click(); return true; }
        return false;
      }
      if (!trySwitch()) { setTimeout(trySwitch, 150); setTimeout(trySwitch, 400); }
    });
  }

  // ── FAB + popup toggle ──────────────────────────────────────────────────
  function setupFAB() {
    var _open = false;
    function toggle() {
      var popup = document.getElementById('nexus-agent-popup');
      var fab   = document.getElementById('nexus-agent-fab');
      if (!popup || !fab) return;
      _open = !_open;
      if (_open) {
        popup.classList.add('open');
        fab.textContent = '✕';
        fab.style.background = 'linear-gradient(135deg,#1A3060,#3B6FD4)';
      } else {
        popup.classList.remove('open');
        fab.textContent = '✦';
        fab.style.background = '';
      }
    }
    window.nexusToggleAgent = toggle;
    document.addEventListener('click', function (e) {
      if (e.target.closest('#nexus-agent-fab') || e.target.closest('#nexus-popup-close')) {
        toggle();
      }
    });
  }

  // ── Quick chip injection ────────────────────────────────────────────────
  function setupChips() {
    function sendChip(text) {
      var popup = document.getElementById('nexus-agent-popup');
      if (popup && !popup.classList.contains('open') && window.nexusToggleAgent) {
        window.nexusToggleAgent();
      }
      var area = document.querySelector('#nexus-msg-input textarea');
      if (!area) return;
      var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      setter.call(area, text);
      area.dispatchEvent(new Event('input', { bubbles: true }));
      setTimeout(function () {
        var btn = document.querySelector('#nexus-send-btn');
        if (btn) btn.click();
      }, 60);
    }
    window.nexusChip = sendChip;
    document.addEventListener('click', function (e) {
      var chip = e.target.closest('.qchip[data-query]');
      if (chip) sendChip(chip.getAttribute('data-query'));
    });
  }

  // ── Scenario switcher ───────────────────────────────────────────────────
  function setupScenarios() {
    function switchScenario(key) {
      var sel = document.querySelector('#nexus-scenario-selector select');
      if (sel) {
        var nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
        nativeSetter.call(sel, key);
        sel.dispatchEvent(new Event('change', { bubbles: true }));
        return;
      }
      document.querySelectorAll('#nexus-scenario-selector input').forEach(function (inp) {
        if (inp.value === key) inp.click();
      });
    }
    window.nexusScenario = switchScenario;
    document.addEventListener('click', function (e) {
      var btn = e.target.closest('[data-scenario]');
      if (btn) switchScenario(btn.getAttribute('data-scenario'));
    });
  }

  // ── Fix chat flex layout after teleport ─────────────────────────────────
  // Walks from #nexus-chatbot up to #nexus-agent-chat-mount, applying flex
  // properties to every unknown Svelte/Gradio wrapper div along the way.
  function fixChatLayout() {
    var chatbot = document.getElementById('nexus-chatbot');
    var mount   = document.getElementById('nexus-agent-chat-mount');
    if (!chatbot || !mount) return;
    var node = chatbot.parentElement;
    while (node && node !== mount) {
      node.style.setProperty('display',        'flex',        'important');
      node.style.setProperty('flex-direction', 'column',      'important');
      node.style.setProperty('flex',           '1 1 0',       'important');
      node.style.setProperty('min-height',     '0',           'important');
      node.style.setProperty('overflow',       'hidden',      'important');
      node.style.setProperty('background',     'transparent', 'important');
      node.style.setProperty('border',         'none',        'important');
      node.style.setProperty('box-shadow',     'none',        'important');
      node.style.setProperty('padding',        '0',           'important');
      node.style.setProperty('margin',         '0',           'important');
      node.style.setProperty('gap',            '0',           'important');
      node = node.parentElement;
    }
    chatbot.style.setProperty('flex',       '1 1 0', 'important');
    chatbot.style.setProperty('min-height', '0',     'important');
    chatbot.style.setProperty('height',     'auto',  'important');
    var inputBar = document.getElementById('nexus-input-bar');
    if (inputBar) inputBar.style.setProperty('flex-shrink', '0', 'important');
  }

  // ── Teleport Gradio components into popup ───────────────────────────────
  function setupTeleport() {
    function teleport() {
      var staging = document.getElementById('nexus-agent-staging');
      var mount   = document.getElementById('nexus-agent-chat-mount');
      if (!staging || !mount) return false;
      if (!staging.querySelector('textarea, .gradio-chatbot, [class*="chatbot"]')) return false;
      if (mount.querySelector('textarea, .gradio-chatbot, [class*="chatbot"]')) {
        fixChatLayout();
        return true;
      }
      while (staging.firstChild) mount.appendChild(staging.firstChild);
      fixChatLayout();
      return true;
    }
    var attempts = 0;
    function tryTeleport() {
      if (teleport()) return;
      if (++attempts < 40) setTimeout(tryTeleport, 250);
    }
    var obs = new MutationObserver(function () { if (teleport()) obs.disconnect(); });
    var staging = document.getElementById('nexus-agent-staging');
    if (staging) obs.observe(staging, { childList: true, subtree: true });
    setTimeout(tryTeleport, 300);
  }

  // ── Popup resize (left edge, top edge, corner) ─────────────────────────
  function setupResize() {
    var popup = document.getElementById('nexus-agent-popup');
    if (!popup) { setTimeout(setupResize, 400); return; }

    // Inject three hit-area divs
    var corner = document.createElement('div'); corner.id = 'nexus-resize-corner';
    var left   = document.createElement('div'); left.id   = 'nexus-resize-left';
    var top    = document.createElement('div'); top.id    = 'nexus-resize-top';
    popup.appendChild(corner);
    popup.appendChild(left);
    popup.appendChild(top);

    var MIN_W = 300, MAX_W = Math.round(window.innerWidth  * 0.85);
    var MIN_H = 280, MAX_H = Math.round(window.innerHeight * 0.88);

    function startDrag(e, resizeW, resizeH) {
      e.preventDefault();
      e.stopPropagation();
      var rect  = popup.getBoundingClientRect();
      var origX = e.clientX, origY = e.clientY;
      var origW = rect.width,  origH = rect.height;
      var handle = e.currentTarget;
      handle.classList.add('dragging');
      document.body.style.userSelect = 'none';
      document.body.style.cursor = getComputedStyle(handle).cursor;

      function onMove(ev) {
        // Popup anchored bottom-right: drag LEFT increases W, drag UP increases H
        if (resizeW) {
          var newW = Math.max(MIN_W, Math.min(MAX_W, origW + (origX - ev.clientX)));
          popup.style.width = newW + 'px';
        }
        if (resizeH) {
          var newH = Math.max(MIN_H, Math.min(MAX_H, origH + (origY - ev.clientY)));
          popup.style.height = newH + 'px';
        }
      }
      function onUp() {
        handle.classList.remove('dragging');
        document.body.style.userSelect = '';
        document.body.style.cursor = '';
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
      }
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    }

    corner.addEventListener('mousedown', function(e) { startDrag(e, true,  true);  });
    left.addEventListener(  'mousedown', function(e) { startDrag(e, true,  false); });
    top.addEventListener(   'mousedown', function(e) { startDrag(e, false, true);  });

    // Keep limits in sync if window resizes
    window.addEventListener('resize', function() {
      MAX_W = Math.round(window.innerWidth  * 0.85);
      MAX_H = Math.round(window.innerHeight * 0.88);
    });
  }

  // ── Dropdown scroll-close ────────────────────────────────────────────────
  // Gradio 6.x positions [role="listbox"] as position:fixed using its own
  // internal JS (calculate_window_distance / refElement.getBoundingClientRect).
  // We must NOT override that positioning — it already works correctly.
  // We only close open dropdowns when the user scrolls, because their fixed
  // position would become stale relative to the input anchor.
  function setupDropdownFix() {
    document.addEventListener('scroll', function () {
      document.querySelectorAll('[role="listbox"]').forEach(function (list) {
        // Gradio hides via visibility:hidden (not display:none)
        if (getComputedStyle(list).visibility === 'hidden') return;
        var wrap = list.closest('.wrap') || list.parentElement;
        var inp  = wrap && (wrap.querySelector('input') || wrap.querySelector('textarea'));
        if (inp) {
          inp.dispatchEvent(new KeyboardEvent('keydown',
            { key: 'Escape', keyCode: 27, bubbles: true }));
          inp.blur();
        }
      });
    }, true); // capture phase — fires before scroll reaches children
  }

  // ── Schedule popup — pure JS, no Gradio round-trip for open/close ───────
  // The popup column (visible=True in Gradio) is hidden by CSS by default.
  // JS adds/removes the 'sched-open' class to show/hide it instantly,
  // avoiding any server round-trip that would cause DOM reflow/blink.
  function setupSchedPopup() {
    var backdrop = document.createElement('div');
    backdrop.id = 'nexus-sched-backdrop';
    document.body.appendChild(backdrop);

    var _open = false;

    function openPopup() {
      var popup = document.getElementById('nexus-sched-popup');
      if (!popup) return;
      _open = true;
      popup.classList.add('sched-open');
      backdrop.style.display = 'block';
    }

    function closePopup() {
      var popup = document.getElementById('nexus-sched-popup');
      if (!popup) return;
      _open = false;
      popup.classList.remove('sched-open');
      backdrop.style.display = 'none';
    }

    document.addEventListener('click', function(e) {
      if (e.target.closest('#nexus-sched-toggle-btn')) {
        if (_open) closePopup(); else openPopup();
        return;
      }
      if (e.target.closest('#nexus-sched-close-btn')) { closePopup(); return; }
      if (e.target === backdrop) { closePopup(); return; }
    });
  }

  // ── Zero-out pre-body-row Gradio wrapper divs that add unwanted height ──
  // Gradio wraps every top-level component in a div. Wrappers for hidden
  // helpers (market pills, FAB HTML, timer) must not add vertical space.
  function fixTopLevelGaps() {
    var bodyRow = document.getElementById('nexus-body-row');
    if (!bodyRow) { setTimeout(fixTopLevelGaps, 200); return; }
    var wrap = bodyRow.parentElement;
    if (!wrap) return;
    Array.from(wrap.children).forEach(function(child) {
      if (child.id === 'nexus-body-row') return;
      if (child.contains(document.getElementById('nexus-topbar'))) return;
      child.style.setProperty('height',     '0',       'important');
      child.style.setProperty('min-height', '0',       'important');
      child.style.setProperty('max-height', '0',       'important');
      child.style.setProperty('overflow',   'hidden',  'important');
      child.style.setProperty('padding',    '0',       'important');
      child.style.setProperty('margin',     '0',       'important');
      child.style.setProperty('border',     'none',    'important');
      child.style.setProperty('font-size',  '0',       'important');
      child.style.setProperty('line-height','0',       'important');
    });
  }

  // ── Watchlist JS→Gradio bridge ──────────────────────────────────────────
  // The "+ Watch" and "Remove" buttons live inside gr.HTML, so they can't
  // fire Gradio events directly.  We bridge them via a hidden Textbox +
  // hidden Button: JS sets the text to "add|CUSIP|POOL" or "remove|CUSIP",
  // then programmatically clicks the hidden Gradio button.
  function setupWatchlistActions() {
    function nexusWatchlistAction(action, cusip, poolId) {
      // Find the hidden textbox (Gradio renders it as <input> or <textarea>)
      var wrap = document.getElementById('nexus-wl-action-input');
      if (!wrap) { console.warn('[nexus] nexus-wl-action-input not found'); return; }
      var inp = wrap.querySelector('textarea') || wrap.querySelector('input[type="text"]') || wrap.querySelector('input');
      if (!inp) { console.warn('[nexus] no input inside nexus-wl-action-input'); return; }
      var proto = (inp.tagName === 'TEXTAREA')
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
      var setter = Object.getOwnPropertyDescriptor(proto, 'value');
      if (setter && setter.set) {
        setter.set.call(inp, action + '|' + cusip + '|' + (poolId || ''));
      } else {
        inp.value = action + '|' + cusip + '|' + (poolId || '');
      }
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      inp.dispatchEvent(new Event('change', { bubbles: true }));
      // Click the hidden trigger button after a short delay
      setTimeout(function () {
        var btnWrap = document.getElementById('nexus-wl-action-btn');
        if (!btnWrap) { console.warn('[nexus] nexus-wl-action-btn not found'); return; }
        var btn = btnWrap.querySelector('button');
        if (btn) btn.click();
      }, 80);
    }
    // Keep window.* helpers for backwards compat (onclick handlers in static HTML)
    window.nexusAddWatchlistFromSearch = function (cusip, pool) {
      nexusWatchlistAction('add', cusip, pool || cusip);
    };
    window.nexusRemoveWatchlist = function (cusip) {
      nexusWatchlistAction('remove', cusip, '');
    };
    // Event delegation — handles buttons with data-nexus-cusip attributes.
    // Gradio 6 sanitizes dynamically-set HTML and strips onclick attributes,
    // so we use data-* attributes + a document-level click listener instead.
    // Use capture=true so the event fires before Gradio's internal handlers
    // can stop propagation, and works even inside shadow DOM boundaries.
    document.addEventListener('click', function (e) {
      var target = e.target;
      // Walk up the DOM tree to find the button (in case the click hit a child element)
      var btn = null;
      var node = target;
      while (node && node !== document.body) {
        if (node.classList && (node.classList.contains('nexus-watch-btn') || node.classList.contains('nexus-remove-btn'))) {
          btn = node;
          break;
        }
        node = node.parentElement;
      }
      if (!btn) return;
      var cusip = btn.getAttribute('data-nexus-cusip');
      if (!cusip) return;
      e.stopPropagation();
      if (btn.classList.contains('nexus-watch-btn')) {
        var pool = btn.getAttribute('data-nexus-pool') || cusip;
        nexusWatchlistAction('add', cusip, pool);
      } else if (btn.classList.contains('nexus-remove-btn')) {
        nexusWatchlistAction('remove', cusip, '');
      }
    }, true); // capture phase — fires before Gradio's internal event handling
  }

  // ── Avatar menu (logout dropdown) ───────────────────────────────────────
  function setupAvatarMenu() {
    var wrap = document.getElementById('nexus-avatar-wrap');
    var menu = document.getElementById('nexus-avatar-menu');
    if (!wrap || !menu) return;

    // Toggle open/close on avatar click
    wrap.addEventListener('click', function (e) {
      e.stopPropagation();
      menu.classList.toggle('open');
    });

    // Close when clicking outside
    document.addEventListener('click', function () {
      menu.classList.remove('open');
    });

    // Sync displayed username from the user-card in the sidebar
    function syncUsername() {
      var nameEl = document.getElementById('nexus-avatar-name');
      if (!nameEl) return;
      var card = document.querySelector('#nexus-user-card .user-name');
      if (card && card.textContent && card.textContent !== 'Loading…') {
        nameEl.textContent = card.textContent;
        // Update avatar initial
        var avatar = document.getElementById('nexus-avatar');
        if (avatar) avatar.textContent = card.textContent.charAt(0).toUpperCase();
      }
    }
    syncUsername();
    // Re-sync after Gradio populates the user card
    var obs = new MutationObserver(syncUsername);
    obs.observe(document.body, { childList: true, subtree: true, characterData: true });
  }

  // ── Boot ────────────────────────────────────────────────────────────────
  setupDate();
  setupPillSync();
  setupSidebar();
  setupFAB();
  setupChips();
  setupScenarios();
  setupTeleport();
  setupResize();
  setupDropdownFix();
  setupSchedPopup();
  fixTopLevelGaps();
  setupWatchlistActions();
  setupAvatarMenu();
})();
"""


# ─────────────────────────────────────────────────────────────────────────────
# Workflow schedule helpers
# ─────────────────────────────────────────────────────────────────────────────

_DOW_CHOICES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _build_dash_header_html(date_label: str = "Latest data", n_positions: int = 5) -> str:
    return (
        f'<div class="dash-header-left">'
        f'  <div class="dash-header-title">Good morning, Trader</div>'
        f'  <div class="dash-header-sub">'
        f'    Agency MBS Portfolio &nbsp;·&nbsp; {n_positions} positions'
        f'    &nbsp;·&nbsp; {date_label}'
        f'  </div>'
        f'</div>'
    )


def _get_available_run_dates() -> list[str]:
    """Return distinct run dates from projections and risk_metrics_cache."""
    dates = set()
    try:
        from db.projections import list_projection_run_dates
        for d in list_projection_run_dates():
            dates.add(d)
    except Exception:
        pass
    try:
        from db.cache import query
        rows = query(
            "SELECT DISTINCT CAST(as_of_date AS VARCHAR) AS d "
            "FROM risk_metrics_cache ORDER BY d DESC LIMIT 30"
        )
        for r in rows:
            if r.get("d"):
                dates.add(r["d"])
    except Exception:
        pass
    sorted_dates = sorted(dates, reverse=True)
    return ["Latest"] + sorted_dates if sorted_dates else ["Latest"]


def _scheduler_status_html(status: dict | None = None) -> str:
    """Render the workflow run-status card (with progress bar when running)."""
    if status is None:
        try:
            from workflow.scheduler import get_scheduler
            status = get_scheduler().get_status()
        except Exception:
            status = {"status": "unavailable", "config": {}, "last_result": None,
                      "next_run": "", "progress": {}}

    st   = status.get("status", "idle")
    cfg  = status.get("config", {})
    lr   = status.get("last_result")
    nxt  = status.get("next_run", "")
    prog = status.get("progress", {})

    badge_color = {
        "idle": "#64748B", "running": "#3B6FD4",
        "success": "#059669", "partial": "#D97706", "failed": "#E5484D",
    }.get(st, "#64748B")

    spinner = (
        '<span class="sched-spinner"></span>'
        if st == "running" else
        f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
        f'background:{badge_color};margin-right:6px;vertical-align:middle;"></span>'
    )

    # Progress bar (only when running)
    if st == "running" and prog.get("total", 0) > 0:
        pct  = prog.get("pct", 0.0)
        msg  = prog.get("message", "")
        done = prog.get("done", 0)
        tot  = prog.get("total", 0)
        progress_block = f"""
        <div class="sched-progress-wrap">
          <div class="sched-progress-bar">
            <div class="sched-progress-fill" style="width:{pct:.1f}%;"></div>
          </div>
          <div class="sched-progress-label">{msg} — {pct:.0f}% ({done}/{tot})</div>
        </div>"""
    elif st == "running":
        progress_block = '<div class="sched-progress-label">Initialising…</div>'
    else:
        progress_block = ""

    # Last run block
    if lr:
        dur_min = lr["duration_secs"] // 60
        dur_sec = lr["duration_secs"] % 60
        dur_str = f"{dur_min:.0f}m {dur_sec:.0f}s" if dur_min else f"{dur_sec:.0f}s"
        fail_str = (
            f' <span style="color:#E5484D;">({lr["pools_failed"]} failed)</span>'
            if lr["pools_failed"] else ""
        )
        last_block = f"""
        <div class="sched-row">
          <span class="sched-label">Last run</span>
          <span class="sched-val">{lr["started_at"]}</span>
        </div>
        <div class="sched-row">
          <span class="sched-label">Duration</span>
          <span class="sched-val">{dur_str}</span>
        </div>
        <div class="sched-row">
          <span class="sched-label">Pools processed</span>
          <span class="sched-val">{lr["pools_processed"]}{fail_str}</span>
        </div>"""
        if lr.get("error"):
            last_block += (
                f'<div class="sched-row"><span class="sched-label">Error</span>'
                f'<span class="sched-val" style="color:#E5484D;">{lr["error"][:80]}</span></div>'
            )
    else:
        last_block = '<div class="sched-row"><span class="sched-val" style="color:#94A3B8;">No runs yet</span></div>'

    freq    = cfg.get("frequency", "daily").capitalize()
    hour    = cfg.get("hour", 6)
    enabled = cfg.get("enabled", False)
    next_block = (
        f'<div class="sched-row"><span class="sched-label">Next run</span>'
        f'<span class="sched-val">{nxt}</span></div>'
        if (enabled and nxt) else
        '<div class="sched-row"><span class="sched-val" style="color:#94A3B8;">'
        'Schedule not configured</span></div>'
    )

    return f"""
<div class="sched-status-card">
  <div class="sched-header">
    <span class="sched-title">Run Status</span>
    <span style="font-size:12px;font-family:var(--mono);color:{badge_color};">{spinner}{st.upper()}</span>
  </div>
  <div class="sched-body">
    {progress_block}
    {('<div class="sched-divider"></div>' if progress_block else '') + last_block}
    <div class="sched-divider"></div>
    {next_block}
    {'<div class="sched-row"><span class="sched-label">Schedule</span>'
     f'<span class="sched-val">{freq} at {hour:02d}:00 UTC</span></div>'
     if enabled else ''}
  </div>
</div>
"""


# ─────────────────────────────────────────────────────────────────────────────
# Layout builder
# ─────────────────────────────────────────────────────────────────────────────

def get_launch_kwargs() -> dict:
    """Return theme/CSS/JS kwargs to pass to demo.launch() in Gradio 6.x."""
    return {"theme": get_theme(), "css": CUSTOM_CSS, "js": _INIT_JS}


def _get_session_username(request: gr.Request) -> str:
    """Extract authenticated username from the session cookie."""
    try:
        from auth.session import get_username, COOKIE_NAME
        token = request.request.cookies.get(COOKIE_NAME)
        return get_username(token) or "unknown"
    except Exception:
        return "unknown"


def _render_user_card(username: str) -> str:
    """Render the sidebar user-card HTML with the given username."""
    initials = username[:1].upper() if username and username != "unknown" else "?"
    display  = username if username and username != "unknown" else "Loading…"
    return (
        '<div class="user-card">'
        f'  <div class="avatar" style="width:32px;height:32px;font-size:12px;font-weight:700;flex-shrink:0;">{initials}</div>'
        '  <div class="user-info">'
        f'    <div class="user-name">{display}</div>'
        '    <div class="user-role">Agency MBS Trading</div>'
        '  </div>'
        '  <form method="POST" action="/logout" style="margin-left:auto;">'
        '    <button type="submit" title="Sign out"'
        '      style="background:none;border:none;color:#64748B;cursor:pointer;font-size:16px;'
        '             padding:4px;border-radius:4px;transition:color 0.15s;"'
        '      onmouseover="this.style.color=\'#E5484D\'" onmouseout="this.style.color=\'#64748B\'">&#9211;</button>'
        '  </form>'
        '</div>'
    )


def create_layout() -> gr.Blocks:
    """Build and return the complete Oasia Gradio Blocks layout."""
    from ui.security_analytics   import create_security_analytics_tab
    from ui.portfolio_analytics  import create_portfolio_analytics_tab
    from ui.attribution          import create_attribution_tab
    from ui.agent_panel          import create_agent_panel, wire_agent_panel
    from ui.watchlist            import create_watchlist_tab
    from ui.portfolio_planning   import create_portfolio_planning_tab

    with gr.Blocks(title="Oasia", theme=get_theme(), css=CUSTOM_CSS, js=_INIT_JS) as demo:

        # ── Shared state ─────────────────────────────────────────────────
        shared_state       = gr.State({})
        username_state     = gr.State("unknown")
        orchestrator_state = gr.State({})
        dashboard_state    = gr.State({"filter_product": None, "refresh_count": 0, "scenario": "default"})

        # ── Topbar (full-width, above body row) ───────────────────────────
        gr.HTML(TOPBAR_HTML)

        # Hidden Gradio-managed market pills source; JS copies into topbar
        with gr.Column(elem_id="nexus-market-hidden-col",
                       visible=True,
                       scale=0):
            market_pills = gr.HTML(
                value=_get_market_pills_html(),
                elem_id="nexus-market-pills-src",
            )

        # ── FAB + floating agent popup (position:fixed via CSS) ─────────
        gr.HTML(_FAB_AND_POPUP_HTML)

        # ── Schedule timer (non-visual — declared here at Blocks level) ──
        sched_timer = gr.Timer(value=10)

        # ── Body row: sidebar | main tabs ────────────────────────────────
        with gr.Row(elem_id="nexus-body-row", equal_height=True):

            # ── Left sidebar ──────────────────────────────────────────────
            with gr.Column(scale=0, min_width=220, elem_id="nexus-sidebar-col"):
                gr.HTML(SIDEBAR_HTML)
                sidebar_user_html = gr.HTML(
                    value=_render_user_card(""),
                    elem_id="nexus-user-card",
                )

            # ── Main content tabs ─────────────────────────────────────────
            with gr.Column(scale=3, elem_id="nexus-main-col"):
                with gr.Tabs(elem_id="nexus-main-tabs"):

                    with gr.Tab("Dashboard", id=0):

                        # ── Header row: greeting left, controls right ──────
                        with gr.Row(elem_id="nexus-dash-header-row"):
                            dash_header = gr.HTML(
                                value=_build_dash_header_html(),
                                elem_id="nexus-dash-header-left",
                                scale=3,
                            )
                            with gr.Column(
                                scale=0, min_width=320,
                                elem_id="nexus-dash-header-right",
                            ):
                                with gr.Row(elem_classes=["dash-ctrl-row"]):
                                    run_date_dd = gr.Dropdown(
                                        choices=_get_available_run_dates(),
                                        value="Latest",
                                        show_label=False,
                                        container=False,
                                        interactive=True,
                                        elem_id="nexus-run-date-dd",
                                        scale=0,
                                        min_width=150,
                                    )
                                    toggle_sched_btn = gr.Button(
                                        "⚙  Workflow Schedule",
                                        variant="secondary", size="sm",
                                        elem_id="nexus-sched-toggle-btn",
                                        scale=0,
                                    )

                        # ── Schedule popup (always in DOM; CSS+JS controls visibility) ──
                        with gr.Column(visible=True, elem_id="nexus-sched-popup") as sched_panel:
                            with gr.Row(elem_classes=["sched-popup-hdr"]):
                                gr.HTML('<div class="sched-popup-title">Workflow Schedule</div>')
                                close_popup_btn = gr.Button(
                                    "✕", elem_id="nexus-sched-close-btn",
                                    variant="secondary", size="sm", scale=0,
                                )
                            with gr.Column(elem_classes=["sched-freq-col"]):
                                freq_dd = gr.Radio(
                                    choices=["Daily", "Weekly", "Monthly"],
                                    value="Daily", label="Run Frequency",
                                    interactive=True, elem_id="nexus-sched-freq",
                                )
                            with gr.Row(elem_classes=["sched-inputs-row"]):
                                hour_slider = gr.Slider(
                                    minimum=0, maximum=23, step=1, value=6,
                                    label="Hour (UTC)", interactive=True, scale=2,
                                )
                                day_dd = gr.Dropdown(
                                    choices=_DOW_CHOICES, value="Monday",
                                    label="Day of week", visible=False,
                                    interactive=True, container=False, scale=1,
                                )
                                dom_input = gr.Number(
                                    value=1, minimum=1, maximum=28, precision=0,
                                    label="Day of month", visible=False,
                                    interactive=True, scale=1,
                                )
                            with gr.Row(elem_classes=["sched-action-row"]):
                                save_sched_btn = gr.Button("Save Schedule", variant="primary",  size="sm", scale=1)
                                run_now_btn    = gr.Button("▶  Run Now",    variant="secondary", size="sm", scale=1)
                            schedule_status = gr.HTML(value="", elem_id="nexus-schedule-status", visible=False)

                        dashboard_html = gr.HTML(
                            value=build_full_dashboard(),
                            elem_id="nexus-dashboard-html",
                        )

                    with gr.Tab("Portfolio Analytics", id=1):
                        with gr.Column(elem_classes=["nexus-tab-content"]):
                            create_portfolio_analytics_tab(shared_state)

                    with gr.Tab("Security Analytics", id=2):
                        with gr.Column(elem_classes=["nexus-tab-content"]):
                            create_security_analytics_tab(shared_state)

                    with gr.Tab("Attribution", id=3):
                        with gr.Column(elem_classes=["nexus-tab-content"]):
                            create_attribution_tab(shared_state)

                    with gr.Tab("Watchlist", id=4):
                        with gr.Column(elem_classes=["nexus-tab-content"]):
                            create_watchlist_tab(shared_state, dashboard_html)

                    with gr.Tab("Portfolio Planning", id=5):
                        with gr.Column(elem_classes=["nexus-tab-content"]):
                            create_portfolio_planning_tab(shared_state)

        # ── Agent staging: off-screen, teleported into popup by JS ───────
        with gr.Column(elem_id="nexus-agent-staging"):
            chatbot, msg_input, send_btn, clear_btn = create_agent_panel()

        # ── Wire agent events ────────────────────────────────────────────
        wire_agent_panel(
            chatbot, msg_input, send_btn, clear_btn,
            orchestrator_state, dashboard_state,
        )

        # ── Market refresh button (hidden; advanced users can enable) ─────
        with gr.Column(visible=False):
            refresh_btn = gr.Button("↻ Refresh market data", size="sm", variant="secondary")
        refresh_btn.click(fn=_get_market_pills_html, outputs=[market_pills])

        # ── Scenario switcher (driven by JS nexusScenario → hidden dropdown) ─
        scenario_selector = gr.Dropdown(
            choices=["default", "stressed", "cheapPools"],
            value="default",
            visible=False,
            elem_id="nexus-scenario-selector",
        )

        def _switch_scenario(scenario: str):
            return build_full_dashboard(scenario=scenario)

        scenario_selector.change(
            fn=_switch_scenario,
            inputs=[scenario_selector],
            outputs=[dashboard_html],
        )

        # ── Workflow schedule events ──────────────────────────────────────
        # Note: popup open/close is handled entirely by JS (setupSchedPopup).
        # No Gradio click handlers needed for toggle/close — that avoids the
        # server round-trip that caused DOM reflow and visible blinking.

        # Show/hide day-of-week / day-of-month pickers based on frequency
        def _on_freq_change(freq: str):
            return (
                gr.update(visible=(freq == "Weekly")),
                gr.update(visible=(freq == "Monthly")),
            )

        freq_dd.change(
            fn=_on_freq_change,
            inputs=[freq_dd],
            outputs=[day_dd, dom_input],
        )

        # Save schedule config
        def _save_schedule(freq, hour, day, dom):
            try:
                from workflow.scheduler import get_scheduler
                dow = _DOW_CHOICES.index(day) if day in _DOW_CHOICES else 0
                get_scheduler().configure(freq, int(hour), dow, int(dom))
            except Exception:
                pass
            return gr.update(value=_scheduler_status_html(), visible=True)

        save_sched_btn.click(
            fn=_save_schedule,
            inputs=[freq_dd, hour_slider, day_dd, dom_input],
            outputs=[schedule_status],
        )

        # Run Now — triggers run and reveals status card
        def _run_now():
            try:
                from workflow.scheduler import get_scheduler
                get_scheduler().run_now()
            except Exception:
                pass
            return gr.update(value=_scheduler_status_html(), visible=True)

        run_now_btn.click(fn=_run_now, outputs=[schedule_status])

        # View run date filter
        def _on_date_change(run_date: str):
            date_label = f"Data as of {run_date}" if run_date != "Latest" else "Latest data"
            return (
                build_full_dashboard(run_date=run_date),
                _build_dash_header_html(date_label),
            )

        run_date_dd.change(
            fn=_on_date_change,
            inputs=[run_date_dd],
            outputs=[dashboard_html, dash_header],
        )

        # Timer — poll every 10 s for progress/status updates
        def _poll_scheduler():
            try:
                from workflow.scheduler import get_scheduler
                status = get_scheduler().get_status()
            except Exception:
                status = {"status": "unavailable", "config": {}, "last_result": None,
                          "next_run": "", "progress": {}}

            st = status.get("status", "idle")

            # Only show the status card when something is happening or has happened
            has_activity = st in ("running", "success", "partial", "failed")
            status_html_update = gr.update(
                value=_scheduler_status_html(status),
                visible=has_activity,
            )

            # Rebuild dashboard + refresh date choices when run completes
            if st in ("success", "partial"):
                new_dates  = _get_available_run_dates()
                latest_date = new_dates[1] if len(new_dates) > 1 else "Latest"
                date_label  = f"Data as of {latest_date}"
                new_dash    = build_full_dashboard()
                new_header  = _build_dash_header_html(date_label)
                return (
                    status_html_update,
                    new_dash,
                    gr.update(choices=new_dates),
                    new_header,
                )
            else:
                return status_html_update, gr.update(), gr.update(), gr.update()

        sched_timer.tick(
            fn=_poll_scheduler,
            outputs=[schedule_status, dashboard_html, run_date_dd, dash_header],
        )

        # (JavaScript is injected via gr.Blocks(js=_INIT_JS) above)

        def _on_load(request: gr.Request) -> str:
            return _render_user_card(_get_session_username(request))

        demo.load(
            fn=_on_load,
            inputs=None,
            outputs=[sidebar_user_html],
        )

    return demo
