"""Public API contract."""
from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    db_ok: bool
    policy_version: str
    sf_enabled: bool
    ai_enabled: bool


class ScoreAccountRequest(BaseModel):
    account_id: str | None = Field(default=None, description="Score a stored account by id, or pass inline sub-scores")
    account_name: str | None = None
    intent_score: float | None = Field(default=None, ge=0, le=100)
    usage_score: float | None = Field(default=None, ge=0, le=100)
    engagement_score: float | None = Field(default=None, ge=0, le=100)
    firmographic_fit_score: float | None = Field(default=None, ge=0, le=100)


class ScoreAccountResponse(BaseModel):
    account_id: str | None
    account_name: str | None
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
    forecasted_units: int | None = None
    custom_overage_rate: float | None = None


class ApprovalOut(BaseModel):
    status: str
    approvers: list[str]
    reasons: list[str]


class AuditRowOut(BaseModel):
    rule_triggered: str
    required_approver: str | None
    decision_reason: str


class EvaluateQuoteResponse(BaseModel):
    economics: dict[str, float] | None
    usage: dict[str, float] | None
    approval: ApprovalOut
    audit_rows: list[AuditRowOut]
    validation_error: str | None = None
    policy_version: str
