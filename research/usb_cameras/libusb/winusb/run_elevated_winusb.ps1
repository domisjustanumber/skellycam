# run_elevated_winusb.ps1 - launch install_winusb.ps1 / rollback_winusb.ps1 elevated for SEVERAL cameras with ONE UAC
# prompt, wait for the log, print the result JSON. Camera-agnostic successor of run_elevated.ps1 (unchanged).
#   pwsh -File research/usb_cameras/libusb/winusb/run_elevated_winusb.ps1 -Action install  -Device 046D:085C,4C4A:4A55 [-Target Parent|MI_00]
#   pwsh -File research/usb_cameras/libusb/winusb/run_elevated_winusb.ps1 -Action rollback -Device 046D:085C,4C4A:4A55
#   pwsh -File research/usb_cameras/libusb/winusb/run_elevated_winusb.ps1 -Action install  -Device 046D:085C,4C4A:4A55 -DryRun
#     (-DryRun runs the installer's dry run NON-elevated in this shell: no UAC prompt, nothing changed)
# -Device: VID:PID or instance ids, comma separated (quote instance ids: they contain '&').
# Polls up to -TimeoutS seconds for results/windows/<host>/winusb_multi/<action>.done. Exit 0 if the elevated
# script reported OK (or dry-run OK).
param(
  [Parameter(Mandatory)][ValidateSet("install", "rollback")][string]$Action,
  [string[]]$Device,
  [ValidateSet("Parent", "MI_00")][string]$Target = "Parent",
  [switch]$DryRun,
  [int]$TimeoutS = 300
)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
. (Join-Path $here "winusb_common.ps1")
$outDir = Get-WinUsbResultsDir $here
$specs = if ($Device) { Split-DeviceSpecs $Device } else { @() }
if ($Action -eq "install" -and -not $specs) { Write-Error "-Device is required for install"; exit 2 }
$script = Join-Path $here ($(if ($Action -eq "install") { "install_winusb.ps1" } else { "rollback_winusb.ps1" }))
$pwsh = (Get-Command pwsh).Source
if ($DryRun) {
  if ($Action -ne "install") { Write-Error "-DryRun applies to install only"; exit 2 }
  & $pwsh -NoProfile -ExecutionPolicy Bypass -File $script -Device ($specs -join ",") -Target $Target -DryRun | Out-Host
  $json = Join-Path $outDir "install_dryrun_result.json"
} else {
  $done = Join-Path $outDir "$Action.done"
  Remove-Item $done -ErrorAction SilentlyContinue
  $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$script`"")
  if ($specs) { $argList += @("-Device", "`"$($specs -join ',')`"") }
  if ($Action -eq "install") { $argList += @("-Target", $Target) }
  Start-Process -FilePath $pwsh -Verb RunAs -ArgumentList ($argList -join " ") -WindowStyle Hidden
  $t0 = Get-Date
  while (-not (Test-Path $done)) {
    if (((Get-Date) - $t0).TotalSeconds -gt $TimeoutS) { Write-Error "timed out waiting for $done (UAC declined?)"; exit 2 }
    Start-Sleep -Seconds 2
  }
  $json = Join-Path $outDir ($(if ($Action -eq "install") { "install_result.json" } else { "rollback_result.json" }))
}
Get-Content -Raw $json
$r = Get-Content -Raw $json | ConvertFrom-Json
if ("$($r.outcome)" -like "OK*" -or "$($r.outcome)" -like "dry-run*") { exit 0 } else { exit 1 }
