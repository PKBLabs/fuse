#!/usr/bin/env python3
"""Check repository-local Markdown links used by the documentation site."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

DOCS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DOCS_ROOT.parent

LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
HTML_LINK_RE = re.compile(r"""href=["']([^"']+)["']""")

SKIP_SCHEMES = {"http", "https", "mailto", "tel"}


def _strip_title(target: str) -> str:
    """Remove optional Markdown link title text from a target."""
    target = target.strip()
    if " " not in target:
        return target
    if target.startswith("<") and ">" in target:
        return target[1:target.index(">")]
    return target.split()[0]


def _iter_links(text: str) -> list[str]:
    """Return Markdown and simple HTML links from a Markdown document."""
    links = []
    links.extend(match.group(1) for match in LINK_RE.finditer(text))
    links.extend(match.group(1) for match in IMAGE_RE.finditer(text))
    links.extend(match.group(1) for match in HTML_LINK_RE.finditer(text))
    return links


def _anchor_exists(path: Path, anchor: str) -> bool:
    """Best-effort check that a Markdown heading anchor exists."""
    if not anchor:
        return True
    if path.suffix.lower() not in {".md", ".markdown"}:
        return True
    text = path.read_text(encoding="utf-8", errors="ignore")
    requested = anchor.lower()
    requested = requested.replace("%20", "-")
    headings = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        title = stripped.lstrip("#").strip()
        slug = re.sub(r"[^\w\s-]", "", title.lower())
        slug = re.sub(r"\s+", "-", slug).strip("-")
        headings.append(slug)
    return requested in headings


def main() -> int:
    """Run the documentation link check."""
    failures: list[str] = []
    markdown_files = sorted(DOCS_ROOT.rglob("*.md"))

    for md_file in markdown_files:
        if "generated" in md_file.parts:
            continue
        text = md_file.read_text(encoding="utf-8", errors="ignore")
        for raw_target in _iter_links(text):
            target = _strip_title(raw_target)
            if not target or target.startswith("#"):
                continue

            parsed = urlparse(target)
            if parsed.scheme in SKIP_SCHEMES:
                continue
            if parsed.scheme and parsed.scheme not in {"file"}:
                continue

            target_path = unquote(parsed.path)
            if not target_path:
                continue

            # MkDocs/Doxygen generated HTML is produced during docs builds. If it
            # already exists locally this still passes the normal file check.
            candidate = (md_file.parent / target_path).resolve()
            try:
                candidate.relative_to(REPO_ROOT)
            except ValueError:
                failures.append(f"{md_file.relative_to(REPO_ROOT)} -> {target} points outside repository")
                continue

            if not candidate.exists():
                # Doxygen HTML is generated during documentation builds and is
                # intentionally not required in a clean checkout.
                rel_candidate = candidate.relative_to(REPO_ROOT)
                if rel_candidate.parts[:3] == ("docs", "generated", "html"):
                    continue
                failures.append(f"{md_file.relative_to(REPO_ROOT)} -> {target} not found")
                continue

            if not _anchor_exists(candidate, parsed.fragment):
                failures.append(f"{md_file.relative_to(REPO_ROOT)} -> {target} anchor not found")

    if failures:
        print("Broken documentation links:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"Checked {len(markdown_files)} Markdown files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
