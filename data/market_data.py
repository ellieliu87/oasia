"""
Market data loading and management.

Provides term structures (SOFR, Treasury) and cohort OAS levels.
Falls back to synthetic data if no CSV files are found.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from analytics.rate_paths import TermStructure


# ---------------------------------------------------------------------------
# Synthetic fallback data
# ---------------------------------------------------------------------------

# Standard tenors used throughout the system
_STANDARD_TENORS = np.array([0.083, 0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20, 30])

# Synthetic SOFR curve (approximately 2025 market levels)
_SYNTHETIC_SOFR_RATES = np.array([
    0.0430,  # 1M
    0.0435,  # 3M
    0.0440,  # 6M
    0.0445,  # 1Y
    0.0455,  # 2Y
    0.0460,  # 3Y
    0.0465,  # 5Y
    0.0468,  # 7Y
    0.0470,  # 10Y
    0.0475,  # 15Y
    0.0478,  # 20Y
    0.0480,  # 30Y
])

# Synthetic Treasury curve
_SYNTHETIC_TREASURY_RATES = np.array([
    0.0420,  # 1M
    0.0425,  # 3M
    0.0430,  # 6M
    0.0435,  # 1Y
    0.0445,  # 2Y
    0.0450,  # 3Y
    0.0455,  # 5Y
    0.0458,  # 7Y
    0.0460,  # 10Y
    0.0465,  # 15Y
    0.0468,  # 20Y
    0.0470,  # 30Y
])

# Cohort OAS by product and coupon bucket (bps)
_SYNTHETIC_COHORT_OAS = {
    # Conventional 30yr
    "CC30_4.0": 42,
    "CC30_4.5": 45,
    "CC30_5.0": 48,
    "CC30_5.5": 52,
    "CC30_6.0": 55,
    "CC30_6.5": 60,
    "CC30_7.0": 65,
    # Conventional 15yr
    "CC15_4.0": 28,
    "CC15_4.5": 30,
    "CC15_5.0": 33,
    "CC15_5.5": 36,
    "CC15_6.0": 38,
    "CC15_6.5": 42,
    # Ginnie Mae 30yr
    "GN30_4.0": 38,
    "GN30_4.5": 40,
    "GN30_5.0": 43,
    "GN30_5.5": 47,
    "GN30_6.0": 50,
    "GN30_6.5": 55,
    "GN30_7.0": 60,
    # Ginnie Mae 15yr
    "GN15_4.0": 25,
    "GN15_4.5": 27,
    "GN15_5.0": 30,
    "GN15_5.5": 32,
    "GN15_6.0": 35,
    "GN15_6.5": 38,
}


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class TermStructureData:
    """Market data snapshot for a single date."""
    as_of_date: date
    sofr_curve: TermStructure
    treasury_curve: TermStructure
    cohort_oas: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Load from CSV
# ---------------------------------------------------------------------------

def _load_from_csv(as_of_date: date, data_dir: str) -> Optional[TermStructureData]:
    """Try to load market data from CSV for a specific date."""
    # Try exact date file
    fname = f"market_data_{as_of_date.strftime('%Y%m%d')}.csv"
    fpath = Path(data_dir) / fname
    if not fpath.exists():
        return None

    try:
        df = pd.read_csv(fpath)
        if "tenor_years" not in df.columns:
            return None

        tenors = df["tenor_years"].values.astype(float)
        sofr_rates = df["sofr_rate"].values.astype(float) if "sofr_rate" in df.columns else _SYNTHETIC_SOFR_RATES
        treasury_rates = df["treasury_rate"].values.astype(float) if "treasury_rate" in df.columns else _SYNTHETIC_TREASURY_RATES

        cohort_oas = _SYNTHETIC_COHORT_OAS.copy()
        # Load cohort OAS columns if present
        for col in df.columns:
            if col.startswith(("CC30_", "CC15_", "GN30_", "GN15_")):
                cohort_oas[col] = float(df[col].iloc[0])

        return TermStructureData(
            as_of_date=as_of_date,
            sofr_curve=TermStructure(tenors=tenors, rates=sofr_rates),
            treasury_curve=TermStructure(tenors=tenors, rates=treasury_rates),
            cohort_oas=cohort_oas,
        )
    except Exception:
        return None


def _find_latest_csv(data_dir: str) -> Optional[date]:
    """Find the most recent market data CSV file."""
    data_path = Path(data_dir)
    if not data_path.exists():
        return None

    latest_date = None
    for f in data_path.glob("market_data_*.csv"):
        try:
            date_str = f.stem.replace("market_data_", "")
            d = datetime.strptime(date_str, "%Y%m%d").date()
            if latest_date is None or d > latest_date:
                latest_date = d
        except ValueError:
            continue
    return latest_date


def _synthetic_market_data(as_of_date: date) -> TermStructureData:
    """Return synthetic market data when no CSV files are available."""
    return TermStructureData(
        as_of_date=as_of_date,
        sofr_curve=TermStructure(
            tenors=_STANDARD_TENORS.copy(),
            rates=_SYNTHETIC_SOFR_RATES.copy(),
        ),
        treasury_curve=TermStructure(
            tenors=_STANDARD_TENORS.copy(),
            rates=_SYNTHETIC_TREASURY_RATES.copy(),
        ),
        cohort_oas=_SYNTHETIC_COHORT_OAS.copy(),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_market_data(as_of_date: date = None, data_dir: str = None) -> TermStructureData:
    """
    Load market data for a specific date.

    Tries to load from CSV files in data_dir. Falls back to synthetic data
    if no file is found.

    Parameters
    ----------
    as_of_date : date, optional
        Date to load data for. Defaults to today.
    data_dir : str, optional
        Directory containing market data CSV files. Defaults to Config.MARKET_DATA_DIR.

    Returns
    -------
    TermStructureData
    """
    if as_of_date is None:
        as_of_date = date.today()

    if data_dir is None:
        try:
            from config import Config
            data_dir = Config.MARKET_DATA_DIR
        except Exception:
            data_dir = "./data/market_data/"

    # Try to load from CSV
    result = _load_from_csv(as_of_date, data_dir)
    if result is not None:
        return result

    # Fall back to synthetic data
    return _synthetic_market_data(as_of_date)


def get_current_market_data() -> TermStructureData:
    """
    Returns the latest available market data.

    Looks for the most recent CSV file in MARKET_DATA_DIR. Falls back to
    synthetic data if no files are found.
    """
    try:
        from config import Config
        data_dir = Config.MARKET_DATA_DIR
    except Exception:
        data_dir = "./data/market_data/"

    latest = _find_latest_csv(data_dir)
    if latest is not None:
        result = _load_from_csv(latest, data_dir)
        if result is not None:
            return result

    # Fall back to synthetic data with today's date
    return _synthetic_market_data(date.today())


def get_cohort_oas_key(product_type: str, coupon: float) -> str:
    """Build cohort OAS lookup key from product type and coupon."""
    coupon_pct = round(coupon * 100 * 2) / 2  # round to nearest 0.5
    return f"{product_type}_{coupon_pct:.1f}"
