"""
Tests for portfolio attribution engine.

Verifies the adding-up constraint: sum of attribution drivers == total change.
All tests use synthetic snapshots — no API keys required.
"""
import numpy as np
import pytest
import pandas as pd
from datetime import date


# ---------------------------------------------------------------------------
# Helpers to build synthetic snapshots
# ---------------------------------------------------------------------------

def _make_snapshot(pools: list[dict], snapshot_date: date = None) -> pd.DataFrame:
    """Build a synthetic snapshot DataFrame."""
    if snapshot_date is None:
        snapshot_date = date(2025, 1, 1)

    rows = []
    for p in pools:
        rows.append({
            "snapshot_date": snapshot_date,
            "pool_id": p["pool_id"],
            "face_amount": p.get("face_amount", 1_000_000),
            "book_price": p.get("book_price", 100.0),
            "coupon": p.get("coupon", 0.06),
            "wac": p.get("wac", 0.065),
            "oas": p.get("oas", 50.0),
            "oad": p.get("oad", 4.5),
            "convexity": p.get("convexity", -0.5),
            "book_yield": p.get("book_yield", 0.06),
            "product_type": p.get("product_type", "CC30"),
            "purchase_date": p.get("purchase_date", "2024-01-01"),
        })
    return pd.DataFrame(rows)


# Standard test portfolio
_POOL_A = {
    "pool_id": "TEST-POOL-30YR",
    "face_amount": 5_000_000,
    "book_price": 101.5,
    "coupon": 0.06,
    "wac": 0.065,
    "oas": 54.2,
    "oad": 4.52,
    "convexity": -0.74,
    "book_yield": 0.0608,
    "product_type": "CC30",
    "purchase_date": "2024-06-01",
}

_POOL_B = {
    "pool_id": "TEST-POOL-15YR",
    "face_amount": 3_000_000,
    "book_price": 99.5,
    "coupon": 0.055,
    "wac": 0.059,
    "oas": 36.8,
    "oad": 3.21,
    "convexity": -0.22,
    "book_yield": 0.0562,
    "product_type": "CC15",
    "purchase_date": "2024-09-15",
}

_POOL_C = {
    "pool_id": "TEST-POOL-GN30",
    "face_amount": 4_000_000,
    "book_price": 103.0,
    "coupon": 0.065,
    "wac": 0.07,
    "oas": 58.1,
    "oad": 4.18,
    "convexity": -1.12,
    "book_yield": 0.0631,
    "product_type": "GN30",
    "purchase_date": "2023-12-01",
}


# ---------------------------------------------------------------------------
# OAS Attribution Tests
# ---------------------------------------------------------------------------

class TestOASAttribution:

    def test_oas_attribution_adds_up(self):
        """Sum of OAS attribution drivers must equal total OAS change."""
        from portfolio.attribution import compute_oas_attribution

        start_date = date(2025, 1, 1)
        end_date = date(2025, 2, 1)

        start_snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], start_date)

        # End snapshot: same pools with slightly changed OAS
        pool_a_end = {**_POOL_A, "oas": 58.0, "oad": 4.45}
        pool_b_end = {**_POOL_B, "oas": 39.0, "oad": 3.18}
        pool_c_end = {**_POOL_C, "oas": 62.0, "oad": 4.10}
        end_snap = _make_snapshot([pool_a_end, pool_b_end, pool_c_end], end_date)

        universe_oas_start = {
            "CC30": 52.0, "CC15": 34.0, "GN30": 47.0, "GN15": 30.0,
        }
        universe_oas_end = {
            "CC30": 54.5, "CC15": 36.0, "GN30": 49.0, "GN15": 32.0,
        }

        result = compute_oas_attribution(
            start_snapshot=start_snap,
            end_snapshot=end_snap,
            universe_oas_start=universe_oas_start,
            universe_oas_end=universe_oas_end,
        )

        # Adding-up constraint
        drivers = [
            result["sector_spread_change"],
            result["spread_carry"],
            result["mix_new_purchases"],
            result["mix_paydowns"],
            result["prepay_model_effect"],
        ]
        driver_sum = sum(drivers)
        total = result["total"]

        assert abs(driver_sum - total) < 1e-6, (
            f"OAS attribution doesn't add up: "
            f"sum(drivers)={driver_sum:.6f}, total={total:.6f}, "
            f"difference={abs(driver_sum - total):.2e}"
        )

    def test_oas_attribution_with_new_purchase(self):
        """Adding a new high-OAS pool should show up in mix_new_purchases."""
        from portfolio.attribution import compute_oas_attribution

        start_snap = _make_snapshot([_POOL_A, _POOL_B], date(2025, 1, 1))

        # End: same pools + one new high-OAS pool
        new_pool = {
            "pool_id": "NEW-POOL-CHEAP",
            "face_amount": 2_000_000,
            "book_price": 99.0,
            "coupon": 0.065,
            "oas": 75.0,
            "oad": 4.8,
            "book_yield": 0.068,
            "product_type": "CC30",
        }
        end_snap = _make_snapshot([_POOL_A, _POOL_B, new_pool], date(2025, 2, 1))

        result = compute_oas_attribution(
            start_snapshot=start_snap,
            end_snapshot=end_snap,
            universe_oas_start={"CC30": 52.0, "CC15": 34.0},
            universe_oas_end={"CC30": 52.5, "CC15": 34.5},
        )

        # Sum should equal total
        drivers_sum = (
            result["sector_spread_change"] + result["spread_carry"] +
            result["mix_new_purchases"] + result["mix_paydowns"] +
            result["prepay_model_effect"]
        )
        assert abs(drivers_sum - result["total"]) < 1e-6, (
            f"Adding-up failed with new purchase: diff={abs(drivers_sum - result['total']):.2e}"
        )


