"""The domain objects. Frozen: a bill that has been issued does not change.

Nothing in this module knows about any particular company. Every company fact
arrives from the profile directory (see ``load.py``), which is what lets the
same engine bill for a second company.

**Validation lives here, once.** These are Pydantic models rather than plain
dataclasses so that the loader, ``doctor`` and anything built on top read the
same schema instead of keeping four drifting copies of what a valid company is.
Two consequences worth stating:

- **Every value passes through ``money()`` or ``quantity()`` before it becomes a
  ``Decimal``.** ``tomllib`` returns real floats, and Pydantic would happily
  coerce ``0.1`` into ``Decimal('0.1000000000000000055511151231257827')``.
  ``BeforeValidator`` puts the string conversion in front of that, which is the
  whole reason ``money.py`` exists.
- **Swiss QR bill limits are field types, not checks someone remembers to run.**
  A name over 70 characters or a country code that is not two letters produces a
  payment part the bank rejects — discovered after the invoice was sent.
"""

from __future__ import annotations

# Imported as a module, not `from datetime import date`: Bill has a field
# named `date`, which shadows the type for every annotation after it.
import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from .money import money, quantity

#: A monetary amount. `money()` is the coercion authority: it takes the value
#: through `str` so a TOML float cannot arrive as binary noise.
Money = Annotated[Decimal, BeforeValidator(money)]

#: A quantity of something billable — hours, items. Same guarantee, different
#: rounding: 12.5 hours is not rounded to rappen.
Quantity = Annotated[Decimal, BeforeValidator(quantity)]

# Swiss QR bill maximum field lengths, from the Implementation Guidelines.
QrName = Annotated[str, Field(max_length=70)]
QrStreet = Annotated[str, Field(max_length=70)]
QrHouseNumber = Annotated[str, Field(max_length=16)]
QrPostalCode = Annotated[str, Field(max_length=16)]
QrCity = Annotated[str, Field(max_length=35)]
CountryCode = Annotated[str, Field(pattern=r"^[A-Z]{2}$")]


class Frozen(BaseModel):
    """An issued document does not change, and neither do its parts."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Address(Frozen):
    """A postal address, split the way the Swiss QR bill needs it."""

    name: QrName
    street: QrStreet
    house_number: QrHouseNumber
    postal_code: QrPostalCode
    city: QrCity
    country: CountryCode = "CH"
    #: Optional lines shown above the street on the document (department, attn).
    lines: tuple[str, ...] = ()

    @property
    def street_line(self) -> str:
        return f"{self.street} {self.house_number}".strip()

    @property
    def city_line(self) -> str:
        return f"{self.postal_code} {self.city}".strip()

    def as_block(self, country_name: str | None = None) -> tuple[str, ...]:
        """The address as document lines, top to bottom."""
        block = (self.name, *self.lines, self.street_line, self.city_line)
        return (*block, country_name) if country_name else block


class Company(Frozen):
    """The issuer. Loaded from ``<profile>/company.toml``."""

    name: str
    #: Who signs. Printed in the return address and the signature, and nowhere
    #: in the payment part: for a GmbH or an AG the signer is not the account
    #: holder.
    person: str = ""
    address: Address
    email: str = ""
    iban: str
    bank: str = ""
    bic: str = ""
    website: str = ""
    phone: str = ""
    #: Swiss business identification number (CHE-...). Omitted from the document
    #: when empty, which is correct for a sole proprietorship that has none.
    uid: str = ""
    #: VAT registration. Below the CHF 100'000 threshold this stays False and no
    #: VAT block is rendered — the shape the current bills already have.
    vat_registered: bool = False
    vat_rate: Money = Decimal("0")
    legal_form: str = ""
    default_terms_days: int = 14
    default_language: str = "de"
    #: ``[qr] creditor_name``: the account holder, when it is not
    #: ``address.name``, e.g. a sole proprietor whose account is in their own
    #: name rather than the trading name. Empty: ``address.name``.
    qr_creditor_name: QrName = ""

    @property
    def creditor_name(self) -> str:
        """The name the bank matches against the account holder."""
        return self.qr_creditor_name or self.address.name

    @property
    def effective_vat_rate(self) -> Decimal:
        """The rate that actually applies. Zero unless registered.

        One place decides this. Spelling it inline as
        ``vat_rate if vat_registered else 0`` produced an ``int`` in some call
        sites and a ``Decimal`` in others, which is exactly the float-adjacent
        drift `money.py` exists to prevent.
        """
        return self.vat_rate if self.vat_registered else Decimal("0")

    @property
    def iban_compact(self) -> str:
        return self.iban.replace(" ", "")


class Client(Frozen):
    """A billing counterparty. Loaded from ``<profile>/clients/<key>.toml``."""

    key: str
    address: Address
    #: Person addressed in the salutation, e.g. "Prof. Dr. R. Muster".
    contact: str = ""
    #: Full salutation line per language. Explicit rather than assembled,
    #: because honorifics do not compose reliably from a name and a gender flag
    #: — and a German salutation on an English invoice is exactly the kind of
    #: detail a client notices.
    salutations: dict[str, str] = Field(default_factory=dict)
    language: str = "de"
    reference: str = ""

    def salutation(self, language: str) -> str:
        """The salutation for ``language``, falling back to the client's own."""
        return self.salutations.get(language) or self.salutations.get(self.language, "")


