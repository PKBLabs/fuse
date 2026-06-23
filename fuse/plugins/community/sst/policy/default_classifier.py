# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Classify SST parameter metadata defaults and value kinds."""

from __future__ import annotations

import ast
import operator
import re
from typing import Any

from fuse.plugins.community.sst.policy.models import DefaultKind, ParamKind


_TYPE_HINT_RE = re.compile(r"^\s*\(([^)]+)\)")
_NUMERIC_LITERAL_RE = re.compile(r"^[+-]?(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?)$")
_UNIT_LITERAL_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?\s*[A-Za-z][A-Za-z0-9_/]*$")
_PLAIN_STRING_LITERAL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:\-./]*$")
_SYMBOLIC_DEFAULT_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_]*\s*[-+*/()]|[-+*/()]\s*[A-Za-z_][A-Za-z0-9_]*"
)

_NUMERIC_STRING_RE = re.compile(r"^[+-]?(?:0[xX][0-9a-fA-F]+|\d+)$")


_BYTE_UNITS = {
    "b": 1,
    "byte": 1,
    "bytes": 1,
    "kb": 1000,
    "mb": 1000**2,
    "gb": 1000**3,
    "tb": 1000**4,
    "kib": 1024,
    "mib": 1024**2,
    "gib": 1024**3,
    "tib": 1024**4,
}


def infer_kind_from_description(description: str | None) -> ParamKind:
    """Infer a JSON kind from a leading SST ``(type)`` description hint."""

    text = description or ""
    match = _TYPE_HINT_RE.search(text)

    if not match:
        return ParamKind.UNKNOWN

    hint = match.group(1).strip().lower()

    if "bool" in hint:
        return ParamKind.BOOL

    if "uint" in hint or "int" in hint or "long" in hint or "size_t" in hint:
        return ParamKind.INTEGER

    if "float" in hint or "double" in hint:
        return ParamKind.FLOAT

    if "unit" in hint:
        return ParamKind.UNIT

    if "string" in hint or "comma separated" in hint:
        return ParamKind.STRING

    return ParamKind.UNKNOWN


def metadata_default_is_symbolic(default_value: Any) -> bool:
    """Return true if an SST default looks like a component-internal expression."""

    if not isinstance(default_value, str):
        return False

    text = default_value.strip()

    if not text:
        return False

    lowered = text.lower()

    if lowered in {"true", "false", "yes", "no", "on", "off"}:
        return False

    if _NUMERIC_LITERAL_RE.fullmatch(text):
        return False

    if _UNIT_LITERAL_RE.fullmatch(text):
        return False

    if _PLAIN_STRING_LITERAL_RE.fullmatch(text):
        return False

    if text in {"[]", "{}"}:
        return False

    return bool(_SYMBOLIC_DEFAULT_RE.search(text))


def classify_default(default_value: Any, kind: ParamKind = ParamKind.UNKNOWN) -> DefaultKind:
    """Classify an SST metadata default."""

    if default_value is None:
        return DefaultKind.NONE

    if isinstance(default_value, str):
        text = default_value.strip()

        if not text:
            return DefaultKind.EMPTY

        if text in {"<required>", "required"}:
            return DefaultKind.NONE

        if metadata_default_is_symbolic(text):
            return DefaultKind.SYMBOLIC

    try:
        normalize_value(default_value, kind)
    except ValueError:
        return DefaultKind.UNKNOWN

    return DefaultKind.LITERAL


def looks_like_untyped_number(value: Any) -> bool:
    """Return true for numeric-looking user strings whose policy is unknown."""

    if isinstance(value, int) and not isinstance(value, bool):
        return True

    if not isinstance(value, str):
        return False

    return bool(_NUMERIC_STRING_RE.fullmatch(value.strip()))


def _replace_byte_units(expr: str) -> str:
    """Replace byte-unit tokens like 4GiB with integer literals."""

    def repl(match: re.Match[str]) -> str:
        number = match.group("number")
        unit = match.group("unit").lower()
        multiplier = _BYTE_UNITS[unit]
        value = float(number) * multiplier

        if not value.is_integer():
            raise ValueError(f"Byte-unit value {match.group(0)!r} is not an integer")

        return str(int(value))

    pattern = re.compile(
        r"(?P<number>(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?))\s*(?P<unit>"
        + "|".join(sorted(_BYTE_UNITS, key=len, reverse=True))
        + r")\b",
        re.IGNORECASE,
    )

    return pattern.sub(repl, expr)


_ALLOWED_INT_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.BitXor: operator.xor,
}

_ALLOWED_INT_UNARY = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
    ast.Invert: operator.invert,
}


def _eval_int_ast(node: ast.AST) -> int:
    if isinstance(node, ast.Expression):
        return _eval_int_ast(node.body)

    if isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
        return int(node.value)

    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_INT_BINOPS:
        left = _eval_int_ast(node.left)
        right = _eval_int_ast(node.right)
        return int(_ALLOWED_INT_BINOPS[type(node.op)](left, right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_INT_UNARY:
        return int(_ALLOWED_INT_UNARY[type(node.op)](_eval_int_ast(node.operand)))

    raise ValueError("integer expression may only contain integer literals and arithmetic operators")


def parse_integer_value(value: Any) -> int:
    """Parse a user/SST value as a JSON integer."""

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        raise ValueError(f"expected integer value, got {value!r}")

    if not isinstance(value, str):
        raise ValueError(f"expected integer value, got {value!r}")

    text = value.strip()

    if not text:
        raise ValueError("expected integer value, got empty string")

    # Fast path for decimal/hex literals.
    if re.fullmatch(r"[+-]?0[xX][0-9a-fA-F]+", text):
        return int(text, 16)

    if re.fullmatch(r"[+-]?\d+", text):
        return int(text, 10)

    expr = _replace_byte_units(text)

    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"expected integer expression, got {value!r}") from exc

    return _eval_int_ast(tree)


def normalize_value(value: Any, kind: ParamKind) -> Any:
    """Normalize a raw parameter value to the requested JSON kind."""

    if kind == ParamKind.INTEGER:
        return parse_integer_value(value)

    if kind == ParamKind.BOOL:
        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            if value in (0, 1):
                return bool(value)
            raise ValueError(f"expected boolean value, got {value!r}")

        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"1", "true", "yes", "on"}:
                return True
            if text in {"0", "false", "no", "off"}:
                return False

        raise ValueError(f"expected boolean value, got {value!r}")

    if kind == ParamKind.FLOAT:
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"expected floating-point value, got {value!r}") from exc

    if kind in {ParamKind.STRING, ParamKind.UNIT}:
        if isinstance(value, str):
            return value
        return str(value)

    if kind in {ParamKind.ANY, ParamKind.UNKNOWN}:
        return value

    return value
