# gem5 Plugin

The gem5 plugin is included in the community plugin tree as a placeholder for gem5 model-building support.

Plugin path:

```text
fuse/plugins/community/gem5/
```

## Current status

The current gem5 plugin can be discovered by the FUSE plugin runtime and initialized, but it does not yet provide a complete gem5 component catalog.

## Manifest

```text
fuse/plugins/community/gem5/plugin.toml
```

Example entry point:

```toml
[entry_points]
register = "fuse.plugins.community.gem5.plugin:register_plugin"
```

## Intended future responsibilities

The gem5 plugin is expected to provide:

- gem5 component discovery.
- gem5 parameter/property metadata.
- gem5 model construction assistance.
- gem5 configuration generation/export.
- gem5 live integration tests.

## Live tests

Tests requiring a real gem5 binary should be marked:

```python
@pytest.mark.gem5_live
```

The CI workflow for these tests should use a gem5-capable Docker image or a self-hosted runner.
