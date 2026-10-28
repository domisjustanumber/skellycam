# revert_uvc_metadata.ps1 -- ELEVATED. Undo enable_uvc_metadata.ps1: deletes MetadataBufferSizeInKB0 for the same
# camera interface keys and restarts the devices.
# Run: Start-Process powershell -Verb RunAs -ArgumentList '-ExecutionPolicy Bypass -File <this> -Log <logfile>'
param([string]$Log = "$env:TEMP\revert_uvc_metadata.log")
& (Join-Path $PSScriptRoot 'enable_uvc_metadata.ps1') -Remove -Log $Log
