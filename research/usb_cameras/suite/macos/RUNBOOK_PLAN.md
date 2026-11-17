# macOS runbook: capture-plan run (`--plan`)

For Dom. One command on an Apple silicon Mac with the latest macOS. It answers what the native-MJPEG capture
plan needs from macOS: does AVFoundation hand over the camera's own JPEG bytes (the gating question), open/close
reliability, all cameras at once, the sample-buffer clock, controls, camera identity strings and the environment.
**Tier 0 only**: no driver change, no endpoint-0 requests, no sudo, nothing written to the system.

## 1. Before the run

1. Get the skellycam repository onto the Mac on branch `dom/research` (clone or pull it if that branch is pushed,
   otherwise copy the repository folder over). Run everything from the repository root.
2. Plug in the cameras you have: Logitech C922, Logitech C930e, the generic camera (4c4a:4a55), Razer Kiyo Pro.
   Use the ports you would normally use. A hub is fine.
3. Quit Photo Booth, FaceTime, Zoom, Teams, browsers, OBS, Logi Tune / Logi Options+ and Razer Synapse.
4. Turn Video Effects / Edge Light off for the cameras (Control Center > Video Effects).
5. Point the cameras at a lit scene with some texture. Nothing has to move.
6. **Camera permission.** It belongs to the app you type the command in (Terminal, iTerm2, VS Code ...), not to
   Python. Open System Settings > Privacy & Security > Camera and switch that app on. If it is not in the list,
   the run asks at its start: click **Allow** in the dialog (you have 30 s). If you change the setting, quit and
   reopen the app, then start again. Run it from a local window, not over SSH (no dialog can appear over SSH).
7. Internet access on the first run: the script installs `uv` into `~/.local/bin` if it is missing, then Python
   3.12.13 and the pinned packages (PyObjC 13.0, numpy 2.2.6, Pillow 12.0.0, simplejpeg 1.8.2). No sudo.

## 2. Start command

```text
bash research/usb_cameras/suite/macos/run_suite.sh --plan
```

Expected duration: about 15-25 minutes with four cameras (plus a few minutes of package downloads on the first run).
Leave the Mac alone and awake while it runs (cameras may switch on and off; that is expected).

**If the Kiyo Pro wedges** (stops streaming): do nothing. Let the run finish. The run records it once, marks the
Kiyo Pro dead, skips it for the rest of the run and tests the other cameras. Do not unplug it during the run.

If the run prints `CAMERA PERMISSION MISSING`, grant the permission (step 6) and run the command again.

## 3. What to bring back

- The whole results folder: `research/usb_cameras/results/macos/plan/suite_<UTC stamp>/` (the last line of the
  run names it). Zip it and send it, or copy it into the same path on the Windows machine. Host name, user name
  and home path are already replaced in it; USB serial numbers are kept on purpose (camera identity).
- Paste `summary.md` from that folder into the chat (the same text is printed at the end of the run).
- Not needed: the raw frames in `~/skellycam-raw/` (outside the repository; samples only).

## 4. What the run does

| Test | What it answers |
| --- | --- |
| M-ENV, M-TCC | macOS version and build, Mac model, Python and package versions, camera apps running, Camera permission state |
| M-TOPO, M-ID | USB topology (bandwidth domains), serial / locationID / port path / AVFoundation uniqueID and modelID strings exactly as macOS reports them |
| M-FMT, M-CTRL-LIST | the formats and the control modes AVFoundation lists (nothing streamed) |
| M-MJPEG | each 720-line MJPEG mode at 30 fps and at its top rate (60 where offered), 4 s each with `videoSettings` nil, `{}` (device-native), `'dmb1'` and Chromium's dictionary: JPEG block buffer or decoded pixels, pixel formats delivered, SOI/EOI, strict decode, header SHA-1 and markers, frames vs expected, fps, bytes per frame (min/median/p99/max) |
| M-CYC | 20 open / first frame / close cycles per camera in one process: failures and time to first frame |
| M-CTRL-EFFECT | exposure, white balance and focus set to locked (auto off) and read back; image brightness logged; original modes restored. AVFoundation has no absolute exposure or focus on macOS |
| M-MULTI | all cameras together at 720p30 for 90 s: frames, fps, drops, refusals, granted alt per camera |
| M-TS | 30 s per camera: the sample-buffer clock (synchronizationClock vs the host clock = mach_absolute_time), its grid, inter-frame jitter against the fitted period |

Left out on purpose: endpoint-0 UVC requests (absolute exposure/focus values; opt-in `--ep0`), CoreMediaIO
controls (not implemented), turning auto modes back on as a test, UVC header/PTS/SCR, per-process cycles, mode
switching, M-FMT-NOGRAB, M-FX and the Kiyo Pro polling test.
