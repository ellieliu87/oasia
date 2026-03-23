"""
Portfolio Analytics — Usage-driven workflow.

Modes
-----
  CCAR     : 27-month portfolio interest income under BHCB / BHCS / FedB / FedSA
  Daily IP : 30-year portfolio interest income + OAS / OAD / Convexity (Monte Carlo)

UX flow
-------
  1. User picks Usage, Scenarios, Start Date
  2. Click "Run Portfolio Analytics"  ->  confirmation card appears in-place
  3. User confirms  ->  card hides, animated progress bar streams
  4. Computation finishes  ->  results section appears
"""
from __future__ import annotations

import time
from datetime import date, datetime

import gradio as gr
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ═══════════════════════════════════════════════════════════════════════════════
# Demo portfolio
# ═══════════════════════════════════════════════════════════════════════════════

_DEMO_POSITIONS = [
    {
        "pool_id":      "TEST-POOL-30YR",
        "product_type": "CC30",
        "face_amount":  5_000_000,
        "book_price":   101.5,
        "market_price": 102.1,
        "coupon":       0.060,
        "wac":          0.065,
        "wala":         12,
        "wam":          348,
        "oas_bps":      54.2,
        "oad_years":    4.52,
        "convexity":    -0.74,
        "book_yield":   0.0608,
        "purchase_date":"2024-06-01",
    },
    {
        "pool_id":      "TEST-POOL-15YR",
        "product_type": "CC15",
        "face_amount":  3_000_000,
        "book_price":   99.5,
        "market_price": 100.2,
        "coupon":       0.055,
        "wac":          0.059,
        "wala":         6,
        "wam":          174,
        "oas_bps":      36.8,
        "oad_years":    3.21,
        "convexity":    -0.22,
        "book_yield":   0.0562,
        "purchase_date":"2024-09-15",
    },
    {
        "pool_id":      "TEST-POOL-GN30",
        "product_type": "GN30",
        "face_amount":  4_000_000,
        "book_price":   103.0,
        "market_price": 103.8,
        "coupon":       0.065,
        "wac":          0.070,
        "wala":         24,
        "wam":          336,
        "oas_bps":      58.1,
        "oad_years":    4.18,
        "convexity":    -1.12,
        "book_yield":   0.0631,
        "purchase_date":"2023-12-01",
    },
]

# ═══════════════════════════════════════════════════════════════════════════════
# Scenario configuration
# ═══════════════════════════════════════════════════════════════════════════════

_CCAR_SCENARIOS = ["BHCB", "BHCS", "FedB", "FedSA"]
_DIP_SCENARIOS  = ["Outlook", "Parallel Shocks"]

# Approximate rate shocks (bps) representing each CCAR scenario
_CCAR_SHOCK = {"BHCB": 100, "BHCS": 200, "FedB": 0, "FedSA": -300}

# Parallel shocks run for "Parallel Shocks" scenario in Daily IP
_PARALLEL_SHOCKS = [-300, -200, -100, 0, 100, 200, 300]


# ═══════════════════════════════════════════════════════════════════════════════
# HTML helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _progress_html(pct: float, eta_sec: float, task: str) -> str:
    fill = max(0, min(100, int(pct * 100)))
    if pct >= 1.0:
        eta_str = "Complete"
    elif eta_sec > 60:
        eta_str = f"{int(eta_sec/60)}m {int(eta_sec % 60)}s remaining"
    elif eta_sec > 1:
        eta_str = f"{int(eta_sec)}s remaining"
    else:
        eta_str = "Finishing…"
    return (
        f"<div style='padding:18px 0 8px;'>"
        f"<div style='font-size:12.5px;color:#0F172A;font-family:DM Sans,sans-serif;"
        f"margin-bottom:10px;font-weight:500;'>{fill}%"
        + (f" &nbsp;·&nbsp; <span style='color:#64748B;font-weight:400;'>{task}</span>" if task else "")
        + f"</div>"
        f"<div style='background:#E2E8F0;border-radius:6px;height:10px;overflow:hidden;margin-bottom:8px;'>"
        f"<div style='background:linear-gradient(90deg,#3B6FD4 0%,#6366F1 100%);"
        f"width:{fill}%;height:100%;transition:width 0.35s ease;border-radius:6px;'></div>"
        f"</div>"
        f"<div style='font-size:11px;color:#94A3B8;font-family:DM Sans,sans-serif;'>{eta_str}</div>"
        f"</div>"
    )


