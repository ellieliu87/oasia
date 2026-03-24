# Oasia — Agency MBS Trading Desk Analytics Platform

A browser-based analytics platform for agency MBS portfolio management. Specialized AI agents assist with security selection, what-if analysis, portfolio analytics, attribution, and new-volume planning — with an interactive Gradio UI, human-in-the-loop approval gates, and end-to-end agent observability via **Weights & Biases Weave**.

Built on **Gradio 6 + FastAPI**, with a multi-agent backend powered by the **OpenAI Agents SDK**.

---

## Table of Contents

- [Key Features](#key-features)
- [Agentic Architecture](#agentic-architecture)
- [NEXUS Agent Reference](#nexus-agent-reference)
- [UI Modules](#ui-modules)
- [Code Structure](#code-structure)
- [Setup](#setup)
- [Running the App](#running-the-app)
- [Authentication](#authentication)
- [Observability](#observability)
- [Scripts Reference](#scripts-reference)
- [Architecture Notes](#architecture-notes)

---

## Key Features

### Multi-Agent Chat Panel (NEXUS Agent)
A floating AI assistant powered by an orchestrator + six specialist sub-agents (7 agents total). The orchestrator routes natural-language queries to the appropriate specialist (security selection, portfolio analytics, what-if analysis, attribution, market data, or dashboard), synthesises responses, and streams them back to the UI — all without leaving the dashboard.

### Portfolio Planning Workflow — Human-in-the-Loop
A sequential four-agent pipeline (NewVolume → Risk → Allocation → MBS Decomposition) with five trader approval gates. Each gate presents structured results and pauses for explicit trader approval, modification, or rejection before the next phase proceeds. State is persisted to JSON after every phase; interrupted sessions can be resumed.

### Schedulable Analytics Pipeline
The analytics workflow can be configured to run on a daily, weekly, or monthly schedule directly from the UI. A background scheduler (APScheduler) runs the pipeline at the configured time, with real-time progress visible in the dashboard.

### Security Selection & Screening
Screen the full pool universe (CC30, CC15, GN30, GN15) against user-defined filters: OAS range, duration, coupon, product type, liquidity, and value score. Results are sortable, exportable to CSV, and selectable for downstream analytics.

### What-If Sandbox
Interactively modify pool parameters (CPR, prepayment speed, spread) and reprice pools in real time. Run parallel rate shock scenarios (+/− 100–300 bps) and compare OAD, OAS, and price impacts across the book.

### Portfolio Analytics
Full portfolio risk dashboard: EVE (Economic Value of Equity) stress tests, OA Duration, book yield, NAV history, and sector allocation. Configurable risk appetite and EVE breach limits.

### Attribution
Decompose period-over-period P&L into OAS, OAD, yield, and EVE drivers across the book and at the pool level. Side-by-side attribution tables with exportable memos.

### LDAP / Active Directory Authentication
Production-grade LDAP/AD authentication with session cookie management and per-request middleware enforcement. A built-in mock mode (`LDAP_SERVER=mock://`) accepts any username with a configurable test password — no corporate VPN required during development.

### End-to-End Agent Tracing
All agent runs, tool calls, and model interactions are traced via Weights & Biases Weave. A dashboard URL is printed at startup. Tracing is optional and degrades gracefully when `WANDB_API_KEY` is not set.

---

## Agentic Architecture

### NEXUS Agent (inline chat panel)

```
User message
     │
┌────▼────────────────────────────┐
│       OrchestratorAgent         │  (orchestrator.md skill, gpt-4o)
│                                 │
│  delegate_to_* tools            │
└──┬───────┬───────┬───────┬──────┘
   │       │       │       │       │              │
┌──▼──┐ ┌──▼──┐ ┌──▼──┐ ┌─▼───────┐ ┌──────────┐ ┌──────────┐
│Sec. │ │Port.│ │What-│ │Attribu- │ │ Market   │ │Dashboard │
│Sel. │ │Ana. │ │If   │ │tion     │ │ Data     │ │          │
└─────┘ └─────┘ └─────┘ └─────────┘ └──────────┘ └──────────┘
```

1. The orchestrator LLM receives the user message and decides which specialist(s) to invoke.
2. It calls one or more `delegate_to_<agent>` tools.
3. Each sub-agent runs its own agentic loop, calling analytics tools and resolving results.
4. Sub-agent text responses are returned to the orchestrator as tool results.
5. The orchestrator synthesises a final response and streams it to the chat panel.

### Portfolio Planning Workflow (human-in-the-loop)

```
┌──────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATOR                              │
│                                                                  │
│  Phase 1: NEW_VOLUME                                             │
│    NewVolumeAgent ──► compute monthly + annual purchase volumes  │
│    GATE 1 ──────────► Trader: Approve / Modify target / Reject   │
│                                                                  │
│  Phase 2: RISK_ASSESSMENT                                        │
│    RiskAgent ────────► duration, liquidity, concentration, OAS   │
│    GATE 2 ──────────► Trader: Accept / Adjust bounds / Reject    │
│                                                                  │
│  Phase 3: ALLOCATION                                             │
│    AllocationAgent ──► 3 scenarios (Conservative / Moderate /    │
│                        Aggressive) with trade-off explanations   │
│    GATE 3 ──────────► Trader: Select scenario or enter custom %  │
│                                                                  │
│  Phase 4: MBS_DECOMPOSITION                                      │
│    MBSDecompositionAgent ► FNMA/FHLMC/GNMA × fixed/ARM          │
│                            sub-buckets; final purchase schedule  │
│    GATE 4 ──────────► Trader: Approve / Modify / Reject         │
│                                                                  │
│  Phase 5: FINAL_APPROVAL                                         │
│    GATE 5 ──────────► Trader: Confirm / Revise (→ Gate 3) / Abort│
│                                                                  │
│  Output: Purchase schedule + gate audit trail (persisted JSON)   │
└──────────────────────────────────────────────────────────────────┘
```

### Workflow Agents and Responsibilities

| Agent | Role | Key Tools |
|---|---|---|
| **NewVolumeAgent** | Calculates monthly and annual new-purchase volumes needed to hit portfolio growth targets | `compute_new_volume_schedule`, `compute_volume_timing_analysis`, `summarise_pool_universe` |
| **RiskAgent** | Evaluates duration, liquidity, credit concentration, and OAS; sets risk guardrails | `assess_portfolio_risk`, `estimate_duration_impact`, `get_risk_constraints_summary` |
| **AllocationAgent** | Generates three MBS/CMBS/Treasury allocation scenarios with trade-off explanations | `generate_allocation_scenarios`, `select_allocation_scenario`, `estimate_duration_impact` |
| **MBSDecompositionAgent** | Breaks MBS allocation into agency sub-buckets; compiles the final purchase schedule | `decompose_mbs_allocation`, `build_purchase_schedule`, `estimate_duration_impact` |

### Gate Behaviour

| Gate | Presented to Trader | Trader Options |
|---|---|---|
| Gate 1 — New Volume | Monthly schedule + annual totals | Approve / Modify target $MM / Reject |
| Gate 2 — Risk Assessment | Duration bounds, liquidity floor, risk flags | Accept / Change bounds or risk appetite / Reject |
| Gate 3 — Allocation | Three scenarios side-by-side | Select 1–3 / Enter custom MBS/CMBS/TSY % / Reject |
| Gate 4 — MBS Decomposition | Agency sub-bucket breakdown table | Approve / Modify percentages / Reject |
| Gate 5 — Final Approval | Full purchase schedule (10 items) | Confirm / Revise (→ Gate 3) / Abort |

---

## NEXUS Agent Reference

### The 7 Agents

| # | Agent | Role | Analytics Tools |
|---|---|---|---|
| 1 | **Orchestrator** | Classifies user intent and routes to the correct specialist(s). Handles multi-intent queries by calling several delegates in parallel. Never answers analytical questions itself. | *(none — only `delegate_to_*` routing tools)* |
| 2 | **Security Selection** | Screens the agency MBS universe for relative value. Identifies CHEAP / FAIR / RICH pools using OAS vs cohort benchmarks, flags risk factors (LTV, FICO, geography, convexity). | `screen_securities`, `get_pool_details`, `compute_bond_analytics`, `get_market_data` |
| 3 | **What-If Analysis** | Models hypothetical changes to pool characteristics (WAC, WALA, LTV, FICO, CPR override) and quantifies the impact on OAS, OAD, yield, and price. Runs parallel rate shock scenarios. | `run_what_if`, `compute_bond_analytics`, `run_scenario_analysis`, `get_pool_details` |
| 4 | **Portfolio Analytics** | Reports on the current state of the MBS book: book yield, OAS, OAD, EVE stress tests, KPIs, and position contributions. Flags EVE limit breaches and recommends corrective trades. | `get_portfolio_summary`, `get_portfolio_positions`, `compute_eve_profile`, `get_market_data` |
| 5 | **Attribution** | Decomposes period-over-period changes in portfolio OAS, OAD, book yield, and EVE into constituent drivers (carry, sector spread, mix changes, prepay model effect). | `get_attribution`, `get_portfolio_summary`, `get_portfolio_positions` |
| 6 | **Market Data** | Retrieves current SOFR/Treasury curves, cohort OAS levels, and rate environment context. Provides 2s10s slope, spread richness/cheapness signals, and CPR rate environment commentary. | `get_market_data` |
| 7 | **Dashboard** | Answers questions about what is currently shown on the portfolio dashboard: NAV trajectory, top/bottom performers, sector allocation, health score, watchlist contents, and planning session status. | `get_nav_projection`, `get_top_performers`, `get_sector_allocation`, `get_portfolio_health`, `get_watchlist`, `get_planning_session` |

### Agent–UI Coverage Map

The table below shows which NEXUS specialist is engaged when a user asks a question from each UI tab.

| UI Tab | Typical User Question | Agent(s) Invoked | Circumstance |
|---|---|---|---|
| **Dashboard** | "What does my NAV projection look like?" | Dashboard | Asking about the NAV chart, portfolio value trend, or projected runoff |
| **Dashboard** | "Which pools performed best this month?" | Dashboard | Top/bottom performer rankings or MTD return |
| **Dashboard** | "What is my sector allocation?" | Dashboard | Sector pie, product-type breakdown, or concentration |
| **Dashboard** | "What is my portfolio health score?" | Dashboard | Health score or any sub-metric (duration, liquidity, concentration) |
| **Dashboard** | "What is on my watchlist?" | Dashboard | Watchlist CUSIPs, prices, or unrealized P&L |
| **Dashboard** | "Where is the planning session?" | Dashboard | Current planning workflow phase or open gate decisions |
| **Portfolio Analytics** | "What is my portfolio OAD and EVE?" | Portfolio Analytics | Portfolio-level KPIs, risk metrics, or EVE stress results |
| **Portfolio Analytics** | "Are we breaching our EVE limit?" | Portfolio Analytics | EVE limit monitoring or breach identification |
| **Portfolio Analytics** | "Morning risk briefing" | Portfolio Analytics + Market Data | Multi-intent: portfolio state + current rate environment |
| **Security Analytics** | "Find me cheap CC30 pools" | Security Selection | Pool screening with OAS/OAD/coupon filters |
| **Security Analytics** | "What are the analytics for pool X?" | Security Selection | Single-pool OAS, OAD, convexity, or CPR |
| **Security Analytics** | "Is CUSIP 3140X7GK4 cheap or rich?" | Security Selection | Relative value vs cohort benchmark |
| **Attribution** | "Why did portfolio OAS change last month?" | Attribution | Period-over-period OAS, OAD, yield, or EVE decomposition |
| **Attribution** | "What drove the EVE change?" | Attribution | EVE attribution into rate curve, mix, and prepay model drivers |
| **What-If Sandbox** | "What happens if WAC goes up 50 bps?" | What-If Analysis | Characteristic modification and repricing |
| **What-If Sandbox** | "Show me rate shocks ±200 bps" | What-If Analysis | Parallel scenario analysis across rate shock range |
| **What-If Sandbox** | "What is the fair value price for this pool?" | What-If Analysis | OAS-targeting or model price solving |
| **Portfolio Planning** | "What phase is the planning session in?" | Dashboard | Current phase or pending gate decisions |
| **Portfolio Planning** | "What is the new-volume recommendation?" | Dashboard | Gate 1 output — monthly/annual purchase schedule |
| **Any tab** | "What are current Treasury rates?" | Market Data | SOFR/Treasury curve levels, 2s10s slope, or OAS context |
| **Any tab** | "Are agency MBS spreads tight or wide?" | Market Data | Cohort OAS levels vs historical ranges |

> **Note:** The orchestrator handles multi-intent queries automatically. For example, "Give me the morning briefing" will trigger simultaneous calls to Portfolio Analytics, Market Data, and Dashboard, then synthesise all three responses into a single reply.

---

## UI Modules

| Tab | Description |
|---|---|
| **Dashboard** | KPI cards (NAV, book yield, OAD, OAS), NAV history chart with projection, portfolio health score, holdings table, sector allocation, watchlist |
| **Portfolio Analytics** | EVE stress tests, duration/convexity profile, book yield decomposition, risk limit monitoring |
| **Security Analytics** | Pool screener, CUSIP lookup, OAS calculator, rate shock table |
| **Attribution** | P&L attribution by OAS/OAD/yield/EVE drivers; exportable memos |
| **Portfolio Planning** | Multi-agent new-volume planning workflow with five human-in-the-loop gates |
| **Watchlist** | Track pools by CUSIP; add/remove from any analytics view |

---

## Code Structure

```
nexus_mbs/
│
├── app.py                          # Entry point — FastAPI + Gradio + uvicorn
├── config.py                       # Environment-based configuration (Config class)
├── pyproject.toml                  # Project metadata and dependencies (uv)
├── uv.lock                         # Locked dependency versions (auto-generated)
├── weave_config.py                 # W&B Weave tracing initialisation
├── .env.example                    # Environment variable template
│
├── auth/
│   ├── middleware.py               # Starlette middleware — enforces auth on every request
│   ├── routes.py                   # FastAPI login / logout routes
│   ├── login_page.py               # Dark-themed HTML login page
│   ├── ldap_auth.py                # LDAP/AD authentication + mock:// mode
│   └── session.py                  # Signed session cookie management
│
├── ui/
│   ├── layout.py                   # Main Gradio Blocks layout (topbar, sidebar, tabs)
│   ├── theme.py                    # CUSTOM_CSS, INIT_JS, get_theme()
│   ├── dashboard.py                # Dashboard tab — KPIs, charts, holdings
│   ├── security_analytics.py       # Security Analytics tab
│   ├── security_selection.py       # Security Selection / screener tab
│   ├── portfolio_analytics.py      # Portfolio Analytics tab
│   ├── attribution.py              # Attribution tab
│   ├── portfolio_planning.py       # Portfolio Planning workflow UI
│   ├── watchlist.py                # Watchlist tab
│   ├── whatif_sandbox.py           # What-If Sandbox tab
│   └── agent_panel.py              # Inline NEXUS Agent chat panel
│
├── agent/
│   ├── orchestrator.py             # OrchestratorAgent — routes to sub-agents
│   ├── base_agent.py               # BaseAgent — wraps OpenAI Agents SDK runner
│   ├── skill_loader.py             # Parses skills/*.md → Agent objects
│   ├── tools.py                    # Analytics tool definitions (function_tools)
│   ├── prompts.py                  # Quick-query templates for the chat panel
│   └── skills/                     # Agent definitions as Markdown + YAML frontmatter
│       ├── orchestrator.md
│       ├── security_selection.md
│       ├── what_if_analysis.md
│       ├── portfolio_analytics.md
│       ├── attribution.md
│       ├── market_data.md
│       └── dashboard.md
│
├── workflow/                        # Portfolio Planning multi-agent pipeline
│   ├── scheduler.py                # APScheduler wrapper — daily/weekly/monthly runs
│   ├── runner.py                   # Async workflow runner (phase dispatch loop)
│   ├── projection_runner.py        # Standalone projection computation runner
│   ├── agents/                     # Thin agent builder wrappers
│   │   ├── new_volume_agent.py
│   │   ├── risk_agent.py
│   │   ├── allocation_agent.py
│   │   └── mbs_decomposition_agent.py
│   ├── skills/                     # Workflow agent skill definitions (Markdown)
│   │   ├── new_volume_agent.md
│   │   ├── risk_agent.md
│   │   ├── allocation_agent.md
│   │   ├── mbs_decomposition_agent.md
│   │   └── skill_loader.py
│   ├── tools/                      # Pure-function analytics tools
│   │   ├── computation.py          # New-volume computation tools
│   │   ├── risk_tools.py           # Duration, liquidity, OAS risk tools
│   │   ├── allocation_tools.py     # Scenario generation, MBS decomposition
│   │   └── tool_registry.py        # Tool name → callable mapping
│   ├── models/
│   │   └── workflow_state.py       # Pydantic WorkflowState — single source of truth
│   ├── data/
│   │   └── sample_data.py          # Synthetic pool + portfolio data generator
│   └── persistence/
│       └── state_manager.py        # Async JSON session persistence
│
├── data/
│   ├── position_data.py            # Position snapshot loader + portfolio summary
│   ├── watchlist_store.py          # Watchlist JSON persistence
│   ├── market_data/                # Rate curves, OAS history, market data files
│   └── models/                     # Trained model files (prepay.pkl, bgm.pkl)
│
├── db/
│   ├── connection.py               # DuckDB connection factory
│   ├── projections.py              # Projection + KPI reads/writes
│   └── cache.py                    # DuckDB-backed risk metrics cache
│
├── analytics/                      # Core analytics computations (OAS, OAD, EVE)
├── portfolio/                      # Portfolio-level aggregation and calculations
├── tool/                           # Low-level analytics tools used by agents
│
├── scripts/
│   ├── generate_hypothetical_prepay_model.py   # Train + save prepayment model
│   ├── generate_hypothetical_bgm_model.py      # Train + save BGM term structure model
│   ├── generate_universe_1000.py               # Generate 1,000-pool synthetic universe
│   ├── backfill_snapshots.py                   # Backfill historical position snapshots
│   ├── calibrate_curves.py                     # Calibrate rate curves to market data
│   └── warm_cache.py                           # Pre-compute and cache risk metrics
│
├── evals/                          # Agent evaluation suites
│
└── tests/
    ├── conftest.py                 # Shared pytest fixtures
    └── unit/                       # Fast unit tests — no API calls
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

---

### 2. Clone the repository

```bash
git clone <repo-url>
cd nexus_mbs
```

---

### 3. Create the virtual environment and install dependencies

```bash
uv sync
```

This creates `.venv/` at the project root and installs all locked dependencies from `uv.lock`.

---

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
WANDB_PROJECT=nexus-mbs

# Optional — live Intex prepay/analytics data
INTEX_API_KEY=

# Authentication — set to mock:// for local development (no corporate network needed)
LDAP_SERVER=mock://
LDAP_MOCK_PASSWORD=oasis-test

# For production: point to your company's Active Directory server
# LDAP_SERVER=ldap://ad.yourcompany.com
# LDAP_USER_DN_TEMPLATE={username}@yourcompany.com

# UI
GRADIO_PORT=7860
```

---

### 5. Generate model files

The prepayment model and BGM term structure model must be generated before the app can run analytics. Run these once after cloning:

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

The app starts on `http://localhost:7860` (or the port set in `GRADIO_PORT`).

The startup banner confirms which integrations are active:

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

Set `LDAP_SERVER=mock://` in `.env`. Any username is accepted with the password in `LDAP_MOCK_PASSWORD` (default: `oasis-test`).

```
Username: <anything>
Password: oasis-test
```

### Production (LDAP / Active Directory)

Set `LDAP_SERVER` to your company's AD server. Common bind DN formats:

| Format | Example value for `LDAP_USER_DN_TEMPLATE` |
|---|---|
| UPN (most common) | `{username}@yourcompany.com` |
| Down-level logon | `DOMAIN\{username}` |
| Full LDAP DN | `uid={username},ou=users,dc=yourcompany,dc=com` |

```env
LDAP_SERVER=ldap://ad.yourcompany.com
LDAP_USE_SSL=false
LDAP_USER_DN_TEMPLATE={username}@yourcompany.com
```

For SSL/TLS: use `ldaps://` and set `LDAP_USE_SSL=true`.

Sessions are managed via signed HTTP-only cookies and expire after 8 hours. The auth middleware enforces login on every request; Gradio's internal routes (`/gradio_api/`, `/static/`, `/assets/`, `/theme.css`, etc.) are automatically excluded from auth checks.

---

## Observability

When `WANDB_API_KEY` is configured, Oasia automatically initialises Weave tracing at startup. The following are captured:

- **Agent runs** — full execution trace for every orchestrator and sub-agent invocation (prompt, model, token usage, response)
- **Tool calls** — inputs and outputs for every analytics tool call
- **Raw model interactions** — latency, streaming behaviour, finish reason

The Weave dashboard URL is printed at startup:

```
Weave dashboard: https://wandb.ai/<entity>/projects/nexus-mbs/weave
```

Tracing is fully optional. If `WANDB_API_KEY` is not set, the app runs normally with a log message indicating tracing is disabled.

---

## Scripts Reference

| Script | Purpose |
|---|---|
| `scripts/generate_hypothetical_prepay_model.py` | Train and save the neural prepayment model to `data/models/prepay_model.pkl` |
| `scripts/generate_hypothetical_bgm_model.py` | Train and save the BGM term structure model to `data/models/bgm_model.pkl` |
| `scripts/generate_universe_1000.py` | Generate a 1,000-pool synthetic MBS universe for screening and analytics |
| `scripts/backfill_snapshots.py` | Backfill historical position snapshots into the snapshot database |
| `scripts/calibrate_curves.py` | Calibrate rate curves to market data |
| `scripts/warm_cache.py` | Pre-compute risk metrics and populate the DuckDB cache |

---

## Architecture Notes

### Skills-Based Agent Architecture
Each agent in both the NEXUS chat panel and the Portfolio Planning workflow is defined by a single `.md` file in its `skills/` directory. YAML frontmatter specifies the model, tools list, and metadata; the Markdown body contains the plain-language instructions passed to the model. Adding or modifying an agent's behaviour requires no Python changes — only editing the `.md` file.

### State as Single Source of Truth
The Portfolio Planning workflow uses a Pydantic `WorkflowState` as the canonical session representation. Every agent output, gate decision, and phase transition is recorded on this object before being persisted to JSON. Agents and tools share no mutable global state.

### Separation of Concerns
- **Agents** — responsible only for reasoning and producing structured output.
- **Tools** — pure functions, deterministic given their inputs, no side effects on global state.
- **Gates** — responsible for presenting structured results to the trader and capturing decisions.
- **Orchestrator** — responsible for sequencing, phase branching, and persisting state.

### Non-Linear Workflow Branching
A `REJECT` at any gate terminates the workflow cleanly. A `REVISE` response at Gate 5 loops back to Phase 3 (Allocation), allowing the trader to select a different scenario and regenerate the MBS decomposition and purchase schedule without rerunning the risk assessment.

### Database Layer
Analytics results, projections, and risk metrics are stored in DuckDB (`data/nexus_results.duckdb`). Position snapshots are stored in a separate SQLite database (`data/snapshots.db`). A DiskCache layer caches expensive risk metric computations across requests.

### UI Architecture
The Gradio UI is mounted inside a FastAPI application and served by uvicorn. Custom CSS and JavaScript (passed via `gr.mount_gradio_app`) implement a three-panel layout: fixed sidebar navigation, scrollable main content tabs, and a floating agent chat popup. The Gradio tab system is driven entirely by sidebar nav clicks via JavaScript, with the native Gradio tab bar hidden from view.
