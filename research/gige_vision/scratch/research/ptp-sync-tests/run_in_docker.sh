#!/bin/bash
# Runs inside the gev-ptp-test container. /t is this folder (read-only), /out is writable.
set -u
cd /out
echo "=== versions"; tshark --version | head -1; dpkg -l | awk '/aravis-tools /{print $2,$3}'; python3 --version
echo; echo "=== 1. offline selftest + tshark decode of generated ACTION_CMD packets"
python3 -I /t/gev_ptp_sync_test.py selftest --pcap /out/action_cmds.pcap
tshark -r /out/action_cmds.pcap -d udp.port==3956,gvcp -V -Y gvcp 2>/dev/null | grep -E "Command:|Flags|Scheduled Action|Acknowledge Required|Device Key|Group Key|Group Mask|Action Scheduled Time|Payload Length|Request ID" 
echo; echo "=== 2. start Aravis fake GigE Vision camera on loopback"
arv-fake-gv-camera-0.8 -i 127.0.0.1 > /out/fake.log 2>&1 &
FAKE=$!
sleep 2
tshark -i lo -w /out/live.pcap -f "udp" > /out/tshark.log 2>&1 &
TS=$!
sleep 2
echo; echo "=== 3. arv-tool feature query (GenICam names)"
arv-tool-0.8 -a 127.0.0.1 control GevTimestampTickFrequency GevIEEE1588 PtpEnable GevIEEE1588Status PtpStatus ActionDeviceKey TriggerSource TimestampLatch 2>&1 | head -20
arv-tool-0.8 -a 127.0.0.1 features 2>/dev/null | grep -i -E "ptp|1588|action|timestamp" | head -20
echo; echo "=== 4. probe (bootstrap registers)"
python3 -I /t/gev_ptp_sync_test.py probe 127.0.0.1
echo; echo "=== 5. latch timestamps (camera clock vs host clock)"
python3 -I /t/gev_ptp_sync_test.py latch 127.0.0.1 127.0.0.1 --rounds 10
echo; echo "=== 6. ptp --enable (expect: capability says not supported)"
python3 -I /t/gev_ptp_sync_test.py ptp 127.0.0.1 --enable --timeout 3; echo "rc=$?"
echo; echo "=== 7. action (expect: fake camera does not implement ACTION_CMD -> no ACTION_ACK)"
python3 -I /t/gev_ptp_sync_test.py action 127.0.0.1 --dest 127.0.0.1 --delay-ms 200; echo "rc=$?"
echo; echo "=== 8. stream a few frames to capture GVSP leader timestamps"
date +%s%N > /out/host_ns_before
timeout 4 arv-camera-test-0.8 -n Aravis-Fake-GV01 2>&1 | tail -3
date +%s%N > /out/host_ns_after
sleep 1
kill $TS; sleep 1; kill $FAKE
echo; echo "=== 9. decode live capture"
tshark -r /out/live.pcap -d udp.port==3956,gvcp -Y "gvcp" -T fields -e gvcp.cmd.command 2>/dev/null | sort | uniq -c | sort -rn | head -15
echo "-- action commands seen on the wire:"
tshark -r /out/live.pcap -d udp.port==3956,gvcp -Y "gvcp.cmd.command == 0x0100" -T fields -e ip.dst -e gvcp.cmd.flag.scheduledactioncommand -e gvcp.cmd.action.devicekey -e gvcp.cmd.action.groupkey -e gvcp.cmd.action.groupmask -e gvcp.cmd.action.time 2>/dev/null
echo "-- GVSP leader timestamps (first 5) vs host clock window:"
tshark -r /out/live.pcap -Y "gvsp.format == 1" -T fields -e gvsp.blockid16 -e gvsp.timestamp -e gvsp.pixel -e gvsp.sizex -e gvsp.sizey 2>/dev/null | head -5
echo "host_ns_before=$(cat /out/host_ns_before) host_ns_after=$(cat /out/host_ns_after)"
echo "-- fake camera log tail:"; tail -5 /out/fake.log
