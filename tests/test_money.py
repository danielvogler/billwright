"""Money formatting is Swiss, and the arithmetic is exact."""

from decimal import Decimal

import pytest

from billwright.money import format_amount, format_chf, format_quantity, money


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "0.00"),
        ("250", "250.00"),
        ("1234", "1’234.00"),
        ("1234.5", "1’234.50"),
        ("1234567.89", "1’234’567.89"),
        ("-250", "-250.00"),
    ],
)
def test_format_amount_uses_swiss_separators(value, expected):
    assert format_amount(Decimal(value)) == expected


def test_thousands_separator_is_the_typographic_apostrophe():
    # U+2019, not ASCII '. They look alike and only one is correct.
    assert "’" in format_amount(Decimal("1234"))
    assert "'" not in format_amount(Decimal("1234"))


def test_format_chf_appends_the_code():
    assert format_chf(Decimal("1234")) == "1’234.00 CHF"


def test_floats_round_trip_through_str():
    # 0.1 + 0.2 as floats is 0.30000000000000004; via str it is 0.30.
    assert money(0.1) + money(0.2) == Decimal("0.30")


def test_money_rounds_half_up():
    assert money("0.005") == Decimal("0.01")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("7.25", "7.25"), ("1.0", "1.0"), ("1", "1.0"), ("3.5", "3.5")],
)
def test_quantity_keeps_a_decimal_place(value, expected):
    assert format_quantity(Decimal(value)) == expected


def test_rejects_nonsense():
    with pytest.raises(ValueError):
        money("not a number")
