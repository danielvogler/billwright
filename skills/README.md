# Skills

How to rebuild this system for another company.

## The split

The seam is **engine vs. profile**. The Python package holds no company facts at
all — no name, no IBAN, no colour, no wordmark. Everything specific arrives from
a profile directory (`data/`) and an assets directory (`assets/`). That is what
makes a second company a data exercise rather than a fork.

Three skills, in two layers:

| Skill | Layer | Contains |
|---|---|---|
| [`swiss-billing-generator`](swiss-billing-generator/) | generic | How to build the whole system: architecture, data model, CLI, rendering pipeline, Swiss domain rules, testing. **No company facts, no brand values.** |
| [`brand-profile`](brand-profile/) | generic | How to derive a brand profile from an existing website and express it as tokens. The *method*, not any palette. |
| *(private company profile)* | specific | The concrete values for the company being billed for: palette, wordmark, tone, company facts, and the decisions behind them. Lives outside version control. |

Read the generic two to build the machine. Read the third only to understand
this particular company — or copy its shape to write one for another.

## Onboarding a second company

1. Copy `swiss-billing-generator/` and `brand-profile/` into the new repo.
   They are complete and carry no company-specific assumptions.
2. Write a `<company>-profile/SKILL.md` beside them, using
   the private company profile skill as the shape. It records *decisions*,
   not just values — why this accent, why no VAT block, what the tone is.
3. Create the profile directory the engine actually reads:

   ```
   data/
   ├── company.toml     issuer, address, IBAN, VAT status, defaults
   ├── brand.toml       colour tokens + wordmark structure
   ├── rates.toml       service categories -> rate
   ├── clients/*.toml   one per counterparty
   ├── bills/<year>/*.toml
   └── years/<year>.toml  expenses, balance figures, notes
   ```

4. Drop the company's font into `assets/fonts/` and point `brand.toml` at it.
5. `billwright --profile <dir> bill <number>`.

Nothing in `src/` should need to change. If it does, that is a bug in the split:
the company-specific thing belongs in the profile, and the generic mechanism
belongs in the engine. Fix the seam rather than special-casing.

## What deliberately is NOT a skill

The company's actual numbers — IBAN, revenue, client addresses — live in
`data/`, not in a skill. Skills describe how to build and decide; the profile
directory holds the facts. Keeping them apart is what lets a skill be copied to
another company without carrying this one's bank details along with it.
