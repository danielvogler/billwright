"""The `billwright` command line."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from .model import Brand, Company
from .native import ensure_native_libraries

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSETS = REPO_ROOT / "assets"
DEFAULT_OUT = REPO_ROOT / "out"
ARCHIVE = REPO_ROOT / "archive"


def _slug(text: str) -> str:
    keep = [c if c.isalnum() else "_" for c in text]
    return "".join(keep).strip("_").replace("__", "_")


def _profile(args: argparse.Namespace) -> Path:
    from .load import resolve_profile

    return resolve_profile(args.profile)


def _load_context(profile: Path) -> tuple[Company, Brand]:
    from .load import load_brand, load_company

    return load_company(profile), load_brand(profile)


def cmd_bill(args: argparse.Namespace) -> int:
    from .load import find_bill
    from .render import render_bill

    profile = _profile(args)
    company, brand = _load_context(profile)
    bill = find_bill(profile, args.number)
    if args.language:
        bill = bill.model_copy(update={"language": args.language})

    filename = f"{_slug(company.name)}_-_{bill.number}.pdf"
    target = (ARCHIVE / "bills" / str(bill.year) if args.archive else Path(args.out)) / filename

    result = render_bill(bill, company, brand, Path(args.assets), target, not args.no_qr, profile)
    print(f"{result.path}  ({result.pages} page(s), payment part: {result.payment_layout})")
    if result.pages > 1:
        print(
            "  note: the invoice body runs past one page, so the payment part "
            "moved to its own sheet.",
            file=sys.stderr,
        )
    return 0


def cmd_statement(args: argparse.Namespace) -> int:
    from .render import render_statement
    from .statement import build_statement

    profile = _profile(args)
    company, brand = _load_context(profile)
    statement = build_statement(
        profile, args.year, company, language=args.language, place=args.place
    )

    out_dir = ARCHIVE / "statements" / str(args.year) if args.archive else Path(args.out)
    stem = f"{_slug(company.name)}_-_Jahresrechnung_{args.year}"

    targets = [(f"{stem}.pdf", "statement.html.j2")]
    if not args.no_figures:
        targets.append((f"{stem}_-_Kennzahlen.pdf", "figures.html.j2"))

    for filename, template in targets:
        result = render_statement(
            statement, company, brand, Path(args.assets), out_dir / filename, template, profile
        )
        print(f"{result.path}  ({result.pages} page(s))")

    if statement.is_nil:
        print(f"  {args.year} is a nil year: revenue, expenses and profit are all CHF 0.00.")
    else:
        print(
            f"  {args.year}: revenue {statement.revenue}, expenses "
            f"{statement.expenses}, profit {statement.profit}"
        )
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    from .load import bill_paths, load_client, load_rates
    from .numbering import next_number

    profile = _profile(args)
    company, _ = _load_context(profile)
    client = load_client(profile, args.client)
    rates = load_rates(profile)

    year = args.year or date.today().year
    existing = [path.stem for path in bill_paths(profile)]
    number = next_number(existing, year)

    target = profile / "bills" / str(year) / f"{number}.toml"
    if target.exists():
        print(f"{target} already exists", file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(_bill_template(str(number), client.key, company, rates), encoding="utf-8")
    print(f"{target}\nEdit the items, then: billwright bill {number}")
    return 0


def _bill_template(number: str, client_key: str, company: Company, rates: dict) -> str:
    """A scaffold that renders as written.

    The service name comes from the profile's own rates. Hardcoding one here
    put a company's service category in the engine and, worse, scaffolded a
    bill that failed on 'unknown service' the first time a new user ran it —
    the very first command after setting up a profile.
    """
    known = sorted(rates)
    if known:
        priced = f'service = "{known[0]}"'
        options = f"# services in this profile: {', '.join(known)}"
    else:
        # No rates.toml: price the line directly rather than name a rate that
        # does not exist.
        priced = 'unit_price = "0.00"'
        options = "# no rates.toml in this profile, so the price is on the line"

    return f'''# {number}
number = "{number}"
date = {date.today().isoformat()}
client = "{client_key}"
language = "{company.default_language}"
terms_days = {company.default_terms_days}
project = ""

# `service` looks the rate up in rates.toml; `unit_price` overrides it.
{options}
[[items]]
description = ""
quantity = 0.0
unit = "hours"
{priced}
'''


def cmd_list(args: argparse.Namespace) -> int:
    from .load import load_bills
    from .money import format_chf

    profile = _profile(args)
    company, _ = _load_context(profile)
    bills = load_bills(profile, args.year)
    if not bills:
        scope = f" for {args.year}" if args.year else ""
        print(f"no bills{scope}")
        return 0

    vat_rate = company.effective_vat_rate
    total = Decimal("0")
    for bill in sorted(bills, key=lambda b: (b.date, b.number)):
        amount = bill.total(vat_rate)
        total += amount
        status = f"paid {bill.paid_on}" if bill.paid_on else "open"
        print(
            f"{bill.number}  {bill.date}  {format_chf(amount):>16}  "
            f"{status:<14}  {bill.client.address.name}"
        )
    print(f"{'':<12}{'':<12}{format_chf(total):>16}  total ({len(bills)} bills)")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from .load import bill_paths, load_bills, load_expenses
    from .numbering import find_duplicates, find_gaps

    profile = _profile(args)
    numbers = [path.stem for path in bill_paths(profile)]
    problems = 0

    duplicates = find_duplicates(numbers)
    if duplicates:
        problems += 1
        print(f"duplicate bill numbers: {', '.join(duplicates)}", file=sys.stderr)

    years = {int(path.parent.name) for path in bill_paths(profile)}
    for year in sorted(years):
        # Numbers issued before this tool existed are not gaps — they are Word
        # files in a folder somewhere. They must still be declared, so that a
        # genuinely missing number is never mistaken for one of them.
        _, year_data = load_expenses(profile, year)
        elsewhere = set(year_data.get("bills_issued_elsewhere", []))
        if elsewhere:
            print(f"{year}: {len(elsewhere)} bill(s) issued before migration, not in this repo")
        gaps = [g for g in find_gaps(numbers + sorted(elsewhere), year) if str(g) not in elsewhere]
        if gaps:
            problems += 1
            print(
                f"{year}: gaps in the numbering: {', '.join(str(g) for g in gaps)}",
                file=sys.stderr,
            )

    for bill in load_bills(profile):
        if str(bill.number) != f"{bill.number}":
            continue
        if not bill.items:
            problems += 1
            print(f"{bill.number}: no line items", file=sys.stderr)
        if bill.net <= 0:
            problems += 1
            print(f"{bill.number}: net amount is {bill.net}", file=sys.stderr)

    if problems:
        return 1
    print(f"ok — {len(numbers)} bill(s), no numbering gaps, no duplicates")
    return 0


def cmd_init_profile(args: argparse.Namespace) -> int:
    from .scaffold import write_profile

    target = Path(args.into)
    source = Path(args.source) if args.source else REPO_ROOT / "example"
    try:
        written = write_profile(target, brand_source=source)
    except FileExistsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for path in written:
        print(path)
    print(
        f"\nFill in the required fields, then: billwright --profile {target} doctor\n"
        "It lists everything still missing or wrong, all at once."
    )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .doctor import Level, diagnose

    profile = _profile(args)
    problems = diagnose(profile, Path(args.assets))

    errors = [p for p in problems if p.level is Level.ERROR]
    warnings = [p for p in problems if p.level is Level.WARNING]

    # Everything at once, on purpose: a user who fixes one field per run gives
    # up before the profile is valid.
    for problem in [*errors, *warnings]:
        print(problem, file=sys.stderr if problem.level is Level.ERROR else sys.stdout)

    if errors:
        print(
            f"\n{len(errors)} error(s), {len(warnings)} warning(s) in {profile}",
            file=sys.stderr,
        )
        return 1
    print(f"{profile}: ready to bill" + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="billwright",
        description="Generate bills and yearly statements.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help=(
            "profile directory; otherwise $BILLWRIGHT_PROFILE, "
            "[tool.billwright] profile, ./data, then ./example"
        ),
    )
    parser.add_argument("--assets", default=str(DEFAULT_ASSETS), help="assets directory")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    sub = parser.add_subparsers(dest="command", required=True)

    bill = sub.add_parser("bill", help="render one bill")
    bill.add_argument("number", help="bill number, e.g. RE-26001")
    bill.add_argument("--archive", action="store_true", help="write into archive/ instead of out/")
    bill.add_argument("--no-qr", action="store_true", help="omit the Swiss QR payment part")
    bill.add_argument("--language", default="", help="override the bill's language, e.g. en")
    bill.set_defaults(func=cmd_bill)

    statement = sub.add_parser("statement", help="render the yearly accounts")
    statement.add_argument("year", type=int)
    statement.add_argument("--language", default="de")
    statement.add_argument("--place", default="")
    statement.add_argument("--archive", action="store_true")
    statement.add_argument("--no-figures", action="store_true", help="skip the figures sheet")
    statement.set_defaults(func=cmd_statement)

    new = sub.add_parser("new", help="scaffold the next bill")
    new.add_argument("--client", required=True)
    new.add_argument("--year", type=int)
    new.set_defaults(func=cmd_new)

    listing = sub.add_parser("list", help="list issued bills")
    listing.add_argument("--year", type=int)
    listing.set_defaults(func=cmd_list)

    check = sub.add_parser("check", help="numbering and sanity checks")
    check.set_defaults(func=cmd_check)

    doctor = sub.add_parser("doctor", help="validate the profile and the environment")
    doctor.set_defaults(func=cmd_doctor)

    init = sub.add_parser("init-profile", help="write an empty profile to fill in")
    init.add_argument("--into", default="data", help="where to create it (default: data)")
    init.add_argument("--from", dest="source", default="", help="profile to take brand.toml from")
    init.set_defaults(func=cmd_init_profile)

    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_native_libraries(argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as exc:  # surfaced as a message, not a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
