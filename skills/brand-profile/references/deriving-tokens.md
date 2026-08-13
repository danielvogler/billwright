# Deriving tokens — worked procedure

## 1. Locate the palette

```bash
find . -name "global.css" -o -name "tokens.css" -not -path "*/node_modules/*"
grep -rn "@theme\|--color-\|:root" src/styles/
```

Also check for a second, competing definition:

```bash
ls brand/ 2>/dev/null && grep -n "TOKENS\|colors" brand/build.* 2>/dev/null
```

If the two disagree, the live site's stylesheet wins. Record the drift in the
company's profile skill so the next person does not rediscover it.

## 2. Convert oklch to hex

```python
import math

def oklch_to_hex(L, C, h):
    hr = math.radians(h)
    a, b = C * math.cos(hr), C * math.sin(hr)
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_**3, m_**3, s_**3
    r  =  4.0767416621*l - 3.3077115913*m + 0.2309699292*s
    g  = -1.2684380046*l + 2.6097574011*m - 0.3413193965*s
    bb = -0.0041960863*l - 0.7034186147*m + 1.7076147010*s

    def gamma(x):
        x = max(0.0, min(1.0, x))
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055

    return "#{:02X}{:02X}{:02X}".format(*[round(gamma(v) * 255) for v in (r, g, bb)])
```

Cross-check the result against any sibling repo that already converted the same
palette. Agreement is the confirmation; disagreement means one of you is wrong
and it is worth finding out which.

## 3. Measure a typeset wordmark

```python
from fontTools.ttLib import TTFont

font = TTFont(font_path)
upm = font["head"].unitsPerEm
cmap = font.getBestCmap()
cap_ratio = font["OS/2"].sCapHeight / upm     # e.g. Inter -> 0.7275

def width(text, size, tracking_em):
    return sum(font["hmtx"][cmap[ord(c)]][0] / upm * size + tracking_em * size
               for c in text)
```

For a tight `viewBox` on two stacked lines with baselines `y1`, `y2`:

- top = `y1 - cap_ratio * size`
- bottom = `y2` (caps have no descender)
- width = `max(width(line1), width(line2))`

Run it with `uv run --with fonttools python …` rather than installing anything.

## 4. Checklist before shipping

- [ ] Every colour in the stylesheets resolves to a token in `brand.toml`
- [ ] No raw hex anywhere in `src/`
- [ ] Page ground is white; the site's paper tone is not used as a fill
- [ ] The accent appears once or twice per page, not everywhere
- [ ] Font is vendored, static weights, embedded as data URIs
- [ ] Licence permits redistribution and `LICENSE` says so
- [ ] Rendered to PNG and actually looked at, in the real document
