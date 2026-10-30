# USB camera investigation harness

Test harnesses backing the report "Low-cost USB cameras: MJPEG, timing, bandwidth, naming, cross-platform".
Every claim in the report cites a result file under `results/`.

## Method comparison (2026-10-30)

How each capture method tested so far scores against the study's goals and the must-haves for any adopted
solution. Every cell was checked against the result files by an extractor agent and an adversarial verifier
(workflow `wf_30cb7742-77f`, script `workflows/goal-matrix-and-gap-plan-wf_30cb7742-77f.js`). The full matrix,
with evidence paths and notes for every cell, is in
`results/agent_reports/goal_matrix_gap_plan_wf_30cb7742-77f.json`. The tests that fill the gaps are in
[docs/test_gap_plan.md](docs/test_gap_plan.md). Rows left out of this summary (MF with MF's own decoder, the
DirectShow graph probe, libusb enumeration only, identity helpers, inferred-only third-party stacks and wrappers)
are in the JSON and in the plan's §2 gap table.

**Goals** (numbered as in the current brief; REPORT.md uses the older order 1 MJPEG, 2 timing, 3 bandwidth, 4 naming, 5 cross-platform):

- **G1 sync:** does the method tighten *when light hits the sensor* across cameras, i.e. align exposures?
- **G2 timestamp:** does it give a per-frame time close to when light hit the sensor?
- **G3 MJPEG:** does it return the camera's own JPEG bytes, with no decode or re-encode?
- **G4 ID:** does it expose, or map to, a unique, stable camera identity (USB serial, else physical port)? A method rates Yes
  if it opens by a path that maps to that key, even though the path itself can change (REPORT finding 23).
- **G5 bandwidth:** can the app choose the USB isochronous allocation (alt setting), so more cameras fit on a link?
- **Must-haves:** **M1** exposure / shutter control, **M2** format control (resolution, fps, pixel format),
  **M3** focus control.

**Legend:**

- **Yes** / **Part.** (partial) / **No** / **?** (not tested; "unknown" in the matrix JSON) / — (does not apply;
  "n/a" in the plan and JSON).
- (m) = measured on the Windows test machine "Gerald"; (i) = inferred from source code or docs, not run;
  web = outside source, not checked here; derived = computed from measured numbers, not itself measured.
- Cameras measured: Logitech C922, Logitech C930e and a generic camera (USB 4C4A:4A55); WinUSB rows are C930e only.
- "Flash floor" = ~0.5 ms, the limit of the flash method (monitor-flash ground truth,
  [timing/VERIFY_method.md](timing/VERIFY_method.md)): the true error is at most that, not known. (The ESP32 sync
  rig's floor is *est.* 10–20 µs with the strobe band and 15–30 µs with the LED bar, not measured; see
  [sync_rig/](sync_rig/).)
- MAD = median absolute deviation; other timing errors are std (REPORT method note).
- DS = DirectShow (REPORT.md: DShow). "DS side channel" = exposure set out of band through `IAMCameraControl` on a
  separately opened DirectShow filter for the same camera, not through the method's own API; only readback was
  checked.
- alt = alt setting (isochronous slot size); UAC = the Windows admin elevation prompt.

### Windows, normal camera driver (usbvideo.sys)

