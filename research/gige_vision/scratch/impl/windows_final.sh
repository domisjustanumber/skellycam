#!/bin/bash
# Final Windows-native verification run (Git Bash). Fakes run in a separate process from the viva-win venv.
S="C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad"
G=C:/Users/Dom/GitHub/freemocap/skellycam/research/gige_vision/hardware_tests  # was skellycam/system/diagnostics/gige before 2026-10-28
PY=$S/venvs/viva-win/Scripts/python.exe   # python 3.12 + viva-genicam 0.10.0
W=$S/impl/win_out; rm -rf $W; mkdir -p $W; cd $W
run() { echo; echo "\$ $*"; "$@"; echo "[exit=$?]"; }
waitfakes() { while ! grep -q "blocks_sent" "$1" 2>/dev/null; do sleep 1; done; }
echo "### host: $(python --version) $(uname -a)"
echo "### selftests + --help (system python 3.12, no viva-genicam)"
for s in gev_probe gev_ptp_sync_test gvsp_capture_report udp_recv_benchmark viva_sync_capture_test; do python $G/$s.py --selftest | tail -1; python $G/$s.py --help > /dev/null && echo "$s --help exit 0"; done
run python $G/viva_sync_capture_test.py --duration 1
echo "### broadcast discovery on all interfaces, no cameras"
run python $G/gev_probe.py --timeout 1
($PY $S/impl/run_viva_fakes.py -n 2 --seconds 40 --drop "3:5,4:10,4:11,6:100" > fakes.log 2>&1 &); sleep 3
run python $G/gev_probe.py --ip 127.0.0.1 --ip 127.0.0.2 --json probe.json --save-xml xml
run python $G/gev_ptp_sync_test.py --ip 127.0.0.1 --ip 127.0.0.2 --enable-ptp --ptp-timeout 5 --duration 2 --no-program-keys --device-key 0x42 --group-key 1 --group-mask 1 --json ptp.json
run python $G/gvsp_capture_report.py --ip 127.0.0.1 --seconds 3 --save-frame frames --json live.json
run python $G/gvsp_capture_report.py --ip 127.0.0.2 --seconds 3 --no-resend --json live_noresend.json
run $PY $G/gvsp_capture_report.py --ip 127.0.0.2 --seconds 1 --control viva
waitfakes fakes.log; cat fakes.log
echo "### viva script with in-process fake"
run $PY $G/viva_sync_capture_test.py --fake-cameras 1 --duration 3 --out viva_free
run $PY $G/viva_sync_capture_test.py --fake-cameras 1 --mode scheduled-action --out viva_sched_skip
run $PY $G/viva_sync_capture_test.py --fake-cameras 1 --mode scheduled-action --skip-trigger-config --device-key 0x42 --group-key 1 --group-mask 1 --triggers 60 --out viva_sched_dry
echo "### simulated-register harnesses"
($PY $S/impl/run_viva_fakes.py -n 2 --seconds 25 > fakes_sim.log 2>&1 &); sleep 3; run python $S/impl/harness_ptp_sim.py $G synced; waitfakes fakes_sim.log
($PY $S/impl/run_viva_fakes.py -n 2 --seconds 25 > fakes_sim2.log 2>&1 &); sleep 3; run python $S/impl/harness_ptp_sim.py $G unsynced; waitfakes fakes_sim2.log
run $PY $S/impl/harness_viva_revoke.py $G viva_revoke
run $PY $S/impl/harness_stdlib_revoke.py $G
run $PY $S/impl/harness_viva_ptp_sim.py $G lock viva_ptp_lock
run $PY $S/impl/harness_viva_ptp_sim.py $G nolock viva_ptp_nolock
echo "### udp benchmark"
run python $G/udp_recv_benchmark.py --sizes 1472,8972 --rates 1000,0 --seconds 2 --json bench_local.json
(timeout 30 python $G/udp_recv_benchmark.py --role receiver --bind 127.0.0.1 --port 50200 --max-runs 2 --json bench_rx.json > bench_rx.log 2>&1 &); sleep 2
run python $G/udp_recv_benchmark.py --role sender --target 127.0.0.1 --port 50200 --sizes 1472,8972 --rates 800 --seconds 3
sleep 4; cat bench_rx.log
