from PySide6.QtCore import QPointF

from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment
from fuse.core.model.validation import ValidationIssue


def _component(name="CPU"):
    return ComponentDefinition(
        plugin_id="core",
        component_id=name.lower(),
        element="test",
        name=name,
        category="processor",
    )


def _make_window(qtbot, monkeypatch):
    monkeypatch.setattr("fuse.app.app.ensure_database_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr("fuse.app.app.load_framework_targets", lambda: [])
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )
    monkeypatch.setattr(
        "fuse.core.ui.component_palette.ComponentPalette.load_components",
        lambda self: None,
    )

    from fuse.app.app import MainWindow

    monkeypatch.setattr(
        MainWindow,
        "confirm_discard_unsaved_changes",
        lambda self, action_name: True,
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.set_dirty(False)
    return window


def test_validation_results_panel_lists_and_filters_structured_issues(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    issues = [
        ValidationIssue("component_parameter", "cpu0", "Clock is required.", node_id=1, parameter_name="clock"),
        ValidationIssue("warning_port", "link0", "Port direction is unusual.", link_id=7, severity="warning"),
    ]

    window.show_validation_results(issues, "FUSE model validation")

    assert window.validation_results.topLevelItemCount() == 2
    assert window.validation_results.topLevelItem(0).text(0) == "Error"
    assert window.validation_results.topLevelItem(0).text(1) == "Component"
    assert window.validation_results.topLevelItem(0).text(4) == "Set 'clock' in the Properties panel."

    window.validation_filter.setCurrentText("Warnings")

    assert window.validation_results.topLevelItemCount() == 1
    assert window.validation_results.topLevelItem(0).text(0) == "Warning"
    assert window.validation_results.topLevelItem(0).text(2) == "link0"

    window.set_dirty(False)
    window.close()


def test_validation_result_double_click_focuses_component(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    node = window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    issue = ValidationIssue("component_parameter", node.instance_name, "Clock is required.", node_id=node.node_id, parameter_name="clock")

    window.show_validation_results([issue], "FUSE model validation")
    item = window.validation_results.topLevelItem(0)
    window.on_validation_result_activated(item, 0)

    assert window.scene.selected_component is node
    assert node.validation_messages == ["Clock is required."] or node.validation_messages == []

    window.set_dirty(False)
    window.close()


def test_apply_validation_issues_marks_link_and_subcomponent_attachment(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    source = window.scene.create_component_node(_component("Source"), QPointF(10, 20))
    target = window.scene.create_component_node(_component("Target"), QPointF(300, 20))

    source_port = next(port for port in source.ports if port.name == "out")
    target_port = next(port for port in target.ports if port.name == "in")
    link = ModelLink(1, "link0", source.node_id, source.instance_name, "out", target.node_id, target.instance_name, "in")
    window.scene.links.append(link)

    from fuse.core.ui.graphics_items import ConnectionItem

    connection = ConnectionItem(link, source_port, target_port)
    window.scene.addItem(connection)

    attachment = ModelSubcompAttachment(1, "attach0", source.node_id, source.instance_name, "slot", target.node_id, target.instance_name)
    window.scene.subcomp_attachments.append(attachment)

    link_issue = ValidationIssue("link_parameter", "link0", "Latency is required.", link_id=1, parameter_name="source_latency")
    attachment_issue = ValidationIssue("subcomp_attachment", "attach0", "Interface mismatch.", attachment_id=1)

    window.apply_validation_issues([link_issue, attachment_issue])

    assert connection.validation_messages == ["Latency is required."]
    # There is no visual attachment item in this lightweight fixture, but the
    # issue should still render as a SubComponent result in the panel.
    window.show_validation_results([attachment_issue], "FUSE model validation")
    assert window.validation_results.topLevelItem(0).text(1) == "SubComponent"

    window.set_dirty(False)
    window.close()
