# Oasia — Stakeholder Summary

**Oasia** is an AI-powered analytics and decision-support platform for institutional Agency MBS (mortgage-backed securities) portfolio management teams. It replaces spreadsheet-driven workflows with a unified, browser-based workbench that combines quantitative fixed-income analytics, a 7-agent AI assistant, and a structured human-in-the-loop purchase-planning workflow.

---

## The Problem We Solve

Agency MBS portfolio managers face three recurring challenges:

1. **Fragmented tooling.** Analytics live in Excel, risk reports arrive by email, and the security screener is a separate application. Cross-referencing them wastes time and introduces errors.
2. **Manual, slow purchase planning.** Building a purchase schedule—estimating new volumes, stress-testing duration and EVE, comparing allocation scenarios—takes days of analyst time for what should be a same-day decision.
3. **No institutional memory in AI tools.** Generic AI assistants don't know OAS, OAD, or EVE. They can't screen a pool universe, flag an EVE breach, or generate a CMBS allocation scenario.

---

## What Oasia Does

### A Single Workbench for the Full Investment Lifecycle

Oasia integrates eight analytical views inside one browser application:

| View | What It Gives You |
|------|-------------------|
| **Dashboard** | Live portfolio KPIs — NAV, book yield, OAD, OAS — plus a 30-year NAV projection, health scorecard, and YTD top performers |
| **Portfolio Analytics** | EVE stress test (+/− 300 bps), duration/convexity profile, book-yield breakdown, and historical KPI trends |
| **Security Analytics** | Single-pool OAS/OAD/convexity detail and rate-shock comparison table (−200 to +300 bps) |
| **Security Selection** | Screened universe with relative-value labels (CHEAP / FAIR / RICH), sortable by any analytics metric |
| **What-If Sandbox** | Real-time repricing after modifying CPR, WAC, or spread assumptions; before/after comparison at any rate shock |
| **Attribution** | Period P&L decomposed into OAS change, carry/roll, yield income, and EVE drivers — by position or portfolio |
| **Portfolio Planning** | 4-phase AI-guided purchase workflow with 5 human approval gates (described below) |
| **Watchlist** | User-curated pool tracker with unrealised P&L and one-click navigation to analytics |

---

### 7-Agent AI Assistant (Oasia Agent)

A floating chat panel — always visible, on every screen — gives portfolio managers a conversational interface to the analytics engine. Behind a single chat window, seven specialist AI agents collaborate:

| Agent | What It Does |
|-------|-------------|
| **Orchestrator** | Routes each question to the right specialist; synthesises the answer |
| **Security Selection** | Screens pools, identifies cheap/rich opportunities, runs cohort comparisons |
| **What-If Analysis** | Reprices pools under modified assumptions; runs rate-shock scenarios |
| **Portfolio Analytics** | Reports OAS, OAD, book yield, EVE; detects limit breaches |
| **Attribution** | Decomposes P&L into its drivers |
| **Market Data** | Retrieves the current SOFR and Treasury curves; reports cohort spreads |
| **Dashboard** | Answers questions about NAV, top performers, sector allocation, health scores, and the active planning session |

Every agent call — from the user's question to each tool result to the final answer — is captured in the observability dashboard (W&B Weave) for audit and performance monitoring.

---

### AI-Guided Purchase Planning (Human-in-the-Loop Workflow)

The Portfolio Planning tab automates the most time-consuming part of the investment process. A 4-phase AI pipeline, with 5 structured approval gates, turns a target balance number into an actionable purchase schedule in a single session:

```
Phase 1 — New Volume
  AI calculates the month-by-month new-purchase schedule needed
  to hit the target portfolio balance, accounting for prepayment runoff.
  ↓ Gate 1: Trader approves, adjusts, or rejects the volume schedule.

Phase 2 — Risk Assessment
  AI evaluates duration, liquidity, and concentration constraints
  for the proposed purchases; flags any policy breaches.
  ↓ Gate 2: Trader accepts the risk guardrails or adjusts bounds.

Phase 3 — Allocation
  AI proposes three scenarios (Conservative / Moderate / Aggressive)
  showing MBS, CMBS, and Treasury mix with projected duration, yield, and rationale.
  ↓ Gate 3: Trader selects a scenario or enters a custom allocation.

Phase 4 — MBS Decomposition
  AI breaks the MBS dollar amount into FNMA / FHLMC / GNMA sub-buckets
  and assembles a final, prioritised purchase schedule.
  ↓ Gate 4: Trader approves the breakdown or adjusts sub-bucket percentages.

Phase 5 — Final Approval
  Trader confirms the complete purchase schedule, revises (back to Phase 3),
  or aborts.
  ↓ Gate 5: Session committed or returned for revision.
```

The AI does the quantitative heavy lifting; the trader retains full decision authority at every gate.

---

## Who Uses It

| Role | Primary Use |
|------|-------------|
| **Portfolio Manager** | Daily analytics review, purchase planning, quick what-if sensitivity analysis |
| **Trader** | Gate approvals in the planning workflow; executing the final purchase schedule |
| **Risk Analyst** | EVE monitoring, duration/concentration alerts, attribution review |
| **ALCO / Senior Leadership** | Dashboard KPIs, NAV projection, health scorecard |

---

## Technology at a Glance

| Component | Technology |
|-----------|-----------|
| UI | Gradio 6 + FastAPI, dark-themed custom CSS |
| Analytics core | Python: OAS solver (Monte Carlo + Brent's method), Hull-White rate paths, neural prepayment model |
| AI agents | OpenAI GPT-4o via OpenAI Agents SDK |
| Cash-flow engine | Intex API (production) / synthetic fallback (development) |
| Database | DuckDB (analytics cache) + SQLite (historical positions) |
| Observability | W&B Weave tracing + evaluation; OpenAI platform dashboard |
| Authentication | LDAP / Active Directory (or mock mode for development) |
| Deployment | Single Python process; runs on-premises or in a private cloud |

---

## Key Differentiators

- **Domain-native AI.** Agents understand OAS, OAD, EVE, CPR, WAC, and WALA natively — not generic language-model knowledge but skills tuned to Agency MBS.
- **Human always in control.** The purchase-planning workflow gives the AI analytical authority and the trader decisional authority — at every gate, the trader can override, adjust, or reject.
- **Full audit trail.** Every agent call, tool invocation, and gate decision is logged. The W&B Weave dashboard provides a complete trace waterfall for compliance and performance review.
- **No external dependency for evaluation.** The built-in evaluation suite (LLM-as-judge) measures agent response quality — relevance, financial accuracy, actionability, and tool coverage — on every release.
- **Minimal operational footprint.** Runs as a single Python process with no microservices, no container orchestration, and no mandatory external APIs. Optional integrations (Intex, W&B, LDAP) are all gracefully degraded when unavailable.
