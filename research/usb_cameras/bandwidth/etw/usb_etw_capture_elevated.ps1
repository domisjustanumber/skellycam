# usb_etw_capture_elevated.ps1 -- ELEVATED part of the goal-3 USB ETW capture (Windows). Needs admin (one UAC prompt).
# Starts a NON-persistent ETW session (logman ... -ets: nothing is written to the Data Collector Set store) with the
# USB 3 stack providers + keywords from Microsoft's "How to capture a USB event trace with Logman"
# (Default = rundown incl. descriptors; FullDataBusTrace = all transfers with up to 4 KB of control-transfer data;
# isochronous payload is never logged). Waits until -FlagFile exists (written by the non-elevated test driver after its
# camera runs) or -MaxMinutes elapse, then stops the session. Log: <OutDir>\elevated_log.txt
# Revert: usb_etw_revert.ps1 (stops the session if still running). Launched by etw_capture.py via Start-Process -Verb RunAs.
param([Parameter(Mandatory=$true)][string]$OutDir, [Parameter(Mandatory=$true)][string]$FlagFile, [int]$MaxMinutes = 10)
$ErrorActionPreference = 'Continue'
New-Item -ItemType Directory -Force $OutDir | Out-Null
$log = Join-Path $OutDir 'elevated_log.txt'
function L($m) { "$(Get-Date -Format o) $m" | Out-File -Append -Encoding utf8 $log }
$s = 'skellycam_usbbw'
$etl = Join-Path $OutDir 'usbbw.etl'
L "whoami: $(whoami) ; elevated: $(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"
L (& logman stop $s -ets 2>&1 | Out-String)  # in case a previous run left it
L (& logman start $s -o $etl -nb 128 640 -bs 128 -ets -p Microsoft-Windows-USB-UCX '(Default,FullDataBusTrace)' 2>&1 | Out-String)
L (& logman update $s -ets -p Microsoft-Windows-USB-USBHUB3 '(Default,FullDataBusTrace)' 2>&1 | Out-String)
L (& logman update $s -ets -p Microsoft-Windows-USB-USBXHCI '(Default,FullDataBusTrace)' 2>&1 | Out-String)
L (& logman query $s -ets 2>&1 | Out-String)
L 'STARTED'
$deadline = (Get-Date).AddMinutes($MaxMinutes)
while (-not (Test-Path $FlagFile) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
L ("flag present: " + (Test-Path $FlagFile))
L (& logman stop $s -ets 2>&1 | Out-String)
L (& logman query -ets 2>&1 | Out-String)
L 'STOPPED'
