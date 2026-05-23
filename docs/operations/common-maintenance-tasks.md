# Common Maintenance Tasks

## Refresh SST metadata

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

## Reset the local database

```bash
rm -f app_data/app.db
./scripts/setup_dev.sh
```

## Add a new component icon

1. Add PNG to `fuse/core/resources/media/arch_component_icons/`.
2. Update plugin icon mapping if needed.
3. Add/adjust icon resolver tests.

## Add a new plugin

1. Create `fuse/plugins/community/<plugin_id>/`.
2. Add `plugin.toml`.
3. Add `plugin.py` with `register_plugin()`.
4. Add tests under plugin-local `tests/`.
5. Update documentation.

## Add a new required model validation rule

1. Update `fuse/core/model/validation.py`.
2. Add tests in `fuse/tests/test_validation.py`.
3. Update `docs/user/properties-and-validation.md`.

## Add a new live integration dependency

1. Add pytest marker.
2. Add plugin-local live tests.
3. Add Dockerfile or self-hosted runner documentation.
4. Add GitHub Actions workflow.
