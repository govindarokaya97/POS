"""Ticket tax rules for the cinema counter.

Fixed by the business rules:

    Gold seat    Rs 400   |  Silver seat  Rs 300
    VAT          13%      |  Local tax     3%

The prices are the FULL amount the customer pays: VAT and local tax are
contained inside them (so Rs 400 stays Rs 400 on the bill). The two taxes
are both taken from the pre-tax amount (not on top of each other).

Everything can be overridden in settings.py if the law or prices change:

    CINEMA_VAT_PERCENT        = 13
    CINEMA_LOCAL_TAX_PERCENT  = 3
    CINEMA_PRICES_INCLUDE_TAX = True    # False -> taxes are added on top
"""
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

TWO_PLACES = Decimal("0.01")

GOLD = "gold"
SILVER = "silver"

SECTION_CHOICES = (
    (GOLD, "Gold"),
    (SILVER, "Silver"),
)

DEFAULT_GOLD_PRICE = Decimal("400.00")
DEFAULT_SILVER_PRICE = Decimal("300.00")


def _rate(name, default):
    return Decimal(str(getattr(settings, name, default)))


def vat_percent():
    return _rate("CINEMA_VAT_PERCENT", "13")


def local_tax_percent():
    return _rate("CINEMA_LOCAL_TAX_PERCENT", "3")


def prices_include_tax():
    return bool(getattr(settings, "CINEMA_PRICES_INCLUDE_TAX", True))


def _round(value):
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def tax_breakdown(price):
    """Split one seat's price into base + VAT + local tax.

    Returns a dict where base + vat + local_tax == total, to the paisa
    (the base absorbs any rounding difference, so the bill always adds up).
    """
    price = Decimal(price)
    vat_p = vat_percent()
    local_p = local_tax_percent()

    if prices_include_tax():
        divisor = 1 + (vat_p + local_p) / 100
        vat = _round(price * vat_p / 100 / divisor)
        local_tax = _round(price * local_p / 100 / divisor)
        total = _round(price)
        base = total - vat - local_tax
    else:
        base = _round(price)
        vat = _round(base * vat_p / 100)
        local_tax = _round(base * local_p / 100)
        total = base + vat + local_tax

    return {
        "base": base,
        "vat": vat,
        "local_tax": local_tax,
        "total": total,
        "vat_percent": vat_p,
        "local_tax_percent": local_p,
    }
