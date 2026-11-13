# Launch the single-writer MCAP desk test (copy of ../mcap_electron/run_electron.ps1 with -Files). Usage:
#   pwsh run_sw.ps1 -Exe <electron.exe> -Media <dir from gen_media.py> -Nm <node_modules with @mcap/core 2.4.0> -Out <result.json> -Files a.mcap[,b.mcap] [-TimeoutS 900]
param([string]$Exe, [string]$Media, [string]$Nm, [string]$Out, [string]$Files, [int]$TimeoutS = 900)
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$env:MCAP_MEDIA = $Media; $env:MCAP_NM = $Nm; $env:MCAP_OUT = $Out; $env:MCAP_FILES = $Files
$main = Join-Path $PSScriptRoot 'main_sw.cjs'
$p = Start-Process -FilePath $Exe -ArgumentList "`"$main`"" -PassThru -NoNewWindow
if (-not $p.WaitForExit($TimeoutS * 1000)) { Write-Output "TIMEOUT; killing $($p.Id)"; Stop-Process -Id $p.Id -Force }
Write-Output "exit $($p.ExitCode); out exists: $(Test-Path $Out)"
