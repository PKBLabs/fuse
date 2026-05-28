# Command Reference

## Setup

```bash
chmod +x scripts/setup_dev.sh
./scripts/setup_dev.sh
```

## Run application

```bash
fuse-mod
```

Run directly:

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.app.main
```

## Reset database

```bash
rm -f app_data/app.db
./scripts/setup_dev.sh
```

## Force SST import refresh

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

Import/refresh a specific SST version label from the active SST environment:

```bash
FUSE_SST_VERSION=15.1.2 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
FUSE_SST_VERSION=16.0.0 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

## Run tests

All tests:

```bash
.venv/bin/python -m pytest -q
```

Fast tests:

```bash
.venv/bin/python -m pytest -q -m "not sst_live and not gem5_live"
```

SST live tests:

```bash
.venv/bin/python -m pytest -q -m "sst_live"
```

gem5 live tests:

```bash
.venv/bin/python -m pytest -q -m "gem5_live"
```

## Inspect database

```bash
sqlite3 app_data/app.db ".tables"
sqlite3 app_data/app.db "SELECT id, name, version, enabled FROM core_plugins;"
sqlite3 app_data/app.db "SELECT COUNT(*) FROM sst_components;"
```

## Run SST import from file

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.plugins.community.sst.get_sstinfo --from-file latest_sst_info_stdout.txt
```

## Audit SST icon mapping

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.plugins.community.sst.audit_sst_icon_mapping --help
```

## Build simulator CI images locally

SST 15 example:

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

gem5 25 example:

```bash
docker build \
  --build-arg GEM5_REF=v25.1.0.1 \
  --build-arg GEM5_BUILD_ISA=X86 \
  --build-arg GEM5_BUILD_JOBS=2 \
  -f docker/gem5-ci/Dockerfile \
  -t ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1-local \
  .
```
