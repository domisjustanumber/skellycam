# phase2_windows.ps1 - PHASE 2 runner: user-space UVC streaming of the Logitech C930e on WinUSB.
# Prerequisite: research/usb_cameras/libusb/winusb/run_elevated.ps1 -Action install  (then verify).
# Afterwards:   research/usb_cameras/libusb/winusb/run_elevated.ps1 -Action rollback
#
#   pwsh -File research/usb_cameras/libusb/phase2_windows.ps1 [-Seconds 10] [-Exposure 156] [-WbTemp 4000]
#
# Runs (each camera-touching command separately through tools/camlock.py, each < ~1 min):
#   1. winusb/verify_winusb_c930e.ps1
#   2. libuvc (C): 1280x720@30 MJPEG, default alt, then forced alts 9,7,6,5,4,3 and pyuvc-style
#      --bandwidth-factor 2.0/1.5/1.0; manual exposure/WB; --frame-qpc (USB frame<->QPC samples)
#   3. 1920x1080@30 default alt and --bandwidth-factor 1.5
#   4. pure Python (py-libusb1): default alt and --alt 6
#   5. pyuvc (pupil-labs-uvc 1.0.8): --stream with bandwidth factors 2.0,1.0
# Results: research/usb_cameras/results/windows/<host>/phase2_libusb/<run>/ (result.json, frames.jsonl,
# usb_frame_qpc.jsonl). Then analyse with tools/analyze_frames.py (frames.jsonl) - SCR SOF vs
# usb_frame_qpc.jsonl gives the device-clock -> QPC mapping.
param([int]$Seconds = 10, [int]$Exposure = 156, [int]$WbTemp = 4000)
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = [IO.Path]::GetFullPath((Join-Path $here "..\..\.."))
$exe = Join-Path $here "build\cmake\bin\Release\uvc_capture_test.exe"
$camlock = "research/usb_cameras/tools/camlock.py"
$out = [IO.Path]::GetFullPath((Join-Path $here "..\results\windows\$env:COMPUTERNAME\phase2_libusb"))
New-Item -ItemType Directory -Force $out | Out-Null
$index = [ordered]@{ test = "phase2_libusb_windows"; platform = "windows"; hostname = $env:COMPUTERNAME
  utc_started = (Get-Date).ToUniversalTime().ToString("o"); command = $MyInvocation.Line; runs = [ordered]@{} }
Push-Location $repo
function Cam([string]$name, [string[]]$cmd) {
  $log = Join-Path $out "$name.log"
  & uv run --script $camlock -- @cmd *> $log
  $script:index.runs[$name] = [ordered]@{ command = ($cmd -join " "); exit_code = $LASTEXITCODE; log = $log }
  Write-Host "$name exit=$LASTEXITCODE"
}
pwsh -NoProfile -File (Join-Path $here "winusb\verify_winusb_c930e.ps1") | Out-Null
$ctl = @("--exposure-abs", "$Exposure", "--wb-temp", "$WbTemp", "--frame-qpc")
$base = @($exe, "--vid", "046d", "--pid", "0843", "--seconds", "$Seconds")
Cam "c_720p30_default" ($base + @("--width", "1280", "--height", "720", "--fps", "30", "--save-jpeg", "2", "--out-dir", "$out\c_720p30_default") + $ctl)
foreach ($alt in 9, 7, 6, 5, 4, 3) {
  Cam "c_720p30_alt$alt" ($base + @("--width", "1280", "--height", "720", "--fps", "30", "--alt", "$alt", "--out-dir", "$out\c_720p30_alt$alt") + $ctl)
}
foreach ($bf in "2.0", "1.5", "1.0") {
  Cam "c_720p30_bwf$bf" ($base + @("--width", "1280", "--height", "720", "--fps", "30", "--bandwidth-factor", $bf, "--out-dir", "$out\c_720p30_bwf$bf") + $ctl)
}
Cam "c_1080p30_default" ($base + @("--width", "1920", "--height", "1080", "--fps", "30", "--out-dir", "$out\c_1080p30_default") + $ctl)
Cam "c_1080p30_bwf1.5" ($base + @("--width", "1920", "--height", "1080", "--fps", "30", "--bandwidth-factor", "1.5", "--out-dir", "$out\c_1080p30_bwf1.5") + $ctl)
$py = @("uv", "run", "--script", "research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py", "--vid", "046d", "--pid", "0843", "--seconds", "$Seconds", "--width", "1280", "--height", "720", "--fps", "30", "--exposure-abs", "$Exposure", "--wb-temp", "$WbTemp")
Cam "py_720p30_default" ($py + @("--out-dir", "$out\py_720p30_default"))
Cam "py_720p30_alt6" ($py + @("--alt", "6", "--out-dir", "$out\py_720p30_alt6"))
Cam "pyuvc_720p30" @("uv", "run", "--script", "research/usb_cameras/libusb/pyuvc/pyuvc_probe.py", "--stream", "--vid", "046d", "--pid", "0843", "--seconds", "$Seconds", "--bandwidth-factors", "2.0,1.0", "--manual-exposure", "$Exposure", "--out-dir", "$out\pyuvc_720p30")
Pop-Location
$index.utc_finished = (Get-Date).ToUniversalTime().ToString("o")
$index | ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 (Join-Path $out "index.json")
Write-Host "wrote $out\index.json"
