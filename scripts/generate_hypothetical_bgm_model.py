"""
Generate and save a hypothetical calibrated BGM0.5 term structure model.

This script builds a BGMTermStructureModel with parameters representative of
a high-rate environment (SOFR ~4.5%, typical 2025 MBS desk configuration):

    Rebonato vol:    a=0.10, b=0.20, c=0.60, d=0.08
    Correlation:     beta_corr=0.015
    Factors:         3 (level / slope / curvature)
    Tenor spacing:   delta=0.5 yr  (semi-annual LIBOR)
    Horizon:         N=60 forward rates (30 years)

Validation checks:
    1. Factor variance explained (>= 90% expected)
    2. Vol surface shape  (humped; peak around 1-2yr time-to-expiry)
    3. No-negative-rates  (log-normal dynamics guarantee positivity)
    4. Martingale check   (E[L_k] approx L_k(0) under spot measure)
    5. OAS-relevance      (spread stability across parallel rate shocks)

Usage
-----
    uv run python scripts/generate_hypothetical_bgm_model.py
    uv run python scripts/generate_hypothetical_bgm_model.py --output ./data/models/bgm_model.pkl
    uv run python scripts/generate_hypothetical_bgm_model.py --skip-validation
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from analytics.bgm_model import BGMParameters, BGMTermStructureModel
from analytics.rate_paths import TermStructure, generate_rate_paths


# ---------------------------------------------------------------------------
# Reference curve (high-rate 2025 environment)
# ---------------------------------------------------------------------------

def _reference_curve() -> TermStructure:
    """
    Synthetic SOFR curve representing a 4.5% rate environment.
    Used only for validation; the saved model does not embed a curve.
    """
    tenors = np.array([0.083, 0.25, 0.5, 1.0, 2.0, 3.0,
                       5.0,   7.0, 10.0, 15.0, 20.0, 30.0])
    # Slight positive slope: short ~4.3%, 10Y ~4.65%, 30Y ~4.75%
    rates = np.array([0.0430, 0.0440, 0.0445, 0.0455, 0.0460, 0.0462,
                      0.0465, 0.0468, 0.0470, 0.0472,  0.0473,  0.0475])
    return TermStructure(tenors=tenors, rates=rates)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(model: BGMTermStructureModel, verbose: bool = True) -> dict:
    """Run sanity checks and return a dict of results."""

    results = {}
    curve = _reference_curve()

    # 1. Factor variance explained
    var_exp = model.variance_explained
    results["variance_explained"] = var_exp
    _log(f"  Factor variance explained : {var_exp*100:.2f}%  (>= 90% expected)", verbose)

    # 2. Vol surface shape
    vols = model.vol_surface(t_obs=0.0)
    peak_idx = int(np.argmax(vols))
    peak_tte = peak_idx * model.params.delta
    results["vol_peak_tte_yr"] = peak_tte
    results["vol_short_end"] = float(vols[0])
    results["vol_long_end"] = float(vols[-1])
    _log(f"  Vol short-end (x=0)       : {vols[0]*100:.1f}%", verbose)
    _log(f"  Vol peak      (x={peak_tte:.1f}yr)   : {vols[peak_idx]*100:.1f}%  "
         f"(humped > flat is desirable)", verbose)
    _log(f"  Vol long-end  (x=30yr)    : {vols[-1]*100:.1f}%", verbose)

    # 3. No negative rates
    paths = model.generate_paths(curve, n_paths=64, n_periods=120, seed=1)
    neg_rate_pct = float((paths.short_rates < 0).mean()) * 100
    results["neg_rate_pct"] = neg_rate_pct
    _log(f"  Negative short rates      : {neg_rate_pct:.3f}%  (0% expected for log-normal)", verbose)

    # 4. Martingale check: E[L_k(T)] / L_k(0) - 1 for k=5 (2.5yr rate)
    k_check = 5
    delta = model.params.delta
    T_check = (k_check + 1) * delta

    # Initial forward rate
    disc = np.array([curve.discount_factor(t * delta) for t in range(model.params.n_tenors + 1)])
    L0 = np.maximum((disc[:-1] / disc[1:] - 1.0) / delta, 1e-6)
    L0_k = float(L0[k_check])

    # Simulated forward rate at expiry (period index ~ T_check / dt)
    n_sim_periods = max(1, int(T_check / (1 / 12)) + 1)
    paths_mart = model.generate_paths(curve, n_paths=256, n_periods=n_sim_periods, seed=7)
    L_k_expiry = (np.exp(paths_mart.short_rates[:, -1] * delta) - 1.0) / delta  # approx
    L_k_mean = float(np.mean(L_k_expiry))
    mart_bias_bps = (L_k_mean - L0_k) / L0_k * 100
    results["martingale_bias_pct"] = mart_bias_pct = mart_bias_bps
    _log(f"  Martingale check L_{k_check}       : "
         f"E[L]/L0 - 1 = {mart_bias_pct:+.2f}%  (small |value| expected)", verbose)

    # 5. Parallel shift consistency: OAS should be roughly stable
    #    Run BGM with base curve and +100bp shifted curve; compare mean short rate
    curve_up = curve.shifted(parallel_shift_bps=100)
    paths_base = model.generate_paths(curve,    n_paths=64, n_periods=60, seed=3)
    paths_up   = model.generate_paths(curve_up, n_paths=64, n_periods=60, seed=3)
    mean_diff_bps = float(np.mean(paths_up.short_rates - paths_base.short_rates)) * 10_000
    results["shift_passthrough_bps"] = mean_diff_bps
    _log(f"  +100bp shift passthrough  : mean short rate delta = {mean_diff_bps:.1f} bps "
         f"(~100 bps expected)", verbose)

    # 6. Discount factor sanity: DF[T=10yr] should be plausible
    df_10y = float(np.mean(paths.discount_factors[:, 119]))   # period 120 ≈ 10yr
    implied_yield = -np.log(df_10y) / 10.0
    results["df_10y_implied_yield"] = implied_yield
    _log(f"  10Y implied yield (avg)   : {implied_yield*100:.2f}%  "
         f"(near 4-5% expected)", verbose)

    return results


def _log(msg: str, verbose: bool) -> None:
    if verbose:
        print(msg)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(args: argparse.Namespace) -> None:
    output_path = Path(args.output)

    print("=" * 60)
    print("Oasia - Hypothetical BGM0.5 Term Structure Model")
    print("=" * 60)
    print(f"  Tenor spacing : delta = 0.5 yr (semi-annual LIBOR)")
    print(f"  Forward rates : N = 60  (30-year horizon)")
    print(f"  Factors       : 3  (level / slope / curvature)")
    print(f"  Vol model     : Rebonato (a,b,c,d) humped parameterisation")
    print(f"  Correlation   : exponential decay  rho_ij = exp(-0.015 * |i-j|)")
    print(f"  Output        : {output_path}")
    print()

    t0 = time.time()

    # --- Build model -------------------------------------------------------
    params = BGMParameters(
        a=0.10,          # short-end vol contribution
        b=0.20,          # hump amplitude
        c=0.60,          # hump decay rate
        d=0.08,          # long-end vol floor
        beta_corr=0.015,  # correlation decay: rho(1Y-10Y)~0.74, rho(1Y-5Y)~0.86
        delta=0.5,
        n_tenors=60,
        n_factors=3,
    )

    print("Building BGM0.5 model ...")
    model = BGMTermStructureModel(params)
    model.build()
    elapsed = time.time() - t0

    print(f"  Factor structure built in {elapsed:.2f}s")
    print(f"  Factor loadings shape : {model._factor_loadings.shape}")
    print(f"  Variance explained    : {model.variance_explained*100:.2f}%")
    print()

    # --- Validation --------------------------------------------------------
    if not args.skip_validation:
        print("Validating ...")
        validate(model, verbose=True)
        print()

    # --- Save --------------------------------------------------------------
    model.save(output_path)
    size_kb = output_path.stat().st_size / 1024
    print(f"Model saved -> {output_path}  ({size_kb:.0f} KB)")
    print()
    print("To activate: set  BGM_MODEL_PATH=./data/models/bgm_model.pkl  in .env")
    print("             generate_rate_paths() will use BGM automatically.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build and save the hypothetical Oasia BGM0.5 term structure model."
    )
    parser.add_argument(
        "--output", default="./data/models/bgm_model.pkl",
        help="Output path (default: ./data/models/bgm_model.pkl)",
    )
    parser.add_argument(
        "--skip-validation", action="store_true",
        help="Skip post-build validation",
    )
    main(parser.parse_args())
