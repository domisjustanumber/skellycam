# dshow_probe_all.ps1 -- run timing/build/dshow_open_probe.exe on the in-scope cameras only (Kiyo 1532:0E05 excluded). Run UNDER camlock.
param([Parameter(Mandatory)][string]$Out)
$exe = 'C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\timing\build\dshow_open_probe.exe'
$reqs = @(
  @('vid_046d&pid_085c', 'MJPG', 1280, 720, 30), @('vid_046d&pid_0843', 'MJPG', 1280, 720, 30), @('vid_4c4a&pid_4a55', 'MJPG', 1280, 720, 30),
  @('vid_046d&pid_085c', 'YUY2', 640, 480, 30), @('vid_046d&pid_0843', 'YUY2', 640, 480, 30), @('vid_4c4a&pid_4a55', 'YUY2', 640, 480, 30))
foreach ($r in $reqs) {
  $o = & $exe --dev $r[0] --sub $r[1] --w $r[2] --h $r[3] --fps $r[4] 2>&1
  "exit=$LASTEXITCODE $($r -join ' ')" | Add-Content "$Out.exitcodes.txt"
  $o | Add-Content $Out
}
