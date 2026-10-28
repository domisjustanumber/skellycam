# Revert for win_restart_devices_admin.ps1 (run elevated only if a camera is left stopped/disabled after the test):
#   Start-Process powershell -Verb RunAs -ArgumentList '-ExecutionPolicy Bypass -File <this file> -RunDir <dir>'
# For each id in <RunDir>\ids.txt: pnputil /enable-device, then pnputil /scan-devices. Logs to <RunDir>\revert_log.txt.
# NOTE: if pnputil /restart-device returned 3010 (restart vetoed by a process holding the camera, see
# pnp_veto_events_225.json) the devnode keeps DN_NEED_RESTART (0x100) in DevNodeStatus while the camera keeps
# working. Only a reboot, an unplug/replug or a later non-vetoed restart clears that flag - this script does not.
param([Parameter(Mandatory = $true)][string]$RunDir)
$log = Join-Path $RunDir 'revert_log.txt'
function Log($m) { "$((Get-Date).ToUniversalTime().ToString('o')) $m" | Out-File -FilePath $log -Append -Encoding utf8 }
foreach ($id in (Get-Content (Join-Path $RunDir 'ids.txt') | Where-Object { $_.Trim() -ne '' })) {
    $out = & pnputil.exe /enable-device "$id" 2>&1 | Out-String
    Log "enable-device exit=$LASTEXITCODE $id :: $($out.Trim() -replace "`r?`n", ' | ')"
}
$out = & pnputil.exe /scan-devices 2>&1 | Out-String
Log "scan-devices exit=$LASTEXITCODE :: $($out.Trim() -replace "`r?`n", ' | ')"
'done' | Out-File (Join-Path $RunDir 'revert_done.txt') -Encoding ascii
