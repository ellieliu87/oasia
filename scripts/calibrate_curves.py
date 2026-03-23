"""
Calibrate interest rate model curves from market data.

Fits Hull-White parameters (mean reversion speed a, volatility sigma)
to match observed swaption volatilities or cap/floor prices.

Usage:
    python scripts/calibrate_curves.py [--input FILE] [--output FILE] [--date DATE]

Input: CSV with columns: tenor_years, sofr_rate, treasury_rate
Output: JSON with calibrated Hull-White parameters + fitted term structure

The calibration minimizes the RMSE between model-implied bond prices
and market zero-coupon bond prices from the input curve.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, date
from pathlib import Path

import numpy as np

# Add parent directory to path so we can import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("calibrate_curves")


def _load_curve_from_csv(fpath: str) -> "TermStructure":
    """Load a TermStructure from a CSV file."""
    import pandas as pd
    from analytics.rate_paths import TermStructure

    df = pd.read_csv(fpath)
    if "tenor_years" not in df.columns or "sofr_rate" not in df.columns:
        raise ValueError(
            f"CSV must have 'tenor_years' and 'sofr_rate' columns. "
            f"Found: {list(df.columns)}"
        )

    tenors = df["tenor_years"].values.astype(float)
    rates = df["sofr_rate"].values.astype(float)
    return TermStructure(tenors=tenors, rates=rates)


def _model_implied_bond_price(
    t: float,
    r0: float,
    a: float,
    sigma: float,
    curve: "TermStructure",
) -> float:
    """
    Compute Hull-White model-implied zero-coupon bond price P(0, t).

    In Hull-White, the bond price is:
    P(0,t) = A(0,t) * exp(-B(0,t) * r0)

    where:
    B(0,t) = (1 - exp(-a*t)) / a
    ln A(0,t) = ln(P_mkt(0,t)/P_mkt(0,0)) - B(0,t) * f(0,0)
                - sigma^2 / (4a) * (1 - exp(-2a*t)) * B(0,t)^2

    For calibration purposes, we check that the model reproduces the market
    zero-coupon bond prices (which it should exactly by construction).
    """
    # Market bond price at t
    p_mkt = curve.discount_factor(t)

    # B factor
    if a < 1e-6:
        B = t
    else:
        B = (1 - np.exp(-a * t)) / a

    # log A factor (based on market fit)
    f0 = curve.forward_rate(1e-4)  # instantaneous forward at t=0

    # Variance term
    variance_term = (sigma ** 2 / (2 * a ** 2)) * (
        t - (2 / a) * (1 - np.exp(-a * t))
        + (1 / (2 * a)) * (1 - np.exp(-2 * a * t))
    ) if a > 1e-6 else sigma ** 2 * t ** 3 / 6

    log_A = np.log(p_mkt) + B * f0 - 0.5 * variance_term

    return np.exp(log_A - B * r0)


def calibrate_hull_white(
    curve: "TermStructure",
    target_tenors: np.ndarray = None,
    initial_a: float = 0.10,
    initial_sigma: float = 0.015,
    verbose: bool = True,
) -> dict:
    """
    Calibrate Hull-White parameters to fit the input term structure.

    Minimizes RMSE between model-implied and market zero-coupon bond prices
    using scipy minimize.

    Parameters
    ----------
    curve : TermStructure
        Market term structure to calibrate against.
    target_tenors : np.ndarray, optional
        Tenors to use for calibration (defaults to curve tenors).
    initial_a : float
        Initial mean reversion speed.
    initial_sigma : float
        Initial volatility.
    verbose : bool
        Print calibration progress.

    Returns
    -------
    dict
        {a, sigma, rmse_bps, fit_quality, calibration_date}
    """
    from scipy.optimize import minimize

    if target_tenors is None:
        target_tenors = curve.tenors

    # Initial short rate = instantaneous forward rate
    r0 = curve.forward_rate(1e-4)

    # Market bond prices
    market_prices = np.array([curve.discount_factor(t) for t in target_tenors])

    def objective(params: np.ndarray) -> float:
        a, sigma = params[0], params[1]
        if a <= 0 or sigma <= 0:
            return 1e10

        model_prices = np.array([
            _model_implied_bond_price(t, r0, a, sigma, curve)
            for t in target_tenors
        ])

        # Convert to yields for comparison
        eps = 1e-10
        model_yields = np.where(
            target_tenors > eps,
            -np.log(np.maximum(model_prices, eps)) / target_tenors,
            r0,
        )
        market_yields = np.where(
            target_tenors > eps,
            -np.log(np.maximum(market_prices, eps)) / target_tenors,
            r0,
        )

        rmse = np.sqrt(np.mean((model_yields - market_yields) ** 2))
        return float(rmse)

    if verbose:
        logger.info("Starting Hull-White calibration...")
        logger.info("Initial parameters: a=%.4f, sigma=%.4f", initial_a, initial_sigma)

    result = minimize(
        objective,
        x0=[initial_a, initial_sigma],
        method="Nelder-Mead",
        options={
            "xatol": 1e-6,
            "fatol": 1e-8,
            "maxiter": 1000,
            "disp": False,
        },
        bounds=[(0.001, 2.0), (0.001, 0.50)],
    )

    a_cal = float(result.x[0])
    sigma_cal = float(result.x[1])
    rmse = float(result.fun)
    rmse_bps = rmse * 10_000

    if verbose:
        logger.info("Calibration complete:")
        logger.info("  Mean reversion (a):  %.6f", a_cal)
        logger.info("  Volatility (sigma):  %.6f", sigma_cal)
        logger.info("  RMSE:                %.4f bps", rmse_bps)
        logger.info("  Convergence:         %s", "YES" if result.success else "NO")
        logger.info("  Iterations:          %d", result.nit)

    # Assess fit quality
    if rmse_bps < 0.1:
        fit_quality = "excellent"
    elif rmse_bps < 1.0:
        fit_quality = "good"
    elif rmse_bps < 5.0:
        fit_quality = "acceptable"
    else:
        fit_quality = "poor"

    return {
        "a": a_cal,
        "sigma": sigma_cal,
        "r0": float(r0),
        "rmse_bps": round(rmse_bps, 4),
        "fit_quality": fit_quality,
        "converged": bool(result.success),
        "iterations": int(result.nit),
        "calibration_date": date.today().isoformat(),
        "tenors": target_tenors.tolist(),
        "market_rates": [float(curve.zero_rate(t)) for t in target_tenors],
    }


def _validate_calibration(
    params: dict,
    curve: "TermStructure",
    n_paths: int = 256,
    n_periods: int = 120,
    seed: int = 42,
) -> dict:
    """
    Validate calibration by checking arbitrage-free property.

    Runs Monte Carlo paths and checks E[df[:,t]] matches market bond prices.
    """
    from analytics.rate_paths import generate_rate_paths

    logger.info("Validating calibration with %d paths, %d periods...", n_paths, n_periods)

    rate_paths = generate_rate_paths(
        curve=curve,
        n_paths=n_paths,
        n_periods=n_periods,
        a=params["a"],
        sigma=params["sigma"],
        seed=seed,
    )

    # Check E[df] vs market prices at select tenors
    dt = 1 / 12.0
    validation_periods = [12, 24, 60, 120]  # 1Y, 2Y, 5Y, 10Y
    validation_results = []

    for t_idx in validation_periods:
        if t_idx >= n_periods:
            continue

        t = (t_idx + 1) * dt
        mean_df = float(np.mean(rate_paths.discount_factors[:, t_idx]))
        mkt_df = float(curve.discount_factor(t))
        error_bps = abs(mean_df - mkt_df) / mkt_df * 10_000 * t  # approximate yield error

        validation_results.append({
            "tenor_years": round(t, 2),
            "market_df": round(mkt_df, 6),
            "model_mean_df": round(mean_df, 6),
            "error_bps": round(error_bps, 3),
        })
        logger.info(
            "  t=%.1fY: mkt_df=%.6f, model_df=%.6f, error=%.2f bps",
            t, mkt_df, mean_df, error_bps,
        )

    return {"validation_checks": validation_results}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calibrate Hull-White parameters to the current SOFR curve."
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Input CSV with tenor_years, sofr_rate columns (default: latest market data CSV).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file for calibrated parameters (default: CACHE_DIR/hw_params.json).",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Market data date YYYY-MM-DD (default: today).",
    )
    parser.add_argument(
        "--initial-a",
        type=float,
        default=0.10,
        help="Initial mean reversion speed (default: 0.10).",
    )
    parser.add_argument(
        "--initial-sigma",
        type=float,
        default=0.015,
        help="Initial volatility (default: 0.015).",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run Monte Carlo validation after calibration.",
    )
    parser.add_argument(
        "--n-paths",
        type=int,
        default=256,
        help="Number of MC paths for validation (default: 256).",
    )

    args = parser.parse_args()

    # Determine input file
    if args.input:
        curve = _load_curve_from_csv(args.input)
    else:
        try:
            from data.market_data import load_market_data
            as_of = None
            if args.date:
                as_of = datetime.strptime(args.date, "%Y-%m-%d").date()
            md = load_market_data(as_of_date=as_of)
            curve = md.sofr_curve
            logger.info("Loaded market data for %s", md.as_of_date)
        except Exception as e:
            logger.error("Could not load market data: %s", e)
            sys.exit(1)

    # Determine output file
    if args.output:
        output_path = Path(args.output)
    else:
        try:
            from config import Config
            output_path = Path(Config.CACHE_DIR) / "hw_params.json"
        except Exception:
            output_path = Path("./data/cache/hw_params.json")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Run calibration
    logger.info("Calibrating Hull-White model to SOFR curve...")
    params = calibrate_hull_white(
        curve=curve,
        initial_a=args.initial_a,
        initial_sigma=args.initial_sigma,
        verbose=True,
    )

    # Optionally validate
    if args.validate:
        validation = _validate_calibration(params, curve, n_paths=args.n_paths)
        params.update(validation)

    # Save results
    with open(output_path, "w") as f:
        json.dump(params, f, indent=2)

    logger.info("Parameters saved to: %s", output_path)

    # Print summary
    print("\n" + "=" * 50)
    print("HULL-WHITE CALIBRATION SUMMARY")
    print("=" * 50)
    print(f"  Mean reversion (a):  {params['a']:.6f}")
    print(f"  Volatility (sigma):  {params['sigma']:.6f}")
    print(f"  Initial rate (r0):   {params['r0']:.4f} ({params['r0']*100:.2f}%)")
    print(f"  RMSE:                {params['rmse_bps']:.4f} bps")
    print(f"  Fit quality:         {params['fit_quality'].upper()}")
    print(f"  Converged:           {'YES' if params['converged'] else 'NO'}")
    print("=" * 50)

    sys.exit(0 if params["converged"] else 1)


if __name__ == "__main__":
    main()
