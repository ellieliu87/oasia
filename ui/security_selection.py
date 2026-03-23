"""
Security Analytics — combined screening + what-if tab.

UX: progressive disclosure.
  Step 1  Search or filter the universe     ->  results table appears
  Step 2  Click any row                     ->  pool detail + analytics appear
  Step 3  Edit "New Value" cells + Recalculate  ->  base vs modified comparison
  Step 4  (optional) open "Rate Shock Analysis" accordion  ->  shock table
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

import gradio as gr
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# HTML rendering helpers
# ─────────────────────────────────────────────────────────────────────────────

def _rv_pill(signal: str) -> str:
    cfg = {
        "CHEAP": ("background:#D1FAE5;color:#065F46;", "CHEAP"),
        "RICH":  ("background:#FEE2E2;color:#991B1B;", "RICH"),
        "FAIR":  ("background:#F1F5F9;color:#475569;", "FAIR"),
    }
    style, label = cfg.get(signal, ("background:#F1F5F9;color:#475569;", signal))
    return (
        f"<span style='{style}padding:3px 10px;border-radius:20px;"
        f"font-size:11px;font-weight:700;letter-spacing:.04em;"
        f"font-family:DM Sans,sans-serif;'>{label}</span>"
    )


def _pool_header_html(r: dict) -> str:
    bal = r.get("current_balance", r.get("original_balance", 0)) / 1e6
    snap = str(r.get("snapshot_date", ""))[:7]
    coupon = r.get("coupon", 0)
    coupon_str = f"{coupon:.2f}%" if coupon < 2 else f"{coupon:.2f}%"
    rv_html = _rv_pill(r.get("rv_signal", "—"))
    items = [
        r.get("pool_id", "—"),
        r.get("product_type", "—"),
        f"Coupon {coupon_str}",
        f"${bal:,.0f}M",
        f"As of {snap}",
    ]
    pills = " &nbsp;·&nbsp; ".join(
        f"<span style='color:#334155;'>{x}</span>" for x in items
    )
    return (
        f"<div style='background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;"
        f"padding:12px 18px;display:flex;align-items:center;gap:14px;'>"
        f"<span style='font-size:15px;font-weight:700;color:#0F172A;"
        f"font-family:DM Sans,sans-serif;white-space:nowrap;'>{r.get('pool_id','—')}</span>"
        f"<span style='font-size:12px;color:#64748B;font-family:DM Sans,sans-serif;'>"
        f"{r.get('product_type','—')} &nbsp;·&nbsp; Coupon {coupon_str} "
        f"&nbsp;·&nbsp; ${bal:,.0f}M &nbsp;·&nbsp; As of {snap}</span>"
        f"&nbsp;{rv_html}"
        f"</div>"
    )


def _build_chars_table(r: dict) -> pd.DataFrame:
    """Build editable Pool Facts DataFrame: Parameter | Value (2 cols).
    User edits Value cells in-place; overrides detected by diffing against
    the original values re-derived from pool_row_state at Recalculate time.
    """
    def fmt_pct(v, d=2):
        if v is None: return "—"
        f = float(v)
        return f"{f*100:.{d}f}" if f < 2 else f"{f:.{d}f}"

    rows = [
        ("CUSIP",          r.get("cusip", "—")),
        ("Issuer",         r.get("issuer", "—")),
        ("Servicer",       r.get("servicer", "—")),
        ("Product Type",   str(r.get("product_type", "—"))),
        ("Coupon %",       f"{float(r.get('coupon', 0)):.3f}"),
        ("WAC %",          f"{float(r.get('wac', 0)):.3f}"),
        ("WALA (mo)",      str(int(r.get("wala", r.get("wala_at_issue", 0))))),
        ("WAM (mo)",       str(int(r.get("wam", 0)))),
        ("LTV",            fmt_pct(r.get("ltv"), 3)),
        ("FICO",           str(int(r.get("fico", 0)))),
        ("% California",   fmt_pct(r.get("pct_ca"), 1)),
        ("% Purchase",     fmt_pct(r.get("pct_purchase"), 1)),
        ("Loan Size",      f"${float(r.get('loan_size', 0)):,.0f}"),
        ("CPR (latest)",   f"{float(r.get('cpr', 0))*100:.1f}%"),
        ("Refi Incentive", f"{float(r.get('refi_incentive', 0))*100:+.2f}%"),
    ]
    return pd.DataFrame(rows, columns=["Parameter", "Value"])


_OVERRIDE_KEY_MAP = {
    "Coupon %":     "coupon",
    "WAC %":        "wac",
    "WALA (mo)":    "wala",
    "WAM (mo)":     "wam",
    "LTV":          "ltv",
    "FICO":         "fico",
    "% California": "pct_ca",
    "% Purchase":   "pct_pur",
    "Product Type": "product",
}


def _parse_overrides(tbl_df, pool_row: dict) -> dict:
    """Detect which Value cells the user changed vs the pool's original values."""
    if tbl_df is None or not pool_row:
        return {}
    curr = pd.DataFrame(tbl_df) if not isinstance(tbl_df, pd.DataFrame) else tbl_df
    if curr.empty or "Value" not in curr.columns:
        return {}
    # Derive original values fresh from the unchanged pool_row
    orig_df   = _build_chars_table(pool_row)
    orig_vals = dict(zip(orig_df["Parameter"], orig_df["Value"]))

    ov = {}
    for _, row in curr.iterrows():
        param    = str(row.get("Parameter", "")).strip()
        curr_val = str(row.get("Value",     "")).strip()
        orig_val = str(orig_vals.get(param, "")).strip()
        if param not in _OVERRIDE_KEY_MAP or curr_val == orig_val:
            continue
        try:
            k = _OVERRIDE_KEY_MAP[param]
            if k in ("wala", "wam", "fico"):
                ov[k] = int(float(curr_val))
            elif k == "product":
                ov[k] = curr_val
            else:
                ov[k] = float(curr_val)
        except (ValueError, TypeError):
            pass
    return ov


