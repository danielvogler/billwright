"""`billwright doctor` — the authority for "is this profile complete".

Everything downstream loops against its exit code, so the tests are about the
two properties that makes possible: it reports *everything* at once, and it is
right about the fields where being wrong costs money.
"""

import shutil

import pytest

from billwright.doctor import (
    Level,
    check_company,
    check_environment,
    check_rates,
    diagnose,
)
from billwright.paths import DEFAULT_ASSETS

BAD_CHECKSUM_IBAN = "CH93 0076 2011 6238 5295 8"  # scan: allow — last digit changed
FOREIGN_IBAN = "DE89 3704 0044 0532 0130 00"  # scan: allow — documentation IBAN


@pytest.fixture
def broken(profile, tmp_path):
    """A copy of the example profile that tests may damage."""
    root = tmp_path / "profile"
    shutil.copytree(profile, root)
    return root


def edit_company(root, old, new):
    path = root / "company.toml"
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new), encoding="utf-8")


def messages(problems, level=Level.ERROR):
    return " | ".join(p.message for p in problems if p.level is level)


def test_the_example_profile_is_valid(profile):
    """The profile a fresh clone bills from must pass its own doctor."""
    errors = [p for p in diagnose(profile) if p.level is Level.ERROR]
    assert errors == []


def test_a_transposed_iban_digit_is_caught(broken):
    """The highest-stakes field in the system: nobody retypes a scanned QR code."""
    edit_company(broken, 'iban = "CH93 0076 2011 6238 5295 7"', f'iban = "{BAD_CHECKSUM_IBAN}"')
    assert "mod-97" in messages(check_company(broken))


def test_the_iban_is_not_echoed_in_the_error(broken):
    """A wrong IBAN is still a bank account number, and this output gets pasted."""
    edit_company(broken, 'iban = "CH93 0076 2011 6238 5295 7"', f'iban = "{BAD_CHECKSUM_IBAN}"')
    printed = " ".join(str(p) for p in check_company(broken))
    assert BAD_CHECKSUM_IBAN not in printed
    assert BAD_CHECKSUM_IBAN.replace(" ", "") not in printed


def test_a_foreign_iban_fails_clearly(broken):
    """Better than emitting a payment part no Swiss bank will accept."""
    edit_company(broken, 'iban = "CH93 0076 2011 6238 5295 7"', f'iban = "{FOREIGN_IBAN}"')
    assert "CH or LI" in messages(check_company(broken))


def test_a_non_swiss_issuer_fails_clearly(broken):
    edit_company(broken, 'country = "CH"', 'country = "DE"')
    assert "Swiss QR bills" in messages(check_company(broken))


def test_unanswered_vat_is_an_error_not_a_false(broken):
    """Registered and silent means under-invoicing, and the money is still owed."""
    edit_company(broken, "vat_registered = false\n", "")
    assert "unanswered" in messages(check_company(broken))


def test_registered_without_a_rate_is_an_error(broken):
    edit_company(broken, "vat_registered = false", "vat_registered = true")
    edit_company(broken, 'vat_rate = "8.1"', 'vat_rate = "0"')
    assert "vat_rate" in messages(check_company(broken))


def test_an_empty_uid_is_a_warning_not_an_error(broken):
    """Correct for a sole proprietorship that has none."""
    problems = check_company(broken)
    assert "uid" in messages(problems, Level.WARNING)
    assert "uid" not in messages(problems, Level.ERROR)


def test_a_too_long_name_is_caught(broken):
    """Over 70 characters the bank rejects the payment part, after you sent it."""
    # Replaces the issuer name and the address name, which is the QR field.
    edit_company(broken, 'name = "EXAMPLE CONSULTING"', f'name = "{"A" * 71}"')
    assert "70" in messages(check_company(broken))


def test_everything_is_reported_at_once(broken):
    """A user who fixes one field per run gives up before the profile is valid."""
    edit_company(broken, 'iban = "CH93 0076 2011 6238 5295 7"', f'iban = "{BAD_CHECKSUM_IBAN}"')
    edit_company(broken, "vat_registered = false\n", "")
    edit_company(broken, 'country = "CH"', 'country = "DE"')

    errors = [p for p in check_company(broken) if p.level is Level.ERROR]
    assert len(errors) >= 3


def test_a_missing_rates_file_is_only_a_warning(broken):
    (broken / "rates.toml").unlink()
    assert [p.level for p in check_rates(broken)] == [Level.WARNING]


def test_a_missing_company_file_is_one_clear_error(tmp_path):
    problems = check_company(tmp_path)
    assert len(problems) == 1
    assert problems[0].level is Level.ERROR


def test_a_fonts_directory_missing_a_declared_face_is_an_error(tmp_path):
    """Non-empty is not the same as complete: OFL.txt alone used to pass."""
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "OFL.txt").write_text("licence\n", encoding="utf-8")

    problems = check_environment(tmp_path)

    faces = [p for p in problems if "Inter-Regular.otf" in p.message]
    assert faces and faces[0].level is Level.ERROR


def test_the_packaged_assets_satisfy_doctor():
    assert not [p for p in check_environment(DEFAULT_ASSETS) if "font" in p.message.lower()]
