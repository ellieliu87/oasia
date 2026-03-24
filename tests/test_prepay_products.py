"""
Tests for prepayment model product-type handling.

Verifies:
- Non-MBS products (TSY, CDBT, CMBS) return CPR_MIN
- Standard MBS products produce variable CPR
- New product types in pool universe exist
"""
import numpy as np
import pytest

from analytics.prepay import PoolCharacteristics, PrepayModel, _stub_predict, CPR_MIN
from analytics.rate_paths import TermStructure, generate_rate_paths


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def rate_paths():
    tenors = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    rates = np.full_like(tenors, 0.047)
    curve = TermStructure(tenors=tenors, rates=rates)
    return generate_rate_paths(curve=curve, n_paths=16, n_periods=60, seed=1)


def _make_pool(product_type: str) -> PoolCharacteristics:
    return PoolCharacteristics(
        coupon=0.06, wac=0.065, wala=0, wam=360,
        loan_size=400_000, ltv=0.75, fico=750,
        pct_ca=0.10, pct_purchase=0.65,
        product_type=product_type,
    )


# ---------------------------------------------------------------------------
# Non-MBS products return CPR_MIN
# ---------------------------------------------------------------------------

class TestNonMBSProductTypes:

    @pytest.mark.parametrize("product_type", ["TSY", "CDBT", "CMBS"])
    def test_returns_cpr_min(self, product_type, rate_paths):
        pool = _make_pool(product_type)
        cpr = _stub_predict(pool, rate_paths)
        expected = np.full(rate_paths.short_rates.shape, CPR_MIN)
        np.testing.assert_array_equal(cpr, expected,
            err_msg=f"{product_type} should return CPR_MIN={CPR_MIN} everywhere")

    @pytest.mark.parametrize("product_type", ["TSY", "CDBT", "CMBS"])
    def test_shape_is_correct(self, product_type, rate_paths):
        pool = _make_pool(product_type)
        cpr = _stub_predict(pool, rate_paths)
        assert cpr.shape == rate_paths.short_rates.shape

    @pytest.mark.parametrize("product_type", ["TSY", "CDBT", "CMBS"])
    def test_prepay_model_also_returns_cpr_min(self, product_type, rate_paths):
        """PrepayModel.predict() should delegate to stub for non-MBS."""
        model = PrepayModel()
        pool = _make_pool(product_type)
        cpr = model.predict(pool, rate_paths)
        assert np.all(cpr == CPR_MIN), (
            f"PrepayModel for {product_type} should return CPR_MIN, got {cpr.mean():.4f}"
        )


# ---------------------------------------------------------------------------
# Standard MBS products produce variable CPR
# ---------------------------------------------------------------------------

class TestMBSProductTypes:

    @pytest.mark.parametrize("product_type", ["CC30", "CC15", "GN30", "GN15"])
    def test_cpr_varies_across_paths(self, product_type, rate_paths):
        """Standard MBS CPR should vary across paths (not constant)."""
        pool = _make_pool(product_type)
        cpr = _stub_predict(pool, rate_paths)
        assert cpr.std() > 0.001, (
            f"{product_type}: CPR should vary across rate paths (std={cpr.std():.6f})"
        )

    @pytest.mark.parametrize("product_type", ["CC30", "CC15", "GN30", "GN15"])
    def test_cpr_not_all_cpr_min(self, product_type, rate_paths):
        """MBS products should not return a flat CPR_MIN everywhere."""
        pool = _make_pool(product_type)
        cpr = _stub_predict(pool, rate_paths)
        assert not np.all(cpr == CPR_MIN), (
            f"{product_type}: CPR should not be uniformly {CPR_MIN}"
        )

    @pytest.mark.parametrize("product_type", ["CC30", "CC15", "GN30", "GN15"])
    def test_cpr_bounded(self, product_type, rate_paths):
        pool = _make_pool(product_type)
        cpr = _stub_predict(pool, rate_paths)
        assert np.all(cpr >= 0.0), f"{product_type}: CPR must be >= 0"
        assert np.all(cpr <= 1.0), f"{product_type}: CPR must be <= 1"


# ---------------------------------------------------------------------------
# New product types in pool universe
# ---------------------------------------------------------------------------

class TestPoolUniverse:

    def test_pool_universe_importable(self):
        from data.pool_universe import get_pool_universe
        df = get_pool_universe()
        assert len(df) > 0

    def test_arm_product_type_present(self):
        from data.pool_universe import get_pool_universe
        df = get_pool_universe()
        types = set(df["product_type"].unique())
        assert "ARM" in types, f"ARM product type missing. Available: {types}"

    def test_cmbs_product_type_present(self):
        from data.pool_universe import get_pool_universe
        df = get_pool_universe()
        types = set(df["product_type"].unique())
        assert "CMBS" in types, f"CMBS product type missing. Available: {types}"

    def test_cdbt_product_type_present(self):
        from data.pool_universe import get_pool_universe
        df = get_pool_universe()
        types = set(df["product_type"].unique())
        assert "CDBT" in types, f"CDBT product type missing. Available: {types}"

    def test_all_standard_types_present(self):
        from data.pool_universe import get_pool_universe
        df = get_pool_universe()
        types = set(df["product_type"].unique())
        for expected in ["CC30", "CC15", "GN30", "GN15"]:
            assert expected in types, f"{expected} missing from pool universe"

    def test_non_mbs_stub_returns_cpr_min(self, rate_paths):
        """_stub_predict for TSY/CDBT/CMBS should return CPR_MIN."""
        for product_type in ("TSY", "CDBT", "CMBS"):
            pool = _make_pool(product_type)
            cpr = _stub_predict(pool, rate_paths)
            assert np.all(cpr == CPR_MIN), (
                f"{product_type} pool should return CPR_MIN"
            )
