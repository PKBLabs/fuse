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
"""Graphics-scene model editor for FUSE diagrams.

``ModelScene`` is the canvas data owner for one open model. It manages
component nodes, port-to-port links, subcomponent attachments, selection state,
drag rerouting, compatibility feedback, and pending connection gestures. The
scene exposes editor-oriented operations that ``MainWindow`` and ``ModelView``
can call without needing to manipulate individual ``QGraphicsItem`` instances
directly.

The scene stores lightweight Python model records in parallel with Qt graphics
items. Persistence and exporters consume the model records, while the graphics
items provide interaction and rendering.
"""
from __future__ import annotations

import os
import re
from typing import Optional
from copy import deepcopy

from PySide6.QtCore import QPointF, QRectF, Qt, QThreadPool, QTimer
from PySide6.QtGui import QBrush, QKeySequence, QPen, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QMessageBox,
)

from fuse.core.model.models import ModelLink, ModelSubcompAttachment
from fuse.core.model.name_generation import (
    has_name_index_token,
    implicit_name_template,
    next_name_from_template,
    render_name_template,
    template_for_source_name,
    copy_start_index_for_name,
)
from fuse.core.model.composite_mini_model import (
    collect_mini_model_component_names,
    uniquify_mini_model_component_names,
)
from fuse.core.plugin_runtime.manager import get_plugin_by_id, load_all_palette_items
from fuse.core.diagnostics import active_operation, breadcrumb
from fuse.core.ui.async_link_routing import (
    LinkRouteRequest,
    LinkRouteResult,
    LinkRoutingWorker,
)
from fuse.core.ui.graphics_items import (
    ComponentNodeItem,
    ConnectionItem,
    PortItem,
    SubcompAttachmentItem,
    SubcompConnectorItem,
)
from fuse.plugin_api.interfaces import LinkCompatibilityResult, LinkEndpoint


