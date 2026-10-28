FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq git meson ninja-build gcc g++ pkg-config libxml2-dev libglib2.0-dev zlib1g-dev libusb-1.0-0-dev gobject-introspection libgirepository1.0-dev python3-gi python3-numpy gettext >/dev/null && rm -rf /var/lib/apt/lists/*
