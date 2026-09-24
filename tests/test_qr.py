"""The Swiss QR payment part carries the right payload.

The failure this guards against is the one the Word originals had: a payment part
pasted in as an image, whose amount silently stops matching the invoice total.

Assertions read their expected values from the profile rather than repeating them
as literals. That keeps real bank details out of the source, and it means these
tests still pass for whichever profile they are pointed at.
"""

from decimal import Decimal

import pytest

from billwright.load import find_bill, load_company
from billwright.qr import build_qr_svg

BILL = "RE-26001"


@pytest.fixture
def svg(profile):
    company = load_company(profile)
    bill = find_bill(profile, BILL)
    return build_qr_svg(bill, company, "de")


def test_amount_matches_the_invoice_total(svg, profile):
    bill = find_bill(profile, BILL)
    # 12.5 * 200 + 3.25 * 180 + 8 * 250 = 2500 + 585 + 2000
    assert bill.total(0) == Decimal("5085.00")
    # qrbill renders the amount with a space as the thousands separator.
    assert "5 085.00" in svg


def test_creditor_iban_is_present(svg, profile):
    assert load_company(profile).iban in svg


def incorporated(profile, **changes):
    """The example issuer as a GmbH: account held by the entity, letter signed by a person."""
    company = load_company(profile)
    address = company.address.model_copy(update={"name": "Muster Engineering GmbH"})
    fields = {"address": address, "person": "Alex Muster", "qr_creditor_name": "", **changes}
    return company.model_copy(update=fields)


def test_the_creditor_is_the_address_name_not_the_signer(profile):
    """For a GmbH the account is held by the entity, and `person` only signs.

    The creditor used to be taken from `person`, which for an incorporated
    issuer asked the client to pay a different legal party than the one that
    invoiced them. Nothing on the page showed it; a bank bouncing the payment
    did.
    """
    svg = build_qr_svg(find_bill(profile, BILL), incorporated(profile), "de")
    assert "Muster Engineering GmbH" in svg
    assert "Alex Muster" not in svg


def test_an_explicit_creditor_name_overrides_the_address_name(profile):
    """A sole proprietor whose account is in their own name says so in [qr]."""
    company = incorporated(profile, qr_creditor_name="Dr. Alex Muster")
    svg = build_qr_svg(find_bill(profile, BILL), company, "de")
    assert "Dr. Alex Muster" in svg


def test_a_blank_creditor_name_falls_back_to_the_address_name(profile, tmp_path):
    """Whitespace is not a payee: it must not reach the payment part."""
    import shutil

    root = tmp_path / "profile"
    shutil.copytree(profile, root)
    path = root / "company.toml"
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'creditor_name = "Dr. Alex Muster"', 'creditor_name = " "'
        ),
        encoding="utf-8",
    )
    company = load_company(root)
    assert company.creditor_name == company.address.name


def test_a_qr_value_that_is_not_a_table_is_a_profile_error(profile, tmp_path):
    import shutil

    from billwright.load import ProfileError

    root = tmp_path / "profile"
    shutil.copytree(profile, root)
    path = root / "company.toml"
    text = path.read_text(encoding="utf-8").replace('[qr]\ncreditor_name = "Dr. Alex Muster"\n', "")
    path.write_text(
        text.replace('person = "Dr. Alex Muster"', 'person = "Dr. Alex Muster"\nqr = "x"'),
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="qr must be a table"):
        load_company(root)


def test_the_example_creditor_comes_from_its_qr_table(svg, profile):
    assert load_company(profile).qr_creditor_name in svg


def test_debtor_is_the_client(svg, profile):
    name = find_bill(profile, BILL).client.address.name
    assert name in svg or name.replace("&", "&amp;") in svg


def test_invoice_number_travels_in_the_free_text_field(svg):
    assert BILL in svg
