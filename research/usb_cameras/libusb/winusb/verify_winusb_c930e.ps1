# verify_winusb_c930e.ps1 - non-admin check after install_winusb_c930e.ps1 (phase 2).
#   pwsh -File research/usb_cameras/libusb/winusb/verify_winusb_c930e.ps1 [-Stream]
# 1. PnP: the C930e parent (or MI_00) reports service WinUSB; lists the children that vanished.
# 2. libusb (C, libusb 1.0.30 build): uvc_capture_test --list must show 046d:0843 open=OK.
# 3. libusb (Python, python-libusb1 3.4.0 / libusb 1.0.29): uvc_libusb1_stream.py --list.
# 4. uvc_capture_test --probe-only (PROBE/COMMIT round trip, no streaming); with -Stream also a 5 s
#    1280x720@30 MJPEG capture with libuvc's default alt and with --alt 6 (944 B/packet).
# Every camera-touching step goes through tools/camlock.py. Writes
# results/windows/<host>/winusb_install/verify_result.json (+ per-step outputs in that folder).
param([switch]$Stream)
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = [IO.Path]::GetFullPath((Join-Path $here "..\..\..\.."))
$outDir = [IO.Path]::GetFullPath((Join-Path $here "..\..\results\windows\$env:COMPUTERNAME\winusb_install"))
New-Item -ItemType Directory -Force $outDir | Out-Null
$exe = Join-Path $here "..\build\cmake\bin\Release\uvc_capture_test.exe"
$camlock = Join-Path $repo "research\usb_cameras\tools\camlock.py"
$res = [ordered]@{ test = "winusb_verify_c930e"; platform = "windows"; hostname = $env:COMPUTERNAME
  utc_started = (Get-Date).ToUniversalTime().ToString("o"); command = $MyInvocation.Line; steps = [ordered]@{} }
$res.pnp = @(Get-PnpDevice | Where-Object { $_.InstanceId -like 'USB\VID_046D&PID_0843*' } | ForEach-Object {
  [ordered]@{ instance_id = $_.InstanceId; present = $_.Present; status = "$($_.Status)"; class = $_.Class
    service = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_Service -ErrorAction SilentlyContinue).Data } })
$res.winusb_bound = [bool]($res.pnp | Where-Object { $_.present -and $_.service -eq "WinUSB" })

function Run($name, [string[]]$cmd) {
  $o = Join-Path $outDir "verify_$name.txt"
  Push-Location $repo
  & uv run --script $camlock -- @cmd *> $o
  $code = $LASTEXITCODE
  Pop-Location
  $script:res.steps[$name] = [ordered]@{ command = ($cmd -join " "); exit_code = $code; output = $o }
  return $code
}
Run "libuvc_list" @($exe, "--list", "--json-out", (Join-Path $outDir "verify_libuvc_list.json")) | Out-Null
Run "py_libusb1_list" @("uv", "run", "--script", "research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py", "--list", "--out-dir", (Join-Path $outDir "verify_py_libusb1_list")) | Out-Null
Run "libuvc_probe_only" @($exe, "--vid", "046d", "--pid", "0843", "--probe-only", "--out-dir", (Join-Path $outDir "verify_probe_only")) | Out-Null
if ($Stream) {
  Run "libuvc_stream_default_alt" @($exe, "--vid", "046d", "--pid", "0843", "--width", "1280", "--height", "720", "--fps", "30", "--seconds", "5", "--save-jpeg", "2", "--out-dir", (Join-Path $outDir "verify_stream_default")) | Out-Null
  Run "libuvc_stream_alt6" @($exe, "--vid", "046d", "--pid", "0843", "--width", "1280", "--height", "720", "--fps", "30", "--seconds", "5", "--alt", "6", "--out-dir", (Join-Path $outDir "verify_stream_alt6")) | Out-Null
}
try {
  $l = Get-Content -Raw (Join-Path $outDir "verify_libuvc_list.json") | ConvertFrom-Json
  $res.c930e_open_result = ($l.devices | Where-Object { $_.vid -eq "046d" -and $_.pid -eq "0843" }).open_result
} catch { $res.c930e_open_result = "list json missing: $_" }
$res.outcome = if ($res.winusb_bound -and $res.c930e_open_result -eq "OK") { "OK: C930e on WinUSB and openable by libusb" } else { "NOT READY" }
$res.utc_finished = (Get-Date).ToUniversalTime().ToString("o")
$res | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $outDir "verify_result.json")
$res | ConvertTo-Json -Depth 6
