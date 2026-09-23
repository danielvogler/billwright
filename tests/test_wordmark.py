"""The wordmark template treats brand.toml's [wordmark] as the open mapping it is.

Under StrictUndefined an absent key is an error rather than a falsy value, so a
template written as though keys were optional has to read them with .get().
"""

from billwright.model import Brand
from billwright.render import _environment


def render(**wordmark: str) -> str:
    template = _environment().get_template("_wordmark.html.j2")
    return template.render(brand=Brand(wordmark=wordmark))


def test_a_one_line_wordmark_needs_only_line2():
    html = render(line2="ACME")
    assert "ACME" in html
    assert "head__tagline" not in html


def test_the_dot_defaults_to_a_period():
    assert '<span class="dot">.</span>' in render(line2="ACME")


def test_an_empty_dot_means_no_dot():
    """A brand decision the profile makes in brand.toml, not in a template."""
    assert 'class="dot"' not in render(line2="ACME", dot="")


def test_the_accent_part_follows_line2_in_its_own_span():
    html = render(line2="bill", accent="wright", dot="")
    assert 'bill<span class="wordmark__accent">wright</span>' in html


def test_a_mark_is_drawn_before_the_text():
    template = _environment().get_template("_wordmark.html.j2")
    brand = Brand(wordmark={"line2": "ACME"}, mark="data:image/png;base64,AA==")
    html = template.render(brand=brand)
    assert html.index('class="wordmark__mark"') < html.index("ACME")
    assert "wordmark--with-mark" in html


def test_without_a_mark_the_markup_is_unchanged():
    assert "wordmark--with-mark" not in render(line2="ACME")
