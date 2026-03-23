"""
Attribution UI — Workflow 4.

4-quadrant waterfall chart layout for OAS, OAD, yield, and EVE attribution.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import gradio as gr
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _make_waterfall(title: str, drivers: dict, color_theme: str = "cyan") -> go.Figure:
    """Create a Plotly waterfall chart for attribution drivers."""
    colors = {
        "cyan":  {"positive": "#3B6FD4", "negative": "#E5484D", "total": "#0F1F3D"},
        "green": {"positive": "#059669", "negative": "#E5484D", "total": "#0F1F3D"},
        "amber": {"positive": "#D97706", "negative": "#E5484D", "total": "#0F1F3D"},
    }
    c = colors.get(color_theme, colors["cyan"])

    labels = list(drivers.keys())
    values = list(drivers.values())

    # Separate out "total" for special treatment
    measure = ["relative"] * len(labels)
    if "total" in labels:
        total_idx = labels.index("total")
        measure[total_idx] = "total"

    bar_colors = []
    for i, (label, val) in enumerate(zip(labels, values)):
        if label == "total":
            bar_colors.append(c["total"])
        elif isinstance(val, (int, float)) and val >= 0:
            bar_colors.append(c["positive"])
        else:
            bar_colors.append(c["negative"])

    fig = go.Figure(go.Waterfall(
        name=title,
        orientation="v",
        measure=measure,
        x=[l.replace("_", " ").title() for l in labels],
        y=values,
        connector=dict(line=dict(color="#CBD5E1", width=1)),
        increasing=dict(marker_color=c["positive"]),
        decreasing=dict(marker_color=c["negative"]),
        totals=dict(marker_color=c["total"]),
        text=[f"{v:+.2f}" if isinstance(v, (int, float)) else str(v) for v in values],
        textposition="outside",
    ))

    fig.update_layout(
        title=dict(text=title, font=dict(color="#3B6FD4", size=13)),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#F8F9FC",
        font=dict(color="#0F172A", family="JetBrains Mono", size=10),
        xaxis=dict(gridcolor="#E2E8F0", tickangle=-30),
        yaxis=dict(gridcolor="#E2E8F0"),
        showlegend=False,
        height=280,
        margin=dict(l=40, r=20, t=50, b=60),
    )

    return fig


def _run_attribution(start_date: date, end_date: date) -> tuple:
    """
    Run attribution analysis between two dates.

    Returns (oas_attr, oad_attr, yield_attr, eve_attr) dicts.
    """
    # In production, load snapshots from SnapshotStore
    # For demo, use synthetic attribution data scaled by time period
    n_months = max(1, (end_date - start_date).days // 30)

    oas_attr = {
        "sector_spread_change": round(2.5 * n_months / 3, 2),
        "spread_carry": round(0.3 * n_months, 2),
        "mix_new_purchases": round(1.8 * n_months / 3, 2),
        "mix_paydowns": round(-0.4 * n_months / 3, 2),
        "prepay_model_effect": 0.0,  # will be residual
        "total": 0.0,
    }
    subtotal = sum(v for k, v in oas_attr.items() if k not in ("prepay_model_effect", "total"))
    total_oas = round(4.0 * n_months / 3, 2)
    oas_attr["prepay_model_effect"] = round(total_oas - subtotal, 4)
    oas_attr["total"] = total_oas

    oad_attr = {
        "seasoning_effect": round(-0.02 * n_months, 4),
        "rate_level_effect": round(0.15 * n_months / 3, 4),
        "mix_new_purchases": round(0.08 * n_months / 3, 4),
        "mix_paydowns": round(-0.01 * n_months / 3, 4),
        "sales_disposals": 0.0,
        "total": 0.0,
    }
    subtotal_oad = sum(v for k, v in oad_attr.items() if k not in ("sales_disposals", "total"))
    total_oad = round(0.20 * n_months / 3, 4)
    oad_attr["sales_disposals"] = round(total_oad - subtotal_oad, 6)
    oad_attr["total"] = total_oad

    yield_attr = {
        "prepay_burndown": round(-0.003 * n_months / 3, 4),
        "new_purchases": round(0.015 * n_months / 3, 4),
        "paydown_effect": round(0.002 * n_months / 3, 4),
        "coupon_reinvested": round(0.001 * n_months / 3, 4),
        "amortization_scheduled": 0.0,
        "total": 0.0,
    }
    subtotal_yield = sum(v for k, v in yield_attr.items() if k not in ("amortization_scheduled", "total"))
    total_yield = round(0.010 * n_months / 3, 4)
    yield_attr["amortization_scheduled"] = round(total_yield - subtotal_yield, 6)
    yield_attr["total"] = total_yield

    eve_attr = {
        "rate_curve_change": round(-450_000 * n_months / 3, 0),
        "portfolio_mix_change": round(120_000 * n_months / 3, 0),
        "prepay_model_effect": round(30_000 * n_months / 3, 0),
        "new_purchases_added": 0.0,
        "total": 0.0,
    }
    subtotal_eve = sum(v for k, v in eve_attr.items() if k not in ("new_purchases_added", "total"))
    total_eve = round(-350_000 * n_months / 3, 0)
    eve_attr["new_purchases_added"] = round(total_eve - subtotal_eve, 0)
    eve_attr["total"] = total_eve

    return oas_attr, oad_attr, yield_attr, eve_attr


def create_attribution_tab(shared_state: gr.State):
    """Build the Attribution tab."""

    gr.HTML(
        '<div class="dash-header-left" style="padding-bottom:16px;border-bottom:1px solid var(--border);margin-bottom:20px;">'
        '<div class="dash-header-title">Performance Attribution</div>'
        '<div class="dash-header-sub">Decompose portfolio total return into OAS carry, rate duration, convexity, spread change, and principal cash-flow components over a chosen look-back period.</div>'
        "</div>",
        elem_classes=["nexus-tab-hdr"],
    )

    with gr.Column():

        # ---- Period Selector ----
        with gr.Row():
            preset = gr.Dropdown(
                choices=["1 Month", "3 Months", "6 Months", "YTD", "Custom"],
                value="1 Month",
                label="Period Preset",
            )
            with gr.Row():
                start_date_input = gr.Textbox(
                    label="Start Date",
                    placeholder="YYYY-MM-DD",
                    value=(date.today() - timedelta(days=30)).strftime("%Y-%m-%d"),
                )
                end_date_input = gr.Textbox(
                    label="End Date",
                    placeholder="YYYY-MM-DD",
                    value=date.today().strftime("%Y-%m-%d"),
                )

        with gr.Row():
            run_attribution_btn = gr.Button("Run Attribution", variant="primary")
            memo_btn = gr.Button("Generate Memo", variant="secondary")

        attribution_status = gr.Markdown("*Click 'Run Attribution' to compute.*")

        with gr.Column(visible=False) as results_col:
            # ---- 4-Quadrant Waterfall Charts ----
            with gr.Row():
                oas_chart = gr.Plot(label="OAS Attribution")
                oad_chart = gr.Plot(label="OAD Attribution")

            with gr.Row():
                yield_chart = gr.Plot(label="Yield Attribution")
                eve_chart = gr.Plot(label="EVE Attribution")

            # ---- Detail Tables ----
            with gr.Row():
                with gr.Column():
                    oas_detail = gr.DataFrame(label="OAS Attribution (bps)", interactive=False)
                with gr.Column():
                    oad_detail = gr.DataFrame(label="OAD Attribution (years)", interactive=False)

            with gr.Row():
                with gr.Column():
                    yield_detail = gr.DataFrame(label="Yield Attribution (%)", interactive=False)
                with gr.Column():
                    eve_detail = gr.DataFrame(label="EVE Attribution ($)", interactive=False)

            export_csv_btn = gr.Button("Export Attribution Report as CSV", variant="primary")

        # ---- Memo output ----
        memo_output = gr.HTML(visible=False)

    # ---- Event Handlers ----
    def update_dates(preset_val):
        today = date.today()
        if preset_val == "1 Month":
            start = today - timedelta(days=30)
        elif preset_val == "3 Months":
            start = today - timedelta(days=90)
        elif preset_val == "6 Months":
            start = today - timedelta(days=180)
        elif preset_val == "YTD":
            start = date(today.year, 1, 1)
        else:
            return gr.update(), gr.update()  # custom — don't change
        return start.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")

    preset.change(
        fn=update_dates,
        inputs=[preset],
        outputs=[start_date_input, end_date_input],
    )

    def run_attribution(start_str, end_str):
        try:
            start = datetime.strptime(start_str.strip(), "%Y-%m-%d").date()
            end = datetime.strptime(end_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return [None] * 8 + ["Error: Invalid date format.", gr.update()]

        oas_attr, oad_attr, yield_attr, eve_attr = _run_attribution(start, end)

        # Build waterfall charts
        oas_fig = _make_waterfall("OAS Change (bps)", oas_attr, "cyan")
        oad_fig = _make_waterfall("OAD Change (years)", oad_attr, "green")
        yield_fig = _make_waterfall(
            "Yield Change (%)",
            {k: round(v * 100, 4) for k, v in yield_attr.items()},
            "amber"
        )
        eve_fig = _make_waterfall(
            f"EVE Change ($000s)",
            {k: round(v / 1000, 1) for k, v in eve_attr.items()},
            "cyan"
        )

        def _attr_to_df(attr: dict, unit: str = "") -> pd.DataFrame:
            rows = [
                {"Driver": k.replace("_", " ").title(), "Value": f"{v:+.4f}{unit}"}
                for k, v in attr.items()
            ]
            return pd.DataFrame(rows)

        oas_df = _attr_to_df(oas_attr, " bps")
        oad_df = _attr_to_df(oad_attr, " yr")
        yield_df = _attr_to_df({k: v * 100 for k, v in yield_attr.items()}, "%")
        eve_df = _attr_to_df({k: v / 1000 for k, v in eve_attr.items()}, "K")

        status = f"Attribution for {start} → {end} | Period: {(end-start).days} days"

        return oas_fig, oad_fig, yield_fig, eve_fig, oas_df, oad_df, yield_df, eve_df, status, gr.update(visible=True)

    run_attribution_btn.click(
        fn=run_attribution,
        inputs=[start_date_input, end_date_input],
        outputs=[
            oas_chart, oad_chart, yield_chart, eve_chart,
            oas_detail, oad_detail, yield_detail, eve_detail,
            attribution_status, results_col,
        ],
    )

    def generate_memo(start_str, end_str):
        """Generate a plain-text attribution memo."""
        try:
            start = datetime.strptime(start_str.strip(), "%Y-%m-%d").date()
            end = datetime.strptime(end_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return gr.update(visible=True, value="<div style='color:#E5484D;padding:8px;'>Error: Invalid dates.</div>")

        oas_attr, oad_attr, yield_attr, eve_attr = _run_attribution(start, end)

        memo = f"""Oasia — Attribution Memo
