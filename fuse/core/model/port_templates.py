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
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU General Public License for more details.
from __future__ import annotations

import ast
import itertools
import re
from typing import Any


_PRINTF_EXPR_TOKEN_RE = re.compile(r"%\((?P<expr>[^)]+)\)d")


class PortTemplateExpressionError(ValueError):
    """Raised when a port-template expression cannot be safely evaluated."""


def _safe_int(value: Any, default: int | None = None) -> int | None:
    try:
        if isinstance(value, bool):
            return int(value)
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _numeric_context(
    parameters: dict[str, Any] | None = None,
    variable_port_counts: dict[str, Any] | None = None,
) -> dict[str, int]:
    context: dict[str, int] = {}

    for source in (parameters or {}, variable_port_counts or {}):
        for key, value in source.items():
            if not key:
                continue
            parsed = _safe_int(value)
            if parsed is not None:
                context[str(key)] = parsed

    # firefly.loopBack advertises a historical SST port pattern containing
    # ``num_vNics/nicsPerNode`` even though its public parameters are
    # ``numCores`` and ``nicsPerNode``. In Firefly this is the number of
    # virtual NIC/core endpoints, so derive it when the catalog did not
    # expose it directly.
    if "num_vNics" not in context:
        num_cores = context.get("numCores", 1)
        nics_per_node = context.get("nicsPerNode", 1)
        context["num_vNics"] = max(0, num_cores) * max(0, nics_per_node)

    return context


def _eval_expr_node(node: ast.AST, context: dict[str, int]) -> int:
    if isinstance(node, ast.Expression):
        return _eval_expr_node(node.body, context)

    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return int(node.value)

    if isinstance(node, ast.Name):
        return int(context.get(node.id, 1))

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_expr_node(node.operand, context)

    if isinstance(node, ast.BinOp):
        left = _eval_expr_node(node.left, context)
        right = _eval_expr_node(node.right, context)

        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, (ast.Div, ast.FloorDiv)):
            if right == 0:
                raise PortTemplateExpressionError("division by zero")
            return left // right

    raise PortTemplateExpressionError(
        f"unsupported port-template expression: {ast.dump(node)}"
    )


def evaluate_port_template_count(
    expression: str,
    *,
    parameters: dict[str, Any] | None = None,
    variable_port_counts: dict[str, Any] | None = None,
) -> int:
    """Safely evaluate a small integer expression used as an SST port count."""

    context = _numeric_context(parameters, variable_port_counts)
    tree = ast.parse(str(expression or "1"), mode="eval")
    return max(0, _eval_expr_node(tree, context))


def expand_parametric_port_template(
    template: str,
    *,
    parameters: dict[str, Any] | None = None,
    variable_port_counts: dict[str, Any] | None = None,
) -> list[str]:
    """
    Expand SST-style printf port templates into concrete port names.

    SST catalogs sometimes contain patterns such as
    ``nic%(nicsPerNode)dcore%(num_vNics/nicsPerNode)d``. SST's JSON loader
    does not accept those patterns in links; links must use concrete names
    such as ``nic0core0``. Each ``%(...)d`` token is interpreted as a count
    expression and expanded over ``range(count)``.
    """

    text = str(template or "")
    tokens = list(_PRINTF_EXPR_TOKEN_RE.finditer(text))
    if not tokens:
        return [text] if text else []

    counts: list[int] = []
    for token in tokens:
        try:
            counts.append(
                evaluate_port_template_count(
                    token.group("expr"),
                    parameters=parameters,
                    variable_port_counts=variable_port_counts,
                )
            )
        except (SyntaxError, PortTemplateExpressionError):
            return [text] if text else []

    if any(count <= 0 for count in counts):
        return []

    names: list[str] = []
    for values in itertools.product(*(range(count) for count in counts)):
        pieces: list[str] = []
        last_index = 0
        for token, value in zip(tokens, values):
            pieces.append(text[last_index: token.start()])
            pieces.append(str(value))
            last_index = token.end()
        pieces.append(text[last_index:])
        names.append("".join(pieces))

    return names
