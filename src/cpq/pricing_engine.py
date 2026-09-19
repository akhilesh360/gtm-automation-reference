"""Deterministic pricing math for subscription and usage-based products."""
from __future__ import annotations

from src.cpq.models import PricedQuote, Product, QuoteEconomics, QuoteRequest, UsageEconomics


def calculate_quote(list_price: float, quantity: int, discount_percent: float, contract_term_months: int) -> QuoteEconomics:
    gross = list_price * quantity * contract_term_months
    disc = gross * (discount_percent / 100.0)
    net = gross - disc
    acv = net * (12.0 / contract_term_months)
    return QuoteEconomics(round(gross, 2), round(disc, 2), round(net, 2), round(acv, 2))


def calculate_usage_pricing(
    monthly_commitment: float,
    included_units: int,
    forecasted_units: int,
    overage_price_per_unit: float,
    term_months: int,
) -> UsageEconomics:
    overage_units = max(int(forecasted_units) - int(included_units), 0)
    monthly_overage = overage_units * overage_price_per_unit
    monthly_total = monthly_commitment + monthly_overage
    return UsageEconomics(
        overage_units=overage_units,
        monthly_overage=round(monthly_overage, 2),
        monthly_total=round(monthly_total, 2),
        total_contract_value=round(monthly_total * term_months, 2),
    )


def price_quote(request: QuoteRequest, product: Product) -> PricedQuote:
    """Compose usage and subscription math. A custom overage rate replaces the product rate."""
    usage = None
    if product.pricing_model == "usage":
        effective_overage_rate = (
            request.custom_overage_rate
            if request.custom_overage_rate is not None
            else (product.overage_price_per_unit or 0.0)
        )
        usage = calculate_usage_pricing(
            monthly_commitment=request.monthly_commitment,
            included_units=product.included_units or 0,
            forecasted_units=request.forecasted_units or 0,
            overage_price_per_unit=effective_overage_rate,
            term_months=request.contract_term_months,
        )
        effective_list_price = usage.monthly_total
    else:
        effective_list_price = request.monthly_commitment

    econ = calculate_quote(effective_list_price, request.quantity, request.discount_percent, request.contract_term_months)
    return PricedQuote(request=request, product=product, effective_list_price=effective_list_price, economics=econ, usage=usage)
