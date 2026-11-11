# Windows UVC suite run, Gerald, 20261111T040003Z

Mode: full (W-CYC profile reliability, cycles 50, process cycles 15, frames 30, MJPEG 3.0 s per mode; streaming mode scope exactly 720 lines at >= 30 fps). Elapsed 5h24m. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261111T040003Z`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261111T040003Z`.

Ratings use the plan section 3 thresholds (common/rating.py), on tier-0 data only (the cameras as found; no UVC PTS/SCR, Dom 2026-11-09). Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | 2026-11-10T22:07:35.509176+00:00 | 2026-11-10T22:07:35.509176+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/8` | Logitech Webcam C930e | 046d:0843 | HS | 2026-11-10T22:07:46.470029+00:00 | 2026-11-10T22:07:46.470029+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | 2026-11-09T21:34:51.037086+00:00 | **2026-11-11T07:00:52.872268+00:00** (re-arrived) |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | 2026-11-09T21:34:51.119106+00:00 | 2026-11-09T21:34:51.119106+00:00 |

## USB link at run start

| Camera | Speed | bcdUSB | Port protocols | Plug-in age at start | Last arrival |
| --- | --- | --- | --- | --- | --- |
| USB Video Device (Kiyo) | SS | 0320 | usb3 | 352.5 min | 2026-11-10T22:07:35.509176+00:00 |
| Logitech Webcam C930e | HS | 0200 | usb1.1, usb2.0 | 352.3 min | 2026-11-10T22:07:46.470029+00:00 |
| USB Camera | HS | 0200 | usb1.1, usb2.0 | 1825.2 min | 2026-11-09T21:34:51.037086+00:00 |
| c922 Pro Stream Webcam | HS | 0200 | usb1.1, usb2.0 | 1825.2 min | 2026-11-09T21:34:51.119106+00:00 |

## Ratings per goal, camera and API

### G-ID

| Camera | all |
| --- | --- |
| all | [partial (provisional: persistence not measured)](W-ID.json) |

### G-TS

| Camera | ds | ds:frame_index_fit | ds:pyav_pts | ds_ffmpeg | ds_ffmpeg:ffmpeg_pts | ds_ffmpeg:frame_index_fit | mf | mf:frame_index_fit | mf:mf_sample_time |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |
| Logitech Webcam C930e (046d:0843) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |
| USB Camera (4c4a:4a55) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |
| c922 Pro Stream Webcam (046d:085c) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [untested](W-TS.json) | [**no**](W-TS.json) |

### G-MJPEG

| Camera | ds | mf | pyav_ds |
| --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes (in-scope modes; rate not honoured in 1)](W-MJPEG.json) | [yes (in-scope modes; rate not honoured in 1)](W-MJPEG.json) | [**no**](W-MJPEG.json) |
| Logitech Webcam C930e (046d:0843) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) |
| USB Camera (4c4a:4a55) | [yes (in-scope modes; rate not honoured in 1)](W-MJPEG.json) | [yes (in-scope modes; rate not honoured in 1)](W-MJPEG.json) | [yes (in-scope modes; rate not honoured in 1)](W-MJPEG.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) | [yes (in-scope modes)](W-MJPEG.json) |

### G-RAW

| Camera | ffmpeg | mf | ocv_dshow | ocv_msmf | pyav |
| --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-RAW.json) | [yes](W-RAW.json) | [**no (no raw frames in the requested format)**](W-RAW.json) | [partial](W-RAW.json) | [yes](W-RAW.json) |
| Logitech Webcam C930e (046d:0843) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) |
| USB Camera (4c4a:4a55) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) |
| c922 Pro Stream Webcam (046d:085c) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) | [untested (no raw mode in scope)](W-RAW.json) |

### G-CTRL

| Camera | ds | mf | opencv_dshow | opencv_msmf |
| --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-CTRL-EFFECT.json) | [yes](W-CTRL-EFFECT.json) | [partial](W-OCV-CTRL.json) | [partial](W-OCV-CTRL.json) |
| Logitech Webcam C930e (046d:0843) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) | [partial](W-OCV-CTRL.json) | [partial](W-OCV-CTRL.json) |
| USB Camera (4c4a:4a55) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) | [yes](W-OCV-CTRL.json) | [partial](W-OCV-CTRL.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-CTRL-EFFECT.json) | [yes](W-CTRL-EFFECT.json) | [partial](W-OCV-CTRL.json) | [partial](W-OCV-CTRL.json) |

### G-CTRL-AUTO

| Camera | ds-ae | ds-af | mf-ae | mf-af | opencv_dshow-ae | opencv_dshow-af | opencv_msmf-ae | opencv_msmf-af |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [partial](W-AUTO.json) | [untested (inconclusive)](W-AUTO.json) | [partial](W-AUTO.json) | [untested (inconclusive)](W-AUTO.json) | [untested (inconclusive)](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [untested (inconclusive)](W-OCV-CTRL.json) | [untested (inconclusive)](W-OCV-CTRL.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-AUTO.json) | [yes](W-AUTO.json) | [yes](W-AUTO.json) | [yes](W-AUTO.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) |
| USB Camera (4c4a:4a55) | [yes](W-AUTO.json) | [untested (n/a)](W-AUTO.json) | [yes](W-AUTO.json) | [untested (n/a)](W-AUTO.json) | [yes](W-OCV-CTRL.json) | [untested (n/a)](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [untested (n/a)](W-OCV-CTRL.json) |
| c922 Pro Stream Webcam (046d:085c) | [partial](W-AUTO.json) | [yes](W-AUTO.json) | [partial](W-AUTO.json) | [yes](W-AUTO.json) | [yes](W-OCV-CTRL.json) | [**no (flag only)**](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) |

### reliability

| Camera | ds_ffmpeg_inproc | ds_inproc | ds_modeswitch | ds_newproc | mf_inproc | mf_modeswitch | mf_newproc | opencv_inproc | opencv_skellycam | opencv_skellycam_fps30 | pymf_inproc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-CYC-KIYO.json) | [partial (format mismatch; rate < 90% of requested in 50/50)](W-CYC-KIYO.json) | [partial (format mismatch; rate < 90% of requested in 25/25)](W-CYC-KIYO.json) | [partial (format mismatch; rate < 90% of requested in 15/15)](W-CYC-KIYO.json) | [yes](W-CYC-KIYO.json) | [yes (point estimate; n=25, Wilson lower 0.867; rate < 90% of requested in 12/25)](W-CYC-KIYO.json) | [partial (n too small for a 99 % claim: 100 cycles; Wilson lower 0.963)](W-CYC-KIYO.json) | [**no (latency)**](W-CYC-KIYO.json) | [**no (latency)**](W-CYC-KIYO.json) | [**no (latency)**](W-CYC-KIYO.json) | [yes (point estimate; n=60, Wilson lower 0.940)](W-PYMF.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-CYC.json) | [yes (point estimate; n=50, Wilson lower 0.929)](W-CYC.json) |  | [yes (point estimate; n=15, Wilson lower 0.796)](W-CYC.json) | [yes](W-CYC.json) |  | [partial (n too small for a 99 % claim: 100 cycles; Wilson lower 0.963)](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes (point estimate; n=60, Wilson lower 0.940)](W-PYMF.json) |
| USB Camera (4c4a:4a55) | [yes (rate < 90% of requested in 400/400)](W-CYC.json) | [yes (point estimate; n=50, Wilson lower 0.929; rate < 90% of requested in 50/50)](W-CYC.json) |  | [yes (point estimate; n=15, Wilson lower 0.796; rate < 90% of requested in 15/15)](W-CYC.json) | [yes (rate < 90% of requested in 400/400)](W-CYC.json) |  | [partial (n too small for a 99 % claim: 100 cycles; Wilson lower 0.963; rate < 90% of requested in 100/100)](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [untested](W-PYMF.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-CYC.json) | [yes (point estimate; n=50, Wilson lower 0.929)](W-CYC.json) | [yes (point estimate; n=25, Wilson lower 0.867)](W-CYC.json) | [yes (point estimate; n=15, Wilson lower 0.796)](W-CYC.json) | [yes](W-CYC.json) | [yes (point estimate; n=25, Wilson lower 0.867)](W-CYC.json) | [partial (n too small for a 99 % claim: 100 cycles; Wilson lower 0.963)](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes (point estimate; n=60, Wilson lower 0.940)](W-PYMF.json) |

### pymf_equivalence

| Camera | all | pymf |
| --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo |  | [yes](W-PYMF.json) |
| Logitech Webcam C930e (046d:0843) |  | [yes](W-PYMF.json) |
| USB Camera (4c4a:4a55) |  | [partial (cycles untested)](W-PYMF.json) |
| c922 Pro Stream Webcam (046d:085c) |  | [yes](W-PYMF.json) |
| all | [partial (4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2 untested: device fault)](W-PYMF.json) |  |

### G-BW

| Camera | all | ds | mf | pyav_ds |
| --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [untested](W-MULTI.json) |  |  |  |
| all | [untested](W-TOPO.json) | [partial](W-MULTI.json) | [yes](W-MULTI.json) | [partial](W-MULTI.json) |

### fmt_equivalence

| Camera | all |
| --- | --- |
| all | [yes](W-FMT.json) |

### fmt_nograb

| Camera | ds | ffmpeg | hub_ioctl | mf | opencv | winrt |
| --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-FMT-NOGRAB.json) | [**no (incomplete)**](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) |  |  |
| Logitech Webcam C930e (046d:0843) | [yes](W-FMT-NOGRAB.json) | [**no (incomplete)**](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) |  |  |
| USB Camera (4c4a:4a55) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) |  |  |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-FMT-NOGRAB.json) | [**no (incomplete)**](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) | [yes](W-FMT-NOGRAB.json) |  |  |
| all |  |  |  |  | [**no (cannot list without opening capture)**](W-FMT-NOGRAB.json) | [**no (cannot list without opening capture)**](W-FMT-NOGRAB.json) |

### list_touch

| Camera | ffmpeg_list_devices | ffmpeg_list_options | pyav_list_devices | pyav_list_options |
| --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo |  | [partial (touches but harmless)](W-PYAV-LIST.json) (gated) |  | [partial (touches but harmless)](W-PYAV-LIST.json) (gated) |
| Logitech Webcam C930e (046d:0843) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |
| USB Camera (4c4a:4a55) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |
| c922 Pro Stream Webcam (046d:085c) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |
| all | [partial (touches but harmless)](W-PYAV-LIST.json) |  | [partial (touches but harmless)](W-PYAV-LIST.json) |  |

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
| USB Camera (4c4a:4a55) | 2026-11-11T04:25:20.502643+00:00 | W-PYMF | MJPG 1280x720@30 | timeout / unreleasable | 1850.5 min | W-PYMF | recovered 2026-11-11T04:27:39.822887+00:00 |
| USB Video Device (1532:0e05) Kiyo | 2026-11-11T06:53:23.737209+00:00 | W-MULTI | MJPG 1280x720@30 | watchdog timeout / hang | 525.8 min | W-MULTI multi_launch child | faulted |

First device-level failed camera command per camera (open / stream error, timeout, 0x8007001F; a helper exit for a format / rate mismatch with every cycle streamed is not one):

- USB Camera (4c4a:4a55): 2026-11-11T04:23:56.540999Z in W-PYMF, mf MJPG 1280x720@30 at None: 4 (None), plug-in age 1849.7 min
- c922 Pro Stream Webcam (046d:085c): 2026-11-11T06:48:16.337307+00:00 in W-MULTI, mf MJPG 1280x720@30 at first_sample: 0x800718CF (bandwidth_certain), plug-in age 1993.5 min
- USB Video Device (1532:0e05) Kiyo: 2026-11-11T06:52:46.943415+00:00 in W-MULTI, ds MJPG 1280x720@30 at open: timeout (device_not_ready), plug-in age 525.7 min

Earlier non-device failures (the command streamed; its own format / rate checks failed):

- USB Video Device (1532:0e05) Kiyo: 2026-11-11T06:34:51.782329+00:00 in W-CYC-KIYO, opencv MJPG 1280x720@30: exit 4
- Logitech Webcam C930e (046d:0843): 2026-11-11T07:51:22.994477+00:00 in W-CYC, opencv MJPG 1280x720@30: exit 4

Kiyo onset, USB Video Device (1532:0e05) Kiyo (W-KIYO background poller from 2026-11-11T04:00:04.015563+00:00, plug-in age at start 352.5 min):

- first unanswered control poll 2026-11-11T06:53:17.540569Z during W-MULTI, plug-in age 525.7 min, codes []
- vendor processes at that poll: razer_elevation_service.exe:42144
- 2026-11-11T06:53:17.540569Z mf -> not_answering (during W-MULTI, plug-in age 525.7 min)
- 2026-11-11T06:53:23.836517Z ds -> not_answering (during W-MULTI, plug-in age 525.8 min)
- first device fault: 2026-11-11T06:53:23.737209+00:00 in W-MULTI MJPG 1280x720@30 (watchdog timeout, hang), plug-in age 525.8 min

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-POLICY | ok | 0m00s | 0m10s | 0 | - | [W-POLICY.json](W-POLICY.json) |
| W-TOPO | ok | 0m01s | 1m02s | 0 | - | [W-TOPO.json](W-TOPO.json) |
| W-ID | ok | 0m13s | 1m20s | 0 | - | [W-ID.json](W-ID.json) |
| W-FMT | ok | 0m02s | 0m34s | 0 | - | [W-FMT.json](W-FMT.json) |
| W-FMT-NOGRAB | ok | 3m20s | 3m55s | 0 | - | [W-FMT-NOGRAB.json](W-FMT-NOGRAB.json) |
| W-CTRL-LIST | ok | 0m02s | 0m34s | 0 | - | [W-CTRL-LIST.json](W-CTRL-LIST.json) |
| W-MJPEG | ok | 2m46s | 3m22s | 0 | - | [W-MJPEG.json](W-MJPEG.json) |
| W-RAW | ok | 3m10s | 5m43s | 0 | - | [W-RAW.json](W-RAW.json) |
| W-TS | ok | 6m22s | 7m12s | 0 | - | [W-TS.json](W-TS.json) |
| W-PYMF | ok | 11m32s | 18m47s | 0 | - | [W-PYMF.json](W-PYMF.json) |
| W-CTRL-EFFECT | ok | 14m00s | 19m44s | 0 | - | [W-CTRL-EFFECT.json](W-CTRL-EFFECT.json) |
| W-AUTO | ok | 24m26s | 34m12s | 0 | - | [W-AUTO.json](W-AUTO.json) |
| W-OCV-CTRL | ok | 34m50s | 41m36s | 0 | - | [W-OCV-CTRL.json](W-OCV-CTRL.json) |
| W-CYC-KIYO | ok | 1h06m | 1h24m | 0 | - | [W-CYC-KIYO.json](W-CYC-KIYO.json) |
| W-MULTI | ok | 13m28s | 23m09s | 0 | - | [W-MULTI.json](W-MULTI.json) |
| W-PYAV-LIST | ok | 7m17s | 5m20s | 0 | USB Video Device (1532:0e05) Kiyo | [W-PYAV-LIST.json](W-PYAV-LIST.json) |
| W-CYC | ok | 2h16m | 2h49m | 0 | USB Video Device (1532:0e05) Kiyo | [W-CYC.json](W-CYC.json) |
| W-KIYO | ok (background) | 0m03s | 0m00s | 0 | - | [W-KIYO.json](W-KIYO.json) |
