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
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from fuse.core.model.subcomponents import is_visual_subcomponent_connection_parameter
from fuse.plugins.community.sst.policy.models import ParamKind
from fuse.plugins.community.sst.policy.runtime import (
    default_params_for_node,
    looks_like_untyped_number,
    normalize_param_value,
    normalize_params,
    parameter_metadata_for_node,
    resolve_param_kind,
    should_require_metadata_param_for_export,
)


DEFAULT_LINK_LATENCY = "1ns"
SST_EXPORT_FORMAT = "sst.json"
SST_EXPORT_SCHEMA_VERSION = "0.5.0"
UINT64_MAX_VALUE = str((1 << 64) - 1)
_SYMBOLIC_UINT64_MAX_VALUES = {
    "uint64_t-1",
    "UINT64_MAX",
    "std::numeric_limits<uint64_t>::max()",
}


class SSTJsonExportError(RuntimeError):
    """Raised when a model cannot be converted to valid SST JSON."""


@dataclass
class SSTExportReport:
    """Structured readiness report for SST JSON export."""

    errors: list[Any] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)

    @property
    def can_export(self) -> bool:
        return not self.errors

    @property
    def issues(self) -> list[Any]:
        return [*self.errors, *self.warnings]

    def raise_for_errors(self) -> None:
        if not self.errors:
            return

        lines = ["FUSE model is not ready for SST JSON export:", ""]
        for issue in self.errors[:25]:
            object_name = getattr(issue, "object_name", "Project") or "Project"
            message = getattr(issue, "message", str(issue))
            lines.append(f"- {object_name}: {message}")

        if len(self.errors) > 25:
            lines.append(f"...and {len(self.errors) - 25} more error(s).")

        raise SSTJsonExportError("\n".join(lines))


def validation_issue(
    issue_type: str,
    object_name: str,
    message: str,
    *,
    severity: str = "error",
    node_id: int | None = None,
    link_id: int | None = None,
    attachment_id: int | None = None,
    parameter_name: str | None = None,
):
    from fuse.core.model.validation import ValidationIssue

    return ValidationIssue(
        issue_type=issue_type,
        object_name=object_name,
        message=message,
        node_id=node_id,
        link_id=link_id,
        attachment_id=attachment_id,
        parameter_name=parameter_name,
        severity=severity,
    )


def clean_value(value: Any) -> Any:
    """
    Keep SST parameter values simple and JSON-safe before final export.

    SST component/subcomponent params are ultimately emitted as strings because
    SST's JSON model parser treats the ``params`` object as string key/value
    pairs. Typed FUSE values are preserved during policy validation and are
    stringified only at the final params boundary.
    """
    if value is None:
        return ""

    return value


def non_empty_params(parameters: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in sorted(parameters.items(), key=lambda item: str(item[0])):
        if key is None:
            continue

        key_text = str(key).strip()

        if not key_text:
            continue

        cleaned = clean_value(value)

        if cleaned is None:
            continue

        if isinstance(cleaned, str) and cleaned.strip() == "":
            continue

        result[key_text] = cleaned

    return result


def sst_param_string_value(value: Any) -> str:
    """
    Convert one component/subcomponent parameter value to SST JSON's string form.

    SST's JSON model parser accepts structured JSON for the graph itself, but
    component ``params`` are parsed as string key/value entries. Emitting JSON
    booleans or numbers in ``params`` can fail before SST reaches simulation
    initialization, for example at ``"broadcast": false`` on memHierarchy.Bus.
    """

    if value is None:
        return ""

    if isinstance(value, bool):
        return "true" if value else "false"

    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, separators=(",", ":"))

    return str(value)


def stringify_sst_params(parameters: dict[str, Any]) -> dict[str, str]:
    """Return SST component/subcomponent params in parser-compatible form."""

    return {
        str(key): sst_param_string_value(value)
        for key, value in parameters.items()
    }


def _normalize_sst_runtime_symbolic_values(parameters: dict[str, Any]) -> dict[str, Any]:
    """
    Convert SST metadata expressions that are not accepted by Params::find().

    Some SST ELI/catalog defaults are C/C++-style expressions rather than
    runtime parser literals. For example, DirectoryController metadata can
    advertise ``uint64_t-1`` for ``addr_range_end`` to mean the maximum address,
    but SST's runtime parameter parser expects an integer string.
    """

    result: dict[str, Any] = {}

    for key, value in parameters.items():
        if isinstance(value, str):
            compact = "".join(value.strip().split())
            if compact in _SYMBOLIC_UINT64_MAX_VALUES:
                result[key] = UINT64_MAX_VALUE
                continue

        result[key] = value

    return result


