# run_flash_libuvc.ps1 -- phase-2 screen-flash run: C930e via libuvc/WinUSB (UVC PTS/SCR from payload headers,
# USB frame<->QPC samples) and, at the same time, C922 via Media Foundation (mf_uvc_timing.exe), both against ONE
# flash_timecode sequence on monitor 0. Run UNDER camlock:
#   uv run --script research/usb_cameras/tools/camlock.py -- pwsh -NoProfile -File research/usb_cameras/timing/scripts/run_flash_libuvc.ps1 -RunDir <dir> [-Seconds 30] [-PacketsPerTransfer 0] [-NoC922] [-ControlsAfterStart]
# Output: <RunDir>/display_m0 (flash log), <RunDir>/c930e_libuvc (frames.jsonl, usb_frame_qpc.jsonl, result.json,
# frame_<seq>.jpg written AFTER the stream stops), <RunDir>/capture (C922 MF frames.jsonl + .mjpeg), logs.
# Exposure: C930e exposure_abs 78 (x100 us = 7.8 ms, UVC units), C922 2^-7 s = 7.8125 ms; WB 4500 K on both.
param(
  [Parameter(Mandatory)][string]$RunDir,
  [int]$Seconds = 30,
  [int]$PacketsPerTransfer = 0,
  [int]$ExposureAbs = 78,
  [switch]$NoC922,
  [switch]$ControlsAfterStart
)
$ErrorActionPreference = 'Stop'
$here = $PSScriptRoot
$bin = Join-Path $here '..\build'
$uvc = Join-Path $here '..\..\libusb\build\cmake\bin\Release\uvc_capture_test.exe'
New-Item -ItemType Directory -Force $RunDir | Out-Null
$t0 = [DateTime]::UtcNow.ToString('o')
$flash = Start-Process -PassThru -FilePath (Join-Path $bin 'flash_timecode.exe') -ArgumentList @('--out', (Join-Path $RunDir 'display_m0'), '--seconds', ($Seconds + 8), '--monitor', 0, '--seed', 100)
Start-Sleep -Seconds 2
$mf = $null
if (-not $NoC922) {
  $mfArgs = @('--out', (Join-Path $RunDir 'capture'), '--seconds', ($Seconds + 2), '--save-mjpeg', '--cam', 'vid_046d&pid_085c,1280,720,30,-7,4500')
  $mf = Start-Process -PassThru -FilePath (Join-Path $bin 'mf_uvc_timing.exe') -ArgumentList $mfArgs `
        -RedirectStandardOutput (Join-Path $RunDir 'mf_c922.stdout.log') -RedirectStandardError (Join-Path $RunDir 'mf_c922.stderr.log')
}
$uArgs = @('--vid', '046d', '--pid', '0843', '--width', '1280', '--height', '720', '--fps', '30', '--seconds', $Seconds,
           '--exposure-abs', $ExposureAbs, '--wb-temp', '4500', '--frame-qpc', '--save-jpeg', '5000', '--save-jpeg-deferred',
           '--out-dir', (Join-Path $RunDir 'c930e_libuvc'))
if ($ControlsAfterStart) { $uArgs += '--controls-after-start' }
if ($PacketsPerTransfer -gt 0) { $uArgs += @('--packets-per-transfer', $PacketsPerTransfer) }
& $uvc @uArgs 2>&1 | Tee-Object (Join-Path $RunDir 'c930e_libuvc.log')
$uvcExit = $LASTEXITCODE
if ($mf) { $mf | Wait-Process -Timeout 60 -ErrorAction SilentlyContinue }
$flash | Wait-Process -Timeout 60 -ErrorAction SilentlyContinue
@{ utc_started = $t0; utc_finished = [DateTime]::UtcNow.ToString('o'); seconds = $Seconds; packets_per_transfer = $PacketsPerTransfer;
   exposure_abs_c930e = $ExposureAbs; c922 = (-not $NoC922); uvc_exit = $uvcExit; mf_exit = $(if ($mf) { $mf.ExitCode } else { $null });
   uvc_args = ($uArgs -join ' ') } | ConvertTo-Json | Set-Content (Join-Path $RunDir 'run.json')
"done uvc_exit=$uvcExit"
