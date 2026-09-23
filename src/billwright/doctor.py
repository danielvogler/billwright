"""Check a profile and the environment, and report *everything* wrong at once.

The authority for "is this profile complete". Everything downstream — the setup
skill, an agent onboarding a company — loops against this exit code rather than
its own judgement, which is why it must report the full list rather than the
first failure: a user fixing one field per run gives up before the profile is
valid.

Three ideas decide what is checked and how it is reported:

- **The IBAN is the highest-stakes field in the system.** A transposed digit
  sends money to a stranger, and nobody retypes a scanned QR code to notice.
  It is checked with mod-97 rather than a length or a regex.
- **Unanswered is not the same as answered-empty.** `vat_registered` missing is
  *unknown*, not `false`: silently omitting VAT when registered means
  under-invoicing, and the difference is still owed. An empty `uid` is
  legitimately correct for a sole proprietorship that has none.
- **A wrong document is worse than no document.** A non-Swiss issuer fails
  clearly rather than emitting a payment part that no bank will accept.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .fonts import describe_missing, missing_faces
from .native import missing_native_library_hint

# Swiss QR bill field limits, from the Implementation Guidelines. Exceeding one
# does not raise — it produces a payment part a bank rejects, which is found out
# after the invoice has been sent.
QR_LIMITS = {
    "name": 70,
    "street": 70,
    "house_number": 16,
    "postal_code": 16,
    "city": 35,
}


class Level(Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Problem:
    level: Level
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.value}: {self.where}: {self.message}"


def _read(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _check_iban(raw: str, problems: list[Problem]) -> None:
    compact = raw.replace(" ", "").upper()
    if not compact:
        problems.append(Problem(Level.ERROR, "company.toml", "iban is missing"))
        return

    try:
        from stdnum import iban as iban_module
    except ImportError:  # pragma: no cover - a transitive dep of qrbill
        problems.append(
            Problem(
                Level.WARNING,
                "company.toml",
                "python-stdnum absent, IBAN checksum not checked",
            )
        )
        return

    if not iban_module.is_valid(compact):
        # Deliberately does not echo the value: a wrong IBAN is still a bank
        # account number, and this output gets pasted into issues and logs.
        problems.append(
            Problem(
                Level.ERROR,
                "company.toml",
                "iban fails its mod-97 checksum — check it against your bank statement, "
                "digit by digit. A transposed digit pays a stranger.",
            )
        )
    elif not compact.startswith("CH") and not compact.startswith("LI"):
        problems.append(
            Problem(
                Level.ERROR,
                "company.toml",
                f"iban is {compact[:2]}, but this generates Swiss QR bills, "
                "which require a CH or LI account",
            )
        )


def _check_address(where: str, address: dict, problems: list[Problem]) -> None:
    for field, limit in QR_LIMITS.items():
        value = str(address.get(field, ""))
        if not value:
            problems.append(Problem(Level.ERROR, where, f"address.{field} is missing"))
        elif len(value) > limit:
            problems.append(
                Problem(
                    Level.ERROR,
                    where,
                    f"address.{field} is {len(value)} characters; the Swiss QR bill "
                    f"allows {limit}, and a longer one is rejected by the bank",
                )
            )

    country = str(address.get("country", "CH"))
    if len(country) != 2 or not country.isupper():
        problems.append(
            Problem(
                Level.ERROR,
                where,
                f"address.country must be a two-letter code, got {country!r}",
            )
        )


def _check_creditor(data: dict, problems: list[Problem]) -> None:
    """The QR creditor must be the account holder, and only the user knows who that is.

    It is ``address.name`` unless ``[qr] creditor_name`` says otherwise. When
    the signer differs from the address name, either can be the holder: the
    entity for a GmbH, often the person for a sole proprietorship. The creditor
    was once taken from ``person``, so a profile written then may be relying on
    it. Unanswered, like ``vat_registered``, is asked about rather than guessed.
    """
    qr = data.get("qr", {})
    if not isinstance(qr, dict):
        problems.append(
            Problem(Level.ERROR, "company.toml", 'qr must be a table: [qr] creditor_name = "…"')
        )
        return
    creditor = str(qr.get("creditor_name", "")).strip()
    limit = QR_LIMITS["name"]
    if len(creditor) > limit:
        problems.append(
            Problem(
                Level.ERROR,
                "company.toml",
                f"qr.creditor_name is {len(creditor)} characters; the Swiss QR bill "
                f"allows {limit}, and a longer one is rejected by the bank",
            )
        )

    person = str(data.get("person", "")).strip()
    holder = str(data.get("address", {}).get("name", "")).strip()
    if person and holder and person != holder and not creditor.strip():
        problems.append(
            Problem(
                Level.WARNING,
                "company.toml",
                f"the QR payment part names {holder!r} (address.name) as the account "
                f"holder, not the signer {person!r}. Set [qr] creditor_name to the "
                "name your bank holds the account under — either one — to confirm it; "
                "a mismatch bounces the payment.",
            )
        )


def check_company(profile: Path) -> list[Problem]:
    problems: list[Problem] = []
    path = profile / "company.toml"
    if not path.is_file():
        return [Problem(Level.ERROR, "company.toml", f"missing: {path}")]

    data = _read(path)
    # `iban` is not in this loop: _check_iban reports its absence itself, with
    # the reason attached.
    if not str(data.get("name", "")).strip():
        problems.append(Problem(Level.ERROR, "company.toml", "name is missing"))

    _check_iban(str(data.get("iban", "")), problems)
    _check_address("company.toml", data.get("address", {}), problems)
    _check_creditor(data, problems)

    country = str(data.get("address", {}).get("country", "CH"))
    if country != "CH":
        problems.append(
            Problem(
                Level.ERROR,
                "company.toml",
                f"issuer country is {country}: this tool generates Swiss QR bills and "
                "cannot produce a valid payment part for a non-Swiss issuer",
            )
        )

    # Unanswered, not answered-false. Being registered and omitting VAT means
    # under-invoicing, and the amount is owed whether or not it was charged.
    if "vat_registered" not in data:
        problems.append(
            Problem(
                Level.ERROR,
                "company.toml",
                "vat_registered is unanswered. Set it to true or false explicitly — "
                "absent is not the same as false, and guessing it wrong under-invoices.",
            )
        )
    elif data.get("vat_registered") and not str(data.get("vat_rate", "")).strip("0. "):
        problems.append(
            Problem(Level.ERROR, "company.toml", "vat_registered is true but vat_rate is not set")
        )

    # An empty uid is correct for a sole proprietorship without one, so this is
    # a note rather than a failure.
    if not str(data.get("uid", "")).strip():
        problems.append(
            Problem(
                Level.WARNING,
                "company.toml",
                "uid is empty. Correct if you have no CHE number; otherwise it "
                "belongs on the invoice.",
            )
        )

    return problems


def check_clients(profile: Path) -> list[Problem]:
    problems: list[Problem] = []
    directory = profile / "clients"
    if not directory.is_dir() or not any(directory.glob("*.toml")):
        return [Problem(Level.WARNING, "clients/", "no clients yet — add one before billing")]

    for path in sorted(directory.glob("*.toml")):
        where = f"clients/{path.name}"
        data = _read(path)
        _check_address(where, data.get("address", {}), problems)
        if not data.get("salutation"):
            problems.append(
                Problem(Level.WARNING, where, "no salutation; the letter opens with a default")
            )
    return problems


def check_rates(profile: Path) -> list[Problem]:
    path = profile / "rates.toml"
    if not path.is_file():
        return [
            Problem(
                Level.WARNING,
                "rates.toml",
                "absent — every line item will need an explicit unit_price",
            )
        ]
    if not _read(path).get("hourly"):
        return [Problem(Level.WARNING, "rates.toml", "no [hourly] rates defined")]
    return []


def check_environment(assets: Path | None = None) -> list[Problem]:
    problems: list[Problem] = []

    if hint := missing_native_library_hint():
        problems.append(Problem(Level.ERROR, "environment", hint.splitlines()[0]))

    try:
        import weasyprint  # noqa: F401
    except OSError as exc:
        problems.append(
            Problem(Level.ERROR, "environment", f"WeasyPrint cannot load its libraries: {exc}")
        )
    except ImportError:
        problems.append(Problem(Level.ERROR, "environment", "WeasyPrint is not installed"))

    if assets is not None and (missing := missing_faces(assets)):
        # Named faces, not a non-empty directory: a fonts/ holding only OFL.txt
        # satisfied the old check and still rendered with a substituted face.
        problems.append(Problem(Level.ERROR, "environment", describe_missing(assets, missing)))
    return problems


def diagnose(profile: Path, assets: Path | None = None) -> list[Problem]:
    """Every problem with this profile and this machine, in one list."""
    return [
        *check_environment(assets),
        *check_company(profile),
        *check_clients(profile),
        *check_rates(profile),
    ]
