"""
What-If Sandbox UI — Workflow 2.

Three-panel layout: Base | Delta | Modified
Allows users to tweak pool characteristics and see analytics impact in real time.
"""
from __future__ import annotations

from datetime import date

import gradio as gr
import pandas as pd


def _build_pool_chars(pool_id, coupon, wac, wala, wam, loan_size, ltv, fico, pct_ca, pct_purchase, product_type):
    from analytics.prepay import PoolCharacteristics
    return PoolCharacteristics(
        coupon=coupon / 100.0,
        wac=wac / 100.0,
        wala=int(wala),
        wam=int(wam),
        loan_size=float(loan_size),
        ltv=float(ltv),
        fico=int(fico),
        pct_ca=float(pct_ca),
        pct_purchase=float(pct_purchase),
        product_type=str(product_type),
        pool_id=pool_id or "WHAT-IF",
        current_balance=1_000_000,
    )


def _run_analytics_for_chars(pool_id, pool_chars, price, cpr_override=None, psa_override=None):
    """Compute analytics for given characteristics."""
    from data.market_data import get_current_market_data
    from data.intex_client import MockIntexClient
    from analytics.rate_paths import generate_rate_paths
    from analytics.prepay import PrepayModel, project_prepay_speeds
    from analytics.cashflows import get_cash_flows
    from analytics.oas_solver import compute_analytics, solve_oas, price_from_oas

    market_data = get_current_market_data()
    rate_paths = generate_rate_paths(curve=market_data.sofr_curve, n_paths=64, seed=42)
    intex_client = MockIntexClient()
    prepay_model = PrepayModel()

    return compute_analytics(
        pool_id=pool_id or "WHAT-IF",
        pool_chars=pool_chars,
        market_price=float(price),
        settlement_date=date.today(),
        rate_paths=rate_paths,
        intex_client=intex_client,
        prepay_model=prepay_model,
    )


def _format_analytics(a) -> dict:
    if a is None:
        return {}
    return {
        "OAS (bps)": round(a.oas, 2),
        "Z-Spread (bps)": round(a.z_spread, 2),
        "OAD (yrs)": round(a.oad, 3),
        "Mod Duration (yrs)": round(a.mod_duration, 3),
        "Convexity": round(a.convexity, 4),
        "Yield (%)": round(a.yield_, 4),
        "Model CPR (%)": round(a.model_cpr, 2),
        "Model Price": round(a.model_price, 4),
    }


def _compute_delta(base: dict, modified: dict) -> dict:
    delta = {}
    for k in base:
        try:
            b, m = float(base[k]), float(modified[k])
            d = m - b
            delta[k] = round(d, 4)
        except Exception:
            delta[k] = "N/A"
    return delta


def _fmt_analytics_html(data: dict) -> str:
    """Render analytics dict as a compact HTML table."""
    if not data:
        return "<div style='color:#64748B;padding:8px;font-size:12px;'>No data.</div>"
    if "error" in data:
        return f"<div style='color:#E5484D;padding:8px;font-size:12px;'>Error: {data['error']}</div>"
    rows = "".join(
        f"<tr>"
        f"<td style='color:#64748B;padding:4px 8px;font-size:12px;width:55%;font-family:DM Sans,sans-serif;'>{k}</td>"
        f"<td style='font-family:JetBrains Mono,monospace;color:#0F172A;padding:4px 8px;font-size:12px;text-align:right;'>{v}</td>"
        f"</tr>"
        for k, v in data.items()
    )
    return f"<table style='width:100%;border-collapse:collapse;'><tbody>{rows}</tbody></table>"


def _fmt_delta_html(delta: dict) -> str:
    """Render delta dict with green/red coloring."""
    rows = ""
    for k, v in delta.items():
        if v == "N/A":
            col = "#64748B"
            txt = "N/A"
        else:
            fv = float(v)
            col = "#059669" if fv > 0 else ("#E5484D" if fv < 0 else "#64748B")
            txt = f"{fv:+.4f}"
        rows += (
            f"<tr>"
            f"<td style='color:#64748B;padding:4px 8px;font-size:12px;width:55%;font-family:DM Sans,sans-serif;'>{k}</td>"
            f"<td style='font-family:JetBrains Mono,monospace;color:{col};padding:4px 8px;font-size:12px;text-align:right;'>{txt}</td>"
            f"</tr>"
        )
    if not rows:
        return "<div style='color:#64748B;padding:8px;font-size:12px;'>No delta data.</div>"
    return f"<table style='width:100%;border-collapse:collapse;'><tbody>{rows}</tbody></table>"


