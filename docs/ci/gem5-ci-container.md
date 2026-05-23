# gem5 CI Container

Live gem5 tests require a real gem5 binary. The recommended approach is a reusable Docker image.

## Image contents

The gem5 CI image should include:

- Ubuntu 24.04.
- Python 3.12.
- Qt runtime libraries.
- gem5 build dependencies.
- A built gem5 binary such as `/opt/gem5/build/X86/gem5.opt`.

## Environment variables

```text
GEM5_ROOT=/opt/gem5
GEM5_BINARY=/opt/gem5/build/X86/gem5.opt
```

## Run live gem5 tests

```bash
.venv/bin/python -m pytest -q -m "gem5_live"
```

## When to rebuild

Rebuild the gem5 image when:

- gem5 version/ref changes.
- Dockerfile changes.
- Dependencies change.
- The base image needs security refresh.