def _confirm_html(usage: str, scenarios: list, start_dt, n_pools: int) -> str:
    if usage == "CCAR":
        scope  = "27-month interest income projection"
        method = "Deterministic scenario rate paths (per CCAR specification)"
    else:
        scope  = "30-year interest income + OAS / OAD / Convexity"
        method = "Monte Carlo simulation (64 rate paths)"

    start_str = (
        start_dt.strftime("%Y-%m-%d") if hasattr(start_dt, "strftime")
        else str(start_dt or date.today())[:10]
    )
    scen_str = ", ".join(scenarios) if scenarios else "(none selected)"
    n_scen   = len(scenarios) if scenarios else 0
    if usage == "CCAR":
        tasks = n_pools * n_scen
    else:
        tasks = sum(
            n_pools * len(_PARALLEL_SHOCKS) if s == "Parallel Shocks" else n_pools
            for s in (scenarios or [])
        )

    rows = [
        ("Usage",       usage),
        ("Scenarios",   scen_str),
        ("Start Date",  start_str),
        ("Portfolio",   f"{n_pools} pools"),
        ("Scope",       scope),
        ("Method",      method),
        ("Total tasks", f"{tasks} pool×scenario combinations"),
    ]
    trs = "".join(
        f"<tr>"
        f"<td style='color:#64748B;font-size:12px;padding:5px 18px 5px 0;"
        f"font-family:DM Sans,sans-serif;white-space:nowrap;vertical-align:top;'>{k}</td>"
        f"<td style='font-size:12px;font-weight:500;color:#0F172A;"
        f"font-family:DM Sans,sans-serif;'>{v}</td>"
        f"</tr>"
        for k, v in rows
    )
    return (
        f"<div style='background:#F0F6FF;border:1.5px solid #3B6FD4;border-radius:10px;"
        f"padding:20px 24px;'>"
        f"<div style='font-size:13px;font-weight:700;color:#1E3A8A;margin-bottom:14px;"
        f"font-family:DM Sans,sans-serif;'>Review &amp; Confirm Run</div>"
        f"<table style='width:100%;border-collapse:collapse;'><tbody>{trs}</tbody></table>"
        f"</div>"
    )


def _kpi_html(items: list[tuple]) -> str:
    """Render a flex row of KPI cards. items = [(label, value, color_class)]."""
    def _color(cl):
        return "#059669" if cl == "pos" else ("#E5484D" if cl == "neg" else
               "#3B6FD4" if cl == "accent" else "#0F172A")
    cards = "".join(
        f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-radius:8px;"
        f"padding:12px 18px;min-width:130px;flex:1;'>"
        f"<div style='font-size:10px;color:#64748B;text-transform:uppercase;"
        f"letter-spacing:.06em;margin-bottom:5px;font-family:DM Sans,sans-serif;'>{lb}</div>"
        f"<div style='font-family:JetBrains Mono,monospace;font-size:15px;font-weight:600;"
        f"color:{_color(cl)};'>{val}</div>"
        f"</div>"
        for lb, val, cl in items
    )
    return f"<div style='display:flex;gap:10px;flex-wrap:wrap;padding:4px 0 14px;'>{cards}</div>"


