# FUSE Plugin Manifest

Every FUSE plugin must include a `plugin.toml` file at the root of the plugin
directory or package.

The manifest declares plugin identity, version, license, compatibility, entry
points, and capabilities.

FUSE may refuse to load plugins with missing, invalid, or incompatible manifests.