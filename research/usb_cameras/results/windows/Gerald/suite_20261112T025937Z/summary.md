# Windows UVC suite run, Gerald, 20261112T025937Z

Mode: full (W-CYC profile reliability, cycles 50, process cycles 15, frames 30, MJPEG 3.0 s per mode; streaming mode scope exactly 720 lines at >= 30 fps). Elapsed 5h10m. Results folder: `C:\Users\Dom\GitHub\freemocap\skellycam\research\usb_cameras\results\windows\Gerald\suite_20261112T025937Z`. Raw frames: `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_20261112T025937Z`.

Ratings use the plan section 3 thresholds (common/rating.py), on tier-0 data only (the cameras as found; no UVC PTS/SCR, Dom 2026-11-09). Each cell links to the JSON with the criteria and evidence. A camera x API aggregate cell (e.g. G-TS without a route suffix) shows the best available route, and 'untested' ranks above 'no' there by design (an unscored route may still work); the per-route cells hold the measured ratings. '(gated)' = skipped by the device-fault gate.

## Cameras

| Key | Name | VID:PID | Speed | Last arrival (discovery) | Last arrival (latest check) |
| --- | --- | --- | --- | --- | --- |
| `1532:0e05:port=PCIROOT(0)#PCI(1C04)#PCI(0000)#PCI(0200)#PCI(0000)#USBROOT(0)/4.4` | USB Video Device (Kiyo) | 1532:0e05 | SS | 2026-11-11T23:27:22.817345+00:00 | 2026-11-11T23:27:22.817345+00:00 |
| `046d:0843:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/8` | Logitech Webcam C930e | 046d:0843 | HS | 2026-11-11T14:11:38.552007+00:00 | 2026-11-11T14:11:38.552007+00:00 |
| `4c4a:4a55:port=PCIROOT(0)#PCI(1400)#USBROOT(0)/13.1.2` | USB Camera | 4c4a:4a55 | HS | 2026-11-11T14:11:44.546053+00:00 | **2026-11-12T07:09:33.309147+00:00** (re-arrived) |
| `046d:085c:sn=C922SN01` | c922 Pro Stream Webcam | 046d:085c | HS | 2026-11-12T00:57:22.463265+00:00 | 2026-11-12T00:57:22.463265+00:00 |

## USB link at run start

| Camera | Speed | bcdUSB | Port protocols | Plug-in age at start | Last arrival |
| --- | --- | --- | --- | --- | --- |
| USB Video Device (Kiyo) | SS | 0320 | usb3 | 212.2 min | 2026-11-11T23:27:22.817345+00:00 |
| Logitech Webcam C930e | HS | 0200 | usb1.1, usb2.0 | 768.0 min | 2026-11-11T14:11:38.552007+00:00 |
| USB Camera | HS | 0200 | usb1.1, usb2.0 | 767.9 min | 2026-11-11T14:11:44.546053+00:00 |
| c922 Pro Stream Webcam | HS | 0200 | usb1.1, usb2.0 | 122.2 min | 2026-11-12T00:57:22.463265+00:00 |

## Ratings per goal, camera and API

### G-ID

| Camera | all |
| --- | --- |
| all | [partial](W-ID.json) |

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
| USB Video Device (1532:0e05) Kiyo | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) | [partial](W-OCV-CTRL.json) | [partial](W-OCV-CTRL.json) |
| Logitech Webcam C930e (046d:0843) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) | [partial](W-OCV-CTRL.json) | [partial](W-OCV-CTRL.json) |
| USB Camera (4c4a:4a55) | [partial](W-CTRL-EFFECT.json) | [partial](W-CTRL-EFFECT.json) | [yes](W-OCV-CTRL.json) | [partial](W-OCV-CTRL.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-CTRL-EFFECT.json) | [yes](W-CTRL-EFFECT.json) | [partial](W-OCV-CTRL.json) | [partial](W-OCV-CTRL.json) |

### G-CTRL-NODRIFT

| Camera | mf |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-NODRIFT.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-NODRIFT.json) |
| USB Camera (4c4a:4a55) | [yes](W-NODRIFT.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-NODRIFT.json) |

### G-CTRL-AUTO

