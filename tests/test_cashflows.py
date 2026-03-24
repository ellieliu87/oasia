"""
Tests for cash flow generation.

All tests use MockIntexClient — no API keys required.
"""
import numpy as np
import pytest
from datetime import date

from analytics.rate_paths import TermStructure, generate_rate_paths
from analytics.prepay import PoolCharacteristics, PrepayModel, project_prepay_speeds
from analytics.cashflows import get_cash_flows
from data.intex_client import MockIntexClient, CashFlows


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def flat_curve():
    tenors = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    rates = np.full_like(tenors, 0.047)
    return TermStructure(tenors=tenors, rates=rates)


@pytest.fixture
def rate_paths(flat_curve):
    return generate_rate_paths(curve=flat_curve, n_paths=32, n_periods=360, seed=42)


@pytest.fixture
def rate_paths_15yr(flat_curve):
    return generate_rate_paths(curve=flat_curve, n_paths=32, n_periods=180, seed=42)


@pytest.fixture
def mock_client():
    return MockIntexClient()


@pytest.fixture
def prepay_model():
    return PrepayModel()


@pytest.fixture
def pool_30yr():
    return PoolCharacteristics(
        coupon=0.06, wac=0.065, wala=0, wam=360,
        loan_size=400_000, ltv=0.75, fico=750,
        pct_ca=0.15, pct_purchase=0.65,
        product_type="CC30", pool_id="TEST-POOL-30YR",
        current_balance=1_000_000,
    )


@pytest.fixture
def pool_15yr():
    return PoolCharacteristics(
        coupon=0.055, wac=0.059, wala=0, wam=180,
        loan_size=350_000, ltv=0.70, fico=760,
        pct_ca=0.10, pct_purchase=0.70,
        product_type="CC15", pool_id="TEST-POOL-15YR",
        current_balance=1_000_000,
    )


@pytest.fixture
def cpr_low(pool_30yr, rate_paths):
    """Low CPR (5%) applied uniformly."""
    return project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.05)


@pytest.fixture
def cpr_high(pool_30yr, rate_paths):
    """High CPR (25%) applied uniformly."""
    return project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.25)


@pytest.fixture
def cf_30yr_low(pool_30yr, rate_paths, cpr_low, mock_client):
    return get_cash_flows(
        pool_id="TEST-POOL-30YR",
        cpr_vectors=cpr_low,
        settlement_date=date(2025, 1, 1),
        face_amount=1_000_000,
        intex_client=mock_client,
    )


