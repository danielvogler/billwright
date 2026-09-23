# AGENTS.md

Instructions for a coding agent working on billwright: invoices and yearly
statements. Read this before touching anything. This is the single source of
truth for agent rules in this repo; `CLAUDE.md` and `GEMINI.md` only point here.

Everything here is **client-facing or tax-facing**. A broken invoice is
discovered by a client who is being asked for money; a broken statement is
discovered by the Steueramt. Bias hard towards verifying rather than assuming.

Humans: see [README.md](README.md).

---

## If you are setting up a new company, start here

Someone has cloned this and wants to bill with it. **Do the setup for them** —
they should not have to install anything by hand before talking to you.

**Step 1: get the environment working.** Check what is missing and install it,
asking before you run anything that needs `sudo` or touches their system:

```bash
uv --version                                   # https://astral.sh/uv if absent
python3 -c "import ctypes.util as u; print(u.find_library('gobject-2.0'))"
```

WeasyPrint binds Pango and Cairo through cffi, and a missing one produces
`cannot load library 'libgobject-2.0-0'` rather than anything about fonts:

| Platform | Command |
|---|---|
| macOS | `brew install pango` (and `poppler`, to turn a PDF into a PNG you can look at) |
| Debian/Ubuntu | `sudo apt install libpango-1.0-0 libpangoft2-1.0-0 poppler-utils` |
| Fedora | `sudo dnf install pango poppler-utils` |

**Step 2: prove the renderer works before touching their data.** This separates
a missing system library from a mistake you are about to make:

```bash
make setup                     # uv sync
make bill BILL=RE-26001        # renders the bundled example into out/
```

**Step 3: give them their own profile.** Either way, `data/` is gitignored and
`example/` stays exactly as it is:

```bash
uv run billwright init-profile --into data    # empty form, every field marked
                                              # required or optional
```

or, if you would rather start from a filled-in example and edit it down:

```bash
cp -r example data
rm -rf data/bills/* data/years/*   # their profile, not the sample's numbers
```

**Step 4: take whatever they have and write the TOML yourself.**

They do not know this file format and should never be asked to learn it. Ask
what they already have and read it:

- **an invoice they sent before** — PDF, Word, Pages, a photo of a printout.
  This is the best source: it has the issuer block, the footer, the payment
  details and a real line item, all in one place.
- **a letterhead, an email signature, a business card, their website**
- **a bank statement or e-banking screenshot**, for the IBAN and the bank name
- **nothing at all** — then just ask, in plain questions, one topic at a time.

Read the source, extract the fields, and write the files. Where a document is
ambiguous, ask about that one field rather than guessing the lot.

| Where it usually is on an old invoice | Goes to |
|---|---|
| Sender block, top left or in the letterhead | `company.toml`: `name`, `person`, `address` |
| Footer: email, website, CHE number, legal form | `company.toml`: `email`, `website`, `uid`, `legal_form` |
| Payment slip or "Zahlbar an" | `company.toml`: `iban`, `bank` |
| "MwSt/TVA" line, or its absence | `company.toml`: `vat_registered`, `vat_rate` |
| "Zahlbar innert 30 Tagen" | `company.toml`: `default_terms_days` |
| Recipient block | `clients/<key>.toml` |
| Line items and their unit prices | `rates.toml` service categories |
| Logo, colours and typeface | `brand.toml` (a drawn logo goes in the profile as `mark`), or leave the default |

**Never invent a financial or legal value, and never trust your own reading of
one.** An invented or misread IBAN sends money to a stranger; an invented VAT
rate under-invoices and the difference is still owed.

- **Read every extracted financial value back to them for confirmation** — the
  IBAN in full, the VAT rate, the rates. OCR and PDF text layers transpose
  digits, and an invoice is the last place that gets noticed.
- If they do not know, stop and let them find out. `vat_registered` being absent
  means *unknown*, not `false`.
- `billwright doctor` checks the IBAN's mod-97 checksum, so a transposed digit
  usually fails there — but a checksum-valid wrong IBAN exists, which is why
  the human confirms it too.

Then:

```bash
uv run billwright doctor       # is the profile complete and the IBAN valid?
uv run billwright check        # numbering, gaps, empty bills
make new CLIENT=<their-key>    # scaffolds the next number
# fill in the line items, then:
make bill BILL=<number>        # renders into out/ — LOOK AT IT (rule 6 below)
make scan                      # nothing private reached a tracked file
```

