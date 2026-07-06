from fuse.core.model.project_settings import (
    PluginProjectSettings,
    ProjectSettings,
    ToolchainSettings,
)


def test_toolchain_settings_round_trip_preserves_backend_paths_env_and_ssh_fields():
    settings = ToolchainSettings(
        backend="ssh",
        tool_paths={"sst": "/opt/sst/bin/sst"},
        environment={"SST_HOME": "/opt/sst"},
        options={"versionPolicy": "major_minor"},
        host="cluster.example.org",
        port=2200,
        username="alice",
        host_alias="sst-cluster",
        auth_method="ssh-agent",
        remote_setup_command="module load sst",
    )

    restored = ToolchainSettings.from_dict(settings.to_dict())

    assert restored == settings


def test_toolchain_settings_accepts_snake_case_legacy_keys():
    restored = ToolchainSettings.from_dict(
        {
            "backend": "ssh",
            "tool_paths": {"gem5Binary": "/gem5.opt"},
            "host_alias": "gem5-node",
            "remote_setup_command": "source env.sh",
        }
    )

    assert restored.backend == "ssh"
    assert restored.tool_paths == {"gem5Binary": "/gem5.opt"}
    assert restored.host_alias == "gem5-node"
    assert restored.remote_setup_command == "source env.sh"
    assert restored.port == 22


def test_plugin_project_settings_from_flat_legacy_toolchain_fields():
    settings = PluginProjectSettings.from_dict(
        "sst",
        {
            "enabled": True,
            "target_id": "7",
            "target_label": "SST 16",
            "framework_version": "16.0.0",
            "executionBackend": "ssh",
            "sstInfoPath": "/remote/bin/sst-info",
            "sstExecutablePath": "/remote/bin/sst",
            "host": "hpc",
            "port": 2222,
            "username": "user",
            "remoteSetupCommand": "module load sst/16",
            "options": {"strict": True},
        },
    )

    assert settings.plugin_id == "sst"
    assert settings.enabled is True
    assert settings.target_id == "7"
    assert settings.target_label == "SST 16"
    assert settings.framework_version == "16.0.0"
    assert settings.toolchain.backend == "ssh"
    assert settings.toolchain.tool_paths["sstInfo"] == "/remote/bin/sst-info"
    assert settings.toolchain.tool_paths["sst"] == "/remote/bin/sst"
    assert settings.toolchain.host == "hpc"
    assert settings.toolchain.port == 2222
    assert settings.options == {"strict": True}


def test_project_settings_plugin_settings_creates_and_reuses_plugin_entry():
    project_settings = ProjectSettings(project_name="Demo")

    first = project_settings.plugin_settings("sst")
    first.enabled = True
    second = project_settings.plugin_settings("sst")

    assert first is second
    assert project_settings.plugins["sst"].enabled is True


def test_project_settings_active_plugin_settings_returns_none_without_active_plugin():
    settings = ProjectSettings()

    assert settings.active_plugin_settings() is None


def test_project_settings_from_project_settings_dict_round_trip():
    source = ProjectSettings(
        project_name="Round Trip",
        active_plugin_id="gem5",
        plugins={
            "gem5": PluginProjectSettings(
                plugin_id="gem5",
                enabled=True,
                target_id="3",
                target_label="gem5 25",
                framework_version="25.1.0.1",
                toolchain=ToolchainSettings(tool_paths={"gem5Binary": "/bin/gem5"}),
            )
        },
    )

    restored = ProjectSettings.from_dict(source.to_dict())

    assert restored.project_name == "Round Trip"
    assert restored.active_plugin_id == "gem5"
    assert restored.active_plugin_settings().target_id == "3"
    assert restored.active_plugin_settings().toolchain.tool_paths["gem5Binary"] == "/bin/gem5"


def test_project_settings_from_legacy_active_target_project_dict():
    restored = ProjectSettings.from_project_dict(
        {
            "project": {"name": "Legacy"},
            "activeTarget": {"pluginId": "sst", "targetId": "2"},
        }
    )

    assert restored.project_name == "Legacy"
    assert restored.active_plugin_id == "sst"
    assert restored.plugins["sst"].enabled is True
    assert restored.plugins["sst"].target_id == "2"


def test_project_settings_defaults_are_stable_for_missing_or_empty_data():
    assert ProjectSettings.from_dict(None).project_name == "Untitled FUSE Project"
    assert ToolchainSettings.from_dict(None).backend == "local"
    assert PluginProjectSettings.from_dict("x", None).target_id == ""


def test_project_settings_component_catalog_preferences_round_trip():
    settings = ProjectSettings(
        project_name="Catalog Preferences",
        active_plugin_id="sst",
        preferred_component_sorting_mode="Catalog Order",
        preferred_component_grouping_mode="Function",
        auto_expand_all_component_tree=True,
        component_catalog_expanded=True,
    )

    restored = ProjectSettings.from_dict(settings.to_dict())

    assert restored.preferred_component_sorting_mode == "Catalog Order"
    assert restored.preferred_component_grouping_mode == "Function"
    assert restored.auto_expand_all_component_tree is True
    assert restored.component_catalog_expanded is True



def test_project_settings_merges_legacy_top_level_plugin_settings_with_project_settings():
    restored = ProjectSettings.from_project_dict(
        {
            "project": {"name": "Copied"},
            "projectSettings": {
                "projectName": "Copied",
                "activePluginId": "sst",
                "plugins": {
                    "sst": {
                        "enabled": True,
                        "targetId": "16",
                        "targetLabel": "SST 16",
                    }
                },
            },
            "pluginSettings": {
                "sst": {
                    "enabled": True,
                    "targetId": "16",
                    "targetLabel": "SST 16",
                    "frameworkVersion": "16.0.0",
                    "toolchain": {
                        "backend": "local",
                        "toolPaths": {
                            "sst": "/opt/sst/bin/sst",
                            "sstInfo": "/opt/sst/bin/sst-info",
                        },
                    },
                }
            },
            "activeTarget": {"pluginId": "sst", "targetId": "16"},
        }
    )

    active = restored.active_plugin_settings()
    assert active is not None
    assert active.toolchain.tool_paths["sst"] == "/opt/sst/bin/sst"
    assert active.toolchain.tool_paths["sstInfo"] == "/opt/sst/bin/sst-info"
    assert active.framework_version == "16.0.0"
