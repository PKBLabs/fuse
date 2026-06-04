# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from fuse.core.model.models import (
    ComponentDefinition,
    ModelLink,
    ModelSubcompAttachment,
)
from fuse.plugins.community.sst.external_validation.metadata import (
    SSTExternalValidationMetadata,
)


SST_JSON_TOP_LEVEL_SECTIONS = (
    "program_options",
    "shared_params",
    "statistics_options",
    "components",
    "statistics_group",
    "links",
)


@dataclass(frozen=True)
class SSTExternalValidationFixture:
    """One backend-only FUSE-generated SST acceptance fixture.

    Fixtures live in the SST plugin because their semantics are SST-specific.
    They intentionally use a lightweight scene object so the external
    validation harness can run without bringing up Qt UI objects.
    """

    metadata: SSTExternalValidationMetadata
    scene: object
    expected_top_level_sections: tuple[str, ...] = SST_JSON_TOP_LEVEL_SECTIONS
    expected_component_names: tuple[str, ...] = field(default_factory=tuple)
    expected_link_names: tuple[str, ...] = field(default_factory=tuple)

    @property
    def output_filename(self) -> str:
        name = self.metadata.name.strip() or "sst_external_fixture"
        return f"{name}.sst.json"


class SSTExternalValidationScene:
    """Minimal scene protocol needed by the SST JSON exporter."""

    def __init__(
        self,
        nodes: list[object],
        links: list[ModelLink] | None = None,
        attachments: list[ModelSubcompAttachment] | None = None,
    ):
        self.nodes = list(nodes)
        self.links = list(links or [])
        self.subcomp_attachments = list(attachments or [])

    def component_items(self) -> list[object]:
        return list(self.nodes)


def make_fixture_component(
    *,
    component_id: str,
    element: str,
    name: str,
    target_id: str = "1",
    framework_version: str = "15.0.0",
    is_subcomp: int = 0,
    iface: str = "",
) -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="sst",
        target_id=target_id,
        target_label=f"SST {framework_version}",
        framework_version=framework_version,
        component_id=component_id,
        element=element,
        name=name,
        is_subcomp=is_subcomp,
        category="External Validation",
        iface=iface,
        display_name_override=f"{element}.{name}",
    )


def make_fixture_node(
    *,
    node_id: int,
    instance_name: str,
    component: ComponentDefinition,
    ports: tuple[str, ...],
    parameters: dict[str, Any] | None = None,
):
    return SimpleNamespace(
        node_id=node_id,
        instance_name=instance_name,
        component=component,
        parameters=parameters or {},
        ports=[SimpleNamespace(name=name) for name in ports],
    )


def minimal_two_component_link_fixture() -> SSTExternalValidationFixture:
    """Build the first generated SST acceptance fixture for v0.7.0.

    This is intentionally synthetic and small. It validates the FUSE/SST export
    contract before later phases add real SST element-library smoke models.
    Its metadata uses run_mode="json" so it never claims to be runnable under
    a real SST installation.
    """
    source_component = make_fixture_component(
        component_id="external-source",
        element="fuseExternalValidation",
        name="Source",
    )
    target_component = make_fixture_component(
        component_id="external-target",
        element="fuseExternalValidation",
        name="Target",
    )

    source = make_fixture_node(
        node_id=1,
        instance_name="source0",
        component=source_component,
        ports=("out",),
        parameters={"clock": "1GHz", "empty_parameter": ""},
    )
    target = make_fixture_node(
        node_id=2,
        instance_name="target0",
        component=target_component,
        ports=("in",),
        parameters={"clock": "1GHz"},
    )

    link = ModelLink(
        link_id=1,
        name="link_source_target",
        source_node_id=source.node_id,
        source_component_name=source.instance_name,
        source_port="out",
        target_node_id=target.node_id,
        target_component_name=target.instance_name,
        target_port="in",
        source_latency="1ns",
        target_latency="1ns",
        plugin_id="sst",
    )

    metadata = SSTExternalValidationMetadata(
        name="minimal_two_component_link",
        description=(
            "Synthetic FUSE-generated SST JSON acceptance fixture with two "
            "components and one explicit-latency link."
        ),
        run_mode="json",
        timeout_seconds=60,
        expected_return_code=0,
    )

    return SSTExternalValidationFixture(
        metadata=metadata,
        scene=SSTExternalValidationScene([source, target], [link]),
        expected_component_names=("source0", "target0"),
        expected_link_names=("link_source_target",),
    )


