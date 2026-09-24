"""Write an empty profile for someone to fill in.

The pattern this exists to support is: **deterministic scaffold, then an agent
fills in the values, then deterministic validation.** Code writes the file
structure and code checks the result; the judgement in the middle only has to
supply facts. An agent inventing the layout of a profile is how you get a file
that loads but means something different from what the user said.

So every key the loader reads appears here, empty, with a comment saying
whether it is required and what happens if it is wrong. `tests/test_scaffold.py`
asserts that against `example/`, so a key added to the model cannot silently go
missing from the scaffold.
"""

from __future__ import annotations

import shutil
import tomllib
from datetime import date
from pathlib import Path

from .model import Company

COMPANY = """# Your company. Everything on the invoice above the line items comes from here.
#
# Fill in every `required` field, then run `billwright doctor` — it checks the
# IBAN's checksum, the Swiss QR field lengths, and whether anything is missing,
# and lists everything wrong at once.

# required — the name on the invoice
name = ""

# optional — the person who signs; shown in the return address and under the
# greeting, and never in the QR payment part
person = ""

# optional — printed in the header and the footer
email = ""
website = ""
phone = ""

# required — the account the money is paid into.
# Checked with mod-97 by `billwright doctor`. Copy it from e-banking rather
# than typing it: a transposed digit pays a stranger, and nobody retypes a
# scanned QR code to notice.
iban = ""

# optional — the bank's name, shown on the payment part
bank = ""
bic = ""

# optional — CHE-xxx.xxx.xxx. Empty is correct if you have none.
uid = ""

# optional — e.g. "Einzelunternehmen"
legal_form = ""

# required — true or false, answered deliberately.
# Absent is not the same as false: if you are registered and this is missing,
# the invoice omits VAT you still owe. `vat_rate` is the percentage, as a
# string, e.g. "8.1".
vat_registered = false
vat_rate = "0"

# optional — defaults for new bills
default_terms_days = 30
default_language = "de"

# required — the issuer's address. These are Swiss QR bill fields, so they have
# length limits (name and street 70, house number and postal code 16) and the
# country must be a two-letter code. Only CH issuers are supported today.
# `name` is also the creditor in the QR payment part, unless [qr] says otherwise.
[address]
name = ""
street = ""
house_number = ""
postal_code = ""
city = ""
country = "CH"

# optional — extra lines printed above the street, e.g. a department,
# "c/o", or a building name
lines = []

# optional — the name your bank holds the account under, if it is not
# address.name: a sole proprietor's account is often in their own name. Banks
# match it against the account holder, and a mismatch bounces the payment.
# `billwright doctor` asks for it when `person` and address.name differ.
[qr]
creditor_name = ""
"""

CLIENT = """# One file per client. The filename without .toml is the key you pass to
# `billwright new --client <key>`, so keep it short and lowercase.

# optional — the person the letter is addressed to
contact = ""

# optional — "de" or "en". Decides the language of a bill for this client.
language = "de"

# optional — a reference of theirs to print on the invoice, e.g. a PO number
reference = ""

# optional — write it out in full, exactly as it should appear. Per language,
# because a German salutation on an English invoice is worse than a plain one.
[salutation]
de = ""
en = ""

# required — the recipient's address. Swiss QR bill limits apply here too.
[address]
name = ""
street = ""
house_number = ""
postal_code = ""
city = ""
country = "CH"

# optional — extra lines printed above the street, e.g. a department,
# "c/o", or a building name
lines = []
"""

RATES = """# Service categories and their hourly rates.
#
# A bill line names a service and the rate is looked up here, so a rate change
# is one edit rather than one per invoice. A line may also carry `unit_price`
# directly, which overrides this.
#
# Rates are strings so they stay exact — never floats.

[hourly]
consulting = "0.00"
"""


def write_profile(target: Path, brand_source: Path | None = None) -> list[Path]:
    """Create an empty profile at ``target``. Never overwrites.

    ``brand.toml`` is copied from ``brand_source`` rather than emptied: a blank
    palette renders a blank document, and the sample's neutral palette is a
    usable default that someone can ignore until they care.

    A ``brand_source`` without a ``brand.toml`` raises. It used to be skipped in
    silence, which produced a profile that cannot render at all — ``load_brand``
    requires the file — and said so only later, from a different command.
    """
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} already exists and is not empty")

    if brand_source is not None and not (brand_source / "brand.toml").is_file():
        raise FileNotFoundError(
            f"no brand.toml in {brand_source}, so the new profile would have none "
            "and could not render. Pass --from <profile> pointing at one that has it."
        )

    (target / "clients").mkdir(parents=True, exist_ok=True)

    written = []
    for relative, content in (
        ("company.toml", COMPANY),
        ("rates.toml", RATES),
        ("clients/your-client.toml", CLIENT),
    ):
        path = target / relative
        path.write_text(content, encoding="utf-8")
        written.append(path)

    if brand_source is not None:
        source_text = (brand_source / "brand.toml").read_text(encoding="utf-8")
        brand = target / "brand.toml"
        brand.write_text(source_text, encoding="utf-8")
        written.append(brand)
        written.extend(_copy_mark(brand_source, target, source_text))

    # No bills/ or years/ directory, and no .gitkeep anywhere: git cannot track
    # an empty directory, and a committed-but-empty profile would be selected by
    # resolve_profile() and then fail instead of falling through to the sample.
    # Every writer creates its own directory when it first needs it.
    return written


def _copy_mark(brand_source: Path, target: Path, brand_text: str) -> list[Path]:
    """Copy the logo a copied brand.toml names, so the new profile can load.

    Without it the new profile names a file it does not have, and load_brand
    refuses it — correctly, but only at the first render.
    """
    name = tomllib.loads(brand_text).get("wordmark", {}).get("mark", "")
    if not name:
        return []
    source = brand_source / name
    if not source.is_file():
        raise FileNotFoundError(
            f"{brand_source / 'brand.toml'} names {source}, which does not exist"
        )
    copy = target / name
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, copy)
    return [copy]


def bill_template(number: str, client_key: str, company: Company, rates: dict) -> str:
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