class LineItem(Frozen):
    """One billable line."""

    description: str
    quantity: Quantity
    unit: str = "hours"
    unit_price: Money

    @property
    def total(self) -> Decimal:
        return money(self.quantity * self.unit_price)


class Bill(Frozen):
    """An invoice. ``number`` is the identity; see ``numbering.py``."""

    number: str
    date: datetime.date
    client: Client
    items: tuple[LineItem, ...]
    language: str = "de"
    terms_days: int = 14
    #: Free note rendered above the signature, optional.
    note: str = ""
    #: Set when the money arrives. Decides which year the revenue counts in —
    #: see `statement.py`.
    paid_on: datetime.date | None = None
    project: str = ""

    @property
    def net(self) -> Decimal:
        return money(sum((item.total for item in self.items), Decimal("0")))

    def vat(self, rate: Decimal) -> Decimal:
        return money(self.net * rate / Decimal("100"))

    def total(self, vat_rate: Decimal = Decimal("0")) -> Decimal:
        return money(self.net + self.vat(vat_rate))

    @property
    def year(self) -> int:
        return self.date.year


class ExpenseItem(Frozen):
    """A business expense for the yearly statement."""

    description: str
    amount: Money


class Statement(Frozen):
    """A year's Erfolgsrechnung plus Vermögensstand.

    Deliberately supports the nil case as a real result: a year with no mandates
    is a statement of zeros, not an absence of one.
    """

    year: int
    revenue_lines: tuple[tuple[str, Money], ...] = ()
    expense_lines: tuple[ExpenseItem, ...] = ()
    assets: tuple[tuple[str, Money], ...] = ()
    liabilities: tuple[tuple[str, Money], ...] = ()
    language: str = "de"
    #: Prose explaining the year, rendered under the tables. A table of zeros
    #: invites a question; one sentence answers it in advance.
    note: str = ""
    place: str = ""
    prepared_on: datetime.date | None = None
    bill_count: int = 0

    @property
    def revenue(self) -> Decimal:
        return money(sum((amount for _, amount in self.revenue_lines), Decimal("0")))

    @property
    def expenses(self) -> Decimal:
        return money(sum((item.amount for item in self.expense_lines), Decimal("0")))

    @property
    def profit(self) -> Decimal:
        return money(self.revenue - self.expenses)

    @property
    def total_assets(self) -> Decimal:
        return money(sum((amount for _, amount in self.assets), Decimal("0")))

    @property
    def total_liabilities(self) -> Decimal:
        return money(sum((amount for _, amount in self.liabilities), Decimal("0")))

    @property
    def equity(self) -> Decimal:
        return money(self.total_assets - self.total_liabilities)

    @property
    def expense_pairs(self) -> tuple[tuple[str, Decimal], ...]:
        """Expenses in the same (label, amount) shape as the other ledger blocks."""
        return tuple((item.description, item.amount) for item in self.expense_lines)

    @property
    def is_nil(self) -> bool:
        return self.revenue == 0 and self.expenses == 0


class Brand(Frozen):
    """Visual tokens. Loaded from ``<profile>/brand.toml``.

    ``colors`` and ``wordmark`` are deliberately left as open mappings rather
    than schematised: a new company adds a token and the stylesheet picks it up
    with no Python change. Everything else in this module is strict; these two
    are the seam that keeps the engine generic.
    """

    colors: dict[str, str] = Field(default_factory=dict)
    font_family: str = "Inter"
    font_file: str = "fonts/InterVariable.ttf"
    wordmark: dict[str, str] = Field(default_factory=dict)
    #: The logo named by ``wordmark.mark``, read once at load time and carried
    #: as a data URI, so the rendered PDF is self-contained. Empty: no logo.
    mark: str = ""

    def css_variables(self) -> str:
        return "\n".join(f"  --{name}: {value};" for name, value in sorted(self.colors.items()))
