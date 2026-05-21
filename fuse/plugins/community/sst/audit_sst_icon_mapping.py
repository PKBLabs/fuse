#!/usr/bin/env python3
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
"""
audit_sst_icon_mapping.py

Parse an SST-INFO stdout text file, run each parsed object through
sst_icon_resolver.py, and write a CSV audit showing which icon each
component/subcomponent maps to.

Typical use from the project root:

    python scripts/audit_sst_icon_mapping.py latest_sst_info_stdout.txt

or, if the script is in the project root:

    python audit_sst_icon_mapping.py latest_sst_info_stdout.txt

Outputs by default:

    sst_icon_audit.csv
    sst_icon_audit_summary.txt

The script expects sst_icon_resolver.py to be either:
    - in the same directory as this script,
    - in the parent directory of this script, or
    - in the current working directory.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


def import_icon_resolver():
    from fuse.plugins.community.sst import sst_icon_resolver
    return sst_icon_resolver


@dataclass
class SstInfoObject:
    element_library_index: str = ""
    element_library: str = ""
    element_library_description: str = ""
    object_kind: str = ""
    object_index: str = ""
    name: str = ""
    alias: str = ""
    description: str = ""
    eli_version: str = ""
    compiled_file: str = ""
    category: str = ""
    interface: str = ""
    parameter_count: str = ""
    port_count: str = ""
    subcomponent_slot_count: str = ""
    statistic_count: str = ""
    checkpointable: str = ""


@dataclass
class IconAuditRow:
    element_library_index: str
    element_library: str
    object_kind: str
    object_index: str
    name: str
    alias: str
    description: str
    category: str
    interface: str
    compiled_file: str
    guessed_icon_key: str
    guessed_icon_path: str
    resolved_icon_path: str
    icon_exists: str
    generic_fallback: str
    review_reason: str


SECTION_KINDS = {
    "Components": "Component",
    "SubComponents": "SubComponent",
    "Modules": "Module",
    "PortModules": "PortModule",
}

LIBRARY_RE = re.compile(r"^ELEMENT LIBRARY\s+(\d+)\s+=\s+(.+?)\s+\((.*)\)\s*$")
SECTION_RE = re.compile(
    r"^(Components|SubComponents|Modules|PortModules)\s+\((\d+)\s+total\)\s*$"
)
OBJECT_RE = re.compile(
    r"^\s+(Component|SubComponent|Module|PortModule)\s+(\d+):\s+(.+?)\s*$"
)
COUNT_RE = re.compile(
    r"^\s+(Parameters|Ports|SubComponent Slots|Statistics)\s+\((\d+)\s+total\)\s*$"
)


def strip_value(line: str, prefix: str) -> str:
    return line.split(prefix, 1)[1].strip()


def parse_sst_info(text: str, include_kinds: set[str]) -> list[SstInfoObject]:
    objects: list[SstInfoObject] = []

    current_library_index = ""
    current_library = ""
    current_library_description = ""
    current_section_kind = ""
    current: SstInfoObject | None = None

    def flush_current():
        nonlocal current
        if current is not None and current.object_kind in include_kinds:
            objects.append(current)
        current = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")

        library_match = LIBRARY_RE.match(line)
        if library_match:
            flush_current()
            current_library_index = library_match.group(1)
            current_library = library_match.group(2).strip()
            current_library_description = library_match.group(3).strip()
            current_section_kind = ""
            continue

        section_match = SECTION_RE.match(line.strip())
        if section_match:
            flush_current()
            current_section_kind = SECTION_KINDS[section_match.group(1)]
            continue

        object_match = OBJECT_RE.match(line)
        if object_match:
            flush_current()

            object_kind = object_match.group(1)
            object_index = object_match.group(2)
            object_name = object_match.group(3).strip()

            # Trust the object line first. The current section is mostly useful
            # for validating structure, but object_kind is explicit.
            current = SstInfoObject(
                element_library_index=current_library_index,
                element_library=current_library,
                element_library_description=current_library_description,
                object_kind=object_kind,
                object_index=object_index,
                name=object_name,
            )
            continue

        if current is None:
            continue

        stripped = line.strip()

        # Example:
        #   SubCompSender is aliased as: SubCompSender_alias
        if " is aliased as: " in stripped:
            current.alias = stripped.split(" is aliased as: ", 1)[1].strip()
            continue

        if stripped.startswith("Description:"):
            current.description = strip_value(stripped, "Description:")
            continue

        if stripped.startswith("ELI version:"):
            current.eli_version = strip_value(stripped, "ELI version:")
            continue

        if stripped.startswith("Compiled using file:"):
            current.compiled_file = strip_value(stripped, "Compiled using file:")
            continue

        if stripped.startswith("Category:"):
            current.category = strip_value(stripped, "Category:")
            continue

        if stripped.startswith("Interface:"):
            current.interface = strip_value(stripped, "Interface:")
            continue

        if stripped.startswith("Checkpointable:"):
            current.checkpointable = strip_value(stripped, "Checkpointable:")
            continue

        count_match = COUNT_RE.match(line)
        if count_match:
            label = count_match.group(1)
            count = count_match.group(2)

            if label == "Parameters":
                current.parameter_count = count
            elif label == "Ports":
                current.port_count = count
            elif label == "SubComponent Slots":
                current.subcomponent_slot_count = count
            elif label == "Statistics":
                current.statistic_count = count

    flush_current()
    return objects


def review_reason_for(
    obj: SstInfoObject,
    guessed_icon_key: str,
    guessed_icon_path: str,
    resolved_icon_path: Path,
) -> str:
    reasons: list[str] = []

    if guessed_icon_key == "generic_component":
        reasons.append("generic fallback")

    if not guessed_icon_path:
        reasons.append("resolver returned empty icon path")

    if guessed_icon_path and not resolved_icon_path.exists():
        reasons.append("icon file missing on disk")

    if not obj.description:
        reasons.append("missing description")

    if obj.object_kind in {"Module", "PortModule"}:
        reasons.append(f"{obj.object_kind} included for review")

    return "; ".join(reasons)


def audit_objects(objects: Iterable[SstInfoObject], resolver) -> list[IconAuditRow]:
    rows: list[IconAuditRow] = []

    for obj in objects:
        guessed_icon_key = resolver.guess_component_icon_key(
            name=obj.name,
            description=obj.description,
            category=obj.category,
            iface=obj.interface,
            element=obj.element_library,
            object_kind=obj.object_kind,
        )

        guessed_icon_path = resolver.guess_component_icon_path(
            name=obj.name,
            description=obj.description,
            category=obj.category,
            iface=obj.interface,
            element=obj.element_library,
            object_kind=obj.object_kind,
        )

        resolved_icon_path = resolver.resolve_icon_path(guessed_icon_path)
        icon_exists = bool(resolved_icon_path and resolved_icon_path.exists())

        rows.append(
            IconAuditRow(
                element_library_index=obj.element_library_index,
                element_library=obj.element_library,
                object_kind=obj.object_kind,
                object_index=obj.object_index,
                name=obj.name,
                alias=obj.alias,
                description=obj.description,
                category=obj.category,
                interface=obj.interface,
                compiled_file=obj.compiled_file,
                guessed_icon_key=guessed_icon_key,
                guessed_icon_path=guessed_icon_path,
                resolved_icon_path=str(resolved_icon_path) if resolved_icon_path else "",
                icon_exists="yes" if icon_exists else "no",
                generic_fallback="yes" if guessed_icon_key == "generic_component" else "no",
                review_reason=review_reason_for(
                    obj=obj,
                    guessed_icon_key=guessed_icon_key,
                    guessed_icon_path=guessed_icon_path,
                    resolved_icon_path=resolved_icon_path,
                ),
            )
        )

    return rows


def write_csv(rows: list[IconAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(asdict(rows[0]).keys()) if rows else [
        "element_library_index",
        "element_library",
        "object_kind",
        "object_index",
        "name",
        "alias",
        "description",
        "category",
        "interface",
        "compiled_file",
        "guessed_icon_key",
        "guessed_icon_path",
        "resolved_icon_path",
        "icon_exists",
        "generic_fallback",
        "review_reason",
    ]

    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for row in rows:
            writer.writerow(asdict(row))


def build_summary(rows: list[IconAuditRow]) -> str:
    total = len(rows)
    by_kind = Counter(row.object_kind for row in rows)
    by_icon = Counter(row.guessed_icon_key for row in rows)
    generic = [row for row in rows if row.generic_fallback == "yes"]
    missing = [row for row in rows if row.icon_exists == "no"]

    lines: list[str] = []
    lines.append("SST Icon Resolver Audit Summary")
    lines.append("=" * 35)
    lines.append("")
    lines.append(f"Total parsed objects: {total}")
    lines.append("")

    lines.append("Objects by kind:")
    for kind, count in sorted(by_kind.items()):
        lines.append(f"  {kind:16s} {count}")

    lines.append("")
    lines.append(f"Generic fallback rows: {len(generic)}")
    lines.append(f"Rows with missing icon files: {len(missing)}")
    lines.append("")

    lines.append("Top guessed icon keys:")
    for icon_key, count in by_icon.most_common(40):
        lines.append(f"  {icon_key:32s} {count}")

    if generic:
        lines.append("")
        lines.append("Generic fallback examples:")
        for row in generic[:50]:
            lines.append(
                f"  {row.element_library}.{row.name} "
                f"({row.object_kind}) - {row.description[:90]}"
            )
        if len(generic) > 50:
            lines.append(f"  ... and {len(generic) - 50} more")

    if missing:
        lines.append("")
        lines.append("Missing icon file examples:")
        for row in missing[:50]:
            lines.append(
                f"  {row.element_library}.{row.name} "
                f"-> {row.guessed_icon_key} / {row.guessed_icon_path}"
            )
        if len(missing) > 50:
            lines.append(f"  ... and {len(missing) - 50} more")

    return "\n".join(lines) + "\n"


def parse_include_kinds(args: argparse.Namespace) -> set[str]:
    include_kinds = {"Component", "SubComponent"}

    if args.include_modules:
        include_kinds.add("Module")

    if args.include_portmodules:
        include_kinds.add("PortModule")

    if args.include_all:
        include_kinds.update({"Module", "PortModule"})

    return include_kinds


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit SST component/subcomponent icon resolver mappings."
    )
    parser.add_argument(
        "sst_info_file",
        type=Path,
        help="Path to captured sst-info stdout text.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("sst_icon_audit.csv"),
        help="CSV output path. Default: sst_icon_audit.csv",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=Path("sst_icon_audit_summary.txt"),
        help="Summary text output path. Default: sst_icon_audit_summary.txt",
    )
    parser.add_argument(
        "--include-modules",
        action="store_true",
        help="Also include Modules in the audit.",
    )
    parser.add_argument(
        "--include-portmodules",
        action="store_true",
        help="Also include PortModules in the audit.",
    )
    parser.add_argument(
        "--include-all",
        action="store_true",
        help="Include Components, SubComponents, Modules, and PortModules.",
    )
    parser.add_argument(
        "--generic-only",
        action="store_true",
        help="Write only rows that fall back to generic_component.",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Write only rows whose resolved icon file does not exist.",
    )

    args = parser.parse_args()

    if not args.sst_info_file.exists():
        print(f"Input file does not exist: {args.sst_info_file}", file=sys.stderr)
        return 2

    resolver = import_icon_resolver()

    text = args.sst_info_file.read_text(encoding="utf-8", errors="replace")
    objects = parse_sst_info(text, include_kinds=parse_include_kinds(args))
    rows = audit_objects(objects, resolver)

    if args.generic_only:
        rows = [row for row in rows if row.generic_fallback == "yes"]

    if args.missing_only:
        rows = [row for row in rows if row.icon_exists == "no"]

    write_csv(rows, args.output)

    summary = build_summary(rows)
    args.summary_output.write_text(summary, encoding="utf-8")

    print(summary)
    print(f"Wrote CSV:     {args.output}")
    print(f"Wrote summary: {args.summary_output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
