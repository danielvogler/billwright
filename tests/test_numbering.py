"""RE-YYNNN parsing, sequencing and gap detection."""

import pytest

from billwright.numbering import BillNumber, find_duplicates, find_gaps, next_number


def test_parses_and_round_trips():
    number = BillNumber.parse("RE-26007")
    assert (number.year, number.sequence) == (2026, 7)
    assert str(number) == "RE-26007"


@pytest.mark.parametrize("bad", ["RE-2600", "26007", "RE-260070", "INV-26007", ""])
def test_rejects_malformed(bad):
    with pytest.raises(ValueError):
        BillNumber.parse(bad)


def test_next_number_starts_a_new_year_at_one():
    assert str(next_number(["RE-26007"], 2027)) == "RE-27001"


def test_next_number_follows_the_highest_in_the_year():
    assert str(next_number(["RE-26001", "RE-26007", "RE-26003"], 2026)) == "RE-26008"


def test_gaps_are_reported():
    gaps = find_gaps(["RE-26001", "RE-26002", "RE-26007"], 2026)
    assert [str(g) for g in gaps] == ["RE-26003", "RE-26004", "RE-26005", "RE-26006"]


def test_no_gaps_in_a_contiguous_series():
    assert find_gaps(["RE-26001", "RE-26002"], 2026) == []


def test_duplicates_are_reported():
    assert find_duplicates(["RE-26001", "RE-26001", "RE-26002"]) == ["RE-26001"]
