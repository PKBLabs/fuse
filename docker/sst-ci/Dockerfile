FROM ubuntu:24.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
ARG SST_CORE_REF=v15.1.2_Final
ARG SST_ELEMENTS_REF=v15.1.0_Final
ARG SST_VERSION=15.1.2
ARG SST_PREFIX=/opt/sst
ARG MAKE_JOBS=2

ENV SST_CORE_HOME=${SST_PREFIX}
ENV SST_ELEMENTS_HOME=${SST_PREFIX}
ENV PATH=${SST_PREFIX}/bin:${PATH}
ENV LD_LIBRARY_PATH=${SST_PREFIX}/lib:${SST_PREFIX}/lib/sst-elements-library:${SST_PREFIX}/lib/sst-elements-library/ext:${LD_LIBRARY_PATH}
ENV PYTHONPATH=${SST_PREFIX}/lib/python3.12/site-packages:${SST_PREFIX}/lib/python3.12/dist-packages:${PYTHONPATH}
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf \
    automake \
    build-essential \
    ca-certificates \
    file \
    gfortran \
    git \
    libboost-all-dev \
    libconfig-dev \
    libffi-dev \
    libhdf5-dev \
    libltdl-dev \
    libopenmpi-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    libtool \
    libtool-bin \
    m4 \
    make \
    openmpi-bin \
    pkg-config \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    tcl-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/sst-build

RUN set -eux; \
    df -h; \
    git clone --depth 1 --branch "${SST_CORE_REF}" https://github.com/sstsimulator/sst-core.git; \
    cd sst-core; \
    ./autogen.sh; \
    ./configure --prefix="${SST_PREFIX}"; \
    make -j"${MAKE_JOBS}"; \
    make install; \
    cd /tmp/sst-build; \
    rm -rf sst-core; \
    rm -rf /root/.cache /tmp/*; \
    df -h

RUN set -eux; \
    df -h; \
    git clone --depth 1 --branch "${SST_ELEMENTS_REF}" https://github.com/sstsimulator/sst-elements.git; \
    cd sst-elements; \
    ./autogen.sh; \
    ./configure --prefix="${SST_PREFIX}" --with-sst-core="${SST_PREFIX}"; \
    make -j"${MAKE_JOBS}"; \
    make install; \
    cd /tmp/sst-build; \
    rm -rf sst-elements; \
    find "${SST_PREFIX}" -name "*.a" -type f -delete; \
    find "${SST_PREFIX}" -name "*.la" -type f -delete; \
    find "${SST_PREFIX}" -name "*.lai" -type f -delete; \
    find "${SST_PREFIX}" -name "__pycache__" -type d -prune -exec rm -rf {} +; \
    find "${SST_PREFIX}" -name "*.pyc" -type f -delete; \
    find "${SST_PREFIX}" -name "*.pyo" -type f -delete; \
    rm -rf /root/.cache /tmp/*; \
    df -h

RUN set -eux; \
    grep -RIl "/tmp/sst-build" "${SST_PREFIX}" 2>/dev/null | while read -r file; do \
        sed -i \
            -e 's#/tmp/sst-build/sst-elements##g' \
            -e 's#/tmp/sst-build/sst-core##g' \
            "$file" || true; \
    done; \
    find "${SST_PREFIX}" -name "*.a" -type f -delete; \
    find "${SST_PREFIX}" -name "*.la" -type f -delete; \
    find "${SST_PREFIX}" -name "*.lai" -type f -delete; \
    find "${SST_PREFIX}" -name "__pycache__" -type d -prune -exec rm -rf {} +; \
    find "${SST_PREFIX}" -name "*.pyc" -type f -delete; \
    find "${SST_PREFIX}" -name "*.pyo" -type f -delete; \
    du -sh "${SST_PREFIX}"; \
    df -h


FROM ubuntu:24.04 AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG SST_PREFIX=/opt/sst

ENV SST_CORE_HOME=${SST_PREFIX}
ENV SST_ELEMENTS_HOME=${SST_PREFIX}
ENV PATH=${SST_PREFIX}/bin:${PATH}
ENV LD_LIBRARY_PATH=${SST_PREFIX}/lib:${SST_PREFIX}/lib/sst-elements-library:${SST_PREFIX}/lib/sst-elements-library/ext:${LD_LIBRARY_PATH}
ENV PYTHONPATH=${SST_PREFIX}/lib/python3.12/site-packages:${SST_PREFIX}/lib/python3.12/dist-packages:${PYTHONPATH}
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gfortran \
    libpython3.12 \
    libboost-atomic1.83.0 \
    libboost-chrono1.83.0 \
    libboost-date-time1.83.0 \
    libboost-filesystem1.83.0 \
    libboost-program-options1.83.0 \
    libboost-regex1.83.0 \
    libboost-serialization1.83.0 \
    libboost-system1.83.0 \
    libboost-thread1.83.0 \
    libconfig9 \
    libegl1 \
    libffi8 \
    libgl1 \
    libhdf5-103-1t64 \
    libltdl7 \
    libopenmpi3t64 \
    libreadline8t64 \
    libsqlite3-0 \
    libssl3t64 \
    libxkbcommon-x11-0 \
    openmpi-bin \
    python3 \
    python3-pip \
    python3-venv \
    tcl \
    xvfb \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder ${SST_PREFIX} ${SST_PREFIX}

RUN set -eux; \
    ldconfig; \
    ldd "${SST_PREFIX}/bin/sst"; \
    ldd "${SST_PREFIX}/bin/sst-info"; \
    if ldd "${SST_PREFIX}/bin/sst" | grep -q "not found"; then \
        echo "Missing runtime libraries for sst:"; \
        ldd "${SST_PREFIX}/bin/sst" | grep "not found"; \
        exit 1; \
    fi; \
    if ldd "${SST_PREFIX}/bin/sst-info" | grep -q "not found"; then \
        echo "Missing runtime libraries for sst-info:"; \
        ldd "${SST_PREFIX}/bin/sst-info" | grep "not found"; \
        exit 1; \
    fi; \
    which sst; \
    which sst-info; \
    sst --version || true; \
    sst-info --version || true; \
    sst-info | head -100; \
    du -sh "${SST_PREFIX}"; \
    df -h

WORKDIR /workspace