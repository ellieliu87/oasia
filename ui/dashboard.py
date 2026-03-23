"""
Oasia Dashboard — Primary portfolio overview.

Panels:
  - KPI bar: Market Value, Unrealized P&L, OAS, OAD, Book Yield, YTD Return, Health Score
  - Holdings table (filterable)
  - Sector Exposure donut chart (Plotly)
  - Top Performers YTD bar chart (Plotly)
  - Portfolio Health Scorecard radar chart (Plotly) with 6 dimensions
  - Watchlist table
  - Risk metrics card

Dashboard state (gr.State dict):
  {
    "filter_product": None | "CC30" | "CC15" | "GN30" | "GN15",
    "refresh_count": int   # increment to trigger refresh
  }
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import gradio as gr

# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------

_DEMO_POSITIONS = [
    {
        "pool_id": "TEST-POOL-30YR",
        "product_type": "CC30",
        "face_amount": 5_000_000.0,
        "book_price": 101.5,
        "market_price": 102.1,
        "coupon": 0.06,
        "wac": 0.065,
        "wala": 12,
        "wam": 348,
        "oas": 54.2,
        "oad": 4.52,
        "convexity": -0.74,
        "cpr": 12.4,
        "yield_pct": 0.0608,
        "purchase_date": "2024-06-01",
        "ytd_return_pct": 3.42,
    },
    {
        "pool_id": "TEST-POOL-15YR",
        "product_type": "CC15",
        "face_amount": 3_000_000.0,
        "book_price": 99.5,
        "market_price": 100.2,
        "coupon": 0.055,
        "wac": 0.059,
        "wala": 6,
        "wam": 174,
        "oas": 36.8,
        "oad": 3.21,
        "convexity": -0.22,
        "cpr": 9.8,
        "yield_pct": 0.0562,
        "purchase_date": "2024-09-15",
        "ytd_return_pct": 1.87,
    },
    {
        "pool_id": "TEST-POOL-GN30",
        "product_type": "GN30",
        "face_amount": 4_000_000.0,
        "book_price": 103.0,
        "market_price": 103.8,
        "coupon": 0.065,
        "wac": 0.07,
        "wala": 24,
        "wam": 336,
        "oas": 58.1,
        "oad": 4.18,
        "convexity": -1.12,
        "cpr": 14.2,
        "yield_pct": 0.0631,
        "purchase_date": "2023-12-01",
        "ytd_return_pct": 4.15,
    },
]

_WATCHLIST = [
    {"pool_id": "WL-CC30-6.5", "product_type": "CC30", "coupon": 6.5, "oas": 62.1, "oad": 4.81, "signal": "CHEAP"},
    {"pool_id": "WL-GN30-6.0", "product_type": "GN30", "coupon": 6.0, "oas": 51.3, "oad": 4.35, "signal": "FAIR"},
    {"pool_id": "WL-CC15-5.5", "product_type": "CC15", "coupon": 5.5, "oas": 40.2, "oad": 3.10, "signal": "CHEAP"},
    {"pool_id": "WL-GN15-5.0", "product_type": "GN15", "coupon": 5.0, "oas": 28.4, "oad": 2.85, "signal": "RICH"},
    {"pool_id": "WL-CC30-7.0", "product_type": "CC30", "coupon": 7.0, "oas": 71.5, "oad": 4.12, "signal": "CHEAP"},
]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _filter_positions(positions: list, product_filter) -> list:
    """Return positions filtered by product type (None = all)."""
    if not product_filter:
        return positions
    return [p for p in positions if p["product_type"] == product_filter]


def _compute_metrics(positions: list) -> dict:
    """Compute aggregate portfolio metrics from a list of position dicts."""
    if not positions:
        return {
            "total_face": 0.0,
            "total_mv": 0.0,
            "total_book": 0.0,
            "unrealized_pnl": 0.0,
            "unrealized_pnl_pct": 0.0,
            "n_positions": 0,
            "w_oas": 0.0,
            "w_oad": 0.0,
            "w_yield": 0.0,
            "w_convexity": 0.0,
            "w_cpr": 0.0,
            "w_ytd": 0.0,
        }

    total_face = sum(p["face_amount"] for p in positions)
    # MV = face * market_price / 100
    total_mv = sum(p["face_amount"] * p["market_price"] / 100.0 for p in positions)
    total_book = sum(p["face_amount"] * p["book_price"] / 100.0 for p in positions)
    unrealized_pnl = total_mv - total_book
    unrealized_pnl_pct = (unrealized_pnl / total_book * 100.0) if total_book else 0.0

    # MV-weighted metrics
    def _wt(field):
        return sum(p["face_amount"] * p["market_price"] / 100.0 * p[field] for p in positions) / total_mv

    w_oas = _wt("oas")
    w_oad = _wt("oad")
    w_convexity = _wt("convexity")
    w_cpr = _wt("cpr")
    w_ytd = _wt("ytd_return_pct")
    # yield as pct
    w_yield = _wt("yield_pct") * 100.0

    return {
        "total_face": total_face,
        "total_mv": total_mv,
        "total_book": total_book,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
        "n_positions": len(positions),
        "w_oas": w_oas,
        "w_oad": w_oad,
        "w_yield": w_yield,
        "w_convexity": w_convexity,
        "w_cpr": w_cpr,
        "w_ytd": w_ytd,
    }


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _health_dims(metrics: dict, positions: list) -> dict:
    """Compute 6 health dimension scores (0–10)."""
    w_oas = metrics["w_oas"]
    w_yield = metrics["w_yield"]
    w_oad = metrics["w_oad"]
    w_convexity = metrics["w_convexity"]
    w_oas_num = metrics["w_oas"]

    # Value: 20bps→1, 80bps→10, linear
    value = _clamp(1.0 + (w_oas - 20.0) / (80.0 - 20.0) * 9.0, 0.0, 10.0)

    # Carry: 4%→2, 7%→10, linear
    carry = _clamp(2.0 + (w_yield - 4.0) / (7.0 - 4.0) * 8.0, 0.0, 10.0)

    # Diversification: distinct product types * 2.5, positions / 2, cap 10
    n_products = len(set(p["product_type"] for p in positions)) if positions else 0
    n_pos = len(positions)
    diversification = _clamp(n_products * 2.5 + n_pos / 2.0, 0.0, 10.0)

    # Duration Risk: inverse of OAD (2yr→9, 7yr→3, linear)
    duration_risk = _clamp(9.0 - (w_oad - 2.0) / (7.0 - 2.0) * 6.0, 0.0, 10.0)

    # EVE Health: convexity (-0.2→8, -2.0→3, linear)
    eve_health = _clamp(8.0 + (w_convexity - (-0.2)) / ((-2.0) - (-0.2)) * (3.0 - 8.0), 0.0, 10.0)

    # Risk-Adj Return: w_oas / max(w_oad, 0.1) / 1.5, cap 0-10
    risk_adj = _clamp(w_oas_num / max(w_oad, 0.1) / 1.5, 0.0, 10.0)

    return {
        "Value": round(value, 2),
        "Carry": round(carry, 2),
        "Diversification": round(diversification, 2),
        "Duration Risk": round(duration_risk, 2),
        "EVE Health": round(eve_health, 2),
        "Risk-Adj Return": round(risk_adj, 2),
    }


def _composite_score(dims: dict) -> float:
    """Composite health score 0–100 from dimension scores."""
    weights = {
        "Value": 0.20,
        "Carry": 0.20,
        "Diversification": 0.15,
        "Duration Risk": 0.20,
        "EVE Health": 0.15,
        "Risk-Adj Return": 0.10,
    }
    score = sum(dims.get(k, 0.0) * w for k, w in weights.items())
    return _clamp(score * 10.0, 0.0, 100.0)  # dims are 0-10, multiply by 10 for 0-100


# ---------------------------------------------------------------------------
# KPI bar HTML
# ---------------------------------------------------------------------------

def _kpi_html(metrics: dict, composite: float, product_filter) -> str:
    """Build the KPI bar HTML string."""

    def _card(label: str, value: str, color: str = "#0F172A") -> str:
        return (
            f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:6px;'
            f'padding:10px 14px;flex:1;min-width:105px;">'
            f'<div style="font-size:9px;color:#64748B;text-transform:uppercase;'
            f'letter-spacing:0.07em;font-family:DM Sans,sans-serif;margin-bottom:4px;">{label}</div>'
            f'<div style="font-family:\'JetBrains Mono\',monospace;font-size:15px;'
            f'font-weight:600;color:{color};">{value}</div>'
            f'</div>'
        )

    total_mv = metrics["total_mv"]
    pnl = metrics["unrealized_pnl"]
    pnl_pct = metrics["unrealized_pnl_pct"]
    w_oas = metrics["w_oas"]
    w_oad = metrics["w_oad"]
    w_yield = metrics["w_yield"]
    w_ytd = metrics["w_ytd"]

    # Market Value
    c1 = _card("Market Value", f"${total_mv/1e6:.2f}M", "#0F172A")

    # Unrealized P&L
    if pnl >= 0:
        pnl_str = f"+${pnl/1000:.0f}K (+{pnl_pct:.2f}%)"
        pnl_color = "#059669"
    else:
        pnl_str = f"-${abs(pnl)/1000:.0f}K ({pnl_pct:.2f}%)"
        pnl_color = "#E5484D"
    c2 = _card("Unrealized P&L", pnl_str, pnl_color)

    # OAS
    c3 = _card("Portfolio OAS", f"{w_oas:.1f} bps", "#3B6FD4")

    # OAD
    c4 = _card("OAD", f"{w_oad:.2f} yr", "#0F172A")

    # Book Yield
    c5 = _card("Book Yield", f"{w_yield:.2f}%", "#0F172A")

    # YTD Return
    ytd_color = "#059669" if w_ytd >= 0 else "#E5484D"
    c6 = _card("YTD Return", f"{w_ytd:+.2f}%", ytd_color)

    # Health Score
    if composite >= 70:
        hs_color = "#059669"
    elif composite >= 50:
        hs_color = "#D97706"
    else:
        hs_color = "#E5484D"
    c7 = _card("Health Score", f"{composite:.0f}/100", hs_color)

    # Optional filter badge
    badge = ""
    if product_filter:
        badge = (
            f'<span style="background:#E2E8F0;color:#3B6FD4;border:1px solid #0F1F3D;'
            f'border-radius:10px;padding:1px 8px;font-size:10px;margin-left:8px;">'
            f'Filtered: {product_filter}</span>'
        )

    title_row = (
        f'<div style="font-family:DM Sans,sans-serif;font-size:10px;color:#64748B;'
        f'letter-spacing:0.06em;text-transform:uppercase;margin-bottom:6px;">'
        f'Portfolio Overview{badge}</div>'
    )

    return (
        f'{title_row}'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap;padding:2px 0 8px;">'
        f'{c1}{c2}{c3}{c4}{c5}{c6}{c7}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Sector exposure donut
# ---------------------------------------------------------------------------

_SECTOR_COLORS = {
    "CC30": "#3B6FD4",
    "CC15": "#059669",
    "GN30": "#D97706",
    "GN15": "#a371f7",
}


def _make_sector_chart(positions: list) -> go.Figure:
    """Build sector exposure donut chart."""
    sector_face: dict[str, float] = {}
    for p in positions:
        pt = p["product_type"]
        sector_face[pt] = sector_face.get(pt, 0.0) + p["face_amount"]

    labels = list(sector_face.keys())
    values = [sector_face[k] / 1e6 for k in labels]
    colors = [_SECTOR_COLORS.get(k, "#64748B") for k in labels]

    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=0.6,
            marker=dict(colors=colors, line=dict(color="#F8F9FC", width=2)),
            textfont=dict(family="JetBrains Mono", size=10, color="#0F172A"),
            hovertemplate="%{label}: $%{value:.2f}M<extra></extra>",
        )
    )

    n = len(positions)
    fig.add_annotation(
        text=f"<b>{n}</b><br><span style='font-size:10px'>Positions</span>",
        x=0.5, y=0.5,
        font=dict(size=12, color="#64748B", family="JetBrains Mono"),
        showarrow=False,
    )

    fig.update_layout(
        title=dict(text="Sector Exposure", font=dict(color="#64748B", size=11, family="DM Sans"), x=0.02),
        paper_bgcolor="#F8F9FC",
        plot_bgcolor="#F8F9FC",
        font=dict(color="#0F172A", family="JetBrains Mono"),
        height=260,
        margin=dict(l=10, r=10, t=30, b=10),
        showlegend=True,
        legend=dict(
            orientation="v",
            x=1.0, y=0.5,
            font=dict(size=10, color="#0F172A", family="JetBrains Mono"),
            bgcolor="rgba(0,0,0,0)",
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# YTD bar chart
# ---------------------------------------------------------------------------

def _make_ytd_chart(positions: list) -> go.Figure:
    """Build horizontal YTD return bar chart."""
    sorted_pos = sorted(positions, key=lambda p: p["ytd_return_pct"], reverse=True)

    # Shorten pool ID to last part after last dash
    def _short(pool_id: str) -> str:
        parts = pool_id.rsplit("-", 1)
        return parts[-1] if len(parts) > 1 else pool_id

    y_labels = [_short(p["pool_id"]) for p in sorted_pos]
    x_vals = [p["ytd_return_pct"] for p in sorted_pos]
    colors = ["#059669" if v >= 0 else "#E5484D" for v in x_vals]
    texts = [f"{v:+.2f}%" for v in x_vals]

    fig = go.Figure(
        go.Bar(
            x=x_vals,
            y=y_labels,
            orientation="h",
            marker=dict(color=colors),
            text=texts,
            textposition="outside",
            textfont=dict(family="JetBrains Mono", size=10, color="#0F172A"),
            hovertemplate="%{y}: %{x:+.2f}%<extra></extra>",
        )
    )

    fig.update_layout(
        title=dict(text="YTD Return (%)", font=dict(color="#64748B", size=11, family="DM Sans"), x=0.02),
        paper_bgcolor="#F8F9FC",
        plot_bgcolor="#FFFFFF",
        font=dict(color="#0F172A", family="JetBrains Mono"),
        height=260,
        margin=dict(l=10, r=60, t=30, b=10),
        xaxis=dict(
            gridcolor="#E2E8F0",
            zerolinecolor="#CBD5E1",
            tickfont=dict(size=9, color="#64748B"),
        ),
        yaxis=dict(
            showgrid=False,
            tickfont=dict(size=10, color="#0F172A"),
        ),
    )
    return fig


# ---------------------------------------------------------------------------
# Health radar chart
# ---------------------------------------------------------------------------

def _make_health_radar(dims: dict) -> go.Figure:
    """Build portfolio health radar (spider) chart."""
    categories = list(dims.keys())
    values = list(dims.values())

    # Close the loop
    cats_closed = categories + [categories[0]]
    vals_closed = values + [values[0]]
    ref_vals = [5.0] * len(cats_closed)

    fig = go.Figure()

    # Reference polygon at 5.0
    fig.add_trace(
        go.Scatterpolar(
            r=ref_vals,
            theta=cats_closed,
            mode="lines",
            line=dict(color="#CBD5E1", width=1, dash="dot"),
            fill=None,
            showlegend=False,
            hoverinfo="skip",
        )
    )

    # Main portfolio polygon
    fig.add_trace(
        go.Scatterpolar(
            r=vals_closed,
            theta=cats_closed,
            fill="toself",
            fillcolor="rgba(59,111,212,0.15)",
            line=dict(color="#3B6FD4", width=2),
            name="Portfolio",
            hovertemplate="%{theta}: %{r:.1f}<extra></extra>",
        )
    )

    fig.update_layout(
        title=dict(text="Portfolio Health", font=dict(color="#64748B", size=11, family="DM Sans"), x=0.02),
        polar=dict(
            bgcolor="#F8F9FC",
            radialaxis=dict(
                range=[0, 10],
                gridcolor="#E2E8F0",
                tickfont=dict(color="#64748B", size=8),
                showticklabels=True,
                linecolor="#E2E8F0",
            ),
            angularaxis=dict(
                gridcolor="#E2E8F0",
                tickfont=dict(color="#64748B", size=9),
                linecolor="#E2E8F0",
            ),
        ),
        paper_bgcolor="#F8F9FC",
        font=dict(color="#0F172A", family="JetBrains Mono"),
        height=280,
        margin=dict(l=40, r=40, t=40, b=40),
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# Holdings DataFrame
# ---------------------------------------------------------------------------

def _make_holdings_df(positions: list) -> pd.DataFrame:
    """Build holdings display DataFrame."""
    rows = []
    for p in positions:
        rows.append({
            "Pool ID": p["pool_id"],
            "Product": p["product_type"],
            "Face ($M)": round(p["face_amount"] / 1e6, 2),
            "Book Px": round(p["book_price"], 3),
            "Mkt Px": round(p["market_price"], 3),
            "OAS (bps)": round(p["oas"], 1),
            "OAD (yr)": round(p["oad"], 2),
            "Convexity": round(p["convexity"], 3),
            "CPR %": round(p["cpr"], 1),
            "Yield %": round(p["yield_pct"] * 100.0, 3),
            "YTD %": round(p["ytd_return_pct"], 2),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Watchlist DataFrame
# ---------------------------------------------------------------------------

def _make_watchlist_df() -> pd.DataFrame:
    """Build watchlist display DataFrame."""
    rows = []
    for w in _WATCHLIST:
        rows.append({
            "Pool ID": w["pool_id"],
            "Product": w["product_type"],
            "Coupon": w["coupon"],
            "OAS (bps)": w["oas"],
            "OAD (yr)": w["oad"],
            "Signal": w["signal"],
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Risk metrics HTML
# ---------------------------------------------------------------------------

def _make_risk_html(metrics: dict, dims: dict, composite: float) -> str:
    """Build risk profile card HTML."""
    if composite >= 70:
        bar_color = "#059669"
    elif composite >= 50:
        bar_color = "#D97706"
    else:
        bar_color = "#E5484D"

    if composite >= 70:
        score_color = "#059669"
    elif composite >= 50:
        score_color = "#D97706"
    else:
        score_color = "#E5484D"

    w_oas = metrics["w_oas"]
    w_oad = metrics["w_oad"]
    w_convexity = metrics["w_convexity"]
    w_cpr = metrics["w_cpr"]

    eve_approx = -(w_oad * 3.0)
    sharpe_proxy = w_oas / (max(w_oad, 0.1) * 100.0) * 100.0

    def _row(label: str, value: str, val_color: str = "#0F172A") -> str:
        return (
            f'<tr>'
            f'<td style="font-family:DM Sans,sans-serif;font-size:11px;color:#64748B;'
            f'padding:4px 6px 4px 0;">{label}</td>'
            f'<td style="font-family:\'JetBrains Mono\',monospace;font-size:12px;'
            f'color:{val_color};text-align:right;padding:4px 0;">{value}</td>'
            f'</tr>'
        )

    rows_html = (
        _row("Composite Score", f"{composite:.0f}/100", score_color)
        + _row("OAS", f"{w_oas:.1f} bps")
        + _row("OAD", f"{w_oad:.2f} yr")
        + _row("Convexity", f"{w_convexity:.3f}")
        + _row("Model CPR", f"{w_cpr:.1f}%")
        + _row("EVE +300bp", f"≈{eve_approx:.1f}%", "#E5484D")
        + _row("Sharpe Proxy", f"{sharpe_proxy:.2f}", "#3B6FD4")
    )

    return (
        f'<div style="background:#FFFFFF;border:1px solid #E2E8F0;border-radius:6px;'
        f'overflow:hidden;">'
        f'<div style="height:3px;background:{bar_color};"></div>'
        f'<div style="padding:12px;">'
        f'<div style="font-family:DM Sans,sans-serif;font-size:10px;color:#64748B;'
        f'text-transform:uppercase;letter-spacing:0.07em;margin-bottom:8px;">Risk Profile</div>'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'{rows_html}'
        f'</table>'
        f'</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def create_dashboard(shared_state: gr.State, dashboard_state: gr.State):
    """Build the dashboard panel. Called inside a gr.Tab context."""

    # Compute initial values at build time
    _init_ds = {}
    _init_pf = None
    _init_positions = _filter_positions(_DEMO_POSITIONS, _init_pf)
    _init_metrics = _compute_metrics(_init_positions)
    _init_dims = _health_dims(_init_metrics, _init_positions)
    _init_composite = _composite_score(_init_dims)

    _init_kpi = _kpi_html(_init_metrics, _init_composite, _init_pf)
    _init_holdings = _make_holdings_df(_init_positions)
    _init_sector = _make_sector_chart(_init_positions)
    _init_ytd = _make_ytd_chart(_init_positions)
    _init_health = _make_health_radar(_init_dims)
    _init_risk = _make_risk_html(_init_metrics, _init_dims, _init_composite)
    _init_watchlist = _make_watchlist_df()

    # ---- Row 1: KPI bar ----
    kpi_bar = gr.HTML(value=_init_kpi, elem_id="dash-kpi")

    # ---- Row 2: Holdings + Sector + YTD ----
    with gr.Row(equal_height=False):
        with gr.Column(scale=5):
            holdings_table = gr.DataFrame(
                value=_init_holdings,
                label="Holdings",
                interactive=False,
            )
        with gr.Column(scale=3):
            sector_chart = gr.Plot(value=_init_sector, label="")
        with gr.Column(scale=2):
            ytd_chart = gr.Plot(value=_init_ytd, label="")

    # ---- Row 3: Radar + Risk + Watchlist ----
    with gr.Row(equal_height=False):
        with gr.Column(scale=3):
            health_chart = gr.Plot(value=_init_health, label="")
        with gr.Column(scale=2):
            risk_html = gr.HTML(value=_init_risk)
        with gr.Column(scale=3):
            watchlist_table = gr.DataFrame(
                value=_init_watchlist,
                label="Watchlist",
                interactive=False,
            )

    # ---- Row 4: Controls ----
    with gr.Row():
        refresh_dash_btn = gr.Button("Refresh Dashboard", variant="secondary", size="sm")
        filter_label = gr.HTML(
            "<span style='font-size:11px;color:#64748B;font-family:DM Sans,sans-serif;"
            "padding:4px 8px;'>Filter:</span>"
        )
        filter_product = gr.Dropdown(
            choices=["All", "CC30", "CC15", "GN30", "GN15"],
            value="All",
            label="",
            scale=0,
            min_width=100,
        )

    # ---- Event wiring ----

    def _do_refresh(dash_state):
        pf = dash_state.get("filter_product") if dash_state else None
        positions = _filter_positions(_DEMO_POSITIONS, pf)
        metrics = _compute_metrics(positions)
        dims = _health_dims(metrics, positions)
        composite = _composite_score(dims)
        return (
            _kpi_html(metrics, composite, pf),
            _make_holdings_df(positions),
            _make_sector_chart(positions),
            _make_ytd_chart(positions),
            _make_health_radar(dims),
            _make_risk_html(metrics, dims, composite),
            _make_watchlist_df(),
        )

    outputs = [kpi_bar, holdings_table, sector_chart, ytd_chart, health_chart, risk_html, watchlist_table]

    refresh_dash_btn.click(fn=_do_refresh, inputs=[dashboard_state], outputs=outputs)

    def _filter_change(choice, dash_state):
        ds = dict(dash_state or {})
        ds["filter_product"] = None if choice == "All" else choice
        ds["refresh_count"] = ds.get("refresh_count", 0) + 1
        return ds

    filter_product.change(
        fn=_filter_change,
        inputs=[filter_product, dashboard_state],
        outputs=[dashboard_state],
    )

    dashboard_state.change(fn=_do_refresh, inputs=[dashboard_state], outputs=outputs)

    return (kpi_bar, holdings_table, sector_chart, ytd_chart, health_chart, risk_html, watchlist_table, filter_product)
