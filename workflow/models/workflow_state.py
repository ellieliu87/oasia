"""
Shared Pydantic models for the trading workflow.

WorkflowState is the single source of truth passed through every agent.
It is persisted to disk after every gate so the session can be resumed.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class WorkflowPhase(str, Enum):
    INIT              = "init"
    NEW_VOLUME        = "new_volume"       # Gate 1 – confirm purchase schedule
    RISK_ASSESSMENT   = "risk_assessment"  # Gate 2 – risk profile evaluated
    ALLOCATION        = "allocation"       # Gate 3 – product mix proposed
    MBS_DECOMPOSITION = "mbs_decomposition"# Gate 4 – MBS sub-bucket breakdown
    FINAL_APPROVAL    = "final_approval"   # Gate 5 – final sign-off
    COMPLETE          = "complete"


class RiskAppetite(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE     = "moderate"
    AGGRESSIVE   = "aggressive"


class ApprovalStatus(str, Enum):
    PENDING   = "pending"
    APPROVED  = "approved"
    MODIFIED  = "modified"
    REJECTED  = "rejected"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class MonthlyVolume(BaseModel):
    date: str                       # "YYYY-MM-DD"
    target_total_balance_mm: float
    predicted_existing_balance_mm: float
    new_volume_mm: float


class RiskConstraints(BaseModel):
    duration_min: float = 3.5
    duration_max: float = 6.5
    current_portfolio_duration: float = 5.0
    projected_duration_after_purchase: float = 5.0
    liquidity_score_min: float = 6.0
    projected_liquidity_score: float = 7.5
    max_cmbs_pct: float = 30.0
    max_arm_pct: float = 20.0
    notes: List[str] = Field(default_factory=list)


class AllocationScenario(BaseModel):
    scenario_id: str                  # e.g. "conservative", "moderate", "aggressive"
    label: str
    mbs_pct: float
    cmbs_pct: float
    treasury_pct: float
    mbs_mm: float
    cmbs_mm: float
    treasury_mm: float
    total_new_volume_mm: float
    projected_duration: float
    projected_liquidity_score: float
    projected_yield_pct: float
    rationale: str


class MBSBreakdown(BaseModel):
    fnma_fixed_30yr_pct: float = 0.0
    fhlmc_fixed_30yr_pct: float = 0.0
    gnma_fixed_30yr_pct: float = 0.0
    fnma_fixed_15yr_pct: float = 0.0
    fhlmc_fixed_15yr_pct: float = 0.0
    arm_pct: float = 0.0
    # Dollar amounts ($MM)
    fnma_fixed_30yr_mm: float = 0.0
    fhlmc_fixed_30yr_mm: float = 0.0
    gnma_fixed_30yr_mm: float = 0.0
    fnma_fixed_15yr_mm: float = 0.0
    fhlmc_fixed_15yr_mm: float = 0.0
    arm_mm: float = 0.0
    rationale: str = ""


class GateDecision(BaseModel):
    gate_name: str
    status: ApprovalStatus
    trader_choice: str = ""
    trader_overrides: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    notes: str = ""


class PurchaseScheduleItem(BaseModel):
    product_type: str        # MBS | CMBS | TREASURY
    sub_type: str            # e.g. "FNMA Fixed 30YR", "CMBS AAA", "TSY 10YR"
    amount_mm: float
    target_coupon_range: str # e.g. "4.50–5.00%"
    target_duration: float
    target_oas_bps: float
    priority: int            # 1 = execute first


# ---------------------------------------------------------------------------
# Master workflow state
# ---------------------------------------------------------------------------

class WorkflowState(BaseModel):
    # Identity
    session_id: str
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    # Phase tracking
    phase: WorkflowPhase = WorkflowPhase.INIT
    risk_appetite: RiskAppetite = RiskAppetite.MODERATE
    trader_name: str = "Trader"

    # Data summaries (serialisable – not raw DataFrames)
    monthly_volumes: List[MonthlyVolume] = Field(default_factory=list)
    next_12m_new_volume_mm: float = 0.0
    total_10yr_new_volume_mm: float = 0.0

    # Pool universe summary (top-level statistics by product type)
    pool_summary: Dict[str, Any] = Field(default_factory=dict)

    # Risk
    risk_constraints: Optional[RiskConstraints] = None
    risk_report: str = ""

    # Allocation
    allocation_scenarios: List[AllocationScenario] = Field(default_factory=list)
    selected_scenario: Optional[AllocationScenario] = None

    # MBS decomposition
    mbs_breakdown: Optional[MBSBreakdown] = None

    # Gate decisions
    gate_decisions: List[GateDecision] = Field(default_factory=list)

    # Final output
    purchase_schedule: List[PurchaseScheduleItem] = Field(default_factory=list)
    final_summary: str = ""

    def add_gate_decision(self, decision: GateDecision) -> None:
        self.gate_decisions.append(decision)
        self.updated_at = datetime.utcnow().isoformat()

    def last_decision_for(self, gate_name: str) -> Optional[GateDecision]:
        for d in reversed(self.gate_decisions):
            if d.gate_name == gate_name:
                return d
        return None

    def advance_phase(self, next_phase: WorkflowPhase) -> None:
        self.phase = next_phase
        self.updated_at = datetime.utcnow().isoformat()
