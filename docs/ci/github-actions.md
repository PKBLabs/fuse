# GitHub Actions CI/CD

FUSE uses separate workflows for fast dependency-light tests, simulator live-integration tests, and reusable simulator container image builds.

## Workflows

```text
.github/workflows/core-tests.yml
.github/workflows/cla-check.yml
.github/workflows/sst-integration.yml
.github/workflows/gem5-integration.yml
.github/workflows/build-sst-ci-image.yml
.github/workflows/build-gem5-ci-image.yml
```

## Pull request policy

Pull requests should run:

```text
CLA Check
Core Tests
```

Pull requests should **not** run SST/gem5 live integration by default because those tests require large prebuilt simulator images.

## Push policy

Pushes to `main` or `develop` should run:

```text
Core Tests
```

SST/gem5 integration tests run on pushes to `main` or `develop` only when relevant plugin, workflow, Dockerfile, requirements, or plugin API paths change.

## Manual/scheduled policy

SST and gem5 integration workflows also run:

```text
workflow_dispatch
weekly schedule
```

Manual runs are useful before releases and after rebuilding simulator CI images.

## Core Tests

Runs dependency-light tests:

```bash
python -m pytest -q -m "not sst_live and not gem5_live"
```

This workflow should not require real SST or gem5 installations.

Recommended trigger:

```yaml
on:
  pull_request:
  push:
    branches:
      - main
      - develop
```

## CLA Check

Runs on pull requests and checks that required contribution/CLA acknowledgement boxes were checked in the PR body.

This is a lightweight acknowledgement workflow. A formal CLA process may be added later.

## SST Integration Tests

Runs tests marked `sst_live` in a prebuilt SST container image.

Requirements:

- GHCR image with SST Core and SST Elements installed.
- `sst` and `sst-info` on `PATH`.
- Runtime libraries validated by Dockerfile `ldd` checks.

Command:

```bash
.venv/bin/python -m pytest -q -m "sst_live"
```

The SST workflow currently tests matrix images such as:

```text
ghcr.io/pkblabs/fuse-sst-ci:sst-15.1.2
ghcr.io/pkblabs/fuse-sst-ci:sst-16.0.0
```

## gem5 Integration Tests

Runs tests marked `gem5_live` in a prebuilt gem5 container image.

Requirements:

- GHCR image with gem5 built.
- `GEM5_ROOT=/opt/gem5`.
- `GEM5_BINARY=/opt/gem5/build/X86/gem5.opt`.
- Runtime libraries validated by Dockerfile `ldd` checks.

Command:

```bash
.venv/bin/python -m pytest -q -m "gem5_live"
```

The gem5 workflow currently tests matrix images such as:

```text
ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1
ghcr.io/pkblabs/fuse-gem5-ci:gem5-v24.1.0.3
```

## Build image workflows

The simulator image build workflows are manual-only:

```text
build-sst-ci-image.yml
build-gem5-ci-image.yml
```

They should not run on every PR or ordinary push.

Use them when:

- Simulator version/ref changes.
- Dockerfile changes.
- Runtime dependency list changes.
- Base image needs a security refresh.

## Why separate workflows?

External simulation tools are heavy dependencies. Fast tests should be available to all contributors without installing SST or gem5. Live plugin integration should run in prebuilt containers or self-hosted environments.

## Environment variables

Typical CI values:

```yaml
env:
  QT_QPA_PLATFORM: offscreen
  FUSE_SPLASH_MS: "0"
  FUSE_TEST_AUTOCLOSE_MS: "100"
```

SST integration additionally sets:

```yaml
env:
  FUSE_SST_VERSION: "15.1.2"
```

gem5 integration additionally sets:

```yaml
env:
  FUSE_GEM5_VERSION: "25.1.0.1"
  GEM5_ROOT: /opt/gem5
  GEM5_BINARY: /opt/gem5/build/X86/gem5.opt
```

## Local validation before GitHub Actions

To avoid burning GitHub Actions time on long simulator builds, test Docker images locally first:

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

Then run the integration test inside the image:

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

Only push CI image tags after local smoke and live tests pass.

## README badges

Use branch-specific badges for core tests and event-specific badges for manual simulator validation:

```markdown
[![Core Tests](https://github.com/PKBLabs/fuse/actions/workflows/core-tests.yml/badge.svg?branch=develop)](https://github.com/PKBLabs/fuse/actions/workflows/core-tests.yml)
[![SST Integration Tests](https://github.com/PKBLabs/fuse/actions/workflows/sst-integration.yml/badge.svg?branch=develop&event=workflow_dispatch)](https://github.com/PKBLabs/fuse/actions/workflows/sst-integration.yml)
[![gem5 Integration Tests](https://github.com/PKBLabs/fuse/actions/workflows/gem5-integration.yml/badge.svg?branch=develop&event=workflow_dispatch)](https://github.com/PKBLabs/fuse/actions/workflows/gem5-integration.yml)
```