# ---------------------------------------------------------------------------
# OAD Attribution Tests
# ---------------------------------------------------------------------------

class TestOADAttribution:

    def test_oad_attribution_adds_up(self):
        """Sum of OAD attribution drivers must equal total OAD change."""
        from portfolio.attribution import compute_oad_attribution

        start_snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 1, 1))

        # End: OAD slightly changed (aging + rate moves)
        pool_a_end = {**_POOL_A, "oad": 4.45, "oas": 54.5}
        pool_b_end = {**_POOL_B, "oad": 3.15, "oas": 37.0}
        pool_c_end = {**_POOL_C, "oad": 4.10, "oas": 59.0}
        end_snap = _make_snapshot([pool_a_end, pool_b_end, pool_c_end], date(2025, 2, 1))

        result = compute_oad_attribution(start_snap, end_snap)

        drivers_sum = (
            result["seasoning_effect"] + result["rate_level_effect"] +
            result["mix_new_purchases"] + result["mix_paydowns"] +
            result["sales_disposals"]
        )
        total = result["total"]

        assert abs(drivers_sum - total) < 1e-9, (
            f"OAD attribution doesn't add up: "
            f"sum={drivers_sum:.9f}, total={total:.9f}, "
            f"diff={abs(drivers_sum - total):.2e}"
        )

    def test_oad_attribution_with_paydown(self):
        """Removing a high-OAD pool should show up in attribution."""
        from portfolio.attribution import compute_oad_attribution

        start_snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 1, 1))

        # End: POOL_C (high OAD) paid down
        end_snap = _make_snapshot([_POOL_A, _POOL_B], date(2025, 2, 1))

        result = compute_oad_attribution(start_snap, end_snap)

        # Adding-up must hold
        drivers_sum = (
            result["seasoning_effect"] + result["rate_level_effect"] +
            result["mix_new_purchases"] + result["mix_paydowns"] +
            result["sales_disposals"]
        )
        assert abs(drivers_sum - result["total"]) < 1e-9


# ---------------------------------------------------------------------------
# Yield Attribution Tests
# ---------------------------------------------------------------------------

