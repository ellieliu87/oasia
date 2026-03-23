"""
WorkflowRunner — chains the full analytics pipeline:

  1. Refresh market data (SOFR/Treasury curves, cohort OAS)
  2. Generate Hull-White rate paths per shock scenario
  3. Build PoolCharacteristics from universe DataFrame
  4. Run compute_analytics per pool → BondAnalytics
  5. Persist results to DuckDB risk_metrics_cache
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

logger = logging.getLogger("nexus.workflow.runner")


@dataclass
class WorkflowResult:
    started_at: datetime
    finished_at: datetime
    status: str               # "success" | "partial" | "failed"
    pools_processed: int = 0
    pools_failed: int = 0
    duration_secs: float = 0.0
    error: Optional[str] = None


class WorkflowRunner:
    """
    Parameters
    ----------
    n_paths : int      Monte Carlo paths (default 256).
    shocks  : list     Parallel rate shocks in bps (default [0] = base case).
    limit   : int|None Cap pool count (useful for smoke tests).
    skip_cached : bool Skip pools already in DuckDB for today.
    progress_cb : callable(done, total, message) — UI progress hook.
    """

    def __init__(
        self,
        n_paths: int = 256,
        shocks: list[int] | None = None,
        limit: int | None = None,
        skip_cached: bool = True,
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> None:
        self.n_paths     = n_paths
        self.shocks      = shocks if shocks is not None else [0]
        self.limit       = limit
        self.skip_cached = skip_cached
        self.progress_cb = progress_cb

    # ── Public entry point ───────────────────────────────────────────────────

    def run(self) -> WorkflowResult:
        started    = datetime.now()
        pools_ok   = 0
        pools_fail = 0
        err_msg: str | None = None

        try:
            # ── Step 1: market data ──────────────────────────────────────────
            self._progress(0, 1, "Refreshing market data…")
            from data.market_data import get_current_market_data
            md    = get_current_market_data()
            as_of = md.as_of_date

            # ── Step 2: rate paths (one set per shock, shared across all pools)
            self._progress(0, 1, "Generating rate paths…")
            path_cache = self._build_path_cache(md, as_of)

            # ── Step 3: per-pool analytics ───────────────────────────────────
            from data.pool_universe import get_pool_universe
            df = get_pool_universe()
            if self.limit:
                df = df.head(self.limit)

            from analytics.prepay import PrepayModel
            prepay_model = PrepayModel()

            total = len(df)
            for i, pool_row in enumerate(df.itertuples(index=False)):
                pid = pool_row.pool_id
                self._progress(i, total, f"Pool {i + 1}/{total}: {pid}")
                try:
                    self._process_pool(pool_row, as_of, path_cache, prepay_model)
                    pools_ok += 1
                except Exception as ex:
                    logger.warning("Pool %s failed: %s", pid, ex)
                    pools_fail += 1

            self._progress(total, total, "Complete")

            # Run 30-year projections from current positions
            try:
                from workflow.projection_runner import run_projections
                self._progress(total, total, "Computing projections…")
                run_projections(as_of_date=as_of, n_paths=min(self.n_paths, 64))
            except Exception as proj_ex:
                logger.warning("Projection run failed: %s", proj_ex)

        except Exception as ex:
            logger.error("Workflow error: %s", ex, exc_info=True)
            err_msg = str(ex)

        finished = datetime.now()
        status   = (
            "failed"  if err_msg    else
            "partial" if pools_fail else
            "success"
        )
        return WorkflowResult(
            started_at      = started,
            finished_at     = finished,
            status          = status,
            pools_processed = pools_ok,
            pools_failed    = pools_fail,
            duration_secs   = (finished - started).total_seconds(),
            error           = err_msg,
        )

    # ── Internals ────────────────────────────────────────────────────────────

    def _build_path_cache(self, md, as_of) -> dict[int, object]:
        """
        Generate RatePaths for each shock by shifting the SOFR curve
        then running Hull-White Monte Carlo.  Results are written to DuckDB
        (summary stats) but the full RatePaths objects are kept in memory
        for this run to avoid parquet round-trips.
        """
        from analytics.rate_paths import generate_rate_paths
        from db.cache import write_rate_paths

        path_cache: dict[int, object] = {}
        for shock in self.shocks:
            shocked_curve = md.sofr_curve.shifted(parallel_shift_bps=shock)
            rp = generate_rate_paths(
                shocked_curve,
                n_paths   = self.n_paths,
                n_periods = 360,
                seed      = 42,
            )
            # Persist summary stats (non-fatal if DB unavailable)
            try:
                write_rate_paths(
                    as_of, shock, self.n_paths, 360,
                    seed=42, short_rates=rp.short_rates, save_parquet=False,
                )
            except Exception as ex:
                logger.debug("write_rate_paths skipped: %s", ex)

            path_cache[shock] = rp
        return path_cache

    def _process_pool(self, pool_row, as_of, path_cache, prepay_model) -> None:
        from analytics.prepay import PoolCharacteristics
        from analytics.oas_solver import compute_analytics
        from db.cache import read_risk_metrics, write_risk_metrics

        pool_id       = pool_row.pool_id
        price         = float(pool_row.market_price)
        market_cpr_1m = float(getattr(pool_row, "market_cpr_1m", 0.0))

        chars = PoolCharacteristics(
            coupon        = float(pool_row.coupon),
            wac           = float(pool_row.wac),
            wala          = int(pool_row.wala),
            wam           = int(pool_row.wam),
            loan_size     = float(pool_row.loan_size),
            ltv           = float(pool_row.ltv),
            fico          = int(pool_row.fico),
            pct_ca        = float(pool_row.pct_ca),
            pct_purchase  = float(pool_row.pct_purchase),
            product_type  = str(pool_row.product_type),
            pool_id       = pool_id,
            original_balance = float(pool_row.original_balance),
            current_balance  = float(pool_row.current_balance),
        )

        for shock in self.shocks:
            if self.skip_cached and read_risk_metrics(
                pool_id, as_of, price, shock, self.n_paths
            ):
                continue

            analytics = compute_analytics(
                pool_id       = pool_id,
                pool_chars    = chars,
                market_price  = price,
                settlement_date = as_of,
                rate_paths    = path_cache[shock],
                intex_client  = None,
                prepay_model  = prepay_model,
                market_cpr_1m = market_cpr_1m,
            )

            # Map BondAnalytics dataclass → dict keys expected by write_risk_metrics
            result_dict = {
                "oas_bps":       analytics.oas,
                "z_spread_bps":  analytics.z_spread,
                "oad_years":     analytics.oad,
                "mod_duration":  analytics.mod_duration,
                "convexity":     analytics.convexity,
                "yield_pct":     analytics.yield_,
                "model_price":   analytics.model_price,
                "model_cpr_pct": analytics.model_cpr,
            }
            write_risk_metrics(pool_id, as_of, price, shock, self.n_paths, result_dict)

    def _progress(self, done: int, total: int, msg: str) -> None:
        logger.info("[%d/%d] %s", done, total, msg)
        if self.progress_cb:
            self.progress_cb(done, total, msg)
