# Windows UVC suite run, Gerald, 20261109T173335Z

Mode: full (W-CYC profile reliability, cycles 50, process cycles 15, frames 30, MJPEG 3.0 s per mode; streaming mode scope exactly 720 lines at >= 30 fps). Elapsed 0m20s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261109T173335Z`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261109T173335Z`.

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
| USB Video Device (Kiyo) | SS | 0320 | usb3 | 188.5 min | 2026-11-09T14:25:04.535864+00:00 |
| Logitech Webcam C930e | HS | 0200 | usb1.1, usb2.0 | 188.2 min | 2026-11-09T14:25:25.190309+00:00 |
| USB Camera | HS | 0200 | usb1.1, usb2.0 | 182.1 min | 2026-11-09T14:31:30.844483+00:00 |
| c922 Pro Stream Webcam | HS | 0200 | usb1.1, usb2.0 | 188.4 min | 2026-11-09T14:25:14.024580+00:00 |

## Ratings per goal, camera and API

### G-ID

| Camera | all |
| --- | --- |
| all | [partial (provisional: persistence not measured)](W-ID.json) |

### G-BW

| Camera | all |
| --- | --- |
| all | [untested](W-TOPO.json) |

### fmt_equivalence

| Camera | all |
| --- | --- |
| all | [yes](W-FMT.json) |

### key_source_stability

| Camera | all |
| --- | --- |
| all | [yes](W-ID.json) |

### mapper

| Camera | all |
| --- | --- |
| all | [yes](W-TOPO.json) |

### policy_traps

| Camera | all |
| --- | --- |
| all | [yes](W-POLICY.json) |

## Device faults, first failures and the Kiyo onset

No device fault or failed camera command recorded.

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-POLICY | ok | 0m00s | 0m10s | 0 | - | [W-POLICY.json](W-POLICY.json) |
| W-TOPO | ok | 0m01s | 1m02s | 0 | - | [W-TOPO.json](W-TOPO.json) |
| W-ID | ok | 0m13s | 1m20s | 0 | - | [W-ID.json](W-ID.json) |
| W-FMT | ok | 0m03s | 0m34s | 0 | - | [W-FMT.json](W-FMT.json) |
| W-FMT-NOGRAB | not run yet | - | - | - | - | - |
| W-CTRL-LIST | not run yet | - | - | - | - | - |
| W-MJPEG | not run yet | - | - | - | - | - |
| W-RAW | not run yet | - | - | - | - | - |
| W-TS | not run yet | - | - | - | - | - |
| W-PYMF | not run yet | - | - | - | - | - |
| W-CTRL-EFFECT | not run yet | - | - | - | - | - |
| W-AUTO | not run yet | - | - | - | - | - |
| W-OCV-CTRL | not run yet | - | - | - | - | - |
| W-CYC-KIYO | not run yet | - | - | - | - | - |
| W-MULTI | not run yet | - | - | - | - | - |
| W-PYAV-LIST | not run yet | - | - | - | - | - |
| W-CYC | not run yet | - | - | - | - | - |
| W-KIYO | running (background) | - | - | - | - | - |
