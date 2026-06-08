# Installation

FUSE can be installed either from a release artifact or from a source checkout.

<!-- FUSE-MEDIA-TODO id=install-release-artifact type=screenshot path=../assets/screenshots/release-artifact-download.png -->
> **Media TODO (install-release-artifact)**: Add a screenshot showing the GitHub release artifact list and which file a user should download.
> Planned asset: `../assets/screenshots/release-artifact-download.png`

## Install from a release artifact

1. Open the FUSE release page.
2. Download the artifact for your platform.
3. Verify the checksum when `SHA256SUMS.txt` is provided.
4. Unpack or install the artifact.
5. Launch `FUSE`.
6. Open an example project from `examples/`.
7. Validate the model and try an export path.

<!-- FUSE-MEDIA-TODO id=install-first-launch type=screenshot path=../assets/screenshots/first-launch-after-install.png -->
> **Media TODO (install-first-launch)**: Add a screenshot of FUSE launched from an installed/release artifact.
> Planned asset: `../assets/screenshots/first-launch-after-install.png`

For the v0.9.x preparation release, packaged artifacts are expected to mature over time. Source installation remains the most reliable fallback while packaging is hardened.

## Install from source

From the repository root:

```bash
git clone https://github.com/PKBLabs/fuse.git
cd fuse
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r fuse/requirements-dev.txt
python -m fuse.app.main
```

On Windows PowerShell:

```powershell
git clone https://github.com/PKBLabs/fuse.git
cd fuse
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r fuse\requirements-dev.txt
python -m fuse.app.main
```

## Optional simulator toolchains

FUSE can operate as a visual editor without SST or gem5 installed. SST and gem5 are only required when importing metadata from those toolchains, validating against a live toolchain, or running simulator-specific export workflows.

<!-- FUSE-MEDIA-TODO id=toolchain-config type=screenshot path=../assets/screenshots/toolchain-configuration.png -->
> **Media TODO (toolchain-config)**: Add a screenshot of the toolchain configuration area with private paths, usernames, hostnames, and tokens removed.
> Planned asset: `../assets/screenshots/toolchain-configuration.png`

## Related docs

- [Quickstart](quickstart.md)
- [Troubleshooting](troubleshooting.md)
- [Developer setup](../developer/developer-setup.md)
