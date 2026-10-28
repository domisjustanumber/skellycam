# Wrapper: calls run_flash_test.ps1 with a proper string[] -Cams (pwsh -File cannot pass arrays). Run UNDER camlock.
param([Parameter(Mandatory)][string]$RunDir, [int]$ExpLog2 = -7, [int]$Seconds = 30)
$cams = @("vid_046d&pid_085c,1280,720,30,$ExpLog2,4500", "vid_046d&pid_0843,1280,720,30,$ExpLog2,4500")
& 'C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\timing\scripts\run_flash_test.ps1' -RunDir $RunDir -Seconds $Seconds -Monitors @(0) -Cams $cams
