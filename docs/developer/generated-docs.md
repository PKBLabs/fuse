# Generated API documentation

FUSE uses Doxygen and Graphviz to produce generated API documentation and diagrams.

## Build locally

```bash
doxygen Doxyfile
```

Generated HTML output is written to:

```text
docs/generated/html/
```

## CI

The documentation workflow builds Doxygen output and uploads the generated HTML as a workflow artifact.

## Scope

The Doxygen configuration covers:

- `fuse/app`
- `fuse/core`
- `fuse/plugin_api`
- `fuse/plugins/community/sst`
- `fuse/plugins/community/gem5`

The intent is to document architecture and important interfaces, not every private helper before v1.0.
