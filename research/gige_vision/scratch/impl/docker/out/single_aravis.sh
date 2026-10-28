#!/bin/bash
# Single container, --network none: Aravis fake camera on loopback.
cd /out
echo "### python: $(python3 --version), viva: $(/opt/viva/bin/python -c 'import viva_genicam;print(viva_genicam.__version__)'), aravis: $(dpkg-query -W -f='${Version}' aravis-tools)"
echo "### selftests"
python3 /gige/gev_common.py | tail -1
for s in gev_probe gev_ptp_sync_test gvsp_capture_report udp_recv_benchmark; do python3 /gige/$s.py --selftest | tail -1; done
/opt/viva/bin/python /gige/viva_sync_capture_test.py --selftest | tail -1
echo "### --help smoke"
for s in gev_probe gev_ptp_sync_test gvsp_capture_report udp_recv_benchmark viva_sync_capture_test; do python3 /gige/$s.py --help > /dev/null && echo "$s --help ok"; done
echo "### viva script without viva-genicam installed (system python3)"; python3 /gige/viva_sync_capture_test.py; echo "exit=$?"
arv-fake-gv-camera-0.8 -i lo > /out/arv_fake.log 2>&1 &
sleep 2
echo "### gev_probe vs Aravis fake"
python3 /gige/gev_probe.py --ip 127.0.0.1 --json /out/aravis_probe.json --save-xml /out/aravis_xml; echo "exit=$?"
echo "### gev_ptp_sync_test vs Aravis fake"
python3 /gige/gev_ptp_sync_test.py --ip 127.0.0.1 --enable-ptp --ptp-timeout 5 --duration 3 --json /out/aravis_ptp.json; echo "exit=$?"
echo "### gvsp_capture_report live vs Aravis fake (tcpdump running)"
tcpdump -i lo -s 128 -w /out/aravis_live.pcap udp 2>/dev/null & TPID=$!
sleep 1
python3 /gige/gvsp_capture_report.py --ip 127.0.0.1 --seconds 3 --json /out/aravis_live.json --save-frame /out/frames; echo "exit=$?"
sleep 1; kill $TPID; sleep 1
echo "### live with OS-default receive buffer (--rcvbuf 0)"
python3 /gige/gvsp_capture_report.py --ip 127.0.0.1 --seconds 3 --rcvbuf 0 2>&1 | grep -E "frames:|complete|buffer|drops"; echo "exit=${PIPESTATUS[0]}"
echo "### live with SO_RCVBUFFORCE (root in container)"
python3 /gige/gvsp_capture_report.py --ip 127.0.0.1 --seconds 3 --force-rcvbuf --packet-size 8000 --test-packet 2>&1 | grep -E "frames:|complete|buffer|drops|test packet|packet size"; echo "exit=${PIPESTATUS[0]}"
echo "### pcap mode on the tcpdump capture (snaplen 128)"
python3 /gige/gvsp_capture_report.py --pcap /out/aravis_live.pcap --tick-hz 1000000000 --json /out/aravis_pcap.json; echo "exit=$?"
echo "### tshark cross-check of the same capture"
echo "tshark GVSP leaders: $(tshark -r /out/aravis_live.pcap -Y 'gvsp.format == 1' 2>/dev/null | wc -l), trailers: $(tshark -r /out/aravis_live.pcap -Y 'gvsp.format == 2' 2>/dev/null | wc -l)"
tshark -r /out/aravis_live.pcap -Y 'gvsp.format == 1' -T fields -e gvsp.payloadtype -e gvsp.pixel -e gvsp.sizex -e gvsp.sizey 2>/dev/null | sort | uniq -c | head -3
echo "### tshark decode of selftest GVCP packets"
python3 - <<'PY'
import sys; sys.path.insert(0, "/gige")
import gev_common as g
pk = [g.build_action_cmd(0x12345678, 1, 0xFFFFFFFF, None, 0x0102), g.build_action_cmd(0x12345678, 1, 1, 0x000001E23F5A1000, 0x0103),
      g.build_packetresend(0x1234, 5, 9, 0x0A0B), g.build_packetresend(0x0000000100000002, 5, 9, 0x0A0C, extended_ids=True),
      g.build_readreg([0x0934, 0x096C], 3), g.build_writereg([(0x0944, 2)], 4), g.build_readmem(0x0200, 512, 5), g.build_discovery(0xFFFF)]
g.write_pcap("/out/selftest_gvcp.pcap", [("192.168.1.10", 50000, "192.168.1.20", g.GVCP_PORT, p) for p in pk])
fr = g.synth_gvsp_frame(7, 123456789, 0x01080009, 64, 48, 1000) + g.synth_gvsp_frame(2**33, 5, 0x01080001, 64, 48, 1000, extended_ids=True)
g.write_pcap("/out/selftest_gvsp.pcap", [("192.168.1.20", 20202, "192.168.1.10", 40000, p) for p in fr])
PY
tshark -r /out/selftest_gvcp.pcap -T fields -E separator='|' -e gvcp.cmd -e gvcp.flag -e gvcp.cmd.action.devicekey -e gvcp.cmd.action.groupkey -e gvcp.cmd.action.groupmask -e gvcp.cmd.action.time -e gvcp.cmd.resend.firstpacketid -e gvcp.cmd.resend.lastpacketid -e gvcp.cmd.resend.blockid -e gvcp.cmd.resend.blockid64 2>&1 | head -12
tshark -r /out/selftest_gvcp.pcap -V 2>/dev/null | grep -iE "Command:|Flag|Device Key|Group|Action Time|Block ID|Packet ID|Register Address|Count|Malformed" | head -60
echo "### tshark decode of selftest GVSP packets (Decode-As udp.port==40000)"
tshark -r /out/selftest_gvsp.pcap -d udp.port==40000,gvsp -T fields -e gvsp.format -e gvsp.blockid16 -e gvsp.blockid64 -e gvsp.packetid24 -e gvsp.packetid32 -e gvsp.payloadtype -e gvsp.pixel -e gvsp.sizex -e gvsp.sizey -e gvsp.timestamp 2>&1 | grep -v "^3	" | head -12
echo "### udp_recv_benchmark local (Linux default rmem_max)"
python3 /gige/udp_recv_benchmark.py --sizes 1472,8972 --rates 1000 --seconds 2 --json /out/bench_linux_capped.json | tail -9
python3 /gige/udp_recv_benchmark.py --sizes 8972 --rates 1000 --seconds 2 --force-rcvbuf | tail -4
kill %1 2>/dev/null
