"""Bill numbers: ``RE-YYNNN`` — ``RE-`` + two-digit year + three-digit sequence.

The sequence restarts each
year. Gaps matter: an auditor reading a numbered series expects to see every
number in it, so a missing one should be explained, not discovered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

PREFIX = "RE-"
PATTERN = re.compile(r"^RE-(\d{2})(\d{3})$")


@dataclass(frozen=True, order=True)
class BillNumber:
    year: int
    sequence: int

    def __str__(self) -> str:
        return f"{PREFIX}{self.year % 100:02d}{self.sequence:03d}"

    @classmethod
    def parse(cls, text: str) -> BillNumber:
        match = PATTERN.match(text.strip().upper())
        if not match:
            raise ValueError(f"bill number {text!r} is not in RE-YYNNN form (e.g. RE-26001)")
        short_year, sequence = int(match.group(1)), int(match.group(2))
        return cls(year=2000 + short_year, sequence=sequence)

    def next(self) -> BillNumber:
        return BillNumber(self.year, self.sequence + 1)


def next_number(existing: list[str], year: int) -> BillNumber:
    """The next free number for ``year``. Starts at 001 in an empty year."""
    used = [BillNumber.parse(text) for text in existing]
    in_year = [number for number in used if number.year == year]
    if not in_year:
        return BillNumber(year, 1)
    return max(in_year).next()


def find_gaps(existing: list[str], year: int) -> list[BillNumber]:
    """Missing numbers between 001 and the highest issued number of ``year``."""
    in_year = sorted(n for n in (BillNumber.parse(t) for t in existing) if n.year == year)
    if not in_year:
        return []
    present = {number.sequence for number in in_year}
    highest = in_year[-1].sequence
    return [BillNumber(year, seq) for seq in range(1, highest + 1) if seq not in present]


def find_duplicates(existing: list[str]) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for text in existing:
        key = str(BillNumber.parse(text))
        (duplicates if key in seen else seen).add(key)
    return sorted(duplicates)