| Camera | opencv_dshow-ae | opencv_dshow-af | opencv_msmf-ae | opencv_msmf-af |
| --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [untested (inconclusive)](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [untested (inconclusive)](W-OCV-CTRL.json) | [untested (inconclusive)](W-OCV-CTRL.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) |
| USB Camera (4c4a:4a55) | [yes](W-OCV-CTRL.json) | [untested (n/a)](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [untested (n/a)](W-OCV-CTRL.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) | [yes](W-OCV-CTRL.json) |

### reliability

| Camera | ds_ffmpeg_inproc | ds_inproc | ds_modeswitch | ds_newproc | mf_inproc | mf_modeswitch | mf_newproc | opencv_inproc | opencv_skellycam | opencv_skellycam_fps30 | pymf_inproc |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [untested (pre-existing fault)](W-CYC-KIYO.json) (gated) | [yes (point estimate; n=60, Wilson lower 0.940)](W-PYMF.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-CYC.json) | [yes (point estimate; n=50, Wilson lower 0.929)](W-CYC.json) |  | [yes (point estimate; n=15, Wilson lower 0.796)](W-CYC.json) | [yes](W-CYC.json) |  | [yes](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes (point estimate; n=60, Wilson lower 0.940)](W-PYMF.json) |
| USB Camera (4c4a:4a55) | [yes (rate < 90% of requested in 400/400)](W-CYC.json) | [yes (point estimate; n=50, Wilson lower 0.929; rate < 90% of requested in 50/50)](W-CYC.json) |  | [yes (point estimate; n=15, Wilson lower 0.796; rate < 90% of requested in 15/15)](W-CYC.json) | [yes (rate < 90% of requested in 400/400)](W-CYC.json) |  | [partial (99 % not shown at the Wilson lower bound over 400 cycles; Wilson lower 0.978; rate < 90% of requested in 397/397)](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes (point estimate; n=60, Wilson lower 0.940)](W-PYMF.json) |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-CYC.json) | [yes (point estimate; n=50, Wilson lower 0.929)](W-CYC.json) | [yes (point estimate; n=25, Wilson lower 0.867)](W-CYC.json) | [yes (point estimate; n=15, Wilson lower 0.796)](W-CYC.json) | [yes](W-CYC.json) | [yes (point estimate; n=25, Wilson lower 0.867)](W-CYC.json) | [yes](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [**no (latency)**](W-CYC.json) | [yes (point estimate; n=60, Wilson lower 0.940)](W-PYMF.json) |

### pymf_equivalence

| Camera | all | pymf |
| --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo |  | [yes](W-PYMF.json) |
| Logitech Webcam C930e (046d:0843) |  | [yes](W-PYMF.json) |
| USB Camera (4c4a:4a55) |  | [yes](W-PYMF.json) |
| c922 Pro Stream Webcam (046d:085c) |  | [yes](W-PYMF.json) |
| all | [partial (control sets on a streaming source not tested through pymf)](W-PYMF.json) |  |

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

### kiyo

| Camera | all |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [**no**](W-KIYO.json) |

### T-BUMP

| Camera | all |
| --- | --- |
| recording | [untested](W-TBUMP.json) |

### ctrl_list_equivalence

| Camera | all |
| --- | --- |
| all | [yes](W-CTRL-LIST.json) |

### fps_ceiling

| Camera | 1280x720_30 | 1280x720_60 |
| --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [**no**](W-GAIN.json) | [**no**](W-GAIN.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-GAIN.json) |  |
| USB Camera (4c4a:4a55) | [untested (units unknown)](W-GAIN.json) |  |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-GAIN.json) | [**no**](W-GAIN.json) |

### gain_grid

| Camera | 1280x720_30 | 1280x720_60 |
| --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-GAIN.json) | [yes](W-GAIN.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-GAIN.json) |  |
| USB Camera (4c4a:4a55) | [yes](W-GAIN.json) |  |
| c922 Pro Stream Webcam (046d:085c) | [yes](W-GAIN.json) | [yes](W-GAIN.json) |

### gain_rule

| Camera | 1280x720_30 | 1280x720_60 |
| --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [untested (inconclusive)](W-GAIN.json) | [untested (inconclusive)](W-GAIN.json) |
| Logitech Webcam C930e (046d:0843) | [partial](W-GAIN.json) |  |
| USB Camera (4c4a:4a55) | [partial](W-GAIN.json) |  |
| c922 Pro Stream Webcam (046d:085c) | [partial](W-GAIN.json) | [**no**](W-GAIN.json) |

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

