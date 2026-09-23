"""`billwright verify`: re-render the archive and compare bytes.

"An archived bill is never edited" is a rule people keep. This makes it a check
that fails, and the provenance record says why when it does: the data changed,
the file changed, or a different version rendered it.
"""

import json
import shutil

import pytest

from billwright.main import main as billwright_main
from billwright.paths import DEFAULT_ASSETS
from billwright.provenance import record_path, sha256
from billwright.verify import Outcome, verify_archive

BILL = "RE-26001"


@pytest.fixture
def copied(profile, tmp_path):
    """A copy of the example profile that tests may edit after archiving."""
    root = tmp_path / "profile"
    shutil.copytree(profile, root)
    return root


def archive(profile, tmp_path, *extra):
    archive_dir = tmp_path / "archive"
    argv = ["--profile", str(profile), "--archive-dir", str(archive_dir), "--out", str(tmp_path)]
    assert billwright_main([*argv, "bill", BILL, "--archive", *extra]) == 0
    return archive_dir, next((archive_dir / "bills" / "2026").glob("*.pdf"))


def only(findings):
    assert len(findings) == 1, findings
    return findings[0]


def test_a_fresh_archive_verifies(copied, tmp_path):
    archive_dir, _ = archive(copied, tmp_path)
    finding = only(verify_archive(copied, archive_dir, DEFAULT_ASSETS))
    assert finding.outcome is Outcome.OK
    assert not finding.failed


def test_the_recorded_options_are_used_for_the_re_render(copied, tmp_path):
    """Archived in English without a QR part: re-rendering the defaults is not it."""
    archive_dir, _ = archive(copied, tmp_path, "--language", "en", "--no-qr")
    assert only(verify_archive(copied, archive_dir, DEFAULT_ASSETS)).outcome is Outcome.OK


def test_an_input_edited_after_archiving_is_named(copied, tmp_path):
    archive_dir, _ = archive(copied, tmp_path)
    rates = copied / "rates.toml"
    rates.write_text(rates.read_text(encoding="utf-8") + "\n# edited\n", encoding="utf-8")

    finding = only(verify_archive(copied, archive_dir, DEFAULT_ASSETS))

    assert finding.outcome is Outcome.INPUTS_CHANGED
    assert finding.failed
    assert "rates.toml" in finding.detail


def test_an_altered_pdf_is_caught(copied, tmp_path):
    archive_dir, pdf = archive(copied, tmp_path)
    pdf.write_bytes(pdf.read_bytes() + b"\n")

    finding = only(verify_archive(copied, archive_dir, DEFAULT_ASSETS))

    assert finding.outcome is Outcome.MODIFIED
    assert finding.failed


def test_another_version_is_reported_but_not_a_failure(copied, tmp_path):
    """Its bytes cannot match a render by this version; its file and inputs still can."""
    archive_dir, pdf = archive(copied, tmp_path)
    record = json.loads(record_path(pdf).read_text(encoding="utf-8"))
    record_path(pdf).write_text(json.dumps({**record, "billwright": "0.0.1"}), encoding="utf-8")

    finding = only(verify_archive(copied, archive_dir, DEFAULT_ASSETS))

    assert finding.outcome is Outcome.OTHER_VERSION
    assert not finding.failed
    assert "0.0.1" in finding.detail


def test_an_archive_without_a_record_that_differs_is_reported_not_failed(copied, tmp_path):
    """Archived before records existed: the bytes are all there is to go on, and
    a difference has innocent explanations the missing record cannot rule out."""
    archive_dir, pdf = archive(copied, tmp_path)
    record_path(pdf).unlink()
    pdf.write_bytes(pdf.read_bytes() + b"\n")

    finding = only(verify_archive(copied, archive_dir, DEFAULT_ASSETS))

    assert finding.outcome is Outcome.UNRECORDED
    assert not finding.failed
    assert "before provenance records" in finding.detail


def test_a_recorded_archive_whose_bytes_differ_is_a_failure(copied, tmp_path):
    """Same file, same inputs, same version: nothing innocent is left."""
    archive_dir, pdf = archive(copied, tmp_path)
    # Rewrite the PDF and its recorded hash together, as a careful edit would.
    pdf.write_bytes(pdf.read_bytes() + b"\n")
    record = json.loads(record_path(pdf).read_text(encoding="utf-8"))
    record_path(pdf).write_text(json.dumps({**record, "sha256": sha256(pdf)}), encoding="utf-8")

    finding = only(verify_archive(copied, archive_dir, DEFAULT_ASSETS))

    assert finding.outcome is Outcome.DIFFERS
    assert finding.failed


def test_an_archived_pdf_without_a_bill_file_is_a_failure(copied, tmp_path):
    archive_dir, pdf = archive(copied, tmp_path)
    shutil.copyfile(pdf, pdf.with_name(pdf.name.replace(BILL, "RE-26999")))

    findings = verify_archive(copied, archive_dir, DEFAULT_ASSETS)

    orphan = next(f for f in findings if "RE-26999" in f.pdf.name)
    assert orphan.outcome is Outcome.NO_BILL
    assert orphan.failed


def test_the_command_fails_when_anything_does(copied, tmp_path, capsys):
    archive_dir, pdf = archive(copied, tmp_path)
    argv = ["--profile", str(copied), "--archive-dir", str(archive_dir), "verify"]
    assert billwright_main(argv) == 0

    pdf.write_bytes(pdf.read_bytes() + b"\n")
    assert billwright_main(argv) == 1
    assert pdf.name in capsys.readouterr().err


def test_an_empty_archive_says_so(copied, tmp_path, capsys):
    argv = ["--profile", str(copied), "--archive-dir", str(tmp_path / "none"), "verify"]
    assert billwright_main(argv) == 0
    assert "no archived bills" in capsys.readouterr().out
