"""
ui/watchlist.py

Watchlist tab — search the MBS universe, add/remove CUSIPs, sync to dashboard.

Interaction model:
  • Search with filters → results table
  • Click any row      → selection bar with "★ Add to Watchlist" button
  • Add/Remove         → refreshes My Watchlist table AND dashboard card in real time
  • Manual CUSIP form  → direct entry with optional notes
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import gradio as gr

_NEXUS_ROOT = str(Path(__file__).resolve().parents[1])
if _NEXUS_ROOT not in sys.path:
    sys.path.insert(0, _NEXUS_ROOT)


# ─────────────────────────────────────────────────────────────────────────────
# Data helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_watchlist(username: str = "default") -> list[dict]:
    try:
        from data.watchlist_store import load_watchlist
        return load_watchlist(username)
    except Exception:
        return []


def _watchlist_df(username: str = "default") -> pd.DataFrame:
    items = _load_watchlist(username)
    if not items:
        return pd.DataFrame(columns=["CUSIP", "Pool ID", "Notes", "Added"])
    return pd.DataFrame([
        {
            "CUSIP":   it.get("cusip", ""),
            "Pool ID": it.get("pool_id", ""),
            "Notes":   it.get("notes", ""),
            "Added":   it.get("added_at", "")[:10] if it.get("added_at") else "",
        }
        for it in items
    ])


def _watchlist_cusip_choices(username: str = "default") -> list[str]:
    return [it.get("cusip", "") for it in _load_watchlist(username) if it.get("cusip")]


def _search_results(
    product: str = "All",
    issuer: str = "All",
    min_coupon: float = 0.0,
    max_coupon: float = 10.0,
    min_oas: float = -50.0,
    max_oas: float = 300.0,
    min_fico: int = 600,
) -> pd.DataFrame:
    """Filter universe + latest snapshot and return display DataFrame."""
    try:
        from data.universe_1000 import get_universe_1000, get_universe_snapshots
        uni = get_universe_1000()
        snaps = get_universe_snapshots()

        # Join latest snapshot (most recent date per cusip)
        latest = (
            snaps.sort_values("snapshot_date")
            .groupby("cusip", as_index=False)
            .last()[["cusip", "oas_bps", "oad_years", "market_price", "cpr"]]
        )
        df = uni.merge(latest, on="cusip", how="left")

        # Apply filters
        if product and product != "All":
            df = df[df["product_type"] == product]
        if issuer and issuer != "All":
            df = df[df["issuer"] == issuer]
        df = df[df["coupon"].between(min_coupon, max_coupon)]
        df = df[df["fico"] >= min_fico]
        if "oas_bps" in df.columns:
            df = df[df["oas_bps"].between(min_oas, max_oas)]

        df = df.head(50)
        if df.empty:
            return pd.DataFrame(columns=["CUSIP", "Pool ID", "Issuer", "Type",
                                          "Coupon %", "OAS", "OAD", "FICO", "LTV %"])

        return pd.DataFrame([
            {
                "CUSIP":    str(r.get("cusip", "")),
                "Pool ID":  str(r.get("pool_id", "")),
                "Issuer":   str(r.get("issuer", "")),
                "Type":     str(r.get("product_type", "")),
                "Coupon %": f"{float(r.get('coupon', 0)):.2f}",
                "OAS":      f"{float(r.get('oas_bps', 0)):.1f}" if pd.notna(r.get('oas_bps')) else "--",
                "OAD":      f"{float(r.get('oad_years', 0)):.2f}" if pd.notna(r.get('oad_years')) else "--",
                "FICO":     int(r.get("fico", 0)) if r.get("fico") else 0,
                "LTV %":    f"{float(r.get('ltv', 0)) * 100:.0f}",
            }
            for _, r in df.iterrows()
        ])
    except Exception:
        return pd.DataFrame(columns=["CUSIP", "Pool ID", "Issuer", "Type",
                                      "Coupon %", "OAS", "OAD", "FICO", "LTV %"])


def _fresh_dashboard_html(username: str = "default") -> str:
    """Rebuild full dashboard HTML with the correct user's watchlist."""
    try:
        from ui.layout import build_full_dashboard
        return build_full_dashboard(username=username)
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_username(request: gr.Request) -> str:
    try:
        from auth.session import get_username, COOKIE_NAME
        return get_username(request.request.cookies.get(COOKIE_NAME)) or "default"
    except Exception:
        return "default"


def _ok(msg: str) -> str:
    return (
        f'<div style="color:#059669;font-family:var(--mono);font-size:12px;'
        f'padding:6px 10px;background:#ECFDF5;border-radius:6px;'
        f'border:1px solid #A7F3D0;margin-top:4px;">{msg}</div>'
    )


def _err(msg: str) -> str:
    return (
        f'<div style="color:#E5484D;font-family:var(--mono);font-size:12px;'
        f'padding:6px 10px;background:#FFF1F2;border-radius:6px;'
        f'border:1px solid #FECDD3;margin-top:4px;">{msg}</div>'
    )


