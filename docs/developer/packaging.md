# Packaging

FUSE uses PyInstaller as the first packaging path for v0.9.x release preparation.

## Target platforms

Tier 1 for v0.9.x:

- Linux x86_64
- Windows x86_64

Tier 2 / experimental:

- macOS arm64
- macOS x86_64

Source installation remains supported on platforms with compatible Python and PySide6 support.

## Local build

```bash
python -m pip install -e ".[dev]"
python -m pip install pyinstaller
pyinstaller --clean --noconfirm packaging/pyinstaller/fuse.spec
```

Output:

```text
dist/FUSE/
```

## Release artifacts

The release workflow should produce:

- source `.tar.gz`
- source `.zip`
- packaged app artifacts
- checksum file

Native installers such as `.dmg`, `.msi`, or AppImage may be added after the basic PyInstaller artifacts are stable.
