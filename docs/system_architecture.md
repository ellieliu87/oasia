# System Architecture Document — Nexus MBS (Oasia)

> **Document Type:** System Architecture Document (SAD)
> **Audience:** Beginner-level software developers
> **Last Updated:** 2026-03-27

---

## Table of Contents

1. [What Is This Application?](#1-what-is-this-application)
2. [High-Level Architecture Overview](#2-high-level-architecture-overview)
3. [Tech Stack](#3-tech-stack)
4. [Project Structure](#4-project-structure)
5. [Core Components Explained](#5-core-components-explained)
   - 5.1 [The Web Application (FastAPI + Gradio)](#51-the-web-application-fastapi--gradio)
   - 5.2 [Authentication](#52-authentication)
   - 5.3 [The AI Chat Panel Agent System](#53-the-ai-chat-panel-agent-system)
   - 5.4 [The Portfolio Planning Workflow System](#54-the-portfolio-planning-workflow-system)
   - 5.5 [The Analytics Engine](#55-the-analytics-engine)
   - 5.6 [The Tool Registry](#56-the-tool-registry)
   - 5.7 [Data Layer](#57-data-layer)
   - 5.8 [User Interface Tabs](#58-user-interface-tabs)
   - 5.9 [Observability and Tracing](#59-observability-and-tracing)
6. [Agent Workflow — Deep Dive](#6-agent-workflow--deep-dive)
   - 6.1 [Chat Panel: Real-Time Q&A](#61-chat-panel-real-time-qa)
   - 6.2 [Portfolio Planning: Multi-Step Approval Workflow](#62-portfolio-planning-multi-step-approval-workflow)
7. [Key Design Choices](#7-key-design-choices)
8. [Data Models and Databases](#8-data-models-and-databases)
9. [Configuration and Environment Setup](#9-configuration-and-environment-setup)
10. [How Everything Starts Up](#10-how-everything-starts-up)
11. [Suggested Improvements for a Commercial Product](#11-suggested-improvements-for-a-commercial-product)

---

## 1. What Is This Application?

**Nexus MBS** (codenamed *Oasia*) is an analytics platform built for a fixed-income trading desk that invests in **Mortgage-Backed Securities (MBS)** — a type of bond backed by pools of home loans.

The platform helps traders and portfolio managers answer questions like:

- "Which bonds in our universe are cheap vs. expensive right now?"
- "What happens to my portfolio's value if interest rates rise by 200 basis points?"
- "How should I allocate next quarter's new purchase budget across different bond types?"

The unique selling point is that instead of just showing charts, the platform has **AI agents** — programs powered by Large Language Models (LLMs) like GPT-4o — that you can ask questions to in plain English, and that can also run complex analysis workflows autonomously, pausing at key decision points to get human approval.

---

## 2. High-Level Architecture Overview

Below is a simplified map of how the major pieces connect:

```
┌──────────────────────────────────────────────────────────┐
│                  User's Web Browser                      │
│  (Dashboard, Charts, Tables, Forms, Chat Panel)          │
└──────────────────────┬───────────────────────────────────┘
                       │  HTTP requests
                       ▼
┌──────────────────────────────────────────────────────────┐
│              FastAPI + Gradio Server                     │
│  ┌─────────────────┐    ┌──────────────────────────────┐ │
│  │  Auth Middleware │    │   Gradio UI (9 Tabs +        │ │
│  │  (LDAP / mock)  │    │   Floating Chat Panel)        │ │
│  └─────────────────┘    └──────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
                       │  function calls
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐    ┌───────────────────────────────┐
│  Chat Panel      │    │  Portfolio Planning           │
│  Agent System    │    │  Workflow System               │
│  (7 AI Agents)   │    │  (4 AI Agents + 5 Gates)      │
└────────┬─────────┘    └───────────────┬───────────────┘
         │                              │
         └──────────────┬───────────────┘
                        ▼
┌──────────────────────────────────────────────────────────┐
│               Tool Registry (~50 tools)                  │
│  (functions the AI agents can call to get real data)     │
└──────────────────────────────────────────────────────────┘
                        │
         ┌──────────────┼──────────────┐
         ▼              ▼              ▼
┌──────────────┐ ┌────────────┐ ┌──────────────┐
│  Analytics   │ │  Portfolio │ │  Data Layer  │
│  Engine      │ │  Layer     │ │  (DuckDB,    │
│  (OAS, EVE,  │ │  (KPIs,    │ │  SQLite,     │
│  Monte Carlo)│ │  P&L)      │ │  Disk Cache) │
└──────────────┘ └────────────┘ └──────────────┘
                        │
                        ▼
         ┌──────────────────────────────┐
         │  External OpenAI API         │
         │  (gpt-4o LLM for agents)     │
         └──────────────────────────────┘
```

**The key idea:** The user interacts with a standard website. Behind the scenes, AI agents receive the user's questions, decide which analytical tools to call, run the computations, and return plain-English answers.

---

## 3. Tech Stack

The tech stack is the set of technologies chosen to build the application. Here is everything used, organized by category.

### Programming Language

| Technology | Version | Why It Was Chosen |
|---|---|---|
| **Python** | 3.12+ | Industry standard for both financial analytics (NumPy, SciPy) and AI/ML (OpenAI SDK). Large ecosystem, readable syntax. |

### Web Framework

| Technology | Why It Was Chosen |
|---|---|
| **Gradio** | A Python library that turns Python functions into a web UI with minimal code. Excellent for data and analytics dashboards. No need to write HTML/CSS from scratch for every widget. |
| **FastAPI** | A modern Python web framework used here to host the Gradio app and add custom routes (like login/logout). Handles authentication middleware. |
| **Uvicorn** | The server that actually runs the FastAPI application. Think of it as the engine behind the web server. |

### AI and Agents

| Technology | Why It Was Chosen |
|---|---|
| **OpenAI Python SDK** | Makes it easy to call GPT-4o and other OpenAI models from Python code. |
| **OpenAI Agents SDK** | A higher-level library built on top of the OpenAI SDK that adds features specifically for building multi-agent systems (tracing, tool dispatch, agent handoffs). |

### Numerical and Scientific Computing

| Technology | Why It Was Chosen |
|---|---|
| **NumPy** | The foundation of scientific Python. Handles fast array math — essential for running 256 Monte Carlo simulations at once. |
| **SciPy** | Scientific algorithms. Used for Brent's method (a root-finding algorithm to solve for the Option-Adjusted Spread). |
| **Pandas** | DataFrames — think spreadsheets in Python. Used extensively to manipulate tables of bond data. |
| **Plotly** | Creates interactive charts (zoom, hover, download) that appear in the Gradio tabs. |
| **scikit-learn** | Machine learning library used for preprocessing inputs to the neural network prepayment model. |

### Databases and Caching

| Technology | Why It Was Chosen |
|---|---|
| **DuckDB** | An in-process analytical database (like SQLite but optimized for analytics queries). Stores computed results like rate paths, prepayment forecasts, and NAV projections so they don't have to be recomputed every time. |
| **SQLite** | Stores historical portfolio position snapshots (lightweight, serverless, built into Python). |
| **diskcache** | A simple disk-based cache with a time-to-live (TTL). Risk metrics are cached for 1 day so that repeated page loads don't re-run expensive calculations. |
| **PyArrow** | Efficient binary format (Parquet) for storing large Monte Carlo path arrays on disk. |

### Authentication

| Technology | Why It Was Chosen |
|---|---|
| **ldap3** | Python library for LDAP authentication. In an enterprise, user accounts are often managed in Microsoft Active Directory (AD), which speaks LDAP. This library lets the app verify usernames/passwords against AD. |

### Observability (Monitoring and Debugging)

| Technology | Why It Was Chosen |
|---|---|
| **W&B Weave** | A platform from Weights & Biases (W&B) that captures every LLM call, its inputs, outputs, and latency in a searchable UI. Essential for debugging why an agent gave the wrong answer. |
| **OpenAI Tracing** | Built into the OpenAI Agents SDK. Provides a trace waterfall showing how agents delegated to sub-agents and which tools were called. |

### Scheduling

| Technology | Why It Was Chosen |
|---|---|
| **APScheduler** | A task scheduler for Python. Runs the analytics pipeline automatically (daily, weekly, monthly) so the cache is always warm when traders arrive in the morning. |

### Package Management

| Technology | Why It Was Chosen |
|---|---|
| **uv** | A very fast Python package manager (written in Rust). Replaces `pip`. Creates a `uv.lock` file so every developer and deployment environment installs the exact same library versions. |

---

## 4. Project Structure

Here is a map of the important folders and files, with plain-English explanations:

```
nexus_mbs/
│
├── app.py                  ← The main entry point. Run this to start the app.
├── config.py               ← All configuration (API keys, file paths, risk limits).
├── weave_config.py         ← Sets up W&B Weave monitoring.
├── main.py                 ← Alternative thin wrapper around app.py.
├── pyproject.toml          ← Project metadata and dependency list (read by uv).
├── requirements.txt        ← Flat list of dependencies (alternative to pyproject.toml).
│
├── agent/                  ← The real-time Chat Panel AI system (7 agents).
│   ├── orchestrator.py     ← The "boss" agent that routes questions to specialists.
│   ├── base_agent.py       ← Shared logic all agents use (the OpenAI API loop).
│   ├── skill_loader.py     ← Reads agent definition files (.md) into Python objects.
│   ├── tools.py            ← Thin wrapper connecting agents to the tool registry.
│   └── skills/             ← Agent definitions written as Markdown files.
│       ├── orchestrator.md
│       ├── security_selection.md
│       ├── what_if_analysis.md
│       ├── portfolio_analytics.md
│       ├── attribution.md
│       ├── market_data.md
│       └── dashboard.md
│
├── workflow/               ← The Portfolio Planning workflow system (4 agents + gates).
│   ├── runner.py           ← Runs the full analytics pipeline: market data → results.
│   ├── weave_runner.py     ← Wraps each workflow phase in W&B Weave tracing.
│   ├── scheduler.py        ← APScheduler jobs for automated daily/weekly/monthly runs.
│   ├── projection_runner.py← Runs 30-year NAV projection scenarios.
│   ├── agents/             ← One Python file per workflow phase (builds each agent).
│   ├── skills/             ← Workflow agent definitions (same .md format as above).
│   ├── tools/              ← Pure calculation functions (no LLM calls).
│   ├── models/             ← WorkflowState: the Pydantic model for session state.
│   ├── data/               ← Synthetic data generator for development/testing.
│   └── persistence/        ← Saves/loads workflow sessions to/from JSON files.
│
├── analytics/              ← The quantitative math engine (no AI here, pure math).
│   ├── oas_solver.py       ← Prices bonds using Monte Carlo + Brent's method.
│   ├── rate_paths.py       ← Simulates future interest rates (Hull-White model).
│   ├── prepay.py           ← Predicts how fast mortgages will be paid off (CPR).
│   ├── neural_prepay.py    ← Neural-network-based prepayment model (more accurate).
│   ├── bgm_model.py        ← Alternative interest rate model (BGM).
│   ├── cashflows.py        ← Generates the cash flows for each bond.
│   ├── scenarios.py        ← Runs analysis under many rate shock scenarios in parallel.
│   └── risk.py             ← Computes Economic Value of Equity (EVE).
│
├── portfolio/              ← Portfolio-level aggregations (combines individual bonds).
│   ├── aggregator.py       ← Weighted average of KPIs across all positions.
│   ├── attribution.py      ← Decomposes profit/loss into its sources.
│   ├── book_yield.py       ← Computes weighted book yield of the portfolio.
│   └── eve.py              ← Portfolio-level EVE profile across rate shocks.
│
├── tool/                   ← Agent-callable functions (~50 tools, one per task).
│   ├── registry.py         ← The master list of all tools and their JSON schemas.
│   ├── data_tool.py        ← Screen securities, get pool details, get market data.
│   ├── db_tool.py          ← Query DuckDB for cached analytics results.
│   ├── analytics_tool.py   ← Run bond-level analytics on demand.
│   ├── portfolio_tool.py   ← Get portfolio summary, EVE profile, attribution.
│   ├── scenario_tool.py    ← Run rate-shock and what-if scenarios.
│   └── dashboard_tool.py   ← Fetch data for the dashboard (NAV, top performers, etc.).
│
├── data/                   ← Data sources and storage.
│   ├── position_data.py    ← Current portfolio holdings.
│   ├── pool_universe.py    ← 1,000 synthetic MBS pools (the "bond universe").
│   ├── market_data.py      ← SOFR/Treasury rate curves + cohort OAS benchmarks.
│   ├── intex_client.py     ← Client for the Intex data service (or a mock for dev).
│   ├── watchlist_store.py  ← Saves the user's watchlist to a JSON file.
│   ├── snapshot_store.py   ← SQLite-backed historical snapshot storage.
│   ├── models/             ← Trained ML model files (prepay, BGM).
│   ├── market_data/        ← Rate curve CSV files.
│   ├── cache/              ← Disk cache directory (1-day TTL).
│   └── nexus_results.duckdb← DuckDB analytics cache database file.
│
├── db/                     ← Database connection and query logic.
│   ├── connection.py       ← DuckDB singleton connection + schema creation.
│   ├── projections.py      ← NAV projection queries.
│   └── cache.py            ← DuckDB-backed risk metrics cache logic.
│
├── auth/                   ← Authentication.
│   ├── middleware.py        ← Checks every HTTP request has a valid session cookie.
│   ├── routes.py           ← Login and logout FastAPI endpoints.
│   ├── login_page.py       ← HTML for the login form.
│   ├── ldap_auth.py        ← LDAP/Active Directory password verification.
│   └── session.py          ← Creates, signs, and verifies session cookies.
│
├── ui/                     ← Every screen the user sees.
│   ├── layout.py           ← Assembles all tabs, the sidebar, and the chat panel.
│   ├── theme.py            ← Custom CSS and JavaScript for styling.
│   ├── dashboard.py        ← The dashboard tab.
│   ├── portfolio_analytics.py ← The portfolio analytics tab.
│   ├── security_analytics.py  ← Security-level analytics tab.
│   ├── security_selection.py  ← The screener tab.
│   ├── attribution.py      ← P&L attribution tab.
│   ├── whatif_sandbox.py   ← What-If sandbox tab.
│   ├── portfolio_planning.py  ← The 4-phase workflow tab.
│   ├── watchlist.py        ← User watchlist tab.
│   └── agent_panel.py      ← The floating chat window.
│
├── evals/                  ← Automated tests for agent quality (LLM-as-judge).
├── scripts/                ← Utility scripts (generate data, warm cache, calibrate).
├── tests/                  ← Unit tests.
├── docs/                   ← Documentation (you are here).
└── .env.example            ← Template showing what environment variables to set.
```

---

## 5. Core Components Explained

### 5.1 The Web Application (FastAPI + Gradio)

**What it does:** Acts as the web server — it listens for browser requests and responds with the UI.

**How it works:**

1. **FastAPI** is the outer shell. It handles HTTP at a low level — routing requests, running middleware (the auth check), and serving login/logout pages.
2. **Gradio** is mounted *inside* FastAPI at the root path (`/`). Gradio generates all the interactive UI components (charts, tables, buttons, chat box) from Python code.
3. When a user visits the site, FastAPI's auth middleware checks for a valid session cookie first. If the user is not logged in, they are redirected to the login page. If they are logged in, FastAPI lets the request pass through to the Gradio app.

**Beginner analogy:** FastAPI is like a building's security lobby (checks your badge), and Gradio is the actual office floor (where the work happens).

---

### 5.2 Authentication

**What it does:** Makes sure only authorized people can access the app.

**How it works:**

1. The user visits the site, sees a login form (`/auth/login_page.py`).
2. They enter their username and password.
3. `POST /login` hits `/auth/routes.py`, which calls `verify_credentials()` in `/auth/ldap_auth.py`.
4. `ldap_auth.py` connects to the corporate **Active Directory** (AD) via LDAP and asks: "Is this password correct for this user?"
5. If yes, `/auth/session.py` creates a signed, HTTP-only cookie (like a tamper-proof ticket) and sends it to the browser.
6. Every subsequent request, `/auth/middleware.py` reads the cookie and verifies the signature. If valid, the request proceeds. If not, the user is redirected to login.

**Development mode:** Set `LDAP_SERVER=mock://` in `.env` and any username with the mock password will be accepted. This avoids needing a real AD server during development.

**Security notes:**
- Cookies are HTTP-only (JavaScript in the browser cannot read them — protects against XSS attacks).
- Cookies are signed (the server can detect if a cookie was tampered with).
- Sessions expire after 8 hours.

---

### 5.3 The AI Chat Panel Agent System

This is a **multi-agent system** — a team of 7 specialized AI agents coordinated by one "orchestrator" agent.

**The team:**

| Agent | Specialty |
|---|---|
| **Orchestrator** | Reads the user's question and decides which specialist to call. Never answers directly. |
| **Security Selection** | Helps find cheap/fair/rich bonds in the universe. |
| **What-If Analysis** | Re-prices bonds under hypothetical changes (different CPR, rate shocks). |
| **Portfolio Analytics** | Reports OAS, duration, book yield, EVE for the current portfolio. |
| **Attribution** | Explains where profits or losses came from. |
| **Market Data** | Retrieves current interest rate curves and cohort OAS benchmarks. |
| **Dashboard** | Answers questions about the dashboard (NAV, top performers, planning status). |

**How they are defined:**

Each agent is defined as a Markdown file (`.md`) inside the `skills/` folder. The file has a YAML header (called "frontmatter") with configuration, followed by a plain-English system prompt that tells the AI its role, rules, and which tools it can use.

```markdown
---
name: security-selection
model: gpt-4o
tools:
  - screen_securities
  - get_pool_details
  - compute_bond_analytics
---

# Security Selection Agent

You are a fixed-income analyst...
[rest of the prompt]
```

This design means a prompt engineer can update an agent's behavior by editing a text file — no Python code changes needed.

**How agents call tools:**

OpenAI's API supports "tool calling" (also called "function calling"). When the LLM wants to get real data, instead of making something up, it emits a structured request like:

```json
{
  "tool": "screen_securities",
  "arguments": { "min_oas": 50, "product_type": "CC30" }
}
```

The Python code intercepts this, runs the actual `screen_securities()` function, and feeds the result back to the LLM as if it were a message. The LLM then uses the real data to form its answer.

---

### 5.4 The Portfolio Planning Workflow System

This is a separate, **stateful multi-step workflow** — quite different from the chat panel.

**The problem it solves:** Planning next quarter's bond purchases requires multiple complex decisions that build on each other. It's not a one-shot question — it's a structured process involving a human approving each step.

**The 4-phase, 5-gate structure:**

```
Phase 1: NEW VOLUME
  → How many dollars of bonds should we buy each month to hit our target?
  [Gate 1: Trader approves the volume plan, or modifies the target]

Phase 2: RISK ASSESSMENT
  → Does this plan keep duration, liquidity, and concentration within limits?
  [Gate 2: Trader accepts the risk constraints]

Phase 3: ALLOCATION
  → What mix of MBS, CMBS, and Treasuries? (3 scenarios generated)
  [Gate 3: Trader picks a scenario or enters a custom mix]

Phase 4: MBS DECOMPOSITION
  → Within the MBS allocation, break down by FNMA/FHLMC/GNMA × fixed/ARM
  [Gate 4: Trader approves the breakdown]

[Gate 5: Final confirmation — Trader confirms, revises back to Phase 3, or aborts]
  → Output: A detailed monthly purchase schedule
```

**State persistence:** After every gate, the entire workflow state is saved to a JSON file. If the trader closes their browser and comes back later, the workflow resumes exactly where it left off.

**Four specialized agents (one per phase):**

| Agent | Workflow Tools Used |
|---|---|
| **New Volume Agent** | `compute_new_volume_schedule`, `compute_volume_timing_analysis` |
| **Risk Agent** | `assess_portfolio_risk`, `estimate_duration_impact` |
| **Allocation Agent** | `generate_allocation_scenarios`, `select_allocation_scenario` |
| **MBS Decomposition Agent** | `decompose_mbs_allocation`, `build_purchase_schedule` |

---

### 5.5 The Analytics Engine

The analytics engine is the mathematical heart of the application. It runs completely independently of the AI agents — the agents just call it via tools.

**Key computations:**

#### Hull-White Monte Carlo (Interest Rate Simulation)

MBS cash flows depend heavily on future interest rates (because when rates drop, homeowners refinance, paying off their mortgages early). To price these bonds properly, the app simulates 256 possible futures of interest rates using the **Hull-White model** — a mathematical model that generates realistic paths of how short-term rates might evolve.

```
Today's rate curve
       ↓
Hull-White model generates 256 rate paths (possible futures)
       ↓
Each path: a sequence of monthly short rates for 30 years
```

#### OAS Solver (Bond Pricing)

**Option-Adjusted Spread (OAS)** is a key metric for MBS — it measures how much extra yield a bond pays compared to a risk-free Treasury, after accounting for the fact that homeowners can prepay (the "option").

To solve for OAS, the app uses **Brent's method** — a fast numerical root-finding algorithm. It tries different OAS values until it finds the one where the modeled price exactly matches the market price:

```
Market price = $98.50

Try OAS = 80bps → modeled price = $99.10 (too high)
Try OAS = 95bps → modeled price = $97.80 (too low)
Try OAS = 87bps → modeled price = $98.50 ✓ Found it!
```

#### Prepayment Model (CPR Forecasting)

Homeowners pay off their mortgages faster when interest rates fall (refinancing). The prepayment model predicts this rate (expressed as **Conditional Prepayment Rate, CPR**). The app supports two versions:

- **Standard S-curve model** (`prepay.py`): A simple mathematical formula based on the incentive to refinance.
- **Neural network model** (`neural_prepay.py`): A trained machine learning model that may be more accurate.

#### Scenario Analysis

The app runs all the above calculations under multiple rate shock scenarios simultaneously:

```
−300 bps, −200 bps, −100 bps, 0 bps, +100 bps, +200 bps, +300 bps
```

This shows how the portfolio behaves if rates move dramatically in either direction.

---

### 5.6 The Tool Registry

The tool registry (`/tool/registry.py`) is the central directory of every function that AI agents can call.

**Why it exists:** The OpenAI API requires tools to be described in a specific JSON format (called a JSON schema) so the LLM knows what each tool does and what arguments it accepts. The registry aggregates all these schemas in one place and maps tool names to their Python implementations.

**Structure:**

```python
# Each tool module exports:
#   TOOL_SCHEMAS: list of JSON schema dicts (what the LLM sees)
#   HANDLERS: dict mapping tool name → Python function (what actually runs)

# registry.py combines them all:
OPENAI_TOOLS = (
    data_tool.TOOL_SCHEMAS +
    db_tool.TOOL_SCHEMAS +
    analytics_tool.TOOL_SCHEMAS +
    # ... ~50 tools total
)

def handle_tool_call(tool_name: str, tool_input: dict) -> str:
    handler = _HANDLERS[tool_name]
    result = handler(tool_input)
    return json.dumps(result)
```

**Adding a new tool** requires only:
1. Write the Python function in the appropriate `*_tool.py` file.
2. Add its JSON schema to `TOOL_SCHEMAS` in that file.
3. Add it to `HANDLERS`.
4. Import it in `registry.py`.

No changes needed to any agent or orchestrator code.

---

### 5.7 Data Layer

The data layer is responsible for storing and retrieving all data.

**Three storage systems:**

| System | Used For | Why This Choice |
|---|---|---|
| **DuckDB** | Computed analytics results (rate paths, prepay forecasts, NAV projections) | Column-oriented, fast for aggregation queries, serverless, can query Parquet files directly |
| **SQLite** | Historical portfolio position snapshots | Lightweight, serverless, good for row-oriented data |
| **Disk Cache** (diskcache) | Short-term risk metric caching (1-day TTL) | Simple key-value with automatic expiry, avoids recomputing expensive metrics on every page load |

**Data sources:**

| Source | What It Provides |
|---|---|
| `pool_universe.py` | 1,000 synthetic MBS pools for development/demo (no real market data needed) |
| `market_data.py` | SOFR and Treasury rate curves, cohort OAS benchmarks (can be live or file-based) |
| `intex_client.py` | Cash flows and prepayment statistics per pool (live Intex API or mock) |
| `position_data.py` | Current portfolio holdings (which bonds are held, at what size and price) |

---

### 5.8 User Interface Tabs

The UI is built with Gradio's `Blocks` API. Each tab is a Python file in `/ui/`.

| Tab | File | What the User Can Do |
|---|---|---|
| **Dashboard** | `dashboard.py` | See KPI cards, NAV chart, 30-year projection, top performers, sector allocation, watchlist |
| **Portfolio Analytics** | `portfolio_analytics.py` | Run EVE stress tests, inspect OA duration profile, view book yield decomposition, see breach alerts |
| **Security Analytics** | `security_analytics.py` | Look up a specific bond by CUSIP, see its metrics, view rate-shock sensitivity table |
| **Security Selection** | `security_selection.py` | Screen the 1,000-bond universe using filters (OAS, duration, coupon, FICO, LTV), see CHEAP/FAIR/RICH labels, export to CSV |
| **Attribution** | `attribution.py` | See where the portfolio's P&L came from (OAS changes, duration exposure, yield carry) |
| **What-If Sandbox** | `whatif_sandbox.py` | Reprice a bond under a hypothetical change (e.g., "what if CPR doubles?") |
| **Portfolio Planning** | `portfolio_planning.py` | Run the 4-phase, 5-gate AI workflow to produce a quarterly purchase plan |
| **Watchlist** | `watchlist.py` | Track specific bonds of interest, see unrealized P&L |

**The floating chat panel** (`agent_panel.py`) is overlaid on top of all tabs — it is always accessible, like a chat assistant in the corner of the screen.

---

### 5.9 Observability and Tracing

When something goes wrong with an AI agent (wrong answer, slow response, excessive tool calls), developers need to see exactly what happened. Two tracing systems are used:

**OpenAI Platform Tracing:**
- Built into the OpenAI Agents SDK.
- Every time `AgentOrchestrator.chat()` is called, the code opens a trace context (`agents.trace("nexus_orchestrator")`).
- The SDK automatically logs every LLM call, tool invocation, and response within that context.
- Viewable in the OpenAI dashboard.

**W&B Weave:**
- Functions decorated with `@weave.op` are automatically instrumented.
- Logs inputs, outputs, token usage, and latency.
- W&B's Weave UI supports side-by-side comparison of runs, making it easy to see if a prompt change improved things.

Both systems capture the same information — the redundancy means if one is unavailable, you still have the other for debugging.

---

## 6. Agent Workflow — Deep Dive

### 6.1 Chat Panel: Real-Time Q&A

Here is what happens step by step when a trader types "What is my portfolio OAD and EVE?" into the chat panel:

```
Step 1: User types the question and presses Enter.

Step 2: agent_panel.py receives the message and calls
        AgentOrchestrator.chat("What is my portfolio OAD and EVE?")

Step 3: The Orchestrator opens an OpenAI trace ("nexus_orchestrator")
        and appends the user message to the conversation history.

Step 4: The Orchestrator calls GPT-4o with:
        - Its system prompt (role: "master router, never answer directly")
        - The user message
        - Available tools: [delegate_to_portfolio_analytics,
                            delegate_to_security_selection, ...]

Step 5: GPT-4o responds with a tool call:
        { "tool": "delegate_to_portfolio_analytics",
          "arguments": { "query": "What is the portfolio OAD and EVE?" } }

Step 6: The orchestrator intercepts this tool call and calls
        PortfolioAnalyticsAgent.chat("What is the portfolio OAD and EVE?")

Step 7: The Portfolio Analytics agent has its own GPT-4o call with:
        - Its system prompt (role: "report portfolio risk metrics")
        - Available tools: [get_portfolio_summary, compute_eve_profile, ...]

Step 8: GPT-4o responds with tool calls:
        { "tool": "get_portfolio_summary", "arguments": {} }
        { "tool": "compute_eve_profile", "arguments": {} }

Step 9: Python calls the real get_portfolio_summary() and compute_eve_profile()
        functions. These query the database and/or run analytics.

Step 10: Results are fed back to the Portfolio Analytics agent's GPT-4o call.

Step 11: GPT-4o produces a natural-language response:
         "Your portfolio OAD is 4.7 years. EVE under a +200 bps shock
          is −3.2%, within the −5.0% limit."

Step 12: This response is returned to the Orchestrator as the tool result.

Step 13: The Orchestrator calls GPT-4o again with this result.

Step 14: The Orchestrator synthesizes and returns the final answer to the user.

Step 15: The answer appears in the chat panel.
```

**Key details:**
- The orchestrator can call multiple sub-agents for multi-part questions.
- Each sub-agent can call multiple tools.
- The loop repeats up to 8 times per message to handle complex multi-step reasoning.
- All LLM calls and tool calls are logged in both tracing systems.

---

### 6.2 Portfolio Planning: Multi-Step Approval Workflow

Here is the full workflow from clicking "Start Planning" to receiving a purchase schedule:

```
User clicks "Start Planning" and enters:
  - Target portfolio balance: $500M
  - Current balance: $420M
  - Trader name: Jane Smith

══════════════════════════════════════
  PHASE 1: NEW VOLUME
══════════════════════════════════════

The New Volume Agent is initialized with its skill (.md) file.
It calls:
  compute_new_volume_schedule(target=500, current=420, ...)
  compute_volume_timing_analysis(...)

It produces a month-by-month schedule showing how $80M of new
purchases should be phased over 12 months.

  ┌──────────────────────────────────────┐
  │  GATE 1 — Trader Decision            │
  │  "Approve" / "Modify target" / "Reject"│
  └──────────────────────────────────────┘

Trader clicks "Approve" → Gate 1 is logged to WorkflowState.
WorkflowState is saved to JSON.

══════════════════════════════════════
  PHASE 2: RISK ASSESSMENT
══════════════════════════════════════

The Risk Agent is initialized.
It calls:
  assess_portfolio_risk(workflow_state)
  estimate_duration_impact(new_volume=80, ...)

It checks: will this plan keep OAD, liquidity score, CMBS concentration
within the firm's risk limits?

  ┌──────────────────────────────────────┐
  │  GATE 2 — Trader Decision            │
  │  "Accept" / "Adjust limits" / "Reject"│
  └──────────────────────────────────────┘

Trader clicks "Accept" → Gate 2 logged. State saved.

══════════════════════════════════════
  PHASE 3: ALLOCATION
══════════════════════════════════════

The Allocation Agent is initialized.
It calls:
  generate_allocation_scenarios(workflow_state)

It generates 3 scenarios:
  Scenario 1 — Conservative: 70% MBS, 20% CMBS, 10% Treasuries
  Scenario 2 — Moderate: 80% MBS, 15% CMBS, 5% Treasuries
  Scenario 3 — Aggressive: 90% MBS, 8% CMBS, 2% Treasuries

  ┌──────────────────────────────────────┐
  │  GATE 3 — Trader Decision            │
  │  Pick scenario 1, 2, or 3;           │
  │  or enter a custom split             │
  └──────────────────────────────────────┘

Trader selects Scenario 2 → Gate 3 logged. State saved.

══════════════════════════════════════
  PHASE 4: MBS DECOMPOSITION
══════════════════════════════════════

The MBS Decomposition Agent is initialized.
It calls:
  decompose_mbs_allocation(mbs_pct=80, total_new_volume=80)
  build_purchase_schedule(...)

It breaks down the $64M of MBS purchases into:
  FNMA 30yr Fixed: 40%
  FNMA 15yr Fixed: 20%
  FHLMC 30yr Fixed: 15%
  GNMA 30yr Fixed: 15%
  ARM products: 10%

  ┌──────────────────────────────────────┐
  │  GATE 4 — Trader Decision            │
  │  "Approve" / "Modify %" / "Reject"   │
  └──────────────────────────────────────┘

Trader approves → Gate 4 logged. State saved.

  ┌──────────────────────────────────────┐
  │  GATE 5 — Final Approval             │
  │  "Confirm" / "Revise" / "Abort"      │
  │  (Revise goes back to Phase 3)       │
  └──────────────────────────────────────┘

Trader confirms → Full purchase schedule displayed and downloadable.

═══════════════════════════════════════════
  OUTPUT: Monthly Purchase Schedule
═══════════════════════════════════════════
Month      Product       Amount    Target Coupon
2024-04    FNMA 30yr     $10M      6.0%–6.5%
2024-04    GNMA 30yr     $4M       6.0%–6.5%
2024-05    FNMA 30yr     $10M      6.0%–6.5%
...
```

**Session resumption example:**
If Jane closes her browser after Gate 2 and comes back tomorrow, the app loads `workflow_state.json` and resumes at Gate 3 — she does not lose her Phase 1 and Phase 2 results.

---

## 7. Key Design Choices

This section explains the important architectural decisions and the reasoning behind them.

### Choice 1: Skills as Markdown Files (Declarative Agent Definitions)

**What:** Each AI agent's personality, role, rules, and tool list is stored in a `.md` file, not hard-coded in Python.

**Why:** Separates *what the agent should do* (a business/domain question) from *how agents work* (a technical question). A domain expert or prompt engineer can tune an agent's behavior by editing text without touching Python code. This also makes it easy to track changes via Git — a diff of a `.md` file is meaningful to a non-programmer.

---

### Choice 2: Orchestrator-Sub-Agent Pattern (Not One Giant Agent)

**What:** One orchestrator reads the user's question and hands it to a specialist sub-agent, rather than having one all-knowing agent.

**Why:**
- **Context limits:** Each LLM call has a limited context window. A single agent handling all domains would need to be given all tool schemas and data, filling up the context. Smaller specialist agents keep context lean.
- **Accuracy:** A security selection specialist trained on relative-value rules performs better at that task than a generalist.
- **Debuggability:** If the attribution agent gives a wrong answer, you can look at just its trace, isolated from everything else.

---

### Choice 3: Two Separate Agent Systems (Chat vs. Workflow)

**What:** The chat panel (real-time) and the portfolio planning workflow (stateful, multi-step) are completely separate code paths.

**Why:**
- They have fundamentally different requirements. The chat panel needs sub-second responses and is stateless. The workflow needs to persist state for days, support branching logic, and pause for human decisions.
- Mixing them would make both worse. Keeping them separate makes each simpler.

---

### Choice 4: Monte Carlo + Brent's Method for OAS Pricing (Not Closed-Form)

**What:** Bond pricing uses simulation (256 paths of interest rates) rather than a closed-form formula.

**Why:** MBS have **negative convexity** — when rates fall, homeowners refinance, capping the bond's price appreciation. There is no simple formula that accurately captures this. Monte Carlo simulation naturally handles this because prepayment behavior can be modeled on each path separately.

Brent's method is used instead of a grid search to find OAS efficiently — it converges in ~15 iterations regardless of the starting point.

---

### Choice 5: DuckDB for Analytics Results Cache

**What:** Computed analytics results (rate paths, prepay speeds, NAV projections) are stored in DuckDB.

**Why:** The alternative is recomputing them on every page load, which would take 10–60 seconds. DuckDB is chosen over a traditional relational database (PostgreSQL) because:
- It runs in-process (no separate server to manage).
- It is optimized for analytical queries (column-oriented storage).
- It can directly query Parquet files (where large Monte Carlo path arrays are stored).

---

### Choice 6: Environment-Based Fallbacks (Mock Modes)

**What:** When `OPENAI_API_KEY` is not set, agents return helpful stub responses. When `INTEX_API_KEY` is not set, a `MockIntexClient` provides synthetic cash flows. When `LDAP_SERVER=mock://`, any password works.

**Why:** New developers should be able to clone the repo and run the app immediately without needing production credentials. Mock modes make the development experience identical to production from a code-path perspective, reducing "works on my machine" bugs.

---

### Choice 7: WorkflowState as Single Source of Truth

**What:** The entire state of a portfolio planning session is stored in one Pydantic model (`WorkflowState`) that is serialized to JSON after every gate.

**Why:**
- **No hidden state:** Every fact about the session is in one place, making it easy to debug.
- **Auditability:** Every gate decision is timestamped and stored, providing a full audit trail.
- **Resumability:** The JSON representation survives server restarts and browser closes.
- **Concurrency-safe:** Each session has its own `session_id` and its own JSON file — sessions don't interfere with each other.

---

## 8. Data Models and Databases

### WorkflowState (the Portfolio Planning Session)

This Pydantic model represents everything about a planning session. Pydantic is a Python library that validates data types automatically.

```
WorkflowState
├── session_id          (unique identifier, e.g., "a3f8-...")
├── phase               (INIT → NEW_VOLUME → RISK_ASSESSMENT → ALLOCATION → MBS_DECOMPOSITION → COMPLETE)
├── trader_name         ("Jane Smith")
│
├── Phase 1 outputs:
│   ├── next_12m_new_volume_mm    ($80M)
│   └── monthly_volumes           (list of monthly purchase targets)
│
├── Phase 2 outputs:
│   ├── risk_constraints          (duration min/max, liquidity floor, etc.)
│   └── risk_report               (plain-English summary from the Risk Agent)
│
├── Phase 3 outputs:
│   ├── allocation_scenarios      (list of 3 scenarios with projections)
│   └── selected_scenario         (which one the trader picked)
│
├── Phase 4 outputs:
│   ├── mbs_breakdown             (FNMA/FHLMC/GNMA × fixed/ARM percentages)
│   └── purchase_schedule         (final month-by-month purchase plan)
│
└── gate_decisions                (list of all gate decisions with timestamps)
```

### DuckDB Schema (Analytics Cache)

```sql
-- Stores statistics about Monte Carlo rate paths
rate_path_cache (
    curve_date, shock_bps, n_paths, n_periods, seed,   ← primary key
    mean_1yr, std_1yr, p10_1yr, p90_1yr,               ← 1-year rate statistics
    mean_10yr, std_10yr, p10_10yr, p90_10yr,           ← 10-year rate statistics
    ...                                                 ← etc. for 3yr, 5yr, 20yr, 30yr
    parquet_path                                        ← file path to full path arrays
)

-- Stores prepayment speed forecasts per bond and scenario
prepay_cache (
    pool_id, as_of_date, shock_bps, n_paths,           ← primary key
    lifetime_cpr_pct, yr1_cpr_pct, yr5_cpr_pct, ...   ← CPR projections
    wac_pct, wala_months, wam_months                   ← bond characteristics
)

-- Similar tables for interest income and NAV projections
```

### SQLite Schema (Position Snapshots)

```sql
snapshots (
    snapshot_date,  ← e.g., "2024-03-31"
    pool_id,        ← bond identifier
    cusip,          ← 9-character bond identifier (standard)
    par_mm,         ← face value held ($M)
    price,          ← market price (e.g., 98.50)
    oas, oad,       ← option-adjusted spread and duration
    nav_contribution← this bond's contribution to portfolio NAV
)
```

---

## 9. Configuration and Environment Setup

All runtime configuration is controlled through environment variables, loaded from a `.env` file by the `python-dotenv` library. This avoids hard-coding sensitive values (like API keys) in source code.

**Key variables:**

| Variable | Default | Required? | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | — | Yes (for AI features) | Authenticates calls to the OpenAI API |
| `LDAP_SERVER` | — | Yes | LDAP/AD server URL, or `mock://` for dev |
| `LDAP_MOCK_PASSWORD` | — | If using mock | Password accepted in mock mode |
| `LDAP_USER_DN_TEMPLATE` | `{username}@company.com` | For LDAP | DN format for AD bind |
| `INTEX_API_KEY` | — | No | For live Intex data (uses mock if absent) |
| `WANDB_API_KEY` | — | No | Enables W&B Weave tracing |
| `N_RATE_PATHS` | `256` | No | Number of Monte Carlo paths (higher = more accurate but slower) |
| `EVE_LIMIT_PCT` | `-5.0` | No | EVE breach alert threshold |
| `GRADIO_PORT` | `7860` | No | Port the web server listens on |

**To get started:**
```bash
cp .env.example .env
# Edit .env and set at minimum: OPENAI_API_KEY and LDAP_MOCK_PASSWORD
uv sync              # Install dependencies
python app.py        # Start the app
# Open http://localhost:7860 in your browser
```

---

## 10. How Everything Starts Up

When you run `python app.py`, here is the sequence:

```
1. Python imports all modules (triggers config.py to read .env)

2. _check_dependencies()
   → Verifies required Python packages are installed.

3. _init_directories()
   → Creates data/, data/cache/, data/market_data/ if they don't exist.

4. _init_weave()
   → If WANDB_API_KEY is set, initializes W&B Weave monitoring.
   → If not set, silently skips.

5. _print_banner()
   → Prints a startup summary to the terminal showing which features
     are enabled (OpenAI: ✓, Intex: mock, Weave: ✓, etc.)

6. DuckDB schema initialization (db/connection.py)
   → Opens nexus_results.duckdb and creates tables if they don't exist.

7. _init_scheduler()
   → Starts APScheduler.
   → Registers jobs to run the analytics pipeline on a schedule
     (e.g., every day at 6am, run warm_cache.py).

8. create_layout() (ui/layout.py)
   → Builds the full Gradio Blocks UI:
     - Creates sidebar
     - Creates each of the 9 tabs
     - Creates the floating chat panel
     - Wires all event handlers (button clicks, tab changes)

9. Mount Gradio on FastAPI
   → gr.mount_gradio_app(fastapi_app, gradio_blocks, path="/")

10. Add AuthMiddleware to FastAPI
    → Every request will now go through the auth check first.

11. uvicorn.run(fastapi_app, host="0.0.0.0", port=7860)
    → The web server starts listening for connections.
    → The terminal shows: "Running on http://localhost:7860"
```

---

## 11. Suggested Improvements for a Commercial Product

The current codebase is a well-structured prototype. To turn it into a production-grade commercial product, the following improvements are recommended:

---

### 11.1 Replace Gradio with a Purpose-Built Frontend

**Current state:** Gradio is great for rapid prototyping and data science demos, but it is not designed for complex, custom enterprise UIs.

**Recommendation:** Migrate the frontend to **React** or **Next.js** with a component library like Material UI or Ant Design, and expose a proper REST or GraphQL API from the FastAPI backend.

**Why:** Gradio limits customization of layout, responsiveness, and interactivity. A dedicated frontend framework gives full control over UX, supports real-time updates (WebSockets), and allows professional-grade design that meets enterprise buyer expectations.

---

### 11.2 Persistent User Management and Multi-Tenancy

**Current state:** Authentication is validated against LDAP/AD, but there is no database of users, roles, or permissions. All users see the same portfolio.

**Recommendation:**
- Add a **users table** in a proper database (PostgreSQL recommended).
- Implement **Role-Based Access Control (RBAC)**: e.g., Trader vs. Risk Manager vs. Read-Only Analyst.
- Support **multi-tenancy**: different teams/firms with their own isolated data.
- Consider **SSO (Single Sign-On)** via OAuth 2.0 / SAML for enterprise integration.

---

### 11.3 Replace SQLite and DuckDB with PostgreSQL

**Current state:** SQLite (position snapshots) and DuckDB (analytics cache) are file-based, single-process databases.

**Recommendation:** Use **PostgreSQL** as the primary relational database. Consider **TimescaleDB** (a PostgreSQL extension) for time-series analytics. Use **Redis** for caching instead of diskcache.

**Why:** File-based databases do not scale to multiple concurrent users or multiple server instances. PostgreSQL supports concurrent writes, replication, backups, and cloud hosting (AWS RDS, Azure Database for PostgreSQL).

---

### 11.4 Proper Secret Management

**Current state:** API keys and passwords are stored in a `.env` file on the server.

**Recommendation:** Use a secrets manager:
- **AWS Secrets Manager** or **HashiCorp Vault** in cloud deployments.
- Never store secrets in `.env` files in production.
- Rotate API keys automatically.
- Audit every access to secrets.

---

### 11.5 Containerization and Horizontal Scaling

**Current state:** The app runs as a single Python process on one machine.

**Recommendation:**
- **Dockerize** the application (`Dockerfile` + `docker-compose.yml`).
- Deploy to **Kubernetes** (or a managed container service like AWS ECS).
- Separate the compute-heavy analytics pipeline into **background workers** (Celery + Redis, or AWS Lambda).
- Run multiple instances of the web server behind a **load balancer**.
- Move the APScheduler jobs to a proper job queue (e.g., **Celery Beat** or **AWS EventBridge**).

---

### 11.6 Model Risk and AI Governance

**Current state:** The app uses OpenAI's GPT-4o for all LLM calls. There is limited control over model versions or output validation.

**Recommendation:**
- Pin specific **model versions** (not just "gpt-4o") to ensure reproducibility.
- Implement **output validation**: parse structured outputs (Pydantic models) from agent responses; reject malformed outputs.
- Add **guardrails**: detect and block harmful or nonsensical queries before they reach the LLM.
- Maintain a **model registry**: track which model version was used for each analysis (regulatory requirement in financial services).
- Consider **fine-tuning** on firm-specific vocabulary and data once enough usage data is collected.
- Evaluate whether a **self-hosted LLM** (e.g., via Azure OpenAI or a private deployment) is required for data residency / compliance reasons.

---

### 11.7 Real Market Data Integration

**Current state:** The pool universe (1,000 bonds) is synthetic. The `MockIntexClient` provides simulated cash flows.

**Recommendation:**
- Integrate with **real Intex API** for live MBS cash flows.
- Subscribe to live **Bloomberg** or **ICE Data Services** for rate curves, bond prices, and reference data.
- Implement a **data pipeline** (e.g., using Apache Airflow or Prefect) to ingest, validate, and normalize market data daily.
- Add **data quality checks**: alert if a rate curve looks stale or if a bond's price is an outlier.

---

### 11.8 Comprehensive Testing

**Current state:** There are unit tests (`/tests/`) and LLM evaluation suites (`/evals/`), but coverage is not comprehensive.

**Recommendation:**
- Aim for >80% unit test coverage of analytics functions.
- Add **integration tests** that run the full workflow against a test database.
- Implement **regression tests** for analytics outputs: if a model change shifts OAS calculations by more than a threshold, a test should fail.
- Add **load tests** (e.g., using Locust) to understand how many concurrent users the system can handle.
- Expand the **LLM evaluation suite** with more edge cases and adversarial queries.

---

### 11.9 Regulatory and Audit Compliance

For a commercial financial product, regulatory requirements are non-negotiable:

- **Full audit logging:** Every user action, data query, and model output must be logged with user ID, timestamp, and inputs.
- **Data lineage:** It must be possible to trace any figure in the UI back to the raw data and model version that produced it.
- **SOC 2 compliance:** Controls for security, availability, processing integrity, confidentiality, and privacy.
- **Model validation:** Quantitative models (OAS solver, prepay model) must be independently validated before use in live trading decisions.
- **Data retention policies:** Define how long logs, snapshots, and session data are retained, in compliance with regulations (e.g., SEC 17a-4 for broker-dealers).

---

### 11.10 UX and Workflow Improvements

- **Real-time collaboration:** Allow multiple traders to view and comment on the same planning session.
- **Email/Slack notifications:** Notify traders when a scheduled workflow run completes or when a risk limit is breached.
- **Explainability:** For every AI agent answer, provide a "Show reasoning" button that reveals the tool calls and data the agent used.
- **Mobile responsiveness:** The current Gradio UI is desktop-only. A responsive design would allow risk managers to check the dashboard on their phones.
- **Dark mode:** A staple of trading desk UIs.

---

## What Is This Document Called in Software Development?

This type of document is called a **System Architecture Document (SAD)**, also sometimes called a:

- **Software Architecture Document**
- **Technical Design Document (TDD)**
- **Software Design Document (SDD)**

It serves as the authoritative reference for how a system is structured, why key decisions were made, and how its components interact. It is typically written after the initial design is settled and updated as the system evolves.

Other related document types you may encounter:
- **Architecture Decision Record (ADR):** A short document capturing a single architectural decision and its rationale (e.g., "Why we chose DuckDB over PostgreSQL").
- **Runbook:** Operational instructions for deploying and maintaining the system.
- **API Reference:** Detailed documentation of every endpoint and function signature.
- **Requirements Document:** What the system should do (the *what*), as opposed to the SAD which explains *how* it does it.
