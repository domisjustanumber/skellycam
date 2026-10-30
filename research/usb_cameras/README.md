# USB camera investigation harness

Test harnesses backing the report "Low-cost USB cameras: MJPEG, timing, bandwidth, naming, cross-platform".
Every claim in the report cites a result file under `results/`.

## Method comparison (2026-10-30)

How each capture method tested so far scores against the study's goals and the must-haves for any adopted
solution. Every cell was checked against the result files by an extractor agent and an adversarial verifier
(workflow `wf_30cb7742-77f`, script `workflows/goal-matrix-and-gap-plan-wf_30cb7742-77f.js`). The full matrix,
with evidence paths and notes for every cell, is in
`results/agent_reports/goal_matrix_gap_plan_wf_30cb7742-77f.json`. The tests that fill the gaps are in
[docs/test_gap_plan.md](docs/test_gap_plan.md).

**Goals** (numbered as in the current brief; REPORT.md uses the older order 1 MJPEG, 2 timing, 3 bandwidth, 4 naming, 5 cross-platform):

- **G1 Sync:** does the method tighten *when light hits the sensor* across cameras, i.e. align exposures?
- **G2 Timestamp:** does it give a per-frame time close to when light hit the sensor?
- **G3 MJPEG:** does it return the camera's own JPEG bytes, with no decode or re-encode?
- **G4 ID:** does it expose, or map to, a unique, stable camera identity (USB serial, else physical port)?
- **G5 Bandwidth:** can the app choose the USB isochronous allocation (alt setting), so more cameras fit on a link?
- **Must-haves:** **M1** exposure / shutter control, **M2** format control (resolution, fps, pixel format),
  **M3** focus control.

**Legend:** **Yes** / **Part.** (partial) / **No** / **?** (not tested) / — (does not apply).
(m) = measured on the Windows test machine "Gerald"; (i) = inferred from source code or docs, not run.
Cameras measured: Logitech C922, Logitech C930e and a generic 4C4A:4A55; WinUSB rows are C930e only.
"Floor" = the ~0.5 ms limit of the monitor-flash ground truth, so the true error is at most that, not known.

### Windows, normal camera driver (usbvideo.sys)

| Method | G1 Sync | G2 Timestamp | G3 MJPEG | G4 ID | G5 Bandwidth | M1 Exposure | M2 Format | M3 Focus | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| OpenCV `CAP_DSHOW` (skellycam today) | No (i) | No: host time after `read()` only (m) | No: always BGR, 25–40% of a core (m) | Part.: opens by index; indices changed (m) | No (m) | Part.: only via separate DS `IAMCameraControl`, readback only (m) | Part.: MJPG only if size is set before FOURCC (m) | ? | Status quo; baseline only |
| OpenCV `CAP_MSMF` | No (i) | No: synthetic 33.333 ms steps (m) | No: BGR/NV12, 46–156% of a core (m) | Part.: index (m) | No (m) | Part.: DS side channel (m) | Part.: generic camera padded with repeats (m) | ? | Rejected: 39–41 s to open |
| **Media Foundation `IMFSourceReader`, native MJPG + UVC metadata** | No (i) | **Part.: C922 UVC PTS ≤ 0.5 ms (floor), needs admin registry value; OS time 4.4 ms** (m) | **Yes**: 0.7–2.2% of a core (m) | **Yes**: symlink → serial/port key (m) | No: max alt always granted (m) | Part.: applied on C922; C930e 1 of 5 runs (m) | **Yes** (m) | ? (read only) | **Best Windows path** |
| **PyAV / FFmpeg DirectShow `vcodec=mjpeg`** | No (i) | No: synthesized timestamps (m) | **Yes**: bytes identical to MF (m) | **Yes**: opens by `@device_pnp_` path → key (m) | No (m) | Part.: no PyAV API; DS side channel, readback only (m) | **Yes** (m) | ? | Pure-Python fallback |
| WinRT `MediaFrameReader` | No (i) | No: 16 ms grid (m) | No: MJPG subtype fails (m) | Yes (i) | No (i) | ? | Part.: NV12 only (m) | ? | Rejected |
| GStreamer `mfvideosrc` | No (i) | No: arrival time, 16 ms grid (m) | Yes (m) | Yes: device-path = MF symlink (m) | No (i) | No: no control API (i) | Yes, 720p30 only tried (m) | No: no control API (i) | Wrapper; nothing beyond raw MF |
| GStreamer `ksvideosrc` | No (i) | No: arrival − 1 frame (m) | Yes (m) | No: name only (m) | No (i) | No (i) | Yes, 720p30 (m) | No (i) | Rejected: deprecated, opens every camera |
| SDL3 3.4.18 camera API | No (i) | No: 16 ms grid (m) | Yes (m) | No: name only (m) | No (i) | ? | Yes, 720p30 (m) | ? | Rejected: no ID, opens every camera |
| nokhwa 0.10.11 (Rust, MSMF) | No (i) | No: 16 ms grid, no UVC metadata (m) | Yes (m) | Part.: symlink exposed, but opens by index (m) | No (m) | Part.: DS side channel (m) | Part.: format list hides MJPEG (m) | ? | Adds nothing over raw MF |
| pygrabber 0.2 | No (i) | No (m) | No: RGB24 (m) | No: names (m) | No (i) | No (i) | Part.: RGB24 out (m) | No (i) | Rejected |
| openpnp-capture 0.0.30 (and the `dom/openpnp-capture*` branches) | No (i) | No: `hardware_timestamp_ns` always 0 (i) | No: RGB24; the MF DLL was never built (m) | Part.: DS path (m) | No (i) | Part.: API exists, untested (i) | Part.: RGB24 out (m) | Part.: API exists, untested (i) | Rejected; branch has an EOI-scan crash |