Tell them plainly, once, before their first real invoice: **scan the QR code
with a banking app.** The payload is unit-tested; a live scan is the only thing
that proves the money would arrive.

---

## First, orient

```bash
make setup                     # uv sync
make bill BILL=RE-26001        # render one bill into out/
make statement YEAR=2026       # yearly accounts + figures sheet into out/
make scan                      # fail if a tracked file holds a private value
make check                     # lint + scan + tests + numbering checks (what CI runs)
uv run billwright --help
```

The entry point is `billwright.main:main`, exposed as `billwright` and as
`python -m billwright`.

There is a second, optional entry point: `billwright.mcp_server:main`, exposed
as `billwright-mcp` and installed only with the `mcp` extra. **It is not the way
in, and it is not a place to put behaviour.** It serves this file verbatim as a
resource and calls the same loaders the CLI calls; anything it did that the CLI
does not is by definition drift. If you are about to add logic there, add it to
the engine and let both call it.

**How the repo is split** — this is the thing to understand first:

- `src/billwright/` is a **generic engine**. It contains no company name, address,
  IBAN, colour, font or wordmark.
- `data/` is the **profile**: all company facts. Gitignored. `example/` is a
  fictional profile that is committed, and what the tests run against.
- `src/billwright/assets/fonts/` holds the vendored typeface. It is inside the
  package so that an installed copy renders correctly with no flags; a face the
  renderer cannot find is now an error rather than a substitution.
- `assets/reference/` (gitignored) is for source documents from clients.
- `skills/` documents how to rebuild the system, split generic vs. specific, so
  it can be reused for another company. Read
  [`skills/README.md`](skills/README.md) before making structural changes.

---

## Non-negotiables

**1. Never put a company value in `src/`.** No name, address, IBAN, hex colour,
font choice or wordmark string. If you need one, it belongs in `data/`. A value
appearing in `src/` means the engine/profile seam has leaked — fix the seam
rather than special-casing.

`make scan` enforces this across every **tracked** file, not just `src/`: it
matches the active profile's own values, anything shaped like an IBAN, a Swiss
UID, an email address or a phone number, and the literals in the gitignored
`notes/denylist.txt`. It runs inside `make check`. It never prints what it
matched — a guard that echoes the value into a log has moved the leak rather
than caught it, so findings name the file and line and you look yourself.

**2. Totals are computed, never stored.** No data file may carry a `total`
field. This is not a style preference: the Word original this replaces states
a total its own lines did not sum to, and computing the total is
what makes that impossible. `tests/test_load.py` pins it.

**3. Money is `Decimal`.** Never `float`. Format Swiss: `1’234.50 CHF`, with
U+2019 for thousands and a period for decimals. `’` and `'` look alike and only
one is correct — `tests/test_money.py` asserts on it.

**4. Swiss German uses `ss`, never `ß`.** `Grüssen`, `vereinbarungsgemäss`. The
Word originals got this wrong; do not reintroduce it.

**5. Never invent a colour, font or spacing value.** Everything comes from
`data/brand.toml` (colours, wordmark) and the scale in
`src/billwright/styles/tokens.css` (type, spacing). The palette mirrors
the profile's `brand.toml`. If something looks like it
needs a new value, it almost certainly needs an existing one.

**But the accent is an accent.** One 1 pt rule under the title is the entire
brand presence on an invoice. Filling boxes with the tint is how this gets
wrecked.

**6. Render it and actually look at it.** This is the rule that matters most.
Structural checks pass happily while a payment part sits on top of the totals.

```bash
make bill BILL=RE-26001
cd out && pdftoppm -png -r 100 *RE-26001.pdf page   # then open page-1.png
```

If you cannot view images in your environment, **say so explicitly in your
report** and describe the check as unverified. Never imply visual confirmation
you did not perform.

**7. Never edit a PDF, and never edit an archived one at all.** The archived PDF
is the record of what a client was sent — `OR Art. 958f` requires keeping it ten
years. Change the data and re-render. `tests/test_reproducible.py` proves a
re-render is byte-identical.

**8. The invoice body has ~165 mm.** A4 minus the 105 mm Swiss QR payment part
and the top margin. Every spacing decision lives under that budget. When a bill
overflows, measure before adjusting:

