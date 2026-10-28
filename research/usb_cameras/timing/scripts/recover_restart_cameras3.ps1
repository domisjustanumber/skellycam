# recover_restart_cameras3.ps1 -- ELEVATED. Clears the DN_NEED_RESTART state on the three cameras without a reboot.
# LogiTuneAgent.exe is respawned by the LogiTuneUpdaterService service (parent pid = LogiTuneUpdater.exe) and vetoes
# device removal, so: stop that service, kill the agent, restart the composite (parent) devices with SetupAPI
# DIF_PROPERTYCHANGE (timing\build\devrestart.exe; pnputil refuses devices already flagged "pending reboot"),
# fall back to disable+enable, then start the service again (restoring its prior state).
param([string]$Log = "$env:TEMP\recover_restart_cameras3.log",
      [string[]]$Parents = @('USB\VID_1532&PID_0E05\9&3A0ECB01&0&4', 'USB\VID_046D&PID_085C\B76395EF', 'USB\VID_046D&PID_0843\7&7DCC7CE&0&4'))
function W([string]$s) { Add-Content -LiteralPath $Log -Value $s -Encoding UTF8 }
Set-Content -LiteralPath $Log -Encoding UTF8 -Value "=== $(Get-Date -Format o) recover_restart_cameras3"
$exe = Join-Path $PSScriptRoot '..\build\devrestart.exe'
$svc = Get-Service -Name LogiTuneUpdaterService -ErrorAction SilentlyContinue
$was = if ($svc) { $svc.Status } else { 'absent' }
W "LogiTuneUpdaterService status before: $was"
if ($svc -and $svc.Status -eq 'Running') { try { Stop-Service LogiTuneUpdaterService -Force -ErrorAction Stop; W 'stopped LogiTuneUpdaterService' } catch { W "stop service failed: $_" } }
Get-Process -Name LogiTuneAgent, LogiTune, RazerAppEngine -ErrorAction SilentlyContinue | ForEach-Object { W "stopping $($_.ProcessName) pid=$($_.Id)"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep 2
$o = & $exe --kill 'LogiTuneAgent.exe,LogiTune.exe,RazerAppEngine.exe' @Parents 2>&1 | Out-String
W "devrestart propchange exit=$LASTEXITCODE`n$o"
if ($LASTEXITCODE -ne 0) {
  $o = & $exe --disable-enable --kill 'LogiTuneAgent.exe,LogiTune.exe,RazerAppEngine.exe' @Parents 2>&1 | Out-String
  W "devrestart disable+enable exit=$LASTEXITCODE`n$o"
}
Start-Sleep 5
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_1532&PID_0E05|VID_046D&PID_085C|VID_046D&PID_0843' } | ForEach-Object {
  $st = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_DevNodeStatus).Data
  W ("{0} status={1} devnodestatus=0x{2:X} need_restart={3}" -f $_.InstanceId, $_.Status, $st, [bool]($st -band 0x01000000))
}
if ($was -eq 'Running') { try { Start-Service LogiTuneUpdaterService -ErrorAction Stop; W 'restarted LogiTuneUpdaterService' } catch { W "start service failed: $_" } }
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-PnP'; Id=225; StartTime=(Get-Date).AddMinutes(-2)} -ErrorAction SilentlyContinue |
  ForEach-Object { W "VETO EVENT $($_.TimeCreated): $(($_.Message -split "`n")[0])" }
W "DONE $(Get-Date -Format o)"
