# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Runtime SST export policy helpers used by the JSON exporter."""

from __future__ import annotations

from typing import Any

from fuse.plugins.community.sst.policy.default_classifier import (
    classify_default,
    infer_kind_from_description,
    looks_like_untyped_number,
    metadata_default_is_internal_type,
    metadata_default_is_symbolic,
    normalize_value,
)
from fuse.plugins.community.sst.policy.loader import component_policy, normalize_sst_version, param_policy_override
from fuse.plugins.community.sst.policy.models import (
    DefaultKind,
    MissingSeverity,
    ParamKind,
    ParamPolicy,
    RequiredContext,
)


def component_type_for_node(node) -> str:
    """Return the SST element.component type for a FUSE node."""

    component = getattr(node, "component", None)
    element = str(getattr(component, "element", "") or "").strip()
    name = str(getattr(component, "name", "") or "").strip()

    if not name:
        return ""

    return f"{element}.{name}" if element else name


def node_is_subcomponent(node) -> bool:
    """Return true when a FUSE node represents an SST SubComponent."""

    component = getattr(node, "component", None)
    return bool(int(getattr(component, "is_subcomp", 0) or 0))


def framework_version_for_node(node) -> str:
    """Return the SST framework version associated with a node, when known."""

    component = getattr(node, "component", None)

    for attr in ("framework_version", "target_label", "target_id"):
        value = getattr(component, attr, "")
        version = normalize_sst_version(value)
        if version:
            # target_id is often a database id; use it only if it looks version-like.
            if attr == "target_id" and "." not in version:
                continue
            return version

    target_id = getattr(component, "target_id", "")

    if target_id not in (None, ""):
        try:
            from fuse.core.persistence.database import get_connection

            with get_connection() as conn:
                row = conn.execute(
                    """
                    SELECT version
                    FROM sst_framework_versions
                    WHERE id = ?
                    """,
                    (int(target_id),),
                ).fetchone()

            if row is not None:
                version = normalize_sst_version(row["version"])
                if version:
                    return version
        except Exception:
            pass

    return ""


def _is_suppressed_slot_param(param_name: Any, suppress_prefixed_slots: set[str]) -> bool:
    """Return true when a param belongs to an attached subcomponent slot."""

    name = str(param_name)

    return any(
        name == slot or name.startswith(f"{slot}.")
        for slot in suppress_prefixed_slots
    )


def parameter_metadata_for_node(node) -> dict[str, dict[str, Any]]:
    """Load imported SST parameter metadata for a node, when available."""

    component = getattr(node, "component", None)
    if component is None or (getattr(component, "plugin_id", "") or "") != "sst":
        return {}

    component_id = getattr(component, "component_id", None)
    if component_id in (None, ""):
        return {}

    target_id = getattr(component, "target_id", None) or None

    try:
        from fuse.plugins.community.sst.db_utils import get_parameters_for_component

        rows = get_parameters_for_component(component_id, framework_version_id=target_id)
    except Exception:
        return {}

    metadata: dict[str, dict[str, Any]] = {}

    for row in rows:
        name = str(row.get("name", "")).strip()
        if not name:
            continue

        default_value = row.get("default_val", "")
        required = bool(row.get("required", False))

        # Some import paths encode "required" by omitting/emptying default_val.
        if isinstance(default_value, str) and default_value.strip() == "<required>":
            required = True
            default_value = ""

        metadata[name] = {
            "description": row.get("description", "") or "",
            "default_val": default_value,
            "required": required,
        }

    return metadata


def _enum_value(enum_cls, value: Any, default):
    if value is None:
        return default

    try:
        return enum_cls(str(value))
    except ValueError:
        return default


def _override_kind(value: Any, fallback: ParamKind) -> ParamKind:
    return _enum_value(ParamKind, value, fallback)


def _override_default_kind(value: Any, fallback: DefaultKind) -> DefaultKind:
    return _enum_value(DefaultKind, value, fallback)


def _override_missing_severity(value: Any, fallback: MissingSeverity) -> MissingSeverity:
    return _enum_value(MissingSeverity, value, fallback)


def _override_required_context(value: Any, fallback: RequiredContext) -> RequiredContext:
    return _enum_value(RequiredContext, value, fallback)


