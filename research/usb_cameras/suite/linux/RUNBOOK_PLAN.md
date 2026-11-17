# Linux runbook: capture-plan run (`--plan`)

For Dom. One command on the latest Ubuntu, on the same PC as the Windows runs (Intel xHCI, all four cameras). It
answers what the native-MJPEG capture plan needs from Linux: does V4L2 hand over the camera's own JPEG bytes (raw
`VIDIOC_DQBUF` mmap through the suite's ctypes code), open/close reliability, all cameras at once, the buffer
clock, manual controls, camera identity strings and the environment. **Tier 0 only**: no driver or module
changes, no UVC metadata/PTS/SCR, no sudo, nothing written to the system.

## 1. Before the run

1. Get the skellycam repository onto the Ubuntu install on branch `dom/research` (clone or pull it if that branch
   is pushed, otherwise copy the repository folder over). Run everything from the repository root.
2. Plug in the four cameras where they are on Windows: Logitech C922, Logitech C930e, the generic camera
   (4c4a:4a55), Razer Kiyo Pro.
3. **Log in to the desktop and open a terminal there** (not over SSH). The desktop session gives your user access
   to `/dev/video*`. Over SSH you would need the `video` group (`sudo usermod -aG video $USER`, then log out and
   in); the run says when a camera is not accessible.
4. Close every app that uses a camera: Cheese / Camera, browsers with a call open, Zoom, OBS. PipeWire and
   WirePlumber may stay running (they only watch the cameras); a camera another app is streaming is skipped and
   reported, not opened.
5. Point the cameras at a lit scene with some texture. Nothing has to move.
6. Internet access on the first run: the script installs `uv` into `~/.local/bin` if it is missing (with `curl`
   or `wget`), then Python 3.12.13 and the pinned packages (Pillow 12.0.0, numpy 2.2.6, simplejpeg 1.8.2). No sudo.

## 2. Start command

```text
bash research/usb_cameras/suite/linux/run_suite.sh --plan
```

Expected duration: about 12-15 minutes with four cameras (plus a minute or two of downloads on the first run).
Leave the PC alone while it runs (the camera lights switch on and off; that is expected).

Optional pre-flight (opens no camera, prints the plan as JSON): `bash research/usb_cameras/suite/linux/run_suite.sh --plan --dry-run`.

**If the Kiyo Pro wedges** (stops streaming): do nothing. Let the run finish. The run records it once, marks the
Kiyo Pro dead, skips it for the rest of the run and tests the other cameras. Do not unplug it during the run.

## 3. What to bring back

- The whole results folder: `research/usb_cameras/results/linux/plan/suite_<UTC stamp>/` (the last line of the run
  names it). Zip it and send it, or copy it into the same path on the Windows side. Host name, user name and home
  path are already replaced in it; USB serial numbers are kept on purpose (camera identity), so run
  `tools/redact_run.py` before anything is committed.
- Paste `summary.md` from that folder into the chat (the same text is printed at the end of the run).
- Not needed: the raw frames in `~/skellycam-raw/` (outside the repository; samples only).

## 4. What the run does

| Test | What it answers |
| --- | --- |
| L-ENV, L-DESK | Ubuntu release, kernel, uvcvideo parameters (read only), Python and package versions, PipeWire/WirePlumber versions and state, who holds `/dev/video*`, how this user reaches the nodes (seat ACL / `video` group) |
| L-TOPO, L-ID | USB topology (bandwidth domains); serial, port path, sysfs name, QUERYCAP `bus_info`, udev `ID_PATH`, `/dev/v4l/by-id` and `by-path` exactly as Linux reports them (5 repeats) |
| L-FMT, L-CTRL-LIST | every mode and every control with its range (nothing streamed) |
| L-MJPEG | each 720-line MJPEG mode at >= 30 fps (720p30, and 720p60 where offered), 5 s each, raw V4L2 mmap: SOI/EOI, strict decode, header SHA-1 (count of distinct values), frames vs expected, delivered fps (host and buffer time), lost sequence numbers, error-flagged buffers, bytes per frame (min/median/p99/max) |
| L-CYC | 20 open / first frame / close cycles per camera in one process (native path only): failures and time to first frame |
| L-CTRL-EFFECT | auto exposure and autofocus off; manual exposure (3 values) and manual focus (min/mid/max) set, read back and checked on the image (brightness, sharpness); manual exposure after close/reopen; the camera's original settings restored at the end |
| L-TS | 20 s per camera at 720p30: the buffer timestamp flags and clock (`CLOCK_MONOTONIC` -> `linux_monotonic`), its granularity, inter-frame jitter against the fitted frame period |
| L-MULTI | all cameras at once at 720p30 for 90 s (one process each): frames, fps, lost frames, refusals with their errno, granted alt and bandwidth domain per camera |

Left out on purpose: PyAV / OpenCV / GStreamer legs, per-process and mode-switch cycles, bandwidth pair tests,
L-FMT-NOGRAB, the Kiyo Pro polling test (L-KIYO), UVC metadata/PTS/SCR, turning auto modes back on as a test.
