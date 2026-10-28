#!/bin/bash
# analyze_full.sh RUN_DIR  (C922 + C930e or C922 + generic run): analyze_run.sh + fixed ROI + step/impulse + wide scan + verify_method + compact table
cd /c/Users/Dom/GitHub/freemocap/skellycam
D="$1"; S=research/usb_cameras/timing/scripts; RT=research/usb_cameras/results/windows/Gerald/timing/rerun_20261027
/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/tools/analyze_run.sh "$D"
uv run --script $S/flash_roi_rows.py --display $D/display_m0 --capture $D/capture --cam 085c --col-frac 0.75 --source uvc_pts_mapped_direct --out $D/roi_rows_c922_mapped_direct.json > $D/roi_rows_c922.log 2>&1
uv run --script $S/flash_step_response.py $D 0.75 0.5 --cam c922 --out $D/step_response.json >/dev/null 2>>$D/step.err
uv run --script $S/flash_impulse_response.py $D 0.75 0.5 --cam c922 --out $D/impulse_response.json >/dev/null 2>>$D/impulse.err
if ls $D/capture/*0843*.frames.jsonl >/dev/null 2>&1; then
  uv run --script $S/flash_roi_rows.py --display $D/display_m0 --capture $D/capture --cam 0843 --col-frac 0.45 --source uvc_pts_via_scr_lsq_envelope --out $D/roi_rows_c930e_scr_lsq.json > $D/roi_rows_c930e.log 2>&1
  uv run --script $S/flash_step_response.py $D 0.45 0.5 --cam c930e_mf --mf-glob '*0843*' --out $D/step_response.json >/dev/null 2>>$D/step.err
  uv run --script $S/flash_impulse_response.py $D 0.45 0.5 --cam c930e_mf --mf-glob '*0843*' --out $D/impulse_response.json >/dev/null 2>>$D/impulse.err
  uv run --script $S/flash_exposure_scan.py --display $D/display_m0 --capture $D/capture --source uvc_pts_via_scr_lsq_envelope --grid-ms 2,4,6,7.8125,10,12,14,17,20,24,28,32,36,40,45 --out $RT/exposure_scan_wide/$(basename $D).json >/dev/null 2>&1
  uv run --script $S/flash_verify_method.py --display $D/display_m0 --capture $D/capture --out $D/verify_method.json > $D/verify_method.log 2>&1
  uv run --script $RT/tools/mf_fixed_gt.py $D --glob '*0843*' --col 0.45 --rows 0.5 --out $D/mf_fixed_gt_c930e.json > $D/mf_fixed_gt.log 2>&1
fi
if ls $D/capture/*4a55*.frames.jsonl >/dev/null 2>&1; then
  uv run --script $RT/tools/mf_fixed_gt.py $D --glob '*4a55*' --col 0.456 --rows 0.45,0.572,0.7 --out $D/mf_fixed_gt_generic.json > $D/mf_fixed_gt.log 2>&1
  uv run --script $S/flash_step_response.py $D 0.456 0.572 --cam generic_mf --mf-glob '*4a55*' --out $D/step_response.json >/dev/null 2>>$D/step.err
  uv run --script $S/flash_impulse_response.py $D 0.456 0.572 --cam generic_mf --mf-glob '*4a55*' --out $D/impulse_response.json >/dev/null 2>>$D/impulse.err
fi
uv run --script $RT/tools/mf_fixed_gt.py $D --glob '*085c*' --col 0.75 --rows 0.5 --out $D/mf_fixed_gt_c922.json >> $D/mf_fixed_gt.log 2>&1
uv run --script $RT/tools/luma_timeline.py $D/capture --out $D/luma_timeline.json > /dev/null 2>&1
uv run --script $RT/tools/compact_table.py $D
