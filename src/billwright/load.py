"""Read the profile directory into the domain model.

This is the only boundary where untrusted-ish data enters, so every required
field is checked here and reported with the file it came from. A bill that is
wrong should fail to render, not render wrongly.
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .model import Address, Bill, Brand, Client, Company, ExpenseItem, LineItem
from .money import money

T = TypeVar("T", bound=BaseModel)

PROFILE_ENV = "BILLWRIGHT_PROFILE"
PROFILE_MARKER = "company.toml"


class ProfileError(Exception):
    """A profile file is missing or malformed."""


def is_profile_dir(path: Path) -> bool:
    """True only if ``path`` holds ``company.toml``.

    The directory existing is not enough. A half-built or empty ``data/`` must
    fall through to ``example/`` so that a fresh clone renders the sample
    instead of erroring — which is also why no ``.gitkeep`` may be committed
    under ``data/``, ``archive/`` or ``out/``.
    """
    return (path / PROFILE_MARKER).is_file()


def _configured_profile(root: Path) -> Path | None:
    """``[tool.billwright] profile`` from ``pyproject.toml``, if set."""
    path = root / "pyproject.toml"
    if not path.is_file():
        return None
    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path}: {exc}") from exc
    configured = data.get("tool", {}).get("billwright", {}).get("profile")
    if not configured:
        return None
    return root / str(configured)


def _requested(path: Path, source: str) -> Path:
    """Honour an explicitly requested profile, or fail naming what is wrong.

    A typo must never fall through to ``example/``: silently billing under the
    example company is a worse outcome than not billing at all.
    """
    if not is_profile_dir(path):
        raise ProfileError(f"{source} points at {path}, which has no {PROFILE_MARKER}")
    return path


def resolve_profile(
    explicit: str | Path | None = None,
    *,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    """Find the profile directory to bill from.

    In order: the ``--profile`` flag, ``$BILLWRIGHT_PROFILE``, the
    ``[tool.billwright] profile`` setting, ``./data``, ``./example``.

    The first two are requests and are honoured as given — a bad one is an
    error. The rest are candidates: each is used only if it holds
    ``company.toml``, so a fresh clone with no ``data/`` lands on ``example/``
    and renders the sample.

    Relative paths resolve against ``root``, which defaults to the working
    directory.
    """
    root = Path.cwd() if root is None else Path(root)
    environ = os.environ if env is None else env

    if explicit:
        return _requested(Path(explicit), "--profile")

    requested = environ.get(PROFILE_ENV, "").strip()
    if requested:
        return _requested(root / requested, f"${PROFILE_ENV}")

    candidates = [
        candidate
        for candidate in (_configured_profile(root), root / "data", root / "example")
        if candidate is not None
    ]
    for candidate in candidates:
        if is_profile_dir(candidate):
            return candidate

    tried = ", ".join(str(candidate) for candidate in candidates)
    raise ProfileError(
        f"no profile found (looked for {PROFILE_MARKER} in: {tried}). "
        f"Pass --profile, set ${PROFILE_ENV}, or create data/{PROFILE_MARKER}."
    )


def _read(path: Path) -> dict:
    if not path.exists():
        raise ProfileError(f"missing file: {path}")
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path}: {exc}") from exc


def _build(model: type[T], path: Path, **fields: Any) -> T:
    """Construct a model, reporting any failure against the file it came from.

    Pydantic's own message is precise about the field and useless about the
    source; a profile has half a dozen files and the answer to "which one" is
    the first thing anyone needs. Every failure is listed, not the first.
    """
    try:
        return model(**fields)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc']) or model.__name__}: {error['msg']}"
            for error in exc.errors()
        )
        raise ProfileError(f"{path}: {details}") from exc


def _require(data: dict, key: str, path: Path) -> Any:
    """The value at ``key``, or a ProfileError naming the file that lacks it.

    Typed ``Any`` deliberately: TOML is dynamic, the guarantee that this is a
    string or a table is the check right here plus the model it is handed to,
    and threading ``object`` through every call site buys casts rather than
    safety.
    """
    if key not in data:
        raise ProfileError(f"{path}: missing required key {key!r}")
    return data[key]


def _address(data: dict, path: Path) -> Address:
    for key in ("name", "street", "house_number", "postal_code", "city"):
        _require(data, key, path)
    return _build(
        Address,
        path,
        name=data["name"],
        street=data["street"],
        house_number=str(data["house_number"]),
        postal_code=str(data["postal_code"]),
        city=data["city"],
        country=data.get("country", "CH"),
        lines=tuple(data.get("lines", ())),
    )


def load_company(profile: Path) -> Company:
    path = profile / "company.toml"
    data = _read(path)
    address = _address(_require(data, "address", path), path)
    return _build(
        Company,
        path,
        name=_require(data, "name", path),
        person=data.get("person", ""),
        address=address,
        email=data.get("email", ""),
        iban=_require(data, "iban", path),
        bank=data.get("bank", ""),
        bic=data.get("bic", ""),
        website=data.get("website", ""),
        phone=data.get("phone", ""),
        uid=data.get("uid", ""),
        vat_registered=bool(data.get("vat_registered", False)),
        vat_rate=Decimal(str(data.get("vat_rate", "0"))),
        legal_form=data.get("legal_form", ""),
        default_terms_days=int(data.get("default_terms_days", 14)),
        default_language=data.get("default_language", "de"),
    )


def load_brand(profile: Path) -> Brand:
    path = profile / "brand.toml"
    data = _read(path)
    return _build(
        Brand,
        path,
        colors=dict(data.get("colors", {})),
        font_family=data.get("font_family", "Inter"),
        font_file=data.get("font_file", "fonts/InterVariable.ttf"),
        wordmark=dict(data.get("wordmark", {})),
    )


def load_client(profile: Path, key: str) -> Client:
    path = profile / "clients" / f"{key}.toml"
    data = _read(path)
    return _build(
        Client,
        path,
        key=key,
        address=_address(_require(data, "address", path), path),
        contact=data.get("contact", ""),
        salutations=_salutations(data.get("salutation", {})),
        language=data.get("language", "de"),
        reference=data.get("reference", ""),
    )


def _salutations(raw: object) -> dict[str, str]:
    """A salutation may be one string (all languages) or a table keyed by language."""
    if isinstance(raw, str):
        return {"de": raw, "en": raw} if raw else {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    raise ProfileError(f"'salutation' must be a string or a table, got {type(raw).__name__}")


def load_rates(profile: Path) -> dict[str, Decimal]:
    """Service category -> hourly rate. Lets a bill name a service, not a price."""
    path = profile / "rates.toml"
    if not path.exists():
        return {}
    data = _read(path)
    return {name: money(value) for name, value in data.get("hourly", {}).items()}


def load_bill(profile: Path, path: Path) -> Bill:
    """Load one bill TOML. ``unit_price`` may be omitted if ``service`` names a rate."""
    data = _read(path)
    client = load_client(profile, str(_require(data, "client", path)))
    rates = load_rates(profile)

    items: list[LineItem] = []
    for raw in _require(data, "items", path):
        if "unit_price" in raw:
            price = money(raw["unit_price"])
        else:
            service = raw.get("service")
            if service is None:
                raise ProfileError(
                    f"{path}: line {raw.get('description', '?')!r} needs "
                    "either 'unit_price' or 'service'"
                )
            if service not in rates:
                raise ProfileError(
                    f"{path}: unknown service {service!r}; "
                    f"known: {', '.join(sorted(rates)) or '(none)'}"
                )
            price = rates[service]
        items.append(
            _build(
                LineItem,
                path,
                description=_require(raw, "description", path),
                quantity=raw.get("quantity", 1),
                unit=raw.get("unit", "hours"),
                unit_price=price,
            )
        )

    issued = _require(data, "date", path)
    if not isinstance(issued, date):
        raise ProfileError(f"{path}: 'date' must be a TOML date (e.g. 2026-01-01)")

    # `paid_on` decides which tax year the money is income in, so a quoted
    # "2027-01-14" — a string, silently not a date — would drop the bill out of
    # every statement rather than fail. Check it here, at the boundary.
    paid_on = data.get("paid_on")
    if paid_on is not None and not isinstance(paid_on, date):
        raise ProfileError(
            f"{path}: 'paid_on' must be a TOML date (e.g. 2026-02-10), "
            f"got {type(paid_on).__name__}; it decides the year the revenue counts in"
        )

    return _build(
        Bill,
        path,
        number=str(_require(data, "number", path)),
        date=issued,
        client=client,
        items=tuple(items),
        language=data.get("language", client.language),
        terms_days=int(data.get("terms_days", 14)),
        note=data.get("note", ""),
        paid_on=paid_on,
        project=data.get("project", ""),
    )


def bill_paths(profile: Path, year: int | None = None) -> list[Path]:
    root = profile / "bills"
    if not root.exists():
        return []
    pattern = f"{year}/*.toml" if year else "*/*.toml"
    return sorted(root.glob(pattern))


def load_bills(profile: Path, year: int | None = None) -> list[Bill]:
    return [load_bill(profile, path) for path in bill_paths(profile, year)]


def find_bill(profile: Path, number: str) -> Bill:
    for path in bill_paths(profile):
        if path.stem.upper() == number.strip().upper():
            return load_bill(profile, path)
    raise ProfileError(f"no bill file for {number} under {profile / 'bills'}")


def load_expenses(profile: Path, year: int) -> tuple[list[ExpenseItem], dict]:
    """Expenses and balance figures for a year, from ``<profile>/years/<year>.toml``.

    Absent file means a year with no expenses recorded — which is a real answer,
    not an error. 2025 is exactly that case.
    """
    path = profile / "years" / f"{year}.toml"
    if not path.exists():
        return [], {}
    data = _read(path)
    expenses = [
        _build(ExpenseItem, path, description=raw["description"], amount=raw["amount"])
        for raw in data.get("expenses", [])
    ]
    return expenses, data
