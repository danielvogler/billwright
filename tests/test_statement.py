"""Aggregation follows the money, and a nil year is a real result.

The example profile carries the year-boundary case on purpose: RE-26001 is
paid in 2026, RE-26002 is issued in December 2026 and paid in January 2027.
Which year each counts in is a tax question, not a formatting one.
"""

import shutil
from decimal import Decimal

import pytest

from billwright.load import ProfileError, load_bill, load_company
from billwright.statement import build_statement


def test_2025_is_a_true_nil(profile):
    company = load_company(profile)
    statement = build_statement(profile, 2025, company)

    assert statement.is_nil
    assert statement.revenue == Decimal("0.00")
    assert statement.expenses == Decimal("0.00")
    assert statement.profit == Decimal("0.00")
    assert statement.bill_count == 0


def test_a_nil_year_explains_itself(profile):
    """A table of zeros invites a query; the note answers it in advance."""
    company = load_company(profile)
    statement = build_statement(profile, 2025, company)
    assert "keine Aufträge" in statement.note
    assert "2025" in statement.note


def test_nil_note_is_translated(profile):
    company = load_company(profile)
    statement = build_statement(profile, 2025, company, language="en")
    assert "No mandates" in statement.note


def test_a_year_with_bills_aggregates_them(profile):
    company = load_company(profile)
    statement = build_statement(profile, 2026, company)

    assert not statement.is_nil
    assert statement.revenue == Decimal("5085.00")
    assert statement.bill_count == 1
    # Revenue is itemised per invoice so the tax office can trace each figure.
    assert len(statement.revenue_lines) == 1
    assert "RE-26001" in statement.revenue_lines[0][0]


def test_profit_equals_revenue_minus_expenses(profile):
    company = load_company(profile)
    statement = build_statement(profile, 2026, company)
    assert statement.profit == statement.revenue - statement.expenses


def test_income_follows_payment_not_the_invoice_date(profile):
    """OR Art. 957 II: December's invoice, paid in January, is next year's income.

    RE-26002 is dated 2026-12-18 and paid 2027-01-14. Aggregating by invoice
    date would move CHF 1'795 into the wrong tax year, and the file lives under
    bills/2026/, so a directory-based lookup would miss it in 2027 entirely.
    """
    company = load_company(profile)

    year_issued = build_statement(profile, 2026, company)
    year_paid = build_statement(profile, 2027, company)

    numbers_2026 = " ".join(label for label, _ in year_issued.revenue_lines)
    assert "RE-26002" not in numbers_2026
    assert year_issued.revenue == Decimal("5085.00")

    numbers_2027 = " ".join(label for label, _ in year_paid.revenue_lines)
    assert "RE-26002" in numbers_2027
    assert year_paid.revenue == Decimal("1795.00")


def test_the_receivable_in_the_balance_matches_the_open_invoice(profile):
    """The example ties out: what is not yet revenue is an asset instead."""
    company = load_company(profile)
    statement = build_statement(profile, 2026, company)
    open_invoice = load_bill(profile, profile / "bills" / "2026" / "RE-26002.toml")

    receivables = [amount for label, amount in statement.assets if "Forderungen" in label]
    assert receivables == [open_invoice.net]


def unpaid_profile(profile, tmp_path):
    """A copy of the example whose only bill went out and was never settled."""
    root = tmp_path / "unpaid"
    shutil.copytree(profile, root)
    shutil.rmtree(root / "bills")
    (root / "bills" / "2026").mkdir(parents=True)
    (root / "bills" / "2026" / "RE-26001.toml").write_text(
        "number = 'RE-26001'\ndate = 2026-03-01\nclient = 'example-institute'\n"
        "\n[[items]]\ndescription = 'Consulting - Strategy'\n"
        "quantity = 4\nunit = 'hours'\nservice = 'consulting'\n",
        encoding="utf-8",
    )
    return root


def test_an_unpaid_year_does_not_claim_there_were_no_mandates(profile, tmp_path):
    """Zero revenue with an invoice open is not the same as zero revenue.

    Saying "no mandates were accepted" to the tax office when invoices went out
    and were not settled is a false statement, not a wording preference.
    """
    company = load_company(profile)
    statement = build_statement(unpaid_profile(profile, tmp_path), 2026, company)

    assert statement.revenue == Decimal("0.00")
    assert "keine Aufträge" not in statement.note
    assert "keine Zahlungen" in statement.note
    assert "offen" in statement.note


def test_the_unpaid_note_is_translated(profile, tmp_path):
    company = load_company(profile)
    statement = build_statement(unpaid_profile(profile, tmp_path), 2026, company, language="en")
    assert "outstanding" in statement.note
    assert "No mandates" not in statement.note


def test_paid_on_must_be_a_date(profile, tmp_path):
    """A quoted date is a string, and would silently drop the bill from every year."""
    path = tmp_path / "RE-26099.toml"
    path.write_text(
        "number = 'RE-26099'\ndate = 2026-03-01\nclient = 'example-institute'\n"
        "paid_on = '2026-04-01'\n"
        "\n[[items]]\ndescription = 'Consulting'\nquantity = 1\nservice = 'consulting'\n",
        encoding="utf-8",
    )
    with pytest.raises(ProfileError, match="paid_on"):
        load_bill(profile, path)
