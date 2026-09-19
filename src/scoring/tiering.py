"""Tier assignment from policy thresholds and the v1 action per tier."""
from __future__ import annotations

from src.policy import Policy


def assign_tier(priority: float, policy: Policy) -> str:
    t = policy.scoring.tiers
    if priority >= t.tier_1:
        return "Tier 1"
    if priority >= t.tier_2:
        return "Tier 2"
    return "Tier 3"


def tier_action(tier: str) -> str:
    return {
        "Tier 1": "Create high-priority sales task (Salesforce Flow B creates the Task and dedupes)",
        "Tier 2": "Add to outbound sequence; normal-priority local task",
        "Tier 3": "Nurture; no immediate sales action",
    }[tier]
