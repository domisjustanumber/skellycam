# verify_winusb.ps1 - NON-admin check of one or more cameras after install_winusb.ps1 (or after rollback with -Mf).
# Camera-agnostic successor of verify_winusb_c930e.ps1 (unchanged).
#   pwsh -File research/usb_cameras/libusb/winusb/verify_winusb.ps1 -Device 046D:085C,4C4A:4A55 [-Stream] [-Mf] [-OutDir DIR]
# Per device (VID:PID):
#   1. PnP: the present parent of that VID/PID, its service/INF, and which MI_xx children are present
#      (after a WinUSB parent install + replug the children are gone; after rollback they are back);
#   2. libuvc (libusb 1.0.30): uvc_capture_test --list -> open_result for that VID/PID (once for all devices);
#   3. python-libusb1 (libusb 1.0.29): uvc_libusb1_stream.py --list -> "open" for that VID/PID (once);
#   4. Rust uvc_iso (libusb 1.0.27): uvc_iso list --backend libusb (once; enumerates + reads descriptors);
#   5. uvc_capture_test --probe-only at 1280x720@30 (PROBE/COMMIT round trip, no streaming);
#   6. -Stream: 5 s 1280x720@30 MJPEG at libuvc's default alt;
#   7. -Mf: Media Foundation (bandwidth/build/mf_multi_open.exe) 5 s MJPG 1280x720@30 - use after ROLLBACK + replug
#      (the C930e did not deliver MF frames after rollback until it was replugged).
# Every camera-opening command goes through tools/camlock.py. Writes <OutDir>/verify_result.json (+ per-step
# logs). Default OutDir: results/windows/<host>/winusb_multi/verify_<utc stamp>.
# Exit code 0 when every device is on WinUSB and openable by libuvc (or, with -Mf alone, streams through MF).
param(
  [Parameter(Mandatory)][string[]]$Device,
  [switch]$Stream,
  [switch]$Mf,
  [switch]$SkipLibusb,
  [string]$OutDir,
  [int]$LockTimeoutS = 1800
)
$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "winusb_common.ps1")
$repo = [IO.Path]::GetFullPath((Join-Path $here "..\..\..\.."))
$stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
if (-not $OutDir) { $OutDir = Join-Path (Get-WinUsbResultsDir $here) "verify_$stamp" }
$OutDir = [IO.Path]::GetFullPath($OutDir)
New-Item -ItemType Directory -Force $OutDir | Out-Null
$exe = [IO.Path]::GetFullPath((Join-Path $here "..\build\cmake\bin\Release\uvc_capture_test.exe"))
$rust = [IO.Path]::GetFullPath((Join-Path $here "..\..\rust\build\release\uvc_iso.exe"))
$mfExe = [IO.Path]::GetFullPath((Join-Path $here "..\..\bandwidth\build\mf_multi_open.exe"))
$camlock = "research/usb_cameras/tools/camlock.py"
$specs = Split-DeviceSpecs $Device
$res = [ordered]@{ test = "winusb_verify"; platform = "windows"; hostname = $env:COMPUTERNAME
  utc_started = (Get-Date).ToUniversalTime().ToString("o")
  command = "verify_winusb.ps1 -Device $($specs -join ',')$(if ($Stream) { ' -Stream' })$(if ($Mf) { ' -Mf' })$(if ($SkipLibusb) { ' -SkipLibusb' })"
  out_dir = $OutDir; steps = [ordered]@{}; devices = @() }

function Run([string]$name, [string[]]$cmd) {
  $o = Join-Path $OutDir "$name.log"
  Push-Location $repo
  & uv run --script $camlock --timeout-s $LockTimeoutS -- @cmd *> $o
  $code = $LASTEXITCODE
  Pop-Location
  $script:res.steps[$name] = [ordered]@{ command = ($cmd -join " "); exit_code = $code; log = $o }
  Write-Host "$name exit=$code"
  return $code
}
function TryJson([string]$p) { try { return (Get-Content -Raw $p | ConvertFrom-Json) } catch { return $null } }

$devs = @()
foreach ($s in $specs) {
  $d = [ordered]@{ spec = $s; vid = $null; pid = $null }
  if ($s -match '^([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})$') { $d.vid = $Matches[1].ToLower(); $d.pid = $Matches[2].ToLower() }
  elseif ((Get-VidPidOf $s)) { $vp = (Get-VidPidOf $s).ToLower().Split(":"); $d.vid = $vp[0]; $d.pid = $vp[1] }
  try {
    $parent = Resolve-ParentInstance $s
    $fam = Get-Family $parent
    $d.parent_instance_id = $parent
    $d.pnp = $fam
    $p = $fam | Where-Object { $_.function -eq "parent" } | Select-Object -First 1
    $d.parent_service = $p.service; $d.parent_inf = $p.inf; $d.parent_class = $p.class
    $d.winusb_bound = [bool]($p.present -and (Test-ServiceEq $p.service "WinUSB"))
    $d.children_present = @($fam | Where-Object { $_.function -ne "parent" -and $_.present } | ForEach-Object { "$($_.function)=$($_.service)" })
  } catch { $d.pnp_error = "$($_.Exception.Message)"; $d.winusb_bound = $false }
  $devs += $d
}