def resolve_param_policy(
    component_type: str,
    param_name: str,
    metadata: dict[str, Any] | None = None,
    *,
    node=None,
) -> ParamPolicy:
    """Resolve the effective policy for one SST parameter."""

    metadata = metadata or {}
    version = framework_version_for_node(node) if node is not None else ""
    override = param_policy_override(version, component_type, param_name) if version else {}

    inferred_kind = infer_kind_from_description(metadata.get("description", ""))
    kind = _override_kind(override.get("kind"), inferred_kind)

    required = bool(metadata.get("required", False))
    if "required" in override:
        required = bool(override.get("required"))

    default_value = metadata.get("default_val", None)
    if "default_value" in override:
        default_value = override.get("default_value")

    default_kind = classify_default(default_value, kind)
    default_kind = _override_default_kind(override.get("default_kind"), default_kind)

    if default_kind == DefaultKind.LITERAL:
        export_default = True
    else:
        export_default = False

    if "export_default" in override:
        export_default = bool(override.get("export_default"))

    # Bundled/generated catalogs are intentionally conservative, but older
    # catalog entries can still mark SST-internal extension-point defaults or
    # symbolic C/C++ expressions as literal. Treat those entries as non-runtime
    # defaults at export time so stale policy data cannot leak invalid SST JSON.
    if metadata_default_is_internal_type(default_value, kind):
        default_kind = DefaultKind.INTERNAL
        export_default = False

    if metadata_default_is_symbolic(default_value):
        default_kind = DefaultKind.SYMBOLIC
        export_default = False

    required_context = RequiredContext.UNKNOWN
    if required:
        required_context = RequiredContext.ALWAYS
    required_context = _override_required_context(
        override.get("required_context"),
        required_context,
    )

    missing_severity = MissingSeverity.SILENT
    if required and required_context in {RequiredContext.ALWAYS, RequiredContext.TOP_LEVEL_COMPONENT}:
        missing_severity = MissingSeverity.ERROR
    missing_severity = _override_missing_severity(
        override.get("missing_severity"),
        missing_severity,
    )

    validate_user_value = bool(override.get("validate_user_value", True))
    notes = str(override.get("notes", "") or "")

    return ParamPolicy(
        name=param_name,
        kind=kind,
        required=required,
        required_context=required_context,
        default_value=default_value,
        default_kind=default_kind,
        export_default=export_default,
        missing_severity=missing_severity,
        validate_user_value=validate_user_value,
        notes=notes,
    )


def resolve_param_kind(
    component_type: str,
    param_name: str,
    metadata: dict[str, Any] | None = None,
    *,
    node=None,
) -> ParamKind:
    """Return the resolved kind for a parameter."""

    return resolve_param_policy(component_type, param_name, metadata, node=node).kind


def normalize_param_value(
    component_type: str,
    param_name: str,
    value: Any,
    metadata: dict[str, Any] | None = None,
    *,
    node=None,
) -> Any:
    """Normalize one parameter value according to resolved SST policy."""

    if node is not None and not framework_version_for_node(node) and not (metadata or {}):
        return value

    policy = resolve_param_policy(component_type, param_name, metadata, node=node)

    if not policy.validate_user_value:
        return value

    return normalize_value(value, policy.kind)


def normalize_params(
    component_type: str,
    params: dict[str, Any],
    metadata_by_name: dict[str, dict[str, Any]] | None = None,
    *,
    node=None,
) -> dict[str, Any]:
    """Normalize a params dict according to resolved SST policy."""

    metadata_by_name = metadata_by_name or {}
    normalized: dict[str, Any] = {}

    for name, value in params.items():
        metadata = metadata_by_name.get(name, {})
        normalized[name] = normalize_param_value(
            component_type,
            name,
            value,
            metadata,
            node=node,
        )

    return normalized


def default_params_for_node(
    node,
    *,
    suppress_prefixed_slots: set[str] | None = None,
) -> dict[str, Any]:
    """Return safe literal defaults that should be made explicit in SST JSON."""

    suppress_prefixed_slots = suppress_prefixed_slots or set()
    component_type = component_type_for_node(node)

    if not component_type:
        return {}

    defaults: dict[str, Any] = {}
    metadata_by_name = parameter_metadata_for_node(node)
    version = framework_version_for_node(node)

    # Do not inject catalog-derived defaults into synthetic/unversioned nodes.
    # Unit tests and some legacy/editor-only objects may identify an SST
    # component type without carrying a target/catalog version or imported
    # database metadata. In that case user-entered params should pass through
    # unchanged instead of inheriting defaults from the newest bundled catalog.
    if not version and not metadata_by_name:
        return {}

    catalog_params = component_policy(version, component_type).get("params", {}) if version else {}

    if not isinstance(catalog_params, dict):
        catalog_params = {}

    names = set(metadata_by_name) | set(catalog_params)

    for name in sorted(names):
        if _is_suppressed_slot_param(name, suppress_prefixed_slots):
            continue

        metadata = metadata_by_name.get(name, {})
        policy = resolve_param_policy(component_type, name, metadata, node=node)

        if not policy.export_default:
            continue

        if policy.default_kind != DefaultKind.LITERAL:
            continue

        if policy.default_value in (None, ""):
            continue

        try:
            defaults[name] = normalize_param_value(
                component_type,
                name,
                policy.default_value,
                metadata,
                node=node,
            )
        except ValueError:
            # If SST metadata says a default is literal but it does not fit the
            # resolved type, leave it to SST rather than emitting invalid JSON.
            continue

    return defaults


def should_require_metadata_param_for_export(
    node,
    param_name: str,
    metadata: dict[str, Any],
    params: dict[str, Any],
    attached_slot_names: set[str] | None = None,
) -> bool:
    """Return true when a missing metadata-required parameter should block export."""

    attached_slot_names = attached_slot_names or set()

    if param_name in params:
        return False

    if _is_suppressed_slot_param(param_name, attached_slot_names):
        return False

    if node_is_subcomponent(node):
        # Attached subcomponents often have required metadata params that are
        # provided by the parent slot/attachment instead of as user params.
        return False

    component_type = component_type_for_node(node)
    policy = resolve_param_policy(component_type, param_name, metadata, node=node)

    return policy.missing_severity == MissingSeverity.ERROR
