"""The leak guard.

Every assertion here is about a mistake that is cheap to make and expensive to
undo: a private value in a tracked file is a history rewrite once pushed, not
an edit. The scan is worth having only if it fires on the real cases and stays
quiet on the documentation ones, so both directions are tested.
"""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# tools/ is repo tooling rather than part of the package, so it is loaded by
# path instead of imported. Keeping it out of src/ keeps the billing engine to
# billing.
_spec = importlib.util.spec_from_file_location("scan", REPO_ROOT / "tools" / "scan.py")
assert _spec and _spec.loader
scan_module = importlib.util.module_from_spec(_spec)
# Registered before execution because @dataclass resolves its annotations
# through sys.modules, and the module uses postponed evaluation.
sys.modules[_spec.name] = scan_module
_spec.loader.exec_module(scan_module)

DOCUMENTATION_IBAN = "CH93 0076 2011 6238 5295 7"  # scan: allow — fixture, not a real account
OTHER_IBAN = "CH56 0483 5012 3456 7800 9"  # scan: allow — fixture, not a real account


def structural(line: str) -> list[str]:
    return [finding.label for finding in scan_module.structural_findings("f.toml", 1, line)]


# ---- structural detectors: no profile, no configuration ----


def test_an_iban_is_found():
    assert "IBAN" in structural(f'iban = "{OTHER_IBAN}"')


def test_the_documentation_iban_is_not_a_leak():
    """It is in example/ on purpose: checksum-valid and belonging to nobody."""
    assert structural(f'iban = "{DOCUMENTATION_IBAN}"') == []


def test_a_compact_iban_is_found_too():
    assert "IBAN" in structural(OTHER_IBAN.replace(" ", ""))


def test_a_swiss_uid_is_found():
    assert "Swiss UID (CHE number)" in structural("uid = 'CHE-123.456.789'")  # scan: allow


def test_an_email_address_is_found():
    assert "email address" in structural("contact: someone@a-real-company.ch")  # scan: allow


def test_documentation_email_domains_are_allowed():
    assert structural("billing@example.com and info@example.org") == []


def test_a_swiss_phone_number_is_found():
    assert "Swiss phone number" in structural("phone = '+41 79 123 45 67'")  # scan: allow


# ---- the profile layer ----


def write_profile(root: Path) -> Path:
    profile = root / "data"
    (profile / "clients").mkdir(parents=True)
    (profile / "company.toml").write_text(
        "name = 'Kaufmann Analytics'\n"
        "person = 'Nora Kaufmann'\n"
        "email = 'nora@kaufmann-analytics.ch'\n"  # scan: allow
        f"iban = '{OTHER_IBAN}'\n"
        "\n[address]\n"
        "name = 'Nora Kaufmann'\n"
        "street = 'Lindenweg'\n"
        "house_number = 7\n"
        "postal_code = 8004\n"
        "city = 'Zürich'\n",
        encoding="utf-8",
    )
    (profile / "clients" / "orbit-labs.toml").write_text(
        "contact = 'Dr. Sam Perez'\n\n[address]\nname = 'Orbit Labs'\nstreet = 'Hafenweg'\n",
        encoding="utf-8",
    )
    return profile


def test_profile_patterns_are_curated_not_swept(tmp_path):
    patterns = scan_module.profile_patterns(write_profile(tmp_path))
    values = set(patterns.values())

    assert "Kaufmann Analytics" in values
    assert "Orbit Labs" in values
    assert "Dr. Sam Perez" in values
    # Both forms: an IBAN is written either way and only one would be caught.
    assert OTHER_IBAN.replace(" ", "") in values
    assert OTHER_IBAN in values
    # A city and a house number match half the repository. Noise is how a
    # scan gets ignored, then removed.
    assert "Zürich" not in values
    assert "8004" not in values
    assert "7" not in values


