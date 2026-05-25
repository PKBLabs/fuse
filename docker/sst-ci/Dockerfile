FROM ubuntu:24.04 AS builder

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


FROM ubuntu:24.04 AS runtime

ARG DEBIAN_FRONTEND=noninteractive
ARG SST_PREFIX=/opt/sst

ENV SST_CORE_HOME=${SST_PREFIX}
ENV SST_ELEMENTS_HOME=${SST_PREFIX}
ENV PATH=${SST_PREFIX}/bin:${PATH}
ENV LD_LIBRARY_PATH=${SST_PREFIX}/lib:${SST_PREFIX}/lib/sst-elements-library:${LD_LIBRARY_PATH}
ENV PYTHONPATH=${SST_PREFIX}/lib/python3.12/site-packages:${SST_PREFIX}/lib/python3.12/dist-packages:${PYTHONPATH}
ENV QT_QPA_PLATFORM=offscreen

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gfortran \
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

RUN ldconfig \
    && which sst \
    && which sst-info \
    && sst --version || true \
    && sst-info --version || true \
    && sst-info | head -100

WORKDIR /workspace