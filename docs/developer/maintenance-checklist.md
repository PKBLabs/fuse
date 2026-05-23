# Maintenance Checklist

## Before merging major UI changes

- Run core tests.
- Manually launch the app.
- Verify drag/drop from component palette.
- Verify component selection updates properties panel.
- Verify link creation and link selection.
- Verify save/load round trip.

## Before merging plugin changes

- Run dependency-light tests.
- Run plugin-local tests.
- If external tools are needed, run live plugin tests.
- Check plugin manifest entry points.
- Check plugin database schema changes.

## Before changing project file format

- Update `SCHEMA_VERSION` if needed.
- Update `project_io.py`.
- Add compatibility tests.
- Document migration behavior.

## Before changing database schema

- Add/adjust initialization code.
- Add/adjust tests.
- Update database table reference docs.
- Decide whether existing developer DBs must be reset.

## Before changing plugin API

- Update `plugin_api/interfaces.py`.
- Update plugin API docs.
- Update plugin manifests if compatibility ranges change.
- Update `PLUGIN-API-STABILITY.md`.

## Cleanup items to avoid committing

Do not commit:

- `.venv/`
- `__pycache__/`
- `.pytest_cache/`
- `app_data/app.db`
- IDE workspace files unless intentionally shared
