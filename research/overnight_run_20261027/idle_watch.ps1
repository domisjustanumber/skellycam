# Waits until the machine is idle after 23:00, then prints IDLE and exits 0.
# Idle = no keyboard/mouse input for $IdleMinutes AND average CPU load below $MaxCpu over 3 samples.
# Gives up at $GiveUpHour the next morning: prints TIMEOUT and exits 1.
param(
    [int]$StartHour = 23,
    [int]$IdleMinutes = 15,
    [int]$MaxCpu = 25,
    [int]$GiveUpHour = 6
)

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class IdleInfo {
    [StructLayout(LayoutKind.Sequential)] struct LII { public uint cbSize; public uint dwTime; }
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LII p);
    public static uint Seconds() {
        LII l = new LII(); l.cbSize = (uint)Marshal.SizeOf(l);
        GetLastInputInfo(ref l);
        return ((uint)Environment.TickCount - l.dwTime) / 1000;
    }
}
'@

$started = Get-Date
$deadline = $started.Date.AddDays(1).AddHours($GiveUpHour)
$windowStart = $started.Date.AddHours($StartHour)
"watcher started $($started.ToString('s')); window opens $($windowStart.ToString('s')); gives up $($deadline.ToString('s'))"

while ($true) {
    $now = Get-Date
    if ($now -ge $deadline) { "TIMEOUT $($now.ToString('s')): machine never went idle"; exit 1 }
    if ($now -ge $windowStart) {
        $idle = [IdleInfo]::Seconds()
        if ($idle -ge $IdleMinutes * 60) {
            $samples = 1..3 | ForEach-Object {
                (Get-CimInstance Win32_Processor | Measure-Object LoadPercentage -Average).Average
                Start-Sleep -Seconds 5
            }
            $cpu = ($samples | Measure-Object -Average).Average
            if ($cpu -lt $MaxCpu) {
                "IDLE $($now.ToString('s')) input_idle_s=$idle cpu_avg=$([math]::Round($cpu,1))"
                exit 0
            }
        }
    }
    Start-Sleep -Seconds 60
}