### Windows, camera rebound to WinUSB (driver swap: admin, UAC, replug; camera hidden from other apps)

| Method | G1 Sync | G2 Timestamp | G3 MJPEG | G4 ID | G5 Bandwidth | M1 Exposure | M2 Format | M3 Focus | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **libuvc + patch 0001 (C)** | No: free-running (i) | **Part.: SCR 0.41–0.74 ms MAD (floor); SOF→QPC basis holds only ~2–3.5 s** (m) | Yes: 0 corrupt in 2,135 strict decodes (m) | **Yes**: port path + serial (m) | **Yes**: 720p30 at alt 5 (800 B), 1080p at alt 8 (m) | Part.: only if re-applied after stream start (m) | Part.: MJPEG 480p–1080p30 (m) | Part.: AF off/on set and read back; absolute focus never set (m) | **Bandwidth reference** |
| Python libusb1 streamer | No (i) | Part.: PTS/SCR logged, never scored (m) | Yes (m) | Part.: port; serial needs open (m) | Yes: alt 5 at 720p (m) | Part.: set before COMMIT, effect unverified (m) | Part.: MJPEG 720p/1080p (m) | ? | Python prototype |
| Rust `uvc_iso` (libusb backend) | No (i) | Part.: PTS/SCR logged, never scored (m) | Yes: 0 corrupt in 7,543 (m) | Part.: port path; serial not read (m) | Yes: alt 4/5/6 at 720p30 (m) | Part.: set before COMMIT, effect unverified (m) | Part.: 720p30 only (m) | ? | Best native-core candidate |
| pyuvc (PyPI 1.0.8 crashes; locally patched build) | No (i) | No: 103–129 ms off (m) | Yes, patched build (m) | No: bus:address only (m) | Yes: `bandwidth_factor` (m) | Part.: readback only (m) | Part. (m) | ? | Rejected unless fixed |
| Rust `uvc_iso` (rawusb backend) / nusb PR #233 fork | No (i) | ? | Part. (m) | Part. (m) | Part.: queue underruns, 15–23 fps (m) | ? | Part. (m) | ? | Not ready |

### Linux and macOS (harnesses drafted, never run on hardware)

