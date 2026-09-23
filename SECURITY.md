# Security

## Reporting

Report a vulnerability privately through
[GitHub security advisories](https://github.com/danielvogler/billwright/security/advisories/new).
Please do not open a public issue for anything exploitable, and never paste a
real IBAN, address or client name into an issue, even to show a bug.

## What this repository is careful about

billwright handles a company's bank details and its clients' names, addresses
and amounts. It is built so that none of those can reach this repository or
leave your machine through it:

- **The engine holds no company value.** Everything company-specific lives in a
  profile directory — `data/` by default — and `data/`, `archive/` and
  `assets/reference/` are gitignored. `src/` contains no name, address, IBAN,
  colour or wordmark; one appearing there is treated as a defect.
- **`billwright scan` blocks private values from tracked files.** It runs as a
  pre-commit hook and in CI, and fails on anything shaped like an IBAN, a Swiss
  UID, an email address or a Swiss phone number; on the active profile's own
  values; and on every literal in the gitignored `notes/denylist.txt`. It never
  prints what it matched — findings name the file and line, so a CI log cannot
  become the leak. The only exceptions are the registry's documentation IBAN
  used in `example/`, and lines marked `scan: allow`, which show up in a diff
  the way a lint waiver does.
- **Nothing is sent anywhere.** billwright reads and writes local files. It has
  no network code, no account, no telemetry, no storage backend and nothing
  that mails or uploads a document. An invoice leaving the company is a human
  decision.
- **The payment amount cannot be typed wrong.** Totals are computed from the
  line items in exact decimals and never stored, and the Swiss QR payment part
  is built from that same computed total, so the amount a client scans is the
  amount billed. `billwright doctor` validates the IBAN's checksum.
- **Releases carry no credential.** Publishing to PyPI uses trusted publishing
  from a tag; there is no API token in the repository, in a GitHub secret or on
  a laptop.

## What it cannot protect

A coding agent is a separate program. Whatever you show a cloud-hosted agent —
an old invoice, your IBAN, a client's name — goes to that agent's model
provider under its terms. The README's "What the agent sees" section describes
the choices; billwright cannot change them.

If a private value does reach a pushed commit, deleting it in a later commit
leaves it in the history. Report it privately as above rather than in an issue.
