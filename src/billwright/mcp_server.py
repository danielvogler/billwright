"""MCP over the same engine the command line drives.

Optional, and deliberately thin: ``pip install billwright[mcp]``. The command
line remains the way in, and `AGENTS.md` remains the instructions. This exists
for one case the shell cannot cover — an agent with no terminal, in a chat
client or on a schedule, that still needs to issue a bill.

Three rules shaped it:

**It restates nothing.** The rules live in `AGENTS.md`, and this serves that
file verbatim as a resource rather than paraphrasing it into tool descriptions.
A second copy would drift, and the copy an agent reads would be the stale one.

**It computes nothing.** Every franc here comes from `money.py` by way of the
same loaders the CLI uses, so an invoice rendered over MCP is byte-identical to
one rendered from the shell. There is no code path in this file that could
arrive at a different number.

**It says which company it is billing as, every single time.** Resolution
happens once, at startup, and the answer is attached to every response. Billing
under the wrong company is worse than not billing, and a chat client shows no
working directory to notice it from.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .load import find_bill, load_bills, load_brand, load_client, load_company, load_rates
from .money import format_chf
from .paths import (
    DEFAULT_ASSETS,
    PACKAGE_ROOT,
    bill_target,
    default_out,
    statement_dir,
    statement_stem,
)

if TYPE_CHECKING:  # pragma: no cover - import cost is real, the annotation is not
    from fastmcp import FastMCP

#: The invoice, then the figures sheet. Order matters: `statement` renders both.
STATEMENT_TEMPLATES = (("", "statement.html.j2"), ("_-_Kennzahlen", "figures.html.j2"))


def _archive_dir(profile: Path, explicit: Path | None) -> Path:
    """The same resolution the CLI performs, so neither can drift from the other."""
    from .load import resolve_archive_dir

    return resolve_archive_dir(explicit, profile=profile)


def _amounts(value: Any) -> dict[str, str]:
    """One amount, twice: exact for arithmetic, Swiss-formatted for a human.

    JSON has no decimal type, so the exact figure travels as a string. Anything
    that reads ``chf`` and re-parses it has already lost the guarantee this
    tool exists to provide.
    """
    return {"exact": str(value), "chf": format_chf(value)}


def summarise(profile: Path) -> dict[str, Any]:
    """Which company this server is billing as, and whether it can.

    The orientation call. Everything else repeats ``profile`` so that an agent
    which skipped this one still cannot misattribute an invoice.
    """
    company = load_company(profile)
    brand = load_brand(profile)
    return {
        "profile": str(profile),
        "company": company.name,
        "vat_registered": company.vat_registered,
        "vat_rate": str(company.effective_vat_rate),
        "wordmark": dict(brand.wordmark),
        "clients": sorted(path.stem for path in (profile / "clients").glob("*.toml")),
        "services": sorted(load_rates(profile)),
    }


def bill_list(profile: Path, year: int | None = None) -> dict[str, Any]:
    """Every bill issued, with its computed total and whether it was paid."""
    company = load_company(profile)
    vat_rate = company.effective_vat_rate
    bills = sorted(load_bills(profile, year), key=lambda b: (b.date, b.number))
    return {
        "profile": str(profile),
        "company": company.name,
        "bills": [
            {
                "number": bill.number,
                "date": bill.date.isoformat(),
                "client": bill.client.address.name,
                "total": _amounts(bill.total(vat_rate)),
                "paid_on": bill.paid_on.isoformat() if bill.paid_on else None,
            }
            for bill in bills
        ],
    }


def bill_detail(profile: Path, number: str) -> dict[str, Any]:
    """One bill's line items and the total they come to.

    The total is computed here and not stored anywhere, which is the point: a
    caller cannot be handed a figure that disagrees with the lines above it.
    """
    company = load_company(profile)
    bill = find_bill(profile, number)
    vat_rate = company.effective_vat_rate
    return {
        "profile": str(profile),
        "company": company.name,
        "number": bill.number,
        "date": bill.date.isoformat(),
        "client": bill.client.address.name,
        "project": bill.project,
        "language": bill.language,
        "terms_days": bill.terms_days,
        "paid_on": bill.paid_on.isoformat() if bill.paid_on else None,
        "items": [
            {
                "description": item.description,
                "quantity": str(item.quantity),
                "unit": item.unit,
                "unit_price": _amounts(item.unit_price),
                "total": _amounts(item.total),
            }
            for item in bill.items
        ],
        "net": _amounts(bill.net),
        "vat": _amounts(bill.vat(vat_rate)),
        "total": _amounts(bill.total(vat_rate)),
    }


def scaffold(profile: Path, client: str, year: int | None = None) -> dict[str, Any]:
    """Write the next bill number for a client, with no line items in it.

    Returns the path to edit. It deliberately does not accept amounts: rates
    come from ``rates.toml`` and quantities are the operator's to state.
    """
    from datetime import date

    from .audit import audit
    from .load import bill_paths
    from .numbering import next_number
    from .scaffold import bill_template

    company = load_company(profile)
    load_client(profile, client)  # fail here, rather than in a half-written file
    year = year or date.today().year
    number = next_number([path.stem for path in bill_paths(profile)], year)

    target = profile / "bills" / str(year) / f"{number}.toml"
    if target.exists():
        raise FileExistsError(f"{target} already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        bill_template(str(number), client, company, load_rates(profile)), encoding="utf-8"
    )
    return {
        "profile": str(profile),
        "company": company.name,
        "number": str(number),
        "path": str(target),
        "bills": audit(profile).bills,
    }


def render_bill(
    profile: Path,
    number: str,
    *,
    language: str | None = None,
    archive: bool = False,
    assets: Path = DEFAULT_ASSETS,
    out: Path | None = None,
    archive_dir: Path | None = None,
) -> dict[str, Any]:
    """Render one invoice to a PDF.

    ``archive=True`` writes the permanent copy instead of a draft. That is the
    ten-year record under ``OR Art. 958f`` and is never edited afterwards, so it
    is a separate decision from rendering — exactly as `make bill` and
    `make archive` are two commands and not one.
    """
    from .provenance import bill_stamp, write_record
    from .render import render_bill as render

    company = load_company(profile)
    brand = load_brand(profile)
    bill = find_bill(profile, number)
    if language:
        bill = bill.model_copy(update={"language": language})

    target = bill_target(
        company,
        bill,
        archive=archive,
        out=out if out is not None else default_out(),
        archive_dir=_archive_dir(profile, archive_dir),
    )
    stamp = bill_stamp(profile, bill, brand, qr=True)
    result = render(bill, company, brand, assets, target, True, profile, stamp)
    if archive:
        write_record(result.path, stamp)
    return {
        "profile": str(profile),
        "company": company.name,
        "number": bill.number,
        "path": str(result.path),
        "pages": result.pages,
        "payment_layout": result.payment_layout,
        "archived": archive,
        "total": _amounts(bill.total(company.effective_vat_rate)),
    }


def render_statement(
    profile: Path,
    year: int,
    *,
    language: str | None = None,
    place: str | None = None,
    archive: bool = False,
    assets: Path = DEFAULT_ASSETS,
    out: Path | None = None,
    archive_dir: Path | None = None,
) -> dict[str, Any]:
    """Render a year's accounts: the Jahresrechnung and the figures sheet.

    Revenue is aggregated from bills by ``paid_on``, so a December invoice
    settled in January belongs to the following year. That is the receipts and
    payments basis (``OR Art. 957 II``), and it is decided in `statement.py`
    rather than here.
    """
    from .render import render_statement as render
    from .statement import build_statement

    company = load_company(profile)
    brand = load_brand(profile)
    # The same defaults the CLI declares, spelled here because `None` is how an
    # MCP client says "not given" and `build_statement` takes strings.
    statement = build_statement(
        profile, year, company, language=language or "de", place=place or ""
    )

    directory = statement_dir(
        year,
        archive=archive,
        out=out if out is not None else default_out(),
        archive_dir=_archive_dir(profile, archive_dir),
    )
    stem = statement_stem(company, year)
    rendered = [
        render(
            statement, company, brand, assets, directory / f"{stem}{suffix}.pdf", template, profile
        )
        for suffix, template in STATEMENT_TEMPLATES
    ]
    return {
        "profile": str(profile),
        "company": company.name,
        "year": year,
        "paths": [str(result.path) for result in rendered],
        "archived": archive,
        "is_nil": statement.is_nil,
        "bill_count": statement.bill_count,
        "revenue": _amounts(statement.revenue),
        "expenses": _amounts(statement.expenses),
        "profit": _amounts(statement.profit),
        "equity": _amounts(statement.equity),
    }


def check(profile: Path) -> dict[str, Any]:
    """Read the bills as a numbered series and report what an auditor would ask."""
    from .audit import audit

    report = audit(profile)
    return {
        "profile": str(profile),
        "ok": report.ok,
        "bills": report.bills,
        "problems": list(report.problems),
        "notes": list(report.notes),
    }


def doctor(profile: Path, assets: Path = DEFAULT_ASSETS) -> dict[str, Any]:
    """Is the profile complete, and is the IBAN a real one?

    Everything at once, on purpose: a caller who fixes one field per run gives
    up before the profile is valid.
    """
    from .doctor import Level, diagnose

    problems = diagnose(profile, assets)
    return {
        "profile": str(profile),
        "ready": not any(p.level is Level.ERROR for p in problems),
        "errors": [str(p) for p in problems if p.level is Level.ERROR],
        "warnings": [str(p) for p in problems if p.level is not Level.ERROR],
    }


#: `AGENTS.md` is tracked once, at the repository root, and force-included into
#: the wheel at build time (see pyproject.toml). One tracked copy, because a
#: second one is the copy that goes stale — which is the rule this file exists
#: to honour. Installed, only the first of these exists; in a checkout, only the
#: second.
MANUAL_CANDIDATES = (PACKAGE_ROOT / "AGENTS.md", PACKAGE_ROOT.parents[1] / "AGENTS.md")


def manual() -> str:
    """`AGENTS.md`, verbatim. Raises rather than paraphrasing if it is absent."""
    for candidate in MANUAL_CANDIDATES:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    looked = ", ".join(str(candidate) for candidate in MANUAL_CANDIDATES)
    raise FileNotFoundError(
        f"AGENTS.md is not installed alongside billwright (looked in: {looked}). "
        "The operating manual is served verbatim rather than paraphrased, so there "
        "is no fallback text to return. Reinstall billwright[mcp]."
    )


def build_server(
    profile: Path,
    *,
    assets: Path = DEFAULT_ASSETS,
    out: Path | None = None,
) -> FastMCP:
    """Wire the functions above onto a FastMCP server.

    The profile is bound here, once, rather than being a parameter on every
    tool: a tool that takes a profile is a tool an agent can point at the wrong
    company.
    """
    from fastmcp import FastMCP

    server: FastMCP = FastMCP(
        name="billwright",
        instructions=(
            "Swiss QR invoices and year-end accounts, rendered from TOML in a profile "
            f"directory. This server bills as the company in {profile}. Read the "
            "billwright://agents resource before setting anything up: it is the "
            "operating manual and this server does not repeat it. Never invent a "
            "financial value — an invented IBAN pays a stranger. Ask instead."
        ),
    )

    @server.resource("billwright://agents", mime_type="text/markdown")
    def agents() -> str:
        """AGENTS.md — how to operate billwright. The single source, served verbatim."""
        return manual()

    @server.tool
    def profile_info() -> dict[str, Any]:
        """Which company this server bills as, its clients, services and VAT status."""
        return summarise(profile)

    @server.tool
    def list_bills(year: int | None = None) -> dict[str, Any]:
        """Every bill issued, with computed totals and paid status."""
        return bill_list(profile, year)

    @server.tool
    def show_bill(number: str) -> dict[str, Any]:
        """One bill's line items and the total computed from them."""
        return bill_detail(profile, number)

    @server.tool
    def new_bill(client: str, year: int | None = None) -> dict[str, Any]:
        """Scaffold the next bill number for a client. Writes a file with no amounts."""
        return scaffold(profile, client, year)

    @server.tool
    def bill(number: str, language: str | None = None, archive: bool = False) -> dict[str, Any]:
        """Render one invoice to PDF. `archive=True` writes the permanent ten-year copy."""
        return render_bill(
            profile, number, language=language, archive=archive, assets=assets, out=out
        )

    @server.tool
    def statement(
        year: int,
        language: str | None = None,
        place: str | None = None,
        archive: bool = False,
    ) -> dict[str, Any]:
        """Render a year's accounts. `archive=True` writes the permanent copy."""
        return render_statement(
            profile,
            year,
            language=language,
            place=place,
            archive=archive,
            assets=assets,
            out=out,
        )

    @server.tool
    def check_bills() -> dict[str, Any]:
        """Numbering gaps, duplicates and empty bills."""
        return check(profile)

    @server.tool
    def check_profile() -> dict[str, Any]:
        """Whether the profile is complete and the IBAN valid."""
        return doctor(profile, assets)

    return server


def main(argv: list[str] | None = None) -> int:
    """Run the server on stdio, which is how an MCP client launches it."""
    from .load import ProfileError, resolve_profile

    parser = argparse.ArgumentParser(
        prog="billwright-mcp", description="Serve billwright over MCP (stdio)."
    )
    parser.add_argument("--profile", help="profile directory to bill from")
    parser.add_argument("--assets", default=str(DEFAULT_ASSETS), help="assets directory")
    parser.add_argument("--out", default=str(default_out()), help="where drafts are written")
    args = parser.parse_args(argv)

    try:
        profile = resolve_profile(args.profile)
    except ProfileError as exc:
        # stderr, not stdout: stdout is the MCP transport, and a message on it
        # is a protocol error rather than an error message.
        parser.error(str(exc))

    build_server(profile, assets=Path(args.assets), out=Path(args.out)).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
