# Changelog

All notable changes to this project. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
follows [semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-09-12

### Added

- **`billwright --version`**, and the same string in the PDF metadata as
  `/Creator`. "Which version of the tool produced this document" is a question
  an archive kept for ten years should answer on its own, rather than by way of
  a lock file in another repository that may have moved on. It is metadata, not
  visible on the document — a client has no use for it.

  One consequence, stated plainly: re-rendering an archived invoice under a
  *later* version now produces different bytes. `tests/test_reproducible.py`
  still holds — the same input and the same version give the same file — but
  "re-render and diff" as a way of checking an archive is now a check against
  the version that wrote it.

- The version is read from the installed distribution rather than being a second
  string in `__init__.py` to drift from `pyproject.toml`.

- **`billwright scan`.** The leak guard shipped only in `tools/`, outside the
  wheel, so an installed copy could not run it — and it is the check that makes
  keeping a company profile inside another repository defensible rather than
  merely convenient. It already took `--root`, so a consuming repository can now
  gate its own commits on `billwright scan --root .`. Nothing about the
  detectors changed, including that it never echoes what it matched.

### Fixed

- **`--archive` no longer writes the ten-year record into the virtualenv.**
  `paths.py` derived its directories from `Path(__file__).parents[2]` — the
  repository root in a clone, but `<venv>/lib/python3.x/` once billwright is
  installed as a dependency. `billwright bill … --archive` filed the invoice
  there, printed the path and exited 0, and the next `uv sync --reinstall`
  deleted it. The failure was silent and the record is required for ten years
  under `OR Art. 958f`.

  The archive now defaults to `<profile>/archive` — beside the company data,
  because that is what an issued invoice is — and can be pointed anywhere with
  `--archive-dir`, `$BILLWRIGHT_ARCHIVE` or `[tool.billwright] archive`,
  resolved against the working directory exactly as `profile` already is. An
  archive path inside the Python installation is refused rather than written.
  Drafts (`--out`) likewise default to `./out` in the working directory.

- **The typeface now ships in the wheel.** `assets/fonts/` sat at the repository
  root, outside the package, so an installed copy found no faces and typeset
  client-facing invoices in whatever WeasyPrint substituted — silently, because
  a missing face was skipped with `continue`. The faces moved to
  `src/billwright/assets/fonts/`, a missing one is now an error, and `doctor`
  checks for the three declared faces rather than for a non-empty directory
  (one holding only `OFL.txt` used to pass and still render wrong).

- **`init-profile` no longer writes a profile that cannot render.** A missing
  `brand.toml` at the source was skipped in silence, and `load_brand` requires
  the file; it is now reported when the profile is created rather than by a
  later command. `--from` defaults to `./example` in the working directory.

- **The MCP server can serve its own manual when installed.** The
  `billwright://agents` resource read `AGENTS.md` from the repository root and
  raised `FileNotFoundError` from an installed copy — while the server's own
  instructions tell a client to read it first. `AGENTS.md` is now force-included
  into the wheel; it is still tracked exactly once.

### Added

- **An optional MCP server**, `billwright[mcp]`, run as `billwright-mcp`. It
  exists for the one case a shell cannot cover: an agent with no terminal, in a
  chat client or on a schedule, that still has to issue a bill. The command line
  remains the way in.

  It restates nothing — `AGENTS.md` is served verbatim as the
  `billwright://agents` resource rather than paraphrased into tool descriptions,
  because the paraphrase is the copy that goes stale. It computes nothing: every
  figure comes from the same loaders and the same `money.py` the CLI uses. And
  it names the company it is billing as in every response, because a chat client
  shows no working directory to notice the wrong profile from.

- `paths.py`, holding the naming and target-directory rules for rendered
  documents. Two callers spelling the same invoice differently is how an archive
  stops being a series.

- `audit.py`, holding the numbering audit that `billwright check` prints. Two
  implementations of "is the numbering sound" would eventually disagree about a
  real invoice.

### Changed

- `bill_template` moved from `main.py` to `scaffold.py`, so the CLI and the MCP
  server scaffold byte-identical bills.
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
