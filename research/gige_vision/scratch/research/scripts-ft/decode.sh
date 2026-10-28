#!/bin/bash
P=/out/gev_${TAG:-clean}.pcap
H="--enable-heuristic gvsp_udp"
echo "== GVCP commands seen (count by info prefix) =="
tshark -r $P $H -Y gvcp -T fields -e _ws.col.Info 2>/dev/null | awk '{print $1}' | sort | uniq -c
echo "== GVCP writes to stream-channel registers (0x0d00..0x0d3c) =="
tshark -r $P $H -Y 'gvcp' -T fields -e frame.number -e udp.srcport -e udp.dstport -e _ws.col.Info 2>/dev/null | grep -i "SCP\|SCDA\|0x00000d" | head -20
echo "== First GVSP frame block: first 4 and last 3 packets =="
FIRST=$(tshark -r $P $H -Y 'gvsp' -T fields -e frame.number 2>/dev/null | head -1)
tshark -r $P $H -Y "gvsp && frame.number >= $FIRST && frame.number < $((FIRST+200))" -T fields -e frame.number -e frame.len -e udp.srcport -e udp.dstport -e _ws.col.Info 2>/dev/null | awk 'NR<=4 || /TRAILER/' | head -8
echo "== Verbose decode of first GVSP leader and first trailer =="
L=$(tshark -r $P $H -Y 'gvsp.format == 1' -T fields -e frame.number 2>/dev/null | head -1)
T=$(tshark -r $P $H -Y 'gvsp.format == 2' -T fields -e frame.number 2>/dev/null | head -1)
tshark -r $P $H -Y "frame.number == $L" -O gvsp 2>/dev/null | sed -n '/GigE Vision Streaming/,$p'
echo "-- leader raw bytes (UDP payload) --"
tshark -r $P $H -Y "frame.number == $L" -T fields -e udp.payload 2>/dev/null
tshark -r $P $H -Y "frame.number == $T" -O gvsp 2>/dev/null | sed -n '/GigE Vision Streaming/,$p'
echo "-- trailer raw bytes (UDP payload) --"
tshark -r $P $H -Y "frame.number == $T" -T fields -e udp.payload 2>/dev/null
echo "== Leader timestamps of first 5 frames =="
tshark -r $P $H -Y 'gvsp.format == 1' -T fields -e frame.time_epoch -e gvsp.blockid16 -e gvsp.timestamp 2>/dev/null | head -5
echo "== resend commands / resent packets =="
tshark -r $P $H -Y 'gvcp.cmd == 0x0040' -T fields -e frame.number -e _ws.col.Info 2>/dev/null | head -10
echo "resent GVSP packets (status 0x0100):" $(tshark -r $P $H -Y 'gvsp.status == 0x0100' 2>/dev/null | wc -l)
