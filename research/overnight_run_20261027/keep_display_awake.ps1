# Keeps the display and system awake until $StopFile exists (or $MaxHours pass).
# Needed by the timing flash tests, which film the monitor. No admin rights required.
param(
    [string]$StopFile = "$PSScriptRoot\stop_display_hold",
    [int]$MaxHours = 10
)

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class Exec {
    [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);
    [DllImport("user32.dll")] public static extern void mouse_event(uint flags, int dx, int dy, uint data, UIntPtr extra);
}
'@

Remove-Item $StopFile -ErrorAction SilentlyContinue
# ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
[void][Exec]::SetThreadExecutionState(0x80000003)
# Wake a display that already went to sleep: the execution state only keeps it on, so nudge the mouse 1 px and back.
[Exec]::mouse_event(0x0001, 1, 0, 0, [UIntPtr]::Zero)
Start-Sleep -Milliseconds 50
[Exec]::mouse_event(0x0001, -1, 0, 0, [UIntPtr]::Zero)
"display hold on $((Get-Date).ToString('s'))"
$end = (Get-Date).AddHours($MaxHours)
while (-not (Test-Path $StopFile) -and (Get-Date) -lt $end) { Start-Sleep -Seconds 20 }
[void][Exec]::SetThreadExecutionState(0x80000000)
"display hold released $((Get-Date).ToString('s'))"
