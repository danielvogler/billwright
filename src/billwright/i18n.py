"""Document strings, de-CH and en.

Swiss German: ``ss`` never ``ß``. The Word originals had ``Vereinbarungsgemäß``
and ``Grüßen``, which are German-German spellings on a Zurich invoice.
"""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "de": {
        "invoice": "Rechnung",
        "invoice_number": "Rechnungsnummer",
        "date": "Datum",
        "service_date_note": "Rechnungsdatum entspricht Liefer-/Leistungsdatum",
        "position": "Position",
        "quantity": "Anzahl",
        "unit": "Einheit",
        "description": "Bezeichnung",
        "unit_price": "Einzelpreis",
        "line_total": "Gesamtpreis",
        "net": "Nettopreis",
        "vat": "MWST",
        "total": "Rechnungsbetrag",
        "intro": (
            "vielen Dank für Ihren Auftrag. Vereinbarungsgemäss berechnen wir "
            "Ihnen hiermit folgende Leistungen:"
        ),
        "terms": (
            "Bitte überweisen Sie den Rechnungsbetrag innerhalb von {days} Tagen "
            "auf unser unten genanntes Konto."
        ),
        "questions": "Für weitere Fragen stehen wir Ihnen sehr gerne zur Verfügung.",
        "closing": "Mit freundlichen Grüssen",
        "fallback_salutation": "Sehr geehrte Damen und Herren,",
        "hours": "Stunden",
        # Yearly statement
        "statement": "Jahresrechnung",
        "income_statement": "Erfolgsrechnung",
        "period": "Berichtsperiode",
        "revenue": "Ertrag",
        "revenue_consulting": "Ertrag aus Beratung",
        "expenses": "Aufwand",
        "profit": "Gewinn",
        "loss": "Verlust",
        "result": "Gewinn / Verlust",
        "assets": "Aktiven",
        "liabilities": "Passiven",
        "equity": "Eigenkapital",
        "net_worth": "Vermögensstand per 31.12.{year}",
        "total_label": "Total",
        "no_entries": "Keine Positionen",
        "entries": "Positionen",
        "place_date": "Ort, Datum",
        "signature": "Unterschrift",
        "prepared_by": "Erstellt von",
        "figures_title": "Kennzahlen für die Steuererklärung {year}",
        "figures_intro": (
            "Werte zur Übertragung in die Steuererklärung. Die vollständige "
            "Jahresrechnung liegt separat bei."
        ),
        "legal_basis": (
            "Buchführung nach Art. 957 Abs. 2 OR (Einnahmen, Ausgaben, "
            "Vermögenslage). Umsatz unter CHF 500’000."
        ),
    },
    "en": {
        "invoice": "Invoice",
        "invoice_number": "Invoice number",
        "date": "Date",
        "service_date_note": "Invoice date corresponds to the date of service",
        "position": "Item",
        "quantity": "Quantity",
        "unit": "Unit",
        "description": "Description",
        "unit_price": "Unit price",
        "line_total": "Amount",
        "net": "Net amount",
        "vat": "VAT",
        "total": "Total due",
        # English capitalises the first word after the salutation; German does
        # not, which is why the German string above starts lowercase and this
        # one does not. Carrying the German convention across is a tell that a
        # document was translated rather than written.
        "intro": (
            "Thank you for the engagement. As agreed, we are invoicing the following services:"
        ),
        "terms": ("Please transfer the total due within {days} days to the account shown below."),
        "questions": "We are happy to answer any further questions.",
        "closing": "Kind regards",
        "fallback_salutation": "Dear Sir or Madam,",
        "hours": "hours",
        # Yearly statement
        "statement": "Annual accounts",
        "income_statement": "Income statement",
        "period": "Reporting period",
        "revenue": "Revenue",
        "revenue_consulting": "Consulting revenue",
        "expenses": "Expenses",
        "profit": "Profit",
        "loss": "Loss",
        "result": "Profit / loss",
        "assets": "Assets",
        "liabilities": "Liabilities",
        "equity": "Equity",
        "net_worth": "Statement of assets as at 31.12.{year}",
        "total_label": "Total",
        "no_entries": "No entries",
        "entries": "entries",
        "place_date": "Place, date",
        "signature": "Signature",
        "prepared_by": "Prepared by",
        "figures_title": "Figures for the {year} tax return",
        "figures_intro": (
            "Values for transfer into the tax return. The full annual accounts "
            "are attached separately."
        ),
        "legal_basis": (
            "Accounts kept under Art. 957 para. 2 CO (receipts, payments, asset "
            "position). Turnover below CHF 500,000."
        ),
    },
}

#: Month names for the long date form used in the letter head.
MONTHS = {
    "de": (
        "Januar",
        "Februar",
        "März",
        "April",
        "Mai",
        "Juni",
        "Juli",
        "August",
        "September",
        "Oktober",
        "November",
        "Dezember",
    ),
    "en": (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ),
}

#: Canonical unit tokens. A bill writes `unit = "hours"`; the document shows the
#: word for its language. Anything not listed here is printed as written, so an
#: unusual unit needs no code change.
UNITS = {
    "hours": {"de": "Stunden", "en": "hours"},
    "days": {"de": "Tage", "en": "days"},
    "items": {"de": "Stück", "en": "items"},
    "flat": {"de": "Pauschal", "en": "flat rate"},
}


COUNTRY_NAMES = {
    "de": {"CH": "Schweiz", "DE": "Deutschland", "AT": "Österreich"},
    "en": {"CH": "Switzerland", "DE": "Germany", "AT": "Austria"},
}


def strings(language: str) -> dict[str, str]:
    """Strings for ``language``, falling back to German (the default locale here)."""
    return STRINGS.get(language, STRINGS["de"])


def unit_name(language: str, unit: str) -> str:
    """Translate a canonical unit token; pass anything else through unchanged."""
    entry = UNITS.get(unit)
    if entry is None:
        return unit
    return entry.get(language, entry["de"])


def country_name(language: str, code: str) -> str:
    return COUNTRY_NAMES.get(language, COUNTRY_NAMES["de"]).get(code, code)
