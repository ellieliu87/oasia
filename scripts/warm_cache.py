"""
Warm the DuckDB results cache for all 1000 CUSIPs.

Usage
-----
    # Full run (all pools, base + 6 shock scenarios):
    python scripts/warm_cache.py

    # Quick smoke-test (first 10 pools, base only):
    python scripts/warm_cache.py --limit 10 --shocks 0

    # Only specific products:
    python scripts/warm_cache.py --products CC30 GN30

    # Resume — skip pools already in cache:
    python scripts/warm_cache.py --skip-cached

    # Save rate-path Parquet files too:
    python scripts/warm_cache.py --save-parquet

What it computes per pool × scenario
-------------------------------------
  1. Rate paths          (256 paths × 360 months) via BGM/Hull-White
  2. Prepayment speeds   (annual CPR for 30 years)
  3. Risk metrics        (OAS, OAD, convexity, yield, Z-spread)
  4. Interest income     (10-year projection, gross + net)

Progress is printed to stdout and can be piped to a log file.
The script is restartable: rows already in the DB are skipped with --skip-cached.
"""
from __future__ import annotations

import argparse
import sys
import time
import traceback
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pre-compute and cache model results for 1000 CUSIPs")
    p.add_argument("--limit",        type=int,   default=None,
                   help="Max pools to process (default: all 1000)")
    p.add_argument("--shocks",       type=int,   nargs="+",
                   default=[0, 100, 200, 300, -100, -200, -300],
                   help="Rate shocks in bps (default: 0 ±100 ±200 ±300)")
    p.add_argument("--products",     type=str,   nargs="+",
                   default=["CC30", "CC15", "GN30", "GN15"],
                   help="Product types to include")
    p.add_argument("--as-of-date",   type=str,   default=None,
                   help="Curve date YYYY-MM-DD (default: today)")
    p.add_argument("--n-paths",      type=int,   default=256,
                   help="Monte Carlo paths per run (default 256)")
    p.add_argument("--horizon-years",type=int,   default=10,
                   help="Interest-income horizon years (default 10)")
    p.add_argument("--skip-cached",  action="store_true",
                   help="Skip pools already present in DB for base scenario")
    p.add_argument("--save-parquet", action="store_true",
                   help="Save full rate-path arrays to Parquet files")
    p.add_argument("--workers",      type=int,   default=1,
                   help="Parallel worker threads (default 1; DuckDB write lock limits concurrency)")
    return p.parse_args()


# ── Per-pool computation ───────────────────────────────────────────────────────

