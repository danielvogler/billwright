"""A profile can change how its documents look, without forking the engine.

`brand.toml` covers colour, typeface and wordmark, which is most of an
identity but not all of one. Two companies that both want their own *layout*
need more than tokens, and the alternative to an override is a fork — at which
point every fix has to be merged by hand into each company's copy.

The cascade is: package stylesheets first, the profile's last. Templates the
other way round, because a template is replaced rather than layered.
"""

import shutil

import pytest
from pypdf import PdfReader

from billwright.load import find_bill, load_brand, load_company
from billwright.render import _stylesheet, render_bill

BILL = "RE-26001"


@pytest.fixture
def custom(profile, tmp_path):
    """A copy of the sample profile that a test may add overrides to."""
    root = tmp_path / "profile"
    shutil.copytree(profile, root)
    return root


def text_of(path):
    return "\n".join(page.extract_text() for page in PdfReader(str(path)).pages)


def test_without_overrides_nothing_changes(profile, assets, tmp_path):
    """The escape hatch must cost nothing when it is not used."""
    company, brand = load_company(profile), load_brand(profile)
    bill = find_bill(profile, BILL)

    plain = tmp_path / "plain.pdf"
    with_profile = tmp_path / "with.pdf"
    render_bill(bill, company, brand, assets, plain)
    render_bill(bill, company, brand, assets, with_profile, profile=profile)

    assert plain.read_bytes() == with_profile.read_bytes()


def test_a_profile_stylesheet_is_appended_after_the_packaged_one(custom, assets):
    """Last in the cascade wins, which is what makes it an override."""
    (custom / "styles").mkdir()
    (custom / "styles" / "overrides.css").write_text(".title { color: red; }", encoding="utf-8")

    css = _stylesheet(load_brand(custom), assets, "bill.css", custom)

    assert css.index("/* profile/styles/overrides.css */") > css.index("--page-margin-x")
    assert css.rstrip().endswith(".title { color: red; }")


def test_a_document_specific_stylesheet_applies_to_that_document(custom, assets):
    (custom / "styles").mkdir()
    (custom / "styles" / "bill.css").write_text(".items { display: none; }", encoding="utf-8")

    on_bill = _stylesheet(load_brand(custom), assets, "bill.css", custom)
    on_statement = _stylesheet(load_brand(custom), assets, "statement.css", custom)

    assert ".items { display: none; }" in on_bill
    assert ".items { display: none; }" not in on_statement


def test_an_override_actually_changes_the_rendered_document(custom, assets, tmp_path):
    """Not just present in the CSS — visible in the PDF."""
    company, brand = load_company(custom), load_brand(custom)
    bill = find_bill(custom, BILL)

    before = tmp_path / "before.pdf"
    render_bill(bill, company, brand, assets, before, profile=custom)

    (custom / "styles").mkdir()
    (custom / "styles" / "bill.css").write_text(
        ".intro, .terms { display: none; }", encoding="utf-8"
    )
    after = tmp_path / "after.pdf"
    render_bill(bill, company, brand, assets, after, profile=custom)

    assert before.read_bytes() != after.read_bytes()
    assert "Vereinbarungsgemäss" in text_of(before)
    assert "Vereinbarungsgemäss" not in text_of(after)


def test_a_profile_template_replaces_the_packaged_one(custom, assets, tmp_path):
    """The whole layout is replaceable, which is the point of a generic engine."""
    company, brand = load_company(custom), load_brand(custom)
    bill = find_bill(custom, BILL)

    (custom / "templates").mkdir()
    (custom / "templates" / "bill.html.j2").write_text(
        "<html><body><h1>Faktura {{ bill.number }}</h1></body></html>",
        encoding="utf-8",
    )

    target = tmp_path / "custom.pdf"
    render_bill(bill, company, brand, assets, target, with_qr=False, profile=custom)

    rendered = text_of(target)
    assert "Faktura RE-26001" in rendered
    assert "Rechnung" not in rendered


def test_overrides_stay_reproducible(custom, assets, tmp_path):
    """An overridden document is still byte-identical on a re-render."""
    company, brand = load_company(custom), load_brand(custom)
    bill = find_bill(custom, BILL)
    (custom / "styles").mkdir()
    (custom / "styles" / "overrides.css").write_text(".title { color: #333; }", encoding="utf-8")

    first, second = tmp_path / "a.pdf", tmp_path / "b.pdf"
    render_bill(bill, company, brand, assets, first, profile=custom)
    render_bill(bill, company, brand, assets, second, profile=custom)

    assert first.read_bytes() == second.read_bytes()
