#!/bin/bash
cd /out
arv-fake-gv-camera-0.8 -i lo > /dev/null 2>&1 &
sleep 2
python3 /gige/gvsp_capture_report.py --ip 127.0.0.1 --seconds 3 --force-rcvbuf --packet-size 8000 --test-packet 2>&1 | grep -E "frames:|frames complete|buffer|drops|test packet"; echo "exit=${PIPESTATUS[0]}"
python3 /gige/udp_recv_benchmark.py --sizes 8972 --rates 1000 --seconds 2 --force-rcvbuf | grep -E "PASS|FAIL|WARN" | head -3
tshark -r /out/selftest_gvcp.pcap -V 2>/dev/null | grep -iE "time" | grep -iv "arrival\|epoch\|since\|shift\|delta\|reference\|utc" | head -5
