#!/usr/bin/env bash
# Verify a built wheel by installing it somewhere clean and using it.
#
# Every test in this repository imports from the working tree, where a file left
# out of the wheel is invisible: 0.2.0 shipped without the typeface and typeset
# client invoices in a substituted face, silently. This is the one check that
# looks at what somebody actually installs, and the last cheap moment to look —
# a version on PyPI can be yanked but never replaced.
#
# Used by `make dist-check` before tagging and by release.yml after building, so
# the release and the local rehearsal cannot drift apart.
#
# Usage: scripts/verify-wheel.sh path/to/wheel.whl
set -euo pipefail

wheel="${1:-}"
if [ -z "$wheel" ] || [ ! -f "$wheel" ]; then
  echo "usage: scripts/verify-wheel.sh path/to/wheel.whl" >&2
  exit 2
fi

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
venv="$workdir/venv"

uv venv "$venv" --quiet
VIRTUAL_ENV="$venv" uv pip install --quiet "$wheel"

# The console script resolves, and reports the version that was installed rather
# than the one in the working tree.
"$venv/bin/billwright" --version

# What the wheel is asked to carry beyond the code: the faces the stylesheet
# declares, their licence, and the operating manual the MCP server serves
# verbatim. Asserted against `fonts.FACES` rather than a second list here, so a
# face added to the stylesheet is a face this check starts demanding.
"$venv/bin/python" - <<'PY'
from billwright.fonts import fonts_dir, missing_faces
from billwright.paths import DEFAULT_ASSETS, PACKAGE_ROOT

missing = missing_faces(DEFAULT_ASSETS)
assert not missing, f"the installed wheel is missing font faces: {', '.join(missing)}"

licence = fonts_dir(DEFAULT_ASSETS) / "OFL.txt"
assert licence.is_file(), f"the installed wheel is missing the typeface licence: {licence}"

manual = PACKAGE_ROOT / "AGENTS.md"
assert manual.is_file(), f"the installed wheel is missing the operating manual: {manual}"
PY

# Presence is not typesetting: the faces can be in place and the render still
# fail on a native library or a template that did not travel. `example/` is the
# profile a clone falls through to, and the one CI renders.
"$venv/bin/billwright" --profile "$repo/example" --out "$workdir/out" bill RE-26001
pdf=$(ls "$workdir"/out/*RE-26001*.pdf)
test -s "$pdf" || { echo "the installed wheel rendered an empty PDF" >&2; exit 1; }

# The profile and the packaged assets, checked by the tool's own authority on
# "is this complete" rather than by a second opinion written here.
"$venv/bin/billwright" --profile "$repo/example" doctor

echo "installed wheel renders $(basename "$pdf")"
