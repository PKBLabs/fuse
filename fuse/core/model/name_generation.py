# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Helpers for deterministic component instance-name generation.

FUSE lets users opt into explicit indexed names by including ``%d`` in a
component or composite-template name. The same helpers also provide the core
default of treating names as if they had an implicit ``_%d`` suffix when copies
or repeated placements need unique names.
"""

from __future__ import annotations

import re
from typing import Iterable


NAME_INDEX_TOKEN = "%d"


def has_name_index_token(name: str | None) -> bool:
    """Return true when *name* contains FUSE's index token."""
    return NAME_INDEX_TOKEN in str(name or "")


def render_name_template(template: str, index: int) -> str:
    """Render a user-provided name template with an integer index.

    All occurrences of ``%d`` are replaced. In normal use there is one token, but
    replacing all occurrences keeps behavior predictable if a user repeats it.
    """
    text = str(template or "Component").strip() or "Component"
    if NAME_INDEX_TOKEN not in text:
        return text
    return text.replace(NAME_INDEX_TOKEN, str(int(index)))


def implicit_name_template(base_name: str | None) -> str:
    """Return the default indexed template for a name without ``%d``."""
    base = str(base_name or "Component").strip() or "Component"
    if has_name_index_token(base):
        return base
    return f"{base}_{NAME_INDEX_TOKEN}"


def infer_template_from_rendered_name(name: str | None) -> str:
    """Infer a reusable template from an already rendered component name.

    This preserves the old ``Name_1``/``Name_2`` style by treating a trailing
    underscore-number suffix as an indexed name family. Other names use the core
    implicit ``_%d`` suffix.
    """
    text = str(name or "Component").strip() or "Component"
    if has_name_index_token(text):
        return text
    match = re.fullmatch(r"(.+)_\d+", text)
    if match:
        return f"{match.group(1)}_{NAME_INDEX_TOKEN}"
    return implicit_name_template(text)


def index_for_rendered_name(current_name: str, template: str) -> int | None:
    """Return the index that renders *current_name* from *template*, if any."""
    text = str(current_name or "")
    if NAME_INDEX_TOKEN not in str(template or ""):
        return None
    pattern = re.escape(str(template)).replace(re.escape(NAME_INDEX_TOKEN), r"(\d+)")
    match = re.fullmatch(pattern, text)
    if match is None:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def copy_start_index_for_name(current_name: str, template: str) -> int:
    """Return the first index to try when copying a node with *template*.

    If the displayed/source name is exactly the rendered index-zero form, trying
    from zero is fine because the source name itself is already in the used-name
    set. If the source was a custom name without a rendered ``_0`` suffix, start
    at one so copies become ``name_1``, ``name_2``, ... rather than creating a
    nearby ``name_0`` while the source remains ``name``.
    """
    rendered_index = index_for_rendered_name(str(current_name or ""), template)
    if rendered_index is not None:
        return max(0, rendered_index + 1)
    return 0 if str(current_name or "") == render_name_template(template, 0) else 1


def next_name_from_template(
    template: str,
    used_names: Iterable[str] | None = None,
    *,
    start_index: int = 0,
) -> tuple[str, int]:
    """Return the first unused rendered name and the index that produced it."""
    used = {str(name) for name in (used_names or set()) if str(name)}
    index = max(0, int(start_index))
    while True:
        candidate = render_name_template(template, index)
        if candidate and candidate not in used:
            return candidate, index
        index += 1


def template_for_source_name(name: str | None) -> str:
    """Return an explicit or inferred template for a source component name."""
    return infer_template_from_rendered_name(name)
