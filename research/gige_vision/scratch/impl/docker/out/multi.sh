#!/bin/bash
# Test container on the dedicated network; cameras: Aravis fakes .11/.12, viva fakes .21/.22
cd /out
echo "### interfaces"; ip -4 -o addr show | awk '{print $2, $4}'
echo "### gev_probe: broadcast discovery on all interfaces"
python3 /gige/gev_probe.py --json /out/multi_probe.json; echo "exit=$?"
echo "### gev_ptp_sync_test: all cameras (mixed emulators), programs keys where supported"
python3 /gige/gev_ptp_sync_test.py --enable-ptp --ptp-timeout 5 --duration 3 --json /out/multi_ptp_all.json 2>&1 | tail -22; echo "exit=${PIPESTATUS[0]}"
echo "### gev_ptp_sync_test: two viva fakes, emulator action keys, subnet broadcast"
python3 /gige/gev_ptp_sync_test.py --ip 172.31.77.21 --ip 172.31.77.22 --no-program-keys --device-key 0x42 --group-key 1 --group-mask 1 --duration 3 --json /out/multi_ptp_viva.json 2>&1 | grep -E "ACTION|sending|exit|verdict|accepted"; echo "exit=${PIPESTATUS[0]}"
echo "### gev_ptp_sync_test: same, unicast"
python3 /gige/gev_ptp_sync_test.py --ip 172.31.77.21 --ip 172.31.77.22 --no-program-keys --device-key 0x42 --group-key 1 --group-mask 1 --duration 3 --action-dest unicast 2>&1 | grep -E "ACTION|sending"; echo "exit=${PIPESTATUS[0]}"
echo "### gvsp_capture_report live: viva fake over the bridge (stdlib control, forced buffer)"
python3 /gige/gvsp_capture_report.py --ip 172.31.77.21 --seconds 3 --force-rcvbuf --json /out/multi_live_viva.json 2>&1 | grep -E "\[|frames:|image:"; echo "exit=${PIPESTATUS[0]}"
echo "### gvsp_capture_report live: Aravis fake over the bridge"
python3 /gige/gvsp_capture_report.py --ip 172.31.77.11 --seconds 3 --force-rcvbuf --json /out/multi_live_arv.json 2>&1 | grep -E "\[|frames:|image:"; echo "exit=${PIPESTATUS[0]}"
echo "### gvsp_capture_report live: viva fake, --control viva"
/opt/viva/bin/python /gige/gvsp_capture_report.py --ip 172.31.77.22 --seconds 3 --force-rcvbuf --control viva 2>&1 | grep -E "\[|frames:|control"; echo "exit=${PIPESTATUS[0]}"   # viva cannot discover an IP-bound viva fake -> clean FAIL
