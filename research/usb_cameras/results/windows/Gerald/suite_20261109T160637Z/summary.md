# Windows UVC suite run, Gerald, 20261109T160637Z

Mode: quick (W-CYC profile quick, cycles 4, process cycles 2, frames 10, MJPEG 1.5 s per mode; streaming mode scope exactly 720 lines at >= 30 fps). Elapsed 25m04s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261109T160637Z`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261109T160637Z`.

Ratings use the plan section 3 thresholds (common/rating.py), on tier-0 data only (the cameras as found; no UVC PTS/SCR, Dom 2026-11-09). Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | 2026-11-09T14:25:04.535864+00:00 | 2026-11-09T14:25:04.535864+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/8` | Logitech Webcam C930e | 046d:0843 | HS | 2026-11-09T14:25:25.190309+00:00 | 2026-11-09T14:25:25.190309+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | 2026-11-09T14:31:30.844483+00:00 | 2026-11-09T14:31:30.844483+00:00 |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | 2026-11-09T14:25:14.024580+00:00 | 2026-11-09T14:25:14.024580+00:00 |

## USB link at run start

| Camera | Speed | bcdUSB | Port protocols | Plug-in age at start | Last arrival |
| --- | --- | --- | --- | --- | --- |
| USB Video Device (Kiyo) | SS | 0320 | usb3 | 101.6 min | 2026-11-09T14:25:04.535864+00:00 |
| Logitech Webcam C930e | HS | 0200 | usb1.1, usb2.0 | 101.2 min | 2026-11-09T14:25:25.190309+00:00 |
| USB Camera | HS | 0200 | usb1.1, usb2.0 | 95.1 min | 2026-11-09T14:31:30.844483+00:00 |
| c922 Pro Stream Webcam | HS | 0200 | usb1.1, usb2.0 | 101.4 min | 2026-11-09T14:25:14.024580+00:00 |

## Ratings per goal, camera and API

### G-TS

| Camera | ds | ds:frame_index_fit | ds:pyav_pts | ds_ffmpeg | ds_ffmpeg:ffmpeg_pts | ds_ffmpeg:frame_index_fit | mf | mf:frame_index_fit | mf:mf_sample_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |
| Logitech Webcam C930e (046d:0843) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |
| USB Camera (4c4a:4a55) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |
| c922 Pro Stream Webcam (046d:085c) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |

### G-RAW

| Camera | ffmpeg | mf | ocv_dshow | ocv_msmf | pyav |
| --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-RAW.json) | [yes](W-RAW.json) | [**no (no raw frames in the requested format)**](W-RAW.json) | [partial](W-RAW.json) | [yes](W-RAW.json) |
| Logitech Webcam C930e (046d:0843) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) |
| USB Camera (4c4a:4a55) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) |
| c922 Pro Stream Webcam (046d:085c) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) |

### G-CTRL

| Camera | opencv_dshow | opencv_msmf |
| --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [partial](W-OCV-CTRL.json) | [**no**](W-OCV-CTRL.json) |
| Logitech Webcam C930e (046d:0843) | [partial](W-OCV-CTRL.json) | [untested (device fault)](W-OCV-CTRL.json) |
| USB Camera (4c4a:4a55) | [partial](W-OCV-CTRL.json) | [**no**](W-OCV-CTRL.json) |
| c922 Pro Stream Webcam (046d:085c) | [partial](W-OCV-CTRL.json) | [untested (device fault)](W-OCV-CTRL.json) |

### G-CTRL-AUTO

| Camera | ds-ae | ds-af | mf-ae | mf-af | opencv_dshow-ae | opencv_dshow-af | opencv_msmf-ae | opencv_msmf-af |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-AUTO.json) | [untested (inconclusive)](W-AUTO.json) | [yes](W-AUTO.json) | [untested (inconclusive)](W-AUTO.json) | [untested (inconclusive)](W-OCV-CTRL.json) | [untested (inconclusive)](W-OCV-CTRL.json) | [untested (inconclusive)](W-OCV-CTRL.json) | [untested (inconclusive)](W-OCV-CTRL.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-AUTO.json) | [yes](W-AUTO.json) | [yes](W-AUTO.json) | [yes](W-AUTO.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [untested (device fault)](W-OCV-CTRL.json) | [untested (device fault)](W-OCV-CTRL.json) |
| USB Camera (4c4a:4a55) | [yes](W-AUTO.json) | [untested (n/a)](W-AUTO.json) | [yes](W-AUTO.json) | [untested (n/a)](W-AUTO.json) | [yes](W-OCV-CTRL.json) | [untested (n/a)](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [untested (n/a)](W-OCV-CTRL.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-AUTO.json) | [**no (flag only)**](W-AUTO.json) | [**no (flag only)**](W-AUTO.json) | [yes](W-AUTO.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [untested (device fault)](W-OCV-CTRL.json) | [untested (device fault)](W-OCV-CTRL.json) |

### reliability

| Camera | ds_ffmpeg_inproc | ds_inproc | ds_modeswitch | ds_newproc | mf_inproc | mf_modeswitch | mf_newproc | opencv_inproc | opencv_skellycam | opencv_skellycam_fps30 | pymf_inproc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes (point estimate; n=4, Wilson lower 0.510; rate < 90% of requested in 4/4)](W-CYC.json) | [partial (format mismatch; rate < 90% of requested in 4/4)](W-CYC.json) | [partial (format mismatch; rate < 90% of requested in 2/2)](W-CYC.json) | [partial (format mismatch; rate < 90% of requested in 2/2)](W-CYC.json) | [yes (point estimate; n=4, Wilson lower 0.510; rate < 90% of requested in 4/4)](W-CYC.json) | [yes (point estimate; n=2, Wilson lower 0.342; rate < 90% of requested in 2/2)](W-CYC.json) | [yes (point estimate; n=2, Wilson lower 0.342; rate < 90% of requested in 2/2)](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes](W-PYMF.json) |
| Logitech Webcam C930e (046d:0843) | [yes (point estimate; n=4, Wilson lower 0.510)](W-CYC.json) | [yes (point estimate; n=4, Wilson lower 0.510)](W-CYC.json) |  | [yes (point estimate; n=2, Wilson lower 0.342)](W-CYC.json) | [yes (point estimate; n=4, Wilson lower 0.510)](W-CYC.json) |  | [yes (point estimate; n=2, Wilson lower 0.342)](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes](W-PYMF.json) |
| USB Camera (4c4a:4a55) | [yes (point estimate; n=4, Wilson lower 0.510; rate < 90% of requested in 4/4)](W-CYC.json) | [yes (point estimate; n=4, Wilson lower 0.510; rate < 90% of requested in 4/4)](W-CYC.json) |  | [yes (point estimate; n=2, Wilson lower 0.342; rate < 90% of requested in 2/2)](W-CYC.json) | [yes (point estimate; n=4, Wilson lower 0.510; rate < 90% of requested in 4/4)](W-CYC.json) |  | [yes (point estimate; n=2, Wilson lower 0.342; rate < 90% of requested in 2/2)](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes](W-PYMF.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes (point estimate; n=4, Wilson lower 0.510)](W-CYC.json) | [yes (point estimate; n=4, Wilson lower 0.510)](W-CYC.json) | [yes (point estimate; n=2, Wilson lower 0.342)](W-CYC.json) | [yes (point estimate; n=2, Wilson lower 0.342)](W-CYC.json) | [yes (point estimate; n=4, Wilson lower 0.510)](W-CYC.json) | [yes (point estimate; n=2, Wilson lower 0.342)](W-CYC.json) | [yes (point estimate; n=2, Wilson lower 0.342)](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes](W-PYMF.json) |

### pymf_equivalence

| Camera | all | pymf |
| --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo |  | [yes](W-PYMF.json) |
| Logitech Webcam C930e (046d:0843) |  | [yes](W-PYMF.json) |
| USB Camera (4c4a:4a55) |  | [yes](W-PYMF.json) |
| c922 Pro Stream Webcam (046d:085c) |  | [yes](W-PYMF.json) |
| all | [partial (control sets on a streaming source not tested through pymf)](W-PYMF.json) |  |

### G-BW

| Camera | all |
| --- | --- |
| all | [untested](W-TOPO.json) |

### list_touch

| Camera | ffmpeg_list_devices | ffmpeg_list_options | pyav_list_devices | pyav_list_options |
| --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |
| Logitech Webcam C930e (046d:0843) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |
| USB Camera (4c4a:4a55) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |
| c922 Pro Stream Webcam (046d:085c) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |
| all | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  |

### mapper

| Camera | all |
| --- | --- |
| all | [yes](W-TOPO.json) |

## Device faults, first failures and the Kiyo onset

Faults (0x8007001F / unreleasable reader / killed streaming command) gate a camera's streaming work from the next test on; each later test re-probes it once with a 1-frame MF capture. "(gated)" in a rating cell = the camera was faulted when that test started.

| Camera | Faulted since (UTC) | Test | Mode | Code / class | Plug-in age | Source | Now |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Logitech Webcam C930e (046d:0843) | 2026-11-09T16:22:50.725306+00:00 | W-OCV-CTRL | MJPG 1280x720@30 | timeout / unreleasable | 117.4 min | camcmd_scan | recovered 2026-11-09T16:25:30.770551+00:00 |
| c922 Pro Stream Webcam (046d:085c) | 2026-11-09T16:25:29.578971+00:00 | W-OCV-CTRL | MJPG 1280x720@30 | timeout / unreleasable | 120.3 min | camcmd_scan | recovered 2026-11-09T16:25:31.775474+00:00 |

First failed camera command per camera (any class):

- Logitech Webcam C930e (046d:0843): 2026-11-09T16:22:50.725306+00:00 in W-OCV-CTRL, opencv MJPG 1280x720@30 at format sets: timeout (unreleasable), plug-in age 117.4 min
- c922 Pro Stream Webcam (046d:085c): 2026-11-09T16:25:29.578971+00:00 in W-OCV-CTRL, opencv MJPG 1280x720@30 at format sets: timeout (unreleasable), plug-in age 120.3 min
- USB Video Device (1532:0e05) Kiyo: 2026-11-09T16:27:19.726817+00:00 in W-CYC, opencv MJPG 1280x720@30 at None: 4 (None), plug-in age 122.6 min
- USB Camera (4c4a:4a55): 2026-11-09T16:30:12.945855+00:00 in W-CYC, opencv MJPG 1280x720@30 at None: 4 (None), plug-in age 118.8 min

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m01s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-TOPO | ok | 0m02s | 1m02s | 0 | - | [W-TOPO.json](W-TOPO.json) |
| W-RAW | ok | 2m37s | 5m13s | 0 | - | [W-RAW.json](W-RAW.json) |
| W-TS | ok | 1m57s | 2m48s | 0 | - | [W-TS.json](W-TS.json) |
| W-PYMF | ok | 1m43s | 5m03s | 0 | - | [W-PYMF.json](W-PYMF.json) |
| W-AUTO | ok | 5m53s | 11m00s | 0 | - | [W-AUTO.json](W-AUTO.json) |
| W-OCV-CTRL | ok | 6m34s | 15m12s | 0 | - | [W-OCV-CTRL.json](W-OCV-CTRL.json) |
| W-PYAV-LIST | ok | 1m02s | 3m20s | 0 | - | [W-PYAV-LIST.json](W-PYAV-LIST.json) |
| W-CYC | ok | 5m09s | 8m33s | 0 | - | [W-CYC.json](W-CYC.json) |
