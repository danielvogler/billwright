# Module contracts and data schema

The engine/profile seam, stated precisely enough to rebuild it.

## Rule

`src/` may not contain a company name, address, IBAN, colour, font choice or
wordmark. If one appears there, the seam has leaked: move the value into the
profile and leave the mechanism behind.

## Profile schema

### `company.toml`

```toml
name = "…"                 # trading name
person = "…"               # signatory; also the QR-bill creditor
email = "…"  website = "…"  phone = "…"
bank = "…"  iban = "…"  bic = "…"
uid = ""                   # CHE-…; omitted from documents when empty
vat_registered = false
vat_rate = "8.1"           # ignored unless registered
legal_form = "…"
default_terms_days = 14
default_language = "de"

[address]
name = "…"  street = "…"  house_number = "…"
postal_code = "…"  city = "…"  country = "CH"
lines = []                 # optional extra lines above the street
```

`street` and `house_number` are split because the QR bill needs them separately.

### `brand.toml`

```toml
font_family = "…"
font_file = "fonts/….otf"

[colors]                   # become CSS custom properties verbatim
ink = "#…"  muted = "#…"  rule = "#…"
accent = "#…"  accent-soft = "#…"  accent-faint = "#…"

[wordmark]                 # typeset text, plus an optional drawn mark
mark = "logo.svg"  line1 = "…"  line2 = "…"  accent = "…"  dot = "."  tagline = "…"
```

Add a token by adding a key — no Python change. The CSS may only reference
tokens that exist here.

### `rates.toml`

```toml
[hourly]
project_management = "250.00"
```

A bill line names a `service`; the rate is looked up. Historical bills keep the
price they were issued with, because the rendered PDF is the record.

### `clients/<key>.toml`

```toml
contact = "…"
salutation = "Sehr geehrter Herr …,"   # explicit: German honorifics do not
                                        # compose reliably from name + gender
language = "de"
reference = ""                          # client's own PO/reference

[address]
name = "…"  lines = ["…"]  street = "…"  house_number = "…"
postal_code = "…"  city = "…"  country = "CH"
```

### `bills/<year>/<NUMBER>.toml`

```toml
number = "RE-26001"
date = 2026-01-01          # a real TOML date, not a string
client = "example-institute"
language = "de"
terms_days = 14
project = ""
paid_on =                  # optional; drives `list`, never printed

[[items]]
description = "…"
quantity = 7.25
unit = "Stunden"
service = "project_management"   # or unit_price = "250.00"
```

**No `total` field, ever.** It is computed.

### `years/<year>.toml`

```toml
place = "Zürich"
prepared_on = 2026-08-13
note = ""                          # overrides the generated nil-year sentence
bills_issued_elsewhere = []        # numbers issued before migration

[[expenses]]
description = "…"
amount = "…"

[[assets]]
description = "…"
amount = "…"

[[liabilities]]
description = "…"
amount = "…"
```

Absent file = a year with nothing recorded, which is a valid answer.

## Module contracts

| Module | Depends on | Must not |
|---|---|---|
| `money` | stdlib | know about documents |
| `model` | `money` | read files |
| `numbering` | stdlib | read files |
| `load` | `model`, `money` | render anything |
| `qr` | `model`, `qrbill` | know about CSS |
| `statement` | `load`, `model` | render anything |
| `render` | all of the above, Jinja2, WeasyPrint | contain company values |
| `i18n` | — | contain company values |
| `native` | stdlib | import weasyprint |

`render` imports WeasyPrint **lazily, inside functions**, so that importing the
package does not trigger the native-library load before `native.py` has had its
chance to repair the path.

## Derived properties belong on the model

`Bill.net`, `Statement.profit`, `Statement.equity` are computed properties, not
stored fields. A template can then never print a total that disagrees with the
lines above it, because there is no second copy to disagree with.
