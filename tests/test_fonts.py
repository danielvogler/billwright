"""The faces a document embeds, and what happens when one is absent.

A substituted face on a client-facing invoice is the failure this guards: it
is invisible on the machine that rendered it, because that machine has a font
that looks close enough. `continue` was the wrong choice here — the document
goes to someone who is being asked for money.
"""

import shutil

import pytest

from billwright.fonts import FACES, FontError, missing_faces
from billwright.load import ProfileError, find_bill, load_brand, load_company
from billwright.paths import DEFAULT_ASSETS
from billwright.render import font_face_css, render_bill


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


INTER_REGULAR = DEFAULT_ASSETS / "fonts" / "Inter-Regular.otf"


@pytest.fixture
def custom(profile, tmp_path):
    """A copy of the example profile, about to declare faces of its own."""
    root = tmp_path / "profile"
    shutil.copytree(profile, root)
    return root


def declare(root, faces, *, copy=True):
    """Write ``faces`` into brand.toml and, unless told not to, the files onto disk."""
    lines = [f'  {{ file = "{name}", weight = {weight} }},' for name, weight in faces]
    brand = root / "brand.toml"
    text = brand.read_text(encoding="utf-8")
    brand.write_text(
        text.replace(
            'font_family = "Inter"\n',
            'font_family = "Custom"\nfaces = [\n' + "\n".join(lines) + "\n]\n",
        ),
        encoding="utf-8",
    )
    if copy:
        for name, _ in faces:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(INTER_REGULAR, root / name)


def test_a_profile_declares_its_own_faces(custom, tmp_path):
    """The typeface is profile data, not three filenames in the engine.

    It used to be a constant, so a company with another typeface had to put its
    files on disk under Inter's names: filenames lying about their contents, on
    the path that renders client invoices.
    """
    declare(custom, [("fonts/Custom-Regular.otf", 400), ("fonts/Custom-Bold.ttf", 600)])
    empty_assets = tmp_path / "no-assets"

    css = font_face_css(load_brand(custom), empty_assets)

    assert css.count("@font-face") == 2
    assert "font-family: 'Custom'" in css
    assert "font-weight: 600" in css
    assert "format('opentype')" in css
    assert "format('truetype')" in css


def test_without_declared_faces_the_packaged_ones_are_used(profile):
    assert load_brand(profile).faces == ()


def test_a_declared_face_that_is_missing_refuses_to_load(custom):
    """Same rule as the packaged faces: a substitution is found out too late."""
    declare(custom, [("fonts/Custom-Regular.otf", 400)], copy=False)
    with pytest.raises(ProfileError, match="Custom-Regular.otf"):
        load_brand(custom)


@pytest.mark.parametrize(
    ("faces", "complaint"),
    [
        ([("fonts/A.woff", 400)], ".otf or .ttf"),
        ([("fonts/A.otf", 450)], "weight"),
        ([("fonts/A.otf", 400), ("fonts/B.otf", 400)], "twice"),
    ],
)
def test_a_malformed_face_list_refuses_to_load(custom, faces, complaint):
    declare(custom, faces)
    with pytest.raises(ProfileError, match=complaint):
        load_brand(custom)


@pytest.mark.parametrize("name", ["../outside.otf", "/tmp/outside.otf"])
def test_a_face_outside_the_profile_refuses_to_load(custom, name):
    """A brand.toml must not read files from elsewhere on the machine."""
    declare(custom, [("fonts/A.otf", 400)])
    brand = custom / "brand.toml"
    brand.write_text(
        brand.read_text(encoding="utf-8").replace("fonts/A.otf", name), encoding="utf-8"
    )
    with pytest.raises(ProfileError, match="inside the profile"):
        load_brand(custom)


def test_a_bill_renders_in_declared_faces(custom, tmp_path):
    declare(
        custom,
        [("fonts/C-Regular.otf", 400), ("fonts/C-Medium.otf", 500), ("fonts/C-Semi.otf", 600)],
    )
    bill = find_bill(custom, "RE-26001")
    target = tmp_path / "out" / "bill.pdf"

    result = render_bill(
        bill, load_company(custom), load_brand(custom), tmp_path / "no-assets", target
    )

    assert result.pages == 1
    assert target.is_file()
