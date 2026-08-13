"""The same input renders the same bytes.

Without this, an archived bill and a re-render of it differ, and the archive
stops being evidence of what the client was actually sent.
"""

from billwright.load import find_bill, load_brand, load_company
from billwright.render import render_bill, render_statement
from billwright.statement import build_statement


def test_bill_renders_byte_identically(tmp_path, profile, assets):
    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, "RE-26001")

    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    render_bill(bill, company, brand, assets, first)
    render_bill(bill, company, brand, assets, second)

    assert first.read_bytes() == second.read_bytes()


def test_statement_renders_byte_identically(tmp_path, profile, assets):
    company, brand = load_company(profile), load_brand(profile)
    statement = build_statement(profile, 2025, company)

    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    render_statement(statement, company, brand, assets, first)
    render_statement(statement, company, brand, assets, second)

    assert first.read_bytes() == second.read_bytes()
