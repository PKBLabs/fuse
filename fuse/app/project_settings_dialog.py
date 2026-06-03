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

from copy import deepcopy
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
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
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
from fuse.plugins.community.sst.get_sstinfo import validate_sst_toolchain


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
        self.load_from_settings(self._settings)
        self.update_visibility()

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

        actions_row.addStretch(1)
        environment_layout.addLayout(actions_row)

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

        elif not sst_info_path:
            return (
                False,
                (
                    "No remote sst-info path is configured.\n\n"
                    "Enter the remote path to sst-info, for example:\n"
                    "/opt/sst/bin/sst-info"
                ),
            )

        ok, message, _ = validate_sst_toolchain(
            toolchain=toolchain,
            expected_version=expected_version,
            timeout_seconds=60,
        )

        return ok, message

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