class ModelScene(QGraphicsScene):
    """Interactive graphics scene for a single FUSE model document.

    The scene owns component-node items and connection items, coordinates
    connection gestures, and notifies the application when the model changes.
    It is also responsible for local canvas behaviors such as route updates,
    selection highlights, compatibility warnings, and deletion cascades.

    ``ModelScene`` should remain simulator-neutral. Framework-specific rules are
    queried through plugin compatibility helpers and are reflected in generic UI
    warnings/highlights rather than embedded directly in the scene.
    """
    def __init__(self):
        super().__init__()
        self.setSceneRect(0, 0, 2000, 1500)

        self.pending_source_port: Optional[PortItem] = None
        self.pending_subcomp_connector: Optional[SubcompConnectorItem] = None
        self.pending_line: Optional[QGraphicsLineItem] = None

        self.properties_panel: Optional["PropertiesPanel"] = None

        self.links: list[ModelLink] = []
        self.subcomp_attachments: list[ModelSubcompAttachment] = []

        self._next_node_id = 1
        self._next_link_id = 1
        self._next_subcomp_attachment_id = 1

        self._next_group_id = 1
        self.node_group_ids: dict[int, int] = {}
        self._moving_group = False

        self.snap_to_grid_enabled = False
        self.snap_grid_width = float(ComponentNodeItem.WIDTH)
        self.snap_grid_height = float(ComponentNodeItem.HEIGHT)
        self.snap_grid_origin = QPointF(0.0, 0.0)

        self.model_changed_callback = None
        self._model_change_batch_depth = 0
        self._batched_model_change_pending = False
        self.component_added_callback = None
        self.component_used_callback = None
        self.component_favorite_requested_callback = None
        self.selection_changed_callback = None

        self.active_plugin_id: str | None = None
        self.selected_connection: Optional[ConnectionItem] = None
        self.selected_subcomp_attachment: Optional[SubcompAttachmentItem] = None
        self.selected_component: Optional[ComponentNodeItem] = None
        self.suppress_mixed_endpoint_warning = False
        self.suppress_port_occupied_warning = False
        self.suppressed_compatibility_warnings: set[str] = set()

        # Link routing is relatively expensive. A component drag can generate
        # hundreds of ItemPositionHasChanged events per second. During drag we
        # use cheap preview routing, then do one full reroute on release.
        self._dragging_node = False
        self._drag_changed = False
        self._drag_start_positions: dict[int, tuple[float, float]] = {}
        self._reroute_timer = QTimer()
        self._reroute_timer.setSingleShot(True)
        self._reroute_timer.setInterval(250)
        self._reroute_timer.timeout.connect(self.reroute_all_links)

        # Keep large selections responsive while dragging. Updating every
        # connected link for every ItemPositionHasChanged event scales poorly as
        # diagrams grow, so drag preview routing is throttled to one small batch
        # per timer tick. Drop/release still performs the accurate reroute.
        self._drag_preview_timer = QTimer()
        self._drag_preview_timer.setSingleShot(True)
        self._drag_preview_timer.setInterval(33)
        self._drag_preview_timer.timeout.connect(self.update_drag_preview_links)
        self._drag_preview_node_ids: set[int] = set()
        self._drag_moved_node_ids: set[int] = set()
        self._drag_node_count = 0
        self._bulk_drag_preview_suppressed = False
        self._bulk_drag_preview_threshold = 12

        # Full orthogonal routing can be expensive on dense diagrams. Keep Qt
        # graphics mutation on the GUI thread, but compute numeric route points
        # in a thread-pool worker from a GUI-thread geometry snapshot.
        self._route_thread_pool = QThreadPool.globalInstance()
        self._route_generation = 0
        self._route_batch_id = 0
        self._active_route_workers: set[LinkRoutingWorker] = set()
        self._pending_route_batches: dict[int, dict] = {}
        self._routing_dirty = False
        self._routing_dirty_update_all_attachments = False
        self._routing_dirty_attachment_node_ids: set[int] = set()
        self._async_routing_enabled = not self._env_flag("FUSE_DISABLE_ASYNC_ROUTING")
        self._async_route_workers = self._read_async_route_workers()

        # During project load, build the scene first and avoid item-change
        # callbacks, incremental routing, and model-change snapshots until the
        # complete model has been restored.
        self._model_loading_depth = 0
        self._model_load_previous_index_method = None
        self._deleting_node_ids: set[int] = set()

        # Large-selection drags need a more aggressive fast path than ordinary
        # link-preview throttling.  When many nodes are selected, the cost is no
        # longer just routing: every mouse-move can invoke Python itemChange()
        # handlers, update the scene spatial index, repaint long link paths, and
        # recompute link hit-test shapes.  For those drags, temporarily suppress
        # geometry-change callbacks on the moving nodes and hide link visuals.
        # Release-time code restores everything and schedules one route batch.
        self._bulk_drag_fast_path_active = False
        self._bulk_drag_geometry_flag_state: dict[int, bool] = {}
        self._bulk_drag_movable_flag_state: dict[int, bool] = {}
        self._bulk_drag_hidden_item_state: dict[object, bool] = {}
        self._bulk_drag_hidden_node_state: dict[int, bool] = {}
        self._bulk_drag_anchor_node_id: int | None = None
        self._bulk_drag_proxy_item: QGraphicsRectItem | None = None
        self._bulk_drag_previous_index_method = None
        self._drag_nodes_by_id: dict[int, ComponentNodeItem] = {}
        self._deferred_drag_select_node: ComponentNodeItem | None = None
        self._highlighted_link_items: set[ConnectionItem] = set()
        self._highlighted_attachment_items: set[SubcompAttachmentItem] = set()
        self._suppress_link_hit_tests = False
        self._drag_model_change_pending = False
        breadcrumb(
            "model_scene.initialized",
            scene_id=id(self),
            async_routing_enabled=self._async_routing_enabled,
            async_route_workers=self._async_route_workers,
        )

    @staticmethod
    def _env_flag(name: str) -> bool:
        value = os.environ.get(name, "")
        return value.strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _read_async_route_workers() -> int:
        value = os.environ.get("FUSE_ASYNC_ROUTE_WORKERS", "1")
        try:
            return max(1, int(value))
        except ValueError:
            return 1

    def connection_items(self) -> list[ConnectionItem]:
        items = [item for item in self.items() if isinstance(item, ConnectionItem)]
        return sorted(items, key=lambda item: item.link.link_id)

    def subcomp_attachment_items(self) -> list[SubcompAttachmentItem]:
        items = [
            item
            for item in self.items()
            if isinstance(item, SubcompAttachmentItem)
        ]
        return sorted(items, key=lambda item: item.attachment.attachment_id)

    def component_items(self) -> list[ComponentNodeItem]:
        items = [item for item in self.items() if isinstance(item, ComponentNodeItem)]
        return sorted(items, key=lambda item: item.node_id)

    def _diagnostic_component_type(self, node: ComponentNodeItem) -> str:
        component = getattr(node, "component", None)
        element = getattr(component, "element", "") or ""
        name = getattr(component, "name", "") or ""
        return f"{element}.{name}".strip(".")

    def _diagnostic_node_snapshot(self, node: ComponentNodeItem) -> dict:
        return {
            "node_id": int(getattr(node, "node_id", 0) or 0),
            "instance_name": getattr(node, "instance_name", ""),
            "component_type": self._diagnostic_component_type(node),
            "plugin_id": getattr(getattr(node, "component", None), "plugin_id", ""),
            "is_subcomp": bool(int(getattr(getattr(node, "component", None), "is_subcomp", 0) or 0)),
            "position": {"x": node.pos().x(), "y": node.pos().y()},
            "ports": [getattr(port, "name", "") for port in getattr(node, "ports", [])],
            "connectors": [getattr(connector, "name", "") for connector in getattr(node, "subcomp_connectors", [])],
        }

    def _diagnostic_link_snapshot(self, connection: ConnectionItem) -> dict:
        link = getattr(connection, "link", None)
        return {
            "link_id": int(getattr(link, "link_id", 0) or 0),
            "name": getattr(link, "name", ""),
            "source": f"{getattr(link, 'source_component_name', '')}.{getattr(link, 'source_port', '')}",
            "target": f"{getattr(link, 'target_component_name', '')}.{getattr(link, 'target_port', '')}",
            "plugin_id": getattr(link, "plugin_id", ""),
        }

    def _diagnostic_attachment_snapshot(self, attachment_item: SubcompAttachmentItem) -> dict:
        attachment = getattr(attachment_item, "attachment", None)
        return {
            "attachment_id": int(getattr(attachment, "attachment_id", 0) or 0),
            "name": getattr(attachment, "name", ""),
            "parent": f"{getattr(attachment, 'parent_component_name', '')}.{getattr(attachment, 'slot_name', '')}",
            "child": getattr(attachment, "child_component_name", ""),
            "plugin_id": getattr(attachment, "plugin_id", ""),
        }

    def diagnostic_snapshot(self) -> dict:
        """Return a crash-safe summary of the scene and current selection."""

        try:
            selected_nodes = [self._diagnostic_node_snapshot(node) for node in self.selected_component_nodes(expand_groups=False)]
        except Exception as exc:
            selected_nodes = [{"error": f"{type(exc).__name__}: {exc}"}]

        try:
            selected_items = [type(item).__name__ for item in self.selectedItems()]
        except Exception as exc:
            selected_items = [f"error: {type(exc).__name__}: {exc}"]

        selected_connection = None
        if self.selected_connection is not None:
            try:
                selected_connection = self._diagnostic_link_snapshot(self.selected_connection)
            except Exception as exc:
                selected_connection = {"error": f"{type(exc).__name__}: {exc}"}

        selected_attachment = None
        if self.selected_subcomp_attachment is not None:
            try:
                selected_attachment = self._diagnostic_attachment_snapshot(self.selected_subcomp_attachment)
            except Exception as exc:
                selected_attachment = {"error": f"{type(exc).__name__}: {exc}"}

        return {
            "scene_id": id(self),
            "item_count": len(self.items()),
            "component_count": len(self.component_items()),
            "link_count": len(self.links),
            "attachment_count": len(self.subcomp_attachments),
            "model_loading_depth": getattr(self, "_model_loading_depth", 0),
            "model_change_batch_depth": getattr(self, "_model_change_batch_depth", 0),
            "selected_items": selected_items,
            "selected_nodes": selected_nodes,
            "selected_connection": selected_connection,
            "selected_subcomp_attachment": selected_attachment,
            "pending_source_port": getattr(getattr(self, "pending_source_port", None), "name", ""),
            "pending_subcomp_connector": getattr(getattr(self, "pending_subcomp_connector", None), "name", ""),
            "highlighted_links": len(getattr(self, "_highlighted_link_items", [])),
            "highlighted_attachments": len(getattr(self, "_highlighted_attachment_items", [])),
        }

    def clear_model(self):
        breadcrumb("model_scene.clear_model.start", snapshot=self.diagnostic_snapshot())
        self.cancel_pending_connection()
        self.cancel_pending_subcomp_attachment()
        self.invalidate_pending_link_routes(reason="clear_model")
        self.clear_deferred_link_routing()
        self.restore_bulk_drag_fast_path()
        self._reroute_timer.stop()
        self._drag_preview_timer.stop()
        self.clear()
        self._highlighted_link_items.clear()
        self._highlighted_attachment_items.clear()
        self._suppress_link_hit_tests = False
        self.links = []
        self.subcomp_attachments = []
        self._next_link_id = 1
        self._next_subcomp_attachment_id = 1
        self.suppressed_compatibility_warnings = set()
        self._next_group_id = 1
        self.node_group_ids = {}
        self._next_node_id = 1
        self.notify_model_changed()
        breadcrumb("model_scene.clear_model.end", snapshot=self.diagnostic_snapshot())

    def begin_model_load(self) -> None:
        """Enter a project-load batch.

        Qt graphics items are still created on the GUI thread, but their
        position-change handlers should not trigger routing/history work until
        all nodes, links, and subcomponent attachments have been restored.

        Loading many items is much faster when QGraphicsScene does not maintain
        its spatial index after every addItem()/setPos(). Restore the previous
        indexing policy once the bulk load is complete.
        """
        breadcrumb("model_scene.begin_model_load", depth=self._model_loading_depth, snapshot=self.diagnostic_snapshot())
        self._model_loading_depth += 1
        self.begin_model_change_batch()
        if self._model_loading_depth == 1:
            try:
                self._model_load_previous_index_method = self.itemIndexMethod()
                self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
            except Exception:
                self._model_load_previous_index_method = None
        self.invalidate_pending_link_routes(reason="begin_model_load")
        self.clear_deferred_link_routing()
        self._reroute_timer.stop()
        self._drag_preview_timer.stop()

    def end_model_load(self, *, emit_model_changed: bool = False) -> None:
        """Leave a project-load batch.

        By default, project open/undo paths perform their own explicit outline
        and history reset after the model is restored. Emitting the normal
        model_changed callback here would immediately walk the fresh scene to
        build an undo snapshot, then the caller would do the same work again.
        """
        breadcrumb(
            "model_scene.end_model_load.start",
            depth=self._model_loading_depth,
            emit_model_changed=emit_model_changed,
            snapshot=self.diagnostic_snapshot(),
        )
        if self._model_loading_depth > 0:
            self._model_loading_depth -= 1

        if self._model_loading_depth == 0:
            # Port connection-state changes intentionally skip connector
            # visibility relayouts while a project is being restored. Do one
            # consolidated refresh now so connected hidden/deprecated SST
            # connectors are revealed without paying a full node relayout for
            # every restored link.
            self.refresh_all_connector_visibility()

            previous_index_method = self._model_load_previous_index_method
            self._model_load_previous_index_method = None
            if previous_index_method is not None:
                try:
                    self.setItemIndexMethod(previous_index_method)
                except Exception:
                    pass

            self.mark_link_routing_dirty(
                update_all_attachments=True,
                reason="end_model_load",
            )

        self.end_model_change_batch(emit_changed=emit_model_changed)
        breadcrumb("model_scene.end_model_load.end", depth=self._model_loading_depth, snapshot=self.diagnostic_snapshot())

    def refresh_all_connector_visibility(self) -> None:
        """Refresh guided connector visibility for all nodes in one pass."""
        for node in self.component_items():
            if hasattr(node, "apply_port_visibility"):
                node.apply_port_visibility()
            if hasattr(node, "apply_subcomp_connector_visibility"):
                node.apply_subcomp_connector_visibility()

    def clear_deferred_link_routing(self) -> None:
        """Clear coalesced routing requests that have not started yet."""
        self._routing_dirty = False
        self._routing_dirty_update_all_attachments = False
        self._routing_dirty_attachment_node_ids.clear()

    def invalidate_pending_link_routes(self, *, reason: str = "scene_mutation") -> None:
        """Drop stale asynchronous route batches.

        Worker threads cannot be forcibly stopped, but bumping the generation
        makes their eventual results no-ops. Clearing the bookkeeping prevents
        old workers from keeping scene state alive after a model clear/load.
        """
        pending_count = len(self._pending_route_batches)
        active_count = len(self._active_route_workers)
        self._route_generation += 1
        self._pending_route_batches.clear()
        self._active_route_workers.clear()
        breadcrumb(
            "async_router.batch.cancel",
            generation=self._route_generation,
            pending_count=pending_count,
            active_count=active_count,
            reason=reason,
        )

    def routing_is_suppressed(self) -> bool:
        """Return whether route batches should be coalesced for later."""
        return self._model_loading_depth > 0 or self._model_change_batch_depth > 0

    def mark_link_routing_dirty(
        self,
        *,
        connections: list[ConnectionItem] | None = None,
        update_all_attachments: bool = False,
        attachment_nodes: list["ComponentNodeItem"] | None = None,
        reason: str = "suppressed",
    ) -> None:
        """Coalesce suppressed route requests into one later full refresh."""
        self._routing_dirty = True
        self._routing_dirty_update_all_attachments = (
            self._routing_dirty_update_all_attachments
            or bool(update_all_attachments)
        )
        for node in attachment_nodes or []:
            node_id = int(getattr(node, "node_id", 0) or 0)
            if node_id > 0:
                self._routing_dirty_attachment_node_ids.add(node_id)

        breadcrumb(
            "model_scene.routing_suppressed",
            generation=self._route_generation,
            link_count=len(connections or []),
            update_all_attachments=bool(update_all_attachments),
            attachment_node_count=len(attachment_nodes or []),
            model_loading_depth=self._model_loading_depth,
            model_change_batch_depth=self._model_change_batch_depth,
            reason=reason,
        )
        breadcrumb(
            "model_scene.routing_dirty",
            generation=self._route_generation,
            dirty=self._routing_dirty,
            update_all_attachments=self._routing_dirty_update_all_attachments,
            attachment_node_count=len(self._routing_dirty_attachment_node_ids),
            reason=reason,
        )

    def flush_deferred_link_routing(self, *, reason: str = "batch_end") -> None:
        """Start one consolidated route batch after a load/change batch ends."""
        if not self._routing_dirty or self.routing_is_suppressed():
            return

        self._routing_dirty = False
        self._routing_dirty_update_all_attachments = False
        self._routing_dirty_attachment_node_ids.clear()

        connections = self.connection_items()
        breadcrumb(
            "model_scene.routing_flush",
            generation=self._route_generation,
            link_count=len(connections),
            attachment_count=len(self.subcomp_attachment_items()),
            reason=reason,
        )
        self.schedule_async_link_routing(
            connections,
            update_all_attachments=True,
        )

    def next_component_node_id(self) -> int:
        """Return the next component id for this scene.

        FUSE can have multiple ModelScene instances alive at once: the main model
        scene plus composite-template and composite-instance editor scenes. Node
        ids are only meaningful inside one scene/project fragment, so allocation
        must be scene-local. A process-global ComponentNodeItem counter lets a
        nested composite editor reset or advance the main scene's ids, which can
        make copy/paste create duplicate component ids.
        """
        used_ids = {
            int(getattr(node, "node_id", 0))
            for node in self.component_items()
            if int(getattr(node, "node_id", 0)) > 0
        }
        candidate = max(1, int(getattr(self, "_next_node_id", 1) or 1))
        while candidate in used_ids:
            candidate += 1
        self._next_node_id = candidate + 1
        return candidate

    def set_snap_grid_size(self, width: float, height: float) -> None:
        self.snap_grid_width = max(1.0, float(width))
        self.snap_grid_height = max(1.0, float(height))

    def set_snap_to_grid(self, enabled: bool) -> None:
        self.snap_to_grid_enabled = bool(enabled)

    def snap_position_to_grid(self, position: QPointF) -> QPointF:
        width = max(1.0, float(getattr(self, "snap_grid_width", ComponentNodeItem.WIDTH)))
        height = max(1.0, float(getattr(self, "snap_grid_height", ComponentNodeItem.HEIGHT)))
        origin = getattr(self, "snap_grid_origin", QPointF(0.0, 0.0))

        x_units = (position.x() - origin.x()) / width
        y_units = (position.y() - origin.y()) / height
        x_index = int(x_units + 0.5) if x_units >= 0 else int(x_units - 0.5)
        y_index = int(y_units + 0.5) if y_units >= 0 else int(y_units - 0.5)

        return QPointF(
            origin.x() + x_index * width,
            origin.y() + y_index * height,
        )

    def notify_model_changed(self):
        if self._model_change_batch_depth > 0:
            self._batched_model_change_pending = True
            return

        if self.model_changed_callback is not None:
            self.model_changed_callback()

    def request_deferred_model_changed(self) -> None:
        """Emit the model-changed callback after the current UI event returns.

        Drag release should make the canvas responsive before history/sidebar
        bookkeeping runs. Coalesce repeated release-time requests into one
        callback.
        """
        if self._drag_model_change_pending:
            return

        self._drag_model_change_pending = True
        QTimer.singleShot(0, self._emit_deferred_model_changed)

    def _emit_deferred_model_changed(self) -> None:
        if not self._drag_model_change_pending:
            return

        self._drag_model_change_pending = False
        self.notify_model_changed()

    def begin_model_change_batch(self) -> None:
        self._model_change_batch_depth += 1

    def end_model_change_batch(self, *, emit_changed: bool = True) -> None:
        if self._model_change_batch_depth <= 0:
            return

        self._model_change_batch_depth -= 1
        if self._model_change_batch_depth == 0 and self._batched_model_change_pending:
            self._batched_model_change_pending = False
            if emit_changed:
                self.notify_model_changed()

        if self._model_change_batch_depth == 0:
            self.flush_deferred_link_routing(reason="model_change_batch_end")

    def notify_component_added(self, node: ComponentNodeItem):
        if self._model_change_batch_depth > 0:
            self.notify_model_changed()
            return

        if self.component_added_callback is not None:
            self.component_added_callback(node)
        self.notify_model_changed()

    def existing_component_names(self) -> set[str]:
        return {node.instance_name for node in self.component_items()}

    def existing_component_and_composite_internal_names(
        self,
        exclude_nodes: set[int] | None = None,
    ) -> set[str]:
        """Return names currently used by top-level and composite-internal nodes."""
        excluded = set(exclude_nodes or set())
        names: set[str] = set()

        for node in self.component_items():
            if int(getattr(node, "node_id", 0)) in excluded:
                continue
            instance_name = str(getattr(node, "instance_name", "") or "")
            if instance_name:
                names.add(instance_name)

            mini_model = getattr(node, "composite_instance_model", {}) or {}
            names.update(collect_mini_model_component_names(mini_model))

        return names

    def allocate_component_name_from_template(
        self,
        template: str,
        used_names: set[str] | None = None,
        *,
        start_index: int = 0,
    ) -> tuple[str, str]:
        """Allocate a unique component name from an explicit/implicit template."""
        used = set(self.existing_component_names() if used_names is None else used_names)
        name, _index = next_name_from_template(
            template,
            used,
            start_index=start_index,
        )
        return name, template

    def allocate_component_name_from_base(
        self,
        base_name: str,
        used_names: set[str] | None = None,
        *,
        start_index: int = 0,
    ) -> tuple[str, str]:
        """Allocate a unique component name from a raw component/template name."""
        base = (base_name or "Component").strip() or "Component"
        template = base if has_name_index_token(base) else implicit_name_template(base)
        return self.allocate_component_name_from_template(
            template,
            used_names,
            start_index=start_index,
        )

    def generate_unique_component_name(self, component) -> str:
        name, _template = self.allocate_component_name_from_base(component.name or "Component")
        return name

    def generate_unique_name_from_base(self, base_name: str, used_names: set[str] | None = None) -> str:
        name, _template = self.allocate_component_name_from_base(
            base_name,
            used_names,
            start_index=0,
        )
        return name

    def preview_component_instance_name(
        self,
        node: ComponentNodeItem | None,
        requested_name: str,
    ) -> tuple[str, str]:
        """Return the effective name/template for a user name edit."""
        requested = (requested_name or "Component").strip() or "Component"
        used = self.existing_component_names()
        if node is not None:
            used.discard(str(getattr(node, "instance_name", "") or ""))

        if has_name_index_token(requested):
            template = requested
            name, _index = next_name_from_template(template, used, start_index=0)
            return name, template

        return requested, template_for_source_name(requested)

    def rename_component_node(self, node: ComponentNodeItem, requested_name: str) -> str:
        """Rename a node, resolving optional ``%d`` name templates.

        A user-entered template such as ``cpu%d`` is rendered immediately to the
        index-zero visible name (``cpu0``) while the unrendered template is stored
        on the node for future copies. Property widgets may later commit the
        already-rendered text again while focus changes or the panel refreshes.
        Treat that exact no-op as a no-op so the preserved ``cpu%d`` template is
        not replaced by an inferred ``cpu0_%d`` template.
        """
        requested = (requested_name or "Component").strip() or "Component"
        current_name = str(getattr(node, "instance_name", "") or "")
        current_template = str(getattr(node, "instance_name_template", "") or "")
        if requested == current_name and current_template:
            return current_name

        new_name, template = self.preview_component_instance_name(node, requested)
        if new_name == current_name and template == current_template:
            return current_name
        node.set_instance_name(new_name, name_template=template)
        self.notify_model_changed()
        return new_name

    def existing_link_names(self) -> set[str]:
        return {link.name for link in self.links}

    def generate_unique_link_name_from_base(self, base_name: str) -> str:
        base = (base_name or "link").strip() or "link"
        used = self.existing_link_names()

        if base not in used:
            return base

        index = 1
        while f"{base}_{index}" in used:
            index += 1

        return f"{base}_{index}"

    def selected_component_nodes(self, expand_groups: bool = True) -> list[ComponentNodeItem]:
        selected = [
            item
            for item in self.selectedItems()
            if isinstance(item, ComponentNodeItem)
        ]

        if self.selected_component is not None and self.selected_component not in selected:
            selected.append(self.selected_component)

        if not expand_groups:
            return sorted(set(selected), key=lambda node: node.node_id)

        selected_ids = {node.node_id for node in selected}
        group_ids = {
            self.node_group_ids[node_id]
            for node_id in selected_ids
            if node_id in self.node_group_ids
        }

        if group_ids:
            for node in self.component_items():
                if self.node_group_ids.get(node.node_id) in group_ids:
                    selected_ids.add(node.node_id)

        return [
            node
            for node in self.component_items()
            if node.node_id in selected_ids
        ]

    def copy_selection_to_clipboard(self) -> bool:
        nodes = self.selected_component_nodes(expand_groups=True)
        if not nodes:
            return False

        node_ids = {node.node_id for node in nodes}
        node_payloads = []
        for node in nodes:
            node_payloads.append(
                {
                    "old_node_id": node.node_id,
                    "component": deepcopy(node.component),
                    "instance_name": node.instance_name,
                    "instance_name_template": getattr(node, "instance_name_template", ""),
                    "parameters": deepcopy(getattr(node, "parameters", {}) or {}),
                    "variable_port_counts": deepcopy(getattr(node, "variable_port_counts", {}) or {}),
                    "icon_path": getattr(node, "icon_path", ""),
                    "composite_instance_model": deepcopy(getattr(node, "composite_instance_model", {}) or {}),
                    "composite_port_mappings": deepcopy(getattr(node, "composite_port_mappings", []) or []),
                    "pos": {"x": node.pos().x(), "y": node.pos().y()},
                    "group_id": self.node_group_ids.get(node.node_id),
                }
            )

        link_payloads = []
        for connection in self.connection_items():
            link = connection.link
            if link.source_node_id in node_ids and link.target_node_id in node_ids:
                link_payloads.append({"link": deepcopy(link)})

        attachment_payloads = []
        for item in self.subcomp_attachment_items():
            attachment = item.attachment
            if attachment.parent_node_id in node_ids and attachment.child_node_id in node_ids:
                attachment_payloads.append(
                    {
                        "attachment": deepcopy(attachment),
                        "target_connector_name": getattr(item.target_connector, "name", ""),
                    }
                )

        ModelScene._entity_clipboard = {
            "nodes": node_payloads,
            "links": link_payloads,
            "subcomp_attachments": attachment_payloads,
        }
        return True

    def paste_clipboard(self, scene_pos: QPointF | None = None) -> list[ComponentNodeItem]:
        payload = getattr(ModelScene, "_entity_clipboard", None)
        if not payload or not payload.get("nodes"):
            return []

        nodes_payload = payload.get("nodes", [])
        if scene_pos is None:
            scene_pos = QPointF(40.0, 40.0)

        min_x = min(float(item["pos"]["x"]) for item in nodes_payload)
        min_y = min(float(item["pos"]["y"]) for item in nodes_payload)

        used_names = self.existing_component_and_composite_internal_names()
        old_to_new: dict[int, ComponentNodeItem] = {}
        old_group_to_new: dict[int, int] = {}

        self.begin_model_change_batch()
        try:
            self.clearSelection()

            for item in nodes_payload:
                component = deepcopy(item["component"])
                source_name = str(item.get("instance_name") or component.name or "Component")
                source_template = str(item.get("instance_name_template") or "")
                if not source_template:
                    source_template = template_for_source_name(source_name)
                start_index = copy_start_index_for_name(source_name, source_template)
                new_name, new_template = self.allocate_component_name_from_template(
                    source_template,
                    used_names,
                    start_index=start_index,
                )
                used_names.add(new_name)

                offset_x = float(item["pos"]["x"]) - min_x
                offset_y = float(item["pos"]["y"]) - min_y
                node = self.create_component_node(
                    component,
                    QPointF(scene_pos.x() + offset_x, scene_pos.y() + offset_y),
                    instance_name=new_name,
                    instance_name_template=new_template,
                    notify=False,
                )
                node.parameters = deepcopy(item.get("parameters", {}) or {})
                node.variable_port_counts = deepcopy(item.get("variable_port_counts", {}) or {})
                node.composite_instance_model = deepcopy(item.get("composite_instance_model", {}) or {})
                node.composite_port_mappings = deepcopy(item.get("composite_port_mappings", []) or [])
                if int(getattr(node.component, "is_composite", 0) or 0):
                    self.uniquify_composite_instance_node(node, used_names)
                if item.get("icon_path") and hasattr(node, "set_icon_path"):
                    node.set_icon_path(str(item.get("icon_path") or ""))
                if hasattr(node, "sync_ports_to_templates"):
                    node.sync_ports_to_templates()
                if hasattr(node, "sync_composite_ports_from_mappings"):
                    node.sync_composite_ports_from_mappings()

                old_to_new[int(item["old_node_id"])] = node
                old_group_id = item.get("group_id")
                if old_group_id is not None:
                    old_group_id = int(old_group_id)
                    if old_group_id not in old_group_to_new:
                        old_group_to_new[old_group_id] = self._next_group_id
                        self._next_group_id += 1
                    self.node_group_ids[node.node_id] = old_group_to_new[old_group_id]

                node.setSelected(True)

            for item in payload.get("links", []):
                old_link = item.get("link")
                source_node = old_to_new.get(int(old_link.source_node_id))
                target_node = old_to_new.get(int(old_link.target_node_id))
                if source_node is None or target_node is None:
                    continue

                source_port = self.find_port(source_node.node_id, old_link.source_port)
                target_port = self.find_port(target_node.node_id, old_link.target_port)
                if source_port is None or target_port is None:
                    continue

                link = deepcopy(old_link)
                link.link_id = self._next_link_id
                self._next_link_id += 1
                link.name = self.generate_unique_link_name_from_base(link.name)
                link.source_node_id = source_node.node_id
                link.source_component_name = source_node.instance_name
                link.target_node_id = target_node.node_id
                link.target_component_name = target_node.instance_name

                self.links.append(link)
                connection = ConnectionItem(link, source_port, target_port)
                self.addItem(connection)

            for item in payload.get("subcomp_attachments", []):
                old_attachment = item.get("attachment")
                parent_node = old_to_new.get(int(old_attachment.parent_node_id))
                child_node = old_to_new.get(int(old_attachment.child_node_id))
                if parent_node is None or child_node is None:
                    continue

                slot_connector = self.find_subcomp_connector(
                    parent_node.node_id,
                    old_attachment.slot_name,
                    role="slot",
                )
                interface_connector = self.find_subcomp_connector(
                    child_node.node_id,
                    str(item.get("target_connector_name") or ""),
                    role="interface",
                )
                if slot_connector is None:
                    continue
                if interface_connector is None:
                    connectors = [
                        connector
                        for connector in getattr(child_node, "subcomp_connectors", [])
                        if getattr(connector, "role", "") == "interface"
                    ]
                    interface_connector = connectors[0] if connectors else None
                if interface_connector is None:
                    continue

                attachment = deepcopy(old_attachment)
                attachment.attachment_id = self._next_subcomp_attachment_id
                self._next_subcomp_attachment_id += 1
                attachment.parent_node_id = parent_node.node_id
                attachment.parent_component_name = parent_node.instance_name
                attachment.child_node_id = child_node.node_id
                attachment.child_component_name = child_node.instance_name

                self.subcomp_attachments.append(attachment)
                attachment_item = SubcompAttachmentItem(attachment, slot_connector, interface_connector)
                self.addItem(attachment_item)

            self.reroute_all_links()
            self.notify_model_changed()
        finally:
            self.end_model_change_batch()

        return list(old_to_new.values())

    def group_selection(self) -> bool:
        nodes = self.selected_component_nodes(expand_groups=False)
        if len(nodes) < 2:
            return False

        group_id = self._next_group_id
        self._next_group_id += 1

        for node in nodes:
            self.node_group_ids[node.node_id] = group_id

        self.notify_model_changed()
        return True

    def ungroup_selection(self) -> bool:
        nodes = self.selected_component_nodes(expand_groups=True)
        if not nodes:
            return False

        group_ids = {
            self.node_group_ids[node.node_id]
            for node in nodes
            if node.node_id in self.node_group_ids
        }
        if not group_ids:
            return False

        self.node_group_ids = {
            node_id: group_id
            for node_id, group_id in self.node_group_ids.items()
            if group_id not in group_ids
        }
        self.notify_model_changed()
        return True

    def group_members_for_node(self, node: ComponentNodeItem) -> list[ComponentNodeItem]:
        group_id = self.node_group_ids.get(node.node_id)
        if group_id is None:
            return []
        return [
            candidate
            for candidate in self.component_items()
            if candidate is not node and self.node_group_ids.get(candidate.node_id) == group_id
        ]

    def apply_group_drag(self, node: ComponentNodeItem) -> None:
        if self._moving_group or not self._dragging_node:
            return

        members = self.group_members_for_node(node)
        if not members:
            return

        start = self._drag_start_positions.get(node.node_id)
        if start is None:
            return

        dx = node.pos().x() - start[0]
        dy = node.pos().y() - start[1]
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return

        self._moving_group = True
        try:
            for member in members:
                member_start = self._drag_start_positions.get(member.node_id)
                if member_start is None:
                    continue
                member.setPos(member_start[0] + dx, member_start[1] + dy)
        finally:
            self._moving_group = False

    def create_component_node(
        self,
        component,
        scene_pos,
        instance_name: str | None = None,
        instance_name_template: str | None = None,
        *,
        notify: bool = True,
    ):
        if self.snap_to_grid_enabled:
            scene_pos = self.snap_position_to_grid(scene_pos)

        if instance_name is None:
            instance_name, instance_name_template = self.allocate_component_name_from_base(
                component.name or "Component",
            )
        else:
            requested_name = str(instance_name)
            if instance_name_template is None:
                if has_name_index_token(requested_name):
                    instance_name, instance_name_template = self.allocate_component_name_from_base(
                        requested_name,
                    )
                else:
                    instance_name_template = template_for_source_name(requested_name)

        node = ComponentNodeItem(
            component,
            node_id=self.next_component_node_id(),
            instance_name=instance_name,
            instance_name_template=instance_name_template,
        )
        node.setPos(scene_pos)
        self.addItem(node)

        if int(getattr(component, "is_composite", 0) or 0):
            self.populate_composite_instance_node_from_template(node)

        if notify:
            if self.component_used_callback is not None:
                self.component_used_callback(component)

            self.notify_component_added(node)
        return node

    def populate_composite_instance_node_from_template(self, node: ComponentNodeItem) -> None:
        """Load a placed composite's mini-model from its reusable definition."""
        try:
            from fuse.core.persistence.composite_components import get_composite_component_definition
        except Exception:
            return

        composite_id = (
            getattr(node.component, "composite_id", "")
            or getattr(node.component, "component_id", "")
            or ""
        )
        if not composite_id:
            return

        definition = get_composite_component_definition(str(composite_id))
        if definition is None:
            return

        self.set_composite_instance_model(
            node,
            definition.mini_model or {},
            definition.port_mappings,
        )

    def set_composite_instance_model(
        self,
        node: ComponentNodeItem,
        mini_model: dict,
        port_mappings: list,
    ) -> None:
        """Install a composite mini-model on a node with unique internal names."""
        node.composite_instance_model = deepcopy(mini_model or {})
        node.composite_port_mappings = deepcopy(port_mappings or [])
        self.uniquify_composite_instance_node(node)

    def uniquify_composite_instance_node(
        self,
        node: ComponentNodeItem,
        used_names: set[str] | None = None,
    ) -> None:
        """Ensure a composite node's internal component names are unique."""
        if not int(getattr(node.component, "is_composite", 0) or 0):
            return
        mini_model = getattr(node, "composite_instance_model", {}) or {}
        if not isinstance(mini_model, dict) or not mini_model.get("components"):
            return

        if used_names is None:
            used_names = self.existing_component_and_composite_internal_names(
                exclude_nodes={int(getattr(node, "node_id", 0) or 0)}
            )
            node_name = str(getattr(node, "instance_name", "") or "")
            if node_name:
                used_names.add(node_name)

        normalized_model, normalized_mappings = uniquify_mini_model_component_names(
            mini_model,
            getattr(node, "composite_port_mappings", []) or [],
            used_names,
        )
        node.composite_instance_model = normalized_model
        node.composite_port_mappings = normalized_mappings
        if hasattr(node, "sync_composite_ports_from_mappings"):
            node.sync_composite_ports_from_mappings()

    def find_port(self, node_id: int, port_name: str) -> Optional[PortItem]:
        for node in self.component_items():
            if node.node_id != node_id:
                continue

            for port in node.ports:
                if port.name == port_name:
                    return port

        return None

    def find_subcomp_connector(
        self,
        node_id: int,
        connector_name: str,
        role: str = "",
    ) -> Optional[SubcompConnectorItem]:
        for node in self.component_items():
            if node.node_id != node_id:
                continue

            for connector in getattr(node, "subcomp_connectors", []):
                if connector.name != connector_name:
                    continue

                if role and getattr(connector, "role", "") != role:
                    continue

                return connector

        return None

    def clear_link_highlights(self):
        self.selected_connection = None

        for connection in list(self._highlighted_link_items):
            if connection.scene() is self:
                connection.set_highlighted(False)
        self._highlighted_link_items.clear()

    def clear_subcomp_attachment_highlights(self):
        self.selected_subcomp_attachment = None

        for attachment in list(self._highlighted_attachment_items):
            if attachment.scene() is self:
                attachment.set_highlighted(False)
        self._highlighted_attachment_items.clear()

    def clear_all_selection_highlights(self):
        self.clear_link_highlights()
        self.clear_subcomp_attachment_highlights()

    def highlight_links_for_node(self, node: "ComponentNodeItem"):
        # Do not walk and restyle every link in the model on every component
        # click. Only clear the items that were previously highlighted, then
        # touch the links/attachments actually connected to the newly selected
        # node.
        self.clear_link_highlights()
        self.clear_subcomp_attachment_highlights()

        for connection in self.links_attached_to_node(node):
            if connection.scene() is self:
                connection.set_highlighted(True)
                self._highlighted_link_items.add(connection)

        for attachment in self.attachments_attached_to_node(node):
            if attachment.scene() is self:
                attachment.set_highlighted(True)
                self._highlighted_attachment_items.add(attachment)

    def select_component(self, node: "ComponentNodeItem"):
        try:
            breadcrumb("model_scene.select_component", node=self._diagnostic_node_snapshot(node))
        except Exception:
            pass
        self.selected_component = node
        self.selected_connection = None
        self.selected_subcomp_attachment = None
        self.highlight_links_for_node(node)

        if self.properties_panel is not None:
            self.properties_panel.show_component(node)

        if self.selection_changed_callback is not None:
            self.selection_changed_callback(node)

    def select_link(self, connection: ConnectionItem):
        try:
            breadcrumb("model_scene.select_link", link=self._diagnostic_link_snapshot(connection))
        except Exception:
            pass
        self.clear_all_selection_highlights()
        self.selected_component = None
        self.selected_connection = connection
        connection.set_highlighted(True)
        self._highlighted_link_items.add(connection)

        if self.properties_panel is not None:
            self.properties_panel.show_link(connection)

        if self.selection_changed_callback is not None:
            self.selection_changed_callback(None)

    def select_subcomp_attachment(self, attachment: SubcompAttachmentItem):
        try:
            breadcrumb("model_scene.select_subcomp_attachment", attachment=self._diagnostic_attachment_snapshot(attachment))
        except Exception:
            pass
        self.clear_all_selection_highlights()
        self.selected_component = None
        self.selected_subcomp_attachment = attachment
        attachment.set_highlighted(True)
        self._highlighted_attachment_items.add(attachment)

        if self.properties_panel is not None:
            self.properties_panel.show_subcomp_attachment(attachment)

        if self.selection_changed_callback is not None:
            self.selection_changed_callback(None)

    def find_node_by_id(self, node_id: int) -> ComponentNodeItem | None:
        for node in self.component_items():
            if node.node_id == node_id:
                return node

        return None

    def begin_node_drag(self, node: Optional["ComponentNodeItem"] = None):
        # Invalidate any pending background route batch so stale paths do not
        # overwrite drag previews while the user is moving components.
        self._route_generation += 1
        self._suppress_link_hit_tests = True
        self._dragging_node = True
        self._drag_changed = False
        self.restore_bulk_drag_fast_path()

        drag_nodes: set[ComponentNodeItem] = set()
        if node is not None:
            drag_nodes.add(node)
            drag_nodes.update(self.group_members_for_node(node))

        for selected_node in self.selected_component_nodes(expand_groups=True):
            drag_nodes.add(selected_node)

        if not drag_nodes:
            drag_nodes = set(self.component_items())

        self._drag_nodes_by_id = {
            drag_node.node_id: drag_node
            for drag_node in drag_nodes
        }
        self._drag_start_positions = {
            drag_node.node_id: (drag_node.pos().x(), drag_node.pos().y())
            for drag_node in drag_nodes
        }
        self._drag_node_count = len(drag_nodes)
        self._bulk_drag_preview_suppressed = (
            self._drag_node_count >= self._bulk_drag_preview_threshold
        )
        self._reroute_timer.stop()
        self._drag_preview_timer.stop()
        self._drag_preview_node_ids.clear()
        self._drag_moved_node_ids.clear()

        if self._bulk_drag_preview_suppressed:
            self.begin_bulk_drag_fast_path(drag_nodes, anchor_node=node)

    def _scene_rect_for_nodes(self, nodes: set["ComponentNodeItem"]) -> QRectF:
        """Return one scene-coordinate rectangle covering the given nodes."""
        rect: QRectF | None = None
        for node in nodes:
            node_rect = node.mapRectToScene(node.rect())
            rect = node_rect if rect is None else rect.united(node_rect)
        return rect if rect is not None else QRectF()

    def begin_bulk_drag_fast_path(
        self,
        drag_nodes: set["ComponentNodeItem"],
        *,
        anchor_node: "ComponentNodeItem" | None = None,
    ) -> None:
        """Enable the very-low-overhead path for large selection moves.

        Qt still performs the actual item movement on the GUI thread, but FUSE
        stops doing Python work for every tiny mouse-move step.  The final
        release handler compares positions against ``_drag_start_positions`` and
        reroutes once.
        """
        if self._bulk_drag_fast_path_active:
            return

        self._bulk_drag_fast_path_active = True

        try:
            self._bulk_drag_previous_index_method = self.itemIndexMethod()
            self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        except Exception:
            self._bulk_drag_previous_index_method = None

        if anchor_node not in drag_nodes:
            anchor_node = sorted(drag_nodes, key=lambda item: item.node_id)[0] if drag_nodes else None
        self._bulk_drag_anchor_node_id = int(getattr(anchor_node, "node_id", 0) or 0) if anchor_node else None

        # For very large selections, letting Qt move every selected component on
        # every mouse event is still expensive even if Python routing callbacks
        # are disabled. Keep only the grabbed/anchor node movable and show one
        # lightweight outline representing the whole moved block. On release,
        # apply the final anchor delta to the rest of the nodes exactly once.
        self._bulk_drag_geometry_flag_state = {}
        self._bulk_drag_movable_flag_state = {}
        self._bulk_drag_hidden_node_state = {}
        for drag_node in drag_nodes:
            try:
                self._bulk_drag_geometry_flag_state[drag_node.node_id] = bool(
                    drag_node.flags() & QGraphicsItem.ItemSendsGeometryChanges
                )
                self._bulk_drag_movable_flag_state[drag_node.node_id] = bool(
                    drag_node.flags() & QGraphicsItem.ItemIsMovable
                )
                drag_node.setFlag(QGraphicsItem.ItemSendsGeometryChanges, False)
                if anchor_node is not None and drag_node is not anchor_node:
                    drag_node.setFlag(QGraphicsItem.ItemIsMovable, False)
                    self._bulk_drag_hidden_node_state[drag_node.node_id] = bool(drag_node.isVisible())
                    drag_node.setVisible(False)
            except Exception:
                pass

        if anchor_node is not None:
            try:
                scene_rect = self._scene_rect_for_nodes(drag_nodes).adjusted(-24.0, -24.0, 24.0, 24.0)
                local_rect = QRectF(
                    anchor_node.mapFromScene(scene_rect.topLeft()),
                    anchor_node.mapFromScene(scene_rect.bottomRight()),
                ).normalized()
                proxy = QGraphicsRectItem(local_rect, anchor_node)
                proxy.setPen(QPen(QColor(40, 120, 220, 180), 2.0, Qt.PenStyle.DashLine))
                proxy.setBrush(QBrush(Qt.BrushStyle.NoBrush))
                proxy.setZValue(10000)
                proxy.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self._bulk_drag_proxy_item = proxy
            except Exception:
                self._bulk_drag_proxy_item = None

        # Hide only graphics attached to the moving nodes. Hiding the entire
        # model's link layer made unrelated links blink out and made release
        # restoration scale with total model size instead of the moved cluster.
        self._bulk_drag_hidden_item_state = {}
        hidden_items: set[object] = set()
        for drag_node in drag_nodes:
            hidden_items.update(self.links_attached_to_node(drag_node))
            hidden_items.update(self.attachments_attached_to_node(drag_node))

        for item in hidden_items:
            try:
                self._bulk_drag_hidden_item_state[item] = bool(item.isVisible())
                item.setVisible(False)
            except Exception:
                pass

    def restore_bulk_drag_fast_path(self) -> None:
        """Restore scene state after a large-selection drag fast path."""
        if not self._bulk_drag_fast_path_active and not self._bulk_drag_geometry_flag_state:
            return

        proxy = self._bulk_drag_proxy_item
        self._bulk_drag_proxy_item = None
        if proxy is not None:
            try:
                if proxy.scene() is self:
                    self.removeItem(proxy)
                else:
                    proxy.setParentItem(None)
            except Exception:
                pass

        for node_id, was_visible in list(self._bulk_drag_hidden_node_state.items()):
            node = self._drag_nodes_by_id.get(node_id) or self.find_node_by_id(node_id)
            if node is None:
                continue
            try:
                node.setVisible(bool(was_visible))
            except Exception:
                pass
        self._bulk_drag_hidden_node_state = {}

        for node_id, was_movable in list(self._bulk_drag_movable_flag_state.items()):
            node = self._drag_nodes_by_id.get(node_id) or self.find_node_by_id(node_id)
            if node is None:
                continue
            try:
                node.setFlag(QGraphicsItem.ItemIsMovable, bool(was_movable))
            except Exception:
                pass
        self._bulk_drag_movable_flag_state = {}

        for node_id, was_enabled in list(self._bulk_drag_geometry_flag_state.items()):
            node = self._drag_nodes_by_id.get(node_id) or self.find_node_by_id(node_id)
            if node is None:
                continue
            try:
                node.setFlag(QGraphicsItem.ItemSendsGeometryChanges, bool(was_enabled))
            except Exception:
                pass
        self._bulk_drag_geometry_flag_state = {}

        self._bulk_drag_anchor_node_id = None

        for item, was_visible in list(self._bulk_drag_hidden_item_state.items()):
            try:
                if item.scene() is self:
                    item.setVisible(bool(was_visible))
            except Exception:
                pass
        self._bulk_drag_hidden_item_state = {}

        previous_index_method = self._bulk_drag_previous_index_method
        self._bulk_drag_previous_index_method = None
        if previous_index_method is not None:
            try:
                self.setItemIndexMethod(previous_index_method)
            except Exception:
                pass

        self._bulk_drag_fast_path_active = False

    def is_bulk_drag_fast_path_active(self) -> bool:
        """Return whether the current mouse gesture is a large-selection drag."""
        return bool(self._bulk_drag_fast_path_active)

    def defer_component_selection_until_drag_end(self, node: "ComponentNodeItem") -> None:
        """Delay expensive single-node link highlighting until we know it was a click."""
        self._deferred_drag_select_node = node

    def maybe_apply_deferred_drag_selection(self, changed: bool) -> None:
        node = self._deferred_drag_select_node
        self._deferred_drag_select_node = None
        if changed or node is None or node.scene() is not self:
            return
        self.select_component(node)

    def note_bulk_drag_node_moved(self, node: "ComponentNodeItem") -> None:
        """Record a move seen while the fast path is active."""
        if node is None:
            return
        node_id = int(getattr(node, "node_id", 0) or 0)
        if node_id > 0:
            self._drag_moved_node_ids.add(node_id)

    def commit_bulk_drag_proxy_delta(self) -> None:
        """Apply the anchor-node drag delta to hidden bulk-drag members once.

        During the large-selection fast path, only the grabbed anchor item moves
        interactively. The rest of the selection is hidden/frozen while a cheap
        outline follows the anchor. At release, commit the final delta to the
        frozen nodes before moved-node detection and rerouting.
        """
        if not self._bulk_drag_fast_path_active:
            return

        anchor_id = self._bulk_drag_anchor_node_id
        if anchor_id is None:
            return

        anchor = self._drag_nodes_by_id.get(anchor_id) or self.find_node_by_id(anchor_id)
        start = self._drag_start_positions.get(anchor_id)
        if anchor is None or start is None:
            return

        dx = anchor.pos().x() - start[0]
        dy = anchor.pos().y() - start[1]
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return

        for node_id, node_start in list(self._drag_start_positions.items()):
            if node_id == anchor_id:
                continue
            node = self._drag_nodes_by_id.get(node_id) or self.find_node_by_id(node_id)
            if node is None:
                continue
            try:
                node.setPos(node_start[0] + dx, node_start[1] + dy)
                self._drag_moved_node_ids.add(node_id)
            except Exception:
                pass

    def _moved_drag_nodes_from_start_positions(self) -> list["ComponentNodeItem"]:
        """Return drag nodes whose current position differs from drag start."""
        moved_nodes: list[ComponentNodeItem] = []

        for node_id, start in self._drag_start_positions.items():
            node = self._drag_nodes_by_id.get(node_id) or self.find_node_by_id(node_id)
            if node is None:
                continue

            dx = abs(node.pos().x() - start[0])
            dy = abs(node.pos().y() - start[1])
            if dx > 0.001 or dy > 0.001:
                moved_nodes.append(node)

        return moved_nodes

    def end_node_drag(self, node: Optional["ComponentNodeItem"] = None):
        """
        End an interactive drag.

        Scalability rule: do NOT reroute the entire model automatically here.
        Instead, reroute:
          1. links attached to moved nodes,
          2. subcomponent attachment edges attached to moved nodes, and
          3. for small drags only, existing links whose current route now
             intersects a moved node box.

        Large-selection drags use a fast path that suppresses per-mouse-move
        Python callbacks.  Therefore release detection compares all tracked
        start positions against current positions instead of relying solely on
        ItemPositionHasChanged.
        """
        self.commit_bulk_drag_proxy_delta()

        moved_nodes = self._moved_drag_nodes_from_start_positions()
        changed = self._drag_changed or bool(moved_nodes)

        if changed and self.snap_to_grid_enabled:
            # Geometry-change callbacks may still be disabled here for the bulk
            # fast path.  That is intentional: snap all moved nodes without
            # triggering per-node routing, then reroute once below.
            for moved_node in moved_nodes:
                snapped_position = self.snap_position_to_grid(moved_node.pos())
                if snapped_position != moved_node.pos():
                    moved_node.setPos(snapped_position)

            moved_nodes = self._moved_drag_nodes_from_start_positions()
            changed = changed or bool(moved_nodes)

        moved_node_ids = {
            int(moved_node.node_id)
            for moved_node in moved_nodes
        }
        moved_node_ids.update(self._drag_moved_node_ids)
        if changed and node is not None:
            moved_node_ids.add(node.node_id)

        moved_nodes = [
            self._drag_nodes_by_id.get(moved_node_id) or self.find_node_by_id(moved_node_id)
            for moved_node_id in moved_node_ids
        ]
        moved_nodes = [moved_node for moved_node in moved_nodes if moved_node is not None]

        # Restore hidden links and geometry-change notifications before applying
        # release-time visual updates.
        self.restore_bulk_drag_fast_path()

        self._dragging_node = False
        self._suppress_link_hit_tests = False
        self._bulk_drag_preview_suppressed = False
        self._drag_node_count = 0
        self._drag_preview_timer.stop()
        self._drag_preview_node_ids.clear()
        self._drag_moved_node_ids.clear()

        if changed and moved_nodes:
            self.reroute_links_affected_by_nodes(moved_nodes)

        self._drag_changed = False
        self._drag_start_positions = {}
        self._drag_nodes_by_id = {}

        self.maybe_apply_deferred_drag_selection(changed)

        if changed:
            self.request_deferred_model_changed()

    def request_reroute_all_links(self):
        """
        Schedule a full reroute shortly in the future.

        Do not full-reroute while a node is actively being dragged. That is what
        caused multi-second UI freezes in dense models.
        """
        if self._dragging_node:
            return

        if self.routing_is_suppressed():
            self.mark_link_routing_dirty(
                connections=self.connection_items(),
                update_all_attachments=True,
                reason="request_reroute_all_links",
            )
            return

        self._reroute_timer.start()

    def request_drag_preview_for_node(self, node: "ComponentNodeItem") -> None:
        """Throttle cheap link preview updates during interactive drags."""
        if not self._dragging_node:
            self.reroute_links_for_node(node)
            return

        node_id = int(getattr(node, "node_id", 0) or 0)
        if node_id <= 0:
            return

        self._drag_preview_node_ids.add(node_id)
        self._drag_moved_node_ids.add(node_id)

        # For large selections, even "cheap" preview routing can dominate the
        # mouse-move path because every moved node fires ItemPositionHasChanged.
        # Record the moved nodes, but defer all visual rerouting until release.
        if self._bulk_drag_preview_suppressed:
            return

        if not self._drag_preview_timer.isActive():
            self._drag_preview_timer.start()

    def update_drag_preview_links(self) -> None:
        """Update attached link previews for nodes moved since the last tick."""
        if not self._dragging_node:
            self._drag_preview_node_ids.clear()
            return

        if self._bulk_drag_preview_suppressed:
            self._drag_preview_node_ids.clear()
            return

        node_ids = set(self._drag_preview_node_ids)
        self._drag_preview_node_ids.clear()
        if not node_ids:
            return

        affected_connections: set[ConnectionItem] = set()
        affected_nodes: list[ComponentNodeItem] = []

        for node_id in node_ids:
            node = self.find_node_by_id(node_id)
            if node is None:
                continue
            affected_nodes.append(node)
            affected_connections.update(self.links_attached_to_node(node))

        for connection in sorted(affected_connections, key=lambda item: item.link.link_id):
            connection.update_position_fast()

        for node in affected_nodes:
            self.update_subcomp_attachments_for_node(node)

    def route_obstacle_rect_tuples(self) -> list[tuple[float, float, float, float]]:
        """Snapshot padded component rectangles for background link routing."""
        pad = ConnectionItem.ROUTE_CLEARANCE
        rects: list[tuple[float, float, float, float]] = []

        for node in self.component_items():
            rect = node.mapRectToScene(node.rect()).adjusted(-pad, -pad, pad, pad)
            rects.append((rect.left(), rect.top(), rect.right(), rect.bottom()))

        return rects

    def route_request_for_connection(
        self,
        connection: ConnectionItem,
    ) -> LinkRouteRequest:
        """Snapshot one connection's route inputs on the GUI thread."""
        source_center = connection.source_port.scene_center()
        target_center = connection.target_port.scene_center()
        source_exit = connection.exit_point_for_port(connection.source_port)
        target_exit = connection.exit_point_for_port(connection.target_port)
        config = connection.routing_config()

        return LinkRouteRequest(
            link_id=int(connection.link.link_id),
            source_center=(source_center.x(), source_center.y()),
            target_center=(target_center.x(), target_center.y()),
            source_exit=(source_exit.x(), source_exit.y()),
            target_exit=(target_exit.x(), target_exit.y()),
            lane_distance=float(connection.outward_lane_distance()),
            config={
                "route_clearance": float(config.route_clearance),
                "exit_margin": float(config.exit_margin),
                "lane_spacing": float(config.lane_spacing),
                "bend_penalty": float(config.bend_penalty),
                "fallback_margin": float(config.fallback_margin),
            },
        )

    def route_generation(self) -> int:
        """Advance and return the latest asynchronous routing generation."""
        self._route_generation += 1
        return self._route_generation

    def schedule_async_link_routing(
        self,
        connections: list[ConnectionItem],
        *,
        update_all_attachments: bool = False,
        attachment_nodes: list["ComponentNodeItem"] | None = None,
    ) -> None:
        """Route links on worker threads and apply the resulting paths later.

        Only plain geometry snapshots leave the GUI thread. The returned route
        points are applied to ``ConnectionItem`` graphics objects on the GUI
        thread via Qt signals.
        """
        if self.routing_is_suppressed():
            self.mark_link_routing_dirty(
                connections=list(connections),
                update_all_attachments=update_all_attachments,
                attachment_nodes=attachment_nodes,
                reason="schedule_async_link_routing",
            )
            return

        connections = [
            connection
            for connection in connections
            if connection.scene() is self
        ]

        if not connections:
            if update_all_attachments:
                for attachment in self.subcomp_attachment_items():
                    attachment.update_position()
            elif attachment_nodes:
                for node in attachment_nodes:
                    self.update_subcomp_attachments_for_node(node)
            return

        if not self._async_routing_enabled:
            breadcrumb(
                "async_router.batch.disabled",
                link_count=len(connections),
                reason="FUSE_DISABLE_ASYNC_ROUTING",
            )
            self.reroute_connections_sync(
                connections,
                update_all_attachments=update_all_attachments,
                attachment_nodes=attachment_nodes,
                fast=True,
            )
            return

        generation = self.route_generation()
        self._route_batch_id += 1
        batch_id = self._route_batch_id
        obstacle_rects = self.route_obstacle_rect_tuples()
        requests = [
            self.route_request_for_connection(connection)
            for connection in sorted(
                connections,
                key=lambda item: item.link.link_id,
            )
        ]

        worker = LinkRoutingWorker(
            generation=generation,
            requests=requests,
            obstacle_rects=obstacle_rects,
            max_workers=self._async_route_workers,
            batch_id=batch_id,
        )
        self._active_route_workers.add(worker)
        self._pending_route_batches[generation] = {
            "worker": worker,
            "batch_id": batch_id,
            "connection_ids": [int(connection.link.link_id) for connection in connections],
            "obstacle_count": len(obstacle_rects),
            "update_all_attachments": bool(update_all_attachments),
            "attachment_node_ids": [
                int(node.node_id)
                for node in (attachment_nodes or [])
                if node is not None
            ],
        }

        breadcrumb(
            "async_router.batch.start",
            generation=generation,
            batch_id=batch_id,
            link_count=len(requests),
            obstacle_count=len(obstacle_rects),
            worker_count=self._async_route_workers,
        )

        worker.signals.finished.connect(self.apply_async_link_routes)
        worker.signals.failed.connect(self.handle_async_link_routing_failed)

        self._route_thread_pool.start(worker)

    def reroute_connections_sync(
        self,
        connections: list[ConnectionItem],
        *,
        update_all_attachments: bool = False,
        attachment_nodes: list["ComponentNodeItem"] | None = None,
        fast: bool = False,
    ) -> None:
        """Synchronous fallback used if the background router fails."""
        for connection in sorted(connections, key=lambda item: item.link.link_id):
            if connection.scene() is self:
                connection.clear_route_points()
                if fast:
                    connection.update_position_fast()
                else:
                    connection.update_position()

        if update_all_attachments:
            for attachment in self.subcomp_attachment_items():
                attachment.update_position()
        elif attachment_nodes:
            for node in attachment_nodes:
                self.update_subcomp_attachments_for_node(node)

    def apply_async_link_routes(
        self,
        generation: int,
        results: list[LinkRouteResult],
    ) -> None:
        """Apply worker-computed link routes if they are still current."""
        generation = int(generation)
        batch = self._pending_route_batches.pop(generation, {})
        worker = batch.get("worker")
        if worker is not None:
            self._active_route_workers.discard(worker)

        if generation != int(self._route_generation):
            breadcrumb(
                "async_router.batch.result.discard_stale",
                generation=generation,
                current_generation=self._route_generation,
                batch_id=batch.get("batch_id"),
                result_count=len(results),
                reason="generation_mismatch",
            )
            return

        connections_by_id = {
            int(connection.link.link_id): connection
            for connection in self.connection_items()
        }

        applied_count = 0
        discarded_count = 0
        for result in results:
            connection = connections_by_id.get(int(result.link_id))
            source_node = getattr(getattr(connection, "source_port", None), "node", None)
            target_node = getattr(getattr(connection, "target_port", None), "node", None)
            if (
                connection is None
                or connection.scene() is not self
                or source_node is None
                or target_node is None
                or source_node.scene() is not self
                or target_node.scene() is not self
            ):
                discarded_count += 1
                continue

            connection.set_route_points_from_tuples(result.points)
            applied_count += 1

        breadcrumb(
            "async_router.batch.result.apply",
            generation=generation,
            batch_id=batch.get("batch_id"),
            result_count=len(results),
            applied_count=applied_count,
            discarded_count=discarded_count,
            link_count=len(batch.get("connection_ids", [])),
            obstacle_count=batch.get("obstacle_count"),
        )
        self.update_attachments_for_route_batch(batch)

    def handle_async_link_routing_failed(
        self,
        generation: int,
        message: str,
    ) -> None:
        """Fallback to cheap synchronous routing for the latest failed batch."""
        generation = int(generation)
        batch = self._pending_route_batches.pop(generation, {})
        worker = batch.get("worker")
        if worker is not None:
            self._active_route_workers.discard(worker)

        if generation != int(self._route_generation):
            breadcrumb(
                "async_router.batch.result.discard_stale",
                generation=generation,
                current_generation=self._route_generation,
                batch_id=batch.get("batch_id"),
                reason="failed_generation_mismatch",
                error=message,
            )
            return

        connection_ids = {
            int(link_id)
            for link_id in batch.get("connection_ids", [])
        }
        connections = [
            connection
            for connection in self.connection_items()
            if int(connection.link.link_id) in connection_ids
        ]
        attachment_nodes = self.nodes_for_route_batch(batch)

        breadcrumb(
            "async_router.batch.failed",
            generation=generation,
            batch_id=batch.get("batch_id"),
            link_count=len(connections),
            obstacle_count=batch.get("obstacle_count"),
            error=message,
        )
        self.reroute_connections_sync(
            connections,
            update_all_attachments=bool(batch.get("update_all_attachments")),
            attachment_nodes=attachment_nodes,
            fast=True,
        )

    def nodes_for_route_batch(self, batch: dict) -> list["ComponentNodeItem"]:
        """Resolve stored node ids for a completed asynchronous route batch."""
        node_ids = {
            int(node_id)
            for node_id in batch.get("attachment_node_ids", [])
        }
        if not node_ids:
            return []

        return [
            node
            for node in self.component_items()
            if int(node.node_id) in node_ids
        ]

    def update_attachments_for_route_batch(self, batch: dict) -> None:
        """Update attachment lines requested by a route batch."""
        if bool(batch.get("update_all_attachments")):
            for attachment in self.subcomp_attachment_items():
                attachment.update_position()
            return

        for node in self.nodes_for_route_batch(batch):
            self.update_subcomp_attachments_for_node(node)

    def reroute_all_links(self):
        """
        Recompute link paths in link-id order.

        The expensive route search runs on a thread-pool worker from a snapshot
        of numeric geometry. Qt graphics items are updated when the worker
        returns to the GUI thread.
        """
        self.schedule_async_link_routing(
            self.connection_items(),
            update_all_attachments=True,
        )

    def reroute_links_for_node(self, node: "ComponentNodeItem", force_full: bool = False):
        """
        Update only links and subcomponent attachment edges attached to a node.
        """
        connections = sorted(
            self.links_attached_to_node(node),
            key=lambda item: item.link.link_id,
        )

        if self._dragging_node and not force_full:
            for connection in connections:
                connection.update_position_fast()
            self.update_subcomp_attachments_for_node(node)
            return

        self.schedule_async_link_routing(
            connections,
            attachment_nodes=[node],
        )

    def update_subcomp_attachments_for_node(self, node: "ComponentNodeItem"):
        for attachment in self.subcomp_attachment_items():
            if attachment.is_connected_to_node(node):
                attachment.update_position()

    def links_attached_to_node(self, node: "ComponentNodeItem") -> set[ConnectionItem]:
        seen: set[ConnectionItem] = set()

        for port in node.ports:
            for connection in port.connections:
                seen.add(connection)

        return seen

    def attachments_attached_to_node(self, node: "ComponentNodeItem") -> set[SubcompAttachmentItem]:
        return {
            attachment
            for attachment in self.subcomp_attachment_items()
            if attachment.is_connected_to_node(node)
        }

    def link_route_intersects_node(self, connection: ConnectionItem, node: "ComponentNodeItem") -> bool:
        """
        Return True if an existing rendered link path crosses the moved node's
        padded box. This lets us reroute only the links that were made invalid
        by the move.
        """
        if not connection.route_points:
            return False

        # Use the same clearance concept as ConnectionItem's router.
        pad = ConnectionItem.ROUTE_CLEARANCE
        rect = connection.node_body_rect(node).adjusted(-pad, -pad, pad, pad)

        for a, b in zip(connection.route_points, connection.route_points[1:]):
            if connection.segment_intersects_rect(a, b, rect):
                return True

        return False

    def reroute_links_affected_by_node(self, node: "ComponentNodeItem"):
        """
        Reroute links attached to the moved node plus unrelated links whose
        current path now crosses the moved node.
        """
        self.reroute_links_affected_by_nodes([node])

    def reroute_links_affected_by_nodes(self, nodes: list["ComponentNodeItem"]):
        """
        Reroute links affected by one or more moved nodes as one release-time batch.
        """
        moved_nodes = [node for node in nodes if node is not None]
        if not moved_nodes:
            return

        affected: set[ConnectionItem] = set()
        for node in moved_nodes:
            affected.update(self.links_attached_to_node(node))

        # Release-time work must be bounded by the moved selection, not by total
        # diagram size. Do not scan every unrelated link for crossing tests here;
        # that made even one-node drags feel like a full-model operation on dense
        # canvases. Attached links are reconnected immediately, then accurately
        # rerouted by the background worker.
        affected_connections = sorted(affected, key=lambda item: item.link.link_id)
        for connection in affected_connections:
            connection.update_position_fast()

        for node in moved_nodes:
            self.update_subcomp_attachments_for_node(node)

        self.schedule_async_link_routing(
            affected_connections,
            attachment_nodes=moved_nodes,
        )

    def endpoint_for_port(self, port: PortItem) -> LinkEndpoint:
        return LinkEndpoint(
            component_name=port.node.instance_name,
            port_name=port.name,
            port_metadata=getattr(port, "metadata", {}) or {},
        )

    def default_link_name(self, source_port: PortItem, target_port: PortItem) -> str:
        base = f"lnk_{source_port.node.instance_name}_{target_port.node.instance_name}"
        base = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)

        existing = {link.name for link in self.links}

        if base not in existing:
            return base

        index = 1
        while f"{base}_{index}" in existing:
            index += 1

        return f"{base}_{index}"

    def check_link_compatibility(
        self,
        source_port: PortItem,
        target_port: PortItem,
    ) -> LinkCompatibilityResult:
        source_plugin_id = getattr(source_port.node.component, "plugin_id", "") or ""
        target_plugin_id = getattr(target_port.node.component, "plugin_id", "") or ""
        plugin_id = source_plugin_id if source_plugin_id == target_plugin_id else (self.active_plugin_id or source_plugin_id)

        if not plugin_id:
            return LinkCompatibilityResult()

        try:
            plugin = get_plugin_by_id(plugin_id)
        except Exception:
            return LinkCompatibilityResult()

        if not hasattr(plugin, "check_link_compatibility"):
            return LinkCompatibilityResult()

        return plugin.check_link_compatibility(
            self.endpoint_for_port(source_port),
            self.endpoint_for_port(target_port),
        )

    def confirm_link_compatibility_warning(self, result: LinkCompatibilityResult) -> bool:
        response = QMessageBox.warning(
            None,
            result.title or "Link Compatibility Warning",
            result.message or "The selected ports may not be compatible. Create the link anyway?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        return response == QMessageBox.Yes

    def compatibility_warning_is_suppressed(self, result: LinkCompatibilityResult) -> bool:
        code = (result.code or "").strip()
        return bool(code and code in self.suppressed_compatibility_warnings)

    def confirm_subcomp_compatibility_warning(self, result: LinkCompatibilityResult) -> bool:
        if self.compatibility_warning_is_suppressed(result):
            return True

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle(result.title or "SubComponent Compatibility Warning")
        message_box.setText(
            result.message
            or "The selected SubComponent may not be compatible with this slot."
        )
        message_box.setInformativeText("Create the SubComponent attachment anyway?")
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        message_box.setDefaultButton(QMessageBox.No)

        checkbox = None
        warning_code = (result.code or "").strip()
        if warning_code:
            checkbox = QCheckBox("Do not show this warning again for this project")
            message_box.setCheckBox(checkbox)

        response = message_box.exec()

        if checkbox is not None and checkbox.isChecked():
            self.suppressed_compatibility_warnings.add(warning_code)

        return response == QMessageBox.Yes

    def clear_port_compatibility_highlights(self):
        for node in self.component_items():
            for port in node.ports:
                port.set_compatibility_highlight("")

    def highlight_compatible_ports(self, source_port: PortItem):
        """
        Highlight structurally linkable ports.

        For regular links, FUSE should not try to fully type-check SST event
        compatibility from ordinary port metadata. Plugin compatibility hooks may
        still return warnings/errors for plugins that have reliable link metadata,
        but SST currently treats ordinary declared ports as structurally linkable.
        """
        for node in self.component_items():
            for port in node.ports:
                if port is source_port:
                    continue

                if port.is_connected():
                    continue

                if (
                    self.sst_runtime_slot_shadow_rule_for_port(source_port) is not None
                    or self.sst_runtime_slot_shadow_rule_for_port(port) is not None
                ):
                    port.set_compatibility_highlight("incompatible")
                    continue

                if self.sst_memhierarchy_slot_port_mode_link_would_conflict(
                    source_port,
                    port,
                ):
                    port.set_compatibility_highlight("incompatible")
                    continue

                result = self.check_link_compatibility(source_port, port)

                if result.severity == "error" or not result.can_create:
                    port.set_compatibility_highlight("incompatible")
                elif result.severity == "warning":
                    port.set_compatibility_highlight("warning")
                else:
                    port.set_compatibility_highlight("compatible")

    def create_link_between_ports(
        self,
        source_port: PortItem,
        target_port: PortItem,
        compatibility: LinkCompatibilityResult,
    ) -> ConnectionItem:
        link_id = self._next_link_id
        self._next_link_id += 1

        link = ModelLink(
            link_id=link_id,
            name=self.default_link_name(source_port, target_port),
            source_node_id=source_port.node.node_id,
            source_component_name=source_port.node.instance_name,
            source_port=source_port.name,
            target_node_id=target_port.node.node_id,
            target_component_name=target_port.node.instance_name,
            target_port=target_port.name,
            source_latency="1ns",
            target_latency="1ns",
            link_type="point_to_point",
            plugin_id=(
                getattr(source_port.node.component, "plugin_id", "")
                if getattr(source_port.node.component, "plugin_id", "") == getattr(target_port.node.component, "plugin_id", "")
                else (self.active_plugin_id or getattr(source_port.node.component, "plugin_id", ""))
            ),
            compatibility_severity=compatibility.severity,
            compatibility_code=compatibility.code,
            compatibility_message=compatibility.message,
            plugin_metadata={},
        )

        self.links.append(link)

        connection = ConnectionItem(link, source_port, target_port)
        self.addItem(connection)
        connection.update_position()
        self.select_link(connection)
        self.notify_model_changed()

        return connection

    def delete_link(self, connection: ConnectionItem):
        if connection is None:
            return

        self.invalidate_pending_link_routes(reason="delete_link")
        try:
            breadcrumb("model_scene.delete_link", link=self._diagnostic_link_snapshot(connection))
        except Exception:
            pass
        if connection.link in self.links:
            self.links.remove(connection.link)

        self._highlighted_link_items.discard(connection)
        if self.selected_connection is connection:
            self.selected_connection = None

        if connection.scene() is self:
            connection.setSelected(False)
            connection.set_highlighted(False)

        for port in (connection.source_port, connection.target_port):
            if connection in port.connections:
                port.connections.remove(connection)
            port.update_connection_state()

        if connection.scene() is self:
            self.removeItem(connection)

        if self.properties_panel is not None:
            self.properties_panel.show_empty()

        self.notify_model_changed()

    def find_connection_by_link_id(self, link_id: int) -> ConnectionItem | None:
        for connection in self.connection_items():
            if connection.link.link_id == link_id:
                return connection

        return None

    def select_link_by_id(self, link_id: int):
        connection = self.find_connection_by_link_id(link_id)

        if connection is None:
            return

        self.select_link(connection)

    def delete_component_node(self, node: ComponentNodeItem):
        """
        Delete a component or subcomponent instance from the model.

        This also removes:
        - normal links attached to any of the node's ports
        - subcomponent attachment edges where the node is either the parent or child
        - child subcomponents recursively attached underneath this node
        """
        if node is None or node.scene() is not self:
            return

        self.invalidate_pending_link_routes(reason="delete_component_node")
        try:
            breadcrumb("model_scene.delete_component_node.start", node=self._diagnostic_node_snapshot(node), snapshot=self.diagnostic_snapshot())
        except Exception:
            pass

        node_id = int(getattr(node, "node_id", 0) or 0)
        self._deleting_node_ids.add(node_id)
        try:
            node.setSelected(False)

            # Recursively delete attached child subcomponents first.
            child_node_ids = [
                attachment.child_node_id
                for attachment in list(getattr(self, "subcomp_attachments", []))
                if attachment.parent_node_id == node.node_id
            ]

            for child_node_id in child_node_ids:
                child_node = self.find_node_by_id(child_node_id)
                if child_node is not None:
                    self.delete_component_node(child_node)

            # Delete normal links attached to this node.
            for connection in list(self.connection_items()):
                if connection.is_connected_to_node(node):
                    self.delete_link(connection)

            # Delete subcomponent attachment edges involving this node.
            for attachment_item in list(self.subcomp_attachment_items()):
                attachment = attachment_item.attachment
                if (
                        attachment.parent_node_id == node.node_id
                        or attachment.child_node_id == node.node_id
                ):
                    self.delete_subcomp_attachment(attachment_item)

            if self.selected_component is node:
                self.selected_component = None

            self.node_group_ids.pop(node.node_id, None)

            if self.properties_panel is not None:
                self.properties_panel.show_empty()

            if node.scene() is self:
                self.removeItem(node)
            self.notify_model_changed()
            breadcrumb("model_scene.delete_component_node.end", node_id=node_id, snapshot=self.diagnostic_snapshot())
        finally:
            self._deleting_node_ids.discard(node_id)

    def delete_component_nodes(self, nodes: list[ComponentNodeItem]) -> bool:
        """Delete several component nodes as one model change.

        Group expansion and recursive subcomponent deletion can cause the same
        node to appear more than once or to be removed while the batch is still
        iterating, so deletion is driven by stable node ids and skips ids that
        have already disappeared.
        """
        node_ids = sorted(
            {
                int(getattr(node, "node_id", 0))
                for node in nodes
                if node is not None and int(getattr(node, "node_id", 0)) > 0
            }
        )
        if not node_ids:
            return False

        deleted_any = False
        breadcrumb("model_scene.delete_component_nodes.request", node_ids=node_ids, snapshot=self.diagnostic_snapshot())
        self.begin_model_change_batch()
        try:
            self.invalidate_pending_link_routes(reason="delete_component_nodes")
            self.clear_all_selection_highlights()
            self.clearSelection()

            for node_id in node_ids:
                node = self.find_node_by_id(node_id)
                if node is None:
                    continue
                self.delete_component_node(node)
                deleted_any = True
        finally:
            self.end_model_change_batch()

        return deleted_any

    def delete_selection(self) -> bool:
        """Delete the current canvas selection.

        Component selections are preferred over highlighted links/attachments so
        deleting a multi-component selection removes the selected components, and
        selecting one member of a group removes every component in that group.
        """
        breadcrumb("model_scene.delete_selection.request", snapshot=self.diagnostic_snapshot())
        nodes = self.selected_component_nodes(expand_groups=True)
        if nodes:
            return self.delete_component_nodes(nodes)

        selected_connections = [
            item for item in self.selectedItems() if isinstance(item, ConnectionItem)
        ]
        if self.selected_connection is not None:
            selected_connections.append(self.selected_connection)

        unique_connections = []
        seen_connections: set[int] = set()
        for connection in selected_connections:
            link_id = getattr(getattr(connection, "link", None), "link_id", id(connection))
            if link_id in seen_connections:
                continue
            seen_connections.add(link_id)
            unique_connections.append(connection)

        if unique_connections:
            self.begin_model_change_batch()
            try:
                self.invalidate_pending_link_routes(reason="delete_selection_links")
                for connection in list(unique_connections):
                    if connection.scene() is self:
                        self.delete_link(connection)
            finally:
                self.end_model_change_batch()
            return True

        selected_attachments = [
            item
            for item in self.selectedItems()
            if isinstance(item, SubcompAttachmentItem)
        ]
        if self.selected_subcomp_attachment is not None:
            selected_attachments.append(self.selected_subcomp_attachment)

        unique_attachments = []
        seen_attachments: set[int] = set()
        for attachment_item in selected_attachments:
            attachment_id = getattr(
                getattr(attachment_item, "attachment", None),
                "attachment_id",
                id(attachment_item),
            )
            if attachment_id in seen_attachments:
                continue
            seen_attachments.add(attachment_id)
            unique_attachments.append(attachment_item)

        if unique_attachments:
            self.begin_model_change_batch()
            try:
                self.invalidate_pending_link_routes(reason="delete_selection_attachments")
                for attachment_item in list(unique_attachments):
                    if attachment_item.scene() is self:
                        self.delete_subcomp_attachment(attachment_item)
            finally:
                self.end_model_change_batch()
            return True

        return False

    def delete_component_by_id(self, node_id: int):
        node = self.find_node_by_id(node_id)

        if node is None:
            return

        self.delete_component_node(node)

    def delete_link_by_id(self, link_id: int):
        connection = self.find_connection_by_link_id(link_id)

        if connection is None:
            return

        self.delete_link(connection)

    def find_subcomp_attachment_by_id(self, attachment_id: int) -> SubcompAttachmentItem | None:
        for item in self.subcomp_attachment_items():
            if item.attachment.attachment_id == attachment_id:
                return item

        return None

    def delete_subcomp_attachment_by_id(self, attachment_id: int):
        item = self.find_subcomp_attachment_by_id(attachment_id)

        if item is None:
            return

        self.delete_subcomp_attachment(item)

    def port_clicked(self, port: PortItem):
        if self.pending_subcomp_connector is not None:
            self.warn_mixed_endpoint_types()
            self.cancel_pending_subcomp_attachment()
            return

        if port.is_connected():
            self.warn_port_already_connected()
            self.cancel_pending_connection()
            return

        if self.pending_source_port is None:
            self.pending_source_port = port
            self.clear_port_compatibility_highlights()
            self.highlight_compatible_ports(port)

            self.pending_line = QGraphicsLineItem()
            self.pending_line.setPen(QPen(QColor("#2f80ed"), 2, Qt.DashLine))
            self.pending_line.setZValue(4)
            self.pending_line.setAcceptedMouseButtons(Qt.NoButton)
            self.addItem(self.pending_line)
            return

        source_port = self.pending_source_port
        target_port = port

        if source_port is target_port:
            self.cancel_pending_connection()
            return

        if target_port.is_connected():
            self.warn_port_already_connected()
            self.cancel_pending_connection()
            return

        if self.sst_memhierarchy_slot_port_mode_link_guard(source_port, target_port):
            self.cancel_pending_connection()
            return

        if self.sst_shadowed_raw_port_link_guard(source_port, target_port):
            self.cancel_pending_connection()
            return

        if not self.confirm_sst_deprecated_port_link_use(source_port, target_port):
            self.cancel_pending_connection()
            return

        compatibility = self.check_link_compatibility(source_port, target_port)

        if compatibility.severity == "error" or not compatibility.can_create:
            QMessageBox.critical(
                None,
                compatibility.title or "Cannot Create Link",
                compatibility.message or "The selected ports cannot be linked.",
            )
            self.cancel_pending_connection()
            return

        if compatibility.severity == "warning":
            if not self.confirm_link_compatibility_warning(compatibility):
                self.cancel_pending_connection()
                return

        self.cancel_pending_visual_line_only()
        self.clear_port_compatibility_highlights()
        self.create_link_between_ports(source_port, target_port, compatibility)
        self.pending_source_port = None

    def begin_connection(self, source_port: PortItem):
        """
        Backward-compatible wrapper for older callers.

        New link creation is handled through port_clicked(), which creates the link
        immediately after the second port is selected, uses endpoint latencies, and
        shows the new link in the properties panel. Do not prompt for latency here.
        """
        if source_port.is_connected():
            return

        self.cancel_pending_connection()
        self.cancel_pending_subcomp_attachment()
        self.pending_source_port = source_port
        self.clear_port_compatibility_highlights()
        self.highlight_compatible_ports(source_port)

        self.pending_line = QGraphicsLineItem()
        self.pending_line.setPen(QPen(QColor("#2f80ed"), 2, Qt.DashLine))
        self.pending_line.setZValue(4)
        self.pending_line.setAcceptedMouseButtons(Qt.NoButton)

        start = source_port.scene_center()
        self.pending_line.setLine(start.x(), start.y(), start.x(), start.y())
        self.addItem(self.pending_line)

    def finish_connection(self, target_port: PortItem):
        """
        Backward-compatible wrapper for older callers.

        This delegates to the same no-popup behavior used by port_clicked().
        """
        if self.pending_source_port is None:
            return

        self.port_clicked(target_port)

    def subcomp_connectors_for_node(self, node: ComponentNodeItem) -> list[SubcompConnectorItem]:
        return list(getattr(node, "subcomp_connectors", []))

    def subcomp_connector_is_connected(self, connector: SubcompConnectorItem) -> bool:
        for attachment in self.subcomp_attachment_items():
            if attachment.source_connector is connector or attachment.target_connector is connector:
                return True

        return False

    @staticmethod
    def _connector_metadata_truthy(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def subcomp_connector_allows_multiple(self, connector: SubcompConnectorItem) -> bool:
        metadata = getattr(connector, "metadata", {}) or {}
        return self._connector_metadata_truthy(metadata.get("allow_multiple", False))

    def subcomp_connector_has_available_capacity(self, connector: SubcompConnectorItem) -> bool:
        if not self.subcomp_connector_is_connected(connector):
            return True

        return self.subcomp_connector_allows_multiple(connector)


    def sst_port_visibility_rule_for_port(self, port: PortItem):
        """Return the SST raw/advanced visibility rule for a normal port."""
        if port is None:
            return None

        node = getattr(port, "node", None)
        component = getattr(node, "component", None)
        if getattr(component, "plugin_id", "") != "sst":
            return None

        try:
            from fuse.plugins.community.sst.port_visibility import rule_for_node_port

            return rule_for_node_port(node, getattr(port, "name", ""))
        except Exception:
            return None

    def sst_runtime_slot_shadow_rule_for_port(self, port: PortItem):
        """Return a shadowed raw-port rule that must not be linked directly."""
        rule = self.sst_port_visibility_rule_for_port(port)
        if getattr(rule, "mode", "") == "runtime_slot_shadow":
            return rule
        return None


    def sst_deprecated_port_rule_for_port(self, port: PortItem):
        """Return a deprecated-connector rule for an SST normal port."""
        if port is None:
            return None

        node = getattr(port, "node", None)
        component = getattr(node, "component", None)
        if getattr(component, "plugin_id", "") != "sst":
            return None

        try:
            from fuse.plugins.community.sst.port_visibility import (
                deprecated_port_rule_for_node,
            )

            return deprecated_port_rule_for_node(node, getattr(port, "name", ""))
        except Exception:
            return None

    def sst_deprecated_slot_rule_for_connector(
        self,
        connector: SubcompConnectorItem,
    ):
        """Return a deprecated-connector rule for an SST SubComponent slot."""
        if connector is None or getattr(connector, "role", "") != "slot":
            return None

        node = getattr(connector, "node", None)
        component = getattr(node, "component", None)
        if getattr(component, "plugin_id", "") != "sst":
            return None

        try:
            from fuse.plugins.community.sst.port_visibility import (
                deprecated_slot_rule_for_node,
            )

            return deprecated_slot_rule_for_node(node, getattr(connector, "name", ""))
        except Exception:
            return None

    def sst_deprecated_connector_stage(self, node: ComponentNodeItem, rule) -> str:
        try:
            from fuse.plugins.community.sst.port_visibility import (
                deprecated_connector_stage_for_node,
            )

            return deprecated_connector_stage_for_node(node, rule)
        except Exception:
            return "deprecated"

    def sst_deprecated_connector_warning_details(
        self,
        *,
        node: ComponentNodeItem,
        connector_name: str,
        connector_kind: str,
        rule,
    ) -> tuple[str, str]:
        """Build link/attachment warning copy for a deprecated SST connector."""
        label = f"{node.instance_name}.{connector_name}"
        kind = "SubComponent slot" if connector_kind == "slot" else "port"
        stage = self.sst_deprecated_connector_stage(node, rule)

        if stage == "legacy_deprecated":
            text = f"{label} is a deprecated/legacy SST {kind}."
        elif stage == "removed":
            text = f"{label} was removed from this SST target."
        else:
            text = f"{label} is a deprecated SST {kind}."

        details = []
        deprecated_since = str(getattr(rule, "deprecated_since", "") or "").strip()
        if deprecated_since:
            details.append(f"Deprecated since SST {deprecated_since}.")

        replacement = str(getattr(rule, "replacement_name", "") or "").strip()
        replacement_kind = str(getattr(rule, "replacement_kind", "") or "").strip()
        if replacement:
            replacement_label = replacement_kind or connector_kind
            details.append(f"Preferred {replacement_label}: {replacement}.")

        explanation = str(getattr(rule, "explanation", "") or "").strip()
        if explanation:
            details.append("")
            details.append(explanation)

        details.append("")
        details.append(
            "FUSE will keep legacy projects editable, but new SST models should "
            "use the preferred connector because this one may be removed in a "
            "future SST Elements version."
        )
        details.append("")
        details.append("Use this deprecated connector anyway?")

        return text, "\n".join(details)

    def confirm_sst_deprecated_connector_use(
        self,
        *,
        node: ComponentNodeItem,
        connector_name: str,
        connector_kind: str,
        rule,
    ) -> bool:
        """Ask before a user creates a new link/attachment to a deprecated connector."""
        if rule is None:
            return True

        text, details = self.sst_deprecated_connector_warning_details(
            node=node,
            connector_name=connector_name,
            connector_kind=connector_kind,
            rule=rule,
        )

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("Deprecated SST Connector")
        message_box.setText(text)
        message_box.setInformativeText(details)
        message_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        message_box.setDefaultButton(QMessageBox.No)

        return message_box.exec() == QMessageBox.Yes

    def confirm_sst_deprecated_port_link_use(
        self,
        source_port: PortItem,
        target_port: PortItem,
    ) -> bool:
        """Warn before creating a normal link that uses a deprecated SST port."""
        for port in (source_port, target_port):
            rule = self.sst_deprecated_port_rule_for_port(port)
            if rule is None:
                continue

            if not self.confirm_sst_deprecated_connector_use(
                node=port.node,
                connector_name=port.name,
                connector_kind="port",
                rule=rule,
            ):
                return False

        return True

    def confirm_sst_deprecated_slot_attachment_use(
        self,
        slot_connector: SubcompConnectorItem,
    ) -> bool:
        """Warn before creating a SubComponent attachment to a deprecated slot."""
        rule = self.sst_deprecated_slot_rule_for_connector(slot_connector)
        if rule is None:
            return True

        return self.confirm_sst_deprecated_connector_use(
            node=slot_connector.node,
            connector_name=slot_connector.name,
            connector_kind="slot",
            rule=rule,
        )

    def sst_memhierarchy_node_uses_port_slot_modes(
        self,
        node: ComponentNodeItem | None,
    ) -> bool:
        """Return whether a node is a memHierarchy component with port/slot modes."""
        return self.sst_node_type(node).startswith("memHierarchy.")

    def sst_memhierarchy_same_name_slot_for_port(
        self,
        port: PortItem,
    ) -> SubcompConnectorItem | None:
        """Return the same-named memHierarchy slot connector for a direct port."""
        node = getattr(port, "node", None)
        if not self.sst_memhierarchy_node_uses_port_slot_modes(node):
            return None

        return self.find_subcomp_connector(
            node.node_id,
            str(getattr(port, "name", "") or "").strip(),
            role="slot",
        )

    def sst_memhierarchy_port_slot_conflicts_with_attached_slot(
        self,
        port: PortItem,
    ) -> bool:
        """Return true if linking this port would mix direct and slot modes."""
        slot_connector = self.sst_memhierarchy_same_name_slot_for_port(port)
        return bool(
            slot_connector is not None
            and self.subcomp_connector_is_connected(slot_connector)
        )

    def sst_memhierarchy_slot_conflicts_with_connected_port(
        self,
        slot_connector: SubcompConnectorItem,
    ) -> bool:
        """Return true if attaching this slot would mix direct and slot modes."""
        if getattr(slot_connector, "role", "") != "slot":
            return False

        node = getattr(slot_connector, "node", None)
        if not self.sst_memhierarchy_node_uses_port_slot_modes(node):
            return False

        port = self.find_port(
            node.node_id,
            str(getattr(slot_connector, "name", "") or "").strip(),
        )
        return bool(port is not None and port.is_connected())

    def sst_memhierarchy_slot_port_mode_link_would_conflict(
        self,
        source_port: PortItem,
        target_port: PortItem,
    ) -> bool:
        return any(
            self.sst_memhierarchy_port_slot_conflicts_with_attached_slot(port)
            for port in (source_port, target_port)
        )

    def show_sst_memhierarchy_slot_port_mode_block(
        self,
        *,
        node: ComponentNodeItem,
        side_name: str,
        attempted_mode: str,
    ) -> None:
        """Explain that same-name memHierarchy port and slot modes are exclusive."""
        node_label = f"{node.instance_name}.{side_name}"
        if attempted_mode == "slot":
            text = f"{node_label} already has a direct port link."
            action = (
                "Delete the direct port link before attaching a MemLink/MemNIC "
                "child to this same-named slot."
            )
        else:
            text = f"{node_label} already has a SubComponent slot attachment."
            action = (
                "Delete the same-named SubComponent attachment before using the "
                "direct port link."
            )

        details = (
            "memHierarchy supports two valid construction modes for highlink/"
            "lowlink-style sides:\n\n"
            f"  Direct-port mode: connect {node_label} directly to another "
            "memHierarchy port.\n"
            f"  Slot-manager mode: attach MemLink/MemNIC/MemNICFour to "
            f"{node_label}, then connect the child port(s).\n\n"
            "Use exactly one mode on a given side; do not use the same name as "
            "both a direct port and a SubComponent slot.\n\n"
            f"{action}"
        )

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("Choose One memHierarchy Link Mode")
        message_box.setText(text)
        message_box.setInformativeText(details)
        message_box.setStandardButtons(QMessageBox.Ok)
        message_box.exec()

    def sst_memhierarchy_slot_port_mode_link_guard(
        self,
        source_port: PortItem,
        target_port: PortItem,
    ) -> bool:
        """Block links that would use both memHierarchy port and slot modes."""
        for port in (source_port, target_port):
            if not self.sst_memhierarchy_port_slot_conflicts_with_attached_slot(port):
                continue

            self.show_sst_memhierarchy_slot_port_mode_block(
                node=port.node,
                side_name=port.name,
                attempted_mode="port",
            )
            return True

        return False

    def sst_memhierarchy_slot_port_mode_attachment_guard(
        self,
        slot_connector: SubcompConnectorItem,
    ) -> bool:
        """Block attachments that would use both memHierarchy port and slot modes."""
        if not self.sst_memhierarchy_slot_conflicts_with_connected_port(slot_connector):
            return False

        self.show_sst_memhierarchy_slot_port_mode_block(
            node=slot_connector.node,
            side_name=slot_connector.name,
            attempted_mode="slot",
        )
        return True

    def sst_shadowed_raw_port_link_guard(
        self,
        source_port: PortItem,
        target_port: PortItem,
    ) -> bool:
        """Block or guide links that target raw SST ports shadowed by slots.

        Returns True when the attempted link has been handled and the normal
        link creation path should stop.
        """
        for raw_port, peer_port in (
            (source_port, target_port),
            (target_port, source_port),
        ):
            rule = self.sst_runtime_slot_shadow_rule_for_port(raw_port)
            if rule is not None:
                return self.offer_sst_shadowed_raw_port_quick_fix(
                    raw_port,
                    peer_port,
                    rule,
                )

        return False

    def sst_node_type(self, node: ComponentNodeItem | None) -> str:
        """Return the SST element.component type string for a scene node."""
        component = getattr(node, "component", None)
        if component is None:
            return ""

        element = str(getattr(component, "element", "") or "").strip()
        name = str(getattr(component, "name", "") or "").strip()
        if element and name:
            return f"{element}.{name}"

        return name

    def sst_attached_child_for_slot(
        self,
        slot_connector: SubcompConnectorItem,
    ) -> tuple[ComponentNodeItem | None, SubcompAttachmentItem | None]:
        """Return the existing child attached to a slot connector, if any."""
        if slot_connector is None:
            return None, None

        parent_node_id = getattr(slot_connector.node, "node_id", None)
        slot_name = str(getattr(slot_connector, "name", "") or "").strip()

        for item in self.subcomp_attachment_items():
            attachment = getattr(item, "attachment", None)
            if attachment is None:
                continue
            if getattr(attachment, "parent_node_id", None) != parent_node_id:
                continue
            if str(getattr(attachment, "slot_name", "") or "").strip() != slot_name:
                continue

            child_node = self.find_node_by_id(getattr(attachment, "child_node_id", None))
            return child_node, item

        return None, None

    def sst_shadowed_raw_port_repair_candidate(self, issue) -> dict | None:
        """Return repair context for an existing shadowed raw-port validation issue."""
        if str(getattr(issue, "issue_type", "") or "") != "sst_export_shadowed_raw_port":
            return None

        connection = self.find_connection_by_link_id(getattr(issue, "link_id", None))
        if connection is None:
            return None

        issue_node_id = getattr(issue, "node_id", None)
        issue_port_name = str(getattr(issue, "parameter_name", "") or "").strip()

        endpoint_pairs = [
            (connection.source_port, connection.target_port),
            (connection.target_port, connection.source_port),
        ]
        if issue_node_id is not None and issue_port_name:
            endpoint_pairs = [
                (raw_port, peer_port)
                for raw_port, peer_port in endpoint_pairs
                if (
                    getattr(getattr(raw_port, "node", None), "node_id", None) == issue_node_id
                    and str(getattr(raw_port, "name", "") or "").strip() == issue_port_name
                )
            ] + [
                (raw_port, peer_port)
                for raw_port, peer_port in endpoint_pairs
                if not (
                    getattr(getattr(raw_port, "node", None), "node_id", None) == issue_node_id
                    and str(getattr(raw_port, "name", "") or "").strip() == issue_port_name
                )
            ]

        for raw_port, peer_port in endpoint_pairs:
            rule = self.sst_runtime_slot_shadow_rule_for_port(raw_port)
            if rule is None:
                continue

            slot_name = str(getattr(rule, "use_slot", "") or "").strip()
            child_type = str(getattr(rule, "child_type", "") or "").strip()
            child_port_name = str(getattr(rule, "child_port", "") or "").strip()
            if not slot_name or not child_type or not child_port_name:
                continue

            slot_connector = self.find_subcomp_connector(
                raw_port.node.node_id,
                slot_name,
                role="slot",
            )
            if slot_connector is None:
                continue

            guide = self.sst_construction_guide_for_connector(slot_connector)
            if guide is None:
                continue

            if str(getattr(guide, "child_type", "") or "").strip() != child_type:
                continue
            if str(getattr(guide, "quick_fix_child_port", "") or "").strip() != child_port_name:
                continue

            try:
                from fuse.plugins.community.sst.construction_guidance import (
                    guide_has_quick_fix,
                )
            except Exception:
                guide_has_quick_fix = lambda item: False

            if not guide_has_quick_fix(guide):
                continue

            child_node, attachment_item = self.sst_attached_child_for_slot(slot_connector)
            child_component = None
            if child_node is None:
                if not self.subcomp_connector_has_available_capacity(slot_connector):
                    continue
                child_component = self.sst_palette_component_by_type(
                    child_type,
                    getattr(raw_port.node.component, "target_id", ""),
                )
                if child_component is None:
                    continue
            elif self.sst_node_type(child_node) != child_type:
                continue

            return {
                "connection": connection,
                "raw_port": raw_port,
                "peer_port": peer_port,
                "rule": rule,
                "slot_connector": slot_connector,
                "guide": guide,
                "child_node": child_node,
                "child_component": child_component,
                "attachment_item": attachment_item,
            }

        return None

    def can_repair_sst_shadowed_raw_port_issue(self, issue) -> bool:
        """Return whether an existing raw-port validation issue can be repaired."""
        return self.sst_shadowed_raw_port_repair_candidate(issue) is not None

    def apply_sst_shadowed_raw_port_validation_fix(self, issue) -> bool:
        """Rewrite an existing shadowed raw-port link into slot-child-port form."""
        candidate = self.sst_shadowed_raw_port_repair_candidate(issue)
        if candidate is None:
            return False

        connection: ConnectionItem = candidate["connection"]
        raw_port: PortItem = candidate["raw_port"]
        peer_port: PortItem = candidate["peer_port"]
        slot_connector: SubcompConnectorItem = candidate["slot_connector"]
        guide = candidate["guide"]
        child_node: ComponentNodeItem | None = candidate["child_node"]
        child_component = candidate["child_component"]

        raw_extra_connections = [
            item for item in getattr(raw_port, "connections", []) if item is not connection
        ]
        peer_extra_connections = [
            item for item in getattr(peer_port, "connections", []) if item is not connection
        ]
        if raw_extra_connections or peer_extra_connections:
            QMessageBox.information(
                None,
                "Cannot Repair Raw SST Link",
                (
                    "FUSE can only replace this raw-port link when both endpoints "
                    "are connected solely by the validation issue's link."
                ),
            )
            return False

        self.begin_model_change_batch()
        try:
            if child_node is None:
                parent_node = slot_connector.node
                child_pos = parent_node.pos() + QPointF(ComponentNodeItem.WIDTH + 120.0, 0.0)
                child_name = self.default_sst_quickfix_child_name(
                    slot_connector,
                    child_component,
                )
                child_node = self.create_component_node(
                    child_component,
                    child_pos,
                    instance_name=child_name,
                    notify=True,
                )

                interface_connector = None
                for connector in getattr(child_node, "subcomp_connectors", []):
                    if getattr(connector, "role", "") == "interface":
                        interface_connector = connector
                        break

                if interface_connector is None:
                    QMessageBox.critical(
                        None,
                        "Cannot Attach SubComponent",
                        (
                            f"Created {child_node.instance_name}, but it does not "
                            "have a SubComponent interface connector."
                        ),
                    )
                    return False

                compatibility = self.check_subcomp_connector_compatibility(
                    slot_connector,
                    interface_connector,
                )
                if compatibility.severity == "error" or not compatibility.can_create:
                    QMessageBox.critical(
                        None,
                        compatibility.title or "Cannot Attach SubComponent",
                        compatibility.message
                        or "The selected subcomponent is not compatible with this slot.",
                    )
                    return False

                if compatibility.severity == "warning":
                    if not self.confirm_subcomp_compatibility_warning(compatibility):
                        return False

                self.create_subcomp_attachment(
                    slot_connector,
                    interface_connector,
                    compatibility,
                )

            child_port = self.find_port(
                child_node.node_id,
                getattr(guide, "quick_fix_child_port", ""),
            )
            if child_port is None:
                QMessageBox.information(
                    None,
                    "SubComponent Created",
                    (
                        f"Created or found {child_node.instance_name}, but could "
                        f"not find port {getattr(guide, 'quick_fix_child_port', '')!r} on it.\n\n"
                        "Connect the child subcomponent's real port manually, then "
                        "delete the raw-port link."
                    ),
                )
                return False

            if child_port.is_connected():
                QMessageBox.information(
                    None,
                    "Cannot Repair Raw SST Link",
                    (
                        f"{child_node.instance_name}.{child_port.name} is already "
                        "connected. Delete or review that link before applying this fix."
                    ),
                )
                return False

            link_compatibility = self.check_link_compatibility(child_port, peer_port)
            if (
                link_compatibility.severity == "error"
                or not link_compatibility.can_create
            ):
                QMessageBox.critical(
                    None,
                    link_compatibility.title or "Cannot Create Link",
                    link_compatibility.message
                    or "The child subcomponent's real port cannot be linked to the peer port.",
                )
                return False

            if link_compatibility.severity == "warning":
                if not self.confirm_link_compatibility_warning(link_compatibility):
                    return False

            old_link = connection.link
            old_name = str(getattr(old_link, "name", "") or "").strip()
            old_source_latency = getattr(old_link, "source_latency", "1ns")
            old_target_latency = getattr(old_link, "target_latency", "1ns")
            old_link_type = getattr(old_link, "link_type", "point_to_point")
            old_plugin_id = getattr(old_link, "plugin_id", "")

            self.delete_link(connection)
            new_connection = self.create_link_between_ports(
                child_port,
                peer_port,
                link_compatibility,
            )

            if old_name:
                new_connection.link.name = old_name
            new_connection.link.source_latency = old_source_latency
            new_connection.link.target_latency = old_target_latency
            new_connection.link.link_type = old_link_type
            new_connection.link.plugin_id = old_plugin_id

            self.select_component(child_node)
            return True
        finally:
            self.end_model_change_batch()


    def sst_deprecated_slot_repair_candidate(self, issue):
        """Return the replacement slot information for a deprecated-slot issue."""
        if str(getattr(issue, "issue_type", "") or "") != "sst_export_deprecated_connector":
            return None

        attachment_id = getattr(issue, "attachment_id", None)
        if attachment_id is None:
            return None

        attachment_item = self.find_subcomp_attachment_by_id(attachment_id)
        if attachment_item is None:
            return None

        old_slot = getattr(attachment_item, "source_connector", None)
        if old_slot is None or getattr(old_slot, "role", "") != "slot":
            return None

        rule = self.sst_deprecated_slot_rule_for_connector(old_slot)
        if rule is None:
            return None

        replacement_name = str(getattr(rule, "replacement_name", "") or "").strip()
        replacement_kind = str(getattr(rule, "replacement_kind", "") or "").strip()
        if not replacement_name or replacement_kind not in {"", "slot"}:
            return None

        replacement_slot = self.find_subcomp_connector(
            old_slot.node.node_id,
            replacement_name,
            role="slot",
        )
        if replacement_slot is None:
            return None

        if self.subcomp_connector_is_connected(replacement_slot):
            return None

        if self.sst_memhierarchy_slot_conflicts_with_connected_port(replacement_slot):
            return None

        return {
            "attachment_item": attachment_item,
            "old_slot": old_slot,
            "replacement_slot": replacement_slot,
            "rule": rule,
        }

    def can_repair_sst_deprecated_slot_issue(self, issue) -> bool:
        """Return whether a deprecated-slot validation issue can be auto-repaired."""
        return self.sst_deprecated_slot_repair_candidate(issue) is not None

    def apply_sst_deprecated_slot_validation_fix(self, issue) -> bool:
        """Move an existing SubComponent attachment from a deprecated slot alias."""
        candidate = self.sst_deprecated_slot_repair_candidate(issue)
        if candidate is None:
            return False

        attachment_item: SubcompAttachmentItem = candidate["attachment_item"]
        old_slot: SubcompConnectorItem = candidate["old_slot"]
        replacement_slot: SubcompConnectorItem = candidate["replacement_slot"]

        attachment = attachment_item.attachment
        replacement_metadata = getattr(replacement_slot, "metadata", {}) or {}

        self.begin_model_change_batch()
        try:
            attachment.slot_name = replacement_slot.name
            attachment.required_interface = (
                replacement_metadata.get("required_interface", "")
                or replacement_metadata.get("iface", "")
                or replacement_metadata.get("interface", "")
                or attachment.required_interface
                or ""
            )

            attachment_item.source_connector = replacement_slot
            attachment_item.update_position()
            attachment_item.update_tooltip()

            for connector in (old_slot, replacement_slot):
                node = getattr(connector, "node", None)
                if node is not None and hasattr(node, "apply_subcomp_connector_visibility"):
                    node.apply_subcomp_connector_visibility()

            self.select_subcomp_attachment(attachment_item)
            self.notify_model_changed()
            return True
        finally:
            self.end_model_change_batch()


    def sst_shadowed_raw_port_message(
        self,
        raw_port: PortItem,
        peer_port: PortItem,
        rule,
        *,
        can_quick_fix: bool,
    ) -> tuple[str, str]:
        raw_label = f"{raw_port.node.instance_name}.{raw_port.name}"
        peer_label = f"{peer_port.node.instance_name}.{peer_port.name}"
        slot_name = str(getattr(rule, "use_slot", "") or "")
        child_type = str(getattr(rule, "child_type", "") or "")
        child_port = str(getattr(rule, "child_port", "") or "")

        if slot_name:
            text = (
                f"{raw_label} is a raw SST catalog port shadowed by runtime "
                f"slot {slot_name}."
            )
        else:
            text = f"{raw_label} is a raw SST catalog port shadowed by a runtime slot."

        details = [str(getattr(rule, "explanation", "") or "").strip()]
        details.append("")
        details.append("Use the slot-based construction instead:")

        if slot_name and child_type:
            details.append(f"  {raw_port.node.instance_name}.{slot_name} -> {child_type}")
        elif slot_name:
            details.append(f"  {raw_port.node.instance_name}.{slot_name} -> required SubComponent")
        else:
            details.append("  Attach the required runtime SubComponent to the owning slot.")

        if child_type and child_port:
            details.append(f"  {child_type}.{child_port} <-> {peer_label}")
        elif child_port:
            details.append(f"  child.{child_port} <-> {peer_label}")
        else:
            details.append(f"  child real port <-> {peer_label}")

        if can_quick_fix:
            details.append("")
            details.append("Create the required child subcomponent and link now?")

        return text, "\n".join(line for line in details if line is not None)

    def show_sst_shadowed_raw_port_block(
        self,
        raw_port: PortItem,
        peer_port: PortItem,
        rule,
        *,
        reason: str = "",
    ) -> None:
        text, details = self.sst_shadowed_raw_port_message(
            raw_port,
            peer_port,
            rule,
            can_quick_fix=False,
        )
        if reason:
            details = f"{details}\n\n{reason}"

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("Invalid Raw SST Port Connection")
        message_box.setText(text)
        message_box.setInformativeText(details)
        message_box.setStandardButtons(QMessageBox.Ok)
        message_box.exec()

    def offer_sst_shadowed_raw_port_quick_fix(
        self,
        raw_port: PortItem,
        peer_port: PortItem,
        rule,
    ) -> bool:
        """Explain a shadowed raw-port link and optionally apply a guided fix."""
        slot_name = str(getattr(rule, "use_slot", "") or "")
        child_type = str(getattr(rule, "child_type", "") or "")
        child_port = str(getattr(rule, "child_port", "") or "")

        if not slot_name:
            self.show_sst_shadowed_raw_port_block(raw_port, peer_port, rule)
            return True

        slot_connector = self.find_subcomp_connector(
            raw_port.node.node_id,
            slot_name,
            role="slot",
        )
        if slot_connector is None:
            self.show_sst_shadowed_raw_port_block(
                raw_port,
                peer_port,
                rule,
                reason=(
                    f"FUSE could not find the {slot_name!r} SubComponent slot on "
                    f"{raw_port.node.instance_name}. Create the slot-based "
                    "construction manually."
                ),
            )
            return True

        guide = self.sst_construction_guide_for_connector(slot_connector)
        if guide is None:
            self.show_sst_shadowed_raw_port_block(
                raw_port,
                peer_port,
                rule,
                reason="FUSE does not have enough guidance to auto-create this slot child.",
            )
            return True

        if child_type and str(getattr(guide, "child_type", "") or "") != child_type:
            self.show_sst_shadowed_raw_port_block(
                raw_port,
                peer_port,
                rule,
                reason="The raw-port visibility rule and slot construction guide do not agree.",
            )
            return True

        if child_port and str(getattr(guide, "quick_fix_child_port", "") or "") != child_port:
            self.show_sst_shadowed_raw_port_block(
                raw_port,
                peer_port,
                rule,
                reason="The slot construction guide does not provide a compatible child port.",
            )
            return True

        try:
            from fuse.plugins.community.sst.construction_guidance import (
                guide_has_quick_fix,
            )
        except Exception:
            guide_has_quick_fix = lambda item: False

        if not guide_has_quick_fix(guide):
            self.show_sst_shadowed_raw_port_block(raw_port, peer_port, rule)
            return True

        if not self.subcomp_connector_has_available_capacity(slot_connector):
            self.show_sst_shadowed_raw_port_block(
                raw_port,
                peer_port,
                rule,
                reason=(
                    f"{raw_port.node.instance_name}.{slot_name} already has a "
                    "SubComponent attachment. Connect the existing child "
                    f"{getattr(guide, 'quick_fix_child_port', 'port')} to "
                    f"{peer_port.node.instance_name}.{peer_port.name} instead."
                ),
            )
            return True

        child_component = self.sst_palette_component_by_type(
            getattr(guide, "child_type", ""),
            getattr(raw_port.node.component, "target_id", ""),
        )
        if child_component is None:
            self.show_sst_shadowed_raw_port_block(
                raw_port,
                peer_port,
                rule,
                reason=(
                    f"FUSE could not find {getattr(guide, 'child_type', '')} in "
                    "the active SST palette, so create that subcomponent from "
                    "the palette and attach it to this slot manually."
                ),
            )
            return True

        text, details = self.sst_shadowed_raw_port_message(
            raw_port,
            peer_port,
            rule,
            can_quick_fix=True,
        )
        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("Invalid Raw SST Port Connection")
        message_box.setText(text)
        message_box.setInformativeText(details)

        create_button = message_box.addButton(
            f"Create {getattr(guide, 'child_type', '')} and Connect",
            QMessageBox.AcceptRole,
        )
        message_box.addButton(QMessageBox.Cancel)
        message_box.exec()

        if message_box.clickedButton() is not create_button:
            return True

        return self.create_sst_slot_port_quick_fix(
            slot_connector,
            peer_port,
            guide,
            child_component,
        )


    def sst_construction_guide_for_connector(self, connector: SubcompConnectorItem):
        """Return SST construction guidance for a subcomponent slot connector."""
        try:
            from fuse.plugins.community.sst.construction_guidance import (
                guide_for_slot_connector,
            )

            return guide_for_slot_connector(connector)
        except Exception:
            return None

    def sst_palette_component_by_type(self, full_type: str, target_id: str | None = None):
        """Find a palette ComponentDefinition for an SST element.component type."""
        element, _, name = str(full_type or "").partition(".")
        if not element or not name:
            return None

        plugin_id = getattr(self, "active_plugin_id", "") or "sst"
        target_candidates = []
        if target_id:
            target_candidates.append(str(target_id))
        target_candidates.extend([None, ""])

        seen_targets: set[str | None] = set()
        for candidate_target_id in target_candidates:
            if candidate_target_id in seen_targets:
                continue
            seen_targets.add(candidate_target_id)

            try:
                items = load_all_palette_items(
                    plugin_id=plugin_id,
                    target_id=candidate_target_id,
                )
            except Exception:
                items = []

            for item in items:
                if (
                    str(getattr(item, "element", "") or "") == element
                    and str(getattr(item, "name", "") or "") == name
                ):
                    return item

        return None

    def default_sst_quickfix_child_name(
        self,
        slot_connector: SubcompConnectorItem,
        child_component,
    ) -> str:
        """Choose a readable instance name for an auto-created SST child."""
        parent_name = str(getattr(slot_connector.node, "instance_name", "") or "")
        slot_name = str(getattr(slot_connector, "name", "") or "")
        child_name = str(getattr(child_component, "name", "") or "subcomponent")

        suffix = ""
        match = re.search(r"(\d+)(?!.*\d)", parent_name)
        if match:
            suffix = match.group(1)

        if child_name == "linkcontrol":
            base = "linkcontrol"
        elif child_name == "VirtNic":
            base = "VirtNic"
        elif child_name == "ctrlMsg":
            base = "ctrlMsg"
        else:
            base = child_name or slot_name or "subcomponent"

        if suffix:
            requested = f"{base}_{suffix}"
        else:
            requested = base

        used = self.existing_component_and_composite_internal_names()
        return self.allocate_component_name_from_template(
            template_for_source_name(requested),
            used,
        )[0]

    def slot_port_quickfix_message(
        self,
        slot_connector: SubcompConnectorItem,
        target_port: PortItem,
        guide,
    ) -> tuple[str, str]:
        """Build the explanation shown when a slot is dragged to a real port."""
        slot_label = (
            f"{slot_connector.node.instance_name}.{slot_connector.name}"
        )
        target_label = f"{target_port.node.instance_name}.{target_port.name}"
        child_short_name = str(getattr(guide, "child_type", "") or "").split(".")[-1]
        child_instance = self.default_sst_quickfix_child_name(
            slot_connector,
            self.sst_palette_component_by_type(
                getattr(guide, "child_type", ""),
                getattr(slot_connector.node.component, "target_id", ""),
            )
            or type("_ComponentName", (), {"name": child_short_name})(),
        )

        text = f"{slot_label} is a SubComponent slot, not a real SST link port."
        details = (
            f"{getattr(guide, 'explanation', '')}\n\n"
            "FUSE can create the required child subcomponent and then connect "
            "that child's real port to the port you clicked.\n\n"
            "Planned construction:\n"
            f"  {slot_label} -> {child_instance} : {getattr(guide, 'child_type', '')}\n"
            f"  {child_instance}.{getattr(guide, 'quick_fix_child_port', '')} <-> {target_label}\n\n"
            "Create this subcomponent and link now?"
        )
        return text, details

    def offer_sst_slot_to_port_quick_fix(
        self,
        slot_connector: SubcompConnectorItem,
        target_port: PortItem,
    ) -> bool:
        """Offer to create the child subcomponent required between a slot and port.

        Returns True when the mixed endpoint gesture was handled, whether the
        user accepted the quick fix or cancelled the guided dialog. Returning
        False lets the normal generic mixed-endpoint warning run.
        """
        if slot_connector is None or target_port is None:
            return False

        if getattr(slot_connector, "role", "") != "slot":
            return False

        guide = self.sst_construction_guide_for_connector(slot_connector)
        try:
            from fuse.plugins.community.sst.construction_guidance import (
                guide_has_quick_fix,
            )
        except Exception:
            guide_has_quick_fix = lambda item: False

        if not guide_has_quick_fix(guide):
            return False

        if target_port.is_connected():
            self.warn_port_already_connected()
            return True

        child_component = self.sst_palette_component_by_type(
            getattr(guide, "child_type", ""),
            getattr(slot_connector.node.component, "target_id", ""),
        )
        if child_component is None:
            QMessageBox.information(
                None,
                "Create SubComponent First",
                (
                    f"{slot_connector.node.instance_name}.{slot_connector.name} "
                    "is a SubComponent slot, not a real SST link port.\n\n"
                    f"{getattr(guide, 'concise_fix', '')}\n\n"
                    f"FUSE could not find {getattr(guide, 'child_type', '')} in "
                    "the active SST palette, so create that subcomponent from the "
                    "palette and attach it to this slot manually."
                ),
            )
            return True

        text, details = self.slot_port_quickfix_message(
            slot_connector,
            target_port,
            guide,
        )

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Information)
        message_box.setWindowTitle("Create Required SST SubComponent?")
        message_box.setText(text)
        message_box.setInformativeText(details)

        create_button = message_box.addButton(
            f"Create {getattr(guide, 'child_type', '')} and Connect",
            QMessageBox.AcceptRole,
        )
        message_box.addButton(QMessageBox.Cancel)
        message_box.exec()

        if message_box.clickedButton() is not create_button:
            return True

        return self.create_sst_slot_port_quick_fix(
            slot_connector,
            target_port,
            guide,
            child_component,
        )

    def create_sst_slot_port_quick_fix(
        self,
        slot_connector: SubcompConnectorItem,
        target_port: PortItem,
        guide,
        child_component,
    ) -> bool:
        """Create the SST child subcomponent and real link for a guided fix."""
        parent_node = slot_connector.node
        child_pos = parent_node.pos() + QPointF(ComponentNodeItem.WIDTH + 120.0, 0.0)
        child_name = self.default_sst_quickfix_child_name(
            slot_connector,
            child_component,
        )

        self.begin_model_change_batch()
        try:
            child_node = self.create_component_node(
                child_component,
                child_pos,
                instance_name=child_name,
                notify=True,
            )

            interface_connector = None
            for connector in getattr(child_node, "subcomp_connectors", []):
                if getattr(connector, "role", "") == "interface":
                    interface_connector = connector
                    break

            if interface_connector is None:
                QMessageBox.critical(
                    None,
                    "Cannot Attach SubComponent",
                    (
                        f"Created {child_node.instance_name}, but it does not "
                        "have a SubComponent interface connector."
                    ),
                )
                return True

            compatibility = self.check_subcomp_connector_compatibility(
                slot_connector,
                interface_connector,
            )
            if compatibility.severity == "error" or not compatibility.can_create:
                QMessageBox.critical(
                    None,
                    compatibility.title or "Cannot Attach SubComponent",
                    compatibility.message
                    or "The selected subcomponent is not compatible with this slot.",
                )
                return True

            if compatibility.severity == "warning":
                if not self.confirm_subcomp_compatibility_warning(compatibility):
                    return True

            self.create_subcomp_attachment(
                slot_connector,
                interface_connector,
                compatibility,
            )

            child_port = self.find_port(
                child_node.node_id,
                getattr(guide, "quick_fix_child_port", ""),
            )
            if child_port is None:
                QMessageBox.information(
                    None,
                    "SubComponent Created",
                    (
                        f"Created and attached {child_node.instance_name}, but "
                        f"could not find port "
                        f"{getattr(guide, 'quick_fix_child_port', '')!r} on it.\n\n"
                        "Connect the child subcomponent's real port manually."
                    ),
                )
                return True

            if child_port.is_connected() or target_port.is_connected():
                self.warn_port_already_connected()
                return True

            link_compatibility = self.check_link_compatibility(child_port, target_port)
            if (
                link_compatibility.severity == "error"
                or not link_compatibility.can_create
            ):
                QMessageBox.critical(
                    None,
                    link_compatibility.title or "Cannot Create Link",
                    link_compatibility.message
                    or "The created child port cannot be linked to the target port.",
                )
                return True

            if link_compatibility.severity == "warning":
                if not self.confirm_link_compatibility_warning(link_compatibility):
                    return True

            self.create_link_between_ports(child_port, target_port, link_compatibility)
            self.select_component(child_node)
            return True
        finally:
            self.end_model_change_batch()



    def create_sst_slot_child_quick_fix(
        self,
        slot_connector: SubcompConnectorItem,
        guide,
        *,
        select_child: bool = True,
    ) -> ComponentNodeItem | None:
        """Create and attach the child subcomponent described by an SST guide."""
        if slot_connector is None or guide is None:
            return None

        if getattr(slot_connector, "role", "") != "slot":
            return None

        if not self.subcomp_connector_has_available_capacity(slot_connector):
            QMessageBox.information(
                None,
                "Slot Already Filled",
                (
                    f"{slot_connector.node.instance_name}.{slot_connector.name} "
                    "already has the required SubComponent attachment."
                ),
            )
            return None

        child_component = self.sst_palette_component_by_type(
            getattr(guide, "child_type", ""),
            getattr(slot_connector.node.component, "target_id", ""),
        )
        if child_component is None:
            QMessageBox.information(
                None,
                "Create SubComponent Manually",
                (
                    f"FUSE knows that {slot_connector.node.instance_name}."
                    f"{slot_connector.name} should contain "
                    f"{getattr(guide, 'child_type', '')}, but that component was "
                    "not found in the active SST palette.\n\n"
                    "Create the child subcomponent from the palette and attach it "
                    "to this slot manually."
                ),
            )
            return None

        parent_node = slot_connector.node
        child_pos = parent_node.pos() + QPointF(ComponentNodeItem.WIDTH + 120.0, 0.0)
        child_name = self.default_sst_quickfix_child_name(
            slot_connector,
            child_component,
        )

        self.begin_model_change_batch()
        try:
            child_node = self.create_component_node(
                child_component,
                child_pos,
                instance_name=child_name,
                notify=True,
            )

            interface_connector = None
            for connector in getattr(child_node, "subcomp_connectors", []):
                if getattr(connector, "role", "") == "interface":
                    interface_connector = connector
                    break

            if interface_connector is None:
                QMessageBox.critical(
                    None,
                    "Cannot Attach SubComponent",
                    (
                        f"Created {child_node.instance_name}, but it does not "
                        "have a SubComponent interface connector."
                    ),
                )
                return None

            compatibility = self.check_subcomp_connector_compatibility(
                slot_connector,
                interface_connector,
            )
            if compatibility.severity == "error" or not compatibility.can_create:
                QMessageBox.critical(
                    None,
                    compatibility.title or "Cannot Attach SubComponent",
                    compatibility.message
                    or "The selected subcomponent is not compatible with this slot.",
                )
                return None

            if compatibility.severity == "warning":
                if not self.confirm_subcomp_compatibility_warning(compatibility):
                    return None

            self.create_subcomp_attachment(
                slot_connector,
                interface_connector,
                compatibility,
            )

            if select_child:
                self.select_component(child_node)

            return child_node
        finally:
            self.end_model_change_batch()


    def warn_mixed_endpoint_types(self):
        if self.suppress_mixed_endpoint_warning:
            return

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("Invalid Connection Type")
        message_box.setText(
            "SubComponent Slots can only be connected to SubComponent Connectors."
        )
        message_box.setInformativeText(
            "Use normal component ports for SST links. Use purple "
            "subcomp_connector endpoints for SubComponent slot assignments."
        )
        message_box.setStandardButtons(QMessageBox.Ok)

        checkbox = QCheckBox("Do not show this warning again")
        message_box.setCheckBox(checkbox)

        message_box.exec()

        if checkbox.isChecked():
            self.suppress_mixed_endpoint_warning = True

    def warn_port_already_connected(self):
        if self.suppress_port_occupied_warning:
            return

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Critical)
        message_box.setWindowTitle("Port Already Connected")
        message_box.setText("Port already connected!")
        message_box.setInformativeText(
            "Each port can only be connected to one link. Delete the existing link "
            "or choose a different unoccupied port."
        )
        message_box.setStandardButtons(QMessageBox.Ok)

        checkbox = QCheckBox("Do not show this warning again")
        message_box.setCheckBox(checkbox)

        message_box.exec()

        if checkbox.isChecked():
            self.suppress_port_occupied_warning = True

    def clear_subcomp_connector_compatibility_highlights(self):
        for node in self.component_items():
            for connector in self.subcomp_connectors_for_node(node):
                connector.set_compatibility_highlight("")

    def highlight_compatible_subcomp_connectors(self, source_connector: SubcompConnectorItem):
        for node in self.component_items():
            for connector in self.subcomp_connectors_for_node(node):
                if connector is source_connector:
                    continue

                if not self.subcomp_connector_has_available_capacity(connector):
                    continue

                pair = self.compatible_subcomp_connector_pair(source_connector, connector)
                if pair is None:
                    continue

                slot_connector, interface_connector = pair
                if self.sst_memhierarchy_slot_conflicts_with_connected_port(
                    slot_connector,
                ):
                    connector.set_compatibility_highlight("incompatible")
                    continue

                compatibility = self.check_subcomp_connector_compatibility(
                    slot_connector,
                    interface_connector,
                )

                if compatibility.severity == "error" or not compatibility.can_create:
                    continue

                if compatibility.severity == "warning":
                    connector.set_compatibility_highlight("warning")
                else:
                    connector.set_compatibility_highlight("compatible")

    def compatible_subcomp_connector_pair(
        self,
        source: SubcompConnectorItem,
        target: SubcompConnectorItem,
    ) -> tuple[SubcompConnectorItem, SubcompConnectorItem] | None:
        if source is target:
            return None

        source_role = getattr(source, "role", "")
        target_role = getattr(target, "role", "")

        if source_role == "slot" and target_role == "interface":
            return source, target

        if source_role == "interface" and target_role == "slot":
            return target, source

        return None

    def check_subcomp_connector_compatibility(
        self,
        slot_connector: SubcompConnectorItem,
        interface_connector: SubcompConnectorItem,
    ) -> LinkCompatibilityResult:
        plugin_id = (
            self.active_plugin_id
            or getattr(slot_connector.node.component, "plugin_id", "")
            or getattr(interface_connector.node.component, "plugin_id", "")
        )

        if not plugin_id:
            return LinkCompatibilityResult()

        try:
            plugin = get_plugin_by_id(plugin_id)
        except Exception:
            return LinkCompatibilityResult()

        if not hasattr(plugin, "check_subcomponent_slot_compatibility"):
            return LinkCompatibilityResult()

        return plugin.check_subcomponent_slot_compatibility(
            getattr(slot_connector, "metadata", {}) or {},
            getattr(interface_connector, "metadata", {}) or {},
        )

    def default_subcomp_attachment_name(
        self,
        slot_connector: SubcompConnectorItem,
        interface_connector: SubcompConnectorItem,
    ) -> str:
        base = (
            f"subcomp_{slot_connector.node.instance_name}_"
            f"{slot_connector.name}_{interface_connector.node.instance_name}"
        )
        return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)

    def create_subcomp_attachment(
        self,
        slot_connector: SubcompConnectorItem,
        interface_connector: SubcompConnectorItem,
        compatibility: LinkCompatibilityResult,
    ) -> SubcompAttachmentItem:
        attachment_id = self._next_subcomp_attachment_id
        self._next_subcomp_attachment_id += 1

        slot_metadata = getattr(slot_connector, "metadata", {}) or {}
        interface_metadata = getattr(interface_connector, "metadata", {}) or {}

        attachment_plugin_metadata = dict(slot_metadata.get("plugin_metadata", {}) or {})
        if self._connector_metadata_truthy(slot_metadata.get("visual_only", False)):
            attachment_plugin_metadata["visual_only"] = True
        if self._connector_metadata_truthy(slot_metadata.get("allow_multiple", False)):
            attachment_plugin_metadata["allow_multiple"] = True

        attachment = ModelSubcompAttachment(
            attachment_id=attachment_id,
            name=self.default_subcomp_attachment_name(slot_connector, interface_connector),
            parent_node_id=slot_connector.node.node_id,
            parent_component_name=slot_connector.node.instance_name,
            slot_name=slot_connector.name,
            child_node_id=interface_connector.node.node_id,
            child_component_name=interface_connector.node.instance_name,
            required_interface=(
                slot_metadata.get("required_interface", "")
                or slot_metadata.get("iface", "")
                or slot_metadata.get("interface", "")
                or ""
            ),
            provided_interface=(
                interface_metadata.get("provided_interface", "")
                or interface_metadata.get("iface", "")
                or interface_metadata.get("interface", "")
                or ""
            ),
            compatibility_severity=compatibility.severity,
            compatibility_code=compatibility.code,
            compatibility_message=compatibility.message,
            plugin_id=(
                self.active_plugin_id
                or getattr(slot_connector.node.component, "plugin_id", "")
            ),
            plugin_metadata=attachment_plugin_metadata,
        )

        self.subcomp_attachments.append(attachment)

        item = SubcompAttachmentItem(
            attachment=attachment,
            slot_connector=slot_connector,
            interface_connector=interface_connector,
        )
        self.addItem(item)
        item.update_position()
        self.select_subcomp_attachment(item)
        self.notify_plugin_subcomp_attachment_created(attachment)

        if hasattr(slot_connector.node, "apply_subcomp_connector_visibility"):
            slot_connector.node.apply_subcomp_connector_visibility()
        if hasattr(interface_connector.node, "apply_subcomp_connector_visibility"):
            interface_connector.node.apply_subcomp_connector_visibility()

        self.notify_model_changed()

        return item

    def plugin_for_node(self, node: ComponentNodeItem):
        plugin_id = (
            getattr(getattr(node, "component", None), "plugin_id", "")
            or getattr(self, "active_plugin_id", "")
            or ""
        )
        if not plugin_id:
            return None

        try:
            return get_plugin_by_id(plugin_id)
        except Exception:
            return None

    def plugin_for_subcomp_attachment(self, attachment: ModelSubcompAttachment):
        plugin_id = (
            getattr(attachment, "plugin_id", "")
            or getattr(self, "active_plugin_id", "")
            or ""
        )
        if not plugin_id:
            return None

        try:
            return get_plugin_by_id(plugin_id)
        except Exception:
            return None

    def notify_plugin_variable_port_count_changed(
        self,
        node: ComponentNodeItem,
        base_name: str,
        count: int,
        port_template: dict | None = None,
    ) -> None:
        plugin = self.plugin_for_node(node)
        hook = getattr(plugin, "on_variable_port_count_changed", None)
        if callable(hook):
            hook(self, node, base_name, count, port_template or {})

    def notify_plugin_subcomp_attachment_created(self, attachment: ModelSubcompAttachment) -> None:
        plugin = self.plugin_for_subcomp_attachment(attachment)
        hook = getattr(plugin, "on_subcomponent_attachment_created", None)
        if callable(hook):
            hook(self, attachment)

    def notify_plugin_subcomp_attachment_deleted(self, attachment: ModelSubcompAttachment) -> None:
        plugin = self.plugin_for_subcomp_attachment(attachment)
        hook = getattr(plugin, "on_subcomponent_attachment_deleted", None)
        if callable(hook):
            hook(self, attachment)

    def delete_subcomp_attachment(self, item: SubcompAttachmentItem):
        if item is None:
            return

        self.invalidate_pending_link_routes(reason="delete_subcomp_attachment")
        try:
            breadcrumb("model_scene.delete_subcomp_attachment", attachment=self._diagnostic_attachment_snapshot(item))
        except Exception:
            pass
        attachment = item.attachment
        connectors = (
            getattr(item, "source_connector", None),
            getattr(item, "target_connector", None),
        )

        if attachment in self.subcomp_attachments:
            self.subcomp_attachments.remove(attachment)

        self._highlighted_attachment_items.discard(item)
        if self.selected_subcomp_attachment is item:
            self.selected_subcomp_attachment = None

        if item.scene() is self:
            item.setSelected(False)
            item.set_highlighted(False)
            self.removeItem(item)

        if self.properties_panel is not None:
            self.properties_panel.show_empty()

        self.notify_plugin_subcomp_attachment_deleted(attachment)

        for connector in connectors:
            node = getattr(connector, "node", None)
            node_id = int(getattr(node, "node_id", 0) or 0) if node is not None else 0
            if node_id in self._deleting_node_ids:
                continue
            if (
                node is not None
                and node.scene() is self
                and hasattr(node, "apply_subcomp_connector_visibility")
            ):
                node.apply_subcomp_connector_visibility()

        self.notify_model_changed()

    def subcomp_connector_clicked(self, connector: SubcompConnectorItem):
        if self.pending_source_port is not None:
            self.warn_mixed_endpoint_types()
            self.cancel_pending_connection()
            return

        if not self.subcomp_connector_has_available_capacity(connector):
            return

        if self.pending_subcomp_connector is None:
            self.pending_subcomp_connector = connector
            self.clear_subcomp_connector_compatibility_highlights()
            self.highlight_compatible_subcomp_connectors(connector)

            self.pending_line = QGraphicsLineItem()
            self.pending_line.setPen(QPen(QColor("#8b5cf6"), 2, Qt.DashLine))
            self.pending_line.setZValue(4)
            self.pending_line.setAcceptedMouseButtons(Qt.NoButton)

            start = connector.scene_center()
            self.pending_line.setLine(start.x(), start.y(), start.x(), start.y())
            self.addItem(self.pending_line)
            return

        source_connector = self.pending_subcomp_connector
        target_connector = connector

        pair = self.compatible_subcomp_connector_pair(source_connector, target_connector)

        if pair is None:
            QMessageBox.warning(
                None,
                "Cannot Attach SubComponent",
                (
                    "SubComponent attachments must connect a parent "
                    "subcomp_connector slot to a subcomponent interface connector."
                ),
            )
            self.cancel_pending_subcomp_attachment()
            return

        slot_connector, interface_connector = pair

        if not self.subcomp_connector_has_available_capacity(slot_connector):
            self.cancel_pending_subcomp_attachment()
            return

        if not self.subcomp_connector_has_available_capacity(interface_connector):
            self.cancel_pending_subcomp_attachment()
            return

        if self.sst_memhierarchy_slot_port_mode_attachment_guard(slot_connector):
            self.cancel_pending_subcomp_attachment()
            return

        if not self.confirm_sst_deprecated_slot_attachment_use(slot_connector):
            self.cancel_pending_subcomp_attachment()
            return

        compatibility = self.check_subcomp_connector_compatibility(
            slot_connector,
            interface_connector,
        )

        if compatibility.severity == "error" or not compatibility.can_create:
            QMessageBox.critical(
                None,
                compatibility.title or "Cannot Attach SubComponent",
                compatibility.message
                or "The selected subcomponent is not compatible with this slot.",
            )
            self.cancel_pending_subcomp_attachment()
            return

        if compatibility.severity == "warning":
            if not self.confirm_subcomp_compatibility_warning(compatibility):
                self.cancel_pending_subcomp_attachment()
                return

        self.cancel_pending_visual_line_only()
        self.clear_subcomp_connector_compatibility_highlights()
        self.create_subcomp_attachment(
            slot_connector,
            interface_connector,
            compatibility,
        )
        self.pending_subcomp_connector = None

    def begin_subcomp_attachment(self, connector: SubcompConnectorItem):
        self.subcomp_connector_clicked(connector)

    def cancel_pending_visual_line_only(self):
        if self.pending_line is not None:
            self.removeItem(self.pending_line)
            self.pending_line = None

    def cancel_pending_connection(self):
        self.cancel_pending_visual_line_only()
        self.pending_source_port = None
        self.clear_port_compatibility_highlights()

    def cancel_pending_subcomp_attachment(self):
        self.cancel_pending_visual_line_only()
        self.pending_subcomp_connector = None
        self.clear_subcomp_connector_compatibility_highlights()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            if self.copy_selection_to_clipboard():
                event.accept()
                return

        if event.matches(QKeySequence.Paste):
            self.paste_clipboard()
            event.accept()
            return

        if event.key() == Qt.Key_G and event.modifiers() == Qt.ControlModifier:
            if self.group_selection():
                event.accept()
                return

        if event.key() == Qt.Key_G and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
            if self.ungroup_selection():
                event.accept()
                return

        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            breadcrumb("model_scene.delete_key_pressed", key=int(event.key()), snapshot=self.diagnostic_snapshot())
            with active_operation("model_scene.delete_selection", snapshot=self.diagnostic_snapshot()):
                deleted = self.delete_selection()
            if deleted:
                event.accept()
                return

        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        if self.pending_line is not None and self.pending_source_port is not None:
            start = self.pending_source_port.scene_center()
            end = event.scenePos()
            self.pending_line.setLine(start.x(), start.y(), end.x(), end.y())

        if self.pending_line is not None and self.pending_subcomp_connector is not None:
            start = self.pending_subcomp_connector.scene_center()
            end = event.scenePos()
            self.pending_line.setLine(start.x(), start.y(), end.x(), end.y())

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        clicked_items = self.items(event.scenePos())

        clicked_a_port = any(isinstance(item, PortItem) for item in clicked_items)
        clicked_a_subcomp_connector = any(
            isinstance(item, SubcompConnectorItem)
            for item in clicked_items
        )
        clicked_a_component = any(
            isinstance(item, ComponentNodeItem)
            for item in clicked_items
        )
        clicked_a_link = any(
            isinstance(item, ConnectionItem)
            for item in clicked_items
        )
        clicked_a_subcomp_attachment = any(
            isinstance(item, SubcompAttachmentItem)
            for item in clicked_items
        )

        # If the user mixes endpoint kinds, explain why the connection is not allowed.
        # Do this here because the scene may otherwise cancel the pending state before
        # the clicked item receives its own mouse event.
        if self.pending_source_port is not None and clicked_a_subcomp_connector:
            clicked_connector = next(
                (
                    item
                    for item in clicked_items
                    if isinstance(item, SubcompConnectorItem)
                ),
                None,
            )
            if (
                clicked_connector is not None
                and self.offer_sst_slot_to_port_quick_fix(
                    clicked_connector,
                    self.pending_source_port,
                )
            ):
                self.cancel_pending_connection()
                event.accept()
                return

            self.warn_mixed_endpoint_types()
            self.cancel_pending_connection()
            event.accept()
            return

        if self.pending_subcomp_connector is not None and clicked_a_port:
            clicked_port = next(
                (item for item in clicked_items if isinstance(item, PortItem)),
                None,
            )
            if (
                clicked_port is not None
                and self.offer_sst_slot_to_port_quick_fix(
                    self.pending_subcomp_connector,
                    clicked_port,
                )
            ):
                self.cancel_pending_subcomp_attachment()
                event.accept()
                return

            self.warn_mixed_endpoint_types()
            self.cancel_pending_subcomp_attachment()
            event.accept()
            return

        # Clicking empty canvas, or anything unrelated to the pending endpoint kind,
        # cancels pending creation state.
        if (
                self.pending_source_port is not None
                and not clicked_a_port
                and not clicked_a_subcomp_connector
        ):
            self.cancel_pending_connection()

        if (
                self.pending_subcomp_connector is not None
                and not clicked_a_subcomp_connector
                and not clicked_a_port
        ):
            self.cancel_pending_subcomp_attachment()

        if (
            not clicked_a_port
            and not clicked_a_subcomp_connector
            and not clicked_a_component
            and not clicked_a_link
            and not clicked_a_subcomp_attachment
        ):
            self.selected_component = None
            self.clear_all_selection_highlights()

            if self.properties_panel is not None:
                self.properties_panel.show_empty()

            if self.selection_changed_callback is not None:
                self.selection_changed_callback(None)

        super().mousePressEvent(event)