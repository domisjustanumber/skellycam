date -Is
d="vid_1532&pid_0e05"
for m in "1280 720 30" "1280 720 60" "1920 1080 30" "640 480 30"; do set -- $m
  o=/c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/kiyo_recheck_$1x$2at$3; rm -rf $o; C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/mjpeg/build/mf_mjpeg_capture.exe --dev "$d" --width $1 --height $2 --fps $3 --seconds 3 --warmup 1 --out $o 2>&1 | grep -v VCAMDS | tail -2; echo "mode $m rc=${PIPESTATUS[0]}"
done
C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/mjpeg/build/mf_mjpeg_capture.exe --dev "$d" --subtype YUY2 --width 1280 --height 720 --fps 10 --seconds 2 --warmup 1 --out /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/kiyo_recheck_yuy2 2>&1 | grep -v VCAMDS | tail -2
C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/mjpeg/build/mf_mjpeg_capture.exe --dev "$d" --via-dshow --width 1280 --height 720 --fps 30 --seconds 2 --warmup 1 --out /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/kiyo_recheck_viadshow 2>&1 | grep -v VCAMDS | tail -2
date -Is
