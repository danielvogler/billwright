"""HTML/CSS -> PDF via WeasyPrint.

The style source is a website, so the shortest path to "looks like the site" is
to reuse its tokens in real CSS rather than to re-implement the layout in a
drawing API. WeasyPrint gives real ``@page`` control and honours
``SOURCE_DATE_EPOCH``, which is what makes the archived PDFs reproducible.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined

from . import __version__
from .fonts import FACES, FontError, describe_missing, fonts_dir, missing_faces
from .i18n import MONTHS, country_name, strings, unit_name
from .model import Bill, Brand, Company, Statement
from .money import format_amount, format_chf, format_quantity
from .paths import PACKAGE_ROOT
from .provenance import META_NAME, Stamp
from .qr import build_qr_svg

TEMPLATES = PACKAGE_ROOT / "templates"
STYLES = PACKAGE_ROOT / "styles"


@dataclass(frozen=True)
class RenderResult:
    path: Path
    pages: int
    #: "inline" (payment part at the foot of page 1) or "separate" (own sheet).
    payment_layout: str = ""


def _environment(profile: Path | None = None) -> Environment:
    """Jinja, with the profile's own templates taking precedence.

    A profile may drop a file of the same name into ``<profile>/templates/`` and
    replace the packaged one outright. That is the escape hatch that keeps this
    a generic engine rather than one shared letterhead: brand.toml changes the
    colours, the typeface and the wordmark, but two companies that both want
    their own *layout* need more than tokens.
    """
    search: list[FileSystemLoader] = []
    if profile is not None and (profile / "templates").is_dir():
        search.append(FileSystemLoader(profile / "templates"))
    search.append(FileSystemLoader(TEMPLATES))

    env = Environment(
        loader=ChoiceLoader(search) if len(search) > 1 else search[0],
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["chf"] = format_chf
    env.filters["amount"] = format_amount
    env.filters["qty"] = format_quantity
    env.filters["unit"] = unit_name
    # A document should be able to say which code produced it — an archive is
    # kept for ten years and the lock file that pinned the version lives in
    # another repository that may have moved on. Metadata only: it is provenance,
    # not something the client has any use for.
    env.globals["billwright_version"] = __version__
    # Which inputs produced it, for the same reason; see provenance.py. Empty
    # unless the caller stamped the render.
    env.globals["provenance_key"] = META_NAME
    env.globals["provenance"] = ""
    return env


def long_date(value: date, language: str) -> str:
    months = MONTHS.get(language, MONTHS["de"])
    return f"{value.day}. {months[value.month - 1]} {value.year}"


def short_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def font_face_css(brand: Brand, assets: Path) -> str:
    """Embed the declared faces as data URIs.

    Vendored rather than system-installed so the build cannot silently
    substitute a different font into a client-facing PDF on another machine.

    An absent face raises. It used to `continue`, which made the docstring above
    false in the one case it was written for: the faces were not in the wheel, so
    an installed copy quietly typeset client invoices in whatever WeasyPrint
    chose and exited 0.
    """
    if missing := missing_faces(assets):
        raise FontError(describe_missing(assets, missing))

    blocks = []
    for filename, weight in FACES:
        path = fonts_dir(assets) / filename
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        blocks.append(
            f"@font-face {{\n"
            f"  font-family: '{brand.font_family}';\n"
            f"  font-weight: {weight};\n"
            f"  font-style: normal;\n"
            f"  src: url(data:font/otf;base64,{encoded}) format('opentype');\n"
            f"}}"
        )
    return "\n".join(blocks)


def _stylesheet(brand: Brand, assets: Path, extra: str, profile: Path | None = None) -> str:
    """The cascade, in order: package first, profile last.

    Anything in ``<profile>/styles/`` is appended after the packaged rules, so a
    profile overrides without forking. ``overrides.css`` applies to every
    document; a file named after the document (``bill.css``, ``statement.css``)
    applies to that one.
    """
    tokens = STYLES / "tokens.css"
    print_css = STYLES / "print.css"
    document_css = STYLES / extra
    variables = f":root {{\n{brand.css_variables()}\n  --font-sans: '{brand.font_family}';\n}}"
    sheets = [
        font_face_css(brand, assets),
        variables,
        tokens.read_text(encoding="utf-8"),
        print_css.read_text(encoding="utf-8"),
        document_css.read_text(encoding="utf-8"),
    ]
    if profile is not None:
        for name in ("overrides.css", extra):
            override = profile / "styles" / name
            if override.is_file():
                sheets.append(f"/* {profile.name}/styles/{name} */")
                sheets.append(override.read_text(encoding="utf-8"))
    return "\n\n".join(sheets)


def _write_pdf(html_source: str, css_source: str, target: Path, when: date) -> int:
    """Render and return the page count. Pins the PDF clock for reproducibility."""
    from weasyprint import CSS, HTML  # imported late: see native.ensure_native_libraries

    epoch = int(datetime(when.year, when.month, when.day, tzinfo=UTC).timestamp())
    previous = os.environ.get("SOURCE_DATE_EPOCH")
    os.environ["SOURCE_DATE_EPOCH"] = str(epoch)
    try:
        document = HTML(string=html_source, base_url=str(PACKAGE_ROOT)).render(
            stylesheets=[CSS(string=css_source)]
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        # custom_metadata writes <meta> names beyond the standard ones, which is
        # where the provenance stamp travels.
        document.write_pdf(target, custom_metadata=True)
        return len(document.pages)
    finally:
        if previous is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = previous


def _page_count(html_source: str, css_source: str) -> int:
    from weasyprint import CSS, HTML

    return len(
        HTML(string=html_source, base_url=str(PACKAGE_ROOT))
        .render(stylesheets=[CSS(string=css_source)])
        .pages
    )


def render_bill(
    bill: Bill,
    company: Company,
    brand: Brand,
    assets: Path,
    target: Path,
    with_qr: bool = True,
    profile: Path | None = None,
    stamp: Stamp | None = None,
) -> RenderResult:
    """Render one bill to PDF, with ``stamp`` in its metadata if given.

    The Swiss QR payment part belongs at the foot of the last page. That is easy
    when the bill is one page, which these always are in practice. If the content
    ever runs longer, the payment part moves to its own final sheet — which the
    standard also permits — rather than being silently squeezed or repeated.
    """
    env = _environment(profile)
    template = env.get_template("bill.html.j2")
    text = strings(bill.language)
    vat_rate = company.effective_vat_rate

    context = {
        "bill": bill,
        "company": company,
        "text": text,
        "brand": brand,
        "language": bill.language,
        "issued_long": long_date(bill.date, bill.language),
        "issued_short": short_date(bill.date),
        "vat_rate": vat_rate,
        "vat_amount": bill.vat(vat_rate) if vat_rate else None,
        "total": bill.total(vat_rate),
        "client_country": country_name(bill.language, bill.client.address.country),
        "company_country": country_name(bill.language, company.address.country),
        "salutation": bill.client.salutation(bill.language) or text["fallback_salutation"],
        "qr_svg": None,
        "payment_layout": "none",
        "provenance": stamp.as_json() if stamp else "",
    }

    if not with_qr:
        html_source = template.render(**context)
        css_source = _stylesheet(brand, assets, "bill.css", profile)
        pages = _write_pdf(html_source, css_source, target, bill.date)
        return RenderResult(path=target, pages=pages, payment_layout="none")

    qr_svg = build_qr_svg(bill, company, bill.language)
    qr_data_uri = "data:image/svg+xml;base64," + base64.b64encode(qr_svg.encode("utf-8")).decode(
        "ascii"
    )

    # Pass one: how long is the body on its own? This decides where the payment
    # part can go, and it is cheaper than guessing and being wrong on a client
    # document.
    probe_source = template.render(**{**context, "payment_layout": "none"})
    base_css = _stylesheet(brand, assets, "bill.css", profile)
    body_pages = _page_count(probe_source, base_css)

    layout = "inline" if body_pages == 1 else "separate"
    html_source = template.render(**{**context, "qr_svg": qr_data_uri, "payment_layout": layout})
    css_source = _stylesheet(brand, assets, "bill.css", profile)
    pages = _write_pdf(html_source, css_source, target, bill.date)

    # The reserved 105 mm can itself push a full page over. Fall back rather
    # than ship a bill whose payment part landed on top of the totals.
    if layout == "inline" and pages > 1:
        layout = "separate"
        html_source = template.render(
            **{**context, "qr_svg": qr_data_uri, "payment_layout": layout}
        )
        pages = _write_pdf(html_source, css_source, target, bill.date)

    return RenderResult(path=target, pages=pages, payment_layout=layout)


def render_statement(
    statement: Statement,
    company: Company,
    brand: Brand,
    assets: Path,
    target: Path,
    template_name: str = "statement.html.j2",
    profile: Path | None = None,
) -> RenderResult:
    """Render the yearly accounts, or the figures sheet that accompanies them."""
    env = _environment(profile)
    template = env.get_template(template_name)
    text = strings(statement.language)
    prepared = statement.prepared_on or date(statement.year + 1, 1, 1)

    html_source = template.render(
        statement=statement,
        company=company,
        brand=brand,
        text=text,
        language=statement.language,
        prepared_long=long_date(prepared, statement.language),
        prepared_short=short_date(prepared),
        company_country=country_name(statement.language, company.address.country),
    )
    css_source = _stylesheet(brand, assets, "statement.css", profile)
    pages = _write_pdf(html_source, css_source, target, prepared)
    return RenderResult(path=target, pages=pages)
