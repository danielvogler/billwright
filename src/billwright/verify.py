"""Re-render every archived bill and compare it with what is stored.

"An archived bill is never edited" (AGENTS.md, rule 7) is a rule people keep.
This turns it into a check that fails. `check` covers the numbering; this covers
the documents themselves, and is what makes an archive evidence rather than a
folder of PDFs.

A re-render is byte-identical to the original (``tests/test_reproducible.py``),
so a difference means something changed. The provenance record beside the PDF
says what, in the order that makes the answer unambiguous:

1. **the file**: its hash no longer matches the one recorded at archive time;
2. **the data**: a profile file it was rendered from has been edited since;
3. **the engine**: another billwright version rendered it, so its bytes cannot
   match this one's. Not a failure, when the file and the data are unchanged;
4. **the bytes**: same file, same data, same version, and still different.

An archive from before records existed can only be compared byte for byte, and
a difference there has too many innocent explanations (another version, data
edited since) to be called a failure without evidence. It is reported instead,
so a check that is red forever does not teach people to ignore it.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from . import __version__
from .load import ProfileError, find_bill, load_brand, load_company
from .model import Bill, Brand, Company
from .provenance import bill_stamp, read_record, sha256
from .render import render_bill

#: Separates the company slug from the bill number in an archived filename.
#: See ``paths.bill_filename``.
NUMBER_SEPARATOR = "_-_"


class Outcome(Enum):
    OK = "ok"
    OTHER_VERSION = "other version"
    MODIFIED = "modified"
    INPUTS_CHANGED = "inputs changed"
    DIFFERS = "differs"
    UNRECORDED = "unrecorded"
    NO_BILL = "no bill"
    UNRENDERABLE = "cannot re-render"


#: Outcomes that are not a failure of the archive.
PASSING = frozenset({Outcome.OK, Outcome.OTHER_VERSION, Outcome.UNRECORDED})


@dataclass(frozen=True)
class Finding:
    pdf: Path
    outcome: Outcome
    detail: str = ""

    @property
    def failed(self) -> bool:
        return self.outcome not in PASSING

    def __str__(self) -> str:
        suffix = f": {self.detail}" if self.detail else ""
        return f"{self.outcome.value}: {self.pdf.name}{suffix}"


def archived_bills(archive_dir: Path) -> list[Path]:
    """Every archived bill PDF, filed as ``bills/<year>/<name>.pdf``."""
    return sorted((archive_dir / "bills").glob("*/*.pdf"))


def verify_archive(profile: Path, archive_dir: Path, assets: Path) -> list[Finding]:
    """One finding per archived bill, in filename order."""
    company, brand = load_company(profile), load_brand(profile)
    return [
        _verify_one(pdf, profile, company, brand, assets) for pdf in archived_bills(archive_dir)
    ]


def _verify_one(pdf: Path, profile: Path, company: Company, brand: Brand, assets: Path) -> Finding:
    """One bill's finding. A bill that cannot be re-rendered is a finding too.

    Anything else would end the run on the first such bill and report nothing
    about the rest, which is the opposite of what an audit of an archive is for.
    """
    try:
        return _verify(pdf, profile, company, brand, assets)
    except Exception as exc:  # reported as a failing finding, never swallowed
        return Finding(pdf, Outcome.UNRENDERABLE, f"{type(exc).__name__}: {exc}")


def _verify(pdf: Path, profile: Path, company: Company, brand: Brand, assets: Path) -> Finding:
    number = pdf.stem.rpartition(NUMBER_SEPARATOR)[2]
    try:
        bill = find_bill(profile, number)
    except ProfileError as exc:
        return Finding(pdf, Outcome.NO_BILL, str(exc))

    try:
        record = read_record(pdf)
    except ValueError as exc:  # json.JSONDecodeError is one
        return Finding(pdf, Outcome.MODIFIED, f"its provenance record is unreadable: {exc}")
    if record is None:
        return _compare(pdf, bill, profile, company, brand, assets, qr=True, recorded=False)

    if sha256(pdf) != record.get("sha256"):
        return Finding(pdf, Outcome.MODIFIED, "the file no longer matches its recorded hash")

    options = record.get("options", {})
    bill = bill.model_copy(update={"language": options.get("language", bill.language)})
    qr = bool(options.get("qr", True))
    if changed := _changed_inputs(record, bill_stamp(profile, bill, brand, assets, qr=qr).inputs):
        return Finding(pdf, Outcome.INPUTS_CHANGED, f"edited since archiving: {', '.join(changed)}")

    version = record.get("billwright")
    if version != __version__:
        return Finding(
            pdf,
            Outcome.OTHER_VERSION,
            f"rendered by billwright {version}, this is {__version__}; the file and "
            "its inputs are unchanged, and the bytes can be compared only by that version",
        )
    return _compare(pdf, bill, profile, company, brand, assets, qr=qr, recorded=True)


def _changed_inputs(record: dict[str, Any], current: Mapping[str, str]) -> list[str]:
    """Inputs added, removed or edited since the record was written."""
    recorded = record.get("inputs", {})
    names = sorted(set(recorded) | set(current))
    return [name for name in names if recorded.get(name) != current.get(name)]


def _compare(
    pdf: Path,
    bill: Bill,
    profile: Path,
    company: Company,
    brand: Brand,
    assets: Path,
    *,
    qr: bool,
    recorded: bool,
) -> Finding:
    """Re-render ``bill`` into a scratch directory and compare bytes with ``pdf``."""
    stamp = bill_stamp(profile, bill, brand, assets, qr=qr) if recorded else None
    with tempfile.TemporaryDirectory() as scratch:
        fresh = Path(scratch) / pdf.name
        render_bill(bill, company, brand, assets, fresh, qr, profile, stamp)
        same = fresh.read_bytes() == pdf.read_bytes()

    if same:
        return Finding(pdf, Outcome.OK)
    if recorded:
        return Finding(pdf, Outcome.DIFFERS, "same file, inputs and version, different bytes")
    return Finding(
        pdf,
        Outcome.UNRECORDED,
        "archived before provenance records and differs from a re-render; another "
        "version, data edited since, or the file itself may explain it",
    )
