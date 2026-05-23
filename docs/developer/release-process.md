# Release Process

This is a suggested release process for the current development state.

## Pre-release checklist

1. Confirm version in `fuse/core/app_info.py`.
2. Confirm `README.md` is current.
3. Run the full dependency-light test suite:

```bash
.venv/bin/python -m pytest -q -m "not sst_live and not gem5_live"
```

4. Run live plugin tests where available:

```bash
.venv/bin/python -m pytest -q -m "sst_live"
.venv/bin/python -m pytest -q -m "gem5_live"
```

5. Verify application launch:

```bash
fuse-mod
```

6. Verify new project save/load.
7. Verify About dialog version and license text.
8. Verify plugin manifests.
9. Review licensing files.

## Tagging

Suggested tag format:

```text
v0.1.0
```

## Release notes

Include:

- New features.
- Breaking changes.
- Plugin API changes.
- Database schema changes.
- Known issues.
- Upgrade notes.

## Plugin compatibility

If the plugin API changes, update:

- `PLUGIN-API-STABILITY.md`
- `plugin_api/version.py`
- Plugin manifests under `plugins/community/*/plugin.toml`

## Database compatibility

If plugin-specific database schemas change, document whether users need to reset `app_data/app.db`.