| Method | G1 sync | G2 timestamp | G3 MJPEG | G4 ID | G5 bandwidth | M1 exposure | M2 format | M3 focus | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| OpenCV `CAP_DSHOW` (skellycam today) | No (i) | No: host time after `read()` only (m) | No: always BGR, 25–40% of a core (m) | Part.: opens by index; indices changed (m) | No (m) | Part.: only via separate DS `IAMCameraControl`, readback only (m) | Part.: MJPG only if size is set before FOURCC (m) | ? | Status quo; baseline only |
| OpenCV `CAP_MSMF` | No (i) | No: synthetic 33.333 ms steps (m) | No: BGR/NV12, 46–156% of a core (m) | Part.: index (m) | No (m) | Part.: DS side channel (m) | Part.: generic camera padded with repeats (m) | ? | Rejected: 39–41 s to open |
| **Media Foundation (MF) native: `IMFSourceReader`, native MJPG type, converters off, UVC metadata** | No (i) | **Part.: C922 UVC PTS 0.47–0.68 ms std, i.e. at the flash floor; needs the `MetadataBufferSizeInKB0` registry value (admin, once per camera, then replug); MF OS timestamp 4.4 ms std** (m) | **Yes**: 0.7–2.2% of a core (m) | **Yes**: symlink → serial/port key (m) | No: max alt always granted (m) | Part.: took effect on C922; C930e 1 of 5 runs (m) | **Yes** (m) | ? (read only) | **Best Windows path** |
| **PyAV / FFmpeg DirectShow `vcodec=mjpeg`** | No (i) | No: synthesized timestamps (m) | **Yes**: bytes identical to MF (m) | **Yes**: opens by `@device_pnp_` path → key (m) | No (m) | Part.: no PyAV API; DS side channel, readback only (m) | **Yes** (m) | ? | Pure-Python fallback |
| WinRT `MediaFrameReader` | No (i) | No: 16 ms grid (m) | No: MJPG subtype fails (m) | Yes (i) | No (i) | ? | Part.: NV12 only (m) | ? | Rejected |
| GStreamer `mfvideosrc` | No (i) | No: arrival time, 16 ms grid (m) | Yes (m) | Yes: opens by `device-path` (= MF symlink) → serial/port key (m) | No (i) | No: no control API (i) | Yes, 720p30 only tried (m) | No: no control API (i) | Wrapper; nothing beyond MF native |
| GStreamer `ksvideosrc` | No (i) | No: arrival − 1 frame (m) | Yes (m) | No: name only (m) | No (i) | No (i) | Yes, 720p30 (m) | No (i) | Rejected: deprecated, opens every camera |
| SDL3 3.4.18 camera API | No (i) | No: 16 ms grid (m) | Yes (m) | No: name only (m) | No (i) | ? | Yes, 720p30 (m) | ? | Rejected: no ID, opens every camera |
| nokhwa 0.10.11 (Rust, MSMF) | No (i) | No: 16 ms grid, no UVC metadata (m) | Yes (m) | Part.: symlink exposed, but opens by index (m) | No (m) | Part.: separate `IAMCameraControl` on the MF source, not nokhwa's API; readback only (m) | Part.: format list hides MJPEG (m) | ? | Adds nothing over MF native |
| pygrabber 0.2 | No (i) | No (m) | No: RGB24 (m) | No: names (m) | No (i) | No (i) | Part.: RGB24 out (m) | No (i) | Rejected |
| openpnp-capture 0.0.30 (and the `dom/openpnp-capture*` branches) | No (i) | No: `hardware_timestamp_ns` always 0 (i) | No: RGB24; the MF DLL was never built (m) | Part.: DS path (m) | No (i) | Part.: API exists, untested (i) | Part.: RGB24 out (m) | Part.: API exists, untested (i) | Rejected; branch has an EOI-scan crash |

### Windows, camera rebound to WinUSB (driver swap: admin, UAC, replug; camera hidden from other apps)

| Method | G1 sync | G2 timestamp | G3 MJPEG | G4 ID | G5 bandwidth | M1 exposure | M2 format | M3 focus | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **libuvc + patch 0001 (C)** | No: free-running (i) | **Part.: SCR 0.41–0.74 ms MAD (flash floor); the SCR→QPC mapping (xHCI frame-number→QPC IOCTL) holds only ~2–3.5 s (REPORT finding 14)** (m) | Yes: 0 corrupt in 2,135 strict decodes (m) | **Yes**: port path + serial (m) | **Yes**: 720p30 at alt 5 (800 B), 1080p at alt 8 (m) | Part.: only if re-applied after stream start (m) | Part.: MJPEG 480p–1080p30 (m) | Part.: autofocus off/on set and read back; absolute focus never set (m) | **Bandwidth reference** |
| Python libusb1 streamer | No (i) | Part.: PTS/SCR logged, never scored (m) | Yes (m) | Part.: port; serial needs open (m) | Yes: alt 5 at 720p (m) | Part.: set before COMMIT, effect unverified (m) | Part.: MJPEG 720p/1080p (m) | ? | Python prototype |
| Rust `uvc_iso` (libusb backend) | No (i) | Part.: PTS/SCR logged, never scored (m) | Yes: 0 corrupt in 7,543 (m) | Part.: port path; serial not read (m) | Yes: alt 4/5/6 at 720p30 (m) | Part.: set before COMMIT, effect unverified (m) | Part.: 720p30 only (m) | ? | Best candidate for a native (Rust) capture core |
| pyuvc (PyPI 1.0.8 crashes; locally patched build) | No (i) | No: 103–129 ms off (m) | Yes, patched build (m) | No: bus:address only (m) | Yes: `bandwidth_factor` (m) | Part.: readback only (m) | Part. (m) | ? | Rejected unless fixed |
| Rust `uvc_iso` (rawusb 0.1.7 backend) | No (i) | Part.: PTS/SCR logged, never scored (m) | Part.: 8,127/8,128 strict decodes; passed through one error-flagged startup frame (m) | Yes: port path + C922 serial without opening; patched crate only (m) | Part.: alt honored, but queue underruns: 15–23 fps (m) | Part.: set before COMMIT, effect unverified (m) | Part.: 720p30 only (m) | ? | Not ready |
| nusb PR #233 isochronous fork (Rust; upstream nusb has no isochronous support) | No (i) | ? | Part.: fork only, 301/301 valid JPEG (m) | ? | Part.: only 1 transfer queues, 15 fps (m) | ? | Part.: 720p30 PROBE/COMMIT only (m) | ? | Not ready |

