#!/usr/bin/env python3
# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

"""Build/audit SST runtime overlay candidates from SST source.

This maintainer tool scans SST source for runtime ``loadUserSubComponent()``
slots and compares them with both the raw sst-info component catalog and the
versioned FUSE runtime overlay. It is intentionally conservative: ambiguous
owners remain in the report for human review instead of being silently inserted
into committed overlays.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


LOAD_USER_SUBCOMPONENT_RE = re.compile(
    r"loadUserSubComponent(?:Array)?\s*<(?P<api>[^>]+)>\s*\(\s*\"(?P<slot>[^\"]+)\"",
    re.DOTALL,
)
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
CLASS_RE = re.compile(r"\bclass\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\b")
METHOD_DEF_RE = re.compile(
    r"(?m)^\s*(?:[A-Za-z_][\w:<>*&~]*\s+)?(?P<class>[A-Za-z_]\w*)::[~A-Za-z_]\w*\s*\("
)
REGISTER_NAMES = ("SST_ELI_REGISTER_COMPONENT", "SST_ELI_REGISTER_SUBCOMPONENT")


@dataclass(frozen=True)
class RuntimeSlotCandidate:
    component_type: str
    owner_class: str
    slot_name: str
    api: str
    source_path: str
    line: int
    already_declared: bool = False
    already_overlayed: bool = False
    ambiguous_owner_types: tuple[str, ...] = ()


def _strip_comments(text: str) -> str:
    """Remove comments while preserving string literals and line count."""
    out: list[str] = []
    i = 0
    in_string = False
    in_char = False
    in_line_comment = False
    in_block_comment = False
    escape = False
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                out.append(ch)
            else:
                out.append(" ")
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                out.extend("  ")
                in_block_comment = False
                i += 2
            else:
                out.append("\n" if ch == "\n" else " ")
                i += 1
            continue
        if in_string:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if in_char:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_char = False
            i += 1
            continue
        if ch == "/" and nxt == "/":
            out.extend("  ")
            in_line_comment = True
            i += 2
            continue
        if ch == "/" and nxt == "*":
            out.extend("  ")
            in_block_comment = True
            i += 2
            continue
        if ch == '"':
            in_string = True
        elif ch == "'":
            in_char = True
        out.append(ch)
        i += 1
    return "".join(out)


def _strings_from_macro_body(body: str) -> list[str]:
    return [bytes(match.group(1), "utf-8").decode("unicode_escape") for match in STRING_RE.finditer(body)]


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _find_macro_bodies(text: str, macro_name: str) -> list[tuple[int, str]]:
    bodies: list[tuple[int, str]] = []
    needle = macro_name + "("
    start = 0
    while True:
        macro_start = text.find(needle, start)
        if macro_start < 0:
            break
        open_paren = macro_start + len(macro_name)
        depth = 0
        in_string = False
        in_char = False
        escape = False
        i = open_paren
        while i < len(text):
            ch = text[i]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
            elif in_char:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == "'":
                    in_char = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "'":
                    in_char = True
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
                    if depth == 0:
                        bodies.append((macro_start, text[open_paren + 1 : i]))
                        start = i + 1
                        break
            i += 1
        else:
            break
    return bodies


def _split_top_level_args(body: str) -> list[str]:
    args: list[str] = []
    buf: list[str] = []
    depth = 0
    in_string = False
    in_char = False
    escape = False
    for ch in body:
        if in_string:
            buf.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if in_char:
            buf.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == "'":
                in_char = False
            continue
        if ch == '"':
            in_string = True
            buf.append(ch)
        elif ch == "'":
            in_char = True
            buf.append(ch)
        elif ch in "({[":
            depth += 1
            buf.append(ch)
        elif ch in ")}]":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        args.append("".join(buf).strip())
    return args


def _unquote(value: str) -> str | None:
    match = re.match(r'\s*"((?:[^"\\]|\\.)*)"\s*$', value)
    if not match:
        return None
    return bytes(match.group(1), "utf-8").decode("unicode_escape")


def _declared_slots_from_component_catalog(path: Path | None) -> dict[str, set[str]]:
    if path is None or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for component in raw.get("components", []) or []:
        element = component.get("element") or component.get("element_name") or ""
        name = component.get("name") or component.get("component_name") or ""
        component_type = component.get("type") or f"{element}.{name}".strip(".")
        if not component_type or "." not in component_type:
            continue
        result[component_type] = {
            str(slot.get("name", "") or "")
            for slot in component.get("subcomp_slots", []) or []
            if str(slot.get("name", "") or "").strip()
        }
    return result


def _component_types_from_catalog(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: set[str] = set()
    for component in raw.get("components", []) or []:
        element = component.get("element") or component.get("element_name") or ""
        name = component.get("name") or component.get("component_name") or ""
        component_type = component.get("type") or f"{element}.{name}".strip(".")
        if component_type and "." in component_type:
            result.add(component_type)
    return result


def _overlay_slots(path: Path | None) -> dict[str, set[str]]:
    if path is None or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[str, set[str]] = {}
    for component_type, entry in (raw.get("components", {}) or {}).items():
        slots = set((entry.get("runtime_slots", {}) or {}).keys())
        if slots:
            result[component_type] = slots
    return result


def _manual_resolutions(path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    """Return human-reviewed decisions for otherwise ambiguous candidates.

    Runtime overlays should only add concrete executable slots. Some
    ``loadUserSubComponent`` calls live in base/helper classes and are already
    declared by the concrete SST element types through ELI metadata. Those
    cases should not be inserted into the runtime overlay, but they still need
    a durable review record so audits can distinguish them from unreviewed
    scanner misses.
    """

    if path is None or not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in raw.get("manual_resolutions", []) or []:
        owner_class = str(entry.get("owner_class", "") or "").strip()
        slot_name = str(entry.get("slot_name", "") or "").strip()
        if owner_class and slot_name:
            result[(owner_class, slot_name)] = entry
    return result


def _component_class_index(source_root: Path, catalog_types: set[str]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for path in sorted(source_root.rglob("*")):
        if path.suffix not in {".h", ".hh", ".hpp", ".cc", ".cpp"}:
            continue
        try:
            text = _strip_comments(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            continue
        for macro_name in REGISTER_NAMES:
            for _, body in _find_macro_bodies(text, macro_name):
                args = _split_top_level_args(body)
                if len(args) < 3:
                    continue
                class_name = args[0].strip().split()[-1].split("::")[-1]
                direct_element = _unquote(args[1])
                direct_name = _unquote(args[2])
                component_type = f"{direct_element}.{direct_name}" if direct_element and direct_name else ""
                if component_type:
                    index.setdefault(class_name, set()).add(component_type)
                    continue

                strings = _strings_from_macro_body(body)
                candidates: list[str] = []
                for i, element in enumerate(strings):
                    for name in strings[i + 1 : i + 4]:
                        candidate_type = f"{element}.{name}"
                        if candidate_type in catalog_types:
                            candidates.append(candidate_type)
                for candidate_type in sorted(set(candidates)):
                    index.setdefault(class_name, set()).add(candidate_type)
    return index


def _owner_class(text: str, offset: int, known_classes: set[str]) -> str:
    prefix = text[:offset]
    method_matches = list(METHOD_DEF_RE.finditer(prefix))
    for match in reversed(method_matches):
        owner = match.group("class")
        if owner in known_classes:
            return owner
    if method_matches:
        return method_matches[-1].group("class")
    class_matches = list(CLASS_RE.finditer(prefix))
    for match in reversed(class_matches):
        owner = match.group("name")
        if owner in known_classes:
            return owner
    if class_matches:
        return class_matches[-1].group("name")
    return ""


def _scan_source(source_root: Path, catalog_types: set[str]) -> list[RuntimeSlotCandidate]:
    class_index = _component_class_index(source_root, catalog_types)
    candidates: list[RuntimeSlotCandidate] = []
    for path in sorted(source_root.rglob("*")):
        if path.suffix not in {".h", ".hh", ".hpp", ".cc", ".cpp"}:
            continue
        try:
            raw_text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        text = _strip_comments(raw_text)
        for match in LOAD_USER_SUBCOMPONENT_RE.finditer(text):
            owner = _owner_class(text, match.start(), set(class_index))
            owner_types = sorted(class_index.get(owner, set()))
            component_type = owner_types[0] if len(owner_types) == 1 else ""
            candidates.append(
                RuntimeSlotCandidate(
                    component_type=component_type,
                    owner_class=owner,
                    slot_name=match.group("slot"),
                    api=" ".join(match.group("api").split()),
                    source_path=str(path.relative_to(source_root)),
                    line=_line_number(text, match.start()),
                    ambiguous_owner_types=tuple(owner_types) if len(owner_types) > 1 else (),
                )
            )
    return candidates


def build_runtime_overlay_candidate_report(
    *,
    source_root: Path,
    component_catalog: Path | None = None,
    overlay: Path | None = None,
) -> dict[str, Any]:
    catalog_types = _component_types_from_catalog(component_catalog)
    declared_slots = _declared_slots_from_component_catalog(component_catalog)
    overlay_slots = _overlay_slots(overlay)
    manual_resolutions = _manual_resolutions(overlay)

    candidates = []
    for candidate in _scan_source(source_root, catalog_types):
        already_declared = candidate.slot_name in declared_slots.get(candidate.component_type, set())
        already_overlayed = candidate.slot_name in overlay_slots.get(candidate.component_type, set())
        unknown_or_ambiguous = not candidate.component_type
        manual_resolution = manual_resolutions.get((candidate.owner_class, candidate.slot_name))
        reviewed_no_overlay = bool(manual_resolution and not bool(manual_resolution.get("requires_overlay", False)))
        candidates.append(
            {
                "component_type": candidate.component_type,
                "owner_class": candidate.owner_class,
                "ambiguous_owner_types": list(candidate.ambiguous_owner_types),
                "slot_name": candidate.slot_name,
                "api": candidate.api,
                "source": f"{candidate.source_path}:{candidate.line}",
                "already_declared": already_declared,
                "already_overlayed": already_overlayed,
                "manual_resolution": manual_resolution or {},
                "reviewed_no_overlay": reviewed_no_overlay,
                "needs_overlay": not unknown_or_ambiguous and not already_declared and not already_overlayed,
                "unknown_or_ambiguous_owner": unknown_or_ambiguous and not reviewed_no_overlay,
                "owner_resolution_status": (
                    "reviewed_no_overlay"
                    if reviewed_no_overlay
                    else "unknown_or_ambiguous"
                    if unknown_or_ambiguous
                    else "resolved"
                ),
            }
        )

    candidates.sort(key=lambda item: (item["component_type"], item["owner_class"], item["slot_name"], item["source"]))
    missing = [item for item in candidates if item["needs_overlay"]]
    unknown = [item for item in candidates if item["unknown_or_ambiguous_owner"]]
    reviewed = [item for item in candidates if item["reviewed_no_overlay"]]
    return {
        "schema_version": 1,
        "source_root": str(source_root),
        "component_catalog": str(component_catalog or ""),
        "overlay": str(overlay or ""),
        "candidate_count": len(candidates),
        "missing_overlay_count": len(missing),
        "unknown_or_ambiguous_owner_count": len(unknown),
        "reviewed_no_overlay_count": len(reviewed),
        "candidates": candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--component-catalog", type=Path)
    parser.add_argument("--overlay", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Return nonzero when runtime slots are found that are neither in sst-info nor in the overlay.",
    )
    parser.add_argument(
        "--fail-on-unknown-owner",
        action="store_true",
        help="Return nonzero when loadUserSubComponent() owner components cannot be mapped to catalog types.",
    )
    args = parser.parse_args()

    report = build_runtime_overlay_candidate_report(
        source_root=args.source_root,
        component_catalog=args.component_catalog,
        overlay=args.overlay,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.fail_on_missing and report["missing_overlay_count"]:
        return 1
    if args.fail_on_unknown_owner and report["unknown_or_ambiguous_owner_count"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
