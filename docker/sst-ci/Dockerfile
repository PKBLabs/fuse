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
    libncurses-dev \
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
    libboost-atomic1.83.0 \
    libboost-chrono1.83.0 \
    libboost-date-time1.83.0 \
    libboost-filesystem1.83.0 \
    libboost-iostreams1.83.0 \
    libboost-program-options1.83.0 \
    libboost-regex1.83.0 \
    libboost-serialization1.83.0 \
    libboost-system1.83.0 \
    libboost-thread1.83.0 \
    libconfig9 \
    libdbus-1-3 \
    libegl1 \
    libffi8 \
    libfontconfig1 \
    libfreetype6 \
    libgl1 \
    libglib2.0-0 \
    libhdf5-103-1t64 \
    libltdl7 \
    libncurses6 \
    libncursesw6 \
    libopenmpi3t64 \
    libpython3.12 \
    libreadline8t64 \
    libsqlite3-0 \
    libssl3t64 \
    libtinfo6 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-cursor0 \
    libxcb-glx0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-shm0 \
    libxcb-sync1 \
    libxcb-util1 \
    libxcb-xfixes0 \
    libxcb-xkb1 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libxrender1 \
    openmpi-bin \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    tcl \
    xvfb \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder ${SST_PREFIX} ${SST_PREFIX}

RUN set -eux; \
    ldconfig; \
    find "${SST_PREFIX}/bin" "${SST_PREFIX}/lib" \
        -type f \( -perm /111 -o -name "*.so" -o -name "*.so.*" \) \
        -print0 \
      | xargs -0 -r ldd \
      | tee /tmp/sst-ldd.txt; \
    if grep -q "not found" /tmp/sst-ldd.txt; then \
        echo "Missing SST runtime shared libraries:"; \
        grep "not found" /tmp/sst-ldd.txt; \
        exit 1; \
    fi; \
    rm -f /tmp/sst-ldd.txt; \
    which sst; \
    which sst-info; \
    sst --version || true; \
    sst-info --version || true; \
    sst-info > /tmp/sst-info.txt; \
    head -100 /tmp/sst-info.txt; \
    rm -f /tmp/sst-info.txt; \
    du -sh "${SST_PREFIX}"; \
    df -h

WORKDIR /workspace