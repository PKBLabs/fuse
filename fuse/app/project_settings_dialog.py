# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
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
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from fuse.core.model.project_settings import (
    PluginProjectSettings,
    ProjectSettings,
    ToolchainSettings,
)
from fuse.core.persistence.db_access import load_framework_targets
from fuse.core.toolchains.discovery import discover_local_sst, discover_local_sst_info
from fuse.plugins.community.sst.get_sstinfo import validate_sst_toolchain


class ProjectSettingsDialog(QDialog):
    """Project-level plugin/toolchain settings dialog.

    This dialog deliberately stores only connection/path/configuration settings.
    It does not store SSH passwords, private keys, or passphrases.
    """

    def __init__(self, settings: ProjectSettings | None = None, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Project Settings")
        self.setMinimumWidth(780)
        self.setMinimumHeight(560)

        self._settings = deepcopy(settings) if settings else ProjectSettings()
        self._targets = load_framework_targets()

        root = QVBoxLayout(self)
        root.setSpacing(12)

        general_group = QGroupBox("General", self)
        general_form = QFormLayout(general_group)

        self.project_name_edit = QLineEdit(self._settings.project_name, self)
        general_form.addRow("Project name:", self.project_name_edit)

        self.active_plugin_combo = QComboBox(self)
        self.active_plugin_combo.addItem("SST", "sst")
        # gem5 is included in the project format now, but the current gem5 plugin
        # is still placeholder-level. Keep it visible but disabled until richer
        # gem5 project settings are implemented.
        self.active_plugin_combo.addItem("gem5 (not configured)", "gem5")
        general_form.addRow("Active framework/plugin:", self.active_plugin_combo)

        active_index = self.active_plugin_combo.findData(self._settings.active_plugin_id or "sst")
        if active_index >= 0:
            self.active_plugin_combo.setCurrentIndex(active_index)

        root.addWidget(general_group)

        self.sst_group = QGroupBox("SST", self)
        sst_layout = QVBoxLayout(self.sst_group)

        self.sst_enabled = QCheckBox("Enable SST for this project", self)
        sst_layout.addWidget(self.sst_enabled)

        target_form = QFormLayout()
        self.sst_target_combo = QComboBox(self)
        target_form.addRow("Target version/catalog:", self.sst_target_combo)
        sst_layout.addLayout(target_form)

        backend_group = QGroupBox("Execution location", self)
        backend_layout = QVBoxLayout(backend_group)

        self.backend_local = QRadioButton("Local machine", self)
        self.backend_ssh = QRadioButton("Remote over SSH", self)
        backend_layout.addWidget(self.backend_local)
        backend_layout.addWidget(self.backend_ssh)
        sst_layout.addWidget(backend_group)

        local_group = QGroupBox("Local SST toolchain", self)
        local_form = QFormLayout(local_group)

        self.local_sst_info_path = QLineEdit(self)
        self.local_sst_path = QLineEdit(self)

        local_sst_info_row = QHBoxLayout()
        local_sst_info_row.addWidget(self.local_sst_info_path)
        browse_sst_info = QPushButton("Browse...", self)
        browse_sst_info.clicked.connect(self.browse_local_sst_info)
        local_sst_info_row.addWidget(browse_sst_info)

        local_sst_row = QHBoxLayout()
        local_sst_row.addWidget(self.local_sst_path)
        browse_sst = QPushButton("Browse...", self)
        browse_sst.clicked.connect(self.browse_local_sst)
        local_sst_row.addWidget(browse_sst)

        local_form.addRow("sst-info path:", local_sst_info_row)
        local_form.addRow("sst path:", local_sst_row)

        discover_button = QPushButton("Discover Local SST", self)
        discover_button.clicked.connect(self.discover_local_sst_paths)
        local_form.addRow("", discover_button)

        sst_layout.addWidget(local_group)

        remote_group = QGroupBox("Remote SSH SST toolchain", self)
        remote_form = QFormLayout(remote_group)

        self.remote_host = QLineEdit(self)
        self.remote_port = QSpinBox(self)
        self.remote_port.setRange(1, 65535)
        self.remote_port.setValue(22)
        self.remote_username = QLineEdit(self)
        self.remote_sst_info_path = QLineEdit(self)
        self.remote_sst_path = QLineEdit(self)
        self.remote_setup_command = QLineEdit(self)
        self.remote_setup_command.setPlaceholderText("Optional, for example: module load sst/15.0.0")

        remote_form.addRow("Host:", self.remote_host)
        remote_form.addRow("Port:", self.remote_port)
        remote_form.addRow("Username:", self.remote_username)
        remote_form.addRow("Remote sst-info path:", self.remote_sst_info_path)
        remote_form.addRow("Remote sst path:", self.remote_sst_path)
        remote_form.addRow("Remote setup command:", self.remote_setup_command)

        sst_layout.addWidget(remote_group)

        actions_row = QHBoxLayout()
        validate_button = QPushButton("Validate SST Toolchain", self)
        validate_button.clicked.connect(self.validate_sst_toolchain)
        actions_row.addWidget(validate_button)
        actions_row.addStretch(1)
        sst_layout.addLayout(actions_row)

        root.addWidget(self.sst_group, stretch=1)

        info = QLabel(
            "SSH settings use the system ssh client with BatchMode enabled. "
            "Do not store passwords or private keys in project files.",
            self,
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #64748b;")
        root.addWidget(info)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply,
            self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply_to_internal_settings)
        root.addWidget(buttons)

        self.populate_targets()
        self.load_from_settings(self._settings)

    def populate_targets(self) -> None:
        self.sst_target_combo.clear()

        for target in self._targets:
            if target.plugin_id == "sst":
                self.sst_target_combo.addItem(
                    target.display_name,
                    {
                        "plugin_id": target.plugin_id,
                        "target_id": target.target_id,
                        "target_label": target.display_name,
                        "framework_version": target.framework_version,
                    },
                )

    def load_from_settings(self, settings: ProjectSettings) -> None:
        sst_settings = settings.plugin_settings("sst")

        self.sst_enabled.setChecked(sst_settings.enabled or settings.active_plugin_id == "sst")

        if sst_settings.target_id:
            for index in range(self.sst_target_combo.count()):
                data = self.sst_target_combo.itemData(index) or {}
                if data.get("target_id") == sst_settings.target_id:
                    self.sst_target_combo.setCurrentIndex(index)
                    break

        toolchain = sst_settings.toolchain
        self.backend_ssh.setChecked(toolchain.backend == "ssh")
        self.backend_local.setChecked(toolchain.backend != "ssh")

        self.local_sst_info_path.setText(toolchain.tool_paths.get("sstInfo", ""))
        self.local_sst_path.setText(toolchain.tool_paths.get("sst", ""))

        self.remote_host.setText(toolchain.host)
        self.remote_port.setValue(toolchain.port or 22)
        self.remote_username.setText(toolchain.username)
        self.remote_sst_info_path.setText(toolchain.tool_paths.get("remoteSstInfo", ""))
        self.remote_sst_path.setText(toolchain.tool_paths.get("remoteSst", ""))
        self.remote_setup_command.setText(toolchain.remote_setup_command)

    def browse_local_sst_info(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select sst-info executable")
        if path:
            self.local_sst_info_path.setText(path)

    def browse_local_sst(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select sst executable")
        if path:
            self.local_sst_path.setText(path)

    def discover_local_sst_paths(self) -> None:
        sst_info = discover_local_sst_info()
        sst = discover_local_sst()

        if sst_info:
            self.local_sst_info_path.setText(sst_info)

        if sst:
            self.local_sst_path.setText(sst)

        if not sst_info and not sst:
            QMessageBox.information(self, "SST Discovery", "No local SST tools were found on PATH or known default locations.")

    def current_target_data(self) -> dict:
        return self.sst_target_combo.currentData() or {}

    def build_sst_toolchain_settings(self) -> ToolchainSettings:
        if self.backend_ssh.isChecked():
            return ToolchainSettings(
                backend="ssh",
                host=self.remote_host.text().strip(),
                port=int(self.remote_port.value()),
                username=self.remote_username.text().strip(),
                remote_setup_command=self.remote_setup_command.text().strip(),
                tool_paths={
                    "sstInfo": self.remote_sst_info_path.text().strip() or "sst-info",
                    "sst": self.remote_sst_path.text().strip() or "sst",
                    "remoteSstInfo": self.remote_sst_info_path.text().strip(),
                    "remoteSst": self.remote_sst_path.text().strip(),
                },
            )

        return ToolchainSettings(
            backend="local",
            tool_paths={
                "sstInfo": self.local_sst_info_path.text().strip() or "sst-info",
                "sst": self.local_sst_path.text().strip() or "sst",
            },
        )

    def apply_to_internal_settings(self) -> ProjectSettings:
        self._settings.project_name = self.project_name_edit.text().strip() or "Untitled FUSE Project"
        self._settings.active_plugin_id = self.active_plugin_combo.currentData() or "sst"

        target_data = self.current_target_data()
        sst_settings = self._settings.plugin_settings("sst")
        sst_settings.enabled = self.sst_enabled.isChecked() or self._settings.active_plugin_id == "sst"
        sst_settings.target_id = str(target_data.get("target_id", "") or "")
        sst_settings.target_label = target_data.get("target_label", "") or self.sst_target_combo.currentText()
        sst_settings.framework_version = target_data.get("framework_version", "") or ""
        sst_settings.toolchain = self.build_sst_toolchain_settings()

        return self._settings

    def settings(self) -> ProjectSettings:
        return self.apply_to_internal_settings()

    def validate_sst_toolchain(self) -> None:
        target_data = self.current_target_data()
        expected_version = target_data.get("framework_version", "") or ""
        toolchain = self.build_sst_toolchain_settings()

        ok, message, _ = validate_sst_toolchain(
            toolchain=toolchain,
            expected_version=expected_version,
            timeout_seconds=60,
        )

        if ok:
            QMessageBox.information(self, "SST Toolchain Validated", message)
        else:
            QMessageBox.warning(self, "SST Toolchain Validation Failed", message)
