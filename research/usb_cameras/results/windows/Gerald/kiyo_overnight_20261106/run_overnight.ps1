# Driver for the Kiyo overnight test (docs/kiyo_overnight_handoff.md).
# Step 1: 300 min control-poll window. Step 2: one MF stream start, whatever step 1 showed.
$ErrorActionPreference = 'Continue'
Set-Location 'C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras'
$out = 'results/windows/Gerald/kiyo_overnight_20261106'
$log = "$out/driver.log"
function Log($m) { "$((Get-Date).ToUniversalTime().ToString('o')) $m" | Tee-Object -FilePath $log -Append }

Log "driver start; Kiyo LastArrivalDate=$((Get-PnpDeviceProperty -InstanceId 'USB\VID_1532&PID_0E05&MI_00\A&34494D13&0&0000' -KeyName DEVPKEY_Device_LastArrivalDate).Data)"
Log "step 1: poll window"
uv run --script suite/windows/run_suite.py --only W-KIYO --kiyo-foreground --kiyo-minutes 300 --camera 0e05 --out-dir $out *>> "$out/run_suite.log"
Log "step 1 exit=$LASTEXITCODE"

Log "step 2: final MF stream start"
$wincam = (Resolve-Path suite/windows/native/build/wincam.exe).Path
uv run --script tools/camlock.py --timeout-s 60 -- $wincam capture --api mf --device vid_1532 --width 1280 --height 720 --fps 30 --frames 90 --timeout-ms 10000 --out-dir "$out/final_stream" *>> "$out/final_stream.log"
Log "step 2 exit=$LASTEXITCODE"

Get-PnpDeviceProperty -InstanceId 'USB\VID_1532&PID_0E05&MI_00\*' -KeyName DEVPKEY_Device_ProblemCode,DEVPKEY_Device_LastArrivalDate |
  Format-Table InstanceId,KeyName,Data -AutoSize | Out-String | Out-File "$out/device_state_after.txt"
Log "driver done"
