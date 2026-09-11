"""Whether a profile's bills hold together as a numbered series.

An auditor reading ``RE-26001, RE-26003`` asks what became of ``RE-26002``, and
"nothing" is not an answer anyone accepts after the fact. This makes the
question answerable before it is asked.

Kept out of ``main.py`` because the command line is no longer the only caller:
the MCP server reports the same audit, and two implementations of "is the
numbering sound" would eventually disagree about a real invoice.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .load import bill_paths, load_bills, load_expenses
from .numbering import find_duplicates, find_gaps


@dataclass(frozen=True)
class YearAudit:
    """One year of the series.

    ``migrated`` counts numbers issued before this tool existed — Word files in
    a folder somewhere. They are not gaps, but they must be *declared* in
    ``years/<year>.toml`` so that a genuinely missing number can never hide
    among them.
    """

    year: int
    gaps: tuple[str, ...]
    migrated: int


@dataclass(frozen=True)
class Audit:
    """What one profile's bills look like read end to end."""

    bills: int
    duplicates: tuple[str, ...]
    years: tuple[YearAudit, ...]
    empty: tuple[str, ...]
    nonpositive: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def problems(self) -> tuple[str, ...]:
        """Every finding, as lines. Empty means the series is sound."""
        lines = []
        if self.duplicates:
            lines.append(f"duplicate bill numbers: {', '.join(self.duplicates)}")
        for year in self.years:
            if year.gaps:
                lines.append(f"{year.year}: gaps in the numbering: {', '.join(year.gaps)}")
        lines.extend(f"{number}: no line items" for number in self.empty)
        lines.extend(f"{number}: net amount is not positive" for number in self.nonpositive)
        return tuple(lines)

    @property
    def notes(self) -> tuple[str, ...]:
        """True but not wrong — stated so the numbers below them add up."""
        return tuple(
            f"{year.year}: {year.migrated} bill(s) issued before migration, not in this repo"
            for year in self.years
            if year.migrated
        )


def audit(profile: Path) -> Audit:
    """Read every bill in ``profile`` and report what an auditor would ask about."""
    numbers = [path.stem for path in bill_paths(profile)]

    years = []
    for year in sorted({int(path.parent.name) for path in bill_paths(profile)}):
        _, year_data = load_expenses(profile, year)
        elsewhere = set(year_data.get("bills_issued_elsewhere", []))
        gaps = [
            str(gap)
            for gap in find_gaps(numbers + sorted(elsewhere), year)
            if str(gap) not in elsewhere
        ]
        years.append(YearAudit(year=year, gaps=tuple(gaps), migrated=len(elsewhere)))

    bills = load_bills(profile)
    # An empty bill is reported as empty and not *also* as non-positive: one
    # fault, one line. `nonpositive` is for a bill that has lines and still does
    # not come to anything, which is a different mistake.
    empty = tuple(bill.number for bill in bills if not bill.items)
    nonpositive = tuple(bill.number for bill in bills if bill.items and bill.net <= 0)

    return Audit(
        bills=len(numbers),
        duplicates=tuple(find_duplicates(numbers)),
        years=tuple(years),
        empty=empty,
        nonpositive=nonpositive,
    )
