date -Is
C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/mjpeg/build/mf_mjpeg_capture.exe --list > /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/mf_recheck_list.json; echo list_rc=$?
for d in "vid_046d&pid_085c" "vid_1532&pid_0e05" "vid_046d&pid_0843"; do
  rm -rf /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/mf_recheck_${d//&/_}; C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/mjpeg/build/mf_mjpeg_capture.exe --dev "$d" --width 1280 --height 720 --fps 30 --seconds 3 --warmup 1 --out /c/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/96d4d83a-4013-4e95-a9bd-1cfedc6522c8/scratchpad/mf_recheck_${d//&/_} 2>&1 | grep -v VCAMDS | tail -5; echo "cap $d rc=${PIPESTATUS[0]}"
done
date -Is
