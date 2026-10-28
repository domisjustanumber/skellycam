#!/bin/bash
H=/c/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/bandwidth; E=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/runs/phase2/bin/uvc_capture_test.exe; O=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/runs/phase2/sweep
TAG=_bwf2.0 $H/alt_sweep_run.sh $E $O 1280 720 30 10 "0" --bandwidth-factor 2.0
TAG=_bwf1.0 $H/alt_sweep_run.sh $E $O 1280 720 30 10 "0" --bandwidth-factor 1.0
TAG=_bwf1.5 $H/alt_sweep_run.sh $E $O 1920 1080 30 10 "0" --bandwidth-factor 1.5
