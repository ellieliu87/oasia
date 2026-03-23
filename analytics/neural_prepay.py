"""
Neural Network Prepayment Model for Agency MBS.

Architecture
────────────
Feedforward neural network (MLPRegressor) with MBS-domain feature engineering.

Input features (11 per observation):
  1.  refi_incentive    WAC − current mortgage rate (primary driver)
  2.  burnout           cumulative excess refi incentive experienced (path-dependent)
  3.  seasoning         WALA + period (loan age in months, log-scaled)
  4.  ltv               LTV ratio (decimal)
  5.  fico_norm         (FICO − 740) / 80
  6.  loan_size_norm    log(loan_size / 350_000)
  7.  pct_ca            California concentration (decimal)
  8.  pct_purchase      purchase loan fraction (decimal)
  9.  is_gnma           1 if GN30 or GN15 product, else 0
  10. is_15yr           1 if CC15 or GN15 product, else 0
  11. wam_norm          WAM / 360 (remaining maturity fraction)

Target: annualised CPR (decimal, clipped to [0.02, 0.58])

Network topology: 11 → 128 → 64 → 32 → 1 (relu hidden, logistic output)
The logistic output is linearly rescaled from [0, 1] to [0.02, 0.58] so
the network learns an unconstrained real-valued problem internally.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from analytics.rate_paths import RatePaths


# CPR output bounds
CPR_MIN = 0.02   # 2% floor  (turnover / housing mobility)
CPR_MAX = 0.58   # 58% cap   (extreme refi wave)


# ─────────────────────────────────────────────────────────────────────────────
# Feature engineering
# ─────────────────────────────────────────────────────────────────────────────

def _mortgage_rate_from_short_rate(short_rates: np.ndarray) -> np.ndarray:
    """
    Approximate 30-year mortgage rate from short rate paths.

    Mortgage rate ≈ 10Y equivalent + primary/secondary spread (~170 bps).
    We approximate the 10Y rate as a smoothed version of the short rate
    using an exponential kernel (mimics term premium without extra state).
    """
    # Rolling 120-period (10Y) smoothed version of short rate
    n_paths, n_periods = short_rates.shape
    smooth = np.zeros_like(short_rates)
    alpha = 2.0 / (120 + 1)           # EMA weight
    smooth[:, 0] = short_rates[:, 0]
    for t in range(1, n_periods):
        smooth[:, t] = alpha * short_rates[:, t] + (1 - alpha) * smooth[:, t - 1]
    return smooth + 0.017              # 170 bps primary/secondary spread


def build_feature_matrix(
    pool,                              # PoolCharacteristics
    rate_paths: RatePaths,
    n_periods_override: int | None = None,
) -> np.ndarray:
    """
    Build the (n_paths × n_periods, 11) feature matrix.

    Parameters
    ----------
    pool : PoolCharacteristics
    rate_paths : RatePaths
    n_periods_override : int, optional
        Trim to fewer periods (used during batch training for speed).

    Returns
    -------
    np.ndarray  shape (n_paths * n_periods, 11)
    """
    n_paths, n_periods = rate_paths.short_rates.shape
    if n_periods_override:
        n_periods = min(n_periods, n_periods_override)

    short = rate_paths.short_rates[:, :n_periods]            # (P, T)
    mortgage_rate = _mortgage_rate_from_short_rate(short)    # (P, T)

    # 1. Refinancing incentive: positive = in-the-money to refi
    refi_inc = pool.wac - mortgage_rate                      # (P, T)

    # 2. Burnout: cumulative positive incentive per path (path-dependent memory)
    positive_inc = np.maximum(refi_inc, 0.0)
    burnout = np.cumsum(positive_inc, axis=1)                # (P, T)
    # Normalise: cap at 1.0 (after ~12 months of strong incentive, fully burnt)
    burnout_norm = np.clip(burnout / 0.60, 0.0, 1.0)

    # 3. Seasoning (log-scaled loan age in months)
    periods = np.arange(1, n_periods + 1)                    # (T,)
    loan_age = pool.wala + periods                           # (T,)
    seasoning = np.log1p(loan_age) / np.log1p(360)          # (T,) → [0, 1]
    seasoning_mat = np.broadcast_to(
        seasoning[np.newaxis, :], (n_paths, n_periods)
    ).copy()

    # 4–11: pool-level scalars broadcast to (P, T)
    def _fill(v: float) -> np.ndarray:
        return np.full((n_paths, n_periods), v)

    ltv          = _fill(float(pool.ltv))
    fico_norm    = _fill((pool.fico - 740.0) / 80.0)
    loan_sz_norm = _fill(np.log(max(pool.loan_size, 1.0) / 350_000.0))
    pct_ca       = _fill(float(pool.pct_ca))
    pct_purch    = _fill(float(pool.pct_purchase))
    is_gnma      = _fill(1.0 if pool.product_type in ("GN30", "GN15") else 0.0)
    is_15yr      = _fill(1.0 if pool.product_type in ("CC15", "GN15") else 0.0)
    wam_norm     = _fill(pool.wam / 360.0)

    # Stack all features: (P, T, 11) → (P*T, 11)
    features = np.stack(
        [refi_inc, burnout_norm, seasoning_mat, ltv, fico_norm,
         loan_sz_norm, pct_ca, pct_purch, is_gnma, is_15yr, wam_norm],
        axis=2,
    )
    return features.reshape(-1, 11)


# ─────────────────────────────────────────────────────────────────────────────
# Model class
# ─────────────────────────────────────────────────────────────────────────────

class NeuralPrepayModel:
    """
    Feedforward neural network prepayment model.

    Wraps a scikit-learn MLPRegressor with domain-specific feature engineering
    and provides the standard predict(pool, rate_paths) → np.ndarray interface.

    Architecture
    ────────────
    11 inputs → [128, 64, 32] hidden (ReLU) → 1 output (logistic)
    Output is linearly rescaled to [CPR_MIN, CPR_MAX].

    The model is trained by scripts/generate_hypothetical_prepay_model.py and
    serialised to data/models/prepay_model.pkl via NeuralPrepayModel.save().
    """

    N_FEATURES = 11
    HIDDEN_LAYERS = (128, 64, 32)

    def __init__(self):
        from sklearn.neural_network import MLPRegressor
        from sklearn.preprocessing import StandardScaler

        self._scaler = StandardScaler()
        self._net = MLPRegressor(
            hidden_layer_sizes=self.HIDDEN_LAYERS,
            activation="relu",            # ReLU on hidden layers
            solver="adam",
            alpha=1e-4,                   # L2 regularisation
            batch_size=2048,
            learning_rate="adaptive",
            max_iter=500,
            random_state=42,
            verbose=False,
        )
        # Output activation: targets are scaled to [0, 1] before fitting,
        # so the linear output layer learns to stay in [0, 1]; predictions
        # are clipped to [0, 1] in predict() for safety.
        self._fitted = False

    # ── Training ──────────────────────────────────────────────────────────

    def fit(self, X: np.ndarray, y: np.ndarray) -> "NeuralPrepayModel":
        """
        Fit the network.

        Parameters
        ----------
        X : (N, 11) feature matrix from build_feature_matrix()
        y : (N,) target CPR in [CPR_MIN, CPR_MAX]
        """
        # Scale target to (0, 1) for logistic output
        y_scaled = (y - CPR_MIN) / (CPR_MAX - CPR_MIN)
        y_scaled = np.clip(y_scaled, 0.0, 1.0)

        X_scaled = self._scaler.fit_transform(X)
        self._net.fit(X_scaled, y_scaled)
        self._fitted = True
        return self

    # ── Inference ─────────────────────────────────────────────────────────

    def predict(self, pool, rate_paths: RatePaths) -> np.ndarray:
        """
        Predict CPR for each Monte Carlo path and period.

        Parameters
        ----------
        pool : PoolCharacteristics
        rate_paths : RatePaths  shape (n_paths, n_periods)

        Returns
        -------
        np.ndarray  shape (n_paths, n_periods), annualised CPR in [CPR_MIN, CPR_MAX]
        """
        n_paths, n_periods = rate_paths.short_rates.shape

        X = build_feature_matrix(pool, rate_paths)          # (P*T, 11)
        X_scaled = self._scaler.transform(X)
        y_scaled = self._net.predict(X_scaled)               # (P*T,) in (0, 1)

        # Rescale back to CPR range
        cpr_flat = CPR_MIN + (CPR_MAX - CPR_MIN) * np.clip(y_scaled, 0.0, 1.0)
        return cpr_flat.reshape(n_paths, n_periods)

    def predict_from_features(self, X: np.ndarray) -> np.ndarray:
        """
        Run inference directly on a pre-built feature matrix.

        Parameters
        ----------
        X : (N, 11) feature matrix (output of build_feature_matrix)

        Returns
        -------
        np.ndarray  shape (N,), CPR in [CPR_MIN, CPR_MAX]
        """
        X_scaled = self._scaler.transform(X)
        y_scaled = self._net.predict(X_scaled)
        return CPR_MIN + (CPR_MAX - CPR_MIN) * np.clip(y_scaled, 0.0, 1.0)

    # ── Persistence ───────────────────────────────────────────────────────

    def save(self, path: str | Path) -> None:
        """Serialise model and scaler to a pickle file."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: str | Path) -> "NeuralPrepayModel":
        """Load a previously saved model from disk."""
        with open(path, "rb") as f:
            obj = pickle.load(f)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected NeuralPrepayModel, got {type(obj)}")
        return obj
