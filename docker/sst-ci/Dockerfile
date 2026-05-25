FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG SST_VERSION=15.0.0
ARG SST_PREFIX=/opt/sst

ENV SST_CORE_HOME=${SST_PREFIX}
ENV SST_ELEMENTS_HOME=${SST_PREFIX}
ENV PATH=${SST_PREFIX}/bin:${PATH}
ENV LD_LIBRARY_PATH=${SST_PREFIX}/lib:${SST_PREFIX}/lib/sst-elements-library:${LD_LIBRARY_PATH}
ENV PYTHONPATH=${SST_PREFIX}/lib/python3.12/site-packages:${SST_PREFIX}/lib/python3.12/dist-packages:${PYTHONPATH}
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y --no-install-recommends \
    autoconf \
    automake \
    build-essential \
    ca-certificates \
    curl \
    file \
    gfortran \
    git \
    libboost-all-dev \
    libconfig-dev \
    libegl1 \
    libffi-dev \
    libgl1 \
    libhdf5-dev \
    libltdl-dev \
    libopenmpi-dev \
    libreadline-dev \
    libsqlite3-dev \
    libssl-dev \
    libtool \
    libtool-bin \
    libxkbcommon-x11-0 \
    m4 \
    make \
    openmpi-bin \
    pkg-config \
    python3 \
    python3-dev \
    python3-pip \
    python3-venv \
    tcl-dev \
    wget \
    xvfb \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp/sst-build

RUN curl -L -o sstcore.tar.gz \
    https://github.com/sstsimulator/sst-core/releases/download/v${SST_VERSION}_Final/sstcore-${SST_VERSION}.tar.gz

RUN tar xzf sstcore.tar.gz \
    && cd sstcore-${SST_VERSION} \
    && ./configure --prefix=${SST_PREFIX} \
    && make -j"$(nproc)" \
    && make install

RUN curl -L -o sstelements.tar.gz \
    https://github.com/sstsimulator/sst-elements/releases/download/v${SST_VERSION}_Final/sstelements-${SST_VERSION}.tar.gz

RUN tar xzf sstelements.tar.gz \
    && cd sstelements-${SST_VERSION} \
    && ./configure --prefix=${SST_PREFIX} --with-sst-core=${SST_PREFIX} \
    && make -j"$(nproc)" \
    && make install

RUN ldconfig

RUN which sst-info
RUN sst-info --version || true
RUN sst-info | head -100

WORKDIR /workspace