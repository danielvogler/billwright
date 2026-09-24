"""End-to-end rendering: it produces a PDF, on the right number of pages."""

from pypdf import PdfReader

from billwright.load import find_bill, load_brand, load_company
from billwright.render import render_bill, render_statement
from billwright.statement import build_statement

BILL = "RE-26001"

A4_WIDTH_PT = 595
A4_HEIGHT_PT = 842


def _page_size(path):
    box = PdfReader(str(path)).pages[0].mediabox
    return round(float(box.width)), round(float(box.height))


def test_bill_renders_on_one_page_with_the_payment_part(tmp_path, profile, assets):
    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL)
    target = tmp_path / "bill.pdf"

    result = render_bill(bill, company, brand, assets, target)

    assert target.exists()
    # One sheet, payment part at its foot: what the client already recognises.
    assert result.pages == 1
    assert result.payment_layout == "inline"


def test_bill_is_a4(tmp_path, profile, assets):
    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL)
    target = tmp_path / "bill.pdf"
    render_bill(bill, company, brand, assets, target)

    width, height = _page_size(target)
    assert abs(width - A4_WIDTH_PT) <= 1
    assert abs(height - A4_HEIGHT_PT) <= 1


def test_bill_text_carries_the_computed_total(tmp_path, profile, assets):
    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL)
    target = tmp_path / "bill.pdf"
    render_bill(bill, company, brand, assets, target)

    text = PdfReader(str(target)).pages[0].extract_text()
    assert "5’085.00 CHF" in text
    assert BILL in text
    # Swiss German, not German German.
    assert "Grüssen" in text
    assert "ß" not in text


def test_english_bill_renders(tmp_path, profile, assets):
    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL).model_copy(update={"language": "en"})
    target = tmp_path / "bill-en.pdf"
    render_bill(bill, company, brand, assets, target)

    text = PdfReader(str(target)).pages[0].extract_text()
    assert "Invoice" in text
    assert "Total due" in text


def test_statement_renders(tmp_path, profile, assets):
    company, brand = load_company(profile), load_brand(profile)
    statement = build_statement(profile, 2025, company)
    target = tmp_path / "statement.pdf"

    result = render_statement(statement, company, brand, assets, target)

    assert result.pages == 1
    text = PdfReader(str(target)).pages[0].extract_text()
    assert "Jahresrechnung 2025" in text
    assert "0.00 CHF" in text


def test_figures_sheet_renders(tmp_path, profile, assets):
    company, brand = load_company(profile), load_brand(profile)
    statement = build_statement(profile, 2025, company)
    target = tmp_path / "figures.pdf"

    render_statement(statement, company, brand, assets, target, "figures.html.j2")

    text = PdfReader(str(target)).pages[0].extract_text()
    assert "Kennzahlen" in text


def test_english_bill_translates_salutation_and_units(tmp_path, profile, assets):
    """A German salutation or unit on an English invoice is what this guards."""
    from pypdf import PdfReader

    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL).model_copy(update={"language": "en"})
    target = tmp_path / "bill-en.pdf"
    render_bill(bill, company, brand, assets, target)

    text = PdfReader(str(target)).pages[0].extract_text()
    assert "Dear Professor Muster," in text
    assert "hours" in text
    assert "Stunden" not in text
    assert "Sehr geehrter" not in text


def test_german_bill_keeps_german_units(tmp_path, profile, assets):
    from pypdf import PdfReader

    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL)
    target = tmp_path / "bill-de.pdf"
    render_bill(bill, company, brand, assets, target)

    text = PdfReader(str(target)).pages[0].extract_text()
    assert "Stunden" in text
    assert "Sehr geehrter Herr Prof. Dr. Muster," in text


def test_english_intro_reads_as_written_english(tmp_path, profile, assets):
    """Not a literal translation of the German.

    'Auftrag' became 'instruction', which is legalistic English, and the German
    lowercase-after-salutation convention had been carried across. Both are
    tells that a document was translated rather than written.
    """
    from pypdf import PdfReader

    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL).model_copy(update={"language": "en"})
    target = tmp_path / "bill-en.pdf"
    render_bill(bill, company, brand, assets, target)

    text = PdfReader(str(target)).pages[0].extract_text()
    assert "Thank you for the engagement." in text
    assert "instruction" not in text
    assert "thank you for" not in text  # lowercase opener is a German habit


def test_the_pdf_records_which_version_rendered_it(tmp_path, profile, assets):
    """An archive should answer "which code produced this" on its own.

    Deliberately in the metadata rather than on the visible document: it is a
    provenance fact, not something a client has any use for.
    """
    from billwright import __version__

    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL)
    target = tmp_path / "versioned.pdf"
    render_bill(bill, company, brand, assets, target)

    creator = PdfReader(str(target)).metadata.creator
    assert creator == f"billwright {__version__}"


def test_the_version_is_the_installed_distributions(tmp_path):
    """Not a second hardcoded string that drifts from pyproject.toml."""
    from importlib.metadata import version

    from billwright import __version__

    assert __version__ == version("billwright")


def _embedded_fonts(path):
    """The base names of every font the PDF embeds, without the subset prefix."""
    names = set()
    for page in PdfReader(str(path)).pages:
        fonts = page.get("/Resources", {}).get("/Font", {})
        for font in fonts.values():
            names.add(str(font.get_object()["/BaseFont"]).lstrip("/").split("+")[-1])
    return names


def test_the_packaged_faces_are_the_ones_embedded(tmp_path, profile, assets):
    """The document is typeset in the faces it embeds, not in a system font.

    WeasyPrint ignores @font-face unless it is handed a FontConfiguration, so
    the faces were read, encoded and then dropped: a machine with Inter
    installed typeset the invoice in its own copy, and one without it in
    whatever fontconfig chose, with an exit code of 0 either way. A family name
    no system has makes the difference visible in the PDF.
    """
    brand = load_brand(profile).model_copy(update={"font_family": "BillwrightProbe"})
    target = tmp_path / "probe.pdf"

    render_bill(find_bill(profile, BILL), load_company(profile), brand, assets, target, False)

    embedded = _embedded_fonts(target)
    assert embedded
    assert all(name.startswith("BillwrightProbe") for name in embedded), embedded
