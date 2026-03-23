"""
Tests for scenario analysis.

All tests use MockIntexClient and stub PrepayModel — no API keys required.
"""
import numpy as np
import pytest
from datetime import date

from analytics.rate_paths import TermStructure, generate_rate_paths
from analytics.prepay import PoolCharacteristics, PrepayModel
from analytics.scenarios import run_scenarios, STANDARD_SCENARIOS, ScenarioResult
from analytics.oas_solver import compute_analytics
from data.intex_client import MockIntexClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def flat_curve():
    """Flat term structure at 4.7%."""
    tenors = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    rates = np.full_like(tenors, 0.047)
    return TermStructure(tenors=tenors, rates=rates)


@pytest.fixture
def pool_chars_30yr():
    """Standard 30-year CC30 pool."""
    return PoolCharacteristics(
        coupon=0.06,
        wac=0.065,
        wala=12,
        wam=348,
        loan_size=400_000,
        ltv=0.75,
        fico=750,
        pct_ca=0.15,
        pct_purchase=0.65,
        product_type="CC30",
        pool_id="TEST-POOL-30YR",
        current_balance=1_000_000,
    )


@pytest.fixture
def mock_client():
    return MockIntexClient()


@pytest.fixture
def prepay_model():
    return PrepayModel()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_price_monotonic_with_rates(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """
    Higher rate shock → lower price for a positive-duration bond.

    This is the fundamental bond math property: price and yield move inversely.
    """
    # Run a subset of scenarios to keep test fast
    scenarios = {
        "Base": {"parallel_shift": 0},
        "Up 100": {"parallel_shift": 100},
        "Up 200": {"parallel_shift": 200},
        "Down 100": {"parallel_shift": -100},
    }

    results = run_scenarios(
        pool_id="TEST-POOL-30YR",
        pool_chars=pool_chars_30yr,
        market_price=100.0,
        settlement_date=date(2025, 1, 1),
        base_curve=flat_curve,
        scenarios=scenarios,
        n_paths=32,
        seed=42,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    # Extract model prices
    base_price = results["Base"].analytics.model_price
    up100_price = results["Up 100"].analytics.model_price
    up200_price = results["Up 200"].analytics.model_price
    down100_price = results["Down 100"].analytics.model_price

    # Monotonicity: higher rates → lower prices
    assert up100_price < base_price, (
        f"Up 100bp price ({up100_price:.4f}) should be < base ({base_price:.4f})"
    )
    assert up200_price < up100_price, (
        f"Up 200bp price ({up200_price:.4f}) should be < Up 100bp ({up100_price:.4f})"
    )
    assert down100_price > base_price, (
        f"Down 100bp price ({down100_price:.4f}) should be > base ({base_price:.4f})"
    )


def test_oas_roughly_stable_across_parallel_shifts(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """
    OAS should be relatively stable across parallel rate shifts.

    The whole point of OAS is to provide a rate-normalized spread measure.
    While OAS isn't perfectly stable (it can change due to prepayment model
    and option value changes), it should be much more stable than Z-spread.
    """
    scenarios = {
        "Base": {"parallel_shift": 0},
        "Up 100": {"parallel_shift": 100},
        "Down 100": {"parallel_shift": -100},
    }

    results = run_scenarios(
        pool_id="TEST-POOL-30YR",
        pool_chars=pool_chars_30yr,
        market_price=100.0,
        settlement_date=date(2025, 1, 1),
        base_curve=flat_curve,
        scenarios=scenarios,
        n_paths=32,
        seed=42,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    base_oas = results["Base"].analytics.oas
    up_oas = results["Up 100"].analytics.oas
    down_oas = results["Down 100"].analytics.oas

    # OAS should be within 100 bps of base across ±100bp shifts
    # (allowing for model/numerical effects)
    assert abs(up_oas - base_oas) < 100.0, (
        f"OAS change of {abs(up_oas - base_oas):.1f} bps across +100bp shift is too large"
    )
    assert abs(down_oas - base_oas) < 100.0, (
        f"OAS change of {abs(down_oas - base_oas):.1f} bps across -100bp shift is too large"
    )


def test_eve_sign_consistency(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """
    Rate rise → negative ΔEVE for a positive duration portfolio.

    A standard MBS with positive duration loses value when rates rise.
    """
    from analytics.risk import compute_eve
    from analytics.prepay import project_prepay_speeds

    # Build simple portfolio
    rate_paths = generate_rate_paths(curve=flat_curve, n_paths=32, n_periods=360, seed=42)
    cpr = project_prepay_speeds(pool_chars_30yr, rate_paths, model=prepay_model)

    positions = [{
        "pool_id": "TEST-POOL-30YR",
        "pool_chars": pool_chars_30yr,
        "face_amount": 1_000_000,
        "book_price": 100.0,
    }]

    eve_results = compute_eve(
        portfolio_positions=positions,
        base_curve=flat_curve,
        shocks_bps=[-100, 0, 100, 200],
        n_paths=32,
        n_periods=360,
        seed=42,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    # Base EVE should be positive (it's a value)
    assert eve_results[0]["eve"] > 0, "Base EVE should be positive"

    # Rate rise → negative delta EVE
    delta_eve_up100 = eve_results[100]["delta_eve"]
    delta_eve_up200 = eve_results[200]["delta_eve"]

    assert delta_eve_up100 < 0, (
        f"EVE should decrease when rates rise +100bp, got delta = {delta_eve_up100:.2f}"
    )
    assert delta_eve_up200 < 0, (
        f"EVE should decrease when rates rise +200bp, got delta = {delta_eve_up200:.2f}"
    )

    # More rate rise → more negative delta
    assert delta_eve_up200 < delta_eve_up100, (
        f"+200bp EVE change ({delta_eve_up200:.2f}) should be worse than "
        f"+100bp ({delta_eve_up100:.2f})"
    )


def test_scenario_base_matches_base_analytics(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """
    Base scenario result should match compute_analytics() called directly.

    Ensures consistency between scenario runner and direct analytics.
    """
    settlement = date(2025, 1, 1)
    market_price = 100.0
    n_paths = 32
    seed = 42

    # Direct analytics
    rate_paths = generate_rate_paths(curve=flat_curve, n_paths=n_paths, n_periods=360, seed=seed)
    direct_analytics = compute_analytics(
        pool_id="TEST-POOL-30YR",
        pool_chars=pool_chars_30yr,
        market_price=market_price,
        settlement_date=settlement,
        rate_paths=rate_paths,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    # Via scenario runner
    scenarios = {"Base": {"parallel_shift": 0}}
    scenario_results = run_scenarios(
        pool_id="TEST-POOL-30YR",
        pool_chars=pool_chars_30yr,
        market_price=market_price,
        settlement_date=settlement,
        base_curve=flat_curve,
        scenarios=scenarios,
        n_paths=n_paths,
        seed=seed,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    base_scenario = scenario_results["Base"]

    # Prices should be very close (same seed, same curve)
    assert abs(base_scenario.analytics.model_price - direct_analytics.model_price) < 0.1, (
        f"Base scenario price {base_scenario.analytics.model_price:.4f} "
        f"differs from direct analytics {direct_analytics.model_price:.4f}"
    )

    # OAS should be very close
    assert abs(base_scenario.analytics.oas - direct_analytics.oas) < 2.0, (
        f"Base scenario OAS {base_scenario.analytics.oas:.2f} "
        f"differs from direct analytics {direct_analytics.oas:.2f}"
    )


def test_scenario_deltas_computed_correctly(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """
    ScenarioResult deltas should equal the difference between scenario and base analytics.
    """
    scenarios = {
        "Base": {"parallel_shift": 0},
        "Up 100": {"parallel_shift": 100},
    }

    results = run_scenarios(
        pool_id="TEST-POOL-30YR",
        pool_chars=pool_chars_30yr,
        market_price=100.0,
        settlement_date=date(2025, 1, 1),
        base_curve=flat_curve,
        scenarios=scenarios,
        n_paths=32,
        seed=42,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    base = results["Base"]
    up100 = results["Up 100"]

    # Verify deltas are correctly computed
    expected_price_delta = up100.analytics.model_price - base.analytics.model_price
    expected_oas_delta = up100.analytics.oas - base.analytics.oas
    expected_oad_delta = up100.analytics.oad - base.analytics.oad

    assert abs(up100.price_delta - expected_price_delta) < 0.001, (
        f"Price delta mismatch: {up100.price_delta} vs {expected_price_delta}"
    )
    assert abs(up100.oas_delta - expected_oas_delta) < 0.01, (
        f"OAS delta mismatch: {up100.oas_delta} vs {expected_oas_delta}"
    )
    assert abs(up100.oad_delta - expected_oad_delta) < 0.001, (
        f"OAD delta mismatch: {up100.oad_delta} vs {expected_oad_delta}"
    )


def test_all_standard_scenarios_run(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """All 9 standard scenarios should run without error."""
    results = run_scenarios(
        pool_id="TEST-POOL-30YR",
        pool_chars=pool_chars_30yr,
        market_price=100.0,
        settlement_date=date(2025, 1, 1),
        base_curve=flat_curve,
        scenarios=STANDARD_SCENARIOS,
        n_paths=16,  # small for speed
        seed=42,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    assert len(results) == len(STANDARD_SCENARIOS), (
        f"Expected {len(STANDARD_SCENARIOS)} scenarios, got {len(results)}"
    )

    for name in STANDARD_SCENARIOS:
        assert name in results, f"Missing scenario: {name}"
        r = results[name]
        assert isinstance(r, ScenarioResult)
        assert isinstance(r.analytics.oas, float)
        assert isinstance(r.analytics.oad, float)
        assert isinstance(r.analytics.model_price, float)
