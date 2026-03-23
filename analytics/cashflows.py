"""
Cash flow projection for MBS pools.

Wraps Intex API (or MockIntexClient) with diskcache for performance.
"""
from __future__ import annotations

import hashlib
import os
from datetime import date
from pathlib import Path

import numpy as np

from data.intex_client import CashFlows, get_intex_client


def _hash_cpr_vectors(cpr_vectors: np.ndarray) -> str:
    """Create a stable hash for cache keying."""
    return hashlib.md5(cpr_vectors.tobytes()).hexdigest()[:16]


def get_cash_flows(
    pool_id: str,
    cpr_vectors: np.ndarray,
    settlement_date: date,
    face_amount: float = 1_000_000,
    intex_client=None,
    cache_dir: str = None,
) -> CashFlows:
    """
    Retrieve or compute cash flows for an MBS pool.

    Uses diskcache with 1-day TTL to avoid redundant computations.

    Parameters
    ----------
    pool_id : str
        Pool identifier.
    cpr_vectors : np.ndarray
        CPR vectors of shape (n_paths, n_periods).
    settlement_date : date
        Settlement date for the pool.
    face_amount : float
        Face amount in dollars.
    intex_client : IntexClient, optional
        Client to use. If None, uses default (MockIntexClient if no API key).
    cache_dir : str, optional
        Directory for disk cache. Defaults to Config.CACHE_DIR.

    Returns
    -------
    CashFlows
    """
    # Set up disk cache
    if cache_dir is None:
        try:
            from config import Config
            cache_dir = Config.CACHE_DIR
        except Exception:
            cache_dir = "./data/cache"

    import diskcache
    cache = diskcache.Cache(str(Path(cache_dir) / "cashflows"), disk=diskcache.Disk)

    # Build cache key
    cache_key = (
        f"cf:{pool_id}:{settlement_date.isoformat()}:"
        f"{face_amount:.2f}:{_hash_cpr_vectors(cpr_vectors)}"
    )

    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    # Get client
    if intex_client is None:
        intex_client = get_intex_client(cache_dir=cache_dir)

    # Fetch cash flows
    result = intex_client.get_cash_flows(
        pool_id=pool_id,
        cpr_vectors=cpr_vectors,
        settlement_date=settlement_date,
        face_amount=face_amount,
    )

    # Cache for 1 day (86400 seconds)
    cache.set(cache_key, result, expire=86400)

    return result
