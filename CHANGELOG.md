# Changelog

All notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- A logo and an architecture diagram in the README.

## [0.1.0] — 2026-08-13

First release: a generic engine that renders Swiss invoices and year-end
accounts as typeset PDFs from a profile directory of TOML.

### Documents

- **Swiss invoice** with a QR payment part, rendered from HTML and CSS through
  WeasyPrint. The payment part is generated with `qrbill` from the invoice
  itself, so the amount encoded in the QR code cannot differ from the amount
  billed. It sits at the foot of the sheet when the bill is one page and moves
  to its own sheet when it is not — a two-pass render, because `@page :last`
  does not exist and `position: fixed` repeats on every page.
- **Year-end accounts** (`Jahresrechnung`): Erfolgsrechnung and Vermögensstand
  for the tax office, plus a one-page figures sheet for transcription into the
  return. A year with no mandates renders as a statement of zeros with a
  sentence explaining why; a year whose invoices went unpaid says that instead,
  which is a different statement and not interchangeable with it.
- **German and English**, with a complete table per language. `StrictUndefined`
  turns a missing key into a render error rather than a blank on a document.

### The profile

- Every company value — issuer, address, IBAN, clients, rates, brand tokens,
  per-year figures — lives in a profile directory outside the package. The
  engine holds none, so one install bills for any number of companies.
- `resolve_profile()` selects it: the `--profile` flag, then
  `$BILLWRIGHT_PROFILE`, then the `[tool.billwright] profile` setting, then
  `./data`, then `./example`. The first two are requests and are strict — a
  path with no `company.toml` is an error rather than a silent fallback,
  because billing under the wrong company is worse than not billing. The rest
  are candidates, each used only if it holds a `company.toml`.
- `example/` is a complete fictional profile, committed. A fresh clone renders
  an invoice and a set of accounts with no configuration, and the test suite
  and CI run against it rather than against anyone's real data.
- `billwright init-profile` writes an empty profile in which every key the
  loader reads is present and marked required or optional, with the consequence
  of getting it wrong stated beside the field.
- `billwright doctor` validates a profile and the environment, listing
  everything wrong at once. It checks the IBAN with mod-97, the Swiss QR field
  lengths and the country code, and treats an unanswered `vat_registered` as
  unknown rather than false. It never echoes the IBAN.

### Correctness

- **Totals are computed from the line items and never stored.** No data file
  may carry a `total`, so a document cannot disagree with itself.
- **Money is `Decimal` throughout, never `float`.** `money()` and `quantity()`
  are the only coercion path, wired in ahead of every model field, so a TOML
  float cannot become binary noise.
- **Revenue is aggregated by payment date, not invoice date.** Under
  `OR Art. 957 II` a bill issued in December and settled in January is the
  following year's income. `example/` demonstrates the case.
- **Renders are byte-reproducible.** Re-rendering an archived bill produces an
  identical file, which is what makes the archive evidence rather than a copy.
- **The profile is validated once, at the boundary**, against a single Pydantic
  schema. Models are frozen and reject unknown keys; Swiss QR field limits are
  field types, so an over-long name fails when the profile loads rather than
  when a bank rejects the payment part.
- Swiss conventions throughout: `ss` rather than `ß`, and the Swiss apostrophe
  as the thousands separator.

### Tooling

- `billwright` CLI: `bill`, `statement`, `new`, `list`, `check`, `doctor`,
  `init-profile`, wrapped by a `Makefile`.
- `make scan` fails if a tracked file contains a private value — anything from
  the active profile, anything shaped like an IBAN, a Swiss UID, an email
  address or a phone number, and any literal in a local denylist. It never
  prints what it matched. Runs in `make check`, in CI and as a pre-commit hook.
- `make check` runs ruff, the leak scan, mypy, the test suite, the numbering
  checks and every pre-commit hook — the same set CI runs.
- GitHub Actions across Python 3.11 to 3.14 on Ubuntu, a macOS job exercising
  the dyld repair that WeasyPrint needs there, and a job running every hook.
  CI runs against `example/` only.
- `AGENTS.md` documents the repository for a coding agent, including a setup
  procedure for onboarding a new company from whatever the user already has —
  an old invoice, a letterhead, or nothing but answers to questions.

### Known limits

- The payment part implements the Swiss QR bill, so issuers outside
  Switzerland are not supported.
- The reference type is `NON`: the invoice number travels in the free-text
  field. Structured creditor references (`QRR`) need a bank-issued range.