Period: {start} to {end}
Generated: {date.today()}

══════════════════════════════════════

OAS ATTRIBUTION: Total Change = {oas_attr['total']:+.2f} bps
  Sector Spread Change:    {oas_attr.get('sector_spread_change', 0):+.2f} bps
  Spread Carry:            {oas_attr.get('spread_carry', 0):+.2f} bps
  Mix - New Purchases:     {oas_attr.get('mix_new_purchases', 0):+.2f} bps
  Mix - Paydowns:          {oas_attr.get('mix_paydowns', 0):+.2f} bps
  Prepay Model Effect:     {oas_attr.get('prepay_model_effect', 0):+.2f} bps
  ─────────────────────────────────────
  TOTAL:                   {oas_attr['total']:+.2f} bps

OAD ATTRIBUTION: Total Change = {oad_attr['total']:+.4f} years
  Seasoning Effect:        {oad_attr.get('seasoning_effect', 0):+.4f} yr
  Rate Level Effect:       {oad_attr.get('rate_level_effect', 0):+.4f} yr
  Mix - New Purchases:     {oad_attr.get('mix_new_purchases', 0):+.4f} yr
  Mix - Paydowns:          {oad_attr.get('mix_paydowns', 0):+.4f} yr
  Sales/Disposals:         {oad_attr.get('sales_disposals', 0):+.4f} yr
  ─────────────────────────────────────
  TOTAL:                   {oad_attr['total']:+.4f} yr

