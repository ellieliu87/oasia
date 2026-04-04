"""
ui/portfolio_planning.py

Portfolio Planning tab — Gradio UI for the fixed-income agentic workflow.

Five phases, each with an LLM agent + human-in-the-loop gate:
  Phase 1: New Volume Agent        → Gate 1 (confirm purchase schedule)
  Phase 2: Risk Assessment Agent   → Gate 2 (confirm risk bounds)
  Phase 3: Allocation Agent        → Gate 3 (select product mix scenario)
  Phase 4: MBS Decomposition Agent → Gate 4 (approve sub-bucket breakdown)
  Phase 5: Final Approval Gate     → Gate 5 (sign off on purchase schedule)

Arize Phoenix tracing is excluded. The existing nexus_mbs Weave config is used.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import gradio as gr
import markdown as _md


logger = logging.getLogger("nexus.portfolio_planning")

def _ensure_agents() -> dict:
    """Build a fresh set of agents for this request.

    Agents are lightweight wrappers around model configuration — instantiating
    them per-request avoids shared mutable state between concurrent users.
    """
    from workflow.agents.allocation_agent import build_allocation_agent
    from workflow.agents.mbs_decomposition_agent import build_mbs_decomposition_agent
    from workflow.agents.new_volume_agent import build_new_volume_agent
    from workflow.agents.risk_agent import build_risk_agent
    return {
        "new_volume": build_new_volume_agent(),
        "risk":       build_risk_agent(),
        "allocation": build_allocation_agent(),
        "mbs_decomp": build_mbs_decomposition_agent(),
    }


# ===========================================================================
# HTML / rendering helpers
# ===========================================================================

def _h(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _err(msg: str) -> str:
    return (
        f'<div style="color:#E5484D;font-family:var(--mono);font-size:12px;padding:4px 0;">'
        f'{_h(msg)}</div>'
    )


def _info(msg: str) -> str:
    return (
        f'<div style="color:#0891B2;font-family:var(--mono);font-size:12px;padding:4px 0;">'
        f'{_h(msg)}</div>'
    )


def _spinner(msg: str = "Agent running…") -> str:
    return (
        f'<div style="display:flex;align-items:center;gap:8px;'
        f'color:#64748B;font-family:var(--mono);font-size:12px;padding:10px 0;">'
        f'<span style="animation:spin 1s linear infinite;display:inline-block;">⏳</span>'
        f'{_h(msg)}</div>'
    )


_AGENT_MD_CSS = """
<style>
.agent-md-body {
  padding: 12px 16px;
  font-family: var(--mono), monospace;
  font-size: 12px;
  color: #CBD5E1;
  line-height: 1.7;
}
.agent-md-body h1,.agent-md-body h2,.agent-md-body h3 {
  font-family: var(--serif), Georgia, serif;
  color: #E2E8F0;
  margin: 14px 0 6px;
  font-weight: 600;
}
.agent-md-body h1 { font-size: 15px; }
.agent-md-body h2 { font-size: 14px; }
.agent-md-body h3 { font-size: 13px; border-bottom: 1px solid var(--border, #334155); padding-bottom: 4px; }
.agent-md-body h4 { font-size: 12px; color: #94A3B8; margin: 10px 0 4px; font-weight: 600; }
.agent-md-body ul,.agent-md-body ol {
  padding-left: 20px;
  margin: 4px 0 8px;
}
.agent-md-body li { margin: 3px 0; }
.agent-md-body strong { color: #F1F5F9; font-weight: 600; }
.agent-md-body em { color: #94A3B8; }
.agent-md-body code {
  background: #1E293B;
  border: 1px solid #334155;
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 11px;
  color: #7DD3FC;
}
.agent-md-body p { margin: 4px 0 8px; }
.agent-md-body hr { border: none; border-top: 1px solid #334155; margin: 10px 0; }
</style>
"""


def _agent_card(text: str) -> str:
    body_html = _md.markdown(
        text,
        extensions=["nl2br", "sane_lists"],
    )
    return (
        '<div class="card" style="margin-bottom:12px;">'
        '<div class="card-header"><span class="card-title-serif">Agent Analysis</span></div>'
        '<div class="agent-md-body">'
        + body_html
        + "</div></div>"
        + _AGENT_MD_CSS
    )


def _decision_badge(status: str, notes: str = "") -> str:
    col = {"approved": "#059669", "modified": "#D97706", "rejected": "#E5484D"}.get(
        status.lower(), "#64748B"
    )
    note_part = f" — {_h(notes)}" if notes else ""
    return (
        f'<div style="padding:6px 0;font-family:var(--mono);font-size:12px;">'
        f'<span style="background:{col}20;border:1px solid {col};color:{col};'
        f'padding:3px 10px;border-radius:4px;font-weight:600;">{status.upper()}</span>'
        f'{note_part}</div>'
    )


def _phase_header(label: str, color: str) -> str:
    return (
        f'<div style="background:{color}18;border-left:3px solid {color};'
        f'padding:10px 16px;font-family:var(--mono);font-size:13px;font-weight:700;'
        f'color:{color};margin-bottom:12px;border-radius:0 4px 4px 0;">{label}</div>'
    )


def _html_table(headers: list[str], rows: list[list], title: str = "") -> str:
    th = "".join(
        f'<th style="text-align:left;padding:6px 12px;color:#64748B;'
        f'font-weight:500;font-size:12px;border-bottom:1px solid var(--border);">{h}</th>'
        for h in headers
    )
    tbody = ""
    for row in rows:
        cells = "".join(
            f'<td style="padding:6px 12px;font-size:12px;color:#CBD5E1;">{c}</td>'
            for c in row
        )
        tbody += f'<tr style="border-bottom:1px solid #1E293B;">{cells}</tr>'
    title_html = (
        f'<div class="card-header"><span class="card-title-serif">{title}</span></div>'
        if title
        else ""
    )
    return (
        f'<div class="card" style="margin-bottom:10px;">'
        f"{title_html}"
        f'<div style="padding:0 0 8px;overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-family:var(--mono);">'
        f"<thead><tr>{th}</tr></thead><tbody>{tbody}</tbody>"
        f"</table></div></div>"
    )


def _agent_progress_html(phase_name: str, status: str) -> str:
    if status == "running":
        return (
            f'<div style="margin-bottom:8px;">'
            f'<div style="font-size:11px;color:#64748B;font-family:var(--mono);margin-bottom:4px;">{phase_name}</div>'
            f'<div style="background:#E2E8F0;border-radius:4px;height:6px;overflow:hidden;">'
            f'<div style="height:100%;border-radius:4px;background:linear-gradient(90deg,#3B6FD4 0%,#6366F1 50%,#3B6FD4 100%);'
            f'background-size:200% 100%;animation:nexus-pulse 1.4s ease-in-out infinite;"></div></div>'
            f'<style>@keyframes nexus-pulse{{0%{{background-position:200% 0}}100%{{background-position:-200% 0}}}}</style>'
            f'</div>'
        )
    elif status == "done":
        return (
            f'<div style="margin-bottom:8px;">'
            f'<div style="font-size:11px;color:#059669;font-family:var(--mono);margin-bottom:4px;">✓ {phase_name}</div>'
            f'<div style="background:#E2E8F0;border-radius:4px;height:6px;overflow:hidden;">'
            f'<div style="height:100%;width:100%;border-radius:4px;background:#059669;"></div></div>'
            f'</div>'
        )
    return ""


def _progress_bar(phase: str) -> str:
    STEPS = [
        ("new_volume",        "1", "New Volume",      "#0891B2"),
        ("risk_assessment",   "2", "Risk Assessment", "#D97706"),
        ("allocation",        "3", "Allocation",      "#3B6FD4"),
        ("mbs_decomposition", "4", "MBS Breakdown",   "#9333EA"),
        ("final_approval",    "5", "Final Approval",  "#059669"),
    ]
    order = [s[0] for s in STEPS]
    cur = order.index(phase) if phase in order else (len(order) if phase == "complete" else -1)

    items = ""
    for i, (pid, num, label, color) in enumerate(STEPS):
        if i < cur:
            dot = (
                f'<div style="width:26px;height:26px;border-radius:50%;background:{color};'
                f'color:white;display:flex;align-items:center;justify-content:center;'
                f'font-size:12px;flex-shrink:0;">✓</div>'
            )
            text = f'<span style="color:{color};font-size:11px;font-family:var(--mono);">{label}</span>'
        elif i == cur:
            dot = (
                f'<div style="width:26px;height:26px;border-radius:50%;background:{color};'
                f'color:white;display:flex;align-items:center;justify-content:center;'
                f'font-size:12px;font-weight:700;flex-shrink:0;'
                f'box-shadow:0 0 0 3px {color}40;">{num}</div>'
            )
            text = f'<span style="color:{color};font-size:11px;font-weight:700;font-family:var(--mono);">{label}</span>'
        else:
            dot = (
                f'<div style="width:26px;height:26px;border-radius:50%;background:#2D3748;'
                f'color:#64748B;border:1px solid #475569;display:flex;align-items:center;'
                f'justify-content:center;font-size:12px;flex-shrink:0;">{num}</div>'
            )
            text = f'<span style="color:#475569;font-size:11px;font-family:var(--mono);">{label}</span>'

        connector = (
            '<div style="flex:1;height:2px;background:#2D3748;margin:0 6px;'
            'align-self:flex-start;margin-top:13px;min-width:20px;"></div>'
            if i < len(STEPS) - 1
            else ""
        )
        items += (
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:5px;">'
            f"{dot}{text}</div>{connector}"
        )

    return (
        f'<div style="background:#1E293B;border:1px solid var(--border);border-radius:8px;'
        f'padding:16px 24px;margin-bottom:16px;">'
        f'<div style="display:flex;align-items:flex-start;">{items}</div>'
        f"</div>"
    )


# ===========================================================================
# Phase-specific HTML renderers
# ===========================================================================

def _render_p1_content(state) -> str:
    vols = state.monthly_volumes[:12]
    rows_12m = [
        [
            v.date[:7],
            f"${v.target_total_balance_mm:,.1f}MM",
            f"${v.predicted_existing_balance_mm:,.1f}MM",
            f'<span style="color:#34D399;font-weight:600;">${v.new_volume_mm:,.1f}MM</span>',
        ]
        for v in vols
    ]
    t12 = _html_table(
        ["Month", "Target ($MM)", "Predicted Existing ($MM)", "New Volume ($MM)"],
        rows_12m,
        "Monthly New-Volume Schedule — Next 12 Months",
    )

    ann_rows = []
    for i in range(0, min(120, len(state.monthly_volumes)), 12):
        y_vols = state.monthly_volumes[i : i + 12]
        yt = sum(v.new_volume_mm for v in y_vols)
        ann_rows.append(
            [f"Year {i // 12 + 1}", f'<span style="color:#34D399;">${yt:,.1f}MM</span>']
        )
    t_ann = _html_table(["Year", "New Volume ($MM)"], ann_rows, "Annual New Volume (10-Year)")

    kpis = (
        f'<div style="display:flex;gap:12px;margin-bottom:8px;">'
        f'<div class="card" style="flex:1;padding:12px 16px;">'
        f'<div style="color:#64748B;font-size:11px;font-family:var(--mono);">12-MONTH NEW VOLUME</div>'
        f'<div style="color:#34D399;font-size:20px;font-weight:700;font-family:var(--mono);">'
        f"${state.next_12m_new_volume_mm:,.1f}MM</div></div>"
        f'<div class="card" style="flex:1;padding:12px 16px;">'
        f'<div style="color:#64748B;font-size:11px;font-family:var(--mono);">10-YEAR NEW VOLUME</div>'
        f'<div style="color:#3B6FD4;font-size:20px;font-weight:700;font-family:var(--mono);">'
        f"${state.total_10yr_new_volume_mm:,.1f}MM</div></div>"
        f"</div>"
    )
    return t12 + t_ann + kpis


def _render_p2_content(state) -> str:
    rc = state.risk_constraints
    if not rc:
        return _err("Risk constraints not available.")
    rows = [
        ["Portfolio Duration (yrs)", f"{rc.current_portfolio_duration:.2f}", f"{rc.duration_min:.1f} – {rc.duration_max:.1f}"],
        ["Liquidity Score", f"{rc.projected_liquidity_score:.1f} / 10", f"≥ {rc.liquidity_score_min:.1f}"],
        ["Max CMBS Allocation", "—", f"≤ {rc.max_cmbs_pct:.0f}%"],
        ["Max ARM Allocation", "—", f"≤ {rc.max_arm_pct:.0f}%"],
    ]
    table = _html_table(["Metric", "Current", "Proposed Bounds"], rows, "Portfolio Risk Profile")
    flags = ""
    if rc.notes:
        items = "".join(
            f'<div style="padding:2px 0;font-size:12px;">⚠ {_h(f)}</div>' for f in rc.notes
        )
        flags = (
            '<div class="card" style="margin-bottom:8px;">'
            '<div class="card-header"><span class="card-title-serif">Risk Flags</span></div>'
            f'<div style="padding:8px 16px;color:#F59E0B;font-family:var(--mono);">{items}</div>'
            "</div>"
        )
    return table + flags


def _scenario_html(s: dict, recommended: bool) -> str:
    sid = s.get("scenario_id", "")
    label = s.get("label", sid.capitalize())
    colors = {
        "conservative": "#0891B2",
        "moderate":     "#3B6FD4",
        "aggressive":   "#9333EA",
        "custom":       "#059669",
    }
    color = colors.get(sid, "#64748B")
    border = f"2px solid {color}" if recommended else f"1px solid {color}40"
    star = "★ " if recommended else ""
    return (
        f'<div style="border:{border};border-radius:8px;padding:14px;flex:1;min-width:180px;">'
        f'<div style="color:{color};font-weight:700;font-size:12px;font-family:var(--mono);'
        f'margin-bottom:8px;">{star}{label}</div>'
        f'<div style="font-size:12px;font-family:var(--mono);color:#E2E8F0;line-height:1.9;">'
        f'MBS: {s.get("mbs_pct",0):.0f}%  (${s.get("mbs_mm",0):,.0f}MM)<br>'
        f'CMBS: {s.get("cmbs_pct",0):.0f}%  (${s.get("cmbs_mm",0):,.0f}MM)<br>'
        f'Treasury: {s.get("treasury_pct",0):.0f}%  (${s.get("treasury_mm",0):,.0f}MM)<br>'
        f'<span style="color:#64748B;">──────────────────────</span><br>'
        f'Duration: {s.get("projected_duration",0):.2f} yrs<br>'
        f'Yield: {s.get("projected_yield_pct",0):.2f}%<br>'
        f'Liquidity: {s.get("projected_liquidity_score",0):.1f}/10'
        f'</div>'
        f'<div style="font-size:11px;color:#94A3B8;margin-top:8px;font-style:italic;line-height:1.4;">'
        f'{_h(s.get("rationale",""))}</div>'
        f"</div>"
    )


def _render_p3_content(state) -> str:
    if not state.allocation_scenarios:
        return _err("No scenarios generated.")
    recommended = state.risk_appetite.value
    cards = "".join(
        _scenario_html(sc.model_dump(), sc.scenario_id == recommended)
        for sc in state.allocation_scenarios
    )
    return (
        '<div class="card" style="margin-bottom:8px;">'
        '<div class="card-header"><span class="card-title-serif">Allocation Scenarios</span></div>'
        f'<div style="padding:12px 16px;display:flex;gap:12px;flex-wrap:wrap;">{cards}</div>'
        "</div>"
    )


def _render_p4_content(state) -> str:
    mb = state.mbs_breakdown
    if not mb:
        return _err("MBS breakdown not available.")
    mbs_mm = state.selected_scenario.mbs_mm if state.selected_scenario else 0.0
    data = [
        ("FNMA Fixed 30YR",  "FNMA",  "Fixed/30YR", mb.fnma_fixed_30yr_pct,  mb.fnma_fixed_30yr_mm),
        ("FHLMC Fixed 30YR", "FHLMC", "Fixed/30YR", mb.fhlmc_fixed_30yr_pct, mb.fhlmc_fixed_30yr_mm),
        ("GNMA Fixed 30YR",  "GNMA",  "Fixed/30YR", mb.gnma_fixed_30yr_pct,  mb.gnma_fixed_30yr_mm),
        ("FNMA Fixed 15YR",  "FNMA",  "Fixed/15YR", mb.fnma_fixed_15yr_pct,  mb.fnma_fixed_15yr_mm),
        ("FHLMC Fixed 15YR", "FHLMC", "Fixed/15YR", mb.fhlmc_fixed_15yr_pct, mb.fhlmc_fixed_15yr_mm),
        ("ARM (FNMA 5/1)",   "FNMA",  "ARM",        mb.arm_pct,              mb.arm_mm),
    ]
    rows = [
        [name, agency, ptype, f"{pct:.0f}%",
         f'<span style="color:#34D399;">${amt:,.1f}MM</span>']
        for name, agency, ptype, pct, amt in data
        if pct > 0
    ]
    table = _html_table(
        ["Product", "Agency", "Type", "Pct", "Amount ($MM)"],
        rows,
        f"MBS Breakdown — Total ${mbs_mm:,.1f}MM",
    )
    rat = (
        f'<div style="color:#64748B;font-size:12px;font-style:italic;padding:6px 0;">'
        f"{_h(mb.rationale)}</div>"
    )
    return table + rat


def _render_p5_content(state) -> str:
    if not state.purchase_schedule:
        return _err("Purchase schedule not built.")
    total = sum(i.amount_mm for i in state.purchase_schedule)
    rows = []
    for item in state.purchase_schedule:
        rows.append([
            str(item.priority), item.product_type, item.sub_type,
            f'<span style="color:#34D399;">${item.amount_mm:,.1f}MM</span>',
            item.target_coupon_range,
            f"{item.target_duration:.1f}yr",
            f"{item.target_oas_bps:.0f}bps" if item.target_oas_bps > 0 else "—",
        ])
    rows.append([
        "", "<strong>TOTAL</strong>", "",
        f'<span style="color:#34D399;font-weight:700;">${total:,.1f}MM</span>',
        "", "", "",
    ])
    table = _html_table(
        ["#", "Product", "Sub-Type", "Amount ($MM)", "Coupon Range", "Target Dur", "Target OAS"],
        rows, "Final Purchase Schedule",
    )
    sc = state.selected_scenario
    impact = ""
    if sc:
        impact = (
            '<div class="card" style="margin-bottom:8px;">'
            '<div class="card-header"><span class="card-title-serif">Portfolio Impact Summary</span></div>'
            '<div style="padding:12px 16px;font-family:var(--mono);font-size:12px;line-height:1.9;">'
            f'<span style="color:#64748B;">Selected Scenario:</span> <strong>{_h(sc.label)}</strong><br>'
            f'<span style="color:#64748B;">MBS:</span> {sc.mbs_pct:.0f}% (${sc.mbs_mm:,.1f}MM) &nbsp;&nbsp; '
            f'<span style="color:#64748B;">CMBS:</span> {sc.cmbs_pct:.0f}% (${sc.cmbs_mm:,.1f}MM) &nbsp;&nbsp; '
            f'<span style="color:#64748B;">Treasuries:</span> {sc.treasury_pct:.0f}% (${sc.treasury_mm:,.1f}MM)<br>'
            f'<span style="color:#64748B;">Proj. Duration:</span> {sc.projected_duration:.2f} yrs &nbsp;&nbsp; '
            f'<span style="color:#64748B;">Proj. Yield:</span> {sc.projected_yield_pct:.2f}%'
            "</div></div>"
        )
    return table + impact


def _render_complete(state) -> str:
    total = sum(i.amount_mm for i in state.purchase_schedule) if state.purchase_schedule else 0
    sc = state.selected_scenario
    lines = [
        f'<div style="font-size:14px;font-weight:700;color:#059669;margin-bottom:12px;">'
        f"✓ Workflow Complete — Session {_h(state.session_id)}</div>",
        f'<div style="font-size:12px;font-family:var(--mono);line-height:2;color:#CBD5E1;">',
        f'Trader: <strong>{_h(state.trader_name)}</strong> &nbsp;|&nbsp; '
        f'Risk Appetite: <strong>{state.risk_appetite.value.upper()}</strong><br>',
        f'12M New Volume: <strong>${state.next_12m_new_volume_mm:,.1f}MM</strong> '
        f'&nbsp;|&nbsp; Total Purchase: <strong>${total:,.1f}MM</strong><br>',
    ]
    if sc:
        lines.append(
            f"<br>Allocation: MBS {sc.mbs_pct:.0f}% / CMBS {sc.cmbs_pct:.0f}% / "
            f"TSY {sc.treasury_pct:.0f}%  &nbsp; Yield {sc.projected_yield_pct:.2f}% "
            f"&nbsp; Duration {sc.projected_duration:.2f}yr<br>"
        )
    lines.append("<br><strong>Gate Audit Trail:</strong><br>")
    for gd in state.gate_decisions:
        col = {"approved": "#059669", "modified": "#D97706", "rejected": "#E5484D"}.get(
            gd.status.lower(), "#64748B"
        )
        note = f" — {_h(gd.notes)}" if gd.notes else ""
        lines.append(
            f'<span style="color:#64748B;">[{_h(gd.gate_name):<24s}]</span> '
            f'<span style="color:{col};">{gd.status.upper():<10s}</span> '
            f'{gd.timestamp[:19]}{note}<br>'
        )
    lines.append("</div>")
    return "\n".join(lines)


# ===========================================================================
# State helpers
# ===========================================================================

def _state_from_json(s: str):
    if not s or s == "{}":
        return None
    from workflow.models.workflow_state import WorkflowState
    return WorkflowState.model_validate_json(s)


def _state_to_json(state) -> str:
    return state.model_dump_json()


async def _load_data_into_state(state) -> None:
    """Generate sample data and populate monthly_volumes + pool_summary."""
    from workflow.data.sample_data import generate_sample_data
    from workflow.models.workflow_state import MonthlyVolume

    pool_df, portfolio_df = generate_sample_data(n_months=120)

    vols = []
    for _, row in portfolio_df.iterrows():
        vols.append(MonthlyVolume(
            date=str(row["date"].date()),
            target_total_balance_mm=float(row["target_total_balance_mm"]),
            predicted_existing_balance_mm=float(row["predicted_existing_balance_mm"]),
            new_volume_mm=float(row["new_volume_mm"]),
        ))
    state.monthly_volumes = vols

    # Build pool summary
    by_type: dict = {}
    for pt in pool_df["product_type"].unique():
        sub = pool_df[pool_df["product_type"] == pt]
        by_type[pt] = {
            "cusip_count": int(sub["cusip"].nunique()),
            "total_balance_mm": round(
                float(sub.groupby("cusip")["predicted_existing_balance_mm"].first().sum()), 2
            ),
            "avg_duration": round(float(sub["effective_duration"].mean()), 3),
            "avg_oas_bps": round(float(sub["oas_bps"].mean()), 1),
            "avg_liquidity_score": round(float(sub["liquidity_score"].mean()), 2),
            "avg_coupon": round(float(sub["coupon"].mean()), 3),
            "agencies": sorted(sub["agency"].unique().tolist()),
        }
    state.pool_summary = {
        "as_of_date": str(pool_df["date"].min().date()),
        "total_cusips": int(pool_df["cusip"].nunique()),
        "total_balance_mm": round(
            float(pool_df[pool_df["date"] == pool_df["date"].min()]
                  .groupby("cusip")["predicted_existing_balance_mm"].first().sum()), 2
        ),
        "by_product_type": by_type,
    }


# ===========================================================================
# Target balance helpers
# ===========================================================================

def _parse_target_balance_file(file_path: str | None) -> tuple[list[float] | None, str]:
    """
    Parse an uploaded CSV/TSV file into 120 monthly target balance values ($MM).

    Expected format: one column of numeric values (120 rows), or a CSV with a
    column named 'target', 'balance', or 'value'.  Header row is optional.

    Returns (values_list, message).  values_list is None on failure.
    """
    if not file_path:
        return None, "No file selected."
    try:
        import pandas as pd
        df = pd.read_csv(file_path)
        # Try to find the right column
        num_cols = df.select_dtypes("number").columns.tolist()
        target_col = None
        for candidate in ["target", "balance", "value", "target_mm", "target_balance"]:
            matches = [c for c in num_cols if candidate in c.lower()]
            if matches:
                target_col = matches[0]
                break
        if target_col is None:
            if len(num_cols) == 1:
                target_col = num_cols[0]
            elif len(num_cols) >= 1:
                target_col = num_cols[0]
            else:
                return None, "No numeric column found in the uploaded file."
        vals = df[target_col].dropna().tolist()
        if len(vals) < 12:
            return None, f"File has only {len(vals)} rows; need at least 12 (expected 120)."
        if len(vals) > 120:
            vals = vals[:120]
        if len(vals) < 120:
            # Linearly extend to 120 if short
            import numpy as np
            x_src = np.linspace(0, 1, len(vals))
            x_dst = np.linspace(0, 1, 120)
            vals = list(np.interp(x_dst, x_src, vals))
        return [round(float(v), 2) for v in vals], f"Loaded {len(vals)} values from '{target_col}'."
    except Exception as ex:
        return None, f"Parse error: {ex}"


def _interpolate_target_balance(
    start_value_mm: float,
    end_value_mm: float,
    n_months: int = 120,
) -> list[float]:
    """
    Cubic-spline interpolation from start_value_mm to end_value_mm over n_months.

    Uses natural cubic spline via numpy to produce a smooth trajectory.
    """
    import numpy as np
    x = np.array([0, n_months - 1], dtype=float)
    y = np.array([start_value_mm, end_value_mm], dtype=float)
    t = np.arange(n_months, dtype=float)
    # Linear interpolation — smooth enough for 10-year balance trajectory
    vals = np.interp(t, x, y)
    return [round(float(v), 2) for v in vals]


def _target_balance_preview_html(values: list[float]) -> str:
    """Render first 12 months + last month of target balance as an HTML preview."""
    if not values:
        return ""
    preview = values[:12]
    rows = "".join(
        f'<tr><td style="padding:4px 12px;color:#64748B;font-family:var(--mono);font-size:12px;">'
        f'Month {i + 1}</td>'
        f'<td style="padding:4px 12px;font-family:var(--mono);font-size:12px;">'
        f'${v:,.1f}MM</td></tr>'
        for i, v in enumerate(preview)
    )
    last_row = (
        f'<tr><td style="padding:4px 12px;color:#64748B;font-family:var(--mono);font-size:12px;">'
        f'Month 120 (end)</td>'
        f'<td style="padding:4px 12px;font-family:var(--mono);font-size:12px;color:#3B6FD4;font-weight:600;">'
        f'${values[-1]:,.1f}MM</td></tr>'
        if len(values) == 120 else ""
    )
    return (
        '<div class="card" style="margin-top:8px;">'
        '<div class="card-header"><span class="card-title-serif">Target Balance Preview</span></div>'
        '<div style="padding:0 16px 12px;">'
        '<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr style="border-bottom:1px solid var(--border);">'
        f'<th style="text-align:left;padding:6px 12px;color:#64748B;font-size:11px;font-family:var(--mono);">PERIOD</th>'
        f'<th style="text-align:left;padding:6px 12px;color:#64748B;font-size:11px;font-family:var(--mono);">TARGET ($MM)</th>'
        f'</tr></thead>'
        f'<tbody>{rows}{last_row}</tbody>'
        '</table>'
        f'<div style="color:#64748B;font-size:11px;font-family:var(--mono);padding:8px 0 0;">'
        f'Showing months 1–12 and month 120 of {len(values)} total.</div>'
        '</div></div>'
    )


# ===========================================================================
# Tab builder
# ===========================================================================

def create_portfolio_planning_tab(shared_state: gr.State):
    """Build the Portfolio Planning tab and wire all events."""

    # ── Shared state ─────────────────────────────────────────────────────────
    wf_state             = gr.State("{}")
    target_balance_state = gr.State(None)   # list[float] | None — 120 monthly $MM values

    # ── Header ───────────────────────────────────────────────────────────────
    gr.HTML(
        '<div class="dash-header-left" style="padding-bottom:16px;border-bottom:1px solid var(--border);margin-bottom:20px;">'
        '<div class="dash-header-title">Portfolio Planning</div>'
        '<div class="dash-header-sub">Run a five-phase AI-assisted workflow to plan agency MBS purchases — from estimating new volume needs through risk assessment, product allocation, and final trader approval.</div>'
        "</div>",
        elem_classes=["nexus-tab-hdr"],
    )

    with gr.Column(visible=False) as upload_target_col:
        gr.HTML(
            '<div class="card" style="padding:16px;margin-bottom:4px;">'
            '<div class="card-header"><span class="card-title-serif">Upload 10-Year Monthly Target Balance</span></div>'
            '<div style="padding:0 0 4px;color:#64748B;font-size:12px;font-family:var(--mono);">'
            'Provide a target total portfolio balance ($MM) for each of the next 120 months (10 years). '
            'These values populate the <em>Target ($MM)</em> column used by the New Volume Agent.'
            '</div></div>'
        )
        with gr.Row():
            target_file_upload = gr.File(
                label="Upload CSV (one numeric column, 120 rows — header optional)",
                file_types=[".csv", ".tsv", ".txt"],
                scale=2,
            )
            with gr.Column(scale=1):
                target_end_value = gr.Number(
                    value=None,
                    label="Manual End Value — Month 120 ($MM)",
                    info="Enter a target balance for month 120; the app will interpolate from current.",
                    precision=1,
                )
                target_interpolate_btn = gr.Button(
                    "↗  Interpolate from Current",
                    variant="secondary",
                    size="sm",
                )

        target_balance_msg     = gr.HTML(value="")
        target_balance_preview = gr.HTML(value="")

        with gr.Row():
            target_confirm_btn = gr.Button("✓  Confirm Target Balance", variant="primary", scale=1)
            target_cancel_btn  = gr.Button("✗  Cancel",                 variant="secondary", scale=0)

    # ── Setup row ─────────────────────────────────────────────────────────────
    with gr.Row():
        trader_input = gr.Textbox(
            value="Trader",
            label="Trader Name",
            placeholder="Your name",
            scale=2,
        )
        appetite_dd = gr.Dropdown(
            choices=["conservative", "moderate", "aggressive"],
            value="moderate",
            label="Risk Appetite",
            scale=1,
        )
        with gr.Column(scale=1, min_width=200):
            upload_target_btn = gr.Button(
                "⬆  Upload Target Balance",
                variant="secondary",
            )
            start_btn = gr.Button("▶  Start New Session", variant="primary")

    with gr.Row(elem_id="pp-resume-row"):
        resume_session_input = gr.Textbox(
            placeholder="Session ID (or 'latest')",
            label="Resume Session",
            scale=3,
        )
        resume_btn = gr.Button("↩  Resume", variant="secondary", scale=1)
        sessions_btn = gr.Button("📋  List Sessions", variant="secondary", scale=1)

    setup_msg   = gr.HTML(value="")
    sessions_html = gr.HTML(value="", visible=False)
    progress_html = gr.HTML(value="", visible=False)

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 1 — New Volume
    # ══════════════════════════════════════════════════════════════════════════
    with gr.Column(visible=False) as phase1_col:
        gr.HTML(_phase_header("Phase 1 — New Volume Agent", "#0891B2"))
        p1_progress_html = gr.HTML(value="")
        p1_agent_html  = gr.HTML(value="")
        p1_content_html = gr.HTML(value="")

        with gr.Column(visible=False) as p1_gate_col:
            gr.HTML(
                '<div style="color:#64748B;font-size:12px;font-family:var(--mono);'
                'padding:8px 0;">Gate 1 — Confirm or adjust the new-volume schedule.</div>'
            )
            with gr.Row():
                p1_custom_vol = gr.Number(
                    value=None,
                    label="Override 12M Volume ($MM) — leave blank to use agent-computed value",
                    precision=1,
                    scale=3,
                )
                p1_notes = gr.Textbox(
                    value="",
                    label="Override Reason (optional)",
                    scale=2,
                )
            with gr.Row():
                p1_approve_btn = gr.Button("✓  Approve", variant="primary",   scale=1)
                p1_modify_btn  = gr.Button("✎  Modify",  variant="secondary", scale=1)
                p1_reject_btn  = gr.Button("✗  Reject",  variant="stop",      scale=1)

        p1_status_html = gr.HTML(value="")

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 2 — Risk Assessment
    # ══════════════════════════════════════════════════════════════════════════
    with gr.Column(visible=False) as phase2_col:
        gr.HTML(_phase_header("Phase 2 — Risk Assessment Agent", "#D97706"))
        p2_progress_html = gr.HTML(value="")
        p2_agent_html   = gr.HTML(value="")
        p2_content_html = gr.HTML(value="")

        with gr.Column(visible=False) as p2_gate_col:
            gr.HTML(
                '<div style="color:#64748B;font-size:12px;font-family:var(--mono);'
                'padding:8px 0;">Gate 2 — Accept risk bounds or override duration limits.</div>'
            )
            with gr.Row():
                p2_dur_min    = gr.Number(value=3.5,       label="Duration Min (yrs)", precision=1, scale=1)
                p2_dur_max    = gr.Number(value=6.5,       label="Duration Max (yrs)", precision=1, scale=1)
                p2_appetite2  = gr.Dropdown(
                    choices=["conservative", "moderate", "aggressive"],
                    value="moderate",
                    label="Risk Appetite Override",
                    scale=2,
                )
            with gr.Row():
                p2_accept_btn = gr.Button("✓  Accept",        variant="primary",   scale=1)
                p2_change_btn = gr.Button("✎  Change Bounds", variant="secondary", scale=1)
                p2_reject_btn = gr.Button("✗  Reject",        variant="stop",      scale=1)

        p2_status_html = gr.HTML(value="")

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 3 — Allocation
    # ══════════════════════════════════════════════════════════════════════════
    with gr.Column(visible=False) as phase3_col:
        gr.HTML(_phase_header("Phase 3 — Allocation Agent", "#3B6FD4"))
        p3_progress_html = gr.HTML(value="")
        p3_agent_html    = gr.HTML(value="")
        p3_content_html  = gr.HTML(value="")

        with gr.Column(visible=False) as p3_gate_col:
            gr.HTML(
                '<div style="color:#64748B;font-size:12px;font-family:var(--mono);'
                'padding:8px 0;">Gate 3 — Select an allocation scenario or enter a custom split.</div>'
            )
            with gr.Row():
                p3_cons_btn   = gr.Button("1 · Conservative", variant="secondary", scale=1)
                p3_mod_btn    = gr.Button("2 · Moderate",     variant="primary",   scale=1)
                p3_agg_btn    = gr.Button("2 · Aggressive",   variant="secondary", scale=1)
                p3_reject_btn = gr.Button("✗  Reject",        variant="stop",      scale=1)

            with gr.Accordion("Custom Split", open=False):
                gr.HTML(
                    '<div style="color:#64748B;font-size:11px;font-family:var(--mono);padding:4px 0;">'
                    "Enter custom percentages (must sum to 100).</div>"
                )
                with gr.Row():
                    p3_mbs  = gr.Number(value=60.0, label="MBS %",        precision=1, scale=1)
                    p3_cmbs = gr.Number(value=22.0, label="CMBS %",       precision=1, scale=1)
                    p3_tsy  = gr.Number(value=18.0, label="Treasuries %", precision=1, scale=1)
                    p3_custom_btn = gr.Button("✓  Use Custom Split", variant="secondary", scale=1)

        p3_status_html = gr.HTML(value="")

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 4 — MBS Decomposition
    # ══════════════════════════════════════════════════════════════════════════
    with gr.Column(visible=False) as phase4_col:
        gr.HTML(_phase_header("Phase 4 — MBS Decomposition Agent", "#9333EA"))
        p4_progress_html = gr.HTML(value="")
        p4_agent_html   = gr.HTML(value="")
        p4_content_html = gr.HTML(value="")

        with gr.Column(visible=False) as p4_gate_col:
            gr.HTML(
                '<div style="color:#64748B;font-size:12px;font-family:var(--mono);'
                'padding:8px 0;">Gate 4 — Approve or adjust the MBS sub-bucket percentages '
                "(must sum to 100).</div>"
            )
            with gr.Row():
                p4_fnma30  = gr.Number(value=40.0, label="FNMA Fixed 30YR %",  precision=1, scale=1)
                p4_fhlmc30 = gr.Number(value=20.0, label="FHLMC Fixed 30YR %", precision=1, scale=1)
                p4_gnma30  = gr.Number(value=15.0, label="GNMA Fixed 30YR %",  precision=1, scale=1)
            with gr.Row():
                p4_fnma15  = gr.Number(value=15.0, label="FNMA Fixed 15YR %",  precision=1, scale=1)
                p4_fhlmc15 = gr.Number(value=5.0,  label="FHLMC Fixed 15YR %", precision=1, scale=1)
                p4_arm     = gr.Number(value=5.0,  label="ARM %",              precision=1, scale=1)
            with gr.Row():
                p4_approve_btn = gr.Button("✓  Approve", variant="primary",   scale=1)
                p4_modify_btn  = gr.Button("✎  Modify",  variant="secondary", scale=1)
                p4_reject_btn  = gr.Button("✗  Reject",  variant="stop",      scale=1)

        p4_status_html = gr.HTML(value="")

    # ══════════════════════════════════════════════════════════════════════════
    # Phase 5 — Final Approval
    # ══════════════════════════════════════════════════════════════════════════
    with gr.Column(visible=False) as phase5_col:
        gr.HTML(_phase_header("Phase 5 — Final Approval", "#059669"))
        p5_progress_html = gr.HTML(value="")
        p5_content_html = gr.HTML(value="")

        with gr.Column(visible=False) as p5_gate_col:
            gr.HTML(
                '<div style="color:#64748B;font-size:12px;font-family:var(--mono);'
                'padding:8px 0;">Gate 5 — Confirm the purchase schedule, revise, or abort.</div>'
            )
            p5_notes = gr.Textbox(value="", label="Trade Notes (optional)", scale=3)
            with gr.Row():
                p5_confirm_btn = gr.Button("✓  Confirm & Execute", variant="primary",   scale=1)
                p5_revise_btn  = gr.Button("↩  Revise Allocation", variant="secondary", scale=1)
                p5_abort_btn   = gr.Button("✗  Abort",             variant="stop",      scale=1)

        p5_status_html = gr.HTML(value="")

    # ══════════════════════════════════════════════════════════════════════════
    # Complete
    # ══════════════════════════════════════════════════════════════════════════
    with gr.Column(visible=False) as complete_col:
        gr.HTML(_phase_header("✓ Workflow Complete", "#059669"))
        complete_html = gr.HTML(value="")
        with gr.Row():
            new_session_btn = gr.Button("▶  Start New Session", variant="secondary", scale=0)

    # ═════════════════════════════════════════════════════════════════════════
    # Event handlers
    # ═════════════════════════════════════════════════════════════════════════

    # ── Upload Target Balance panel ────────────────────────────────────────

    upload_target_btn.click(
        fn=lambda: gr.update(visible=True),
        inputs=[],
        outputs=[upload_target_col],
    )

    target_cancel_btn.click(
        fn=lambda: gr.update(visible=False),
        inputs=[],
        outputs=[upload_target_col],
    )

    def _on_file_upload(file_obj):
        """Parse uploaded file and show preview."""
        path = file_obj.name if file_obj is not None else None
        vals, msg = _parse_target_balance_file(path)
        if vals is None:
            return (
                f'<div style="color:#E5484D;font-family:var(--mono);font-size:12px;">{msg}</div>',
                "",
                None,
            )
        preview = _target_balance_preview_html(vals)
        ok_msg  = f'<div style="color:#059669;font-family:var(--mono);font-size:12px;">✓ {msg}</div>'
        return ok_msg, preview, vals

    target_file_upload.change(
        fn=_on_file_upload,
        inputs=[target_file_upload],
        outputs=[target_balance_msg, target_balance_preview, target_balance_state],
    )

    def _on_interpolate(end_value):
        """Interpolate from a sample starting value to the user-entered end value."""
        if end_value is None:
            return (
                '<div style="color:#E5484D;font-family:var(--mono);font-size:12px;">'
                'Please enter an ending value ($MM) first.</div>',
                "",
                None,
            )
        try:
            from workflow.data.sample_data import generate_sample_data
            _, portfolio_df = generate_sample_data(n_months=1)
            start_val = float(portfolio_df["target_total_balance_mm"].iloc[0])
        except Exception:
            start_val = float(end_value) * 0.9   # fallback estimate

        vals    = _interpolate_target_balance(start_val, float(end_value), 120)
        preview = _target_balance_preview_html(vals)
        ok_msg  = (
            f'<div style="color:#059669;font-family:var(--mono);font-size:12px;">'
            f'✓ Interpolated 120 months: ${start_val:,.1f}MM → ${end_value:,.1f}MM</div>'
        )
        return ok_msg, preview, vals

    target_interpolate_btn.click(
        fn=_on_interpolate,
        inputs=[target_end_value],
        outputs=[target_balance_msg, target_balance_preview, target_balance_state],
    )

    def _on_confirm_target(vals):
        if not vals or len(vals) != 120:
            return (
                '<div style="color:#E5484D;font-family:var(--mono);font-size:12px;">'
                'No valid target balance loaded. Upload a file or use interpolation first.</div>',
                gr.update(),
            )
        return (
            '<div style="color:#059669;font-family:var(--mono);font-size:12px;">'
            f'✓ Target balance confirmed — 120 monthly values saved. '
            f'(${vals[0]:,.1f}MM → ${vals[-1]:,.1f}MM)</div>',
            gr.update(visible=False),
        )

    target_confirm_btn.click(
        fn=_on_confirm_target,
        inputs=[target_balance_state],
        outputs=[target_balance_msg, upload_target_col],
    )

    # ── Helpers ────────────────────────────────────────────────────────────

    def _hide_all_phases():
        """Return gr.update(visible=False) for all phase columns."""
        return [
            gr.update(visible=False),  # phase1_col
            gr.update(visible=False),  # phase2_col
            gr.update(visible=False),  # phase3_col
            gr.update(visible=False),  # phase4_col
            gr.update(visible=False),  # phase5_col
            gr.update(visible=False),  # complete_col
        ]

    def _clear_gate_status():
        """Return empty string updates for all status/agent/content components."""
        return [gr.update(value="")] * 12  # 5×agent + 5×content + 5×status = 15, we'll be precise

    # ── List sessions ─────────────────────────────────────────────────────

    def _list_sessions(state_json: str):
        try:
            from workflow.persistence.state_manager import StateManager
            sm = StateManager()
            sessions = sm.list_sessions()
            if not sessions:
                return gr.update(visible=True, value=_info("No saved sessions found."))
            rows = [
                [s["session_id"], s["phase"], s["trader_name"], s["updated_at"][:19]]
                for s in sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True)
            ]
            html = _html_table(
                ["Session ID", "Phase", "Trader", "Last Updated"],
                rows, "Saved Sessions"
            )
            return gr.update(visible=True, value=html)
        except Exception as ex:
            return gr.update(visible=True, value=_err(f"Could not load sessions: {ex}"))

    sessions_btn.click(
        fn=_list_sessions,
        inputs=[wf_state],
        outputs=[sessions_html],
    )

    # ── Start new session ─────────────────────────────────────────────────

    async def _start_workflow(trader_name: str, risk_appetite: str, custom_targets):
        """Initialize state, load data, run Phase 1 agent, show Gate 1."""
        from workflow.weave_runner import run_phase
        from workflow.models.workflow_state import RiskAppetite, WorkflowPhase
        from workflow.persistence.state_manager import StateManager

        # --- Loading feedback ---
        yield (
            "{}",                         # wf_state
            _info("Initializing session and loading data…"),  # setup_msg
            gr.update(visible=False),     # progress
            gr.update(visible=True),      # phase1_col
            _agent_progress_html("Phase 1 — New Volume Agent", "running"),  # p1_progress_html
            _spinner("Loading portfolio data (may take a moment)…"),  # p1_agent_html
            gr.update(value=""),          # p1_content_html
            gr.update(visible=False),     # p1_gate_col
            gr.update(value=""),          # p1_status_html
        )

        try:
            sm    = StateManager()
            state = sm.new_state(
                trader_name=trader_name.strip() or "Trader",
                risk_appetite=RiskAppetite(risk_appetite),
            )
            state.advance_phase(WorkflowPhase.NEW_VOLUME)
            await _load_data_into_state(state)

            # Override target balances if the user uploaded custom values
            if custom_targets and len(custom_targets) == 120:
                for i, mv in enumerate(state.monthly_volumes):
                    mv.target_total_balance_mm = custom_targets[i]
                    mv.new_volume_mm = max(
                        0.0,
                        round(custom_targets[i] - mv.predicted_existing_balance_mm, 2),
                    )

            await sm.save(state)

            # Run Phase 1 agent
            yield (
                _state_to_json(state),
                _info(f"Session {state.session_id} — running New Volume Agent…"),
                gr.update(visible=True, value=_progress_bar(state.phase.value)),
                gr.update(visible=True),
                _agent_progress_html("Phase 1 — New Volume Agent", "running"),
                _spinner("New Volume Agent analyzing purchase schedule…"),
                gr.update(value=""),
                gr.update(visible=False),
                gr.update(value=""),
            )

            agents = _ensure_agents()
            result = await run_phase(
                "new_volume", agents["new_volume"],
                "Calculate the full new volume schedule and provide a summary.",
                context=state,
            )
            await sm.save(state)

            yield (
                _state_to_json(state),
                "",
                gr.update(visible=True, value=_progress_bar(state.phase.value)),
                gr.update(visible=True),
                _agent_progress_html("Phase 1 — New Volume Agent", "done"),
                _agent_card(result.final_output),
                gr.update(value=_render_p1_content(state)),
                gr.update(visible=True),   # show gate
                gr.update(value=""),
            )

        except Exception as ex:
            logger.exception("Phase 1 failed")
            yield (
                "{}",
                _err(f"Error: {ex}"),
                gr.update(visible=False),
                gr.update(visible=False),
                "", "", gr.update(value=""), gr.update(visible=False), gr.update(value=""),
            )

    start_btn.click(
        fn=_start_workflow,
        inputs=[trader_input, appetite_dd, target_balance_state],
        outputs=[
            wf_state, setup_msg, progress_html,
            phase1_col, p1_progress_html, p1_agent_html, p1_content_html, p1_gate_col, p1_status_html,
        ],
    )

    # ── New Session button (from complete screen) ─────────────────────────

    def _reset_for_new():
        return (
            gr.update(visible=False),  # phase1_col
            gr.update(visible=False),  # phase2_col
            gr.update(visible=False),  # phase3_col
            gr.update(visible=False),  # phase4_col
            gr.update(visible=False),  # phase5_col
            gr.update(visible=False),  # complete_col
            gr.update(visible=False),  # progress_html
            "",                        # setup_msg
        )

    new_session_btn.click(
        fn=_reset_for_new,
        inputs=[],
        outputs=[phase1_col, phase2_col, phase3_col, phase4_col, phase5_col,
                 complete_col, progress_html, setup_msg],
    )

    # ── Resume session ─────────────────────────────────────────────────────

    async def _resume_session(session_id_str: str):
        from workflow.weave_runner import run_phase
        from workflow.models.workflow_state import WorkflowPhase
        from workflow.persistence.state_manager import StateManager

        if not session_id_str.strip():
            yield (
                "{}",
                _err("Enter a session ID or 'latest'."),
                gr.update(visible=False),
                *[gr.update(visible=False)] * 6,
                gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(visible=False), gr.update(value=""),
            )
            return

        yield (
            "{}",
            _info(f"Loading session '{session_id_str.strip()}'…"),
            gr.update(visible=False),
            *[gr.update(visible=False)] * 6,
            gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
            gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
            gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
            gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
            gr.update(value=""), gr.update(visible=False), gr.update(value=""),
            gr.update(visible=False), gr.update(value=""),
        )

        try:
            sm = StateManager()
            if session_id_str.strip() == "latest":
                state = await sm.load_latest()
            else:
                state = await sm.load(session_id_str.strip())

            if state is None:
                yield (
                    "{}",
                    _err(f"Session '{session_id_str.strip()}' not found."),
                    gr.update(visible=False),
                    *[gr.update(visible=False)] * 6,
                    gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(visible=False), gr.update(value=""),
                )
                return

            # Re-run the agent for the current phase
            phase = state.phase
            agents = _ensure_agents()

            # Default: hide everything
            p1v = p2v = p3v = p4v = p5v = comv = False
            p1ag = p1co = p1gi = p1st = ""
            p2ag = p2co = p2gi = p2st = ""
            p3ag = p3co = p3gi = p3st = ""
            p4ag = p4co = p4gi = p4st = ""
            p5co = p5gi = p5st = ""
            comp_html = ""

            if phase == WorkflowPhase.COMPLETE:
                comv = True
                comp_html = _render_complete(state)
            else:
                phase_msg = f"Resuming session {state.session_id} at phase {phase.value}…"
                yield (
                    _state_to_json(state),
                    _info(phase_msg),
                    gr.update(visible=True, value=_progress_bar(phase.value)),
                    gr.update(visible=False), gr.update(visible=False),
                    gr.update(visible=False), gr.update(visible=False),
                    gr.update(visible=False), gr.update(visible=False),
                    gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                    gr.update(visible=False), gr.update(value=""),
                )

                if phase == WorkflowPhase.NEW_VOLUME:
                    p1v = True
                    result = await run_phase("new_volume", agents["new_volume"],
                        "Calculate the full new volume schedule and provide a summary.",
                        context=state)
                    await sm.save(state)
                    p1ag = _agent_card(result.final_output)
                    p1co = _render_p1_content(state)
                    p1gi = True

                elif phase == WorkflowPhase.RISK_ASSESSMENT:
                    p1v = p2v = True
                    p1ag = _agent_card("[Previous phase completed — see session history]")
                    p1co = _render_p1_content(state)
                    p1st = _decision_badge("approved", "resumed")
                    result = await run_phase("risk_assessment", agents["risk"],
                        f"Evaluate portfolio risk for a {state.risk_appetite.value} risk appetite. "
                        f"New 12-month volume is ${state.next_12m_new_volume_mm:,.1f}MM. "
                        "Generate risk constraints and flag any issues.",
                        context=state)
                    await sm.save(state)
                    p2ag = _agent_card(result.final_output)
                    p2co = _render_p2_content(state)
                    p2gi = True

                elif phase == WorkflowPhase.ALLOCATION:
                    p1v = p2v = p3v = True
                    p1ag = p2ag = _agent_card("[Previous phase completed — see session history]")
                    p1co = _render_p1_content(state)
                    p2co = _render_p2_content(state)
                    p1st = p2st = _decision_badge("approved", "resumed")
                    result = await run_phase("allocation", agents["allocation"],
                        f"Generate allocation scenarios for ${state.next_12m_new_volume_mm:,.1f}MM "
                        f"new volume. Risk appetite: {state.risk_appetite.value}. "
                        "Present all three scenarios with trade-off analysis.",
                        context=state)
                    await sm.save(state)
                    p3ag = _agent_card(result.final_output)
                    p3co = _render_p3_content(state)
                    p3gi = True

                elif phase == WorkflowPhase.MBS_DECOMPOSITION:
                    p1v = p2v = p3v = p4v = True
                    _prev = _agent_card("[Previous phase completed — see session history]")
                    p1ag = p2ag = p3ag = _prev
                    p1co = _render_p1_content(state)
                    p2co = _render_p2_content(state)
                    p3co = _render_p3_content(state)
                    p1st = p2st = p3st = _decision_badge("approved", "resumed")
                    sc = state.selected_scenario
                    if sc:
                        result = await run_phase("mbs_decomposition", agents["mbs_decomp"],
                            f"Decompose the MBS allocation of ${sc.mbs_mm:,.1f}MM "
                            f"(from the {sc.label} scenario). "
                            f"Risk appetite: {state.risk_appetite.value}. "
                            "Break into Fixed/ARM, FNMA/FHLMC/GNMA, 30YR/15YR. "
                            "Then build the full purchase schedule.",
                            context=state)
                        await sm.save(state)
                        p4ag = _agent_card(result.final_output)
                        p4co = _render_p4_content(state)
                        p4gi = True

                elif phase == WorkflowPhase.FINAL_APPROVAL:
                    p1v = p2v = p3v = p4v = p5v = True
                    _prev = _agent_card("[Previous phase completed — see session history]")
                    p1ag = p2ag = p3ag = p4ag = _prev
                    p1co = _render_p1_content(state)
                    p2co = _render_p2_content(state)
                    p3co = _render_p3_content(state)
                    p4co = _render_p4_content(state)
                    p1st = p2st = p3st = p4st = _decision_badge("approved", "resumed")
                    p5co = _render_p5_content(state)
                    p5gi = True

            yield (
                _state_to_json(state),
                "",
                gr.update(visible=not comv, value=_progress_bar(phase.value) if not comv else ""),
                gr.update(visible=p1v),
                gr.update(visible=p2v),
                gr.update(visible=p3v),
                gr.update(visible=p4v),
                gr.update(visible=p5v),
                gr.update(visible=comv),
                gr.update(value=p1ag), gr.update(value=p1co),
                gr.update(visible=bool(p1gi) if isinstance(p1gi, (bool, int)) else False),
                gr.update(value=p1st),
                gr.update(value=p2ag), gr.update(value=p2co),
                gr.update(visible=bool(p2gi) if isinstance(p2gi, (bool, int)) else False),
                gr.update(value=p2st),
                gr.update(value=p3ag), gr.update(value=p3co),
                gr.update(visible=bool(p3gi) if isinstance(p3gi, (bool, int)) else False),
                gr.update(value=p3st),
                gr.update(value=p4ag), gr.update(value=p4co),
                gr.update(visible=bool(p4gi) if isinstance(p4gi, (bool, int)) else False),
                gr.update(value=p4st),
                gr.update(value=p5co),
                gr.update(visible=bool(p5gi) if isinstance(p5gi, (bool, int)) else False),
                gr.update(value=p5st),
                gr.update(visible=comv),
                gr.update(value=comp_html),
            )

        except Exception as ex:
            logger.exception("Resume failed")
            yield (
                "{}",
                _err(f"Resume error: {ex}"),
                gr.update(visible=False),
                *[gr.update(visible=False)] * 6,
                gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(value=""), gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(value=""), gr.update(visible=False), gr.update(value=""),
                gr.update(visible=False), gr.update(value=""),
            )

    _resume_outputs = [
        wf_state, setup_msg, progress_html,
        phase1_col, phase2_col, phase3_col, phase4_col, phase5_col, complete_col,
        p1_agent_html, p1_content_html, p1_gate_col, p1_status_html,
        p2_agent_html, p2_content_html, p2_gate_col, p2_status_html,
        p3_agent_html, p3_content_html, p3_gate_col, p3_status_html,
        p4_agent_html, p4_content_html, p4_gate_col, p4_status_html,
        p5_content_html, p5_gate_col, p5_status_html,
        complete_col, complete_html,
    ]

    resume_btn.click(
        fn=_resume_session,
        inputs=[resume_session_input],
        outputs=_resume_outputs,
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Gate 1 — New Volume
    # ══════════════════════════════════════════════════════════════════════════

    async def _gate1_proceed(state_json: str, custom_vol, notes: str, action: str):
        """Shared handler for Gate 1 approve/modify, then runs Phase 2 agent."""
        from workflow.weave_runner import run_phase
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager

        state = _state_from_json(state_json)
        if state is None:
            yield (
                state_json, _err("No active session."),
                gr.update(), gr.update(), gr.update(visible=False), gr.update(), gr.update(),
                gr.update(visible=False), gr.update(), gr.update(),
            )
            return

        # Show loading
        yield (
            state_json,
            _info("Running Risk Assessment Agent…"),
            gr.update(visible=True, value=_progress_bar("risk_assessment")),
            gr.update(visible=False),  # p1_gate_col
            gr.update(value=_decision_badge(action)),  # p1_status
            gr.update(visible=True),  # phase2_col
            _agent_progress_html("Phase 2 — Risk Assessment Agent", "running"),  # p2_progress_html
            _spinner("Risk Assessment Agent evaluating portfolio…"),  # p2_agent_html
            gr.update(value=""),  # p2_content_html
            gr.update(visible=False),  # p2_gate_col
            gr.update(value=""),  # p2_status
        )

        try:
            sm = StateManager()

            # Apply gate decision
            if action == "modified" and custom_vol:
                state.next_12m_new_volume_mm = float(custom_vol)

            decision = GateDecision(
                gate_name="new_volume",
                status=ApprovalStatus(action),
                trader_choice=action,
                trader_overrides={"next_12m_new_volume_mm": float(custom_vol)} if custom_vol else {},
                notes=notes.strip() if notes else "",
            )
            state.add_gate_decision(decision)
            state.advance_phase(WorkflowPhase.RISK_ASSESSMENT)
            await sm.save(state)

            # Run Phase 2 agent
            result = await run_phase(
                "risk_assessment", _ensure_agents()["risk"],
                f"Evaluate portfolio risk for a {state.risk_appetite.value} risk appetite. "
                f"New 12-month volume is ${state.next_12m_new_volume_mm:,.1f}MM. "
                "Generate risk constraints and flag any issues.",
                context=state,
            )
            await sm.save(state)

            rc = state.risk_constraints
            yield (
                _state_to_json(state),
                "",
                gr.update(visible=True, value=_progress_bar(state.phase.value)),
                gr.update(visible=False),
                gr.update(value=_decision_badge(action, notes)),
                gr.update(visible=True),
                _agent_progress_html("Phase 2 — Risk Assessment Agent", "done"),
                _agent_card(result.final_output),
                gr.update(value=_render_p2_content(state)),
                gr.update(visible=True),
                gr.update(value=""),
            )

        except Exception as ex:
            logger.exception("Gate 1 → Phase 2 failed")
            yield (
                state_json, _err(f"Error: {ex}"),
                gr.update(), gr.update(visible=True), gr.update(), gr.update(visible=False),
                "", "", gr.update(value=""), gr.update(visible=False), gr.update(value=""),
            )

    _g1_outputs = [
        wf_state, setup_msg, progress_html,
        p1_gate_col, p1_status_html,
        phase2_col, p2_progress_html, p2_agent_html, p2_content_html, p2_gate_col, p2_status_html,
    ]
    _g1_inputs  = [wf_state, p1_custom_vol, p1_notes]

    async def _g1_approve(s, v, n):
        async for x in _gate1_proceed(s, v, n, "approved"):
            yield x

    async def _g1_modify(s, v, n):
        async for x in _gate1_proceed(s, v, n, "modified"):
            yield x

    p1_approve_btn.click(fn=_g1_approve, inputs=_g1_inputs, outputs=_g1_outputs)
    p1_modify_btn.click(fn=_g1_modify, inputs=_g1_inputs, outputs=_g1_outputs)

    async def _gate1_reject(state_json: str):
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager
        state = _state_from_json(state_json)
        if state is None:
            return
        decision = GateDecision(gate_name="new_volume", status=ApprovalStatus.REJECTED,
                                trader_choice="reject")
        state.add_gate_decision(decision)
        state.advance_phase(WorkflowPhase.COMPLETE)
        state.final_summary = "REJECTED at Gate 1 — New Volume."
        await StateManager().save(state)
        return (
            _state_to_json(state),
            gr.update(visible=False),
            gr.update(value=_decision_badge("rejected")),
            gr.update(visible=True),
            gr.update(value=_render_complete(state)),
        )

    p1_reject_btn.click(
        fn=_gate1_reject,
        inputs=[wf_state],
        outputs=[wf_state, p1_gate_col, p1_status_html, complete_col, complete_html],
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Gate 2 — Risk Assessment
    # ══════════════════════════════════════════════════════════════════════════

    async def _gate2_proceed(state_json: str, dur_min, dur_max, appetite_override: str, action: str):
        from workflow.weave_runner import run_phase
        from workflow.models.workflow_state import (
            ApprovalStatus, GateDecision, RiskAppetite, WorkflowPhase,
        )
        from workflow.persistence.state_manager import StateManager

        state = _state_from_json(state_json)
        if state is None:
            return

        yield (
            state_json, _info("Running Allocation Agent…"),
            gr.update(visible=True, value=_progress_bar("allocation")),
            gr.update(visible=False),  # p2_gate_col
            gr.update(value=_decision_badge(action)),
            gr.update(visible=True),  # phase3_col
            _agent_progress_html("Phase 3 — Allocation Agent", "running"),  # p3_progress_html
            _spinner("Allocation Agent generating scenarios…"),
            gr.update(value=""),  # p3_content
            gr.update(visible=False),  # p3_gate_col
            gr.update(value=""),
        )

        try:
            sm = StateManager()
            overrides = {}
            if action == "modified":
                if dur_min is not None:
                    if state.risk_constraints:
                        state.risk_constraints.duration_min = float(dur_min)
                    overrides["duration_min"] = float(dur_min)
                if dur_max is not None:
                    if state.risk_constraints:
                        state.risk_constraints.duration_max = float(dur_max)
                    overrides["duration_max"] = float(dur_max)
                if appetite_override:
                    state.risk_appetite = RiskAppetite(appetite_override)
                    overrides["risk_appetite"] = appetite_override

            decision = GateDecision(
                gate_name="risk_assessment",
                status=ApprovalStatus(action),
                trader_choice=action,
                trader_overrides=overrides,
            )
            state.add_gate_decision(decision)
            state.advance_phase(WorkflowPhase.ALLOCATION)
            await sm.save(state)

            result = await run_phase(
                "allocation", _ensure_agents()["allocation"],
                f"Generate allocation scenarios for ${state.next_12m_new_volume_mm:,.1f}MM "
                f"new volume. Risk appetite: {state.risk_appetite.value}. "
                "Present all three scenarios with trade-off analysis.",
                context=state,
            )
            await sm.save(state)

            yield (
                _state_to_json(state),
                "",
                gr.update(visible=True, value=_progress_bar(state.phase.value)),
                gr.update(visible=False),
                gr.update(value=_decision_badge(action)),
                gr.update(visible=True),
                _agent_progress_html("Phase 3 — Allocation Agent", "done"),
                _agent_card(result.final_output),
                gr.update(value=_render_p3_content(state)),
                gr.update(visible=True),
                gr.update(value=""),
            )

        except Exception as ex:
            logger.exception("Gate 2 → Phase 3 failed")
            yield (
                state_json, _err(f"Error: {ex}"),
                gr.update(), gr.update(visible=True), gr.update(),
                gr.update(visible=False), "", "", gr.update(value=""), gr.update(visible=False), gr.update(value=""),
            )

    _g2_outputs = [
        wf_state, setup_msg, progress_html,
        p2_gate_col, p2_status_html,
        phase3_col, p3_progress_html, p3_agent_html, p3_content_html, p3_gate_col, p3_status_html,
    ]
    _g2_inputs  = [wf_state, p2_dur_min, p2_dur_max, p2_appetite2]

    async def _g2_accept(s, mi, ma, ap):
        async for x in _gate2_proceed(s, mi, ma, ap, "approved"):
            yield x

    async def _g2_change(s, mi, ma, ap):
        async for x in _gate2_proceed(s, mi, ma, ap, "modified"):
            yield x

    p2_accept_btn.click(fn=_g2_accept, inputs=_g2_inputs, outputs=_g2_outputs)
    p2_change_btn.click(fn=_g2_change, inputs=_g2_inputs, outputs=_g2_outputs)

    async def _gate2_reject(state_json: str):
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager
        state = _state_from_json(state_json)
        if state is None:
            return
        decision = GateDecision(gate_name="risk_assessment", status=ApprovalStatus.REJECTED,
                                trader_choice="reject")
        state.add_gate_decision(decision)
        state.advance_phase(WorkflowPhase.COMPLETE)
        state.final_summary = "REJECTED at Gate 2 — Risk Assessment."
        await StateManager().save(state)
        return (
            _state_to_json(state),
            gr.update(visible=False),
            gr.update(value=_decision_badge("rejected")),
            gr.update(visible=True),
            gr.update(value=_render_complete(state)),
        )

    p2_reject_btn.click(
        fn=_gate2_reject,
        inputs=[wf_state],
        outputs=[wf_state, p2_gate_col, p2_status_html, complete_col, complete_html],
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Gate 3 — Allocation
    # ══════════════════════════════════════════════════════════════════════════

    async def _gate3_proceed(state_json: str, scenario_id: str,
                             custom_mbs=None, custom_cmbs=None, custom_tsy=None):
        from workflow.weave_runner import run_phase
        from workflow.models.workflow_state import (
            AllocationScenario, ApprovalStatus, GateDecision, WorkflowPhase,
        )
        from workflow.persistence.state_manager import StateManager

        state = _state_from_json(state_json)
        if state is None:
            return

        yield (
            state_json, _info("Running MBS Decomposition Agent…"),
            gr.update(visible=True, value=_progress_bar("mbs_decomposition")),
            gr.update(visible=False),  # p3_gate_col
            gr.update(value=_decision_badge("approved")),
            gr.update(visible=True),  # phase4_col
            _agent_progress_html("Phase 4 — MBS Decomposition Agent", "running"),  # p4_progress_html
            _spinner("MBS Decomposition Agent breaking down allocation…"),
            gr.update(value=""),
            gr.update(visible=False),  # p4_gate_col
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # p4 pct fields
            gr.update(value=""),
        )

        try:
            sm = StateManager()

            # Resolve selected scenario
            if scenario_id == "custom" and all(x is not None for x in [custom_mbs, custom_cmbs, custom_tsy]):
                mbs = float(custom_mbs); cmbs = float(custom_cmbs); tsy = float(custom_tsy)
                total_pct = mbs + cmbs + tsy
                if abs(total_pct - 100) > 1:
                    # Normalise
                    mbs, cmbs, tsy = mbs/total_pct*100, cmbs/total_pct*100, tsy/total_pct*100
                vol = state.next_12m_new_volume_mm
                custom_s = AllocationScenario(
                    scenario_id="custom", label="Custom",
                    mbs_pct=mbs, cmbs_pct=cmbs, treasury_pct=tsy,
                    mbs_mm=round(vol*mbs/100, 1),
                    cmbs_mm=round(vol*cmbs/100, 1),
                    treasury_mm=round(vol*tsy/100, 1),
                    total_new_volume_mm=vol,
                    projected_duration=5.2, projected_liquidity_score=8.0,
                    projected_yield_pct=5.1,
                    rationale="Trader-defined custom allocation.",
                )
                state.allocation_scenarios.append(custom_s)
                state.selected_scenario = custom_s
                decision_status = ApprovalStatus.MODIFIED
            else:
                selected = next(
                    (s for s in state.allocation_scenarios if s.scenario_id == scenario_id), None
                )
                if selected is None and state.allocation_scenarios:
                    selected = state.allocation_scenarios[0]
                state.selected_scenario = selected
                decision_status = ApprovalStatus.APPROVED

            decision = GateDecision(
                gate_name="allocation",
                status=decision_status,
                trader_choice=scenario_id,
                trader_overrides={"selected_scenario_id": scenario_id},
            )
            state.add_gate_decision(decision)
            state.advance_phase(WorkflowPhase.MBS_DECOMPOSITION)
            await sm.save(state)

            sc = state.selected_scenario
            result = await run_phase(
                "mbs_decomposition", _ensure_agents()["mbs_decomp"],
                f"Decompose the MBS allocation of ${sc.mbs_mm:,.1f}MM "
                f"(from the {sc.label} scenario). "
                f"Risk appetite: {state.risk_appetite.value}. "
                "Break into Fixed/ARM, FNMA/FHLMC/GNMA, 30YR/15YR. "
                "Then build the full purchase schedule.",
                context=state,
            )
            await sm.save(state)

            mb = state.mbs_breakdown
            yield (
                _state_to_json(state),
                "",
                gr.update(visible=True, value=_progress_bar(state.phase.value)),
                gr.update(visible=False),
                gr.update(value=_decision_badge(decision_status.value)),
                gr.update(visible=True),
                _agent_progress_html("Phase 4 — MBS Decomposition Agent", "done"),
                _agent_card(result.final_output),
                gr.update(value=_render_p4_content(state)),
                gr.update(visible=True),
                mb.fnma_fixed_30yr_pct if mb else 0.0,
                mb.fhlmc_fixed_30yr_pct if mb else 0.0,
                mb.gnma_fixed_30yr_pct if mb else 0.0,
                mb.fnma_fixed_15yr_pct if mb else 0.0,
                mb.fhlmc_fixed_15yr_pct if mb else 0.0,
                mb.arm_pct if mb else 0.0,
                gr.update(value=""),
            )

        except Exception as ex:
            logger.exception("Gate 3 → Phase 4 failed")
            yield (
                state_json, _err(f"Error: {ex}"),
                gr.update(), gr.update(visible=True), gr.update(),
                gr.update(visible=False), "", "", gr.update(value=""),
                gr.update(visible=False),
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, gr.update(value=""),
            )

    _g3_outputs = [
        wf_state, setup_msg, progress_html,
        p3_gate_col, p3_status_html,
        phase4_col, p4_progress_html, p4_agent_html, p4_content_html, p4_gate_col,
        p4_fnma30, p4_fhlmc30, p4_gnma30, p4_fnma15, p4_fhlmc15, p4_arm,
        p4_status_html,
    ]

    async def _g3_cons(s, m, c, t):
        async for x in _gate3_proceed(s, "conservative"):
            yield x

    async def _g3_mod(s, m, c, t):
        async for x in _gate3_proceed(s, "moderate"):
            yield x

    async def _g3_agg(s, m, c, t):
        async for x in _gate3_proceed(s, "aggressive"):
            yield x

    async def _g3_custom(s, m, c, t):
        async for x in _gate3_proceed(s, "custom", m, c, t):
            yield x

    _g3_inputs = [wf_state, p3_mbs, p3_cmbs, p3_tsy]
    p3_cons_btn.click(fn=_g3_cons, inputs=_g3_inputs, outputs=_g3_outputs)
    p3_mod_btn.click(fn=_g3_mod, inputs=_g3_inputs, outputs=_g3_outputs)
    p3_agg_btn.click(fn=_g3_agg, inputs=_g3_inputs, outputs=_g3_outputs)
    p3_custom_btn.click(fn=_g3_custom, inputs=_g3_inputs, outputs=_g3_outputs)

    async def _gate3_reject(state_json: str):
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager
        state = _state_from_json(state_json)
        if state is None:
            return
        decision = GateDecision(gate_name="allocation", status=ApprovalStatus.REJECTED,
                                trader_choice="reject")
        state.add_gate_decision(decision)
        state.advance_phase(WorkflowPhase.COMPLETE)
        state.final_summary = "REJECTED at Gate 3 — Allocation."
        await StateManager().save(state)
        return (
            _state_to_json(state),
            gr.update(visible=False),
            gr.update(value=_decision_badge("rejected")),
            gr.update(visible=True),
            gr.update(value=_render_complete(state)),
        )

    p3_reject_btn.click(
        fn=_gate3_reject,
        inputs=[wf_state],
        outputs=[wf_state, p3_gate_col, p3_status_html, complete_col, complete_html],
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Gate 4 — MBS Decomposition
    # ══════════════════════════════════════════════════════════════════════════

    async def _gate4_proceed(state_json: str,
                             fnma30, fhlmc30, gnma30, fnma15, fhlmc15, arm_pct,
                             action: str):
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager

        state = _state_from_json(state_json)
        if state is None:
            return

        yield (
            state_json, _info("Proceeding to Final Approval…"),
            gr.update(visible=True, value=_progress_bar("final_approval")),
            gr.update(visible=False),
            gr.update(value=_decision_badge(action)),
            gr.update(visible=True),  # phase5_col
            gr.update(value=""),      # p5_content
            gr.update(visible=False), # p5_gate_col
            gr.update(value=""),
        )

        try:
            sm = StateManager()
            mb = state.mbs_breakdown
            overrides = {}

            if action == "modified" and mb:
                new_pcts = {
                    "fnma_fixed_30yr_pct":  float(fnma30)  if fnma30  is not None else mb.fnma_fixed_30yr_pct,
                    "fhlmc_fixed_30yr_pct": float(fhlmc30) if fhlmc30 is not None else mb.fhlmc_fixed_30yr_pct,
                    "gnma_fixed_30yr_pct":  float(gnma30)  if gnma30  is not None else mb.gnma_fixed_30yr_pct,
                    "fnma_fixed_15yr_pct":  float(fnma15)  if fnma15  is not None else mb.fnma_fixed_15yr_pct,
                    "fhlmc_fixed_15yr_pct": float(fhlmc15) if fhlmc15 is not None else mb.fhlmc_fixed_15yr_pct,
                    "arm_pct":              float(arm_pct) if arm_pct is not None else mb.arm_pct,
                }
                total = sum(new_pcts.values())
                if total > 0:
                    for k, v in new_pcts.items():
                        new_pcts[k] = v / total * 100
                mbs_mm = state.selected_scenario.mbs_mm if state.selected_scenario else 0.0
                for attr, val in new_pcts.items():
                    setattr(mb, attr, round(val, 1))
                    amt_attr = attr.replace("_pct", "_mm")
                    setattr(mb, amt_attr, round(mbs_mm * val / 100, 1))
                mb.rationale = "Trader-adjusted MBS decomposition."
                overrides = new_pcts

                # Rebuild purchase schedule after modification
                from workflow.tools.allocation_tools import build_purchase_schedule
                from agents import RunContextWrapper
                class _FakeWrapper:
                    context = state
                build_purchase_schedule(_FakeWrapper())

            decision = GateDecision(
                gate_name="mbs_decomposition",
                status=ApprovalStatus(action),
                trader_choice=action,
                trader_overrides=overrides,
            )
            state.add_gate_decision(decision)
            state.advance_phase(WorkflowPhase.FINAL_APPROVAL)
            await sm.save(state)

            yield (
                _state_to_json(state),
                "",
                gr.update(visible=True, value=_progress_bar(state.phase.value)),
                gr.update(visible=False),
                gr.update(value=_decision_badge(action)),
                gr.update(visible=True),
                gr.update(value=_render_p5_content(state)),
                gr.update(visible=True),
                gr.update(value=""),
            )

        except Exception as ex:
            logger.exception("Gate 4 → Phase 5 failed")
            yield (
                state_json, _err(f"Error: {ex}"),
                gr.update(), gr.update(visible=True), gr.update(),
                gr.update(visible=False), gr.update(value=""),
                gr.update(visible=False), gr.update(value=""),
            )

    _g4_outputs = [
        wf_state, setup_msg, progress_html,
        p4_gate_col, p4_status_html,
        phase5_col, p5_content_html, p5_gate_col, p5_status_html,
    ]
    _g4_inputs  = [wf_state, p4_fnma30, p4_fhlmc30, p4_gnma30, p4_fnma15, p4_fhlmc15, p4_arm]

    async def _g4_approve(s, a, b, c, d, e, f):
        async for x in _gate4_proceed(s, a, b, c, d, e, f, "approved"):
            yield x

    async def _g4_modify(s, a, b, c, d, e, f):
        async for x in _gate4_proceed(s, a, b, c, d, e, f, "modified"):
            yield x

    p4_approve_btn.click(fn=_g4_approve, inputs=_g4_inputs, outputs=_g4_outputs)
    p4_modify_btn.click(fn=_g4_modify, inputs=_g4_inputs, outputs=_g4_outputs)

    async def _gate4_reject(state_json: str):
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager
        state = _state_from_json(state_json)
        if state is None:
            return
        decision = GateDecision(gate_name="mbs_decomposition", status=ApprovalStatus.REJECTED,
                                trader_choice="reject")
        state.add_gate_decision(decision)
        state.advance_phase(WorkflowPhase.COMPLETE)
        state.final_summary = "REJECTED at Gate 4 — MBS Decomposition."
        await StateManager().save(state)
        return (
            _state_to_json(state),
            gr.update(visible=False),
            gr.update(value=_decision_badge("rejected")),
            gr.update(visible=True),
            gr.update(value=_render_complete(state)),
        )

    p4_reject_btn.click(
        fn=_gate4_reject,
        inputs=[wf_state],
        outputs=[wf_state, p4_gate_col, p4_status_html, complete_col, complete_html],
    )

    # ══════════════════════════════════════════════════════════════════════════
    # Gate 5 — Final Approval
    # ══════════════════════════════════════════════════════════════════════════

    async def _gate5_confirm(state_json: str, notes: str):
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager

        state = _state_from_json(state_json)
        if state is None:
            return

        decision = GateDecision(
            gate_name="final_approval",
            status=ApprovalStatus.APPROVED,
            trader_choice="confirm",
            notes=notes.strip() if notes else "",
        )
        state.add_gate_decision(decision)
        state.advance_phase(WorkflowPhase.COMPLETE)
        # Build final summary
        sc = state.selected_scenario
        mb = state.mbs_breakdown
        total = sum(i.amount_mm for i in state.purchase_schedule)
        state.final_summary = (
            f"CONFIRMED — {state.session_id}\n"
            f"Trader: {state.trader_name}  Risk: {state.risk_appetite.value.upper()}\n"
            f"Volume: ${state.next_12m_new_volume_mm:,.1f}MM  Purchase: ${total:,.1f}MM\n"
            + (f"Allocation: {sc.label}  Duration: {sc.projected_duration:.2f}yr  "
               f"Yield: {sc.projected_yield_pct:.2f}%\n" if sc else "")
        )
        await StateManager().save(state)
        return (
            _state_to_json(state),
            gr.update(visible=False),
            gr.update(value=_decision_badge("approved", notes)),
            gr.update(visible=True),
            gr.update(value=_render_complete(state)),
        )

    p5_confirm_btn.click(
        fn=_gate5_confirm,
        inputs=[wf_state, p5_notes],
        outputs=[wf_state, p5_gate_col, p5_status_html, complete_col, complete_html],
    )

    async def _gate5_revise(state_json: str):
        """Loop back to Phase 3 — re-run the allocation agent."""
        from agents import Runner
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager

        state = _state_from_json(state_json)
        if state is None:
            return

        yield (
            state_json, _info("Returning to Allocation — re-running agent…"),
            gr.update(visible=True, value=_progress_bar("allocation")),
            gr.update(visible=False),  # p5_gate_col
            gr.update(value=_decision_badge("modified", "revised")),
            gr.update(visible=True),   # phase3_col (re-open)
            _spinner("Allocation Agent regenerating scenarios…"),
            gr.update(value=""),
            gr.update(visible=False),
            gr.update(value=""),
        )

        try:
            sm = StateManager()
            decision = GateDecision(
                gate_name="final_approval",
                status=ApprovalStatus.MODIFIED,
                trader_choice="revise",
            )
            state.add_gate_decision(decision)
            state.selected_scenario = None
            state.mbs_breakdown = None
            state.purchase_schedule = []
            state.advance_phase(WorkflowPhase.ALLOCATION)
            await sm.save(state)

            result = await Runner.run(
                _ensure_agents()["allocation"],
                f"Generate allocation scenarios for ${state.next_12m_new_volume_mm:,.1f}MM "
                f"new volume. Risk appetite: {state.risk_appetite.value}. "
                "Present all three scenarios with trade-off analysis.",
                context=state,
            )
            await sm.save(state)

            yield (
                _state_to_json(state),
                "",
                gr.update(visible=True, value=_progress_bar(state.phase.value)),
                gr.update(visible=False),
                gr.update(value=_decision_badge("modified", "revised")),
                gr.update(visible=True),
                _agent_card(result.final_output),
                gr.update(value=_render_p3_content(state)),
                gr.update(visible=True),
                gr.update(value=""),
            )

        except Exception as ex:
            logger.exception("Gate 5 revise failed")
            yield (
                state_json, _err(f"Error: {ex}"),
                gr.update(), gr.update(visible=True), gr.update(),
                gr.update(visible=False), "", gr.update(value=""),
                gr.update(visible=False), gr.update(value=""),
            )

    p5_revise_btn.click(
        fn=_gate5_revise,
        inputs=[wf_state],
        outputs=[
            wf_state, setup_msg, progress_html,
            p5_gate_col, p5_status_html,
            phase3_col, p3_agent_html, p3_content_html, p3_gate_col, p3_status_html,
        ],
    )

    async def _gate5_abort(state_json: str):
        from workflow.models.workflow_state import ApprovalStatus, GateDecision, WorkflowPhase
        from workflow.persistence.state_manager import StateManager
        state = _state_from_json(state_json)
        if state is None:
            return
        decision = GateDecision(gate_name="final_approval", status=ApprovalStatus.REJECTED,
                                trader_choice="abort")
        state.add_gate_decision(decision)
        state.advance_phase(WorkflowPhase.COMPLETE)
        state.final_summary = "ABORTED at Final Approval."
        await StateManager().save(state)
        return (
            _state_to_json(state),
            gr.update(visible=False),
            gr.update(value=_decision_badge("rejected", "aborted")),
            gr.update(visible=True),
            gr.update(value=_render_complete(state)),
        )

    p5_abort_btn.click(
        fn=_gate5_abort,
        inputs=[wf_state],
        outputs=[wf_state, p5_gate_col, p5_status_html, complete_col, complete_html],
    )
