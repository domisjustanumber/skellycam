# Windows UVC suite run, Gerald, 20261106T221040Z

Mode: quick (cycles 4, process cycles 2, frames 10, MJPEG 1.5 s per mode; streaming mode scope >= 30 fps and >= 720 lines). Elapsed 18m02s. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_build_selftest_20261106\scope_nograb_quick`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_build_selftest_20261106\scope_nograb_quick`.

Ratings use the plan section 3 thresholds (common/rating.py). Tier 1 = needs the one-time admin configuration (MetadataBufferSizeInKB0); everything else is tier 0. Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Tier-1 metadata | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- | --- |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | True | 2026-11-06T15:04:37.661901+00:00 | 2026-11-06T15:04:37.661901+00:00 |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | True | 2026-11-06T20:32:29.065252+00:00 | 2026-11-06T20:32:29.065252+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | False | 2026-11-06T21:19:13.117126+00:00 | **2026-11-06T22:26:45.172797+00:00** (re-arrived) |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/7` | Logitech Webcam C930e | 046d:0843 | HS | False | 2026-11-06T15:00:22.388177+00:00 | 2026-11-06T15:00:22.388177+00:00 |

## Ratings per goal, camera and API

### G-ID

| Camera | all |
| --- | --- |
| all | [partial (provisional: persistence not measured)](W-ID.json) |

### G-TS

| Camera | ds | ds:frame_index_fit | ds:pyav_pts | mf | mf:frame_index_fit | mf:mf_sample_time | mf:uvc_pts | mf:uvc_scr_stc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [partial](W-TS.json) (tier 1) | [untested](W-TS.json) | [**no**](W-TS.json) | [partial](W-TS.json) (tier 1) | [partial](W-TS.json) (tier 1) |
| USB Video Device (1532:0e05) Kiyo | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) (tier 1) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) (tier 1) | [untested](W-TS.json) (tier 1) |
| USB Camera (4c4a:4a55) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |  |  |
| Logitech Webcam C930e (046d:0843) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |  |  |

### G-MJPEG

| Camera | ds | mf | pyav_ds |
| --- | --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) |
| USB Video Device (1532:0e05) Kiyo | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) | [**no**](W-MJPEG.json) |
| USB Camera (4c4a:4a55) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) |
| Logitech Webcam C930e (046d:0843) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) | [partial](W-MJPEG.json) |

### G-CTRL

| Camera | ds | mf |
| --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) |
| USB Video Device (1532:0e05) Kiyo | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) |
| USB Camera (4c4a:4a55) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) |
| Logitech Webcam C930e (046d:0843) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) |

### reliability

| Camera | ds_inproc | ds_modeswitch | ds_newproc | mf_inproc | mf_modeswitch | mf_newproc | opencv_inproc | opencv_skellycam |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) |
| USB Video Device (1532:0e05) Kiyo | [partial (format mismatch)](W-CYC.json) | [partial (format mismatch)](W-CYC.json) | [partial (format mismatch)](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) |
| USB Camera (4c4a:4a55) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [yes](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) |

### G-BW

| Camera | all | ds | mf | pyav_ds |
| --- | --- | --- | --- | --- |
| all | [untested](W-TOPO.json) | [partial](W-MULTI.json) | [yes](W-MULTI.json) | [partial](W-MULTI.json) |

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
| all |  |  |  |  | [**no (needs a stream)**](W-FMT-NOGRAB.json) | [**no (needs a stream)**](W-FMT-NOGRAB.json) |

### kiyo

| Camera | all |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-KIYO.json) |

### ctrl_list_equivalence

| Camera | all |
| --- | --- |
| all | [yes](W-CTRL-LIST.json) |

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

Faults (0x8007001F / unreleasable reader / killed streaming command) gate a camera's streaming work from the next test on; each later test re-probes it once with a 1-frame MF capture. "(gated)" in a rating cell = the camera was faulted when that test started.

First failed camera command per camera (any class):

- USB Camera (4c4a:4a55): 2026-11-06T22:24:32.837848+00:00 in W-MULTI, ds MJPG 1280x720@30 at open: 5 (other), plug-in age 65.3 min

Kiyo onset, USB Video Device (1532:0e05) Kiyo (W-KIYO background poller from 2026-11-06T22:10:40.643418+00:00, plug-in age at start 98.2 min):

- answered every control poll so far (218 polls)

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-POLICY | ok | 0m00s | 0m10s | 0 | - | [W-POLICY.json](W-POLICY.json) |
| W-TOPO | ok | 0m01s | 1m02s | 0 | - | [W-TOPO.json](W-TOPO.json) |
| W-ID | ok | 0m04s | 1m20s | 0 | - | [W-ID.json](W-ID.json) |
| W-FMT | ok | 0m02s | 0m34s | 0 | - | [W-FMT.json](W-FMT.json) |
| W-FMT-NOGRAB | ok | 2m48s | 5m40s | 0 | - | [W-FMT-NOGRAB.json](W-FMT-NOGRAB.json) |
| W-CTRL-LIST | ok | 0m03s | 0m34s | 0 | - | [W-CTRL-LIST.json](W-CTRL-LIST.json) |
| W-CYC | ok | 3m51s | 5m57s | 0 | - | [W-CYC.json](W-CYC.json) |
| W-CTRL-EFFECT | ok | 3m46s | 6m00s | 0 | - | [W-CTRL-EFFECT.json](W-CTRL-EFFECT.json) |
| W-TS | ok | 1m16s | 1m28s | 0 | - | [W-TS.json](W-TS.json) |
| W-MULTI | ok | 4m45s | 6m22s | 0 | - | [W-MULTI.json](W-MULTI.json) |
| W-MJPEG | ok | 1m20s | 1m47s | 0 | - | [W-MJPEG.json](W-MJPEG.json) |
| W-KIYO | ok (background) | 0m00s | 0m00s | 0 | - | [W-KIYO.json](W-KIYO.json) |
