"""The faces a document embeds, and what happens when one is absent.

A substituted face on a client-facing invoice is the failure this guards: it
is invisible on the machine that rendered it, because that machine has a font
that looks close enough. `continue` was the wrong choice here — the document
goes to someone who is being asked for money.
"""

import pytest

from billwright.fonts import FACES, FontError, missing_faces
from billwright.load import load_brand
from billwright.paths import DEFAULT_ASSETS
from billwright.render import font_face_css


def test_the_packaged_assets_hold_every_declared_face():
    """`pip install billwright` must render correctly with no flags.

    The faces used to sit in the repository root, outside the wheel, so an
    installed copy typeset whatever WeasyPrint substituted.
    """
    assert missing_faces(DEFAULT_ASSETS) == []


def test_missing_faces_names_every_absent_file(tmp_path):
    (tmp_path / "fonts").mkdir()
    assert missing_faces(tmp_path) == [filename for filename, _ in FACES]


def test_a_directory_holding_only_the_licence_is_not_enough(tmp_path):
    """`doctor` used to accept any non-empty fonts/ — this is that hole."""
    fonts = tmp_path / "fonts"
    fonts.mkdir()
    (fonts / "OFL.txt").write_text("licence\n", encoding="utf-8")
    assert missing_faces(tmp_path) == [filename for filename, _ in FACES]


def test_a_missing_face_is_an_error_not_a_substitution(tmp_path, profile):
    brand = load_brand(profile)
    (tmp_path / "fonts").mkdir()
    with pytest.raises(FontError) as caught:
        font_face_css(brand, tmp_path)
    message = str(caught.value)
    assert "Inter-Regular.otf" in message
    assert str(tmp_path / "fonts") in message


def test_every_declared_face_is_embedded_from_the_packaged_assets(profile):
    brand = load_brand(profile)
    css = font_face_css(brand, DEFAULT_ASSETS)
    assert css.count("@font-face") == len(FACES)
    assert "data:font/otf;base64," in css
