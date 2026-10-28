# usb_etw_revert.ps1 -- revert for usb_etw_capture_elevated.ps1: stop the non-persistent ETW session if it still runs.
# Run elevated:  Start-Process powershell -Verb RunAs -ArgumentList '-File <this file>'
# Nothing else is changed by the capture (no registry, no persistent data collector set, no driver change).
logman stop skellycam_usbbw -ets
logman query -ets | Select-String skellycam
