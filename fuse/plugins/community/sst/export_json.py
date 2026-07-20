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

from fuse.core.model.port_templates import expand_parametric_port_template
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
from fuse.plugins.community.sst.runtime_overlays import (
    framework_version_for_node,
    logical_ports_for_component,
    runtime_slots_for_component,
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

EMBER_MOTIF_INTERFACE = "SST::Ember::EmberGenerator"
EMBER_MOTIF_SLOT = "motif"
EMBER_MOTIF_ATTACHMENT_KIND = "sst.ember.motif"
INTERNAL_EMBER_MOTIF_PARAMS = {
    "primary",
    "_motifNum",
    "_jobId",
    "_enginePtr",
    "distribModule",
}
EMBER_INIT_MOTIF_TYPE = "ember.InitMotif"
EMBER_FINI_MOTIF_TYPE = "ember.FiniMotif"
EMBER_MOTIF_TYPES_NOT_REQUIRING_INIT_FINI = {
    EMBER_INIT_MOTIF_TYPE,
    EMBER_FINI_MOTIF_TYPE,
    "ember.NullMotif",
}

FIREFLY_NIC_SIMPLE_MEMORY_SLOT = "simpleMemoryModel"
FIREFLY_NIC_SIMPLE_MEMORY_TYPE = "firefly.SimpleMemory"


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

    if component_type == "firefly.hades":
        node_perf = str(result.get("nodePerf", "")).strip()
        if node_perf in {"", "0", "1"}:
            # sst-info/policy catalogs can present a numeric/sentinel default
            # for nodePerf, but at runtime the value is a module name. Omitting
            # the parameter lets Hades use its compiled default,
            # firefly.SimpleNodePerf.
            result.pop("nodePerf", None)

    return result


_FIREFLY_CTRLMSG_PROCESS_RUNTIME_DEFAULTS: dict[str, Any] = {
    # firefly.ctrlMsg is the user-visible ProcessQueuesState subcomponent
    # nested under firefly.CtrlMsgProto's "process" slot. It constructs an
    # anonymous firefly.msgTiming helper using its own Params object. In
    # SST-Elements 16, msgTiming unconditionally loads several LatencyMod
    # modules when their selector params are missing/empty. The raw sst-info
    # catalog exposes empty string defaults, but those are not safe runtime
    # defaults. Emit explicit zero-latency modules unless the user selected
    # something else.
    "shortMsgLength": "4096",
    "sendAckDelay_ns": "0",
    "txSetupMod": "firefly.LatencyMod",
    "rxSetupMod": "firefly.LatencyMod",
    "txFiniMod": "firefly.LatencyMod",
    "rxFiniMod": "firefly.LatencyMod",
    "txSetupModParams.base": "0ns",
    "rxSetupModParams.base": "0ns",
    "txFiniModParams.base": "0ns",
    "rxFiniModParams.base": "0ns",
}


_FIREFLY_CTRLMSG_PROTO_RUNTIME_DEFAULTS: dict[str, Any] = {
    # firefly.CtrlMsgProto constructs an anonymous firefly.ctrlMsgMemory helper
    # and passes the CtrlMsgProto Params object to it. That helper
    # unconditionally loads tx/rx memcpy LatencyMod modules, so the defaults
    # belong on the proto node rather than the process child.
    "txMemcpyMod": "firefly.LatencyMod",
    "rxMemcpyMod": "firefly.LatencyMod",
    "txMemcpyModParams.base": "0ns",
    "rxMemcpyModParams.base": "0ns",
}


_FIREFLY_HADES_RUNTIME_DEFAULTS: dict[str, Any] = {
    # Hades asserts that netMapName is non-empty whenever netMapSize > 0.
    # Ember's Python endpoint generator uses a shared "Ember<jobId>" region
    # name; FUSE's visual graph usually has one job and no direct parent access
    # at this point, so use the same safe default for job 0 unless overridden.
    "netMapName": "Ember0",
}


_EMBER_ENGINE_RUNTIME_DEFAULTS: dict[str, Any] = {
    # EmberEngine builds its API map from api.N.module params and asserts that
    # at least one API exists. Normal Firefly/Ember MPI jobs use hadesMP.
    "api.0.module": "firefly.hadesMP",
}


SST_ATTACHMENT_SELECTOR_PARAMS: dict[tuple[str, str], str] = {
    # User-visible attached children should be the source of truth for selector
    # params. The exporter derives these params from the graph so stale saved
    # text fields cannot disagree with what is connected.
    ("merlin.hr_router", "topology"): "topology",
    ("merlin.hr_router", "XbarArb"): "xbar_arb",
    ("firefly.hades", "virtNic"): "nicModule",
}


SST_SELECTOR_ONLY_ATTACHMENT_SLOTS: set[tuple[str, str]] = {
    # hr_router does not load XbarArb as a user subcomponent. It reads xbar_arb
    # and then constructs the XbarArb slot anonymously itself, so a visual
    # attachment should export only the selector param.
    ("merlin.hr_router", "XbarArb"),
}


def _runtime_required_default_params_for_node(node) -> dict[str, Any]:
    """Return safe non-catalog defaults required by SST runtime loaders.

    Some SST Elements runtime helper subcomponents read parameters that are not
    represented as normal catalog defaults for the user-visible component. Those
    values belong in plugin policy rather than raw generated catalogs.
    """

    component_type = sst_component_type_for_node(node)

    if component_type == "firefly.CtrlMsgProto":
        return dict(_FIREFLY_CTRLMSG_PROTO_RUNTIME_DEFAULTS)

    if component_type == "firefly.ctrlMsg":
        return dict(_FIREFLY_CTRLMSG_PROCESS_RUNTIME_DEFAULTS)

    if component_type == "ember.EmberEngine":
        return dict(_EMBER_ENGINE_RUNTIME_DEFAULTS)

    if component_type == "firefly.hades":
        net_map_size = str(getattr(node, "parameters", {}).get("netMapSize", "")).strip()
        if net_map_size and not _looks_like_zero(net_map_size):
            return dict(_FIREFLY_HADES_RUNTIME_DEFAULTS)

    return {}


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


def runtime_slots_for_node(node) -> dict[str, Any]:
    """Return runtime overlay slots for a node's SST type/version."""

    try:
        component_type = sst_component_type_for_node(node)
    except SSTJsonExportError:
        return {}

    return runtime_slots_for_component(
        component_type,
        framework_version_for_node(node),
    )


def logical_ports_for_node(node) -> dict[str, Any]:
    """Return logical port mappings for a node's SST type/version."""

    try:
        component_type = sst_component_type_for_node(node)
    except SSTJsonExportError:
        return {}

    return logical_ports_for_component(
        component_type,
        framework_version_for_node(node),
    )


def _overlay_runtime_slot_names_for_node(node) -> set[str]:
    return set(runtime_slots_for_node(node).keys())


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
    merged.update(_runtime_required_default_params_for_node(node))
    merged.update(
        raw_export_params_for_node(
            node,
            suppress_prefixed_slots=suppress_prefixed_slots,
        )
    )

    return non_empty_params(merged)


def _normalize_ember_engine_motif_param_names(params: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy motifN type params into SST's motifN.name form."""

    result = dict(params)
    for key, value in list(params.items()):
        name = str(key or "").strip()
        if not name.startswith("motif"):
            continue

        suffix = name[len("motif") :]
        if not suffix.isdigit():
            continue

        target_key = f"motif{suffix}.name"
        if target_key not in result and value not in (None, ""):
            result[target_key] = value
        result.pop(name, None)

    return result


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
    if component_type == "ember.EmberEngine":
        params = _normalize_ember_engine_motif_param_names(params)
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
    nodes_by_id: dict[int, object] | None = None,
) -> tuple[list, set[str]]:
    """Return deterministic export-child attachments and their slot names."""

    child_attachments = sorted(
        [
            attachment
            for attachment in attachments_by_parent_id.get(node.node_id, [])
            if not _is_visual_parameter_attachment(node, attachment, nodes_by_id)
        ],
        key=lambda item: (str(item.slot_name), str(item.name), int(item.attachment_id)),
    )
    attached_slot_names = {
        str(attachment.slot_name)
        for attachment in child_attachments
        if str(getattr(attachment, "slot_name", "") or "").strip()
    }
    attached_slot_names.update(_overlay_runtime_slot_names_for_node(node))
    return child_attachments, attached_slot_names


def _attached_subcomponent_for_slot(
    node,
    slot_name: str,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
):
    """Return the child node attached to ``slot_name`` on ``node``, if any."""

    for attachment in attachments_by_parent_id.get(getattr(node, "node_id", None), []) or []:
        if _is_visual_parameter_attachment(node, attachment, nodes_by_id):
            continue
        if str(getattr(attachment, "slot_name", "") or "").strip() != slot_name:
            continue

        child = nodes_by_id.get(getattr(attachment, "child_node_id", None))
        if child is not None:
            return child

    return None


def _attached_child_for_slot_including_selector_only(
    node,
    slot_name: str,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
):
    """Return the attached child for selector derivation, including param-only slots."""

    for attachment in attachments_by_parent_id.get(getattr(node, "node_id", None), []) or []:
        if str(getattr(attachment, "slot_name", "") or "").strip() != slot_name:
            continue

        child = nodes_by_id.get(getattr(attachment, "child_node_id", None))
        if child is not None:
            return child

    return None


def _selector_param_attachment_key(parent, attachment) -> tuple[str, str]:
    return (
        sst_component_type_for_node(parent),
        str(getattr(attachment, "slot_name", "") or "").strip(),
    )


def _is_selector_only_attachment(parent, attachment) -> bool:
    return _selector_param_attachment_key(parent, attachment) in SST_SELECTOR_ONLY_ATTACHMENT_SLOTS


def _is_firefly_nic_simple_memory_attachment(
    parent,
    attachment,
    nodes_by_id: dict[int, object] | None = None,
) -> bool:
    """Return true for the FUSE-only firefly.nic SimpleMemory editor slot."""

    if sst_component_type_for_node(parent) != "firefly.nic":
        return False

    if str(getattr(attachment, "slot_name", "") or "").strip() != FIREFLY_NIC_SIMPLE_MEMORY_SLOT:
        return False

    if nodes_by_id is None:
        return True

    child = nodes_by_id.get(getattr(attachment, "child_node_id", None))
    return bool(child is not None and sst_component_type_for_node(child) == FIREFLY_NIC_SIMPLE_MEMORY_TYPE)


def _firefly_nic_simple_memory_params_for_node(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    """Fold an attached firefly.SimpleMemory node into firefly.nic params.

    firefly.nic loads firefly.SimpleMemory anonymously when useSimpleMemoryModel
    is enabled.  The visible subcomponent attachment is a FUSE editor aid; SST
    expects the attached node's params to be scoped as simpleMemoryModel.* on the
    parent NIC rather than exported as a real nested subcomponent.
    """

    if sst_component_type_for_node(node) != "firefly.nic":
        return {}

    for attachment in attachments_by_parent_id.get(getattr(node, "node_id", None), []) or []:
        if not _is_firefly_nic_simple_memory_attachment(node, attachment, nodes_by_id):
            continue

        child = nodes_by_id.get(getattr(attachment, "child_node_id", None))
        if child is None:
            continue

        params: dict[str, Any] = {"useSimpleMemoryModel": "1"}
        child_params = normalize_params_for_node(
            child,
            non_empty_params(dict(getattr(child, "parameters", {}) or {})),
        )
        for key, value in child_params.items():
            params[f"{FIREFLY_NIC_SIMPLE_MEMORY_SLOT}.{key}"] = value

        return params

    return {}


def _derived_export_params_for_node(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    """Return SST params derived from graph structure rather than user fields."""

    component_type = sst_component_type_for_node(node)

    derived: dict[str, Any] = {}

    for (parent_type, slot_name), selector_param in SST_ATTACHMENT_SELECTOR_PARAMS.items():
        if parent_type != component_type:
            continue

        child = _attached_child_for_slot_including_selector_only(
            node,
            slot_name,
            attachments_by_parent_id,
            nodes_by_id,
        )
        if child is None:
            continue

        child_type = sst_component_type_for_node(child)
        if child_type:
            derived[selector_param] = child_type

    if component_type == "ember.EmberEngine":
        derived.update(
            _ember_motif_params_for_node(
                node,
                attachments_by_parent_id,
                nodes_by_id,
            )
        )

    if component_type == "firefly.nic":
        derived.update(
            _firefly_nic_simple_memory_params_for_node(
                node,
                attachments_by_parent_id,
                nodes_by_id,
            )
        )

    return derived


def _merge_derived_params_into_component(
    component: dict[str, Any],
    node,
    derived_params: dict[str, Any],
) -> None:
    """Normalize and merge derived params into an exported SST component."""

    if not derived_params:
        return

    params = dict(component.get("params", {}) or {})
    params.update(normalize_params_for_node(node, derived_params))
    if params:
        component["params"] = params


def _build_runtime_overlay_subcomponent_tree(
    slot_name: str,
    component_type: str,
    version: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an injected runtime-overlay subcomponent tree."""

    subcomponent: dict[str, Any] = {
        "slot_name": slot_name,
        "type": component_type,
    }

    cleaned_params = stringify_sst_params(non_empty_params(dict(params or {})))
    if cleaned_params:
        subcomponent["params"] = cleaned_params

    children = []
    for child_slot_name, child_slot in sorted(
        runtime_slots_for_component(component_type, version).items(),
        key=lambda item: item[0],
    ):
        if not child_slot.inject_default or not child_slot.default_type:
            continue
        children.append(
            _build_runtime_overlay_subcomponent_tree(
                child_slot_name,
                child_slot.default_type,
                version,
                child_slot.params,
            )
        )

    if children:
        subcomponent["subcomponents"] = children

    return subcomponent


def _injected_runtime_overlay_subcomponents(
    node,
    child_attachments: list,
) -> list[dict[str, Any]]:
    """Return export subcomponents injected by runtime overlay defaults."""

    attached_slots = {
        str(getattr(attachment, "slot_name", "") or "").strip()
        for attachment in child_attachments
    }
    version = framework_version_for_node(node)
    injected = []

    for slot_name, slot in sorted(runtime_slots_for_node(node).items(), key=lambda item: item[0]):
        if slot_name in attached_slots:
            continue
        if not slot.inject_default or not slot.default_type:
            continue
        injected.append(
            _build_runtime_overlay_subcomponent_tree(
                slot_name,
                slot.default_type,
                version,
                slot.params,
            )
        )

    return injected


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
        nodes_by_id,
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

    children.extend(_injected_runtime_overlay_subcomponents(node, child_attachments))

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
        nodes_by_id,
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

    _merge_derived_params_into_component(
        subcomponent,
        node,
        _derived_export_params_for_node(
            node,
            attachments_by_parent_id,
            nodes_by_id,
        ),
    )

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
        nodes_by_id,
    )

    component = build_sst_component(
        node,
        suppress_prefixed_slots=attached_slot_names,
    )
    _merge_derived_params_into_component(
        component,
        node,
        _derived_export_params_for_node(
            node,
            attachments_by_parent_id,
            nodes_by_id,
        ),
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


def _runtime_path_component_reference(
    *,
    base_component: str,
    component_path: str,
) -> str:
    """Append a colon-separated runtime subcomponent path to an SST component ref."""

    current = str(base_component or "").strip()
    for part in str(component_path or "").split(":"):
        part = part.strip()
        if part:
            current = f"{current}:{part}" if current else part
    return current


def _logical_port_mapping_for_endpoint(node, port: str):
    if node is None:
        return None
    return logical_ports_for_node(node).get(str(port or "").strip())


def _resolved_endpoint_port_name(node, port: str) -> str:
    """Resolve a saved SST printf-style port template to a concrete port name."""

    port_name = str(port or "").strip()
    if "%(" not in port_name:
        return port_name

    expanded = expand_parametric_port_template(
        port_name,
        parameters=getattr(node, "parameters", {}) if node is not None else {},
        variable_port_counts=getattr(node, "variable_port_counts", {}) if node is not None else {},
    )
    concrete = [name for name in expanded if name and name != port_name]

    if len(concrete) == 1:
        return concrete[0]

    # Older saved models may contain a template endpoint before the UI has had
    # a chance to materialize it. Export the first concrete port rather than
    # emitting an SST-JSON link to the literal template, which SST will reject.
    if concrete:
        return concrete[0]

    return port_name


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

    base_component = _sst_component_reference(
        node_id=node_id,
        fallback_component=fallback_component,
        nodes_by_id=nodes_by_id,
        attachments_by_child_id=attachments_by_child_id,
    )

    node = nodes_by_id.get(node_id) if nodes_by_id is not None and node_id is not None else None
    endpoint_port = _resolved_endpoint_port_name(node, str(port or ""))
    mapping = _logical_port_mapping_for_endpoint(node, endpoint_port)
    if mapping is not None:
        return (
            _runtime_path_component_reference(
                base_component=base_component,
                component_path=mapping.component_path,
            ),
            mapping.port,
        )

    return (
        base_component,
        endpoint_port,
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


def _attachment_metadata(attachment) -> dict[str, Any]:
    metadata = getattr(attachment, "plugin_metadata", {}) or {}
    return dict(metadata) if isinstance(metadata, dict) else {}


def _attachment_declares_visual_kind(attachment, kind: str) -> bool:
    return _attachment_metadata(attachment).get("visual_attachment_kind") == kind


def _node_iface(node) -> str:
    return str(getattr(getattr(node, "component", None), "iface", "") or "").strip()


def _is_ember_motif_node(node) -> bool:
    component = getattr(node, "component", None)
    return (
        sst_component_type_for_node(node).startswith("ember.")
        and bool(int(getattr(component, "is_subcomp", 0) or 0))
        and _node_iface(node) == EMBER_MOTIF_INTERFACE
    )


def _is_ember_motif_attachment(
    parent,
    attachment,
    nodes_by_id: dict[int, object] | None = None,
) -> bool:
    """Return true for visual EmberEngine.motif -> EmberGenerator attachments."""

    if str(getattr(attachment, "slot_name", "") or "").strip() != EMBER_MOTIF_SLOT:
        return False

    if _attachment_declares_visual_kind(attachment, EMBER_MOTIF_ATTACHMENT_KIND):
        return True

    if sst_component_type_for_node(parent) != "ember.EmberEngine":
        return False

    if nodes_by_id is None:
        return False

    child = nodes_by_id.get(getattr(attachment, "child_node_id", None))
    return bool(child is not None and _is_ember_motif_node(child))


def _is_visual_parameter_attachment(
    parent,
    attachment,
    nodes_by_id: dict[int, object] | None = None,
) -> bool:
    """Return true when an attachment is a plugin-owned visual parameter edge."""

    if _is_ember_motif_attachment(parent, attachment, nodes_by_id):
        return True

    if _is_firefly_nic_simple_memory_attachment(parent, attachment, nodes_by_id):
        return True

    return _is_selector_only_attachment(parent, attachment)


def _exported_attachment_slot_names(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object] | None = None,
) -> set[str]:
    return {
        str(attachment.slot_name)
        for attachment in attachments_by_parent_id.get(getattr(node, "node_id", None), [])
        if str(getattr(attachment, "slot_name", "") or "").strip()
        and not _is_visual_parameter_attachment(node, attachment, nodes_by_id)
    }


def _visual_parameter_child_node_ids(
    nodes_by_id: dict[int, object],
    attachments: list,
) -> set[int]:
    result: set[int] = set()
    for attachment in attachments:
        parent = nodes_by_id.get(getattr(attachment, "parent_node_id", None))
        if parent is None:
            continue
        if _is_visual_parameter_attachment(parent, attachment, nodes_by_id):
            child_id = getattr(attachment, "child_node_id", None)
            if child_id is not None:
                result.add(child_id)
    return result


def _ordered_ember_motif_attachments_for_engine(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> list:
    attachments = [
        attachment
        for attachment in attachments_by_parent_id.get(getattr(node, "node_id", None), []) or []
        if _is_ember_motif_attachment(node, attachment, nodes_by_id)
    ]
    return sorted(
        attachments,
        key=lambda item: (int(getattr(item, "attachment_id", 0) or 0), str(getattr(item, "name", "") or "")),
    )


def _non_empty_motif_user_params(node) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for key, value in dict(getattr(node, "parameters", {}) or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        if name in INTERNAL_EMBER_MOTIF_PARAMS or name.startswith("_"):
            continue
        if value in (None, ""):
            continue
        params[name] = value
    return params


def _motif_entries_with_required_init_fini(
    entries: list[tuple[str, dict[str, Any]]],
) -> list[tuple[str, dict[str, Any]]]:
    """Return motif entries wrapped with Ember Init/Fini when a workload needs it."""

    if not entries:
        return entries

    has_workload_motif = any(
        motif_type not in EMBER_MOTIF_TYPES_NOT_REQUIRING_INIT_FINI
        for motif_type, _params in entries
    )
    if not has_workload_motif:
        return entries

    wrapped = list(entries)
    if wrapped[0][0] != EMBER_INIT_MOTIF_TYPE:
        wrapped.insert(0, (EMBER_INIT_MOTIF_TYPE, {}))
    if wrapped[-1][0] != EMBER_FINI_MOTIF_TYPE:
        wrapped.append((EMBER_FINI_MOTIF_TYPE, {}))
    return wrapped


def _ember_motif_params_for_node(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    if sst_component_type_for_node(node) != "ember.EmberEngine":
        return {}

    motif_attachments = _ordered_ember_motif_attachments_for_engine(
        node,
        attachments_by_parent_id,
        nodes_by_id,
    )
    if not motif_attachments:
        return {}

    motif_entries: list[tuple[str, dict[str, Any]]] = []
    for attachment in motif_attachments:
        child = nodes_by_id.get(getattr(attachment, "child_node_id", None))
        if child is None:
            continue

        motif_type = sst_component_type_for_node(child)
        if not motif_type:
            continue

        motif_params = {
            param_name: param_value
            for param_name, param_value in _non_empty_motif_user_params(child).items()
            if param_name != "name"
        }
        motif_entries.append((motif_type, motif_params))

    motif_entries = _motif_entries_with_required_init_fini(motif_entries)
    derived: dict[str, Any] = {"motif_count": str(len(motif_entries))}
    for index, (motif_type, motif_params) in enumerate(motif_entries):
        derived[f"motif{index}.name"] = motif_type
        for param_name, param_value in motif_params.items():
            derived[f"motif{index}.{param_name}"] = param_value

    return derived


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


def _group_list_from_sst_value(value: Any) -> list[int]:
    """Parse SST MemNIC source/destination group values into integers."""

    if value is None:
        return []

    if isinstance(value, int) and not isinstance(value, bool):
        return [value]

    if isinstance(value, (list, tuple, set)):
        result: list[int] = []
        for item in value:
            result.extend(_group_list_from_sst_value(item))
        return result

    text = str(value).strip()
    if not text or text in {"[]", "{}"}:
        return []

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, list):
        return _group_list_from_sst_value(parsed)
    if isinstance(parsed, int) and not isinstance(parsed, bool):
        return [parsed]

    groups: list[int] = []
    for token in text.replace(";", ",").split(","):
        token = token.strip()
        if not token:
            continue
        parsed_int = _parse_sst_integer_literal(token)
        if parsed_int is not None:
            groups.append(parsed_int)

    return groups


def _node_export_params_for_validation(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    """Return exportable params plus graph-derived params for validation."""

    attached_slot_names = _exported_attachment_slot_names(
        node,
        attachments_by_parent_id,
        nodes_by_id,
    )
    params = exportable_params_for_node(
        node,
        suppress_prefixed_slots=attached_slot_names,
    )
    params.update(
        _derived_export_params_for_node(
            node,
            attachments_by_parent_id,
            nodes_by_id,
        )
    )
    return params


def _subcomponent_parent_attachment(
    node,
    attachments_by_child_id: dict[int, object],
):
    return attachments_by_child_id.get(getattr(node, "node_id", None))


def _infer_memnic_role(
    node,
    nodes_by_id: dict[int, object],
    attachments_by_child_id: dict[int, object],
) -> str:
    """Infer a MemNIC role from its parent component type and slot."""

    attachment = _subcomponent_parent_attachment(node, attachments_by_child_id)
    if attachment is None:
        return "unknown"

    parent = nodes_by_id.get(getattr(attachment, "parent_node_id", None))
    if parent is None:
        return "unknown"

    parent_type = sst_component_type_for_node(parent)
    slot_name = str(getattr(attachment, "slot_name", "") or "").strip()

    if parent_type == "memHierarchy.standardInterface" and slot_name == "lowlink":
        return "requester"

    if parent_type == "memHierarchy.MemController" and slot_name == "highlink":
        return "memory_target"

    if parent_type == "memHierarchy.Cache" and slot_name == "highlink":
        return "cache_upstream"

    if parent_type == "memHierarchy.Cache" and slot_name == "lowlink":
        return "cache_downstream"

    if parent_type == "memHierarchy.DirectoryController" and slot_name == "highlink":
        return "directory_upstream"

    if parent_type == "memHierarchy.DirectoryController" and slot_name == "lowlink":
        return "directory_downstream"

    return "unknown"


def _standard_cpu_has_direct_memnic_lowlink(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> bool:
    """Return true for standardCPU -> standardInterface -> MemNIC topologies."""

    iface = _attached_subcomponent_for_slot(
        node,
        "memory",
        attachments_by_parent_id,
        nodes_by_id,
    )
    if iface is None or sst_component_type_for_node(iface) != "memHierarchy.standardInterface":
        return False

    lowlink = _attached_subcomponent_for_slot(
        iface,
        "lowlink",
        attachments_by_parent_id,
        nodes_by_id,
    )

    return lowlink is not None and sst_component_type_for_node(lowlink) == "memHierarchy.MemNIC"


def _runtime_path_exists(
    node,
    component_path: str,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> bool:
    """Return true if a runtime overlay component path exists or is injected."""

    current = node
    for part in str(component_path or "").split(":"):
        slot_name = part.strip()
        if not slot_name:
            continue

        child = _attached_subcomponent_for_slot(
            current,
            slot_name,
            attachments_by_parent_id,
            nodes_by_id,
        )
        if child is not None:
            current = child
            continue

        slot = runtime_slots_for_node(current).get(slot_name)
        if slot is not None and slot.inject_default and slot.default_type:
            # The exporter will materialize this runtime slot.  For nested
            # paths below an injected slot, follow the default type using a
            # tiny synthetic object for overlay lookup only.
            from types import SimpleNamespace
            component = SimpleNamespace(
                plugin_id="sst",
                element=slot.default_type.split(".", 1)[0] if "." in slot.default_type else "",
                name=slot.default_type.split(".", 1)[1] if "." in slot.default_type else slot.default_type,
                framework_version=framework_version_for_node(current),
                is_subcomp=1,
            )
            current = SimpleNamespace(
                node_id=None,
                instance_name=slot.default_type,
                component=component,
                parameters={},
            )
            continue

        return False

    return True


def _add_runtime_overlay_guidance(
    nodes: list,
    links: list,
    nodes_by_id: dict[int, object],
    attachments_by_parent_id: dict[int, list],
    add_issue,
) -> None:
    """Validate versioned runtime-overlay slots and logical ports."""

    for node in nodes:
        object_name = str(getattr(node, "instance_name", "") or "SST component")

        for slot_name, slot in sorted(runtime_slots_for_node(node).items(), key=lambda item: item[0]):
            child = _attached_subcomponent_for_slot(
                node,
                slot_name,
                attachments_by_parent_id,
                nodes_by_id,
            )
            if child is None and slot.required and not slot.inject_default:
                default_hint = f" Default type: {slot.default_type}." if slot.default_type else ""
                add_issue(
                    validation_issue(
                        "sst_export_runtime_slot",
                        object_name,
                        (
                            f"Required SST runtime subcomponent slot '{slot_name}' is not filled. "
                            "This slot is supplied by the SST plugin runtime overlay because it is loaded by SST runtime code "
                            "but is not fully declared by sst-info."
                            f"{default_hint}"
                        ),
                        node_id=getattr(node, "node_id", None),
                        parameter_name=slot_name,
                    )
                )

        logical_ports = logical_ports_for_node(node)
        for port_name, mapping in sorted(logical_ports.items()):
            if not _runtime_path_exists(
                node,
                mapping.component_path,
                attachments_by_parent_id,
                nodes_by_id,
            ):
                # Only warn here; the required-slot check above provides the
                # blocking diagnostic for missing required overlay slots.
                add_issue(
                    validation_issue(
                        "sst_export_runtime_port",
                        object_name,
                        (
                            f"Logical port '{port_name}' maps to runtime path "
                            f"'{mapping.component_path}.{mapping.port}', but that path is not complete. "
                            "Fill the required runtime subcomponent slots or use a template that expands them."
                        ),
                        severity="warning",
                        node_id=getattr(node, "node_id", None),
                        parameter_name=port_name,
                    )
                )

    for link in links:
        for side in ("source", "target"):
            node = nodes_by_id.get(getattr(link, f"{side}_node_id", None))
            port = str(getattr(link, f"{side}_port", "") or "").strip()
            mapping = _logical_port_mapping_for_endpoint(node, port)
            if mapping is None:
                continue
            if not _runtime_path_exists(
                node,
                mapping.component_path,
                attachments_by_parent_id,
                nodes_by_id,
            ):
                add_issue(
                    validation_issue(
                        "sst_export_runtime_port",
                        getattr(link, "name", "") or f"link_{getattr(link, 'link_id', '')}",
                        (
                            f"Link {side} uses logical port '{port}', which exports to "
                            f"'{mapping.component_path}.{mapping.port}', but that runtime path is incomplete."
                        ),
                        node_id=getattr(node, "node_id", None),
                        link_id=getattr(link, "link_id", None),
                        parameter_name=f"{side}_port",
                    )
                )


def _add_sst_specific_guidance(
    nodes: list,
    nodes_by_id: dict[int, object],
    attachments_by_parent_id: dict[int, list],
    attachments_by_child_id: dict[int, object],
    add_issue,
) -> None:
    """Add graph-aware SST guidance for common memHierarchy/Merlin traps."""

    memnic_infos: list[dict[str, Any]] = []
    groups: dict[int, list[dict[str, Any]]] = {}

    for node in nodes:
        if sst_component_type_for_node(node) != "memHierarchy.MemNIC":
            continue

        params = _node_export_params_for_validation(
            node,
            attachments_by_parent_id,
            nodes_by_id,
        )
        group = _parse_sst_integer_literal(params.get("group"))
        role = _infer_memnic_role(node, nodes_by_id, attachments_by_child_id)
        info = {
            "node": node,
            "params": params,
            "group": group,
            "role": role,
            "sources": _group_list_from_sst_value(params.get("sources")),
            "destinations": _group_list_from_sst_value(params.get("destinations")),
        }
        memnic_infos.append(info)
        if group is not None:
            groups.setdefault(group, []).append(info)

        object_name = str(getattr(node, "instance_name", "") or "MemNIC")
        if group is None:
            add_issue(
                validation_issue(
                    "sst_export_memnic",
                    object_name,
                    "MemNIC parameter 'group' is required for networked memHierarchy routing.",
                    node_id=getattr(node, "node_id", None),
                    parameter_name="group",
                )
            )

    for info in memnic_infos:
        node = info["node"]
        object_name = str(getattr(node, "instance_name", "") or "MemNIC")
        role = info["role"]

        for param_name in ("sources", "destinations"):
            for group in info[param_name]:
                if group not in groups:
                    add_issue(
                        validation_issue(
                            "sst_export_memnic",
                            object_name,
                            f"MemNIC parameter '{param_name}' references group {group}, but no MemNIC in this network uses that group.",
                            severity="warning",
                            node_id=getattr(node, "node_id", None),
                            parameter_name=param_name,
                        )
                    )

        if role == "requester" and not info["destinations"]:
            add_issue(
                validation_issue(
                    "sst_export_memnic",
                    object_name,
                    "Requester-side MemNIC has no destinations. Usually set destinations to the memory/cache target group.",
                    severity="warning",
                    node_id=getattr(node, "node_id", None),
                    parameter_name="destinations",
                )
            )

        if role == "memory_target" and info["destinations"]:
            requester_destination_groups = [
                group
                for group in info["destinations"]
                if any(member["role"] == "requester" for member in groups.get(group, []))
            ]
            if requester_destination_groups:
                add_issue(
                    validation_issue(
                        "sst_export_memnic",
                        object_name,
                        (
                            "Memory-controller-side MemNIC should not list requester groups as destinations; "
                            f"group(s) {requester_destination_groups} contain requester endpoints that advertise overlapping default address ranges. "
                            "Use sources for requester groups and leave destinations blank."
                        ),
                        node_id=getattr(node, "node_id", None),
                        parameter_name="destinations",
                    )
                )
            else:
                add_issue(
                    validation_issue(
                        "sst_export_memnic",
                        object_name,
                        "Memory-controller-side MemNIC usually should leave destinations blank and use sources for requester groups.",
                        severity="warning",
                        node_id=getattr(node, "node_id", None),
                        parameter_name="destinations",
                    )
                )

    for node in nodes:
        if sst_component_type_for_node(node) != "memHierarchy.standardCPU":
            continue
        if not _standard_cpu_has_direct_memnic_lowlink(node, attachments_by_parent_id, nodes_by_id):
            continue

        params = _node_export_params_for_validation(
            node,
            attachments_by_parent_id,
            nodes_by_id,
        )
        enabled = [
            name
            for name in ("flush_freq", "flushcache_freq", "flushinv_freq", "llsc_freq")
            if (_parse_sst_integer_literal(params.get(name)) or 0) > 0
        ]
        if enabled:
            add_issue(
                validation_issue(
                    "sst_export_standardcpu",
                    str(getattr(node, "instance_name", "") or "standardCPU"),
                    (
                        "This standardCPU is connected directly to a MemNIC without a cache, "
                        f"but cache-line-dependent traffic is enabled ({', '.join(enabled)}). "
                        "Set these frequencies to 0 or insert a Cache between the CPU interface and the MemNIC."
                    ),
                    severity="warning",
                    node_id=getattr(node, "node_id", None),
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
    attachments_by_child_id = {attachment.child_node_id: attachment for attachment in attachments}
    attachments_by_parent_id: dict[int, list] = {}
    for attachment in attachments:
        attachments_by_parent_id.setdefault(
            attachment.parent_node_id,
            [],
        ).append(attachment)

    visual_parameter_child_ids = _visual_parameter_child_node_ids(nodes_by_id, attachments)

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
        if getattr(node, "node_id", None) in visual_parameter_child_ids:
            continue

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
            attached_slot_names = _exported_attachment_slot_names(
                node,
                attachments_by_parent_id,
                nodes_by_id,
            )

            raw_user_params = raw_export_params_for_node(
                node,
                suppress_prefixed_slots=attached_slot_names,
            )
            params = _node_export_params_for_validation(
                node,
                attachments_by_parent_id,
                nodes_by_id,
            )
            metadata_by_name = parameter_metadata_for_node(node)

            if component_type == "merlin.hr_router":
                topology_child = _attached_subcomponent_for_slot(
                    node,
                    "topology",
                    attachments_by_parent_id,
                    nodes_by_id,
                )
                if topology_child is not None:
                    attached_topology_type = sst_component_type_for_node(topology_child)
                    raw_topology = raw_user_params.get("topology")
                    if raw_topology and str(raw_topology).strip() != attached_topology_type:
                        add_issue(
                            validation_issue(
                                "sst_export_topology",
                                name or "<unnamed component>",
                                (
                                    f"Router topology parameter is {raw_topology!r}, but the attached topology subcomponent is "
                                    f"{attached_topology_type!r}; exporter will use the attached topology type."
                                ),
                                severity="warning",
                                node_id=getattr(node, "node_id", None),
                                parameter_name="topology",
                            )
                        )

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
            if ports and source_port not in ports and source_port not in logical_ports_for_node(source):
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
            if ports and target_port not in ports and target_port not in logical_ports_for_node(target):
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

    _add_runtime_overlay_guidance(
        nodes,
        links,
        nodes_by_id,
        attachments_by_parent_id,
        add_issue,
    )

    _add_sst_specific_guidance(
        nodes,
        nodes_by_id,
        attachments_by_parent_id,
        attachments_by_child_id,
        add_issue,
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
