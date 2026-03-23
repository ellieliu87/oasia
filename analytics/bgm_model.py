"""
BGM0.5 Term Structure Model (Brace-Gatarek-Musiela / LIBOR Market Model).

"BGM0.5" refers to a BGM model with delta = 0.5 year (semi-annual) tenor spacing.

Theory
------
Rather than modelling an unobservable short rate (Hull-White), BGM directly
models the evolution of discrete, market-observable simply-compounded forward
LIBOR rates L_k(t) = L(t; T_k, T_{k+1}), where T_k = k * delta.

For a 30-year MBS horizon with delta = 0.5 yr there are N = 60 forward rates.

Dynamics (log-normal, spot LIBOR measure)
------------------------------------------
  d ln L_k = (mu_k - 0.5 * ||sigma_k * v_k||^2) dt  +  sigma_k(t) * v_k . dW

Drift in the spot measure (no-arbitrage):
  mu_k(t) = sigma_k(t) * sum_{j=beta(t)}^{k}  rho_{k,j} * sigma_j(t) * delta * L_j(t)
                                                ----------------------------------------
                                                       1 + delta * L_j(t)

where beta(t) = floor(t / delta) is the index of the currently live forward rate.

Volatility: Rebonato (a, b, c, d) humped parameterisation
  sigma_k(t) = (a + b * (T_k - t)) * exp(-c * (T_k - t)) + d

Correlation: exponential decay
  rho_{i,j} = exp(-beta_corr * |i - j|)

Multi-factor reduction: 3-factor PCA of the N x N correlation matrix.
  rho ≈ V V^T   where V is (N, 3) scaled eigenvectors

Output: RatePaths with monthly short rates and discount factors,
        compatible with the existing Hull-White interface.

Short rate conversion:
  r(t_m) = ln(1 + delta * L_{k_live}(t_m)) / delta   [continuously compounded]

Period discount factor (monthly):
  P(t_m, t_{m+1}) = (1 + delta * L_{k_live}(t_m)) ^ (-dt / delta)
                  = (1 + delta * L_{k_live})          ^ (-1/6)
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Parameter container
# ---------------------------------------------------------------------------

@dataclass
class BGMParameters:
    """Calibrated parameters for the BGM0.5 model."""

    # Rebonato humped-vol parameters  sigma(x) = (a + b*x)*exp(-c*x) + d
    a: float = 0.10    # short-end level
    b: float = 0.20    # hump slope
    c: float = 0.60    # decay rate
    d: float = 0.08    # long-end floor

    # Correlation decay:  rho_{i,j} = exp(-beta_corr * |i - j|)
    # beta_corr=0.015 calibrated to match real yield curve correlations:
    #   rho(1Y-10Y) ~ 0.74, rho(1Y-5Y) ~ 0.86, rho(10Y-30Y) ~ 0.42
    beta_corr: float = 0.015

    # Model structure
    delta: float = 0.5       # tenor spacing in years (0.5 = semi-annual)
    n_tenors: int = 60        # number of forward rates  (60 * 0.5 = 30 yr)
    n_factors: int = 3        # PCA factors (level / slope / curvature)


# ---------------------------------------------------------------------------
# Model class
# ---------------------------------------------------------------------------

class BGMTermStructureModel:
    """
    BGM0.5 LIBOR Market Model.

    Persistent state (saved to disk):
        params           : BGMParameters
        _factor_loadings : (N, n_factors) scaled PCA eigenvectors
        _eigenvalue_share: fraction of variance explained by the factors

    Runtime state (not saved):
        Initial forward rates are derived fresh from the input TermStructure
        on each call to generate_paths(), so the model remains daily-curve-agnostic.
    """

    def __init__(self, params: BGMParameters | None = None):
        self.params = params or BGMParameters()
        self._factor_loadings: np.ndarray | None = None   # (N, n_factors)
        self._eigenvalue_share: float = 0.0
        self._built = False

    # ------------------------------------------------------------------
    # Build / calibrate
    # ------------------------------------------------------------------

    def build(self) -> "BGMTermStructureModel":
        """
        Pre-compute the factor structure from the correlation matrix.

        Must be called once before generate_paths().  Does not depend on
        the market curve (initial forward rates are injected at simulation time).
        """
        p = self.params
        N = p.n_tenors

        # Full N x N correlation matrix
        idx = np.arange(N, dtype=float)
        rho = np.exp(-p.beta_corr * np.abs(idx[:, None] - idx[None, :]))

        # Symmetric eigendecomposition
        eigenvalues, eigenvectors = np.linalg.eigh(rho)

        # Sort descending
        order = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[order]
        eigenvectors = eigenvectors[:, order]

        # Keep top n_factors; scale columns by sqrt(eigenvalue)
        # so that  V V^T  approximates  rho
        lam = eigenvalues[:p.n_factors]
        V = eigenvectors[:, :p.n_factors] * np.sqrt(lam)[None, :]

        self._factor_loadings = V                                # (N, n_factors)
        self._eigenvalue_share = lam.sum() / eigenvalues.sum()  # variance explained
        self._built = True
        return self

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------

    def generate_paths(
        self,
        curve,                       # TermStructure — current market curve
        n_paths: int = 256,
        n_periods: int = 360,        # monthly periods
        dt: float = 1 / 12,
        seed: int | None = None,
    ):
        """
        Simulate BGM0.5 rate paths and return a RatePaths object.

        The output is fully compatible with the existing Hull-White RatePaths
        interface used throughout the analytics stack.

        Parameters
        ----------
        curve : TermStructure
            Current SOFR / swap zero-coupon curve for initialising forward rates.
        n_paths : int
            Total paths (must be even for antithetic variates).
        n_periods : int
            Monthly time steps.
        dt : float
            Step size in years (default 1/12).
        seed : int, optional

        Returns
        -------
        RatePaths
        """
        from analytics.rate_paths import RatePaths

        if not self._built:
            self.build()

        if n_paths % 2 != 0:
            n_paths += 1

        p = self.params
        N = p.n_tenors
        rng = np.random.default_rng(seed)
        half = n_paths // 2
        n_factors = p.n_factors

        # ── Initial forward rates from market curve ──────────────────────
        # L_k(0) = [P(0, T_k) / P(0, T_{k+1}) - 1] / delta
        T = np.arange(N + 1) * p.delta           # T_0=0, ..., T_N=30 yr
        disc = np.array([curve.discount_factor(t) for t in T])   # (N+1,)
        L0 = np.maximum((disc[:-1] / disc[1:] - 1.0) / p.delta, 1e-6)  # (N,)

        # ── Pre-compute static arrays ─────────────────────────────────────
        tenors_T = T[:-1]                         # reset times T_k  (N,)
        V = self._factor_loadings                 # (N, n_factors)
        sqrt_dt = np.sqrt(dt)
        delta = p.delta
        a, b, c, d = p.a, p.b, p.c, p.d

        # ── Run simulation ─────────────────────────────────────────────────
        # Antithetic variates: generate half paths, mirror shocks
        # Z shape: (half, n_periods, n_factors)
        Z = rng.standard_normal((half, n_periods, n_factors))

        sr_pos, df_pos = self._simulate(L0, tenors_T, V, Z, half, n_periods, dt, sqrt_dt,
                                        delta, a, b, c, d, n_factors)
        sr_neg, df_neg = self._simulate(L0, tenors_T, V, -Z, half, n_periods, dt, sqrt_dt,
                                        delta, a, b, c, d, n_factors)

        short_rates = np.vstack([sr_pos, sr_neg])       # (n_paths, n_periods)
        discount_factors = np.vstack([df_pos, df_neg])  # (n_paths, n_periods)

        return RatePaths(
            short_rates=short_rates,
            discount_factors=discount_factors,
            dt=dt,
        )

    @staticmethod
    def _simulate(
        L0: np.ndarray,          # (N,)  initial forward rates
        tenors_T: np.ndarray,    # (N,)  reset times T_k
        V: np.ndarray,           # (N, n_factors)  factor loadings
        Z: np.ndarray,           # (half, n_periods, n_factors)  shocks
        half: int,
        n_periods: int,
        dt: float,
        sqrt_dt: float,
        delta: float,
        a: float, b: float, c: float, d: float,
        n_factors: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Core Euler simulation loop for one set of half-paths.

        Returns
        -------
        short_rates    : (half, n_periods)
        discount_factors: (half, n_periods)  cumulative
        """
        N = len(L0)

        # Mutable forward rate state: (half, N)
        L = np.tile(L0, (half, 1)).copy()

        short_rates = np.empty((half, n_periods))
        df_period   = np.empty((half, n_periods))

        for m in range(n_periods):
            t = m * dt

            # Index of the currently live forward rate (expires every 6 months)
            k_live = min(int(t / delta), N - 1)
            live = slice(k_live, N)
            N_live = N - k_live

            # Live forward rates and factor loadings
            L_live  = L[:, live]              # (half, N_live)
            V_live  = V[live, :]              # (N_live, n_factors)
            T_live  = tenors_T[live]          # (N_live,)

            # ── Rebonato volatilities ─────────────────────────────────────
            tte = np.maximum(T_live - t, 0.0)       # time-to-expiry  (N_live,)
            sigma_live = (a + b * tte) * np.exp(-c * tte) + d   # (N_live,)

            # ── BGM drift (spot measure) via factor lower-triangular sum ──
            # a_j = sigma_j * delta * L_j / (1 + delta * L_j)   (half, N_live)
            a_mat = sigma_live[None, :] * (delta * L_live / (1.0 + delta * L_live))

            # Cumulative factor-weighted sum: aV[p,k,f] = sum_{j<=k} a[p,j] * V[j,f]
            # Shape: (half, N_live, n_factors)
            aV       = a_mat[:, :, None] * V_live[None, :, :]
            aV_cum   = np.cumsum(aV, axis=1)          # (half, N_live, n_factors)

            # drift[p,k] = sigma_k * sum_f V[k,f] * aV_cum[p,k,f]
            # = sigma_k * dot(V[k,:], aV_cum[p,k,:])
            dot_prod   = np.einsum("kf,pkf->pk", V_live, aV_cum)  # (half, N_live)
            drift_live = sigma_live[None, :] * dot_prod            # (half, N_live)

            # ── Diffusion ─────────────────────────────────────────────────
            # dif[p,k] = sigma_k * sum_f V[k,f] * Z[p,m,f]
            Z_m        = Z[:, m, :]                                # (half, n_factors)
            dif_live   = sigma_live[None, :] * (Z_m @ V_live.T)   # (half, N_live)

            # Per-rate variance ||sigma_k * v_k||^2 = sigma_k^2 * ||v_k||^2
            var_live = sigma_live ** 2 * np.sum(V_live ** 2, axis=1)  # (N_live,)

            # ── Log-Euler update ──────────────────────────────────────────
            ln_L_new = (
                np.log(np.maximum(L_live, 1e-9))
                + (drift_live - 0.5 * var_live[None, :]) * dt
                + dif_live * sqrt_dt
            )
            L[:, live] = np.exp(ln_L_new)

            # ── Extract short rate and period discount factor ──────────────
            L_k = L[:, k_live]                                     # (half,)
            short_rates[:, m] = np.log1p(delta * L_k) / delta     # cont. compounded
            df_period[:, m]   = (1.0 + delta * L_k) ** (-dt / delta)

        return short_rates, np.cumprod(df_period, axis=1)

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def vol_surface(self, t_obs: float = 0.0) -> np.ndarray:
        """
        Rebonato caplet volatilities at observation time t_obs.

        Returns sigma_k for k = 0 ... N-1  (annualised lognormal vol).
        """
        p = self.params
        tenors_T = np.arange(p.n_tenors) * p.delta
        tte = np.maximum(tenors_T - t_obs, 0.0)
        return (p.a + p.b * tte) * np.exp(-p.c * tte) + p.d

    @property
    def variance_explained(self) -> float:
        """Fraction of correlation variance captured by the n_factors PCA factors."""
        return self._eigenvalue_share

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Serialise to pickle."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as fh:
            pickle.dump(self, fh, protocol=pickle.HIGHEST_PROTOCOL)

    @classmethod
    def load(cls, path: str | Path) -> "BGMTermStructureModel":
        """Load from pickle."""
        with open(path, "rb") as fh:
            obj = pickle.load(fh)
        if not isinstance(obj, cls):
            raise TypeError(f"Expected BGMTermStructureModel, got {type(obj)}")
        return obj
