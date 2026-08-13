"""Build a year's accounts from the bills that were *paid* in it.

Paid, not issued. Under OR Art. 957 II a sole proprietorship below the
threshold accounts for receipts and payments, so a bill issued in December and
settled in January is the following year's income. Aggregating by invoice date
instead would move revenue between tax years — the kind of error that is
discovered by the Steueramt rather than by a test.

An invoice that has not been paid is therefore income in no year yet. It still
has to be visible: a year whose only bills are outstanding would otherwise
render as "no mandates were accepted", which is false.

A year with no mandates produces a statement of zeros — a real result, not a
missing one. That case is the whole reason this module exists rather than being
a template with numbers typed into it: the figure the tax office sees should be
derived from the bill files, so it cannot drift from them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from .i18n import strings
from .load import load_bills, load_expenses
from .model import Company, Statement
from .money import money


def build_statement(
    profile: Path,
    year: int,
    company: Company,
    language: str = "de",
    place: str = "",
    prepared_on: date | None = None,
) -> Statement:
    # Every bill, not just the ones filed under bills/<year>/: the December
    # invoice that pays in January lives in the previous year's directory and
    # belongs in this year's revenue.
    all_bills = load_bills(profile)
    bills = [bill for bill in all_bills if bill.paid_on and bill.paid_on.year == year]
    outstanding = [bill for bill in all_bills if bill.year == year and not bill.paid_on]
    expenses, year_data = load_expenses(profile, year)

    vat_rate = company.vat_rate if company.vat_registered else Decimal("0")

    # Revenue is not summed here: Statement derives it from revenue_lines, so
    # the total on the document and the lines above it cannot disagree.
    revenue_lines: tuple[tuple[str, Decimal], ...] = ()
    if bills:
        text = strings(language)
        revenue_lines = tuple(
            (f"{text['invoice']} {bill.number} — {bill.client.address.name}", bill.total(vat_rate))
            for bill in sorted(bills, key=lambda b: b.number)
        )

    assets = tuple(
        (row["description"], money(row["amount"])) for row in year_data.get("assets", [])
    )
    liabilities = tuple(
        (row["description"], money(row["amount"])) for row in year_data.get("liabilities", [])
    )

    note = year_data.get("note", "")
    if not note and not bills:
        if outstanding:
            note = _outstanding_note(year, len(outstanding), language)
        elif not expenses:
            note = _default_nil_note(year, language)

    return Statement(
        year=year,
        revenue_lines=revenue_lines,
        expense_lines=tuple(expenses),
        assets=assets,
        liabilities=liabilities,
        language=language,
        note=note,
        place=place or year_data.get("place", company.address.city),
        prepared_on=prepared_on or year_data.get("prepared_on"),
        bill_count=len(bills),
    )


def _outstanding_note(year: int, count: int, language: str) -> str:
    """Zero revenue with invoices open is not the same as zero revenue.

    Saying "no mandates were accepted" when invoices went out and were not
    settled is a false statement to the tax office, so the two cases get two
    different sentences.
    """
    if language == "en":
        invoices = "invoice" if count == 1 else "invoices"
        return (
            f"No payments were received in {year}. {count} {invoices} issued in "
            f"{year} were still outstanding at the year end; under the receipts "
            f"and payments basis they count as income in the year they are paid."
        )
    rechnungen = "Rechnung" if count == 1 else "Rechnungen"
    waren = "war" if count == 1 else "waren"
    return (
        f"Im Jahr {year} sind keine Zahlungen eingegangen. {count} im Jahr {year} "
        f"gestellte {rechnungen} {waren} per Jahresende offen; nach der "
        f"Einnahmen-Ausgaben-Rechnung zählen sie im Jahr der Zahlung als Ertrag."
    )


def _default_nil_note(year: int, language: str) -> str:
    """Explain a zero year in one sentence, so nobody has to ask."""
    if language == "en":
        return (
            f"No mandates were accepted in {year}. The business was therefore "
            f"without revenue, and no business expenses were incurred. Revenue, "
            f"expenses and profit for {year} are accordingly CHF 0.00."
        )
    return (
        f"Im Jahr {year} wurden keine Aufträge angenommen. Das Unternehmen war "
        f"daher ohne Umsatz, und es sind keine Geschäftsaufwände angefallen. "
        f"Ertrag, Aufwand und Gewinn {year} betragen entsprechend CHF 0.00."
    )
