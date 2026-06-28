# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

import pytest


pytestmark = pytest.mark.sst


def test_project_settings_roundtrip_preserves_sst_target_toolchain_options_and_project_uid():
    from fuse.core.model.project_settings import (
        PluginProjectSettings,
        ProjectSettings,
        ToolchainSettings,
    )

    settings = ProjectSettings(
        project_uid="project-uid-123",
        project_name="SST Project",
        active_plugin_id="sst",
    )
    settings.plugins["sst"] = PluginProjectSettings(
        plugin_id="sst",
        enabled=True,
        target_id="42",
        target_label="SST 16.0.0 — Local custom",
        framework_version="16.0.0",
        toolchain=ToolchainSettings(
            backend="ssh",
            tool_paths={"sstInfo": "/remote/bin/sst-info", "sst": "/remote/bin/sst"},
            environment={"SST_ELEMENTS_HOME": "/remote/elements"},
            options={"timeout": "120"},
            host="sst.example.test",
            port=2222,
            username="alice",
            host_alias="sst-test",
            auth_method="ssh-agent",
            remote_setup_command="module load sst/16",
        ),
        options={"lastRuntimeVerification": {"ok": True}},
    )

    restored = ProjectSettings.from_dict(settings.to_dict())
    sst = restored.plugin_settings("sst")

    assert restored.project_uid == "project-uid-123"
    assert restored.active_plugin_settings() is sst
    assert sst.enabled
    assert sst.target_id == "42"
    assert sst.target_label == "SST 16.0.0 — Local custom"
    assert sst.framework_version == "16.0.0"
    assert sst.toolchain.backend == "ssh"
    assert sst.toolchain.tool_paths["sstInfo"] == "/remote/bin/sst-info"
    assert sst.toolchain.environment["SST_ELEMENTS_HOME"] == "/remote/elements"
    assert sst.toolchain.options["timeout"] == "120"
    assert sst.toolchain.host == "sst.example.test"
    assert sst.toolchain.port == 2222
    assert sst.toolchain.username == "alice"
    assert sst.toolchain.host_alias == "sst-test"
    assert sst.toolchain.remote_setup_command == "module load sst/16"
    assert sst.options["lastRuntimeVerification"] == {"ok": True}


def test_project_settings_legacy_flat_toolchain_fields_are_migrated():
    from fuse.core.model.project_settings import PluginProjectSettings

    settings = PluginProjectSettings.from_dict(
        "sst",
        {
            "enabled": True,
            "targetId": 7,
            "targetLabel": "SST 16.0.0",
            "frameworkVersion": "16.0.0",
            "executionBackend": "ssh",
            "sstInfoPath": "/legacy/sst-info",
            "sstExecutablePath": "/legacy/sst",
            "host": "legacy.example.test",
            "port": "2200",
            "username": "legacy-user",
            "remoteSetupCommand": "source /etc/profile",
        },
    )

    assert settings.enabled
    assert settings.target_id == "7"
    assert settings.toolchain.backend == "ssh"
    assert settings.toolchain.tool_paths["sstInfo"] == "/legacy/sst-info"
    assert settings.toolchain.tool_paths["sst"] == "/legacy/sst"
    assert settings.toolchain.host == "legacy.example.test"
    assert settings.toolchain.port == 2200
    assert settings.toolchain.username == "legacy-user"
    assert settings.toolchain.remote_setup_command == "source /etc/profile"


def test_project_settings_legacy_project_without_project_uid_gets_stable_uid_on_load():
    from fuse.core.model.project_settings import ProjectSettings

    project = {
        "project": {"name": "legacy-project"},
        "activeTarget": {"pluginId": "sst", "targetId": "99"},
    }

    settings = ProjectSettings.from_project_dict(project)

    assert settings.project_uid
    assert settings.project_name == "legacy-project"
    assert settings.active_plugin_id == "sst"
    assert settings.plugin_settings("sst").enabled
    assert settings.plugin_settings("sst").target_id == "99"

    serialized = settings.to_dict()
    restored = ProjectSettings.from_dict(serialized)
    assert restored.project_uid == settings.project_uid
