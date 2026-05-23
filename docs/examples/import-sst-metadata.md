# Example: Import SST Metadata

This example populates the SST plugin catalog using `sst-info`.

## Prerequisites

Verify `sst-info` is available:

```bash
which sst-info
sst-info --version
```

## Run setup

```bash
./scripts/setup_dev.sh
```

If a successful import already exists, the plugin may skip refresh.

Force refresh:

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

## Check imported tables

```bash
sqlite3 app_data/app.db ".tables"
```

Expected SST tables:

```text
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

## Import from captured file

If you have a saved `sst-info` output file:

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.plugins.community.sst.get_sstinfo --from-file latest_sst_info_stdout.txt
```

## Launch FUSE

```bash
fuse-mod
```

The component palette should contain SST-provided items.
