# Developer Setup

This page describes the basic source-based setup for contributors.

## Prerequisites

Install:

- Python 3.12 or newer.
- Git.
- Qt runtime libraries required by PySide6 on your platform.
- Doxygen and Graphviz when building generated API documentation.
- MkDocs dependencies when building the documentation website.

## Create a virtual environment

From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r fuse/requirements-dev.txt
```

On Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r fuse\requirements-dev.txt
```

## Run the app

```bash
python -m fuse.app.main
```

## Run tests

```bash
python -m pytest -q
```

Some tests require simulator-specific toolchains or containers. See the [testing guide](../testing/testing-guide.md) for details.

## Build documentation

```bash
python -m pip install -r docs/requirements.txt
doxygen Doxyfile
mkdocs build
```

The generated Doxygen HTML is expected at:

```text
docs/generated/html/index.html
```

The MkDocs site is the user-facing documentation website and links to the Doxygen output as generated API reference.
