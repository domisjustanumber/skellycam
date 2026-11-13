# Windows UVC suite run, Gerald, 20261113T035946Z

Mode: full (W-CYC profile reliability, cycles 50, process cycles 15, frames 30, MJPEG 3.0 s per mode; streaming mode scope exactly 720 lines at >= 30 fps). Elapsed 23m22s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261113T035946Z`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261113T035946Z`.

Ratings use the plan section 3 thresholds (common/rating.py), on tier-0 data only (the cameras as found; no UVC PTS/SCR, Dom 2026-11-09). Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | 2026-11-12T22:27:22.836943+00:00 | 2026-11-12T22:27:22.836943+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/8` | Logitech Webcam C930e | 046d:0843 | HS | 2026-11-11T14:11:38.552007+00:00 | 2026-11-11T14:11:38.552007+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | 2026-11-12T07:09:33.309147+00:00 | **2026-11-13T04:22:11.542870+00:00** (re-arrived) |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | 2026-11-12T15:15:34.937875+00:00 | 2026-11-12T15:15:34.937875+00:00 |

## USB link at run start

| Camera | Speed | bcdUSB | Port protocols | Plug-in age at start | Last arrival |
| --- | --- | --- | --- | --- | --- |
| USB Video Device (Kiyo) | SS | 0320 | usb3 | 332.4 min | 2026-11-12T22:27:22.836943+00:00 |
| Logitech Webcam C930e | HS | 0200 | usb1.1, usb2.0 | 2268.1 min | 2026-11-11T14:11:38.552007+00:00 |
| USB Camera | HS | 0200 | usb1.1, usb2.0 | 1250.2 min | 2026-11-12T07:09:33.309147+00:00 |
| c922 Pro Stream Webcam | HS | 0200 | usb1.1, usb2.0 | 764.2 min | 2026-11-12T15:15:34.937875+00:00 |

## Ratings per goal, camera and API

### G-BW

| Camera | all | ds | mf | pyav_ds |
| --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [untested](W-MULTI.json) (gated) |  |  |  |
| USB Camera (4c4a:4a55) | [untested](W-MULTI.json) |  |  |  |
| all | [untested](W-TOPO.json) | [untested](W-MULTI.json) | [untested](W-MULTI.json) | [untested](W-MULTI.json) |

### kiyo

| Camera | all |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [**no**](W-KIYO.json) |

### T-BUMP

| Camera | all |
| --- | --- |
| Logitech Webcam C930e (046d:0843) | [yes](W-TBUMP.json) |
| USB Camera (4c4a:4a55) | [yes](W-TBUMP.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-TBUMP.json) |
| recording | [yes](W-TBUMP.json) |

### mapper

| Camera | all |
| --- | --- |
| all | [yes](W-TOPO.json) |

### pymf_in_use

| Camera | all |
| --- | --- |
| Logitech Webcam C930e (046d:0843) | [yes](W-PYMF-ALL.json) |

### pymf_multi

| Camera | 720p30 | 720p60 | all |
| --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-PYMF-ALL.json) | [untested (device fault)](W-PYMF-ALL.json) |  |
| Logitech Webcam C930e (046d:0843) | [yes](W-PYMF-ALL.json) | [untested (scope)](W-PYMF-ALL.json) |  |
| USB Camera (4c4a:4a55) | [yes](W-PYMF-ALL.json) | [untested (scope)](W-PYMF-ALL.json) |  |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-PYMF-ALL.json) | [yes](W-PYMF-ALL.json) |  |
| all |  |  | [partial (Kiyo Pro faulted)](W-PYMF-ALL.json) |

### pymf_streaming_set

| Camera | exposure |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-PYMF-ALL.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-PYMF-ALL.json) |
| USB Camera (4c4a:4a55) | [partial (ROI luma moved in the expected direction after each set)](W-PYMF-ALL.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-PYMF-ALL.json) |

## Device faults, first failures and the Kiyo onset

Faults (0x8007001F / unreleasable reader / killed streaming command) gate a camera's streaming work from the next test on; each later test re-probes it once with a 1-frame MF capture. "(gated)" in a rating cell = the camera was faulted when that test started.

| Camera | Faulted since (UTC) | Test | Mode | Code / class | Plug-in age | Source | Now |
| --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | 2026-11-13T04:13:01.098257+00:00 | W-PYMF-ALL | MJPG 1280x720@60 | timeout / unreleasable | 345.6 min | W-PYMF-ALL | faulted |
| USB Camera (4c4a:4a55) | 2026-11-13T04:22:15.825571+00:00 | W-MULTI | MJPG 1280x720@30 | watchdog timeout / hang | 0.1 min | W-MULTI multi_launch child | faulted |

First device-level failed camera command per camera (open / stream error, timeout, 0x8007001F; a helper exit for a format / rate mismatch with every cycle streamed is not one):

- USB Video Device (1532:0e05) Kiyo: 2026-11-13T04:13:01.098257+00:00 in W-PYMF-ALL, pymf MJPG 1280x720@60 at first_sample: timeout (unreleasable), plug-in age 345.6 min
- USB Camera (4c4a:4a55): 2026-11-13T04:22:00.642500+00:00 in W-MULTI, pyav_ds MJPG 1280x720@30 at open: timeout (device_not_ready), plug-in age 0.0 min

Kiyo onset, USB Video Device (1532:0e05) Kiyo (W-KIYO background poller from 2026-11-13T03:59:46.197866+00:00, plug-in age at start 332.4 min):

- first unanswered control poll 2026-11-13T04:13:01.194751Z during W-PYMF-ALL, plug-in age 345.6 min, codes []
- 2026-11-13T04:13:01.194751Z mf -> not_answering (during W-PYMF-ALL, plug-in age 345.6 min)
- first device fault: 2026-11-13T04:13:01.098257+00:00 in W-PYMF-ALL MJPG 1280x720@60 (timeout, unreleasable), plug-in age 345.6 min

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-TOPO | ok | 0m01s | 1m02s | 0 | - | [W-TOPO.json](W-TOPO.json) |
| W-PYMF-ALL | ok | 14m02s | 16m48s | 0 | - | [W-PYMF-ALL.json](W-PYMF-ALL.json) |
| W-TBUMP | ok | 2m53s | 6m00s | 0 | USB Video Device (1532:0e05) Kiyo | [W-TBUMP.json](W-TBUMP.json) |
| W-MULTI | ok | 6m23s | 23m09s | 0 | USB Video Device (1532:0e05) Kiyo | [W-MULTI.json](W-MULTI.json) |
| W-KIYO | ok (background) | 0m00s | 0m00s | 0 | - | [W-KIYO.json](W-KIYO.json) |
