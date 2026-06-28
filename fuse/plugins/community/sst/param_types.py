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
from __future__ import annotations

import ast
from decimal import Decimal, InvalidOperation
from enum import Enum
import re
from typing import Any


class SSTParamKind(str, Enum):
    """Coarse JSON value kinds used by the SST JSON exporter."""

    UNKNOWN = "unknown"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOL = "bool"
    UNIT_ALGEBRA = "unit_algebra"
    ANY = "any"


_PARAM_TYPE_RE = re.compile(r"^\s*\((?P<hint>[^)]*)\)")
_NUMERIC_BYTE_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<number>(?:0[xX][0-9A-Fa-f_]+)|(?:\d+(?:\.\d+)?))\s*"
    r"(?P<unit>[KMGTPE]?i?B|[KMGTPE]?B)\b"
)
_NUMERIC_STRING_RE = re.compile(
    r"^\s*[+-]?(?:(?:0[xX][0-9A-Fa-f_]+)|(?:\d+(?:\.\d+)?))\s*$"
)

_INTEGER_HINTS = {
    "int",
    "integer",
    "uint",
    "unsigned",
    "unsigned int",
    "uint32_t",
    "uint64_t",
    "int32_t",
    "int64_t",
    "short",
    "long",
    "long long",
    "size_t",
}

_FLOAT_HINTS = {
    "float",
    "double",
    "real",
}

_BOOL_HINTS = {
    "bool",
    "boolean",
}

_STRING_HINTS = {
    "char",
    "string",
    "str",
    "unit",
    "unit algebra",
    "unitalgebra",
    "time",
    "frequency",
}

_BYTE_UNITS = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "PB": 1000**5,
    "EB": 1000**6,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
    "PiB": 1024**5,
    "EiB": 1024**6,
}

# This table is intentionally small and curated. It fills gaps where imported
# sst-info metadata does not include a formal leading "(uint)" or "(int)" hint.
# Add to this table as FUSE gains first-class support for more SST elements.
CURATED_PARAM_KINDS: dict[tuple[str, str], SSTParamKind] = {
    ("memHierarchy.Cache", "L1"): SSTParamKind.INTEGER,
    ("memHierarchy.Cache", "access_latency_cycles"): SSTParamKind.INTEGER,
    ("memHierarchy.Cache", "associativity"): SSTParamKind.INTEGER,
    ("memHierarchy.Cache", "cache_line_size"): SSTParamKind.INTEGER,
    ("memHierarchy.Cache", "coherence_protocol"): SSTParamKind.STRING,
    ("memHierarchy.Cache", "cache_type"): SSTParamKind.STRING,
    ("memHierarchy.DirectoryController", "addr_range_start"): SSTParamKind.INTEGER,
    ("memHierarchy.DirectoryController", "addr_range_end"): SSTParamKind.INTEGER,
    ("memHierarchy.DirectoryController", "cache_line_size"): SSTParamKind.INTEGER,
    ("memHierarchy.DirectoryController", "coherence_protocol"): SSTParamKind.STRING,
    ("memHierarchy.DirectoryController", "node"): SSTParamKind.INTEGER,
    ("memHierarchy.MemController", "addr_range_start"): SSTParamKind.INTEGER,
    ("memHierarchy.MemController", "addr_range_end"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "flush_freq"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "flushcache_freq"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "flushinv_freq"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "llsc_freq"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "maxOutstanding"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "memFreq"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "opCount"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "read_freq"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "reqsPerIssue"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "rngseed"): SSTParamKind.INTEGER,
    ("memHierarchy.standardCPU", "write_freq"): SSTParamKind.INTEGER,
}


def _split_hint(raw_hint: str) -> set[str]:
    return {
        part.strip().lower()
        for part in re.split(r"[/,;|]", raw_hint)
        if part.strip()
    }


def infer_param_kind_from_metadata(
    description: str = "",
    default_value: str = "",
) -> SSTParamKind:
    """
    Infer a coarse SST JSON parameter kind from imported sst-info metadata.

    sst-info is not a complete typed schema, but many SST parameter
    descriptions start with hints such as "(uint)", "(int)", "(bool)", or
    "(string)". FUSE treats those as best-effort type hints and uses curated
    overrides for cases where the metadata is ambiguous.
    """

    description = str(description or "")
    default_value = str(default_value or "")

    match = _PARAM_TYPE_RE.match(description)
    if match:
        hint_parts = _split_hint(match.group("hint"))

        if hint_parts & _BOOL_HINTS:
            return SSTParamKind.BOOL

        if hint_parts & _INTEGER_HINTS:
            return SSTParamKind.INTEGER

        if hint_parts & _FLOAT_HINTS:
            return SSTParamKind.FLOAT

        if hint_parts & _STRING_HINTS:
            if {"unit", "unit algebra", "unitalgebra", "time", "frequency"} & hint_parts:
                return SSTParamKind.UNIT_ALGEBRA
            return SSTParamKind.STRING

    if default_value.lower() in {"true", "false"}:
        return SSTParamKind.BOOL

    return SSTParamKind.UNKNOWN


