"""The Swiss QR bill payment part (Zahlteil), as SVG.

Wraps ``qrbill``, which implements the Swiss Payment Standards geometry. The
point of generating it rather than pasting an image — as the Word bills did — is
that the amount inside the QR code then always matches the invoice total.

Reference type is ``NON`` (no structured reference); the bill number travels in
the free-text "Additional information" field, which is what the existing bills
do. Switching to a structured creditor reference (QRR) means asking your bank
for a reference range first; ``reference_number`` is wired for that day.
"""

from __future__ import annotations

import io

from qrbill import QRBill

from .model import Address, Bill, Company
from .money import money

#: The payment part is 210 x 105 mm at the foot of the last page, by standard.
PAYMENT_PART_HEIGHT_MM = 105


def _party(address: Address, name_override: str | None = None) -> dict[str, str]:
    return {
        "name": name_override or address.name,
        "street": address.street,
        "house_num": address.house_number,
        "pcode": address.postal_code,
        "city": address.city,
        "country": address.country,
    }


def build_qr_svg(bill: Bill, company: Company, language: str = "de") -> str:
    """Render the payment part for ``bill`` and return the SVG source.

    The creditor is whoever holds the IBAN: banks match the account holder, and
    a mismatch gets the payment bounced. That is ``address.name`` unless
    ``[qr] creditor_name`` says otherwise — never ``person``, who only signs,
    and who for a GmbH is a different legal party from the one invoicing.
    """
    qr = QRBill(
        account=company.iban_compact,
        creditor=_party(company.address, name_override=company.creditor_name),
        debtor=_party(bill.client.address),
        amount=str(money(bill.total(company.effective_vat_rate))),
        currency="CHF",
        additional_information=_additional_information(bill, company),
        reference_number=None,
        language=language if language in {"de", "en", "fr", "it"} else "de",
    )
    buffer = io.StringIO()
    qr.as_svg(buffer)
    return buffer.getvalue()


def _additional_information(bill: Bill, company: Company) -> str:
    """Free-text reference. Kept short — the field is capped at 140 characters."""
    parts = [company.name, f"Rechnung {bill.number}"]
    if bill.project:
        parts.append(bill.project)
    text = " | ".join(parts)
    return text[:140]
