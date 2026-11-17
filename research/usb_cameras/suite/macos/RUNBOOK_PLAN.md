# macOS runbook: capture-plan run (`--plan`)

For Dom. One command on an Apple silicon Mac with the latest macOS. It answers what the native-MJPEG capture
plan needs from macOS: does AVFoundation hand over the camera's own JPEG bytes (the gating question), open/close
reliability, all cameras at once, the sample-buffer clock, controls, camera identity strings and the environment.
Then, in the same run, whether absolute exposure, gain and focus can be set on macOS.
**Tier 0 only**: no driver change, no sudo, nothing written to the system, no camera seized, claimed or detached.

Endpoint-0 requests are the standard UVC control messages (read a control's range, set a value, read it back)
sent to the camera's control interface. AVFoundation has no absolute exposure or focus, so this is the only way.
They are sent in a separate last phase, after every other result and a first `summary.md` are saved.

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

Expected duration: about 20-30 minutes with four cameras (the last 4-5 minutes are the endpoint-0 phase), plus a
few minutes of package downloads on the first run.
Leave the Mac alone and awake while it runs (cameras may switch on and off, and the image may get darker, brighter
or blurred during the endpoint-0 phase; that is expected). Every camera's controls are put back as they were.

**If the Kiyo Pro wedges** (stops streaming or stops answering): do nothing. Let the run finish. The run records it
once, marks the Kiyo Pro dead, skips it for the rest of the run (endpoint-0 phase included) and tests the other
cameras. Do not unplug it during the run.

To run it again without any endpoint-0 request:

```text
bash research/usb_cameras/suite/macos/run_suite.sh --plan --no-ep0
```

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
| Endpoint-0 phase (last; M-CTRL-LIST and M-CTRL-EFFECT again) | per camera: range of exposure, gain, focus, white balance and their auto switches; auto exposure to manual, then exposure x3, gain x3, white balance x3, focus x3; set accepted, read back, effect on brightness / colour / sharpness; exposure set before the stream starts and read again after the camera is closed; every value and auto mode put back. Results in `m_ctrl_list_ep0.json`, `m_ctrl_effect_ep0.json` and the "Manual controls via endpoint 0" part of `summary.md` |

Left out on purpose: endpoint-0 requests in every test before the endpoint-0 phase, UVC selectors the camera does
not advertise, extension-unit controls, CoreMediaIO controls (not implemented), turning AVFoundation auto modes
back on as a test, UVC header/PTS/SCR, per-process cycles, mode switching, M-FMT-NOGRAB, M-FX and the Kiyo Pro
polling test.
