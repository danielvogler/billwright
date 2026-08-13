"""The profile loads, and a malformed profile fails loudly rather than quietly."""

from decimal import Decimal

import pytest

from billwright.load import (
    ProfileError,
    find_bill,
    load_bills,
    load_brand,
    load_client,
    load_company,
    load_rates,
)

BILL = "RE-26001"


def test_company_loads(profile):
    company = load_company(profile)
    assert company.name == "EXAMPLE CONSULTING"
    assert company.vat_registered is False


def test_iban_is_normalised_for_the_payment_part(profile):
    """The QR payload needs the compact form; the document shows the spaced one."""
    company = load_company(profile)
    assert " " not in company.iban_compact
    assert company.iban_compact == company.iban.replace(" ", "")


def test_brand_tokens_load(profile):
    brand = load_brand(profile)
    assert brand.colors["accent"].startswith("#")
    assert brand.wordmark["line1"] == "EXAMPLE"


def test_brand_colors_stay_an_open_mapping(profile):
    """A new company must be able to add a token without touching Python."""
    brand = load_brand(profile)
    assert set(brand.colors) >= {"ink", "muted", "rule", "accent", "paper"}


def test_bill_resolves_rates_by_service_name(profile):
    """A line names a service; the price comes from rates.toml, not the bill."""
    bill = find_bill(profile, BILL)
    rates = load_rates(profile)
    assert len(bill.items) == 3
    assert {item.unit_price for item in bill.items} == set(rates.values())


def test_bill_total_is_computed_from_the_lines(profile):
    """The whole point of generating from data: the total cannot drift.

    A Word original this replaces stated a total that its own line items did not
    sum to. Totals are derived here, never stored, so that cannot recur.
    """
    bill = find_bill(profile, BILL)
    # 12.5 * 200.00 + 3.25 * 180.00 + 8 * 250.00
    assert sum(item.quantity for item in bill.items) == Decimal("23.75")
    assert bill.net == sum(item.total for item in bill.items)
    assert bill.net == Decimal("5085.00")


def test_fractional_hours_do_not_drift(profile):
    """3.25 hours at 180.00 is exactly 585.00 — not 584.9999999."""
    bill = find_bill(profile, BILL)
    for item in bill.items:
        assert item.total == item.quantity * item.unit_price
        assert item.total.as_tuple().exponent == -2


def test_missing_bill_is_an_error(profile):
    with pytest.raises(ProfileError):
        find_bill(profile, "RE-99999")


def test_every_bill_in_the_profile_loads(profile):
    for bill in load_bills(profile):
        assert bill.items
        assert bill.net > 0


def test_salutation_is_per_language(profile):
    client = load_client(profile, "example-institute")
    assert client.salutation("de").startswith("Sehr geehrter")
    assert client.salutation("en").startswith("Dear")
    # An unknown language falls back to the client's own, never to empty.
    assert client.salutation("fr") == client.salutation("de")


def test_a_toml_float_never_reaches_decimal_directly():
    """`tomllib` returns real floats; Decimal(0.1) is binary noise.

    `money()` and `quantity()` take the value through `str` first, wired in as
    BeforeValidator. Without that, Pydantic coerces the float itself and the
    exactness money.py exists to guarantee is silently gone.
    """
    from billwright.model import LineItem

    item = LineItem(description="x", quantity=0.1, unit="hours", unit_price=1234.567)

    assert item.quantity == Decimal("0.1")
    assert item.unit_price == Decimal("1234.57")


def test_a_bill_cannot_be_modified_after_loading(profile):
    """An issued invoice does not change. Re-render from the data instead."""
    import pydantic

    bill = find_bill(profile, "RE-26001")
    with pytest.raises(pydantic.ValidationError):
        bill.number = "RE-26099"


def test_an_unknown_key_is_rejected_rather_than_ignored(profile):
    """A typo'd field silently dropped is a field the user thinks they set."""
    import pydantic

    from billwright.model import Address

    with pytest.raises(pydantic.ValidationError):
        Address(
            name="A",
            street="B",
            house_number="1",
            postal_code="8001",
            city="Zürich",
            postcode="8001",
        )


def test_a_qr_field_over_its_limit_names_the_file(profile, tmp_path):
    """The bank rejects it after the invoice was sent, so it fails at load."""
    import shutil

    root = tmp_path / "p"
    shutil.copytree(profile, root)
    path = root / "company.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace('city = "Zürich"', f'city = "{"A" * 80}"'),
        encoding="utf-8",
    )

    with pytest.raises(ProfileError) as exc:
        load_company(root)

    assert "company.toml" in str(exc.value)
    assert "35" in str(exc.value)
