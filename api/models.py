"""Public API contract."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    db_ok: bool
    policy_version: str
    sf_enabled: bool
    ai_enabled: bool


class ScoreAccountRequest(BaseModel):
    account_id: Optional[str] = Field(default=None, description="Score a stored account by id, or pass inline sub-scores")
    account_name: Optional[str] = None
    intent_score: Optional[float] = Field(default=None, ge=0, le=100)
    usage_score: Optional[float] = Field(default=None, ge=0, le=100)
    engagement_score: Optional[float] = Field(default=None, ge=0, le=100)
    firmographic_fit_score: Optional[float] = Field(default=None, ge=0, le=100)


class ScoreAccountResponse(BaseModel):
    account_id: Optional[str]
    account_name: Optional[str]
    sub_scores: dict[str, float]
    priority_score: float
    account_tier: str
    scoring_reason: str
    action: str
    policy_version: str


class EvaluateQuoteRequest(BaseModel):
    account_name: str
    product_id: str
    monthly_commitment: float
    quantity: int = 1
    contract_term_months: int
    discount_percent: float
    payment_terms: str
    custom_pricing: bool = False
    forecasted_units: Optional[int] = None
    custom_overage_rate: Optional[float] = None


class ApprovalOut(BaseModel):
    status: str
    approvers: list[str]
    reasons: list[str]


class AuditRowOut(BaseModel):
    rule_triggered: str
    required_approver: Optional[str]
    decision_reason: str


class EvaluateQuoteResponse(BaseModel):
    economics: Optional[dict[str, float]]
    usage: Optional[dict[str, float]]
    approval: ApprovalOut
    audit_rows: list[AuditRowOut]
    validation_error: Optional[str] = None
    policy_version: str
