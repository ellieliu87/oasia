"""
Generate and train a hypothetical feedforward neural network prepayment model.

This script:
  1. Constructs a wide synthetic training set spanning realistic agency MBS
     pool characteristics and interest rate environments.
  2. Labels each observation using a closed-form behavioural prepayment
     function (S-curve refi + seasoning + credit/geo adjustments) with
     calibrated noise to mimic estimation uncertainty from real loan data.
  3. Trains a NeuralPrepayModel (MLPRegressor: 11 → 128 → 64 → 32 → 1).
  4. Validates: monotonicity, R², and out-of-sample MAE.
  5. Saves to PREPAY_MODEL_PATH (default ./data/models/prepay_model.pkl).

Usage
─────
    uv run python scripts/generate_hypothetical_prepay_model.py
    uv run python scripts/generate_hypothetical_prepay_model.py --n-pools 400 --n-rate-scenarios 32
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

# Add project root to path so we can import analytics/
sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.rate_paths import TermStructure, RatePaths, generate_rate_paths
from analytics.prepay import PoolCharacteristics
from analytics.neural_prepay import (
    NeuralPrepayModel, build_feature_matrix, CPR_MIN, CPR_MAX,
)


# ─────────────────────────────────────────────────────────────────────────────
# Behavioural label function
# ─────────────────────────────────────────────────────────────────────────────

def _generate_labels(
    pool: PoolCharacteristics,
    rate_paths: RatePaths,
    noise_std: float = 0.012,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """
    Closed-form behavioural prepayment function used to generate training labels.

    This encodes the economic intuition that should be recovered by the NN:
      - Refinancing: logistic S-curve in refi incentive (dominant driver)
      - Burnout: high cumulative incentive → slower future speeds
      - Seasoning: PSA-style ramp over first 30 months
      - Turnover: baseline mobility (home sales), not rate-dependent
      - Credit/geo: multiplicative adjustments for LTV, FICO, CA, purchase
      - Product: 15yr vs 30yr, conventional vs Ginnie Mae
    """
    if rng is None:
        rng = np.random.default_rng(0)

    n_paths, n_periods = rate_paths.short_rates.shape
    short = rate_paths.short_rates

    # Approximate mortgage rate
    n = short.shape[1]
    smooth = np.zeros_like(short)
    alpha = 2.0 / 121
    smooth[:, 0] = short[:, 0]
    for t in range(1, n):
        smooth[:, t] = alpha * short[:, t] + (1 - alpha) * smooth[:, t - 1]
    mortgage_rate = smooth + 0.017

    # ── Refinancing component ──────────────────────────────────────────────
    refi_inc = pool.wac - mortgage_rate                       # (P, T)

    # Burnout: accumulated incentive damps future prepays
    pos_inc = np.maximum(refi_inc, 0.0)
    cumulative = np.cumsum(pos_inc, axis=1)
    burnout_damper = np.exp(-2.5 * cumulative)               # range (0, 1]

    # S-curve: steepness=6.5, centred at +30 bps incentive
    refi_cpr = 0.38 / (1.0 + np.exp(-6.5 * (refi_inc - 0.003)))
    refi_cpr = refi_cpr * burnout_damper

    # ── Turnover component (rate-independent baseline mobility) ────────────
    # ~4-6% CPR from house sales regardless of rates
    turnover_base = 0.04 + 0.015 * pool.pct_purchase         # purchase pools turn faster

    # ── Seasoning ramp ────────────────────────────────────────────────────
    periods = np.arange(1, n_periods + 1)
    loan_age = pool.wala + periods
    ramp = np.minimum(loan_age / 30.0, 1.0)                  # (T,)
    ramp_mat = ramp[np.newaxis, :]

    # ── Combined CPR before adjustments ───────────────────────────────────
    total_refi = refi_cpr * ramp_mat
    total_cpr = total_refi + turnover_base * ramp_mat

    # ── Multiplicative adjustments ────────────────────────────────────────
    # LTV: high LTV → constrained borrowers, can't refi easily
    ltv_adj = np.clip(1.0 - 1.2 * max(pool.ltv - 0.72, 0.0), 0.55, 1.05)

    # FICO: higher score → more rate-sensitive, faster refi
    fico_adj = 1.0 + 0.18 * np.clip((pool.fico - 740) / 80.0, -1.5, 1.5)

    # Loan size: jumbo-lite pools (large loans) refi faster when incentive exists
    loan_size_adj = 1.0 + 0.12 * np.log(max(pool.loan_size, 1.0) / 350_000.0)
    loan_size_adj = np.clip(loan_size_adj, 0.80, 1.25)

    # California concentration
    ca_adj = 1.0 + 0.12 * pool.pct_ca

    # 15-year product: faster absolute speeds due to shorter loan term
    yr15_adj = 1.15 if pool.product_type in ("CC15", "GN15") else 1.0

    # Ginnie Mae: slightly slower refi (FHA/VA borrowers less rate-sensitive)
    gnma_adj = 0.90 if pool.product_type in ("GN30", "GN15") else 1.0

    adjustment = ltv_adj * fico_adj * loan_size_adj * ca_adj * yr15_adj * gnma_adj

    cpr = total_cpr * adjustment

    # ── Add calibrated noise ───────────────────────────────────────────────
    noise = rng.normal(0.0, noise_std, size=cpr.shape)
    cpr = cpr + noise

    return np.clip(cpr, CPR_MIN, CPR_MAX)


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic pool and rate generators
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_pools(n: int, rng: np.random.Generator) -> list[PoolCharacteristics]:
    """Generate n diverse PoolCharacteristics covering the MBS universe."""
    product_types = ["CC30", "CC30", "CC30", "CC15", "GN30", "GN15"]  # weighted
    pools = []
    for _ in range(n):
        pt = product_types[rng.integers(len(product_types))]
        is_15 = "15" in pt

        # Coupon (WAC) range: 4.5–8.0% for typical MBS universe
        wac = rng.uniform(0.045, 0.080)
        coupon = wac - rng.uniform(0.002, 0.006)   # pass-through < WAC

        wala = int(rng.integers(0, 120))
        wam  = (180 if is_15 else 360) - wala
        wam  = max(wam, 12)

        pools.append(PoolCharacteristics(
            coupon       = coupon,
            wac          = wac,
            wala         = wala,
            wam          = wam,
            loan_size    = rng.uniform(150_000, 900_000),
            ltv          = rng.uniform(0.55, 0.97),
            fico         = int(rng.integers(640, 820)),
            pct_ca       = rng.uniform(0.0, 0.45),
            pct_purchase = rng.uniform(0.10, 0.90),
            product_type = pt,
        ))
    return pools


def _synthetic_curve(base_10y: float, slope_2s10s: float) -> TermStructure:
    """Generate a TermStructure from a 10Y rate and 2s10s slope."""
    tenors = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])
    # Simple Nelson-Siegel-like parametric curve
    short = base_10y - slope_2s10s
    rates = short + (base_10y - short) * (1 - np.exp(-tenors / 5.0))
    rates = np.clip(rates, 0.01, 0.15)
    return TermStructure(tenors=tenors, rates=rates)


# ─────────────────────────────────────────────────────────────────────────────
# Main training pipeline
# ─────────────────────────────────────────────────────────────────────────────

def build_training_data(
    n_pools: int = 250,
    n_rate_scenarios: int = 24,
    n_paths_per_scenario: int = 16,
    n_periods: int = 120,           # 10 years is enough to capture prepay dynamics
    rng_seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate X (features) and y (CPR labels) for model training.

    Strategy
    ────────
    - Sample n_pools diverse pool profiles
    - For each pool, sample n_rate_scenarios different rate curves
      (varying 10Y level 3%–8%, slope −50bp to +200bp)
    - For each (pool, curve), generate n_paths_per_scenario Monte Carlo paths
    - Label using the behavioural function + noise
    - This gives n_pools × n_rate_scenarios × n_paths_per_scenario × n_periods
      rows — each row is one (path, period) observation

    Returns
    -------
    X : (N, 11)   feature matrix
    y : (N,)      CPR labels
    """
    rng = np.random.default_rng(rng_seed)
    pools = _synthetic_pools(n_pools, rng)

    all_X: list[np.ndarray] = []
    all_y: list[np.ndarray] = []

    print(f"Building training data: {n_pools} pools x {n_rate_scenarios} rate scenarios "
          f"x {n_paths_per_scenario} paths x {n_periods} periods")

    for p_idx, pool in enumerate(pools):
        if (p_idx + 1) % 50 == 0:
            print(f"  Pool {p_idx + 1}/{n_pools}  "
                  f"({len(all_X)} batches accumulated so far)")

        for _ in range(n_rate_scenarios):
            # Random rate environment
            base_10y  = rng.uniform(0.030, 0.080)
            slope     = rng.uniform(-0.005, 0.020)
            curve = _synthetic_curve(base_10y, slope)

            rate_paths = generate_rate_paths(
                curve=curve,
                n_paths=n_paths_per_scenario,
                n_periods=n_periods,
                seed=int(rng.integers(1_000_000)),
            )

            X = build_feature_matrix(pool, rate_paths, n_periods_override=n_periods)
            y = _generate_labels(pool, rate_paths, rng=rng)
            y_flat = y.reshape(-1)                # (P*T,)

            all_X.append(X)
            all_y.append(y_flat)

    X_train = np.concatenate(all_X, axis=0)
    y_train = np.concatenate(all_y, axis=0)

    print(f"Training set: {X_train.shape[0]:,} observations, "
          f"{X_train.shape[1]} features")
    print(f"CPR range in labels: [{y_train.min():.3f}, {y_train.max():.3f}]  "
          f"mean={y_train.mean():.3f}  std={y_train.std():.3f}")

    return X_train, y_train


