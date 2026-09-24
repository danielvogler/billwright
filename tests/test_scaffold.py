"""Deterministic scaffold, agent fills, deterministic validation.

The middle step is the only one that needs judgement, and it only has to supply
facts. These tests pin the two ends: the scaffold covers every key the loader
reads, and a filled-in scaffold passes `doctor`.
"""

import shutil
import tomllib

import pytest

from billwright.doctor import Level, check_company, diagnose
from billwright.load import ProfileError, load_brand
from billwright.paths import DEFAULT_ASSETS, PACKAGED_EXAMPLE, sample_profile
from billwright.scaffold import write_profile


def load(path):
    with path.open("rb") as handle:
        return tomllib.load(handle)


def keys(data, prefix=""):
    """Every key path in a TOML table, as dotted strings."""
    found = set()
    for key, value in data.items():
        path = f"{prefix}{key}"
        found.add(path)
        if isinstance(value, dict):
            found |= keys(value, f"{path}.")
    return found


def test_the_scaffold_covers_every_key_the_sample_profile_uses(profile, tmp_path):
    """A key added to the model must not silently go missing from the scaffold.

    Someone filling this in has no other list of what exists; a field absent
    here is a field they never learn about.
    """
    write_profile(tmp_path / "new", brand_source=profile)

    expected = keys(load(profile / "company.toml"))
    scaffolded = keys(load(tmp_path / "new" / "company.toml"))
    assert expected - scaffolded == set()


def test_the_client_scaffold_covers_the_sample_client(profile, tmp_path):
    write_profile(tmp_path / "new", brand_source=profile)

    sample = next((profile / "clients").glob("*.toml"))
    scaffolded = tmp_path / "new" / "clients" / "your-client.toml"
    assert keys(load(sample)) - keys(load(scaffolded)) == set()


def test_every_field_is_empty(tmp_path):
    """It is a form, not a starting company. A left-in value would be issued."""
    write_profile(tmp_path / "new")
    company = load(tmp_path / "new" / "company.toml")

    assert company["name"] == ""
    assert company["iban"] == ""
    assert company["address"]["street"] == ""
    # Except the ones where a value is the safe answer.
    assert company["address"]["country"] == "CH"
    assert company["vat_registered"] is False


def test_required_and_optional_are_marked(tmp_path):
    write_profile(tmp_path / "new")
    text = (tmp_path / "new" / "company.toml").read_text(encoding="utf-8")
    assert "# required" in text
    assert "# optional" in text


def test_the_brand_is_copied_rather_than_emptied(profile, tmp_path):
    """A blank palette renders a blank document; the neutral default is usable."""
    write_profile(tmp_path / "new", brand_source=profile)
    assert load(tmp_path / "new" / "brand.toml")["colors"]["ink"]


def test_the_logo_a_copied_brand_names_is_copied_with_it(profile, tmp_path):
    """Otherwise the new profile names a file it does not have, and cannot load."""
    written = write_profile(tmp_path / "new", brand_source=profile)
    assert tmp_path / "new" / "mark.svg" in written
    assert load_brand(tmp_path / "new").mark.startswith("data:image/svg+xml")


def test_the_faces_a_copied_brand_declares_are_copied_with_it(profile, tmp_path):
    """Same reason as the logo: a profile naming files it lacks cannot render."""
    source = tmp_path / "source"
    shutil.copytree(profile, source)
    (source / "fonts").mkdir()
    shutil.copyfile(DEFAULT_ASSETS / "fonts" / "Inter-Regular.otf", source / "fonts" / "R.otf")
    brand = source / "brand.toml"
    brand.write_text(
        brand.read_text(encoding="utf-8").replace(
            'font_family = "Inter"\n',
            'font_family = "Inter"\nfaces = [{ file = "fonts/R.otf", weight = 400 }]\n',
        ),
        encoding="utf-8",
    )

    written = write_profile(tmp_path / "new", brand_source=source)

    assert tmp_path / "new" / "fonts" / "R.otf" in written
    assert load_brand(tmp_path / "new").faces[0].file == tmp_path / "new" / "fonts" / "R.otf"


def test_a_copied_brand_naming_a_file_outside_it_is_refused(profile, tmp_path):
    """Otherwise the copy would be written outside the new profile."""
    source = tmp_path / "source"
    shutil.copytree(profile, source)
    brand = source / "brand.toml"
    brand.write_text(
        brand.read_text(encoding="utf-8").replace('mark = "mark.svg"', 'mark = "../escape.svg"'),
        encoding="utf-8",
    )
    (tmp_path / "escape.svg").write_text("<svg/>", encoding="utf-8")

    with pytest.raises(ProfileError, match="inside the profile"):
        write_profile(tmp_path / "new" / "deep", brand_source=source)
    assert not (tmp_path / "new").exists()


def test_init_profile_falls_back_to_the_packaged_sample(tmp_path):
    """An installed copy has no ./example; the package carries one (#10)."""
    assert sample_profile(tmp_path) == PACKAGED_EXAMPLE


def test_a_local_example_takes_precedence(profile, tmp_path):
    local = tmp_path / "example"
    local.mkdir()
    (local / "brand.toml").write_text((profile / "brand.toml").read_text(encoding="utf-8"))
    assert sample_profile(tmp_path) == local


def test_a_fresh_scaffold_fails_doctor_with_the_missing_fields(tmp_path):
    """The loop is: scaffold, fill, validate. An empty form must not pass."""
    write_profile(tmp_path / "new")
    errors = [p.message for p in check_company(tmp_path / "new") if p.level is Level.ERROR]

    assert any("name is missing" in m for m in errors)
    assert any("iban is missing" in m for m in errors)
    # Reported once, with its reason attached — not twice by two checks.
    assert len([m for m in errors if "iban is missing" in m]) == 1


def test_a_filled_scaffold_passes_doctor(profile, tmp_path):
    """The other end of the loop: fill in the required fields and it is valid."""
    target = tmp_path / "new"
    write_profile(target, brand_source=profile)

    path = target / "company.toml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'name = ""\n\n# optional — the person', 'name = "Test AG"\n\n# optional — the person'
    )
    text = text.replace('iban = ""', 'iban = "CH93 0076 2011 6238 5295 7"')
    text = text.replace(
        '''[address]
name = ""
street = ""
house_number = ""
postal_code = ""
city = ""''',
        '''[address]
name = "Test AG"
street = "Teststrasse"
house_number = "1"
postal_code = "8001"
city = "Zürich"''',
    )
    path.write_text(text, encoding="utf-8")

    (target / "clients" / "your-client.toml").unlink()

    errors = [p for p in diagnose(target) if p.level is Level.ERROR]
    assert errors == [], [str(p) for p in errors]


def test_it_refuses_to_overwrite(tmp_path):
    """A profile is someone's bank details; a scaffold must never land on one."""
    target = tmp_path / "new"
    write_profile(target)
    with pytest.raises(FileExistsError):
        write_profile(target)


def test_no_placeholder_directories(tmp_path):
    """No bills/, years/ or .gitkeep — writers create what they need."""
    target = tmp_path / "new"
    write_profile(target)
    assert not (target / "bills").exists()
    assert not (target / "years").exists()
    assert list(target.rglob(".gitkeep")) == []
