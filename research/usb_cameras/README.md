# USB camera investigation harness

Test harnesses backing the report "Low-cost USB cameras: MJPEG, timing, bandwidth, naming, cross-platform".
Every claim in the report cites a result file under `results/`.

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
