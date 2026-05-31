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
def test_component_palette_loads_plugin_component_definitions(qtbot, monkeypatch):
    from fuse.core.model.models import ComponentDefinition
    from fuse.core.ui.component_palette import ComponentPalette

    definitions = [
        ComponentDefinition(
            plugin_id="sst",
            component_id="1",
            element="testElement",
            name="TestCPU",
            category="PROCESSOR COMPONENT",
            display_name_override="testElement.TestCPU",
        ),
        ComponentDefinition(
            plugin_id="sst",
            component_id="2",
            element="testElement",
            name="TestCache",
            category="MEMORY COMPONENT",
            display_name_override="testElement.TestCache",
        ),
    ]

    monkeypatch.setattr(
        "fuse.core.ui.component_palette.load_component_definitions",
        lambda: definitions,
    )

    palette = ComponentPalette()
    qtbot.addWidget(palette)

    palette.load_components()

    assert palette.tree.topLevelItemCount() > 0


def test_component_palette_load_components_does_not_crash(qtbot):
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.core.ui.component_palette import ComponentPalette

    ensure_database_ready(run_plugin_bootstrap=False)

    palette = ComponentPalette()
    qtbot.addWidget(palette)

    palette.load_components()

    assert palette is not None