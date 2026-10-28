# run_flash_test.ps1 -- Windows screen-flash ground-truth run (run UNDER camlock):
#   uv run --script research/usb_cameras/tools/camlock.py -- pwsh -NoProfile -File research/usb_cameras/timing/scripts/run_flash_test.ps1 -RunDir <dir>
# Shows an independent flash sequence full-screen on EVERY monitor (seed = 100 + monitor index, so the analysis can tell
# which monitor each camera sees), captures MJPEG + all timestamps from the cameras with manual exposure/WB, then exits.
# Analyse with: uv run --script research/usb_cameras/timing/scripts/flash_analyze.py --display <RunDir>\display_m0 --display <RunDir>\display_m1 --capture <RunDir>\capture --out ...
param(
  [Parameter(Mandatory)][string]$RunDir,
  [int]$Seconds = 30,
  [int[]]$Monitors = @(),   # empty = every monitor
  [string[]]$Cams = @('vid_046d&pid_085c,1280,720,30,-7,4500', 'vid_046d&pid_0843,1280,720,30,-7,4500', 'vid_1532&pid_0e05,1280,720,30,-7,4500')
)
$ErrorActionPreference = 'Stop'
$bin = Join-Path $PSScriptRoot '..\build'
New-Item -ItemType Directory -Force $RunDir | Out-Null
$mons = & (Join-Path $bin 'flash_timecode.exe') --list | ConvertFrom-Json
$mons | ConvertTo-Json | Set-Content (Join-Path $RunDir 'monitors.json')
$flash = @()
foreach ($m in $mons) {
  if ($Monitors.Count -and -not ($Monitors -contains [int]$m.monitor)) { continue }
  $d = Join-Path $RunDir ("display_m{0}" -f $m.monitor)
  $flash += Start-Process -PassThru -FilePath (Join-Path $bin 'flash_timecode.exe') -ArgumentList @('--out', $d, '--seconds', ($Seconds + 6), '--monitor', $m.monitor, '--seed', (100 + $m.monitor))
}
Start-Sleep -Seconds 2
$capArgs = @('--out', (Join-Path $RunDir 'capture'), '--seconds', $Seconds, '--save-mjpeg')
foreach ($c in $Cams) { $capArgs += @('--cam', $c) }
& (Join-Path $bin 'mf_uvc_timing.exe') @capArgs 2>&1 | Tee-Object (Join-Path $RunDir 'capture.log')
$flash | Wait-Process -Timeout 60 -ErrorAction SilentlyContinue
"done"