@pytest.fixture
def cf_30yr_high(pool_30yr, rate_paths, cpr_high, mock_client):
    return get_cash_flows(
        pool_id="TEST-POOL-30YR",
        cpr_vectors=cpr_high,
        settlement_date=date(2025, 1, 1),
        face_amount=1_000_000,
        intex_client=mock_client,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCashFlowBasics:

    def test_cash_flows_sum_to_face(self, cf_30yr_low):
        """
        Total principal returned across all periods should equal original face amount.

        This verifies the fundamental accounting constraint: all principal is returned.
        """
        face_amount = 1_000_000
        total_principal = cf_30yr_low.total_principal  # (n_paths, n_periods)

        # Sum of principal per path
        per_path_total = np.sum(total_principal, axis=1)  # (n_paths,)

        # Each path should return all principal (within numerical tolerance)
        for i, path_total in enumerate(per_path_total):
            assert abs(path_total - face_amount) < 1.0, (
                f"Path {i}: total principal {path_total:.2f} != face {face_amount}"
            )

    def test_interest_decreases_over_time(self, cf_30yr_low):
        """
        Interest payments should decrease over time as the balance amortizes.

        The first 12 months should have higher average interest than the last
        12 months before payoff.
        """
        # Average interest across paths
        mean_interest = np.mean(cf_30yr_low.interest, axis=0)  # (n_periods,)

        # First 12 months vs months 100-111 (should be lower later)
        early_interest = np.mean(mean_interest[:12])
        mid_interest = np.mean(mean_interest[100:112])

        assert mid_interest < early_interest, (
            f"Mid-life interest ({mid_interest:.2f}) should be < "
            f"early interest ({early_interest:.2f})"
        )

    def test_balance_decreases_monotonically(self, cf_30yr_low):
        """Balance should be non-increasing over time on each path."""
        # Check first path as representative
        balance_path0 = cf_30yr_low.balance[0, :]

        # Balance should not increase
        for t in range(1, len(balance_path0)):
            if balance_path0[t] > 0:
                assert balance_path0[t] <= balance_path0[t - 1] + 0.01, (
                    f"Balance increased at period {t}: "
                    f"{balance_path0[t-1]:.2f} → {balance_path0[t]:.2f}"
                )

    def test_cash_flows_nonnegative(self, cf_30yr_low):
        """All cash flow components should be non-negative."""
        assert np.all(cf_30yr_low.scheduled_principal >= -0.01), \
            "Scheduled principal should be non-negative"
        assert np.all(cf_30yr_low.prepaid_principal >= -0.01), \
            "Prepaid principal should be non-negative"
        assert np.all(cf_30yr_low.interest >= -0.01), \
            "Interest should be non-negative"
        assert np.all(cf_30yr_low.balance >= -0.01), \
            "Balance should be non-negative"

    def test_cash_flows_shape(self, cf_30yr_low, rate_paths):
        """Cash flows should have shape (n_paths, n_periods)."""
        n_paths = rate_paths.short_rates.shape[0]
        n_periods = rate_paths.short_rates.shape[1]

        assert cf_30yr_low.scheduled_principal.shape == (n_paths, n_periods), \
            f"Shape mismatch: {cf_30yr_low.scheduled_principal.shape}"
        assert cf_30yr_low.prepaid_principal.shape == (n_paths, n_periods)
        assert cf_30yr_low.interest.shape == (n_paths, n_periods)
        assert cf_30yr_low.balance.shape == (n_paths, n_periods)


class TestPrepaymentEffects:

    def test_higher_cpr_faster_payoff(self, cf_30yr_low, cf_30yr_high):
        """
        Higher CPR → shorter effective maturity (faster principal return).

        The pool with 25% CPR should return 90% of principal in fewer periods
        than the pool with 5% CPR.
        """
        # Find period when 90% of principal is returned (mean across paths)
        def _periods_to_pct_payoff(cf: CashFlows, pct: float = 0.90) -> int:
            face = np.sum(cf.total_principal[0, :])
            cumulative = np.cumsum(np.mean(cf.total_principal, axis=0))
            indices = np.where(cumulative >= pct * face)[0]
            if len(indices) == 0:
                return cf.n_periods
            return int(indices[0])

        period_low = _periods_to_pct_payoff(cf_30yr_low)
        period_high = _periods_to_pct_payoff(cf_30yr_high)

        assert period_high < period_low, (
            f"High CPR pool should payoff sooner: {period_high} periods < {period_low} periods"
        )

    def test_higher_cpr_more_prepaid_principal(self, pool_30yr, rate_paths, mock_client):
        """Higher CPR → more prepaid principal, less scheduled principal."""
        cpr_low = project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.05)
        cpr_high = project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.30)

        cf_low = get_cash_flows(
            "TEST-POOL-30YR", cpr_low, date(2025, 1, 1), 1_000_000, mock_client
        )
        cf_high = get_cash_flows(
            "TEST-POOL-30YR", cpr_high, date(2025, 1, 1), 1_000_000, mock_client
        )

        total_prepay_low = np.mean(np.sum(cf_low.prepaid_principal, axis=1))
        total_prepay_high = np.mean(np.sum(cf_high.prepaid_principal, axis=1))

        assert total_prepay_high > total_prepay_low, (
            f"High CPR should produce more prepaid principal: "
            f"{total_prepay_high:.0f} vs {total_prepay_low:.0f}"
        )

    def test_zero_cpr_no_prepayments(self, pool_30yr, rate_paths, mock_client):
        """At CPR=0, prepaid principal should be 0 everywhere."""
        cpr_zero = project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.0)
        cf = get_cash_flows(
            "TEST-POOL-30YR", cpr_zero, date(2025, 1, 1), 1_000_000, mock_client
        )

        assert np.all(cf.prepaid_principal < 1.0), (
            "At CPR=0, prepaid principal should be essentially 0 everywhere"
        )

    def test_total_principal_increases_with_cpr(self, pool_30yr, rate_paths, mock_client):
        """More CPR → higher total principal returned in early periods."""
        cpr_low = project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.05)
        cpr_high = project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.30)

        cf_low = get_cash_flows(
            "TEST-POOL-30YR", cpr_low, date(2025, 1, 1), 1_000_000, mock_client
        )
        cf_high = get_cash_flows(
            "TEST-POOL-30YR", cpr_high, date(2025, 1, 1), 1_000_000, mock_client
        )

        # Early period (first 24 months) total principal
        early_principal_low = np.mean(np.sum(cf_low.total_principal[:, :24], axis=1))
        early_principal_high = np.mean(np.sum(cf_high.total_principal[:, :24], axis=1))

        assert early_principal_high > early_principal_low, (
            f"Higher CPR should produce more early principal: "
            f"{early_principal_high:.0f} vs {early_principal_low:.0f}"
        )


