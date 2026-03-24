# Oasia — Agency MBS Trading Desk Analytics Platform

A browser-based analytics application for agency MBS portfolio management. Two AI agent systems work in parallel: a **floating chat assistant** for real-time analytical queries, and a **structured portfolio planning workflow** with human-in-the-loop approval gates. Built on **Gradio 6 + FastAPI**, with all agent calls traced end-to-end via **Weights & Biases Weave**.

---

## Table of Contents

- [Key Features](#key-features)
- [Two Agent Systems](#two-agent-systems)
  - [Chat Panel — 7 Agents](#chat-panel--7-agents)
  - [Portfolio Planning Workflow — 4 Agents](#portfolio-planning-workflow--4-agents)
- [Agent Reference](#agent-reference)
- [UI Modules](#ui-modules)
- [Code Structure](#code-structure)
- [Setup](#setup)
- [Running the App](#running-the-app)
- [Authentication](#authentication)
- [Observability](#observability)
- [Evaluation](#evaluation)
- [Scripts Reference](#scripts-reference)
- [Architecture Notes](#architecture-notes)

---

## Key Features

### Chat Panel — Oasia Agent
A floating AI assistant, always visible on every screen, powered by an orchestrator and six specialist sub-agents (7 total). The orchestrator routes natural-language queries to the appropriate specialist — security selection, portfolio analytics, what-if analysis, attribution, market data, or dashboard — then synthesises responses back to the user without leaving the current view.

### Portfolio Planning Workflow — Human-in-the-Loop
A sequential four-agent pipeline (New Volume → Risk Assessment → Allocation → MBS Decomposition) with five structured trader-approval gates. The AI produces quantitative recommendations at each phase; the trader retains decisional authority at every gate. State is persisted to JSON after each phase so interrupted sessions can be resumed.

### Schedulable Analytics Pipeline
The full analytics run (market data refresh, rate path generation, pool OAS/OAD/EVE computation, KPI aggregation, NAV projections) can be scheduled daily, weekly, or monthly directly from the UI. A background APScheduler job runs at the configured time with real-time progress reported to the dashboard.

### Security Selection and Screening
Screen the full pool universe (CC30, CC15, GN30, GN15) by OAS range, duration, coupon, FICO, LTV, product type, and value score. Results are sortable, exportable to CSV, and carry relative-value labels (CHEAP / FAIR / RICH) based on cohort OAS benchmarks.

### What-If Sandbox
Interactively modify pool parameters (CPR, WAC, spread assumptions) and reprice in real time. Run parallel rate-shock scenarios (−300 to +300 bps) with side-by-side before/after comparisons of OAS, OAD, convexity, and price.

### Portfolio Analytics
Full portfolio risk dashboard: EVE (Economic Value of Equity) stress tests across seven rate shocks, OA duration profile, book yield decomposition, NAV history with 30-year projection, and sector concentration. Configurable EVE breach limit with automatic alerts.

### Attribution
Decompose period-over-period P&L into OAS change, carry/roll (OAD), yield income, and EVE drivers at both the portfolio and pool levels. Exportable attribution memos.

### LDAP / Active Directory Authentication
Production-grade LDAP/AD authentication with signed session cookies (8-hour TTL) and per-request middleware. A built-in mock mode (`LDAP_SERVER=mock://`) accepts any username with a configurable test password — no corporate VPN required in development.

### End-to-End Agent Tracing
Both agent systems — the chat panel and the planning workflow — are fully traced via W&B Weave and the OpenAI platform dashboard. Every agent run, tool call, delegation, and model interaction is captured with token usage, latency, and finish reason.

---

## Two Agent Systems

Oasia runs two independent agent systems in parallel. They share the same analytics tools and data layer but differ in architecture, invocation pattern, and purpose.

| | Chat Panel | Portfolio Planning Workflow |
|---|---|---|
| **Agents** | 7 (1 orchestrator + 6 specialists) | 4 (one per planning phase) |
| **Invocation** | User types a question; real-time | Triggered by "Start Planning" button; sequential |
| **Human control** | Conversational; user directs each query | 5 structured approval gates; trader decides at each phase |
| **Skills location** | `agent/skills/*.md` | `workflow/skills/*.md` |
| **Agent runner** | `agent/base_agent.py` + `agent/orchestrator.py` | `workflow/weave_runner.py` → `Runner.run()` |
| **State** | Conversation history (`list[dict]`) | Pydantic `WorkflowState` persisted to JSON |
| **OpenAI platform tracing** | `agents.trace("nexus_orchestrator")` | Automatic (OpenAI Agents SDK) |
| **Weave tracing** | `@weave.op` on `chat()` and `_execute_tool()` | `@weave.op` on `run_phase()` |

---

### Chat Panel — 7 Agents

```
User message
     │
┌────▼──────────────────────────────┐
│         OrchestratorAgent          │  (orchestrator.md skill, gpt-4o)
│  Routes via delegate_to_* tools    │
└──┬──────┬──────┬──────┬──────┬────┘
   │      │      │      │      │      │
┌──▼──┐ ┌─▼───┐ ┌▼────┐ ┌▼───────┐ ┌▼──────┐ ┌▼─────────┐
│Sec. │ │Port.│ │What-│ │Attrib- │ │Market │ │Dashboard │
│Sel. │ │Ana. │ │If   │ │ution   │ │Data   │ │          │
└─────┘ └─────┘ └─────┘ └────────┘ └───────┘ └──────────┘
```

1. The orchestrator receives the user message and decides which specialist(s) to invoke.
2. It calls one or more `delegate_to_<agent>` tools, forwarding a complete self-contained query.
3. Each sub-agent runs its own agentic loop — calling analytics tools, resolving results, returning text.
4. Tool calls within each sub-agent are wrapped in `custom_span("tool:<name>")` for OpenAI platform visibility.
5. The orchestrator synthesises all sub-agent responses into a single reply.

| # | Agent | Role | Analytics Tools |
|---|---|---|---|
| 1 | **Orchestrator** | Routes queries to specialists; synthesises responses; never answers analytical questions itself | *(delegation tools only)* |
| 2 | **Security Selection** | Screens the universe for CHEAP/FAIR/RICH relative value; flags credit and convexity risk | `screen_securities`, `get_pool_details`, `compute_bond_analytics`, `get_market_data` |
| 3 | **What-If Analysis** | Reprices pools after parameter changes; runs parallel rate-shock scenarios | `run_what_if`, `compute_bond_analytics`, `run_scenario_analysis`, `get_pool_details` |
| 4 | **Portfolio Analytics** | Reports OAS, OAD, book yield, EVE; flags limit breaches; recommends corrective trades | `get_portfolio_summary`, `get_portfolio_positions`, `compute_eve_profile`, `get_market_data` |
| 5 | **Attribution** | Decomposes period P&L into OAS change, carry/roll, income, and EVE drivers | `get_attribution`, `get_portfolio_summary`, `get_portfolio_positions` |
| 6 | **Market Data** | Retrieves SOFR/Treasury curves, cohort OAS levels, and rate-environment context | `get_market_data` |
| 7 | **Dashboard** | Answers questions about NAV, top performers, sector allocation, health scores, watchlist, and planning session status | `get_nav_projection`, `get_top_performers`, `get_sector_allocation`, `get_portfolio_health`, `get_watchlist`, `get_planning_session` |

---

### Portfolio Planning Workflow — 4 Agents

```
┌──────────────────────────────────────────────────────────────────┐
│                  PORTFOLIO PLANNING WORKFLOW                      │
│                                                                  │
│  Phase 1 — NEW VOLUME                                            │
│    NewVolumeAgent ─────► Monthly + annual new-purchase schedule  │
│    GATE 1 ─────────────► Trader: Approve / Modify target / Reject│
│                                                                  │
│  Phase 2 — RISK ASSESSMENT                                       │
│    RiskAgent ──────────► Duration, liquidity, concentration, OAS │
│    GATE 2 ─────────────► Trader: Accept / Adjust bounds / Reject │
│                                                                  │
│  Phase 3 — ALLOCATION                                            │
│    AllocationAgent ────► 3 scenarios: Conservative / Moderate /  │
│                          Aggressive, with trade-off explanations │
│    GATE 3 ─────────────► Trader: Select scenario / Custom % / Reject│
│                                                                  │
│  Phase 4 — MBS DECOMPOSITION                                     │
│    MBSDecompositionAgent► FNMA / FHLMC / GNMA × fixed/ARM       │
│                           sub-buckets; final purchase schedule   │
│    GATE 4 ─────────────► Trader: Approve / Modify / Reject      │
│                                                                  │
│  Phase 5 — FINAL APPROVAL                                        │
│    GATE 5 ─────────────► Trader: Confirm / Revise (→ Gate 3) / Abort│
│                                                                  │
│  Output: Purchase schedule + full gate audit trail (JSON)        │
└──────────────────────────────────────────────────────────────────┘
```

| Agent | Phase | Responsibility | Key Tools |
|---|---|---|---|
| **NewVolumeAgent** | 1 — New Volume | Calculates month-by-month purchase volumes needed to reach the target portfolio balance, accounting for prepayment runoff | `compute_new_volume_schedule`, `compute_volume_timing_analysis`, `summarise_pool_universe` |
| **RiskAgent** | 2 — Risk Assessment | Evaluates duration, liquidity, credit concentration, and OAS against policy limits; sets risk guardrails for allocation | `assess_portfolio_risk`, `estimate_duration_impact`, `get_risk_constraints_summary` |
| **AllocationAgent** | 3 — Allocation | Generates three MBS/CMBS/Treasury allocation scenarios with projected OAD, yield, liquidity score, and plain-language rationale | `generate_allocation_scenarios`, `select_allocation_scenario`, `estimate_duration_impact` |
| **MBSDecompositionAgent** | 4 — MBS Decomposition | Breaks the MBS dollar amount into FNMA/FHLMC/GNMA × fixed/ARM sub-buckets; compiles the final prioritised purchase schedule | `decompose_mbs_allocation`, `build_purchase_schedule`, `estimate_duration_impact` |

**Gate logic summary:**

| Gate | After Phase | Trader Options | On Revise |
|---|---|---|---|
| Gate 1 | New Volume | Approve / Modify target $MM / Reject | Re-run Phase 1 with updated target |
| Gate 2 | Risk Assessment | Accept / Adjust bounds or risk appetite / Reject | Re-run Phase 2 with updated constraints |
| Gate 3 | Allocation | Select scenario 1–3 / Enter custom MBS/CMBS/TSY % / Reject | Accept custom allocation, advance to Phase 4 |
| Gate 4 | MBS Decomposition | Approve / Modify sub-bucket % / Reject | Re-run Phase 4 with updated percentages |
| Gate 5 | Final Approval | Confirm / Revise / Abort | Loop back to Gate 3 (skips re-running Phases 1–2) |

---

## Agent Reference

### Chat Panel — Agent–UI Coverage Map

| UI Tab | Typical Question | Agent(s) Invoked |
|---|---|---|
| **Dashboard** | "What does my NAV projection look like?" | Dashboard |
| **Dashboard** | "Which pools performed best this month?" | Dashboard |
| **Dashboard** | "What is my sector allocation?" | Dashboard |
| **Dashboard** | "What is on my watchlist?" | Dashboard |
| **Portfolio Analytics** | "What is my portfolio OAD and EVE?" | Portfolio Analytics |
| **Portfolio Analytics** | "Are we breaching our EVE limit?" | Portfolio Analytics |
| **Portfolio Analytics** | "Morning risk briefing" | Portfolio Analytics + Market Data |
| **Security Analytics** | "Find me cheap CC30 pools" | Security Selection |
| **Security Analytics** | "Is pool X cheap or rich?" | Security Selection |
| **Attribution** | "Why did portfolio OAS change last month?" | Attribution |
| **Attribution** | "What drove the EVE change?" | Attribution |
| **What-If Sandbox** | "What happens if WAC goes up 50 bps?" | What-If Analysis |
| **What-If Sandbox** | "Show me rate shocks ±200 bps" | What-If Analysis |
| **Portfolio Planning** | "What phase is the planning session in?" | Dashboard |
| **Any tab** | "What are current Treasury rates?" | Market Data |
| **Any tab** | "Are agency spreads tight or wide?" | Market Data |

> The orchestrator handles multi-intent queries automatically — "Give me the morning briefing" simultaneously calls Portfolio Analytics, Market Data, and Dashboard, then synthesises all three into a single reply.

---

## UI Modules

| Tab | File | Description |
|---|---|---|
| **Dashboard** | `ui/dashboard.py` | KPI cards (NAV, book yield, OAD, OAS), NAV history + 30-year projection, portfolio health scorecard, holdings table, sector allocation, top performers, watchlist |
| **Portfolio Analytics** | `ui/portfolio_analytics.py` | EVE stress tests (±300 bps), duration/convexity profile, book yield decomposition, breach alerts, KPI trend charts |
| **Security Analytics** | `ui/security_analytics.py` | Pool screener with OAS/OAD/coupon/FICO/LTV filters, CUSIP lookup, single-pool analytics, rate-shock comparison table |
| **Security Selection** | `ui/security_selection.py` | Universe with CHEAP/FAIR/RICH relative-value labels, cohort comparison, CSV export, watchlist add |
| **Attribution** | `ui/attribution.py` | P&L attribution by OAS/OAD/yield/EVE drivers; period selector; exportable memos |
| **What-If Sandbox** | `ui/whatif_sandbox.py` | Real-time repricing after parameter changes; parallel rate-shock scenarios; before/after comparison |
| **Portfolio Planning** | `ui/portfolio_planning.py` | Four-phase AI workflow with five human-in-the-loop approval gates; session persistence and resumption |
| **Watchlist** | `ui/watchlist.py` | User-curated pool tracker with unrealised P&L and one-click navigation to analytics |

---

## Code Structure

```
oasia/
│
├── app.py                          # Entry point — FastAPI + Gradio + uvicorn
├── config.py                       # Environment-based configuration (Config class)
├── weave_config.py                 # W&B Weave initialisation and weave_op() helper
├── main.py                         # Alternative entry point (wraps app.py)
├── pyproject.toml                  # Project metadata and dependencies (uv)
├── uv.lock                         # Locked dependency versions (auto-generated)
├── .env.example                    # Environment variable template
│
├── docs/
│   ├── requirements.md             # Full functional and technical requirements (update on every change)
│   └── stakeholder_summary.md      # One-page business overview for non-technical stakeholders
│
├── auth/
│   ├── middleware.py               # Starlette middleware — enforces auth on every request
│   ├── routes.py                   # FastAPI login / logout routes
│   ├── login_page.py               # Dark-themed HTML login form
│   ├── ldap_auth.py                # LDAP/AD authentication + mock:// dev mode
│   └── session.py                  # Signed HTTP-only session cookie management
│
├── ui/
│   ├── layout.py                   # Main Gradio Blocks layout (sidebar, tabs, floating chat popup)
│   ├── theme.py                    # CUSTOM_CSS, INIT_JS, get_theme()
│   ├── dashboard.py                # Dashboard tab
│   ├── portfolio_analytics.py      # Portfolio Analytics tab
│   ├── security_analytics.py       # Security Analytics tab
│   ├── security_selection.py       # Security Selection / screener tab
│   ├── attribution.py              # Attribution tab
│   ├── whatif_sandbox.py           # What-If Sandbox tab
│   ├── portfolio_planning.py       # Portfolio Planning workflow tab
│   ├── watchlist.py                # Watchlist tab
│   └── agent_panel.py              # Floating Oasia agent chat panel
│
├── agent/                          # Chat Panel agent system
│   ├── orchestrator.py             # AgentOrchestrator — routes to sub-agents, wraps agents.trace()
│   ├── base_agent.py               # BaseAgent — OpenAI Agents SDK agentic loop + @weave.op tracing
│   ├── skill_loader.py             # Parses agent/skills/*.md → AgentSkill objects
│   ├── tools.py                    # OPENAI_TOOLS list + handle_tool_call() dispatcher
│   ├── prompts.py                  # Quick-query prompt templates
│   └── skills/                     # Agent definitions (YAML frontmatter + Markdown instructions)
│       ├── orchestrator.md
│       ├── security_selection.md
│       ├── what_if_analysis.md
│       ├── portfolio_analytics.md
│       ├── attribution.md
│       ├── market_data.md
│       └── dashboard.md
│
├── workflow/                        # Portfolio Planning agent system
│   ├── weave_runner.py             # run_phase() — @weave.op wrapper around Runner.run()
│   ├── scheduler.py                # APScheduler wrapper — daily/weekly/monthly analytics runs
│   ├── runner.py                   # Full analytics pipeline runner (market data → OAS → KPIs)
│   ├── projection_runner.py        # 30-year NAV projection runner
│   ├── agents/                     # Agent builder wrappers (one per phase)
│   │   ├── new_volume_agent.py     # build_new_volume_agent() → Agent
│   │   ├── risk_agent.py           # build_risk_agent() → Agent
│   │   ├── allocation_agent.py     # build_allocation_agent() → Agent
│   │   └── mbs_decomposition_agent.py
│   ├── skills/                     # Workflow agent skill definitions (YAML + Markdown)
│   │   ├── new_volume_agent.md
│   │   ├── risk_agent.md
│   │   ├── allocation_agent.md
│   │   ├── mbs_decomposition_agent.md
│   │   └── skill_loader.py         # SkillLoader — parses .md → Skill, builds Agent via ToolRegistry
│   ├── tools/                      # Pure-function analytics tools for planning agents
│   │   ├── computation.py          # New-volume computation tools
│   │   ├── risk_tools.py           # Duration, liquidity, concentration tools
│   │   ├── allocation_tools.py     # Scenario generation and MBS decomposition tools
│   │   └── tool_registry.py        # Tool name → callable mapping (ToolRegistry)
│   ├── models/
│   │   └── workflow_state.py       # Pydantic WorkflowState — canonical session representation
│   ├── data/
│   │   └── sample_data.py          # Synthetic pool and portfolio data generator
│   └── persistence/
│       └── state_manager.py        # Async JSON session persistence and resumption
│
├── analytics/                      # Core quantitative analytics
│   ├── oas_solver.py               # OAS/OAD/convexity solver (Monte Carlo + Brent's method)
│   ├── rate_paths.py               # Hull-White short-rate Monte Carlo simulation
│   ├── prepay.py                   # Prepayment model (CPR projection)
│   ├── neural_prepay.py            # Neural network prepayment model wrapper
│   ├── bgm_model.py                # BGM term structure model (alternative to HW)
│   ├── cashflows.py                # Cash flow generation (Intex API or MockIntexClient)
│   ├── scenarios.py                # Parallel rate-shock scenario analysis
│   └── risk.py                     # EVE computation across rate shocks
│
├── portfolio/                      # Portfolio-level aggregation
│   ├── aggregator.py               # Weighted KPI aggregation
│   ├── attribution.py              # P&L attribution decomposition
│   ├── book_yield.py               # Book yield aggregation
│   └── eve.py                      # EVE profile computation
│
├── tool/                           # Agent-callable tool layer (NEXUS chat panel)
│   ├── registry.py                 # Tool schema registry
│   ├── data_tool.py                # screen_securities, get_pool_details, get_market_data
│   ├── db_tool.py                  # DuckDB query tools
│   ├── term_structure_tool.py      # Rate path generation tools
│   ├── prepay_tool.py              # Prepayment forecast tools
│   ├── interest_income_tool.py     # Income projection tools
│   ├── analytics_tool.py           # compute_bond_analytics, batch_compute_analytics
│   ├── portfolio_tool.py           # get_portfolio_summary, compute_eve_profile, get_attribution
│   ├── scenario_tool.py            # run_scenario_analysis, run_what_if
│   └── dashboard_tool.py           # Dashboard data retrieval tools
│
├── data/
│   ├── position_data.py            # Portfolio position snapshots and summary loader
│   ├── pool_universe.py            # 1,000-pool synthetic MBS universe
│   ├── market_data.py              # SOFR/Treasury curve + cohort OAS loader
│   ├── intex_client.py             # IntexClient (live) / MockIntexClient (dev fallback)
│   ├── watchlist_store.py          # Watchlist JSON persistence
│   └── snapshot_store.py           # SQLite historical position snapshot store
│
├── db/
│   ├── connection.py               # DuckDB singleton connection + schema management
│   ├── projections.py              # Portfolio KPI reads/writes + NAV projection queries
│   └── cache.py                    # DuckDB-backed risk metrics cache (1-day TTL)
│
├── evals/                          # Agent evaluation suites
│   ├── run_evals.py                # CLI runner for chat panel agent evaluations
│   ├── run_workflow_evals.py       # CLI runner for portfolio planning agent evaluations
│   ├── dataset.py                  # EVAL_DATASET (chat panel) + PLANNING_EVAL_DATASET (workflow)
│   └── judges.py                   # LLM-as-judge scorers: Relevance, FinancialAccuracy, Actionability, ToolCoverage
│
├── scripts/
│   ├── generate_hypothetical_prepay_model.py   # Train and save the neural prepayment model
│   ├── generate_hypothetical_bgm_model.py      # Train and save the BGM term structure model
│   ├── generate_universe_1000.py               # Generate 1,000-pool synthetic MBS universe
│   ├── backfill_snapshots.py                   # Populate historical position snapshots
│   ├── calibrate_curves.py                     # Calibrate rate curves to market data
│   └── warm_cache.py                           # Pre-compute and cache risk metrics
│
└── tests/
    ├── conftest.py                 # Shared pytest fixtures (market data, mock clients, universe)
    └── test_*.py                   # Unit tests for analytics, workflow, persistence, tools
```

---

## Setup

### Prerequisites

- Python 3.12 or higher
- [uv](https://docs.astral.sh/uv/) — fast Python package and project manager
- An OpenAI API key (required for AI agent features)

### 1. Install uv

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart your terminal after installation so `uv` is on your PATH.

### 2. Clone the repository

```bash
git clone <repo-url>
cd oasia
```

### 3. Create the virtual environment and install dependencies

```bash
uv sync
```

This creates `.venv/` at the project root and installs all locked dependencies from `uv.lock`.

### 4. Configure environment variables

```bash
# macOS / Linux
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env
```

Open `.env` and fill in your values:

```env
# Required for AI agent features
OPENAI_API_KEY=sk-your-key-here

# Optional — enables Weave agent tracing dashboard
WANDB_API_KEY=your-wandb-key
WANDB_ENTITY=your-wandb-username-or-team
WANDB_PROJECT=oasia

# Optional — live Intex cash-flow data (MockIntexClient used if absent)
INTEX_API_KEY=

# Authentication — use mock:// for local development
LDAP_SERVER=mock://
LDAP_MOCK_PASSWORD=oasia-test

# For production: point to your company's Active Directory server
# LDAP_SERVER=ldap://ad.yourcompany.com
# LDAP_USER_DN_TEMPLATE={username}@yourcompany.com

GRADIO_PORT=7860
```

### 5. Generate model files

The prepayment model and BGM term structure model must be generated once before running analytics:

```bash
uv run python scripts/generate_hypothetical_prepay_model.py
uv run python scripts/generate_hypothetical_bgm_model.py
```

**Optional** — generate a 1,000-pool synthetic universe and pre-warm the analytics cache:

```bash
uv run python scripts/generate_universe_1000.py
uv run python scripts/warm_cache.py
```

---

## Running the App

```bash
uv run python app.py
```

The app starts on `http://localhost:7860` (or the port in `GRADIO_PORT`).

The startup banner confirms active integrations:

```
+--------------------------------------------------------------+
|          Oasia -- Fixed Income Portfolio Copilot             |
+--------------------------------------------------------------+
|  Status:                                                     |
|    OpenAI API : OK - Configured                              |
|    Intex API  : Not set (using mock client)                  |
|    Port       : 7860                                         |
+--------------------------------------------------------------+
```

If Weave tracing is enabled, a dashboard URL is also printed at startup.

---

## Authentication

### Development (mock mode)

Set `LDAP_SERVER=mock://` in `.env`. Any username is accepted with the password in `LDAP_MOCK_PASSWORD`:

```
Username: <anything>
Password: oasia-test
```

### Production (LDAP / Active Directory)

| Bind DN format | `LDAP_USER_DN_TEMPLATE` value |
|---|---|
| UPN (most common) | `{username}@yourcompany.com` |
| Down-level logon | `DOMAIN\{username}` |
| Full LDAP DN | `uid={username},ou=users,dc=yourcompany,dc=com` |

```env
LDAP_SERVER=ldap://ad.yourcompany.com
LDAP_USE_SSL=false
LDAP_USER_DN_TEMPLATE={username}@yourcompany.com
```

For SSL: use `ldaps://` and set `LDAP_USE_SSL=true`.

Sessions are managed via signed HTTP-only cookies and expire after 8 hours. Auth middleware enforces login on every request; Gradio's internal routes (`/gradio_api/`, `/static/`, `/assets/`) are excluded automatically.

---

## Observability

Both agent systems emit traces to two destinations simultaneously:

| Destination | What Is Captured | Requires |
|---|---|---|
| **W&B Weave** | All agent calls, tool executions, LLM inputs/outputs, latency, token usage | `WANDB_API_KEY` |
| **OpenAI platform dashboard** | Full agent traces via `agents.trace()` and `custom_span()` | `openai-agents` SDK (already installed) |

When `WANDB_API_KEY` is configured, `init_weave()` patches the OpenAI SDK at startup so all `chat.completions.create()` calls are automatically captured. The Weave dashboard URL is printed at startup:

```
Weave dashboard: https://wandb.ai/<entity>/projects/oasia/weave
```

Tracing is fully optional. If `WANDB_API_KEY` is not set, the app runs normally with tracing disabled.

---

## Evaluation

Oasia ships with two evaluation suites, each powered by four LLM-as-judge scorers (Relevance, Financial Accuracy, Actionability, Tool Coverage):

### Chat Panel Agents

```bash
# Run all 10 chat panel eval cases
uv run python -m evals.run_evals

# Filter to a specific specialist agent
uv run python -m evals.run_evals --agent portfolio_analytics

# Use a custom Weave project
uv run python -m evals.run_evals --project oasia-evals
```

### Portfolio Planning Workflow Agents

```bash
# Run all 7 planning eval cases (2 per agent)
uv run python -m evals.run_workflow_evals

# Filter to a single planning phase
uv run python -m evals.run_workflow_evals --agent new_volume

# Use a custom Weave project
uv run python -m evals.run_workflow_evals --project oasia-planning-evals
```

Both suites require `OPENAI_API_KEY` and `WANDB_API_KEY`. Results are captured in Weave with per-case scores, pass/fail breakdowns, full trace waterfalls, and a side-by-side response viewer.

---

## Scripts Reference

| Script | Purpose |
|---|---|
| `scripts/generate_hypothetical_prepay_model.py` | Train and save neural prepayment model to `data/models/prepay_model.pkl` |
| `scripts/generate_hypothetical_bgm_model.py` | Train and save BGM term structure model to `data/models/bgm_model.pkl` |
| `scripts/generate_universe_1000.py` | Generate 1,000-pool synthetic MBS universe |
| `scripts/backfill_snapshots.py` | Populate historical position snapshots into `data/snapshots.db` |
| `scripts/calibrate_curves.py` | Calibrate SOFR/Treasury rate curves to live market data |
| `scripts/warm_cache.py` | Pre-compute risk metrics and populate the DuckDB cache |

---

## Architecture Notes

### Skills-Based Agent Definitions
Every agent in both systems is defined by a single `.md` file: YAML frontmatter for model, tools, and metadata; Markdown body for instructions. Changing an agent's behaviour requires editing only the `.md` file — no Python changes needed.

### Weave Tracing for Both Systems
- **Chat panel agents:** `BaseAgent.chat()` and `BaseAgent._execute_tool()` are decorated with `@_op` (via `weave_config.weave_op()`). The orchestrator's chat loop is also wrapped in `agents.trace("nexus_orchestrator")` for the OpenAI platform.
- **Planning workflow agents:** All `Runner.run()` calls go through `workflow/weave_runner.py::run_phase()`, which is decorated `@_op`. The OpenAI Agents SDK automatically instruments each `Runner.run()` for the OpenAI platform.

### WorkflowState as Single Source of Truth
The planning workflow uses a Pydantic `WorkflowState` as the canonical session object. Every agent output, gate decision, and phase transition is recorded on it before being persisted to JSON. No mutable global state; safe for concurrent sessions.

### Non-Linear Workflow Branching
A `REJECT` at any gate terminates the workflow cleanly. A `REVISE` at Gate 5 loops back to Phase 3 (Allocation), regenerating only the allocation and MBS decomposition — not the more expensive risk assessment.

### Database Layer
- **DuckDB** (`data/nexus_results.duckdb`): analytics cache, portfolio KPIs, rate path statistics, NAV projections.
- **SQLite** (`data/snapshots.db`): historical monthly position snapshots.
- **Disk cache**: expensive risk metric computations (1-day TTL).

### UI Architecture
Gradio is mounted inside FastAPI and served by uvicorn. Custom CSS/JS implements a three-panel layout: fixed sidebar navigation, scrollable tabbed main content, and a floating agent chat popup. The Gradio native tab bar is hidden; tabs are driven entirely by sidebar clicks via JavaScript.

### Documentation
`docs/requirements.md` is the single source of truth for all functional and technical requirements. **Any code change affecting a feature must update the relevant section and add a row to the Change Log** before the PR is merged.
