"""Fail if a tracked file contains a private value.

This is the guardrail that catches the mistake at 23:00. The engine holds no
company facts by design, but the way that design breaks is a value copied into
a test, a README example or a commit message while debugging — and once pushed,
removing it is a history rewrite rather than an edit.

Three layers, in increasing specificity:

1. **Structural detectors** that need no configuration: anything shaped like an
   IBAN, a Swiss UID, an email address or a Swiss phone number. These run
   everywhere, including CI on a clone that has no private profile at all.
2. **The active profile's own values**, when one is present. Curated field by
   field rather than swept from every string: `example/` legitimately contains
   "Inter", "Zürich" and "hours", so a denylist built from every value in the
   profile is nothing but false positives.
3. **`notes/denylist.txt`**, one literal per line, for anything the first two
   miss — a former address, a client who is no longer in the profile.

`notes/` and `data/` are gitignored, so neither the denylist nor the profile it
is derived from is ever committed.

**This script never prints the value it matched.** A leak guard that echoes the
secret into a CI log has moved the leak rather than caught it. Findings name the
pattern, the file and the line; you look at the line yourself.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Relative to the repository being scanned, not to this file: `--root` must
# scan that tree's denylist, or a test would silently inherit this one's.
DENYLIST = Path("notes") / "denylist.txt"

# A line carrying this marker is skipped. Documentation and the scanner's own
# tests need values that are deliberately IBAN-shaped; without an escape the
# only way to keep the build green is to delete the check. Per-line and visible
# in a diff, the way a lint waiver is — a reviewer sees what was waived.
ALLOW_MARKER = "scan: allow"

# The IBAN registry's Swiss documentation example. It is in `example/` on
# purpose — checksum-valid, belonging to nobody — so it must never be reported.
DOCUMENTATION_IBANS = frozenset({"CH9300762011623852957"})

# RFC 2606 reserves these for documentation. Anything else that looks like an
# address is a real one until proven otherwise.
DOCUMENTATION_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")

# Fonts and images cannot be grepped for a street name, but a tracked PDF is a
# category error on its own — see `is_forbidden_binary`.
TEXT_SUFFIXES_TO_SKIP = frozenset({".lock"})

IBAN_SHAPED = re.compile(r"\bCH\d{2}[ ]?(?:[0-9A-Z]{4}[ ]?){4}[0-9A-Z]{1}\b")
UID_SHAPED = re.compile(r"\bCHE[-\s]?\d{3}[.\s]?\d{3}[.\s]?\d{3}\b")
EMAIL_SHAPED = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
PHONE_SHAPED = re.compile(r"(?:\+41|0041)[\s./-]?(?:\d[\s./-]?){9}")


@dataclass(frozen=True)
class Finding:
    label: str
    path: str
    line: int


def tracked_files(root: Path) -> list[Path]:
    """Every file git knows about. Untracked-and-ignored files are the point."""
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return [root / name for name in result.stdout.split("\0") if name]


def is_public_profile(root: Path, profile: Path) -> bool:
    """True if git tracks this profile — which makes its values public already.

    `example/` is committed on purpose, and a clone with no `data/` resolves to
    it. Deriving a denylist from a tracked profile is a contradiction: it would
    report the Makefile's own default client and the README's own quickstart,
    and CI would fail on every clean run.
    """
    marker = profile / "company.toml"
    if not marker.is_file():
        return False
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", str(marker)],
        cwd=root,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def public_profile_values(root: Path) -> set[str]:
    """Values from every tracked profile in the tree — public by definition."""
    values: set[str] = set()
    for marker in sorted(root.glob("*/company.toml")):
        profile = marker.parent
        if is_public_profile(root, profile):
            values |= set(profile_patterns(profile).values())
    return values


def is_forbidden_binary(path: Path) -> bool:
    """A tracked PDF is always wrong.

    `out/` is scratch and `archive/` is the ten-year record; both are ignored.
    A PDF that has become tracked is an issued document heading for a public
    remote, carrying a client, an amount and an address in its own text layer.
    """
    return path.suffix.lower() == ".pdf"


def _looks_binary(blob: bytes) -> bool:
    return b"\0" in blob[:4096]


def _normalise_iban(text: str) -> str:
    return re.sub(r"\s", "", text).upper()


def structural_findings(path_label: str, line_number: int, line: str) -> list[Finding]:
    """Detectors that need no profile and no configuration."""
    findings: list[Finding] = []

    for match in IBAN_SHAPED.finditer(line):
        if _normalise_iban(match.group()) not in DOCUMENTATION_IBANS:
            findings.append(Finding("IBAN", path_label, line_number))

    if UID_SHAPED.search(line):
        findings.append(Finding("Swiss UID (CHE number)", path_label, line_number))

    for match in EMAIL_SHAPED.finditer(line):
        domain = match.group().rsplit("@", 1)[-1].lower()
        if not domain.endswith(DOCUMENTATION_EMAIL_DOMAINS):
            findings.append(Finding("email address", path_label, line_number))

    if PHONE_SHAPED.search(line):
        findings.append(Finding("Swiss phone number", path_label, line_number))

    return findings


def profile_patterns(profile: Path) -> dict[str, str]:
    """Curated private values from a profile: label -> literal to match.

    Curated, not swept. Every string in the profile would include "Inter",
    "hours" and "Zürich", which `example/` contains for good reasons; the
    resulting noise is how a scan gets ignored and then removed.
    """
    patterns: dict[str, str] = {}

    def add(label: str, value: object) -> None:
        text = str(value or "").strip()
        # Two characters matches half the English language; a house number
        # matches every line number. Both belong to the structural layer or to
        # notes/denylist.txt, not here.
        if len(text) >= 4 and not text.isdigit():
            patterns[label] = text

    company_file = profile / "company.toml"
    if company_file.is_file():
        with company_file.open("rb") as handle:
            company = tomllib.load(handle)
        address = company.get("address", {})
        add("company name", company.get("name"))
        add("company person", company.get("person"))
        add("company email", company.get("email"))
        add("company phone", company.get("phone"))
        add("company website", company.get("website"))
        add("company BIC", company.get("bic"))
        add("company UID", company.get("uid"))
        add("company street", address.get("street"))
        add("company addressee", address.get("name"))
        for extra in address.get("lines", ()):
            add(f"company address line {extra[:1]}", extra)

        iban = _normalise_iban(str(company.get("iban", "")))
        if len(iban) >= 15:
            patterns["IBAN (compact)"] = iban
            patterns["IBAN (spaced)"] = " ".join(re.findall(r".{1,4}", iban))

    for client_file in sorted((profile / "clients").glob("*.toml")):
        with client_file.open("rb") as handle:
            client = tomllib.load(handle)
        address = client.get("address", {})
        key = client_file.stem
        add(f"client {key}: key", key)
        add(f"client {key}: name", address.get("name"))
        add(f"client {key}: street", address.get("street"))
        add(f"client {key}: contact", client.get("contact"))
        add(f"client {key}: reference", client.get("reference"))

    return patterns


def strip_comment(raw: str) -> str:
    """Remove a `#` comment without eating a hex colour.

    `#` cannot simply start a comment: brand hex values are among the most
    likely things to list, and `#2F5C86` would parse as an empty line — the
    denylist would silently hold nothing, which is the worst failure mode a
    leak guard has. A comment is `#` at the start of the line followed by
    whitespace, or ` #` with a space in front.
    """
    line = raw.strip()
    if line.startswith("#") and (len(line) == 1 or line[1].isspace()):
        return ""
    return re.split(r"\s+#", line, maxsplit=1)[0].strip()


def denylist_patterns(path: Path) -> dict[str, str]:
    """Extra literals, one per line. Gitignored — see notes/denylist.txt."""
    if not path.is_file():
        return {}
    patterns: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = strip_comment(raw)
        if line:
            patterns[f"{path.name}:{number}"] = line
    return patterns


def scan(
    root: Path,
    patterns: dict[str, str],
    *,
    structural: bool = True,
) -> tuple[list[Finding], int]:
    """Return findings and the number of files actually read."""
    findings: list[Finding] = []
    lowered = {label: value.lower() for label, value in patterns.items()}
    scanned = 0

    for path in tracked_files(root):
        label = str(path.relative_to(root))

        if is_forbidden_binary(path):
            findings.append(Finding("tracked PDF", label, 0))
            continue
        if path.suffix in TEXT_SUFFIXES_TO_SKIP or not path.is_file():
            continue

        blob = path.read_bytes()
        if _looks_binary(blob):
            continue

        scanned += 1
        for number, line in enumerate(blob.decode("utf-8", "replace").splitlines(), 1):
            if ALLOW_MARKER in line:
                continue
            if structural:
                findings.extend(structural_findings(label, number, line))
            haystack = line.lower()
            for pattern_label, needle in lowered.items():
                if needle in haystack:
                    findings.append(Finding(pattern_label, label, number))

    return findings, scanned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scan",
        description="Fail if a tracked file contains a private value.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="profile whose values must not appear in tracked files (default: resolved)",
    )
    parser.add_argument("--root", default=str(REPO_ROOT), help="repository to scan")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    sys.path.insert(0, str(root / "src"))
    from billwright.load import ProfileError, resolve_profile

    patterns: dict[str, str] = {}
    try:
        profile = resolve_profile(args.profile, root=root)
        name = str(profile.relative_to(root) if profile.is_relative_to(root) else profile)
        if is_public_profile(root, profile):
            source = f"{name} (tracked, so public — structural detectors only)"
        else:
            patterns |= profile_patterns(profile)
            # A value identical to the committed sample's is not private: it is
            # the sample. Onboarding starts with `cp -r example data`, and
            # without this every not-yet-replaced field reports the README and
            # the Makefile against themselves on the user's first `make check`.
            public = public_profile_values(root)
            patterns = {label: value for label, value in patterns.items() if value not in public}
            source = name
    except ProfileError as exc:
        # No profile is not an error here: a clone may have none, and the
        # structural detectors are exactly what protects that case.
        source = f"none ({exc})"

    patterns |= denylist_patterns(root / DENYLIST)
    findings, scanned = scan(root, patterns)

    print(f"scan: {scanned} tracked text file(s), profile: {source}, {len(patterns)} literal(s)")
    if not findings:
        print("scan: clean")
        return 0

    # Deliberately no excerpt: printing the match would put the private value
    # into the CI log that this check exists to keep it out of.
    for finding in sorted({(f.path, f.line, f.label) for f in findings}):
        path, line, label = finding
        where = f"{path}:{line}" if line else path
        print(f"{where}: {label}", file=sys.stderr)
    print(f"scan: {len(findings)} finding(s) — private values must not be tracked", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