if (-not $SkipLibusb) {
  Run "libuvc_list" @($exe, "--list", "--json-out", (Join-Path $OutDir "libuvc_list.json")) | Out-Null
  Run "py_libusb1_list" @("uv", "run", "--script", "research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py", "--list", "--out-dir", (Join-Path $OutDir "py_libusb1_list")) | Out-Null
  Run "rust_uvc_iso_list_libusb" @($rust, "list", "--backend", "libusb", "--out", (Join-Path $OutDir "rust_list_libusb")) | Out-Null
  $l = TryJson (Join-Path $OutDir "libuvc_list.json")
  $py = TryJson (Join-Path $OutDir "py_libusb1_list\result.json")
  $rs = TryJson (Join-Path $OutDir "rust_list_libusb\summary.json")
  foreach ($d in $devs) {
    $tag = "$($d.vid)_$($d.pid)"
    $d.libuvc_open_result = if ($l) { "$(($l.devices | Where-Object { $_.vid -eq $d.vid -and $_.pid -eq $d.pid } | Select-Object -First 1).open_result)" } else { "libuvc list json missing" }
    $d.py_libusb1_open = if ($py) { "$(($py.cameras | Where-Object { $_.vid -eq $d.vid -and $_.pid -eq $d.pid } | Select-Object -First 1).open)" } else { "py list json missing" }
    $d.rust_list_libusb_seen = if ($rs) { [bool]($rs.uvc_devices | Where-Object { $_.vid -eq $d.vid -and $_.pid -eq $d.pid }) } else { $null }
    $po = Join-Path $OutDir "probe_only_$tag"
    Run "libuvc_probe_only_$tag" @($exe, "--vid", $d.vid, "--pid", $d.pid, "--width", "1280", "--height", "720", "--fps", "30", "--probe-only", "--out-dir", $po) | Out-Null
    $pr = TryJson (Join-Path $po "result.json")
    $d.probe_commit_dwMaxPayloadTransferSize = if ($pr) { $pr.negotiation.commit.dwMaxPayloadTransferSize } else { $null }
    if ($Stream) {
      $so = Join-Path $OutDir "stream_default_$tag"
      Run "libuvc_stream_default_$tag" @($exe, "--vid", $d.vid, "--pid", $d.pid, "--width", "1280", "--height", "720", "--fps", "30", "--seconds", "5", "--out-dir", $so) | Out-Null
      $sr = TryJson (Join-Path $so "result.json")
      if ($sr) { $d.stream = [ordered]@{ chosen_alt = $sr.iso.chosen_altsetting; frames = $sr.measurements.frames; fps = $sr.measurements.fps_from_arrivals; jpeg_soi_eoi_ok = $sr.measurements.jpeg_soi_eoi_ok } }
    }
  }
}
if ($Mf) {
  foreach ($d in $devs) {
    $tag = "$($d.vid)_$($d.pid)"
    $mo = Join-Path $OutDir "mf_$tag.json"
    Run "mf_stream_$tag" @($mfExe, "--cam", "vid_$($d.vid)&pid_$($d.pid):MJPG:1280x720@30", "--seconds", "5", "--out", $mo) | Out-Null
    $m = TryJson $mo
    $c = if ($m) { $m.cameras | Select-Object -First 1 } else { $null }
    $d.mf = if ($c) { [ordered]@{ streamed = $c.streamed; samples = $c.samples; steady_fps = $c.steady_fps; failed_stage = $c.failed_stage; error_hr = $c.error_hr } } else { "mf json missing" }
  }
}
$res.devices = $devs
$okLib = -not ($devs | Where-Object { -not $_.winusb_bound -or $_.libuvc_open_result -ne "OK" })
$okMf = -not ($devs | Where-Object { -not ($_.mf -is [System.Collections.IDictionary]) -or -not $_.mf.streamed })
$res.outcome = if (-not $SkipLibusb -and $okLib) { "OK: all $($devs.Count) device(s) on WinUSB and openable by libuvc" }
  elseif ($SkipLibusb -and $Mf -and $okMf) { "OK: all $($devs.Count) device(s) stream through Media Foundation" }
  else { "NOT READY: " + (@($devs | ForEach-Object { "$($_.spec) winusb=$($_.winusb_bound) libuvc=$($_.libuvc_open_result) py=$($_.py_libusb1_open)$(if ($Mf) { ' mf=' + $(if ($_.mf -is [System.Collections.IDictionary]) { $_.mf.streamed } else { $_.mf }) })" }) -join "; ") }
$res.utc_finished = (Get-Date).ToUniversalTime().ToString("o")
$res | ConvertTo-Json -Depth 8 | Set-Content -Encoding utf8 (Join-Path $OutDir "verify_result.json")
Write-Host $res.outcome
Write-Host "wrote $(Join-Path $OutDir 'verify_result.json')"
if ($res.outcome -like "OK*") { exit 0 } else { exit 1 }
