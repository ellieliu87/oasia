"""
Scenario analysis for MBS pools.

Applies rate shocks to the term structure, regenerates paths, and recomputes analytics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np

from analytics.rate_paths import TermStructure, RatePaths, generate_rate_paths
from analytics.oas_solver import BondAnalytics, compute_analytics


# ---------------------------------------------------------------------------
# Standard scenarios
# ---------------------------------------------------------------------------

STANDARD_SCENARIOS = {
    "Base":       {"parallel_shift": 0},
    "Up 100":     {"parallel_shift": 100},
    "Up 200":     {"parallel_shift": 200},
    "Up 300":     {"parallel_shift": 300},
    "Down 100":   {"parallel_shift": -100},
    "Down 200":   {"parallel_shift": -200},
    "Down 300":   {"parallel_shift": -300},
    "Flattener":  {"short_shift": 50,  "long_shift": -50},
    "Steepener":  {"short_shift": -50, "long_shift": 50},
}


# ---------------------------------------------------------------------------
# ScenarioResult
# ---------------------------------------------------------------------------

@dataclass
class ScenarioResult:
    scenario_name: str
    analytics: BondAnalytics
    price_delta: float   # vs base
    oas_delta: float     # vs base bps
    oad_delta: float     # vs base years


# ---------------------------------------------------------------------------
# Scenario runner
# ---------------------------------------------------------------------------

def _apply_scenario(curve: TermStructure, scenario: dict) -> TermStructure:
    """Apply a rate scenario dict to a TermStructure."""
    parallel = scenario.get("parallel_shift", 0)
    short_shift = scenario.get("short_shift", 0)
    long_shift = scenario.get("long_shift", 0)
    return curve.shifted(
        parallel_shift_bps=parallel,
        short_shift_bps=short_shift,
        long_shift_bps=long_shift,
    )


def run_scenarios(
    pool_id: str,
    pool_chars,
    market_price: float,
    settlement_date: date,
    base_curve: TermStructure,
    scenarios: dict = None,
    n_paths: int = None,
    n_periods: int = 360,
    seed: int = 42,
    intex_client=None,
    prepay_model=None,
) -> dict[str, ScenarioResult]:
    """
    Run rate scenarios for a single MBS pool.

    For each scenario:
    1. Apply rate shock to base_curve
    2. Regenerate rate paths
    3. Recompute full analytics

    Parameters
    ----------
    pool_id : str
    pool_chars : PoolCharacteristics
    market_price : float
        Market price as % par (held constant across scenarios).
    settlement_date : date
    base_curve : TermStructure
    scenarios : dict, optional
        Dict of {name: shock_params}. Defaults to STANDARD_SCENARIOS.
    n_paths : int, optional
        Number of Monte Carlo paths.
    n_periods : int
        Number of monthly periods.
    seed : int
        Random seed.
    intex_client : optional
    prepay_model : optional

    Returns
    -------
    dict[str, ScenarioResult]
    """
    if scenarios is None:
        scenarios = STANDARD_SCENARIOS

    if n_paths is None:
        try:
            from config import Config
            n_paths = Config.N_RATE_PATHS
        except Exception:
            n_paths = 64  # smaller default for scenario runs

    results = {}
    base_analytics = None

    # Pre-generate all scenarios to track base
    for scenario_name, shock_params in scenarios.items():
        # Apply shock to curve
        shocked_curve = _apply_scenario(base_curve, shock_params)

        # Generate rate paths for this scenario
        rate_paths = generate_rate_paths(
            curve=shocked_curve,
            n_paths=n_paths,
            n_periods=n_periods,
            seed=seed,
        )

        # Compute analytics
        analytics = compute_analytics(
            pool_id=pool_id,
            pool_chars=pool_chars,
            market_price=market_price,
            settlement_date=settlement_date,
            rate_paths=rate_paths,
            intex_client=intex_client,
            prepay_model=prepay_model,
        )

        results[scenario_name] = analytics

        if scenario_name == "Base":
            base_analytics = analytics

    # If no base scenario was run, use the first result
    if base_analytics is None:
        base_analytics = next(iter(results.values()))

    # Build ScenarioResult objects with deltas vs base
    scenario_results = {}
    for scenario_name, analytics in results.items():
        price_delta = analytics.model_price - base_analytics.model_price
        oas_delta = analytics.oas - base_analytics.oas
        oad_delta = analytics.oad - base_analytics.oad

        scenario_results[scenario_name] = ScenarioResult(
            scenario_name=scenario_name,
            analytics=analytics,
            price_delta=round(price_delta, 4),
            oas_delta=round(oas_delta, 2),
            oad_delta=round(oad_delta, 3),
        )

    return scenario_results
