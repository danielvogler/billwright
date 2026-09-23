"""Which inputs produced an archived document, recorded where it travels.

With a git-backed profile a commit answered "which version of this bill made
this PDF". On object storage, a Drive or a USB stick nothing did, unless
versioning was on and somebody read it. So the answer is written into the
document and beside it, and the storage choice stops being load-bearing.

Two places, holding different things:

- **The PDF metadata** carries one digest over every input the render read,
  and the options it was rendered with. Hashes, never a clock, so a re-render
  reproduces the same bytes (``tests/test_reproducible.py``), which is what
  lets ``verify`` compare an archive against a fresh render at all. One digest
  rather than a list, because the PDF goes to the client: a list would name
  the client's own file and show, invoice by invoice, when the rates changed.
- **A record beside the PDF** stays in the archive. It lists every input and
  its hash, so a mismatch names the file, and adds what the document cannot
  hold about itself: its own hash and when it was rendered. It is JSON, so it
  can be read without parsing a PDF.

Not on the visible page: it is provenance, of no use to the client.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__
from .fonts import FACES, fonts_dir
from .load import bill_file
from .model import Bill, Brand

#: The <meta> name the stamp is rendered under, and the key it lands at in the
#: PDF's document information: WeasyPrint lowercases the name and drops what
#: is not a letter or a digit.
META_NAME = "billwright-inputs"
PDF_KEY = "billwrightinputs"

#: The record beside an archived PDF is named after it, with this suffix.
RECORD_SUFFIX = ".provenance.json"

#: Profile files a bill may be shaped by beyond its own data, when present.
PROFILE_STYLES = ("styles/overrides.css", "styles/bill.css")

#: Prefix for inputs from outside the profile: the embedded font faces.
ASSETS_PREFIX = "assets:"


@dataclass(frozen=True)
class Stamp:
    """The inputs of one render: input name to SHA-256, and options."""

    inputs: Mapping[str, str]
    language: str
    qr: bool

    @property
    def digest(self) -> str:
        """One SHA-256 over every input name and hash, in name order."""
        canonical = json.dumps(dict(sorted(self.inputs.items())), separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def as_json(self) -> str:
        """What the PDF carries, as canonical JSON: the same stamp, the same bytes."""
        return json.dumps(
            {"inputs": self.digest, "language": self.language, "qr": self.qr},
            sort_keys=True,
            separators=(",", ":"),
        )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bill_inputs(profile: Path, bill: Bill, brand: Brand) -> list[Path]:
    """Every profile file a render of ``bill`` reads.

    The bill, the company, the brand and the client are always read; the rates,
    the logo, the profile's stylesheets and templates only when present.
    """
    required = [
        bill_file(profile, bill.number),
        profile / "company.toml",
        profile / "brand.toml",
        profile / "clients" / f"{bill.client.key}.toml",
    ]
    optional = [profile / "rates.toml", *(profile / name for name in PROFILE_STYLES)]
    if mark := brand.wordmark.get("mark", ""):
        optional.append(profile / mark)
    templates = profile / "templates"
    if templates.is_dir():
        optional.extend(sorted(templates.glob("*.j2")))
    return [*required, *(path for path in optional if path.is_file())]


def fingerprint(profile: Path, paths: list[Path]) -> dict[str, str]:
    """Profile-relative POSIX path to SHA-256, sorted by path."""
    return {path.relative_to(profile).as_posix(): sha256(path) for path in sorted(paths)}


def face_inputs(assets: Path) -> dict[str, str]:
    """The embedded faces, keyed apart from profile files: they shape every byte."""
    directory = fonts_dir(assets)
    return {
        f"{ASSETS_PREFIX}fonts/{filename}": sha256(directory / filename)
        for filename, _ in FACES
        if (directory / filename).is_file()
    }


def bill_stamp(profile: Path, bill: Bill, brand: Brand, assets: Path, *, qr: bool) -> Stamp:
    """The stamp for rendering ``bill`` as it now stands in ``profile`` and ``assets``."""
    inputs = {**fingerprint(profile, bill_inputs(profile, bill, brand)), **face_inputs(assets)}
    return Stamp(inputs=dict(sorted(inputs.items())), language=bill.language, qr=qr)


def record_path(pdf: Path) -> Path:
    return pdf.with_name(pdf.name.removesuffix(".pdf") + RECORD_SUFFIX)


def write_record(pdf: Path, stamp: Stamp, *, rendered_at: datetime | None = None) -> Path:
    """Write the record beside an archived ``pdf``, after it has been rendered."""
    when = (rendered_at or datetime.now(UTC)).astimezone(UTC)
    record = {
        "document": pdf.name,
        "sha256": sha256(pdf),
        "billwright": __version__,
        "rendered_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "options": {"language": stamp.language, "qr": stamp.qr},
        "inputs_sha256": stamp.digest,
        "inputs": dict(stamp.inputs),
    }
    path = record_path(pdf)
    path.write_text(json.dumps(record, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path


def read_record(pdf: Path) -> dict[str, Any] | None:
    """The record beside ``pdf``, or None for one archived before records existed."""
    path = record_path(pdf)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a provenance record")
    return data
