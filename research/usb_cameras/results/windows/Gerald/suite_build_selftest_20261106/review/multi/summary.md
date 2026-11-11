# Windows UVC suite run, Gerald, 20261106T181417Z

Mode: quick (cycles 4, process cycles 2, frames 10, MJPEG 1.5 s per mode). Elapsed 3m34s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_build_selftest_20261106\review\multi`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_build_selftest_20261106\review\multi`.

Ratings use the plan section 3 thresholds (common/rating.py). Tier 1 = needs the one-time admin configuration (MetadataBufferSizeInKB0); everything else is tier 0. Each cell links to the JSON with the criteria and evidence.

## Cameras

| Key | Name | VID:PID | Speed | Tier-1 metadata | Last arrival |
| --- | --- | --- | --- | --- | --- |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | True | 2026-11-06T15:04:37.661901+00:00 |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | True | 2026-11-06T14:59:24.581364+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | False | 2026-11-06T17:47:04.819155+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/7` | Logitech Webcam C930e | 046d:0843 | HS | False | 2026-11-06T15:00:22.388177+00:00 |

## Ratings per goal, camera and API

### G-BW

| Camera | ds | mf | pyav_ds |
| --- | --- | --- | --- |
| all | [partial](W-MULTI.json) | [yes](W-MULTI.json) | [**no**](W-MULTI.json) |

### policy_traps

| Camera | all |
| --- | --- |
| all | [yes](W-POLICY.json) |

## Tests

| Test | Status | Elapsed | ETA was | Errors | JSON |
| --- | --- | --- | --- | --- | --- |
| W-POLICY | ok | 0m00s | 0m10s | 0 | [W-POLICY.json](W-POLICY.json) |
| W-MULTI | ok | 3m34s | 4m34s | 0 | [W-MULTI.json](W-MULTI.json) |
