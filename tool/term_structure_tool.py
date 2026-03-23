"""
Term Structure Tool
===================
Generates 256 simulated interest-rate paths using the BGM or Hull-White model.

Each path covers 360 monthly periods (30 years).  The tool is used by the
agent to obtain a `RatePaths` object that feeds into the prepayment model,
OAS solver, and interest-income calculations.
"""
from __future__ import annotations

import json
from typing import Any


# ── OpenAI schema ──────────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "generate_rate_paths",
            "description": (
                "Generate simulated interest-rate paths using the term structure model "
                "(BGM0.5 LIBOR market model with Hull-White fallback).  "
                "Returns 256 monthly short-rate paths over 30 years (360 periods), "
                "plus summary statistics for each path set."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "n_paths": {
                        "type": "integer",
                        "description": "Number of Monte Carlo paths (default 256, max 1024).",
                    },
                    "horizon_years": {
                        "type": "number",
                        "description": "Simulation horizon in years (default 30).",
                    },
                    "as_of_date": {
                        "type": "string",
                        "description": "Curve date YYYY-MM-DD (default: today).",
                    },
                    "rate_shock_bps": {
                        "type": "integer",
                        "description": (
                            "Optional parallel shift applied to the initial curve "
                            "before simulation (bps, default 0).  "
                            "Use to generate shocked path sets."
                        ),
                    },
                    "seed": {
                        "type": "integer",
                        "description": "RNG seed for reproducibility (default 42).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_rate_path_summary",
            "description": (
                "Return summary statistics for a set of simulated rate paths: "
                "mean/std/percentile short rates at key horizons (1, 3, 5, 10, 20, 30 yr), "
                "plus implied forward curve."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "as_of_date": {"type": "string", "description": "YYYY-MM-DD."},
                    "shock_scenarios_bps": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": (
                            "List of parallel shifts (bps) for which to return summaries.  "
                            "Default: [−300, −200, −100, 0, 100, 200, 300]."
                        ),
                    },
                },
                "required": [],
            },
        },
    },
]


# ── Handlers ──────────────────────────────────────────────────────────────────

def _handle_generate_rate_paths(inp: dict) -> str:
    import numpy as np
    from datetime import datetime, date as date_type
    from data.market_data import load_market_data
    from analytics.rate_paths import generate_rate_paths
    from db.cache import read_rate_paths, write_rate_paths

    n_paths     = min(int(inp.get("n_paths", 256)), 1024)
    horizon_yrs = float(inp.get("horizon_years", 30.0))
    shock_bps   = int(inp.get("rate_shock_bps", 0))
    seed        = int(inp.get("seed", 42))

    date_str = inp.get("as_of_date", "")
    as_of    = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date_type.today()
    n_periods = int(round(horizon_yrs * 12))

    # ── Cache check ────────────────────────────────────────────────────────
    cached = read_rate_paths(as_of, shock_bps, n_paths, n_periods, seed)
    if cached:
        cached["message"] = (
            f"Loaded {n_paths} paths × {n_periods} periods from cache "
            f"(shock {shock_bps:+d} bps)."
        )
        return json.dumps(cached, default=str)

    # ── Compute ────────────────────────────────────────────────────────────
    md = load_market_data(as_of)
    curve = md.sofr_curve

    if shock_bps:
        from analytics.rate_paths import TermStructure
        curve = TermStructure(
            tenors=curve.tenors,
            rates=curve.rates + shock_bps / 10_000.0,
        )

    rp = generate_rate_paths(curve=curve, n_paths=n_paths, n_periods=n_periods, seed=seed)
    sr = rp.short_rates

    key_months = [m for m in [12, 36, 60, 120, 240, 360] if m <= n_periods]
    summary: dict[str, Any] = {
        "n_paths":   n_paths,
        "n_periods": n_periods,
        "dt_years":  float(rp.dt),
        "shock_bps": shock_bps,
        "as_of_date": as_of.isoformat(),
        "short_rate_at_key_horizons": {},
    }
    for m in key_months:
        col = sr[:, m - 1]
        summary["short_rate_at_key_horizons"][f"{m//12}yr"] = {
            "mean_pct": round(float(np.mean(col)) * 100, 3),
            "std_pct":  round(float(np.std(col))  * 100, 3),
            "p5_pct":   round(float(np.percentile(col, 5))  * 100, 3),
            "p25_pct":  round(float(np.percentile(col, 25)) * 100, 3),
            "p75_pct":  round(float(np.percentile(col, 75)) * 100, 3),
            "p95_pct":  round(float(np.percentile(col, 95)) * 100, 3),
        }

    if n_periods >= 120:
        summary["implied_10y_fwd_rate_pct"] = round(
            float(np.mean(sr[:, 108:120])) * 100, 3
        )

    summary["message"] = (
        f"Generated {n_paths} paths × {n_periods} periods "
        f"(shock {shock_bps:+d} bps)."
    )

    # ── Write to cache (summary + Parquet) ────────────────────────────────
    try:
        write_rate_paths(as_of, shock_bps, n_paths, n_periods, seed, sr,
                         save_parquet=True)
    except Exception:
        pass

    return json.dumps(summary, default=str)


def _handle_get_rate_path_summary(inp: dict) -> str:
    import numpy as np
    from datetime import datetime
    from data.market_data import load_market_data
    from analytics.rate_paths import generate_rate_paths, TermStructure

    date_str = inp.get("as_of_date", "")
    as_of = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else None
    shocks = inp.get("shock_scenarios_bps", [-300, -200, -100, 0, 100, 200, 300])

    md = load_market_data(as_of)
    n_paths  = 256
    n_periods = 360
    key_months = [12, 60, 120, 240, 360]
    results: dict[str, Any] = {"as_of_date": md.as_of_date.isoformat(), "scenarios": {}}

    for shock in shocks:
        curve = md.sofr_curve
        if shock:
            from analytics.rate_paths import TermStructure
            curve = TermStructure(
                tenors=curve.tenors,
                rates=curve.rates + shock / 10_000.0,
            )
        rp = generate_rate_paths(curve=curve, n_paths=n_paths, n_periods=n_periods, seed=42)
        sr = rp.short_rates
        scen: dict[str, Any] = {}
        for m in key_months:
            if m <= n_periods:
                col = sr[:, m - 1]
                scen[f"{m//12}yr"] = {
                    "mean_pct": round(float(np.mean(col)) * 100, 3),
                    "p10_pct":  round(float(np.percentile(col, 10)) * 100, 3),
                    "p90_pct":  round(float(np.percentile(col, 90)) * 100, 3),
                }
        results["scenarios"][str(shock)] = scen

    return json.dumps(results, default=str)


# ── Handler registry ──────────────────────────────────────────────────────────

HANDLERS: dict[str, Any] = {
    "generate_rate_paths":    _handle_generate_rate_paths,
    "get_rate_path_summary":  _handle_get_rate_path_summary,
}
