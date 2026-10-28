FROM python:3.12-bookworm
RUN apt-get update -qq && apt-get install -y -qq aravis-tools gir1.2-aravis-0.8 python3-gi iproute2 >/dev/null && rm -rf /var/lib/apt/lists/*
RUN pip install -q numpy psutil pytest