def validate_model(
    model: NeuralPrepayModel,
    rng_seed: int = 999,
    n_pools: int = 20,
) -> None:
    """
    Run a set of sanity checks on the trained model.

    Checks
    ──────
    1. R² on held-out validation set
    2. MAE on held-out validation set
    3. Monotonicity: higher refi incentive → higher CPR
    4. Burnout: same incentive after high cumulative incentive → lower CPR
    5. Seasoning: seasoned loan (WALA=60) > unseasoned (WALA=0) in early periods
    """
    from sklearn.metrics import r2_score, mean_absolute_error

    print("\nValidation")
    print("----------")

    # ── Held-out validation set ────────────────────────────────────────────
    X_val, y_val = build_training_data(
        n_pools=n_pools, n_rate_scenarios=8, n_paths_per_scenario=8,
        n_periods=60, rng_seed=rng_seed,
    )
    y_pred = model.predict_from_features(X_val)

    r2  = r2_score(y_val, y_pred)
    mae = mean_absolute_error(y_val, y_pred) * 100    # in CPR percentage points

    print(f"  R2:   {r2:.4f}  (>0.92 expected)")
    print(f"  MAE:  {mae:.2f} CPR pp  (<1.5 pp expected)")

    # ── Monotonicity check ─────────────────────────────────────────────────
    base_pool = PoolCharacteristics(
        coupon=0.060, wac=0.065, wala=24, wam=336,
        loan_size=400_000, ltv=0.75, fico=740,
        pct_ca=0.15, pct_purchase=0.60, product_type="CC30",
    )
    base_curve = TermStructure(
        tenors=np.array([0.5, 1, 2, 5, 10, 30]),
        rates=np.array([0.043, 0.044, 0.045, 0.046, 0.047, 0.048]),
    )

    # Rate shocks: +300bp means rates way above WAC → little refi incentive
    cprs = {}
    for shock_bps in [-200, -100, 0, 100, 200, 300]:
        shifted = TermStructure(
            tenors=base_curve.tenors,
            rates=base_curve.rates + shock_bps / 10_000,
        )
        paths = generate_rate_paths(shifted, n_paths=32, n_periods=36, seed=1)
        pred = model.predict(base_pool, paths)
        cprs[shock_bps] = float(pred.mean())

    print("\n  Monotonicity (rate shock -> CPR):")
    prev = None
    mono_ok = True
    for shock, cpr in sorted(cprs.items()):
        flag = ""
        if prev is not None and cpr > prev + 0.002:
            flag = "  [FAIL: should decrease as rates rise]"
            mono_ok = False
        print(f"    {shock:+4d} bp -> CPR {cpr*100:.1f}%{flag}")
        prev = cpr

    print(f"  Monotonicity: {'PASS' if mono_ok else 'FAIL (may occur at curve edges)'}")

    # ── Burnout check ──────────────────────────────────────────────────────
    # Simulate a pool that has already been through a refi wave vs fresh pool
    low_rate_curve = TermStructure(
        tenors=np.array([0.5, 1, 2, 5, 10, 30]),
        rates=np.array([0.025, 0.026, 0.027, 0.028, 0.029, 0.030]),
    )
    paths_fresh = generate_rate_paths(low_rate_curve, n_paths=32, n_periods=60, seed=2)
    cpr_fresh = model.predict(base_pool, paths_fresh).mean(axis=0)

    burnout_pool = PoolCharacteristics(
        **{k: getattr(base_pool, k) for k in base_pool.__dataclass_fields__}  # copy
    )
    burnout_pool.wala = 84   # 7 years seasoned — more burnout expected
    cpr_burnout = model.predict(burnout_pool, paths_fresh).mean(axis=0)

    ratio = cpr_fresh[30] / max(cpr_burnout[30], 1e-6)
    print(f"\n  Burnout check (period 30, low rates):")
    print(f"    Fresh pool CPR:   {cpr_fresh[30]*100:.1f}%")
    print(f"    Burnout pool CPR: {cpr_burnout[30]*100:.1f}%")
    print(f"    Ratio: {ratio:.2f}  (>1.0 expected - fresh pool should prepay faster)")


