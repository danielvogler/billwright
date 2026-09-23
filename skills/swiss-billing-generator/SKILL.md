---
name: swiss-billing-generator
description: >
  Build a Python system that generates Swiss invoices with a QR payment part and
  yearly accounts for a sole proprietorship, rendered as PDF from HTML/CSS. Use
  when setting up billing for a new company, adding a document type, or changing
  how bills or statements are produced. Carries no company-specific values.
---

# Swiss billing generator

How to build (or rebuild) a generator that turns data files into two documents:
a Swiss invoice with a QR payment part, and a year's accounts for the tax
office. Everything here is generic. Company values live in a profile directory —
see [`../brand-profile/SKILL.md`](../brand-profile/SKILL.md) and the company's
own profile skill.

## The shape of the thing

```
src/<package>/
├── money.py        Decimal arithmetic + Swiss number formatting
├── model.py        frozen dataclasses: Company, Client, LineItem, Bill, Statement, Brand
├── load.py         TOML -> model, with validation at the boundary
├── numbering.py    invoice number parsing, sequencing, gap detection
├── qr.py           Swiss QR payment part via `qrbill`
├── statement.py    aggregate a year of bills into accounts
├── render.py       Jinja2 -> HTML -> WeasyPrint -> PDF
├── i18n.py         document strings per language
├── native.py       macOS dyld repair for WeasyPrint
├── templates/*.j2
└── styles/*.css
```

Data — never code:

```
data/company.toml  brand.toml  rates.toml  clients/*.toml  bills/<year>/*.toml  years/<year>.toml
```

## Non-negotiables

**1. Money is `Decimal`, never `float`.** Coerce floats through `str` so `0.1`
means what it prints as. Quantise to centimes with `ROUND_HALF_UP`.

**2. Totals are computed, never stored.** The document renders
`sum(line.total)`. This is the entire point: a hand-made invoice can state a
total that disagrees with its own line items, and does. Never accept a `total`
field from a data file.

**3. Validate at the boundary, in `load.py`.** A bill that is wrong should fail
to render, not render wrongly. Report the file path in every error.

**4. Never invent a colour, font or spacing value.** They come from the profile's
brand tokens, injected as CSS custom properties. If something looks like it
needs a new token it almost certainly needs an existing one.

**5. Render it and look at it.** Page-count assertions and text extraction do not
catch a heading colliding with a table or a payment part sitting on the totals.
Render to PNG (`pdftoppm -png -r 100`) and actually open it.

**6. Never edit an archived PDF.** It is the record of what a client was sent.
Change the data and re-render; the reproducibility test proves the two agree.

## Swiss specifics

These are the things that are easy to get wrong and expensive to get wrong late.
Details in [`references/swiss-rules.md`](references/swiss-rules.md).

- **Number format** is `1’234.50` — apostrophe (U+2019, *not* ASCII `'`) for
  thousands, period for decimals. German `6.490,00` is wrong on a Swiss invoice.
- **Swiss German uses `ss`, never `ß`.** `Grüsse`, `vereinbarungsgemäss`.
- **The QR payment part is 210 × 105 mm**, flush to the bottom edge of the sheet
  it sits on. It is fixed geometry that a bank's scanner reads — content must
  never encroach on it.
- **The creditor on the QR bill is the account holder**, whatever the letter
  says. Banks match the holder; a mismatch bounces the payment. For a GmbH or
  an AG that is the entity, not the person who signs; for a sole
  proprietorship it is often the owner's own name. Take it from the bank, not
  from the letterhead.
- **Retention is ten years** (`OR Art. 958f`). Commit the rendered PDFs.
- **Below CHF 500'000 turnover**, a sole proprietorship owes only a
  *Milchbüechlirechnung* under `OR Art. 957 II` — receipts, payments, asset
  position. Do not render a full double-entry balance sheet it does not owe.
- **Below CHF 100'000 turnover**, no VAT registration, so no VAT line. Build the
  block anyway and gate it on a flag; crossing the threshold is a config change,
  not a template rewrite.

## Rendering: HTML/CSS to PDF

WeasyPrint, because the style source for a consultancy is usually its website,
and reusing real CSS tokens beats re-implementing the layout in a drawing API.
It gives true `@page` control and honours `SOURCE_DATE_EPOCH`.

Gotchas, all of which cost time to rediscover — see
[`references/weasyprint.md`](references/weasyprint.md):

- On macOS it needs Homebrew's Pango/GLib/Cairo, which dyld does not search by
  default. `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib`. Set from *outside*
  the process — dyld reads it at launch, so `os.environ[...]` in Python is too
  late. Re-exec once with a sentinel guard (`native.py`).
- Use **hex**, not `oklch()`. Convert the site's oklch tokens once and record the
  conversion in a comment.
- Prefer **static font weights** over a variable font; variable-axis support is
  not reliable. Embed as data URIs so another machine cannot substitute a
  different face into a client-facing PDF.
- `@page :first` and named pages (`@page payment { … }`) work. `@page :last`
  does not.
- `position: fixed` repeats an element on **every** page.

### Placing the payment part

The standard wants it at the foot of the last page. `@page :last` does not
exist, so:

1. Render the body alone and count pages.
2. One page → reserve the strip as bottom page margin on a named page, and place
   the SVG `position: fixed` with negative offsets cancelling the page margins so
   it bleeds to the paper edge.
3. More than one page → put it on its own final sheet (also permitted by the
   standard) using a zero-margin named page with the strip bottom-aligned.
4. Re-check after rendering: the reserved margin can itself push a full page
   over. Fall back rather than ship an overlap.

Budget the layout backwards from this. A4 is 297 mm; minus 105 mm of payment
part and a top margin, the invoice body gets roughly **165 mm**. That constraint
should drive the spacing scale, not be discovered at the end.

## Testing

- `money`: formatting, separators, rounding, float coercion.
- `numbering`: parse, round-trip, sequence, gaps, duplicates.
- `load`: the real profile loads; malformed input raises.
- `qr`: the payload carries the right IBAN, amount, debtor and reference.
- `render`: page count, A4 dimensions, extracted text contains the computed
  total, both languages render.
- **reproducibility**: rendering twice produces byte-identical PDFs. Without it
  the archive stops being evidence.

Pin any real-world discrepancy you find as a regression test with a docstring
explaining it. That is how a one-off discovery becomes a permanent guarantee.

## Numbering

`RE-YYNNN` — prefix, two-digit year, three-digit sequence, restarting yearly.
Auditors expect a contiguous series, so `check` must report gaps and duplicates.
Numbers issued before the tool existed are declared in `years/<year>.toml` as
`bills_issued_elsewhere`, so a real gap is never mistaken for a migration
artefact.

## References

- [`references/swiss-rules.md`](references/swiss-rules.md) — QR bill, formatting, accounting obligations
- [`references/weasyprint.md`](references/weasyprint.md) — print CSS, page geometry, platform setup
- [`references/architecture.md`](references/architecture.md) — module contracts and data schema
