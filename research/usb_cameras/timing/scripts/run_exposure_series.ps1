# run_exposure_series.ps1 -- (run UNDER camlock) flash runs at several manual exposures for the C922 + C930e, to test
# whether the exposure-start offset vs UVC PTS is independent of exposure time (PTS = start of exposure) or shifts by
# the exposure change (PTS = end of exposure / readout).
param([Parameter(Mandatory)][string]$Root, [int[]]$ExposuresLog2 = @(-9, -6), [int]$Seconds = 30, [int[]]$Monitors = @(0))
foreach ($e in $ExposuresLog2) {
  $cams = @("vid_046d&pid_085c,1280,720,30,$e,4500", "vid_046d&pid_0843,1280,720,30,$e,4500")
  & (Join-Path $PSScriptRoot 'run_flash_test.ps1') -RunDir (Join-Path $Root "exp$e") -Seconds $Seconds -Monitors $Monitors -Cams $cams
}
