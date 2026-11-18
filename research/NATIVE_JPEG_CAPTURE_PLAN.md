# Native JPEG capture and skellyfileformat recording: plan

2026-11-17, revision 1 · status: **decisions accepted by Dom in a grilling session on 2026-11-17; the phase
specs are not written yet.** This plan replaces `CAPTURE_AND_RECORDING_PLAN.md` (rev 3.12), which is kept as
history. Where the two differ, this file wins.

Labels: **[D]** decided by Dom (2026-11-17 unless dated), **[M]** measured (result file named), **[C]** read
from code, **[I]** inferred, **[NV]** not verified. Every [M] result so far comes from one Windows 11 machine.
Linux and macOS have had no hardware run.

## 1. Goals

1. A native capture pipeline that takes the camera's own MJPEG bytes and passes them, untouched, to the ring
   buffer, the UI and the recorder.
2. Recording and playback in the skellyfileformat take folder (MJPEG in MKV, CSV timing sidecars, Opus audio
   in fragmented MP4, manifest, capture info).
3. A smaller, simpler ring buffer.
4. A UI preview that shows the camera's JPEG frames directly.
5. Last: remove the lockstep gate.

## 2. Scope and ground rules [D]

- **Repos.** This plan covers skellycam only. FreeMoCap is updated on a new branch by a separate session in
  the freemocap repo. skellycam gives that session an interface note after phase 4 (§9).
- **No backwards compatibility.** There is no legacy read call. Every camera has a JPEG ring; a BGR ring
  exists only when the consumer asks for it [D 2026-11-18, replaces "the ring carries JPEG only, no BGR ring
  mode, no decode helper"; see §4]. FreeMoCap takes JPEG or BGR, whichever is the camera's native format.
  The old frontend-payload calls and BGR `put_frame` are deleted. D26 (2026-11-12) stands: freemocap does not
  use this skellycam until its own branch is ready.
- **Base.** A new branch in Dom's fork, in a new worktree, based on `upstream/development-streaming`. Nothing
  is pushed and no pull request is opened upstream without Dom's approval each time.
- **Versions.** Python 3.13.18. Every Python and npm dependency bumped to its latest release, pinned exactly,
  and tested (§8 phase 1). PyAV 19.0.2 and OpenCV 5 are part of that pass.
- **Method.** Each phase: spec and test list, Dom's review, failing tests, then code. Sub-agents (Opus,
  Sonnet or Haiku; never Fable) do the work and the main session checks it.
- **Standing rules that still apply.** JPEG only and I-frames only (2026-11-11). Tier 0 only: no driver or
  registry changes, no UVC PTS/SCR (2026-11-09). Streaming tests use 720-line modes at 30 fps or more. Manual
  camera controls only, auto modes off. Kiyo Pro wedge: record, mark dead, never revive. Read old recording
  formats, write only the new one. Stored frames are never rotated; rotation is display-only. No overlays in
  recorded frames.
- **Out of this plan.** The automatic exposure step (D14) and the ChArUco focus step (they wait for the board
  rig). The ESP32 strobe rig. FreeMoCap's own changes. skellysync. The Blender addon.

## 3. Capture

| OS | Now | End state |
|---|---|---|
| Windows | OpenCV DirectShow, decoded BGR [C] | Pure-Python Media Foundation through comtypes, no compiled extension [D 2026-11-08]. OpenCV capture deleted. |
| Linux | OpenCV V4L2, decoded BGR [C] | V4L2 through ctypes, once the hardware run passes. Until then OpenCV, with decoded frames re-encoded to JPEG. Timestamps: the kernel buffer timestamp only [D]. |
| macOS | OpenCV AVFoundation, decoded BGR [C] | AVFoundation through PyObjC if it hands over the camera's JPEG (the gating test). If it does not, macOS stays on decode then re-encode. Manual controls through IOKit endpoint-0 requests, if the hardware run shows they work. |

