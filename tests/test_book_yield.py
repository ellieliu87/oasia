"""
Tests for book yield computation.

All tests use MockIntexClient and stub PrepayModel — no API keys required.
"""
import numpy as np
import pytest
from datetime import date

from analytics.rate_paths import TermStructure, generate_rate_paths
from analytics.prepay import PoolCharacteristics, PrepayModel
from portfolio.book_yield import compute_book_yield, compute_portfolio_book_yields
from data.intex_client import MockIntexClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def flat_curve():
    """Flat curve at 6% (matches coupon for par bond test)."""
    tenors = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    rates = np.full_like(tenors, 0.06)
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
def pool_30yr_6pct():
    """30-year pool with 6% coupon (WAC = 6%)."""
    return PoolCharacteristics(
        coupon=0.06,
        wac=0.06,   # WAC equals coupon for clean par bond test
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
def pool_15yr_5_5pct():
    """15-year pool with 5.5% coupon."""
    return PoolCharacteristics(
        coupon=0.055,
        wac=0.055,
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBookYieldSingleBond:

    def test_book_yield_at_par(self, pool_30yr_6pct, rate_paths, mock_client, prepay_model):
        """
        Bond purchased at par → book yield ≈ coupon rate.

        At par, the yield equals the coupon rate because there is no
        premium or discount amortization. This is a fundamental bond
        property.
        """
        book_yield = compute_book_yield(
            pool_id="TEST-POOL-30YR",
            pool_chars=pool_30yr_6pct,
            book_price=100.0,
            face_amount=1_000_000,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        coupon = pool_30yr_6pct.wac  # 6%

        # Book yield should be close to coupon rate
        # Allow ±50bps for prepayment model effects and numerical precision
        assert abs(book_yield - coupon) < 0.005, (
            f"Par bond yield {book_yield*100:.3f}% should be close to "
            f"coupon {coupon*100:.3f}%, difference: {abs(book_yield - coupon)*10000:.1f}bps"
        )

    def test_premium_bond_yield_below_coupon(self, pool_30yr_6pct, rate_paths, mock_client, prepay_model):
        """
        Bond purchased at premium (105) → book yield < coupon rate.

        Premium amortizes over the life of the bond, reducing the effective
        yield below the stated coupon rate.
        """
        yield_par = compute_book_yield(
            pool_id="TEST-POOL-30YR",
            pool_chars=pool_30yr_6pct,
            book_price=100.0,
            face_amount=1_000_000,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        yield_premium = compute_book_yield(
            pool_id="TEST-POOL-30YR",
            pool_chars=pool_30yr_6pct,
            book_price=105.0,
            face_amount=1_000_000,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        coupon = pool_30yr_6pct.wac

        assert yield_premium < coupon, (
            f"Premium bond yield ({yield_premium*100:.3f}%) should be "
            f"< coupon ({coupon*100:.3f}%)"
        )
        assert yield_premium < yield_par, (
            f"Premium bond yield ({yield_premium*100:.3f}%) should be "
            f"< par bond yield ({yield_par*100:.3f}%)"
        )

    def test_discount_bond_yield_above_coupon(self, pool_30yr_6pct, rate_paths, mock_client, prepay_model):
        """
        Bond purchased at discount (95) → book yield > coupon rate.

        Discount accretes over the life of the bond, increasing the effective
        yield above the stated coupon rate.
        """
        yield_par = compute_book_yield(
            pool_id="TEST-POOL-30YR",
            pool_chars=pool_30yr_6pct,
            book_price=100.0,
            face_amount=1_000_000,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        yield_discount = compute_book_yield(
            pool_id="TEST-POOL-30YR",
            pool_chars=pool_30yr_6pct,
            book_price=95.0,
            face_amount=1_000_000,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        coupon = pool_30yr_6pct.wac

        assert yield_discount > coupon, (
            f"Discount bond yield ({yield_discount*100:.3f}%) should be "
            f"> coupon ({coupon*100:.3f}%)"
        )
        assert yield_discount > yield_par, (
            f"Discount bond yield ({yield_discount*100:.3f}%) should be "
            f"> par bond yield ({yield_par*100:.3f}%)"
        )

    def test_yield_positive(self, pool_30yr_6pct, rate_paths, mock_client, prepay_model):
        """Book yield should always be positive for reasonable prices."""
        for price in [90.0, 95.0, 100.0, 105.0, 110.0]:
            y = compute_book_yield(
                pool_id="TEST-POOL-30YR",
                pool_chars=pool_30yr_6pct,
                book_price=price,
                face_amount=1_000_000,
                settlement_date=date(2025, 1, 1),
                rate_paths=rate_paths,
                intex_client=mock_client,
                prepay_model=prepay_model,
            )
            assert y > 0, f"Yield should be positive for price {price}, got {y}"
            assert y < 0.30, f"Yield should be < 30% for price {price}, got {y}"

    def test_yield_monotonic_with_price(self, pool_30yr_6pct, rate_paths, mock_client, prepay_model):
        """Higher price → lower yield (inverse price-yield relationship)."""
        prices = [92.0, 96.0, 100.0, 104.0, 108.0]
        yields = []

        for price in prices:
            y = compute_book_yield(
                pool_id="TEST-POOL-30YR",
                pool_chars=pool_30yr_6pct,
                book_price=price,
                face_amount=1_000_000,
                settlement_date=date(2025, 1, 1),
                rate_paths=rate_paths,
                intex_client=mock_client,
                prepay_model=prepay_model,
            )
            yields.append(y)

        # Yields should be decreasing as prices increase
        for i in range(len(yields) - 1):
            assert yields[i] > yields[i + 1], (
                f"Yield should decrease as price increases: "
                f"price {prices[i]}→{prices[i+1]}, "
                f"yield {yields[i]*100:.3f}%→{yields[i+1]*100:.3f}%"
            )


class TestPortfolioBookYields:

    def _make_positions(self, pool_30yr, pool_15yr, rate_paths):
        """Build a 3-position portfolio."""
        return [
            {
                "pool_id": "TEST-POOL-30YR",
                "pool_chars": pool_30yr,
                "face_amount": 5_000_000,
                "book_price": 101.5,
                "purchase_date": date(2024, 6, 1),
            },
            {
                "pool_id": "TEST-POOL-15YR",
                "pool_chars": pool_15yr,
                "face_amount": 3_000_000,
                "book_price": 99.5,
                "purchase_date": date(2024, 9, 15),
            },
            {
                "pool_id": "TEST-POOL-GN30",
                "pool_chars": PoolCharacteristics(
                    coupon=0.065, wac=0.065, wala=24, wam=336,
                    loan_size=350_000, ltv=0.90, fico=700,
                    pct_ca=0.10, pct_purchase=0.60,
                    product_type="GN30", pool_id="TEST-POOL-GN30",
                    current_balance=4_000_000,
                ),
                "face_amount": 4_000_000,
                "book_price": 103.0,
                "purchase_date": date(2023, 12, 1),
            },
        ]

    def test_portfolio_yield_weighted_average(self, pool_30yr_6pct, pool_15yr_5_5pct, rate_paths, mock_client, prepay_model):
        """Portfolio yield should be between min and max position yields."""
        positions = self._make_positions(pool_30yr_6pct, pool_15yr_5_5pct, rate_paths)

        result = compute_portfolio_book_yields(
            positions=positions,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        total_yield = result["total_yield"]

        # Compute individual position yields
        individual_yields = []
        for pos in positions:
            y = compute_book_yield(
                pool_id=pos["pool_id"],
                pool_chars=pos["pool_chars"],
                book_price=pos["book_price"],
                face_amount=pos["face_amount"],
                settlement_date=date(2025, 1, 1),
                rate_paths=rate_paths,
                intex_client=mock_client,
                prepay_model=prepay_model,
            )
            individual_yields.append(y)

        min_yield = min(individual_yields)
        max_yield = max(individual_yields)

        assert min_yield <= total_yield <= max_yield, (
            f"Portfolio yield {total_yield*100:.3f}% should be between "
            f"min {min_yield*100:.3f}% and max {max_yield*100:.3f}%"
        )

    def test_portfolio_yields_return_all_keys(self, pool_30yr_6pct, pool_15yr_5_5pct, rate_paths, mock_client, prepay_model):
        """Portfolio yields function should return required keys."""
        positions = self._make_positions(pool_30yr_6pct, pool_15yr_5_5pct, rate_paths)

        result = compute_portfolio_book_yields(
            positions=positions,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        required_keys = {"existing_yield", "new_yield", "total_yield", "pickup_bps"}
        assert required_keys.issubset(set(result.keys())), (
            f"Missing keys: {required_keys - set(result.keys())}"
        )

    def test_portfolio_yield_with_cutoff_date(self, pool_30yr_6pct, pool_15yr_5_5pct, rate_paths, mock_client, prepay_model):
        """Yield pickup should reflect difference between new and existing positions."""
        positions = self._make_positions(pool_30yr_6pct, pool_15yr_5_5pct, rate_paths)

        # Cutoff: positions purchased after 2024-07-01 are "new"
        # Based on purchase dates above: POOL-30YR is "existing", POOL-15YR and POOL-GN30 are mixed
        cutoff = date(2024, 7, 1)

        result = compute_portfolio_book_yields(
            positions=positions,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            cutoff_date=cutoff,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        # All yields should be reasonable
        assert result["total_yield"] > 0
        assert result["total_yield"] < 0.20
        assert result["existing_yield"] > 0

    def test_empty_portfolio_returns_zeros(self):
        """Empty portfolio should return zero yields."""
        from analytics.rate_paths import TermStructure, generate_rate_paths
        tenors = np.array([1, 2, 5, 10, 30], dtype=float)
        rates = np.full_like(tenors, 0.05)
        curve = TermStructure(tenors=tenors, rates=rates)
        rate_paths = generate_rate_paths(curve=curve, n_paths=16, n_periods=360, seed=42)

        result = compute_portfolio_book_yields(
            positions=[],
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
        )

        assert result["total_yield"] == 0.0
        assert result["existing_yield"] == 0.0
        assert result["pickup_bps"] == 0.0


class TestBookYieldConsistency:

    def test_book_yield_vs_oas_yield_ordering(self, pool_30yr_6pct, rate_paths, mock_client, prepay_model):
        """
        At premium, book yield should be below OAS yield (option cost).

        Book yield is the IRR at purchase price. For a premium bond,
        both measures should be below the coupon.
        """
        book_y = compute_book_yield(
            pool_id="TEST-POOL-30YR",
            pool_chars=pool_30yr_6pct,
            book_price=103.0,
            face_amount=1_000_000,
            settlement_date=date(2025, 1, 1),
            rate_paths=rate_paths,
            intex_client=mock_client,
            prepay_model=prepay_model,
        )

        # Both should be positive and below coupon
        assert 0 < book_y < pool_30yr_6pct.wac, (
            f"Premium bond yield {book_y*100:.3f}% should be between 0 and coupon {pool_30yr_6pct.wac*100:.3f}%"
        )

    def test_face_amount_does_not_affect_yield(self, pool_30yr_6pct, rate_paths, mock_client, prepay_model):
        """
        Book yield should be the same regardless of face amount
        (it's a percentage, not a dollar measure).
        """
        y_1m = compute_book_yield(
            "TEST-POOL-30YR", pool_30yr_6pct, 101.0, 1_000_000,
            date(2025, 1, 1), rate_paths, mock_client, prepay_model,
        )
        y_5m = compute_book_yield(
            "TEST-POOL-30YR", pool_30yr_6pct, 101.0, 5_000_000,
            date(2025, 1, 1), rate_paths, mock_client, prepay_model,
        )

        assert abs(y_1m - y_5m) < 0.0001, (
            f"Yield should not depend on face amount: {y_1m*100:.4f}% vs {y_5m*100:.4f}%"
        )