def test_denylist_strips_comments_and_blanks(tmp_path):
    path = tmp_path / "denylist.txt"
    path.write_text("# a former address\nRosenweg 4\n\n   \nAcme GmbH  # old client\n", "utf-8")
    assert set(scan_module.denylist_patterns(path).values()) == {"Rosenweg 4", "Acme GmbH"}


def test_no_denylist_file_is_fine(tmp_path):
    assert scan_module.denylist_patterns(tmp_path / "absent.txt") == {}


def test_a_hex_colour_survives_comment_stripping(tmp_path):
    """Regression: `#` as the comment character eats the brand hex values.

    A brand palette is one of the most likely things to list, and treating a
    leading `#` as a comment made the whole denylist parse as empty — a guard
    that silently holds no patterns is worse than no guard.
    """
    path = tmp_path / "denylist.txt"
    path.write_text("# brand\n#2F5C86\n#DCE6EF  # accent-soft\n", encoding="utf-8")
    assert set(scan_module.denylist_patterns(path).values()) == {"#2F5C86", "#DCE6EF"}


# ---- the scan over a repository ----


def make_repo(root: Path) -> Path:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    return root


def track(root: Path, name: str, content: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", "--force", name], cwd=root, check=True)


def test_a_private_value_in_a_tracked_file_is_found(tmp_path):
    make_repo(tmp_path)
    write_profile(tmp_path)
    track(tmp_path, "README.md", "# Docs\n\nBilling for Kaufmann Analytics.\n")

    patterns = scan_module.profile_patterns(tmp_path / "data")
    findings, scanned = scan_module.scan(tmp_path, patterns)

    assert scanned == 1
    assert [(f.path, f.line, f.label) for f in findings] == [("README.md", 3, "company name")]


def test_an_untracked_file_is_not_scanned(tmp_path):
    """`data/` is gitignored; the scan is about what git would publish."""
    make_repo(tmp_path)
    write_profile(tmp_path)
    (tmp_path / "scratch.md").write_text("Kaufmann Analytics\n", encoding="utf-8")

    findings, _ = scan_module.scan(tmp_path, scan_module.profile_patterns(tmp_path / "data"))
    assert findings == []


def test_a_tracked_pdf_is_a_finding_on_its_own(tmp_path):
    """An issued invoice carries a client, an amount and an address in its text."""
    make_repo(tmp_path)
    track(tmp_path, "docs/sample.pdf", "%PDF-1.7\n")

    findings, _ = scan_module.scan(tmp_path, {})
    assert [f.label for f in findings] == ["tracked PDF"]


def test_the_output_never_prints_the_value_it_matched(tmp_path, capsys):
    """A guard that echoes the secret into a CI log has moved the leak."""
    make_repo(tmp_path)
    write_profile(tmp_path)
    track(tmp_path, "notes.md", "Kaufmann Analytics, IBAN " + OTHER_IBAN + "\n")

    assert scan_module.main(["--root", str(tmp_path)]) == 1

    captured = capsys.readouterr()
    printed = captured.out + captured.err
    assert "Kaufmann Analytics" not in printed
    assert OTHER_IBAN not in printed
    assert OTHER_IBAN.replace(" ", "") not in printed
    assert "notes.md:1" in printed


def test_a_tracked_profile_is_public_and_yields_no_denylist(tmp_path, capsys):
    """Regression: a clean clone resolves to `example/`, which is committed.

    Deriving a denylist from a tracked profile reports the repository's own
    quickstart against itself — the Makefile default client, the README's
    example bill number — so CI would fail on every clean run, and a scan that
    always fails is a scan that gets removed.
    """
    make_repo(tmp_path)
    example = tmp_path / "example"
    example.mkdir()
    (example / "company.toml").write_text("name = 'Example Consulting'\n", encoding="utf-8")
    track(tmp_path, "example/company.toml", (example / "company.toml").read_text())
    track(tmp_path, "Makefile", "# render the sample for Example Consulting\n")

    assert scan_module.is_public_profile(tmp_path, example)
    assert scan_module.main(["--root", str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert "tracked, so public" in out
    assert "0 literal(s)" in out


def test_an_untracked_profile_is_private_and_does_yield_a_denylist(tmp_path):
    make_repo(tmp_path)
    profile = write_profile(tmp_path)
    assert not scan_module.is_public_profile(tmp_path, profile)


def test_a_fresh_copy_of_the_sample_does_not_report_itself(tmp_path, capsys):
    """Onboarding starts with `cp -r example data`.

    Until the values are replaced, the new profile *is* the sample, and every
    unedited field would report the README and Makefile against themselves on
    the user's very first `make check`.
    """
    make_repo(tmp_path)
    (tmp_path / "example").mkdir()
    (tmp_path / "example" / "company.toml").write_text(
        "name = 'Example Consulting'\n", encoding="utf-8"
    )
    track(tmp_path, "example/company.toml", (tmp_path / "example" / "company.toml").read_text())
    track(tmp_path, "README.md", "Renders the invoice of Example Consulting.\n")

    # The user copies it, and has not yet replaced the name.
    shutil.copytree(tmp_path / "example", tmp_path / "data")

    assert scan_module.main(["--root", str(tmp_path)]) == 0
    assert "clean" in capsys.readouterr().out


def test_but_a_replaced_value_is_private_again(tmp_path, capsys):
    make_repo(tmp_path)
    (tmp_path / "example").mkdir()
    (tmp_path / "example" / "company.toml").write_text(
        "name = 'Example Consulting'\n", encoding="utf-8"
    )
    track(tmp_path, "example/company.toml", (tmp_path / "example" / "company.toml").read_text())

    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "company.toml").write_text("name = 'Kaufmann Analytics'\n", "utf-8")
    track(tmp_path, "README.md", "Billing for Kaufmann Analytics.\n")

    assert scan_module.main(["--root", str(tmp_path)]) == 1


def test_a_clean_repository_exits_zero(tmp_path, capsys):
    make_repo(tmp_path)
    write_profile(tmp_path)
    track(tmp_path, "README.md", "# A generic engine\n")

    assert scan_module.main(["--root", str(tmp_path)]) == 0
    assert "clean" in capsys.readouterr().out


def test_this_repository_is_clean():
    """The real thing, against whichever profile this checkout resolves to."""
    assert scan_module.main(["--root", str(REPO_ROOT)]) == 0


@pytest.mark.parametrize(
    "path",
    [
        "data/company.toml",
        "archive/bills/2026/x.pdf",
        "assets/reference/x.docx",
        "notes/x.md",
    ],
)
def test_the_private_paths_are_ignored(path):
    """A path *inside* each directory, not the directory itself.

    `data/` and friends are directory patterns, and git can only match those
    against something it knows is a directory. On a fresh clone none of them
    exist, so checking the bare name reports 'not ignored' — which is how this
    passed locally and failed in CI on every runner.
    """
    result = subprocess.run(
        ["git", "check-ignore", "-v", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{path} is not gitignored"


def test_a_line_can_waive_the_check(tmp_path):
    """Documentation needs IBAN-shaped values; the alternative is deleting the check."""
    make_repo(tmp_path)
    track(
        tmp_path,
        "docs.md",
        f"An IBAN looks like {OTHER_IBAN}  <!-- {scan_module.ALLOW_MARKER} -->\n",
    )
    findings, _ = scan_module.scan(tmp_path, {})
    assert findings == []


def test_the_waiver_is_per_line_not_per_file(tmp_path):
    make_repo(tmp_path)
    track(
        tmp_path,
        "docs.md",
        f"Allowed {OTHER_IBAN}  <!-- {scan_module.ALLOW_MARKER} -->\nNot allowed {OTHER_IBAN}\n",
    )
    findings, _ = scan_module.scan(tmp_path, {})
    assert [(f.line, f.label) for f in findings] == [(2, "IBAN")]
