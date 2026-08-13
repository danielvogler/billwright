# Swiss invoicing and accounting rules

Practical reference for the generator. Not legal advice — where a number or a
form name matters, verify against current cantonal guidance or a Treuhänder.

## Number and date formatting

| Thing | Swiss form | Common mistake |
|---|---|---|
| Thousands | `1’234.50` — U+2019 RIGHT SINGLE QUOTATION MARK | ASCII `'`, or German `1.234,50` |
| Decimal | period | comma |
| Currency | `1’234.50 CHF`, code after | `CHF 1.234,50` |
| Date | `06.07.2026` | ISO on a client-facing document |
| Sharp S | never — `Grüsse`, `vereinbarungsgemäss` | German `ß` |

The apostrophe matters: `'` and `’` look nearly identical on screen and are
different characters in the PDF. Assert on it in a test.

## The Swiss QR bill (QR-Rechnung)

Defined by the Swiss Payment Standards. Generate it — never paste an image,
which is how an amount silently stops matching the invoice.

- **Geometry**: 210 × 105 mm, flush to the bottom edge of the sheet. Receipt
  (Empfangsschein) 62 mm on the left, payment part (Zahlteil) to its right, with
  a perforation line between and above.
- **Position**: foot of the invoice's last page, or on its own sheet. Both are
  permitted; the first is nicer for the client, the second is the safe fallback
  for a long invoice.
- **Creditor**: the **account holder** as the bank knows them, not the trading
  name. A trading name that does not match the IBAN holder gets the payment
  returned. Put the trading name in "Additional information" instead.
- **Reference type**:
  - `NON` — no structured reference; the invoice number travels in the free-text
    *Additional information* field (max 140 chars). Zero setup. Start here.
  - `QRR` — structured creditor reference, lets the bank auto-match incoming
    payments to invoices. Requires the bank to issue a reference range first.
  Wire the parameter for `QRR` from the start even while using `NON`.
- **Library**: `qrbill` (PyPI). `QRBill(...).as_svg(buffer)` emits a 210 mm-wide
  SVG. It renders the amount with a space separator (`6 500.00`) — that is the
  standard's own formatting inside the payment part, and it correctly differs
  from the apostrophe form used in the invoice body.

## Accounting obligations for a sole proprietorship (Einzelunternehmen)

- **Under CHF 500'000 turnover**: only a *Milchbüechlirechnung* is owed —
  `OR Art. 957 II`: receipts (Einnahmen), payments (Ausgaben) and asset position
  (Vermögenslage). No double-entry bookkeeping, no formal Bilanz. The statement
  template should match this, not over-produce a corporate-looking balance sheet.
- **Over CHF 500'000**: full double-entry accounting applies.
- **Retention**: ten years, `OR Art. 958f`. The rendered PDF is the record, not
  the source data — commit it.
- **VAT**: registration required above CHF 100'000 turnover. Below it, no VAT
  line on the invoice at all. Keep the block in the template behind a flag.

## A nil year

A year with no mandates is a real result, not missing data. Render it as a
statement of zeros and **say in one sentence why**: a bare table of zeros invites
a follow-up question from the tax office; a sentence answers it in advance.

Distinguish carefully:

- **no revenue and no expenses** → profit `0.00`, nothing to carry forward
- **no revenue but some expenses** → a **loss**, which can be carried forward

The distinction changes the tax outcome, so it is worth asking about explicitly
rather than inferring from "I made no profit". The usual hidden expense in a
zero-revenue year is the AHV *Mindestbeitrag*: it falls due for someone
registered as primarily self-employed, but not where the business is a
Nebenerwerb alongside employment whose contributions already run through the
employer. An AHV assessment at CHF 0 is good evidence of a true nil — keep it
filed with the statement.

## Tax filing

Cantonal, and the form names change. For Zürich the figures go into the
self-employment sheet of the return in ZHprivateTax, with the accounts attached
as a supporting document. **Verify the current form name and field labels before
relying on them** — generating a clean `Jahresrechnung` PDF is safe regardless,
but a transcription sheet's labels should match the real form.
