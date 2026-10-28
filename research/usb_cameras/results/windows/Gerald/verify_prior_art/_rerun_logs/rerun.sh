#!/bin/bash
set -u
R=/c/Users/Dom/GitHub/freemocap/skellycam
G=$R/research/usb_cameras/results/windows/Gerald
V=$G/verify_prior_art
S=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/verify_prior_art
mkdir -p $V $S/backup
cd $R
LOCK="uv run --script research/usb_cameras/tools/camlock.py --"
SDL=C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/downloads/sdl3-3.4.18/x64/SDL3.dll
run_fixed () {  # $1 = fixed result dir name, $2 = verify name, rest = command
  d=$1; v=$2; shift 2
  rm -rf $S/backup/$d; cp -r $G/$d $S/backup/$d
  echo "=== $v: $*" 
  $LOCK "$@" > $S/$v.log 2>&1; echo "exit $?" >> $S/$v.log
  rm -rf $V/$v; mv $G/$d $V/$v; cp -r $S/backup/$d $G/$d
  tail -3 $S/$v.log
}
run_fixed prior_art_gst_capture-mfvideosrc gst_capture-mfvideosrc uv run --script research/usb_cameras/prior_art/gst_probe.py --capture --source mfvideosrc --seconds 6
run_fixed prior_art_gst_capture-ksvideosrc gst_capture-ksvideosrc uv run --script research/usb_cameras/prior_art/gst_probe.py --capture --source ksvideosrc --seconds 6
echo "=== pyav"
$LOCK uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --seconds 6 --tag verify > $S/pyav.log 2>&1; echo "exit $?" >> $S/pyav.log
rm -rf $V/pyav_dshow-verify; mv $G/prior_art_pyav_dshow-verify $V/pyav_dshow-verify; tail -2 $S/pyav.log
echo "=== pyav kiyo 1080p"
$LOCK uv run --script research/usb_cameras/prior_art/pyav_dshow_probe.py --only vid_1532 --width 1920 --height 1080 --seconds 3 --tag verify-kiyo-1080p > $S/pyav1080.log 2>&1; echo "exit $?" >> $S/pyav1080.log
rm -rf $V/pyav_dshow-verify-kiyo-1080p; mv $G/prior_art_pyav_dshow-verify-kiyo-1080p $V/pyav_dshow-verify-kiyo-1080p; tail -2 $S/pyav1080.log
run_fixed prior_art_sdl3_camera sdl3_camera uv run --script research/usb_cameras/prior_art/sdl3_camera_probe.py --lib $SDL
run_fixed prior_art_gst_capture-ksvideosrc gst_capture-ksvideosrc-timeBeginPeriod1 uv run --script research/usb_cameras/verify_prior_art/timer_res_wrapper.py --period-ms 1 -- --capture --source ksvideosrc --seconds 6
run_fixed prior_art_gst_capture-mfvideosrc gst_capture-mfvideosrc-timeBeginPeriod1 uv run --script research/usb_cameras/verify_prior_art/timer_res_wrapper.py --period-ms 1 -- --capture --source mfvideosrc --seconds 6
echo ALLDONE
