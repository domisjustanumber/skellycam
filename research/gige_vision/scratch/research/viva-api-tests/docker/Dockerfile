FROM python:3.12-bookworm
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends aravis-tools iproute2 >/dev/null && rm -rf /var/lib/apt/lists/*
RUN pip install -q --no-cache-dir viva-genicam==0.10.0 numpy
