---
name: brand-profile
description: >
  Derive a company's visual profile from its existing website and express it as
  print tokens for generated documents. Use when onboarding a new company to the
  bill generator, when documents drift from the website, or when a brand asset
  needs to work in print. Method only — contains no specific palette.
---

# Brand profile

How to get a generated PDF to look like the company's website, without inventing
anything. The output is a `brand.toml` and a font file. No values here are
specific to any company.

## Find the real source of truth

Look for the stylesheet the **live site** actually renders — typically
`src/styles/global.css`, a Tailwind `@theme` block, or a `tokens.css`. That file
is canonical.

Be suspicious of a `brand/` folder of generated logo assets. It often exists,
and it often carries an **older palette** than the live site. Two candidate
palettes that disagree is the normal case, not an anomaly. Resolve it by asking
which one the live site renders, take that, and record the drift rather than
quietly picking one.

Check whether other repos (decks, templates) already converted the palette. If
one has, match it — three surfaces agreeing matters more than a fresh
derivation, and it is evidence your conversion is right.

## Convert to print

### Colour

Modern sites define colour in `oklch()`. Print renderers may not support it.
Convert to hex once, and **keep the oklch source in a comment** so the
derivation stays auditable:

```
--color-accent: oklch(0.46 0.08 249)  ->  #2F5C86
```

That pair is `example/brand.toml`'s accent, so the illustration can be checked
against a file in this repository. Never paste a real company's palette into a
generic skill: the visual identity is a company value like any other, and this
file is tracked.

Verify by comparing against any existing converted palette in a sibling repo.

### The page ground is white

A site's warm `paper` tone is right on a screen and wrong on A4: it floods an
inkjet and scans badly. Put the brand in the accent rule, the heading and the
table header instead. This is a deliberate, documented deviation — not an
oversight — and it is the single most common mistake when porting a web palette
to print.

### Accent is an accent

The fastest way to wreck a document is to fill every box with the tint. On an
invoice, one 1 pt accent rule under the title is usually the entire brand
presence, and it is enough.

## The wordmark

Check whether the logo is **drawn** or **typeset**. Open the SVG. Very often it
is just `<text>` — a name in a weight of the body font with one coloured
character. If so, do not embed an image: set it in HTML/CSS.

Typesetting it wins on every axis — vector-sharp at any size, no asset to keep
in sync, and it inherits the document's font stack automatically. It also makes
"crop the padding off the logo" a non-question, because there is no padding.

Record the structure as data so another company supplies its own:

```toml
[wordmark]
mark = "logo.svg" # optional: a drawn mark in the profile, .svg or .png
line1 = "…"       # optional first line
line2 = "…"       # the main line
accent = "…"      # optional: text straight after line2, in the accent colour
dot = "."         # the accent character; "" for none, "." if absent
tagline = "…"     # optional, usually suppressed on dense documents
```

Every key is optional. Case, weight and size come from the packaged styles;
change them in `<profile>/styles/overrides.css` — `example/` does exactly that
for its lowercase wordmark.

If the logo *is* drawn, save it into the profile, name it as `mark`, and
tighten its `viewBox` rather than
cropping a raster — the padding in a square logo asset is deliberate whitespace
for social avatars and is wrong in a letterhead. To compute a tight box for
typeset text, measure with `fontTools`:

```python
font = TTFont(path); upm = font["head"].unitsPerEm
cap = font["OS/2"].sCapHeight / upm            # top of caps above baseline
width = sum(font["hmtx"][cmap[ord(c)]][0]/upm*size + tracking*size for c in text)
```

## Fonts

Vendor the files into the profile and declare them in `faces`; do not rely on
a system install. A machine with a
different font set must not be able to substitute a face into a client-facing
document. Prefer static weights over a variable font — see the WeasyPrint
reference in the generator skill.

Check the licence permits redistribution (SIL OFL does) and say so in `LICENSE`.

## Deliverable

```toml
font_family = "…"
faces = [                  # optional; without it, the packaged Inter faces
  { file = "fonts/…-Regular.otf",  weight = 400 },
  { file = "fonts/…-Medium.otf",   weight = 500 },
  { file = "fonts/…-SemiBold.otf", weight = 600 },
]

[colors]
ink = "#…"  muted = "#…"  rule = "#…"
accent = "#…"  accent-soft = "#…"  accent-faint = "#…"

[wordmark]
line1 = "…"  line2 = "…"  dot = "."  tagline = "…"
```

Every token becomes a CSS custom property. The stylesheets may reference only
these — that constraint is what keeps two documents from one company looking
related.

## References

- [`references/deriving-tokens.md`](references/deriving-tokens.md) — the conversion script and a worked checklist
