"""CHF arithmetic and Swiss number formatting.

Money is ``Decimal`` everywhere. A float would silently drift on the third
invoice line and nobody would notice until a client queried the total.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

#: Swiss thousands separator: RIGHT SINGLE QUOTATION MARK, not ASCII apostrophe.
#: `1'234` and `1’234` look nearly identical on screen and differ in a PDF.
THOUSANDS_SEP = "’"

CENT = Decimal("0.01")


def money(value: str | int | float | Decimal) -> Decimal:
    """Coerce to a Decimal rounded to centimes.

    Floats are accepted but routed through ``str`` so that ``0.1`` means what it
    prints as, not what it stores as.
    """
    if isinstance(value, float):
        value = str(value)
    try:
        return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"not a valid amount: {value!r}") from exc


def quantity(value: str | int | float | Decimal) -> Decimal:
    """Coerce a line quantity. Kept at full precision — 7.25 hours is exact."""
    if isinstance(value, float):
        value = str(value)
    return Decimal(value)


def format_amount(value: Decimal) -> str:
    """Format as Swiss currency without the code: ``1’234.50``.

    Swiss convention is an apostrophe for thousands and a period for decimals.
    German convention writes ``1234,50``; this is the Swiss form.
    """
    value = money(value)
    sign = "-" if value < 0 else ""
    whole, _, frac = f"{abs(value):.2f}".partition(".")
    groups: list[str] = []
    while len(whole) > 3:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    groups.insert(0, whole)
    return f"{sign}{THOUSANDS_SEP.join(groups)}.{frac}"


def format_chf(value: Decimal) -> str:
    """Format with the currency code, as it appears on a bill: ``1’234.50 CHF``."""
    return f"{format_amount(value)} CHF"


def format_quantity(value: Decimal) -> str:
    """Format a line quantity: trailing zeros trimmed, but never bare (``1`` -> ``1.0``)."""
    text = format(value.normalize(), "f")
    return f"{text}.0" if "." not in text else text
