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
"""Project settings dialog for framework targets and toolchain execution.

This module owns the Qt dialog that edits project-wide FUSE settings, including
the active simulator plugin, selected framework/catalog target, and local or
SSH-based toolchain configuration. The dialog keeps sensitive SSH material out
of project files and relies on the user's system SSH configuration instead.
"""

from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
import shutil

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fuse.core.model.project_settings import (
    ProjectSettings,
    ToolchainSettings,
)
from fuse.core.persistence.db_access import load_framework_targets
from fuse.core.toolchains.discovery import (
    discover_local_gem5_binary,
    discover_local_gem5_root,
    discover_local_sst,
    discover_local_sst_info,
)
from fuse.core.toolchains.providers import provider_from_toolchain
from fuse.core.toolchains.version_match import compare_version_prefix
from fuse.plugins.community.sst.component_catalog import (
    DiscoveredComponentEntry,
    SSTComponentDiscovery,
    catalog_source_summary_for_target,
    delete_custom_catalog_target,
    describe_component_metadata_diff,
    discover_sst_components_for_toolchain,
    has_component_catalog,
    import_custom_component_selection,
    revert_target_to_bundled_baseline,
    verify_project_sst_runtime,
    used_sst_component_keys_for_scene,
)
from fuse.plugins.community.sst.get_sstinfo import validate_sst_toolchain
from fuse.plugins.community.sst.policy.loader import has_policy_catalog



