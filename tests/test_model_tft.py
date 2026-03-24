"""
Tests for analytics/model_tft.py — TFTPrepayModel (Model PI TFT).
"""
import numpy as np
import pytest

from analytics.model_tft import TFTPrepayModel
from analytics.neural_prepay import CPR_MIN, CPR_MAX
from analytics.prepay import PoolCharacteristics
from analytics.rate_paths import TermStructure, generate_rate_paths


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def flat_curve():
    tenors = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    rates = np.full_like(tenors, 0.047)
    return TermStructure(tenors=tenors, rates=rates)


@pytest.fixture(scope="module")
def rate_paths_32x120(flat_curve):
    return generate_rate_paths(curve=flat_curve, n_paths=32, n_periods=120, seed=42)


@pytest.fixture(scope="module")
def rate_paths_8x60(flat_curve):
    return generate_rate_paths(curve=flat_curve, n_paths=8, n_periods=60, seed=0)


@pytest.fixture(scope="module")
def pool_cc30():
    return PoolCharacteristics(
        coupon=0.06, wac=0.065, wala=0, wam=360,
        loan_size=400_000, ltv=0.75, fico=750,
        pct_ca=0.15, pct_purchase=0.65,
        product_type="CC30", pool_id="TFT-TEST-30YR",
        current_balance=1_000_000,
    )


@pytest.fixture(scope="module")
def pool_gn15():
    return PoolCharacteristics(
        coupon=0.055, wac=0.058, wala=12, wam=168,
        loan_size=300_000, ltv=0.80, fico=700,
        pct_ca=0.10, pct_purchase=0.70,
        product_type="GN15", pool_id="TFT-TEST-GN15",
        current_balance=500_000,
    )


@pytest.fixture(scope="module")
def tft_model():
    return TFTPrepayModel(seed=7)


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------

class TestTFTOutputShape:

    def test_predict_shape_matches_rate_paths(self, tft_model, pool_cc30, rate_paths_32x120):
        cpr = tft_model.predict(pool_cc30, rate_paths_32x120)
        n_paths, n_periods = rate_paths_32x120.short_rates.shape
        assert cpr.shape == (n_paths, n_periods), (
            f"Expected shape ({n_paths}, {n_periods}), got {cpr.shape}"
        )

    def test_predict_shape_small(self, tft_model, pool_cc30, rate_paths_8x60):
        cpr = tft_model.predict(pool_cc30, rate_paths_8x60)
        assert cpr.shape == (8, 60)

    def test_predict_shape_gn15(self, tft_model, pool_gn15, rate_paths_8x60):
        cpr = tft_model.predict(pool_gn15, rate_paths_8x60)
        assert cpr.shape == (8, 60)


# ---------------------------------------------------------------------------
# CPR bounds
# ---------------------------------------------------------------------------

class TestTFTCPRBounds:

    def test_cpr_lower_bound(self, tft_model, pool_cc30, rate_paths_32x120):
        cpr = tft_model.predict(pool_cc30, rate_paths_32x120)
        assert np.all(cpr >= CPR_MIN - 1e-6), (
            f"CPR below minimum {CPR_MIN}: min={cpr.min():.6f}"
        )

    def test_cpr_upper_bound(self, tft_model, pool_cc30, rate_paths_32x120):
        cpr = tft_model.predict(pool_cc30, rate_paths_32x120)
        assert np.all(cpr <= CPR_MAX + 1e-6), (
            f"CPR above maximum {CPR_MAX}: max={cpr.max():.6f}"
        )

    def test_cpr_values_are_finite(self, tft_model, pool_cc30, rate_paths_32x120):
        cpr = tft_model.predict(pool_cc30, rate_paths_32x120)
        assert np.all(np.isfinite(cpr)), "CPR contains NaN or Inf"

    def test_cpr_not_constant(self, tft_model, pool_cc30, rate_paths_32x120):
        """TFT should produce varied CPR predictions, not a flat array."""
        cpr = tft_model.predict(pool_cc30, rate_paths_32x120)
        assert cpr.std() > 0.001, f"CPR output is suspiciously flat (std={cpr.std():.6f})"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestTFTDeterminism:

    def test_same_seed_same_output(self, pool_cc30, rate_paths_32x120):
        model_a = TFTPrepayModel(seed=7)
        model_b = TFTPrepayModel(seed=7)
        cpr_a = model_a.predict(pool_cc30, rate_paths_32x120)
        cpr_b = model_b.predict(pool_cc30, rate_paths_32x120)
        np.testing.assert_array_equal(cpr_a, cpr_b,
            err_msg="Different instances with same seed should produce identical output")

    def test_different_seed_different_output(self, pool_cc30, rate_paths_32x120):
        model_a = TFTPrepayModel(seed=7)
        model_b = TFTPrepayModel(seed=99)
        cpr_a = model_a.predict(pool_cc30, rate_paths_32x120)
        cpr_b = model_b.predict(pool_cc30, rate_paths_32x120)
        assert not np.allclose(cpr_a, cpr_b), \
            "Different seeds should produce different outputs"


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

class TestTFTFeatureEngineering:

    def test_build_features_shape(self, tft_model, pool_cc30, rate_paths_32x120):
        feats = tft_model._build_features(pool_cc30, rate_paths_32x120.short_rates)
        n_paths, n_periods = rate_paths_32x120.short_rates.shape
        assert feats.shape == (n_paths, n_periods, 11), (
            f"Expected (n_paths, n_periods, 11), got {feats.shape}"
        )

    def test_is_gnma_flag_zero_for_cc30(self, tft_model, pool_cc30, rate_paths_8x60):
        feats = tft_model._build_features(pool_cc30, rate_paths_8x60.short_rates)
        # is_gnma is feature index 8
        assert np.all(feats[:, :, 8] == 0.0), "CC30 should have is_gnma=0"

    def test_is_gnma_flag_one_for_gn30(self, tft_model, rate_paths_8x60):
        pool_gn30 = PoolCharacteristics(
            coupon=0.065, wac=0.068, wala=0, wam=360,
            loan_size=350_000, ltv=0.96, fico=680,
            pct_ca=0.05, pct_purchase=0.80,
            product_type="GN30",
        )
        feats = tft_model._build_features(pool_gn30, rate_paths_8x60.short_rates)
        assert np.all(feats[:, :, 8] == 1.0), "GN30 should have is_gnma=1"

    def test_is_15yr_flag(self, tft_model, pool_gn15, rate_paths_8x60):
        feats = tft_model._build_features(pool_gn15, rate_paths_8x60.short_rates)
        # is_15yr is feature index 9
        assert np.all(feats[:, :, 9] == 1.0), "GN15 should have is_15yr=1"


# ---------------------------------------------------------------------------
# Interface compatibility with PrepayModel
# ---------------------------------------------------------------------------

class TestTFTInterfaceCompatibility:

    def test_same_interface_as_prepay_model(self, pool_cc30, rate_paths_32x120):
        """TFTPrepayModel should expose same predict() signature as PrepayModel."""
        from analytics.prepay import PrepayModel
        stub = PrepayModel()
        tft  = TFTPrepayModel()

        cpr_stub = stub.predict(pool_cc30, rate_paths_32x120)
        cpr_tft  = tft.predict(pool_cc30, rate_paths_32x120)

        assert cpr_stub.shape == cpr_tft.shape, (
            f"Shape mismatch: PrepayModel {cpr_stub.shape} vs TFT {cpr_tft.shape}"
        )
        assert cpr_tft.dtype in (np.float32, np.float64), \
            f"Unexpected dtype: {cpr_tft.dtype}"