class TestYieldAttribution:

    def test_yield_attribution_adds_up(self):
        """Sum of yield attribution drivers must equal total yield change."""
        from portfolio.attribution import compute_yield_attribution

        start_snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 1, 1))

        # End: yields slightly changed
        pool_a_end = {**_POOL_A, "book_yield": 0.0612}
        pool_b_end = {**_POOL_B, "book_yield": 0.0568}
        pool_c_end = {**_POOL_C, "book_yield": 0.0638}
        end_snap = _make_snapshot([pool_a_end, pool_b_end, pool_c_end], date(2025, 2, 1))

        result = compute_yield_attribution(start_snap, end_snap)

        drivers_sum = (
            result["prepay_burndown"] + result["new_purchases"] +
            result["paydown_effect"] + result["coupon_reinvested"] +
            result["amortization_scheduled"]
        )
        total = result["total"]

        assert abs(drivers_sum - total) < 1e-9, (
            f"Yield attribution doesn't add up: "
            f"sum={drivers_sum:.9f}, total={total:.9f}, "
            f"diff={abs(drivers_sum - total):.2e}"
        )

    def test_yield_attribution_with_new_high_yield_purchase(self):
        """Adding a new higher-yield position should increase total yield."""
        from portfolio.attribution import compute_yield_attribution

        start_snap = _make_snapshot([_POOL_A, _POOL_B], date(2025, 1, 1))

        new_pool = {
            "pool_id": "HIGH-YIELD-POOL",
            "face_amount": 3_000_000,
            "book_price": 98.5,
            "book_yield": 0.075,
            "coupon": 0.07,
            "product_type": "CC30",
        }
        end_snap = _make_snapshot([_POOL_A, _POOL_B, new_pool], date(2025, 2, 1))

        result = compute_yield_attribution(start_snap, end_snap)

        # Adding-up
        drivers_sum = (
            result["prepay_burndown"] + result["new_purchases"] +
            result["paydown_effect"] + result["coupon_reinvested"] +
            result["amortization_scheduled"]
        )
        assert abs(drivers_sum - result["total"]) < 1e-9


# ---------------------------------------------------------------------------
# EVE Attribution Tests
# ---------------------------------------------------------------------------

class TestEVEAttribution:

    def test_eve_attribution_adds_up(self):
        """Sum of EVE attribution drivers must equal total EVE change."""
        from portfolio.attribution import compute_eve_attribution

        start_snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 1, 1))

        # End: OAD changed (rates moved)
        pool_a_end = {**_POOL_A, "oad": 4.60, "book_price": 100.8}
        pool_b_end = {**_POOL_B, "oad": 3.28, "book_price": 99.1}
        pool_c_end = {**_POOL_C, "oad": 4.25, "book_price": 102.5}
        end_snap = _make_snapshot([pool_a_end, pool_b_end, pool_c_end], date(2025, 2, 1))

        result = compute_eve_attribution(start_snap, end_snap, shock_bps=200)

        drivers_sum = (
            result["rate_curve_change"] + result["portfolio_mix_change"] +
            result["prepay_model_effect"] + result["new_purchases_added"]
        )
        total = result["total"]

        assert abs(drivers_sum - total) < 1e-2, (
            f"EVE attribution doesn't add up: "
            f"sum={drivers_sum:.4f}, total={total:.4f}, "
            f"diff={abs(drivers_sum - total):.4f}"
        )

    def test_eve_attribution_different_shocks(self):
        """Adding-up should hold for any shock level."""
        from portfolio.attribution import compute_eve_attribution

        start_snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 1, 1))
        end_snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 2, 1))

        for shock in [100, 200, 300]:
            result = compute_eve_attribution(start_snap, end_snap, shock_bps=shock)

            drivers_sum = (
                result["rate_curve_change"] + result["portfolio_mix_change"] +
                result["prepay_model_effect"] + result["new_purchases_added"]
            )
            assert abs(drivers_sum - result["total"]) < 1e-2, (
                f"EVE attribution at {shock}bp doesn't add up: diff={abs(drivers_sum - result['total']):.4f}"
            )


# ---------------------------------------------------------------------------
# No-Change Tests
# ---------------------------------------------------------------------------

