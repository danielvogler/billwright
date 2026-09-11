"""Where a rendered document goes, and what it is called.

Filenames carry the company name, so they are built here rather than at each
call site. Two callers spelling the same invoice differently is how an archive
stops being a series — and the archive is the ten-year record (``OR Art. 958f``),
so a name is not a cosmetic decision.

Holds no company value: the name is an argument, never a literal.
"""

from __future__ import annotations

from pathlib import Path

from .model import Bill, Company

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSETS = REPO_ROOT / "assets"
DEFAULT_OUT = REPO_ROOT / "out"
ARCHIVE = REPO_ROOT / "archive"


def slug(text: str) -> str:
    """Reduce a company name to something safe in a filename.

    Deliberately lossy and deliberately stable: existing archives are named by
    this function, so changing the rule renames history.
    """
    keep = [c if c.isalnum() else "_" for c in text]
    return "".join(keep).strip("_").replace("__", "_")


def bill_filename(company: Company, bill: Bill) -> str:
    return f"{slug(company.name)}_-_{bill.number}.pdf"


def bill_target(company: Company, bill: Bill, *, archive: bool, out: Path) -> Path:
    """The full path to write one invoice to.

    An archived bill is filed under the year it was *issued* in, not the year it
    was paid — the archive mirrors what was sent, while the statement follows the
    money. See ``statement.py`` for the other half of that distinction.
    """
    directory = ARCHIVE / "bills" / str(bill.year) if archive else out
    return directory / bill_filename(company, bill)


def statement_stem(company: Company, year: int) -> str:
    """The shared stem of a year's two documents, without a suffix."""
    return f"{slug(company.name)}_-_Jahresrechnung_{year}"


def statement_dir(year: int, *, archive: bool, out: Path) -> Path:
    return ARCHIVE / "statements" / str(year) if archive else out
