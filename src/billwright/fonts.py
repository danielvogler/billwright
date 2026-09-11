"""Which faces a document embeds, and whether they are actually present.

One list, in one place, because two answers to "is the typography right" is how
this breaks. `render.py` embeds these faces and `doctor.py` reports on them; when
the list lived in the renderer and the check was "is the directory non-empty", a
fonts directory holding only `OFL.txt` passed `doctor` and still rendered with a
substituted face.

Substitution is the failure mode worth being loud about. It is invisible on the
machine that rendered the document — that machine has something close enough
installed — and the document is an invoice going to someone who is being asked
for money.
"""

from __future__ import annotations

from pathlib import Path

#: Filename and CSS weight of every face the packaged stylesheet declares.
#: Static weights on purpose: a variable font or a system install is how a
#: substituted face reaches a client document. See AGENTS.md.
FACES: tuple[tuple[str, int], ...] = (
    ("Inter-Regular.otf", 400),
    ("Inter-Medium.otf", 500),
    ("Inter-SemiBold.otf", 600),
)


class FontError(Exception):
    """A declared face is not where it was looked for."""


def fonts_dir(assets: Path) -> Path:
    return assets / "fonts"


def missing_faces(assets: Path) -> list[str]:
    """The declared faces absent from ``assets/fonts/``, in declaration order."""
    directory = fonts_dir(assets)
    return [filename for filename, _ in FACES if not (directory / filename).is_file()]


def describe_missing(assets: Path, missing: list[str]) -> str:
    """A message that says what to do about it, not merely that it happened."""
    return (
        f"missing font face(s) in {fonts_dir(assets)}: {', '.join(missing)}. "
        "The document embeds its faces, and a substituted one on a client's "
        "invoice is not something you find out about in time. Point --assets at "
        "a directory holding a fonts/ subdirectory with these files, or omit it "
        "to use the faces shipped with the package."
    )
