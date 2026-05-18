from dataclasses import dataclass, field
from pathlib import Path
from sst_icon_resolver import guess_component_icon_path
import re
import subprocess
import sys

from initialize_db import (
    initialize_database,
    save_sst_info_run,
    get_connection,
)


@dataclass
class CommandResult:
    command: list[str]
    return_code: int
    stdout: str
    stderr: str


@dataclass
class ParsedElement:
    name: str
    description: str = ""


@dataclass
class ParsedParameter:
    name: str
    description: str = ""
    default_val: str = ""
    required: int = 0


@dataclass
class ParsedPort:
    name: str
    description: str = ""
    iface: str = ""


@dataclass
class ParsedSubcompSlot:
    name: str
    description: str = ""
    iface: str = ""


@dataclass
class ParsedStatistic:
    name: str
    description: str = ""
    units: str = ""
    iface: str = ""
    parameters: list[ParsedParameter] = field(default_factory=list)


@dataclass
class ParsedComponent:
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


def get_sstinfo(args=None, timeout_seconds=60) -> CommandResult:
    if args is None:
        args = []

    command = ["sst-info", *args]

    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout_seconds,
    )

    return CommandResult(
        command=command,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_and_store_raw_sstinfo(args=None) -> int:
    initialize_database()

    result = get_sstinfo(args=args)

    run_id = save_sst_info_run(
        command=result.command,
        return_code=result.return_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )

    if result.return_code != 0:
        raise RuntimeError(
            f"sst-info failed with return code {result.return_code}\n"
            f"STDERR:\n{result.stderr}"
        )

    return run_id


def split_name_and_rest(line: str) -> tuple[str, str]:
    if ":" not in line:
        return line.strip(), ""

    name, rest = line.split(":", 1)
    return name.strip(), rest.strip()


def find_outer_final_bracket(text: str) -> int | None:
    """
    Finds the '[' that matches a final trailing ']'.

    Example:
        'foo [[1.0]]' -> returns index of the outer '['
    """
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
    name, rest = split_name_and_rest(line)

    description = rest
    default_val = ""

    bracket_index = find_outer_final_bracket(rest)

    if bracket_index is not None:
        description = rest[:bracket_index].rstrip()
        default_val = rest[bracket_index + 1 : -1]

    return name, description, default_val


def parse_parameter_line(line: str) -> ParsedParameter:
    name, description, default_val = parse_name_description_default(line)

    return ParsedParameter(
        name=name,
        description=description,
        default_val=default_val,
        required=1 if default_val == "<required>" else 0,
    )


def parse_statistic_line(line: str) -> ParsedStatistic:
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
    """
    Some sst-info descriptions may wrap onto a following line.
    This appends that continuation text to the previous parsed item.
    """
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

        # These are real sst-info sections, but they do not fit the current schema.
        # Add separate tables later if you want to track them.
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

                port = ParsedPort(
                    name=name,
                    description=description,
                    iface="",
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


def get_or_create_element(conn, name: str, description: str = "") -> int:
    row = conn.execute(
        """
        SELECT id
        FROM elements
        WHERE name = ?
        """,
        (name,),
    ).fetchone()

    if row is not None:
        if description:
            conn.execute(
                """
                UPDATE elements
                SET description = ?
                WHERE id = ?
                """,
                (description, row["id"]),
            )

        return int(row["id"])

    cursor = conn.execute(
        """
        INSERT INTO elements (name, description)
        VALUES (?, ?)
        """,
        (name, description),
    )

    return int(cursor.lastrowid)


def get_component_id(conn, parent_id: int, name: str, is_subcomp: int) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM components
        WHERE parent_id = ?
          AND name = ?
          AND is_subcomp = ?
        """,
        (parent_id, name, is_subcomp),
    ).fetchone()

    if row is None:
        return None

    return int(row["id"])


def insert_or_update_component(
    conn,
    parent_id: int,
    name: str,
    description: str,
    is_subcomp: int,
    iface: str,
    category: str,
    functionality: str,
    checkpointable: int,
) -> int:
    existing_id = get_component_id(
        conn=conn,
        parent_id=parent_id,
        name=name,
        is_subcomp=is_subcomp,
    )

    if existing_id is not None:
        conn.execute(
            """
            UPDATE components
            SET description = ?,
                iface = ?,
                category = ?,
                functionality = ?,
                checkpointable = ?
            WHERE id = ?
            """,
            (
                description,
                iface,
                category,
                functionality,
                checkpointable,
                existing_id,
            ),
        )

        return existing_id

    cursor = conn.execute(
        """
        INSERT INTO components (
            name,
            description,
            is_subcomp,
            iface,
            parent_id,
            category,
            functionality,
            checkpointable
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
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


def backfill_component_icons(conn) -> None:
    """
    Fill components.icon_path for components/subcomponents that do not already
    have an icon.

    This intentionally only updates rows where icon_path is NULL or empty, so
    manual user choices are not overwritten during future sst-info refreshes.
    """
    rows = conn.execute(
        """
        SELECT
            c.id,
            c.name,
            COALESCE(c.description, '') AS description,
            COALESCE(c.category, '') AS category,
            COALESCE(c.iface, '') AS iface,
            COALESCE(e.name, '') AS element,
            c.is_subcomp
        FROM components c
        JOIN elements e ON c.parent_id = e.id
        WHERE c.icon_path IS NULL OR c.icon_path = ''
        """
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
                """
                UPDATE components
                SET icon_path = ?
                WHERE id = ?
                """,
                (icon_path, int(row["id"])),
            )


def get_statistic_id(conn, parent_id: int, name: str) -> int | None:
    row = conn.execute(
        """
        SELECT id
        FROM statistics
        WHERE parent_id = ?
          AND name = ?
        """,
        (parent_id, name),
    ).fetchone()

    if row is None:
        return None

    return int(row["id"])


def insert_or_update_statistic(
    conn,
    parent_id: int,
    name: str,
    description: str,
    units: str,
    iface: str,
) -> int:
    existing_id = get_statistic_id(
        conn=conn,
        parent_id=parent_id,
        name=name,
    )

    if existing_id is not None:
        conn.execute(
            """
            UPDATE statistics
            SET description = ?,
                units = ?,
                iface = ?
            WHERE id = ?
            """,
            (
                description,
                units,
                iface,
                existing_id,
            ),
        )

        return existing_id

    cursor = conn.execute(
        """
        INSERT INTO statistics (
            name,
            description,
            units,
            iface,
            parent_id
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            name,
            description,
            units,
            iface,
            parent_id,
        ),
    )

    return int(cursor.lastrowid)


def delete_parameters_for(conn, parent_type: str, parent_id: int) -> None:
    conn.execute(
        """
        DELETE FROM parameters
        WHERE parent_type = ?
          AND parent_id = ?
        """,
        (parent_type, parent_id),
    )


def insert_parameter(
    conn,
    parent_type: str,
    parent_id: int,
    parameter: ParsedParameter,
) -> int:
    if parent_type not in {"components", "statistics"}:
        raise ValueError(f"Unsupported parameter parent_type: {parent_type}")

    cursor = conn.execute(
        """
        INSERT INTO parameters (
            name,
            description,
            default_val,
            parent_id,
            parent_type,
            required
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            parameter.name,
            parameter.description,
            parameter.default_val,
            parent_id,
            parent_type,
            parameter.required,
        ),
    )

    return int(cursor.lastrowid)


def replace_component_children(
    conn,
    component_id: int,
    component: ParsedComponent,
) -> None:
    delete_parameters_for(
        conn=conn,
        parent_type="components",
        parent_id=component_id,
    )

    conn.execute("DELETE FROM ports WHERE parent_id = ?", (component_id,))
    conn.execute("DELETE FROM subcomp_slots WHERE parent_id = ?", (component_id,))

    old_statistics = conn.execute(
        """
        SELECT id
        FROM statistics
        WHERE parent_id = ?
        """,
        (component_id,),
    ).fetchall()

    for old_statistic in old_statistics:
        delete_parameters_for(
            conn=conn,
            parent_type="statistics",
            parent_id=int(old_statistic["id"]),
        )

    conn.execute("DELETE FROM statistics WHERE parent_id = ?", (component_id,))

    for parameter in component.parameters:
        insert_parameter(
            conn=conn,
            parent_type="components",
            parent_id=component_id,
            parameter=parameter,
        )

    for port in component.ports:
        conn.execute(
            """
            INSERT INTO ports (
                name,
                description,
                iface,
                parent_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                port.name,
                port.description,
                port.iface,
                component_id,
            ),
        )

    for slot in component.subcomp_slots:
        conn.execute(
            """
            INSERT INTO subcomp_slots (
                name,
                description,
                iface,
                parent_id
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                slot.name,
                slot.description,
                slot.iface,
                component_id,
            ),
        )

    for statistic in component.statistics:
        statistic_id = insert_or_update_statistic(
            conn=conn,
            parent_id=component_id,
            name=statistic.name,
            description=statistic.description,
            units=statistic.units,
            iface=statistic.iface,
        )

        for parameter in statistic.parameters:
            insert_parameter(
                conn=conn,
                parent_type="statistics",
                parent_id=statistic_id,
                parameter=parameter,
            )


def sync_parsed_sstinfo_to_database(
    elements: list[ParsedElement],
    components: list[ParsedComponent],
) -> None:
    with get_connection() as conn:
        element_ids_by_name: dict[str, int] = {}

        for element in elements:
            element_id = get_or_create_element(
                conn=conn,
                name=element.name,
                description=element.description,
            )

            element_ids_by_name[element.name] = element_id

        for component in components:
            element_id = element_ids_by_name.get(component.element_name)

            if element_id is None:
                element_id = get_or_create_element(
                    conn=conn,
                    name=component.element_name,
                    description="",
                )

                element_ids_by_name[component.element_name] = element_id

            component_id = insert_or_update_component(
                conn=conn,
                parent_id=element_id,
                name=component.name,
                description=component.description,
                is_subcomp=component.is_subcomp,
                iface=component.iface,
                category=component.category or "UNCATEGORIZED COMPONENT",
                functionality=component.functionality or component.description,
                checkpointable=component.checkpointable,
            )

            replace_component_children(
                conn=conn,
                component_id=component_id,
                component=component,
            )

            backfill_component_icons(conn)


def sync_sstinfo_to_database(args=None) -> int:
    initialize_database()

    result = get_sstinfo(args=args)

    run_id = save_sst_info_run(
        command=result.command,
        return_code=result.return_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )

    if result.return_code != 0:
        raise RuntimeError(
            f"sst-info failed with return code {result.return_code}\n"
            f"STDERR:\n{result.stderr}"
        )

    elements, components = parse_sstinfo_output(result.stdout)

    sync_parsed_sstinfo_to_database(
        elements=elements,
        components=components,
    )

    return run_id


def sync_sstinfo_file_to_database(path: str) -> None:
    initialize_database()

    stdout = Path(path).read_text()

    elements, components = parse_sstinfo_output(stdout)

    print(f"Parsed {len(elements)} elements")
    print(f"Parsed {len(components)} components/subcomponents")

    sync_parsed_sstinfo_to_database(
        elements=elements,
        components=components,
    )

    print("Database populated from file.")


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--from-file":
        sync_sstinfo_file_to_database(sys.argv[2])
        return

    run_id = sync_sstinfo_to_database()

    print(f"Stored and synced sst-info run with id: {run_id}")


if __name__ == "__main__":
    main()