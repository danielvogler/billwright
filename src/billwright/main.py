"""The `billwright` command line."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from .model import Brand, Company
from .native import ensure_native_libraries
from .paths import (
    DEFAULT_ASSETS,
    bill_target,
    default_out,
    legacy_archive_note,
    statement_dir,
    statement_stem,
)


def _profile(args: argparse.Namespace) -> Path:
    from .load import resolve_profile

    return resolve_profile(args.profile)


def _archive_dir(args: argparse.Namespace, profile: Path) -> Path:
    """Where ``--archive`` writes, resolved the same way the profile is.

    Only consulted when ``--archive`` was given, so an unarchived render never
    fails on an archive setting it is not going to use.
    """
    from .load import resolve_archive_dir

    return resolve_archive_dir(args.archive_dir, profile=profile)


def _warn_about_a_stranded_archive(archive_dir: Path) -> None:
    if note := legacy_archive_note(archive_dir):
        print(note, file=sys.stderr)


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

    archive_dir = _archive_dir(args, profile)
    if args.archive:
        _warn_about_a_stranded_archive(archive_dir)

    target = bill_target(
        company, bill, archive=args.archive, out=Path(args.out), archive_dir=archive_dir
    )

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

    archive_dir = _archive_dir(args, profile)
    if args.archive:
        _warn_about_a_stranded_archive(archive_dir)

    out_dir = statement_dir(
        args.year, archive=args.archive, out=Path(args.out), archive_dir=archive_dir
    )
    stem = statement_stem(company, args.year)

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
    from .scaffold import bill_template

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
    target.write_text(bill_template(str(number), client.key, company, rates), encoding="utf-8")
    print(f"{target}\nEdit the items, then: billwright bill {number}")
    return 0


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
    from .audit import audit

    report = audit(_profile(args))

    # Notes are true and not wrong, so they go to stdout; problems are what a
    # caller checking the exit code cares about, so they go to stderr.
    for note in report.notes:
        print(note)
    for problem in report.problems:
        print(problem, file=sys.stderr)

    if not report.ok:
        return 1
    print(f"ok — {report.bills} bill(s), no numbering gaps, no duplicates")
    return 0


def cmd_init_profile(args: argparse.Namespace) -> int:
    from .scaffold import write_profile

    target = Path(args.into)
    source = Path(args.source) if args.source else Path.cwd() / "example"
    try:
        written = write_profile(target, brand_source=source)
    except (FileExistsError, FileNotFoundError) as exc:
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
    parser.add_argument(
        "--assets",
        default=str(DEFAULT_ASSETS),
        help="directory holding fonts/ (default: the faces shipped with the package)",
    )
    parser.add_argument(
        "--out", default=str(default_out()), help="where drafts go (default: ./out)"
    )
    parser.add_argument(
        "--archive-dir",
        default=None,
        help=(
            "where --archive writes the ten-year record; otherwise "
            "$BILLWRIGHT_ARCHIVE, [tool.billwright] archive, then <profile>/archive"
        ),
    )
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
    init.add_argument(
        "--from",
        dest="source",
        default="",
        help="profile to take brand.toml from (default: ./example)",
    )
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
