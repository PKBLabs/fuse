from PySide6.QtCore import QPointF

from fuse.core.model.models import ComponentDefinition
from fuse.core.ui.model_scene import ModelScene


def component(name: str = "CPU") -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="core",
        component_id=name.lower(),
        element="test",
        name=name,
    )


def test_paste_allocates_component_ids_from_destination_scene(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    main_scene = ModelScene()
    for index in range(13):
        main_scene.create_component_node(
            component("CPU"),
            QPointF(float(index * 20), 0.0),
        )

    assert [node.node_id for node in main_scene.component_items()][-1] == 13

    # Opening/loading a composite editor creates another ModelScene. Previously,
    # clearing or populating that scene reset the process-global node counter and
    # the next paste into the main scene could reuse an existing id.
    nested_scene = ModelScene()
    nested_scene.clear_model()
    nested_scene.create_component_node(component("Nested"), QPointF(0.0, 0.0))

    source_node = main_scene.component_items()[-1]
    source_node.setSelected(True)
    assert main_scene.copy_selection_to_clipboard() is True

    pasted_nodes = main_scene.paste_clipboard(QPointF(400.0, 0.0))

    assert len(pasted_nodes) == 1
    assert pasted_nodes[0].node_id == 14

    node_ids = [node.node_id for node in main_scene.component_items()]
    assert len(node_ids) == len(set(node_ids))
