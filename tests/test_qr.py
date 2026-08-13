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


def test_creditor_is_the_account_holder_not_the_trading_name(svg, profile):
    """Banks match the account holder; a mismatch bounces the payment."""
    assert load_company(profile).person in svg


def test_debtor_is_the_client(svg, profile):
    name = find_bill(profile, BILL).client.address.name
    assert name in svg or name.replace("&", "&amp;") in svg


def test_invoice_number_travels_in_the_free_text_field(svg):
    assert BILL in svg
