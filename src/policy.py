"""Loads config/policy.yaml into a validated Policy object. The single authority for thresholds."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from src.config import settings


class DiscountPolicy(BaseModel):
    standard_limit: float = Field(ge=0, le=100)
    manager_limit: float = Field(ge=0, le=100)


class AcvPolicy(BaseModel):
    vp_threshold: float = Field(ge=0)


class PaymentTermsPolicy(BaseModel):
    allowed: list[str]
    standard: list[str]


class SlaPolicy(BaseModel):
    pending_approval_days: int = Field(ge=1)


class ScoringWeights(BaseModel):
    intent: float
    usage: float
    engagement: float
    firmographic: float


class ScoringTiers(BaseModel):
    tier_1: float
    tier_2: float


class ScoringPolicy(BaseModel):
    weights: ScoringWeights
    tiers: ScoringTiers
    window_days: int = Field(ge=1)


class ForecastPolicy(BaseModel):
    stage_probabilities: dict[str, float]

    @model_validator(mode="after")
    def _probabilities(self) -> ForecastPolicy:
        for stage, prob in self.stage_probabilities.items():
            if not 0 <= prob <= 1:
                raise ValueError(f"forecast.stage_probabilities.{stage} must be between 0 and 1")
        return self


class OutboundPolicy(BaseModel):
    sequences: dict[str, str]
    max_active_per_account: int = Field(ge=1)


class Policy(BaseModel):
    version: str
    discount: DiscountPolicy
    acv: AcvPolicy
    payment_terms: PaymentTermsPolicy
    approver_order: list[str]
    sla: SlaPolicy
    scoring: ScoringPolicy
    forecast: ForecastPolicy
    outbound: OutboundPolicy

    @model_validator(mode="after")
    def _invariants(self) -> Policy:
        if self.discount.standard_limit >= self.discount.manager_limit:
            raise ValueError("discount.standard_limit must be below discount.manager_limit")
        if not set(self.payment_terms.standard) <= set(self.payment_terms.allowed):
            raise ValueError("payment_terms.standard must be a subset of payment_terms.allowed")
        w = self.scoring.weights
        if abs((w.intent + w.usage + w.engagement + w.firmographic) - 1.0) > 1e-9:
            raise ValueError("scoring.weights must sum to 1.0")
        if self.scoring.tiers.tier_2 >= self.scoring.tiers.tier_1:
            raise ValueError("scoring.tiers.tier_2 must be below tier_1")
        for role in ("Sales Manager", "RevOps", "Finance", "VP Sales"):
            if role not in self.approver_order:
                raise ValueError(f"approver_order is missing {role!r}")
        return self


def load_policy(path: Path | None = None) -> Policy:
    path = path or settings.policy_file
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Policy.model_validate(raw)


@lru_cache(maxsize=1)
def get_policy() -> Policy:
    return load_policy()


def render_approval_matrix(policy: Policy) -> str:
    """Markdown approval matrix generated from the policy so docs cannot drift."""
    d, a = policy.discount, policy.acv
    std = " / ".join(policy.payment_terms.standard)
    rows = [
        ("Rule", "Route"),
        (f"Discount 0–{d.standard_limit:g}%, standard terms ({std}), ACV < ${a.vp_threshold:,.0f}", "Auto-approve, `STANDARD_POLICY` audit row"),
        (f"Discount {d.standard_limit:g}–{d.manager_limit:g}%", "Sales Manager"),
        (f"Discount > {d.manager_limit:g}%", "RevOps + Finance"),
        (f"ACV ≥ ${a.vp_threshold:,.0f}", "VP Sales"),
        ("Custom pricing, custom commitment, or custom overage rate", "RevOps"),
        (f"Payment terms other than {std}", "Finance"),
    ]
    out = [f"# Approval matrix (policy version {policy.version})", "",
           "Generated from `config/policy.yaml` by `python -m src.main policy --render`. Do not edit by hand.", ""]
    out.append(f"| {rows[0][0]} | {rows[0][1]} |")
    out.append("|---|---|")
    for r in rows[1:]:
        out.append(f"| {r[0]} | {r[1]} |")
    out += ["", f"Approver order on a route: {', '.join(policy.approver_order)}.",
            f"Pending-approval SLA: {policy.sla.pending_approval_days} days.", ""]
    return "\n".join(out)


def render_commercial_policy_metadata(policy: Policy) -> str:
    """Salesforce Custom Metadata record (Commercial_Policy__mdt.Current) generated from the policy so the org can DISPLAY
    the thresholds without owning them. Flows still do not compute policy."""
    vals = [
        ("Policy_Version__c", "string", policy.version),
        ("Discount_Standard_Limit__c", "double", f"{policy.discount.standard_limit:g}"),
        ("Discount_Manager_Limit__c", "double", f"{policy.discount.manager_limit:g}"),
        ("VP_ACV_Threshold__c", "double", f"{policy.acv.vp_threshold:g}"),
        ("Standard_Payment_Terms__c", "string", ", ".join(policy.payment_terms.standard)),
        ("Pending_SLA_Days__c", "double", str(policy.sla.pending_approval_days)),
    ]
    body = "".join(f"\n    <values>\n        <field>{f}</field>\n        <value xsi:type=\"xsd:{t}\">{v}</value>\n    </values>" for f, t, v in vals)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<CustomMetadata xmlns="http://soap.sforce.com/2006/04/metadata" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema">\n'
        f'    <label>Current ({policy.version})</label>\n    <protected>false</protected>{body}\n</CustomMetadata>\n'
    )
