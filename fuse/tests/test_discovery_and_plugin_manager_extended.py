import os
from pathlib import Path

import pytest

from fuse.core.toolchains import discovery


def test_discover_local_executable_prefers_path_lookup(monkeypatch, tmp_path):
    executable = tmp_path / "tool"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

    monkeypatch.setattr(discovery.shutil, "which", lambda name: str(executable))

    assert discovery.discover_local_executable("tool") == str(executable.resolve())


def test_discover_local_executable_falls_back_to_extra_candidates(monkeypatch, tmp_path):
    executable = tmp_path / "candidate"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setattr(discovery.shutil, "which", lambda name: None)

    assert discovery.discover_local_executable("missing", [str(executable)]) == str(executable.resolve())


def test_discover_local_executable_ignores_non_executable_candidate(monkeypatch, tmp_path):
    non_executable = tmp_path / "candidate"
    non_executable.write_text("not executable", encoding="utf-8")
    monkeypatch.setattr(discovery.shutil, "which", lambda name: None)

    assert discovery.discover_local_executable("missing", [str(non_executable)]) == ""


def test_discover_local_directory_returns_first_existing_directory(tmp_path):
    missing = tmp_path / "missing"
    existing = tmp_path / "existing"
    existing.mkdir()

    assert discovery.discover_local_directory([str(missing), str(existing)]) == str(existing.resolve())


def test_prefix_candidates_include_environment_roots(monkeypatch, tmp_path):
    sst_home = tmp_path / "sst"
    gem5_home = tmp_path / "gem5"
    monkeypatch.setenv("SST_HOME", str(sst_home))
    monkeypatch.setenv("GEM5_ROOT", str(gem5_home))

    assert discovery._sst_prefix_candidates()[0] == sst_home
    assert discovery._gem5_prefix_candidates()[0] == gem5_home


def test_load_register_callable_imports_named_function(tmp_path, monkeypatch):
    import fuse.core.plugin_runtime.manager as manager

    module_path = tmp_path / "fake_plugin_module.py"
    module_path.write_text("def register():\n    return 'registered'\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))

    register = manager._load_register_callable("fake_plugin_module:register")

    assert register() == "registered"


def test_load_enabled_plugins_loads_valid_manifest_from_patched_root(tmp_path, monkeypatch):
    import fuse.core.plugin_runtime.manager as manager

    module_path = tmp_path / "plugin_impl.py"
    module_path.write_text(
        "class Plugin:\n"
        "    plugin_id = 'demo'\n"
        "    name = 'Demo Plugin'\n"
        "def register():\n"
        "    return Plugin()\n",
        encoding="utf-8",
    )
    plugin_dir = tmp_path / "community" / "demo"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.toml").write_text(
        "[plugin]\n"
        "id = 'demo'\n"
        "name = 'Demo Plugin'\n"
        "[entry_points]\n"
        "register = 'plugin_impl:register'\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(manager, "PLUGIN_ROOT", tmp_path)

    loaded = manager.load_enabled_plugins()

    assert [plugin.plugin_id for plugin in loaded] == ["demo"]
    assert loaded[0].instance.plugin_id == "demo"


def test_get_plugin_by_id_matches_manifest_or_instance_id(monkeypatch):
    import fuse.core.plugin_runtime.manager as manager

    class Instance:
        plugin_id = "instance-id"

    loaded = manager.LoadedPlugin(
        plugin_id="manifest-id",
        name="Demo",
        root=Path("."),
        manifest={},
        instance=Instance(),
    )
    monkeypatch.setattr(manager, "load_enabled_plugins", lambda: [loaded])

    assert manager.get_plugin_by_id("manifest-id") is loaded.instance
    assert manager.get_plugin_by_id("instance-id") is loaded.instance


def test_load_all_palette_items_filters_by_plugin_and_forwards_target(monkeypatch):
    import fuse.core.plugin_runtime.manager as manager
    from fuse.plugin_api.interfaces import PaletteItem

    class Plugin:
        plugin_id = "p1"

        def load_palette_items(self, target_id=None):
            return [PaletteItem(plugin_id="p1", item_id=str(target_id), display_name="Item", type_name="T")]

    loaded = manager.LoadedPlugin("p1", "P1", Path("."), {}, Plugin())
    monkeypatch.setattr(manager, "load_enabled_plugins", lambda: [loaded])

    assert manager.load_all_palette_items(plugin_id="missing") == []
    assert manager.load_all_palette_items(plugin_id="p1", target_id="target")[0].item_id == "target"


def test_load_item_details_raises_when_plugin_lacks_details(monkeypatch):
    import fuse.core.plugin_runtime.manager as manager

    class Plugin:
        plugin_id = "minimal"

    loaded = manager.LoadedPlugin("minimal", "Minimal", Path("."), {}, Plugin())
    monkeypatch.setattr(manager, "load_enabled_plugins", lambda: [loaded])

    with pytest.raises(KeyError, match="does not provide item details"):
        manager.load_item_details("minimal", "item")