_SECTION_LABEL = (
    "font-size:11px;font-weight:700;color:#94A3B8;text-transform:uppercase;"
    "letter-spacing:.08em;margin:0 0 10px;font-family:DM Sans,sans-serif;"
)


# ─────────────────────────────────────────────────────────────────────────────
# Tab builder
# ─────────────────────────────────────────────────────────────────────────────

def create_watchlist_tab(shared_state: gr.State, dashboard_html: gr.HTML = None):
    gr.HTML(
        '<div class="dash-header-left" style="padding-bottom:16px;'
        'border-bottom:1px solid var(--border);margin-bottom:20px;">'
        '<div class="dash-header-title">Watchlist</div>'
        '<div class="dash-header-sub">Search the agency MBS universe and build a personal '
        'watchlist of CUSIPs to monitor prices, spreads, and key pool characteristics.</div>'
        "</div>",
        elem_classes=["nexus-tab-hdr"],
    )

    # ── Section 1: Universe Search ────────────────────────────────────────────
    gr.HTML(f'<div style="{_SECTION_LABEL}">Universe Search</div>')

    # Row 1: product type + issuer + search button
    with gr.Row():
        wl_filter_product = gr.Dropdown(
            choices=["All", "CC30", "CC15", "GN30", "GN15", "ARM", "TSY", "CMBS", "CMO", "CDBT"],
            value="All", label="Product Type", scale=2,
        )
        wl_filter_issuer = gr.Dropdown(
            choices=["All", "FNMA", "FHLMC", "GNMA"],
            value="All", label="Issuer", scale=2,
        )
        wl_search_btn = gr.Button("Search", variant="primary", scale=1, min_width=120)

    # Row 2: numeric filters
    with gr.Row():
        wl_filter_min_coupon = gr.Number(value=0.0,   label="Min Coupon %", scale=1, precision=2)
        wl_filter_max_coupon = gr.Number(value=10.0,  label="Max Coupon %", scale=1, precision=2)
        wl_filter_min_oas    = gr.Number(value=-50.0, label="Min OAS (bps)", scale=1, precision=0)
        wl_filter_max_oas    = gr.Number(value=300.0, label="Max OAS (bps)", scale=1, precision=0)
        wl_filter_min_fico   = gr.Number(value=600,   label="Min FICO",      scale=1, precision=0)

    wl_results_df = gr.DataFrame(
        value=pd.DataFrame(columns=["CUSIP", "Pool ID", "Issuer", "Type",
                                     "Coupon %", "OAS", "OAD", "FICO", "LTV %"]),
        label="Search Results — click a row to select",
        interactive=False,
        visible=False,
        wrap=False,
    )

    # Selection bar — revealed when a row is clicked
    with gr.Row(visible=False) as wl_selection_row:
        wl_selected_display = gr.Textbox(
            label="Selected CUSIP",
            interactive=False,
            scale=2, max_lines=1,
        )
        wl_sel_notes = gr.Textbox(
            placeholder="Notes (optional)",
            label="Notes",
            scale=2, max_lines=1,
        )
        wl_sel_add_btn = gr.Button("★  Add to Watchlist", variant="primary",
                                   scale=1, min_width=160)

    wl_search_msg = gr.HTML(value="")

    gr.HTML("<div style='height:20px'></div>")

    # ── Section 2: Add by CUSIP directly ─────────────────────────────────────
    gr.HTML(f'<div style="{_SECTION_LABEL}">Add by CUSIP</div>')

    with gr.Row():
        wl_cusip_input = gr.Textbox(
            placeholder="e.g. 3140X7GK4", label="CUSIP", scale=2, max_lines=1,
        )
        wl_notes_input = gr.Textbox(
            placeholder="Notes (optional)", label="Notes", scale=2, max_lines=1,
        )
        wl_add_btn = gr.Button("★  Add to Watchlist", variant="primary",
                               scale=1, min_width=160)

    wl_add_msg = gr.HTML(value="")

    gr.HTML("<div style='height:20px'></div>")

    # ── Section 3: My Watchlist ───────────────────────────────────────────────
    gr.HTML(f'<div style="{_SECTION_LABEL}">My Watchlist</div>')

    wl_table_df = gr.DataFrame(
        value=_watchlist_df(), label="", interactive=False, wrap=False,
    )

    with gr.Row():
        wl_remove_dd = gr.Dropdown(
            choices=_watchlist_cusip_choices(), value=None,
            label="Select CUSIP to remove", scale=3,
        )
        wl_remove_btn = gr.Button("Remove", variant="stop", scale=1, min_width=120)

    wl_remove_msg = gr.HTML(value="")

    # ═════════════════════════════════════════════════════════════════════════
    # Event handlers
    # ═════════════════════════════════════════════════════════════════════════

    def _refresh_wl(username: str):
        return _watchlist_df(username), gr.update(
            choices=_watchlist_cusip_choices(username), value=None
        )

    def _dash(username: str):
        if dashboard_html is None:
            return gr.update()
        return gr.update(value=_fresh_dashboard_html(username))

    def _extra():
        return [dashboard_html] if dashboard_html is not None else []

    # ── Search ────────────────────────────────────────────────────────────────
    def _wl_search(product, issuer, min_cpn, max_cpn, min_oas, max_oas, min_fico):
        df = _search_results(
            product  = product  or "All",
            issuer   = issuer   or "All",
            min_coupon = float(min_cpn  or 0),
            max_coupon = float(max_cpn  or 10),
            min_oas    = float(min_oas  or -50),
            max_oas    = float(max_oas  or 300),
            min_fico   = int(min_fico   or 600),
        )
        has = not df.empty
        return gr.update(value=df, visible=has)

    wl_search_btn.click(
        fn=_wl_search,
        inputs=[wl_filter_product, wl_filter_issuer,
                wl_filter_min_coupon, wl_filter_max_coupon,
                wl_filter_min_oas, wl_filter_max_oas,
                wl_filter_min_fico],
        outputs=[wl_results_df],
    )

    # ── Click row → show selection bar ───────────────────────────────────────
    def _wl_row_select(evt: gr.SelectData, df_value: pd.DataFrame):
        try:
            row   = evt.index[0]
            cusip = str(df_value.iloc[row]["CUSIP"])
            ptype = str(df_value.iloc[row].get("Type", ""))
            cpn   = str(df_value.iloc[row].get("Coupon %", ""))
            label = f"{cusip}  ·  {ptype} {cpn}%".strip(" ·")
            return gr.update(value=label), gr.update(visible=True), ""
        except Exception:
            return gr.update(), gr.update(), _err("Could not read row — try again.")

    wl_results_df.select(
        fn=_wl_row_select,
        inputs=[wl_results_df],
        outputs=[wl_selected_display, wl_selection_row, wl_search_msg],
    )

    # ── Add selected ──────────────────────────────────────────────────────────
    def _wl_sel_add(selected: str, notes: str, request: gr.Request):
        username = _get_username(request)
        cusip    = selected.split("  ·")[0].strip() if selected else ""
        if not cusip:
            return (_err("No CUSIP selected."), gr.update(), gr.update(), _dash(username))
        try:
            from data.watchlist_store import add_to_watchlist
            ok, msg = add_to_watchlist(cusip, pool_id=cusip, notes=notes or "",
                                       username=username)
            df, dd = _refresh_wl(username)
            return (_ok(f"✓ Added {cusip}") if ok else _err(msg)), df, dd, _dash(username)
        except Exception as ex:
            return _err(str(ex)), gr.update(), gr.update(), _dash(username)

    wl_sel_add_btn.click(
        fn=_wl_sel_add,
        inputs=[wl_selected_display, wl_sel_notes],
        outputs=[wl_search_msg, wl_table_df, wl_remove_dd] + _extra(),
    )

    # ── Add by CUSIP ──────────────────────────────────────────────────────────
    def _wl_add(cusip: str, notes: str, request: gr.Request):
        username = _get_username(request)
        cusip    = cusip.strip().upper()
        if not cusip:
            return _err("Please enter a CUSIP."), gr.update(), gr.update(), _dash(username)
        try:
            from data.watchlist_store import add_to_watchlist
            ok, msg = add_to_watchlist(cusip, pool_id=cusip, notes=notes or "",
                                       username=username)
            df, dd = _refresh_wl(username)
            return (_ok(msg) if ok else _err(msg)), df, dd, _dash(username)
        except Exception as ex:
            return _err(str(ex)), gr.update(), gr.update(), _dash(username)

    wl_add_btn.click(
        fn=_wl_add,
        inputs=[wl_cusip_input, wl_notes_input],
        outputs=[wl_add_msg, wl_table_df, wl_remove_dd] + _extra(),
    )

    # ── Remove ────────────────────────────────────────────────────────────────
    def _wl_remove(cusip: str, request: gr.Request):
        username = _get_username(request)
        if not cusip:
            return _err("Select a CUSIP to remove."), gr.update(), gr.update(), _dash(username)
        try:
            from data.watchlist_store import remove_from_watchlist
            ok, msg = remove_from_watchlist(cusip, username=username)
            df, dd = _refresh_wl(username)
            return (_ok(msg) if ok else _err(msg)), df, dd, _dash(username)
        except Exception as ex:
            return _err(str(ex)), gr.update(), gr.update(), _dash(username)

    wl_remove_btn.click(
        fn=_wl_remove,
        inputs=[wl_remove_dd],
        outputs=[wl_remove_msg, wl_table_df, wl_remove_dd] + _extra(),
    )

    return wl_add_msg, wl_table_df