- **One process per camera** stays [D]. A hung camera call or a crash then affects one camera.
- **OpenCV capture is deleted per OS** once native capture passes there; it is not kept as a fallback [D].
- **Cameras in an uncompressed mode** (YUY2, NV12) are JPEG-encoded at capture: Intel `mjpeg_qsv` where
  available on Windows and Linux, `cv2.imencode` otherwise and always on macOS [D 2026-11-18, replaces the
  libjpeg-turbo fallback of 2026-11-11]. Quality 90 by default, chroma layout of the source, Quick Sync at
  depth 2. The main process checks for Quick Sync once per app run. The input range rule and the evidence are
  in the design notes ("Two rings per camera").
- **Controls.** Resolution, frame rate, manual exposure, gain and focus: set and read back through the native
  API, auto modes off. No automation [D].
- **A camera that fails or hangs at open** stops the session from starting, so the user can fix it. The
  message names the camera and says to replug it [D]. skellycam does not try to revive it.
- **The mid-take camera reopen** ("reset after 30 slow frames") is removed with the OpenCV path [D]. Native
  capture reports a slow or stalled camera.
- **The burned-in frame stamp** goes: it cannot survive JPEG passthrough and recordings carry no overlays.

Evidence, Windows [M]: one pymf process streamed 4 cameras at 720p30 for 600 s, 69,525 frames, 0 lost,
8.4 % of one core, no decode (`usb_cameras/docs/windows_results_20261113.md` §2.1). OpenCV reached a first
frame within 2 s in 0 of 180 cycles and never returns JPEG bytes (`usb_cameras/docs/capture_stack_options_plan.md`
§9).

OpenCV 5.1.0 on macOS [C, read 2026-11-17]: handles width, height and frame rate only; no exposure, gain,
focus or white balance; pixel format hardcoded to BGRA. Apple's AVFoundation on macOS has no absolute exposure
or focus API. uvc-util, CameraController and Chromium send UVC control requests through IOKit without seizing
the device on macOS 12 and later. None of this is tested on our cameras [NV].

## 4. Ring buffer

One shared-memory block per camera: a ring header, a table of 64-byte frame headers, then the JPEG slots.
It replaces the five current shared-memory classes (nine shared-memory segments per ring today [C]).

- **Fixed slots** [D]. Slot k of the ring holds frame `k % slot_count`. No lossless reader cursors: the ring
  serves the UI and FreeMoCap only, and the recorder does not read it (§6).
- **Slot size** [D]: `2 × (2,048 + 0.5 × width × height)` bytes, rounded up to 4 KiB. It depends on the
  resolution only. The camera's advertised maximum is not used.

  | mode | slot | largest frame seen | slot / largest |
  |---|---|---|---|
  | 1280x720 | 925,696 | 276,269 (Kiyo Pro) | 3.4 |
  | 1920x1080 | 2,080,768 | 607,032 (Kiyo Pro) | 3.4 |

  Evidence [M]: 850,817 camera frames, none above 0.30 bytes per pixel at 640x480 and above; an encoder
  simulation that matches real frame sizes to about 1 % (`frame_ring_buffer/jpeg_bound/FINDINGS.md`; not
  committed until Dom has reviewed the frames in it). Nothing above 1080p is measured [NV].
- **Oversize guard** [D]. The writer checks each frame's length. A frame that does not fit is not copied; its
  slot is flagged oversize and a counter goes up. The ring also carries the driver's error flag.
- **Self-check** [D]. skellycam logs each camera's largest frame as a fraction of its slot, warns above 50 %,
  and shows the oversize count in the UI.
- **History** [D 2026-11-18, replaces "about 3 seconds"]: 1 second by default, one setting for both rings. At
  720p60 that is 60 slots, about 53 MiB per camera for the JPEG ring, against 1 GiB today. FreeMoCap treats a
  lapped read as a skip and counts its lapped reads, which checks the default against real pipelines.
- **BGR ring on request** [D 2026-11-18]. The consumer can ask, per camera and at session start, for a second
  ring of BGR 24-bit frames (158 MiB at 720p60 for 1 s). It is never on by default. For an MJPG mode the
  frames are decoded with `cv2.imdecode` in their own thread, after the recorder queue and the JPEG ring; if
  the decode falls behind, the BGR ring skips frames and capture is not delayed. For an uncompressed mode the
  BGR ring needs a colour conversion only. skellycam lists each camera mode with its format, so the consumer
  can tell which cameras are natively uncompressed. The full decision table and the evidence are in the
  design notes ("Two rings per camera"). The decode stage is built only after Dom's approval and guidance.
