# Elevated helper for naming/win_restart_test.py. Do not run directly unless you know why.
#   powershell -ExecutionPolicy Bypass -File win_restart_devices_admin.ps1 -RunDir <dir>
# Reads <RunDir>\ids.txt (one device instance id per line), writes <RunDir>\ready.txt, waits for the
# orchestrator to create <RunDir>\go.txt (it does so only while holding the camera lock), then runs
# `pnputil /restart-device "<id>"` for each id, logging to <RunDir>\admin_log.txt, and finally writes done.txt.
# Changes no configuration: a restart stops and restarts the device's driver stack. Revert (if a device is left
# stopped/disabled): win_restart_revert_admin.ps1 -RunDir <dir>
param([Parameter(Mandatory = $true)][string]$RunDir)
$ErrorActionPreference = 'Continue'
$log = Join-Path $RunDir 'admin_log.txt'
function Log($m) { "$((Get-Date).ToUniversalTime().ToString('o')) $m" | Out-File -FilePath $log -Append -Encoding utf8 }
try {
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Log "elevated=$isAdmin user=$env:USERNAME"
    $ids = Get-Content (Join-Path $RunDir 'ids.txt') | Where-Object { $_.Trim() -ne '' }
    'ready' | Out-File (Join-Path $RunDir 'ready.txt') -Encoding ascii
    $deadline = (Get-Date).AddMinutes(35)
    while (-not (Test-Path (Join-Path $RunDir 'go.txt'))) {
        if ((Get-Date) -gt $deadline) { Log 'timeout waiting for go.txt'; exit 2 }
        Start-Sleep -Milliseconds 250
    }
    foreach ($id in $ids) {
        Log "restart-device BEGIN $id"
        $out = & pnputil.exe /restart-device "$id" 2>&1 | Out-String
        Log "restart-device END exit=$LASTEXITCODE $id :: $($out.Trim() -replace "`r?`n", ' | ')"
    }
}
catch { Log "ERROR $_" }
finally { 'done' | Out-File (Join-Path $RunDir 'done.txt') -Encoding ascii }
