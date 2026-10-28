FROM python:3.12-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends aravis-tools gir1.2-aravis-0.8 python3-gi iproute2 procps && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir numpy psutil pytest
