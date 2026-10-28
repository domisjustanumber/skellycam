# Test image for research/gige_vision/hardware_tests (was skellycam/system/diagnostics/gige before 2026-10-28): Aravis fake GigE camera + tcpdump/tshark + python3 + viva-genicam
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
      aravis-tools aravis-tools-cli python3 python3-venv ca-certificates procps iproute2 tcpdump tshark \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/viva && /opt/viva/bin/pip install -q viva-genicam==0.10.0 numpy \
    && /opt/viva/bin/python -c "import viva_genicam, numpy; print(viva_genicam.__version__)"
