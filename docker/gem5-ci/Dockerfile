FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG GEM5_REPO=https://github.com/gem5/gem5.git
ARG GEM5_REF=stable

ENV GEM5_ROOT=/opt/gem5
ENV GEM5_BINARY=/opt/gem5/build/X86/gem5.opt
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    scons \
    python3-dev \
    python3-pip \
    python3-venv \
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
    cmake \
    doxygen \
    clang-format \
    libegl1 \
    libgl1 \
    libxkbcommon-x11-0 \
    xvfb \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch ${GEM5_REF} ${GEM5_REPO} ${GEM5_ROOT}

WORKDIR ${GEM5_ROOT}

RUN scons build/X86/gem5.opt -j"$(nproc)"

RUN ${GEM5_BINARY} --version

WORKDIR /workspace