- **Torn and lapped reads** [D]. Every reader copies the frame out, then checks a CRC-32 of the header and of
  the JPEG against the values the writer stored. One read path on all three OSes; no Intel-only fast path.
  Measured cost: 53 to 71 µs for a 210 kB frame on Python 3.12 [M, scratch benchmark]. The Apple Silicon
  safety argument is not tested on a Mac [NV]; phase 2 includes a ring test that runs on the Mac.
- **Frame header.** Frame number, arrival time, sample time, publish time, source frame number, JPEG length,
  flags, the two CRCs, and a display rotation value for the UI.
- **Lookups.** Newest frame; frame by number; frame nearest to time t [D]. The last one is skellycam's whole
  contribution to live matching: FreeMoCap decides how to group frames.
- **Read results.** OK, not yet written, lapped, corrupt, oversize.

The proposed byte layout, the reasons and the proposed tests are in
`frame_ring_buffer/docs/jpeg_ring_design_notes_20261117.md`; phase 2's spec fixes them.

## 5. UI preview

- One websocket message per camera frame: a small header and the camera's JPEG bytes, untouched. No resize,
  no re-encode, no multiframe payload [D]. The path does not depend on the lockstep gate.
- The server sends only the newest frame per camera when the UI falls behind.
- The UI decodes (it already uses `createImageBitmap` in a worker [C]) and rotates when drawing, from the
  rotation value in the frame header [D].
- Assumes the UI runs on the machine with the cameras.
- The duplicated wire-format constants in the TypeScript code [C] collapse to one copy.

## 6. Recording

- **skellyfileformat is a spec only** [D]. Its repo keeps the spec, the conformance test list, the golden
  folders and the runnable conformance tests, with a configurable fixture so each program runs them through
  its own thin adapter at a pinned commit. The function names the tests call today become the documented
  adapter interface. The build stages, the "stage ends when the program adopts the package" rule and the two
  owed package tests are removed from that repo. It moves to Python 3.13.18: rebuild the golden folders,
  compare checksums, and stop and report if any byte differs.
- **skellycam owns** [D]: the Python writer (MKV, CSV sidecars, Opus fMP4 audio, manifest, capture info),
  crash repair, opening a folder and recognising old formats, the "upgrade recording" converter, and the
  JavaScript reader inside skellycam-ui.
- **Where the recorder runs** [D]: a writer thread in each camera process, fed by a bounded queue of about
  3 seconds of frames. The capture callback stamps the frame, queues it for the recorder, and then publishes
  it to the ring [D 2026-11-18: recorder first; a ring write never blocks and is skipped under load].
- **MKV writer** [D]: PyAV 19.0.2. A small hand-written Matroska writer replaces it only if the once-a-second
  force-to-disk or live byte offsets cannot be done through PyAV (the SFF-788 test decides).
- **Full queue** [D]: capture slows down (frame requests are held back). The event is counted, logged, shown
  in the UI and written as gap rows. The take ends with an error if the stall outlasts a timeout (starting
  value 10 s).
- **Write error mid-take** [D]: the recorder finishes the sidecars and manifest for the frames it wrote,
  marks the take as ended by an error, and leaves the app running.
- **One camera fails mid-take** [D]: the whole take stops, as today. "Carry on without it" waits for the
  gate-removal phase.
- **Camera identity** comes from the OS (serial, port path, device id), not the capture library.
- **Playback**: a canvas player in skellycam-ui (HTTP range fetch, `ImageDecoder`, one master clock)
  replaces the `<video>` player and the H.264 web transcode. Old recordings keep a `<video>` path.

How a slow disk is handled today [C, both `dom/research` and `development-streaming`]: the write is inline in
the capture loop with no queue or timeout. A stall of X seconds stops every camera for X seconds through the
gate; the frames the cameras produce meanwhile are discarded by the driver and counted nowhere; the recording
passes validation.

