"""
DuckDB cache read/write helpers.

All reads and writes share the single connection from db.connection and are
serialised through its RLock.  This is safe for Gradio's threaded model.

Pattern
-------
    cached = read_risk_metrics(pool_id, as_of, price, shock, n_paths)
    if cached:
        return cached          # instant DB read
    result = expensive_compute(...)
    write_risk_metrics(...)    # persist for next time
    return result
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

import numpy as np

from db.connection import get_conn, PARQUET_DIR, _lock


# ── Utility ────────────────────────────────────────────────────────────────────

def _round_price(price: float) -> float:
    return round(float(price), 2)


def query(sql: str, params: list = None) -> list[dict]:
    """
    Execute an arbitrary read SQL statement and return list-of-dicts.
    Used by db_tool for ad-hoc agent queries.
    """
    with _lock:
        conn = get_conn()
        rel  = conn.execute(sql, params or [])
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, row)) for row in rel.fetchall()]


# ══════════════════════════════════════════════════════════════════════════════
# Rate-path cache
# ══════════════════════════════════════════════════════════════════════════════

def read_rate_paths(
    curve_date: date,
    shock_bps:  int,
    n_paths:    int,
    n_periods:  int,
    seed:       int,
) -> Optional[dict]:
    with _lock:
        conn = get_conn()
        row  = conn.execute("""
            SELECT mean_1yr,  std_1yr,  p10_1yr,  p90_1yr,
                   mean_3yr,  std_3yr,  p10_3yr,  p90_3yr,
                   mean_5yr,  std_5yr,  p10_5yr,  p90_5yr,
                   mean_10yr, std_10yr, p10_10yr, p90_10yr,
                   mean_20yr, std_20yr, p10_20yr, p90_20yr,
                   mean_30yr, std_30yr, p10_30yr, p90_30yr,
                   parquet_path, computed_at
            FROM   rate_path_cache
            WHERE  curve_date = ? AND shock_bps = ?
              AND  n_paths = ? AND n_periods = ? AND seed = ?
        """, [curve_date, shock_bps, n_paths, n_periods, seed]).fetchone()

    if row is None:
        return None

    labels = ["1yr", "3yr", "5yr", "10yr", "20yr", "30yr"]
    result: dict[str, Any] = {
        "n_paths": n_paths, "n_periods": n_periods,
        "shock_bps": shock_bps, "curve_date": str(curve_date),
        "dt_years": 1 / 12,
        "short_rate_at_key_horizons": {},
        "parquet_path": row[24],
        "computed_at":  str(row[25]),
        "_from_cache":  True,
    }
    for i, lbl in enumerate(labels):
        b = i * 4
        result["short_rate_at_key_horizons"][lbl] = {
            "mean_pct": round(row[b]   * 100, 3) if row[b]   is not None else None,
            "std_pct":  round(row[b+1] * 100, 3) if row[b+1] is not None else None,
            "p10_pct":  round(row[b+2] * 100, 3) if row[b+2] is not None else None,
            "p90_pct":  round(row[b+3] * 100, 3) if row[b+3] is not None else None,
        }
    return result


def write_rate_paths(
    curve_date:   date,
    shock_bps:    int,
    n_paths:      int,
    n_periods:    int,
    seed:         int,
    short_rates:  np.ndarray,   # (n_paths, n_periods)
    save_parquet: bool = True,
) -> None:
    key_months = [12, 36, 60, 120, 240, 360]
    stats: list = []
    for m in key_months:
        if m <= short_rates.shape[1]:
            col = short_rates[:, m - 1]
            stats += [float(np.mean(col)), float(np.std(col)),
                      float(np.percentile(col, 10)), float(np.percentile(col, 90))]
        else:
            stats += [None, None, None, None]

    parquet_rel: Optional[str] = None
    if save_parquet:
        try:
            import pandas as pd
            fname  = (f"paths_{curve_date.isoformat().replace('-','')}"
                      f"_shock{shock_bps}_n{n_paths}_s{seed}.parquet")
            fpath  = PARQUET_DIR / fname
            df     = pd.DataFrame(short_rates,
                                  columns=[f"p{t}" for t in range(short_rates.shape[1])])
            df["path_idx"] = np.arange(n_paths)
            df.to_parquet(str(fpath), index=False, compression="snappy")
            parquet_rel = fname
        except Exception:
            pass

    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO rate_path_cache
                (curve_date, shock_bps, n_paths, n_periods, seed,
                 mean_1yr,  std_1yr,  p10_1yr,  p90_1yr,
                 mean_3yr,  std_3yr,  p10_3yr,  p90_3yr,
                 mean_5yr,  std_5yr,  p10_5yr,  p90_5yr,
                 mean_10yr, std_10yr, p10_10yr, p90_10yr,
                 mean_20yr, std_20yr, p10_20yr, p90_20yr,
                 mean_30yr, std_30yr, p10_30yr, p90_30yr,
                 parquet_path)
            VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?, ?)
        """, [curve_date, shock_bps, n_paths, n_periods, seed, *stats, parquet_rel])
        conn.commit()