class SSTComponentManagerDialog(QDialog):
    """Dialog for enabling custom/changed SST components discovered by sst-info."""

    ROLE_COMPONENT_KEY = Qt.UserRole + 100
    ROLE_STATUS = Qt.UserRole + 101
    ROLE_DIFF_TEXT = Qt.UserRole + 102

    def __init__(
        self,
        discovery: SSTComponentDiscovery,
        parent=None,
        used_component_keys: set[str] | None = None,
    ):
        super().__init__(parent)

        self.discovery = discovery
        self.used_component_keys = set(used_component_keys or set())
        self.setWindowTitle("Manage SST Components")
        self.setMinimumWidth(1100)
        self.setMinimumHeight(760)

        layout = QVBoxLayout(self)

        baseline_count = sum(1 for entry in discovery.entries if entry.status == "baseline")
        custom_count = sum(1 for entry in discovery.entries if entry.status == "custom")
        changed_count = sum(1 for entry in discovery.entries if entry.status == "changed")
        missing_count = sum(1 for entry in discovery.entries if entry.status == "missing")

        summary = QLabel(
            (
                f"Source: {discovery.source_label}\n"
                f"SST version: {discovery.version}\n"
                f"Baseline: {baseline_count}  "
                f"Custom: {custom_count}  "
                f"Changed: {changed_count}  "
                f"Missing from target: {missing_count}"
            ),
            self,
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Show:", self))

        self.status_filter = QComboBox(self)
        self.status_filter.addItem("All detected components", "detected")
        self.status_filter.addItem("Custom and changed", "actionable")
        self.status_filter.addItem("Custom only", "custom")
        self.status_filter.addItem("Changed only", "changed")
        self.status_filter.addItem("Missing baseline components", "missing")
        self.status_filter.addItem("All detected and missing", "all")
        self.status_filter.currentIndexChanged.connect(self.populate_tree)
        filter_row.addWidget(self.status_filter)

        enable_all_button = QPushButton("Enable All Custom", self)
        enable_all_button.clicked.connect(self.enable_all_custom)
        filter_row.addWidget(enable_all_button)

        enable_changed_button = QPushButton("Enable All Changed", self)
        enable_changed_button.clicked.connect(self.enable_all_changed)
        filter_row.addWidget(enable_changed_button)

        disable_custom_button = QPushButton("Disable Custom/Changed", self)
        disable_custom_button.clicked.connect(self.disable_actionable)
        filter_row.addWidget(disable_custom_button)

        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(9)
        self.tree.setHeaderLabels([
            "Component",
            "Status",
            "Changes",
            "Kind",
            "Used",
            "Params",
            "Ports",
            "Slots",
            "Stats",
        ])
        self.tree.setAlternatingRowColors(True)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        layout.addWidget(self.tree, stretch=1)

        self.detail_view = QPlainTextEdit(self)
        self.detail_view.setReadOnly(True)
        self.detail_view.setPlaceholderText("Select a component to see metadata differences.")
        self.detail_view.setMinimumHeight(140)
        layout.addWidget(self.detail_view)

        self._populating_tree = False
        self._checked_keys = {
            entry.key
            for entry in discovery.entries
            if entry.enabled_by_default and entry.status in {"custom", "changed"}
        }

        help_label = QLabel(
            (
                "This window opens with all components detected from the configured "
                "SST installation, including baseline matches, custom components, "
                "and changed baseline components. Baseline components remain enabled "
                "automatically. Select custom components to add to this "
                "project/toolchain target. For changed baseline components, checking "
                "the row uses the metadata discovered from the configured SST "
                "installation; leaving it unchecked keeps the bundled baseline "
                "metadata. Select a row to review the exact parameter, port, slot, "
                "and statistic differences."
            ),
            self,
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.populate_tree()

    def _visible_entries(self) -> list[DiscoveredComponentEntry]:
        mode = self.status_filter.currentData() or "actionable"

        if mode == "all":
            return list(self.discovery.entries)

        if mode == "detected":
            return [
                entry
                for entry in self.discovery.entries
                if entry.status != "missing"
            ]

        if mode == "actionable":
            return [
                entry
                for entry in self.discovery.entries
                if entry.status in {"custom", "changed"}
            ]

        return [
            entry
            for entry in self.discovery.entries
            if entry.status == mode
        ]

    def populate_tree(self) -> None:
        self._populating_tree = True
        checked_keys = set(self._checked_keys)

        self.tree.clear()

        entries_by_element: dict[str, list[DiscoveredComponentEntry]] = {}
        for entry in self._visible_entries():
            entries_by_element.setdefault(entry.element_name or "Unknown", []).append(entry)

        for element_name in sorted(entries_by_element):
            entries = sorted(
                entries_by_element[element_name],
                key=lambda item: (item.status, item.kind, item.name),
            )

            element_item = QTreeWidgetItem([element_name])
            element_item.setFlags(element_item.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(element_item)

            for entry in entries:
                diff = describe_component_metadata_diff(
                    key=entry.key,
                    baseline_catalog=self.discovery.baseline_catalog,
                    discovered_catalog=self.discovery.discovered_catalog,
                )
                item = QTreeWidgetItem([
                    entry.display_name,
                    entry.status,
                    diff.summary(),
                    entry.kind,
                    "Yes" if entry.key in self.used_component_keys else "",
                    str(entry.parameter_count),
                    str(entry.port_count),
                    str(entry.subcomponent_slot_count),
                    str(entry.statistic_count),
                ])
                item.setData(0, self.ROLE_COMPONENT_KEY, entry.key)
                item.setData(0, self.ROLE_STATUS, entry.status)
                item.setData(0, self.ROLE_DIFF_TEXT, "\n".join(diff.lines))

                if entry.status in {"custom", "changed"}:
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setCheckState(
                        0,
                        Qt.Checked if entry.key in checked_keys else Qt.Unchecked,
                    )
                else:
                    item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)

                element_item.addChild(item)

        self.tree.expandAll()
        for index in range(self.tree.columnCount()):
            self.tree.resizeColumnToContents(index)

        self._populating_tree = False

        current = self.tree.currentItem()
        if current is not None:
            self._show_item_diff(current)
        else:
            self.detail_view.clear()

    def _show_item_diff(self, item: QTreeWidgetItem | None) -> None:
        if item is None:
            self.detail_view.clear()
            return

        key = item.data(0, self.ROLE_COMPONENT_KEY)
        if not key:
            self.detail_view.setPlainText(
                "Select a component or subcomponent row to review metadata differences."
            )
            return

        diff_text = str(item.data(0, self.ROLE_DIFF_TEXT) or "")
        if not diff_text:
            diff_text = "No metadata difference details are available for this row."

        self.detail_view.setPlainText(diff_text)

    def _on_current_item_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        self._show_item_diff(current)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._populating_tree or column != 0:
            return

        key = item.data(0, self.ROLE_COMPONENT_KEY)

        if not key:
            return

        key = str(key)

        if item.checkState(0) == Qt.Checked:
            self._checked_keys.add(key)
        else:
            if key in self.used_component_keys:
                response = QMessageBox.warning(
                    self,
                    "Disable Used SST Component",
                    (
                        "This project already uses this SST component. Disabling "
                        "its discovered metadata can make the current model fail "
                        "validation or export. Disable it anyway?"
                    ),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )

                if response != QMessageBox.Yes:
                    self._populating_tree = True
                    item.setCheckState(0, Qt.Checked)
                    self._populating_tree = False
                    self._checked_keys.add(key)
                    return

            self._checked_keys.discard(key)

    def _set_status_checked(self, statuses: set[str], checked: bool) -> None:
        if not checked:
            used_to_disable = [
                entry.display_name
                for entry in self.discovery.entries
                if entry.status in statuses
                and entry.key in self._checked_keys
                and entry.key in self.used_component_keys
            ]

            if used_to_disable:
                preview = "\n".join(f"- {name}" for name in used_to_disable[:10])
                extra = "" if len(used_to_disable) <= 10 else f"\n...and {len(used_to_disable) - 10} more"
                response = QMessageBox.warning(
                    self,
                    "Disable Used SST Components",
                    (
                        "This project already uses one or more selected SST "
                        "components. Disabling their discovered metadata can make "
                        "the current model fail validation or export.\n\n"
                        f"{preview}{extra}\n\nDisable them anyway?"
                    ),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )

                if response != QMessageBox.Yes:
                    return

        for top_index in range(self.tree.topLevelItemCount()):
            top_item = self.tree.topLevelItem(top_index)

            for child_index in range(top_item.childCount()):
                item = top_item.child(child_index)
                status = item.data(0, self.ROLE_STATUS)

                if status in statuses:
                    key = item.data(0, self.ROLE_COMPONENT_KEY)
                    if key:
                        if checked:
                            self._checked_keys.add(str(key))
                        else:
                            self._checked_keys.discard(str(key))
                    item.setCheckState(0, Qt.Checked if checked else Qt.Unchecked)

        # Also update rows hidden by the active filter.
        for entry in self.discovery.entries:
            if entry.status in statuses:
                if checked:
                    self._checked_keys.add(entry.key)
                else:
                    self._checked_keys.discard(entry.key)

    def enable_all_custom(self) -> None:
        self._set_status_checked({"custom"}, True)

    def enable_all_changed(self) -> None:
        self._set_status_checked({"changed"}, True)

    def disable_actionable(self) -> None:
        self._set_status_checked({"custom", "changed"}, False)

    def enabled_component_keys(self) -> set[str]:
        return set(self._checked_keys)



class ProjectSettingsDialog(QDialog):
    """Project-level plugin and execution-environment settings.

    The project stores plugin enablement, target framework/catalog versions, and
    the execution environment used to query or validate those frameworks.

    Passwords, private keys, and SSH passphrases are intentionally not stored in
    project files. Remote SSH execution uses the user's system ssh client,
    ~/.ssh/config, and ssh-agent.
    """

    def __init__(self, settings: ProjectSettings | None = None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Project Settings")
        self.setMinimumWidth(840)
        self.setMinimumHeight(680)

        self._settings = deepcopy(settings) if settings else ProjectSettings()
        self._targets = load_framework_targets()

        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(10)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)

        content = QWidget(self)
        root = QVBoxLayout(content)
        root.setSpacing(12)

        self._build_general_group(root)
        self._build_plugins_group(root)
        self._build_execution_environment_group(root)

        root.addStretch(1)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll, stretch=1)

        info = QLabel(
            "Execution settings apply to all enabled plugins in this project. "
            "Remote SSH uses the system ssh client with BatchMode enabled. "
            "Do not store passwords or private keys in project files.",
            self,
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #64748b;")
        outer_layout.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(
            self.apply_to_internal_settings
        )
        outer_layout.addWidget(buttons)

        self.populate_targets()
        self.sst_target_combo.currentIndexChanged.connect(
            self.update_sst_catalog_source_summary
        )
        self.sst_enabled.toggled.connect(self.update_sst_catalog_source_summary)
        self.backend_local.toggled.connect(self.update_sst_catalog_source_summary)
        self.backend_ssh.toggled.connect(self.update_sst_catalog_source_summary)
        self.load_from_settings(self._settings)
        self.update_visibility()
        self.update_sst_catalog_source_summary()

    def _build_general_group(self, root: QVBoxLayout) -> None:
        general_group = QGroupBox("General", self)
        general_form = QFormLayout(general_group)

        self.project_name_edit = QLineEdit(self._settings.project_name, self)
        general_form.addRow("Project name:", self.project_name_edit)

        self.active_plugin_combo = QComboBox(self)
        self.active_plugin_combo.addItem("SST", "sst")
        self.active_plugin_combo.addItem("gem5", "gem5")
        self.active_plugin_combo.currentIndexChanged.connect(
            self.on_active_plugin_changed
        )
        general_form.addRow("Active framework/plugin:", self.active_plugin_combo)

        self.preferred_component_grouping_combo = QComboBox(self)
        self.preferred_component_grouping_combo.addItems(
            ["Element", "Function", "Recent", "Flat"]
        )
        general_form.addRow(
            "Preferred Component Grouping Mode:",
            self.preferred_component_grouping_combo,
        )

        self.preferred_component_sorting_combo = QComboBox(self)
        self.preferred_component_sorting_combo.addItems(["Alphabetical", "Catalog Order"])
        general_form.addRow(
            "Preferred Component Sorting Mode:",
            self.preferred_component_sorting_combo,
        )

        self.auto_expand_component_tree_combo = QComboBox(self)
        self.auto_expand_component_tree_combo.addItem("Off", False)
        self.auto_expand_component_tree_combo.addItem("On", True)
        general_form.addRow(
            "Auto Expand All Component Tree:",
            self.auto_expand_component_tree_combo,
        )

        active_index = self.active_plugin_combo.findData(
            self._settings.active_plugin_id or "sst"
        )

        if active_index >= 0:
            self.active_plugin_combo.setCurrentIndex(active_index)

        root.addWidget(general_group)

    def _build_plugins_group(self, root: QVBoxLayout) -> None:
        plugins_group = QGroupBox("Plugins", self)
        plugins_layout = QVBoxLayout(plugins_group)

        self.sst_enabled = QCheckBox("Enable SST for this project", self)
        self.sst_enabled.toggled.connect(self.update_visibility)
        plugins_layout.addWidget(self.sst_enabled)

        self.sst_target_widget = QWidget(self)
        sst_target_layout = QHBoxLayout(self.sst_target_widget)
        sst_target_layout.setContentsMargins(22, 0, 0, 0)
        sst_target_layout.addWidget(QLabel("Target version/catalog:", self))
        self.sst_target_combo = QComboBox(self)
        sst_target_layout.addWidget(self.sst_target_combo, stretch=1)
        plugins_layout.addWidget(self.sst_target_widget)

        self.gem5_enabled = QCheckBox("Enable gem5 for this project", self)
        self.gem5_enabled.toggled.connect(self.update_visibility)
        plugins_layout.addWidget(self.gem5_enabled)

        self.gem5_target_widget = QWidget(self)
        gem5_target_layout = QHBoxLayout(self.gem5_target_widget)
        gem5_target_layout.setContentsMargins(22, 0, 0, 0)
        gem5_target_layout.addWidget(QLabel("Target version/catalog:", self))
        self.gem5_target_combo = QComboBox(self)
        gem5_target_layout.addWidget(self.gem5_target_combo, stretch=1)
        plugins_layout.addWidget(self.gem5_target_widget)

        root.addWidget(plugins_group)

    def _build_execution_environment_group(self, root: QVBoxLayout) -> None:
        environment_group = QGroupBox("Execution Environment", self)
        environment_layout = QVBoxLayout(environment_group)

        backend_group = QGroupBox("Execution location", self)
        backend_layout = QVBoxLayout(backend_group)

        self.backend_local = QRadioButton("Local machine", self)
        self.backend_ssh = QRadioButton("Remote over SSH", self)

        self.backend_local.toggled.connect(self.update_visibility)
        self.backend_ssh.toggled.connect(self.update_visibility)

        backend_layout.addWidget(self.backend_local)
        backend_layout.addWidget(self.backend_ssh)

        environment_layout.addWidget(backend_group)

        self._build_local_environment_section(environment_layout)
        self._build_remote_environment_section(environment_layout)

        actions_row = QHBoxLayout()

        discover_button = QPushButton("Discover Local Tools", self)
        discover_button.clicked.connect(self.discover_local_tool_paths)
        actions_row.addWidget(discover_button)

        validate_button = QPushButton("Validate Enabled Toolchains", self)
        validate_button.clicked.connect(self.validate_enabled_toolchains)
        actions_row.addWidget(validate_button)

        manage_sst_button = QPushButton("Manage SST Components...", self)
        manage_sst_button.clicked.connect(self.manage_sst_components)
        actions_row.addWidget(manage_sst_button)

        verify_sst_runtime_button = QPushButton("Verify SST Runtime", self)
        verify_sst_runtime_button.clicked.connect(self.verify_sst_runtime)
        actions_row.addWidget(verify_sst_runtime_button)

        actions_row.addStretch(1)
        environment_layout.addLayout(actions_row)

        self.sst_catalog_source_group = QGroupBox("SST Catalog Source", self)
        catalog_source_layout = QVBoxLayout(self.sst_catalog_source_group)

        self.sst_catalog_source_summary = QLabel(
            "No SST catalog target is selected.",
            self,
        )
        self.sst_catalog_source_summary.setWordWrap(True)
        self.sst_catalog_source_summary.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        catalog_source_layout.addWidget(self.sst_catalog_source_summary)

        catalog_actions_row = QHBoxLayout()

        self.refresh_sst_catalog_button = QPushButton("Refresh Catalog", self)
        self.refresh_sst_catalog_button.clicked.connect(self.manage_sst_components)
        catalog_actions_row.addWidget(self.refresh_sst_catalog_button)

        self.revert_sst_catalog_button = QPushButton("Revert to Bundled Baseline", self)
        self.revert_sst_catalog_button.clicked.connect(self.revert_sst_catalog_to_baseline)
        catalog_actions_row.addWidget(self.revert_sst_catalog_button)

        self.delete_sst_catalog_button = QPushButton("Delete Custom Catalog", self)
        self.delete_sst_catalog_button.clicked.connect(self.delete_sst_custom_catalog)
        catalog_actions_row.addWidget(self.delete_sst_catalog_button)

        catalog_actions_row.addStretch(1)
        catalog_source_layout.addLayout(catalog_actions_row)
        environment_layout.addWidget(self.sst_catalog_source_group)

        root.addWidget(environment_group, stretch=1)

    def _build_local_environment_section(self, parent_layout: QVBoxLayout) -> None:
        self.local_group = QGroupBox("Local tool paths", self)
        local_layout = QVBoxLayout(self.local_group)

        self.local_sst_paths_widget = QGroupBox("SST tools", self)
        sst_form = QFormLayout(self.local_sst_paths_widget)

        self.local_sst_info_path = QLineEdit(self)
        self.local_sst_path = QLineEdit(self)

        sst_form.addRow(
            "sst-info path:",
            self._browse_row(
                self.local_sst_info_path,
                self.browse_local_sst_info,
            ),
        )
        sst_form.addRow(
            "sst path:",
            self._browse_row(
                self.local_sst_path,
                self.browse_local_sst,
            ),
        )

        self.local_gem5_paths_widget = QGroupBox("gem5 tools", self)
        gem5_form = QFormLayout(self.local_gem5_paths_widget)

        self.local_gem5_root = QLineEdit(self)
        self.local_gem5_binary = QLineEdit(self)
        self.local_gem5_build_isa = QComboBox(self)
        self.local_gem5_build_isa.addItems(["X86", "ARM", "RISCV", "NULL"])

        gem5_form.addRow(
            "gem5 root:",
            self._browse_row(
                self.local_gem5_root,
                self.browse_local_gem5_root,
                directory=True,
            ),
        )
        gem5_form.addRow(
            "gem5 binary:",
            self._browse_row(
                self.local_gem5_binary,
                self.browse_local_gem5_binary,
            ),
        )
        gem5_form.addRow("build ISA:", self.local_gem5_build_isa)

        local_layout.addWidget(self.local_sst_paths_widget)
        local_layout.addWidget(self.local_gem5_paths_widget)

        parent_layout.addWidget(self.local_group)

    def _build_remote_environment_section(self, parent_layout: QVBoxLayout) -> None:
        self.remote_group = QGroupBox("Remote SSH environment", self)
        remote_layout = QVBoxLayout(self.remote_group)

        connection_form = QFormLayout()

        self.remote_host = QLineEdit(self)
        self.remote_port = QSpinBox(self)
        self.remote_port.setRange(1, 65535)
        self.remote_port.setValue(22)
        self.remote_username = QLineEdit(self)
        self.remote_setup_command = QLineEdit(self)
        self.remote_setup_command.setPlaceholderText(
            "Optional, for example: module load sst/15.1.2"
        )

        connection_form.addRow("Host:", self.remote_host)
        connection_form.addRow("Port:", self.remote_port)
        connection_form.addRow("Username:", self.remote_username)
        connection_form.addRow("Remote setup command:", self.remote_setup_command)

        remote_layout.addLayout(connection_form)

        self.remote_sst_paths_widget = QGroupBox("SST remote tools", self)
        remote_sst_form = QFormLayout(self.remote_sst_paths_widget)

        self.remote_sst_info_path = QLineEdit(self)
        self.remote_sst_path = QLineEdit(self)

        remote_sst_form.addRow("Remote sst-info path:", self.remote_sst_info_path)
        remote_sst_form.addRow("Remote sst path:", self.remote_sst_path)

        self.remote_gem5_paths_widget = QGroupBox("gem5 remote tools", self)
        remote_gem5_form = QFormLayout(self.remote_gem5_paths_widget)

        self.remote_gem5_root = QLineEdit(self)
        self.remote_gem5_binary = QLineEdit(self)
        self.remote_gem5_build_isa = QComboBox(self)
        self.remote_gem5_build_isa.addItems(["X86", "ARM", "RISCV", "NULL"])

        remote_gem5_form.addRow("Remote gem5 root:", self.remote_gem5_root)
        remote_gem5_form.addRow("Remote gem5 binary:", self.remote_gem5_binary)
        remote_gem5_form.addRow("build ISA:", self.remote_gem5_build_isa)

        remote_layout.addWidget(self.remote_sst_paths_widget)
        remote_layout.addWidget(self.remote_gem5_paths_widget)

        parent_layout.addWidget(self.remote_group)

    def _browse_row(
        self,
        line_edit: QLineEdit,
        callback,
        directory: bool = False,
    ) -> QWidget:
        widget = QWidget(self)
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit)

        browse_button = QPushButton("Browse...", self)
        browse_button.clicked.connect(callback)
        layout.addWidget(browse_button)

        return widget

    def populate_targets(self) -> None:
        self.sst_target_combo.clear()
        self.gem5_target_combo.clear()

        for target in self._targets:
            data = {
                "plugin_id": target.plugin_id,
                "target_id": target.target_id,
                "target_label": target.display_name,
                "framework_version": target.framework_version,
            }

            if target.plugin_id == "sst":
                self.sst_target_combo.addItem(target.display_name, data)
            elif target.plugin_id == "gem5":
                self.gem5_target_combo.addItem(target.display_name, data)

    def load_from_settings(self, settings: ProjectSettings) -> None:
        sst_settings = settings.plugin_settings("sst")
        gem5_settings = settings.plugin_settings("gem5")

        self.sst_enabled.setChecked(
            sst_settings.enabled or settings.active_plugin_id == "sst"
        )
        self.gem5_enabled.setChecked(
            gem5_settings.enabled or settings.active_plugin_id == "gem5"
        )

        self._select_target(self.sst_target_combo, sst_settings.target_id)
        self._select_target(self.gem5_target_combo, gem5_settings.target_id)

        active_index = self.active_plugin_combo.findData(
            settings.active_plugin_id or "sst"
        )

        if active_index >= 0:
            self.active_plugin_combo.setCurrentIndex(active_index)

        grouping_index = self.preferred_component_grouping_combo.findText(
            settings.preferred_component_grouping_mode or "Element"
        )
        if grouping_index >= 0:
            self.preferred_component_grouping_combo.setCurrentIndex(grouping_index)

        sorting_index = self.preferred_component_sorting_combo.findText(
            settings.preferred_component_sorting_mode or "Alphabetical"
        )
        if sorting_index >= 0:
            self.preferred_component_sorting_combo.setCurrentIndex(sorting_index)

        auto_expand_index = self.auto_expand_component_tree_combo.findData(
            bool(settings.auto_expand_all_component_tree)
        )
        if auto_expand_index >= 0:
            self.auto_expand_component_tree_combo.setCurrentIndex(auto_expand_index)

        toolchain = self._initial_shared_toolchain(settings)

        self.backend_ssh.setChecked(toolchain.backend == "ssh")
        self.backend_local.setChecked(toolchain.backend != "ssh")

        self.local_sst_info_path.setText(toolchain.tool_paths.get("sstInfo", ""))
        self.local_sst_path.setText(toolchain.tool_paths.get("sst", ""))

        self.local_gem5_root.setText(toolchain.tool_paths.get("gem5Root", ""))
        self.local_gem5_binary.setText(toolchain.tool_paths.get("gem5Binary", ""))

        local_isa = toolchain.tool_paths.get("gem5BuildIsa", "X86") or "X86"
        local_isa_index = self.local_gem5_build_isa.findText(local_isa)

        if local_isa_index >= 0:
            self.local_gem5_build_isa.setCurrentIndex(local_isa_index)

        self.remote_host.setText(toolchain.host)
        self.remote_port.setValue(toolchain.port or 22)
        self.remote_username.setText(toolchain.username)
        self.remote_setup_command.setText(toolchain.remote_setup_command)

        self.remote_sst_info_path.setText(
            toolchain.tool_paths.get(
                "remoteSstInfo",
                toolchain.tool_paths.get("sstInfo", ""),
            )
        )
        self.remote_sst_path.setText(
            toolchain.tool_paths.get(
                "remoteSst",
                toolchain.tool_paths.get("sst", ""),
            )
        )

        self.remote_gem5_root.setText(
            toolchain.tool_paths.get(
                "remoteGem5Root",
                toolchain.tool_paths.get("gem5Root", ""),
            )
        )
        self.remote_gem5_binary.setText(
            toolchain.tool_paths.get(
                "remoteGem5Binary",
                toolchain.tool_paths.get("gem5Binary", ""),
            )
        )

        remote_isa = toolchain.tool_paths.get(
            "remoteGem5BuildIsa",
            toolchain.tool_paths.get("gem5BuildIsa", "X86"),
        ) or "X86"

        remote_isa_index = self.remote_gem5_build_isa.findText(remote_isa)

        if remote_isa_index >= 0:
            self.remote_gem5_build_isa.setCurrentIndex(remote_isa_index)

        self.update_sst_catalog_source_summary()

    def _initial_shared_toolchain(self, settings: ProjectSettings) -> ToolchainSettings:
        active = settings.active_plugin_settings()

        if active is not None:
            return active.toolchain

        for plugin_id in ("sst", "gem5"):
            plugin_settings = settings.plugins.get(plugin_id)

            if plugin_settings is not None:
                return plugin_settings.toolchain

        return ToolchainSettings()

    def _select_target(self, combo: QComboBox, target_id: str) -> None:
        if target_id:
            for index in range(combo.count()):
                data = combo.itemData(index) or {}

                if str(data.get("target_id", "")) == str(target_id):
                    combo.setCurrentIndex(index)
                    return

        if combo.count() > 0:
            combo.setCurrentIndex(0)

    def on_active_plugin_changed(self) -> None:
        plugin_id = self.active_plugin_combo.currentData()

        if plugin_id == "sst":
            self.sst_enabled.setChecked(True)
        elif plugin_id == "gem5":
            self.gem5_enabled.setChecked(True)

        self.update_visibility()

    def update_visibility(self) -> None:
        sst_enabled = self.sst_enabled.isChecked()
        gem5_enabled = self.gem5_enabled.isChecked()
        local_enabled = self.backend_local.isChecked()
        ssh_enabled = self.backend_ssh.isChecked()

        self.sst_target_widget.setVisible(sst_enabled)
        self.gem5_target_widget.setVisible(gem5_enabled)

        self.local_group.setVisible(local_enabled)
        self.remote_group.setVisible(ssh_enabled)

        self.local_sst_paths_widget.setVisible(local_enabled and sst_enabled)
        self.remote_sst_paths_widget.setVisible(ssh_enabled and sst_enabled)

        self.local_gem5_paths_widget.setVisible(local_enabled and gem5_enabled)
        self.remote_gem5_paths_widget.setVisible(ssh_enabled and gem5_enabled)

        if hasattr(self, "sst_catalog_source_group"):
            self.sst_catalog_source_group.setVisible(sst_enabled)

    def browse_local_sst_info(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select sst-info executable")

        if path:
            self.local_sst_info_path.setText(path)

    def browse_local_sst(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select sst executable")

        if path:
            self.local_sst_path.setText(path)

    def browse_local_gem5_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select gem5 root directory")

        if path:
            self.local_gem5_root.setText(path)

    def browse_local_gem5_binary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select gem5 executable")

        if path:
            self.local_gem5_binary.setText(path)

    def discover_local_tool_paths(self) -> None:
        found_any = False

        if self.sst_enabled.isChecked():
            sst_info = discover_local_sst_info()
            sst = discover_local_sst()

            if sst_info:
                self.local_sst_info_path.setText(sst_info)
                found_any = True

            if sst:
                self.local_sst_path.setText(sst)
                found_any = True

        if self.gem5_enabled.isChecked():
            gem5_root = discover_local_gem5_root()
            gem5_binary = discover_local_gem5_binary()

            if gem5_root:
                self.local_gem5_root.setText(gem5_root)
                found_any = True

            if gem5_binary:
                self.local_gem5_binary.setText(gem5_binary)
                found_any = True

        if not found_any:
            QMessageBox.information(
                self,
                "Tool Discovery",
                (
                    "No local tools were found for the enabled plugins on PATH "
                    "or known default locations."
                ),
            )

    def _target_data_for_plugin(self, plugin_id: str) -> dict:
        if plugin_id == "sst":
            return self.sst_target_combo.currentData() or {}

        if plugin_id == "gem5":
            return self.gem5_target_combo.currentData() or {}

        return {}

    def build_shared_toolchain_settings(self) -> ToolchainSettings:
        if self.backend_ssh.isChecked():
            return ToolchainSettings(
                backend="ssh",
                host=self.remote_host.text().strip(),
                port=int(self.remote_port.value()),
                username=self.remote_username.text().strip(),
                remote_setup_command=self.remote_setup_command.text().strip(),
                tool_paths={
                    "sstInfo": self.remote_sst_info_path.text().strip(),
                    "sst": self.remote_sst_path.text().strip(),
                    "remoteSstInfo": self.remote_sst_info_path.text().strip(),
                    "remoteSst": self.remote_sst_path.text().strip(),
                    "gem5Root": self.remote_gem5_root.text().strip(),
                    "gem5Binary": self.remote_gem5_binary.text().strip(),
                    "gem5BuildIsa": self.remote_gem5_build_isa.currentText(),
                    "remoteGem5Root": self.remote_gem5_root.text().strip(),
                    "remoteGem5Binary": self.remote_gem5_binary.text().strip(),
                    "remoteGem5BuildIsa": self.remote_gem5_build_isa.currentText(),
                },
            )

        return ToolchainSettings(
            backend="local",
            tool_paths={
                "sstInfo": self.local_sst_info_path.text().strip(),
                "sst": self.local_sst_path.text().strip(),
                "gem5Root": self.local_gem5_root.text().strip(),
                "gem5Binary": self.local_gem5_binary.text().strip(),
                "gem5BuildIsa": self.local_gem5_build_isa.currentText(),
            },
        )

    def apply_to_internal_settings(self) -> ProjectSettings:
        self._settings.project_name = (
            self.project_name_edit.text().strip() or "Untitled FUSE Project"
        )

        self._settings.preferred_component_grouping_mode = (
            self.preferred_component_grouping_combo.currentText() or "Element"
        )
        self._settings.preferred_component_sorting_mode = (
            self.preferred_component_sorting_combo.currentText() or "Alphabetical"
        )
        self._settings.auto_expand_all_component_tree = bool(
            self.auto_expand_component_tree_combo.currentData()
        )

        requested_active_plugin = self.active_plugin_combo.currentData() or ""

        enabled_plugins = []
        if self.sst_enabled.isChecked():
            enabled_plugins.append("sst")
        if self.gem5_enabled.isChecked():
            enabled_plugins.append("gem5")

        if requested_active_plugin in enabled_plugins:
            self._settings.active_plugin_id = requested_active_plugin
        elif enabled_plugins:
            self._settings.active_plugin_id = enabled_plugins[0]
        else:
            self._settings.active_plugin_id = ""

        shared_toolchain = self.build_shared_toolchain_settings()

        self._apply_plugin_settings(
            plugin_id="sst",
            enabled=self.sst_enabled.isChecked(),
            target_data=self._target_data_for_plugin("sst"),
            toolchain=shared_toolchain,
        )

        self._apply_plugin_settings(
            plugin_id="gem5",
            enabled=self.gem5_enabled.isChecked(),
            target_data=self._target_data_for_plugin("gem5"),
            toolchain=shared_toolchain,
        )

        return self._settings

    def _apply_plugin_settings(
        self,
        plugin_id: str,
        enabled: bool,
        target_data: dict,
        toolchain: ToolchainSettings,
    ) -> None:
        plugin_settings = self._settings.plugin_settings(plugin_id)

        plugin_settings.enabled = enabled
        plugin_settings.target_id = str(target_data.get("target_id", "") or "")
        plugin_settings.target_label = (
            target_data.get("target_label", "")
            or target_data.get("display_name", "")
            or ""
        )
        plugin_settings.framework_version = (
            target_data.get("framework_version", "") or ""
        )
        plugin_settings.toolchain = deepcopy(toolchain)

    def settings(self) -> ProjectSettings:
        return self.apply_to_internal_settings()

    def _prepare_sst_toolchain_for_validation(
        self,
        toolchain: ToolchainSettings,
    ) -> tuple[bool, str]:
        """Resolve/check sst-info path fields before validation/discovery."""

        sst_info_path = toolchain.tool_paths.get("sstInfo", "").strip()

        if toolchain.backend == "local":
            resolved = sst_info_path or shutil.which("sst-info") or ""

            if not resolved:
                return (
                    False,
                    (
                        "No local sst-info executable is configured or available on PATH.\n\n"
                        "Use Discover Local Tools, enter the full path to sst-info, "
                        "or switch the execution environment to Remote over SSH."
                    ),
                )

            toolchain.tool_paths["sstInfo"] = resolved
            return True, ""

        if not sst_info_path:
            return (
                False,
                (
                    "No remote sst-info path is configured.\n\n"
                    "Enter the remote path to sst-info, for example:\n"
                    "/opt/sst/bin/sst-info"
                ),
            )

        return True, ""

    def update_sst_catalog_source_summary(self) -> None:
        """Refresh the Project Settings SST catalog lifecycle summary."""

        if not hasattr(self, "sst_catalog_source_summary"):
            return

        if not self.sst_enabled.isChecked():
            self.sst_catalog_source_group.setVisible(False)
            return

        self.sst_catalog_source_group.setVisible(True)

        target_data = self._target_data_for_plugin("sst")
        target_id = str(target_data.get("target_id", "") or "")

        try:
            summary = catalog_source_summary_for_target(
                target_id,
                toolchain=self.build_shared_toolchain_settings(),
                project_uid=getattr(self._settings, "project_uid", ""),
            )
        except Exception as exc:
            self.sst_catalog_source_summary.setText(
                f"Could not load SST catalog source information: {exc}"
            )
            self.revert_sst_catalog_button.setEnabled(False)
            self.delete_sst_catalog_button.setEnabled(False)
            self.refresh_sst_catalog_button.setEnabled(self.sst_enabled.isChecked())
            return

        self.sst_catalog_source_summary.setText(summary.message())

        self.refresh_sst_catalog_button.setEnabled(self.sst_enabled.isChecked())
        self.revert_sst_catalog_button.setEnabled(summary.is_custom)
        self.delete_sst_catalog_button.setEnabled(summary.is_custom)

        if summary.fingerprint_stale:
            self.sst_catalog_source_summary.setStyleSheet(
                "color: #b45309; font-weight: 500;"
            )
        else:
            self.sst_catalog_source_summary.setStyleSheet("color: #475569;")

    def _select_sst_target_id(self, target_id: str) -> bool:
        for index in range(self.sst_target_combo.count()):
            data = self.sst_target_combo.itemData(index) or {}

            if str(data.get("target_id", "")) == str(target_id):
                self.sst_target_combo.setCurrentIndex(index)
                self.update_sst_catalog_source_summary()
                return True

        return False

    def revert_sst_catalog_to_baseline(self) -> None:
        """Switch the project back to the bundled SST baseline for this version."""

        target_data = self._target_data_for_plugin("sst")
        current_target_id = str(target_data.get("target_id", "") or "")

        baseline = revert_target_to_bundled_baseline(current_target_id)

        if baseline is None:
            QMessageBox.information(
                self,
                "Revert to Bundled Baseline",
                "No bundled baseline SST target was found for the selected target.",
            )
            return

        baseline_target_id, baseline_label = baseline

        if not self._select_sst_target_id(baseline_target_id):
            self._targets = load_framework_targets()
            self.populate_targets()
            self._select_sst_target_id(baseline_target_id)

        QMessageBox.information(
            self,
            "Reverted to Bundled Baseline",
            (
                f"This project is now set to use:\n{baseline_label}\n\n"
                "The custom catalog target was not deleted and can still be used "
                "by other projects."
            ),
        )

    def delete_sst_custom_catalog(self) -> None:
        """Delete the selected custom SST catalog target after confirmation."""

        target_data = self._target_data_for_plugin("sst")
        current_target_id = str(target_data.get("target_id", "") or "")

        try:
            summary = catalog_source_summary_for_target(
                current_target_id,
                toolchain=self.build_shared_toolchain_settings(),
                project_uid=getattr(self._settings, "project_uid", ""),
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Delete Custom Catalog",
                f"Could not inspect the selected SST target.\n\n{exc}",
            )
            return

        if not summary.is_custom:
            QMessageBox.information(
                self,
                "Delete Custom Catalog",
                "The selected SST target is a bundled baseline catalog and cannot be deleted.",
            )
            return

        baseline = revert_target_to_bundled_baseline(current_target_id)

        if baseline is None:
            QMessageBox.warning(
                self,
                "Delete Custom Catalog",
                (
                    "FUSE could not find a bundled baseline target for this custom "
                    "catalog's SST version. Revert is unavailable, so the custom "
                    "target was not deleted."
                ),
            )
            return

        preview = summary.message()
        response = QMessageBox.warning(
            self,
            "Delete Custom SST Catalog",
            (
                "Delete this custom SST catalog target?\n\n"
                f"{preview}\n\n"
                "This removes the database metadata and local discovery snapshot "
                "for this custom target. Existing model instances will remain in "
                "the scene, but this target will no longer appear in Project Settings."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if response != QMessageBox.Yes:
            return

        ok, message = delete_custom_catalog_target(
            current_target_id,
            force=True,
        )

        if not ok:
            QMessageBox.warning(self, "Delete Custom Catalog", message)
            return

        baseline_target_id, baseline_label = baseline
        current_gem5_target = (
            self.gem5_target_combo.currentData() or {}
        ).get("target_id", "")

        self._targets = load_framework_targets()
        self.populate_targets()
        self._select_sst_target_id(baseline_target_id)
        self._select_target(self.gem5_target_combo, str(current_gem5_target))

        QMessageBox.information(
            self,
            "Custom Catalog Deleted",
            (
                f"{message}\n\n"
                f"This project has been switched back to:\n{baseline_label}"
            ),
        )


    def manage_sst_components(self) -> None:
        """Discover and enable custom SST components for the configured toolchain."""

        if not self.sst_enabled.isChecked():
            QMessageBox.information(
                self,
                "Manage SST Components",
                "Enable SST for this project before managing SST components.",
            )
            return

        target_data = self._target_data_for_plugin("sst")
        expected_version = target_data.get("framework_version", "") or ""

        if not expected_version:
            QMessageBox.warning(
                self,
                "Manage SST Components",
                "Choose an SST target catalog/version before discovering components.",
            )
            return

        if not has_policy_catalog(expected_version):
            QMessageBox.warning(
                self,
                "Manage SST Components",
                (
                    f"FUSE does not have an SST export policy catalog for "
                    f"SST {expected_version}."
                ),
            )
            return

        if not has_component_catalog(expected_version):
            QMessageBox.warning(
                self,
                "Manage SST Components",
                (
                    f"FUSE does not have a bundled SST component catalog for "
                    f"SST {expected_version}. Generate and install "
                    f"fuse/plugins/community/sst/component_catalogs/"
                    f"sst-{expected_version}.json first."
                ),
            )
            return

        toolchain = self.build_shared_toolchain_settings()
        ok, message = self._prepare_sst_toolchain_for_validation(toolchain)

        if not ok:
            QMessageBox.warning(self, "Manage SST Components", message)
            return

        ok, message, _ = validate_sst_toolchain(
            toolchain=toolchain,
            expected_version=expected_version,
            timeout_seconds=60,
        )

        if not ok:
            QMessageBox.warning(self, "Manage SST Components", message)
            return

        try:
            discovery = discover_sst_components_for_toolchain(
                version=expected_version,
                toolchain=toolchain,
                timeout_seconds=120,
                project_uid=getattr(self._settings, "project_uid", ""),
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Manage SST Components",
                (
                    "FUSE could not discover SST components from the configured "
                    "toolchain.\n\n"
                    f"{exc}"
                ),
            )
            return

        scene = self._active_scene_for_runtime_verification()
        used_component_keys = (
            used_sst_component_keys_for_scene(scene)
            if scene is not None
            else set()
        )

        dialog = SSTComponentManagerDialog(
            discovery,
            self,
            used_component_keys=used_component_keys,
        )

        if dialog.exec() != QDialog.Accepted:
            return

        try:
            target_id, label, catalog_path = import_custom_component_selection(
                discovery=discovery,
                enabled_keys=dialog.enabled_component_keys(),
                project_uid=getattr(self._settings, "project_uid", ""),
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Manage SST Components",
                (
                    "FUSE could not import the selected SST components into the "
                    "database.\n\n"
                    f"{exc}"
                ),
            )
            return

        current_gem5_target = (
            self.gem5_target_combo.currentData() or {}
        ).get("target_id", "")

        self._targets = load_framework_targets()
        self.populate_targets()
        self._select_sst_target_id(str(target_id))
        self._select_target(self.gem5_target_combo, str(current_gem5_target))
        self.update_sst_catalog_source_summary()

        QMessageBox.information(
            self,
            "SST Components Updated",
            (
                f"Created/updated target:\n{label}\n\n"
                f"Snapshot:\n{catalog_path}\n\n"
                "The SST component panel will use this database-backed target "
                "after you apply the Project Settings."
            ),
        )

    def _active_scene_for_runtime_verification(self):
        parent = self.parent()

        if parent is not None and hasattr(parent, "active_model_scene"):
            try:
                return parent.active_model_scene()
            except Exception:
                pass

        if parent is not None and hasattr(parent, "scene"):
            return getattr(parent, "scene")

        return None

    def verify_sst_runtime(self) -> None:
        """Verify that the configured SST runtime exposes the active model's components."""

        if not self.sst_enabled.isChecked():
            QMessageBox.information(
                self,
                "Verify SST Runtime",
                "Enable SST for this project before verifying the SST runtime.",
            )
            return

        target_data = self._target_data_for_plugin("sst")
        expected_version = target_data.get("framework_version", "") or ""

        if not expected_version:
            QMessageBox.warning(
                self,
                "Verify SST Runtime",
                "Choose an SST target catalog/version before verifying the runtime.",
            )
            return

        toolchain = self.build_shared_toolchain_settings()
        ok, message = self._prepare_sst_toolchain_for_validation(toolchain)

        if not ok:
            QMessageBox.warning(self, "Verify SST Runtime", message)
            return

        scene = self._active_scene_for_runtime_verification()

        if scene is None:
            QMessageBox.warning(
                self,
                "Verify SST Runtime",
                "FUSE could not find the active model scene to verify.",
            )
            return

        try:
            report = verify_project_sst_runtime(
                scene=scene,
                framework_version_id=str(target_data.get("target_id", "") or ""),
                expected_version=expected_version,
                target_label=(
                    target_data.get("target_label", "")
                    or target_data.get("display_name", "")
                    or f"SST {expected_version}"
                ),
                toolchain=toolchain,
                timeout_seconds=120,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Verify SST Runtime",
                f"FUSE could not verify the configured SST runtime.\n\n{exc}",
            )
            return

        plugin_settings = self._settings.plugin_settings("sst")
        plugin_settings.options["lastRuntimeVerification"] = {
            "ok": report.ok,
            "targetId": str(target_data.get("target_id", "") or ""),
            "frameworkVersion": expected_version,
            "message": report.message(),
        }

        if report.ok and not report.warnings:
            QMessageBox.information(self, "SST Runtime Verified", report.message())
        elif report.ok:
            QMessageBox.warning(self, "SST Runtime Verified with Warnings", report.message())
        else:
            QMessageBox.critical(self, "SST Runtime Verification Failed", report.message())

    def validate_enabled_toolchains(self) -> None:
        toolchain = self.build_shared_toolchain_settings()
        messages: list[str] = []
        all_ok = True

        if self.sst_enabled.isChecked():
            ok, message = self._validate_sst(toolchain)

            all_ok = all_ok and ok
            messages.append(f"SST: {'OK' if ok else 'FAILED'}\n{message}")

        if self.gem5_enabled.isChecked():
            ok, message = self._validate_gem5(toolchain)

            all_ok = all_ok and ok
            messages.append(f"gem5: {'OK' if ok else 'FAILED'}\n{message}")

        if not messages:
            QMessageBox.information(
                self,
                "Validate Toolchains",
                "No plugins are enabled for this project.",
            )
            return

        title = "Toolchains Validated" if all_ok else "Toolchain Validation Failed"
        text = "\n\n".join(messages)

        if all_ok:
            QMessageBox.information(self, title, text)
        else:
            QMessageBox.warning(self, title, text)

    def _validate_sst(self, toolchain: ToolchainSettings) -> tuple[bool, str]:
        target_data = self._target_data_for_plugin("sst")
        expected_version = target_data.get("framework_version", "") or ""
        target_label = (
            target_data.get("target_label", "")
            or target_data.get("display_name", "")
            or f"SST {expected_version}"
        )

        if not expected_version:
            return (
                False,
                (
                    "No SST target catalog is selected.\n\n"
                    "Choose a supported SST target version in Project Settings."
                ),
            )

        if not has_policy_catalog(expected_version):
            return (
                False,
                (
                    f"FUSE does not have a bundled SST policy catalog for "
                    f"SST {expected_version}.\n\n"
                    "Choose one of the supported SST versions bundled with this "
                    "FUSE build."
                ),
            )

        if not expected_version:
            return (
                False,
                (
                    "No SST target catalog is selected.\n\n"
                    "Choose a supported SST target version in Project Settings."
                ),
            )

        if not has_policy_catalog(expected_version):
            return (
                False,
                (
                    f"FUSE does not have a bundled SST policy catalog for "
                    f"SST {expected_version}.\n\n"
                    "Choose one of the supported SST versions bundled with this "
                    "FUSE build."
                ),
            )

        ok, message = self._prepare_sst_toolchain_for_validation(toolchain)

        if not ok:
            return ok, message

        ok, message, _ = validate_sst_toolchain(
            toolchain=toolchain,
            expected_version=expected_version,
            timeout_seconds=60,
        )

        if not ok:
            return ok, message

        return (
            True,
            (
                f"{message}\n\n"
                "The selected SST toolchain version matches this project target. "
                "Use Manage SST Components if this installation exposes custom "
                "SST element libraries that should appear in FUSE."
            ),
        )

    def _validate_gem5(self, toolchain: ToolchainSettings) -> tuple[bool, str]:
        target_data = self._target_data_for_plugin("gem5")
        expected_version = target_data.get("framework_version", "") or ""

        gem5_binary = toolchain.tool_paths.get("gem5Binary", "").strip()

        if toolchain.backend == "local":
            resolved = gem5_binary or shutil.which("gem5") or ""

            if not resolved:
                return (
                    False,
                    (
                        "No local gem5 executable is configured or available on PATH.\n\n"
                        "Use Discover Local Tools, enter the full path to gem5.opt, "
                        "or switch the execution environment to Remote over SSH."
                    ),
                )

            gem5_binary = resolved
            toolchain.tool_paths["gem5Binary"] = resolved

        elif not gem5_binary:
            return (
                False,
                (
                    "No remote gem5 executable path is configured.\n\n"
                    "Enter the remote path to gem5.opt, for example:\n"
                    "/opt/gem5/build/X86/gem5.opt"
                ),
            )

        provider = provider_from_toolchain(toolchain)

        result = provider.run(
            [gem5_binary, "--version"],
            timeout_seconds=60,
            env=toolchain.environment,
        )

        output = (result.stdout + "\n" + result.stderr).strip()

        if result.return_code != 0:
            return (
                False,
                f"gem5 failed with return code {result.return_code}.\n{output}",
            )

        if expected_version:
            match = compare_version_prefix(
                expected_version=expected_version,
                detected_text=output,
                policy="major_minor",
            )

            if not match.matched:
                return (
                    False,
                    (
                        f"{match.message}\n\n"
                        f"Configured project target: gem5 {expected_version}\n"
                        f"Toolchain output:\n{output}"
                    ),
                )

            return (
                True,
                (
                    f"{match.message}\n\n"
                    f"Toolchain output:\n{output}"
                ),
            )

        return True, output or "gem5 completed successfully."