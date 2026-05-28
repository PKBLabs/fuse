# gem5 CI Container

Live gem5 tests require a real gem5 binary. FUSE uses reusable Docker images with gem5 built for the target ISA.

## Image contents

The gem5 CI image should include:

- Ubuntu 24.04.
- Python 3.12 and runtime Python libraries.
- Qt runtime libraries for PySide6 tests.
- gem5 build/runtime dependencies.
- A built gem5 binary such as `/opt/gem5/build/X86/gem5.opt`.
- Runtime libraries validated by `ldd` during image build.

## Dockerfile path

```text
docker/gem5-ci/Dockerfile
```

The Dockerfile uses a multi-stage build:

```text
builder stage: build dependencies, source checkout, SCons build
runtime stage: built /opt/gem5 tree plus runtime libraries
```

The runtime stage checks the gem5 binary with `ldd` and `--help`. Some gem5 versions do not support `--version`, so CI should not use `gem5.opt --version` as a health check.

## Environment variables

```text
GEM5_ROOT=/opt/gem5
GEM5_BINARY=/opt/gem5/build/X86/gem5.opt
```

## Build gem5 25 locally

```bash
docker build \
  --build-arg GEM5_REF=v25.1.0.1 \
  --build-arg GEM5_BUILD_ISA=X86 \
  --build-arg GEM5_BUILD_JOBS=2 \
  -f docker/gem5-ci/Dockerfile \
  -t ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1-local \
  .
```

## Build gem5 24 locally

```bash
docker build \
  --build-arg GEM5_REF=v24.1.0.3 \
  --build-arg GEM5_BUILD_ISA=X86 \
  --build-arg GEM5_BUILD_JOBS=2 \
  -f docker/gem5-ci/Dockerfile \
  -t ghcr.io/pkblabs/fuse-gem5-ci:gem5-v24.1.0.3-local \
  .
```

## Smoke-test a gem5 image

```bash
docker run --rm \
  ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1-local \
  bash -lc '
    echo "$GEM5_ROOT"
    echo "$GEM5_BINARY"
    test -x "$GEM5_BINARY"
    ldd "$GEM5_BINARY" | grep "not found" && exit 1 || true
    "$GEM5_BINARY" --help | head -40
  '
```

## Run live gem5 tests locally

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  -w /workspace/fuse \
  -e QT_QPA_PLATFORM=offscreen \
  -e FUSE_SPLASH_MS=0 \
  -e FUSE_TEST_AUTOCLOSE_MS=100 \
  -e FUSE_GEM5_VERSION=25.1.0.1 \
  -e GEM5_ROOT=/opt/gem5 \
  -e GEM5_BINARY=/opt/gem5/build/X86/gem5.opt \
  ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1-local \
  bash -lc '
    python3 -m venv .venv
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements-dev.txt
    .venv/bin/python -m pytest -q -m "gem5_live"
  '
```

## Push validated images

After local smoke tests and live integration tests pass:

```bash
docker tag \
  ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1-local \
  ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1

docker push ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1
```

Repeat for gem5 24.

## GitHub build workflow

The manual build workflow is:

```text
.github/workflows/build-gem5-ci-image.yml
```

Inputs:

```text
image_tag       gem5-v25.1.0.1 or gem5-v24.1.0.3
gem5_ref        v25.1.0.1 or v24.1.0.3
gem5_build_isa  X86
make_jobs       usually 2
```

## When to rebuild

Rebuild the gem5 image when:

- gem5 version/ref changes.
- Dockerfile changes.
- Runtime dependency list changes.
- Base image needs a security refresh.
- The build ISA changes.
