"""
ui/watchlist.py

Watchlist tab — search the MBS universe, add/remove CUSIPs, view watchlist.
All interactions are fully Gradio-native (no JS bridge required).
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


def _search_results(product: str = "All", min_oas: float = 0,
                    max_oad: float = 10) -> tuple[pd.DataFrame, list[str]]:
    """Return (display_df, dropdown_choices) for universe search."""
    try:
        from data.universe_1000 import get_universe_1000
        df = get_universe_1000()
        if product and product != "All" and "product_type" in df.columns:
            df = df[df["product_type"] == product]
        df = df.head(20)
        if df.empty:
            return pd.DataFrame(columns=["CUSIP", "Type", "Coupon %", "FICO", "LTV %"]), []
        display = pd.DataFrame([
            {
                "CUSIP":   str(r.get("cusip", "")),
                "Pool ID": str(r.get("pool_id", "")),
                "Type":    str(r.get("product_type", "")),
                "Coupon %": f"{float(r.get('coupon', 0)):.2f}",
                "FICO":    int(r.get("fico", 0)) if r.get("fico") else 0,
                "LTV %":   f"{float(r.get('ltv', 0)) * 100:.0f}",
            }
            for _, r in df.iterrows()
        ])
        choices = [
            f"{r.get('cusip','')} — {r.get('product_type','')} {float(r.get('coupon',0)):.2f}%"
            for _, r in df.iterrows()
        ]
        return display, choices
    except Exception as ex:
        return pd.DataFrame(columns=["CUSIP", "Type", "Coupon %", "FICO", "LTV %"]), []


def _cusip_from_choice(choice: str | None) -> str:
    """Extract bare CUSIP from a dropdown choice string like 'ABCD1234 — CC30 6.00%'."""
    if not choice:
        return ""
    return choice.split(" — ")[0].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Tab builder
# ─────────────────────────────────────────────────────────────────────────────

def _get_username(request: gr.Request) -> str:
    try:
        from auth.session import get_username, COOKIE_NAME
        return get_username(request.request.cookies.get(COOKIE_NAME)) or "default"
    except Exception:
        return "default"


def _ok(msg: str) -> str:
    return f'<div style="color:#059669;font-family:var(--mono);font-size:12px;padding:4px 0;">{msg}</div>'

def _err(msg: str) -> str:
    return f'<div style="color:#E5484D;font-family:var(--mono);font-size:12px;padding:4px 0;">{msg}</div>'


def create_watchlist_tab(shared_state: gr.State):
    gr.HTML(
        '<div class="dash-header-left" style="padding-bottom:16px;'
        'border-bottom:1px solid var(--border);margin-bottom:20px;">'
        '<div class="dash-header-title">Watchlist</div>'
        '<div class="dash-header-sub">Search the agency MBS universe and build a personal '
        'watchlist of CUSIPs to monitor prices, spreads, and key pool characteristics.</div>'
        "</div>",
        elem_classes=["nexus-tab-hdr"],
    )

    # ── Section 1: Add by CUSIP directly ─────────────────────────────────────
    gr.HTML(
        "<div style='font-size:11px;font-weight:700;color:#94A3B8;text-transform:uppercase;"
        "letter-spacing:.08em;margin:0 0 10px;font-family:DM Sans,sans-serif;'>"
        "Add by CUSIP</div>"
    )
    with gr.Row():
        wl_cusip_input = gr.Textbox(
            placeholder="e.g. 3140X7GK4",
            label="CUSIP",
            scale=2,
        )
        wl_notes_input = gr.Textbox(
            placeholder="Notes (optional)",
            label="Notes",
            scale=2,
        )
        wl_add_btn = gr.Button("★  Add to Watchlist", variant="primary", scale=1)

    wl_msg_html = gr.HTML(value="")

    gr.HTML("<div style='height:16px'></div>")

    # ── Section 2: Universe Search ────────────────────────────────────────────
    gr.HTML(
        "<div style='font-size:11px;font-weight:700;color:#94A3B8;text-transform:uppercase;"
        "letter-spacing:.08em;margin:0 0 10px;font-family:DM Sans,sans-serif;'>"
        "Universe Search</div>"
    )
    with gr.Row():
        wl_filter_product = gr.Dropdown(
            choices=["All", "CC30", "CC15", "GN30", "GN15", "ARM", "TSY", "CMBS", "CMO", "CDBT"],
            value="All",
            label="Product Type",
            scale=1,
        )
        wl_filter_min_oas = gr.Number(value=0,  label="Min OAS (bps)", scale=1, precision=0)
        wl_filter_max_oad = gr.Number(value=10, label="Max OAD",       scale=1, precision=1)
        wl_search_btn = gr.Button("Search", variant="primary", scale=1)

    wl_results_df = gr.DataFrame(
        value=pd.DataFrame(columns=["CUSIP", "Pool ID", "Type", "Coupon %", "FICO", "LTV %"]),
        label="Search Results (top 20)",
        interactive=False,
        visible=False,
        wrap=False,
    )

    # ── Section 3: Add from search results ───────────────────────────────────
    with gr.Row(visible=False) as wl_pick_row:
        wl_pick_dd = gr.Dropdown(
            choices=[],
            value=None,
            label="Select CUSIP to add",
            scale=3,
        )
        wl_pick_notes = gr.Textbox(
            placeholder="Notes (optional)",
            label="Notes",
            scale=2,
        )
        wl_pick_add_btn = gr.Button("+ Add Selected", variant="primary", scale=1)

    wl_search_msg = gr.HTML(value="")

    gr.HTML("<div style='height:16px'></div>")

    # ── Section 4: My Watchlist ───────────────────────────────────────────────
    gr.HTML(
        "<div style='font-size:11px;font-weight:700;color:#94A3B8;text-transform:uppercase;"
        "letter-spacing:.08em;margin:0 0 10px;font-family:DM Sans,sans-serif;'>"
        "My Watchlist</div>"
    )

    wl_table_df = gr.DataFrame(
        value=_watchlist_df(),
        label="",
        interactive=False,
        wrap=False,
    )

    with gr.Row():
        wl_remove_dd = gr.Dropdown(
            choices=_watchlist_cusip_choices(),
            value=None,
            label="Select CUSIP to remove",
            scale=3,
        )
        wl_remove_btn = gr.Button("Remove", variant="stop", scale=1, min_width=120)

    wl_remove_msg = gr.HTML(value="")

    # ═════════════════════════════════════════════════════════════════════════
    # Event handlers
    # ═════════════════════════════════════════════════════════════════════════

    def _refresh_watchlist(username: str):
        df      = _watchlist_df(username)
        choices = _watchlist_cusip_choices(username)
        return df, gr.update(choices=choices, value=None)

    # ── Add by CUSIP directly ─────────────────────────────────────────────────
    def _wl_add(cusip: str, notes: str, request: gr.Request):
        username = _get_username(request)
        cusip = cusip.strip().upper()
        if not cusip:
            return _err("Please enter a CUSIP."), gr.update(), gr.update()
        try:
            from data.watchlist_store import add_to_watchlist
            ok, msg = add_to_watchlist(cusip, pool_id=cusip, notes=notes, username=username)
            df, remove_dd = _refresh_watchlist(username)
            return (_ok(msg) if ok else _err(msg)), df, remove_dd
        except Exception as ex:
            return _err(str(ex)), gr.update(), gr.update()

    wl_add_btn.click(
        fn=_wl_add,
        inputs=[wl_cusip_input, wl_notes_input],
        outputs=[wl_msg_html, wl_table_df, wl_remove_dd],
    )

    # ── Universe search ───────────────────────────────────────────────────────
    def _wl_search(product: str, min_oas: float, max_oad: float):
        display_df, choices = _search_results(product, min_oas or 0, max_oad or 10)
        has_results = not display_df.empty
        return (
            gr.update(value=display_df, visible=has_results),
            gr.update(choices=choices, value=None, visible=has_results),
            gr.update(visible=has_results),
        )

    wl_search_btn.click(
        fn=_wl_search,
        inputs=[wl_filter_product, wl_filter_min_oas, wl_filter_max_oad],
        outputs=[wl_results_df, wl_pick_dd, wl_pick_row],
    )

    # ── Add from search results ───────────────────────────────────────────────
    def _wl_pick_add(choice: str, notes: str, request: gr.Request):
        username = _get_username(request)
        cusip = _cusip_from_choice(choice)
        if not cusip:
            return _err("Select a CUSIP from the dropdown first."), gr.update(), gr.update()
        try:
            from data.watchlist_store import add_to_watchlist
            ok, msg = add_to_watchlist(cusip, pool_id=cusip, notes=notes, username=username)
            df, remove_dd = _refresh_watchlist(username)
            return (_ok(msg) if ok else _err(msg)), df, remove_dd
        except Exception as ex:
            return _err(str(ex)), gr.update(), gr.update()

    wl_pick_add_btn.click(
        fn=_wl_pick_add,
        inputs=[wl_pick_dd, wl_pick_notes],
        outputs=[wl_search_msg, wl_table_df, wl_remove_dd],
    )

    # ── Remove from watchlist ─────────────────────────────────────────────────
    def _wl_remove(cusip: str, request: gr.Request):
        username = _get_username(request)
        if not cusip:
            return _err("Select a CUSIP to remove."), gr.update(), gr.update()
        try:
            from data.watchlist_store import remove_from_watchlist
            ok, msg = remove_from_watchlist(cusip, username=username)
            df, remove_dd = _refresh_watchlist(username)
            return (_ok(msg) if ok else _err(msg)), df, remove_dd
        except Exception as ex:
            return _err(str(ex)), gr.update(), gr.update()

    wl_remove_btn.click(
        fn=_wl_remove,
        inputs=[wl_remove_dd],
        outputs=[wl_remove_msg, wl_table_df, wl_remove_dd],
    )

    return wl_msg_html, wl_table_df
