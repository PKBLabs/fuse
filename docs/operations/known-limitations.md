# Known Limitations

FUSE is in early active development. The following limitations are expected.

## UI and model editor

- Undo/redo is available for the current editing session, but long-term history persistence across application restarts is not implemented.
- Routing is designed for responsiveness, not full schematic-quality autorouting.
- Point-to-point links currently allow one connection per port.
- Multi-endpoint/bus links are planned but not complete.
- Large graph layout and automatic placement are not yet complete.

## Project files

- `.fse` schema version is early and may change.
- Backward compatibility may require migration logic as the schema evolves.

## Plugin system

- Plugin API is still stabilizing.
- Some manifest capability fields may be descriptive rather than fully enforced.
- gem5 support may be placeholder-level.

## SST plugin

- Requires `sst-info` for live metadata import.
- If SST is missing, the plugin initializes but skips metadata import.
- SST model export is expected to evolve separately from metadata import.

## CI

- Fast tests do not require real SST or gem5.
- Live SST/gem5 tests require dedicated containers or self-hosted runners.
