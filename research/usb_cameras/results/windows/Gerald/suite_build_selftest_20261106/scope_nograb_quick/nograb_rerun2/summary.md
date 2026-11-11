# Windows UVC suite run, Gerald, 20261106T224223Z

Mode: quick (cycles 4, process cycles 2, frames 10, MJPEG 1.5 s per mode; streaming mode scope >= 30 fps and >= 720 lines). Elapsed 2m48s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_build_selftest_20261106\scope_nograb_quick\nograb_rerun2`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_build_selftest_20261106\scope_nograb_quick\nograb_rerun2`.

Ratings use the plan section 3 thresholds (common/rating.py). Tier 1 = needs the one-time admin configuration (MetadataBufferSizeInKB0); everything else is tier 0. Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Tier-1 metadata | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- | --- |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | True | 2026-11-06T15:04:37.661901+00:00 | 2026-11-06T15:04:37.661901+00:00 |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | True | 2026-11-06T20:32:29.065252+00:00 | 2026-11-06T20:32:29.065252+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | False | 2026-11-06T22:26:45.172797+00:00 | 2026-11-06T22:26:45.172797+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/7` | Logitech Webcam C930e | 046d:0843 | HS | False | 2026-11-06T15:00:22.388177+00:00 | 2026-11-06T15:00:22.388177+00:00 |

## Ratings per goal, camera and API

### fmt_equivalence

| Camera | all |
| --- | --- |
| all | [yes](W-FMT.json) |

### fmt_nograb

| Camera | ds | ffmpeg | hub_ioctl | mf | opencv | winrt |
| --- | --- | --- | --- | --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-FMT-NOGRAB.json) | [**no (incomplete)**](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) |  |  |
| USB Video Device (1532:0e05) Kiyo | [yes](W-FMT-NOGRAB.json) | [**no (incomplete)**](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) |  |  |
| USB Camera (4c4a:4a55) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) |  |  |
| Logitech Webcam C930e (046d:0843) | [**no (incomplete)**](W-FMT-NOGRAB.json) | [**no (incomplete)**](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [**no (incomplete)**](W-FMT-NOGRAB.json) |  |  |
| all |  |  |  |  | [**no (cannot list without opening capture)**](W-FMT-NOGRAB.json) | [**no (cannot list without opening capture)**](W-FMT-NOGRAB.json) |

## Device faults, first failures and the Kiyo onset

No device fault or failed camera command recorded.

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-FMT | ok | 0m03s | 0m34s | 0 | - | [W-FMT.json](W-FMT.json) |
| W-FMT-NOGRAB | ok | 2m45s | 3m03s | 0 | - | [W-FMT-NOGRAB.json](W-FMT-NOGRAB.json) |
