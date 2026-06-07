# Developer setup

This page describes a source checkout suitable for development and testing.

## Prerequisites

- Git
- Python 3.10 or newer
- A working compiler toolchain for packages that build native extensions
- PySide6-compatible Qt platform libraries
- Optional: Doxygen and Graphviz for generated API documentation
- Optional: SST and/or gem5 for live integration testing

## Setup

```bash
git clone https://github.com/PKBLabs/fuse.git
cd fuse
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
git clone https://github.com/PKBLabs/fuse.git
cd fuse
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Run the application

```bash
python -m fuse.app.main
```

## Run tests

```bash
python -m pytest -q -m "not sst_live and not gem5_live"
```

Live simulator tests require the corresponding simulator/toolchain to be installed and configured.

## Build documentation checks locally

```bash
python docs/scripts/check_internal_links.py
doxygen Doxyfile
```

## Packaging smoke test

```bash
python -m pip install pyinstaller
pyinstaller --clean --noconfirm packaging/pyinstaller/fuse.spec
```

The packaged app appears under `dist/FUSE/`.