class TestCMOSequentialWaterfall:

    def test_cmo_sequential_waterfall(self, pool_30yr, rate_paths, mock_client, prepay_model):
        """
        Sequential tranche A is paid before tranche B.

        In a sequential CMO, Tranche A receives all principal payments first
        until it is fully repaid, then Tranche B starts receiving principal.

        We simulate this by running the underlying collateral and verifying
        that tranche A balance reaches 0 before tranche B principal starts.
        """
        # Get base collateral cash flows
        cpr = project_prepay_speeds(pool_30yr, rate_paths, model=prepay_model)
        cf = get_cash_flows(
            pool_id="TEST-POOL-30YR",
            cpr_vectors=cpr,
            settlement_date=date(2025, 1, 1),
            face_amount=2_000_000,
            intex_client=mock_client,
        )

        # Set up sequential tranches
        tranche_a_original = 1_200_000  # 60% of pool
        tranche_b_original = 800_000    # 40% of pool

        # Mean principal across paths
        total_principal_per_period = np.mean(cf.total_principal, axis=0)

        # Sequential waterfall: A gets all principal first
        tranche_a_balance = tranche_a_original
        tranche_b_balance = tranche_b_original

        tranche_a_payoff_period = None
        tranche_b_receives_first_period = None

        for t, princ in enumerate(total_principal_per_period):
            if tranche_a_balance > 0:
                a_payment = min(princ, tranche_a_balance)
                tranche_a_balance -= a_payment
                b_payment = max(0.0, princ - a_payment)
            else:
                b_payment = princ

            if tranche_a_balance <= 0.01 and tranche_a_payoff_period is None:
                tranche_a_payoff_period = t

            if b_payment > 1.0 and tranche_b_receives_first_period is None:
                tranche_b_receives_first_period = t

        # Tranche A should be paid off before or at the same time tranche B starts
        assert tranche_a_payoff_period is not None, "Tranche A should fully amortize"
        if tranche_b_receives_first_period is not None:
            assert tranche_b_receives_first_period >= tranche_a_payoff_period, (
                f"Tranche B starts receiving principal at period {tranche_b_receives_first_period} "
                f"but Tranche A not paid off until period {tranche_a_payoff_period}"
            )


class TestCashFlowProperties:

    def test_15yr_faster_amortization_than_30yr(self, pool_30yr, pool_15yr, rate_paths, mock_client, prepay_model):
        """15-year pool should amortize faster than 30-year pool."""
        cpr_30 = project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.10)
        cpr_15 = project_prepay_speeds(pool_15yr, rate_paths, cpr_override=0.10)

        cf_30 = get_cash_flows("TEST-POOL-30YR", cpr_30, date(2025, 1, 1), 1_000_000, mock_client)
        cf_15 = get_cash_flows("TEST-POOL-15YR", cpr_15, date(2025, 1, 1), 1_000_000, mock_client)

        # 15-yr should have more principal in early periods
        early_princ_30 = np.mean(np.sum(cf_30.total_principal[:, :60], axis=1))
        early_princ_15 = np.mean(np.sum(cf_15.total_principal[:, :60], axis=1))

        assert early_princ_15 > early_princ_30, (
            f"15yr should amortize faster: {early_princ_15:.0f} vs {early_princ_30:.0f} "
            "in first 60 months"
        )

    def test_face_amount_scales_cash_flows(self, pool_30yr, rate_paths, mock_client, prepay_model):
        """Cash flows should scale linearly with face amount."""
        cpr = project_prepay_speeds(pool_30yr, rate_paths, model=prepay_model)

        # Use a unique pool_id to guarantee no stale cache entries affect this test.
        cf_1m = get_cash_flows("SCALE-TEST-30YR", cpr, date(2025, 1, 1), 1_000_000, mock_client)
        cf_5m = get_cash_flows("SCALE-TEST-30YR", cpr, date(2025, 1, 1), 5_000_000, mock_client)

        # Total principal for 5M should be ~5x that of 1M
        total_1m = np.mean(np.sum(cf_1m.total_principal, axis=1))
        total_5m = np.mean(np.sum(cf_5m.total_principal, axis=1))

        ratio = total_5m / total_1m
        assert abs(ratio - 5.0) < 0.1, (
            f"Cash flows should scale with face amount, got ratio {ratio:.2f}"
        )

    def test_interest_equals_balance_times_rate(self, pool_30yr, rate_paths, mock_client, prepay_model):
        """Interest in each period should approximate balance * WAC / 12."""
        cpr = project_prepay_speeds(pool_30yr, rate_paths, cpr_override=0.10)
        cf = get_cash_flows("TEST-POOL-30YR", cpr, date(2025, 1, 1), 1_000_000, mock_client)

        # Check first period (cleaner calculation)
        # MockIntexClient uses spec["wac"]=0.06 for TEST-POOL-30YR,
        # not pool_30yr.wac (0.065), so compare against the spec rate.
        mock_spec_wac = 0.06
        expected_monthly_rate = mock_spec_wac / 12.0
        expected_interest_t0 = cf.balance[:, 0] * expected_monthly_rate

        actual_interest_t0 = cf.interest[:, 0]

        # Should match closely
        rel_error = np.mean(np.abs(actual_interest_t0 - expected_interest_t0) /
                            np.maximum(expected_interest_t0, 1.0))
        assert rel_error < 0.01, (
            f"Interest should equal balance * WAC/12, relative error: {rel_error:.4f}"
        )
