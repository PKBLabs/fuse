#!/usr/bin/env python3
"""Check internal Markdown links in docs and top-level Markdown files."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")


def iter_markdown_files() -> list[Path]:
    files = list(DOCS.rglob("*.md"))
    for name in ("README.md", "CONTRIBUTING.md", "CLA.md"):
        path = ROOT / name
        if path.exists():
            files.append(path)
    return sorted(files)


def strip_anchor(target: str) -> str:
    return target.split("#", 1)[0]


def main() -> int:
    errors: list[str] = []
    files = iter_markdown_files()

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in LINK_RE.finditer(text):
            raw = match.group(1).strip()
            if not raw or raw.startswith(SKIP_PREFIXES):
                continue
            parsed = urlparse(raw)
            if parsed.scheme:
                continue

            target = strip_anchor(unquote(parsed.path))
            if not target:
                continue

            candidate = (path.parent / target).resolve()
            try:
                candidate.relative_to(ROOT)
            except ValueError:
                errors.append(f"{path.relative_to(ROOT)}: link escapes repo: {raw}")
                continue

            if not candidate.exists():
                errors.append(f"{path.relative_to(ROOT)}: missing link target: {raw}")

    if errors:
        print("Internal Markdown link check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print(f"Checked {len(files)} Markdown files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
