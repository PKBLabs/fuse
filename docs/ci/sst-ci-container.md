# SST CI Container

Live SST tests require a real SST environment. FUSE uses reusable Docker images with SST Core and SST Elements installed.

## Build once, run many times

Do not build SST on every CI run. Instead:

1. Build the SST CI image manually, locally, or on a dedicated image-build workflow.
2. Push it to GitHub Container Registry.
3. Pull it in the SST integration workflow.

## Image contents

The SST CI image should include:

- Ubuntu 24.04.
- Python 3.12 and runtime Python libraries.
- Qt runtime libraries for PySide6 tests.
- SST Core.
- SST Elements.
- `sst` on `PATH`.
- `sst-info` on `PATH`.
- Runtime libraries validated by `ldd` during image build.

## Dockerfile path

```text
docker/sst-ci/Dockerfile
```

The Dockerfile uses a multi-stage build:

```text
builder stage: compilers, headers, source trees, build artifacts
runtime stage: installed /opt/sst plus runtime libraries only
```

The runtime stage includes an `ldd` validation block that fails the image build if any installed SST executable or shared object has a missing runtime dependency.

## Build SST 15 locally

From the repository root:

```bash
docker build \
  --build-arg SST_VERSION=15.1.2 \
  --build-arg SST_CORE_REF=v15.1.2_Final \
  --build-arg SST_ELEMENTS_REF=v15.1.0_Final \
  --build-arg MAKE_JOBS=2 \
  -f docker/sst-ci/Dockerfile \
  -t ghcr.io/pkblabs/fuse-sst-ci:sst-15.1.2-local \
  .
```

## Build SST 16 locally

```bash
docker build \
  --build-arg SST_VERSION=16.0.0 \
  --build-arg SST_CORE_REF=v16.0.0_Final \
  --build-arg SST_ELEMENTS_REF=v16.0.0_Final \
  --build-arg MAKE_JOBS=2 \
  -f docker/sst-ci/Dockerfile \
  -t ghcr.io/pkblabs/fuse-sst-ci:sst-16.0.0-local \
  .
```

## Smoke-test an SST image

```bash
docker run --rm \
  ghcr.io/pkblabs/fuse-sst-ci:sst-15.1.2-local \
  bash -lc '
    which sst
    which sst-info
    ldd /opt/sst/bin/sst | grep "not found" && exit 1 || true
    ldd /opt/sst/bin/sst-info | grep "not found" && exit 1 || true
    sst --version || true
    sst-info --version || true
    sst-info | head -100
  '
```

## Run live tests locally in the container

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace/fuse \
  -e QT_QPA_PLATFORM=offscreen \
  -e FUSE_SPLASH_MS=0 \
  -e FUSE_TEST_AUTOCLOSE_MS=100 \
  -e FUSE_SST_VERSION=15.1.2 \
  ghcr.io/pkblabs/fuse-sst-ci:sst-15.1.2-local \
  bash -lc '
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements-dev.txt
    .venv/bin/python -m pytest -q -m "sst_live"
  '
```

## Push validated images

After local smoke tests and live integration tests pass:

```bash
docker tag \
  ghcr.io/pkblabs/fuse-sst-ci:sst-15.1.2-local \
  ghcr.io/pkblabs/fuse-sst-ci:sst-15.1.2

docker push ghcr.io/pkblabs/fuse-sst-ci:sst-15.1.2
```

Repeat for SST 16.

## GitHub build workflow

The manual build workflow is:

```text
.github/workflows/build-sst-ci-image.yml
```

Inputs:

```text
image_tag          sst-15.1.2 or sst-16.0.0
sst_version        15.1.2 or 16.0.0
sst_core_ref       v15.1.2_Final or v16.0.0_Final
sst_elements_ref   v15.1.0_Final or v16.0.0_Final
make_jobs          usually 2
```

GitHub-hosted runners can run out of disk during SST builds. Prefer local builds or a self-hosted runner when debugging Dockerfile changes.

## When to rebuild

Rebuild the SST image when:

- SST version changes.
- Dockerfile changes.
- Runtime dependency list changes.
- Ubuntu base image changes.
- Build dependencies change.
- Security refreshes are needed.
