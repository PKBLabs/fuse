FROM ubuntu:24.04

ARG DEBIAN_FRONTEND=noninteractive
ARG SST_CORE_REF=v15.1.2_Final
ARG SST_ELEMENTS_REF=v15.1.0_Final
ARG SST_VERSION=15.1.2
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

RUN git clone --depth 1 --branch ${SST_CORE_REF} \
    https://github.com/sstsimulator/sst-core.git

RUN cd sst-core \
    && ./autogen.sh \
    && ./configure --prefix=${SST_PREFIX} \
    && make -j"$(nproc)" \
    && make install

RUN git clone --depth 1 --branch ${SST_ELEMENTS_REF} \
    https://github.com/sstsimulator/sst-elements.git

RUN cd sst-elements \
    && ./autogen.sh \
    && ./configure --prefix=${SST_PREFIX} --with-sst-core=${SST_PREFIX} \
    && make -j"$(nproc)" \
    && make install

RUN ldconfig

RUN which sst
RUN which sst-info
RUN sst --version || true
RUN sst-info --version || true
RUN sst-info | head -100

WORKDIR /workspace