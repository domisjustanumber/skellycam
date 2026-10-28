# recover_restart_cameras2.ps1 -- ELEVATED. Same as recover_restart_cameras.ps1 but also stops the LogiTune GUI
# (LogiTune.exe respawned LogiTuneAgent.exe within seconds in the first attempt, which vetoed the restart again).
param([string]$Log = "$env:TEMP\recover_restart_cameras2.log")
& (Join-Path $PSScriptRoot 'recover_restart_cameras.ps1') -Log $Log -StopProcessNames @('LogiTune', 'LogiTuneAgent', 'RazerAppEngine')