def load_rate_paths_from_parquet(parquet_fname: str) -> Optional[np.ndarray]:
    """Load (n_paths, n_periods) short-rate array from a saved Parquet file."""
    import pandas as pd
    fpath = PARQUET_DIR / parquet_fname
    if not fpath.exists():
        return None
    df = pd.read_parquet(str(fpath))
    df = df.drop(columns=["path_idx"], errors="ignore")
    return df.values.astype(np.float64)


# ══════════════════════════════════════════════════════════════════════════════
# Prepayment cache
# ══════════════════════════════════════════════════════════════════════════════

def read_prepay(
    pool_id:    str,
    as_of_date: date,
    shock_bps:  int,
    n_paths:    int,
) -> Optional[dict]:
    with _lock:
        conn = get_conn()
        row  = conn.execute("""
            SELECT lifetime_cpr_pct, yr1_cpr_pct, yr3_cpr_pct, yr5_cpr_pct,
                   yr10_cpr_pct, yr20_cpr_pct, yr30_cpr_pct, peak_cpr_year,
                   annual_cpr_json, wac_pct, wala_months, wam_months, computed_at
            FROM   prepay_cache
            WHERE  pool_id = ? AND as_of_date = ? AND shock_bps = ? AND n_paths = ?
        """, [pool_id, as_of_date, shock_bps, n_paths]).fetchone()

    if row is None:
        return None

    return {
        "pool_id":          pool_id,
        "wac_pct":          row[9],
        "wala_months":      row[10],
        "wam_months":       row[11],
        "shock_bps":        shock_bps,
        "n_paths":          n_paths,
        "lifetime_cpr_pct": row[0],
        "peak_cpr_year":    row[7],
        "annual_cpr":       json.loads(row[8]) if row[8] else [],
        "yr1_cpr_pct":      row[1],
        "yr3_cpr_pct":      row[2],
        "yr5_cpr_pct":      row[3],
        "yr10_cpr_pct":     row[4],
        "yr20_cpr_pct":     row[5],
        "yr30_cpr_pct":     row[6],
        "computed_at":      str(row[12]),
        "_from_cache":      True,
    }