```python
# see skills/swiss-billing-generator/references/weasyprint.md
box.position_y / 96 * 25.4   # mm
```

**9. [CHANGELOG.md](CHANGELOG.md) is written at release time, from the commit
messages — never in a feature branch.** Do not touch it in an ordinary commit.
Two open branches that each add a line under the same heading conflict on that
line every time, and the commit history already records what changed. Cutting
a release is when the commits since the last tag become a section; see
[Releasing it](#releasing-it).

That makes every commit message the draft of a changelog line. Write the subject
and body so that someone who installed this software would recognise the
change: what it does for them and why, not which function moved.

**Using the tool is not a change to it.** Creating a profile under `data/`,
adding a client, issuing a bill, closing a year — none of these get a changelog
entry, and none of them get a commit. `data/` is gitignored: nothing there is
part of this repository, and a public changelog saying that the maintainer set
up a profile tells its readers nothing while inviting a detail that should not
be public. The changelog is written for someone who installed this software,
about the software.

An earlier version of this rule said "data changes and new bills included",
which was correct when this repository *was* one company's billing system.
It is now a generic tool with the company outside it. If you find yourself
writing a changelog line about a bill, you are recording your own bookkeeping
in someone else's release notes.

**The changelog records what changed in this repository. Nothing else.** It must
never carry:

- **Client or commercial matters** — a disputed amount, an under- or
  over-billing, who owes what, why an invoice was reissued.
- **Open decisions** — anything phrased as "whether to X is still open". A
  changelog is a record of what happened, not a place to park a question.
- **Specific money amounts, client names, or account details.** A rule of thumb:
  if the line would embarrass you in front of the client it names, it is in the
  wrong file. Describe the *change* ("totals are now computed from line items"),
  never the *incident* that motivated it.

Those things have homes already, and the changelog is not a shortcut to them:

| Kind of thing | Where it goes |
|---|---|
| An open decision needing Daniel | `TODOS.md` (untracked) |
| A durable fact about the business you bill for | the private company profile skill (gitignored) |
| A defect that must never recur | a regression test, with a docstring saying why |
| A fact about one bill | a comment in that bill's TOML |

Before adding a changelog line, ask whether it describes a change to code, data
or documentation. If it describes a business event, it belongs somewhere above.

**10. No co-authored commits.** No `Co-Authored-By` trailer, no tool attribution
in commit messages.

---

## What this tool does not do

Stated because the obvious fix for a storage problem is the wrong one here, and
the next agent to read "the archive has to outlive a laptop" will otherwise
propose it in good faith.

**No storage backend.** No Drive, no S3, no GCS, no upload of any kind. "It
reads and writes local files and talks to nothing" is a property people rely on,
and it is most of why this tool is allowed near a company's bank details at all.
Making an archive survive a disk is a sync problem, solved outside this tool.

**Nothing that sends a document anywhere.** No mail, no client portal, no
webhook. An invoice leaving the company is a human decision, and a tool that
could send one makes that unenforceable.

If a request seems to need either, the answer is a path on disk and a sentence
explaining who copies it where.

---

## Things that will bite you

**WeasyPrint on macOS.** It binds Pango/GLib/Cairo through cffi and Homebrew
puts them where dyld does not look. `billwright` repairs this itself by re-execing
(`src/billwright/native.py`); the `Makefile` exports the variable for pytest.
Running `uv run python` directly needs it set by hand:

```bash
DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib uv run python …
```

**`@page :last` does not exist.** Placing the payment part on the final page is
a two-pass render: count the body's pages, choose inline or a separate sheet,
then verify the choice did not itself cause an overflow. `render.py` does this;
do not simplify it away.

**`position: fixed` repeats on every page.** It is only safe for the
single-page case, which is why the fallback exists.

**oklch() is not reliable in WeasyPrint.** Tokens are hex, with the oklch source
in a comment in `data/brand.toml`.

**Fonts are vendored static weights**, embedded as data URIs. Do not switch to a
variable font or a system install — a substituted face on a client document is
not something you find out about in time.

---

## Adding things

**A new bill**: `make new CLIENT=<client-key>`, edit the items, `make bill BILL=…`,
look at it, then `make archive BILL=…`.

**A new client**: a TOML in `data/clients/`. Write the salutation out in full.

**A new language**: add the block to `src/billwright/i18n.py`. Both `de` and `en`
must stay complete — `StrictUndefined` turns a missing key into a render error,
which is the intent.

**A different look for one company**: not a change to `src/`. Put CSS in
`<profile>/styles/` (`overrides.css` for everything, `bill.css` or
`statement.css` for one document) — it is appended after the packaged rules — or
replace a template outright by putting a file of the same name in
`<profile>/templates/`. If you are editing `src/billwright/styles/` to make one
company's invoice look right, the seam has leaked.

**A new document type**: a template in `templates/`, a stylesheet in `styles/`, a
subcommand in `main.py`. Reuse `tokens.css` and `print.css`.

**A new command**: a subcommand in `main.py`, and — if an agent without a shell
would need it — a tool in `mcp_server.py` that calls the same function. Put the
logic in a module both can import, never in either entry point. `audit.py` and
`paths.py` exist because that rule was applied to `check` and to filenames.

---

## Releasing it

**Pushing a `vX.Y.Z` tag is the whole release.** `release.yml` runs the same CI
gate main gets, builds, proves the wheel renders once installed, uploads to
PyPI over trusted publishing, and then creates the GitHub release with the
changelog section as its notes and the sdist and wheel attached. Nothing else
publishes, and nothing publishes without a tag.

There is no PyPI token anywhere — not in the repository, not in a GitHub
secret, not on a laptop. PyPI's trusted publishing exchanges the workflow's own
OIDC identity for a credential that lasts minutes. **Three things are
load-bearing and PyPI matches on all of them: the filename `release.yml`, the
environment named `pypi`, and `id-token: write`.** Rename any of them and the
upload fails with a 403 that does not explain itself.

To cut a release:

1. Bump `version` in `pyproject.toml`, then `uv lock` and commit `uv.lock`
   with it. The version is authored in one place — `billwright.__version__`
   reads it back from the installed metadata, and it is the string that lands
   in every PDF's `/Creator` — but the lock file mirrors it, and CI installs
   with `--locked`, so a bump without a relock fails the gate before it fails
   anything interesting.
2. Write the `## [<version>] — <date>` section of `CHANGELOG.md` from the
   commits since the last tag — `git log --no-merges --format='%s%n%b'
   v<previous>..HEAD` — grouped under Added, Changed and Fixed. Leave out what
   nobody who installed it would notice, and apply rule 9's limits to every
   line. The workflow refuses a tag whose version has no such section, and the
   section becomes the release notes —
   `scripts/changelog-section.sh <version>` prints exactly what will be
   published, so there is no second place to keep release notes in step.
3. `make release-check`. It runs everything CI runs, builds, runs `twine
   check`, installs the wheel into a clean virtualenv and renders the example
   bill with it, confirms the changelog entry and a clean tree, then prints the
   two commands below. **Run this before tagging**: a tag can be deleted, but a
   version uploaded to PyPI can only be yanked, never replaced.
4. `git tag -a v<version> -m "v<version>" && git push origin v<version>`.

`scripts/verify-wheel.sh` is the same script the workflow runs, which is why
the rehearsal and the release cannot drift apart. It exists because every test
here imports from the working tree: 0.2.0 shipped a wheel without the typeface,
and an installed copy typeset client invoices in a substituted face without
saying so. Presence of the faces *and* a real render, because the first is what
went wrong and the second is what the faces are for.

The GitHub release runs only after PyPI succeeds — one announcing a version
that never reached PyPI points at nothing installable — and attaches the
artifacts that were uploaded rather than a rebuild, so what is attached is what
is on PyPI.

**Never move a tag that has been pushed.** If a release is wrong, the fix is
the next version.

**The first release needs PyPI configured once.** On PyPI, under *Publishing*,
add a pending trusted publisher: project `billwright`, owner `danielvogler`,
repository `billwright`, workflow `release.yml`, environment `pypi`. Then
create a GitHub environment named `pypi` on the repository. Until both exist,
the publish step fails at the last hop with every earlier check green.

---

## Definition of done

- [ ] `make check` passes
- [ ] The document was rendered **and looked at**
- [ ] No company value landed in `src/`
- [ ] No hardcoded colour or spacing outside the token files
- [ ] CHANGELOG entry added
- [ ] Anything unverified is stated as unverified
