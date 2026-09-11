"""Bills and yearly statements, generated from data."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("billwright")
except PackageNotFoundError:  # pragma: no cover - a source tree with nothing installed
    # Not a silent default: it is a version string that cannot be mistaken for
    # a release, which is what an un-installed source tree actually is.
    __version__ = "0+unknown"

__all__ = ["__version__"]
