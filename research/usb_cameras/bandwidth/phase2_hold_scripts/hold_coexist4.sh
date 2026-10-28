#!/bin/bash
H=/c/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/bandwidth
uv run --script $H/win_usb_topology.py --out /c/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/results/windows/Gerald/phase2_bw_alt/topology_before_coexist4.json > /dev/null 2>&1
$H/coexist_hold.sh /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/runs/phase2/bin/uvc_capture_test.exe /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/runs/phase2/coexist4 gen_first "7 8 9"
uv run --script $H/win_usb_topology.py --out /c/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/results/windows/Gerald/phase2_bw_alt/topology_after_coexist4.json > /dev/null 2>&1
$H/coexist_hold.sh /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/runs/phase2/bin/uvc_capture_test.exe /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/runs/phase2/coexist4 c930e_first "8"
uv run --script $H/win_usb_topology.py --out /c/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/results/windows/Gerald/phase2_bw_alt/topology_after_coexist4b.json > /dev/null 2>&1
