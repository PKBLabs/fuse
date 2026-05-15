from dataclasses import dataclass
from typing import Optional

MIME_COMPONENT = "application/x-fuse-component"
SCHEMA_VERSION = "0.1.0"

@dataclass
class ComponentDefinition:
    element: str
    name: str
    component_id: Optional[int] = None
    is_subcomp: int = 0
    category: str = ""
    iface: str = ""

    @property
    def display_name(self) -> str:
        kind = "SubComponent" if self.is_subcomp else "Component"
        return f"{self.element}.{self.name} ({kind})"

    def to_drag_text(self) -> str:
        return "|".join(
            [
                str(self.component_id or ""),
                self.element,
                self.name,
                str(self.is_subcomp),
                self.category or "",
                self.iface or "",
            ]
        )

    @staticmethod
    def from_drag_text(text: str) -> "ComponentDefinition":
        parts = text.split("|", 5)
        while len(parts) < 6:
            parts.append("")

        component_id_text, element, name, is_subcomp, category, iface = parts

        return ComponentDefinition(
            component_id=int(component_id_text) if component_id_text else None,
            element=element,
            name=name,
            is_subcomp=int(is_subcomp or 0),
            category=category,
            iface=iface,
        )

@dataclass
class ModelLink:
    """
    One SST-style link in the model.

    This is separate from the visual line. Later this should be saved to SQLite
    and eventually exported into an SST Python config.
    """

    link_id: int
    name: str
    latency: str
    source_node_id: int
    source_component_name: str
    source_port: str
    target_node_id: int
    target_component_name: str
    target_port: str
    link_type: str = "point_to_point"
