# Quickstart

This guide gets the FUSE Community Edition running from a fresh checkout.

## Terminology

This documentation uses these terms:

- **Repository root**: the top-level checkout directory that contains `README.md`, `docs/`, `examples/`, and the inner Python package directory.
- **FUSE package root**: the directory that contains `app/`, `core/`, `plugins/`, `scripts/`, and `requirements.txt`.

Depending on how the repository is checked out, the package root may be `fuse/` inside the repository root.

## Prerequisites

Install:

- Python 3.12 or newer.
- `python3-venv`.
- Git.
- On Linux/WSL, Qt runtime libraries required by PySide6.

For SST metadata import, install SST Core and SST Elements so that `sst-info` is on `PATH`. FUSE can still launch without `sst-info`; the SST plugin will skip live metadata import if the command is missing.

## Development setup

From the FUSE package root:

```bash
chmod +x scripts/setup_dev.sh
./scripts/setup_dev.sh
```

The setup script:

1. Creates `.venv/`.
2. Installs `requirements.txt`.
3. Initializes the FUSE SQLite database.
4. Discovers enabled plugins.
5. Allows plugins to initialize plugin-specific database tables.
6. Runs optional plugin bootstrap steps.
7. Creates a `fuse-mod` launcher in `~/.local/bin`.

If `fuse-mod` is not found after setup:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Run the application

```bash
fuse-mod
```

Or run the module directly from the parent directory of the FUSE package root:

```bash
python -m fuse.app.main
```

If you are inside the FUSE package root:

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.app.main
```


## Create your first project

After FUSE opens, use:

```text
File -> New Project
```

Then open Project Settings to choose the active plugin and target version/catalog. For example, select `SST 15.1.2` for an SST project or `gem5 25.1.0.1` for a gem5 project.

Use **Discover Local Tools** to populate local simulator paths where possible, then use **Validate Enabled Toolchains** to confirm the configured local or SSH toolchain matches the selected project target.

Drag components from the left palette into the canvas, edit required parameters in the properties panel, connect ports, and save the result as a `.fse` project file.

## Reset the development database

```bash
rm -f app_data/app.db
./scripts/setup_dev.sh
```

## Force SST metadata refresh

If a successful SST metadata import already exists, the SST plugin may skip re-running `sst-info`. Force refresh with:

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

## Run tests

```bash
.venv/bin/python -m pytest -q
```

Run fast tests only:

```bash
.venv/bin/python -m pytest -q -m "not sst_live and not gem5_live"
```
