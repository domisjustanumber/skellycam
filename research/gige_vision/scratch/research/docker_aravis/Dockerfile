FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq aravis-tools aravis-tools-cli gir1.2-aravis-0.8 python3-gi python3-numpy >/dev/null && rm -rf /var/lib/apt/lists/*
