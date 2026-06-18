# Generated Documentation

FUSE uses two documentation systems with different purposes.

## MkDocs

MkDocs is the primary user-facing and developer-facing documentation site. It contains installation guides, tutorials, screenshots, workflow documentation, architecture notes, maintainer processes, and release documentation.

Build it locally with:

```bash
python -m pip install -r docs/requirements.txt
mkdocs build
```

Run a local preview server with:

```bash
mkdocs serve
```

## Doxygen

Doxygen generates API/class/function reference documentation from Python docstrings and source structure.

Build it locally with:

```bash
doxygen Doxyfile
```

Generated HTML output is written to:

```text
docs/generated/html/
```

The MkDocs site links to the generated Doxygen index at:

[Generated API Reference](../generated/html/index.html)

## Recommended release build order

For CI and release builds, use this order:

```bash
python docs/scripts/check_internal_links.py
doxygen Doxyfile
mkdocs build --strict
```

This ensures that generated API files exist before MkDocs validates links to them.
