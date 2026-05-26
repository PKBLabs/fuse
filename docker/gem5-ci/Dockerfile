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
    scons \
    python3-dev \
    python3-pip \
    python3-venv \
    python3-setuptools \
    python3-wheel \
    git \
    zlib1g \
    zlib1g-dev \
    libprotobuf-dev \
    protobuf-compiler \
    libprotoc-dev \
    libgoogle-perftools-dev \
    libboost-all-dev \
    libhdf5-serial-dev \
    python3-pydot \
    python3-tk \
    m4 \
    libcapstone-dev \
    libpng-dev \
    libelf-dev \
    pkg-config \
    wget \
    curl \
    ca-certificates \
    cmake \
    doxygen \
    clang-format \
    libegl1 \
    libgl1 \
    libxkbcommon-x11-0 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "${GEM5_REF}" "${GEM5_REPO}" "${GEM5_ROOT}"

WORKDIR ${GEM5_ROOT}

RUN scons "build/${GEM5_BUILD_ISA}/gem5.opt" -j"${GEM5_BUILD_JOBS}" \
    && test -x "${GEM5_BINARY}" \
    && "${GEM5_BINARY}" --help >/tmp/gem5-help.txt 2>&1 \
    && head -40 /tmp/gem5-help.txt \
    && rm -f /tmp/gem5-help.txt \
    && find "${GEM5_ROOT}/build/${GEM5_BUILD_ISA}" -name "*.o" -type f -delete \
    && find "${GEM5_ROOT}/build/${GEM5_BUILD_ISA}" -name "*.os" -type f -delete \
    && find "${GEM5_ROOT}/build/${GEM5_BUILD_ISA}" -name "*.a" -type f -delete \
    && find "${GEM5_ROOT}" -name "__pycache__" -type d -prune -exec rm -rf {} + \
    && find "${GEM5_ROOT}" -name "*.pyc" -type f -delete \
    && find "${GEM5_ROOT}" -name "*.pyo" -type f -delete \
    && rm -rf /root/.cache /tmp/*


FROM ubuntu:24.04 AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG GEM5_BUILD_ISA=X86

ENV GEM5_ROOT=/opt/gem5
ENV GEM5_BINARY=/opt/gem5/build/${GEM5_BUILD_ISA}/gem5.opt
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    libprotobuf32t64 \
    libgoogle-perftools4t64 \
    libboost-filesystem1.83.0 \
    libboost-iostreams1.83.0 \
    libboost-program-options1.83.0 \
    libboost-regex1.83.0 \
    libboost-system1.83.0 \
    libboost-thread1.83.0 \
    libhdf5-103-1t64 \
    libcapstone4 \
    libpng16-16t64 \
    libelf1t64 \
    libegl1 \
    libgl1 \
    libxkbcommon-x11-0 \
    python3 \
    python3-pip \
    python3-venv \
    python3-pydot \
    python3-tk \
    xvfb \
    zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder ${GEM5_ROOT} ${GEM5_ROOT}

RUN test -x "${GEM5_BINARY}" \
    && "${GEM5_BINARY}" --help >/tmp/gem5-help.txt 2>&1 \
    && head -40 /tmp/gem5-help.txt \
    && rm -f /tmp/gem5-help.txt \
    && du -sh "${GEM5_ROOT}" \
    && df -h

WORKDIR /workspace