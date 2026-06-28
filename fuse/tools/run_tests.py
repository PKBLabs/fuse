# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Standard FUSE pytest suite runner.

This module gives contributors and CI one canonical place for the supported
test-suite slices.  It deliberately shells out to pytest rather than importing
test modules so it can be used exactly like normal command-line pytest.

The intended ordering is:

1. ``core``
2. ``plugins``
3. ``sst-external-fixtures``
4. optional live/external/remote suites
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
import shlex
import subprocess
import sys
from typing import Sequence


CORE_TEST_PATH = "fuse/tests"
SST_TEST_PATH = "fuse/plugins/community/sst/tests"
GEM5_TEST_PATH = "fuse/plugins/community/gem5/tests"

# One-shot deterministic marker expression.  This excludes tests that require
# a live simulator, SSH endpoint, external acceptance environment, or long
# runtime.  It intentionally does not exclude deterministic SST external
# fixture tests.
FAST_MARKERS = "not sst_live and not sst_remote and not sst_ext and not gem5_live and not slow"

# Tier 2 plugin checks should exercise plugin-owned code without running the
# extra SST external/custom fixture tier.  That fixture tier is run explicitly
# after the base plugin tier.
SST_PLUGIN_MARKERS = (
    "not sst_live and not sst_remote and not sst_ext and not sst_external and not slow"
)
GEM5_PLUGIN_MARKERS = "not gem5_live and not slow"
PLUGIN_MARKERS = (
    "not sst_live and not sst_remote and not sst_ext and not sst_external "
    "and not gem5_live and not slow"
)
SST_EXTERNAL_FIXTURE_MARKERS = (
    "sst_external and not sst_live and not sst_remote and not sst_ext and not slow"
)


@dataclass(frozen=True)
class TestSuite:
    """A named pytest command slice."""

    name: str
    description: str
    pytest_args: tuple[str, ...]