### Linux and macOS (harnesses drafted, never run on hardware)

| Method | G1 sync | G2 timestamp | G3 MJPEG | G4 ID | G5 bandwidth | M1 exposure | M2 format | M3 focus | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| Linux V4L2 + uvcvideo | No (i) | Part.: metadata-node PTS/SCR (i) | Yes (i) | Yes: sysfs serial / `by-path` (i) | No: `quirks=128` (FIX_BANDWIDTH) skips MJPEG per kernel source (i); the uvcvideo maintainer reports it helps MJPEG (REPORT finding 21) | Part. (i) | Yes (i) | ? | Likely Linux default |
| Linux libuvc / libusb via udev rule | No (i) | Part. (i) | Yes (i) | Part. (i) | Yes (i) | Part. (i) | Yes (i) | Part. (i) | Linux bandwidth path |
| macOS AVFoundation | No (i) | ? | ? (probe drafted) | Part.: `uniqueID` ≈ port (i) | No (i) | ? | Part. (i) | ? | Run the MJPEG probe first |
| macOS libusb / libuvc | No (i) | Part., only as root (i) | Part., only as root (i) | Part. (i) | Part., root or entitlement (i) | Part. (i) | Part. (i) | Part. (i) | Not shippable to users |

### Hardware triggers

| Method | G1 sync | G2 timestamp | G3 MJPEG | G4 ID | G5 bandwidth | M1 exposure | M2 format | M3 focus | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| FSIN (sensor frame-sync input) pin driven by an Arduino/ESP32 (InnoMaker OV9281 = U20CAM-9281M; [../arduino_sync/](../arduino_sync/)), plan only | **Part.: designed to align exposure starts; skew unmeasured** (i) | Part.: frame = pulse index (i) | — (set by the capture stack) | — (set by the capture stack) | — (set by the capture stack) | Part. (i) | Part.: ≤ ~50 fps re-trigger lockout (web: MoCapSTR's figure) | ? (fixed lens expected) | **Only route to G1 "yes"** |
| UVC still-image trigger | ? (only the generic camera reports `bTriggerSupport=1`) | ? | ? | — | — | — | — | — | Expected not to align exposure |

### Ranking by goal

| Goal | Answer so far | Ranking (best first) |
|---|---|---|
| G1 sync | **No USB capture method aligns exposures.** Every UVC camera free-runs on its own clock, and nothing in UVC, MF, DirectShow or libusb sets when an exposure starts. That is inferred, not yet measured: every run so far used the flash method, whose ground truth varies by ~35 ms across the image (rolling shutter plus monitor scan-out), and none ran longer than 30 s. Measuring the offset is a G2 tool, not alignment: with a fixed region of interest, the C930e (libusb SCR) minus C922 (MF PTS) offset varied with a standard deviation of 0.54–0.79 ms across 5 runs, comparable to the flash floor (provisional, REPORT finding 15). The cameras' clocks differ by about 39 ppm (derived from `timing/VERIFY_method.md` §5), so their phase should walk about one frame every ~14 min (derived, not measured; plan test S2 measures it). | Hardware FSIN trigger (plan only) ≫ every USB method (all "no"). A software "restart until aligned" loop could at most reach "partial" (plan test S6). |
| G2 timestamp | **Partly: only the camera's own clock (UVC PTS/SCR) gets within the ~0.5 ms flash floor.** OS and arrival timestamps on usbvideo paths sit on a 16 ms grid (4.4–5 ms std vs the flash ground truth). Caveats: rolling shutter spans ~30 ms of each frame; C922 PTS sits near the end of exposure; C930e PTS is synthetic (use SCR); the generic camera has no metadata. Absolute latency (light → timestamp) is not measured. | libusb SCR / back-dated arrival (first-payload time back-dated by packet index; WinUSB) ≈ MF UVC PTS (admin registry value) > MF / WinRT / GStreamer / nokhwa OS or arrival times > synthesized timestamps (PyAV DShow, OpenCV) |
| G3 MJPEG | **Yes on Windows** without a driver swap. | MF native = PyAV DShow (~1–2% of a core) > nokhwa, `mfvideosrc`, SDL3 (heavier dependencies) > libusb (needs the swap); OpenCV, WinRT, pygrabber, openpnp-capture: no |
| G4 ID | **Yes**, through any API that exposes the MF symlink, DS device path or USB port, mapped to `naming/camera_identity.py`'s serial-else-port key. Never by index or friendly name. Stability under reboot, replug and port move is still untested. | MF, PyAV DShow, `mfvideosrc`, libuvc > nokhwa, OpenCV (index → key via enumeration) > SDL3, `ksvideosrc`, pygrabber (names only) |
| G5 bandwidth | **Only with libusb on WinUSB.** Every usbvideo path takes the camera's maximum alt. Two cameras per USB 2.0 link measured (C930e on WinUSB at a forced alt beside the generic camera on MF); three or more at forced alts is untested (REPORT estimates 3–6 per link from its model). On usbvideo alone, two max-alt cameras cannot share a link (REPORT finding 16): the generic camera beside the C930e failed to open. | libuvc ≈ `uvc_iso` (libusb) ≈ Python libusb1 > patched pyuvc > everything on usbvideo (no) |
| M1 exposure | **Not shown on every camera with any one method.** Effect seen in the image: libuvc with exposure re-applied after stream start (C930e), and MF on the C922 (mean luma 24/65/95 at −9/−7/−6, `results/windows/Gerald/timing/rerun_20261027/compact_table_all_runs.txt`; the PTS offset tracks exposure). MF on the C930e took effect in only 1 of 5 runs (REPORT finding 11). Every other cell checked readback only. | libuvc (after start) > MF > DS side channel (PyAV, OpenCV) |
| M2 format | Met on MF and PyAV DShow; partly on libusb (only a few modes tried). | MF = PyAV DShow > libuvc / `uvc_iso` > OpenCV (order-dependent) |
| M3 focus | **Never set on any usbvideo path**; those harnesses only read focus, and autofocus (AF) stayed on in every usbvideo test. On WinUSB, libuvc set AF off/on and read it back; absolute focus was never set. | Unknown; plan test C3 |

**Overall for skellycam on Windows:** (1) MF native MJPG with UVC metadata as the primary path, (2) PyAV
DirectShow as the per-camera fallback, (3) libuvc or Rust `uvc_iso` on WinUSB only if more cameras per link are
worth a driver swap. Each one still has to pass the exposure and focus tests before it can be adopted. Exposure
alignment (G1) needs trigger-capable cameras whichever capture stack is chosen.

## Layout

```
research/usb_cameras/
  tools/        shared helpers (camlock.py, frame-log analysis)
  naming/       G4 ID: device identity (REPORT goal 4)
  mjpeg/        G3 MJPEG: native MJPEG extraction (REPORT goal 1)
  timing/       G2 timestamp: capture-time accuracy (REPORT goal 2)
  bandwidth/    G5 bandwidth: USB bandwidth allocation (REPORT goal 3)
  libusb/       libuvc and from-scratch libusb UVC streaming
  rust/         Rust uvc_iso, nokhwa and nusb probes; rust/platform/ holds run_linux.sh, run_macos.sh, run_windows_phase2.sh
  sync_rig/     ESP32 sync rig: strobe + LED bar ground truth and host clock-sync script (DESIGN.md design; README.md draft firmware compiles, never flashed or run)
  docs/         reports, incl. test_gap_plan.md (tests to fill the method-comparison gaps) and rocsync_review.md (review of RocSync, an open-source LED-clock device that timestamps camera exposures; web research only)
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