def write_prepay(
    pool_id:    str,
    as_of_date: date,
    shock_bps:  int,
    n_paths:    int,
    result:     dict,
) -> None:
    annual   = result.get("annual_cpr", [])
    get_yr   = lambda y: next((r["mean_cpr_pct"] for r in annual if r["year"] == y), None)
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO prepay_cache
                (pool_id, as_of_date, shock_bps, n_paths,
                 lifetime_cpr_pct, yr1_cpr_pct, yr3_cpr_pct, yr5_cpr_pct,
                 yr10_cpr_pct, yr20_cpr_pct, yr30_cpr_pct, peak_cpr_year,
                 annual_cpr_json, wac_pct, wala_months, wam_months)
            VALUES (?,?,?,?, ?,?,?,?, ?,?,?,?, ?,?,?,?)
        """, [
            pool_id, as_of_date, shock_bps, n_paths,
            result.get("lifetime_cpr_pct"),
            get_yr(1), get_yr(3), get_yr(5),
            get_yr(10), get_yr(20), get_yr(30),
            result.get("peak_cpr_year"),
            json.dumps(annual),
            result.get("wac_pct"), result.get("wala_months"), result.get("wam_months"),
        ])
        conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# Risk metrics cache
# ══════════════════════════════════════════════════════════════════════════════

def read_risk_metrics(
    pool_id:      str,
    as_of_date:   date,
    market_price: float,
    shock_bps:    int,
    n_paths:      int,
) -> Optional[dict]:
    with _lock:
        conn = get_conn()
        row  = conn.execute("""
            SELECT oas_bps, z_spread_bps, oad_years, mod_duration,
                   convexity, yield_pct, model_price, model_cpr_pct, computed_at
            FROM   risk_metrics_cache
            WHERE  pool_id = ? AND as_of_date = ?
              AND  market_price_rounded = ? AND shock_bps = ? AND n_paths = ?
        """, [pool_id, as_of_date, _round_price(market_price), shock_bps, n_paths]).fetchone()

    if row is None:
        return None

    return {
        "pool_id":       pool_id,
        "market_price":  market_price,
        "oas_bps":       row[0],
        "z_spread_bps":  row[1],
        "oad_years":     row[2],
        "mod_duration":  row[3],
        "convexity":     row[4],
        "yield_pct":     row[5],
        "model_price":   row[6],
        "model_cpr_pct": row[7],
        "computed_at":   str(row[8]),
        "_from_cache":   True,
    }


def write_risk_metrics(
    pool_id:      str,
    as_of_date:   date,
    market_price: float,
    shock_bps:    int,
    n_paths:      int,
    result:       dict,
) -> None:
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO risk_metrics_cache
                (pool_id, as_of_date, market_price_rounded, shock_bps, n_paths,
                 oas_bps, z_spread_bps, oad_years, mod_duration,
                 convexity, yield_pct, model_price, model_cpr_pct)
            VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?)
        """, [
            pool_id, as_of_date, _round_price(market_price), shock_bps, n_paths,
            result.get("oas_bps"), result.get("z_spread_bps"),
            result.get("oad_years"), result.get("mod_duration"),
            result.get("convexity"), result.get("yield_pct"),
            result.get("model_price"), result.get("model_cpr_pct"),
        ])
        conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
# Interest income cache
# ══════════════════════════════════════════════════════════════════════════════

def read_interest_income(
    pool_id:       str,
    as_of_date:    date,
    shock_bps:     int,
    horizon_years: int,
) -> Optional[dict]:
    with _lock:
        conn = get_conn()
        row  = conn.execute("""
            SELECT total_gross_interest, total_financing_cost, total_net_income,
                   annual_json, financing_rate_pct, computed_at
            FROM   interest_income_cache
            WHERE  pool_id = ? AND as_of_date = ?
              AND  shock_bps = ? AND horizon_years = ?
        """, [pool_id, as_of_date, shock_bps, horizon_years]).fetchone()

    if row is None:
        return None

    return {
        "pool_id":               pool_id,
        "shock_bps":             shock_bps,
        "horizon_years":         horizon_years,
        "total_gross_interest":  row[0],
        "total_financing_cost":  row[1],
        "total_net_income":      row[2],
        "annual":                json.loads(row[3]) if row[3] else [],
        "financing_rate_pct":    row[4],
        "computed_at":           str(row[5]),
        "_from_cache":           True,
    }


def write_interest_income(
    pool_id:            str,
    as_of_date:         date,
    shock_bps:          int,
    horizon_years:      int,
    financing_rate_pct: float,
    result:             dict,
) -> None:
    with _lock:
        conn = get_conn()
        conn.execute("""
            INSERT OR REPLACE INTO interest_income_cache
                (pool_id, as_of_date, shock_bps, horizon_years, financing_rate_pct,
                 total_gross_interest, total_financing_cost, total_net_income, annual_json)
            VALUES (?,?,?,?,?, ?,?,?,?)
        """, [
            pool_id, as_of_date, shock_bps, horizon_years, financing_rate_pct,
            result.get("total_gross_interest"),
            result.get("total_financing_cost"),
            result.get("total_net_income"),
            json.dumps(result.get("annual", [])),
        ])
        conn.commit()