def _looks_like_zero(value: Any) -> bool:
    """Return true for common zero spellings used by SST/FUSE params."""

    if value is None:
        return True

    text = str(value).strip().lower()

    if text in {"", "0", "+0", "0x0", "0.0", "0b", "0 b"}:
        return True

    try:
        return float(text) == 0.0
    except ValueError:
        return False


def _looks_like_sst_no_file_default(value: Any) -> bool:
    """Return true for empty SST file-parameter sentinels that should not export."""

    if value is None:
        return True

    text = str(value).strip()

    return text == "" or text.upper() == "N/A"


def _drop_sst_runtime_incompatible_default_params(
    component_type: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    """
    Drop optional defaults that are valid catalog entries but invalid runtime params.

    ``memHierarchy.standardCPU`` treats ``mmio_addr`` as optional. When it is
    absent and ``mmio_freq`` is zero/absent, no MMIO device is configured. When
    the exporter writes the UI/catalog default ``mmio_addr=0``, SST 16 treats it
    as an explicit MMIO address and rejects it because it is inside physical
    memory. Therefore FUSE should omit the zero default unless MMIO traffic is
    explicitly requested.
    """

    result = dict(parameters)

    if component_type == "memHierarchy.standardCPU" and "mmio_addr" in result:
        mmio_freq = result.get("mmio_freq", 0)
        if _looks_like_zero(result.get("mmio_addr")) and _looks_like_zero(mmio_freq):
            result.pop("mmio_addr", None)

    if (
        component_type == "memHierarchy.MemController"
        and "memory_file" in result
        and _looks_like_sst_no_file_default(result.get("memory_file"))
    ):
        result.pop("memory_file", None)

    return result


def _parse_sst_integer_literal(value: Any) -> int | None:
    """Parse simple integer strings used by SST address-range parameters."""

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    compact = "".join(text.split())
    if compact in _SYMBOLIC_UINT64_MAX_VALUES:
        return int(UINT64_MAX_VALUE)

    try:
        return int(text, 0)
    except ValueError:
        return None


def _is_unbounded_or_default_address_end(value: Any) -> bool:
    """Return true for address-end values that represent an unsafe broad default."""

    parsed = _parse_sst_integer_literal(value)
    if parsed is None:
        return True

    return parsed in {0, int(UINT64_MAX_VALUE)}


def _infer_single_directory_controller_address_range(
    components: list[dict[str, Any]],
) -> None:
    """
    Align a single DirectoryController with the aggregate MemController range.

    In common FUSE-generated memory hierarchies, one DirectoryController fans
    out to one or more MemControllers. SST can default a missing directory
    ``addr_range_end`` to a very broad region, but exported runnable JSON is
    clearer and safer when the directory's region matches the concrete memory
    span it routes to. When multiple directories exist, the exporter avoids
    guessing because each directory may intentionally own a subset/interleave.
    """

    directories = [
        component
        for component in components
        if component.get("type") == "memHierarchy.DirectoryController"
    ]
    memories = [
        component
        for component in components
        if component.get("type") == "memHierarchy.MemController"
    ]

    if len(directories) != 1 or not memories:
        return

    starts: list[int] = []
    ends: list[int] = []

    for memory in memories:
        params = memory.get("params")
        if not isinstance(params, dict):
            continue

        end = _parse_sst_integer_literal(params.get("addr_range_end"))
        if end is None:
            continue

        start = _parse_sst_integer_literal(params.get("addr_range_start"))
        starts.append(0 if start is None else start)
        ends.append(end)

    if not ends:
        return

    aggregate_start = min(starts or [0])
    aggregate_end = max(ends)

    directory = directories[0]
    params = directory.setdefault("params", {})
    if not isinstance(params, dict):
        return

    existing_start = _parse_sst_integer_literal(params.get("addr_range_start"))
    if "addr_range_start" not in params or existing_start is None:
        params["addr_range_start"] = str(aggregate_start)

    if "addr_range_end" not in params or _is_unbounded_or_default_address_end(
        params.get("addr_range_end")
    ):
        params["addr_range_end"] = str(aggregate_end)


def sst_component_type_for_node(node) -> str:
    """
    Convert a FUSE component node into an SST component type.

    SST component types are normally:
        element.component

    Example:
        memHierarchy.Cache
        merlin.hr_router
    """
    element = getattr(node.component, "element", "") or ""
    name = getattr(node.component, "name", "") or ""

    element = str(element).strip()
    name = str(name).strip()

    if not name:
        raise SSTJsonExportError(
            f"Component instance '{node.instance_name}' has no component type name."
        )

    if not element:
        return name

    return f"{element}.{name}"


def _is_suppressed_slot_param(param_name: Any, suppress_prefixed_slots: set[str]) -> bool:
    """Return true when a param belongs to an attached subcomponent slot."""

    name = str(param_name)

    return any(
        name == slot or name.startswith(f"{slot}.")
        for slot in suppress_prefixed_slots
    )


def raw_export_params_for_node(
    node,
    *,
    suppress_prefixed_slots: set[str] | None = None,
) -> dict[str, Any]:
    """Return user/FUSE model parameters that should be considered for export."""

    raw_params = dict(getattr(node, "parameters", {}) or {})
    suppress_prefixed_slots = suppress_prefixed_slots or set()

    if node_is_subcomponent(node):
        raw_params = {
            key: value
            for key, value in raw_params.items()
            if not is_visual_subcomponent_connection_parameter(key)
        }

    if suppress_prefixed_slots:
        raw_params = {
            key: value
            for key, value in raw_params.items()
            if not _is_suppressed_slot_param(key, suppress_prefixed_slots)
        }

    return non_empty_params(raw_params)


def exportable_params_for_node(
    node,
    *,
    suppress_prefixed_slots: set[str] | None = None,
) -> dict[str, Any]:
    """
    Return component parameters that should be written to SST JSON.

    The exporter makes safe literal SST metadata defaults explicit for the
    selected SST version, then overlays user-provided values. Symbolic/internal
    defaults are left for SST to resolve.
    """

    suppress_prefixed_slots = suppress_prefixed_slots or set()

    merged: dict[str, Any] = {}
    merged.update(
        default_params_for_node(
            node,
            suppress_prefixed_slots=suppress_prefixed_slots,
        )
    )
    merged.update(
        raw_export_params_for_node(
            node,
            suppress_prefixed_slots=suppress_prefixed_slots,
        )
    )

    return non_empty_params(merged)


def normalize_params_for_node(
    node,
    params: dict[str, Any],
) -> dict[str, str]:
    """
    Normalize a node's parameters, then stringify them for SST JSON.

    The policy layer still validates booleans, integers, floats, and unit
    strings so invalid user input is caught before export. The exported
    ``params`` object itself uses string values because SSTJSONModel parses
    component/subcomponent params as string key/value pairs.
    """

    component_type = sst_component_type_for_node(node)
    params = _normalize_sst_runtime_symbolic_values(params)
    normalized = normalize_params(
        component_type,
        params,
        parameter_metadata_for_node(node),
        node=node,
    )
    normalized = _drop_sst_runtime_incompatible_default_params(
        component_type,
        normalized,
    )
    return stringify_sst_params(normalized)


def build_partition(node) -> dict[str, int] | None:
    """
    Optional SST partition metadata.

    FUSE does not need to emit this yet unless you later add rank/thread fields
    to the properties panel. This function already supports common attribute
    names so future UI additions do not require rewriting the exporter.
    """
    rank = getattr(node, "rank", None)
    thread = getattr(node, "thread", None)

    if rank is None and thread is None:
        return None

    return {
        "rank": int(rank or 0),
        "thread": int(thread or 0),
    }


def build_sst_component(
    node,
    *,
    suppress_prefixed_slots: set[str] | None = None,
) -> dict[str, Any]:
    """
    Build one top-level SST JSON component object.

    Field order matters for readability and is also safer for SST's streaming
    reader behavior: top-level components emit name and type first.
    """

    component_type = sst_component_type_for_node(node)
    component: dict[str, Any] = {
        "name": node.instance_name,
        "type": component_type,
    }

    params = exportable_params_for_node(
        node,
        suppress_prefixed_slots=suppress_prefixed_slots,
    )

    if params:
        component["params"] = normalize_params_for_node(node, params)

    partition = build_partition(node)

    if partition is not None:
        component["partition"] = partition

    return component


def _child_attachments_for_node(
    node,
    attachments_by_parent_id: dict[int, list],
) -> tuple[list, set[str]]:
    """Return deterministic child attachments and their non-empty slot names."""

    child_attachments = sorted(
        attachments_by_parent_id.get(node.node_id, []),
        key=lambda item: (str(item.slot_name), str(item.name), int(item.attachment_id)),
    )
    attached_slot_names = {
        str(attachment.slot_name)
        for attachment in child_attachments
        if str(getattr(attachment, "slot_name", "") or "").strip()
    }
    return child_attachments, attached_slot_names


def _attach_child_subcomponents(
    component: dict[str, Any],
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    """Attach nested subcomponents to an already-built component/subcomponent."""

    child_attachments, _attached_slot_names = _child_attachments_for_node(
        node,
        attachments_by_parent_id,
    )
    children = []

    for attachment in child_attachments:
        child = nodes_by_id.get(attachment.child_node_id)
        if child is None:
            raise SSTJsonExportError(
                f"Cannot export subcomponent attachment '{attachment.name}': "
                f"missing child node {attachment.child_node_id}."
            )

        children.append(
            build_sst_subcomponent_tree(
                child,
                attachment.slot_name,
                attachments_by_parent_id,
                nodes_by_id,
            )
        )

    if children:
        component["subcomponents"] = children

    return component


def build_sst_subcomponent_tree(
    node,
    slot_name: str,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    """
    Build one nested SST JSON subcomponent object.

    SSTJSONModel subcomponent objects are keyed by their parent slot and type;
    unlike top-level components they do not accept a separate ``name`` field.
    """

    child_attachments, attached_slot_names = _child_attachments_for_node(
        node,
        attachments_by_parent_id,
    )
    del child_attachments  # The helper below will rebuild deterministic children.

    subcomponent: dict[str, Any] = {
        "slot_name": str(slot_name),
        "type": sst_component_type_for_node(node),
    }

    params = exportable_params_for_node(
        node,
        suppress_prefixed_slots=attached_slot_names,
    )

    if params:
        subcomponent["params"] = normalize_params_for_node(node, params)

    return _attach_child_subcomponents(
        subcomponent,
        node,
        attachments_by_parent_id,
        nodes_by_id,
    )


def build_sst_component_tree(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    """
    Build a component/subcomponent tree for SST JSON export.

    Attached child subcomponents are nested under their parent with the slot
    name that should be used by SST's subcomponent assignment mechanism.
    """
    _child_attachments, attached_slot_names = _child_attachments_for_node(
        node,
        attachments_by_parent_id,
    )

    component = build_sst_component(
        node,
        suppress_prefixed_slots=attached_slot_names,
    )

    return _attach_child_subcomponents(
        component,
        node,
        attachments_by_parent_id,
        nodes_by_id,
    )


def source_link_latency(link) -> str:
    latency = (
        getattr(link, "source_latency", "")
        or getattr(link, "latency", "")
        or DEFAULT_LINK_LATENCY
    )
    return str(latency).strip() or DEFAULT_LINK_LATENCY


def target_link_latency(link) -> str:
    latency = (
        getattr(link, "target_latency", "")
        or getattr(link, "latency", "")
        or DEFAULT_LINK_LATENCY
    )
    return str(latency).strip() or DEFAULT_LINK_LATENCY


def has_explicit_source_latency(link) -> bool:
    return bool(str(getattr(link, "source_latency", "") or "").strip())


def has_explicit_target_latency(link) -> bool:
    return bool(str(getattr(link, "target_latency", "") or "").strip())


def current_node_name(nodes_by_id: dict[int, object] | None, node_id: int, fallback: str) -> str:
    if nodes_by_id is None:
        return fallback

    node = nodes_by_id.get(node_id)
    if node is None:
        return fallback

    return getattr(node, "instance_name", "") or fallback


def _attachment_attr(attachment, name: str, fallback: str = "") -> str:
    return str(getattr(attachment, name, "") or fallback)


def _sst_component_reference(
    *,
    node_id: int | None,
    fallback_component: str,
    nodes_by_id: dict[int, object] | None = None,
    attachments_by_child_id: dict[int, object] | None = None,
    _seen: set[int] | None = None,
) -> str:
    """
    Resolve the component reference accepted by SST JSON links.

    SST's JSON loader nests subcomponents under their parent component and
    then resolves link endpoints with ConfigGraph::findComponentByName().
    That resolver expects nested subcomponents to be addressed as
    ``parent:slot`` (or ``parent:slot[index]``), while the endpoint ``port``
    remains the subcomponent's own port such as ``lowlink``. It does not
    accept flattened parent ports such as ``memory.lowlink``.
    """

    attachments_by_child_id = attachments_by_child_id or {}

    if node_id is None:
        return str(fallback_component or "")

    _seen = _seen or set()
    if node_id in _seen:
        return current_node_name(nodes_by_id, node_id, fallback_component)
    _seen.add(node_id)

    attachment = attachments_by_child_id.get(node_id)
    if attachment is None:
        return current_node_name(nodes_by_id, node_id, fallback_component)

    parent_ref = _sst_component_reference(
        node_id=getattr(attachment, "parent_node_id", None),
        fallback_component=_attachment_attr(
            attachment,
            "parent_component_name",
            fallback_component,
        ),
        nodes_by_id=nodes_by_id,
        attachments_by_child_id=attachments_by_child_id,
        _seen=_seen,
    )
    slot_name = _attachment_attr(attachment, "slot_name")

    if not parent_ref or not slot_name:
        return current_node_name(nodes_by_id, node_id, fallback_component)

    return f"{parent_ref}:{slot_name}"


def _sst_link_endpoint(
    *,
    node_id: int | None,
    fallback_component: str,
    port: str,
    nodes_by_id: dict[int, object] | None = None,
    attachments_by_child_id: dict[int, object] | None = None,
) -> tuple[str, str]:
    """
    Resolve an SST JSON link endpoint.

    Top-level component endpoints are exported as their component instance
    names. Attached subcomponent endpoints are exported as ``parent:slot``
    component references with the original subcomponent port unchanged.
    """

    return (
        _sst_component_reference(
            node_id=node_id,
            fallback_component=fallback_component,
            nodes_by_id=nodes_by_id,
            attachments_by_child_id=attachments_by_child_id,
        ),
        str(port or ""),
    )


def build_sst_link(
    link,
    nodes_by_id: dict[int, object] | None = None,
    attachments_by_child_id: dict[int, object] | None = None,
) -> dict[str, Any]:
    """
    Build one SST JSON link object.

    If nodes_by_id is provided, endpoint component names are resolved from the
    current component instances. This prevents stale serialized link endpoint
    names from leaking into the generated SST JSON after a user renames a
    component.

    If an endpoint is an attached SST SubComponent, the exported endpoint uses
    SST's nested component-reference syntax, for example ``cpu0:memory`` with
    port ``lowlink``.
    """
    name = getattr(link, "name", "") or f"link_{getattr(link, 'link_id', '')}"
    source_latency = source_link_latency(link)
    target_latency = target_link_latency(link)

    source_component, source_port = _sst_link_endpoint(
        node_id=getattr(link, "source_node_id", None),
        fallback_component=getattr(link, "source_component_name", "") or "",
        port=getattr(link, "source_port", "") or "",
        nodes_by_id=nodes_by_id,
        attachments_by_child_id=attachments_by_child_id,
    )
    target_component, target_port = _sst_link_endpoint(
        node_id=getattr(link, "target_node_id", None),
        fallback_component=getattr(link, "target_component_name", "") or "",
        port=getattr(link, "target_port", "") or "",
        nodes_by_id=nodes_by_id,
        attachments_by_child_id=attachments_by_child_id,
    )

    missing = []

    if not source_component:
        missing.append("source component")
    if not source_port:
        missing.append("source port")
    if not target_component:
        missing.append("target component")
    if not target_port:
        missing.append("target port")

    if missing:
        raise SSTJsonExportError(
            f"Cannot export link '{name}': missing {', '.join(missing)}."
        )

    return {
        "name": name,
        "noCut": bool(getattr(link, "no_cut", False)),
        "nonlocal": bool(getattr(link, "nonlocal_link", False)),
        "left": {
            "component": source_component,
            "port": source_port,
            "latency": source_latency,
        },
        "right": {
            "component": target_component,
            "port": target_port,
            "latency": target_latency,
        },
    }



def port_names_for_node(node) -> set[str]:
    names = set()

    if hasattr(node, "expanded_port_names"):
        try:
            names.update(str(name) for name in node.expanded_port_names())
        except Exception:
            pass

    for port in getattr(node, "ports", []) or []:
        name = getattr(port, "name", "")
        if name:
            names.add(str(name))

    return names


def node_is_sst(node) -> bool:
    return (getattr(node.component, "plugin_id", "") or "core") == "sst"


def node_is_subcomponent(node) -> bool:
    return bool(int(getattr(node.component, "is_subcomp", 0) or 0))


def add_export_policy_diagnostics(scene, add_issue) -> None:
    """Add grouped custom/changed SST export-policy diagnostics, if any."""

    try:
        from fuse.plugins.community.sst.component_catalog import (
            export_policy_diagnostics_for_scene,
        )

        diagnostics = export_policy_diagnostics_for_scene(scene)
    except Exception:
        # Export validation must not fail merely because diagnostic metadata is
        # unavailable. Structural/type validation below still protects export.
        return

    for message in diagnostics.warning_messages():
        add_issue(
            validation_issue(
                "sst_export_policy",
                "Project",
                message,
                severity="warning",
            )
        )


def validate_sst_json_export(scene) -> SSTExportReport:
    """Validate that a scene can be exported to SST JSON without repair."""
    from fuse.core.model.composite_flattening import flatten_scene_for_export

    scene = flatten_scene_for_export(scene)
    report = SSTExportReport()
    nodes = list(scene.component_items())
    links = list(getattr(scene, "links", []) or [])
    attachments = list(getattr(scene, "subcomp_attachments", []) or [])
    nodes_by_id = {node.node_id: node for node in nodes}
    attached_child_ids = {attachment.child_node_id for attachment in attachments}
    attachments_by_parent_id: dict[int, list] = {}
    for attachment in attachments:
        attachments_by_parent_id.setdefault(
            attachment.parent_node_id,
            [],
        ).append(attachment)

    def add_issue(issue):
        if getattr(issue, "severity", "error") == "warning":
            report.warnings.append(issue)
        else:
            report.errors.append(issue)

    if not nodes:
        add_issue(
            validation_issue(
                "sst_export",
                "Project",
                "There are no components to export to SST JSON.",
            )
        )

    target_ids = {
        str(getattr(node.component, "target_id", "") or "")
        for node in nodes
        if str(getattr(node.component, "target_id", "") or "")
    }
    if len(target_ids) > 1:
        add_issue(
            validation_issue(
                "sst_export",
                "Project",
                "SST JSON export requires all SST components to use the same target/version; "
                f"found {', '.join(sorted(target_ids))}.",
            )
        )
    else:
        add_export_policy_diagnostics(scene, add_issue)

    seen_names: dict[str, int] = {}
    for node in nodes:
        name = str(getattr(node, "instance_name", "") or "").strip()
        if not name:
            add_issue(
                validation_issue(
                    "sst_export_component",
                    "<unnamed component>",
                    "SST JSON export requires every component instance to have a name.",
                    node_id=getattr(node, "node_id", None),
                    parameter_name="name",
                )
            )
        elif name in seen_names:
            add_issue(
                validation_issue(
                    "sst_export_component",
                    name,
                    "SST JSON export requires component instance names to be unique.",
                    node_id=getattr(node, "node_id", None),
                    parameter_name="name",
                )
            )
        else:
            seen_names[name] = getattr(node, "node_id", None)

        if not node_is_sst(node):
            add_issue(
                validation_issue(
                    "sst_export_component",
                    name or "<unnamed component>",
                    "SST JSON export can only include SST components. Remove non-SST components or choose another exporter.",
                    node_id=getattr(node, "node_id", None),
                )
            )

        component_type = ""
        try:
            component_type = sst_component_type_for_node(node)
        except SSTJsonExportError as exc:
            add_issue(
                validation_issue(
                    "sst_export_component",
                    name or "<unnamed component>",
                    str(exc),
                    node_id=getattr(node, "node_id", None),
                )
            )

        if component_type:
            attached_slot_names = {
                str(attachment.slot_name)
                for attachment in attachments_by_parent_id.get(node.node_id, [])
                if str(getattr(attachment, "slot_name", "") or "").strip()
            }

            raw_user_params = raw_export_params_for_node(
                node,
                suppress_prefixed_slots=attached_slot_names,
            )
            params = exportable_params_for_node(
                node,
                suppress_prefixed_slots=attached_slot_names,
            )
            metadata_by_name = parameter_metadata_for_node(node)

            for param_name, metadata in metadata_by_name.items():
                if not should_require_metadata_param_for_export(
                    node,
                    str(param_name),
                    metadata,
                    params,
                    attached_slot_names,
                ):
                    continue

                add_issue(
                    validation_issue(
                        "sst_export_parameter",
                        name or "<unnamed component>",
                        (
                            f"Required SST parameter '{param_name}' is not set. "
                            "Set this parameter before exporting to SST JSON."
                        ),
                        node_id=getattr(node, "node_id", None),
                        parameter_name=str(param_name),
                    )
                )

            for param_name, param_value in params.items():
                metadata = metadata_by_name.get(param_name, {})

                try:
                    normalize_param_value(
                        component_type,
                        param_name,
                        param_value,
                        metadata,
                        node=node,
                    )
                except ValueError as exc:
                    add_issue(
                        validation_issue(
                            "sst_export_parameter",
                            name or "<unnamed component>",
                            (
                                f"Parameter '{param_name}' cannot be exported "
                                f"as the expected SST JSON type: {exc}"
                            ),
                            node_id=getattr(node, "node_id", None),
                            parameter_name=param_name,
                        )
                    )
                    continue

                if (
                    param_name in raw_user_params
                    and resolve_param_kind(
                        component_type,
                        param_name,
                        metadata,
                        node=node,
                    )
                    == ParamKind.UNKNOWN
                    and looks_like_untyped_number(param_value)
                ):
                    add_issue(
                        validation_issue(
                            "sst_export_warning",
                            name or "<unnamed component>",
                            (
                                f"Parameter '{param_name}' looks numeric but "
                                "does not have SST type metadata; exporting it as a string."
                            ),
                            severity="warning",
                            node_id=getattr(node, "node_id", None),
                            parameter_name=param_name,
                        )
                    )

        if node_is_subcomponent(node) and node.node_id not in attached_child_ids:
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    name or "<unnamed subcomponent>",
                    "SST SubComponent instances must be attached to a parent slot before export.",
                    node_id=getattr(node, "node_id", None),
                )
            )

    for attachment in attachments:
        parent = nodes_by_id.get(attachment.parent_node_id)
        child = nodes_by_id.get(attachment.child_node_id)
        object_name = getattr(attachment, "name", "SubComponent attachment")

        if parent is None:
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    "SubComponent attachment parent node is missing.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                )
            )
        if child is None:
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    "SubComponent attachment child node is missing.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                )
            )
            continue

        if child is not None and not node_is_subcomponent(child):
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    "Only SST SubComponent instances can be exported as subcomponent attachments.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                    node_id=getattr(child, "node_id", None),
                )
            )

        if not str(getattr(attachment, "slot_name", "") or "").strip():
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    "SubComponent attachment is missing the parent slot name.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                    parameter_name="slot_name",
                )
            )

        # SST subcomponent interface metadata is not standardized enough to
        # warn in normal export mode. If the visual parent/slot attachment is
        # structurally valid, the exporter trusts that attachment.

    seen_link_names: dict[str, int] = {}
    for link in links:
        object_name = getattr(link, "name", "") or f"link_{getattr(link, 'link_id', '')}"
        link_name = str(getattr(link, "name", "") or "").strip()
        if not link_name:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "SST JSON export requires every link to have a stable name.",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="name",
                )
            )
        elif link_name in seen_link_names:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "SST JSON export requires link names to be unique.",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="name",
                )
            )
        else:
            seen_link_names[link_name] = getattr(link, "link_id", None)

        source = nodes_by_id.get(getattr(link, "source_node_id", None))
        target = nodes_by_id.get(getattr(link, "target_node_id", None))

        if source is None:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link source component no longer exists.",
                    link_id=getattr(link, "link_id", None),
                )
            )
        if target is None:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link target component no longer exists.",
                    link_id=getattr(link, "link_id", None),
                )
            )

        if source is not None and not node_is_sst(source):
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link source is not an SST component.",
                    link_id=getattr(link, "link_id", None),
                    node_id=getattr(source, "node_id", None),
                )
            )
        if target is not None and not node_is_sst(target):
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link target is not an SST component.",
                    link_id=getattr(link, "link_id", None),
                    node_id=getattr(target, "node_id", None),
                )
            )

        source_port = str(getattr(link, "source_port", "") or "").strip()
        target_port = str(getattr(link, "target_port", "") or "").strip()
        if not source_port:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link source port is required for SST JSON export.",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="source_port",
                )
            )
        if not target_port:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link target port is required for SST JSON export.",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="target_port",
                )
            )

        if not has_explicit_source_latency(link):
            add_issue(
                validation_issue(
                    "sst_export_warning",
                    object_name,
                    f"Link source latency was not set; exporter will use the default {DEFAULT_LINK_LATENCY} latency.",
                    severity="warning",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="source_latency",
                )
            )
        if not has_explicit_target_latency(link):
            add_issue(
                validation_issue(
                    "sst_export_warning",
                    object_name,
                    f"Link target latency was not set; exporter will use the default {DEFAULT_LINK_LATENCY} latency.",
                    severity="warning",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="target_latency",
                )
            )

        if source is not None and source_port:
            ports = port_names_for_node(source)
            if ports and source_port not in ports:
                add_issue(
                    validation_issue(
                        "sst_export_warning",
                        object_name,
                        f"Source port '{source_port}' was not found in the source component metadata.",
                        severity="warning",
                        link_id=getattr(link, "link_id", None),
                        node_id=getattr(source, "node_id", None),
                        parameter_name="source_port",
                    )
                )
        if target is not None and target_port:
            ports = port_names_for_node(target)
            if ports and target_port not in ports:
                add_issue(
                    validation_issue(
                        "sst_export_warning",
                        object_name,
                        f"Target port '{target_port}' was not found in the target component metadata.",
                        severity="warning",
                        link_id=getattr(link, "link_id", None),
                        node_id=getattr(target, "node_id", None),
                        parameter_name="target_port",
                    )
                )

        if getattr(link, "compatibility_severity", "ok") == "warning":
            add_issue(
                validation_issue(
                    "sst_export_warning",
                    object_name,
                    getattr(link, "compatibility_message", "") or "Link compatibility is uncertain.",
                    severity="warning",
                    link_id=getattr(link, "link_id", None),
                )
            )
        elif getattr(link, "compatibility_severity", "ok") == "error":
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    getattr(link, "compatibility_message", "") or "Link compatibility failed.",
                    link_id=getattr(link, "link_id", None),
                )
            )

    return report


