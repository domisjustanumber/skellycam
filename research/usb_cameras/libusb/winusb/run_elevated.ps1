# run_elevated.ps1 - launch install / rollback elevated (UAC prompt for the user), wait for the log.
#   pwsh -File research/usb_cameras/libusb/winusb/run_elevated.ps1 -Action install [-Target Parent|MI_00] [-DryRun]
#   pwsh -File research/usb_cameras/libusb/winusb/run_elevated.ps1 -Action rollback
# Polls up to -TimeoutS seconds for results/windows/<host>/winusb_install/<action>.done, then prints
# the result JSON. Exit 0 if the elevated script reported OK.
param(
  [Parameter(Mandatory)][ValidateSet("install", "rollback")][string]$Action,
  [ValidateSet("Parent", "MI_00")][string]$Target = "Parent",
  [switch]$DryRun,
  [int]$TimeoutS = 300
)
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = [IO.Path]::GetFullPath((Join-Path $here "..\..\results\windows\$env:COMPUTERNAME\winusb_install"))
New-Item -ItemType Directory -Force $outDir | Out-Null
$done = Join-Path $outDir "$Action.done"
Remove-Item $done -ErrorAction SilentlyContinue
$script = Join-Path $here ($(if ($Action -eq "install") { "install_winusb_c930e.ps1" } else { "rollback_winusb_c930e.ps1" }))
$argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$script`"")
if ($Action -eq "install") { $argList += @("-Target", $Target); if ($DryRun) { $argList += "-DryRun" } }
$pwsh = (Get-Command pwsh).Source
Start-Process -FilePath $pwsh -Verb RunAs -ArgumentList $argList -WindowStyle Hidden
$t0 = Get-Date
while (-not (Test-Path $done)) {
  if (((Get-Date) - $t0).TotalSeconds -gt $TimeoutS) { Write-Error "timed out waiting for $done (UAC declined?)"; exit 2 }
  Start-Sleep -Seconds 2
}
$json = Join-Path $outDir ($(if ($Action -eq "install") { if ($DryRun) { "install_dryrun_result.json" } else { "install_result.json" } } else { "rollback_result.json" }))
Get-Content -Raw $json
$r = Get-Content -Raw $json | ConvertFrom-Json
if ("$($r.outcome)" -like "OK*" -or "$($r.outcome)" -like "dry-run*") { exit 0 } else { exit 1 }