def _section_hdr(title: str) -> str:
    return (
        f"<div style='font-size:10.5px;font-weight:700;color:#94A3B8;"
        f"text-transform:uppercase;letter-spacing:.08em;margin:16px 0 10px;"
        f"font-family:DM Sans,sans-serif;'>{title}</div>"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Computation helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _get_as_of(start_dt) -> date:
    if start_dt is None:
        return date.today()
    if isinstance(start_dt, datetime):
        return start_dt.date()
    if isinstance(start_dt, date):
        return start_dt
    try:
        return datetime.strptime(str(start_dt)[:10], "%Y-%m-%d").date()
    except Exception:
        return date.today()


def _make_pool_chars(p: dict):
    from analytics.prepay import PoolCharacteristics
    c = float(p["coupon"])
    c = c / 100.0 if c > 2 else c
    w = float(p["wac"])
    w = w / 100.0 if w > 2 else w
    return PoolCharacteristics(
        coupon          = c,
        wac             = w,
        wala            = int(p.get("wala", 12)),
        wam             = int(p.get("wam", 336)),
        loan_size       = 400_000.0,
        ltv             = 0.75,
        fico            = 750,
        pct_ca          = 0.15,
        pct_purchase    = 0.65,
        product_type    = p["product_type"],
        pool_id         = p["pool_id"],
        current_balance = float(p["face_amount"]),
    )


def _get_prepay_model(model_name: str = "Model PI V2"):
    """Return the prepayment model instance for the given name."""
    if model_name == "Model PI TFT":
        from analytics.model_tft import TFTPrepayModel
        return TFTPrepayModel()
    from analytics.prepay import PrepayModel
    return PrepayModel()


def _income_for_pool(pool: dict, shock_bps: int, n_periods: int, as_of: date,
                     model_name: str = "Model PI V2") -> dict:
    """Project interest income for one pool over n_periods months at given rate shock."""
    from analytics.rate_paths import generate_rate_paths, TermStructure
    from analytics.prepay import project_prepay_speeds
    from analytics.cashflows import get_cash_flows
    from data.market_data import load_market_data
    from data.intex_client import MockIntexClient

    mkt   = load_market_data(as_of)
    curve = mkt.sofr_curve
    if shock_bps:
        curve = TermStructure(tenors=curve.tenors, rates=curve.rates + shock_bps / 10_000.0)

    rp    = generate_rate_paths(curve=curve, n_paths=64, n_periods=n_periods, seed=42)
    chars = _make_pool_chars(pool)
    cpr   = project_prepay_speeds(pool=chars, rate_paths=rp, model=_get_prepay_model(model_name))
    cfs   = get_cash_flows(
        pool_id=chars.pool_id, cpr_vectors=cpr, settlement_date=as_of,
        face_amount=chars.current_balance, intex_client=MockIntexClient(),
    )
    n        = min(n_periods, cfs.interest.shape[1])
    mean_int = np.mean(cfs.interest, axis=0)[:n]
    mean_bal = np.mean(cfs.balance,  axis=0)[:n]
    fwd_r    = np.mean(rp.short_rates, axis=0)[:n]
    fin_cost = float(np.sum(mean_bal * fwd_r * rp.dt))
    gross    = float(np.sum(mean_int))
    return {"gross": gross, "fin": fin_cost, "net": gross - fin_cost}


def _risk_for_pool(pool: dict, shock_bps: int, as_of: date,
                   model_name: str = "Model PI V2") -> dict:
    """OAS, OAD, Convexity via Monte Carlo for one pool."""
    from analytics.rate_paths import generate_rate_paths, TermStructure
    from analytics.oas_solver import compute_analytics
    from data.market_data import load_market_data
    from data.intex_client import MockIntexClient

    mkt   = load_market_data(as_of)
    curve = mkt.sofr_curve
    if shock_bps:
        curve = TermStructure(tenors=curve.tenors, rates=curve.rates + shock_bps / 10_000.0)

    rp    = generate_rate_paths(curve=curve, n_paths=64, n_periods=360, seed=42)
    chars = _make_pool_chars(pool)
    price = float(pool.get("market_price", 100.0))
    a     = compute_analytics(
        pool_id=chars.pool_id, pool_chars=chars, market_price=price,
        settlement_date=as_of, rate_paths=rp,
        intex_client=MockIntexClient(), prepay_model=_get_prepay_model(model_name),
    )
    return {
        "oas":          round(a.oas,         1),
        "oad":          round(a.oad,         3),
        "convexity":    round(a.convexity,   4),
        "mod_duration": round(a.mod_duration,3),
        "yield_pct":    round(a.yield_,      3),
        "model_cpr":    round(a.model_cpr,   1),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Results builders
# ═══════════════════════════════════════════════════════════════════════════════

def _build_ccar_results(records: list[dict], positions: list[dict]):
    """Build KPI HTML + results DataFrame for CCAR run."""
    if not records:
        return "", pd.DataFrame()

    df = pd.DataFrame(records)

    # Portfolio-level totals per scenario
    scen_totals = (
        df.groupby("scenario")[["gross", "fin", "net"]]
        .sum()
        .reset_index()
    )

    kpi_items = [
        ("Portfolio", f"{len(positions)} pools", "accent"),
        ("Horizon",   "27 months", ""),
    ]
    for _, row in scen_totals.iterrows():
        kpi_items.append((row["scenario"] + " Net Inc", f"${row['net']/1e3:,.0f}K", "pos"))

    # Per-pool per-scenario display table
    display_rows = []
    for rec in records:
        if "error" in rec:
            display_rows.append({
                "Pool ID": rec["pool"], "Scenario": rec["scenario"],
                "Gross ($K)": "Error", "Financing ($K)": "Error", "Net Income ($K)": rec["error"],
            })
        else:
            display_rows.append({
                "Pool ID":        rec["pool"],
                "Scenario":       rec["scenario"],
                "Gross ($K)":     round(rec["gross"] / 1e3, 1),
                "Financing ($K)": round(rec["fin"]   / 1e3, 1),
                "Net Income ($K)":round(rec["net"]   / 1e3, 1),
            })

    return _kpi_html(kpi_items), pd.DataFrame(display_rows)


def _build_dip_results(records: list[dict], positions: list[dict]):
    """Build KPI HTML + results DataFrame for Daily IP run."""
    if not records:
        return "", pd.DataFrame()

    df = pd.DataFrame([r for r in records if "error" not in r])
    if df.empty:
        return _kpi_html([("Status", "All errors", "neg")]), pd.DataFrame(records)

    # Base (shock=0) KPIs
    base = df[df["shock"] == 0] if "shock" in df.columns else df

    total_mv = sum(p["face_amount"] * p["market_price"] / 100 for p in positions)
    mv_w     = {p["pool_id"]: p["face_amount"] * p["market_price"] / 100 / total_mv for p in positions}

    w_oas = sum(mv_w.get(r["pool"], 0) * r["oas"] for _, r in base.iterrows())
    w_oad = sum(mv_w.get(r["pool"], 0) * r["oad"] for _, r in base.iterrows())
    w_cnv = sum(mv_w.get(r["pool"], 0) * r["convexity"] for _, r in base.iterrows())
    tot_net = base["net"].sum() if "net" in base.columns else 0

    kpi_items = [
        ("Portfolio",    f"{len(positions)} pools",     "accent"),
        ("Horizon",      "30 years",                    ""),
        ("Wtd OAS",      f"{w_oas:.1f} bps",            ""),
        ("Wtd OAD",      f"{w_oad:.3f} yrs",            ""),
        ("Wtd Convexity",f"{w_cnv:.4f}",                "neg" if w_cnv < 0 else ""),
        ("30yr Net Inc", f"${tot_net/1e6:.2f}M",        "pos"),
    ]

    display_rows = []
    for rec in records:
        if "error" in rec:
            display_rows.append({"Pool ID": rec["pool"], "Scenario": rec["scenario"],
                                  "Shock": "—", "Error": rec["error"]})
        else:
            display_rows.append({
                "Pool ID":        rec["pool"],
                "Scenario":       rec["scenario"],
                "Shock (bps)":    rec.get("shock", 0),
                "OAS (bps)":      rec.get("oas",   "—"),
                "OAD (yrs)":      rec.get("oad",   "—"),
                "Convexity":      rec.get("convexity", "—"),
                "Mod Duration":   rec.get("mod_duration", "—"),
                "Yield %":        rec.get("yield_pct", "—"),
                "Model CPR %":    rec.get("model_cpr",  "—"),
                "30yr Net ($M)":  round(rec["net"] / 1e6, 3) if "net" in rec else "—",
            })

    return _kpi_html(kpi_items), pd.DataFrame(display_rows)


# ═══════════════════════════════════════════════════════════════════════════════
# 3-Year portfolio projection (fast deterministic)
# ═══════════════════════════════════════════════════════════════════════════════

def _project_portfolio_3yr(
    scenarios_with_shocks: list[tuple[str, int]],
    n_quarters: int = 12,
) -> pd.DataFrame:
    """
    Fast deterministic 3-year portfolio projection.

    Uses latest position_data snapshot for starting values, then applies:
      - Monthly balance rundown via CPR
      - Duration-adjusted one-time price change from rate shock
      - Quarterly interest income = balance × book_yield / 4

    Parameters
    ----------
    scenarios_with_shocks : list of (label, shock_bps)
    n_quarters            : number of quarters to project (default 12 = 3 years)

    Returns
    -------
    DataFrame with one row per (scenario, quarter).
    """
    try:
        from data.position_data import get_position_data
        df = get_position_data()
        latest = df["snapshot_date"].max()
        pos = df[df["snapshot_date"] == latest]
    except Exception:
        pos = pd.DataFrame()

    # Portfolio-level starting values
    if pos.empty:
        total_mv    = sum(p["face_amount"] * p["market_price"] / 100 for p in _DEMO_POSITIONS)
        w_by        = sum(p["face_amount"] * p["market_price"] / 100 * p["book_yield"] for p in _DEMO_POSITIONS) / total_mv
        w_oas       = sum(p["face_amount"] * p["market_price"] / 100 * p["oas_bps"]    for p in _DEMO_POSITIONS) / total_mv
        w_oad       = sum(p["face_amount"] * p["market_price"] / 100 * p["oad_years"]  for p in _DEMO_POSITIONS) / total_mv
        monthly_cpr = 0.06 / 12
    else:
        total_mv    = float(pos["market_value"].sum())
        w_by        = float((pos["market_value"] * pos["book_yield"]).sum()  / total_mv)
        w_oas       = float((pos["market_value"] * pos["oas_bps"]).sum()     / total_mv)
        w_oad       = float((pos["market_value"] * pos["oad_years"]).sum()   / total_mv)
        monthly_cpr = float(pos["cpr"].mean() / 100 / 12) if "cpr" in pos.columns else 0.005

    rows = []
    for scen_name, shock_bps in scenarios_with_shocks:
        # One-time duration-adjusted mark-to-market from rate shock
        price_adj_pct = -w_oad * shock_bps / 100   # % Δ MV

        balance    = total_mv * (1 + price_adj_pct / 100)
        cum_income = 0.0

        for q in range(1, n_quarters + 1):
            # Amortise balance monthly for 3 months
            for _ in range(3):
                balance *= (1 - monthly_cpr)

            qtr_income = balance * w_by / 4
            cum_income += qtr_income

            yr  = (q - 1) // 4 + 1
            qtr = (q - 1) % 4 + 1
            rows.append({
                "Scenario":              scen_name,
                "Period":                f"Y{yr}Q{qtr}",
                "Market Value ($M)":     round(balance / 1e6, 2),
                "Interest Income ($K)":  round(qtr_income / 1e3, 1),
                "Cumul. Income ($M)":    round(cum_income / 1e6, 3),
                "Book Yield (%)":        round(w_by * 100, 3),
            })

    # OAS and OAD are t=0 solved values — constant for the projection horizon.
    # Return them separately so the caller can display them as KPI cards.
    return pd.DataFrame(rows), round(w_oas, 1), round(w_oad, 3)


# ═══════════════════════════════════════════════════════════════════════════════
# Tab builder
# ═══════════════════════════════════════════════════════════════════════════════

def create_portfolio_analytics_tab(shared_state: gr.State):
    """Build the Portfolio Analytics tab."""

    gr.HTML(
        '<div class="dash-header-left" style="padding-bottom:16px;border-bottom:1px solid var(--border);margin-bottom:20px;">'
        '<div class="dash-header-title">Portfolio Analytics</div>'
        '<div class="dash-header-sub">Stress-test the portfolio under CCAR and daily IP scenarios across multiple rate paths to assess duration, spread, EVE, and book yield sensitivity.</div>'
        "</div>",
        elem_classes=["nexus-tab-hdr"],
    )

    # ─── Configuration panel ──────────────────────────────────────────────────
    gr.HTML(
        "<div style='font-size:10.5px;font-weight:700;color:#94A3B8;"
        "text-transform:uppercase;letter-spacing:.08em;margin-bottom:12px;"
        "font-family:DM Sans,sans-serif;'>Run Configuration</div>"
    )
    with gr.Row(equal_height=True):
        usage_dd = gr.Dropdown(
            choices=["CCAR", "Daily IP"],
            value="CCAR",
            label="Usage",
            scale=1,
            min_width=140,
        )
        scenario_dd = gr.Dropdown(
            choices=_CCAR_SCENARIOS,
            value=["BHCB"],
            label="Scenario (multi-select)",
            multiselect=True,
            scale=3,
        )
        start_date = gr.DateTime(
            label="Start Date",
            include_time=False,
            type="datetime",
            scale=1,
            min_width=160,
        )
        prepay_model_dd = gr.Dropdown(
            choices=["Model PI V2", "Model PI TFT"],
            value="Model PI V2",
            label="Prepayment Model",
            scale=1,
            min_width=160,
        )

    run_btn = gr.Button(
        "Run Portfolio Analytics",
        variant="primary",
        size="sm",
    )

    # ─── Confirmation card (hidden until Run clicked) ─────────────────────────
    with gr.Column(visible=False) as confirm_col:
        gr.HTML("<div style='height:6px'></div>")
        confirm_html = gr.HTML()
        gr.HTML("<div style='height:8px'></div>")
        with gr.Row():
            confirm_btn = gr.Button(
                "Confirm & Run", variant="primary", scale=2, min_width=140,
            )
            cancel_btn = gr.Button(
                "Go Back & Edit", variant="secondary", scale=1, min_width=120,
            )

    # ─── Progress bar (hidden until confirmed) ────────────────────────────────
    with gr.Column(visible=False) as progress_col:
        gr.HTML("<div style='height:4px'></div>")
        progress_bar = gr.HTML()

    # ─── Results (hidden until run complete) ──────────────────────────────────
    with gr.Column(visible=False) as results_col:
        gr.HTML("<div style='height:4px'></div>")
        kpi_bar      = gr.HTML()
        results_table = gr.DataFrame(
            value=None, interactive=False, wrap=False,
            label="3-Year Portfolio Projection — total portfolio by scenario & quarter",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Cached run config state (usage, scenarios, start_dt)
    run_config_state = gr.State(None)

    # ═════════════════════════════════════════════════════════════════════════
    # Event handlers
    # ═════════════════════════════════════════════════════════════════════════

    # ── Update scenario choices when usage changes ────────────────────────────
    def _on_usage_change(usage):
        if usage == "CCAR":
            return gr.update(choices=_CCAR_SCENARIOS, value=["BHCB"])
        else:
            return gr.update(choices=_DIP_SCENARIOS, value=["Outlook"])

    usage_dd.change(
        fn=_on_usage_change,
        inputs=[usage_dd],
        outputs=[scenario_dd],
    )

    # ── Show confirmation card when Run clicked ───────────────────────────────
    def _on_run_click(usage, scenarios, start_dt, prepay_model):
        n_pools = len(_DEMO_POSITIONS)
        html    = _confirm_html(usage, scenarios, start_dt, n_pools)
        config  = {"usage": usage, "scenarios": scenarios, "start_dt": start_dt,
                   "prepay_model": prepay_model or "Model PI V2"}
        return (
            gr.update(visible=True),   # confirm_col
            html,                      # confirm_html
            gr.update(visible=False),  # progress_col
            gr.update(visible=False),  # results_col
            config,                    # run_config_state
        )

    run_btn.click(
        fn=_on_run_click,
        inputs=[usage_dd, scenario_dd, start_date, prepay_model_dd],
        outputs=[confirm_col, confirm_html, progress_col, results_col, run_config_state],
    )

    # ── Cancel → hide confirmation card ──────────────────────────────────────
    cancel_btn.click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[confirm_col],
    )

    # ── Confirm → run computation (streaming generator) ───────────────────────
    def _run(config):
        if not config:
            yield (
                gr.update(visible=False), gr.update(visible=False),
                _progress_html(0, 0, "No config — click Run first."),
                gr.update(visible=False), "", pd.DataFrame(),
                gr.update(),
            )
            return

        usage        = config["usage"]
        scenarios    = config.get("scenarios") or []
        start_dt     = config.get("start_dt")
        prepay_model = config.get("prepay_model", "Model PI V2")
        as_of        = _get_as_of(start_dt)
        positions    = _DEMO_POSITIONS

        # Build task list
        tasks: list[tuple] = []
        if usage == "CCAR":
            for scen in scenarios:
                for pool in positions:
                    tasks.append((pool, scen, _CCAR_SHOCK.get(scen, 0)))
        else:
            for scen in scenarios:
                shocks = _PARALLEL_SHOCKS if scen == "Parallel Shocks" else [0]
                for shock in shocks:
                    for pool in positions:
                        tasks.append((pool, scen, shock))

        total   = len(tasks)
        records = []
        t0      = time.time()

        # ── Initial yield: show progress, hide others ────────────────────────
        yield (
            gr.update(visible=False),  # confirm_col
            gr.update(visible=True),   # progress_col
            _progress_html(0.0, 0, "Initializing…"),
            gr.update(visible=False),  # results_col
            gr.update(),               # kpi_bar — don't touch
            gr.update(),               # results_table — don't touch
            gr.update(),               # ts_section_col — don't touch
        )

        # ── Per-task loop ────────────────────────────────────────────────────
        for i, task in enumerate(tasks):
            pool, scen, shock = task
            try:
                if usage == "CCAR":
                    inc = _income_for_pool(pool, shock, 27, as_of, prepay_model)
                    records.append({
                        "pool": pool["pool_id"], "scenario": scen,
                        **inc,
                    })
                else:  # Daily IP
                    inc  = _income_for_pool(pool, shock, 360, as_of, prepay_model)
                    risk = _risk_for_pool(pool, shock, as_of, prepay_model)
                    records.append({
                        "pool": pool["pool_id"], "scenario": scen, "shock": shock,
                        **inc, **risk,
                    })
            except Exception as exc:
                records.append({
                    "pool": pool["pool_id"], "scenario": scen,
                    "error": str(exc),
                })

            done    = i + 1
            elapsed = time.time() - t0
            eta     = elapsed / done * (total - done) if done < total else 0
            pct     = done / total
            label   = f"{pool['pool_id']} &nbsp;·&nbsp; {scen}" + (
                f" &nbsp;({shock:+d} bps)" if usage == "Daily IP" else ""
            )

            yield (
                gr.update(visible=False),
                gr.update(visible=True),
                _progress_html(pct, eta, label),
                gr.update(visible=False),
                gr.update(),  # kpi_bar — don't touch
                gr.update(),  # results_table — don't touch
                gr.update(),  # ts_section_col — don't touch
            )

        # ── Final yield: show results ─────────────────────────────────────────
        if usage == "CCAR":
            kpi, _ = _build_ccar_results(records, positions)
            scen_shocks = [(s, _CCAR_SHOCK.get(s, 0)) for s in scenarios]
        else:
            kpi, _ = _build_dip_results(records, positions)
            scen_shocks = []
            for s in scenarios:
                if s == "Parallel Shocks":
                    for sh in _PARALLEL_SHOCKS:
                        scen_shocks.append((f"Parallel {sh:+d}bps", sh))
                else:
                    scen_shocks.append((s, 0))

        proj_tbl, base_oas, base_oad = _project_portfolio_3yr(scen_shocks)

        # Append OAS / OAD as KPI cards — these are t=0 solved values,
        # constant for the projection horizon, so displayed once as cards.
        kpi += _kpi_html([
            ("OAS (t=0 solved)", f"{base_oas:.1f} bps", "accent"),
            ("OAD (t=0 solved)", f"{base_oad:.3f} yrs", "accent"),
        ])

        # Small pause so Gradio finishes applying column visibility before
        # populating the table — prevents first-click blank table issue.
        time.sleep(0.15)

        yield (
            gr.update(visible=False),
            gr.update(visible=False),
            _progress_html(1.0, 0, ""),
            gr.update(visible=True),
            kpi,
            proj_tbl,
            gr.update(visible=True),  # ts_section_col
        )

    _RUN_OUTPUTS_CORE = [
        confirm_col, progress_col, progress_bar,
        results_col, kpi_bar, results_table,
    ]
    # ts_section_col wired in after it's created below

    # ═════════════════════════════════════════════════════════════════════════
    # Position Time Series Explorer
    # Plots historical snapshots from position_data for any combination of
    # metrics and pools — independent of the analytics run above.
    # ═════════════════════════════════════════════════════════════════════════

    _METRIC_CHOICES = [
        "Market Value ($M)",
        "Par Value ($M)",
        "Market Price",
        "OAS (bps)",
        "OAD (yrs)",
        "Book Yield (%)",
        "Unrealized P&L (%)",
    ]

    # Metric-name → position_data column mapping
    _METRIC_COL = {
        "Market Value ($M)":  "market_value",
        "Par Value ($M)":     "par_value",
        "Market Price":       "market_price",
        "OAS (bps)":          "oas_bps",
        "OAD (yrs)":          "oad_years",
        "Book Yield (%)":     "book_yield",
        "Unrealized P&L (%)": "unrealized_pnl_pct",
    }

    _METRIC_SCALE = {
        "Market Value ($M)": 1e6,
        "Par Value ($M)":    1e6,
    }

    # Display label → position_data product_type value
    _PRODUCT_TYPE_MAP = {
        "CC 30Yr":      "CC30",
        "CC 15Yr":      "CC15",
        "GNMA 30Yr":    "GN30",
        "GNMA 15Yr":    "GN15",
        "ARM":          "ARM",
        "Agency Debt":  "TSY",
        "CMBS":         "CMBS",
        "CMO":          "CMO",
        "Callable Debt":"CDBT",
    }
    _PRODUCT_TYPE_CHOICES = ["All Product Types"] + list(_PRODUCT_TYPE_MAP.keys())

    with gr.Column(visible=False, elem_classes=["nexus-plain-section"]) as ts_section_col:
        gr.HTML("<hr style='border:none;border-top:1px solid #E2E8F0;margin:24px 0 0;'>")
        gr.HTML(
            "<div style='font-size:15px;font-weight:600;color:#1E293B;"
            "font-family:DM Serif Display,Georgia,serif;margin:20px 0 4px;'>"
            "Position Time Series Explorer</div>"
            "<div style='font-size:12px;color:#64748B;font-family:DM Sans,sans-serif;"
            "margin-bottom:16px;'>Select metrics and pools below, then click "
            "<strong>Plot</strong> to generate time series charts from historical "
            "position snapshots.</div>"
        )

        with gr.Row():
            ts_metrics = gr.CheckboxGroup(
                choices=_METRIC_CHOICES,
                value=["Market Value ($M)", "OAS (bps)"],
                label="Metrics to Plot",
                scale=3,
            )
            ts_product_type = gr.Dropdown(
                choices=_PRODUCT_TYPE_CHOICES,
                value=["All Product Types"],
                label="Product Type Filter",
                multiselect=True,
                scale=2,
            )

        with gr.Row():
            ts_plot_btn = gr.Button("Plot Time Series", variant="primary", size="sm", scale=0, min_width=160)

        ts_error_html = gr.HTML(value="")
        ts_plot = gr.Plot(visible=False, label="")

    def _make_ts_plot(metrics: list, product_types: list):
        _err = lambda msg: (
            f'<div style="color:#E5484D;font-family:var(--mono);font-size:12px;padding:4px 0;">'
            f'{msg}</div>'
        )
        if not metrics:
            return _err("Select at least one metric to plot."), gr.update(visible=False)
        try:
            from data.position_data import get_position_data
            df = get_position_data()
        except Exception as e:
            return _err(f"Failed to load position data: {e}"), gr.update(visible=False)

        # ── Aggregate pool-level data to product-type (or portfolio) level ──────
        # Columns that are summed; all others use market-value-weighted average.
        _SUM_COLS  = {"market_value", "par_value", "monthly_income"}
        _WAVG_COLS = {"market_price", "oas_bps", "oad_years", "book_yield",
                      "unrealized_pnl_pct", "cpr"}

        def _agg(gdf: pd.DataFrame) -> pd.Series:
            w     = gdf["market_value"]
            w_sum = w.sum()
            out   = {}
            for col in _SUM_COLS:
                if col in gdf.columns:
                    out[col] = gdf[col].sum()
            for col in _WAVG_COLS:
                if col in gdf.columns:
                    out[col] = (gdf[col] * w).sum() / w_sum if w_sum > 0 else float("nan")
            return pd.Series(out)

        use_all = (not product_types) or ("All Product Types" in product_types)
        if use_all:
            # Single "Portfolio" series — aggregate everything
            agg_df = (
                df.groupby("snapshot_date", group_keys=False)
                .apply(_agg)
                .reset_index()
            )
            agg_df["_group"] = "Portfolio"
        else:
            codes = [_PRODUCT_TYPE_MAP[pt] for pt in product_types if pt in _PRODUCT_TYPE_MAP]
            df = df[df["product_type"].isin(codes)]
            if df.empty:
                return _err("No position data matches the selected product type filter."), gr.update(visible=False)
            agg_df = (
                df.groupby(["snapshot_date", "product_type"], group_keys=False)
                .apply(_agg)
                .reset_index()
            )
            # Map internal code back to display label for the legend
            _CODE_LABEL = {v: k for k, v in _PRODUCT_TYPE_MAP.items()}
            agg_df["_group"] = agg_df["product_type"].map(_CODE_LABEL).fillna(agg_df["product_type"])

        if agg_df.empty:
            return _err("No aggregated data available."), gr.update(visible=False)

        group_names = sorted(agg_df["_group"].unique())

        # One subplot per metric (stacked vertically)
        n = len(metrics)
        try:
            fig = make_subplots(
                rows=n, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.06,
                subplot_titles=metrics,
            )
        except Exception as e:
            return _err(f"Failed to create chart: {e}"), gr.update(visible=False)

        COLORS = ["#3B6FD4", "#059669", "#D97706", "#E5484D", "#8B5CF6", "#0891B2", "#64748B", "#F59E0B"]

        for mi, metric in enumerate(metrics):
            col_name = _METRIC_COL.get(metric)
            if not col_name or col_name not in agg_df.columns:
                continue
            scale = _METRIC_SCALE.get(metric, 1)
            show_legend = (mi == 0)

            for pi, grp in enumerate(group_names):
                gdf = agg_df[agg_df["_group"] == grp].sort_values("snapshot_date")
                if gdf.empty:
                    continue
                y_vals = gdf[col_name] / scale if scale != 1 else gdf[col_name]
                fig.add_trace(
                    go.Scatter(
                        x=gdf["snapshot_date"].astype(str),
                        y=y_vals.round(4),
                        name=grp,
                        mode="lines+markers",
                        line=dict(color=COLORS[pi % len(COLORS)], width=2),
                        marker=dict(size=5),
                        showlegend=show_legend,
                        legendgroup=grp,
                    ),
                    row=mi + 1, col=1,
                )

            fig.update_yaxes(
                title_text=metric,
                title_font=dict(size=10, color="#64748B"),
                tickfont=dict(size=10, color="#94A3B8", family="JetBrains Mono"),
                gridcolor="rgba(226,232,240,0.13)",
                row=mi + 1, col=1,
            )

        fig.update_xaxes(
            tickfont=dict(size=10, color="#94A3B8", family="JetBrains Mono"),
            showgrid=False,
            row=n, col=1,
        )
        fig.update_layout(
            height=260 * n,
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(
                orientation="h",
                yanchor="bottom", y=1.02,
                xanchor="left", x=0,
                font=dict(size=11, family="DM Sans"),
            ),
            paper_bgcolor="white",
            plot_bgcolor="white",
            font=dict(family="DM Sans"),
            hovermode="x unified",
        )
        for ann in fig.layout.annotations:
            ann.font.size = 11
            ann.font.color = "#94A3B8"

        return "", gr.update(value=fig, visible=True)

    ts_plot_btn.click(
        fn=_make_ts_plot,
        inputs=[ts_metrics, ts_product_type],
        outputs=[ts_error_html, ts_plot],
    )

    # ── Wire confirm_btn.click now that ts_section_col is defined ────────────
    RUN_OUTPUTS = _RUN_OUTPUTS_CORE + [ts_section_col]
    confirm_btn.click(
        fn=_run,
        inputs=[run_config_state],
        outputs=RUN_OUTPUTS,
    )

    return results_table, kpi_bar, ts_section_col