YIELD ATTRIBUTION: Total Change = {yield_attr['total']*100:+.4f}%
  Prepay Burndown:         {yield_attr.get('prepay_burndown', 0)*100:+.4f}%
  New Purchases:           {yield_attr.get('new_purchases', 0)*100:+.4f}%
  Paydown Effect:          {yield_attr.get('paydown_effect', 0)*100:+.4f}%
  Coupon Reinvested:       {yield_attr.get('coupon_reinvested', 0)*100:+.4f}%
  Amortization:            {yield_attr.get('amortization_scheduled', 0)*100:+.4f}%
  ─────────────────────────────────────
  TOTAL:                   {yield_attr['total']*100:+.4f}%

EVE ATTRIBUTION: Total Change = ${eve_attr['total']:+,.0f}
  Rate Curve Change:       ${eve_attr.get('rate_curve_change', 0):+,.0f}
  Portfolio Mix Change:    ${eve_attr.get('portfolio_mix_change', 0):+,.0f}
  Prepay Model Effect:     ${eve_attr.get('prepay_model_effect', 0):+,.0f}
  New Purchases Added:     ${eve_attr.get('new_purchases_added', 0):+,.0f}
  ─────────────────────────────────────
  TOTAL:                   ${eve_attr['total']:+,.0f}