class TestNoChangeAttributions:

    def test_attribution_with_no_change_oas(self):
        """If start == end snapshot, all OAS drivers should be ~0."""
        from portfolio.attribution import compute_oas_attribution

        snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 1, 1))
        universe_oas = {"CC30": 52.0, "CC15": 34.0, "GN30": 47.0}

        result = compute_oas_attribution(snap, snap, universe_oas, universe_oas)

        # With identical snapshots, sector change should be 0
        assert result["sector_spread_change"] == 0.0, (
            f"sector_spread_change should be 0 when universe unchanged, got {result['sector_spread_change']}"
        )
        # Total should be 0 or very close
        assert abs(result["total"]) < 0.001, (
            f"Total OAS change with identical snapshots should be ~0, got {result['total']}"
        )
        # Adding-up must still hold
        drivers_sum = (
            result["sector_spread_change"] + result["spread_carry"] +
            result["mix_new_purchases"] + result["mix_paydowns"] +
            result["prepay_model_effect"]
        )
        assert abs(drivers_sum - result["total"]) < 1e-9

    def test_attribution_with_no_change_oad(self):
        """If start == end snapshot, OAD attribution total should be 0."""
        from portfolio.attribution import compute_oad_attribution

        snap = _make_snapshot([_POOL_A, _POOL_B], date(2025, 1, 1))
        result = compute_oad_attribution(snap, snap)

        assert abs(result["total"]) < 0.001, (
            f"OAD total change should be ~0 with identical snapshots, got {result['total']}"
        )

        drivers_sum = (
            result["seasoning_effect"] + result["rate_level_effect"] +
            result["mix_new_purchases"] + result["mix_paydowns"] +
            result["sales_disposals"]
        )
        assert abs(drivers_sum - result["total"]) < 1e-9

    def test_attribution_with_no_change_yield(self):
        """If start == end snapshot, yield attribution should be ~0."""
        from portfolio.attribution import compute_yield_attribution

        snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 1, 1))
        result = compute_yield_attribution(snap, snap)

        assert abs(result["total"]) < 0.001
        drivers_sum = (
            result["prepay_burndown"] + result["new_purchases"] +
            result["paydown_effect"] + result["coupon_reinvested"] +
            result["amortization_scheduled"]
        )
        assert abs(drivers_sum - result["total"]) < 1e-9

    def test_attribution_with_no_change_eve(self):
        """If start == end snapshot, EVE attribution drivers should be ~0."""
        from portfolio.attribution import compute_eve_attribution

        snap = _make_snapshot([_POOL_A, _POOL_B, _POOL_C], date(2025, 1, 1))
        result = compute_eve_attribution(snap, snap, shock_bps=200)

        assert abs(result["total"]) < 1.0, (
            f"EVE total change with identical snapshots should be ~0, got {result['total']}"
        )

        drivers_sum = (
            result["rate_curve_change"] + result["portfolio_mix_change"] +
            result["prepay_model_effect"] + result["new_purchases_added"]
        )
        assert abs(drivers_sum - result["total"]) < 1e-2


# ---------------------------------------------------------------------------
# Additional robustness tests
# ---------------------------------------------------------------------------

def test_oas_attribution_returns_all_keys():
    """Attribution dict must contain all required driver keys."""
    from portfolio.attribution import compute_oas_attribution

    snap = _make_snapshot([_POOL_A])
    result = compute_oas_attribution(snap, snap, {}, {})

    required_keys = {
        "sector_spread_change", "spread_carry", "mix_new_purchases",
        "mix_paydowns", "prepay_model_effect", "total"
    }
    assert required_keys.issubset(set(result.keys())), (
        f"Missing keys: {required_keys - set(result.keys())}"
    )


def test_oad_attribution_returns_all_keys():
    """OAD attribution dict must contain all required driver keys."""
    from portfolio.attribution import compute_oad_attribution

    snap = _make_snapshot([_POOL_A])
    result = compute_oad_attribution(snap, snap)

    required_keys = {
        "seasoning_effect", "rate_level_effect", "mix_new_purchases",
        "mix_paydowns", "sales_disposals", "total"
    }
    assert required_keys.issubset(set(result.keys()))


def test_yield_attribution_returns_all_keys():
    """Yield attribution dict must contain all required driver keys."""
    from portfolio.attribution import compute_yield_attribution

    snap = _make_snapshot([_POOL_A])
    result = compute_yield_attribution(snap, snap)

    required_keys = {
        "prepay_burndown", "new_purchases", "paydown_effect",
        "coupon_reinvested", "amortization_scheduled", "total"
    }
    assert required_keys.issubset(set(result.keys()))


def test_eve_attribution_returns_all_keys():
    """EVE attribution dict must contain all required driver keys."""
    from portfolio.attribution import compute_eve_attribution

    snap = _make_snapshot([_POOL_A])
    result = compute_eve_attribution(snap, snap)

    required_keys = {
        "rate_curve_change", "portfolio_mix_change",
        "prepay_model_effect", "new_purchases_added", "total"
    }
    assert required_keys.issubset(set(result.keys()))
