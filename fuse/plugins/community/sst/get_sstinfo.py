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

"""SST metadata import and parsing utilities.

This module runs sst-info locally or through a configured toolchain provider,
parses the textual output into structured records, and synchronizes those
records into FUSE's SST metadata tables."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys

from fuse.core.toolchains.version_match import compare_version_prefix
from fuse.core.model.project_settings import ToolchainSettings
from fuse.core.toolchains.providers import (
    CommandExecutionResult,
    LocalCommandProvider,
    provider_from_toolchain,
)

from fuse.core.persistence.database import get_connection
from fuse.plugins.community.sst.initialize_db import (
    get_or_create_sst_framework_version,
    initialize_database,
    save_sst_info_run,
)
from fuse.plugins.community.sst.sst_icon_resolver import guess_component_icon_path


SST_COMPONENT_PARENT_TYPE = "sst_components"
SST_STATISTIC_PARENT_TYPE = "sst_statistics"


@dataclass
class CommandResult:
    """Backward-compatible command result record used by SST import helpers."""
    command: list[str]
    return_code: int
    stdout: str
    stderr: str


@dataclass
class ParsedElement:
    """Structured SST element record parsed from sst-info output."""
    name: str
    description: str = ""


@dataclass
class ParsedParameter:
    """Structured parameter record parsed from a component, slot, or statistic block."""
    name: str
    description: str = ""
    default_val: str = ""
    required: int = 0


@dataclass
class ParsedPort:
    """Structured component port record parsed from sst-info output."""
    name: str
    description: str = ""
    iface: str = ""
    is_variable: int = 0
    base_name: str = ""
    count_parameter: str = ""
    default_count: int = 1


@dataclass(frozen=True)
class VariablePortInfo:
    """Parsed representation of an SST variable-port naming pattern."""
    is_variable: bool
    base_name: str
    count_parameter: str
    default_count: int = 1


_PRINTF_COUNT_PORT_RE = re.compile(
    r"^(?P<base>.+?)%\((?P<count>[A-Za-z_][A-Za-z0-9_]*)\)d$"
)
_SIMPLE_PRINTF_PORT_RE = re.compile(r"^(?P<base>.+?)%d$")


def parse_variable_port_name(name: str) -> VariablePortInfo:
    """Detect SST variable-port syntax and normalize base/count metadata."""
    printf_count_match = _PRINTF_COUNT_PORT_RE.match(name)

    if printf_count_match:
        return VariablePortInfo(
            is_variable=True,
            base_name=printf_count_match.group("base"),
            count_parameter=printf_count_match.group("count"),
            default_count=1,
        )

    simple_match = _SIMPLE_PRINTF_PORT_RE.match(name)

    if simple_match:
        base_name = simple_match.group("base")
        return VariablePortInfo(
            is_variable=True,
            base_name=base_name,
            count_parameter=f"{base_name}_ports",
            default_count=1,
        )

    return VariablePortInfo(
        is_variable=False,
        base_name=name,
        count_parameter="",
        default_count=1,
    )


@dataclass
class ParsedSubcompSlot:
    """Structured SST subcomponent-slot record parsed from sst-info output."""
    name: str
    description: str = ""
    iface: str = ""


@dataclass
class ParsedStatistic:
    """Structured SST statistic record parsed from sst-info output."""
    name: str
    description: str = ""
    units: str = ""
    iface: str = ""
    parameters: list[ParsedParameter] = field(default_factory=list)


@dataclass
class ParsedComponent:
    """Structured SST component or subcomponent record before database synchronization."""
    element_name: str
    name: str
    description: str = ""
    is_subcomp: int = 0
    iface: str = ""
    category: str = ""
    functionality: str = ""
    checkpointable: int = 0
    parameters: list[ParsedParameter] = field(default_factory=list)
    ports: list[ParsedPort] = field(default_factory=list)
    subcomp_slots: list[ParsedSubcompSlot] = field(default_factory=list)
    statistics: list[ParsedStatistic] = field(default_factory=list)


ELEMENT_RE = re.compile(r"^ELEMENT LIBRARY\s+\d+\s+=\s+(.+?)\s+\(")
COMPONENT_RE = re.compile(r"^(Component|SubComponent)\s+\d+:\s+(.+)$")


def default_sst_version_label() -> str:
    """Build the default display label for an imported SST framework version."""
    return os.environ.get("FUSE_SST_VERSION", "15.0.0")


def resolve_framework_version_id(
    conn,
    version: str | None = None,
    label: str | None = None,
    source_kind: str = "sst-info",
    source_path: str = "",
    command: str = "",
    is_default: bool = False,
) -> int:
    """Resolve or create the SST framework-version row for an import operation."""
    resolved_version = version or default_sst_version_label()

    return get_or_create_sst_framework_version(
        conn=conn,
        version=resolved_version,
        label=label or f"SST {resolved_version}",
        source_kind=source_kind,
        source_path=source_path,
        command=command,
        is_default=is_default,
    )


def get_sstinfo(
    args=None,
    timeout_seconds=60,
    provider=None,
    sst_info_path: str = "sst-info",
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run sst-info from a local executable path and capture its output."""
    if args is None:
        args = []

    command = [sst_info_path or "sst-info", *args]

    if provider is None:
        provider = LocalCommandProvider()

    completed = provider.run(
        command,
        timeout_seconds=timeout_seconds,
        env=env,
    )

    return CommandResult(
        command=completed.command,
        return_code=completed.return_code,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def get_sstinfo_for_toolchain(
    toolchain: ToolchainSettings,
    args=None,
    timeout_seconds=60,
) -> CommandResult:
    """Run sst-info using the command provider configured for a toolchain."""
    provider = provider_from_toolchain(toolchain)
    sst_info_path = toolchain.tool_paths.get("sstInfo") or toolchain.tool_paths.get("sst_info") or "sst-info"

    return get_sstinfo(
        args=args,
        timeout_seconds=timeout_seconds,
        provider=provider,
        sst_info_path=sst_info_path,
        env=toolchain.environment,
    )


def validate_sst_toolchain(
    toolchain: ToolchainSettings,
    expected_version: str = "",
    timeout_seconds=60,
    version_policy: str = "major_minor_patch",
) -> tuple[bool, str, CommandResult | None]:
    """Validate that configured SST toolchain settings can run and match a target version.

    ``version_policy`` controls how strictly ``expected_version`` is compared
    with the version reported by ``sst-info --version``. The default preserves
    the interactive/project-settings behavior of accepting any matching major
    SST version, while CI can pass ``major_minor_patch`` for pinned release
    validation.
    """
    result = get_sstinfo_for_toolchain(
        toolchain=toolchain,
        args=["--version"],
        timeout_seconds=timeout_seconds,
    )

    output = (result.stdout + "\n" + result.stderr).strip()

    if result.return_code != 0:
        return (
            False,
            (
                f"sst-info failed with return code {result.return_code}.\n\n"
                f"Command: {' '.join(result.command)}\n\n"
                f"Output:\n{output}"
            ),
            result,
        )

    if expected_version:
        match = compare_version_prefix(
            expected_version=expected_version,
            detected_text=output,
            policy=version_policy,
        )

        if not match.matched:
            return (
                False,
                (
                    f"{match.message}\n\n"
                    f"Configured project target: SST {expected_version}\n\n"
                    f"Toolchain output:\n{output}"
                ),
                result,
            )

        return (
            True,
            (
                f"{match.message}\n\n"
                f"Toolchain output:\n{output}"
            ),
            result,
        )

    return True, output or "sst-info completed successfully.", result


def run_and_store_raw_sstinfo(
    args=None,
    version: str | None = None,
    label: str | None = None,
    is_default: bool = True,
    toolchain: ToolchainSettings | None = None,
) -> int:
    """Run sst-info and persist the raw command result for diagnostics."""
    initialize_database()

    if toolchain is not None:
        result = get_sstinfo_for_toolchain(toolchain, args=args)
    else:
        result = get_sstinfo(args=args)

    command_text = " ".join(result.command)

    with get_connection() as conn:
        framework_version_id = resolve_framework_version_id(
            conn=conn,
            version=version,
            label=label,
            source_kind="sst-info",
            source_path="",
            command=command_text,
            is_default=is_default,
        )

    run_id = save_sst_info_run(
        command=result.command,
        return_code=result.return_code,
        stdout=result.stdout,
        stderr=result.stderr,
        framework_version_id=framework_version_id,
    )

    if result.return_code != 0:
        raise RuntimeError(
            f"sst-info failed with return code {result.return_code}\n"
            f"STDERR:\n{result.stderr}"
        )

    return run_id

def split_name_and_rest(line: str) -> tuple[str, str]:
    """Split an sst-info line into the leading name and remaining description text."""
    if ":" not in line:
        return line.strip(), ""

    name, rest = line.split(":", 1)
    return name.strip(), rest.strip()


def find_outer_final_bracket(text: str) -> int | None:
    """Find the final top-level bracket pair used by default-value syntax."""
    if not text.endswith("]"):
        return None

    depth = 0

    for index in range(len(text) - 1, -1, -1):
        char = text[index]

        if char == "]":
            depth += 1
        elif char == "[":
            depth -= 1

            if depth == 0:
                return index

    return None


def parse_name_description_default(line: str) -> tuple[str, str, str]:
    """Parse a metadata line into name, description, and optional default value."""
    name, rest = split_name_and_rest(line)

    description = rest
    default_val = ""

    bracket_index = find_outer_final_bracket(rest)

    if bracket_index is not None:
        description = rest[:bracket_index].rstrip()
        default_val = rest[bracket_index + 1 : -1]

    return name, description, default_val


def parse_parameter_line(line: str) -> ParsedParameter:
    """Parse a parameter line from sst-info text."""
    name, description, default_val = parse_name_description_default(line)

    return ParsedParameter(
        name=name,
        description=description,
        default_val=default_val,
        required=1 if default_val == "<required>" else 0,
    )


def parse_statistic_line(line: str) -> ParsedStatistic:
    """Parse a statistic line from sst-info text."""
    name, rest = split_name_and_rest(line)

    units_match = re.search(r'\(units\s*=\s*"([^"]*)"\)', rest)
    units = units_match.group(1) if units_match else ""

    description = re.sub(
        r',?\s*\(units\s*=\s*"[^"]*"\)\s*Enable level\s*=\s*\d+\s*$',
        "",
        rest,
    ).strip(" ,")

    return ParsedStatistic(
        name=name,
        description=description,
        units=units,
        iface="",
    )


def append_continuation(item, text: str) -> None:
    """Append a continuation line to the active parsed metadata field."""
    if item is None:
        return

    if not hasattr(item, "description"):
        return

    text = text.strip()

    if not text:
        return

    if item.description:
        item.description += " " + text
    else:
        item.description = text


def parse_sstinfo_output(stdout: str) -> tuple[list[ParsedElement], list[ParsedComponent]]:
    """Parse complete sst-info output into structured element/component records."""
    elements_by_name: dict[str, ParsedElement] = {}
    components: list[ParsedComponent] = []

    current_element_name: str | None = None
    top_section: str | None = None
    detail_section: str | None = None

    current_component: ParsedComponent | None = None
    last_detail_item = None

    for raw_line in stdout.splitlines():
        stripped = raw_line.strip()

        if not stripped:
            continue

        element_match = ELEMENT_RE.match(stripped)

        if element_match:
            current_element_name = element_match.group(1)

            elements_by_name.setdefault(
                current_element_name,
                ParsedElement(name=current_element_name),
            )

            top_section = None
            detail_section = None
            current_component = None
            last_detail_item = None
            continue

        if current_element_name is None:
            continue

        if stripped.startswith("Components ("):
            top_section = "components"
            detail_section = None
            current_component = None
            last_detail_item = None
            continue

        if stripped.startswith("SubComponents ("):
            top_section = "subcomponents"
            detail_section = None
            current_component = None
            last_detail_item = None
            continue

        if stripped.startswith(
            (
                "Modules (",
                "PortModules (",
                "SSTElementPythonModules (",
                "StatisticOutputs (",
                "Statistic<T>s (",
                "ProfileTools (",
                "SSTPartitioners (",
            )
        ):
            top_section = "ignored"
            detail_section = None
            current_component = None
            last_detail_item = None
            continue

        component_match = COMPONENT_RE.match(stripped)

        if component_match and top_section in {"components", "subcomponents"}:
            object_kind = component_match.group(1)
            object_name = component_match.group(2)

            is_subcomp = 1 if object_kind == "SubComponent" else 0

            current_component = ParsedComponent(
                element_name=current_element_name,
                name=object_name,
                is_subcomp=is_subcomp,
                category="SUBCOMPONENT" if is_subcomp else "",
            )

            components.append(current_component)

            detail_section = None
            last_detail_item = None
            continue

        if current_component is None:
            continue

        if stripped.startswith("Description:"):
            description = stripped.split(":", 1)[1].strip()
            current_component.description = description
            current_component.functionality = description
            last_detail_item = None
            continue

        if stripped.startswith("Interface:"):
            current_component.iface = stripped.split(":", 1)[1].strip()
            last_detail_item = None
            continue

        if stripped.startswith("Category:"):
            current_component.category = stripped.split(":", 1)[1].strip()
            last_detail_item = None
            continue

        if stripped.startswith("Checkpointable:"):
            value = stripped.split(":", 1)[1].strip().lower()
            current_component.checkpointable = 1 if value == "true" else 0
            detail_section = None
            last_detail_item = None
            continue

        if stripped.startswith("Parameters ("):
            detail_section = "parameters"
            last_detail_item = None
            continue

        if stripped.startswith("Ports ("):
            detail_section = "ports"
            last_detail_item = None
            continue

        if stripped.startswith("SubComponent Slots ("):
            detail_section = "subcomp_slots"
            last_detail_item = None
            continue

        if stripped.startswith("Statistics ("):
            detail_section = "statistics"
            last_detail_item = None
            continue

        if stripped.startswith(
            (
                "ELI version:",
                "Compiled using file:",
                "Profile Points (",
                "Attributes (",
            )
        ):
            last_detail_item = None
            continue

        if detail_section == "parameters":
            if ":" in stripped:
                parameter = parse_parameter_line(stripped)
                current_component.parameters.append(parameter)
                last_detail_item = parameter
            else:
                append_continuation(last_detail_item, stripped)

        elif detail_section == "ports":
            if ":" in stripped:
                name, description = split_name_and_rest(stripped)

                variable_info = parse_variable_port_name(name)

                port = ParsedPort(
                    name=name,
                    description=description,
                    iface="",
                    is_variable=1 if variable_info.is_variable else 0,
                    base_name=variable_info.base_name,
                    count_parameter=variable_info.count_parameter,
                    default_count=variable_info.default_count,
                )

                current_component.ports.append(port)
                last_detail_item = port
            else:
                append_continuation(last_detail_item, stripped)

        elif detail_section == "subcomp_slots":
            if ":" in stripped:
                name, description, iface = parse_name_description_default(stripped)

                slot = ParsedSubcompSlot(
                    name=name,
                    description=description,
                    iface=iface,
                )

                current_component.subcomp_slots.append(slot)
                last_detail_item = slot
            else:
                append_continuation(last_detail_item, stripped)

        elif detail_section == "statistics":
            if ":" in stripped:
                statistic = parse_statistic_line(stripped)
                current_component.statistics.append(statistic)
                last_detail_item = statistic
            else:
                append_continuation(last_detail_item, stripped)

    return list(elements_by_name.values()), components


def get_or_create_element(conn, framework_version_id: int, name: str, description: str = "") -> int:
    """Return an SST element id, creating the row when absent."""
    row = conn.execute(
        """
        SELECT id
        FROM sst_elements
        WHERE framework_version_id = ?
          AND name = ?
        """,
        (framework_version_id, name),
    ).fetchone()

    if row is not None:
        if description:
            conn.execute(
                """
                UPDATE sst_elements
                SET description = ?
                WHERE id = ?
                  AND framework_version_id = ?
                """,
                (description, row["id"], framework_version_id),
            )

        return int(row["id"])

    cursor = conn.execute(
        """
        INSERT INTO sst_elements (framework_version_id, name, description)
        VALUES (?, ?, ?)
        """,
        (framework_version_id, name, description),
    )

    return int(cursor.lastrowid)


def get_component_id(conn, framework_version_id: int, parent_id: int, name: str, is_subcomp: int) -> int | None:
    """Return the SST component id for a parsed component identity."""
    row = conn.execute(
        """
        SELECT id
        FROM sst_components
        WHERE framework_version_id = ?
          AND parent_id = ?
          AND name = ?
          AND is_subcomp = ?
        """,
        (framework_version_id, parent_id, name, is_subcomp),
    ).fetchone()

    return int(row["id"]) if row is not None else None


def insert_or_update_component(
    conn,
    framework_version_id: int,
    parent_id: int,
    name: str,
    description: str,
    is_subcomp: int,
    iface: str,
    category: str,
    functionality: str,
    checkpointable: int,
) -> int:
    """Insert or update one parsed SST component row."""
    existing_id = get_component_id(conn, framework_version_id, parent_id, name, is_subcomp)

    if existing_id is not None:
        conn.execute(
            """
            UPDATE sst_components
            SET description = ?, iface = ?, category = ?, functionality = ?, checkpointable = ?
            WHERE id = ? AND framework_version_id = ?
            """,
            (description, iface, category, functionality, checkpointable, existing_id, framework_version_id),
        )
        return existing_id

    cursor = conn.execute(
        """
        INSERT INTO sst_components (
            framework_version_id, name, description, is_subcomp, iface,
            parent_id, category, functionality, checkpointable
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            framework_version_id,
            name,
            description,
            is_subcomp,
            iface,
            parent_id,
            category,
            functionality,
            checkpointable,
        ),
    )

    return int(cursor.lastrowid)


def backfill_component_icons(conn, framework_version_id: int | None = None) -> None:
    """Populate missing icon paths for imported SST components."""
    params: list[int] = []
    where = "WHERE c.icon_path IS NULL OR c.icon_path = ''"

    if framework_version_id is not None:
        where += " AND c.framework_version_id = ?"
        params.append(framework_version_id)

    rows = conn.execute(
        f"""
        SELECT c.id, c.name, COALESCE(c.description, '') AS description,
               COALESCE(c.category, '') AS category, COALESCE(c.iface, '') AS iface,
               COALESCE(e.name, '') AS element, c.is_subcomp
        FROM sst_components c
        JOIN sst_elements e ON c.parent_id = e.id
        {where}
        """,
        params,
    ).fetchall()

    for row in rows:
        object_kind = "SubComponent" if int(row["is_subcomp"]) else "Component"
        icon_path = guess_component_icon_path(
            name=row["name"],
            description=row["description"],
            category=row["category"],
            iface=row["iface"],
            element=row["element"],
            object_kind=object_kind,
        )

        if icon_path:
            conn.execute(
                "UPDATE sst_components SET icon_path = ? WHERE id = ?",
                (icon_path, int(row["id"])),
            )


def get_statistic_id(conn, framework_version_id: int, parent_id: int, name: str) -> int | None:
    """Return the database id for an SST statistic row."""
    row = conn.execute(
        """
        SELECT id
        FROM sst_statistics
        WHERE framework_version_id = ? AND parent_id = ? AND name = ?
        """,
        (framework_version_id, parent_id, name),
    ).fetchone()

    return int(row["id"]) if row is not None else None


def insert_or_update_statistic(
    conn,
    framework_version_id: int,
    parent_id: int,
    name: str,
    description: str,
    units: str,
    iface: str,
) -> int:
    """Insert or update one parsed SST statistic row."""
    existing_id = get_statistic_id(conn, framework_version_id, parent_id, name)

    if existing_id is not None:
        conn.execute(
            """
            UPDATE sst_statistics
            SET description = ?, units = ?, iface = ?
            WHERE id = ? AND framework_version_id = ?
            """,
            (description, units, iface, existing_id, framework_version_id),
        )
        return existing_id

    cursor = conn.execute(
        """
        INSERT INTO sst_statistics (framework_version_id, name, description, units, iface, parent_id)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (framework_version_id, name, description, units, iface, parent_id),
    )

    return int(cursor.lastrowid)


def delete_parameters_for(conn, framework_version_id: int, parent_type: str, parent_id: int) -> None:
    """Remove parameter rows associated with a component or statistic parent."""
    conn.execute(
        """
        DELETE FROM sst_parameters
        WHERE framework_version_id = ? AND parent_type = ? AND parent_id = ?
        """,
        (framework_version_id, parent_type, parent_id),
    )


def insert_parameter(conn, framework_version_id: int, parent_type: str, parent_id: int, parameter: ParsedParameter) -> int:
    """Insert one parsed parameter row for a component, statistic, or slot."""
    if parent_type not in {SST_COMPONENT_PARENT_TYPE, SST_STATISTIC_PARENT_TYPE}:
        raise ValueError(f"Unsupported parameter parent_type: {parent_type}")

    cursor = conn.execute(
        """
        INSERT INTO sst_parameters (
            framework_version_id, name, description, default_val, parent_id, parent_type, required
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            framework_version_id,
            parameter.name,
            parameter.description,
            parameter.default_val,
            parent_id,
            parent_type,
            parameter.required,
        ),
    )

    return int(cursor.lastrowid)


def replace_component_children(conn, framework_version_id: int, component_id: int, component: ParsedComponent) -> None:
    """Replace ports, slots, statistics, and child metadata for one SST component."""
    delete_parameters_for(conn, framework_version_id, SST_COMPONENT_PARENT_TYPE, component_id)

    conn.execute(
        "DELETE FROM sst_ports WHERE framework_version_id = ? AND parent_id = ?",
        (framework_version_id, component_id),
    )
    conn.execute(
        "DELETE FROM sst_subcomp_slots WHERE framework_version_id = ? AND parent_id = ?",
        (framework_version_id, component_id),
    )

    old_statistics = conn.execute(
        "SELECT id FROM sst_statistics WHERE framework_version_id = ? AND parent_id = ?",
        (framework_version_id, component_id),
    ).fetchall()

    for old_statistic in old_statistics:
        delete_parameters_for(conn, framework_version_id, SST_STATISTIC_PARENT_TYPE, int(old_statistic["id"]))

    conn.execute(
        "DELETE FROM sst_statistics WHERE framework_version_id = ? AND parent_id = ?",
        (framework_version_id, component_id),
    )

    for parameter in component.parameters:
        insert_parameter(conn, framework_version_id, SST_COMPONENT_PARENT_TYPE, component_id, parameter)

    for port in component.ports:
        conn.execute(
            """
            INSERT INTO sst_ports (
                framework_version_id,
                name,
                description,
                iface,
                parent_id,
                is_variable,
                base_name,
                count_parameter,
                default_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                framework_version_id,
                port.name,
                port.description,
                port.iface,
                component_id,
                int(port.is_variable),
                port.base_name or port.name,
                port.count_parameter or "",
                int(port.default_count or 1),
            ),
        )

    for slot in component.subcomp_slots:
        conn.execute(
            """
            INSERT INTO sst_subcomp_slots (framework_version_id, name, description, iface, parent_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (framework_version_id, slot.name, slot.description, slot.iface, component_id),
        )

    for statistic in component.statistics:
        statistic_id = insert_or_update_statistic(
            conn,
            framework_version_id,
            component_id,
            statistic.name,
            statistic.description,
            statistic.units,
            statistic.iface,
        )

        for parameter in statistic.parameters:
            insert_parameter(conn, framework_version_id, SST_STATISTIC_PARENT_TYPE, statistic_id, parameter)


def sync_parsed_sstinfo_to_database(
    framework_version_id: int | list[ParsedElement],
    elements: list[ParsedElement] | list[ParsedComponent] | None = None,
    components: list[ParsedComponent] | None = None,
) -> None:
    """Sync parsed SST metadata into the versioned catalog.

    Preferred call form:
        sync_parsed_sstinfo_to_database(framework_version_id, elements, components)

    Backward-compatible call form for existing tests/scripts:
        sync_parsed_sstinfo_to_database(elements, components)
    """
    initialize_database()

    if components is None:
        parsed_elements = framework_version_id
        parsed_components = elements

        with get_connection() as conn:
            resolved_framework_version_id = resolve_framework_version_id(
                conn=conn,
                version=None,
                label=None,
                source_kind="test-or-legacy",
                source_path="",
                command="legacy parsed import",
                is_default=True,
            )

        framework_version_id = resolved_framework_version_id
        elements = parsed_elements
        components = parsed_components

    if elements is None or components is None:
        raise TypeError("sync_parsed_sstinfo_to_database requires elements and components.")

    framework_version_id = int(framework_version_id)

    with get_connection() as conn:
        element_ids_by_name: dict[str, int] = {}

        for element in elements:
            element_id = get_or_create_element(conn, framework_version_id, element.name, element.description)
            element_ids_by_name[element.name] = element_id

        for component in components:
            element_id = element_ids_by_name.get(component.element_name)

            if element_id is None:
                element_id = get_or_create_element(conn, framework_version_id, component.element_name, "")
                element_ids_by_name[component.element_name] = element_id

            component_id = insert_or_update_component(
                conn=conn,
                framework_version_id=framework_version_id,
                parent_id=element_id,
                name=component.name,
                description=component.description,
                is_subcomp=component.is_subcomp,
                iface=component.iface,
                category=component.category or "UNCATEGORIZED COMPONENT",
                functionality=component.functionality or component.description,
                checkpointable=component.checkpointable,
            )

            replace_component_children(conn, framework_version_id, component_id, component)

        backfill_component_icons(conn, framework_version_id=framework_version_id)


def sync_sstinfo_to_database(
    args=None,
    version: str | None = None,
    label: str | None = None,
    is_default: bool = True,
    toolchain: ToolchainSettings | None = None,
) -> int:
    """Run sst-info and synchronize the parsed metadata into the database."""
    initialize_database()

    if toolchain is not None:
        result = get_sstinfo_for_toolchain(toolchain, args=args)
    else:
        result = get_sstinfo(args=args)

    command_text = " ".join(result.command)

    with get_connection() as conn:
        framework_version_id = resolve_framework_version_id(
            conn=conn,
            version=version,
            label=label,
            source_kind="sst-info",
            source_path="",
            command=command_text,
            is_default=is_default,
        )

    run_id = save_sst_info_run(
        command=result.command,
        return_code=result.return_code,
        stdout=result.stdout,
        stderr=result.stderr,
        framework_version_id=framework_version_id,
    )

    if result.return_code != 0:
        raise RuntimeError(
            f"sst-info failed with return code {result.return_code}\n"
            f"STDERR:\n{result.stderr}"
        )

    elements, components = parse_sstinfo_output(result.stdout)
    sync_parsed_sstinfo_to_database(framework_version_id, elements, components)

    return run_id

def parsed_sstinfo_to_catalog_dict(
    *,
    version: str,
    elements: list[ParsedElement],
    components: list[ParsedComponent],
    source: str = "sst-info",
) -> dict:
    """Convert parsed SST metadata into a JSON-serializable component catalog.

    This catalog is palette/database metadata, not the SST JSON export policy
    catalog. It intentionally preserves the parser output used by the old
    database import path, including parameters, ports, variable-port metadata,
    subcomponent slots, and statistics.
    """

    return {
        "schema_version": "1.0.0",
        "source": source,
        "sst_version": version,
        "elements": [asdict(element) for element in elements],
        "components": [asdict(component) for component in components],
    }


def write_sstinfo_catalog_json(
    *,
    stdout: str,
    version: str,
    out_path: str | Path,
    source: str = "sst-info",
) -> None:
    """Parse raw sst-info output and write a bundled component catalog JSON."""

    elements, components = parse_sstinfo_output(stdout)
    catalog = parsed_sstinfo_to_catalog_dict(
        version=version,
        elements=elements,
        components=components,
        source=source,
    )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parameter_from_dict(data: dict) -> ParsedParameter:
    return ParsedParameter(
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        default_val=str(data.get("default_val", "") or ""),
        required=int(data.get("required", 0) or 0),
    )


def _port_from_dict(data: dict) -> ParsedPort:
    return ParsedPort(
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        iface=str(data.get("iface", "") or ""),
        is_variable=int(data.get("is_variable", 0) or 0),
        base_name=str(data.get("base_name", "") or ""),
        count_parameter=str(data.get("count_parameter", "") or ""),
        default_count=int(data.get("default_count", 1) or 1),
    )


def _subcomp_slot_from_dict(data: dict) -> ParsedSubcompSlot:
    return ParsedSubcompSlot(
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        iface=str(data.get("iface", "") or ""),
    )


def _statistic_from_dict(data: dict) -> ParsedStatistic:
    return ParsedStatistic(
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        units=str(data.get("units", "") or ""),
        iface=str(data.get("iface", "") or ""),
        parameters=[
            _parameter_from_dict(parameter)
            for parameter in data.get("parameters", []) or []
        ],
    )


def _component_from_dict(data: dict) -> ParsedComponent:
    return ParsedComponent(
        element_name=str(data.get("element_name", "") or ""),
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        is_subcomp=int(data.get("is_subcomp", 0) or 0),
        iface=str(data.get("iface", "") or ""),
        category=str(data.get("category", "") or ""),
        functionality=str(data.get("functionality", "") or ""),
        checkpointable=int(data.get("checkpointable", 0) or 0),
        parameters=[
            _parameter_from_dict(parameter)
            for parameter in data.get("parameters", []) or []
        ],
        ports=[
            _port_from_dict(port)
            for port in data.get("ports", []) or []
        ],
        subcomp_slots=[
            _subcomp_slot_from_dict(slot)
            for slot in data.get("subcomp_slots", []) or []
        ],
        statistics=[
            _statistic_from_dict(statistic)
            for statistic in data.get("statistics", []) or []
        ],
    )


def parsed_sstinfo_from_catalog_dict(
    catalog: dict,
) -> tuple[list[ParsedElement], list[ParsedComponent]]:
    """Load parsed SST metadata from a component catalog JSON dictionary."""

    elements = [
        ParsedElement(
            name=str(element.get("name", "") or ""),
            description=str(element.get("description", "") or ""),
        )
        for element in catalog.get("elements", []) or []
    ]

    components = [
        _component_from_dict(component)
        for component in catalog.get("components", []) or []
    ]

    return elements, components


def clear_sst_framework_metadata(framework_version_id: int) -> None:
    """Remove imported SST metadata for one framework target before re-seeding it."""

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM sst_parameters WHERE framework_version_id = ?",
            (framework_version_id,),
        )
        conn.execute(
            "DELETE FROM sst_ports WHERE framework_version_id = ?",
            (framework_version_id,),
        )
        conn.execute(
            "DELETE FROM sst_subcomp_slots WHERE framework_version_id = ?",
            (framework_version_id,),
        )
        conn.execute(
            "DELETE FROM sst_statistics WHERE framework_version_id = ?",
            (framework_version_id,),
        )
        conn.execute(
            "DELETE FROM sst_components WHERE framework_version_id = ?",
            (framework_version_id,),
        )
        conn.execute(
            "DELETE FROM sst_elements WHERE framework_version_id = ?",
            (framework_version_id,),
        )


def sync_sstinfo_catalog_json_to_database(
    path: str | Path,
    version: str | None = None,
    label: str | None = None,
    source_kind: str = "bundled-component-catalog",
    source_path: str | None = None,
    command: str | None = None,
    is_default: bool = True,
    clear_existing: bool = True,
) -> int:
    """Populate SST metadata tables from a component catalog JSON file.

    This is the install-time path for bundled catalogs and the GUI path for
    custom/toolchain-discovered catalogs. The UI continues to read the database;
    JSON is only a seed/snapshot format.
    """

    initialize_database()

    path_obj = Path(path)
    catalog = json.loads(path_obj.read_text(encoding="utf-8"))

    catalog_version = str(catalog.get("sst_version", "") or "")
    resolved_version = version or catalog_version

    if not resolved_version:
        raise ValueError(
            f"SST component catalog {path_obj} does not declare sst_version."
        )

    with get_connection() as conn:
        framework_version_id = resolve_framework_version_id(
            conn=conn,
            version=resolved_version,
            label=label or f"SST {resolved_version}",
            source_kind=source_kind,
            source_path=source_path if source_path is not None else str(path_obj),
            command=command or f"SST component catalog import: {path_obj}",
            is_default=is_default,
        )

    if clear_existing:
        clear_sst_framework_metadata(framework_version_id)

    elements, components = parsed_sstinfo_from_catalog_dict(catalog)
    sync_parsed_sstinfo_to_database(framework_version_id, elements, components)

    return framework_version_id


def sync_sstinfo_file_to_database(
    path: str,
    version: str | None = None,
    label: str | None = None,
    is_default: bool = True,
) -> None:
    """Import previously captured sst-info output from a file."""
    initialize_database()

    path_obj = Path(path)
    stdout = path_obj.read_text(encoding="utf-8")

    with get_connection() as conn:
        framework_version_id = resolve_framework_version_id(
            conn=conn,
            version=version,
            label=label,
            source_kind="file",
            source_path=str(path_obj),
            command=f"sst-info file import: {path_obj}",
            is_default=is_default,
        )

    elements, components = parse_sstinfo_output(stdout)

    print(f"Parsed {len(elements)} elements")
    print(f"Parsed {len(components)} components/subcomponents")

    sync_parsed_sstinfo_to_database(framework_version_id, elements, components)

    print("Database populated from file.")



def parsed_sstinfo_to_catalog_dict(
    *,
    version: str,
    elements: list[ParsedElement],
    components: list[ParsedComponent],
) -> dict:
    """Convert parsed sst-info metadata into a bundled component catalog.

    This preserves the exact structured data that FUSE already imports into the
    SST metadata tables: components, subcomponents, parameters, ports, variable
    port metadata, subcomponent slots, and statistics.
    """

    return {
        "schema_version": "1.0.0",
        "source": "sst-info",
        "sst_version": version,
        "elements": [asdict(element) for element in elements],
        "components": [asdict(component) for component in components],
    }


def write_sstinfo_catalog_json(
    *,
    stdout: str,
    version: str,
    out_path: str | Path,
) -> None:
    """Parse raw sst-info output and write a reusable component catalog JSON file.

    This is a maintainer/offline helper. Normal FUSE setup should not run
    sst-info; it should import the JSON generated by this function.
    """

    elements, components = parse_sstinfo_output(stdout)

    catalog = parsed_sstinfo_to_catalog_dict(
        version=version,
        elements=elements,
        components=components,
    )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _parameter_from_dict(data: dict) -> ParsedParameter:
    return ParsedParameter(
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        default_val=str(data.get("default_val", "") or ""),
        required=int(data.get("required", 0) or 0),
    )


def _port_from_dict(data: dict) -> ParsedPort:
    return ParsedPort(
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        iface=str(data.get("iface", "") or ""),
        is_variable=int(data.get("is_variable", 0) or 0),
        base_name=str(data.get("base_name", "") or ""),
        count_parameter=str(data.get("count_parameter", "") or ""),
        default_count=int(data.get("default_count", 1) or 1),
    )


def _subcomp_slot_from_dict(data: dict) -> ParsedSubcompSlot:
    return ParsedSubcompSlot(
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        iface=str(data.get("iface", "") or ""),
    )


def _statistic_from_dict(data: dict) -> ParsedStatistic:
    return ParsedStatistic(
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        units=str(data.get("units", "") or ""),
        iface=str(data.get("iface", "") or ""),
        parameters=[
            _parameter_from_dict(parameter)
            for parameter in data.get("parameters", []) or []
        ],
    )


def _component_from_dict(data: dict) -> ParsedComponent:
    return ParsedComponent(
        element_name=str(data.get("element_name", "") or ""),
        name=str(data.get("name", "") or ""),
        description=str(data.get("description", "") or ""),
        is_subcomp=int(data.get("is_subcomp", 0) or 0),
        iface=str(data.get("iface", "") or ""),
        category=str(data.get("category", "") or ""),
        functionality=str(data.get("functionality", "") or ""),
        checkpointable=int(data.get("checkpointable", 0) or 0),
        parameters=[
            _parameter_from_dict(parameter)
            for parameter in data.get("parameters", []) or []
        ],
        ports=[
            _port_from_dict(port)
            for port in data.get("ports", []) or []
        ],
        subcomp_slots=[
            _subcomp_slot_from_dict(slot)
            for slot in data.get("subcomp_slots", []) or []
        ],
        statistics=[
            _statistic_from_dict(statistic)
            for statistic in data.get("statistics", []) or []
        ],
    )


def parsed_sstinfo_from_catalog_dict(
    catalog: dict,
) -> tuple[list[ParsedElement], list[ParsedComponent]]:
    """Load parsed SST metadata from a bundled component catalog JSON object."""

    elements = [
        ParsedElement(
            name=str(element.get("name", "") or ""),
            description=str(element.get("description", "") or ""),
        )
        for element in catalog.get("elements", []) or []
    ]

    components = [
        _component_from_dict(component)
        for component in catalog.get("components", []) or []
    ]

    return elements, components


def sync_sstinfo_catalog_json_to_database(
    path: str | Path,
    version: str | None = None,
    label: str | None = None,
    is_default: bool = True,
) -> None:
    """Populate SST DB tables from a bundled sst-info-derived JSON catalog.

    This is the install/bootstrap path. It reads JSON only. It does not run or
    parse sst-info during normal setup.
    """

    initialize_database()

    path_obj = Path(path)
    catalog = json.loads(path_obj.read_text(encoding="utf-8"))

    catalog_version = str(catalog.get("sst_version", "") or "")
    resolved_version = version or catalog_version

    if not resolved_version:
        raise ValueError(
            f"SST component catalog {path_obj} does not declare sst_version."
        )

    with get_connection() as conn:
        framework_version_id = resolve_framework_version_id(
            conn=conn,
            version=resolved_version,
            label=label or f"SST {resolved_version}",
            source_kind="sst-info",
            source_path="",
            command=f"bundled SST component catalog: {path_obj}",
            is_default=is_default,
        )

    elements, components = parsed_sstinfo_from_catalog_dict(catalog)

    print(f"Importing bundled SST component catalog {path_obj}")
    print(f"Catalog contains {len(elements)} elements")
    print(f"Catalog contains {len(components)} components/subcomponents")

    sync_parsed_sstinfo_to_database(framework_version_id, elements, components)


def main():
    """Command-line entry point for importing SST metadata outside the GUI."""
    parser = argparse.ArgumentParser(description="Import SST component metadata into the FUSE database.")

    parser.add_argument(
        "--from-file",
        help="Import from a saved sst-info output file instead of running sst-info.",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="SST version/catalog label to import as, for example 15.0.0 or 16.0.0.",
    )
    parser.add_argument(
        "--label",
        default=None,
        help="Human-readable target label, for example 'SST 16.0.0'.",
    )
    parser.add_argument(
        "--no-default",
        action="store_true",
        help="Do not mark this imported SST catalog as the default target.",
    )
    parser.add_argument(
        "--write-component-catalog",
        default=None,
        help=(
            "Write a component metadata catalog JSON instead of importing into "
            "the database. With --from-file, the saved sst-info output is used; "
            "otherwise sst-info is executed locally."
        ),
    )

    parser.add_argument(
        "--write-component-catalog",
        default=None,
        help=(
            "Write a bundled component metadata catalog JSON file instead of "
            "importing into the database. With --from-file, the input is a "
            "captured sst-info text file."
        ),
    )

    args = parser.parse_args()

    if args.write_component_catalog:
        if not args.version:
            raise SystemExit("--version is required with --write-component-catalog")

        if args.from_file:
            stdout = Path(args.from_file).read_text(encoding="utf-8")
        else:
            result = get_sstinfo()
            if result.return_code != 0:
                raise SystemExit(
                    f"sst-info failed with return code {result.return_code}\n"
                    f"STDERR:\n{result.stderr}"
                )
            stdout = result.stdout

        write_sstinfo_catalog_json(
            stdout=stdout,
            version=args.version,
            out_path=args.write_component_catalog,
        )
        print(f"Wrote SST component catalog: {args.write_component_catalog}")
        return

    if args.from_file:
        sync_sstinfo_file_to_database(
            path=args.from_file,
            version=args.version,
            label=args.label,
            is_default=not args.no_default,
        )
        return

    run_id = sync_sstinfo_to_database(
        version=args.version,
        label=args.label,
        is_default=not args.no_default,
    )

    print(f"Stored and synced sst-info run with id: {run_id}")


if __name__ == "__main__":
    main()
