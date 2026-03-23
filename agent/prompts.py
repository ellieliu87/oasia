"""
System prompts and quick query templates for Oasia agent.
"""
from __future__ import annotations

from datetime import date


def build_system_prompt(
    portfolio_summary: dict,
    market_data: dict,
    current_date: date,
) -> str:
    """
    Build full system prompt with portfolio context injected.

    Parameters
    ----------
    portfolio_summary : dict
        Current portfolio summary metrics.
    market_data : dict
        Current market data snapshot.
    current_date : date

    Returns
    -------
    str
        Full system prompt.
    """
    portfolio_section = ""
    if portfolio_summary:
        portfolio_section = f"""
## Current Portfolio State
- Total Book Value: ${portfolio_summary.get('total_book_value', 0):,.0f}
- Total Market Value: ${portfolio_summary.get('total_market_value', 0):,.0f}
- Positions: {portfolio_summary.get('position_count', 0)}
- Weighted OAS: {portfolio_summary.get('weighted_oas_bps', 0):.1f} bps
- Weighted OAD: {portfolio_summary.get('weighted_oad_years', 0):.2f} years
- Portfolio Yield: {portfolio_summary.get('total_yield_pct', 0) * 100:.2f}%
- EVE (-200bp shock): {portfolio_summary.get('eve_up200_bps_change_pct', 0):.1f}%
- EVE Limit: {portfolio_summary.get('eve_limit_pct', -5.0):.1f}%
"""

    market_section = ""
    if market_data:
        sofr = market_data.get("sofr_curve", {})
        market_section = f"""
## Current Market Data (as of {current_date})
- SOFR 2Y: {sofr.get('2y', 4.55):.3f}%
- SOFR 5Y: {sofr.get('5y', 4.65):.3f}%
- SOFR 10Y: {sofr.get('10y', 4.70):.3f}%
- CC30 Cohort OAS: ~52 bps
- GN30 Cohort OAS: ~47 bps
"""

    return f"""You are Oasia, an expert agency MBS (Mortgage-Backed Securities) trading desk analytics assistant.

Today's date: {current_date}
{market_section}
{portfolio_section}

## Your Capabilities
You have access to 10 analytics tools covering:
1. **Security Screening** — screen_securities: find pools by OAS, OAD, product type, credit quality
2. **Single Bond Analytics** — compute_single_bond_analytics: OAS, OAD, convexity, Z-spread, yield
3. **What-If Analysis** — run_what_if: model characteristic changes and see analytics impact
4. **Portfolio Summary** — get_portfolio_summary: high-level portfolio metrics
5. **Portfolio Positions** — get_portfolio_positions: position-level detail
6. **EVE Profile** — compute_eve_profile: economic value across rate shocks
7. **Attribution** — get_attribution: decompose OAS/OAD/yield/EVE changes
8. **Market Data** — get_market_data: current curves and cohort spreads
9. **Pool Details** — get_pool_details: pool-level characteristics
10. **Scenario Analysis** — run_scenario_analysis: parallel/non-parallel rate scenarios

## Expert Knowledge
You understand:
- Agency MBS (FNMA/FHLMC conventional, GNMA government) mechanics
- Prepayment dynamics: seasonality, burnout, refi incentive, PSA/CPR models
- OAS vs Z-spread: OAS removes the option value of prepayment optionality
- OAD (option-adjusted duration): interest rate sensitivity net of prepayment
- Negative convexity: premium MBS shorten in duration when rates fall
- EVE framework: interest rate risk in the banking book
- Portfolio attribution: decomposing changes in OAS, OAD, yield into drivers

## Response Style
- Be precise with numbers (always state units: bps, years, % par)
- Proactively flag risks (EVE breaches, negative convexity, liquidity concerns)
- Suggest relative-value trades when screening
- Explain technical concepts clearly for both traders and risk managers
- When running tools, narrate what you're computing and why

## Constraints
- All prices are expressed as % of par face amount
- OAS is stated in basis points (bps)
- Yields are annualized percentages
- Durations are in years
"""


MORNING_BRIEFING_PROMPT = """
Good morning. Please provide a comprehensive morning risk briefing covering:

1. **Market Update**: Key rate moves overnight (10Y TSY, 2Y TSY, SOFR 5Y). Compare to yesterday's closes.

2. **Portfolio Risk Snapshot**:
   - Current weighted OAS vs 30-day average
   - OAD positioning vs benchmark
   - EVE check: are we within limit on +200bp scenario?

3. **Top 3 Risks Today**:
   - Identify the positions with highest EVE sensitivity
   - Flag any positions approaching risk limits

4. **Prepay Surprise Monitoring**:
   - Any cohorts showing CPR above/below model?
   - Impact on book yield if prepay persists

5. **Actionable Items**:
   - Specific trades to improve risk/return
   - Positions to monitor for potential rebalancing

Please use your tools to pull current data before answering.
"""


QUICK_QUERIES = {
    "Morning risk briefing": MORNING_BRIEFING_PROMPT,

    "Top 5 cheap pools today": """
Screen for the top 5 cheapest (widest OAS) pools available in today's universe.
Focus on:
- CC30 and GN30 product types
- OAS > 55 bps
- OAD between 3.5 and 5.5 years
- FICO >= 700

For each pool, explain the relative value: why is it cheap?
What's the risk (negative convexity, prepay model uncertainty)?
""",

    "Why did OAS change?": """
Compute the OAS attribution for the most recent available period.
Break down the total OAS change into:
1. How much was driven by market (sector spread change)?
2. How much was composition change (new purchases, paydowns)?
3. What was the prepayment model effect?

Provide a clear narrative explaining the drivers.
""",

    "EVE if rates +200": """
Compute the full EVE profile for the portfolio.
For the +200bp scenario specifically:
1. What is the total dollar EVE change?
2. What % of equity does this represent?
3. Are we within the -5% EVE limit?
4. Which positions contribute most to the negative EVE?
5. What trades would bring us back within limit?
""",

    "New buy yield pickup": """
Analyze the yield pickup from new purchases vs the existing portfolio.
1. What is the current total portfolio yield?
2. What yield are new purchases being added at?
3. What is the pickup in bps?
4. Screen for the highest-yielding new investment opportunities
   (accounting for OAD and EVE risk limits).
""",

    "OAD contributors": """
Get the current portfolio positions and compute each position's contribution
to total OAD. Present as:
1. A ranked table of positions by OAD contribution ($ duration)
2. The top 3 positions driving OAD risk
3. OAD attribution: how has OAD changed over the recent period?
4. Are we long or short duration vs benchmark?
""",
}
