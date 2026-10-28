#!/bin/bash
# analyze_run.sh RUN_DIR [c922col] [c930ecol]  -- the earlier (flash_verify_*) analysis set on one run; logs commands
cd /c/Users/Dom/GitHub/freemocap/skellycam
RUN="$1"; S=research/usb_cameras/timing/scripts; L="$RUN/analysis_commands.log"
run() { echo "+ $*" >> "$L"; "$@" >> "$RUN/analysis_stdout.log" 2>&1; echo "  exit=$?" >> "$L"; }
[ -f "$RUN/flash_analysis.json" ] || run uv run --script $S/flash_analyze.py --display $RUN/display_m0 --capture $RUN/capture --out $RUN/flash_analysis.json
run uv run --script research/usb_cameras/tools/analyze_frames.py $RUN/capture/*.frames.jsonl --out $RUN/frames_analysis.json
run uv run --script $S/quantization_check.py $RUN/capture/*.frames.jsonl --out $RUN/quantization.json
run uv run --script $S/flash_verify_extra.py --display $RUN/display_m0 --capture $RUN/capture --out $RUN/flash_verify_extra.json
run uv run --script $S/flash_rows.py --display $RUN/display_m0 --capture $RUN/capture --out $RUN/flash_rows.json
run uv run --script $S/flash_exposure_scan.py --display $RUN/display_m0 --capture $RUN/capture --source uvc_pts_mapped_direct --out $RUN/exposure_scan_mapped_direct.json
run uv run --script $S/flash_exposure_scan.py --display $RUN/display_m0 --capture $RUN/capture --source uvc_pts_via_scr_lsq_envelope --out $RUN/exposure_scan_scr_lsq.json
run uv run --script $S/display_model_check.py $RUN --out $RUN/display_model_check.json
run uv run --script research/usb_cameras/results/windows/Gerald/timing/rerun_20261027/tools/capture_conditions.py $RUN/capture --out $RUN/conditions_capture.json
echo done >> "$L"
