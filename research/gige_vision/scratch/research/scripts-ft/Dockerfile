FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq git ca-certificates meson ninja-build gcc g++ pkg-config \
    libglib2.0-dev libxml2-dev zlib1g-dev gettext tcpdump tshark python3 procps iproute2 >/dev/null && rm -rf /var/lib/apt/lists/*
RUN git clone -q --depth 1 --branch 0.8.36 https://github.com/AravisProject/aravis.git /aravis && cd /aravis && git log -1 --format='%H %cd' > /aravis-version.txt \
    && meson setup build -Dviewer=disabled -Dgst-plugin=disabled -Dusb=disabled -Dintrospection=disabled -Ddocumentation=disabled -Dtests=false >/dev/null \
    && ninja -C build >/dev/null && ninja -C build install >/dev/null && ldconfig
