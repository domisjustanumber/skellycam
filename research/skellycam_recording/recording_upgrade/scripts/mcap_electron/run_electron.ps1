# Launch the MCAP desk test in one Electron build. Usage:
#   pwsh run_electron.ps1 -Exe <electron.exe> -Media <dir from gen_media.py> -Nm <node_modules with @mcap/core 2.4.0> -Out <result.json> [-Tests all] [-TimeoutS 900]
param([string]$Exe, [string]$Media, [string]$Nm, [string]$Out, [string]$Tests = 'all', [int]$TimeoutS = 900)
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$env:MCAP_MEDIA = $Media; $env:MCAP_NM = $Nm; $env:MCAP_OUT = $Out; $env:MCAP_TESTS = $Tests
$main = Join-Path $PSScriptRoot 'main.cjs'
$p = Start-Process -FilePath $Exe -ArgumentList "`"$main`"" -PassThru -NoNewWindow
if (-not $p.WaitForExit($TimeoutS * 1000)) { Write-Output "TIMEOUT; killing $($p.Id)"; Stop-Process -Id $p.Id -Force }
Write-Output "exit $($p.ExitCode); out exists: $(Test-Path $Out)"