══════════════════════════════════════
Oasia Analytics Platform""".strip()

        return gr.update(
            visible=True,
            value=f"<pre style='font-family:JetBrains Mono,monospace;font-size:11px;color:#0F172A;padding:12px;background:#FFFFFF;border-radius:6px;white-space:pre-wrap;border:1px solid #E2E8F0;'>{memo}</pre>",
        )

    memo_btn.click(
        fn=generate_memo,
        inputs=[start_date_input, end_date_input],
        outputs=[memo_output],
    )

    def export_report(start_str, end_str):
        """Export attribution report to CSV."""
        import tempfile

        try:
            start = datetime.strptime(start_str.strip(), "%Y-%m-%d").date()
            end = datetime.strptime(end_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None

        oas_attr, oad_attr, yield_attr, eve_attr = _run_attribution(start, end)

        rows = []
        for k, v in oas_attr.items():
            rows.append({"metric": "OAS_bps", "driver": k, "value": v})
        for k, v in oad_attr.items():
            rows.append({"metric": "OAD_yrs", "driver": k, "value": v})
        for k, v in yield_attr.items():
            rows.append({"metric": "Yield_pct", "driver": k, "value": v * 100})
        for k, v in eve_attr.items():
            rows.append({"metric": "EVE_dollars", "driver": k, "value": v})

        df = pd.DataFrame(rows)
        tmp = tempfile.NamedTemporaryFile(suffix=".csv", delete=False)
        df.to_csv(tmp.name, index=False)
        return tmp.name

    _export_file_out = gr.File(label="Attribution Report CSV", visible=False)
    export_csv_btn.click(
        fn=export_report,
        inputs=[start_date_input, end_date_input],
        outputs=[_export_file_out],
    )

    return oas_chart, oad_chart, yield_chart, eve_chart
