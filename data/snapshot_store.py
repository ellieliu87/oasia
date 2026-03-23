"""
SQLite-backed snapshot store for portfolio positions.

Snapshots are immutable: once saved for a date, they cannot be overwritten.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_SNAPSHOTS_TABLE = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date TEXT NOT NULL,
    pool_id TEXT NOT NULL,
    face_amount REAL NOT NULL,
    book_price REAL NOT NULL,
    market_price REAL,
    coupon REAL,
    wac REAL,
    wala INTEGER,
    wam INTEGER,
    loan_size REAL,
    ltv REAL,
    fico INTEGER,
    pct_ca REAL,
    pct_purchase REAL,
    product_type TEXT,
    oas REAL,
    oad REAL,
    convexity REAL,
    book_yield REAL,
    purchase_date TEXT,
    extra_data TEXT,
    PRIMARY KEY (snapshot_date, pool_id)
);
"""

_CREATE_DATES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_snapshot_date ON snapshots (snapshot_date);
"""


# ---------------------------------------------------------------------------
# SnapshotStore
# ---------------------------------------------------------------------------

class SnapshotStore:
    """
    Immutable SQLite-backed snapshot store.

    Each snapshot represents the full portfolio state at a given date.
    Once a snapshot is saved for a date, it cannot be overwritten.
    """

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._get_conn() as conn:
            conn.execute(_CREATE_SNAPSHOTS_TABLE)
            conn.execute(_CREATE_DATES_INDEX)
            conn.commit()

    def save_snapshot(self, snapshot_date: date, positions: list[dict]) -> None:
        """
        Save portfolio snapshot for a date.

        Parameters
        ----------
        snapshot_date : date
            The snapshot date.
        positions : list[dict]
            List of position dictionaries. Required keys: pool_id, face_amount, book_price.

        Raises
        ------
        ValueError
            If a snapshot already exists for this date.
        """
        date_str = snapshot_date.isoformat()

        with self._get_conn() as conn:
            # Check if snapshot already exists
            existing = conn.execute(
                "SELECT COUNT(*) FROM snapshots WHERE snapshot_date = ?",
                (date_str,)
            ).fetchone()[0]
            if existing > 0:
                raise ValueError(
                    f"Snapshot for {snapshot_date} already exists. "
                    "Snapshots are immutable once created."
                )

            # Insert all positions
            for pos in positions:
                # Extract known fields, store remainder in extra_data JSON
                known_keys = {
                    "pool_id", "face_amount", "book_price", "market_price",
                    "coupon", "wac", "wala", "wam", "loan_size", "ltv",
                    "fico", "pct_ca", "pct_purchase", "product_type",
                    "oas", "oad", "convexity", "book_yield", "purchase_date",
                }
                extra = {k: v for k, v in pos.items() if k not in known_keys}

                conn.execute(
                    """
                    INSERT INTO snapshots (
                        snapshot_date, pool_id, face_amount, book_price,
                        market_price, coupon, wac, wala, wam, loan_size,
                        ltv, fico, pct_ca, pct_purchase, product_type,
                        oas, oad, convexity, book_yield, purchase_date, extra_data
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        date_str,
                        pos.get("pool_id", ""),
                        pos.get("face_amount", 0.0),
                        pos.get("book_price", 100.0),
                        pos.get("market_price"),
                        pos.get("coupon"),
                        pos.get("wac"),
                        pos.get("wala"),
                        pos.get("wam"),
                        pos.get("loan_size"),
                        pos.get("ltv"),
                        pos.get("fico"),
                        pos.get("pct_ca"),
                        pos.get("pct_purchase"),
                        pos.get("product_type"),
                        pos.get("oas"),
                        pos.get("oad"),
                        pos.get("convexity"),
                        pos.get("book_yield"),
                        pos.get("purchase_date"),
                        json.dumps(extra) if extra else None,
                    ),
                )
            conn.commit()

    def get_snapshot(self, snapshot_date: date) -> pd.DataFrame:
        """
        Retrieve all positions for a snapshot date.

        Parameters
        ----------
        snapshot_date : date

        Returns
        -------
        pd.DataFrame
            DataFrame with all positions. Empty DataFrame if not found.
        """
        date_str = snapshot_date.isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots WHERE snapshot_date = ? ORDER BY pool_id",
                (date_str,),
            ).fetchall()

        if not rows:
            return pd.DataFrame()

        records = [dict(row) for row in rows]
        df = pd.DataFrame(records)

        # Parse dates
        if "snapshot_date" in df.columns:
            df["snapshot_date"] = pd.to_datetime(df["snapshot_date"]).dt.date
        if "purchase_date" in df.columns:
            df["purchase_date"] = pd.to_datetime(df["purchase_date"], errors="coerce").dt.date

        # Expand extra_data JSON columns
        if "extra_data" in df.columns:
            def expand_extra(row):
                if row and isinstance(row, str):
                    try:
                        return json.loads(row)
                    except Exception:
                        pass
                return {}
            extra_expanded = df["extra_data"].apply(expand_extra)
            extra_df = pd.DataFrame(list(extra_expanded))
            if not extra_df.empty:
                df = pd.concat([df.drop(columns=["extra_data"]), extra_df], axis=1)
            else:
                df = df.drop(columns=["extra_data"])

        return df

    def list_snapshot_dates(self) -> list[date]:
        """Return sorted list of all available snapshot dates."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT snapshot_date FROM snapshots ORDER BY snapshot_date"
            ).fetchall()
        return [datetime.strptime(row[0], "%Y-%m-%d").date() for row in rows]

    def get_snapshot_range(self, start: date, end: date) -> dict[date, pd.DataFrame]:
        """
        Retrieve all snapshots between start and end dates (inclusive).

        Parameters
        ----------
        start : date
        end : date

        Returns
        -------
        dict[date, pd.DataFrame]
        """
        start_str = start.isoformat()
        end_str = end.isoformat()

        with self._get_conn() as conn:
            date_rows = conn.execute(
                """
                SELECT DISTINCT snapshot_date FROM snapshots
                WHERE snapshot_date BETWEEN ? AND ?
                ORDER BY snapshot_date
                """,
                (start_str, end_str),
            ).fetchall()

        result = {}
        for row in date_rows:
            d = datetime.strptime(row[0], "%Y-%m-%d").date()
            result[d] = self.get_snapshot(d)

        return result

    def delete_snapshot(self, snapshot_date: date) -> None:
        """
        Delete a snapshot (admin operation, use with caution).

        This breaks the immutability guarantee and should only be used
        for data corrections.
        """
        date_str = snapshot_date.isoformat()
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM snapshots WHERE snapshot_date = ?",
                (date_str,),
            )
            conn.commit()
