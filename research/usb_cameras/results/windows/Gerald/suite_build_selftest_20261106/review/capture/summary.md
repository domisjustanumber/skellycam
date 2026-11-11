# Windows UVC suite run, Gerald, 20261106T180533Z

Mode: quick (cycles 4, process cycles 2, frames 10, MJPEG 1.5 s per mode). Elapsed 7m33s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_build_selftest_20261106\review\capture`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_build_selftest_20261106\review\capture`.

Ratings use the plan section 3 thresholds (common/rating.py). Tier 1 = needs the one-time admin configuration (MetadataBufferSizeInKB0); everything else is tier 0. Each cell links to the JSON with the criteria and evidence.

## Cameras

| Key | Name | VID:PID | Speed | Tier-1 metadata | Last arrival |
| --- | --- | --- | --- | --- | --- |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | True | 2026-11-06T15:04:37.661901+00:00 |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | True | 2026-11-06T14:59:24.581364+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | False | 2026-11-06T17:47:04.819155+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/7` | Logitech Webcam C930e | 046d:0843 | HS | False | 2026-11-06T15:00:22.388177+00:00 |

## Ratings per goal, camera and API

### G-TS

| Camera | ds | ds:frame_index_fit | ds:pyav_pts | mf | mf:frame_index_fit | mf:mf_sample_time | mf:uvc_pts |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [partial](W-TS.json) (tier 1) | [untested](W-TS.json) | [**no**](W-TS.json) | [partial](W-TS.json) (tier 1) |
| USB Video Device (1532:0e05) Kiyo | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [partial](W-TS.json) (tier 1) | [untested](W-TS.json) | [**no**](W-TS.json) | [partial](W-TS.json) (tier 1) |
| USB Camera (4c4a:4a55) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |  |
| Logitech Webcam C930e (046d:0843) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |  |

### G-MJPEG

| Camera | ds | mf | pyav_ds |
| --- | --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) |
| USB Video Device (1532:0e05) Kiyo | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) | [**no**](W-MJPEG.json) |
| USB Camera (4c4a:4a55) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) |
| Logitech Webcam C930e (046d:0843) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) |

### G-CTRL

| Camera | ds | mf |
| --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) |
| USB Video Device (1532:0e05) Kiyo | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) |
| USB Camera (4c4a:4a55) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) |
| Logitech Webcam C930e (046d:0843) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) |

### reliability

| Camera | ds_inproc | ds_modeswitch | ds_newproc | mf_inproc | mf_modeswitch | mf_newproc | opencv_inproc |
| --- | --- | --- | --- | --- | --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no**](W-CYC.json) |
| USB Video Device (1532:0e05) Kiyo | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no**](W-CYC.json) |
| USB Camera (4c4a:4a55) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no**](W-CYC.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no**](W-CYC.json) |

## Tests

| Test | Status | Elapsed | ETA was | Errors | JSON |
| --- | --- | --- | --- | --- | --- |
| W-MJPEG | ok | 1m28s | 2m01s | 0 | [W-MJPEG.json](W-MJPEG.json) |
| W-CYC | ok | 2m30s | 3m48s | 0 | [W-CYC.json](W-CYC.json) |
| W-TS | ok | 1m15s | 1m28s | 0 | [W-TS.json](W-TS.json) |
| W-CTRL-EFFECT | ok | 2m18s | 3m20s | 0 | [W-CTRL-EFFECT.json](W-CTRL-EFFECT.json) |
