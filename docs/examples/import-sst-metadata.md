# Example: Import SST Metadata

This example populates the SST plugin catalog using `sst-info`.

SST metadata is versioned in FUSE. You can import metadata for more than one SST version and select the desired version per project in Project Settings.

## Prerequisites

Verify `sst-info` is available in the current environment:

```bash
which sst-info
sst-info --version || true
```

Some SST versions may print version information differently. The important check is that `sst-info` runs successfully.

## Import the default SST metadata

From the FUSE package root:

```bash
./scripts/setup_dev.sh
```

If a successful import already exists, the plugin may skip refresh.

Force refresh:

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

## Import a specific SST version label

Run setup/import from an environment where the desired SST installation is active.

For SST 15:

```bash
FUSE_SST_VERSION=15.1.2 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

For SST 16:

```bash
FUSE_SST_VERSION=16.0.0 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

`FUSE_SST_VERSION` labels the imported catalog. It does not install SST or switch your shell environment by itself.

## Check imported tables

```bash
sqlite3 app_data/app.db ".tables"
```

Expected SST tables:

```text
sst_framework_versions
sst_info_runs
sst_elements
sst_components
sst_parameters
sst_ports
sst_statistics
sst_subcomp_slots
```

Count imported items:

```bash
sqlite3 app_data/app.db "SELECT COUNT(*) FROM sst_elements;"
sqlite3 app_data/app.db "SELECT COUNT(*) FROM sst_components;"
```

List imported versions:

```bash
sqlite3 app_data/app.db "SELECT id, version, label, is_default FROM sst_framework_versions;"
```

## Import from captured file

If you have a saved `sst-info` output file:

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.plugins.community.sst.get_sstinfo --from-file latest_sst_info_stdout.txt
```

## Use imported metadata in a project

1. Launch FUSE.
2. Open **File -> Project Settings**.
3. Enable SST.
4. Select the imported SST target/version.
5. Make SST the active framework/plugin.
6. Apply the settings.

The component palette should show SST-provided items for the selected target.

## Validate the SST toolchain

In Project Settings, configure the execution environment:

```text
Local machine
```

or:

```text
Remote over SSH
```

Then click:

```text
Validate Enabled Toolchains
```

FUSE checks that the configured `sst-info` command is reachable and version-compatible with the selected project target.
