"""
Prepayment model for agency MBS.

Provides:
- PoolCharacteristics dataclass
- PrepayModel stub (in-house model interface)
- project_prepay_speeds() function
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

from analytics.rate_paths import RatePaths


@dataclass
class PoolCharacteristics:
    """Loan-level characteristics for an MBS pool."""
    coupon: float         # pass-through coupon rate (decimal, e.g. 0.06)
    wac: float            # weighted average coupon (decimal)
    wala: int             # weighted average loan age (months)
    wam: int              # weighted average maturity (months remaining)
    loan_size: float      # average loan size ($)
    ltv: float            # loan-to-value ratio (decimal, e.g. 0.75)
    fico: int             # weighted average FICO score
    pct_ca: float         # fraction in California (decimal)
    pct_purchase: float   # fraction purchase loans (decimal)
    product_type: str     # CC30/CC15/GN30/GN15/FHLMC30

    # Optional fields
    pool_id: str = ""
    original_balance: float = 0.0
    current_balance: float = 0.0


class PrepayModel:
    """
    Stub for in-house prepayment model.

    In production this loads a calibrated model from PREPAY_MODEL_PATH.
    The stub implements a behavioral prepayment model based on:
    - Refinancing incentive (rate-driven)
    - Seasoning ramp (PSA-style)
    - Geographic and credit adjustments
    """

    def __init__(self, model_path: str = None):
        self.model_path = model_path
        self._loaded = False
        # Try to load production model if path is specified
        if model_path:
            try:
                self._load_model(model_path)
            except Exception:
                pass  # Fall back to stub implementation

    def _load_model(self, path: str) -> None:
        """
        Load model from disk.

        Supports NeuralPrepayModel (pickle) produced by
        scripts/generate_hypothetical_prepay_model.py.
        """
        from analytics.neural_prepay import NeuralPrepayModel
        self._model = NeuralPrepayModel.load(path)
        self._loaded = True

    def predict(self, pool: PoolCharacteristics, rate_paths: RatePaths) -> np.ndarray:
        """
        Predict CPR for each path and period.

        Parameters
        ----------
        pool : PoolCharacteristics
        rate_paths : RatePaths
            Shape (n_paths, n_periods)

        Returns
        -------
        np.ndarray
            CPR array of shape (n_paths, n_periods), values in [0, 1].
        """
        if self._loaded and hasattr(self, "_model"):
            return self._model.predict(pool, rate_paths)

        return _stub_predict(pool, rate_paths)


CPR_MIN = 0.02  # 2% floor (turnover only) for non-prepaying product types


def _stub_predict(pool: PoolCharacteristics, rate_paths: RatePaths) -> np.ndarray:
    """
    Stub prepayment model implementation.

    Driven by:
    1. Refinancing incentive: refi_incentive = WAC - current_mortgage_rate
    2. Seasoning ramp: linear ramp over 30 months
    3. Geographic/credit adjustments
    """
    n_paths, n_periods = rate_paths.short_rates.shape

    # Non-prepaying product types — return near-zero turnover CPR
    if pool.product_type in ("TSY", "CDBT", "CMBS"):
        return np.full((n_paths, n_periods), CPR_MIN)

    dt = rate_paths.dt

    # Convert short rate to approximate 30-year mortgage rate
    # Mortgage rate ≈ 10-year equivalent + 150 bps spread
    # Use 10-year average from the short rate (rough approximation)
    # For each path/period, roll 120-period average as proxy for 10Y rate
    short_rates = rate_paths.short_rates  # (n_paths, n_periods)

    # Approximate current mortgage rate as short rate + 150 bps (historical spread)
    mortgage_rate_proxy = short_rates + 0.015  # rough mortgage spread

    # Refinancing incentive: positive = cheaper to refi
    refi_incentive = pool.wac - mortgage_rate_proxy  # (n_paths, n_periods)

    # Logistic refinancing multiplier
    # S-curve: logistic(x) where x = 8 * refi_incentive (scaled)
    def logistic(x: np.ndarray) -> np.ndarray:
        return 1.0 / (1.0 + np.exp(-x))

    refi_multiplier = logistic(8.0 * refi_incentive)  # (n_paths, n_periods)

    # Base CPR: ranges from ~3% at no incentive to ~40% at strong incentive
    base_cpr_min = 0.03
    base_cpr_max = 0.40
    base_cpr = base_cpr_min + (base_cpr_max - base_cpr_min) * refi_multiplier

    # Seasoning ramp (PSA-style): linear ramp over first 30 months
    period_indices = np.arange(1, n_periods + 1)  # shape (n_periods,)
    loan_age = pool.wala + period_indices           # effective age in months
    seasoning_ramp = np.minimum(loan_age / 30.0, 1.0)  # shape (n_periods,)

    # Broadcast: base_cpr (n_paths, n_periods) * seasoning_ramp (n_periods,)
    seasoned_cpr = base_cpr * seasoning_ramp[np.newaxis, :]

    # Geographic adjustment: CA pools have higher prepayment speeds
    geo_factor = 1.0 + 0.10 * pool.pct_ca

    # LTV adjustment: high LTV pools have lower refinancing ability
    ltv_factor = np.clip(1.0 - 0.5 * (pool.ltv - 0.70), 0.70, 1.20)

    # FICO adjustment: higher FICO → more refinancing savvy
    fico_normalized = (pool.fico - 680) / 100.0
    fico_factor = 1.0 + 0.10 * np.clip(fico_normalized, -1.0, 1.5)

    # Purchase vs. refi adjustment: purchase loans have lower turnover initially
    purchase_factor = 1.0 - 0.10 * pool.pct_purchase

    # Combined adjustment
    adjustment = geo_factor * ltv_factor * fico_factor * purchase_factor

    # Final CPR with all adjustments
    cpr = np.clip(seasoned_cpr * adjustment, 0.01, 0.60)

    return cpr


def _psa_to_cpr(psa_multiple: float, n_periods: int, wala: int = 0) -> np.ndarray:
    """Convert PSA multiple to monthly CPR schedule."""
    # 100 PSA = 0.2% CPR/month ramp to 6% CPR over 30 months
    periods = np.arange(1, n_periods + 1)
    loan_age = wala + periods
    # Standard PSA benchmark
    benchmark_cpr = np.minimum(loan_age * 0.002, 0.06)  # 100 PSA benchmark
    return benchmark_cpr * psa_multiple


def project_prepay_speeds(
    pool: PoolCharacteristics,
    rate_paths: RatePaths,
    model: PrepayModel = None,
    cpr_override: float = None,
    psa_override: float = None,
) -> np.ndarray:
    """
    Project CPR speeds for each Monte Carlo path.

    Parameters
    ----------
    pool : PoolCharacteristics
    rate_paths : RatePaths
    model : PrepayModel, optional
        If None, uses stub model.
    cpr_override : float, optional
        If provided, use constant CPR for all paths and periods.
    psa_override : float, optional
        If provided, convert PSA multiple to CPR schedule (applied uniformly across paths).

    Returns
    -------
    np.ndarray
        Shape (n_paths, n_periods), values in [0, 1] representing annual CPR.
    """
    n_paths, n_periods = rate_paths.short_rates.shape

    if cpr_override is not None:
        return np.full((n_paths, n_periods), cpr_override)

    if psa_override is not None:
        cpr_1d = _psa_to_cpr(psa_override, n_periods, pool.wala)
        return np.broadcast_to(cpr_1d[np.newaxis, :], (n_paths, n_periods)).copy()

    if model is None:
        model = PrepayModel()

    return model.predict(pool, rate_paths)