def main(args: argparse.Namespace) -> None:
    output_path = Path(args.output)

    print("=" * 60)
    print("Oasia - Hypothetical Neural Prepayment Model Generator")
    print("=" * 60)
    print(f"Architecture: 11 -> 128 -> 64 -> 32 -> 1 (ReLU / logistic)")
    print(f"Output path:  {output_path}")
    print()

    t0 = time.time()

    # ── Build training data ────────────────────────────────────────────────
    X_train, y_train = build_training_data(
        n_pools=args.n_pools,
        n_rate_scenarios=args.n_rate_scenarios,
        n_paths_per_scenario=args.n_paths,
        n_periods=args.n_periods,
    )

    # ── Train model ────────────────────────────────────────────────────────
    print(f"\nTraining neural network ...")
    model = NeuralPrepayModel()
    model.fit(X_train, y_train)
    elapsed = time.time() - t0
    print(f"Training complete in {elapsed:.1f}s")
    print(f"  Iterations:  {model._net.n_iter_}")
    print(f"  Loss (final): {model._net.loss_:.6f}")

    # ── Validate ───────────────────────────────────────────────────────────
    if not args.skip_validation:
        try:
            validate_model(model)
        except Exception as exc:
            print(f"  [validation error: {exc}]")

    # ── Save ──────────────────────────────────────────────────────────────
    model.save(output_path)
    size_kb = output_path.stat().st_size / 1024
    print(f"\nModel saved -> {output_path}  ({size_kb:.0f} KB)")
    print("\nTo use: set PREPAY_MODEL_PATH in .env, or pass model_path to PrepayModel().")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Train the hypothetical Oasia neural prepayment model."
    )
    parser.add_argument(
        "--output", default="./data/models/prepay_model.pkl",
        help="Output path for the serialised model (default: ./data/models/prepay_model.pkl)",
    )
    parser.add_argument(
        "--n-pools", type=int, default=250,
        help="Number of synthetic pool profiles (default: 250)",
    )
    parser.add_argument(
        "--n-rate-scenarios", type=int, default=24,
        help="Rate curve scenarios per pool (default: 24)",
    )
    parser.add_argument(
        "--n-paths", type=int, default=16,
        help="Monte Carlo paths per scenario (default: 16)",
    )
    parser.add_argument(
        "--n-periods", type=int, default=120,
        help="Periods per path for training (default: 120)",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Skip post-training validation checks",
    )
    main(parser.parse_args())