def simple_element_example_init_fixture() -> SSTExternalValidationFixture:
    """Build a real-SST init fixture using SST Elements' simple example library.

    This fixture uses ``simpleElementExample.basicClocks`` because it has no
    required links and can initialize under real SST with default parameters.
    It is only exercised when the backend external validation gate is
    explicitly enabled and sst-info can see the simpleElementExample element
    library.
    """
    component = make_fixture_component(
        component_id="simple-basic-clocks",
        element="simpleElementExample",
        name="basicClocks",
    )

    node = make_fixture_node(
        node_id=1,
        instance_name="basic_clocks0",
        component=component,
        ports=(),
        parameters={},
    )

    metadata = SSTExternalValidationMetadata(
        name="simple_element_example_init",
        description=(
            "FUSE-generated SST init fixture for the SST Elements "
            "simpleElementExample.basicClocks component."
        ),
        required_elements=("simpleElementExample",),
        required_components=("basicClocks",),
        run_mode="init",
        timeout_seconds=60,
        expected_return_code=0,
    )

    return SSTExternalValidationFixture(
        metadata=metadata,
        scene=SSTExternalValidationScene([node], []),
        expected_component_names=("basic_clocks0",),
        expected_link_names=(),
    )


def explicit_latency_parameters_fixture() -> SSTExternalValidationFixture:
    """Build a JSON fixture covering typed params and asymmetric latencies."""
    cpu_component = make_fixture_component(
        component_id="external-param-source",
        element="fuseExternalValidation",
        name="ParamSource",
    )
    cache_component = make_fixture_component(
        component_id="external-param-target",
        element="fuseExternalValidation",
        name="ParamTarget",
    )

    cpu = make_fixture_node(
        node_id=10,
        instance_name="param_source0",
        component=cpu_component,
        ports=("cache",),
        parameters={
            "clock": "2GHz",
            "enabled": True,
            "max_reqs": 16,
            "empty_parameter": "",
        },
    )
    cache = make_fixture_node(
        node_id=11,
        instance_name="param_target0",
        component=cache_component,
        ports=("cpu",),
        parameters={"clock": "1GHz"},
    )

    link = ModelLink(
        link_id=10,
        name="link_param_source_target",
        source_node_id=cpu.node_id,
        source_component_name=cpu.instance_name,
        source_port="cache",
        target_node_id=cache.node_id,
        target_component_name=cache.instance_name,
        target_port="cpu",
        source_latency="250ps",
        target_latency="2ns",
        plugin_id="sst",
    )

    metadata = SSTExternalValidationMetadata(
        name="explicit_latency_parameters",
        description=(
            "Synthetic FUSE-generated SST JSON acceptance fixture covering "
            "typed component parameters, empty parameter omission, and "
            "asymmetric endpoint latencies."
        ),
        run_mode="json",
        timeout_seconds=60,
        expected_return_code=0,
        external_suite_tags=("json", "parameters", "latency"),
    )

    return SSTExternalValidationFixture(
        metadata=metadata,
        scene=SSTExternalValidationScene([cpu, cache], [link]),
        expected_component_names=("param_source0", "param_target0"),
        expected_link_names=("link_param_source_target",),
    )


def subcomponent_slot_assignment_fixture() -> SSTExternalValidationFixture:
    """Build a JSON fixture covering native SST SubComponent nesting."""
    parent_component = make_fixture_component(
        component_id="external-parent",
        element="fuseExternalValidation",
        name="Parent",
    )
    child_component = make_fixture_component(
        component_id="external-child-subcomponent",
        element="fuseExternalValidation",
        name="ChildSubComponent",
        is_subcomp=1,
        iface="FUSE::ExternalValidation::Slot",
    )

    parent = make_fixture_node(
        node_id=20,
        instance_name="parent0",
        component=parent_component,
        ports=(),
        parameters={"clock": "1GHz"},
    )
    child = make_fixture_node(
        node_id=21,
        instance_name="slot_child0",
        component=child_component,
        ports=(),
        parameters={"mode": "test"},
    )

    attachment = ModelSubcompAttachment(
        attachment_id=20,
        name="attach_parent0_slot_child0",
        parent_node_id=parent.node_id,
        parent_component_name=parent.instance_name,
        slot_name="backend_slot",
        child_node_id=child.node_id,
        child_component_name=child.instance_name,
        required_interface="FUSE::ExternalValidation::Slot",
        provided_interface="FUSE::ExternalValidation::Slot",
        plugin_id="sst",
    )

    metadata = SSTExternalValidationMetadata(
        name="subcomponent_slot_assignment",
        description=(
            "Synthetic FUSE-generated SST JSON acceptance fixture covering "
            "native SST SubComponent nesting and slot-name export."
        ),
        run_mode="json",
        timeout_seconds=60,
        expected_return_code=0,
        external_suite_tags=("json", "subcomponent", "slot"),
    )

    return SSTExternalValidationFixture(
        metadata=metadata,
        scene=SSTExternalValidationScene([parent, child], attachments=[attachment]),
        expected_component_names=("parent0",),
        expected_link_names=(),
    )


def generated_acceptance_fixtures() -> tuple[SSTExternalValidationFixture, ...]:
    """Return v0.7.0 backend acceptance fixtures owned by the SST plugin."""
    return (
        minimal_two_component_link_fixture(),
        explicit_latency_parameters_fixture(),
        subcomponent_slot_assignment_fixture(),
        simple_element_example_init_fixture(),
    )