def normalize_shared_params_for_sst_json(
    shared_params: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    """Stringify nested shared-param values without changing caller objects."""

    if not shared_params:
        return shared_params

    normalized: list[dict[str, Any]] = []

    for group in shared_params:
        if not isinstance(group, dict):
            normalized.append(group)
            continue

        item = dict(group)
        params = item.get("params")

        if isinstance(params, dict):
            item["params"] = stringify_sst_params(non_empty_params(params))

        normalized.append(item)

    return normalized


def build_sst_json_dict(
    scene,
    program_options: dict[str, Any] | None = None,
    statistics_options: dict[str, Any] | None = None,
    shared_params: list[dict[str, Any]] | None = None,
    statistics_group: list[dict[str, Any]] | None = None,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """
    Build the SST JSON configuration dictionary from the current FUSE scene.

    This is intentionally separate from writing the file so tests can assert
    on the generated dictionary directly.
    """
    from fuse.core.model.composite_flattening import flatten_scene_for_export

    scene = flatten_scene_for_export(scene)
    nodes = sorted(scene.component_items(), key=lambda node: (str(node.instance_name), int(node.node_id)))
    nodes_by_id = {node.node_id: node for node in nodes}

    attachments = sorted(
        list(getattr(scene, "subcomp_attachments", []) or []),
        key=lambda item: (int(item.parent_node_id), str(item.slot_name), str(item.name), int(item.attachment_id)),
    )
    attached_child_ids = {attachment.child_node_id for attachment in attachments}
    attachments_by_child_id = {attachment.child_node_id: attachment for attachment in attachments}
    attachments_by_parent_id: dict[int, list] = {}

    for attachment in attachments:
        attachments_by_parent_id.setdefault(
            attachment.parent_node_id,
            [],
        ).append(attachment)

    components = [
        build_sst_component_tree(node, attachments_by_parent_id, nodes_by_id)
        for node in nodes
        if node.node_id not in attached_child_ids
    ]
    _infer_single_directory_controller_address_range(components)

    links = [
        build_sst_link(
            link,
            nodes_by_id=nodes_by_id,
            attachments_by_child_id=attachments_by_child_id,
        )
        for link in sorted(getattr(scene, "links", []) or [], key=lambda item: (str(item.name), int(item.link_id)))
    ]

    data: dict[str, Any] = {
        "program_options": program_options or {},
    }

    normalized_shared_params = normalize_shared_params_for_sst_json(shared_params)

    if normalized_shared_params:
        data["shared_params"] = normalized_shared_params

    data.update(
        {
            "statistics_options": statistics_options or {},
            "components": components,
            "statistics_group": statistics_group or [],
            "links": links,
        }
    )

    if include_metadata:
        data["metadata"] = {
            "generator": "FUSE",
            "format": SST_EXPORT_FORMAT,
            "schema_version": SST_EXPORT_SCHEMA_VERSION,
            "component_count": len(components),
            "link_count": len(links),
        }

    return data


def export_sst_json(
    scene,
    output_path: str | Path,
    program_options: dict[str, Any] | None = None,
    statistics_options: dict[str, Any] | None = None,
    shared_params: list[dict[str, Any]] | None = None,
    statistics_group: list[dict[str, Any]] | None = None,
    validate: bool = True,
    report_path: str | Path | None = None,
) -> Path:
    """
    Export the current FUSE scene to an SST JSON configuration file.
    """
    output_path = Path(output_path)

    report = validate_sst_json_export(scene)
    if validate:
        report.raise_for_errors()

    data = build_sst_json_dict(
        scene=scene,
        program_options=program_options,
        statistics_options=statistics_options,
        shared_params=shared_params,
        statistics_group=statistics_group,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )

    if report_path is not None:
        export_sst_report(report, report_path)

    return output_path


def export_sst_report(report: SSTExportReport, output_path: str | Path) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def issue_to_dict(issue) -> dict[str, Any]:
        return {
            "severity": getattr(issue, "severity", "error"),
            "type": getattr(issue, "issue_type", ""),
            "object": getattr(issue, "object_name", ""),
            "message": getattr(issue, "message", ""),
            "nodeId": getattr(issue, "node_id", None),
            "linkId": getattr(issue, "link_id", None),
            "attachmentId": getattr(issue, "attachment_id", None),
            "parameter": getattr(issue, "parameter_name", None),
        }

    data = {
        "canExport": report.can_export,
        "errors": [issue_to_dict(issue) for issue in report.errors],
        "warnings": [issue_to_dict(issue) for issue in report.warnings],
    }
    output_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return output_path
