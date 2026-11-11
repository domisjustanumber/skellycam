# Windows UVC suite run, Gerald, 20261106T224912Z

Mode: full (cycles 50, process cycles 15, frames 30, MJPEG 3.0 s per mode; streaming mode scope >= 30 fps and >= 720 lines). Elapsed 1h24m. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261106T224912Z`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261106T224912Z`.

Ratings use the plan section 3 thresholds (common/rating.py). Tier 1 = needs the one-time admin configuration (MetadataBufferSizeInKB0); everything else is tier 0. Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Tier-1 metadata | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- | --- |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | True | 2026-11-06T15:04:37.661901+00:00 | 2026-11-06T15:04:37.661901+00:00 |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | True | 2026-11-06T20:32:29.065252+00:00 | 2026-11-06T20:32:29.065252+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | False | 2026-11-06T22:26:45.172797+00:00 | **2026-11-07T00:10:45.653179+00:00** (re-arrived) |
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
| c922 Pro Stream Webcam (046d:085c) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) |
| USB Video Device (1532:0e05) Kiyo | [untested (device fault)](W-MJPEG.json) (gated) | [untested (device fault)](W-MJPEG.json) (gated) | [untested (device fault)](W-MJPEG.json) (gated) |
| USB Camera (4c4a:4a55) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) |
| Logitech Webcam C930e (046d:0843) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) |

### G-CTRL

| Camera | ds | mf |
| --- | --- | --- |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-CTRL-EFFECT.json) | [yes](W-CTRL-EFFECT.json) |
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
| all |  |  |  |  | [**no (cannot list without opening capture)**](W-FMT-NOGRAB.json) | [**no (cannot list without opening capture)**](W-FMT-NOGRAB.json) |

### kiyo

| Camera | all |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [**no**](W-KIYO.json) |

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

| Camera | Faulted since (UTC) | Test | Mode | Code / class | Plug-in age | Source | Now |
| --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | 2026-11-07T00:04:02.348704+00:00 | W-MULTI | - | 0x8007001F / device_error | 211.6 min | camcmd_scan | faulted |

First failed camera command per camera (any class):

- USB Camera (4c4a:4a55): 2026-11-07T00:00:28.873306+00:00 in W-MULTI, ds MJPG 1280x720@30 at open: 5 (other), plug-in age 93.7 min
- USB Video Device (1532:0e05) Kiyo: 2026-11-07T00:04:02.348704+00:00 in W-MULTI, mf  at control_get: 0x8007001F (device_error), plug-in age 211.6 min

Kiyo onset, USB Video Device (1532:0e05) Kiyo (W-KIYO background poller from 2026-11-06T22:49:12.339966+00:00, plug-in age at start 136.7 min):

- first unanswered control poll 2026-11-07T00:03:01.219341+00:00 during W-MULTI, plug-in age 210.5 min, codes []
- vendor processes at that poll: LogiTune.exe:16536, LogiTune.exe:18788, LogiTune.exe:26388, LogiTune.exe:34856, LogiTune.exe:35428, LogiTune.exe:39072, LogiTune.exe:41652, LogiTune.exe:42572, LogiTune.exe:42832, LogiTuneAgent.exe:3296, LogiTuneUpdater.exe:6532, RazerAppEngine.exe:11860, RazerAppEngine.exe:14228, RazerAppEngine.exe:20916, RazerAppEngine.exe:2452, RazerAppEngine.exe:37044, RazerAppEngine.exe:37240, RazerAppEngine.exe:37416, RazerAppEngine.exe:41092, RazerAppEngine.exe:43916, logioptionsplus_agent.exe:42752, logioptionsplus_appbroker.exe:11372, logioptionsplus_updater.exe:3496, razer_elevation_service.exe:22052
- 2026-11-07T00:03:01.219341+00:00 mf -> not_answering (during W-MULTI, plug-in age 210.5 min)
- 2026-11-07T00:03:42.508740+00:00 ds -> not_answering (during W-MULTI, plug-in age 210.5 min)
- first device fault: 2026-11-07T00:04:02.348704+00:00 in W-MULTI  (0x8007001F, device_error), plug-in age 211.6 min

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-POLICY | ok | 0m00s | 0m10s | 0 | - | [W-POLICY.json](W-POLICY.json) |
| W-TOPO | ok | 0m01s | 1m02s | 0 | - | [W-TOPO.json](W-TOPO.json) |
| W-ID | ok | 0m11s | 1m20s | 0 | - | [W-ID.json](W-ID.json) |
| W-FMT | ok | 0m02s | 0m34s | 0 | - | [W-FMT.json](W-FMT.json) |
| W-FMT-NOGRAB | ok | 2m45s | 3m03s | 0 | - | [W-FMT-NOGRAB.json](W-FMT-NOGRAB.json) |
| W-CTRL-LIST | ok | 0m03s | 0m34s | 0 | - | [W-CTRL-LIST.json](W-CTRL-LIST.json) |
| W-CYC | ok | 44m34s | 56m48s | 0 | - | [W-CYC.json](W-CYC.json) |
| W-CTRL-EFFECT | ok | 14m20s | 19m44s | 0 | - | [W-CTRL-EFFECT.json](W-CTRL-EFFECT.json) |
| W-TS | ok | 4m12s | 4m24s | 0 | - | [W-TS.json](W-TS.json) |
| W-MULTI | ok | 15m40s | 23m09s | 0 | - | [W-MULTI.json](W-MULTI.json) |
| W-MJPEG | ok | 2m19s | 5m11s | 0 | USB Video Device (1532:0e05) Kiyo | [W-MJPEG.json](W-MJPEG.json) |
| W-KIYO | ok (background) | 0m00s | 0m00s | 0 | - | [W-KIYO.json](W-KIYO.json) |