def resolve_param_kind(
    component_type: str,
    param_name: str,
    metadata: dict[str, Any] | None = None,
) -> SSTParamKind:
    """Resolve the export kind for one SST parameter."""

    override = CURATED_PARAM_KINDS.get((str(component_type), str(param_name)))
    if override is not None:
        return override

    metadata = metadata or {}
    return infer_param_kind_from_metadata(
        metadata.get("description", ""),
        metadata.get("default_val", ""),
    )


def _replace_byte_units(expression: str) -> str:
    """Replace byte-unit tokens such as 4KiB with integer byte counts."""

    def replace(match: re.Match) -> str:
        number_text = match.group("number").replace("_", "")
        unit = match.group("unit")
        multiplier = _BYTE_UNITS[unit]

        try:
            if number_text.lower().startswith("0x"):
                number = Decimal(int(number_text, 0))
            else:
                number = Decimal(number_text)
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"Invalid numeric value {number_text!r}.") from exc

        value = number * multiplier
        if value != value.to_integral_value():
            raise ValueError(
                f"Byte-unit value {match.group(0)!r} is not an integer number of bytes."
            )

        return str(int(value))

    return _NUMERIC_BYTE_TOKEN_RE.sub(replace, expression)


def _eval_integer_ast(node: ast.AST) -> int:
    """Evaluate a deliberately small integer-only expression AST."""

    if isinstance(node, ast.Expression):
        return _eval_integer_ast(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int):
            raise ValueError("Expected an integer expression.")
        return int(node.value)

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _eval_integer_ast(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value

    if isinstance(node, ast.BinOp):
        left = _eval_integer_ast(node.left)
        right = _eval_integer_ast(node.right)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.FloorDiv):
            if right == 0:
                raise ValueError("Integer expression divides by zero.")
            return left // right
        if isinstance(node.op, ast.Mod):
            if right == 0:
                raise ValueError("Integer expression divides by zero.")
            return left % right
        if isinstance(node.op, ast.LShift):
            if right < 0:
                raise ValueError("Shift count cannot be negative.")
            return left << right
        if isinstance(node.op, ast.RShift):
            if right < 0:
                raise ValueError("Shift count cannot be negative.")
            return left >> right
        if isinstance(node.op, ast.BitOr):
            return left | right
        if isinstance(node.op, ast.BitAnd):
            return left & right
        if isinstance(node.op, ast.BitXor):
            return left ^ right

    raise ValueError(
        "Only integer literals and simple integer arithmetic are supported."
    )


def parse_integer_param_value(value: Any) -> int:
    """
    Parse a FUSE-edited integer parameter into a JSON integer.

    Accepted text forms include decimal, hexadecimal, underscores, memory-size
    units such as 4GiB, and simple arithmetic such as 4GiB-1 or (1 << 32) - 1.
    """

    if isinstance(value, bool):
        raise ValueError("Boolean values are not integer parameters.")

    if isinstance(value, int):
        return value

    text = str(value).strip()
    if not text:
        raise ValueError("Integer parameter is empty.")

    if text == "uint64_t-1":
        return (1 << 64) - 1

    expression = _replace_byte_units(text)

    try:
        parsed = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid integer expression {value!r}.") from exc

    return _eval_integer_ast(parsed)


def parse_bool_param_value(value: Any) -> bool:
    """Parse common SST boolean parameter spellings into a JSON bool."""

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False

    raise ValueError(f"Invalid boolean value {value!r}.")


def parse_float_param_value(value: Any) -> float:
    """Parse a plain numeric SST parameter into a JSON number."""

    if isinstance(value, bool):
        raise ValueError("Boolean values are not floating-point parameters.")

    if isinstance(value, int | float):
        return float(value)

    text = str(value).strip()
    if not text:
        raise ValueError("Floating-point parameter is empty.")

    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"Invalid floating-point value {value!r}.") from exc


def normalize_param_value(
    component_type: str,
    param_name: str,
    value: Any,
    metadata: dict[str, Any] | None = None,
) -> Any:
    """
    Normalize a FUSE parameter value for SST JSON export.

    Unknown/string/unit parameters are preserved. Numeric/bool conversion only
    happens when FUSE has a known policy from curated overrides or metadata.
    """

    kind = resolve_param_kind(component_type, param_name, metadata)

    if kind == SSTParamKind.INTEGER:
        return parse_integer_param_value(value)

    if kind == SSTParamKind.BOOL:
        return parse_bool_param_value(value)

    if kind == SSTParamKind.FLOAT:
        return parse_float_param_value(value)

    return value


def normalize_params(
    component_type: str,
    params: dict[str, Any],
    metadata_by_name: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize every parameter in a component/subcomponent parameter map."""

    metadata_by_name = metadata_by_name or {}
    return {
        key: normalize_param_value(
            component_type,
            key,
            value,
            metadata_by_name.get(key, {}),
        )
        for key, value in params.items()
    }


def looks_like_untyped_number(value: Any) -> bool:
    """Return True for unknown string values that may need a policy entry."""

    return isinstance(value, str) and bool(_NUMERIC_STRING_RE.match(value))