CONFIG ?= config.yml

# Upstream source of truth. `make sync-data` copies its dist/wismap/ artifacts
# into data/; `make check-data` asserts they have not drifted. With no checkout
# at WISBLOCK_DATA, the script clones WISBLOCK_DATA_REPO@WISBLOCK_DATA_REF —
# which is how CI syncs without a sibling working copy. The script defaults
# that URL to the upstream repository, so the targets also work on a machine
# that has never checked wisblock-data out.
WISBLOCK_DATA ?= ../../wisblock-data
WISBLOCK_DATA_REPO ?=
WISBLOCK_DATA_REF ?= master
export WISBLOCK_DATA WISBLOCK_DATA_REPO WISBLOCK_DATA_REF

# Prefer the project virtualenv when one is present, so the same target works
# locally and on a CI runner that installs into the system interpreter.
PYTHON ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || echo python3)

ifndef VERBOSE
.SILENT:
endif

.venv/touchfile: requirements.txt
 	ifeq (, $(shell which virtualenv))
 		$(error "Could not find virtualenv, consider doing `pip install virtualenv`")
 	endif
	test -d .venv || virtualenv .venv
	. .venv/bin/activate ; pip install -Ur requirements.txt
	touch .venv/touchfile

init: .venv/touchfile

freeze: .venv/touchfile
	set -e ; . .venv/bin/activate ; pip freeze

sync-data:
	tools/sync-data.sh

check-data:
	tools/sync-data.sh --check

# Are the committed consumer fixtures what the current catalog and validation
# logic actually produce? Snapshot, regenerate, compare — deliberately not a
# `git diff`, so the answer is the same on a CI runner and in a working tree
# that has other uncommitted changes. A stale result leaves the freshly
# generated files in place: the fix is to commit them.
check-fixtures:
	set -e ; \
	snapshot=$$(mktemp -d) ; \
	trap 'rm -rf "$$snapshot"' EXIT ; \
	cp -R tests/fixtures/validate tests/fixtures/solve "$$snapshot/" ; \
	$(PYTHON) tests/fixtures/_generate.py >/dev/null ; \
	if diff -r -q "$$snapshot/validate" tests/fixtures/validate >/dev/null && \
	   diff -r -q "$$snapshot/solve" tests/fixtures/solve >/dev/null ; then \
		echo "tests/fixtures match the current catalog and logic" ; \
	else \
		echo "ERROR: tests/fixtures were stale — they have been regenerated, commit the result:" ; \
		diff -r -q "$$snapshot/validate" tests/fixtures/validate || true ; \
		diff -r -q "$$snapshot/solve" tests/fixtures/solve || true ; \
		exit 1 ; \
	fi

list: .venv/touchfile
	set -e ; . .venv/bin/activate ; python wismap.py list

info: .venv/touchfile
	set -e ; . .venv/bin/activate ; python wismap.py info

combine: .venv/touchfile
	set -e ; . .venv/bin/activate ; python wismap.py combine

clean:
	find -iname "*.pyc" -delete
	find -iname "__pycache__" -delete

setup:
	pip install -Ur requirements.txt

# ---------------------------------------------------------------------------
# Web server
# ---------------------------------------------------------------------------

serve: .venv/touchfile
	set -e ; . .venv/bin/activate ; python -m wismap.api

check-openapi:
	set -e ; WISMAP_AUTH_ENABLED=false $(PYTHON) tests/check_openapi_coverage.py

# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# ---------------------------------------------------------------------------
# Docker
# ---------------------------------------------------------------------------

docker-build:
	docker build -t wismap .

docker-run:
	docker run --rm -p 5000:5000 -v ./data:/app/data:ro wismap

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

.PHONY: clean freeze sync-data check-data check-fixtures serve check-openapi frontend-install frontend-dev frontend-build docker-build docker-run docker-up docker-down

