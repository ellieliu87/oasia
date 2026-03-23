"""
Evaluation dataset for the Oasia multi-agent workflow.

Each record contains:
  question          — what the user asks the agent
  context           — optional background the evaluator needs
  expected_topics   — concepts/terms the response MUST address
  expected_tools    — tool names we expect the agent to have called
  agent_type        — which specialist agent should handle this

These records are consumed by evals/run_evals.py and scored by
the LLM-as-judge evaluators in evals/judges.py.
"""
from __future__ import annotations

EVAL_DATASET: list[dict] = [
    # ── Security Selection ─────────────────────────────────────────────
    {
        "id": "SS-01",
        "agent_type": "security_selection",
        "question": "Screen for cheap CC30 pools with OAS above 55 bps and FICO above 720.",
        "context": "User is a portfolio manager looking for relative value in CC30 sector.",
        "expected_topics": ["OAS", "CC30", "FICO", "cheap", "screen"],
        "expected_tools": ["screen_securities"],
    },
    {
        "id": "SS-02",
        "agent_type": "security_selection",
        "question": "What is the OAD and convexity profile of pool FNMA-TEST-001? How does it compare to the CC30 universe median?",
        "context": "User wants to understand duration risk for a specific pool.",
        "expected_topics": ["OAD", "convexity", "pool", "duration"],
        "expected_tools": ["get_pool_details", "compute_bond_analytics"],
    },
    {
        "id": "SS-03",
        "agent_type": "security_selection",
        "question": "Find the top 5 pools by OAS across all product types. Give me their OAD and convexity.",
        "context": "Broad universe search for highest-spread opportunities.",
        "expected_topics": ["OAS", "OAD", "convexity", "product type", "spread"],
        "expected_tools": ["screen_securities", "compute_bond_analytics"],
    },

    # ── Portfolio Analytics ────────────────────────────────────────────
    {
        "id": "PA-01",
        "agent_type": "portfolio_analytics",
        "question": "What is the current portfolio weighted OAS, OAD, and book yield?",
        "context": "Standard morning briefing request.",
        "expected_topics": ["OAS", "OAD", "book yield", "weighted", "portfolio"],
        "expected_tools": ["get_portfolio_summary"],
    },
    {
        "id": "PA-02",
        "agent_type": "portfolio_analytics",
        "question": "Compute the EVE profile for the portfolio across rate shocks from -300 to +300 bps. Flag any breach of the -5% limit.",
        "context": "Risk manager needs EVE sensitivity for ALCO reporting.",
        "expected_topics": ["EVE", "rate shock", "breach", "-5%", "bps"],
        "expected_tools": ["compute_eve_profile"],
    },
    {
        "id": "PA-03",
        "agent_type": "portfolio_analytics",
        "question": "How much of the book value is allocated to GNMA vs conventional pools?",
        "context": "Sector concentration analysis.",
        "expected_topics": ["GNMA", "conventional", "allocation", "book value", "sector"],
        "expected_tools": ["get_portfolio_positions", "get_portfolio_summary"],
    },

    # ── What-If Analysis ──────────────────────────────────────────────
    {
        "id": "WI-01",
        "agent_type": "what_if_analysis",
        "question": "If I increase the WAC on pool CC30-TEST by 50 bps, how does the OAS change?",
        "context": "Loan-level modification sensitivity.",
        "expected_topics": ["WAC", "OAS", "what-if", "modify", "sensitivity"],
        "expected_tools": ["run_what_if"],
    },
    {
        "id": "WI-02",
        "agent_type": "what_if_analysis",
        "question": "Run a parallel rate shock of +200 bps on pool GN30-TEST. Show me OAS, OAD, and convexity before and after.",
        "context": "Rate scenario stress test for a single pool.",
        "expected_topics": ["+200", "rate shock", "OAS", "OAD", "convexity", "before", "after"],
        "expected_tools": ["run_scenario_analysis"],
    },

    # ── Attribution ───────────────────────────────────────────────────
    {
        "id": "AT-01",
        "agent_type": "attribution",
        "question": "Decompose the portfolio OAD change over the last month into its drivers.",
        "context": "Risk committee wants attribution of duration drift.",
        "expected_topics": ["OAD", "attribution", "drivers", "duration", "change"],
        "expected_tools": ["get_attribution", "get_portfolio_summary"],
    },

    # ── Market Data ───────────────────────────────────────────────────
    {
        "id": "MD-01",
        "agent_type": "market_data",
        "question": "What is today's SOFR curve? Show me the 2-year and 10-year rates.",
        "context": "Analyst needs the current rate environment for pricing.",
        "expected_topics": ["SOFR", "2-year", "10-year", "curve", "rate"],
        "expected_tools": ["get_market_data"],
    },
]
