"""An archived bill says which inputs produced it, wherever it is stored.

With a git-backed profile a commit answered "which version of this bill made
this PDF". On object storage, a Drive or a USB stick nothing did. The stamp
travels with the document, so the storage choice stops being load-bearing.
"""

import hashlib
import json
import shutil

from pypdf import PdfReader

from billwright import __version__
from billwright.fonts import FACES
from billwright.load import find_bill, load_brand, load_company
from billwright.main import main as billwright_main
from billwright.provenance import PDF_KEY, bill_stamp, read_record, record_path
from billwright.render import render_bill

BILL = "RE-26001"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_stamp_hashes_every_file_the_render_reads(profile, assets):
    bill = find_bill(profile, BILL)
    stamp = bill_stamp(profile, bill, load_brand(profile), assets, qr=True)

    assert set(stamp.inputs) == {
        "bills/2026/RE-26001.toml",
        "company.toml",
        "brand.toml",
        "rates.toml",
        f"clients/{bill.client.key}.toml",
        "mark.svg",
        "styles/overrides.css",
        *(f"assets:fonts/{name}" for name, _ in FACES),
    }
    assert stamp.inputs["company.toml"] == sha256(profile / "company.toml")
    assert stamp.language == bill.language
    assert stamp.qr is True


def test_the_pdf_carries_the_stamp_in_its_metadata(profile, assets, tmp_path):
    """Not on the visible page: it is provenance, of no use to the client."""
    bill = find_bill(profile, BILL)
    brand = load_brand(profile)
    stamp = bill_stamp(profile, bill, brand, assets, qr=True)
    target = tmp_path / "stamped.pdf"

    render_bill(bill, load_company(profile), brand, assets, target, stamp=stamp)

    recorded = json.loads(PdfReader(str(target)).metadata[f"/{PDF_KEY}"])
    assert recorded == {"inputs": stamp.digest, "language": "de", "qr": True}


def test_the_pdf_names_no_input_file(profile, assets, tmp_path):
    """The PDF goes to the client. A list of inputs would name the client's own
    file and show, invoice by invoice, when the rates changed."""
    bill = find_bill(profile, BILL)
    brand = load_brand(profile)
    target = tmp_path / "stamped.pdf"

    render_bill(
        bill,
        load_company(profile),
        brand,
        assets,
        target,
        stamp=bill_stamp(profile, bill, brand, assets, qr=True),
    )

    metadata = str(PdfReader(str(target)).metadata)
    assert bill.client.key not in metadata
    assert "rates.toml" not in metadata


def test_a_stamped_render_is_still_byte_identical(profile, assets, tmp_path):
    """The stamp holds hashes, never a clock, so a re-render reproduces it."""
    bill = find_bill(profile, BILL)
    brand, company = load_brand(profile), load_company(profile)
    stamp = bill_stamp(profile, bill, brand, assets, qr=True)
    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"

    render_bill(bill, company, brand, assets, first, stamp=stamp)
    render_bill(bill, company, brand, assets, second, stamp=stamp)

    assert first.read_bytes() == second.read_bytes()


def archive(profile, tmp_path, *extra):
    archive_dir = tmp_path / "archive"
    argv = ["--profile", str(profile), "--archive-dir", str(archive_dir), "--out", str(tmp_path)]
    assert billwright_main([*argv, "bill", BILL, "--archive", *extra]) == 0
    return next((archive_dir / "bills" / "2026").glob("*.pdf"))


def test_archiving_writes_a_record_beside_the_pdf(profile, tmp_path):
    """Readable without parsing the document, and holding the one thing the
    PDF cannot: when it was rendered, and the hash of the file itself."""
    pdf = archive(profile, tmp_path)

    record = read_record(pdf)

    assert record_path(pdf).is_file()
    assert record["document"] == pdf.name
    assert record["sha256"] == sha256(pdf)
    assert record["billwright"] == __version__
    assert record["rendered_at"].endswith("Z")
    assert record["inputs"]["company.toml"] == sha256(profile / "company.toml")
    assert len(record["inputs_sha256"]) == 64
    assert record["options"] == {"language": "de", "qr": True}


def test_the_record_keeps_the_render_options(profile, tmp_path):
    """A re-render with the default language would not be the document sent."""
    record = read_record(archive(profile, tmp_path, "--language", "en", "--no-qr"))
    assert record["options"] == {"language": "en", "qr": False}


def test_a_draft_gets_no_record(profile, tmp_path):
    argv = ["--profile", str(profile), "--out", str(tmp_path / "out"), "bill", BILL]
    assert billwright_main(argv) == 0
    assert not list((tmp_path / "out").glob("*.json"))


def test_declared_faces_are_fingerprinted_instead_of_the_packaged_ones(profile, assets, tmp_path):
    """The faces a profile declares are the ones embedded, so they are the inputs."""
    root = tmp_path / "profile"
    shutil.copytree(profile, root)
    (root / "fonts").mkdir()
    shutil.copyfile(assets / "fonts" / "Inter-Regular.otf", root / "fonts" / "Own.otf")
    brand = root / "brand.toml"
    brand.write_text(
        brand.read_text(encoding="utf-8").replace(
            'font_family = "Inter"\n',
            'font_family = "Own"\nfaces = [{ file = "fonts/Own.otf", weight = 400 }]\n',
        ),
        encoding="utf-8",
    )

    stamp = bill_stamp(root, find_bill(root, BILL), load_brand(root), assets, qr=True)

    assert stamp.inputs["fonts/Own.otf"] == sha256(root / "fonts" / "Own.otf")
    assert not [name for name in stamp.inputs if name.startswith("assets:")]
