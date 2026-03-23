"""
db/ — DuckDB persistence layer for Oasia model results.

Stores expensive computation results so that subsequent queries read from
disk instead of recomputing:

  • rate_path_cache        — BGM/HW path summary statistics + Parquet pointer
  • prepay_cache           — Annual CPR forecast by pool/date/scenario
  • risk_metrics_cache     — OAS, OAD, convexity, yield, Z-spread
  • interest_income_cache  — Gross/net interest income by pool/scenario/year

Public API
----------
    from db.cache import cached_risk_metrics, cached_prepay, cached_rate_paths
    from db.connection import get_conn, init_schema
"""
from db.connection import get_conn, init_schema, DB_PATH

__all__ = ["get_conn", "init_schema", "DB_PATH"]
