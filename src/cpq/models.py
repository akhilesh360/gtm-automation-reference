"""Typed models for the CPQ-style engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field


class Product(BaseModel):
    product_id: str
    product_name: str
    pricing_model: str  # "subscription" | "usage"
    list_price_monthly: float
    included_units: Optional[int] = None
    overage_price_per_unit: Optional[float] = None


class QuoteRequest(BaseModel):
    quote_id: Optional[str] = None
    account_id: Optional[str] = None
    account_name: str
    product_id: str
    monthly_commitment: float
    quantity: int = 1
    contract_term_months: int
    discount_percent: float
    payment_terms: str
    custom_pricing: bool = False
    forecasted_units: Optional[int] = None
    custom_overage_rate: Optional[float] = Field(default=None, description="Replaces the product overage rate; implies custom pricing")

    @property
    def has_custom_pricing(self) -> bool:
        return bool(self.custom_pricing) or self.custom_overage_rate is not None


@dataclass(frozen=True)
class QuoteEconomics:
    gross_contract_value: float
    discount_amount: float
    net_contract_value: float
    annual_contract_value: float


@dataclass(frozen=True)
class UsageEconomics:
    overage_units: int
    monthly_overage: float
    monthly_total: float
    total_contract_value: float


@dataclass(frozen=True)
class PricedQuote:
    request: QuoteRequest
    product: Product
    effective_list_price: float
    economics: QuoteEconomics
    usage: Optional[UsageEconomics] = None

    @property
    def discount_percent(self) -> float:
        return self.request.discount_percent

    @property
    def annual_contract_value(self) -> float:
        return self.economics.annual_contract_value

    @property
    def payment_terms(self) -> str:
        return self.request.payment_terms

    @property
    def has_custom_pricing(self) -> bool:
        return self.request.has_custom_pricing


@dataclass(frozen=True)
class AuditRule:
    rule: str
    approver: Optional[str]
    reason: str


@dataclass(frozen=True)
class ApprovalDecision:
    status: str  # "Auto-Approved" | "Pending Approval"
    approvers: list[str]
    reasons: list[str]
    rules: list[AuditRule] = field(default_factory=list)

    @property
    def route(self) -> str:
        return ", ".join(self.approvers)


class ValidationError(ValueError):
    """Raised when a quote request violates a structural rule. Never routed for approval."""
