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


## Packaging and launch troubleshooting

### PySide6 is not installed

Symptom: running from source fails with `ModuleNotFoundError: No module named 'PySide6'`.

Fix:

```bash
python -m pip install -e ".[dev]"
```

### Qt platform plugin error

Symptom: launch fails with an error about the Qt platform plugin, often `xcb` on Linux.

Fix: install the missing system Qt/X11/OpenGL libraries for your distribution, then retry from the same virtual environment.

### SST or gem5 toolchain not found

Symptom: validation, import, or export workflows cannot find `sst-info`, `sst`, or gem5.

Fix: confirm the simulator is installed and available on `PATH`, or configure the appropriate local/remote toolchain path in FUSE.

### Packaged app will not launch

Symptom: a release artifact exits immediately or opens a blank window.

Fix: try launching from a terminal so startup logs remain visible. If filing a bug, include the artifact name, platform, terminal output, and whether source installation works on the same machine.
