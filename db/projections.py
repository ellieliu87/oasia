"""
db/projections.py

DuckDB read/write helpers for 30-year portfolio and pool-level projections.
Tables are created lazily on first write/read.
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger("nexus.db.projections")

_PORTFOLIO_DDL = """
CREATE TABLE IF NOT EXISTS portfolio_projections (
    run_date           DATE    NOT NULL,
    month_offset       INTEGER NOT NULL,
    projection_date    DATE    NOT NULL,
    portfolio_nav      DOUBLE,
    interest_income    DOUBLE,
    principal_cashflow DOUBLE,
    total_cashflow     DOUBLE,
    book_yield         DOUBLE,
    oad                DOUBLE,
    oas                DOUBLE,
    PRIMARY KEY (run_date, month_offset)
)
"""

_POOL_DDL = """
CREATE TABLE IF NOT EXISTS pool_projections (
    run_date           DATE    NOT NULL,
    pool_id            VARCHAR NOT NULL,
    month_offset       INTEGER NOT NULL,
    projection_date    DATE    NOT NULL,
    balance            DOUBLE,
    interest_income    DOUBLE,
    principal_cashflow DOUBLE,
    cpr                DOUBLE,
    PRIMARY KEY (run_date, pool_id, month_offset)
)
"""


def _ensure_tables() -> None:
    from db.connection import get_conn, _lock
    with _lock:
        conn = get_conn()
        conn.execute(_PORTFOLIO_DDL)
        conn.execute(_POOL_DDL)


def write_portfolio_projections(rows: list[dict]) -> None:
    if not rows:
        return
    _ensure_tables()
    import pandas as pd
    from db.connection import get_conn, _lock
    df = pd.DataFrame(rows)
    run_date = df["run_date"].iloc[0]
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM portfolio_projections WHERE run_date = ?", [run_date])
        conn.execute("INSERT INTO portfolio_projections SELECT * FROM df")
    logger.debug("Wrote %d portfolio projection rows for %s", len(df), run_date)


def write_pool_projections(rows: list[dict]) -> None:
    if not rows:
        return
    _ensure_tables()
    import pandas as pd
    from db.connection import get_conn, _lock
    df = pd.DataFrame(rows)
    run_date = df["run_date"].iloc[0]
    with _lock:
        conn = get_conn()
        conn.execute("DELETE FROM pool_projections WHERE run_date = ?", [run_date])
        conn.execute("INSERT INTO pool_projections SELECT * FROM df")
    logger.debug("Wrote %d pool projection rows for %s", len(df), run_date)


def get_portfolio_projections(
    run_date: date | None = None,
    n_months: int = 36,
) -> list[dict]:
    """Return portfolio-level projections for the next n_months months."""
    try:
        _ensure_tables()
        from db.cache import query
        if run_date is None:
            sql = """
                SELECT * FROM portfolio_projections
                WHERE run_date = (SELECT MAX(run_date) FROM portfolio_projections)
                  AND month_offset <= ?
                ORDER BY month_offset
            """
            return query(sql, [n_months])
        else:
            sql = """
                SELECT * FROM portfolio_projections
                WHERE run_date = ? AND month_offset <= ?
                ORDER BY month_offset
            """
            return query(sql, [run_date, n_months])
    except Exception:
        return []


def get_latest_portfolio_kpis() -> dict | None:
    """Return KPI snapshot for the latest projection run (month_offset=1)."""
    try:
        _ensure_tables()
        from db.cache import query
        rows = query("""
            SELECT * FROM portfolio_projections
            WHERE run_date = (SELECT MAX(run_date) FROM portfolio_projections)
              AND month_offset = 1
            LIMIT 1
        """)
        return rows[0] if rows else None
    except Exception:
        return None


def list_projection_run_dates() -> list[str]:
    """Return distinct run dates that have projection data, newest first."""
    try:
        _ensure_tables()
        from db.cache import query
        rows = query("""
            SELECT DISTINCT CAST(run_date AS VARCHAR) AS d
            FROM portfolio_projections
            ORDER BY d DESC LIMIT 30
        """)
        return [r["d"] for r in rows]
    except Exception:
        return []
