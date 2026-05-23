# SST CI Container

Live SST tests require a real SST environment. The recommended approach is to build a reusable Docker image with SST Core and SST Elements installed.

## Build once, run many times

Do not build SST on every CI run. Instead:

1. Build the SST CI image manually or on Dockerfile changes.
2. Push it to GitHub Container Registry.
3. Pull it in the SST integration workflow.

## Image contents

The SST CI image should include:

- Ubuntu 24.04.
- Python 3.12.
- Qt runtime libraries for PySide6 tests.
- SST Core.
- SST Elements.
- `sst-info` on `PATH`.

## Example Dockerfile path

```text
docker/sst-ci/Dockerfile
```

## Build locally

```bash
docker build \
  --build-arg SST_VERSION=15.0.0 \
  -f docker/sst-ci/Dockerfile \
  -t fuse-sst-ci:local \
  .
```

## Run live tests locally in the container

```bash
docker run --rm -it \
  -v "$PWD:/workspace" \
  -w /workspace \
  -e QT_QPA_PLATFORM=offscreen \
  -e FUSE_SPLASH_MS=0 \
  -e FUSE_TEST_AUTOCLOSE_MS=100 \
  fuse-sst-ci:local \
  bash -lc '
    python3 -m venv .venv &&
    .venv/bin/python -m pip install --upgrade pip &&
    .venv/bin/python -m pip install -r requirements-dev.txt &&
    .venv/bin/python -m pytest -q -m "sst_live"
  '
```

## When to rebuild

Rebuild the SST image when:

- SST version changes.
- Dockerfile changes.
- Ubuntu base image changes.
- Build dependencies change.
- You need security refreshes.
