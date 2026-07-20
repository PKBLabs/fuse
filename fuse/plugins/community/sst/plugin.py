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
"""Community SST framework plugin.

The SST plugin translates metadata imported from ``sst-info`` into FUSE palette
items, item details, compatibility checks, toolchain validation, and SST JSON
export support. Core code talks to this plugin through the public
``fuse.plugin_api`` contracts.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    ExportFormat,
    ExportResult,
    FrameworkTarget,
    ItemDetails,
    LinkCompatibilityResult,
    LinkEndpoint,
    PaletteItem,
    PropertyDefinition,
    SubcompConnectorDefinition,
)
from fuse.core.model.subcomponents import is_visual_subcomponent_connection_parameter
from fuse.core.persistence.database import get_connection, rows_to_dicts
from fuse.plugins.community.sst.initialize_db import (
    get_or_create_sst_framework_version,
    initialize_sst_schema,
)
from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_to_database
from fuse.plugins.community.sst.component_catalog import import_bundled_component_catalogs
from fuse.plugins.community.sst.policy.loader import (
    available_policy_catalog_versions,
    has_policy_catalog,
)
from fuse.plugins.community.sst.policy.bootstrap import ensure_sst_policy_catalogs
from fuse.plugins.community.sst.runtime_overlays import runtime_slots_for_component


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


# SST uses a few parameters as type selectors for attached SubComponents.
# These are not normal graph links; FUSE can keep them synchronized when the
# user attaches the corresponding child visually.
SST_SUBCOMP_SLOT_PARAMETER_OVERRIDES = {
    ("merlin.hr_router", "topology"): "topology",
    ("merlin.hr_router", "XbarArb"): "xbar_arb",
    ("firefly.hades", "virtNic"): "nicModule",
}

SST_PORT_COUNT_PARAMETER_CANDIDATES = (
    "num_ports",
    "numPorts",
    "numports",
    "port_count",
    "portCount",
    "num_links",
    "numLinks",
)


def sst_component_type_for_component(component) -> str:
    """Return the canonical SST element.component type for a component definition."""

    element = str(getattr(component, "element", "") or "").strip()
    name = str(getattr(component, "name", "") or "").strip()
    if element and name:
        return f"{element}.{name}"
    return name


def sst_component_type_for_node(node) -> str:
    """Return the canonical SST element.component type for a scene node."""

    return sst_component_type_for_component(getattr(node, "component", None))


def is_ember_engine_node(node) -> bool:
    return sst_component_type_for_node(node) == "ember.EmberEngine"


def is_ember_motif_node(node) -> bool:
    component = getattr(node, "component", None)
    return (
        sst_component_type_for_component(component).startswith("ember.")
        and bool(int(getattr(component, "is_subcomp", 0) or 0))
        and str(getattr(component, "iface", "") or "").strip() == EMBER_MOTIF_INTERFACE
    )


def nodes_by_id_for_scene(scene) -> dict[int, object]:
    return {
        int(getattr(node, "node_id", 0) or 0): node
        for node in scene.component_items()
    }


def property_definitions_by_name(plugin: "SSTPlugin", node) -> dict[str, PropertyDefinition]:
    """Return SST property definitions for a node, keyed by parameter name."""
    component = getattr(node, "component", None)
    if component is None:
        return {}

    try:
        details = plugin.load_item_details(
            getattr(component, "component_id", ""),
            target_id=getattr(component, "target_id", "") or None,
        )
    except Exception:
        return {}

    return {
        str(getattr(prop, "name", "") or ""): prop
        for prop in getattr(details, "properties", []) or []
        if str(getattr(prop, "name", "") or "")
    }


def case_insensitive_property_name(
    property_names: set[str],
    candidate: str,
) -> str:
    if candidate in property_names:
        return candidate

    lowered = candidate.lower()
    for name in property_names:
        if name.lower() == lowered:
            return name

    return ""


def sst_component_type_for_attachment_child(scene, attachment) -> str:
    child = nodes_by_id_for_scene(scene).get(int(getattr(attachment, "child_node_id", 0) or 0))
    return sst_component_type_for_node(child) if child is not None else ""


def is_ember_motif_attachment(scene, attachment) -> bool:
    """Return true for visual EmberEngine.motif -> EmberGenerator attachments."""

    if str(getattr(attachment, "slot_name", "") or "").strip() != EMBER_MOTIF_SLOT:
        return False

    metadata = dict(getattr(attachment, "plugin_metadata", {}) or {})
    if metadata.get("visual_attachment_kind") == EMBER_MOTIF_ATTACHMENT_KIND:
        return True

    nodes_by_id = {
        getattr(node, "node_id", None): node
        for node in scene.component_items()
    }
    parent = nodes_by_id.get(getattr(attachment, "parent_node_id", None))
    child = nodes_by_id.get(getattr(attachment, "child_node_id", None))
    return bool(parent is not None and child is not None and is_ember_engine_node(parent) and is_ember_motif_node(child))


def is_firefly_nic_simple_memory_attachment(scene, attachment) -> bool:
    """Return true for the FUSE-only firefly.nic SimpleMemory editor slot."""

    if str(getattr(attachment, "slot_name", "") or "").strip() != FIREFLY_NIC_SIMPLE_MEMORY_SLOT:
        return False

    nodes_by_id = nodes_by_id_for_scene(scene)
    parent = nodes_by_id.get(int(getattr(attachment, "parent_node_id", 0) or 0))
    child = nodes_by_id.get(int(getattr(attachment, "child_node_id", 0) or 0))

    return bool(
        parent is not None
        and child is not None
        and sst_component_type_for_node(parent) == "firefly.nic"
        and sst_component_type_for_node(child) == FIREFLY_NIC_SIMPLE_MEMORY_TYPE
    )


def sync_firefly_nic_simple_memory_params_for_attachment(scene, attachment) -> None:
    """Enable the firefly.nic anonymous SimpleMemory model for a logical attachment."""

    if not is_firefly_nic_simple_memory_attachment(scene, attachment):
        return

    parent = nodes_by_id_for_scene(scene).get(int(getattr(attachment, "parent_node_id", 0) or 0))
    if parent is None:
        return

    params = dict(getattr(parent, "parameters", {}) or {})
    params["useSimpleMemoryModel"] = "1"
    parent.parameters = params


def ordered_ember_motif_attachments_for_engine(scene, engine_node) -> list:
    """Return visual motif attachments for an EmberEngine in canvas order."""

    attachments = []
    for attachment in getattr(scene, "subcomp_attachments", []) or []:
        if getattr(attachment, "parent_node_id", None) != getattr(engine_node, "node_id", None):
            continue
        if is_ember_motif_attachment(scene, attachment):
            attachments.append(attachment)

    return sorted(
        attachments,
        key=lambda item: (int(getattr(item, "attachment_id", 0) or 0), str(getattr(item, "name", "") or "")),
    )


def non_empty_motif_user_params(node) -> dict:
    """Return motif-node parameters that should become EmberEngine motif args."""

    params = {}
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


def motif_entries_with_required_init_fini(entries: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
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


def derive_ember_motif_params_for_engine(scene, engine_node) -> dict:
    """Convert attached visual motif nodes into EmberEngine motif parameters."""

    nodes_by_id = {
        getattr(node, "node_id", None): node
        for node in scene.component_items()
    }
    motif_attachments = ordered_ember_motif_attachments_for_engine(scene, engine_node)
    if not motif_attachments:
        return {}

    motif_entries = []
    for attachment in motif_attachments:
        child = nodes_by_id.get(getattr(attachment, "child_node_id", None))
        if child is None:
            continue

        motif_type = sst_component_type_for_node(child)
        if not motif_type:
            continue

        motif_params = {
            param_name: param_value
            for param_name, param_value in non_empty_motif_user_params(child).items()
            if param_name != "name"
        }
        motif_entries.append((motif_type, motif_params))

    motif_entries = motif_entries_with_required_init_fini(motif_entries)
    derived = {"motif_count": str(len(motif_entries))}
    for index, (motif_type, motif_params) in enumerate(motif_entries):
        derived[f"motif{index}.name"] = motif_type
        for param_name, param_value in motif_params.items():
            derived[f"motif{index}.{param_name}"] = param_value

    return derived


def remove_generated_ember_motif_params(params: dict) -> dict:
    """Remove params owned by the visual Ember motif attachment abstraction."""

    cleaned = dict(params or {})
    for key in list(cleaned):
        name = str(key or "")
        if name == "motif_count":
            cleaned.pop(key, None)
            continue

        if not name.startswith("motif"):
            continue

        suffix = name[len("motif"):]
        index_text = suffix.split(".", 1)[0]
        if index_text.isdigit():
            cleaned.pop(key, None)

    return cleaned


@dataclass
class SSTPlugin:
    """FUSE plugin implementation for Structural Simulation Toolkit models."""

    plugin_id: str = "sst"
    name: str = "FUSE SST Plugin"

    def initialize_database(self, conn) -> None:
        """Create or migrate SST-specific metadata tables."""
        initialize_sst_schema(conn)

    def register_bundled_policy_targets(self) -> None:
        """Register bundled SST policy catalogs as selectable FUSE targets.

        This makes Project Settings show supported SST versions even before the
        user has configured local or remote SST tools.
        """

        versions = available_policy_catalog_versions()

        if not versions:
            print("SST plugin: no bundled SST policy catalogs were found.")
            return

        default_version = versions[-1]

        with get_connection() as conn:
            existing_default = conn.execute(
                """
                SELECT id
                FROM sst_framework_versions
                WHERE is_default = 1
                LIMIT 1
                """
            ).fetchone()

            for version in versions:
                get_or_create_sst_framework_version(
                    conn=conn,
                    version=version,
                    label=f"SST {version}",
                    source_kind="bundled-component-catalog",
                    source_path="",
                    command="bundled FUSE SST policy/component catalogs",
                    is_default=(
                        existing_default is None
                        and version == default_version
                    ),
                )

    def bootstrap_database(self) -> None:
        """Bootstrap SST plugin metadata that ships with FUSE.

        This intentionally does not run sst-info. Users configure and validate
        local/remote SST tools from Project Settings. Bundled component catalogs
        are imported into the database so the palette remains DB-driven.
        """

        self.register_bundled_policy_targets()
        import_bundled_component_catalogs()

        if shutil.which("sst-info") is None:
            print(
                "SST plugin: sst-info not found; using bundled SST component catalogs. "
                "Configure local or remote SST tools in Project Settings to refresh metadata."
            )

    def list_targets(self) -> list[FrameworkTarget]:
        """Return SST versions available in the local metadata database."""
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    fv.id,
                    fv.version,
                    fv.label,
                    fv.is_default,
                    fv.source_kind,
                    (
                        SELECT COUNT(*)
                        FROM sst_components c
                        WHERE c.framework_version_id = fv.id
                    ) AS component_count
                FROM sst_framework_versions fv
                ORDER BY fv.is_default DESC, fv.version DESC, fv.id DESC
            """).fetchall()

        targets = []
        supported_versions = set(available_policy_catalog_versions())

        for row in rows_to_dicts(rows):
            version = str(row["version"] or "")

            if int(row.get("component_count", 0) or 0) <= 0:
                continue

            targets.append(
                FrameworkTarget(
                    plugin_id=self.plugin_id,
                    target_id=str(row["id"]),
                    display_name=row["label"] or f"SST {version}",
                    framework_name="SST",
                    framework_version=version,
                    is_default=bool(row["is_default"]),
                )
            )

        return targets

    def _default_target_id(self) -> str | None:
        targets = self.list_targets()

        if not targets:
            return None

        for target in targets:
            if target.is_default:
                return target.target_id

        return targets[0].target_id

    def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]:
        """Return SST components/subcomponents for the selected target."""
        if target_id is None:
            target_id = self._default_target_id()

        if target_id is None:
            return []

        framework_version_id = int(target_id)

        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    c.id AS component_id,
                    c.framework_version_id,
                    fv.version AS framework_version,
                    fv.label AS target_label,
                    e.name AS element_name,
                    c.name AS component_name,
                    c.description,
                    c.category,
                    c.functionality,
                    c.iface,
                    c.is_subcomp,
                    c.icon_path
                FROM sst_components c
                JOIN sst_elements e ON c.parent_id = e.id
                JOIN sst_framework_versions fv ON c.framework_version_id = fv.id
                WHERE c.framework_version_id = ?
                  AND e.framework_version_id = ?
                ORDER BY e.name, c.is_subcomp, c.name
            """, (framework_version_id, framework_version_id)).fetchall()

        items = []

        for row in rows_to_dicts(rows):
            kind = "SubComponent" if row["is_subcomp"] else "Component"
            display_name = f'{row["element_name"]}.{row["component_name"]} ({kind})'

            items.append(
                PaletteItem(
                    plugin_id=self.plugin_id,
                    item_id=str(row["component_id"]),
                    display_name=display_name,
                    type_name=row["component_name"],
                    element_name=row["element_name"] or "",
                    category=row["category"] or "",
                    functionality=row["functionality"] or "",
                    description=row["description"] or "",
                    icon_path=row["icon_path"] or "",
                    raw_kind=kind,
                    target_id=str(row["framework_version_id"]),
                    target_label=row["target_label"] or f"SST {row['framework_version']}",
                    framework_version=row["framework_version"] or "",
                    iface=row["iface"] or "",
                )
            )

        return items

    def load_item_details(self, item_id: str, target_id: str | None = None) -> ItemDetails:
        """Load connectors, parameters, and statistics for one SST item."""
        component_id = int(item_id)
        params = [component_id]
        target_filter = ""

        if target_id:
            target_filter = " AND c.framework_version_id = ?"
            params.append(int(target_id))

        with get_connection() as conn:
            component = conn.execute(f"""
                SELECT
                    c.id AS component_id,
                    c.framework_version_id,
                    fv.version AS framework_version,
                    fv.label AS target_label,
                    e.name AS element_name,
                    c.name AS component_name,
                    c.description,
                    c.category,
                    c.functionality,
                    c.iface,
                    c.is_subcomp,
                    c.icon_path
                FROM sst_components c
                JOIN sst_elements e ON c.parent_id = e.id
                JOIN sst_framework_versions fv ON c.framework_version_id = fv.id
                WHERE c.id = ?
                {target_filter}
            """, params).fetchone()

            if component is None:
                raise KeyError(f"SST component {item_id!r} was not found for target {target_id!r}.")

            component_dict = dict(component)
            framework_version_id = int(component_dict["framework_version_id"])

            ports = conn.execute("""
                SELECT
                    name,
                    description,
                    iface,
                    is_variable,
                    base_name,
                    count_parameter,
                    default_count
                FROM sst_ports
                WHERE framework_version_id = ?
                  AND parent_id = ?
                ORDER BY name
            """, (framework_version_id, component_id)).fetchall()

            params_rows = conn.execute("""
                SELECT name, description, default_val, required
                FROM sst_parameters
                WHERE framework_version_id = ?
                  AND parent_id = ?
                  AND parent_type = 'sst_components'
                ORDER BY name
            """, (framework_version_id, component_id)).fetchall()

            slots = conn.execute("""
                SELECT name, description, iface
                FROM sst_subcomp_slots
                WHERE framework_version_id = ?
                  AND parent_id = ?
                ORDER BY name
            """, (framework_version_id, component_id)).fetchall()

        palette_item = PaletteItem(
            plugin_id=self.plugin_id,
            item_id=str(component_dict["component_id"]),
            display_name=f'{component_dict["element_name"]}.{component_dict["component_name"]}',
            type_name=component_dict["component_name"],
            element_name=component_dict["element_name"] or "",
            category=component_dict["category"] or "",
            functionality=component_dict["functionality"] or "",
            description=component_dict["description"] or "",
            icon_path=component_dict["icon_path"] or "",
            raw_kind="SubComponent" if component_dict["is_subcomp"] else "Component",
            target_id=str(component_dict["framework_version_id"]),
            target_label=component_dict["target_label"] or f"SST {component_dict['framework_version']}",
            framework_version=component_dict["framework_version"] or "",
            iface=component_dict["iface"] or "",
        )

        connectors = [
            ConnectorDefinition(
                name=row["name"],
                description=row["description"] or "",
                interface=row["iface"] or "",
                is_variable=bool(row.get("is_variable", 0)),
                base_name=row.get("base_name", "") or row["name"],
                count_parameter=row.get("count_parameter", "") or "",
                default_count=int(row.get("default_count", 1) or 1),
            )
            for row in rows_to_dicts(ports)
        ]

        subcomp_connectors = [
            SubcompConnectorDefinition(
                name=row["name"],
                role="slot",
                description=row["description"] or "",
                required_interface=row["iface"] or "",
                interface=row["iface"] or "",
            )
            for row in rows_to_dicts(slots)
        ]

        # Keep the DB/catalog rows as raw sst-info metadata, then layer in
        # version-specific plugin runtime slots that SST loads through code
        # paths such as loadUserSubComponent() but does not fully declare in
        # ELI/sst-info.  These are deliberately marked in the description so
        # the UI can distinguish overlay metadata from catalog metadata.
        existing_slot_names = {connector.name for connector in subcomp_connectors}
        component_type = f'{component_dict["element_name"]}.{component_dict["component_name"]}'
        for slot in runtime_slots_for_component(
            component_type,
            component_dict.get("framework_version") or "",
        ).values():
            if slot.name in existing_slot_names:
                continue
            default_hint = f" Default type: {slot.default_type}." if slot.default_type else ""
            description = (
                f"[Runtime overlay] {slot.description}"
                f"{default_hint}"
            ).strip()
            subcomp_connectors.append(
                SubcompConnectorDefinition(
                    name=slot.name,
                    role="slot",
                    description=description,
                    required_interface=slot.required_interface,
                    interface=slot.required_interface,
                )
            )

        if component_type == "ember.EmberEngine" and EMBER_MOTIF_SLOT not in existing_slot_names:
            subcomp_connectors.append(
                SubcompConnectorDefinition(
                    name=EMBER_MOTIF_SLOT,
                    role="slot",
                    description=(
                        "[Visual attachment] Attach one or more EmberGenerator motifs here. "
                        "The SST exporter converts these attachments into EmberEngine motif_count/motifN.name parameters."
                    ),
                    required_interface=EMBER_MOTIF_INTERFACE,
                    interface=EMBER_MOTIF_INTERFACE,
                    visual_only=True,
                    allow_multiple=True,
                    plugin_metadata={"visual_attachment_kind": EMBER_MOTIF_ATTACHMENT_KIND},
                )
            )

        if bool(component_dict["is_subcomp"]):
            subcomp_connectors.append(
                SubcompConnectorDefinition(
                    name="interface",
                    role="interface",
                    description=(
                        "SubComponent interface connector"
                        if component_dict.get("iface")
                        else "SubComponent interface connector (interface unspecified)"
                    ),
                    provided_interface=component_dict["iface"] or "",
                    interface=component_dict["iface"] or "",
                )
            )

        properties = []
        component_is_subcomponent = bool(component_dict["is_subcomp"])
        for row in rows_to_dicts(params_rows):
            property_definition = {
                "name": row["name"],
                "description": row["description"] or "",
                "default_val": row["default_val"] or "",
                "required": bool(row["required"]),
            }
            required = bool(row["required"])
            if is_visual_subcomponent_connection_parameter(
                property_definition,
                component_is_subcomponent=component_is_subcomponent,
            ):
                required = False

            properties.append(
                PropertyDefinition(
                    name=row["name"],
                    description=row["description"] or "",
                    default_value=row["default_val"] or "",
                    required=required,
                )
            )

        return ItemDetails(
            palette_item=palette_item,
            connectors=connectors,
            subcomp_connectors=subcomp_connectors,
            properties=properties,
        )

    def port_count_parameter_for_node(
        self,
        node,
        base_name: str,
        port_template: dict | None = None,
    ) -> str:
        """Return the SST parameter controlled by a variable port count."""
        template = dict(port_template or {})
        explicit = str(template.get("count_parameter", "") or "").strip()
        properties = property_definitions_by_name(self, node)
        property_names = set(properties)

        if explicit:
            return case_insensitive_property_name(property_names, explicit) or explicit

        for candidate in SST_PORT_COUNT_PARAMETER_CANDIDATES:
            name = case_insensitive_property_name(property_names, candidate)
            if name:
                return name

        return ""

    def on_variable_port_count_changed(
        self,
        scene,
        node,
        base_name: str,
        count: int,
        port_template: dict | None = None,
    ) -> None:
        """Core hook: keep SST variable-port count parameters synchronized."""
        if getattr(getattr(node, "component", None), "plugin_id", "") != self.plugin_id:
            return

        parameter_name = self.port_count_parameter_for_node(
            node,
            base_name,
            port_template or {},
        )
        if not parameter_name:
            return

        params = dict(getattr(node, "parameters", {}) or {})
        params[parameter_name] = str(int(count))
        node.parameters = params

    def subcomponent_parameter_for_attachment(self, scene, attachment) -> str:
        """Return the parent parameter that should mirror a child subcomponent type."""
        if getattr(attachment, "plugin_id", "") not in ("", self.plugin_id):
            return ""
        if dict(getattr(attachment, "plugin_metadata", {}) or {}).get("visual_only"):
            return ""

        nodes_by_id = nodes_by_id_for_scene(scene)
        parent = nodes_by_id.get(int(getattr(attachment, "parent_node_id", 0) or 0))
        child = nodes_by_id.get(int(getattr(attachment, "child_node_id", 0) or 0))
        if parent is None or child is None:
            return ""

        parent_type = sst_component_type_for_node(parent)
        slot_name = str(getattr(attachment, "slot_name", "") or "").strip()
        if not parent_type or not slot_name:
            return ""

        properties = property_definitions_by_name(self, parent)
        property_names = set(properties)

        override = SST_SUBCOMP_SLOT_PARAMETER_OVERRIDES.get((parent_type, slot_name), "")
        if override:
            return case_insensitive_property_name(property_names, override) or override

        candidates = [
            f"{slot_name}Module",
            f"{slot_name}_module",
            f"{slot_name}Type",
            f"{slot_name}_type",
            f"{slot_name}Class",
            f"{slot_name}_class",
        ]
        for candidate in candidates:
            name = case_insensitive_property_name(property_names, candidate)
            if name:
                return name

        exact = case_insensitive_property_name(property_names, slot_name)
        if exact:
            prop = properties.get(exact)
            description = str(getattr(prop, "description", "") or "").lower()
            default_value = str(getattr(prop, "default_value", "") or "").lower()
            combined = f"{description} {default_value}"
            if any(token in combined for token in ("subcomponent", "sub-component", "module", "type")):
                return exact

        return ""

    def sync_subcomponent_parameter_for_attachment(self, scene, attachment) -> None:
        """Set parent selector params such as topology or nicModule from attachments."""
        parameter_name = self.subcomponent_parameter_for_attachment(scene, attachment)
        if not parameter_name:
            return

        nodes_by_id = nodes_by_id_for_scene(scene)
        parent = nodes_by_id.get(int(getattr(attachment, "parent_node_id", 0) or 0))
        child = nodes_by_id.get(int(getattr(attachment, "child_node_id", 0) or 0))
        if parent is None or child is None:
            return

        child_type = sst_component_type_for_node(child)
        if not child_type:
            return

        params = dict(getattr(parent, "parameters", {}) or {})
        params[parameter_name] = child_type
        parent.parameters = params

    def clear_subcomponent_parameter_for_attachment(self, scene, attachment) -> None:
        """Clear an auto-synced selector param if the corresponding attachment is removed."""
        parameter_name = self.subcomponent_parameter_for_attachment(scene, attachment)
        if not parameter_name:
            return

        nodes_by_id = nodes_by_id_for_scene(scene)
        parent = nodes_by_id.get(int(getattr(attachment, "parent_node_id", 0) or 0))
        if parent is None:
            return

        slot_name = str(getattr(attachment, "slot_name", "") or "")
        replacement_type = ""
        for other in getattr(scene, "subcomp_attachments", []) or []:
            if other is attachment:
                continue
            if int(getattr(other, "parent_node_id", 0) or 0) != int(getattr(attachment, "parent_node_id", 0) or 0):
                continue
            if str(getattr(other, "slot_name", "") or "") != slot_name:
                continue
            replacement_type = sst_component_type_for_attachment_child(scene, other)
            if replacement_type:
                break

        removed_child_type = sst_component_type_for_attachment_child(scene, attachment)
        params = dict(getattr(parent, "parameters", {}) or {})
        current_value = str(params.get(parameter_name, "") or "")
        if replacement_type:
            params[parameter_name] = replacement_type
        elif not removed_child_type or current_value == removed_child_type:
            params.pop(parameter_name, None)
        else:
            return
        parent.parameters = params

    def sync_ember_motif_params_for_node(self, scene, engine_node) -> None:
        """Synchronize EmberEngine params from visual motif attachments."""

        if not is_ember_engine_node(engine_node):
            return

        params = remove_generated_ember_motif_params(dict(getattr(engine_node, "parameters", {}) or {}))
        params.update(derive_ember_motif_params_for_engine(scene, engine_node))
        engine_node.parameters = params

    def on_subcomponent_attachment_created(self, scene, attachment) -> None:
        """Core hook: update plugin-owned params after an attachment is made."""

        if is_ember_motif_attachment(scene, attachment):
            for node in scene.component_items():
                if getattr(node, "node_id", None) == getattr(attachment, "parent_node_id", None):
                    self.sync_ember_motif_params_for_node(scene, node)
                    return

        if is_firefly_nic_simple_memory_attachment(scene, attachment):
            sync_firefly_nic_simple_memory_params_for_attachment(scene, attachment)
            return

        self.sync_subcomponent_parameter_for_attachment(scene, attachment)

    def on_subcomponent_attachment_deleted(self, scene, attachment) -> None:
        """Core hook: update plugin-owned params after an attachment is deleted."""

        if is_ember_motif_attachment(scene, attachment):
            for node in scene.component_items():
                if getattr(node, "node_id", None) == getattr(attachment, "parent_node_id", None):
                    self.sync_ember_motif_params_for_node(scene, node)
                    return

        self.clear_subcomponent_parameter_for_attachment(scene, attachment)

    def check_link_compatibility(
            self,
            source: LinkEndpoint,
            target: LinkEndpoint,
    ) -> LinkCompatibilityResult:
        """
        Return compatibility for ordinary SST Link.connect() port links.

        SST Link.connect() connects named ports. Many normal component ports do not
        expose enough interface metadata in sst-info to prove semantic compatibility.
        Interface checking belongs to SubComponent Slot assignment, where SST
        provides explicit interface metadata.
        """
        return LinkCompatibilityResult()

    def check_subcomponent_slot_compatibility(
            self,
            slot_metadata: dict,
            subcomponent_metadata: dict,
    ) -> LinkCompatibilityResult:
        """
        Check SST SubComponent Slot assignment compatibility.

        This is where SST interface matching belongs. Ordinary SST Link.connect()
        port links should not use this rule.
        """
        slot_iface = (
                slot_metadata.get("required_interface", "")
                or slot_metadata.get("iface", "")
                or slot_metadata.get("interface", "")
                or ""
        ).strip()

        subcomponent_iface = (
                subcomponent_metadata.get("provided_interface", "")
                or subcomponent_metadata.get("iface", "")
                or subcomponent_metadata.get("interface", "")
                or ""
        ).strip()

        if not slot_iface or not subcomponent_iface:
            return LinkCompatibilityResult(
                can_create=True,
                severity="warning",
                title="Unknown SubComponent Interface",
                code="sst.subcomponent_slot_unknown_interface",
                visual_indicator="warning",
                message=(
                    "The interface type for at least one of these endpoints is unknown. "
                    "Compatibility cannot be determined!\n\n"
                    f"Slot interface: {slot_iface or '(unknown)'}\n"
                    f"SubComponent interface: {subcomponent_iface or '(unknown)'}\n\n"
                    "FUSE can create this SubComponent assignment, but the exported SST "
                    "model may not run correctly if the slot and SubComponent are not "
                    "actually compatible."
                ),
            )

        if slot_iface == subcomponent_iface:
            return LinkCompatibilityResult()

        return LinkCompatibilityResult(
            can_create=True,
            severity="warning",
            title="SST SubComponent Interface Mismatch",
            code="sst.subcomponent_slot_interface_mismatch",
            visual_indicator="warning",
            message=(
                "The selected SST SubComponent does not declare the exact "
                "interface required by this slot. SST interface names are not "
                "always standardized, so this may still be the correct "
                "assignment.\n\n"
                f"Slot requires: {slot_iface}\n"
                f"SubComponent provides: {subcomponent_iface}"
            ),
        )

    def export_formats(self) -> list[ExportFormat]:
        """Return SST export formats advertised to the core UI."""
        return [
            ExportFormat(
                format_id="sst.json",
                display_name="SST JSON",
                file_filter="SST JSON (*.json);;All Files (*)",
                default_suffix=".sst.json",
                description="Runnable SST JSON configuration generated from an SST-only FUSE model.",
            )
        ]

    def export_model(
        self,
        scene,
        output_path: str,
        format_id: str = "sst.json",
        *,
        plugin_settings=None,
    ) -> ExportResult:
        if format_id not in ("", "sst.json"):
            raise ValueError(f"Unsupported SST export format: {format_id}")

        from fuse.core.model.composite_flattening import flatten_scene_for_export
        from fuse.plugins.community.sst.export_json import export_sst_json, validate_sst_json_export

        output = Path(output_path)
        export_scene = flatten_scene_for_export(scene)
        report = validate_sst_json_export(export_scene)
        report_path = ""
        if report.warnings:
            report_path = str(output.with_suffix(".export-report.json"))

        export_sst_json(
            scene=export_scene,
            output_path=output,
            report_path=report_path or None,
        )

        warning_count = len(report.warnings)
        if warning_count:
            message = f"Exported SST JSON with {warning_count} warning(s)."
        else:
            message = "Exported SST JSON."

        return ExportResult(
            output_path=str(output),
            format_id="sst.json",
            message=message,
            report_path=report_path,
            warnings=list(report.warnings),
        )

    def validate_export(self, scene) -> list:
        from fuse.core.model.composite_flattening import flatten_scene_for_export
        from fuse.plugins.community.sst.export_json import validate_sst_json_export

        return validate_sst_json_export(flatten_scene_for_export(scene)).issues

    def validate_toolchain(self, plugin_settings) -> tuple[bool, str]:
        """Validate the configured local or remote SST toolchain."""
        expected_version = getattr(plugin_settings, "framework_version", "") or ""
        ok, message, _ = validate_sst_toolchain(
            toolchain=plugin_settings.toolchain,
            expected_version=expected_version,
        )
        return ok, message

    def import_metadata_for_toolchain(self, plugin_settings) -> None:
        """Import ``sst-info`` metadata using configured toolchain settings."""
        version = getattr(plugin_settings, "framework_version", "") or os.environ.get("FUSE_SST_VERSION", "15.0.0")
        label = getattr(plugin_settings, "target_label", "") or f"SST {version}"

        sync_sstinfo_to_database(
            version=version,
            label=label,
            is_default=True,
            toolchain=plugin_settings.toolchain,
        )


def register_plugin():
    """Return the plugin instance consumed by the FUSE plugin runtime."""
    return SSTPlugin()
