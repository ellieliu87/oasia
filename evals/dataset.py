"""
Evaluation dataset for the Oasia multi-agent workflow.

Each record contains:
  question          — what the user asks the agent
  context           — optional background the evaluator needs
  expected_topics   — concepts/terms the response MUST address
  expected_tools    — tool names we expect the agent to have called
  agent_type        — which specialist agent should handle this

EVAL_DATASET          — NEXUS chat panel agents (used by run_evals.py)
PLANNING_EVAL_DATASET — Portfolio Planning workflow agents (used by run_workflow_evals.py)

These records are consumed by evals/run_evals.py /
evals/run_workflow_evals.py and scored by the LLM-as-judge
evaluators in evals/judges.py.
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


# ---------------------------------------------------------------------------
# Portfolio Planning workflow evaluation dataset
# ---------------------------------------------------------------------------
# Each record targets one of the four planning-phase agents:
#   new_volume        — builds the monthly purchase schedule
#   risk_assessment   — evaluates duration/liquidity/concentration risk
#   allocation        — proposes product-mix scenarios
#   mbs_decomposition — breaks the MBS bucket into sub-product allocations
#
# The "prompt" field mirrors the actual prompt forwarded to the agent in
# ui/portfolio_planning.py so the eval exercises the same code path.
# "state_overrides" supplies a minimal WorkflowState fixture; missing
# fields are filled with WorkflowState defaults by run_workflow_evals.py.
# ---------------------------------------------------------------------------

PLANNING_EVAL_DATASET: list[dict] = [
    # ── New Volume Agent ──────────────────────────────────────────────
    {
        "id": "NV-01",
        "agent_name": "new_volume",
        "prompt": (
            "Calculate the full new volume schedule and provide a summary. "
            "The bank targets $5,000 MM total portfolio balance in 12 months "
            "growing to $6,500 MM over 10 years."
        ),
        "context": (
            "New-volume agent receives pool universe data and target balance trajectory. "
            "It must produce a month-by-month schedule of new MBS purchases."
        ),
        "state_overrides": {
            "next_12m_new_volume_mm": 500.0,
            "total_10yr_new_volume_mm": 1500.0,
        },
        "expected_topics": [
            "new volume", "monthly", "schedule", "balance", "purchase",
        ],
        "expected_tools": [],   # new_volume agent uses tool-less LLM reasoning
    },
    {
        "id": "NV-02",
        "agent_name": "new_volume",
        "prompt": (
            "The target total balance is $4,200 MM at month 12 with current "
            "existing balance of $3,800 MM. Calculate the required new volume "
            "by month assuming a 6% annual prepay rate on existing balances."
        ),
        "context": "Stress test for new volume calculation with slower growth trajectory.",
        "state_overrides": {
            "next_12m_new_volume_mm": 400.0,
            "total_10yr_new_volume_mm": 1200.0,
        },
        "expected_topics": [
            "prepay", "CPR", "existing balance", "new volume", "monthly",
        ],
        "expected_tools": [],
    },

    # ── Risk Assessment Agent ─────────────────────────────────────────
    {
        "id": "RA-01",
        "agent_name": "risk_assessment",
        "prompt": (
            "Evaluate the risk profile for the proposed new volume of $500 MM. "
            "Current portfolio OAD is 4.8 years. Risk appetite is moderate. "
            "Check duration, liquidity, and concentration constraints."
        ),
        "context": (
            "Risk assessment agent receives proposed purchase volumes and existing "
            "portfolio metrics, then evaluates whether constraints are met."
        ),
        "state_overrides": {
            "next_12m_new_volume_mm": 500.0,
            "risk_constraints": {
                "duration_min": 3.5,
                "duration_max": 6.5,
                "current_portfolio_duration": 4.8,
                "projected_duration_after_purchase": 5.1,
                "liquidity_score_min": 6.0,
                "projected_liquidity_score": 7.2,
                "max_cmbs_pct": 30.0,
                "max_arm_pct": 20.0,
            },
        },
        "expected_topics": [
            "OAD", "duration", "liquidity", "concentration", "constraint", "risk",
        ],
        "expected_tools": [],
    },
    {
        "id": "RA-02",
        "agent_name": "risk_assessment",
        "prompt": (
            "The proposed allocation includes 35% CMBS. Evaluate whether this breaches "
            "concentration limits and recommend an adjustment to stay within policy."
        ),
        "context": "Breach scenario: CMBS exceeds 30% max concentration limit.",
        "state_overrides": {
            "next_12m_new_volume_mm": 500.0,
            "risk_constraints": {
                "duration_min": 3.5,
                "duration_max": 6.5,
                "current_portfolio_duration": 5.0,
                "projected_duration_after_purchase": 5.2,
                "liquidity_score_min": 6.0,
                "projected_liquidity_score": 6.8,
                "max_cmbs_pct": 30.0,
                "max_arm_pct": 20.0,
            },
        },
        "expected_topics": [
            "CMBS", "concentration", "breach", "limit", "recommend",
        ],
        "expected_tools": [],
    },

    # ── Allocation Agent ──────────────────────────────────────────────
    {
        "id": "AL-01",
        "agent_name": "allocation",
        "prompt": (
            "Generate three allocation scenarios (conservative, moderate, aggressive) "
            "for $500 MM new volume. Show MBS%, CMBS%, Treasury%, projected duration, "
            "liquidity score, and yield for each."
        ),
        "context": (
            "Allocation agent proposes product-mix scenarios given volume, "
            "risk constraints, and current market conditions."
        ),
        "state_overrides": {
            "next_12m_new_volume_mm": 500.0,
            "risk_constraints": {
                "duration_min": 3.5,
                "duration_max": 6.5,
                "current_portfolio_duration": 4.8,
                "projected_duration_after_purchase": 5.0,
                "liquidity_score_min": 6.0,
                "projected_liquidity_score": 7.0,
                "max_cmbs_pct": 30.0,
                "max_arm_pct": 20.0,
            },
        },
        "expected_topics": [
            "conservative", "moderate", "aggressive", "MBS", "CMBS",
            "Treasury", "duration", "yield", "scenario",
        ],
        "expected_tools": [],
    },
    {
        "id": "AL-02",
        "agent_name": "allocation",
        "prompt": (
            "Given the trader has chosen the moderate scenario, finalize the allocation "
            "plan and produce a purchase schedule with product types, amounts, target "
            "coupon ranges, and priority order."
        ),
        "context": "Post-gate allocation finalization after trader selects moderate scenario.",
        "state_overrides": {
            "next_12m_new_volume_mm": 500.0,
            "selected_scenario": {
                "scenario_id": "moderate",
                "label": "Moderate",
                "mbs_pct": 65.0,
                "cmbs_pct": 20.0,
                "treasury_pct": 15.0,
                "mbs_mm": 325.0,
                "cmbs_mm": 100.0,
                "treasury_mm": 75.0,
                "total_new_volume_mm": 500.0,
                "projected_duration": 5.1,
                "projected_liquidity_score": 7.2,
                "projected_yield_pct": 5.8,
                "rationale": "Balanced duration and yield with adequate liquidity.",
            },
        },
        "expected_topics": [
            "purchase schedule", "MBS", "CMBS", "Treasury",
            "coupon", "duration", "priority",
        ],
        "expected_tools": [],
    },

    # ── MBS Decomposition Agent ───────────────────────────────────────
    {
        "id": "MD-01",
        "agent_name": "mbs_decomposition",
        "prompt": (
            "Break down the $325 MM MBS allocation into FNMA Fixed 30yr, "
            "FHLMC Fixed 30yr, GNMA Fixed 30yr, FNMA Fixed 15yr, and ARM buckets. "
            "Target OAS > 50 bps, OAD 4.5–5.5 yr, FICO ≥ 700."
        ),
        "context": (
            "MBS decomposition agent receives the total MBS dollar amount and "
            "investment criteria, then allocates across sub-product types."
        ),
        "state_overrides": {
            "next_12m_new_volume_mm": 500.0,
            "selected_scenario": {
                "scenario_id": "moderate",
                "label": "Moderate",
                "mbs_pct": 65.0,
                "cmbs_pct": 20.0,
                "treasury_pct": 15.0,
                "mbs_mm": 325.0,
                "cmbs_mm": 100.0,
                "treasury_mm": 75.0,
                "total_new_volume_mm": 500.0,
                "projected_duration": 5.1,
                "projected_liquidity_score": 7.2,
                "projected_yield_pct": 5.8,
                "rationale": "Balanced duration and yield with adequate liquidity.",
            },
        },
        "expected_topics": [
            "FNMA", "FHLMC", "GNMA", "ARM", "30yr", "15yr",
            "OAS", "OAD", "FICO", "breakdown",
        ],
        "expected_tools": [],
    },
    {
        "id": "MD-02",
        "agent_name": "mbs_decomposition",
        "prompt": (
            "The current pool universe shows GNMA pools trading 8 bps cheaper than "
            "FNMA on average. Adjust the MBS sub-allocation to overweight GNMA while "
            "keeping total MBS at $325 MM and OAD within 4.5–5.5 yr."
        ),
        "context": "Relative value tilt: GNMA cheapness versus FNMA in current market.",
        "state_overrides": {
            "next_12m_new_volume_mm": 500.0,
            "selected_scenario": {
                "scenario_id": "moderate",
                "label": "Moderate",
                "mbs_pct": 65.0,
                "cmbs_pct": 20.0,
                "treasury_pct": 15.0,
                "mbs_mm": 325.0,
                "cmbs_mm": 100.0,
                "treasury_mm": 75.0,
                "total_new_volume_mm": 500.0,
                "projected_duration": 5.1,
                "projected_liquidity_score": 7.2,
                "projected_yield_pct": 5.8,
                "rationale": "Balanced duration and yield with adequate liquidity.",
            },
        },
        "expected_topics": [
            "GNMA", "overweight", "relative value", "OAD", "MBS", "allocation",
        ],
        "expected_tools": [],
    },
]
