"""
Intex API client with mock support for testing.

Provides:
- CashFlows dataclass
- IntexClient: real API wrapper with disk-cache
- MockIntexClient: deterministic synthetic cash flows for testing
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# CashFlows dataclass
# ---------------------------------------------------------------------------

@dataclass
class CashFlows:
    """Monthly cash flows for an MBS pool."""
    scheduled_principal: np.ndarray  # (n_paths, n_periods)
    prepaid_principal: np.ndarray    # (n_paths, n_periods)
    interest: np.ndarray             # (n_paths, n_periods)
    balance: np.ndarray              # (n_paths, n_periods)

    @property
    def total_principal(self) -> np.ndarray:
        return self.scheduled_principal + self.prepaid_principal

    @property
    def total_cash_flow(self) -> np.ndarray:
        return self.total_principal + self.interest

    @property
    def n_paths(self) -> int:
        return self.scheduled_principal.shape[0]

    @property
    def n_periods(self) -> int:
        return self.scheduled_principal.shape[1]


# ---------------------------------------------------------------------------
# Pool specs for mock client
# ---------------------------------------------------------------------------

_MOCK_POOL_SPECS = {
    "TEST-POOL-30YR": {
        "wac": 0.06,
        "wam": 360,
        "wala": 0,
        "coupon": 0.06,
        "product_type": "CC30",
    },
    "TEST-POOL-15YR": {
        "wac": 0.055,
        "wam": 180,
        "wala": 0,
        "coupon": 0.055,
        "product_type": "CC15",
    },
    "TEST-POOL-GN30": {
        "wac": 0.065,
        "wam": 360,
        "wala": 0,
        "coupon": 0.065,
        "product_type": "GN30",
    },
}


def _hash_cpr_vectors(cpr_vectors: np.ndarray) -> str:
    """Create a stable hash for cache keying."""
    return hashlib.md5(cpr_vectors.tobytes()).hexdigest()[:12]


def _generate_mortgage_cashflows(
    wac: float,
    wam: int,
    cpr_vectors: np.ndarray,
    face_amount: float,
) -> CashFlows:
    """
    Generate standard mortgage cash flows for a pool.

    Parameters
    ----------
    wac : float
        Weighted average coupon (annual, decimal).
    wam : int
        Weighted average maturity in months.
    cpr_vectors : np.ndarray
        CPR array of shape (n_paths, n_periods).
    face_amount : float
        Original face amount ($).

    Returns
    -------
    CashFlows
        Standard mortgage cash flows.
    """
    n_paths, n_periods = cpr_vectors.shape
    actual_periods = min(wam, n_periods)

    # Monthly rate
    r = wac / 12.0

    # Initialize output arrays
    scheduled_principal = np.zeros((n_paths, n_periods))
    prepaid_principal = np.zeros((n_paths, n_periods))
    interest_arr = np.zeros((n_paths, n_periods))
    balance_arr = np.zeros((n_paths, n_periods))

    # Balance starts at face_amount for all paths
    balance = np.full(n_paths, face_amount)

    for t in range(actual_periods):
        # Remaining term at this period
        n_remaining = wam - t

        # Monthly payment (level-pay formula): P * r / (1 - (1+r)^-n)
        if n_remaining <= 0:
            scheduled_p = balance.copy()
            interest_t = np.zeros(n_paths)
            prepay_t = np.zeros(n_paths)
        else:
            if r > 0:
                factor = (1 + r) ** n_remaining
                monthly_payment = balance * r * factor / (factor - 1.0)
            else:
                monthly_payment = balance / n_remaining

            # Interest this period
            interest_t = balance * r

            # Scheduled principal
            scheduled_p = monthly_payment - interest_t
            scheduled_p = np.minimum(scheduled_p, balance)  # can't exceed balance
            scheduled_p = np.maximum(scheduled_p, 0.0)

        # Balance after scheduled payment
        balance_after_sched = balance - scheduled_p

        # Prepayment: SMM = 1 - (1 - CPR)^(1/12)
        cpr_t = cpr_vectors[:, t]
        smm = 1.0 - (1.0 - np.clip(cpr_t, 0.0, 0.99)) ** (1.0 / 12.0)
        prepay_t = balance_after_sched * smm
        prepay_t = np.minimum(prepay_t, balance_after_sched)
        prepay_t = np.maximum(prepay_t, 0.0)

        # Record
        balance_arr[:, t] = balance.copy()
        interest_arr[:, t] = interest_t
        scheduled_principal[:, t] = scheduled_p
        prepaid_principal[:, t] = prepay_t

        # Update balance
        balance = balance_after_sched - prepay_t
        balance = np.maximum(balance, 0.0)

    return CashFlows(
        scheduled_principal=scheduled_principal,
        prepaid_principal=prepaid_principal,
        interest=interest_arr,
        balance=balance_arr,
    )


# ---------------------------------------------------------------------------
# IntexClient
# ---------------------------------------------------------------------------

class IntexClient:
    """
    Wrapper for the Intex API.

    Caches responses using diskcache.
    """

    def __init__(self, api_url: str, api_key: str, cache_dir: str):
        import diskcache
        import pathlib
        self.api_url = api_url
        self.api_key = api_key
        self._cache = diskcache.Cache(str(pathlib.Path(cache_dir) / "intex"))

    def get_pool_details(self, pool_id: str) -> dict:
        """Fetch pool details from Intex API."""
        cache_key = f"pool_details:{pool_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        import requests
        resp = requests.get(
            f"{self.api_url}/pools/{pool_id}",
            headers={"X-API-Key": self.api_key},
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        self._cache.set(cache_key, result, expire=86400)
        return result

    def get_cash_flows(
        self,
        pool_id: str,
        cpr_vectors: np.ndarray,
        settlement_date: date,
        face_amount: float = 1_000_000,
    ) -> CashFlows:
        """Fetch cash flows from Intex API."""
        cache_key = f"cf:{pool_id}:{settlement_date}:{_hash_cpr_vectors(cpr_vectors)}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        import requests
        payload = {
            "pool_id": pool_id,
            "settlement_date": settlement_date.isoformat(),
            "face_amount": face_amount,
            "cpr_vectors": cpr_vectors.tolist(),
        }
        resp = requests.post(
            f"{self.api_url}/cashflows",
            headers={"X-API-Key": self.api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        result = CashFlows(
            scheduled_principal=np.array(data["scheduled_principal"]),
            prepaid_principal=np.array(data["prepaid_principal"]),
            interest=np.array(data["interest"]),
            balance=np.array(data["balance"]),
        )
        self._cache.set(cache_key, result, expire=86400)
        return result


# ---------------------------------------------------------------------------
# MockIntexClient
# ---------------------------------------------------------------------------

class MockIntexClient(IntexClient):
    """
    Returns deterministic synthetic cash flows for test pools.

    Supported pool IDs:
    - TEST-POOL-30YR: 30yr fixed, 6% coupon
    - TEST-POOL-15YR: 15yr fixed, 5.5% coupon
    - TEST-POOL-GN30: 30yr Ginnie Mae, 6.5% coupon
    - Any other ID: treated as CC30 with 6% coupon

    Does NOT call any external API.
    """

    def __init__(self, cache_dir: str = None):
        """Initialize without requiring API credentials."""
        self.api_url = "mock://intex"
        self.api_key = "mock"
        if cache_dir:
            import diskcache
            import pathlib
            self._cache = diskcache.Cache(str(pathlib.Path(cache_dir) / "intex_mock"))
        else:
            self._cache = {}

    def _cache_get(self, key):
        if isinstance(self._cache, dict):
            return self._cache.get(key)
        return self._cache.get(key)

    def _cache_set(self, key, value, **kwargs):
        if isinstance(self._cache, dict):
            self._cache[key] = value
        else:
            self._cache.set(key, value, **kwargs)

    def _in_cache(self, key):
        if isinstance(self._cache, dict):
            return key in self._cache
        return key in self._cache

    def get_pool_details(self, pool_id: str) -> dict:
        """Return mock pool details."""
        spec = _MOCK_POOL_SPECS.get(pool_id, _MOCK_POOL_SPECS["TEST-POOL-30YR"])
        return {
            "pool_id": pool_id,
            "wac": spec["wac"],
            "wam": spec["wam"],
            "wala": spec.get("wala", 0),
            "coupon": spec["coupon"],
            "product_type": spec["product_type"],
            "current_balance": 1_000_000,
            "original_balance": 1_000_000,
            "fico": 750,
            "ltv": 0.75,
            "loan_size": 450_000,
            "pct_ca": 0.15,
            "pct_purchase": 0.65,
        }

    def get_cash_flows(
        self,
        pool_id: str,
        cpr_vectors: np.ndarray,
        settlement_date: date,
        face_amount: float = 1_000_000,
    ) -> CashFlows:
        """Generate deterministic synthetic cash flows."""
        cache_key = f"mock_cf:{pool_id}:{settlement_date}:{face_amount:.2f}:{_hash_cpr_vectors(cpr_vectors)}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached

        spec = _MOCK_POOL_SPECS.get(pool_id, _MOCK_POOL_SPECS["TEST-POOL-30YR"])
        result = _generate_mortgage_cashflows(
            wac=spec["wac"],
            wam=spec["wam"],
            cpr_vectors=cpr_vectors,
            face_amount=face_amount,
        )
        self._cache_set(cache_key, result, expire=86400)
        return result


def get_intex_client(cache_dir: str = None) -> IntexClient:
    """
    Factory function: returns MockIntexClient if INTEX_API_KEY is not set,
    otherwise returns a real IntexClient.
    """
    import os
    api_key = os.getenv("INTEX_API_KEY", "")
    if not api_key:
        return MockIntexClient(cache_dir=cache_dir)

    from config import Config
    return IntexClient(
        api_url=Config.INTEX_API_URL,
        api_key=api_key,
        cache_dir=cache_dir or Config.CACHE_DIR,
    )
