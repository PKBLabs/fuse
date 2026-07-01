#!/usr/bin/env python3
"""Build a starter FUSE SST policy catalog from SST source metadata.

This is an offline maintainer tool. The runtime exporter does not execute it.
It intentionally produces conservative policies:
  * literal defaults may be exported
  * symbolic/computed defaults are left for SST to resolve
  * curated overrides should be reviewed before committing the catalog
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


REGISTER_RE = re.compile(
    r"SST_ELI_REGISTER_(?:COMPONENT|SUBCOMPONENT)\s*\((?P<body>.*?)\)\s*;",
    re.DOTALL,
)
PARAM_BLOCK_RE = re.compile(r"SST_ELI_DOCUMENT_PARAMS\s*\((?P<body>.*?)\)\s*;", re.DOTALL)
PARAM_ENTRY_RE = re.compile(
    r'\{\s*"(?P<name>[^"]+)"\s*,\s*"(?P<description>(?:[^"\\]|\\.)*)"(?:\s*,\s*(?P<default>NULL|"(?:[^"\\]|\\.)*"))?\s*\}',
    re.DOTALL,
)
STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
SST_NAMESPACED_TYPE_DEFAULT_RE = re.compile(r"^SST::[A-Za-z_][A-Za-z0-9_:.]*$")
SST_ELEMENT_TYPE_DEFAULT_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.([A-Za-z_][A-Za-z0-9_]*)$"
)


def _strings_from_macro_body(body: str) -> list[str]:
    return [bytes(match.group(1), "utf-8").decode("unicode_escape") for match in STRING_RE.finditer(body)]


def _default_from_entry(value: str | None) -> tuple[bool, Any]:
    if value is None or value.strip() == "NULL":
        return True, None

    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return False, bytes(value[1:-1], "utf-8").decode("unicode_escape")

    return False, value


def _infer_kind(description: str) -> str:
    text = description.strip().lower()
    if text.startswith("(bool"):
        return "bool"
    if text.startswith("(uint") or text.startswith("(int") or text.startswith("(uint64") or text.startswith("(size"):
        return "integer"
    if text.startswith("(float") or text.startswith("(double"):
        return "float"
    if text.startswith("(string") or text.startswith("(comma separated"):
        return "string"
    return "unknown"


def _is_internal_type_default(value: Any, kind: str) -> bool:
    if kind not in {"unknown", "any"}:
        return False

    if not isinstance(value, str):
        return False

    text = value.strip()

    if not text:
        return False

    if "::" in text or text.startswith("SST::"):
        return bool(SST_NAMESPACED_TYPE_DEFAULT_RE.fullmatch(text))

    if "." in text and "/" not in text and " " not in text:
        match = SST_ELEMENT_TYPE_DEFAULT_RE.fullmatch(text)
        return bool(match and any(char.isupper() for char in match.group(1)))

    return False


def _is_symbolic(value: Any) -> bool:
    if not isinstance(value, str):
        return False

    text = value.strip()
    if not text:
        return False

    if re.fullmatch(r"[+-]?(?:0[xX][0-9a-fA-F]+|\d+(?:\.\d+)?)", text):
        return False
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?\s*[A-Za-z][A-Za-z0-9_/]*", text):
        return False
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_:\-./]*", text):
        return False
    if text.lower() in {"true", "false", "yes", "no", "on", "off"}:
        return False
    if text in {"[]", "{}"}:
        return False

    return bool(re.search(r"[A-Za-z_][A-Za-z0-9_]*\s*[-+*/()]|[-+*/()]\s*[A-Za-z_][A-Za-z0-9_]*", text))


def extract_catalog(source_root: Path, version: str) -> dict[str, Any]:
    catalog: dict[str, Any] = {
        "schema_version": 1,
        "sst_version": version,
        "source": {"source_root": str(source_root)},
        "components": {},
    }

    for path in sorted(source_root.rglob("*")):
        if path.suffix not in {".h", ".hh", ".hpp", ".cc", ".cpp"}:
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        registrations = list(REGISTER_RE.finditer(text))
        params = list(PARAM_BLOCK_RE.finditer(text))

        if not registrations or not params:
            continue

        # Most SST classes keep one params block near their ELI registration.
        for index, reg in enumerate(registrations):
            strings = _strings_from_macro_body(reg.group("body"))
            if len(strings) < 2:
                continue

            element, name = strings[0], strings[1]
            component_type = f"{element}.{name}"

            next_reg_start = registrations[index + 1].start() if index + 1 < len(registrations) else len(text)
            candidate_blocks = [
                block for block in params
                if reg.end() <= block.start() <= next_reg_start or block.end() <= reg.start()
            ]

            if not candidate_blocks:
                candidate_blocks = params[:1]

            block = min(candidate_blocks, key=lambda item: abs(item.start() - reg.start()))
            component = catalog["components"].setdefault(component_type, {"params": {}})

            for entry in PARAM_ENTRY_RE.finditer(block.group("body")):
                required, default_value = _default_from_entry(entry.group("default"))
                kind = _infer_kind(entry.group("description"))
                default_kind = "none"
                export_default = False

                if required:
                    missing_severity = "error"
                else:
                    missing_severity = "silent"
                    if default_value in (None, ""):
                        default_kind = "empty"
                    elif _is_internal_type_default(default_value, kind):
                        default_kind = "internal"
                    elif _is_symbolic(default_value):
                        default_kind = "symbolic"
                    else:
                        default_kind = "literal"
                        export_default = True

                component["params"][entry.group("name")] = {
                    "kind": kind,
                    "required": required,
                    "default_value": default_value,
                    "default_kind": default_kind,
                    "export_default": export_default,
                    "missing_severity": missing_severity,
                }

    return catalog


def merge_override(base: dict[str, Any], override_path: Path | None) -> dict[str, Any]:
    if override_path is None or not override_path.exists():
        return base

    try:
        import yaml  # type: ignore
    except Exception as exc:
        raise SystemExit("YAML overrides require PyYAML") from exc

    override = yaml.safe_load(override_path.read_text(encoding="utf-8")) or {}
    components = override.get("components", {})

    for component_type, component_override in components.items():
        component = base.setdefault("components", {}).setdefault(component_type, {"params": {}})
        for param_name, param_override in component_override.get("params", {}).items():
            component.setdefault("params", {}).setdefault(param_name, {}).update(param_override or {})

    return base


def build_policy_catalog(
    *,
    sst_version: str,
    source_root: str | Path,
    out_path: str | Path,
    overrides: str | Path | None = None,
) -> None:
    """
    Build one SST policy catalog.

    This is used by both:
    - python -m fuse.plugins.community.sst.policy.build_catalog
    - SST plugin bootstrap when explicit rebuild is requested
    """

    source_root = Path(source_root)
    out_path = Path(out_path)
    override_path = Path(overrides) if overrides is not None else None

    catalog = extract_catalog(source_root, sst_version)
    catalog = merge_override(catalog, override_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sst-version", required=True)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--overrides", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    build_policy_catalog(
        sst_version=args.sst_version,
        source_root=args.source_root,
        out_path=args.out,
        overrides=args.overrides,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
