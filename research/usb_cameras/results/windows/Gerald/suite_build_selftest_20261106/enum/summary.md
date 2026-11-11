# Windows UVC suite run, Gerald, 20261106T165518Z

Mode: full (cycles 50, process cycles 15, frames 30, MJPEG 3.0 s per mode). Elapsed 0m18s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_build_selftest_20261106\enum`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_build_selftest_20261106\enum`.

Ratings use the plan section 3 thresholds (common/rating.py). Tier 1 = needs the one-time admin configuration (MetadataBufferSizeInKB0); everything else is tier 0. Each cell links to the JSON with the criteria and evidence.

## Cameras

| Key | Name | VID:PID | Speed | Tier-1 metadata | Last arrival |
| --- | --- | --- | --- | --- | --- |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | True | 2026-11-06T15:04:37.661901+00:00 |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | True | 2026-11-06T14:59:24.581364+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | False | 2026-11-06T14:58:37.875027+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/7` | Logitech Webcam C930e | 046d:0843 | HS | False | 2026-11-06T15:00:22.388177+00:00 |

## Ratings per goal, camera and API

### G-ID

| Camera | all |
| --- | --- |
| all | [partial](W-ID.json) |

### G-CTRL

| Camera | all |
| --- | --- |
| all | [untested](W-CTRL-LIST.json) |

### G-BW

| Camera | all |
| --- | --- |
| all | [untested](W-TOPO.json) |

### G-ID_per_api

| Camera | ds | ffmpeg_cli_dshow | mf | opencv_dshow | opencv_msmf | pyav_dshow |
| --- | --- | --- | --- | --- | --- | --- |
| all | [partial](W-ID.json) | [partial](W-ID.json) | [partial](W-ID.json) | [partial](W-ID.json) | [partial](W-ID.json) | [partial](W-ID.json) |

### ctrl_list_equivalence

| Camera | all |
| --- | --- |
| all | [yes](W-CTRL-LIST.json) |

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
| all | [partial](W-TOPO.json) |

### policy_traps

| Camera | all |
| --- | --- |
| all | [yes](W-POLICY.json) |

## Tests

| Test | Status | Elapsed | ETA was | Errors | JSON |
| --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | [W-ENV.json](W-ENV.json) |
| W-POLICY | ok | 0m00s | 0m10s | 0 | [W-POLICY.json](W-POLICY.json) |
| W-TOPO | ok | 0m01s | 1m02s | 0 | [W-TOPO.json](W-TOPO.json) |
| W-ID | ok | 0m11s | 1m20s | 0 | [W-ID.json](W-ID.json) |
| W-FMT | ok | 0m02s | 0m34s | 0 | [W-FMT.json](W-FMT.json) |
| W-CTRL-LIST | ok | 0m02s | 0m34s | 0 | [W-CTRL-LIST.json](W-CTRL-LIST.json) |
