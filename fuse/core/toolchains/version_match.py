# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
#
# FUSE is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
"""Version parsing and matching helpers for simulator toolchains.

The helpers compare free-form tool output with target version requirements.
They intentionally accept imperfect version strings because simulator commands
may include prefixes, suffixes, or build labels."""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class ParsedVersion:
    """Normalized representation of a version string."""
    parts: tuple[int, ...]
    text: str


@dataclass(frozen=True)
class VersionMatchResult:
    """Result of comparing an expected version with a discovered version."""
    matched: bool
    expected: str
    detected: str
    policy: str
    message: str


def parse_version_text(text: str) -> ParsedVersion | None:
    """Extract comparable numeric version parts from text."""
    if not text:
        return None

    matches = list(re.finditer(r"(\d+(?:\.\d+){0,3})", text))

    if not matches:
        return None

    # Prefer dotted version strings so product names such as "gem5" do not
    # get mistaken for the toolchain version when later output contains
    # "25.1.0.1". If no dotted version is present, fall back to the first
    # numeric token to preserve support for major-only versions.
    match = next((candidate for candidate in matches if "." in candidate.group(1)), matches[0])
    version_text = match.group(1)
    parts = tuple(int(part) for part in version_text.split("."))

    return ParsedVersion(parts=parts, text=version_text)


def compare_version_prefix(
    expected_version: str,
    detected_text: str,
    policy: str = "major",
) -> VersionMatchResult:
    """Compare an expected version prefix with discovered version text."""
    expected = parse_version_text(expected_version)
    detected = parse_version_text(detected_text)

    if expected is None:
        return VersionMatchResult(
            matched=True,
            expected=expected_version,
            detected=detected_text,
            policy=policy,
            message="No expected version was configured.",
        )

    if detected is None:
        return VersionMatchResult(
            matched=False,
            expected=expected_version,
            detected=detected_text,
            policy=policy,
            message=(
                "Could not detect a version number in the toolchain output. "
                "Verify the toolchain manually."
            ),
        )

    if policy == "exact":
        expected_prefix = expected.parts
    elif policy == "major":
        expected_prefix = expected.parts[:1]
    elif policy == "major_minor":
        expected_prefix = expected.parts[:2]
    elif policy == "major_minor_patch":
        expected_prefix = expected.parts[:3]
    else:
        raise ValueError(f"Unsupported version match policy: {policy}")

    detected_prefix = detected.parts[: len(expected_prefix)]
    matched = detected_prefix == expected_prefix

    if matched:
        return VersionMatchResult(
            matched=True,
            expected=expected.text,
            detected=detected.text,
            policy=policy,
            message=(
                f"Detected version {detected.text} is compatible with "
                f"expected version {expected.text} using policy '{policy}'."
            ),
        )

    return VersionMatchResult(
        matched=False,
        expected=expected.text,
        detected=detected.text,
        policy=policy,
        message=(
            f"Detected version {detected.text} is not compatible with "
            f"expected version {expected.text} using policy '{policy}'."
        ),
    )