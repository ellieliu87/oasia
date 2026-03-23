"""
DuckDB connection manager.

DuckDB 1.x supports only one connection per file at a time.  We use a single
persistent connection protected by a threading.RLock for both reads and writes.
This is safe for Gradio's multi-threaded model: each call acquires the lock,
executes the query, and releases.

Database file:  {project_root}/data/nexus_results.duckdb
Override:       set NEXUS_DB_PATH environment variable.

Parquet directory (full rate-path arrays):
              {data_dir}/rate_paths/
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

import duckdb

# ── Path resolution ────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH   = Path(os.getenv("NEXUS_DB_PATH",
                            str(_PROJECT_ROOT / "data" / "nexus_results.duckdb")))
PARQUET_DIR = DB_PATH.parent / "rate_paths"

# ── Single connection with re-entrant lock ─────────────────────────────────────
_lock: threading.RLock = threading.RLock()
_conn: Optional[duckdb.DuckDBPyConnection] = None


def get_conn(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """
    Return the shared DuckDB connection, initialising it on first call.

    The `read_only` parameter is accepted for API compatibility but ignored —
    DuckDB 1.x does not allow multiple simultaneous connections with different
    modes.  All callers share the same connection; use the _lock (or the
    write helpers in db.cache) to serialise access.
    """
    global _conn
    with _lock:
        if _conn is None:
            DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            PARQUET_DIR.mkdir(parents=True, exist_ok=True)
            _conn = duckdb.connect(str(DB_PATH))
            _apply_schema(_conn)
        return _conn


def init_schema() -> None:
    """Explicitly initialise the database schema (idempotent)."""
    with _lock:
        _apply_schema(get_conn())


def _apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Create all tables and views if they do not already exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rate_path_cache (
            curve_date   DATE    NOT NULL,
            shock_bps    INTEGER NOT NULL DEFAULT 0,
            n_paths      INTEGER NOT NULL,
            n_periods    INTEGER NOT NULL,
            seed         INTEGER NOT NULL,
            mean_1yr     FLOAT, std_1yr  FLOAT, p10_1yr  FLOAT, p90_1yr  FLOAT,
            mean_3yr     FLOAT, std_3yr  FLOAT, p10_3yr  FLOAT, p90_3yr  FLOAT,
            mean_5yr     FLOAT, std_5yr  FLOAT, p10_5yr  FLOAT, p90_5yr  FLOAT,
            mean_10yr    FLOAT, std_10yr FLOAT, p10_10yr FLOAT, p90_10yr FLOAT,
            mean_20yr    FLOAT, std_20yr FLOAT, p10_20yr FLOAT, p90_20yr FLOAT,
            mean_30yr    FLOAT, std_30yr FLOAT, p10_30yr FLOAT, p90_30yr FLOAT,
            parquet_path VARCHAR,
            computed_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (curve_date, shock_bps, n_paths, n_periods, seed)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS prepay_cache (
            pool_id          VARCHAR NOT NULL,
            as_of_date       DATE    NOT NULL,
            shock_bps        INTEGER NOT NULL DEFAULT 0,
            n_paths          INTEGER NOT NULL,
            lifetime_cpr_pct FLOAT,
            yr1_cpr_pct      FLOAT,
            yr3_cpr_pct      FLOAT,
            yr5_cpr_pct      FLOAT,
            yr10_cpr_pct     FLOAT,
            yr20_cpr_pct     FLOAT,
            yr30_cpr_pct     FLOAT,
            peak_cpr_year    INTEGER,
            annual_cpr_json  VARCHAR,
            wac_pct          FLOAT,
            wala_months      INTEGER,
            wam_months       INTEGER,
            computed_at      TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (pool_id, as_of_date, shock_bps, n_paths)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_metrics_cache (
            pool_id              VARCHAR NOT NULL,
            as_of_date           DATE    NOT NULL,
            market_price_rounded FLOAT   NOT NULL,
            shock_bps            INTEGER NOT NULL DEFAULT 0,
            n_paths              INTEGER NOT NULL,
            oas_bps              FLOAT,
            z_spread_bps         FLOAT,
            oad_years            FLOAT,
            mod_duration         FLOAT,
            convexity            FLOAT,
            yield_pct            FLOAT,
            model_price          FLOAT,
            model_cpr_pct        FLOAT,
            computed_at          TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (pool_id, as_of_date, market_price_rounded, shock_bps, n_paths)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS interest_income_cache (
            pool_id              VARCHAR NOT NULL,
            as_of_date           DATE    NOT NULL,
            shock_bps            INTEGER NOT NULL DEFAULT 0,
            horizon_years        INTEGER NOT NULL,
            financing_rate_pct   FLOAT,
            total_gross_interest FLOAT,
            total_financing_cost FLOAT,
            total_net_income     FLOAT,
            annual_json          VARCHAR,
            computed_at          TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (pool_id, as_of_date, shock_bps, horizon_years)
        )
    """)

    conn.execute("""
        CREATE OR REPLACE VIEW latest_risk_metrics AS
        SELECT r.*
        FROM risk_metrics_cache r
        INNER JOIN (
            SELECT pool_id, as_of_date, shock_bps, n_paths, MAX(computed_at) AS max_ts
            FROM   risk_metrics_cache
            GROUP  BY pool_id, as_of_date, shock_bps, n_paths
        ) t ON  r.pool_id    = t.pool_id
            AND r.as_of_date = t.as_of_date
            AND r.shock_bps  = t.shock_bps
            AND r.n_paths    = t.n_paths
            AND r.computed_at = t.max_ts
    """)

    conn.execute("""
        CREATE OR REPLACE VIEW latest_prepay AS
        SELECT p.*
        FROM prepay_cache p
        INNER JOIN (
            SELECT pool_id, as_of_date, shock_bps, n_paths, MAX(computed_at) AS max_ts
            FROM   prepay_cache
            GROUP  BY pool_id, as_of_date, shock_bps, n_paths
        ) t ON  p.pool_id    = t.pool_id
            AND p.as_of_date = t.as_of_date
            AND p.shock_bps  = t.shock_bps
            AND p.n_paths    = t.n_paths
            AND p.computed_at = t.max_ts
    """)

    conn.commit()


def cache_stats() -> dict:
    """Return row counts for every cache table."""
    with _lock:
        conn = get_conn()
        stats = {}
        for tbl in ["rate_path_cache", "prepay_cache",
                    "risk_metrics_cache", "interest_income_cache"]:
            try:
                n = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
                stats[tbl] = n
            except Exception:
                stats[tbl] = 0
        return stats
