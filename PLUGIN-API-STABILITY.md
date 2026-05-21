# FUSE Plugin API Stability Policy

The FUSE Plugin API is a public, versioned compatibility surface used by
community plugins, PKB Research Labs community plugins, and PKB Research Labs
commercial plugins.

The public plugin API consists only of modules, classes, functions, schemas, and
interfaces documented under `fuse.plugin_api` and in the official plugin API
documentation.

All other modules are internal implementation details unless explicitly marked
as public API.

## Versioning

The FUSE Plugin API uses semantic versioning.

Given a plugin API version `MAJOR.MINOR.PATCH`:

- PATCH releases include bug fixes and documentation clarifications.
- MINOR releases may add backward-compatible APIs.
- MAJOR releases may introduce breaking changes.

FUSE will not intentionally break compatibility with plugins targeting the same
major plugin API version.

## Compatibility

Plugins must declare the plugin API versions they support.

FUSE may refuse to load plugins that do not declare compatibility or that declare
an incompatible API range.

## Deprecation

Public plugin APIs should be deprecated before removal whenever practical.

Deprecated APIs should remain available until the next major plugin API version
unless there is a security, correctness, or legal reason to remove them sooner.

## Internal APIs

Plugins should not import or rely on FUSE internal modules. Internal APIs may
change at any time without notice.

Modules or names containing `_internal`, `_private`, or not documented as part
of `fuse.plugin_api` are not stable public APIs.

## Commercial plugin compatibility

PKB Research Labs, LLC may distribute commercial plugins that depend on the
public FUSE Plugin API.

The FUSE Community Edition and commercial plugins are expected to remain
compatible within the declared plugin API version ranges.