### pymf_in_use

| Camera | all |
| --- | --- |
| Logitech Webcam C930e (046d:0843) | [yes](W-PYMF-ALL.json) |

### pymf_multi

| Camera | 720p30 | 720p60 | all |
| --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | [partial (1 criteria)](W-PYMF-ALL.json) | [partial (2 criteria)](W-PYMF-ALL.json) |  |
| Logitech Webcam C930e (046d:0843) | [yes](W-PYMF-ALL.json) | [untested (scope)](W-PYMF-ALL.json) |  |
| USB Camera (4c4a:4a55) | [partial (1 criteria)](W-PYMF-ALL.json) | [untested (scope)](W-PYMF-ALL.json) |  |
| c922 Pro Stream Webcam (046d:085c) | [untested (refused)](W-PYMF-ALL.json) | [yes](W-PYMF-ALL.json) |  |
| all |  |  | [partial](W-PYMF-ALL.json) |

### pymf_streaming_set

| Camera | exposure |
| --- | --- |
| USB Video Device (1532:0e05) Kiyo | [yes](W-PYMF-ALL.json) |
| Logitech Webcam C930e (046d:0843) | [yes](W-PYMF-ALL.json) |
| USB Camera (4c4a:4a55) | [partial (ROI luma moved in the expected direction after each set)](W-PYMF-ALL.json) |
| c922 Pro Stream Webcam (046d:085c) | [untested](W-PYMF-ALL.json) |

## Device faults, first failures and the Kiyo onset

Faults (0x8007001F / unreleasable reader / killed streaming command) gate a camera's streaming work from the next test on; each later test re-probes it once with a 1-frame MF capture. "(gated)" in a rating cell = the camera was faulted when that test started.

| Camera | Faulted since (UTC) | Test | Mode | Code / class | Plug-in age | Source | Now |
| --- | --- | --- | --- | --- | --- | --- | --- |
| USB Video Device (1532:0e05) Kiyo | 2026-11-12T05:46:24.269472+00:00 | W-MULTI | MJPG 1280x720@30 | watchdog timeout / hang | 379.0 min | W-MULTI multi_launch child | faulted |
| USB Camera (4c4a:4a55) | 2026-11-12T07:09:33.238324+00:00 | W-CYC | MJPG 1280x720@30 | 0x8007001F / device_error | 1017.8 min | camcmd_scan | recovered 2026-11-12T07:18:38.697559+00:00 |

First device-level failed camera command per camera (open / stream error, timeout, 0x8007001F; a helper exit for a format / rate mismatch with every cycle streamed is not one):

- c922 Pro Stream Webcam (046d:085c): 2026-11-12T05:40:51.387999+00:00 in W-MULTI, mf MJPG 1280x720@30 at first_sample: 0x800718CF (bandwidth_certain), plug-in age 283.6 min
- USB Camera (4c4a:4a55): 2026-11-12T05:44:42.097467+00:00 in W-MULTI, ds MJPG 1280x720@30 at open: OSError(5) (bandwidth_probable), plug-in age 4.8 min
- USB Video Device (1532:0e05) Kiyo: 2026-11-12T05:45:47.327610+00:00 in W-MULTI, ds MJPG 1280x720@30 at open: timeout (device_not_ready), plug-in age 378.9 min

Earlier non-device failures (the command streamed; its own format / rate checks failed):

- Logitech Webcam C930e (046d:0843): 2026-11-12T06:37:23.572736+00:00 in W-CYC, opencv MJPG 1280x720@30: exit 4

Kiyo onset, USB Video Device (1532:0e05) Kiyo (W-KIYO background poller from 2026-11-12T02:59:37.301889+00:00, plug-in age at start 212.2 min):

- first unanswered control poll 2026-11-12T05:46:18.002183Z during W-MULTI, plug-in age 378.9 min, codes []
- 2026-11-12T05:46:18.002183Z mf -> not_answering (during W-MULTI, plug-in age 378.9 min)
- 2026-11-12T05:46:24.465224Z ds -> not_answering (during W-MULTI, plug-in age 379.0 min)
- first device fault: 2026-11-12T05:46:24.269472+00:00 in W-MULTI MJPG 1280x720@30 (watchdog timeout, hang), plug-in age 379.0 min

