#!/bin/bash
# viva-genicam tests on the dedicated network against the two Aravis fakes (.11/.12)
cd /out
echo "### viva_sync_capture_test: free-run, two Aravis fakes (their timestamps share the host clock)"
/opt/viva/bin/python /gige/viva_sync_capture_test.py --ip 172.31.77.11 --ip 172.31.77.12 --fps 25 --duration 6 --skip-ptp --out /out/viva_arv_free; echo "exit=$?"
echo "### same, --expect-aligned (free-run phase is arbitrary -> expected FAIL on spread)"
/opt/viva/bin/python /gige/viva_sync_capture_test.py --ip 172.31.77.11 --ip 172.31.77.12 --fps 25 --duration 4 --expect-aligned --out /out/viva_arv_free_aligned 2>&1 | grep -E "spread|pairing|PTP"; echo "exit=${PIPESTATUS[0]}"
echo "### scheduled-action against Aravis fakes (no Action1 -> SKIP)"
/opt/viva/bin/python /gige/viva_sync_capture_test.py --ip 172.31.77.11 --ip 172.31.77.12 --mode scheduled-action --out /out/viva_arv_sched 2>&1 | grep -E "SKIP|FAIL|PASS"; echo "exit=${PIPESTATUS[0]}"
echo "### scheduled-action dry run against Aravis fakes (latch returns 0 -> SKIP)"
/opt/viva/bin/python /gige/viva_sync_capture_test.py --ip 172.31.77.11 --ip 172.31.77.12 --mode scheduled-action --skip-trigger-config --out /out/viva_arv_sched_dry 2>&1 | grep -E "SKIP|FAIL|PASS|WARN"; echo "exit=${PIPESTATUS[0]}"
echo "### gvsp_capture_report --control viva against an Aravis fake"
/opt/viva/bin/python /gige/gvsp_capture_report.py --ip 172.31.77.12 --seconds 3 --force-rcvbuf --control viva 2>&1 | grep -E "\[|frames:|control"; echo "exit=${PIPESTATUS[0]}"
echo "### gvsp_capture_report --control viva against an unreachable IP (clean FAIL expected)"
/opt/viva/bin/python /gige/gvsp_capture_report.py --ip 172.31.77.99 --seconds 1 --control viva 2>&1 | tail -3; echo "exit=${PIPESTATUS[0]}"
echo "### viva_sync_capture_test --fake-cameras 1 (in-process viva fake) free-run + scheduled dry run"
/opt/viva/bin/python /gige/viva_sync_capture_test.py --fake-cameras 1 --duration 3 --out /out/viva_fake_free 2>&1 | grep -E "PASS|FAIL|WARN"; echo "exit=${PIPESTATUS[0]}"
/opt/viva/bin/python /gige/viva_sync_capture_test.py --fake-cameras 1 --mode scheduled-action --skip-trigger-config --device-key 0x42 --group-key 1 --group-mask 1 --triggers 60 --out /out/viva_fake_sched 2>&1 | grep -E "PASS|FAIL|WARN|actions at"; echo "exit=${PIPESTATUS[0]}"
/opt/viva/bin/python /gige/viva_sync_capture_test.py --fake-cameras 1 --mode scheduled-action --skip-trigger-config --device-key 0x42 --group-key 1 --group-mask 1 --triggers 60 --action-sender stdlib --out /out/viva_fake_sched_stdlib 2>&1 | grep -E "PASS|FAIL|WARN|actions at"; echo "exit=${PIPESTATUS[0]}"
