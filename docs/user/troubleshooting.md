# Troubleshooting

## `fuse-mod` command not found

Add `~/.local/bin` to `PATH`:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Then run:

```bash
fuse-mod
```

## The component palette is empty

Common causes:

1. The database has not been initialized.
2. No plugin has populated component metadata.
3. `sst-info` is not installed or not on `PATH`.

Try:

```bash
./scripts/setup_dev.sh
```

Force SST import:

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

Inspect the database:

```bash
sqlite3 app_data/app.db ".tables"
sqlite3 app_data/app.db "SELECT COUNT(*) FROM sst_components;"
```

## `sst-info` not found

Install SST Core and SST Elements and ensure `sst-info` is on `PATH`:

```bash
which sst-info
sst-info --version
```

If missing, FUSE can still run, but SST component import will be skipped.

## Qt/PySide6 platform plugin errors

On Linux or WSL, install common Qt runtime dependencies:

```bash
sudo apt-get update
sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 xvfb
```

For headless tests:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

or:

```bash
xvfb-run -a .venv/bin/python -m pytest -q
```

## Save fails because required parameters are missing

Select the marked component and fill required fields in the properties panel. Required parameters are marked with `*`.

## A saved project does not load

Check:

- The file is valid JSON.
- `schemaVersion` is supported.
- `components` is a list.
- `links` is a list.
- The plugin providing a saved component is installed and discoverable.

## Links route strangely

The current routing system uses orthogonal routes and padded component obstacles. Routing is optimized for interactive responsiveness rather than full global graph layout.

Use:

```text
Tools -> Reroute All Links
```

if available.

## Reset everything

```bash
rm -rf .venv
rm -f app_data/app.db
./scripts/setup_dev.sh
```
