# FUSE gem5 Plugin

This plugin provides gem5 component catalog, validation, and export support for
FUSE projects.

## Catalog sources

The plugin has two catalog sources:

1. **Built-in fallback catalog**: a small curated catalog of common gem5
   SimObjects such as `System`, CPU models, `SystemXBar`, and DRAM models. This
   keeps FUSE usable when no live gem5 installation has been imported.
2. **Live gem5 import**: when a project has a local gem5 binary configured in
   the plugin toolchain settings, `Gem5Plugin.import_metadata_for_toolchain()`
   runs a gem5 Python probe against that binary, imports `m5.objects`, and
   stores discovered SimObject metadata in the FUSE database.

Imported live catalogs are preferred for the imported target. If no imported
metadata exists for a selected target, the plugin falls back to the built-in
catalog.

## Live metadata import

The live metadata importer runs the configured gem5 binary twice:

- once with `--version`, to identify the installed version
- once with a temporary FUSE probe script, to inspect `m5.objects`

The probe stores discovered SimObject type names, inferred categories, ports,
and parameters. Ports are mapped to FUSE connector interfaces such as
`request_port`, `response_port`, or `gem5_port` where possible.

The current live importer supports **local** gem5 toolchains. SSH/remote import
is intentionally rejected until FUSE has a safe way to stage and execute probe
scripts on remote toolchain hosts.

## Testing

Local/unit tests use mocked gem5 metadata and do not require a gem5 install.
Live tests marked `gem5_live` exercise a real gem5 binary and verify that the
probe and catalog import path work against an installed gem5 environment.

Example live test command:

```bash
QT_QPA_PLATFORM=offscreen GEM5_BINARY=/path/to/gem5.opt pytest -q -m gem5_live
```
