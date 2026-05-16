# validation.py

from dataclasses import dataclass
from typing import Optional

from db_access import get_component_details


@dataclass
class ValidationIssue:
    issue_type: str
    object_name: str
    message: str
    node_id: Optional[int] = None
    link_id: Optional[int] = None
    parameter_name: Optional[str] = None


def normalize_default_value(value) -> str:
    if value is None:
        return ""

    value = str(value)

    if value == "<required>":
        return ""

    return value


def effective_parameter_value(node, parameter: dict) -> str:
    name = parameter.get("name", "")
    default_value = normalize_default_value(parameter.get("default_val", ""))

    value = node.parameters.get(name, default_value)

    if value is None:
        return ""

    return str(value).strip()


def validate_unique_names(scene) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    used: dict[str, list[tuple[str, int | None]]] = {}

    for node in scene.component_items():
        name = node.instance_name.strip()
        used.setdefault(name, []).append(("component", node.node_id))

        if not name:
            issues.append(
                ValidationIssue(
                    issue_type="component_name",
                    object_name="<unnamed component>",
                    node_id=node.node_id,
                    parameter_name="name",
                    message="Component name cannot be empty.",
                )
            )

    for link in scene.links:
        name = link.name.strip()
        used.setdefault(name, []).append(("link", link.link_id))

        if not name:
            issues.append(
                ValidationIssue(
                    issue_type="link_name",
                    object_name="<unnamed link>",
                    link_id=link.link_id,
                    parameter_name="name",
                    message="Link name cannot be empty.",
                )
            )

    for name, users in used.items():
        if not name or len(users) <= 1:
            continue

        for object_type, object_id in users:
            if object_type == "component":
                issues.append(
                    ValidationIssue(
                        issue_type="component_name",
                        object_name=name,
                        node_id=object_id,
                        parameter_name="name",
                        message=f"Name '{name}' is already used. Names must be unique.",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        issue_type="link_name",
                        object_name=name,
                        link_id=object_id,
                        parameter_name="name",
                        message=f"Name '{name}' is already used. Names must be unique.",
                    )
                )

    return issues


def validate_required_component_parameters(scene) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for node in scene.component_items():
        details = get_component_details(node.component.component_id)

        for parameter in details.get("parameters", []):
            name = parameter.get("name", "")
            required = bool(parameter.get("required"))

            if not required:
                continue

            value = effective_parameter_value(node, parameter)

            if not value:
                issues.append(
                    ValidationIssue(
                        issue_type="component_parameter",
                        object_name=node.instance_name,
                        node_id=node.node_id,
                        parameter_name=name,
                        message=f"Required parameter '{name}' has no value.",
                    )
                )

    return issues


def validate_links(scene) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for link in scene.links:
        if not link.latency.strip():
            issues.append(
                ValidationIssue(
                    issue_type="link_parameter",
                    object_name=link.name,
                    link_id=link.link_id,
                    parameter_name="latency",
                    message="Link latency is required.",
                )
            )

    return issues


def validate_model(scene) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    issues.extend(validate_unique_names(scene))
    issues.extend(validate_required_component_parameters(scene))
    issues.extend(validate_links(scene))
    return issues