# WeasyPrint for print documents

Everything here was learned the slow way. Verified against WeasyPrint 69.0.

## Platform setup

WeasyPrint binds Pango, GLib and Cairo through cffi.

```bash
# macOS
brew install pango          # pulls glib, cairo, harfbuzz, fontconfig
# Debian/Ubuntu
sudo apt install libpango-1.0-0 libpangoft2-1.0-0
```

On macOS the libraries land in `/opt/homebrew/lib`, which dyld does not search,
so importing WeasyPrint fails with:

```
OSError: cannot load library 'libgobject-2.0-0'
```

even though the file is present. The fix is `DYLD_FALLBACK_LIBRARY_PATH`, and
the trap is that **dyld reads it when the process starts** — setting
`os.environ[...]` before `import weasyprint` does not work. Re-exec once:

```python
env = {**os.environ,
       "DYLD_FALLBACK_LIBRARY_PATH": "/opt/homebrew/lib:/usr/local/lib:/usr/lib",
       SENTINEL: "1"}
os.execve(sys.executable, [sys.executable, "-m", pkg, *args], env)
```

Guard with a sentinel env var so it can never loop. Note this only helps the CLI
entry point — pytest and direct `python` invocations need the variable set in
the Makefile or shell.

## Colour

`oklch()` is not reliably supported. Convert to hex once and keep the oklch
source values in a comment so the derivation stays auditable.

```python
# oklch(L C H) -> linear sRGB via OKLab, then gamma-encode
l_ = L + 0.3963377774*a + 0.2158037573*b   # a = C*cos(H), b = C*sin(H)
m_ = L - 0.1055613458*a - 0.0638541728*b
s_ = L - 0.0894841775*a - 1.2914855480*b
r  =  4.0767416621*l_**3 - 3.3077115913*m_**3 + 0.2309699292*s_**3
g  = -1.2684380046*l_**3 + 2.6097574011*m_**3 - 0.3413193965*s_**3
bb = -0.0041960863*l_**3 - 0.7034186147*m_**3 + 1.7076147010*s_**3
```

## Fonts

Prefer **static weights** to a variable font — variable-axis support is not
dependable, and a silently-wrong weight on a client document is expensive.
Embed as data URIs:

```python
f"src: url(data:font/otf;base64,{b64}) format('opentype');"
```

Vendoring beats relying on a system install: another machine with a different
font set must not be able to substitute a face into a client-facing PDF.

## Page geometry

Supported and useful:

- `@page { size: A4; margin: … }`
- `@page :first { … }`
- named pages — `@page payment { margin: 0 }` with `.x { page: payment }`
- margin boxes — `@bottom-center { content: element(footer) }` with
  `position: running(footer)`
- `counter(page)` / `counter(pages)`
- `break-before: page`, `break-inside: avoid`

Not available:

- `@page :last` — this is why placing something on the final page needs the
  two-pass render described in the parent skill
- margin boxes on a page whose margin you have set to 0 (nowhere to draw)

`position: fixed` repeats the element on **every** page. Fine for a
known-single-page document; wrong the moment it grows.

Measure real box positions instead of guessing at spacing:

```python
doc = HTML(string=html).render(stylesheets=[CSS(string=css)])
box = doc.pages[0]._page_box
# walk .children; position_y and margin_height() are in CSS px — /96*25.4 for mm
```

That one snippet turns "why is it two pages" from a guessing game into a
measurement.

## Reproducibility

WeasyPrint honours `SOURCE_DATE_EPOCH`. Pin it to the document's own date so a
re-render years later still matches the archived file byte for byte:

```python
os.environ["SOURCE_DATE_EPOCH"] = str(int(datetime(y, m, d, tzinfo=UTC).timestamp()))
```

Restore the previous value afterwards; leaking it into the rest of the process
affects anything else that renders.

## Inspecting output

```bash
pdftoppm -png -r 100 doc.pdf page       # whole pages
pdftoppm -png -r 100 -x 0 -y 0 -W 900 -H 420 doc.pdf top   # crop a region
pdfinfo doc.pdf
```

Text assertions catch wrong numbers; only looking catches wrong layout.