def _analytics_html(a: dict) -> str:
    """Render computed analytics as a clean grouped card."""
    if not a:
        return ""
    if "error" in a:
        return (
            f"<div style='color:#DC2626;font-size:12px;padding:12px;background:#FEF2F2;"
            f"border-radius:8px;border:1px solid #FECACA;'>"
            f"<b>Error:</b> {a['error']}</div>"
        )

    def _row(k, v, divider=False):
        sep = "<tr><td colspan='2' style='padding:0;border-bottom:1px solid #F1F5F9;'></td></tr>" if divider else ""
        return (
            f"{sep}<tr>"
            f"<td style='color:#64748B;font-size:12px;padding:6px 14px 6px 0;"
            f"font-family:DM Sans,sans-serif;white-space:nowrap;'>{k}</td>"
            f"<td style='font-family:JetBrains Mono,monospace;color:#0F172A;font-size:12px;"
            f"font-weight:500;text-align:right;padding:6px 0;'>{v}</td>"
            f"</tr>"
        )

    def _fmt(v, fmt=".2f"):
        try: return f"{float(v):{fmt}}"
        except: return str(v)

    rows = (
        _row("OAS",            f"{_fmt(a.get('OAS (bps)', '—'))} bps")
        + _row("Z-Spread",     f"{_fmt(a.get('Z-Spread (bps)', '—'))} bps")
        + _row("Yield",        f"{_fmt(a.get('Yield (%)', '—'), '.3f')} %")
        + _row("Model CPR",    f"{_fmt(a.get('Model CPR (%)', '—'), '.1f')} %", divider=True)
        + _row("OAD",          f"{_fmt(a.get('OAD (yrs)', '—'), '.3f')} yrs")
        + _row("Mod Duration", f"{_fmt(a.get('Mod Duration', '—'), '.3f')} yrs")
        + _row("Convexity",    f"{_fmt(a.get('Convexity', '—'), '.4f')}")
        + _row("Model Price",  f"{_fmt(a.get('Model Price', '—'), '.4f')}", divider=True)
        + _row("10yr Net Inc", a.get("10yr Net Inc", "—"))
        + _row("Gross Interest", a.get("Gross Interest", "—"))
        + _row("Financing Cost", a.get("Financing Cost", "—"))
    )
    src = " &nbsp;<span style='color:#94A3B8;font-size:10px;'>(cached)</span>" if a.get("_from_cache") else ""
    return (
        f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-radius:8px;padding:14px 18px;'>"
        f"<div style='font-size:10.5px;font-weight:700;color:#94A3B8;text-transform:uppercase;"
        f"letter-spacing:.08em;margin-bottom:10px;'>Analytics{src}</div>"
        f"<table style='width:100%;border-collapse:collapse;'><tbody>{rows}</tbody></table>"
        f"</div>"
    )


