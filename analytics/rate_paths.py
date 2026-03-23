"""
Hull-White one-factor short rate model for generating Monte Carlo rate paths.

Model: dr = (θ(t) - a*r)*dt + σ*dW
- a: mean reversion speed
- σ: volatility
- θ(t): time-dependent drift calibrated to match input term structure
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass


@dataclass
class TermStructure:
    """Continuously compounded zero-coupon term structure."""
    tenors: np.ndarray   # years
    rates: np.ndarray    # continuously compounded zero rates (decimal)

    def zero_rate(self, t: float) -> float:
        """Interpolate zero rate at tenor t (years)."""
        return float(np.interp(t, self.tenors, self.rates))

    def discount_factor(self, t: float) -> float:
        """Zero-coupon bond price P(0, t)."""
        r = self.zero_rate(t)
        return float(np.exp(-r * t))

    def forward_rate(self, t: float, dt: float = 1e-4) -> float:
        """Instantaneous forward rate at time t."""
        if t < dt:
            t = dt
        r_t = self.zero_rate(t)
        r_t_dt = self.zero_rate(t + dt)
        return (r_t_dt * (t + dt) - r_t * t) / dt

    def shifted(self, parallel_shift_bps: float = 0,
                short_shift_bps: float = 0,
                long_shift_bps: float = 0,
                short_tenor_cutoff: float = 2.0) -> "TermStructure":
        """Return a new TermStructure with applied rate shocks (in bps)."""
        shifted_rates = self.rates.copy()
        parallel = parallel_shift_bps / 10_000
        for i, t in enumerate(self.tenors):
            short_weight = max(0.0, 1.0 - t / short_tenor_cutoff) if short_tenor_cutoff > 0 else 0.0
            long_weight = min(1.0, t / short_tenor_cutoff) if short_tenor_cutoff > 0 else 1.0
            shifted_rates[i] += (
                parallel
                + short_shift_bps / 10_000 * short_weight
                + long_shift_bps / 10_000 * long_weight
            )
        return TermStructure(tenors=self.tenors.copy(), rates=shifted_rates)


@dataclass
class RatePaths:
    """Container for Monte Carlo rate path simulation results."""
    short_rates: np.ndarray      # shape (n_paths, n_periods)
    discount_factors: np.ndarray # shape (n_paths, n_periods)
    dt: float                    # time step in years (1/12 for monthly)


# ---------------------------------------------------------------------------
# BGM model singleton — loaded lazily when BGM_MODEL_PATH is configured
# ---------------------------------------------------------------------------

_bgm_cache: dict = {"model": None, "path": None}


def _get_bgm_model():
    """Return the loaded BGMTermStructureModel if BGM_MODEL_PATH is set, else None."""
    try:
        from config import Config
        path = Config.BGM_MODEL_PATH
    except Exception:
        import os
        path = os.getenv("BGM_MODEL_PATH", "")

    if not path:
        return None

    import os
    if not os.path.exists(path):
        return None

    # Reload only if path changed
    if _bgm_cache["path"] != path:
        from analytics.bgm_model import BGMTermStructureModel
        _bgm_cache["model"] = BGMTermStructureModel.load(path)
        _bgm_cache["path"] = path

    return _bgm_cache["model"]


def generate_rate_paths(
    curve: TermStructure,
    n_paths: int = 256,
    n_periods: int = 360,
    dt: float = 1 / 12,
    a: float = 0.1,
    sigma: float = 0.015,
    seed: int = None,
) -> RatePaths:
    """
    Generate Monte Carlo rate paths using the Hull-White one-factor model.

    The model dr = (θ(t) - a*r)*dt + σ*dW is calibrated so that the expected
    discount factors match those implied by the input TermStructure.

    Uses antithetic variates for variance reduction.

    Parameters
    ----------
    curve : TermStructure
        Current market term structure used for calibration.
    n_paths : int
        Total number of paths (must be even for antithetic variates).
    n_periods : int
        Number of monthly time steps.
    dt : float
        Time step size in years (default 1/12 for monthly).
    a : float
        Mean reversion speed.
    sigma : float
        Short rate volatility.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    RatePaths
        Simulated short rates and discount factors.

    Notes
    -----
    When BGM_MODEL_PATH is set in the environment / config, this function
    delegates to BGMTermStructureModel.generate_paths() automatically.
    The Hull-White parameters (a, sigma) are ignored in that case.
    All callers remain unchanged.
    """
    # ── BGM dispatch ──────────────────────────────────────────────────────
    bgm = _get_bgm_model()
    if bgm is not None:
        return bgm.generate_paths(curve, n_paths=n_paths,
                                  n_periods=n_periods, dt=dt, seed=seed)

    # ── Hull-White fallback ───────────────────────────────────────────────
    if n_paths % 2 != 0:
        n_paths += 1  # ensure even for antithetic variates

    rng = np.random.default_rng(seed)
    half = n_paths // 2

    # Build time grid
    times = np.arange(1, n_periods + 1) * dt  # shape (n_periods,)

    # ---------------------------------------------------------------------------
    # Calibrate θ(t) to match the input term structure
    # In Hull-White: θ(t) = f'(0,t) + a*f(0,t) + σ²/(2a) * (1 - e^{-2at})
    # where f(0,t) is the instantaneous forward rate.
    # ---------------------------------------------------------------------------
    forward_rates = np.array([curve.forward_rate(t) for t in times])
    # Finite difference for df/dt
    dt_fwd = 1e-4
    forward_rates_fwd = np.array([curve.forward_rate(t + dt_fwd) for t in times])
    dfdt = (forward_rates_fwd - forward_rates) / dt_fwd

    theta = dfdt + a * forward_rates + (sigma ** 2 / (2 * a)) * (1 - np.exp(-2 * a * times))
    # theta shape: (n_periods,)

    # ---------------------------------------------------------------------------
    # Initial short rate = instantaneous forward rate at t=0
    # ---------------------------------------------------------------------------
    r0 = float(curve.forward_rate(dt / 2))

    # ---------------------------------------------------------------------------
    # Simulate using Euler-Maruyama (vectorized over paths)
    # Generate half paths then mirror for antithetic variates
    # ---------------------------------------------------------------------------
    # Z shape: (half, n_periods) — standard normal shocks
    Z = rng.standard_normal((half, n_periods))
    Z_anti = -Z  # antithetic

    sqrt_dt = np.sqrt(dt)

    def simulate(shocks: np.ndarray) -> np.ndarray:
        """Simulate short rates given (half, n_periods) shocks."""
        n = shocks.shape[0]
        r = np.empty((n, n_periods))
        r_prev = np.full(n, r0)
        for t_idx in range(n_periods):
            drift = (theta[t_idx] - a * r_prev) * dt
            diffusion = sigma * sqrt_dt * shocks[:, t_idx]
            r_next = r_prev + drift + diffusion
            r[:, t_idx] = r_next
            r_prev = r_next
        return r

    r_positive = simulate(Z)
    r_antithetic = simulate(Z_anti)

    # Combine: first half = positive, second half = antithetic
    short_rates = np.vstack([r_positive, r_antithetic])  # (n_paths, n_periods)

    # ---------------------------------------------------------------------------
    # Compute discount factors: df[i, t] = exp(-sum(r[i, 0:t+1]) * dt)
    # Cumulative sum along time axis
    # ---------------------------------------------------------------------------
    cumulative_rates = np.cumsum(short_rates, axis=1) * dt
    discount_factors = np.exp(-cumulative_rates)  # (n_paths, n_periods)

    return RatePaths(
        short_rates=short_rates,
        discount_factors=discount_factors,
        dt=dt,
    )
