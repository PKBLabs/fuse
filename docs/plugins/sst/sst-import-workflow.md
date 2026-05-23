# SST Import Workflow

The SST import workflow converts `sst-info` output into FUSE plugin catalog data.

## Live import

Run setup with SST installed:

```bash
./scripts/setup_dev.sh
```

Force refresh:

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

## Import from file

The SST importer can read previously captured `sst-info` output.

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.plugins.community.sst.get_sstinfo --from-file latest_sst_info_stdout.txt
```

## Import steps

1. Initialize core database.
2. Initialize SST schema.
3. Run `sst-info` or read file.
4. Store raw run in `sst_info_runs` for live command runs.
5. Parse output.
6. Upsert elements into `sst_elements`.
7. Upsert components/subcomponents into `sst_components`.
8. Replace child parameters, ports, subcomponent slots, and statistics.
9. Backfill icons for rows without an icon.

## Idempotency

Repeated imports should not duplicate elements or components. Existing component rows are updated, and children are replaced with the latest parsed data.

## Manual icon choices

`backfill_component_icons()` only fills empty `icon_path` values. It does not overwrite existing icon paths. This preserves manual user choices.

## Debugging

Inspect imported data:

```bash
sqlite3 app_data/app.db "SELECT COUNT(*) FROM sst_elements;"
sqlite3 app_data/app.db "SELECT COUNT(*) FROM sst_components;"
sqlite3 app_data/app.db "SELECT id, command, return_code, created_at FROM sst_info_runs ORDER BY id DESC LIMIT 5;"
```
