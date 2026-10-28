FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends aravis-tools aravis-tools-cli python3 python3-venv libpython3.12t64 iproute2 ca-certificates && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/hv && /opt/hv/bin/pip install --no-cache-dir harvesters==1.4.3 genicam==1.6.0 numpy
