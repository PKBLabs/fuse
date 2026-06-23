# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Policy model objects for SST JSON export decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ParamKind(str, Enum):
    """JSON value kind to use for an SST parameter."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOL = "bool"
    UNIT = "unit"
    ANY = "any"
    UNKNOWN = "unknown"


class DefaultKind(str, Enum):
    """How FUSE understands an SST metadata default value."""

    NONE = "none"
    LITERAL = "literal"
    SYMBOLIC = "symbolic"
    EMPTY = "empty"
    INTERNAL = "internal"
    UNKNOWN = "unknown"


class MissingSeverity(str, Enum):
    """Normal export-validation severity for a missing parameter."""

    SILENT = "silent"
    WARNING = "warning"
    ERROR = "error"


class RequiredContext(str, Enum):
    """Context in which an SST-required parameter should be enforced."""

    ALWAYS = "always"
    TOP_LEVEL_COMPONENT = "top_level_component"
    ATTACHED_SUBCOMPONENT = "attached_subcomponent"
    MANUAL_SUBCOMPONENT = "manual_subcomponent"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ParamPolicy:
    """Resolved policy for one SST parameter."""

    name: str
    kind: ParamKind = ParamKind.UNKNOWN
    required: bool = False
    required_context: RequiredContext = RequiredContext.UNKNOWN
    default_value: Any = None
    default_kind: DefaultKind = DefaultKind.NONE
    export_default: bool = False
    missing_severity: MissingSeverity = MissingSeverity.SILENT
    validate_user_value: bool = True
    notes: str = ""