Evidence for the queue [M, simulated cameras]: the worst writer stall in a 10-minute run at 16 × 1080p60 was
329 ms, absorbed by a 2.87 s queue with capture at most 2.6 ms late
(`skellycam_recording/recording_upgrade/results/write_throughput/FINDINGS.md` §2.8).

## 7. Tests that must exist before the design is committed

| Test | Question | Phase |
|---|---|---|
| Linux `--plan` run | Native JPEG, 20 open/close cycles, all cameras at 720p30, timestamp clock, manual controls, identity strings | 0 |
| macOS `--plan` run | Does AVFoundation hand over the camera's JPEG (gating)? Same list as Linux, plus manual controls through IOKit endpoint 0, in the same single run | 0 |
| Ring on the Mac | Do the CRC-checked reads reject every torn or lapped frame on Apple Silicon? | 2 |
| T-REC-GIL | How much does a writer thread disturb frame arrival times? 4 cameras at 720p30 plus one at 720p60, 10 min, writer on and off | 5 |
| T-REC-MF-DEFER | How does Media Foundation behave when frame requests are held back for 0.5, 2 and 5 s? | 5 |
| T-REC-STALL | Injected write stalls of 0.5, 2 and 10 s: queue high-water, no silent drop, rows stay in line. Once to a slow USB stick. Confirms or changes the 3 s queue and 10 s timeout | 5 |
| SFF-788 | Cost of forcing files to disk about once a second across 16 writers, through PyAV | 5 |
| Kill test | Kill during normal writing and with a full queue, then repair; frames lost against queue depth | 5 |

Phase 0 commands (pushed to the fork's `dom/research` at 5718b6bad, with a follow-up for the macOS
endpoint-0 phase):

- Ubuntu: `bash research/usb_cameras/suite/linux/run_suite.sh --plan`
- macOS: `bash research/usb_cameras/suite/macos/run_suite.sh --plan`

Bring back the whole results folder and paste `summary.md`. Runbooks: `usb_cameras/suite/linux/RUNBOOK_PLAN.md`
and `usb_cameras/suite/macos/RUNBOOK_PLAN.md`. Neither preset has run on hardware [NV].

## 8. Phases

| Phase | Work |
|---|---|
| 0 | Dom runs the Linux preset (this PC booted into the latest Ubuntu, four cameras) and the macOS preset (Apple Silicon, latest macOS, at least the C922 and C930e). Runs alongside everything. |
| 1 | New worktree off `upstream/development-streaming`. Baseline test run; bump every dependency to latest with exact pins; rerun and compare; one four-camera recording before and after. In the skellyfileformat repo: the superseding entry and wording edits for "spec only", and the move to Python 3.13.18, committed locally and pushed only on Dom's approval. |
| 2 | The new JPEG ring. Delete the old ring classes and BGR paths. |
| 3 | Windows native capture into the ring. Linux and macOS stay on OpenCV with JPEG re-encode. |
| 4 | UI preview. Then the interface note for the freemocap session. |
| 5 | Recorder (writer thread, queue), Opus audio, manifest and capture info, camera identity from the OS. |
| 6 | Canvas player, reading old recordings, the "upgrade recording" converter. |
| 7 | Linux and macOS native capture, built from the phase 0 results. Can move earlier if the results arrive early and look clean. |
| 8 | Remove the lockstep gate. **Not designed.** Dom: "we'll do that when we get there." |

## 9. Interface note for the freemocap session (written after phase 4)

It will state: how to attach to a camera's ring; the frame header fields; the three lookups and the read
results; that frames are JPEG and unrotated, with a rotation value; the UI websocket message layout; and the
recording folder (by reference to the skellyfileformat spec). From 2026-11-18 it also states: the mode list
with each mode's format; how to ask for a camera's BGR ring; that both rings share frame numbers; that a
"lapped" read is a normal result which every reader path handles as a skip; and that FreeMoCap counts and
logs its lapped reads.

What FreeMoCap reads today [C]: `CameraSharedMemoryRingBuffer.get_data_by_index(index=, rec_array=)` in two
worker types, taking `.image[0]` as a BGR array, plus `latest_multiframe_number` and `valid` in a third; and
`CameraGroup.get_latest_frontend_payload` / `get_frontend_payload_by_frame_number`, whose bytes it forwards
to its own UI unopened. All of these go away.

