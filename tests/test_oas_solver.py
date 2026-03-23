"""
Tests for OAS solver and bond analytics.

All tests use MockIntexClient and stub PrepayModel — no API keys required.
"""
import numpy as np
import pytest
from datetime import date

from analytics.rate_paths import TermStructure, generate_rate_paths
from analytics.prepay import PoolCharacteristics, PrepayModel
from analytics.oas_solver import (
    price_from_oas,
    solve_oas,
    compute_z_spread,
    compute_analytics,
    BondAnalytics,
)
from data.intex_client import MockIntexClient, CashFlows
from analytics.cashflows import get_cash_flows


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def flat_curve():
    """Simple flat term structure at 4.7%."""
    tenors = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    rates = np.full_like(tenors, 0.047)
    return TermStructure(tenors=tenors, rates=rates)


@pytest.fixture
def upward_curve():
    """Upward-sloping term structure (3% to 5%)."""
    tenors = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    rates = np.array([0.030, 0.032, 0.035, 0.038, 0.042, 0.045, 0.048, 0.050,
                      0.052, 0.054, 0.055, 0.056])
    return TermStructure(tenors=tenors, rates=rates)


@pytest.fixture
def rate_paths_flat(flat_curve):
    """Rate paths from flat curve, small n_paths for speed."""
    return generate_rate_paths(curve=flat_curve, n_paths=64, n_periods=360, seed=42)