def _comparison_html(base: dict, modified: dict) -> str:
    """Render base vs modified as a 3-col comparison table."""
    if not base or not modified:
        return ""
    keys = [
        ("OAS (bps)",       "OAS",          ".1f"),
        ("Z-Spread (bps)",  "Z-Spread",     ".1f"),
        ("Yield (%)",       "Yield %",      ".3f"),
        ("Model CPR (%)",   "Model CPR %",  ".1f"),
        ("OAD (yrs)",       "OAD (yrs)",    ".3f"),
        ("Mod Duration",    "Mod Duration", ".3f"),
        ("Convexity",       "Convexity",    ".4f"),
        ("Model Price",     "Model Price",  ".4f"),
    ]
    dividers_after = {3, 7}  # after Yield, after Model Price

    def _cell(v, fmt):
        try: return f"{float(v):{fmt}}"
        except: return str(v) if v is not None else "—"

    hdr = (
        f"<tr style='background:#F8FAFC;'>"
        f"<th style='font-size:10.5px;font-weight:600;color:#64748B;text-align:left;"
        f"padding:7px 12px 7px 0;border-bottom:1px solid #E2E8F0;'>Metric</th>"
        f"<th style='font-size:10.5px;font-weight:600;color:#64748B;text-align:right;"
        f"padding:7px 0 7px 12px;border-bottom:1px solid #E2E8F0;'>Base</th>"
        f"<th style='font-size:10.5px;font-weight:600;color:#3B6FD4;text-align:right;"
        f"padding:7px 0 7px 12px;border-bottom:1px solid #E2E8F0;'>Modified</th>"
        f"<th style='font-size:10.5px;font-weight:600;color:#64748B;text-align:right;"
        f"padding:7px 0 7px 12px;border-bottom:1px solid #E2E8F0;'>Delta</th>"
        f"</tr>"
    )
    trs = ""
    for i, (k, label, fmt) in enumerate(keys):
        bv = base.get(k)
        mv = modified.get(k)
        b_str = _cell(bv, fmt)
        m_str = _cell(mv, fmt)
        try:
            d = float(mv) - float(bv)
            sign = "+" if d > 0 else ""
            col = "#059669" if d > 0 else ("#DC2626" if d < 0 else "#64748B")
            d_str = f"<span style='color:{col};font-weight:600;'>{sign}{d:{fmt}}</span>"
        except Exception:
            d_str = "—"
        sep = "border-top:2px solid #F1F5F9;" if i in dividers_after else ""
        trs += (
            f"<tr style='{sep}'>"
            f"<td style='color:#475569;font-size:12px;padding:6px 12px 6px 0;"
            f"font-family:DM Sans,sans-serif;'>{label}</td>"
            f"<td style='font-family:JetBrains Mono,monospace;font-size:12px;text-align:right;"
            f"padding:6px 0 6px 12px;color:#0F172A;'>{b_str}</td>"
            f"<td style='font-family:JetBrains Mono,monospace;font-size:12px;text-align:right;"
            f"padding:6px 0 6px 12px;color:#3B6FD4;font-weight:500;'>{m_str}</td>"
            f"<td style='font-family:JetBrains Mono,monospace;font-size:12px;text-align:right;"
            f"padding:6px 0 6px 12px;'>{d_str}</td>"
            f"</tr>"
        )
    return (
        f"<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-radius:8px;padding:14px 18px;'>"
        f"<div style='font-size:10.5px;font-weight:700;color:#94A3B8;text-transform:uppercase;"
        f"letter-spacing:.08em;margin-bottom:10px;'>Base vs Modified</div>"
        f"<table style='width:100%;border-collapse:collapse;'><tbody>{hdr}{trs}</tbody></table>"
        f"</div>"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

# Module-level cache: built once, filtered on every user action (<5ms)
_BASE_DF: pd.DataFrame | None = None


def _get_base_df() -> pd.DataFrame:
    """Build (or return cached) merged universe + latest snapshot DataFrame."""
    global _BASE_DF
    if _BASE_DF is not None:
        return _BASE_DF
    from data.universe_1000 import get_universe_1000, get_universe_snapshots
    univ  = get_universe_1000()
    snaps = get_universe_snapshots()
    latest = (
        snaps.sort_values("snapshot_date")
        .groupby("pool_id").last().reset_index()
        [["pool_id", "snapshot_date", "market_price", "oas_bps", "oad_years",
          "convexity", "book_yield", "cpr", "current_balance", "wala", "wam",
          "refi_incentive", "burnout"]]
    )
    _BASE_DF = univ.merge(latest, on="pool_id", how="left")
    return _BASE_DF


def _prewarm() -> None:
    """Build the base DataFrame in a background thread so first user click is instant."""
    import threading
    threading.Thread(target=_get_base_df, daemon=True).start()


def _get_merged_df(
    products, coupon_min, coupon_max,
    oas_min, oas_max, oad_min, oad_max,
    fico_min, ltv_max, search_text,
) -> pd.DataFrame:
    df = _get_base_df()   # instant if already built

    if products:
        df = df[df["product_type"].isin(products)]
    df = df[df["coupon"].between(coupon_min, coupon_max)]
    df = df[df["oas_bps"].fillna(999).between(oas_min, oas_max)]
    df = df[df["oad_years"].fillna(99).between(oad_min, oad_max)]
    df = df[df["fico"] >= fico_min]
    df = df[df["ltv"] <= ltv_max]

    if search_text and search_text.strip():
        q = search_text.strip().upper()
        df = df[
            df["pool_id"].str.upper().str.contains(q, na=False) |
            df["cusip"].str.upper().str.contains(q, na=False)
        ]

    # Vectorized RV signal — no row-wise apply
    med = df.groupby("product_type")["oas_bps"].transform("median")
    oas  = df["oas_bps"]
    df = df.copy()
    df["rv_signal"] = "FAIR"
    df.loc[oas > med + 8, "rv_signal"] = "CHEAP"
    df.loc[oas < med - 8, "rv_signal"] = "RICH"
    df.loc[oas.isna(),    "rv_signal"] = "—"
    return df


def _format_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    out = pd.DataFrame()
    out["Pool ID"]       = df["pool_id"]
    out["Product"]       = df["product_type"]
    out["Coupon %"]      = df["coupon"].round(2)
    out["WAC %"]         = df["wac"].round(3)
    out["Balance ($M)"]  = (df.get("current_balance", df["original_balance"]) / 1e6).round(1)
    out["Price"]         = df["market_price"].round(2) if "market_price" in df else None
    out["OAS (bps)"]     = df["oas_bps"].round(1) if "oas_bps" in df else None
    out["OAD (yr)"]      = df["oad_years"].round(2) if "oad_years" in df else None
    out["Convexity"]     = df["convexity"].round(3) if "convexity" in df else None
    out["FICO"]          = df["fico"].astype(int)
    out["LTV"]           = df["ltv"].round(3)
    out["RV"]            = df["rv_signal"]
    return out


def _get_pool_row(pool_id: str) -> dict | None:
    from data.universe_1000 import get_universe_1000, get_pool_snapshot
    univ = get_universe_1000()
    row  = univ[(univ["pool_id"] == pool_id) | (univ["cusip"] == pool_id)]
    if row.empty:
        return None
    r = row.iloc[0].to_dict()
    snap = get_pool_snapshot(r["pool_id"])
    if snap:
        r.update(snap)
    if not r.get("wam"):
        r["wam"] = int(r["original_wam"]) - int(r.get("wala", r.get("wala_at_issue", 0)))
    if not r.get("wala"):
        r["wala"] = int(r.get("wala_at_issue", 0))
    return r


def _build_chars(r: dict, overrides: dict | None = None):
    from analytics.prepay import PoolCharacteristics
    ov = overrides or {}
    c = float(ov.get("coupon") or r["coupon"])
    c = c / 100.0 if c > 2 else c
    w = float(ov.get("wac") or r["wac"])
    w = w / 100.0 if w > 2 else w
    return PoolCharacteristics(
        coupon       = c,
        wac          = w,
        wala         = int(ov.get("wala") or r.get("wala", r.get("wala_at_issue", 12))),
        wam          = int(ov.get("wam")  or r.get("wam", 336)),
        loan_size    = float(r.get("loan_size", 400_000)),
        ltv          = float(ov.get("ltv")   or r.get("ltv", 0.75)),
        fico         = int(ov.get("fico")  or r.get("fico", 750)),
        pct_ca       = float(ov.get("pct_ca")  or r.get("pct_ca", 0.15)),
        pct_purchase = float(ov.get("pct_pur") or r.get("pct_purchase", 0.65)),
        product_type = str(ov.get("product")   or r.get("product_type", "CC30")),
        pool_id      = str(r.get("pool_id", "WHAT-IF")),
        current_balance = float(r.get("current_balance", r.get("original_balance", 1_000_000))),
    )


def _compute_analytics(chars, price: float, shock_bps: int = 0, use_cache: bool = True) -> dict:
    """Return analytics dict; checks DuckDB cache first (skipped when use_cache=False)."""
    from data.market_data import load_market_data
    from data.intex_client import MockIntexClient
    from analytics.rate_paths import generate_rate_paths, TermStructure
    from analytics.prepay import PrepayModel
    from analytics.oas_solver import compute_analytics
    from db.cache import read_risk_metrics, write_risk_metrics

    as_of = date.today()
    if shock_bps == 0 and use_cache:
        cached = read_risk_metrics(chars.pool_id, as_of, price, 0, 64)
        if cached:
            return {
                "OAS (bps)":      round(float(cached["oas_bps"]),      1),
                "Z-Spread (bps)": round(float(cached["z_spread_bps"]), 1),
                "Yield (%)":      round(float(cached["yield_pct"]),     3),
                "Model CPR (%)":  round(float(cached["model_cpr_pct"]),1),
                "OAD (yrs)":      round(float(cached["oad_years"]),     3),
                "Mod Duration":   round(float(cached["mod_duration"]),  3),
                "Convexity":      round(float(cached["convexity"]),     4),
                "Model Price":    round(float(cached["model_price"]),   4),
                "_from_cache":    True,
            }

    mkt = load_market_data(as_of)
    curve = mkt.sofr_curve
    if shock_bps:
        curve = TermStructure(tenors=curve.tenors, rates=curve.rates + shock_bps / 10_000.0)

    rp = generate_rate_paths(curve=curve, n_paths=64, n_periods=360, seed=42)
    a  = compute_analytics(
        pool_id=chars.pool_id, pool_chars=chars, market_price=float(price),
        settlement_date=as_of, rate_paths=rp,
        intex_client=MockIntexClient(), prepay_model=PrepayModel(),
    )
    result = {
        "OAS (bps)":      round(a.oas,         1),
        "Z-Spread (bps)": round(a.z_spread,    1),
        "Yield (%)":      round(a.yield_,       3),
        "Model CPR (%)":  round(a.model_cpr,   1),
        "OAD (yrs)":      round(a.oad,          3),
        "Mod Duration":   round(a.mod_duration, 3),
        "Convexity":      round(a.convexity,    4),
        "Model Price":    round(a.model_price,  4),
    }
    if shock_bps == 0:
        try:
            write_risk_metrics(chars.pool_id, as_of, price, 0, 64, {
                "oas_bps": a.oas, "z_spread_bps": a.z_spread, "oad_years": a.oad,
                "mod_duration": a.mod_duration, "convexity": a.convexity,
                "yield_pct": a.yield_, "model_price": a.model_price, "model_cpr_pct": a.model_cpr,
            })
        except Exception:
            pass
    return result


def _compute_income(chars) -> dict:
    from data.market_data import load_market_data
    from data.intex_client import MockIntexClient
    from analytics.rate_paths import generate_rate_paths
    from analytics.prepay import PrepayModel, project_prepay_speeds
    from analytics.cashflows import get_cash_flows
    from db.cache import read_interest_income, write_interest_income
    import numpy as np

    as_of  = date.today()
    cached = read_interest_income(chars.pool_id, as_of, 0, 10)
    if cached:
        gross = float(cached["total_gross_interest"])
        fin   = float(cached["total_financing_cost"])
        net   = float(cached["total_net_income"])
    else:
        mkt = load_market_data(as_of)
        rp  = generate_rate_paths(curve=mkt.sofr_curve, n_paths=64, n_periods=120, seed=42)
        cpr = project_prepay_speeds(pool=chars, rate_paths=rp, model=PrepayModel())
        cfs = get_cash_flows(
            pool_id=chars.pool_id, cpr_vectors=cpr, settlement_date=as_of,
            face_amount=chars.current_balance, intex_client=MockIntexClient(),
        )
        n        = min(120, cfs.interest.shape[1])
        mean_int = np.mean(cfs.interest, axis=0)[:n]
        mean_bal = np.mean(cfs.balance,  axis=0)[:n]
        fwd_r    = np.mean(rp.short_rates, axis=0)[:n]
        fin_cost = mean_bal * fwd_r * rp.dt
        gross = float(np.sum(mean_int))
        fin   = float(np.sum(fin_cost))
        net   = gross - fin
        try:
            fr = float(mkt.sofr_curve.zero_rate(0.25))
            write_interest_income(chars.pool_id, as_of, 0, 10, fr * 100,
                                  {"total_gross_interest": gross,
                                   "total_financing_cost": fin,
                                   "total_net_income": net, "annual": []})
        except Exception:
            pass

    return {
        "10yr Net Inc":    f"${net:,.0f}",
        "Gross Interest":  f"${gross:,.0f}",
        "Financing Cost":  f"${fin:,.0f}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tab builder
# ─────────────────────────────────────────────────────────────────────────────

def create_security_selection_tab(shared_state: gr.State):
    """Build Security Analytics tab with progressive disclosure."""

    # ─── Step 1: Search bar + Filter accordion ────────────────────────────────
    with gr.Row():
        search_input = gr.Textbox(
            placeholder="Search by Pool ID or CUSIP…",
            label="Search",
            scale=5,
            container=True,
        )
        search_btn = gr.Button("Search", variant="primary", scale=1, min_width=100)

    with gr.Accordion("Filter Universe", open=False):
        filter_products = gr.CheckboxGroup(
            choices=["CC30", "CC15", "GN30", "GN15"],
            value=["CC30", "CC15", "GN30", "GN15"],
            label="Product Type",
        )
        with gr.Row():
            f_c_min = gr.Slider(3.0, 9.0, value=3.0, step=0.5, label="Coupon Min %")
            f_c_max = gr.Slider(3.0, 10.0, value=9.0, step=0.5, label="Coupon Max %")
        with gr.Row():
            f_oas_min = gr.Slider(0,   600, value=0,    step=5, label="OAS Min (bps)")
            f_oas_max = gr.Slider(0,   700, value=500,  step=5, label="OAS Max (bps)")
        with gr.Row():
            f_oad_min = gr.Slider(0.0, 15.0, value=0.0,  step=0.5, label="OAD Min (yrs)")
            f_oad_max = gr.Slider(0.0, 15.0, value=12.0, step=0.5, label="OAD Max (yrs)")
        with gr.Row():
            f_fico = gr.Slider(600, 850, value=620, step=10, label="FICO Min")
            f_ltv  = gr.Slider(0.4, 1.0, value=0.99, step=0.01, label="LTV Max")
        screen_btn = gr.Button("Apply Filters", variant="secondary", size="sm")

    # ─── Step 2: Results ──────────────────────────────────────────────────────
    result_md = gr.Markdown(
        "*Apply filters or search above to screen the universe.*",
        elem_classes=["nexus-sa-count"],
    )
    with gr.Row():
        export_btn    = gr.Button("Export CSV", size="sm", scale=0, min_width=100, visible=False)
        download_file = gr.File(visible=False, scale=0)
    results_table = gr.DataFrame(value=None, interactive=False, wrap=False)
    row_hint = gr.Markdown(
        "",
        elem_classes=["nexus-sa-hint"],
    )

    # ─── Step 3: Pool detail + Analytics (hidden until row selected) ──────────
    with gr.Column(visible=False) as pool_col:
        pool_header = gr.HTML()

        gr.HTML("<div style='height:10px'></div>")

        with gr.Row(equal_height=False):
            # Left — pool facts (editable: fill New Value column to run what-if)
            with gr.Column(scale=1, min_width=260):
                pool_facts_table = gr.DataFrame(
                    value=None,
                    headers=["Parameter", "Value"],
                    datatype=["str", "str"],
                    col_count=(2, "fixed"),
                    interactive=True,
                    wrap=False,
                    label="Pool Facts  —  edit any Value cell, then click Recalculate",
                )

            # Right — analytics
            with gr.Column(scale=2, min_width=300):
                with gr.Row():
                    price_input = gr.Number(
                        label="Price (%par)", value=100.0,
                        precision=4, scale=2, minimum=50.0, maximum=130.0,
                    )
                    calc_btn = gr.Button(
                        "Recalculate", variant="secondary",
                        scale=1, min_width=120,
                    )
                analytics_html = gr.HTML()

        gr.HTML("<div style='height:8px'></div>")

        # ─── Rate Shock accordion ──────────────────────────────────────────────
        with gr.Accordion("Rate Shock Analysis", open=False):
            run_shock_btn = gr.Button("Run Shock Scenarios", variant="secondary", size="sm")
            with gr.Column(visible=False) as shock_col:
                shock_table = gr.DataFrame(interactive=False, wrap=False)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal state: pool row as JSON string
    # ─────────────────────────────────────────────────────────────────────────
    pool_row_state = gr.State(None)   # stores the pool dict
    base_analytics_state = gr.State(None)   # stores base analytics dict

    # ═══════════════════════════════════════════════════════════════════════════
    # Event handlers
    # ═══════════════════════════════════════════════════════════════════════════

    FILTER_INPUTS = [
        filter_products, f_c_min, f_c_max,
        f_oas_min, f_oas_max, f_oad_min, f_oad_max,
        f_fico, f_ltv, search_input,
    ]

    def _do_screen(products, cmin, cmax, omin, omax, oadmin, oadmax, fmin, lmax, search):
        try:
            df  = _get_merged_df(products, cmin, cmax, omin, omax, oadmin, oadmax, fmin, lmax, search)
            tbl = _format_table(df)
            cnt = f"**{len(df):,}** pools matched — click any row to analyze it."
            return tbl, cnt, gr.update(visible=True), gr.update(visible=False)
        except Exception as e:
            return pd.DataFrame(), f"*Error: {e}*", gr.update(visible=False), gr.update(visible=False)

    SCREEN_OUTPUTS = [results_table, result_md, export_btn, download_file]

    screen_btn.click(fn=_do_screen, inputs=FILTER_INPUTS, outputs=SCREEN_OUTPUTS)
    search_btn.click(fn=_do_screen, inputs=FILTER_INPUTS, outputs=SCREEN_OUTPUTS)
    search_input.submit(fn=_do_screen, inputs=FILTER_INPUTS, outputs=SCREEN_OUTPUTS)

    def export_csv(df):
        if df is None or len(df) == 0:
            return gr.update(visible=False)
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        pd.DataFrame(df).to_csv(tmp.name, index=False)
        return gr.update(visible=True, value=tmp.name)

    export_btn.click(fn=export_csv, inputs=[results_table], outputs=[download_file])

    # ── Load pool when a table row is clicked ─────────────────────────────────

    def _load_and_compute(evt: gr.SelectData, df_val, state):
        """Called when user clicks any cell in the results table."""
        try:
            row_idx = evt.index[0]
            pool_id = pd.DataFrame(df_val).iloc[row_idx]["Pool ID"]
        except Exception:
            empty_tbl = pd.DataFrame(columns=["Parameter", "Value"])
            return (
                gr.update(), gr.update(), empty_tbl, gr.update(visible=False),
                gr.update(visible=False), gr.update(), None, None, state,
            )
        return _load_pool_by_id(pool_id, None, state)

    def _load_pool_by_id(pool_id: str, price_override, state):
        """Core logic: fetch row, build chars table, auto-run analytics."""
        r = _get_pool_row(str(pool_id).strip())
        if not r:
            return (
                gr.update(visible=False),     # pool_col
                "",                           # header
                pd.DataFrame(columns=["Parameter", "Value"]),  # pool_facts_table
                "",                           # analytics
                gr.update(visible=False),     # shock_col
                100.0,                        # price_input
                None, None,                   # pool_row_state, base_analytics_state
                state,
            )

        header_html  = _pool_header_html(r)
        chars_table  = _build_chars_table(r)
        price        = float(price_override) if price_override else round(float(r.get("market_price", 100.0)), 4)

        # Auto-compute analytics
        chars = _build_chars(r)
        try:
            a   = _compute_analytics(chars, price)
            inc = _compute_income(chars)
            a.update(inc)
            a_html = _analytics_html(a)
        except Exception as e:
            a      = {}
            a_html = _analytics_html({"error": str(e)})

        if state is None:
            state = {}
        state["selected_pool_id"] = r["pool_id"]

        return (
            gr.update(visible=True),   # pool_col
            header_html,
            chars_table,               # pool_facts_table
            a_html,
            gr.update(visible=False),  # shock_col (reset)
            price,
            r,                         # pool_row_state
            a,                         # base_analytics_state
            state,
        )

    LOAD_OUTPUTS = [
        pool_col, pool_header, pool_facts_table, analytics_html,
        shock_col,
        price_input, pool_row_state, base_analytics_state, shared_state,
    ]

    results_table.select(
        fn=_load_and_compute,
        inputs=[results_table, shared_state],
        outputs=LOAD_OUTPUTS,
    )

    # Recalculate: detects edited Value cells vs original pool_row, runs what-if if any changed
    def _recalc(price, facts_tbl, pool_row, state):
        if not pool_row:
            return gr.update(), None
        # Compare current table against original to find user edits
        overrides  = _parse_overrides(facts_tbl, pool_row)
        chars_base = _build_chars(pool_row)
        try:
            a_base = _compute_analytics(chars_base, float(price))
            inc    = _compute_income(chars_base)
            a_base.update(inc)
        except Exception as e:
            return _analytics_html({"error": str(e)}), None

        if overrides:
            try:
                chars_mod = _build_chars(pool_row, overrides)
                # use_cache=False: same pool_id would otherwise return the base cached result
                a_mod     = _compute_analytics(chars_mod, float(price), use_cache=False)
                base_clean = {k: v for k, v in a_base.items()
                              if not k.startswith("_")
                              and k not in ("10yr Net Inc", "Gross Interest", "Financing Cost")}
                mod_clean  = {k: v for k, v in a_mod.items() if not k.startswith("_")}
                return _comparison_html(base_clean, mod_clean), a_base
            except Exception as e:
                return _analytics_html({"error": str(e)}), a_base

        return _analytics_html(a_base), a_base

    calc_btn.click(
        fn=_recalc,
        inputs=[price_input, pool_facts_table, pool_row_state, shared_state],
        outputs=[analytics_html, base_analytics_state],
    )

    # ── Rate Shock Analysis ───────────────────────────────────────────────────

    def _run_shocks(pool_row, base_price):
        if not pool_row:
            return gr.update(), gr.update(visible=False)
        chars  = _build_chars(pool_row)
        shocks = [-300, -200, -100, 0, 100, 200, 300]
        rows   = []
        for shock in shocks:
            try:
                a = _compute_analytics(chars, float(base_price), shock)
                rows.append({
                    "Scenario":  f"{shock:+d} bps" if shock != 0 else "BAU",
                    "OAS (bps)": a.get("OAS (bps)", "—"),
                    "OAD (yrs)": a.get("OAD (yrs)", "—"),
                    "Convexity": a.get("Convexity",  "—"),
                    "Yield (%)": a.get("Yield (%)",  "—"),
                    "CPR (%)":   a.get("Model CPR (%)", "—"),
                })
            except Exception as e:
                rows.append({"Scenario": f"{shock:+d} bps", "Error": str(e)})
        return pd.DataFrame(rows), gr.update(visible=True)

    run_shock_btn.click(
        fn=_run_shocks,
        inputs=[pool_row_state, price_input],
        outputs=[shock_table, shock_col],
    )

    # ── Sync from other tabs ──────────────────────────────────────────────────

    def _sync(state):
        pid = (state or {}).get("selected_pool_id", "")
        return pid or gr.update()

    shared_state.change(fn=_sync, inputs=[shared_state], outputs=[search_input])

    # Kick off background pre-warm so the first user click is instant
    _prewarm()

    return results_table, pool_row_state
