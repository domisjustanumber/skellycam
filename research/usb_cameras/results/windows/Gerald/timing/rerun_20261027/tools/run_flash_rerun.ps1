# run_flash_rerun.ps1 -- 20261027 overnight re-run wrapper around timing/scripts/run_flash_test.ps1. Run UNDER camlock:
#   uv run --script research/usb_cameras/tools/camlock.py -- pwsh -NoProfile -File <this> -RunDir <dir> -Cams "spec1;spec2" [-Seconds 30] [-Monitor 0]
# -Cams is ONE string with ';' between mf_uvc_timing --cam specs (pwsh -File cannot pass string[]; see flash_verify_tools/NOTES.txt).
# Adds, around the unchanged run_flash_test.ps1:
#   * machine CPU% (Win32_Processor LoadPercentage + \Processor(_Total)\% Processor Time) at start and end -> conditions.json
#   * window_cover_check.py in the background: which top-level window owns 25 grid points of the flash monitor every 0.5 s
#     (the flash run is only valid if flash_timecode.exe owns every point while the camera captures) -> cover.json
param(
  [Parameter(Mandatory)][string]$RunDir,
  [Parameter(Mandatory)][string]$Cams,
  [int]$Seconds = 30,
  [int]$Monitor = 0
)
$ErrorActionPreference = 'Stop'
$repo = 'C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras'
New-Item -ItemType Directory -Force $RunDir | Out-Null
function Cpu { $l = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
  $c = (Get-Counter '\Processor(_Total)\% Processor Time' -SampleInterval 1 -MaxSamples 2).CounterSamples | Measure-Object -Property CookedValue -Average
  [ordered]@{ utc = (Get-Date).ToUniversalTime().ToString('o'); win32_load_pct = $l; counter_total_pct_2s = [math]::Round($c.Average, 1) } }
$cond = [ordered]@{ test = 'flash_rerun_20261027'; hostname = $env:COMPUTERNAME; run_dir = $RunDir; cams = $Cams; seconds = $Seconds; monitor = $Monitor
  cpu_start = (Cpu); logituneagent_pids = @(Get-Process LogiTuneAgent -ErrorAction SilentlyContinue | ForEach-Object Id)
  razerappengine_pids = @(Get-Process RazerAppEngine -ErrorAction SilentlyContinue | ForEach-Object Id) }
$mons = & (Join-Path $repo 'timing\build\flash_timecode.exe') --list | ConvertFrom-Json
$m = $mons | Where-Object { $_.monitor -eq $Monitor }
$rect = ($m.rect -join ',')
$cover = Start-Process -PassThru -WindowStyle Hidden -FilePath uv -ArgumentList @('run', '--script', (Join-Path $repo 'results\windows\Gerald\timing\rerun_20261027\tools\window_cover_check.py'), '--rect', $rect, '--seconds', ($Seconds + 9), '--out', (Join-Path $RunDir 'cover.json')) -RedirectStandardOutput (Join-Path $RunDir 'cover.stdout.txt') -RedirectStandardError (Join-Path $RunDir 'cover.stderr.txt')
$camArr = $Cams.Split(';') | Where-Object { $_ }
& (Join-Path $repo 'timing\scripts\run_flash_test.ps1') -RunDir $RunDir -Seconds $Seconds -Monitors @($Monitor) -Cams $camArr
$cover | Wait-Process -Timeout 60 -ErrorAction SilentlyContinue
if (-not $cover.HasExited) { Stop-Process -Id $cover.Id -Force }
$cond.cpu_end = (Cpu)
$cond | ConvertTo-Json -Depth 5 | Set-Content (Join-Path $RunDir 'conditions.json')
"wrapper done"
