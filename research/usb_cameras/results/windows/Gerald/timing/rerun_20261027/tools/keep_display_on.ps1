# Holds a display-required power request (like a video player) while this process runs; no settings are changed.
# Exits by itself after -Minutes. Kill the process to release early.
param([int]$Minutes = 200, [string]$Log)
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class KA { [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f); }
'@
$ES_CONTINUOUS = [uint32]2147483648; $ES_SYSTEM = [uint32]1; $ES_DISPLAY = [uint32]2
$end = (Get-Date).AddMinutes($Minutes)
$r = [KA]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM -bor $ES_DISPLAY)
if ($Log) { "{0} pid={1} SetThreadExecutionState prev=0x{2:X}" -f (Get-Date -Format o), $PID, $r | Add-Content $Log }
while ((Get-Date) -lt $end) { Start-Sleep -Seconds 30; [void][KA]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM -bor $ES_DISPLAY) }
[void][KA]::SetThreadExecutionState($ES_CONTINUOUS)
if ($Log) { "{0} released" -f (Get-Date -Format o) | Add-Content $Log }
