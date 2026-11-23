"""Carbon-credit arithmetic on top of the platform's gross stored-CO2 screening figure.

gross stored CO2 = char x C fraction x stable fraction x 44/12   (engine.models, PERM-001 placeholder map)
credits issued   = gross x (1 - lifecycle share) x (1 - buffer share)
All deduction shares and the fee are scenario assumptions, not registry rules.
"""
from __future__ import annotations

CO2_PER_CAR_T_Y = 4.6   # US EPA typical passenger vehicle, t CO2 per year (equivalence only)


def credit_calc(gross_t_y: float, price: float, lifecycle_share: float, buffer_share: float, fee_per_credit: float) -> dict:
    for n, v in (("lifecycle_share", lifecycle_share), ("buffer_share", buffer_share)):
        if not 0 <= v < 1: raise ValueError(f"{n} must be in [0, 1)")
    gross = max(0.0, gross_t_y)
    credits = gross * (1 - lifecycle_share) * (1 - buffer_share)
    revenue = credits * price
    fees = credits * fee_per_credit
    return {"gross_t_y": gross, "lifecycle_t_y": gross * lifecycle_share, "buffer_t_y": gross * (1 - lifecycle_share) * buffer_share,
            "credits_t_y": credits, "revenue_usd_y": revenue, "fees_usd_y": fees, "net_revenue_usd_y": revenue - fees,
            "cars_equivalent": credits / CO2_PER_CAR_T_Y}


def effective_price_on_gross(price: float, lifecycle_share: float, buffer_share: float, fee_per_credit: float) -> float:
    """USD per tonne of *gross* stored CO2 after deductions and fees (what the economic model multiplies by)."""
    return (price - fee_per_credit) * (1 - lifecycle_share) * (1 - buffer_share)
