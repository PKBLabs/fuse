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

def test_component_palette_search_filters_known_component_fields(qtbot, monkeypatch):
    from fuse.core.model.models import ComponentDefinition
    from fuse.core.ui.component_palette import ComponentPalette

    definitions = [
        ComponentDefinition(
            plugin_id="sst",
            component_id="1",
            element="miranda",
            name="Generator",
            category="PROCESSOR COMPONENT",
            functionality="traffic generator",
            description="Synthetic CPU workload source",
        ),
        ComponentDefinition(
            plugin_id="gem5",
            component_id="2",
            element="mem",
            name="DDR3_1600_8x8",
            category="Memory",
            functionality="DRAM",
            description="Main memory controller",
        ),
    ]

    monkeypatch.setattr(
        "fuse.core.ui.component_palette.load_component_definitions",
        lambda *args, **kwargs: definitions,
    )

    palette = ComponentPalette()
    qtbot.addWidget(palette)
    palette.load_components()

    palette.component_search.setText("dram")

    assert palette.tree.topLevelItemCount() == 1
    simulator_item = palette.tree.topLevelItem(0)
    assert simulator_item.text(0) == "Gem5"


def test_component_palette_returns_to_preferred_grouping_after_selection_clears(qtbot, monkeypatch):
    from fuse.core.model.models import ComponentDefinition
    from fuse.core.ui.component_palette import ComponentPalette

    definitions = [
        ComponentDefinition(
            plugin_id="sst",
            component_id="1",
            element="core",
            name="CPU",
            category="Processor",
        ),
    ]

    monkeypatch.setattr(
        "fuse.core.ui.component_palette.load_component_definitions",
        lambda *args, **kwargs: definitions,
    )
    monkeypatch.setattr(
        "fuse.core.ui.component_palette.load_subcomp_connector_metadata_for_component",
        lambda *args, **kwargs: [],
    )

    palette = ComponentPalette()
    qtbot.addWidget(palette)
    palette.set_project_preferences(grouping_mode="Flat", sorting_mode="Alphabetical")
    palette.load_components()

    class Node:
        component = definitions[0]

    palette.set_compatibility_context(Node())
    assert palette.view_selector.currentText() == palette.VIEW_COMPATIBLE

    palette.clear_compatibility_context()
    assert palette.view_selector.currentText() == palette.VIEW_FLAT


def test_component_palette_expand_collapse_preference_persists_through_callback(qtbot):
    from fuse.core.ui.component_palette import ComponentPalette

    palette = ComponentPalette()
    qtbot.addWidget(palette)
    captured = []
    palette.preferences_changed_callback = captured.append

    palette.expand_all_tree.setChecked(True)

    assert captured[-1]["component_catalog_expanded"] is True


def test_component_palette_places_search_and_view_controls_below_frequently_used(qtbot):
    from fuse.core.ui.component_palette import ComponentPalette

    palette = ComponentPalette()
    qtbot.addWidget(palette)

    layout = palette.layout()

    assert layout.itemAt(0).widget() is palette.quick_section
    assert layout.itemAt(1).widget() is palette.frequent_divider
    assert layout.itemAt(2).layout() is not None
    assert layout.itemAt(3).widget() is palette.component_search
    assert layout.itemAt(4).layout() is not None
    assert layout.itemAt(5).widget() is palette.tree


def test_component_palette_groups_composites_separately(qtbot, monkeypatch):
    from fuse.core.model.models import ComponentDefinition
    from fuse.core.ui.component_palette import ComponentPalette

    definitions = [
        ComponentDefinition(
            plugin_id="sst",
            component_id="1",
            element="miranda",
            name="Generator",
            category="PROCESSOR COMPONENT",
        ),
        ComponentDefinition(
            plugin_id="core",
            target_id="fuse-composite",
            component_id="composite-cache-pair",
            element="Composite Components",
            name="Cache Pair",
            category="Composite Components",
            description="Reusable mini-model",
            is_composite=1,
            composite_id="composite-cache-pair",
        ),
    ]

    monkeypatch.setattr(
        "fuse.core.ui.component_palette.load_component_definitions",
        lambda *args, **kwargs: definitions,
    )

    palette = ComponentPalette()
    qtbot.addWidget(palette)
    palette.load_components()

    top_level_names = [
        palette.tree.topLevelItem(index).text(0)
        for index in range(palette.tree.topLevelItemCount())
    ]

    assert "Composite Components" in top_level_names
    assert "SST" in top_level_names


def test_component_palette_search_matches_composite_description(qtbot, monkeypatch):
    from fuse.core.model.models import ComponentDefinition
    from fuse.core.ui.component_palette import ComponentPalette

    definitions = [
        ComponentDefinition(
            plugin_id="core",
            target_id="fuse-composite",
            component_id="composite-cache-pair",
            element="Composite Components",
            name="Cache Pair",
            category="Composite Components",
            description="Reusable mini-model for paired cache blocks",
            is_composite=1,
            composite_id="composite-cache-pair",
        ),
        ComponentDefinition(
            plugin_id="gem5",
            component_id="2",
            element="mem",
            name="DDR3_1600_8x8",
            category="Memory",
        ),
    ]

    monkeypatch.setattr(
        "fuse.core.ui.component_palette.load_component_definitions",
        lambda *args, **kwargs: definitions,
    )

    palette = ComponentPalette()
    qtbot.addWidget(palette)
    palette.load_components()
    palette.component_search.setText("paired cache")

    assert palette.tree.topLevelItemCount() == 1
    assert palette.tree.topLevelItem(0).text(0) == "Composite Components"