def create_whatif_sandbox_tab(shared_state: gr.State):
    """Build the What-If Sandbox tab."""

    with gr.Column():

        # Pool selection
        with gr.Row():
            pool_id_input = gr.Textbox(
                label="Pool ID",
                value="TEST-POOL-30YR",
                placeholder="Enter pool ID...",
            )
            load_pool_btn = gr.Button("Load Pool", variant="secondary")

        with gr.Row():
            # ---- Base Column ----
            with gr.Column(scale=1):
                gr.HTML("<div class='section-hdr'>Base</div>")
                base_price = gr.Number(label="Price (%par)", value=101.5, precision=4)
                with gr.Accordion("Pool Characteristics", open=True):
                    base_coupon = gr.Number(label="Coupon %", value=6.0, precision=3)
                    base_wac = gr.Number(label="WAC %", value=6.5, precision=3)
                    base_product = gr.Dropdown(
                        choices=["CC30", "CC15", "GN30", "GN15"],
                        value="CC30",
                        label="Product Type",
                    )
                    base_wala = gr.Number(label="WALA (months)", value=12, precision=0)
                    base_wam = gr.Number(label="WAM (months)", value=348, precision=0)
                    base_loan_size = gr.Number(label="Loan Size ($)", value=400_000, precision=0)
                    base_ltv = gr.Number(label="LTV", value=0.75, precision=3)
                    base_fico = gr.Number(label="FICO", value=750, precision=0)
                    base_pct_ca = gr.Number(label="% California", value=0.15, precision=3)
                    base_pct_purchase = gr.Number(label="% Purchase", value=0.65, precision=3)
                    base_cpr_override = gr.Number(
                        label="CPR Override (% or blank)",
                        value=None,
                        precision=1,
                    )

            # ---- Delta Column ----
            with gr.Column(scale=1):
                gr.HTML("<div class='section-hdr'>Delta (Modified − Base)</div>")
                delta_display = gr.HTML(
                    value="<div style='color:#64748B;padding:8px;font-size:12px;'>Compute to see delta.</div>"
                )

            # ---- Modified Column ----
            with gr.Column(scale=1):
                gr.HTML("<div class='section-hdr'>Modified</div>")
                mod_price = gr.Number(label="Price (%par)", value=101.5, precision=4)
                with gr.Accordion("Pool Characteristics", open=True):
                    mod_coupon = gr.Number(label="Coupon %", value=6.0, precision=3)
                    mod_wac = gr.Number(label="WAC %", value=6.5, precision=3)
                    mod_product = gr.Dropdown(
                        choices=["CC30", "CC15", "GN30", "GN15"],
                        value="CC30",
                        label="Product Type",
                    )
                    mod_wala = gr.Number(label="WALA (months)", value=12, precision=0)
                    mod_wam = gr.Number(label="WAM (months)", value=348, precision=0)
                    mod_loan_size = gr.Number(label="Loan Size ($)", value=400_000, precision=0)
                    mod_ltv = gr.Number(label="LTV", value=0.75, precision=3)
                    mod_fico = gr.Number(label="FICO", value=750, precision=0)
                    mod_pct_ca = gr.Number(label="% California", value=0.15, precision=3)
                    mod_pct_purchase = gr.Number(label="% Purchase", value=0.65, precision=3)
                    mod_cpr_override = gr.Number(
                        label="CPR Override (% or blank)",
                        value=None,
                        precision=1,
                    )

        with gr.Row():
            compute_btn = gr.Button("Compute What-If", variant="primary")
            reset_btn = gr.Button("Reset to Base")
            save_scenario_btn = gr.Button("Save Scenario")

        # ---- Base Analytics ----
        with gr.Row():
            with gr.Column():
                gr.HTML("<div class='section-hdr'>Base Analytics</div>")
                base_analytics_json = gr.HTML(
                    value="<div style='color:#64748B;padding:8px;font-size:12px;'>Compute to see base analytics.</div>"
                )
            with gr.Column():
                gr.HTML("<div class='section-hdr'>Modified Analytics</div>")
                mod_analytics_json = gr.HTML(
                    value="<div style='color:#64748B;padding:8px;font-size:12px;'>Compute to see modified analytics.</div>"
                )

        # ---- Rate Shock Comparison ----
        gr.HTML("<div class='section-hdr' style='margin-top:12px;'>Rate Shock Comparison</div>")
        shock_comparison_table = gr.DataFrame(
            label="Scenario Comparison (Base vs Modified)",
            interactive=False,
        )
        run_scenarios_btn = gr.Button("Run Rate Scenarios", variant="secondary")

        # ---- Saved Scenarios ----
        gr.HTML("<div class='section-hdr' style='margin-top:12px;'>Saved Scenarios</div>")
        saved_scenario_name = gr.Textbox(label="Scenario Name", placeholder="Scenario 1...")
        saved_scenarios_dropdown = gr.Dropdown(label="Load Scenario", choices=[], allow_custom_value=True)

    # ---- Event Handlers ----
    _saved_scenarios = {}

    def load_pool(pool_id, state):
        """Load pool characteristics from universe."""
        from data.pool_universe import get_pool_universe
        universe = get_pool_universe()
        row = universe[universe["pool_id"] == pool_id]
        if row.empty:
            return (
                101.5, 6.0, 6.5, "CC30", 12, 348, 400_000, 0.75, 750, 0.15, 0.65,
                101.5, 6.0, 6.5, "CC30", 12, 348, 400_000, 0.75, 750, 0.15, 0.65,
            )
        r = row.iloc[0]
        c = float(r["coupon"]) * 100
        w = float(r["wac"]) * 100
        vals = (
            float(r["market_price"]), c, w, str(r["product_type"]),
            int(r["wala"]), int(r["wam"]),
            float(r["loan_size"]), float(r["ltv"]),
            int(r["fico"]), float(r["pct_ca"]), float(r["pct_purchase"]),
        )
        return vals + vals  # base and modified start the same

    load_pool_btn.click(
        fn=load_pool,
        inputs=[pool_id_input, shared_state],
        outputs=[
            base_price, base_coupon, base_wac, base_product,
            base_wala, base_wam, base_loan_size, base_ltv,
            base_fico, base_pct_ca, base_pct_purchase,
            mod_price, mod_coupon, mod_wac, mod_product,
            mod_wala, mod_wam, mod_loan_size, mod_ltv,
            mod_fico, mod_pct_ca, mod_pct_purchase,
        ],
    )

    def compute_whatif(
        pool_id,
        bp, bc, bwac, bprod, bwala, bwam, bls, bltv, bfico, bpca, bppurch, bcpr,
        mp, mc, mwac, mprod, mwala, mwam, mls, mltv, mfico, mpca, mppurch, mcpr,
    ):
        """Compute base and modified analytics."""
        try:
            base_chars = _build_pool_chars(
                pool_id, bc, bwac, bwala, bwam, bls, bltv, bfico, bpca, bppurch, bprod
            )
            mod_chars = _build_pool_chars(
                pool_id, mc, mwac, mwala, mwam, mls, mltv, mfico, mpca, mppurch, mprod
            )

            cpr_b = float(bcpr) / 100.0 if bcpr else None
            cpr_m = float(mcpr) / 100.0 if mcpr else None

            base_a = _run_analytics_for_chars(pool_id, base_chars, bp, cpr_b)
            mod_a = _run_analytics_for_chars(pool_id, mod_chars, mp, cpr_m)

            base_fmt = _format_analytics(base_a)
            mod_fmt = _format_analytics(mod_a)
            delta_fmt = _compute_delta(base_fmt, mod_fmt)

            return _fmt_analytics_html(base_fmt), _fmt_analytics_html(mod_fmt), _fmt_delta_html(delta_fmt)
        except Exception as e:
            err_html = _fmt_analytics_html({"error": str(e)})
            return err_html, err_html, err_html

    compute_btn.click(
        fn=compute_whatif,
        inputs=[
            pool_id_input,
            base_price, base_coupon, base_wac, base_product,
            base_wala, base_wam, base_loan_size, base_ltv,
            base_fico, base_pct_ca, base_pct_purchase, base_cpr_override,
            mod_price, mod_coupon, mod_wac, mod_product,
            mod_wala, mod_wam, mod_loan_size, mod_ltv,
            mod_fico, mod_pct_ca, mod_pct_purchase, mod_cpr_override,
        ],
        outputs=[base_analytics_json, mod_analytics_json, delta_display],
    )

    def reset_to_base(
        bp, bc, bwac, bprod, bwala, bwam, bls, bltv, bfico, bpca, bppurch
    ):
        return bp, bc, bwac, bprod, bwala, bwam, bls, bltv, bfico, bpca, bppurch

    reset_btn.click(
        fn=reset_to_base,
        inputs=[
            base_price, base_coupon, base_wac, base_product,
            base_wala, base_wam, base_loan_size, base_ltv,
            base_fico, base_pct_ca, base_pct_purchase,
        ],
        outputs=[
            mod_price, mod_coupon, mod_wac, mod_product,
            mod_wala, mod_wam, mod_loan_size, mod_ltv,
            mod_fico, mod_pct_ca, mod_pct_purchase,
        ],
    )

    def run_rate_scenarios(
        pool_id,
        bp, bc, bwac, bprod, bwala, bwam, bls, bltv, bfico, bpca, bppurch,
        mp, mc, mwac, mprod, mwala, mwam, mls, mltv, mfico, mpca, mppurch,
    ):
        """Run rate scenarios for base and modified pool."""
        from analytics.scenarios import run_scenarios, STANDARD_SCENARIOS
        from data.market_data import get_current_market_data
        from data.intex_client import MockIntexClient
        from analytics.prepay import PrepayModel

        base_chars = _build_pool_chars(
            pool_id, bc, bwac, bwala, bwam, bls, bltv, bfico, bpca, bppurch, bprod
        )
        mod_chars = _build_pool_chars(
            pool_id, mc, mwac, mwala, mwam, mls, mltv, mfico, mpca, mppurch, mprod
        )

        market_data = get_current_market_data()

        base_results = run_scenarios(
            pool_id=pool_id or "BASE",
            pool_chars=base_chars,
            market_price=bp,
            settlement_date=date.today(),
            base_curve=market_data.sofr_curve,
            n_paths=32,
            intex_client=MockIntexClient(),
            prepay_model=PrepayModel(),
        )

        mod_results = run_scenarios(
            pool_id=(pool_id or "MOD") + "_mod",
            pool_chars=mod_chars,
            market_price=mp,
            settlement_date=date.today(),
            base_curve=market_data.sofr_curve,
            n_paths=32,
            intex_client=MockIntexClient(),
            prepay_model=PrepayModel(),
        )

        rows = []
        for name in base_results:
            br = base_results[name]
            mr = mod_results.get(name)
            row = {
                "Scenario": name,
                "Base OAS": round(br.analytics.oas, 1),
                "Base OAD": round(br.analytics.oad, 2),
                "Base Price Δ": round(br.price_delta, 4),
                "Mod OAS": round(mr.analytics.oas, 1) if mr else "N/A",
                "Mod OAD": round(mr.analytics.oad, 2) if mr else "N/A",
                "Mod Price Δ": round(mr.price_delta, 4) if mr else "N/A",
            }
            rows.append(row)

        return pd.DataFrame(rows)

    run_scenarios_btn.click(
        fn=run_rate_scenarios,
        inputs=[
            pool_id_input,
            base_price, base_coupon, base_wac, base_product,
            base_wala, base_wam, base_loan_size, base_ltv,
            base_fico, base_pct_ca, base_pct_purchase,
            mod_price, mod_coupon, mod_wac, mod_product,
            mod_wala, mod_wam, mod_loan_size, mod_ltv,
            mod_fico, mod_pct_ca, mod_pct_purchase,
        ],
        outputs=[shock_comparison_table],
    )

    # Load from shared state (when "Send to What-If" is clicked)
    def sync_from_state(state):
        if state and "selected_pool_id" in state:
            return state["selected_pool_id"]
        return gr.update()

    shared_state.change(
        fn=sync_from_state,
        inputs=[shared_state],
        outputs=[pool_id_input],
    )

    return base_analytics_json, mod_analytics_json, delta_display
