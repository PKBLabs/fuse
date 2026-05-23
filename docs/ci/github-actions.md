# GitHub Actions CI/CD

FUSE should use separate CI workflows for fast dependency-light tests and plugin live-integration tests.

## Recommended workflows

```text
.github/workflows/core-tests.yml
.github/workflows/sst-integration.yml
.github/workflows/gem5-integration.yml
.github/workflows/build-sst-ci-image.yml
.github/workflows/build-gem5-ci-image.yml
```

## Core Tests

Runs on every push and pull request.

Command:

```bash
python -m pytest -q -m "not sst_live and not gem5_live"
```

This workflow should not require real SST or gem5 installations.

## SST Integration Tests

Runs tests marked `sst_live`.

Requirements:

- Docker image with SST Core and SST Elements installed.
- `sst-info` on `PATH`.

Command:

```bash
python -m pytest -q -m "sst_live"
```

## gem5 Integration Tests

Runs tests marked `gem5_live`.

Requirements:

- Docker image or self-hosted runner with gem5 installed.
- `GEM5_BINARY` pointing to the binary.

Command:

```bash
python -m pytest -q -m "gem5_live"
```

## Why separate workflows?

External simulation tools are heavy dependencies. Fast tests should be available to all contributors without installing SST or gem5. Live plugin integration should run in containers or self-hosted environments.

## Environment variables

Typical CI values:

```yaml
env:
  QT_QPA_PLATFORM: offscreen
  FUSE_SPLASH_MS: "0"
  FUSE_TEST_AUTOCLOSE_MS: "100"
```

## Core workflow example

```yaml
name: Core Tests

on:
  push:
  pull_request:

jobs:
  core-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
          cache: "pip"
      - run: |
          sudo apt-get update
          sudo apt-get install -y libegl1 libgl1 libxkbcommon-x11-0 xvfb
      - run: |
          python -m pip install --upgrade pip
          python -m pip install -r requirements-dev.txt
      - run: python -m pytest -q -m "not sst_live and not gem5_live"
```
