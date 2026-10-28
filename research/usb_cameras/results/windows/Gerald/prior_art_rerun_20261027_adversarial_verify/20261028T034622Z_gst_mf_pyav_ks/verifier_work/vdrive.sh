#!/bin/bash
# Driver for the 20261027 prior-art rerun. Usage: drive.sh <step>...
set -u
R=/c/Users/Dom/GitHub/freemocap/skellycam
cd $R
export USBCAM_RESULTS_DIR=research/usb_cameras/results/windows/Gerald/prior_art_rerun_20261027_adversarial_verify/${VSTAMP}
L=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/7c9d3345-0e7f-4af6-bb14-20fd851edd1a/scratchpad/verifier_pa/logs; mkdir -p $L
LOCK="uv run --script research/usb_cameras/tools/camlock.py --timeout-s 600 --"
SDL=C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/downloads/sdl3-3.4.18/x64/SDL3.dll
OPNP=C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/downloads/openpnp-capture-v0.0.30/libopenpnp-capture-windows-latest-x86_64.dll
MF_C922='\\?\usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000#{e5323777-f976-4f5b-9b55-b94699c46e44}\global'
MF_C930='\\?\usb#vid_046d&pid_0843&mi_00#8&39dec205&1&0000#{e5323777-f976-4f5b-9b55-b94699c46e44}\global'
MF_GEN='\\?\usb#vid_4c4a&pid_4a55&mi_00#8&35e81179&0&0000#{e5323777-f976-4f5b-9b55-b94699c46e44}\global'
DS_C922='@device_pnp_\\?\usb#vid_046d&pid_085c&mi_00#8&268da596&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global'
DS_C930='@device_pnp_\\?\usb#vid_046d&pid_0843&mi_00#8&39dec205&1&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global'
DS_GEN='@device_pnp_\\?\usb#vid_4c4a&pid_4a55&mi_00#8&35e81179&0&0000#{65e8773d-8f56-11d0-a3b9-00a0c9223196}\global'
MFARGS=(--device-path "$MF_C922" --device-path "$MF_C930" --device-path "$MF_GEN")
KSARGS=(--device-name "c922 Pro Stream Webcam" --device-name "Logitech Webcam C930e" --device-name "USB Camera")
DSARGS=(--device "$DS_C922" --device "$DS_C930" --device "$DS_GEN")

cpu () { powershell.exe -NoProfile -Command "(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average" | tr -d '\r'; }
devnode () {
  powershell.exe -NoProfile -Command "foreach (\$i in @('USB\VID_046D&PID_085C&MI_00\8&268DA596&0&0000','USB\VID_046D&PID_0843&MI_00\8&39DEC205&1&0000','USB\VID_4C4A&PID_4A55&MI_00\8&35E81179&0&0000','USB\VID_1532&PID_0E05&MI_00\A&34494D13&0&0000')) { \$s=(Get-PnpDeviceProperty -InstanceId \$i -KeyName DEVPKEY_Device_DevNodeStatus).Data; '{0} 0x{1:X} need_restart={2}' -f \$i,\$s,[bool](\$s -band 0x100) }" | tr -d '\r'
}
run () {  # $1 = step name, $2 = timeout s, rest = command
  local name=$1 to=$2; shift 2
  local log=$L/$name.log
  { echo "### step=$name utc_start=$(date -u +%Y-%m-%dT%H:%M:%SZ) cpu_load_pct_start=$(cpu)"; echo "### cmd: $*"; } > $log
  timeout -k 10 $to $LOCK "$@" >> $log 2>&1; local rc=$?
  { echo "### exit=$rc utc_end=$(date -u +%Y-%m-%dT%H:%M:%SZ) cpu_load_pct_end=$(cpu)"; devnode; } >> $log
  echo "$name exit=$rc"; grep -E "camlock|###|Error|error|Traceback" $log | head -20
}

for step in "$@"; do case $step in
  gst_mf) run gst_mf 900 uv run --script research/usb_cameras/prior_art/gst_probe.py --capture --source mfvideosrc --seconds 6 "${MFARGS[@]}" ;;
  gst_ks) run gst_ks 900 uv run --script research/usb_cameras/prior_art/gst_probe.py --capture --source ksvideosrc --seconds 6 "${KSARGS[@]}" ;;
  pyav) run pyav 900 uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --seconds 6 "${DSARGS[@]}" ;;
  pyav_wall) run pyav_wall 900 uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --seconds 6 --wallclock "${DSARGS[@]}" ;;
  pyav_listopts) run pyav_listopts 900 uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --list-options --tag listopts "${DSARGS[@]}" ;;
  pygrabber) run pygrabber 900 uv run --script research/usb_cameras/prior_art/pygrabber_probe.py --name "c922 Pro Stream Webcam" --name "Logitech Webcam C930e" --name "USB Camera" ;;
  ks_tbp) run ks_tbp 900 uv run --script research/usb_cameras/verify_prior_art/timer_res_wrapper.py --period-ms 1 -- --capture --source ksvideosrc --seconds 6 "${KSARGS[@]}" ;;
  mf_tbp) run mf_tbp 900 uv run --script research/usb_cameras/verify_prior_art/timer_res_wrapper.py --period-ms 1 -- --capture --source mfvideosrc --seconds 6 "${MFARGS[@]}" ;;
  expo) run expo_$(date -u +%H%M%S) 300 uv run --script research/usb_cameras/tools/dshow_exposure_read.py --vidpid "vid_046d&pid_085c" --vidpid "vid_046d&pid_0843" --vidpid "vid_4c4a&pid_4a55" --label "after_${EXPO_LABEL:-x}" --out $USBCAM_RESULTS_DIR/conditions/exposure_$(date -u +%H%M%S).json ;;
  *) echo "unknown step $step" ;;
esac; done
