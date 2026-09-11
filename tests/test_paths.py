"""Where a rendered document lands, and what it is called."""

from pathlib import Path

from billwright.load import find_bill, load_company
from billwright.paths import (
    ARCHIVE,
    bill_filename,
    bill_target,
    slug,
    statement_dir,
    statement_stem,
)


def test_slug_keeps_only_filename_safe_characters():
    assert slug("Beispiel Beratung GmbH") == "Beispiel_Beratung_GmbH"


def test_slug_strips_leading_and_trailing_separators():
    assert slug("  Acme, Ltd.  ") == "Acme_Ltd"


def test_bill_filename_carries_the_company_and_the_number(profile):
    company = load_company(profile)
    bill = find_bill(profile, "RE-26001")
    assert bill_filename(company, bill) == f"{slug(company.name)}_-_RE-26001.pdf"


def test_a_draft_goes_to_the_requested_directory(profile, tmp_path):
    company = load_company(profile)
    bill = find_bill(profile, "RE-26001")
    assert bill_target(company, bill, archive=False, out=tmp_path).parent == tmp_path


def test_an_archived_bill_goes_to_the_year_it_was_issued_in(profile):
    company = load_company(profile)
    bill = find_bill(profile, "RE-26002")
    target = bill_target(company, bill, archive=True, out=Path("ignored"))
    assert target.parent == ARCHIVE / "bills" / "2026"


def test_statement_stem_carries_the_company_and_the_year(profile):
    company = load_company(profile)
    assert statement_stem(company, 2026) == f"{slug(company.name)}_-_Jahresrechnung_2026"


def test_an_archived_statement_goes_to_its_year(tmp_path):
    assert statement_dir(2026, archive=True, out=tmp_path) == ARCHIVE / "statements" / "2026"
    assert statement_dir(2026, archive=False, out=tmp_path) == tmp_path
