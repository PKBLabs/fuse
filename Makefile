# Flexible User-extensible Simulation Editor (FUSE)
#
# Developer test-suite shortcuts. These targets are intentionally thin wrappers
# around pytest so they work locally, in CI, and in release checklists.

PYTHON ?= $(if $(wildcard ./fuse/.venv/bin/python),./fuse/.venv/bin/python,python3)
PYTEST := PYTHONPATH="$(CURDIR)" $(PYTHON) -m pytest

FAST_MARKERS := not sst_live and not sst_remote and not sst_ext and not gem5_live and not slow
SST_PLUGIN_MARKERS := not sst_live and not sst_remote and not sst_ext and not sst_external and not slow
GEM5_PLUGIN_MARKERS := not gem5_live and not slow
PLUGIN_MARKERS := not sst_live and not sst_remote and not sst_ext and not sst_external and not gem5_live and not slow
SST_EXTERNAL_FIXTURE_MARKERS := sst_external and not sst_live and not sst_remote and not sst_ext and not slow

.PHONY: help \
	test-core test-plugins test-sst-fast test-gem5-fast test-sst-external-fixtures \
	test-sst-full test-sst-live test-sst-live-15 test-sst-live-16 test-sst-external-live test-sst-remote \
	test-fast test-full-deterministic test-collect \
	test-coverage-core test-coverage-plugins test-coverage-sst test-coverage-deterministic

help:
	@echo "FUSE test targets:"
	@echo "  make test-core                   Tier 1: core tests only"
	@echo "  make test-plugins                Tier 2: deterministic plugin tests, SST + gem5"
	@echo "  make test-sst-fast               Tier 2: deterministic SST plugin tests"
	@echo "  make test-gem5-fast              Tier 2: deterministic gem5 plugin tests"
	@echo "  make test-sst-external-fixtures  Tier 3: deterministic SST external/custom fixture tests"
	@echo "  make test-sst-full               Full local SST test directory; live tests skip if unavailable"
	@echo "  make test-sst-live               Optional live SST tests only"
	@echo "  make test-sst-live-15            Optional live SST 15.x tests only"
	@echo "  make test-sst-live-16            Optional live SST 16.x tests only"
	@echo "  make test-sst-external-live      Optional SST external acceptance tests"
	@echo "  make test-sst-remote             Optional remote/SSH SST tests"
	@echo "  make test-fast                   Core + deterministic plugin + SST external fixture tests"
	@echo "  make test-coverage-core          Core tests with core/app coverage"
	@echo "  make test-coverage-plugins       Deterministic plugin tests with plugin coverage"
	@echo "  make test-coverage-sst           Deterministic SST tests with SST coverage"
	@echo "  make test-coverage-deterministic Core + deterministic plugin tests with coverage"

test-core:
	$(PYTEST) -q fuse/tests

test-plugins:
	$(PYTEST) -q fuse/plugins/community/sst/tests fuse/plugins/community/gem5/tests -m "$(PLUGIN_MARKERS)"

test-sst-fast:
	$(PYTEST) -q fuse/plugins/community/sst/tests -m "$(SST_PLUGIN_MARKERS)"

test-gem5-fast:
	$(PYTEST) -q fuse/plugins/community/gem5/tests -m "$(GEM5_PLUGIN_MARKERS)"

test-sst-external-fixtures:
	$(PYTEST) -q fuse/plugins/community/sst/tests -m "$(SST_EXTERNAL_FIXTURE_MARKERS)"

test-sst-full:
	$(PYTEST) -q fuse/plugins/community/sst/tests

test-sst-live:
	$(PYTEST) -q fuse/plugins/community/sst/tests -m "sst_live"

test-sst-live-15:
	$(PYTEST) -q fuse/plugins/community/sst/tests -m "sst_live and sst_15"

test-sst-live-16:
	$(PYTEST) -q fuse/plugins/community/sst/tests -m "sst_live and sst_16"

test-sst-external-live:
	$(PYTEST) -q fuse/plugins/community/sst/tests -m "sst_ext"

test-sst-remote:
	$(PYTEST) -q fuse/plugins/community/sst/tests -m "sst_remote"

test-fast test-full-deterministic: test-core test-plugins test-sst-external-fixtures

test-collect:
	$(PYTEST) --collect-only -q fuse/tests fuse/plugins/community/sst/tests fuse/plugins/community/gem5/tests

test-coverage-core:
	$(PYTEST) -q fuse/tests \
		--cov=fuse.core \
		--cov=fuse.app \
		--cov-report=term-missing \
		--cov-report=xml:coverage-core.xml

test-coverage-plugins:
	$(PYTEST) -q fuse/plugins/community/sst/tests fuse/plugins/community/gem5/tests -m "$(PLUGIN_MARKERS)" \
		--cov=fuse.plugins.community.sst \
		--cov=fuse.plugins.community.gem5 \
		--cov-report=term-missing \
		--cov-report=xml:coverage-plugins.xml

test-coverage-sst:
	$(PYTEST) -q fuse/plugins/community/sst/tests -m "not sst_live and not sst_remote and not sst_ext and not slow" \
		--cov=fuse.plugins.community.sst \
		--cov-report=term-missing \
		--cov-report=xml:coverage-sst.xml

test-coverage-deterministic:
	$(PYTEST) -q fuse/tests fuse/plugins/community/sst/tests fuse/plugins/community/gem5/tests -m "$(FAST_MARKERS)" \
		--cov=fuse.core \
		--cov=fuse.app \
		--cov=fuse.plugins.community.sst \
		--cov=fuse.plugins.community.gem5 \
		--cov-report=term-missing \
		--cov-report=xml:coverage-deterministic.xml