SUITES: dict[str, TestSuite] = {
    "core": TestSuite(
        "core",
        "Tier 1: core FUSE tests only; no plugin test directories.",
        (CORE_TEST_PATH,),
    ),
    "plugins": TestSuite(
        "plugins",
        "Tier 2: deterministic plugin tests for SST and gem5, excluding SST external fixtures.",
        (SST_TEST_PATH, GEM5_TEST_PATH, "-m", PLUGIN_MARKERS),
    ),
    "sst-fast": TestSuite(
        "sst-fast",
        "Tier 2: deterministic SST plugin tests, excluding live, external fixtures, remote, and slow tests.",
        (SST_TEST_PATH, "-m", SST_PLUGIN_MARKERS),
    ),
    "gem5-fast": TestSuite(
        "gem5-fast",
        "Tier 2: deterministic gem5 plugin tests, excluding live and slow tests.",
        (GEM5_TEST_PATH, "-m", GEM5_PLUGIN_MARKERS),
    ),
    "sst-external-fixtures": TestSuite(
        "sst-external-fixtures",
        "Tier 3: deterministic SST external/custom component fixture tests.",
        (SST_TEST_PATH, "-m", SST_EXTERNAL_FIXTURE_MARKERS),
    ),
    "sst-full": TestSuite(
        "sst-full",
        "Full SST plugin test directory; live tests skip when local prerequisites are unavailable.",
        (SST_TEST_PATH,),
    ),
    "sst-live": TestSuite(
        "sst-live",
        "Optional live SST tests requiring a real local/containerized SST installation.",
        (SST_TEST_PATH, "-m", "sst_live"),
    ),
    "sst-live-15": TestSuite(
        "sst-live-15",
        "Optional live SST 15.x tests requiring a real local/containerized SST installation.",
        (SST_TEST_PATH, "-m", "sst_live and sst_15"),
    ),
    "sst-live-16": TestSuite(
        "sst-live-16",
        "Optional live SST 16.x tests requiring a real local/containerized SST installation.",
        (SST_TEST_PATH, "-m", "sst_live and sst_16"),
    ),
    "sst-external-live": TestSuite(
        "sst-external-live",
        "Optional SST external acceptance tests requiring the external validation environment.",
        (SST_TEST_PATH, "-m", "sst_ext"),
    ),
    "sst-remote": TestSuite(
        "sst-remote",
        "Optional SST remote/SSH tests.",
        (SST_TEST_PATH, "-m", "sst_remote"),
    ),
    "fast": TestSuite(
        "fast",
        "One-shot deterministic suite: core plus deterministic plugin tests, including SST external fixtures.",
        (CORE_TEST_PATH, SST_TEST_PATH, GEM5_TEST_PATH, "-m", FAST_MARKERS),
    ),
    "collect": TestSuite(
        "collect",
        "Collect core and plugin tests without running them.",
        ("--collect-only", "-q", CORE_TEST_PATH, SST_TEST_PATH, GEM5_TEST_PATH),
    ),
    "coverage-core": TestSuite(
        "coverage-core",
        "Core tests with core/app coverage.",
        (
            CORE_TEST_PATH,
            "--cov=fuse.core",
            "--cov=fuse.app",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage-core.xml",
        ),
    ),
    "coverage-plugins": TestSuite(
        "coverage-plugins",
        "Tier 2 deterministic plugin tests with SST/gem5 plugin coverage.",
        (
            SST_TEST_PATH,
            GEM5_TEST_PATH,
            "-m",
            PLUGIN_MARKERS,
            "--cov=fuse.plugins.community.sst",
            "--cov=fuse.plugins.community.gem5",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage-plugins.xml",
        ),
    ),
    "coverage-sst": TestSuite(
        "coverage-sst",
        "Deterministic SST tests, including external fixtures, with SST plugin coverage.",
        (
            SST_TEST_PATH,
            "-m",
            "not sst_live and not sst_remote and not sst_ext and not slow",
            "--cov=fuse.plugins.community.sst",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage-sst.xml",
        ),
    ),
    "coverage-deterministic": TestSuite(
        "coverage-deterministic",
        "One-shot core plus deterministic plugin tests with core/app/plugin coverage.",
        (
            CORE_TEST_PATH,
            SST_TEST_PATH,
            GEM5_TEST_PATH,
            "-m",
            FAST_MARKERS,
            "--cov=fuse.core",
            "--cov=fuse.app",
            "--cov=fuse.plugins.community.sst",
            "--cov=fuse.plugins.community.gem5",
            "--cov-report=term-missing",
            "--cov-report=xml:coverage-deterministic.xml",
        ),
    ),
}


def find_repo_root(start: Path | None = None) -> Path:
    """Return the repository root containing the top-level ``fuse`` package."""

    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (
            (candidate / "fuse" / "app" / "main.py").exists()
            and (candidate / "fuse" / "core").is_dir()
            and (candidate / "fuse" / "plugins").is_dir()
        ):
            return candidate

    raise RuntimeError(f"Could not locate FUSE repository root from {current}")


def build_pytest_args(suite_name: str, extra_args: Sequence[str] = ()) -> list[str]:
    """Build the pytest argument vector for ``suite_name``."""

    try:
        suite = SUITES[suite_name]
    except KeyError as exc:
        known = ", ".join(sorted(SUITES))
        raise ValueError(f"Unknown test suite {suite_name!r}. Known suites: {known}") from exc

    return ["-q", *suite.pytest_args, *extra_args]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "suite",
        nargs="?",
        choices=sorted(SUITES),
        default="fast",
        help="Named test suite to run. Defaults to %(default)s.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available suites and exit.",
    )
    parser.add_argument(
        "--print-only",
        action="store_true",
        help="Print the pytest command instead of running it.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args, passthrough = parser.parse_known_args(argv)

    if args.list:
        for suite in SUITES.values():
            print(f"{suite.name:24} {suite.description}")
        return 0

    passthrough = list(passthrough)
    if passthrough[:1] == ["--"]:
        passthrough = passthrough[1:]

    repo_root = find_repo_root()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        part
        for part in [str(repo_root), env.get("PYTHONPATH", "")]
        if part
    )

    pytest_args = build_pytest_args(args.suite, passthrough)
    command = [sys.executable, "-m", "pytest", *pytest_args]

    if args.print_only:
        print(shlex.join(command))
        return 0

    return subprocess.call(command, cwd=repo_root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