## Tests

| Test | Status | Elapsed | ETA was | Errors | Gated (faulted at start) | JSON |
| --- | --- | --- | --- | --- | --- | --- |
| W-ENV | ok | 0m00s | 0m20s | 0 | - | [W-ENV.json](W-ENV.json) |
| W-POLICY | ok | 0m00s | 0m10s | 0 | - | [W-POLICY.json](W-POLICY.json) |
| W-TOPO | ok | 0m01s | 1m02s | 0 | - | [W-TOPO.json](W-TOPO.json) |
| W-ID | ok | 0m12s | 1m20s | 0 | - | [W-ID.json](W-ID.json) |
| W-FMT | ok | 0m01s | 0m34s | 0 | - | [W-FMT.json](W-FMT.json) |
| W-FMT-NOGRAB | ok | 3m17s | 3m55s | 0 | - | [W-FMT-NOGRAB.json](W-FMT-NOGRAB.json) |
| W-CTRL-LIST | ok | 0m02s | 0m34s | 0 | - | [W-CTRL-LIST.json](W-CTRL-LIST.json) |
| W-MJPEG | ok | 2m23s | 3m22s | 0 | - | [W-MJPEG.json](W-MJPEG.json) |
| W-RAW | ok | 2m46s | 5m43s | 0 | - | [W-RAW.json](W-RAW.json) |
| W-TS | ok | 6m22s | 7m12s | 0 | - | [W-TS.json](W-TS.json) |
| W-PYMF | ok | 11m22s | 18m47s | 0 | - | [W-PYMF.json](W-PYMF.json) |
| W-PYMF-ALL | ok | 13m54s | 16m48s | 0 | - | [W-PYMF-ALL.json](W-PYMF-ALL.json) |
| W-NODRIFT | ok | 45m19s | 48m36s | 0 | - | [W-NODRIFT.json](W-NODRIFT.json) |
| W-GAIN | ok | 33m03s | 50m42s | 0 | - | [W-GAIN.json](W-GAIN.json) |
| W-CTRL-EFFECT | ok | 13m45s | 19m44s | 0 | - | [W-CTRL-EFFECT.json](W-CTRL-EFFECT.json) |
| W-OCV-CTRL | ok | 26m17s | 41m36s | 0 | - | [W-OCV-CTRL.json](W-OCV-CTRL.json) |
| W-TBUMP | ok (with errors) | 1m36s | 6m00s | 2 | - | [W-TBUMP.json](W-TBUMP.json) |
| W-MULTI | ok | 12m16s | 23m09s | 0 | - | [W-MULTI.json](W-MULTI.json) |
| W-PYAV-LIST | skipped (Kiyo Pro dead) | 0m00s | 5m20s | 1 | USB Video Device (1532:0e05) Kiyo | [W-PYAV-LIST.json](W-PYAV-LIST.json) |
| W-CYC-KIYO | ok | 0m00s | 1h45m | 0 | USB Video Device (1532:0e05) Kiyo | [W-CYC-KIYO.json](W-CYC-KIYO.json) |
| W-CYC | ok | 2h18m | 3h31m | 0 | USB Video Device (1532:0e05) Kiyo | [W-CYC.json](W-CYC.json) |
| W-KIYO | ok (background) | 0m00s | 0m00s | 0 | - | [W-KIYO.json](W-KIYO.json) |

## First errors per test

- W-TBUMP: `{"run": "baseline", "stage": "connect", "error": {"stage": "connect", "class": "api_error", "message": "group/apply failed: HTTP 500 Camera config for b395 must be an instance of CameraConfig, got <class 'NoneType'> instead."}}`
- W-TBUMP: `{"run": "head", "stage": "connect", "error": {"stage": "connect", "class": "api_error", "message": "group/apply failed: HTTP 500 Camera config for b395 must be an instance of CameraConfig, got <class 'NoneType'> instead."}}`
- W-PYAV-LIST: `{"runner_error": "untested: a Kiyo Pro is dead (dead rule: this test would reach it)"}`
