"""Where a rendered document lands, and what it is called."""

import sysconfig
from pathlib import Path

import pytest

from billwright.load import find_bill, load_company
from billwright.paths import (
    ArchiveLocationError,
    bill_filename,
    bill_target,
    checked_archive_dir,
    default_archive,
    default_out,
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
    target = bill_target(company, bill, archive=False, out=tmp_path, archive_dir=tmp_path / "never")
    assert target.parent == tmp_path


def test_an_archived_bill_goes_to_the_year_it_was_issued_in(profile, tmp_path):
    company = load_company(profile)
    bill = find_bill(profile, "RE-26002")
    target = bill_target(
        company, bill, archive=True, out=tmp_path / "never", archive_dir=tmp_path / "keep"
    )
    assert target.parent == tmp_path / "keep" / "bills" / "2026"


def test_statement_stem_carries_the_company_and_the_year(profile):
    company = load_company(profile)
    assert statement_stem(company, 2026) == f"{slug(company.name)}_-_Jahresrechnung_2026"


def test_an_archived_statement_goes_to_its_year(tmp_path):
    archive = tmp_path / "keep"
    assert (
        statement_dir(2026, archive=True, out=tmp_path, archive_dir=archive)
        == archive / "statements" / "2026"
    )
    assert statement_dir(2026, archive=False, out=tmp_path, archive_dir=archive) == tmp_path


# ---- where the defaults come from ----------------------------------------
#
# The point of these four: nothing may be derived from where the *package*
# sits. Installed as a dependency that is a directory inside the virtualenv,
# and `uv sync --reinstall` deletes it.


def test_the_archive_defaults_to_the_profile(tmp_path):
    """The archive holds company facts, so it travels with the company data."""
    assert (
        default_archive(tmp_path / "admin" / "billing")
        == tmp_path / "admin" / "billing" / "archive"
    )


def test_drafts_default_to_the_working_directory(tmp_path):
    assert default_out(tmp_path) == tmp_path / "out"


def test_drafts_default_below_the_working_directory_when_none_is_given(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert default_out() == tmp_path / "out"


def test_an_ordinary_archive_path_is_accepted(tmp_path):
    assert checked_archive_dir(tmp_path / "archive") == tmp_path / "archive"


def test_an_archive_inside_site_packages_is_refused(tmp_path):
    """The mistake is unrecoverable and silent, so it is worth a guard."""
    doomed = tmp_path / "lib" / "python3.13" / "site-packages" / "archive"
    with pytest.raises(ArchiveLocationError) as caught:
        checked_archive_dir(doomed)
    assert "site-packages" in str(caught.value)


def test_an_archive_inside_this_interpreters_installation_is_refused():
    installation = Path(sysconfig.get_paths()["purelib"])
    with pytest.raises(ArchiveLocationError):
        checked_archive_dir(installation / "archive")
