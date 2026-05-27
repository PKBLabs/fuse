FROM ubuntu:24.04 AS builder

ARG DEBIAN_FRONTEND=noninteractive
ARG GEM5_REPO=https://github.com/gem5/gem5.git
ARG GEM5_REF=v25.1.0.1
ARG GEM5_BUILD_ISA=X86
ARG GEM5_BUILD_JOBS=2

ENV GEM5_ROOT=/opt/gem5
ENV GEM5_BINARY=/opt/gem5/build/${GEM5_BUILD_ISA}/gem5.opt
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    clang-format \
    cmake \
    curl \
    doxygen \
    git \
    libboost-all-dev \
    libcapstone-dev \
    libelf-dev \
    libegl1 \
    libgl1 \
    libgoogle-perftools-dev \
    libhdf5-serial-dev \
    libpng-dev \
    libprotobuf-dev \
    libprotoc-dev \
    libxkbcommon-x11-0 \
    m4 \
    pkg-config \
    protobuf-compiler \
    python3-dev \
    python3-pip \
    python3-pydot \
    python3-setuptools \
    python3-tk \
    python3-venv \
    python3-wheel \
    scons \
    wget \
    xvfb \
    zlib1g \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${GEM5_REF}" "${GEM5_REPO}" "${GEM5_ROOT}"

WORKDIR ${GEM5_ROOT}

RUN set -eux; \
    df -h; \
    scons "build/${GEM5_BUILD_ISA}/gem5.opt" -j"${GEM5_BUILD_JOBS}"; \
    test -x "${GEM5_BINARY}"; \
    "${GEM5_BINARY}" --help > /tmp/gem5-help.txt 2>&1; \
    head -40 /tmp/gem5-help.txt; \
    rm -f /tmp/gem5-help.txt; \
    find "${GEM5_ROOT}/build/${GEM5_BUILD_ISA}" -name "*.o" -type f -delete; \
    find "${GEM5_ROOT}/build/${GEM5_BUILD_ISA}" -name "*.os" -type f -delete; \
    find "${GEM5_ROOT}/build/${GEM5_BUILD_ISA}" -name "*.a" -type f -delete; \
    find "${GEM5_ROOT}" -name "__pycache__" -type d -prune -exec rm -rf {} +; \
    find "${GEM5_ROOT}" -name "*.pyc" -type f -delete; \
    find "${GEM5_ROOT}" -name "*.pyo" -type f -delete; \
    rm -rf /root/.cache /tmp/*; \
    du -sh "${GEM5_ROOT}"; \
    df -h


FROM ubuntu:24.04 AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG GEM5_BUILD_ISA=X86

ENV GEM5_ROOT=/opt/gem5
ENV GEM5_BINARY=/opt/gem5/build/${GEM5_BUILD_ISA}/gem5.opt
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
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
    libcapstone4 \
    libdbus-1-3 \
    libegl1 \
    libelf1t64 \
    libevent-2.1-7t64 \
    libfontconfig1 \
    libfreetype6 \
    libgl1 \
    libglib2.0-0 \
    libgoogle-perftools4t64 \
    libhdf5-103-1t64 \
    libhdf5-cpp-103-1t64 \
    libpng16-16t64 \
    libprotobuf32t64 \
    libpython3.12 \
    libunwind8 \
    libx11-6 \
    libx11-xcb1 \
    libxau6 \
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
    libxdmcp6 \
    libxext6 \
    libxfixes3 \
    libxi6 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libxrender1 \
    python3 \
    python3-dev \
    python3-pip \
    python3-pydot \
    python3-tk \
    python3-venv \
    xvfb \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder ${GEM5_ROOT} ${GEM5_ROOT}

RUN set -eux; \
    ldconfig; \
    echo "Checking gem5 binary runtime dependencies:"; \
    ldd "${GEM5_BINARY}" | tee /tmp/gem5-ldd.txt || true; \
    if grep -q "not found" /tmp/gem5-ldd.txt; then \
        echo ""; \
        echo "Missing gem5 runtime shared libraries:"; \
        grep "not found" /tmp/gem5-ldd.txt; \
        echo ""; \
        echo "Full ldd output:"; \
        cat /tmp/gem5-ldd.txt; \
        exit 1; \
    fi; \
    rm -f /tmp/gem5-ldd.txt; \
    test -x "${GEM5_BINARY}"; \
    echo "Running gem5 help check:"; \
    "${GEM5_BINARY}" --help > /tmp/gem5-help.txt 2>&1; \
    head -40 /tmp/gem5-help.txt; \
    rm -f /tmp/gem5-help.txt; \
    du -sh "${GEM5_ROOT}"; \
    df -h

WORKDIR /workspace