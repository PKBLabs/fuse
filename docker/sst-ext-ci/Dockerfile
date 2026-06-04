ARG BASE_IMAGE=ghcr.io/pkblabs/fuse-sst-ci:sst-16.0.0
FROM ${BASE_IMAGE}

ARG DEBIAN_FRONTEND=noninteractive
ARG SST_EXT_TESTS_REPO=https://github.com/tactcomplabs/sst-ext-tests.git
ARG SST_EXT_TESTS_REF=main
ARG SST_EXT_TESTS_ROOT=/opt/sst-ext-tests

ENV SST_EXT_TESTS_ROOT=${SST_EXT_TESTS_ROOT}

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    cmake \
    git \
    make \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    git clone --depth 1 --branch "${SST_EXT_TESTS_REF}" "${SST_EXT_TESTS_REPO}" "${SST_EXT_TESTS_ROOT}"; \
    cmake --version; \
    test -f "${SST_EXT_TESTS_ROOT}/CMakeLists.txt"; \
    test -d "${SST_EXT_TESTS_ROOT}/tests" || test -d "${SST_EXT_TESTS_ROOT}/src" || true; \
    git -C "${SST_EXT_TESTS_ROOT}" rev-parse HEAD > /opt/sst-ext-tests-revision.txt; \
    find "${SST_EXT_TESTS_ROOT}" -name ".git" -type d -prune -exec rm -rf {} +; \
    find "${SST_EXT_TESTS_ROOT}" -name "__pycache__" -type d -prune -exec rm -rf {} +; \
    find "${SST_EXT_TESTS_ROOT}" -name "*.pyc" -type f -delete; \
    du -sh "${SST_EXT_TESTS_ROOT}"

RUN set -eux; \
    which sst; \
    which sst-info; \
    sst --version || true; \
    sst-info --version || true; \
    test -d "${SST_EXT_TESTS_ROOT}"; \
    test -f /opt/sst-ext-tests-revision.txt; \
    cat /opt/sst-ext-tests-revision.txt

WORKDIR /workspace
