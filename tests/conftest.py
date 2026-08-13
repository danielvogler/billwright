from pathlib import Path

import pytest

from billwright.native import missing_native_library_hint

REPO_ROOT = Path(__file__).resolve().parents[1]

# WeasyPrint's native libraries must be on dyld's search path before the process
# starts, so a test run cannot fix it for itself — see the NATIVE_LIB_PATH
# comment in the Makefile. Fail once, clearly, rather than letting every
# rendering test die on an unexplained `cannot load library 'libgobject-2.0-0'`.
if _hint := missing_native_library_hint():
    pytest.exit(_hint, returncode=1)


@pytest.fixture
def profile() -> Path:
    """The fictional profile. Tests never touch `data/`.

    `data/` is gitignored and holds real client names, rates and bank details;
    a suite that asserts against it puts those values into the repository and
    cannot run in public CI. Everything the tests need is in `example/`.
    """
    return REPO_ROOT / "example"


@pytest.fixture
def assets() -> Path:
    return REPO_ROOT / "assets"