## 10. Open items

- Phase 0 results. They decide phase 7 and whether macOS gets native JPEG and manual controls at all.
- The lockstep gate removal is undesigned. Known from earlier research: the recorder placement in §6 may need
  revisiting then, because slot assembly across per-camera writer processes needs a shared slot clock.
- Whether the version bumps made on `upstream/main` in the phase-1 worktree apply cleanly on
  `development-streaming` [NV].
- How Windows sizes its MJPEG buffers is undocumented; the oversize guard is the only protection there.
- The scripts under `frame_ring_buffer/jpeg_bound/` may hold paths into a temporary folder and may need a
  path fix before they rerun.

## 11. Superseded by this plan

- `CAPTURE_AND_RECORDING_PLAN.md` rev 3.12 as a whole. In particular: its MCAP, FLAC and embedded-sidecar
  sections (already reversed on 2026-11-13 and 11-16); row 1.3 "decode at source to BGR for the ring";
  row 2.1 "JPEG ring behind an option, BGR default"; D8 (build on `upstream/main`); D21 and the shared
  `skellyfileformat` package (D17, D23's package part); the 3.13.13 pin.
- The earlier answer in this session that a camera hanging at open is marked failed while the others start.
  Dom's later ruling is in §3.

## 12. Changes since revision 1

- 2026-11-17 [D]: phase 2 (the JPEG ring) also affects the image preprocessing in skellytracker. Dom will set
  up a skellytracker session for this session to coordinate with for that work.
- 2026-11-17 [D]: phase 1 started. Worktree `../skellycam-native-jpeg`, branch `dom/native-jpeg`, based on
  `upstream/development-streaming` at 169caf637.
- 2026-11-17: phase 1 dependency bumps are committed on `dom/native-jpeg` (7 commits, d3ce158a8 to 3c583e895,
  not pushed). Python tests: 21 failed / 289 passed at the base, 21 failed / 291 passed after (the same 21;
  the 2 new tests cover the PyAV 19 fix) [M]. Held back: `react-resizable-panels` at 3.0.6 (4.x is a rewrite
  that needs a UI change checked by eye). Not run: the Electron app, CI, anything on Linux or macOS, and the
  four-camera before/after recording (W-TBUMP, now pointed at `../skellycam-native-jpeg-baseline` and
  `../skellycam-native-jpeg`) [NV]. OpenCV 5.1.0.95 has macOS wheels for macOS 15 and later only.
- 2026-11-17: the skellyfileformat spec-only change is committed locally in `../skellyfileformat` (6 commits,
  08e55a3 to d67679a; entries YBT1 and K4Y1, both accepted by Dom). Not pushed: the push was blocked by the
  permission system and waits for Dom.
- 2026-11-17 [M]: four-camera before/after recording (W-TBUMP, `usb_cameras/results/windows/Gerald/suite_20261117T221244Z/`,
  not yet redacted or committed). Base 169caf637 (Python 3.12.13, OpenCV 4.12.0, numpy 2.2.6, PyAV 18.1.0)
  against bumped head 3c583e895 (Python 3.13.18, OpenCV 5.1.0, numpy 2.5.5, PyAV 19.0.2), 60 s each, 720p30
  MJPG, lockstep, all four cameras, CPU not idle (other work running). Both: 1,548 frames per camera, equal
  counts. Group fps 25.756 against 25.761 (set by the generic camera). Inter-camera grab range median 0.233
  against 0.237 ms. Connect time 12.0 against 12.2 s. Same codec, CSV headers and log error kinds; no
  tracebacks; clean shutdown. All five verdicts "yes". The Kiyo Pro (plug-in age about 33 h) did not wedge.
  The run before it (`suite_20261117T221102Z`) is not a result: the server never started.
- 2026-11-17 [C, confirmed by running it]: **the skellycam server does not start standalone on
  `upstream/development-streaming` (169caf637).** `entry_point` no longer calls `configure_logging`
  (upstream/main's did), so `logger.api` raises while routes are registered. The W-TBUMP launcher now
  configures logging itself for both runs. Open for Dom: restore the call on `dom/native-jpeg`, and add a
  standalone smoke test (server by its own command, UI, connect, record, stop) to phase 1.
- 2026-11-17 [D]: camera recordings and camera frames are never committed unless they are golden reference
  files. The rule, a pre-commit check (`check_camera_media.py`) and a `commit-files` skill are in the kit
  (`../project`, local commit 6ee0444) and adopted in skellycam: the check alone on `dom/research` (active),
  the full kit on `dom/native-jpeg`. The 84 sample frames of the slot size study were removed from the history
  of `dom/research` (force-pushed; tip 83ba43e1e). No AI attribution in skellycam commits from now on.
- 2026-11-17: **standalone smoke test on `dom/native-jpeg` passed** (Dom at the machine): server started by
  its own entry point on port 53999, Electron UI in development mode, connected, four cameras detected and
  connected, live preview, recording started and stopped, app closed. The recording
  (`skellycam_data/recordings/2026-11-17_18-11-22_GMT-5`, outside the repository) has 771 frames in each of the
  four cameras and a mean frame rate of 26.9 fps with the frame rate left on automatic (-1) [M]. No tracebacks
  in the server log. This is the first run of the bumped UI packages (Electron 45, Vite 8, React Router 7,
  react-i18next 18).
- 2026-11-17, standalone findings, all present on the base branch (none from the bumps); not fixed unless
  stated:
  1. `entry_point` did not configure logging, so the server never started standalone. Fixed (8b5c0d3fb).
  2. The UI has no working control to set the frame rate (Dom).
  3. The default port 53117 is shared with other local servers. A fresh UI retries its websocket to
     `localhost:53117` every 3 s whatever is listening there; the server fails to bind when the port is taken.
  4. When the UI has started a server itself, it sends the shutdown request to port 53117 on exit, ignoring
     the configured port (`electron/main/services/python-server.ts`).
  5. On Windows the UI looks for its bundled server in a folder named `skellycam_server.exe`, so it can never
     find it; "No valid Python server executable found" is logged at every start.
  6. A server whose output is a pipe, as a UI-spawned one is, raises UnicodeEncodeError on every log line
     unless `PYTHONUTF8=1` is set.
  7. `[tool.setuptools.packages.find] where=["."]` treats `skellycam-ui/dist-electron` as a package: the
     Python build fails if the UI dev server deletes that folder at the same time, and a wheel could carry it.
  8. `npm run dev` crashes from a VS Code or Claude Code terminal, because the host sets
     `ELECTRON_RUN_AS_NODE=1`; clear it first.
  9. `react-resizable-panels` warns that the layout sizes add up to 84 %.
  Not tested: playback and every page other than the cameras page; the packaged build; CI.

- 2026-11-18 [D], grilling session on mixed-format rings: "the ring carries JPEG only" and "about 3 seconds of
  history" are replaced. Every camera has a JPEG ring; a BGR 24-bit ring exists on request only; history is
  1 second by default; the decoder is `cv2.imdecode` (benchmark in `frame_ring_buffer/decode_bench/`); H.264
  modes are listed but never selected. §2, §4 and §9 are edited in place; the decision table is in
  `frame_ring_buffer/docs/jpeg_ring_design_notes_20261117.md`, "Two rings per camera". Nothing is built: the
  decode stage waits for Dom's approval and guidance.
- 2026-11-18 [D], later rounds of the same session: this session writes the phase 2 ring spec (2a the JPEG
  ring, 2b the BGR ring and decode stage); the recorder comes first and never loses a frame, rings may skip;
  uncompressed modes are encoded with Quick Sync where available and `cv2.imencode` otherwise (§3); the slot
  header gets a named rotation field and the ring header a `pixel_format` field. The table is in the design
  notes. Benchmarks: `frame_ring_buffer/encode_bench/` and `frame_ring_buffer/encode_qsv_bench/`. The range of the
  test cameras' uncompressed modes was measured (`frame_ring_buffer/yuy2_range/`) [M]: the operating
  system's range flag is wrong for the Kiyo Pro and the generic camera, so the range is checked from the
  pixels at camera start, with a per-camera setting to override it [D].

## 13. State at the end of 2026-11-17 (read this first when resuming)

Changed on 2026-11-18: the ring decisions (two rings per camera, 1 second of history). See the last entry of
§12. Not committed.

**Phase 1 is done except for the items under "Waiting on Dom".** Phase 2 (the ring spec and test list) has
not started.

Where the work is:

| Repository and branch | Tip | Pushed |
|---|---|---|
| skellycam `dom/research` (this plan, research, test suites) | this commit | no: one commit after 0ce011f2d |
| skellycam `dom/native-jpeg`, worktree `../skellycam-native-jpeg` (implementation) | 0a66994c3 | yes |
| skellyfileformat `main` | d67679a | yes |
| project `dom/agents-and-adr-kit` (the kit) | 1e21f8a | no: the hand-off notes commit after 6ee0444 |

Done in phase 1:

- Dependency bumps on `dom/native-jpeg`: tests 21 failed / 292 passed, the same 21 as the base.
- Four-camera before/after recording: no measurable change.
- Standalone fix (`entry_point` configures logging) and the standalone smoke test with the UI: passed.
- skellyfileformat is a spec only (entries YBT1 and K4Y1, accepted), on Python 3.13.18.
- Kit: the camera recordings and frames check, the rule and the `commit-files` skill. Hooks are active in the
  worktrees `skellycam` (camera check only) and `skellycam-native-jpeg` (gitleaks, private data on the files
  of the commit, camera media, AI-attribution warning). Activation is per worktree:
  `git config --worktree core.hooksPath .githooks`.

Waiting on Dom:

1. Phase 0: run `bash research/usb_cameras/suite/linux/run_suite.sh --plan` on Ubuntu and
   `bash research/usb_cameras/suite/macos/run_suite.sh --plan` on the Mac; bring back each results folder and
   `summary.md`. Neither has run on hardware.
2. Three private-data findings in upstream files on `dom/native-jpeg` (the whole-repository check and its test
   fail until decided): a personal email address in the header comment of
   `skellycam-ui/src/hooks/floatingOnboarding.tsx` and of `useDraggableTooltips.tsx` (line 1 of each), and a
   real Windows user path in `skellycam/tests/reference_recordings/README.md` line 36.
3. Two proposed decision entries on `dom/native-jpeg`: NMM1 (the design choices of the camera-media check)
   and 4A7H (other fills of the kit adoption, and `CLAUDE.md` staying untracked).
4. CI on `dom/native-jpeg`: `test.yml` runs on pull requests to `main` and `development` only, not
   `development-streaming`.
5. The standalone findings 2 to 9 in section 12: which of them this plan fixes, and in which phase.
6. `react-resizable-panels` is held at 3.0.6; version 4 needs a UI change checked by eye.
7. The skellytracker session for phase 2 coordination (image preprocessing), and whether 3 seconds of ring
   history is enough for GPU inference.
8. Pass the hand-off notes to the other sessions: `../project/HANDOFF-camera-media-check-skellyfileformat.md`
   and `../project/HANDOFF-camera-media-check-skellytracker.md`.
9. Pushes: this commit on `dom/research`; `1e21f8a` in `../project`.

Not a result: `usb_cameras/results/windows/Gerald/suite_20261117T221102Z/` (untracked; the server never
started in that run).

Standing rules made on 2026-11-17: no camera recordings or frames in git unless golden reference files; no AI
attribution in skellycam commits; Python 3.13.18; skellyfileformat is a spec only; port 53117 may be held by
another session's process, so test servers use another port and nothing is sent to 53117.

Changed on 2026-11-18 (later): Dom accepted the phase 2 ring spec with all 51 of its proposals (P45, the longer
wait in the OpenCV loop, only if a timing measurement on the four cameras shows no harm; the 40 mechanical
ones can be reopened when the tests are written). On his instruction the spec and the phase 2 work are in the
implementation worktree (`../skellycam-native-jpeg`, branch `dom/native-jpeg`), not in this folder. The draft
cited `frame_ring_buffer/docs/jpeg_ring_design_notes_20261117.md` and this file by line number as they are in
this commit. Queued after phase 2: skellycam's part of the skellytracker volunteer "certify suite", on a new
branch `dom/jpeg-testing`, spec first.