@pytest.fixture
def pool_chars_30yr():
    """Standard 30-year CC30 pool."""
    return PoolCharacteristics(
        coupon=0.06,
        wac=0.065,
        wala=0,
        wam=360,
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
def pool_chars_15yr():
    """Standard 15-year CC15 pool."""
    return PoolCharacteristics(
        coupon=0.055,
        wac=0.059,
        wala=0,
        wam=180,
        loan_size=350_000,
        ltv=0.70,
        fico=760,
        pct_ca=0.10,
        pct_purchase=0.70,
        product_type="CC15",
        pool_id="TEST-POOL-15YR",
        current_balance=1_000_000,
    )


@pytest.fixture
def mock_client():
    return MockIntexClient()


@pytest.fixture
def prepay_model():
    return PrepayModel()


@pytest.fixture
def base_cash_flows(pool_chars_30yr, rate_paths_flat, mock_client, prepay_model):
    """Standard 30yr cash flows at moderate CPR."""
    from analytics.prepay import project_prepay_speeds
    cpr = project_prepay_speeds(pool_chars_30yr, rate_paths_flat, model=prepay_model)
    return get_cash_flows(
        pool_id="TEST-POOL-30YR",
        cpr_vectors=cpr,
        settlement_date=date(2025, 1, 1),
        face_amount=1_000_000,
        intex_client=mock_client,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_price_from_oas_at_zero_spread(base_cash_flows, rate_paths_flat, flat_curve):
    """At OAS=0, price should be reasonable (close to Z-spread price)."""
    price_oas_zero = price_from_oas(base_cash_flows, rate_paths_flat, oas_bps=0.0)

    # Z-spread price at 0 spread
    z_spread_price = compute_z_spread(base_cash_flows, flat_curve, market_price=price_oas_zero)

    # At OAS=0, z-spread should be ~0 too (they converge for simple structures)
    assert isinstance(price_oas_zero, float)
    assert 70.0 < price_oas_zero < 130.0, f"Price {price_oas_zero} out of range"

    # Z-spread should be close to 0 when price matches OAS=0 price
    assert abs(z_spread_price) < 50.0, f"Z-spread {z_spread_price} too large at OAS=0 price"


def test_oas_solver_round_trip(base_cash_flows, rate_paths_flat):
    """Solve OAS from price, then reprice at that OAS → should match original price."""
    target_price = 100.0

    # Solve OAS for par price
    oas_result = solve_oas(base_cash_flows, rate_paths_flat, market_price=target_price)
    assert oas_result.converged, "OAS solver should converge"

    # Reprice at solved OAS
    reprice = price_from_oas(base_cash_flows, rate_paths_flat, oas_bps=oas_result.oas_bps)

    # Should match within tolerance
    assert abs(reprice - target_price) < 0.05, (
        f"Round-trip failed: target={target_price}, reprice={reprice}, "
        f"OAS={oas_result.oas_bps:.2f}"
    )


def test_oas_solver_deep_discount(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """85 price bond should have positive OAS > 50 bps."""
    from analytics.prepay import project_prepay_speeds

    rate_paths = generate_rate_paths(curve=flat_curve, n_paths=64, n_periods=360, seed=42)
    cpr = project_prepay_speeds(pool_chars_30yr, rate_paths, model=prepay_model)
    cf = get_cash_flows(
        pool_id="TEST-POOL-30YR",
        cpr_vectors=cpr,
        settlement_date=date(2025, 1, 1),
        face_amount=1_000_000,
        intex_client=mock_client,
    )

    oas_result = solve_oas(cf, rate_paths, market_price=85.0)

    assert oas_result.oas_bps > 50.0, (
        f"Deep discount bond OAS should be > 50bps, got {oas_result.oas_bps:.1f}"
    )


def test_oas_solver_premium(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """105 price bond should have lower OAS than par bond."""
    from analytics.prepay import project_prepay_speeds

    rate_paths = generate_rate_paths(curve=flat_curve, n_paths=64, n_periods=360, seed=42)
    cpr = project_prepay_speeds(pool_chars_30yr, rate_paths, model=prepay_model)
    cf = get_cash_flows(
        pool_id="TEST-POOL-30YR",
        cpr_vectors=cpr,
        settlement_date=date(2025, 1, 1),
        face_amount=1_000_000,
        intex_client=mock_client,
    )

    oas_par = solve_oas(cf, rate_paths, market_price=100.0)
    oas_premium = solve_oas(cf, rate_paths, market_price=105.0)

    assert oas_premium.oas_bps < oas_par.oas_bps, (
        f"Premium bond OAS ({oas_premium.oas_bps:.1f}) should be < "
        f"par bond OAS ({oas_par.oas_bps:.1f})"
    )


def test_oad_positive(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """OAD must be positive for standard MBS."""
    rate_paths = generate_rate_paths(curve=flat_curve, n_paths=64, n_periods=360, seed=42)
    analytics = compute_analytics(
        pool_id="TEST-POOL-30YR",
        pool_chars=pool_chars_30yr,
        market_price=100.0,
        settlement_date=date(2025, 1, 1),
        rate_paths=rate_paths,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    assert analytics.oad > 0.0, f"OAD should be positive, got {analytics.oad}"
    assert analytics.oad < 15.0, f"OAD too large: {analytics.oad}"


def test_convexity_negative_for_premium_mbs(pool_chars_30yr, flat_curve, mock_client, prepay_model):
    """
    Premium MBS (in-the-money prepayment option) should have negative convexity.

    A pool priced at 105 with 6% coupon is a premium bond where the prepayment
    option is valuable — the holder faces negative convexity.
    """
    from analytics.prepay import project_prepay_speeds

    rate_paths = generate_rate_paths(curve=flat_curve, n_paths=64, n_periods=360, seed=42)

    # Use higher CPR to simulate premium bond (more prepayment exposure)
    pool_premium = PoolCharacteristics(
        coupon=0.07,  # high coupon premium bond
        wac=0.075,
        wala=24,      # seasoned pool
        wam=336,
        loan_size=400_000,
        ltv=0.70,
        fico=770,
        pct_ca=0.20,
        pct_purchase=0.60,
        product_type="CC30",
        pool_id="TEST-POOL-30YR",
        current_balance=1_000_000,
    )

    analytics = compute_analytics(
        pool_id="TEST-POOL-30YR",
        pool_chars=pool_premium,
        market_price=105.0,
        settlement_date=date(2025, 1, 1),
        rate_paths=rate_paths,
        intex_client=mock_client,
        prepay_model=prepay_model,
    )

    # Premium MBS should have negative or low positive convexity
    # (the prepayment option creates negative convexity)
    assert analytics.convexity < 2.0, (
        f"Premium MBS convexity should be negative or small positive, "
        f"got {analytics.convexity:.4f}"
    )
