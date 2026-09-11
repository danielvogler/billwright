"""Where a rendered document goes, and what it is called.

Filenames carry the company name, so they are built here rather than at each
call site. Two callers spelling the same invoice differently is how an archive
stops being a series — and the archive is the ten-year record (``OR Art. 958f``),
so a name is not a cosmetic decision.

**Nothing here is derived from where the package sits**, with one exception:
`DEFAULT_ASSETS`, which is the vendored typeface and genuinely does travel with
the engine. Everything else follows the profile or the working directory.

That distinction is the whole point of this module. These constants were once
computed from ``Path(__file__).parents[2]`` — the repository root in a clone,
but ``<venv>/lib/python3.13/`` once billwright is installed as a dependency. So
``--archive`` wrote the ten-year record into the virtualenv, printed the path,
exited 0, and the next ``uv sync --reinstall`` deleted it.

Holds no company value: the name is an argument, never a literal.
"""

from __future__ import annotations

import sys
import sysconfig
from pathlib import Path

from .model import Bill, Company

PACKAGE_ROOT = Path(__file__).resolve().parent

#: The vendored faces, shipped inside the wheel. Package-relative is correct
#: here and nowhere else in this module: a typeface is part of the engine, not
#: a company fact, so `pip install billwright` must render without flags.
DEFAULT_ASSETS = PACKAGE_ROOT / "assets"

#: Directory names, so the two records are spelled once.
ARCHIVE_DIRNAME = "archive"
OUT_DIRNAME = "out"


class ArchiveLocationError(Exception):
    """The archive would be written somewhere it cannot survive."""


def default_out(root: Path | None = None) -> Path:
    """Where a draft goes when ``--out`` is not given.

    A function rather than a constant: a module-level value would capture the
    working directory at import time, and the MCP server is long-running.
    """
    return (Path.cwd() if root is None else Path(root)) / OUT_DIRNAME


def default_archive(profile: Path) -> Path:
    """Where the ten-year record goes when nothing is configured.

    Beside the profile, because the archive *is* company data — the invoices
    actually sent. A profile kept in another repository brings its own archive
    with it and needs no second setting to say so.
    """
    return Path(profile) / ARCHIVE_DIRNAME


def is_inside_python_installation(path: Path) -> bool:
    """True if ``path`` sits where a reinstall would delete it.

    Checked two ways, because neither alone is enough: the name test catches a
    path built from any interpreter's layout, and the prefix test catches a
    virtualenv whose directories are not named ``site-packages`` at all.
    """
    resolved = Path(path).resolve()
    if {"site-packages", "dist-packages"} & set(resolved.parts):
        return True

    roots = {sysconfig.get_paths()[key] for key in ("purelib", "platlib")}
    if sys.prefix != sys.base_prefix:  # an active virtualenv
        roots.add(sys.prefix)
    return any(resolved.is_relative_to(Path(root).resolve()) for root in roots)


def checked_archive_dir(path: Path) -> Path:
    """Return ``path``, or refuse to treat it as an archive.

    Cheap guard against an unrecoverable, silent mistake: the record is required
    for ten years, and writing it into the virtualenv loses it without a word.
    """
    if is_inside_python_installation(path):
        raise ArchiveLocationError(
            f"refusing to use {path} as the archive: it is inside the Python "
            "installation, so the next reinstall would delete it. The archive is "
            "the ten-year record under OR Art. 958f. Set [tool.billwright] "
            "archive in pyproject.toml, or pass --archive-dir."
        )
    return Path(path)


def legacy_archive_note(archive_dir: Path, root: Path | None = None) -> str | None:
    """Warn when an older archive sits somewhere this run will not write to.

    The default moved from ``<repository>/archive`` to ``<profile>/archive``.
    Quietly starting a second series elsewhere is the same class of mistake as
    writing into the virtualenv, so it is said out loud rather than discovered
    by whoever answers the Steueramt.
    """
    legacy = (Path.cwd() if root is None else Path(root)) / ARCHIVE_DIRNAME
    target = Path(archive_dir)
    if target.resolve() == legacy.resolve():
        return None
    if not any(legacy.rglob("*.pdf")):
        return None
    if any(target.rglob("*.pdf")):
        return None
    return (
        f"note: {legacy} holds archived PDFs but this run would write to {target}, "
        "which has none. The default archive is now <profile>/archive. Move the "
        "existing files, or set [tool.billwright] archive to the old location."
    )


def slug(text: str) -> str:
    """Reduce a company name to something safe in a filename.

    Deliberately lossy and deliberately stable: existing archives are named by
    this function, so changing the rule renames history.
    """
    keep = [c if c.isalnum() else "_" for c in text]
    return "".join(keep).strip("_").replace("__", "_")


def bill_filename(company: Company, bill: Bill) -> str:
    return f"{slug(company.name)}_-_{bill.number}.pdf"


def bill_target(
    company: Company,
    bill: Bill,
    *,
    archive: bool,
    out: Path,
    archive_dir: Path,
) -> Path:
    """The full path to write one invoice to.

    Both roots are passed in rather than one being decided here, so that the
    choice between a draft and the record is made once, by the caller that knows
    whether ``--archive`` was given.

    An archived bill is filed under the year it was *issued* in, not the year it
    was paid — the archive mirrors what was sent, while the statement follows the
    money. See ``statement.py`` for the other half of that distinction.
    """
    directory = Path(archive_dir) / "bills" / str(bill.year) if archive else Path(out)
    return directory / bill_filename(company, bill)


def statement_stem(company: Company, year: int) -> str:
    """The shared stem of a year's two documents, without a suffix."""
    return f"{slug(company.name)}_-_Jahresrechnung_{year}"


def statement_dir(year: int, *, archive: bool, out: Path, archive_dir: Path) -> Path:
    if archive:
        return Path(archive_dir) / "statements" / str(year)
    return Path(out)
