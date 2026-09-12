# billwright: typeset invoices and year-end accounts from plain TOML.
#
#   make setup                     install dependencies (run once)
#   make bill BILL=RE-26001        render one bill into out/
#   make statement YEAR=2026       render the yearly accounts into out/
#   make new CLIENT=example-institute   scaffold the next bill number
#
# `make help` lists everything.

BILL   ?= RE-26001
YEAR   ?= 2026
CLIENT ?= example-institute

# WeasyPrint binds Pango/GLib/Cairo through cffi, and Homebrew puts them
# somewhere dyld does not look by default. The `billwright` CLI repairs this
# itself (src/billwright/native.py), but pytest and any direct `uv run python`
# do not go through that entry point, so set it here too.
ifeq ($(shell uname),Darwin)
export DYLD_FALLBACK_LIBRARY_PATH := /opt/homebrew/lib:/usr/local/lib:/usr/lib
endif

.DEFAULT_GOAL := help

.PHONY: help setup bill statement new list check-bills preview archive \
        test lint fmt scan types hooks doctor check clean \
        clean-dist build dist-check release-check

help:  ## List available targets
	@grep -hE '^[a-zA-Z_.-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "} {printf "  %-18s %s\n", $$1, $$2}'

# ---- setup ----

setup:  ## Install dependencies into .venv (run once, then after dependency changes)
	uv sync

# ---- documents ----

bill:  ## Render one bill:  make bill BILL=RE-26001
	uv run billwright bill $(BILL)

statement:  ## Render the yearly accounts:  make statement YEAR=2026
	uv run billwright statement $(YEAR)

new:  ## Scaffold the next bill:  make new CLIENT=example-institute
	uv run billwright new --client $(CLIENT)

list:  ## List issued bills:  make list [YEAR=2026]
	uv run billwright list $(if $(YEAR),--year $(YEAR))

doctor:  ## Validate the profile and the environment
	uv run billwright doctor

check-bills:  ## Numbering gaps, duplicates and sanity checks
	uv run billwright check

preview:  ## Render a bill and open it:  make preview BILL=RE-26001
	uv run billwright bill $(BILL)
	@open out/*$(BILL)*.pdf 2>/dev/null || echo "rendered into out/"

# ---- archive ----
#
# Deliberately separate from `bill`. An archived PDF is the record of what the
# client was sent (OR Art. 958f: keep it ten years), so it is written only when
# you have looked at the draft in out/ and meant it.

archive:  ## Write a reviewed bill into archive/:  make archive BILL=RE-26001
	uv run billwright bill $(BILL) --archive

archive-statement:  ## Write the yearly accounts into archive/:  make archive-statement YEAR=2026
	uv run billwright statement $(YEAR) --archive

# ---- checks ----

test:  ## Run the test suite
	uv run pytest

lint:  ## Check formatting and lint rules
	uv run ruff check .
	uv run ruff format --check .

fmt:  ## Reformat the code
	uv run ruff format .
	uv run ruff check --fix .

scan:  ## Fail if a tracked file contains a private value
	uv run billwright scan

types:  ## Type-check src/
	uv run mypy

hooks:  ## Install the pre-commit hooks (run once)
	uv run pre-commit install

check: lint scan types test check-bills  ## Everything CI runs
	uv run pre-commit run --all-files

# ---- releasing ----
#
# Pushing a `v*` tag is the whole release; see AGENTS.md "Releasing it". These
# targets run the same scripts the workflow runs, so the rehearsal and the
# release cannot drift apart.

clean-dist:  ## Remove built artifacts
	rm -rf dist

build: clean-dist  ## Build the sdist and wheel into dist/
	uv build

dist-check: build  ## Build, then prove the wheel renders once installed
	uvx twine check dist/*
	scripts/verify-wheel.sh dist/*.whl

# Everything the release workflow checks, before a tag exists to check it. A tag
# can be deleted; a version uploaded to PyPI can only be yanked, never replaced.
release-check: check dist-check  ## Rehearse a release locally
	@version=$$(uv run python -c 'import tomllib,pathlib; print(tomllib.loads(pathlib.Path("pyproject.toml").read_text())["project"]["version"])'); \
	scripts/changelog-section.sh "$$version" > /dev/null; \
	test -z "$$(git status --porcelain)" \
		|| { echo "working tree is dirty; commit before tagging" >&2; exit 1; }; \
	echo; \
	echo "ready to release $$version. To publish:"; \
	echo "  git tag -a v$$version -m 'v$$version'"; \
	echo "  git push origin v$$version"

# ---- housekeeping ----

clean:  ## Remove rendered drafts (never touches archive/)
	rm -rf out
