"""
Backfill historical portfolio snapshots from CSV files.

Usage:
    python scripts/backfill_snapshots.py [--dir DIR] [--dry-run]

CSV files should be in MARKET_DATA_DIR/snapshots/ and named:
    snapshot_YYYYMMDD.csv

Expected CSV columns:
    pool_id, face_amount, book_price, market_price, coupon, wac,
    wala, wam, loan_size, ltv, fico, pct_ca, pct_purchase, product_type,
    oas, oad, convexity, book_yield, purchase_date

Snapshots are immutable: existing dates will be skipped (not overwritten).
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

# Add parent directory to path so we can import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("backfill_snapshots")


def _load_snapshot_csv(fpath: Path) -> tuple[datetime.date, pd.DataFrame]:
    """Load a snapshot CSV file and return (date, DataFrame)."""
    # Extract date from filename: snapshot_YYYYMMDD.csv
    stem = fpath.stem
    if not stem.startswith("snapshot_"):
        raise ValueError(f"Unexpected filename format: {fpath.name}")

    date_str = stem.replace("snapshot_", "")
    snapshot_date = datetime.strptime(date_str, "%Y%m%d").date()

    df = pd.read_csv(fpath)
    return snapshot_date, df


def _df_to_positions(df: pd.DataFrame) -> list[dict]:
    """Convert DataFrame rows to position dicts for SnapshotStore."""
    positions = []
    for _, row in df.iterrows():
        pos = {}
        for col in df.columns:
            val = row[col]
            # Convert NaN to None
            if pd.isna(val):
                val = None
            pos[col] = val
        positions.append(pos)
    return positions


def _generate_synthetic_snapshots(
    snapshot_dir: Path,
    start_date: datetime.date,
    end_date: datetime.date,
) -> list[Path]:
    """
    Generate synthetic snapshot CSV files for dates without existing files.

    Used for demo/testing when no historical snapshots are available.
    """
    import numpy as np
    from datetime import timedelta

    snapshot_dir.mkdir(parents=True, exist_ok=True)
    generated = []

    current = start_date
    month = 1
    while current <= end_date:
        fname = snapshot_dir / f"snapshot_{current.strftime('%Y%m%d')}.csv"
        if not fname.exists():
            # Generate synthetic portfolio for this date
            rng = np.random.default_rng(int(current.strftime('%Y%m%d')))

            # Three standard positions with slight variation over time
            positions = [
                {
                    "pool_id": "TEST-POOL-30YR",
                    "face_amount": 5_000_000,
                    "book_price": 101.5,
                    "market_price": round(102.0 + rng.uniform(-1.0, 1.0), 4),
                    "coupon": 0.06,
                    "wac": 0.065,
                    "wala": month,
                    "wam": 360 - month,
                    "loan_size": 400_000,
                    "ltv": 0.75,
                    "fico": 750,
                    "pct_ca": 0.15,
                    "pct_purchase": 0.65,
                    "product_type": "CC30",
                    "oas": round(54.0 + rng.uniform(-5, 5), 2),
                    "oad": round(4.52 - month * 0.01, 3),
                    "convexity": round(-0.74 + rng.uniform(-0.1, 0.1), 4),
                    "book_yield": round(0.0608 + rng.uniform(-0.001, 0.001), 6),
                    "purchase_date": "2024-06-01",
                },
                {
                    "pool_id": "TEST-POOL-15YR",
                    "face_amount": 3_000_000,
                    "book_price": 99.5,
                    "market_price": round(100.0 + rng.uniform(-0.5, 1.0), 4),
                    "coupon": 0.055,
                    "wac": 0.059,
                    "wala": month,
                    "wam": 180 - month,
                    "loan_size": 350_000,
                    "ltv": 0.70,
                    "fico": 760,
                    "pct_ca": 0.10,
                    "pct_purchase": 0.70,
                    "product_type": "CC15",
                    "oas": round(37.0 + rng.uniform(-4, 4), 2),
                    "oad": round(3.21 - month * 0.008, 3),
                    "convexity": round(-0.22 + rng.uniform(-0.05, 0.05), 4),
                    "book_yield": round(0.0562 + rng.uniform(-0.001, 0.001), 6),
                    "purchase_date": "2024-09-15",
                },
                {
                    "pool_id": "TEST-POOL-GN30",
                    "face_amount": 4_000_000,
                    "book_price": 103.0,
                    "market_price": round(103.5 + rng.uniform(-1.0, 1.0), 4),
                    "coupon": 0.065,
                    "wac": 0.07,
                    "wala": 24 + month,
                    "wam": 360 - 24 - month,
                    "loan_size": 350_000,
                    "ltv": 0.90,
                    "fico": 700,
                    "pct_ca": 0.10,
                    "pct_purchase": 0.60,
                    "product_type": "GN30",
                    "oas": round(58.0 + rng.uniform(-5, 5), 2),
                    "oad": round(4.18 - month * 0.01, 3),
                    "convexity": round(-1.12 + rng.uniform(-0.1, 0.1), 4),
                    "book_yield": round(0.0631 + rng.uniform(-0.001, 0.001), 6),
                    "purchase_date": "2023-12-01",
                },
            ]

            df = pd.DataFrame(positions)
            df.to_csv(fname, index=False)
            generated.append(fname)
            logger.info("Generated synthetic snapshot: %s", fname.name)

        # Advance by approximately 1 month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1, day=1)
        else:
            current = current.replace(month=current.month + 1)
        month += 1

    return generated


def backfill_snapshots(
    snapshots_dir: str,
    db_path: str,
    dry_run: bool = False,
    generate_synthetic: bool = False,
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """
    Load all snapshot CSVs from directory and save to SnapshotStore.

    Parameters
    ----------
    snapshots_dir : str
        Directory containing snapshot_YYYYMMDD.csv files.
    db_path : str
        Path to SQLite database.
    dry_run : bool
        If True, scan but don't write to database.
    generate_synthetic : bool
        If True and no CSV files found, generate synthetic test data.
    start_date : str
        Start date for synthetic generation (YYYY-MM-DD).
    end_date : str
        End date for synthetic generation (YYYY-MM-DD).

    Returns
    -------
    dict
        Summary: {loaded, skipped, errors, total_positions}
    """
    from data.snapshot_store import SnapshotStore

    snap_dir = Path(snapshots_dir)
    snap_dir.mkdir(parents=True, exist_ok=True)

    # Find existing snapshot CSVs
    csv_files = sorted(snap_dir.glob("snapshot_*.csv"))

    if not csv_files and generate_synthetic:
        logger.info("No snapshot CSVs found. Generating synthetic data...")
        s_date = datetime.strptime(start_date or "2025-01-01", "%Y-%m-%d").date()
        e_date = datetime.strptime(end_date or "2025-03-01", "%Y-%m-%d").date()
        _generate_synthetic_snapshots(snap_dir, s_date, e_date)
        csv_files = sorted(snap_dir.glob("snapshot_*.csv"))

    if not csv_files:
        logger.warning("No snapshot CSV files found in %s", snap_dir)
        return {"loaded": 0, "skipped": 0, "errors": 0, "total_positions": 0}

    logger.info("Found %d snapshot files in %s", len(csv_files), snap_dir)

    if dry_run:
        logger.info("DRY RUN — no data will be written to database")

    store = SnapshotStore(db_path) if not dry_run else None
    existing_dates = set(store.list_snapshot_dates()) if store else set()

    stats = {"loaded": 0, "skipped": 0, "errors": 0, "total_positions": 0}

    for fpath in csv_files:
        try:
            snapshot_date, df = _load_snapshot_csv(fpath)

            if snapshot_date in existing_dates:
                logger.info("SKIP %s — snapshot already exists", snapshot_date)
                stats["skipped"] += 1
                continue

            positions = _df_to_positions(df)

            if dry_run:
                logger.info("DRY RUN: would load %s with %d positions", snapshot_date, len(positions))
            else:
                store.save_snapshot(snapshot_date, positions)
                existing_dates.add(snapshot_date)
                logger.info("Loaded %s — %d positions", snapshot_date, len(positions))

            stats["loaded"] += 1
            stats["total_positions"] += len(positions)

        except ValueError as e:
            logger.warning("SKIP %s — %s", fpath.name, e)
            stats["errors"] += 1
        except Exception as e:
            logger.error("ERROR loading %s: %s", fpath.name, e)
            stats["errors"] += 1

    logger.info(
        "Backfill complete: loaded=%d, skipped=%d, errors=%d, total_positions=%d",
        stats["loaded"], stats["skipped"], stats["errors"], stats["total_positions"],
    )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill portfolio snapshots from CSV files into the database."
    )
    parser.add_argument(
        "--dir",
        default=None,
        help="Directory containing snapshot CSV files (default: MARKET_DATA_DIR/snapshots/)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite database path (default: Config.SNAPSHOT_DB_PATH)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scan files without writing to database.",
    )
    parser.add_argument(
        "--generate-synthetic",
        action="store_true",
        help="Generate synthetic test data if no CSV files are found.",
    )
    parser.add_argument(
        "--start-date",
        default="2025-01-01",
        help="Start date for synthetic generation (YYYY-MM-DD). Default: 2025-01-01",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="End date for synthetic generation (YYYY-MM-DD). Default: today",
    )

    args = parser.parse_args()

    try:
        from config import Config
        snapshots_dir = args.dir or str(Path(Config.MARKET_DATA_DIR) / "snapshots")
        db_path = args.db or Config.SNAPSHOT_DB_PATH
    except Exception:
        snapshots_dir = args.dir or "./data/market_data/snapshots"
        db_path = args.db or "./data/snapshots.db"

    end_date = args.end_date
    if end_date is None:
        from datetime import date
        end_date = date.today().strftime("%Y-%m-%d")

    stats = backfill_snapshots(
        snapshots_dir=snapshots_dir,
        db_path=db_path,
        dry_run=args.dry_run,
        generate_synthetic=args.generate_synthetic,
        start_date=args.start_date,
        end_date=end_date,
    )

    sys.exit(0 if stats["errors"] == 0 else 1)


if __name__ == "__main__":
    main()
