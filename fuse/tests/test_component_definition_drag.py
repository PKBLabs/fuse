def test_component_definition_drag_round_trip_preserves_plugin_identity():
    from fuse.core.model.models import ComponentDefinition

    original = ComponentDefinition(
        plugin_id="sst",
        component_id="123",
        element="memHierarchy",
        name="Cache",
        is_subcomp=0,
        category="MEMORY COMPONENT",
        iface="",
        icon_path="core/resources/media/arch_component_icons/memory_cache.png",
        display_name_override="memHierarchy.Cache",
    )

    restored = ComponentDefinition.from_drag_text(original.to_drag_text())

    assert restored.plugin_id == "sst"
    assert str(restored.component_id) == "123"
    assert restored.element == "memHierarchy"
    assert restored.name == "Cache"
    assert restored.category == "MEMORY COMPONENT"
    assert restored.icon_path.endswith("memory_cache.png")
    assert restored.display_name_override == "memHierarchy.Cache"


def test_component_definition_old_drag_format_defaults_to_sst():
    from fuse.core.model.models import ComponentDefinition

    old_drag_text = "42|memHierarchy|Cache|0|MEMORY COMPONENT|"

    restored = ComponentDefinition.from_drag_text(old_drag_text)

    assert restored.plugin_id == "sst"
    assert str(restored.component_id) == "42"
    assert restored.element == "memHierarchy"
    assert restored.name == "Cache"
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
