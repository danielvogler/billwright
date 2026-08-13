"""Make WeasyPrint's native libraries loadable on macOS.

WeasyPrint binds Pango/GLib/Cairo through cffi. Homebrew installs them in
``/opt/homebrew/lib``, which is not on dyld's default search path, so importing
WeasyPrint fails with ``cannot load library 'libgobject-2.0-0'`` even though the
library is sitting right there.

``DYLD_FALLBACK_LIBRARY_PATH`` is read by dyld when the process starts, so
setting it from inside Python is too late. The fix is to re-exec once with the
variable in place, guarded by a sentinel so it can never loop.

Call ``ensure_native_libraries()`` before anything imports ``weasyprint``.

This works for the CLI, which owns its own process. It does **not** work under
pytest: pytest installs output capture before it imports ``conftest.py``, so a
re-exec from there inherits the captured file descriptors and the relaunched run
writes its entire output into a buffer nobody reads. Test runs therefore get the
variable from the environment instead (see ``NATIVE_LIB_PATH`` in the Makefile),
and use ``missing_native_library_hint`` to fail with one clear message when it
is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SENTINEL = "BILLWRIGHT_NATIVE_LIBS_READY"
_PROBE = "libgobject-2.0.dylib"
_CANDIDATES = ("/opt/homebrew/lib", "/usr/local/lib")
_DYLD_DEFAULTS = ("/usr/local/lib", "/usr/lib")


def library_directories() -> list[str]:
    """Directories holding the native libraries, if any are installed here."""
    return [path for path in _CANDIDATES if (Path(path) / _PROBE).exists()]


def missing_native_library_hint() -> str | None:
    """An actionable message when the libraries exist but dyld cannot see them.

    Returns ``None`` when nothing is wrong — not macOS, already on the path, or
    the libraries genuinely are not installed (in which case WeasyPrint's own
    error naming the missing library is more useful than ours).
    """
    if sys.platform != "darwin":
        return None
    found = library_directories()
    if not found:
        return None
    current = [p for p in os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(":") if p]
    if all(path in current for path in found):
        return None
    return (
        f"Pango/Cairo are installed in {', '.join(found)} but dyld cannot see them, "
        "so every rendering test would fail on 'cannot load library'.\n"
        "dyld reads DYLD_FALLBACK_LIBRARY_PATH only at process start, so it has to "
        "be set before pytest launches:\n\n"
        "    make test          # sets it for you\n"
        f"    DYLD_FALLBACK_LIBRARY_PATH={':'.join(found)} pytest\n"
    )


def ensure_native_libraries(argv: list[str] | None = None) -> None:
    """Re-exec the CLI with a working library path if macOS needs one.

    No-op elsewhere, and no use outside the CLI — see the module docstring.
    """
    if sys.platform != "darwin" or os.environ.get(_SENTINEL):
        return

    found = library_directories()
    if not found:
        # Nothing to add. Let WeasyPrint raise its own, more informative error.
        return

    current = [p for p in os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "").split(":") if p]
    if all(path in current for path in found):
        os.environ[_SENTINEL] = "1"
        return

    ordered = [*found, *(p for p in current if p not in found), *_DYLD_DEFAULTS]
    env = {
        **os.environ,
        "DYLD_FALLBACK_LIBRARY_PATH": ":".join(dict.fromkeys(ordered)),
        _SENTINEL: "1",
    }
    arguments = sys.argv[1:] if argv is None else argv
    os.execve(sys.executable, [sys.executable, "-m", "billwright", *arguments], env)