def _compute_pool(
    pool_id: str,
    pool_row: dict,
    shock_bps: int,
    as_of: date,
    n_paths: int,
    horizon_years: int,
    save_parquet: bool,
) -> dict:
    """
    Run the full pipeline for one pool × one shock scenario.
    Returns a dict with keys: prepay_ok, risk_ok, income_ok, elapsed_s.
    """
    import numpy as np
    from analytics.prepay import PoolCharacteristics, PrepayModel, project_prepay_speeds
    from analytics.rate_paths import generate_rate_paths, TermStructure
    from analytics.oas_solver import compute_analytics
    from analytics.cashflows import get_cash_flows
    from data.market_data import load_market_data
    from data.intex_client import MockIntexClient
    from db.cache import (
        read_rate_paths, write_rate_paths,
        read_prepay, write_prepay,
        read_risk_metrics, write_risk_metrics,
        read_interest_income, write_interest_income,
    )

    t0 = time.perf_counter()

    # Pool characteristics
    c = float(pool_row["coupon"])
    w = float(pool_row["wac"])
    pool_chars = PoolCharacteristics(
        coupon=c / 100.0 if c > 1 else c,
        wac=w / 100.0 if w > 1 else w,
        wala=int(pool_row["wala_at_issue"]),
        wam=int(pool_row["original_wam"]) - int(pool_row["wala_at_issue"]),
        loan_size=float(pool_row["loan_size"]),
        ltv=float(pool_row["ltv"]),
        fico=int(pool_row["fico"]),
        pct_ca=float(pool_row["pct_ca"]),
        pct_purchase=float(pool_row["pct_purchase"]),
        product_type=str(pool_row["product_type"]),
        pool_id=pool_id,
        current_balance=float(pool_row["original_balance"]),
    )

    # Market price from latest snapshot (or par)
    market_price = 100.0
    try:
        from data.universe_1000 import get_pool_snapshot
        snap = get_pool_snapshot(pool_id)
        if snap:
            market_price = float(snap.get("market_price", 100.0))
    except Exception:
        pass

    # Rate paths (from cache or compute)
    n_periods = 360
    cached_paths = read_rate_paths(as_of, shock_bps, n_paths, n_periods, 42)
    if cached_paths and cached_paths.get("parquet_path"):
        from db.cache import load_rate_paths_from_parquet
        sr = load_rate_paths_from_parquet(cached_paths["parquet_path"])
    else:
        sr = None

    md = load_market_data(as_of)
    curve = md.sofr_curve
    if shock_bps:
        curve = TermStructure(
            tenors=curve.tenors,
            rates=curve.rates + shock_bps / 10_000.0,
        )

    rp = generate_rate_paths(curve=curve, n_paths=n_paths, n_periods=n_periods, seed=42)
    if sr is None:
        try:
            write_rate_paths(as_of, shock_bps, n_paths, n_periods, 42,
                             rp.short_rates, save_parquet=save_parquet)
        except Exception:
            pass

    # ── Prepayment ────────────────────────────────────────────────────────
    prepay_ok = False
    if read_prepay(pool_id, as_of, shock_bps, n_paths) is None:
        try:
            cpr = project_prepay_speeds(pool=pool_chars, rate_paths=rp, model=PrepayModel())
            mean_cpr = np.mean(cpr, axis=0)
            annual = []
            for yr in range(1, 31):
                s, e = (yr - 1) * 12, yr * 12
                annual.append({
                    "year": yr,
                    "mean_cpr_pct": round(float(np.mean(mean_cpr[s:e])) * 100, 2),
                    "p10_cpr_pct":  round(float(np.mean(np.percentile(cpr[:, s:e], 10, axis=0))) * 100, 2),
                    "p90_cpr_pct":  round(float(np.mean(np.percentile(cpr[:, s:e], 90, axis=0))) * 100, 2),
                })
            lifetime = float(np.mean(cpr)) * 100.0
            peak_yr  = int(np.argmax([r["mean_cpr_pct"] for r in annual])) + 1
            prepay_result = {
                "lifetime_cpr_pct": round(lifetime, 2),
                "peak_cpr_year":    peak_yr,
                "annual_cpr":       annual,
                "wac_pct":          round(pool_chars.wac * 100, 3),
                "wala_months":      pool_chars.wala,
                "wam_months":       pool_chars.wam,
            }
            write_prepay(pool_id, as_of, shock_bps, n_paths, prepay_result)
            prepay_ok = True
        except Exception:
            pass
    else:
        prepay_ok = True  # already cached

    # ── Risk metrics ──────────────────────────────────────────────────────
    risk_ok = False
    if read_risk_metrics(pool_id, as_of, market_price, shock_bps, n_paths) is None:
        try:
            analytics = compute_analytics(
                pool_id=pool_id,
                pool_chars=pool_chars,
                market_price=market_price,
                settlement_date=as_of,
                rate_paths=rp,
                intex_client=MockIntexClient(),
                prepay_model=PrepayModel(),
            )
            risk_result = {
                "oas_bps":       analytics.oas,
                "z_spread_bps":  analytics.z_spread,
                "oad_years":     analytics.oad,
                "mod_duration":  analytics.mod_duration,
                "convexity":     analytics.convexity,
                "yield_pct":     analytics.yield_,
                "model_price":   analytics.model_price,
                "model_cpr_pct": analytics.model_cpr,
            }
            write_risk_metrics(pool_id, as_of, market_price, shock_bps, n_paths, risk_result)
            risk_ok = True
        except Exception:
            pass
    else:
        risk_ok = True

    # ── Interest income (base scenario only to limit run time) ────────────
    income_ok = False
    if shock_bps == 0:
        if read_interest_income(pool_id, as_of, 0, horizon_years) is None:
            try:
                financing_rate = float(md.sofr_curve.zero_rate(0.25))
                cpr2 = project_prepay_speeds(pool=pool_chars, rate_paths=rp, model=PrepayModel())
                cfs  = get_cash_flows(
                    pool_id=pool_id, cpr_vectors=cpr2,
                    settlement_date=as_of,
                    face_amount=pool_chars.current_balance,
                    intex_client=MockIntexClient(),
                )
                mean_int  = np.mean(cfs.interest, axis=0)
                mean_bal  = np.mean(cfs.balance,  axis=0)
                fwd_rates = np.mean(rp.short_rates, axis=0)
                financing_cost = mean_bal * fwd_rates * rp.dt
                n_p = min(horizon_years * 12, len(mean_int))
                annual_inc = []
                for yr in range(1, horizon_years + 1):
                    s, e = (yr - 1) * 12, min(yr * 12, n_p)
                    if s >= n_p:
                        break
                    gross = float(np.sum(mean_int[s:e]))
                    fin   = float(np.sum(financing_cost[s:e]))
                    avg_b = float(np.mean(mean_bal[s:e]))
                    nim   = (gross - fin) / avg_b * 12 / (e - s) * 100 if avg_b > 0 else 0.0
                    annual_inc.append({
                        "year": yr, "gross_interest": round(gross, 0),
                        "financing_cost": round(fin, 0),
                        "net_interest_income": round(gross - fin, 0),
                        "avg_balance": round(avg_b, 0),
                        "net_interest_margin_pct": round(nim, 4),
                    })
                inc_result = {
                    "total_gross_interest": round(float(np.sum(mean_int[:n_p])), 0),
                    "total_financing_cost": round(float(np.sum(financing_cost[:n_p])), 0),
                    "total_net_income":     round(
                        float(np.sum(mean_int[:n_p])) - float(np.sum(financing_cost[:n_p])), 0),
                    "annual": annual_inc,
                }
                write_interest_income(
                    pool_id, as_of, 0, horizon_years,
                    financing_rate * 100, inc_result,
                )
                income_ok = True
            except Exception:
                pass
        else:
            income_ok = True

    return {
        "prepay_ok": prepay_ok,
        "risk_ok":   risk_ok,
        "income_ok": income_ok,
        "elapsed_s": round(time.perf_counter() - t0, 2),
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()

    as_of = (
        date.fromisoformat(args.as_of_date) if args.as_of_date else date.today()
    )

    print("=" * 72)
    print("  Oasia — Cache Warm-Up")
    print(f"  As-of date  : {as_of}")
    print(f"  Shocks (bps): {args.shocks}")
    print(f"  n_paths     : {args.n_paths}")
    print(f"  Products    : {args.products}")
    print("=" * 72)

    # Initialise schema
    from db.connection import init_schema, cache_stats
    init_schema()
    print(f"\n[DB] Initialised. Current cache: {cache_stats()}")

    # Load universe
    from data.universe_1000 import get_universe_1000
    univ = get_universe_1000()
    univ = univ[univ["product_type"].isin(args.products)]
    if args.limit:
        univ = univ.head(args.limit)

    pool_ids  = univ["pool_id"].tolist()
    pool_map  = {row["pool_id"]: row for _, row in univ.iterrows()}
    total     = len(pool_ids)
    n_shocks  = len(args.shocks)

    # Skip already-cached pools if requested
    if args.skip_cached:
        from db.cache import query
        cached_set = set(
            r["pool_id"] for r in query(
                "SELECT DISTINCT pool_id FROM risk_metrics_cache WHERE shock_bps = 0"
            )
        )
        pool_ids = [p for p in pool_ids if p not in cached_set]
        print(f"[skip-cached] {total - len(pool_ids)} pools already cached, "
              f"{len(pool_ids)} remaining.\n")
        total = len(pool_ids)

    print(f"Processing {total} pools × {n_shocks} scenarios "
          f"= {total * n_shocks:,} compute tasks\n")

    # ── Process ───────────────────────────────────────────────────────────
    ok_count = err_count = 0
    t_start  = time.perf_counter()

    for i, pool_id in enumerate(pool_ids, 1):
        pool_row = pool_map[pool_id]
        pool_errs = 0

        for shock in args.shocks:
            try:
                res = _compute_pool(
                    pool_id, pool_row, shock, as_of,
                    args.n_paths, args.horizon_years, args.save_parquet,
                )
                if res["risk_ok"] and res["prepay_ok"]:
                    ok_count += 1
                else:
                    pool_errs += 1
                    err_count += 1
            except Exception:
                pool_errs += 1
                err_count += 1
                if "--verbose" in sys.argv:
                    traceback.print_exc()

        # Progress line every pool
        elapsed   = time.perf_counter() - t_start
        rate      = i / elapsed if elapsed > 0 else 0
        remaining = (total - i) / rate if rate > 0 else 0
        status    = "OK" if pool_errs == 0 else f"{pool_errs} ERR"
        print(
            f"  [{i:>4}/{total}] {pool_id:<30}  {status:<8}  "
            f"{elapsed:>6.0f}s elapsed  ~{remaining:>5.0f}s left",
            flush=True,
        )

    # ── Summary ───────────────────────────────────────────────────────────
    total_elapsed = time.perf_counter() - t_start
    print("\n" + "=" * 72)
    print(f"  Done in {total_elapsed:.0f}s")
    print(f"  Successful tasks : {ok_count:,}")
    print(f"  Errored tasks    : {err_count:,}")
    print(f"  Final cache      : {cache_stats()}")
    print("=" * 72)


if __name__ == "__main__":
    main()