| Method | G1 Sync | G2 Timestamp | G3 MJPEG | G4 ID | G5 Bandwidth | M1 Exposure | M2 Format | M3 Focus | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Linux V4L2 + uvcvideo | No (i) | Part.: metadata-node PTS/SCR (i) | Yes (i) | Yes: sysfs serial / `by-path` (i) | No: `quirks=128` skips MJPEG per kernel source (i; disputed) | Part. (i) | Yes (i) | ? | Likely Linux default |
| Linux libuvc / libusb via udev rule | No (i) | Part. (i) | Yes (i) | Part. (i) | Yes (i) | Part. (i) | Yes (i) | Part. (i) | Linux bandwidth path |
| macOS AVFoundation | No (i) | ? | ? (probe drafted) | Part.: `uniqueID` ≈ port (i) | No (i) | ? | Part. (i) | ? | Run the MJPEG probe first |
| macOS libusb / libuvc | No (i) | Part., only as root (i) | Part., only as root (i) | Part. (i) | Part., root or entitlement (i) | Part. (i) | Part. (i) | Part. (i) | Not shippable to users |

### Hardware triggers

| Method | G1 Sync | G2 Timestamp | G3 MJPEG | G4 ID | G5 Bandwidth | M1 Exposure | M2 Format | M3 Focus | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| FSIN pin driven by an Arduino/ESP32 (InnoMaker OV9281; [../arduino_sync/](../arduino_sync/)), plan only | **Part.: designed to align exposure starts; skew unmeasured** (i) | Part.: frame = pulse index (i) | — (capture stack) | — | — | Part. (i) | Part.: ≤ ~50 fps re-trigger lockout (MoCapSTR's figure) | ? (fixed lens expected) | **Only route to G1 "yes"** |
| UVC still-image trigger | ? (only the generic camera reports `bTriggerSupport=1`) | ? | — | — | — | — | — | — | Expected not to align exposure |

### Ranking by goal

| Goal | Answer so far | Ranking (best first) |
|---|---|---|
| G1 Sync | **No USB capture method aligns exposures.** Every UVC camera free-runs on its own clock, and nothing in UVC, MF, DirectShow or libusb sets when an exposure starts. That is inferred, not yet measured: no run so far had a ground truth without display scan-out, and none ran longer than 30 s. Timestamp-based offset measurement reached a C930e−C922 spread of 0.54–0.79 ms, which is the method floor. The cameras' clocks differ by about 39 ppm (derived from `timing/VERIFY_method.md` §5), so their phase should walk about one frame every ~14 min. | Hardware FSIN trigger (plan only) ≫ every USB method (all "no"). A software "restart until aligned" loop could at most reach "partial" (plan test S6). |
| G2 Timestamp | **Partly: only the camera's own clock (UVC PTS/SCR) gets within the ~0.5 ms floor.** OS and arrival times are stuck on a 16 ms grid (4.4–5 ms). Caveats: rolling shutter spans ~30 ms of each frame; C922 PTS sits near the end of exposure; C930e PTS is synthetic (use SCR); the generic camera has no metadata. Absolute latency (light → timestamp) is not measured. | libusb SCR / back-dated arrival (WinUSB) ≈ MF UVC PTS (admin registry value) > MF / WinRT / GStreamer / nokhwa OS or arrival times > synthesized timestamps (PyAV DShow, OpenCV) |
| G3 MJPEG | **Yes on Windows** without a driver swap. | MF native = PyAV DShow (~1–2% of a core) > nokhwa, `mfvideosrc`, SDL3 (heavier dependencies) > libusb (needs the swap); OpenCV, WinRT, pygrabber, openpnp-capture: no |
| G4 ID | **Yes**, through any API that exposes the MF symlink, DS device path or USB port, mapped to `naming/camera_identity.py`'s serial-else-port key. Never by index or friendly name. Stability under reboot, replug and port move is still untested. | MF, PyAV DShow, `mfvideosrc`, libuvc > nokhwa, OpenCV (index → key via enumeration) > SDL3, `ksvideosrc`, pygrabber (names only) |
| G5 Bandwidth | **Only with libusb on WinUSB.** Every usbvideo path takes the camera's maximum alt. Two cameras per USB 2.0 link measured; three or more is untested. | libuvc ≈ `uvc_iso` (libusb) ≈ Python libusb1 > patched pyuvc > everything on usbvideo (no) |
| M1 Exposure | **Not demonstrated end-to-end anywhere.** The only verified effect is libuvc with exposure re-applied after stream start (C930e). MF applied on the C922 but the C930e only 1 of 5 runs, and most cells checked readback, not the image. | libuvc (after start) > MF > DS side channel (PyAV, OpenCV) |
| M2 Format | Met on MF and PyAV DShow; partly on libusb (only a few modes tried). | MF = PyAV DShow > libuvc / `uvc_iso` > OpenCV (order-dependent) |
| M3 Focus | **Never set on any usbvideo path**; the harnesses only read focus, and autofocus ran in every test. libuvc set AF off/on (readback only). | Unknown; plan test C3 |

**Overall for skellycam on Windows:** (1) MF native MJPG with UVC metadata as the primary path, (2) PyAV
DirectShow as the per-camera fallback, (3) libuvc or Rust `uvc_iso` on WinUSB only if more cameras per link are
worth a driver swap. Each one still has to pass the exposure and focus tests before it can be adopted. Exposure
alignment (G1) needs trigger-capable cameras whichever capture stack is chosen.

## Layout

```
research/usb_cameras/
  tools/        shared helpers (camlock.py, frame-log analysis)
  naming/       goal 4: device identity
  mjpeg/        goal 1: native MJPEG extraction
  timing/       goal 2: capture-time accuracy
  bandwidth/    goal 3: USB bandwidth allocation
  libusb/       libuvc and from-scratch libusb UVC streaming
  rust/         Rust uvc_iso, nokhwa and nusb probes; rust/platform/ holds run_linux.sh, run_macos.sh, run_windows_phase2.sh
  sync_rig/     ESP32 strobe / LED time-code rig and host clock-sync script (draft: compiles, never flashed or run)
  docs/         reports, incl. test_gap_plan.md (plan to fill the comparison gaps) and rocsync_review.md
  (no top-level platform/ folder: other per-OS runners sit in each area, e.g. timing/linux/, timing/macos/,
   mjpeg/drafts/, libusb/linux/; corrected 2026-10-28, was "platform/  per-OS runners (run_linux.sh, run_macos.sh, run_windows.ps1)")
  workflows/    the Workflow scripts that drove each phase and the overnight rerun (repo copies)
  results/<platform>/<hostname>/<test>/   JSON + logs written by the tests
```

Progress, machine state and how to resume: `PROGRESS.md`. The overnight rerun script is
`workflows/overnight_rerun_workflow.js` (it sat at the area root before 2026-10-28).

## Conventions

- Python tests are PEP 723 single-file scripts: `uv run --script <file>`. No dependence on the
  skellycam package or its venv, so they run on any machine with `uv`.
- Any command that opens a camera on the shared Windows test machine is wrapped in
  `uv run --script research/usb_cameras/tools/camlock.py -- <command>`.
- Every test writes a JSON result with: `test`, `platform`, `hostname`, `utc_started`,
  `command`, `environment` (OS build, package versions), `cameras`, and its measurements.
- Per-frame logs use the schema below (JSON Lines or Parquet), so `tools/analyze_frames.py`
  works on output from any capture backend.

## Per-frame log schema

| field | type | meaning |
| --- | --- | --- |
| `camera_key` | str | stable identity string from the naming work, or best available |
| `backend` | str | e.g. `msmf-sourcereader`, `pyav-dshow`, `libuvc`, `v4l2` |
| `seq` | int | frame sequence number as delivered |
| `host_arrival_ns` | int | host monotonic clock (QPC / CLOCK_MONOTONIC / mach_absolute_time) when user code received the frame |
| `os_timestamp_ns` | int or null | timestamp the OS/API attached to the frame, converted to the same host clock |
| `os_timestamp_source` | str | what that timestamp is documented/observed to mean |
| `uvc_pts` | int or null | raw UVC payload-header PTS (device clock ticks) |
| `uvc_scr_stc` | int or null | raw SCR source time clock (device clock ticks) |
| `uvc_scr_sof` | int or null | raw SCR 11-bit USB SOF counter |
| `device_clock_hz` | int or null | dwClockFrequency from the VC interface header |
| `payload_bytes` | int | size of the frame payload |
| `is_valid_jpeg` | bool or null | SOI/EOI present and decodes |
