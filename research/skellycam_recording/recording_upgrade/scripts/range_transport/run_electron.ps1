# Launch the T-S5 harness in one Electron build. Usage:
#   pwsh run_electron.ps1 -Exe <electron.exe> -Cfg <cfg.json> -Out <result.json> [-Phases semantics,correct,bench] [-TimeoutS 1800]
param([string]$Exe, [string]$Cfg, [string]$Out, [string]$Phases = 'semantics,correct,bench', [int]$TimeoutS = 1800)
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$env:RT_CFG = $Cfg; $env:RT_OUT = $Out; $env:RT_PHASES = $Phases
$main = Join-Path $PSScriptRoot 'electron\main.cjs'
$p = Start-Process -FilePath $Exe -ArgumentList "`"$main`"" -PassThru -NoNewWindow
if (-not $p.WaitForExit($TimeoutS * 1000)) { Write-Output "TIMEOUT; killing $($p.Id)"; Stop-Process -Id $p.Id -Force }
Write-Output "exit $($p.ExitCode); out exists: $(Test-Path $Out)"
