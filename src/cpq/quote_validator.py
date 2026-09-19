"""Structural validation. Failures are logged and never routed for approval."""
from __future__ import annotations

from src.cpq.models import Product, QuoteRequest, ValidationError
from src.policy import Policy


def validate_quote(request: QuoteRequest, product: Product | None, policy: Policy) -> None:
    if product is None:
        raise ValidationError(f"Unknown product {request.product_id!r}.")
    if not request.account_name or not request.payment_terms:
        raise ValidationError("Required fields missing: account_name and payment_terms are mandatory.")
    if request.discount_percent < 0 or request.discount_percent > 100:
        raise ValidationError("discount_percent must be between 0 and 100.")
    if request.contract_term_months <= 0:
        raise ValidationError("contract_term_months must be positive.")
    if request.monthly_commitment <= 0:
        raise ValidationError("monthly_commitment must be positive.")
    if request.quantity <= 0:
        raise ValidationError("quantity must be positive.")
    if request.payment_terms not in policy.payment_terms.allowed:
        raise ValidationError(f"payment_terms {request.payment_terms!r} is not an allowed value.")
    if product.pricing_model == "usage" and request.forecasted_units is not None and request.forecasted_units < 0:
        raise ValidationError("forecasted_units cannot be negative.")
    if abs(request.monthly_commitment - product.list_price_monthly) > 0.005 and not request.has_custom_pricing:
        raise ValidationError("Monthly commitment must match the product list price unless custom pricing is requested.")
