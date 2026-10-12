"""Small helpers for printing invoices."""
from decimal import Decimal, ROUND_HALF_UP

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
    "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
    "Sixteen", "Seventeen", "Eighteen", "Nineteen",
]
_TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
    "Eighty", "Ninety",
]


def _below_thousand(n):
    words = []

    hundreds, n = divmod(n, 100)
    if hundreds:
        words.append(f"{_ONES[hundreds]} Hundred")

    if n >= 20:
        tens, ones = divmod(n, 10)
        words.append(_TENS[tens] + (f" {_ONES[ones]}" if ones else ""))
    elif n:
        words.append(_ONES[n])

    return " ".join(words)


def _whole_number_words(n):
    """Whole number in words, using the lakh / crore system used in Nepal."""
    if n == 0:
        return "Zero"

    parts = []

    for size, name in ((10_000_000, "Crore"), (100_000, "Lakh"), (1_000, "Thousand")):
        count, n = divmod(n, size)
        if count:
            parts.append(f"{_whole_number_words(count)} {name}")

    if n:
        parts.append(_below_thousand(n))

    return " ".join(parts)


def amount_in_words(amount):
    """Decimal('113.50') -> 'Rupees One Hundred Thirteen and Fifty Paisa Only'."""
    amount = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    rupees, paisa = divmod(int(amount * 100), 100)

    if rupees == 0 and paisa:
        return f"{_whole_number_words(paisa)} Paisa Only"

    text = f"Rupees {_whole_number_words(rupees)}"

    if paisa:
        text += f" and {_whole_number_words(paisa)} Paisa"

    return text + " Only"