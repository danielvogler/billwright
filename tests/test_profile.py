"""Profile resolution: which directory a run bills from.

The stakes are asymmetric. Falling through to `example/` when a real profile
was asked for would issue an invoice under a fictional company; erroring is
always the better failure. So a requested profile is strict, and only the
discovered candidates fall through.
"""

from pathlib import Path

import pytest

from billwright.load import (
    ARCHIVE_ENV,
    PROFILE_ENV,
    ProfileError,
    is_profile_dir,
    resolve_archive_dir,
    resolve_profile,
)
from billwright.paths import ArchiveLocationError


def make_profile(root: Path, name: str) -> Path:
    """A directory that counts as a profile: it has company.toml."""
    path = root / name
    path.mkdir(parents=True, exist_ok=True)
    (path / "company.toml").write_text('name = "Test"\n', encoding="utf-8")
    return path


def test_is_profile_dir_needs_company_toml(tmp_path):
    empty = tmp_path / "data"
    empty.mkdir()
    assert not is_profile_dir(empty)
    assert is_profile_dir(make_profile(tmp_path, "other"))


def test_falls_back_to_example_when_no_data(tmp_path):
    example = make_profile(tmp_path, "example")
    assert resolve_profile(root=tmp_path, env={}) == example


def test_half_built_data_falls_through_to_example(tmp_path):
    """A fresh clone must render the sample, not error on an empty data/."""
    (tmp_path / "data").mkdir()
    example = make_profile(tmp_path, "example")
    assert resolve_profile(root=tmp_path, env={}) == example


def test_data_wins_over_example_once_it_has_a_company(tmp_path):
    data = make_profile(tmp_path, "data")
    make_profile(tmp_path, "example")
    assert resolve_profile(root=tmp_path, env={}) == data


def test_configured_profile_wins_over_data(tmp_path):
    configured = make_profile(tmp_path, "acme")
    make_profile(tmp_path, "data")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.billwright]\nprofile = "acme"\n', encoding="utf-8"
    )
    assert resolve_profile(root=tmp_path, env={}) == configured


def test_configured_profile_falls_through_when_half_built(tmp_path):
    """The tracked pyproject.toml points at data/, which a stranger will not have."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.billwright]\nprofile = "data"\n', encoding="utf-8"
    )
    example = make_profile(tmp_path, "example")
    assert resolve_profile(root=tmp_path, env={}) == example


def test_environment_wins_over_configured_and_data(tmp_path):
    from_env = make_profile(tmp_path, "from-env")
    make_profile(tmp_path, "data")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.billwright]\nprofile = "data"\n', encoding="utf-8"
    )
    resolved = resolve_profile(root=tmp_path, env={PROFILE_ENV: "from-env"})
    assert resolved == from_env


def test_flag_wins_over_everything(tmp_path):
    flagged = make_profile(tmp_path, "flagged")
    make_profile(tmp_path, "data")
    resolved = resolve_profile(flagged, root=tmp_path, env={PROFILE_ENV: "data"})
    assert resolved == flagged


def test_bad_flag_is_an_error_not_a_fallback(tmp_path):
    make_profile(tmp_path, "example")
    with pytest.raises(ProfileError, match="--profile"):
        resolve_profile(tmp_path / "typo", root=tmp_path, env={})


def test_bad_environment_variable_is_an_error_not_a_fallback(tmp_path):
    make_profile(tmp_path, "example")
    with pytest.raises(ProfileError, match=PROFILE_ENV):
        resolve_profile(root=tmp_path, env={PROFILE_ENV: "typo"})


def test_no_profile_anywhere_names_what_was_tried(tmp_path):
    with pytest.raises(ProfileError) as exc:
        resolve_profile(root=tmp_path, env={})
    message = str(exc.value)
    assert "data" in message and "example" in message


def test_repository_resolves_to_a_real_profile(profile):
    """Whatever this checkout has, resolution lands on a usable profile."""
    resolved = resolve_profile(root=profile.parent, env={})
    assert is_profile_dir(resolved)


def test_no_gitkeep_placeholders(profile):
    """A committed-but-empty data/ would be selected and then fail to load."""
    root = profile.parent
    assert not list(root.glob("data/**/.gitkeep"))
    assert not list(root.glob("archive/**/.gitkeep"))
    assert not list(root.glob("out/**/.gitkeep"))


# ---- archive resolution ---------------------------------------------------
#
# Same shape as profile resolution, and deliberately so: the archive is the
# ten-year record (`OR Art. 958f`), and the one thing it must never be is a
# directory inside the virtualenv that the next `uv sync --reinstall` removes.


def test_archive_defaults_to_the_profile(tmp_path):
    data = make_profile(tmp_path, "data")
    assert resolve_archive_dir(profile=data, root=tmp_path, env={}) == data / "archive"


def test_configured_archive_wins_over_the_profile(tmp_path):
    data = make_profile(tmp_path, "data")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.billwright]\narchive = "records/bills"\n', encoding="utf-8"
    )
    resolved = resolve_archive_dir(profile=data, root=tmp_path, env={})
    assert resolved == tmp_path / "records" / "bills"


def test_environment_wins_over_the_configured_archive(tmp_path):
    data = make_profile(tmp_path, "data")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.billwright]\narchive = "records"\n', encoding="utf-8"
    )
    resolved = resolve_archive_dir(profile=data, root=tmp_path, env={ARCHIVE_ENV: "from-env"})
    assert resolved == tmp_path / "from-env"


def test_an_explicit_archive_dir_wins_over_everything(tmp_path):
    data = make_profile(tmp_path, "data")
    resolved = resolve_archive_dir(
        tmp_path / "flagged", profile=data, root=tmp_path, env={ARCHIVE_ENV: "from-env"}
    )
    assert resolved == tmp_path / "flagged"


def test_an_absolute_configured_archive_is_left_alone(tmp_path):
    """Theirs lives outside the working directory entirely — that must be sayable."""
    data = make_profile(tmp_path, "data")
    elsewhere = tmp_path / "elsewhere" / "archive"
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.billwright]\narchive = "{elsewhere}"\n', encoding="utf-8"
    )
    assert resolve_archive_dir(profile=data, root=tmp_path, env={}) == elsewhere


def test_an_archive_inside_the_installation_is_refused(tmp_path):
    data = make_profile(tmp_path, "data")
    doomed = tmp_path / "lib" / "python3.13" / "site-packages" / "archive"
    (tmp_path / "pyproject.toml").write_text(
        f'[tool.billwright]\narchive = "{doomed}"\n', encoding="utf-8"
    )
    with pytest.raises(ArchiveLocationError):
        resolve_archive_dir(profile=data, root=tmp_path, env={})
