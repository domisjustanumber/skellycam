# Windows UVC suite run, Gerald, 20261119T030110Z

Mode: full (W-CYC profile reliability, cycles 50, process cycles 15, frames 30, MJPEG 3.0 s per mode; streaming mode scope exactly 720 lines at >= 30 fps). Elapsed 3m10s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261119T030110Z`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261119T030110Z`.

Ratings use the plan section 3 thresholds (common/rating.py), on tier-0 data only (the cameras as found; no UVC PTS/SCR, Dom 2026-11-09). Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | 2026-11-19T02:59:35.739355+00:00 | 2026-11-19T02:59:35.739355+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/8` | Logitech Webcam C930e | 046d:0843 | HS | 2026-11-16T12:43:00.420074+00:00 | 2026-11-16T12:43:00.420074+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | 2026-11-16T12:43:12.254372+00:00 | 2026-11-16T12:43:12.254372+00:00 |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | 2026-11-16T12:43:01.549968+00:00 | 2026-11-16T12:43:01.549968+00:00 |

## USB link at run start

| Camera | Speed | bcdUSB | Port protocols | Plug-in age at start | Last arrival |
| --- | --- | --- | --- | --- | --- |
| USB Video Device (Kiyo) | SS | 0320 | usb3 | 1.6 min | 2026-11-19T02:59:35.739355+00:00 |
| Logitech Webcam C930e | HS | 0200 | usb1.1, usb2.0 | 3738.2 min | 2026-11-16T12:43:00.420074+00:00 |
| USB Camera | HS | 0200 | usb1.1, usb2.0 | 3738.0 min | 2026-11-16T12:43:12.254372+00:00 |
| c922 Pro Stream Webcam | HS | 0200 | usb1.1, usb2.0 | 3738.2 min | 2026-11-16T12:43:01.549968+00:00 |

## Ratings per goal, camera and API

### G-BW

| Camera | all |
| --- | --- |
| all | [untested](W-TOPO.json) |

### kiyo

| Camera | all |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-KIYO.json) |

### T-BUMP

| Camera | all |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-TBUMP.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-TBUMP.json) |
| USB Camera (4c4a:4a55) | [yes](W-TBUMP.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-TBUMP.json) |
| recording | [yes](W-TBUMP.json) |

### mapper

| Camera | all |
| --- | --- |
| all | [yes](W-TOPO.json) |

## Device faults, first failures and the Kiyo onset

Faults (0x8007001F / unreleasable reader / killed streaming command) gate a camera's streaming work from the next test on; each later test re-probes it once with a 1-frame MF capture. "(gated)" in a rating cell = the camera was faulted when that test started.

Kiyo onset, USB Video Device (1532:0e05) Kiyo (W-KIYO background poller from 2026-11-19T03:01:10.832846+00:00, plug-in age at start 1.6 min):

- answered every control poll so far (6 polls)

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-TOPO | ok | 0m01s | 1m02s | 0 | - | [W-TOPO.json](W-TOPO.json) |
| W-TBUMP | ok | 3m08s | 6m00s | 0 | - | [W-TBUMP.json](W-TBUMP.json) |
| W-KIYO | ok (background) | 0m00s | 0m00s | 0 | - | [W-KIYO.json](W-KIYO.json) |
