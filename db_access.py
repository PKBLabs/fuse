from typing import Optional

from models import ComponentDefinition

try:
    from db_utils import (
        get_all_components_for_element,
        get_all_elements,
        get_ports_for_component,
        get_component_details,
    )
except ImportError:
    get_all_components_for_element = None
    get_all_elements = None
    get_ports_for_component = None
    get_component_details = None

try:
    from initialize_db import initialize_database
except ImportError:
    initialize_database = None

def ensure_database_ready() -> None:
    """
    Create app_data/app.db and all schema tables if they do not exist.

    This should run when the GUI starts. It does not populate SST metadata;
    it only guarantees the database file/schema exists. If the database is
    empty, the component palette will simply be empty.
    """
    if initialize_database is None:
        print("Could not import initialize_database; database was not initialized.")
        return

    try:
        initialize_database()
    except Exception as exc:
        print(f"Failed to initialize database: {exc}")


def load_component_definitions() -> list[ComponentDefinition]:
    if get_all_elements is None or get_all_components_for_element is None:
        return []

    try:
        definitions: list[ComponentDefinition] = []
        elements = get_all_elements()

        for element in elements:
            element_name = element["name"]
            components = get_all_components_for_element(element_name)

            for component in components:
                definitions.append(
                    ComponentDefinition(
                        component_id=component.get("id"),
                        element=element_name,
                        name=component.get("name", ""),
                        is_subcomp=int(component.get("is_subcomp", 0)),
                        category=component.get("category", ""),
                        iface=component.get("iface", ""),
                    )
                )

        return definitions

    except Exception as exc:
        print(f"Failed to load components from database: {exc}")
        return []


def load_port_names_for_component(component_id: Optional[int]) -> list[str]:
    if component_id is None or get_ports_for_component is None:
        return []

    try:
        ports = get_ports_for_component(component_id)
        return [port["name"] for port in ports]
    except Exception as exc:
        print(f"Failed to load ports for component {component_id}: {exc}")
        return []


def demo_components() -> list[ComponentDefinition]:
    return [
        ComponentDefinition(element="demo", name="CPU", category="PROCESSOR COMPONENT"),
        ComponentDefinition(element="demo", name="Cache", category="MEMORY COMPONENT"),
        ComponentDefinition(element="demo", name="Memory", category="MEMORY COMPONENT"),
        ComponentDefinition(element="demo", name="Network", category="NETWORK COMPONENT"),
    ]