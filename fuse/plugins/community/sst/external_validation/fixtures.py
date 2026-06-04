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

from fuse.core.model.models import ComponentDefinition, ModelLink
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

    def __init__(self, nodes: list[object], links: list[ModelLink] | None = None):
        self.nodes = list(nodes)
        self.links = list(links or [])
        self.subcomp_attachments: list[object] = []

    def component_items(self) -> list[object]:
        return list(self.nodes)


def make_fixture_component(
    *,
    component_id: str,
    element: str,
    name: str,
    target_id: str = "1",
    framework_version: str = "15.0.0",
) -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="sst",
        target_id=target_id,
        target_label=f"SST {framework_version}",
        framework_version=framework_version,
        component_id=component_id,
        element=element,
        name=name,
        category="External Validation",
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

    This fixture is only exercised against a real SST installation when the
    backend external validation gate is explicitly enabled and sst-info can
    see the simpleElementExample element library.
    """
    component = make_fixture_component(
        component_id="simple-example0",
        element="simpleElementExample",
        name="example0",
    )

    node = make_fixture_node(
        node_id=1,
        instance_name="example0",
        component=component,
        ports=(),
        parameters={},
    )

    metadata = SSTExternalValidationMetadata(
        name="simple_element_example_init",
        description=(
            "FUSE-generated SST init fixture for the SST Elements "
            "simpleElementExample.example0 component."
        ),
        required_elements=("simpleElementExample",),
        run_mode="init",
        timeout_seconds=60,
        expected_return_code=0,
    )

    return SSTExternalValidationFixture(
        metadata=metadata,
        scene=SSTExternalValidationScene([node], []),
        expected_component_names=("example0",),
        expected_link_names=(),
    )


def generated_acceptance_fixtures() -> tuple[SSTExternalValidationFixture, ...]:
    """Return v0.7.0 backend acceptance fixtures owned by the SST plugin."""
    return (
        minimal_two_component_link_fixture(),
        simple_element_example_init_fixture(),
    )
