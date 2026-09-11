"""The bills of a profile, read as a numbered series.

Every case here is one an auditor would raise: a missing number, the same
number twice, an invoice with nothing on it.
"""

import shutil

import pytest

from billwright.audit import audit


@pytest.fixture
def copied(profile, tmp_path):
    """A writable copy of the example profile, so cases can break it."""
    target = tmp_path / "profile"
    shutil.copytree(profile, target)
    return target


def test_the_example_profile_is_a_sound_series(profile):
    result = audit(profile)
    assert result.ok
    assert result.bills == 2
    assert result.problems == ()


def test_a_missing_number_is_a_gap(copied):
    (copied / "bills" / "2026" / "RE-26001.toml").unlink()

    result = audit(copied)

    assert not result.ok
    assert [y.gaps for y in result.years] == [("RE-26001",)]
    assert any("RE-26001" in line for line in result.problems)


def test_a_number_issued_before_the_migration_is_not_a_gap(copied):
    (copied / "bills" / "2026" / "RE-26001.toml").unlink()
    # Prepended, not appended: the file ends inside a [[liabilities]] table, and
    # a top-level key written after that would belong to the table instead.
    year_file = copied / "years" / "2026.toml"
    year_file.write_text(
        'bills_issued_elsewhere = ["RE-26001"]\n' + year_file.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    result = audit(copied)

    assert result.ok
    assert [y.migrated for y in result.years] == [1]
    assert result.notes == ("2026: 1 bill(s) issued before migration, not in this repo",)


def test_the_same_number_twice_is_a_duplicate(copied):
    source = copied / "bills" / "2026" / "RE-26001.toml"
    (copied / "bills" / "2027").mkdir(parents=True, exist_ok=True)
    shutil.copy(source, copied / "bills" / "2027" / "RE-26001.toml")

    result = audit(copied)

    assert not result.ok
    assert result.duplicates == ("RE-26001",)


def test_a_bill_with_no_line_items_is_reported(copied):
    # `items = []` rather than no `items` key at all: the loader rejects the
    # missing key outright, so an empty list is the shape that reaches here.
    target = copied / "bills" / "2026" / "RE-26001.toml"
    head = target.read_text(encoding="utf-8").split("[[items]]")[0]
    target.write_text(f"{head}\nitems = []\n", encoding="utf-8")

    result = audit(copied)

    assert not result.ok
    assert result.empty == ("RE-26001",)


def test_an_empty_profile_audits_clean(tmp_path):
    (tmp_path / "company.toml").write_text("", encoding="utf-8")
    result = audit(tmp_path)
    assert result.ok
    assert result.bills == 0
