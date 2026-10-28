# recover_restart_cameras.ps1 -- ELEVATED. Restart the three cameras' USB composite (parent) devices so usbvideo
# re-reads its per-interface registry (MetadataBufferSizeInKB0) and the DN_NEED_RESTART state left by a vetoed
# `pnputil /restart-device` on the MI_00 child is cleared (MF then returns MF_E_REBOOT_REQUIRED 0xC00D7167 until
# re-enumeration).
# Why processes are stopped: Kernel-PnP event 225 showed LogiTuneAgent.exe and RazerAppEngine.exe (vendor helper apps
# holding handles to the cameras) vetoing the query-remove. They are user-session apps; relaunch them from the Start
# menu (or re-login) afterwards if wanted. This script records what it stopped.
# Run: Start-Process powershell -Verb RunAs -ArgumentList '-ExecutionPolicy Bypass -File <this> -Log <logfile>'
param(
  [string]$Log = "$env:TEMP\recover_restart_cameras.log",
  [string[]]$Parents = @('USB\VID_1532&PID_0E05\9&3A0ECB01&0&4', 'USB\VID_046D&PID_085C\B76395EF', 'USB\VID_046D&PID_0843\7&7DCC7CE&0&4'),
  [string[]]$StopProcessNames = @('LogiTuneAgent', 'RazerAppEngine')
)
function W([string]$s) { Add-Content -LiteralPath $Log -Value $s -Encoding UTF8 }
Set-Content -LiteralPath $Log -Encoding UTF8 -Value "=== $(Get-Date -Format o) recover_restart_cameras"
foreach ($n in $StopProcessNames) {
  Get-Process -Name $n -ErrorAction SilentlyContinue | ForEach-Object {
    W "stopping $($_.ProcessName) pid=$($_.Id) path=$($_.Path)"
    try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch { W "  stop failed: $_" }
  }
}
Start-Sleep 2
foreach ($p in $Parents) {
  $o = & pnputil.exe /restart-device "$p" 2>&1 | Out-String
  W "pnputil /restart-device $p :: exit=$LASTEXITCODE :: $($o.Trim() -replace '\r?\n',' | ')"
}
Start-Sleep 5
Get-PnpDevice -PresentOnly | Where-Object { $_.InstanceId -match 'VID_1532&PID_0E05|VID_046D&PID_085C|VID_046D&PID_0843' } | ForEach-Object {
  $st = (Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName DEVPKEY_Device_DevNodeStatus).Data
  W ("{0} status={1} devnodestatus=0x{2:X} need_restart={3}" -f $_.InstanceId, $_.Status, $st, [bool]($st -band 0x01000000))
}
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-Kernel-PnP'; Id=225; StartTime=(Get-Date).AddMinutes(-2)} -ErrorAction SilentlyContinue |
  ForEach-Object { W "VETO EVENT $($_.TimeCreated): $(($_.Message -split "`n")[0])" }
W "DONE $(Get-Date -Format o)"
