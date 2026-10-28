#!/bin/bash
# Runs inside gev-ft-research container. Emulated GigE Vision camera over loopback + packet capture.
set -u
OUT=/out
LOST=${LOST:-0}
TAG=${TAG:-clean}
cat /aravis-version.txt
arv-fake-gv-camera-0.8 -i 127.0.0.1 -s GV01 -r $LOST > $OUT/fake_$TAG.log 2>&1 &
FAKE=$!
sleep 1
tcpdump -i lo -U -w $OUT/gev_$TAG.pcap udp > $OUT/tcpdump_$TAG.log 2>&1 &
TD=$!
sleep 1
echo "== arv-tool-0.8 (discovery) =="
arv-tool-0.8 2>&1
echo "== arv-tool-0.8 control (stream/timestamp features) =="
arv-tool-0.8 -n Aravis-Fake-GV01 control PixelFormat Width Height PayloadSize GevSCPSPacketSize GevSCPD GevTimestampTickFrequency 2>&1
echo "== arv-camera-test-0.8 =="
arv-camera-test-0.8 -n Aravis-Fake-GV01 -f 10 --duration 2 ${EXTRA:-} 2>&1 | tail -25
sleep 1
kill $TD; wait $TD 2>/dev/null
kill $FAKE; wait $FAKE 2>/dev/null
echo "== packet counts by protocol =="
tshark -r $OUT/gev_$TAG.pcap --enable-heuristic gvsp_udp -T fields -e _ws.col.Protocol 2>/dev/null | sort | uniq -c
