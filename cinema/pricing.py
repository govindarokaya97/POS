"""Ticket tax rules for the cinema counter (same rule as the printed invoice).

    Gold seat Rs 400   |   Silver seat Rs 300

    Local tax = 3% of the base (entrance fee)
    VAT       = 13% of (base + local tax)

The ticket price is the FULL amount the customer pays, so the taxes are
inside it: Rs 300 -> fee 257.76 + VAT 34.51 + local tax 7.73 = 300.00.
The base absorbs any rounding so the parts always add up exactly.

Override in settings.py if the law, prices or counter details change:

    CINEMA_VAT_PERCENT        = 13
    CINEMA_LOCAL_TAX_PERCENT  = 3
    CINEMA_PRICES_INCLUDE_TAX = True    # False -> taxes are added on top
    CINEMA_HS_CODE            = "00"    # printed on the invoice
    CINEMA_DEVICE_NAME        = "BOX OFFICE 1"
    CINEMA_HOLD_MINUTES       = 7       # how long seats stay Reserved at billing
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


def hs_code():
    return str(getattr(settings, "CINEMA_HS_CODE", "00"))


def hold_minutes():
    return int(getattr(settings, "CINEMA_HOLD_MINUTES", 7))


def device_name():
    return str(getattr(settings, "CINEMA_DEVICE_NAME", "BOX OFFICE 1"))


def tax_breakdown(price):
    """Split one seat's price into base + local tax + VAT.

    Returns a dict where base + local_tax + vat == total, to the paisa.
    """
    price = Decimal(price)
    vat_p = vat_percent()
    local_p = local_tax_percent()

    if prices_include_tax():
        total = _round(price)
        base_exact = price / ((1 + local_p / 100) * (1 + vat_p / 100))
        local_exact = base_exact * local_p / 100
        local_tax = _round(local_exact)
        vat = _round((base_exact + local_exact) * vat_p / 100)
        base = total - local_tax - vat
    else:
        base = _round(price)
        local_tax = _round(base * local_p / 100)
        vat = _round((base + local_tax) * vat_p / 100)
        total = base + local_tax + vat

    return {
        "base": base,
        "vat": vat,
        "local_tax": local_tax,
        "total": total,
        "vat_percent": vat_p,
        "local_tax_percent": local_p,
    }
