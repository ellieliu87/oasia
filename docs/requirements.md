# Oasia (NEXUS) — Functional & Technical Requirements

> **Maintenance rule:** Every code change that adds, removes, or modifies a feature, agent, tool, UI tab, data source, configuration key, or API endpoint **must** be reflected in the relevant section of this document before the PR is merged.

---

## Table of Contents

1. [Overview](#1-overview)
2. [User Roles and Access](#2-user-roles-and-access)
3. [Authentication](#3-authentication)
4. [Application Architecture](#4-application-architecture)
5. [UI Requirements — Pages and Tabs](#5-ui-requirements--pages-and-tabs)
   - 5.1 [Dashboard](#51-dashboard)
   - 5.2 [Portfolio Analytics](#52-portfolio-analytics)
   - 5.3 [Security Analytics](#53-security-analytics)
   - 5.4 [Security Selection](#54-security-selection)
   - 5.5 [Attribution](#55-attribution)
   - 5.6 [What-If Sandbox](#56-what-if-sandbox)
   - 5.7 [Portfolio Planning](#57-portfolio-planning)
   - 5.8 [Watchlist](#58-watchlist)
   - 5.9 [Agent Chat Panel](#59-agent-chat-panel)
6. [Agent Requirements — NEXUS Chat Panel](#6-agent-requirements--nexus-chat-panel)
   - 6.1 [Orchestrator Agent](#61-orchestrator-agent)
   - 6.2 [Security Selection Agent](#62-security-selection-agent)
   - 6.3 [What-If Analysis Agent](#63-what-if-analysis-agent)
   - 6.4 [Portfolio Analytics Agent](#64-portfolio-analytics-agent)
   - 6.5 [Attribution Agent](#65-attribution-agent)
   - 6.6 [Market Data Agent](#66-market-data-agent)
   - 6.7 [Dashboard Agent](#67-dashboard-agent)
7. [Agent Requirements — Portfolio Planning Workflow](#7-agent-requirements--portfolio-planning-workflow)
   - 7.1 [New Volume Agent](#71-new-volume-agent)
   - 7.2 [Risk Assessment Agent](#72-risk-assessment-agent)
   - 7.3 [Allocation Agent](#73-allocation-agent)
   - 7.4 [MBS Decomposition Agent](#74-mbs-decomposition-agent)
8. [Analytics Engine Requirements](#8-analytics-engine-requirements)
9. [Tool Registry Requirements](#9-tool-registry-requirements)
10. [Data Requirements](#10-data-requirements)
11. [Database Requirements](#11-database-requirements)
12. [Portfolio Planning Workflow — Gate Logic](#12-portfolio-planning-workflow--gate-logic)
13. [Evaluation Framework](#13-evaluation-framework)
14. [Observability and Tracing](#14-observability-and-tracing)
15. [Background Scheduler](#15-background-scheduler)
16. [Configuration and Environment Variables](#16-configuration-and-environment-variables)
17. [Non-Functional Requirements](#17-non-functional-requirements)
18. [Dependencies](#18-dependencies)
19. [Testing Requirements](#19-testing-requirements)
20. [Change Log](#20-change-log)

---

## 1. Overview

**Application name:** Oasia (also referred to as NEXUS internally)
**Domain:** Agency Mortgage-Backed Securities (Agency MBS) portfolio management
**Primary users:** Institutional fixed-income portfolio managers, traders, and risk analysts
**Deployment:** Browser-based single-page application (SPA); FastAPI + Gradio 6; can run on-premises or in a private cloud

**Purpose:**
Oasia is an AI-powered analytics workbench and decision-support platform for trading desks managing Agency MBS portfolios. It combines quantitative analytics (OAS, OAD, EVE, prepayment modelling), a 7-agent AI chat assistant, and a 4-phase human-in-the-loop purchase-planning workflow to support the full investment lifecycle: screening → risk assessment → allocation → execution planning.

**Asset classes supported:**

| Code | Description |
|------|-------------|
| CC30 | Conventional 30-year fixed-rate MBS |
| CC15 | Conventional 15-year fixed-rate MBS |
| GN30 | Ginnie Mae (GNMA) 30-year fixed-rate MBS |
| GN15 | Ginnie Mae (GNMA) 15-year fixed-rate MBS |
| ARM | Adjustable-rate MBS |
| CMBS | Commercial MBS |
| TSY | US Treasury securities |

---

## 2. User Roles and Access

| Role | Description | Access Level |
|------|-------------|--------------|
| **Portfolio Manager** | Primary user; views analytics, executes planning workflow, interacts with agents | Full read/write |
| **Risk Analyst** | Monitors EVE, duration, concentration limits | Full read; Gate decisions read-only |
| **Trader** | Executes purchase-planning gates; commits final purchase schedule | Full read/write including gate approvals |
| **Admin** | Manages LDAP configuration, schedules, environment variables | Full system access |
| **Read-Only** | Auditors, executives | Read-only across all tabs; no agent chat |

> Role-based access control (RBAC) is not yet implemented in the UI layer. All authenticated users currently have full access. RBAC is planned for a future release.

---

## 3. Authentication

**Mechanism:** LDAP / Active Directory
**Implementation:** `/auth/ldap_auth.py`, `/auth/middleware.py`, `/auth/session.py`

### 3.1 Requirements

- REQ-AUTH-001: All HTTP requests to the application (except internal Gradio API routes `/gradio_api/*` and static assets `/static/*`) **must** be authenticated.
- REQ-AUTH-002: Unauthenticated requests **must** be redirected to `/login`.
- REQ-AUTH-003: Authentication is performed by binding to an LDAP/Active Directory server using the configured DN template (`LDAP_USER_DN_TEMPLATE`).
- REQ-AUTH-004: A successful login **must** set a signed, HTTP-only session cookie with an 8-hour expiry.
- REQ-AUTH-005: Logout at `GET /logout` **must** clear the session cookie and redirect to `/login`.
- REQ-AUTH-006: A mock authentication mode (`LDAP_SERVER=mock://`) **must** be available for local development. Any username with password equal to `LDAP_MOCK_PASSWORD` (default: `oasis-test`) **must** authenticate successfully.
- REQ-AUTH-007: SSL for LDAP connections is controlled by `LDAP_USE_SSL`. When `true`, the connection **must** use `ldaps://`.

### 3.2 Login Page

- REQ-AUTH-008: The login page **must** render a dark-themed HTML form with username and password fields.
- REQ-AUTH-009: Failed authentication **must** display a generic error message without revealing whether the username or password was incorrect.
- REQ-AUTH-010: After successful authentication, the user **must** be redirected to the application root (`/`).

---

## 4. Application Architecture

### 4.1 Web Framework

- **FastAPI** serves as the top-level ASGI application.
- **Gradio 6** is mounted at `/` via `gr.mount_gradio_app`.
- **Uvicorn** is the ASGI server (`GRADIO_PORT`, default 7860).
- Auth middleware (Starlette) intercepts every request before it reaches Gradio.

### 4.2 Layout

- REQ-LAYOUT-001: The application **must** present a 3-column layout: (1) left sidebar navigation, (2) main content area (tabbed), (3) floating AI chat popup.
- REQ-LAYOUT-002: The sidebar **must** list all navigation tabs and highlight the active tab.
- REQ-LAYOUT-003: The floating chat popup **must** be accessible from any tab without navigating away.
- REQ-LAYOUT-004: The chat popup header **must** display the Oasia agent icon (✦), the agent name ("Oasia Agent"), and the status line "7 agents · OpenAI SDK".
- REQ-LAYOUT-005: All visual properties in the chat popup header **must** use inline `style=""` attributes (not CSS classes) to prevent override by Gradio wrapper styles.

### 4.3 Agent Systems

Two separate agent systems exist in parallel:

| System | Technology | Tracing |
|--------|-----------|---------|
| NEXUS Chat Panel (7 agents) | Raw OpenAI client (`openai.OpenAI().chat.completions.create`) + OpenAI Agents SDK `agents.trace()` | W&B Weave (via SDK patch) + OpenAI platform (via `agents.trace`) |
| Portfolio Planning Workflow (4 agents) | OpenAI Agents SDK (`Runner.run` via `weave_runner.run_phase`) | W&B Weave (via `@weave.op`) + OpenAI platform (automatic SDK instrumentation) |

---

## 5. UI Requirements — Pages and Tabs

### 5.1 Dashboard

**File:** `ui/dashboard.py`

#### KPI Cards (top row)

| Card | Metric | Source | Unit |
|------|--------|--------|------|
| NAV | Total portfolio net asset value | `get_portfolio_summary` | $MM |
| Book Yield | Weighted-average book yield across positions | DB `portfolio_kpis` or position aggregation | % |
| OAD | Weighted-average option-adjusted duration | `get_portfolio_summary` | years |
| OAS | Weighted-average option-adjusted spread | `get_portfolio_summary` | bps |

- REQ-DASH-001: The Book Yield card **must** display the value as a percentage (e.g., 5.44%). Values stored in the DB as raw decimals (< 1.0) **must** be multiplied by 100; values stored as already-percent (> 1.0 and < 50) **must** be displayed as-is; values > 50 (stale records incorrectly scaled) **must** be divided by 100 before display.
- REQ-DASH-002: KPI cards **must** show a coloured trend indicator (green/red arrow) comparing current to the prior month's value.
- REQ-DASH-003: All KPI card values **must** reload when the user triggers a dashboard refresh.

#### NAV History Chart

- REQ-DASH-004: A line chart **must** display monthly NAV history for the prior 6 months.
- REQ-DASH-005: The chart **must** overlay a 30-year NAV projection using the runoff discount model from `db/projections.py`.
- REQ-DASH-006: Projected values **must** be visually distinguished (dashed line or different colour) from historical actuals.

#### Portfolio Health Scorecard

- REQ-DASH-007: A 6-dimension spider/radar chart **must** score: Duration Risk, Convexity, Credit Quality, Liquidity, Concentration, and Yield.
- REQ-DASH-008: Each dimension **must** be scored 0–10 and display a colour-coded status (green ≥ 7, amber 4–6, red < 4).

#### Holdings Table

- REQ-DASH-009: A sortable, paginated table **must** list all positions with columns: Pool ID, Product Type, Coupon, Par Value ($MM), Book Price, Market Price, Book Yield (%), OAS (bps), OAD (yr), Unrealised P&L ($MM), Unrealised P&L (%).
- REQ-DASH-010: The table **must** support filtering by product type.
- REQ-DASH-011: Clicking a row **must** navigate to the Security Analytics tab pre-populated with that pool's CUSIP.

#### Sector Exposure Chart

- REQ-DASH-012: A pie (or donut) chart **must** display portfolio book-value allocation by product type (CC30, CC15, GN30, GN15, ARM, CMBS, TSY).

#### Top 5 YTD Performers

- REQ-DASH-013: A ranked list **must** display the 5 pools with highest YTD total return, showing pool ID, product type, and YTD return (%).

#### Watchlist Panel

- REQ-DASH-014: The dashboard **must** display the user's watchlist (subset of universe pools) with current OAS and OAD.
- REQ-DASH-015: Pools **must** be addable and removable from the watchlist directly on the dashboard.

---

### 5.2 Portfolio Analytics

**File:** `ui/portfolio_analytics.py`

- REQ-PA-001: The tab **must** display EVE stress test results for rate shocks of −300, −200, −100, 0, +100, +200, +300 bps in a table and chart.
- REQ-PA-002: EVE values **must** be expressed as % change from base-case portfolio value.
- REQ-PA-003: Any EVE result breaching the limit (`EVE_LIMIT_PCT`, default −5%) **must** be highlighted in red with a breach alert message.
- REQ-PA-004: A "Run Analytics" button **must** trigger a full analytics recalculation for all positions and persist results to DuckDB.
- REQ-PA-005: The tab **must** display duration and convexity profiles: a bar chart of OAD contribution by pool, and overall portfolio convexity.
- REQ-PA-006: A book-yield breakdown table **must** list each position's contribution to portfolio book yield.
- REQ-PA-007: KPI trend charts **must** display OAS, OAD, and book yield over the prior 6-month snapshot history.
- REQ-PA-008: A warning **must** be displayed if no portfolio run exists in the DB (`get_latest_portfolio_kpis() is None`), advising the user to run Portfolio Analytics first.

---

### 5.3 Security Analytics

**File:** `ui/security_analytics.py`

- REQ-SA-001: A pool screener **must** support the following filter dimensions: product type (multi-select), OAS range (min/max bps), OAD range (min/max yr), coupon range (min/max %), FICO floor, max LTV, free-text search.
- REQ-SA-002: Screener results **must** be returned sorted by OAS descending by default.
- REQ-SA-003: If no portfolio run exists in DB, a simplified-approximation warning **must** be displayed. The warning **must not** be triggered solely because `INTEX_API_KEY` is absent.
- REQ-SA-004: A CUSIP / Pool ID lookup field **must** retrieve single-pool details: OAS, Z-spread, OAD, modified duration, convexity, yield, model price vs market price, and model CPR.
- REQ-SA-005: A rate-shock comparison table **must** show OAS, OAD, and price for the selected pool under −200, −100, 0, +100, +200, +300 bps scenarios.

---

### 5.4 Security Selection

**File:** `ui/security_selection.py`

- REQ-SS-001: The tab **must** display the full pool universe with relative-value labels: CHEAP, FAIR, or RICH, based on OAS vs cohort median.
- REQ-SS-002: The scoring model **must** use: OAS percentile rank within product-type cohort, OAD alignment with portfolio target, credit quality score (FICO, LTV).
- REQ-SS-003: Results **must** be filterable by product type and sortable by any column.
- REQ-SS-004: A "Compare to Portfolio" view **must** show how candidate pools change portfolio OAS, OAD, and EVE if added.
- REQ-SS-005: Users **must** be able to export the screened universe to CSV.
- REQ-SS-006: Pools **must** be addable to the watchlist directly from this tab.

---

### 5.5 Attribution

**File:** `ui/attribution.py`

- REQ-AT-001: The tab **must** decompose period-over-period portfolio P&L into: OAS change contribution, OAD (carry/roll) contribution, yield (income) contribution, and EVE change.
- REQ-AT-002: Attribution **must** be available at the portfolio level and per-position level.
- REQ-AT-003: Side-by-side snapshot tables **must** display the start-of-period and end-of-period values for each position.
- REQ-AT-004: The attribution period **must** be user-selectable (monthly, quarterly, custom date range).
- REQ-AT-005: Attribution results **must** be exportable as a formatted Markdown memo.

---

### 5.6 What-If Sandbox

**File:** `ui/whatif_sandbox.py`

- REQ-WI-001: The sandbox **must** allow the user to modify individual pool parameters: CPR (prepayment speed), WAC (weighted-average coupon), loan size, LTV, FICO, and spread assumption.
- REQ-WI-002: Modified analytics (OAS, OAD, convexity, price) **must** be computed and displayed in real time (on button click).
- REQ-WI-003: A parallel rate-shock scenario table **must** show modified-pool analytics under −200, −100, 0, +100, +200, +300 bps shifts.
- REQ-WI-004: Before/after comparison **must** be displayed side by side.
- REQ-WI-005: If no portfolio run exists in DB, a simplified-approximation warning **must** be shown. The warning **must not** be triggered by the absence of `INTEX_API_KEY`.

---

### 5.7 Portfolio Planning

**File:** `ui/portfolio_planning.py`

See [Section 12](#12-portfolio-planning-workflow--gate-logic) for full gate logic requirements.

- REQ-PP-001: The tab **must** present a stepper UI showing the current phase and all completed/pending phases.
- REQ-PP-002: Agent output for each phase **must** be rendered as formatted Markdown with loading spinners while the agent is running.
- REQ-PP-003: Each gate **must** present structured decision options (approve, modify, reject) and capture the trader's choice and any notes.
- REQ-PP-004: The full `WorkflowState` **must** be persisted to a JSON file after each phase and gate, enabling session resumption.
- REQ-PP-005: A "Resume Session" option **must** be available to reload and continue an interrupted workflow.
- REQ-PP-006: All planning-agent calls **must** go through `workflow.weave_runner.run_phase()` so every phase execution is captured as a Weave op.
- REQ-PP-007: The tab **must** display an abort confirmation before terminating a workflow mid-session.

---

### 5.8 Watchlist

**File:** `ui/watchlist.py`

- REQ-WL-001: The watchlist **must** persist across sessions (stored in `data/watchlist.json`).
- REQ-WL-002: Pools **must** be addable by entering a pool ID or CUSIP.
- REQ-WL-003: The watchlist table **must** display: Pool ID, Product Type, Coupon, Current OAS (bps), OAD (yr), Book Price, Market Price, Unrealised P&L ($MM and %).
- REQ-WL-004: Users **must** be able to remove individual pools from the watchlist.
- REQ-WL-005: One-click navigation to Security Analytics **must** be available for any watchlist pool.

---

### 5.9 Agent Chat Panel

**File:** `ui/agent_panel.py`

- REQ-AGENT-001: The panel **must** be a floating popup accessible from every tab without page navigation.
- REQ-AGENT-002: The chat interface **must** support multi-turn conversation (history maintained within a session).
- REQ-AGENT-003: The panel **must** display the current portfolio context (OAS, OAD, book yield, EVE +200) to the orchestrator on each message.
- REQ-AGENT-004: Users **must** be able to clear conversation history via a "Clear" button.
- REQ-AGENT-005: Pre-wired "Quick Query" buttons **must** be available for common prompts (e.g., "Morning Brief", "EVE Status", "Screen Cheap CC30").

---

## 6. Agent Requirements — NEXUS Chat Panel

**Implementation:** `agent/orchestrator.py`, `agent/base_agent.py`, `agent/skill_loader.py`
**Skill definitions:** `agent/skills/*.md` (YAML frontmatter + Markdown body)
**Model:** GPT-4o (configurable per skill via `model:` frontmatter key)

### 6.1 Orchestrator Agent

**Skill file:** `agent/skills/orchestrator.md`

- REQ-ORCH-001: The orchestrator **must** route every user message to one or more specialist sub-agents via `delegate_to_<agent_name>` tools.
- REQ-ORCH-002: The orchestrator **must** synthesise sub-agent responses into a single, coherent reply to the user.
- REQ-ORCH-003: The orchestrator **must** inject today's date and the current portfolio summary (OAS, OAD, yield, EVE +200) into its system prompt at every call.
- REQ-ORCH-004: The orchestrator **must** wrap its entire chat loop in `agents.trace("nexus_orchestrator")` to produce a top-level trace on the OpenAI platform dashboard.
- REQ-ORCH-005: The orchestrator **must** not be given direct access to analytics tools; it may only call specialist agents.
- REQ-ORCH-006: When no `OPENAI_API_KEY` is set, the orchestrator **must** return a helpful stub response indicating that the key is required, without raising an exception.

### 6.2 Security Selection Agent

**Skill file:** `agent/skills/security_selection.md`
**Permitted tools:** `screen_securities`, `get_pool_details`, `compute_single_bond_analytics`, `get_market_data`

- REQ-SS-AG-001: The agent **must** screen the universe by OAS, OAD, coupon, FICO, LTV, and product type when asked.
- REQ-SS-AG-002: The agent **must** compute relative value labels (CHEAP/FAIR/RICH) using cohort OAS percentile ranks.
- REQ-SS-AG-003: The agent **must** be able to compare a candidate pool's analytics against the portfolio.

### 6.3 What-If Analysis Agent

**Skill file:** `agent/skills/what_if_analysis.md`
**Permitted tools:** `run_what_if`, `compute_bond_analytics`, `run_scenario_analysis`, `get_pool_details`

- REQ-WI-AG-001: The agent **must** reprice a pool after modifying CPR, WAC, LTV, FICO, or spread assumptions.
- REQ-WI-AG-002: The agent **must** run parallel rate-shock scenarios and present before/after analytics.

### 6.4 Portfolio Analytics Agent

**Skill file:** `agent/skills/portfolio_analytics.md`
**Permitted tools:** `get_portfolio_summary`, `get_portfolio_positions`, `compute_eve_profile`, `get_market_data`

- REQ-PA-AG-001: The agent **must** retrieve and summarise portfolio OAS, OAD, book yield, and EVE.
- REQ-PA-AG-002: The agent **must** flag EVE breaches automatically when reporting the EVE profile.

### 6.5 Attribution Agent

**Skill file:** `agent/skills/attribution.md`
**Permitted tools:** `get_attribution`, `get_portfolio_summary`, `get_portfolio_positions`

- REQ-AT-AG-001: The agent **must** decompose period P&L into OAS change, OAD, yield, and EVE contributions.

### 6.6 Market Data Agent

**Skill file:** `agent/skills/market_data.md`
**Permitted tools:** `get_market_data`

- REQ-MD-AG-001: The agent **must** retrieve and summarise the current SOFR and Treasury term structures.
- REQ-MD-AG-002: The agent **must** report cohort OAS levels by product type.

### 6.7 Dashboard Agent

**Skill file:** `agent/skills/dashboard.md`
**Permitted tools:** `get_nav_projection`, `get_top_performers`, `get_sector_allocation`, `get_portfolio_health`, `get_watchlist`, `get_planning_session`

- REQ-DASH-AG-001: The agent **must** answer questions about NAV, NAV projection, top performers, sector allocation, health scorecard, watchlist contents, and the current planning session status.

### 6.8 General Agent Requirements (all NEXUS agents)

- REQ-AG-GENERAL-001: Each agent's behaviour **must** be fully defined by its `agent/skills/<name>.md` file (system prompt + tool list + model). No agent behaviour changes require Python code edits.
- REQ-AG-GENERAL-002: Each sub-agent invocation **must** be wrapped in `agents.tracing.custom_span(f"delegate:<agent_name>")` for granular OpenAI platform visibility.
- REQ-AG-GENERAL-003: Each tool call within a sub-agent **must** be wrapped in `agents.tracing.custom_span(f"tool:<tool_name>")`.
- REQ-AG-GENERAL-004: All agent chat calls **must** be decorated with `@weave.op` (via `weave_config.weave_op()`) so every invocation is captured in W&B Weave.
- REQ-AG-GENERAL-005: If the OpenAI Agents SDK `custom_span` or `trace` are unavailable (import error), agents **must** degrade gracefully and continue operating without tracing.
- REQ-AG-GENERAL-006: Each `BaseAgent` **must** enforce a maximum of 10 tool-call iterations per chat turn (`MAX_ITERATIONS = 10`) to prevent runaway loops.

---

## 7. Agent Requirements — Portfolio Planning Workflow

**Implementation:** `workflow/agents/*.py`, `workflow/skills/*.md`
**Skill loader:** `workflow/skills/skill_loader.py` (`SkillLoader` + `Skill.build()`)
**Agent runner:** `workflow/weave_runner.py` (`run_phase()`)
**State model:** `workflow/models/workflow_state.py` (`WorkflowState`)

### 7.1 New Volume Agent

**Skill file:** `workflow/skills/new_volume_agent.md`
**Tools:** `compute_new_volume_schedule`, `compute_volume_timing_analysis`, `summarise_pool_universe`

- REQ-NV-001: Given a target total portfolio balance and a time horizon, the agent **must** produce a month-by-month schedule of required new purchases.
- REQ-NV-002: The schedule **must** account for expected runoff (prepayments + scheduled amortisation) on existing balances.
- REQ-NV-003: The agent **must** output a `MonthlyVolume` list stored in `WorkflowState.monthly_volumes`.
- REQ-NV-004: The agent **must** summarise the 12-month and 10-year total new volume figures.

### 7.2 Risk Assessment Agent

**Skill file:** `workflow/skills/risk_agent.md`
**Tools:** `assess_portfolio_risk`, `estimate_duration_impact`, `get_risk_constraints_summary`

- REQ-RA-001: The agent **must** evaluate proposed new volumes against the following hard limits: duration 3.5–6.5 yr, liquidity score ≥ 6.0, max CMBS 30%, max ARM 20%.
- REQ-RA-002: The agent **must** project portfolio OAD after the proposed purchases and flag any breach.
- REQ-RA-003: The agent **must** output a `RiskConstraints` object stored in `WorkflowState.risk_constraints`.
- REQ-RA-004: Risk appetite (`conservative`, `moderate`, `aggressive`) **must** influence the recommended duration target.

### 7.3 Allocation Agent

**Skill file:** `workflow/skills/allocation_agent.md`
**Tools:** `generate_allocation_scenarios`, `select_allocation_scenario`, `estimate_duration_impact`

- REQ-AL-001: The agent **must** produce exactly three allocation scenarios: Conservative, Moderate, and Aggressive.
- REQ-AL-002: Each scenario **must** specify: MBS%, CMBS%, Treasury%, total dollar amounts ($MM), projected portfolio OAD, projected liquidity score, projected yield (%), and a plain-language rationale.
- REQ-AL-003: All three scenarios **must** satisfy the risk constraints from Phase 2 (no scenario may breach a hard limit).
- REQ-AL-004: The agent **must** support a custom allocation option where the trader overrides percentages directly.
- REQ-AL-005: The selected scenario **must** be stored in `WorkflowState.selected_scenario`.

### 7.4 MBS Decomposition Agent

**Skill file:** `workflow/skills/mbs_decomposition_agent.md`
**Tools:** `decompose_mbs_allocation`, `build_purchase_schedule`, `estimate_duration_impact`

- REQ-MD-AG-WF-001: Given the MBS dollar amount from the selected allocation scenario, the agent **must** break it into sub-product buckets: FNMA Fixed 30yr, FHLMC Fixed 30yr, GNMA Fixed 30yr, FNMA Fixed 15yr, FHLMC Fixed 15yr, ARM.
- REQ-MD-AG-WF-002: The decomposition **must** target specific OAS, OAD, and FICO criteria passed in the planning context.
- REQ-MD-AG-WF-003: The agent **must** produce a final `PurchaseScheduleItem` list with: product type, sub-type, amount ($MM), target coupon range, target duration, target OAS, and execution priority.
- REQ-MD-AG-WF-004: The final purchase schedule **must** be stored in `WorkflowState.purchase_schedule`.

### 7.5 General Workflow Agent Requirements

- REQ-WF-GENERAL-001: Every planning-agent call **must** go through `workflow.weave_runner.run_phase(agent_name, agent, prompt, context=state)` so each phase is traced as a `@weave.op` in W&B Weave.
- REQ-WF-GENERAL-002: Planning agents **must** receive the full `WorkflowState` as the `context` parameter so they have access to all upstream outputs.
- REQ-WF-GENERAL-003: Planning agents are built via `SkillLoader.load(<skill_file>).build()` using the workflow `ToolRegistry`. No manual `Agent()` construction is permitted.

---

## 8. Analytics Engine Requirements

**Location:** `analytics/`

### 8.1 OAS Solver

**File:** `analytics/oas_solver.py`

- REQ-OAS-001: The solver **must** compute OAS by finding the spread (via Brent's method) that equates the model price to the market price when discounting cash flows on Monte Carlo rate paths.
- REQ-OAS-002: The solver **must** output: OAS (bps), Z-spread (bps), OAD (years), modified duration, convexity, yield-to-maturity (%), model price, market price, and model CPR (%).
- REQ-OAS-003: Results **must** be returned as a `BondAnalytics` dataclass.
- REQ-OAS-004: OAD **must** be computed as the price sensitivity to a 1 bp parallel shift in the OAS curve (numerical differentiation).

### 8.2 Rate Path Generation

**File:** `analytics/rate_paths.py`

- REQ-RP-001: The system **must** support Hull-White one-factor short-rate Monte Carlo simulation as the primary rate-path model.
- REQ-RP-002: The number of Monte Carlo paths **must** be configurable via `N_RATE_PATHS` (default: 256; minimum: 64 for projection sub-tasks).
- REQ-RP-003: Simulations **must** support parallel rate shocks (constant shift to the initial term structure) before path generation.
- REQ-RP-004: Results **must** be stored as a `RatePaths` dataclass with `short_rates` and `discount_factors` arrays of shape `(n_paths, n_periods)`.
- REQ-RP-005: The BGM term-structure model (`analytics/bgm_model.py`) **must** be available as an alternative model.

### 8.3 Prepayment Model

**File:** `analytics/prepay.py`, `analytics/neural_prepay.py`

- REQ-PP-002: The system **must** use a trained neural network (`data/models/prepay_model.pkl`) as the primary prepayment model.
- REQ-PP-003: The model **must** predict CPR per path/period based on: refi incentive (WAC vs current rates), seasoning (WALA), geography (pct_ca), credit quality (FICO, LTV), and loan size.
- REQ-PP-004: If the trained model file is absent, the system **must** fall back to a deterministic stub prepayment model without raising an error.

### 8.4 Cash Flow Generation

**File:** `analytics/cashflows.py`

- REQ-CF-001: Cash flows **must** be generated by the Intex API client when `INTEX_API_KEY` is configured.
- REQ-CF-002: When `INTEX_API_KEY` is not configured, the `MockIntexClient` **must** be used automatically; the system **must** remain fully functional with synthetic cash flows.
- REQ-CF-003: Cash flow results **must** be disk-cached with a 1-day TTL to avoid redundant API calls.

### 8.5 Scenario Analysis

**File:** `analytics/scenarios.py`

- REQ-SCEN-001: Scenario analysis **must** support parallel rate shocks of −300, −200, −100, 0, +100, +200, +300 bps.
- REQ-SCEN-002: Each scenario **must** compute: price delta ($ and %), OAS delta (bps), OAD delta (years), convexity delta vs the base case.

### 8.6 EVE Computation

**File:** `analytics/risk.py`

- REQ-EVE-001: EVE **must** be computed as: (portfolio PV at rate shock − portfolio PV at base) / portfolio PV at base × 100%.
- REQ-EVE-002: Rate shocks applied for EVE: −300, −200, −100, 0, +100, +200, +300 bps.
- REQ-EVE-003: A breach **must** be flagged whenever EVE at +200 bps < `EVE_LIMIT_PCT` (default: −5%).

---

## 9. Tool Registry Requirements

**Location:** `tool/`, `workflow/tools/`

### 9.1 NEXUS Agent Tools

All tools listed below **must** be available to NEXUS chat panel agents via `agent/tools.py` → `OPENAI_TOOLS` list.

| Tool Name | Module | Description |
|-----------|--------|-------------|
| `screen_securities` | `data_tool.py` | Filter pool universe by OAS, OAD, coupon, FICO, LTV, product type |
| `get_pool_details` | `data_tool.py` | Retrieve all characteristics for a single pool ID |
| `get_market_data` | `data_tool.py` | SOFR/Treasury term structure and cohort OAS levels |
| `get_universe_summary` | `data_tool.py` | Aggregate statistics across the universe |
| `query_risk_metrics` | `db_tool.py` | Query DuckDB for cached OAS/OAD/convexity |
| `query_prepay_speeds` | `db_tool.py` | Query historical CPR data |
| `query_interest_income` | `db_tool.py` | Query projected monthly income |
| `get_cache_status` | `db_tool.py` | Report DuckDB cache fill rate |
| `run_sql_query` | `db_tool.py` | Execute a read-only SQL query against DuckDB |
| `generate_rate_paths` | `term_structure_tool.py` | Generate Hull-White rate paths |
| `get_rate_path_summary` | `term_structure_tool.py` | Statistical summary of simulated rate paths |
| `forecast_prepayment` | `prepay_tool.py` | CPR forecast for given pool characteristics |
| `compare_prepayment_scenarios` | `prepay_tool.py` | CPR under different rate/credit regimes |
| `compute_interest_income` | `interest_income_tool.py` | Monthly income projection for one pool |
| `compute_portfolio_interest_income` | `interest_income_tool.py` | Aggregate portfolio income projection |
| `compute_bond_analytics` | `analytics_tool.py` | OAS, OAD, convexity, yield for a pool |
| `batch_compute_analytics` | `analytics_tool.py` | Bulk analytics for multiple pools |
| `get_portfolio_summary` | `portfolio_tool.py` | Weighted portfolio KPIs |
| `get_portfolio_positions` | `portfolio_tool.py` | Position-level detail for all holdings |
| `compute_eve_profile` | `portfolio_tool.py` | EVE across rate shocks |
| `get_attribution` | `portfolio_tool.py` | Period P&L attribution decomposition |
| `run_scenario_analysis` | `scenario_tool.py` | Parallel rate-shock repricing |
| `run_what_if` | `scenario_tool.py` | Pool repricing after parameter modification |
| `get_nav_projection` | `dashboard_tool.py` | 30-year NAV runoff projection |
| `get_top_performers` | `dashboard_tool.py` | YTD top/bottom performing pools |
| `get_sector_allocation` | `dashboard_tool.py` | Book-value breakdown by product type |
| `get_portfolio_health` | `dashboard_tool.py` | 6-dimension health scorecard |
| `get_watchlist` | `dashboard_tool.py` | Watchlist contents with current analytics |
| `get_planning_session` | `dashboard_tool.py` | Current portfolio planning session state |

- REQ-TOOLS-001: Every tool **must** be defined as an OpenAI function-calling schema (JSON) in `OPENAI_TOOLS` and have a corresponding handler in `handle_tool_call`.
- REQ-TOOLS-002: Tool handlers **must** return a JSON-serialisable string. Errors **must** be returned as `{"error": "...", "traceback": "..."}` — they **must not** raise exceptions to the agent.
- REQ-TOOLS-003: Any new tool **must** be added to: (1) the OpenAI tool schema list, (2) the handler dispatch, (3) the skill file's `tools:` frontmatter for the relevant agent, and (4) this requirements document.

### 9.2 Workflow Agent Tools

Workflow tools are registered via `workflow/tools/tool_registry.py` → `ToolRegistry.default()`.

| Tool Name | Module | Agent |
|-----------|--------|-------|
| `compute_new_volume_schedule` | `computation.py` | New Volume |
| `compute_volume_timing_analysis` | `computation.py` | New Volume |
| `summarise_pool_universe` | `computation.py` | New Volume |
| `assess_portfolio_risk` | `risk_tools.py` | Risk Assessment |
| `estimate_duration_impact` | `risk_tools.py` | Risk Assessment, Allocation, MBS Decomp |
| `get_risk_constraints_summary` | `risk_tools.py` | Risk Assessment |
| `generate_allocation_scenarios` | `allocation_tools.py` | Allocation |
| `select_allocation_scenario` | `allocation_tools.py` | Allocation |
| `decompose_mbs_allocation` | `allocation_tools.py` | MBS Decomposition |
| `build_purchase_schedule` | `allocation_tools.py` | MBS Decomposition |

---

## 10. Data Requirements

### 10.1 Pool Universe

**File:** `data/pool_universe.py`

- REQ-DATA-001: The pool universe **must** contain at least 1,000 synthetic Agency MBS pools covering CC30, CC15, GN30, and GN15 product types.
- REQ-DATA-002: Each pool record **must** include: pool_id, product_type, coupon, WAC, WALA, WAM, LTV, FICO, pct_ca, pct_purchase, loan_size, current_balance, market_price, market_cpr_1m.

### 10.2 Portfolio Positions

**File:** `data/position_data.py`

- REQ-DATA-003: The portfolio **must** contain at least 6 historical monthly snapshots.
- REQ-DATA-004: Each position record **must** include: pool_id, product_type, coupon, par_value, book_price, book_yield, OAS (bps), OAD (years), unrealised P&L.
- REQ-DATA-005: Book yield in position data **must** be stored as a percentage value (e.g., 5.44 for 5.44%), not as a decimal.

### 10.3 Market Data

**File:** `data/market_data.py`

- REQ-DATA-006: Market data **must** include the SOFR zero-rate curve and US Treasury par-rate curve.
- REQ-DATA-007: Cohort OAS levels (typical spread for each product-type/coupon bucket) **must** be available.
- REQ-DATA-008: Market data **must** be refreshable at runtime without restarting the application.

### 10.4 Intex API Client

**File:** `data/intex_client.py`

- REQ-DATA-009: When `INTEX_API_KEY` is set, the system **must** use the live Intex API for MBS cash flows.
- REQ-DATA-010: When `INTEX_API_KEY` is not set, the `MockIntexClient` **must** generate deterministic synthetic cash flows that produce analytically reasonable OAS, OAD, and convexity values.
- REQ-DATA-011: The Intex client interface **must** be interchangeable at runtime; no code path should require a specific client type.

---

## 11. Database Requirements

### 11.1 DuckDB — Main Analytics Store

**File:** `db/connection.py`
**Path:** `data/nexus_results.duckdb`

| Table | Key Columns | Purpose |
|-------|------------|---------|
| `rate_path_cache` | as_of_date, shock_bps, n_paths, seed, parquet_path | Pre-computed rate path statistics + pointer to full array |
| `risk_metrics_cache` | pool_id, as_of_date, market_price, shock_bps, n_paths | Pool-level analytics (OAS, OAD, convexity, EVE) |
| `portfolio_kpis` | as_of_date | Portfolio-level aggregates (weighted OAS, OAD, book yield, EVE) |
| `position_snapshots` | snapshot_date, pool_id | Historical position data for trend charts |

- REQ-DB-001: The DuckDB schema **must** be created idempotently on first connection (`CREATE TABLE IF NOT EXISTS`).
- REQ-DB-002: All DuckDB access **must** go through the singleton connection manager in `db/connection.py` with a threading lock to prevent concurrent write conflicts.
- REQ-DB-003: Risk metrics **must** be cached with a 1-day TTL; stale records may be skipped or overwritten on re-run.

### 11.2 SQLite — Historical Positions

**File:** `data/snapshot_store.py`
**Path:** `data/snapshots.db`

- REQ-DB-004: The SQLite DB **must** store all 6 historical monthly position snapshots.
- REQ-DB-005: Book yield values written to the DB **must** be in percent form. Values < 1.0 **must** be multiplied by 100 before storage. Values ≥ 1.0 **must** be stored as-is.

### 11.3 Projections

**File:** `db/projections.py`

- REQ-DB-006: The `get_latest_portfolio_kpis()` function **must** return `None` if no portfolio run exists in DuckDB (used by UI tabs to determine warning display).
- REQ-DB-007: NAV projections **must** use a 30-year runoff model discounting expected cash flows at the current portfolio yield.

### 11.4 Watchlist Store

**File:** `data/watchlist_store.py`
**Path:** `data/watchlist.json`

- REQ-DB-008: The watchlist **must** persist across application restarts (JSON file on disk).
- REQ-DB-009: The watchlist **must** support add, remove, and get-all operations.

---

## 12. Portfolio Planning Workflow — Gate Logic

**File:** `ui/portfolio_planning.py`
**State model:** `workflow/models/workflow_state.py`

### Workflow Phases

```
INIT → NEW_VOLUME → [Gate 1] → RISK_ASSESSMENT → [Gate 2]
     → ALLOCATION → [Gate 3] → MBS_DECOMPOSITION → [Gate 4]
     → FINAL_APPROVAL → [Gate 5] → COMPLETE
```

### Gate Specifications

| Gate | After Phase | Trader Options | On Approve | On Reject | On Modify |
|------|-------------|----------------|-----------|-----------|-----------|
| Gate 1 | New Volume | Approve, Modify target, Reject | Advance to Phase 2 | Abort workflow | Update target balance, re-run Phase 1 |
| Gate 2 | Risk Assessment | Accept, Adjust bounds, Reject | Advance to Phase 3 | Abort workflow | Update constraints, re-run Phase 2 |
| Gate 3 | Allocation | Select scenario (1–3), Custom %, Reject | Advance to Phase 4 | Abort workflow | Accept custom allocation, advance to Phase 4 |
| Gate 4 | MBS Decomposition | Approve, Modify percentages, Reject | Advance to Gate 5 | Abort workflow | Update MBS breakdown, re-run Phase 4 |
| Gate 5 | Final Approval | Confirm, Revise, Abort | Mark COMPLETE | Abort workflow | Loop back to Phase 3 (Allocation) |

- REQ-GATE-001: At Gate 3 "Revise" on Gate 5, the workflow **must** restart from Phase 3 (not Phase 1 or 2) to avoid re-running risk assessment unnecessarily.
- REQ-GATE-002: All gate decisions **must** be recorded in `WorkflowState.gate_decisions` as `GateDecision` objects with timestamp.
- REQ-GATE-003: An aborted workflow **must** preserve all state so the session can be reviewed but not continued.
- REQ-GATE-004: The workflow **must** support session persistence: after any gate, saving `WorkflowState` to JSON; on "Resume Session", loading the latest saved state.

---

## 13. Evaluation Framework

**Location:** `evals/`

### 13.1 NEXUS Chat Panel Evaluations

**Files:** `evals/run_evals.py`, `evals/dataset.py`

- REQ-EVAL-001: `EVAL_DATASET` **must** contain at least one test case for each NEXUS sub-agent type: `security_selection`, `what_if_analysis`, `portfolio_analytics`, `attribution`, `market_data`.
- REQ-EVAL-002: Each test case **must** include: `id`, `agent_type`, `question`, `context`, `expected_topics`, `expected_tools`.
- REQ-EVAL-003: The evaluation runner **must** support filtering by `agent_type` via `--agent` CLI argument.
- REQ-EVAL-004: All evaluation runs **must** be captured in W&B Weave under the configured project.

### 13.2 Portfolio Planning Workflow Evaluations

**Files:** `evals/run_workflow_evals.py`, `evals/dataset.py`

- REQ-EVAL-005: `PLANNING_EVAL_DATASET` **must** contain at least two test cases for each planning agent: `new_volume`, `risk_assessment`, `allocation`, `mbs_decomposition`.
- REQ-EVAL-006: Each planning test case **must** include: `id`, `agent_name`, `prompt`, `context`, `state_overrides`, `expected_topics`, `expected_tools`.
- REQ-EVAL-007: The planning evaluation runner **must** construct a valid `WorkflowState` from `state_overrides` before calling the agent.
- REQ-EVAL-008: All planning eval calls **must** go through `run_phase()` so they are captured as Weave ops.

### 13.3 Judges (both evaluation suites)

**File:** `evals/judges.py`

Four LLM-as-judge scorers **must** be applied to every evaluation response:

| Scorer | Pass Threshold | What It Measures |
|--------|---------------|-----------------|
| `RelevanceScorer` | score ≥ 0.6 | Response directly addresses the MBS question |
| `FinancialAccuracyScorer` | score ≥ 0.7 | Financial terms and metrics are correct |
| `ActionabilityScorer` | score ≥ 0.6 | Response gives specific, actionable data |
| `ToolCoverageScorer` | score ≥ 0.5 | Agent used the expected analytics tools |

- REQ-EVAL-009: Each scorer **must** return `{"score": float, "passed": bool, "reasoning": str}`.
- REQ-EVAL-010: Judge model **must** default to `gpt-4o` and **must** be overridable via `--judge-model` CLI argument or `WEAVE_JUDGE_MODEL` environment variable.

---

## 14. Observability and Tracing

**File:** `weave_config.py`

- REQ-OBS-001: On application startup, `init_weave()` **must** be called. If `WANDB_API_KEY` is not set, Weave **must** initialise in offline/no-op mode without raising an exception.
- REQ-OBS-002: After `init_weave()`, the OpenAI Python SDK **must** be automatically patched so all `chat.completions.create()` calls are captured in Weave traces.
- REQ-OBS-003: The `weave_op()` helper **must** return `weave.op` when Weave is installed and initialised, or a no-op decorator otherwise.
- REQ-OBS-004: NEXUS orchestrator chat calls **must** be wrapped in `agents.trace("nexus_orchestrator")` to produce a top-level trace visible in the OpenAI platform dashboard.
- REQ-OBS-005: Each sub-agent delegation **must** be wrapped in `custom_span(f"delegate:<agent_name>")`.
- REQ-OBS-006: Each tool call within a sub-agent **must** be wrapped in `custom_span(f"tool:<tool_name>")`.
- REQ-OBS-007: All Portfolio Planning agent calls **must** be wrapped in `run_phase()` decorated with `@_op` (Weave op).

---

## 15. Background Scheduler

**File:** `workflow/scheduler.py`

- REQ-SCHED-001: The scheduler **must** support configurable run frequencies: daily, weekly, and monthly.
- REQ-SCHED-002: Scheduled runs **must** execute the full analytics pipeline (market data refresh → rate path generation → pool analytics → KPI aggregation → projections).
- REQ-SCHED-003: Scheduler configuration (frequency, hour, enabled) **must** persist to a JSON file and survive application restarts.
- REQ-SCHED-004: Progress during a scheduled run **must** be reportable via a real-time progress callback (used by the UI for live status updates).
- REQ-SCHED-005: Scheduled runs **must** be async and non-blocking; they **must not** block the Gradio event loop.

---

## 16. Configuration and Environment Variables

**File:** `config.py`, `.env.example`

All configuration **must** be loaded from environment variables (or a `.env` file via `python-dotenv`). The following table is the single source of truth for all supported configuration keys.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes (for agents) | — | OpenAI API key; stub responses returned if absent |
| `WANDB_API_KEY` | No | — | W&B API key for Weave tracing |
| `WANDB_ENTITY` | No | — | W&B username or team name |
| `WANDB_PROJECT` | No | `nexus-mbs` | W&B project name for Weave traces |
| `INTEX_API_URL` | No | `https://api.intex.com/v1` | Intex API base URL |
| `INTEX_API_KEY` | No | — | Intex API key; `MockIntexClient` used if absent |
| `MARKET_DATA_DIR` | No | `./data/market_data` | Directory containing rate curve CSV files |
| `SNAPSHOT_DB_PATH` | No | `./data/snapshots.db` | SQLite historical positions database path |
| `NEXUS_DB_PATH` | No | `./data/nexus_results.duckdb` | DuckDB analytics database path |
| `CACHE_DIR` | No | `./data/cache` | Disk cache directory for analytics results |
| `N_RATE_PATHS` | No | `256` | Number of Monte Carlo rate paths |
| `PREPAY_MODEL_PATH` | No | `./data/models/prepay_model.pkl` | Path to trained neural prepayment model |
| `BGM_MODEL_PATH` | No | `./data/models/bgm_model.pkl` | Path to BGM term structure model |
| `UNIVERSE_PRODUCT_TYPES` | No | `CC30,CC15,GN30,GN15` | Comma-separated product types in universe |
| `EVE_LIMIT_PCT` | No | `-5.0` | EVE breach threshold (%) at +200 bps |
| `GRADIO_PORT` | No | `7860` | HTTP port for the Gradio/FastAPI server |
| `LDAP_SERVER` | No | `mock://` | LDAP server address; `mock://` for dev |
| `LDAP_USE_SSL` | No | `false` | Use `ldaps://` for LDAP connection |
| `LDAP_USER_DN_TEMPLATE` | No | `{username}@company.com` | DN template; `{username}` replaced at login |
| `LDAP_MOCK_PASSWORD` | No | `oasis-test` | Password accepted in mock LDAP mode |
| `WEAVE_JUDGE_MODEL` | No | `gpt-4o` | OpenAI model used for LLM-as-judge evaluations |

- REQ-CFG-001: Adding a new environment variable **must** require: (1) adding it to `config.py`, (2) adding it to `.env.example` with a comment, and (3) adding it to the table above.

---

## 17. Non-Functional Requirements

### 17.1 Performance

- REQ-NFR-001: Single-pool analytics (OAS, OAD, convexity) **must** complete in < 5 seconds when results are not cached.
- REQ-NFR-002: Dashboard KPI card load time **must** be < 2 seconds when portfolio KPIs are in DuckDB.
- REQ-NFR-003: Full universe analytics run (1,000 pools) **must** complete in < 30 minutes with 256 Monte Carlo paths.
- REQ-NFR-004: Agent chat responses **must** begin streaming within 3 seconds of user submission.

### 17.2 Reliability

- REQ-NFR-005: Any analytics computation failure for a single pool **must** be logged and skipped; it **must not** abort the full portfolio run.
- REQ-NFR-006: If the Intex API is unavailable, the system **must** fall back to `MockIntexClient` without user-visible errors.
- REQ-NFR-007: If W&B Weave is unavailable, all agent functionality **must** continue; only observability is degraded.

### 17.3 Security

- REQ-NFR-008: Session cookies **must** be signed (HMAC) and HTTP-only.
- REQ-NFR-009: SQL queries executed by the `run_sql_query` tool **must** be restricted to `SELECT` statements only.
- REQ-NFR-010: API keys **must** never be logged or returned in tool responses.

### 17.4 Maintainability

- REQ-NFR-011: Every agent's behaviour **must** be modifiable by editing its `.md` skill file without Python code changes.
- REQ-NFR-012: Every code change affecting a feature listed in this document **must** include an update to the relevant section and an entry in the [Change Log](#20-change-log).

---

## 18. Dependencies

**File:** `pyproject.toml`

| Package | Minimum Version | Purpose |
|---------|----------------|---------|
| `gradio` | 4.0 | Web UI framework |
| `openai` | 1.30 | OpenAI Python SDK |
| `openai-agents` | 0.0.9 | OpenAI Agents SDK (Portfolio Planning, platform tracing) |
| `numpy` | 1.24 | Numerical computing |
| `scipy` | 1.10 | OAS solver (Brent's method), statistics |
| `pandas` | 2.0 | Data manipulation |
| `plotly` | 5.0 | Interactive charts |
| `duckdb` | 1.0 | Analytical database |
| `weave` | 0.50 | W&B Weave tracing and evaluation |
| `pyyaml` | 6.0 | Skill file YAML frontmatter parsing |
| `python-dotenv` | 1.0 | `.env` file loading |
| `diskcache` | 5.6 | Disk-backed analytics caching |
| `scikit-learn` | 1.3 | Neural prepayment model |
| `apscheduler` | 3.10 | Background job scheduler |
| `ldap3` | 2.9 | LDAP/Active Directory authentication |
| `markdown` | 3.10.2 | Markdown parsing for agent skills |
| `aiofiles` | 23.0 | Async file I/O for state persistence |
| `uvicorn` | 0.27 | ASGI server |

---

## 19. Testing Requirements

**Location:** `tests/`

- REQ-TEST-001: Unit tests **must** cover: OAS solver, scenario analysis, attribution decomposition, book yield aggregation, cash flow generation, neural prepayment model, workflow state persistence, watchlist operations.
- REQ-TEST-002: All tests **must** run with `pytest tests/` without requiring `OPENAI_API_KEY`, `WANDB_API_KEY`, or `INTEX_API_KEY`.
- REQ-TEST-003: `conftest.py` **must** provide shared fixtures: synthetic market data, pool universe, mock Intex client.
- REQ-TEST-004: New analytics functions or tools **must** include at least one unit test.
- REQ-TEST-005: The evaluation suite (`evals/run_evals.py`, `evals/run_workflow_evals.py`) **must** be runnable independently of the main test suite (they require API keys and are not part of `pytest tests/`).

---

## 20. Change Log

| Date | Version | Author | Summary |
|------|---------|--------|---------|
| 2026-03-23 | 1.0.0 | Initial generation | First comprehensive requirements document created from codebase analysis |

> **Process:** Add a row to this table for every PR that changes functionality described in this document. Format: `YYYY-MM-DD | X.Y.Z | <name or PR #> | <one-line summary>`.
