# Phase 3 capture specification: Windows native capture (3a, 3b, 3c)

Status: accepted by the user on 2026-11-19, with the agent choices of section 18
([ADR-4CQC](../decisions/entries/4CQC-phase-3-windows-capture-spec-and-test-list.md)). The failing
tests of a step come before the product code of that step. The decisions D1 to D49 are accepted
by the user ([ADR-EN7A](../decisions/entries/EN7A-phase-3-windows-capture-decisions.md)). Section
20 gives each one in full. The user gave fifteen answers on 2026-11-19, to the questions of the three
drafts and to one agent choice
([ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)). The user
gave eight more answers U16 to U23 on 2026-11-19, after the review of the failing tests of step 3a
([ADR-HB4Z](../decisions/entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md)). They correct this spec. Items 65 to 78 of section 18 came with that pass. The user gave eight
more decisions W1 to W8 on 2026-11-19 and 2026-11-20, after the review of the 3a code ([ADR-PDD3](../decisions/entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md)).
W1 accepts items 65 to 78, with the changes of W2 and W3.

Note of 2026-11-20 (the connection of the take recorder of step 5a, [ADR-YNM2](../decisions/entries/YNM2-connection-of-the-take-recorder-to-the-shared-loop.md)): the edits of section 14 of
[`recorder.md`](recorder.md) are made, with the decisions R1 to R5, M1 to M5, C1, C5 and C6 of that spec. The changed sections
are 1.3, 1.4, 2.3, 5.1, 5.4, 5.5, 5.7, 6.6, 8.1, 8.2, 9.5, 11.3, 11.5, 11.6, 12, 13.2, 13.3, 16.2 and
17.2. The interim rules U4, U5 and U12 are removed; section 20 keeps their text. The tests T-CAP-09,
T-CAP-10, T-CAP-35 and T-CAP-85 are replaced by T-REC-41 to T-REC-44 of [`recorder.md`](recorder.md).

## 0. How to read this spec

Marks:

- **[Dn]**: decision n of the user, 2026-11-19 (section 20,
  [ADR-EN7A](../decisions/entries/EN7A-phase-3-windows-capture-decisions.md)).
- **[Un]**: answer n of the user to a question of a draft or to an agent choice, 2026-11-19 (section 20,
  [ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md) for U1 to
  U15, [ADR-HB4Z](../decisions/entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md) for U16 to U23).
- **[Wn]**: decision n of the user after the review of the 3a code, 2026-11-19 and 2026-11-20
  (section 20, [ADR-PDD3](../decisions/entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md)).
- **[ring x.y]**: section x.y of [`frame-ring.md`](frame-ring.md), the accepted phase 2 spec
  ([ADR-50G8](../decisions/entries/50G8-phase-2-frame-ring-spec.md)). This spec cites the ring spec.
  It does not repeat it.
- **[P §n]**: section n of `research/NATIVE_JPEG_CAPTURE_PLAN.md`. **[notes: row]**: a row of the
  decision tables in `research/frame_ring_buffer/docs/jpeg_ring_design_notes_20261117.md`. **[M
  file]**: measured; the file holds the result. **[proto file]**: the research prototype
  `research/usb_cameras/suite/windows/pymf/<file>` does this. Each of these files is on branch
  `dom/research` at commit fc95be447 of this repository. They are not on this branch.
- **[NV]**: not verified. The prototype does not prove it, or nobody measured it.
- **[agent n]**: an agent filled a gap that the decisions, the ring spec and the plan do not fix.
  Section 18, item n, lists each one. Section 19 holds the questions for the user.

This spec uses British spelling. Code names (`CameraConfig`, `should_grab_by_id`) are from branch
`dom/native-jpeg`, read on 2026-11-19. The spec cites files, not line numbers.

## 1. Purpose, scope, non-goals, terms

### 1.1 Purpose

Phase 3 replaces OpenCV capture on Windows with pure-Python Media Foundation through `comtypes`,
with no compiled extension, built on `development-streaming` [D1]. The camera JPEG goes untouched to the recorder path and to the JPEG
ring [D2]. One shared camera loop serves three sources: Media Foundation, OpenCV and a fake source
for tests [D6].

### 1.2 Scope

| Step | Delivers |
|---|---|
| 3a | MJPG modes through Media Foundation. The shared loop, the capture interface, the fake source, Media Foundation detection and `camera_id`, `supported_modes`, the start-up rules, the rate check, the camera states, live exposure changes, failure reports, the Windows fix of T-RING-46, the CI job [D2, D11, D14, D42, D47, D48]. |
| 3b | Uncompressed modes (YUY2, NV12): the JPEG encoder, the central Quick Sync check and the range rule, chosen through `capture_fourcc` [D2, D19]. |
| 3c | The full mode list as a second field, gain and focus controls, white balance and power line frequency read only [D2, D14, D43, D44]. The last commit of phase 3 deletes the OpenCV source on Windows [D8]. |

Each step has its own tests and its own camera run [D2].

### 1.3 Non-goals

- H.264 modes: listed as not selectable in the 3c list, never opened; `supported_modes` of 3a stays
  MJPG only [D4, U8].
- A merge of upstream `sfn26`. It is a source of ideas only [D1]. No Rust [D1].
- The USB link display and the Windows event-log check [D45].
- A change of the UVC power line frequency control, a flicker measurement, exposure advice [D44].
- Linux and macOS native capture (phase 7) and the hardware runs of phase 0 [D5, D46].
- The removal of the lockstep gate (phase 8) [D5, ring 2.2].
- UVC PTS/SCR timestamps, driver or registry changes (tier 0 only) [P §2].

### 1.4 Decided elsewhere

| Subject | Where | This spec |
|---|---|---|
| What the writer receives per frame | [ring 5.1] | Section 4.2 maps each item to the sources. |
| Recorder first, then the ring | [ring 5.3] | Section 5.1 keeps the order. |
| Ring recreation on a mode change | [ring 7.5] | Section 5.3 and the state model reuse it. |
| BGR ring, decode stage, waiting place | [ring 8.2, 8.3] | Section 5.5 feeds it. |
| Uncompressed hand-over to the BGR ring | [ring 8.7] | Section 13 adds only the capture side. |
| OpenCV as a source | [ring 8.8] | Section 14 keeps it on Linux and macOS. |
| libjpeg warnings | [ring 8.9], [ADR-E817](../decisions/entries/E817-choices-of-the-2b-code.md) item 7 | Section 5.6 gives the Windows fix [D42]. |
| No thread spins | [ring 8.10] | Section 4.3 applies it to capture. |
| Mode list fields | [ring 9] | Section 7.4 fills them in 3c. |
| Encoder, Quick Sync check, range rule | [notes: JPEG encoder, Encoder check, Encoder settings, Input range] | Section 13. |
| One process per camera; no fallback | [P §3] | Kept. |
| The recorder | [`recorder.md`](recorder.md) | Section 5.1 gives it each recorded frame (note of 2026-11-20). |

D23 replaces the plan statement "a camera that fails or hangs at open stops the session from
starting" [P §3]. D38 replaces the plan statement that native capture only "reports a slow or stalled camera"
mid-take [P §3].

### 1.5 Terms

| Term | Meaning |
|---|---|
| source | An object that gives frames of one camera to the shared loop (section 4). |
| shared loop | The one camera loop in each camera process. It knows the gate, the recorder and the rings [D6]. |
| push source | A source whose frames arrive on a thread of the source (Media Foundation, fake). |
| delivered frame | A frame that the source got from the camera. |
| taken frame | A delivered frame that the shared loop took through `read_frame`. |
| replaced frame | A delivered frame that a newer frame replaced before the loop took it [D26]. |
| mode rate | The frame rate of the mode that Media Foundation reports as set after the open [D22]. |
| warm-up | The first 90 frames after the controls are set and read back. They are discarded [D21]. |
| selected camera | A camera in the group with `use_this_camera` true. |
| gate | The lockstep gate, `CameraOrchestrator.should_grab_by_id` (`camera_group/camera_orchestrator.py`). |
| bounded call | A call that runs on a worker thread with a time limit [D10, proto bounded.py]. |

## 2. Steps and their done lists

### 2.1 Step 3a [D48]

Step 3a is done when:

1. All fake-source tests pass on the Windows development machine and on the Windows, Linux and macOS
   CI runners [U20]. The Windows-only tests of 16.1 pass on Windows and are skipped on the other
   systems [U18]. The tests of the kind "local" (T-CAP-49, T-CAP-50) pass on the Windows development
   machine; they do not run in CI.
2. The hardware tests pass on the C922, the C930e and the Kiyo Pro, and the rate check refuses the
   generic camera. T-CAP-54 and T-CAP-55 (D49) are part of this item. They record results and have
   no pass value (16.3). The Linux and macOS hardware tests T-CAP-92 to T-CAP-98 are not part of this
   list. They wait for phase 0, through the certify suite [U21].
3. A three-camera recording, OpenCV loop against native loop, gives equal frame counts across
   cameras, a group rate within 1 % of 30 fps, and no lost camera frame that the replaced-frame count
   does not explain. Both counts start at the first frame that the camera takes in the gate (5.2).
   Section 16.4 gives the run [agent 40].
4. T-CAP-49 (idle CPU of the shared loop under 2 % of one core, the rule of T-RING-31) and T-RING-46
   pass on Windows. T-RING-31 is retired with the phase 2 loop [W8]. The product code of step
   3a changes T-RING-46 and removes its expected-failure mark on Windows, because the warning pipe
   moves to the main process (5.6) [U17].

### 2.2 Step 3b [agent 37]

Step 3b is done when:

1. All fake-source tests of 3a and 3b pass on the three platforms of 2.1 item 1.
2. The 3b hardware tests pass: each test camera that offers a YUY2 or NV12 mode at 30 fps or more
   (at any size) opens in it, and its range decision agrees with
   `research/frame_ring_buffer/yuy2_range/FINDINGS.md` (C922 and C930e limited; Kiyo Pro full). The
   same file states that the C930e and the C922 offer YUY2 at 1280x720 only up to 10 fps. Under the
   floor of U11, the 3b hardware tests use YUY2 640x480 at 30 on the C922 and the C930e, YUY2
   1280x720 at 30 on the Kiyo Pro, and NV12 1280x720 at 30 on the generic camera (the generic camera
   can fail the rate check there).
3. A recording with one mode rate for the group and at least one camera in an uncompressed mode
   gives equal frame counts, a group rate within 1 % of the mode rate, no lost frame that the
   replaced-frame count does not explain, and no encoder fallback.
4. T-RING-47 passes, and T-CAP-49 still passes on Windows [W8].

### 2.3 Step 3c [agent 37]

Step 3c is done when:

1. All fake-source tests of 3a, 3b and 3c pass on the three platforms of 2.1 item 1.
2. The 3c hardware test of D49 (T-CAP-77) runs on the C922, the C930e and the Kiyo Pro, and its
   results are recorded (16.3). Gain and focus set and read back on each camera that has them. White
   balance and power line frequency are read; step 5d writes them to the capture info.
3. The full mode list of each of the four test cameras agrees with the descriptor list of the
   prototype for the same camera.
4. The last commit of phase 3 deletes the OpenCV source on Windows and the source setting [D8]. After
   it, all fake-source tests and T-CAP-76 pass.

## 3. Module layout and dependencies

The prototype stays where it is. The product module is new and smaller, and it is written from the
proven calls of the prototype [D7]. The layout [agent 1]:

| Path | Content |
|---|---|
| `skellycam/core/camera/capture/source.py` | `CaptureSource` protocol, `CapturedFrame`, `OpenedMode`, `ControlState`, `CaptureFailure` (section 4). No `comtypes` import. |
| `skellycam/core/camera/capture/camera_loop.py` | The shared loop. It replaces `opencv/opencv_camera_loop.py`. Note, 2026-11-20: the old loop, its worker method and its own helpers are deleted ([ADR-037V](../decisions/entries/037V-completion-of-w8-the-phase-2-loop-and-its-tests.md)). |
| `skellycam/core/camera/capture/rate_check.py` | The rate formula, the limits, the early decision (section 10). Pure functions. |
| `skellycam/core/camera/capture/modes.py` | `supported_modes`, the mode choice, the auto rate, the rate tolerance, the group rate rule (section 7). Pure functions. |
| `skellycam/core/camera/capture/media_foundation/` | `com.py` (interface declarations), `bounded.py`, `errors.py` (HRESULT to reason, pure), `detect.py`, `source.py` (`MediaFoundationSource`). Windows only: the whole package, and each module can import `comtypes`. Its tests run on Windows only (16.1) [U18]. |
| `skellycam/core/camera/capture/opencv_source.py` | `OpenCVSource`, from the code in `opencv/opencv_helpers/` (section 14). |
| `skellycam/core/camera/camera_worker.py` | The worker target becomes `camera_worker_method`, the current `opencv/opencv_camera_worker_method.py` with a source choice. |
| `skellycam/tests/capture/` | The tests of section 16 and the fake source `fake_source.py` [agent 2]. |

Dependencies:

- `comtypes==1.5.0; sys_platform == "win32"` in `pyproject.toml` [D7]. The prototype pins 1.5.0.
  PyPI listed 1.5.0 as the latest release on 2026-11-19 (released 2026-11-09).
- No compiled extension and no import of `_skellycam_rust` [D1].
- PyAV (`av==19.0.2`, already pinned) gives Quick Sync in 3b [notes: JPEG encoder].
- `cv2_enumerate_cameras` stays for Linux and macOS. On Windows, detection uses Media Foundation
  [D11].

## 4. Capture interface [D6]

### 4.1 Calls

A source has four calls [D6]:

| Call | Does | Returns or raises |
|---|---|---|
| `open(request) -> OpenedMode` | Opens the camera, chooses the mode, starts the stream and waits for the first frame (section 6 for Media Foundation). | `OpenedMode`: width, height, `fps_num`, `fps_den` (the mode rate), format, the device path. Raises `CaptureFailure` with a stage and a reason. |
| `read_frame(timeout_s) -> CapturedFrame or None` | Gives the newest frame that the loop has not taken. If there is none, it waits for the next one, at most `timeout_s` [D26]. | A `CapturedFrame`, or `None` after the timeout. Raises `CaptureFailure` after a stream error. |
| `set_controls(changes) -> ControlState` | Sets each control in `changes`, then reads each control back [D20]. `changes = {}` only reads [agent 3]. | The read-back state of every control (section 11.4). Raises `CaptureFailure` on a hung call. |
| `close() -> None` | Closes in the order of section 6.9. Each step is bounded. | Raises `CaptureFailure` with stage `close` after a hung step. |

The source also has `replaced_count` (an int): the frames that a newer frame replaced since the open
[D26, D27]. The loop reads it at the first frame that the camera takes in the gate, and it reports
the difference from then on (5.2) [agent 49].

`request` holds the requested width, height, rate (a value of -1 or 0 means "auto" [D16]), the
format (`capture_fourcc`, MJPG unless 3b [D19]) and the device to open (section 6.2).

### 4.2 What `read_frame` returns per frame

`CapturedFrame` carries the items of [ring 5.1] that come from capture, plus three more:

| Field | Type | Media Foundation | OpenCV | Fake |
|---|---|---|---|---|
| `payload` | `bytes` (MJPG); `numpy.ndarray` (YUY2, NV12 in 3b; BGR from OpenCV) | One `bytes` object, copied out of the `IMFMediaBuffer` of the sample [proto mf.py `process_sample`] | The decoded BGR image of `retrieve` | A synthetic JPEG made by `cv2.imencode` |
| `format` | str | `MJPG`, `YUY2`, `NV12` | `BGR` | any of these |
| `arrival_ns` | int | `perf_counter_ns()` at entry to `OnReadSample` [D28] | `perf_counter_ns()` after `grab()` returns (as the 2a loop) | as scripted |
| `sample_ns` | int | `100 x IMFSample::GetSampleTime` [agent 10] [NV] | `NO_SAMPLE_NS` | as scripted |
| `delivered_len` | int | the current length of the media buffer | set by the loop: `len` of the re-encoded JPEG | as scripted |
| `driver_error` | bool | `False` [agent 11] [NV] | `False` | as scripted |
| `source_frame_number` | int | the running count of delivered frames since the open, from 0 [D27] | the count of successful grabs since the open, from 0 [agent 5] | as scripted |
| `discontinuity` | bool | `MFSampleExtension_Discontinuity` is non-zero [proto mf.py] | `False` | as scripted |

A gap in `source_frame_number` between two taken frames shows only the frames that the gate did not
take, because the count counts delivered samples [D27]. A frame that the camera drops leaves no gap
there. It shows only in the `DISCONTINUITY` flag [D34] [NV: that Media Foundation sets the
discontinuity attribute on the next sample after a drop]. The shared loop computes `frame_number`
itself (section 5.3).

The `sample_ns` rule [agent 10]: the source writes `NO_SAMPLE_NS` for the rest of the open when a
sample time is later than its arrival time, or more than 200 ms earlier. T-CAP-59 checks the rule on
the cameras.

### 4.3 Threading rules

| Thread | Rule |
|---|---|
| Media Foundation callback thread (a work-queue thread of Media Foundation) | `OnReadSample` takes `arrival_ns` first. It copies the buffer into one `bytes` object, puts the frame in the waiting place, and issues the next `ReadSample` [proto mf.py `ReaderCallback`]. It does no file I/O, no logging per frame, no decode and no wait other than the waiting-place lock. It never raises into Media Foundation. |
| Waiting place | One place per source, at most one frame. A new frame replaces a waiting frame, and the replaced frame counts in `replaced_count` [D26]. When the replaced frame carried a discontinuity, the frame that replaces it carries it too. Thus the next taken frame has the flag [D34] [agent 46]. A source error puts an error marker in the place. The marker wakes the loop at once, and `read_frame` raises `CaptureFailure` [agent 50]. When a frame waits, the marker waits behind it: `read_frame` gives the frame, and the next call raises at once. The marker never replaces a frame [agent 66]. The source uses the rules of `WaitingPlace` of the ring package (`skellycam/core/ipc/frame_ring/decode.py`), with these two additions [agent 4]. The put never waits longer than the time to take the lock [ring 8.3]. |
| Camera loop thread | Waits only in `read_frame`, on the condition of the waiting place, with a timeout [ring 8.10]. It never polls in a loop without a block or a sleep of at least 1 ms. After the start-up, it never calls `set_controls` [U16]. |
| Control thread | One thread for each camera process [U16]. From the end of the start-up, it reads the controls one time per second with `set_controls({})` (11.4), and it applies each live control change (11.2). It sleeps between the reads, with no spin [ring 8.10]. It never waits on the gate. A hung control call blocks only this thread; the loop thread keeps taking frames until the camera process ends (6.6). |
| Bounded-call workers | One short-lived thread per bounded call [proto bounded.py]. Each joins the multithreaded apartment (MTA) first [agent 43]. |
| Decode thread (BGR ring) | As [ring 8.2, 8.3]. |

No thread of the camera process spins [ring 8.10]. T-CAP-49 checks this on the shared loop [D48]. T-RING-31,
the test of the phase 2 loop, is retired [W8].

### 4.4 The three sources

| Source | OS | How it meets the interface |
|---|---|---|
| `MediaFoundationSource` | Windows | Section 6. A push source: an async `IMFSourceReader` with an `IMFSourceReaderCallback` [proto mf.py]. |
| `OpenCVSource` | Linux, macOS; Windows only while the setting of section 14.2 chooses it | A pull source. `read_frame` calls `grab()` and `retrieve()` and returns the BGR image. `replaced_count` stays 0. Section 14. |
| `FakeSource` | all (tests) | A push source on its own thread with a scripted list of modes, arrival times, controls and faults (section 16.1). |

## 5. The shared loop

### 5.1 Steps of one frame

For each taken frame, the loop does these steps in this order:

1. **Gate.** Wait until `should_grab_by_id` is true for this camera (5.2).
2. **Read.** `read_frame` gives the newest frame [D26].
3. **Stall watch.** Section 9.5 and 8.2.
4. **JPEG.** MJPG: the payload is the JPEG. BGR (OpenCV): `cv2.imencode` at quality 90 [ring 2.3,
   8.8]. YUY2 or NV12: the encoder of section 13.
5. **Capture check.** `check_jpeg(payload, delivered_len=..., driver_error=...)` [ring 5.2]. If
   `discontinuity` is true, add `DISCONTINUITY` to the flags [D34].
6. **Recorder.** If the frame is recorded, give it to the recorder ([`recorder.md`](recorder.md) section 10) [ring 5.3].
7. **JPEG ring.** `FrameRingWriter.write` with `newer_frame_waiting=False` [agent 6].
8. **BGR ring.** If the camera has a BGR ring, put the BGR image in the waiting place of the decode
   stage (5.5) [ring 5.3 step 4].
9. **Counts.** Set `frame_count` in the camera status, as the 2a loop does.

A failing ring write does not stop capture or recording, as in the 2a loop [ring 5.3].

### 5.2 Lockstep gate with a push source [D26]

- When the gate opens for a camera, the loop takes the newest frame that it has not taken yet. If
  there is none, it waits for the next one [D26].
- Frames that arrive while the gate is closed are replaced by newer frames and counted in
  `replaced_count` [D26].
- At stop, the loop logs one line per camera with the number of frames replaced since the first frame
  that the camera took in the gate [D27] [agent 49]. Thus this count and the gaps of
  `source_frame_number` between taken frames cover the same span.
- The gate counts only cameras in the states `checking`, `too_slow`, `ready` and `recording`
  (section 8). A camera in `starting`, `waiting`, `failed` or `dead` does not hold the gate back
  [agent 47]. This follows from D23 and D38: the other cameras keep their preview and
  their recording. `should_grab_by_id` and `CameraOrchestrator.all_ready` must change for this.
  Today they need the status of every camera to be ready.
- A camera that joins the gate again (after "apply again" or a mode change) starts with the largest
  gate count of the group [agent 5].

### 5.3 Frame numbers [D27]

- `frame_number` in the ring is the count of frames that the loop took since the ring was created,
  from 0 [ring 7.5, A17] [agent 5]. Thus the frame numbers of the cameras of a group stay equal under
  the gate. The interim relay sends the newest frame of each camera on its own (5.8) [U13].
- `source_frame_number` in the ring is the running count of the source (4.2) [D27].
- The gate count (`frame_count` of the camera status, and the frame number of the old frame record)
  continues across a ring recreation, as `check_for_new_config` does today [agent 5].
- After a ring recreation [ring 7.5], `frame_number` starts at 0 again. After a reopen, the source
  count starts at 0 again.

### 5.4 Timestamps [D28, D41]

- The frame time for the recorder and the ring lookup is `arrival_ns` [D28].
- `sample_ns` goes into the slot header and into the CSV of the recorder [D28].
- The Media Foundation and fake sources do not stamp `pre_frame_retrieve_ns` and
  `post_frame_retrieve_ns`.
- Each camera process has its own camera writer. The connection refuses a take spec whose `camera_id`
  is not the camera of the process [D41].
- The nominal rate of the recorder is the mode rate ([`recorder.md`](recorder.md) 6.5).

### 5.5 Decode for the BGR ring [D9]

The decode of a JPEG runs only for a BGR ring, in the decode stage [ring 8.2 to 8.4]. (Changed on
2026-11-20: the interim decode for the old recorder and its rule U5 are removed.)

### 5.6 libjpeg warnings on Windows [D42]

- The main process gives each camera process a pipe as its error output before OpenCV loads [D42].
  This applies the fix of [ADR-E817](../decisions/entries/E817-choices-of-the-2b-code.md) item 7 and [ring 8.9] on Windows.
- The main process holds the read end. One thread per camera process reads the pipe and logs each
  different line one time per minute at most, with a count [ring 8.9] [agent 42]. In [ring 8.9] the
  camera process reads the pipe. Section 17.2 lists this difference.
- How a spawned process gets the pipe as its standard error handle is [NV]. `multiprocessing` does
  not pass standard handles on Windows by default. The code must show a method, and T-RING-46 must
  pass on Windows [D48].
- The stand-in child of T-RING-46 calls `limit_libjpeg_warnings()` itself. Thus T-RING-46 and its
  expected-failure mark on Windows change together with the product code of step 3a [U17].

### 5.7 A recording with a dead camera [M1]

A dead camera during a recording: [`recorder.md`](recorder.md) 7.3. Its process runs to the end of the recording and writes
placeholders [M1]. (Changed on 2026-11-20: the interim rule U4 is removed.)

### 5.8 The interim preview relay (until phase 4) [U13]

- The websocket relay of [ring 2.3] sends the newest frame of each camera on its own. It does not
  wait for equal frame numbers [U13]. `CameraGroup.read_latest_ring_frames` changes for this.
- Thus the preview frames of different cameras can be one gate round apart. After one camera is
  reopened, the preview of the other cameras continues.
- The relay leaves out a camera that has no frame to show, for example a camera in `starting`. Each
  frame header carries the frame number of its own frame. The message header carries the largest
  of them [agent 54].
- Phase 4 replaces this relay [U13]. Section 17.2 lists the difference from [ring 2.3].

## 6. The Media Foundation source

Each call and interface below is in the prototype [proto mf.py, com.py, bounded.py], unless marked
[NV].

### 6.1 Process set-up

- Each camera process calls `CoInitializeEx` with the MTA and `MFStartup(MF_VERSION)` one time, before
  the first Media Foundation call [proto com.py] [agent 43].
- At the end, it calls `MFShutdown` and `CoUninitialize` only when no bounded call was abandoned
  [proto bounded.py]. Otherwise it ends hard (6.6).

### 6.2 Open by device path [D12]

1. Enumerate: `MFCreateAttributes`, `IMFAttributes::SetGUID(MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE,
   MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID)`, `MFEnumDeviceSources`. Read
   `MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME` and `MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK`
   of each `IMFActivate` [proto mf.py `enum_mf`]. Each open enumerates again [proto mf.py
   `open_session`].
2. Match: keep the one device whose `camera_id` (7.2) equals the `camera_id` of the config. Release the
   other `IMFActivate` objects. No device: failure, stage `open`, reason "camera not found" [agent 48]. Two
   devices: failure, stage `open` [D13] [agent 12].
3. Activate: `IMFActivate::ActivateObject(IID_IMFMediaSource)`, bounded. A call that returns after its
   time limit shuts down its own source [proto mf.py `activate`].
4. Query `IAMCameraControl`, `IAMVideoProcAmp` and `IKsControl` from the `IMFMediaSource` [proto mf.py
   `get_ifaces`].
5. Create the reader: `MFCreateSourceReaderFromMediaSource` with `MF_READWRITE_DISABLE_CONVERTERS = 1`,
   `MF_SOURCE_READER_DISCONNECT_MEDIASOURCE_ON_SHUTDOWN = 1` and `MF_SOURCE_READER_ASYNC_CALLBACK` set
   to the callback object, bounded [proto mf.py `make_reader`].

The camera is never opened by its index [D12].

### 6.3 Mode choice [D15, D16, D17]

1. List the native types of the first video stream: `IMFSourceReader::GetNativeMediaType` with index
   0, 1, ... until it fails. Read `MF_MT_SUBTYPE`, `MF_MT_FRAME_SIZE` and `MF_MT_FRAME_RATE` of each
   [proto mf.py `choose_on`].
2. Choose by section 7.5. Never take the first match: Media Foundation lists a synthesized NV12 type
   immediately before each MJPG type [proto parse.py `select_native_type`, `flag_types`].
3. `SetStreamSelection(MF_SOURCE_READER_ALL_STREAMS, FALSE)`, then
   `SetStreamSelection(MF_SOURCE_READER_FIRST_VIDEO_STREAM, TRUE)`, then
   `SetCurrentMediaType(MF_SOURCE_READER_FIRST_VIDEO_STREAM, NULL, type)`, bounded.
4. Read back with `GetCurrentMediaType`. The subtype, the size and `fps_num`/`fps_den` must equal the
   chosen type. If not, failure, stage `set mode` [proto mf.py `choose_on`].
5. The read-back rate is the mode rate. The rate check compares with it [D22], and the config stores
   it [D17].

### 6.4 Stream start and first frame

1. Issue the first `ReadSample(MF_SOURCE_READER_FIRST_VIDEO_STREAM, 0, NULL, NULL, NULL, NULL)`,
   bounded [proto mf.py `open_session`].
2. Wait for the first sample, at most 5 s from the first `ReadSample` [agent 14]. This is a wait,
   not a hung call: the async `ReadSample` returned, and no sample came. A timeout or a failed
   HRESULT gives a failure with stage `first frame`. Then the close runs with its bounded steps
   (6.9). The process does not end hard for this.
3. `open` returns after the first frame [D20].

### 6.5 The callback

`OnReadSample(hr, stream_index, flags, timestamp, sample)` [proto mf.py `ReaderCallback`]:

1. `arrival_ns = perf_counter_ns()`.
2. A failed `hr`, or `MF_SOURCE_READERF_ERROR`: record the first error, put the error marker in the
   waiting place (it wakes the loop, 4.3), and do not issue a new read. `MF_SOURCE_READERF_ENDOFSTREAM`: the same, with the reason "end of stream".
3. A sample: `IMFSample::ConvertToContiguousBuffer`, lock the `IMFMediaBuffer`, copy the current
   length into one `bytes` object, unlock. Read `GetSampleTime` and `MFSampleExtension_Discontinuity`.
   Increment the source count. Put the frame in the waiting place.
4. A null sample (a stream tick) is not a frame.
5. Issue the next `ReadSample` unless the source is closing [proto mf.py].

### 6.6 Bounded calls and the hard end of the process [D10]

- These calls are bounded: enumerate, `ActivateObject`, the reader creation, the mode set, the first
  `ReadSample`, each control call, `Flush`, each release and each `Shutdown` [D10, proto
  bounded.py].
- Each bounded call has a time limit of 5 s [agent 14]. Only a call that does not return within its
  limit is a hang. The wait for the first frame is not a call (6.4). The prototype used 5 s
  [M `research/usb_cameras/docs/windows_results_20261113.md` §2.2]. On the four test cameras, the
  first frame took 75 to 597 ms (same file, §2.1).
- On a hang, the camera process first reports the failure (section 12) to the main process. Then it
  ends itself with `os._exit` and a non-zero exit code [D10, proto bounded.py] [agent 16]. It does not
  call `MFShutdown` or `CoUninitialize`. It does not run the finalisation of the interpreter.
- On a hang during a recording, the camera process reports, then ends at once. The main process
  completes its files after the process has ended ([`recorder.md`](recorder.md) 7.4) [R4, M5]. (Changed on 2026-11-20: the
  interim rule U12 is removed.)
- After the start-up, each control call runs on the control thread (4.3) [U16]. While it hangs, the
  loop thread keeps taking frames, so the camera does not hold the gate, and the other cameras lose
  no frame. After the limit, the camera process reports and ends hard, as for each hang.
- The main process treats the exit of a camera process that reported a failure as the failure of that
  camera. It does not treat it as a crash of the backend [D10] [agent 16].
- The main process cleans up only that camera: its rings, its worker and its status [D10].
- Other cameras are not touched [D10].
- A bounded call keeps its own COM reference. Thus a hung call never uses an object that the caller
  released [proto mf.py `ref`].

### 6.7 Errors: in use, device removed, stall

| Event | Detection | Result |
|---|---|---|
| In use by another program | `0xC00D3704` (`MF_E_HW_MFT_FAILED_START_STREAMING`), `0xC00D3EA3` (`MF_E_VIDEO_RECORDING_DEVICE_PREEMPTED`), `0x80070964` (`ERROR_DEVICE_IN_USE`), `0x800700AA` (`ERROR_BUSY`) at any open stage [proto parse.py `error_class`] [agent 15]. Measured: a second open of a held C930e failed with `0xC00D3704` at the first frame [M `research/usb_cameras/docs/windows_results_20261113.md` §2.4]. | Failed, reason "in use by another program" [D13]. |
| Device removed | `0xC00D3EA2` (`MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED`), `0x80070651` (`ERROR_DEVICE_REMOVED`), `0x8007048F` (`ERROR_DEVICE_NOT_CONNECTED`), `0x800701B1` (`ERROR_NO_SUCH_DEVICE`) in `OnReadSample` [proto parse.py `error_class`] [agent 15]. | Dead at once [D38]. |
| Other stream error, end of stream | Any other failed `hr`, `MF_SOURCE_READERF_ERROR`, `MF_SOURCE_READERF_ENDOFSTREAM`. | The error marker makes `read_frame` raise at once (4.3, 6.5). The camera is dead at once, with the HRESULT name or "end of stream" as the reason [agent 62]. |
| Stall | No frame for 2 s and no error (9.5). | Dead [D38]. The 2 s rule applies only to this silence. |

### 6.8 Controls

- Exposure and focus: `IAMCameraControl::GetRange`, `Get`, `Set` with `CameraControl_Exposure` and
  `CameraControl_Focus`. Gain, white balance, power line frequency: `IAMVideoProcAmp` with
  `VideoProcAmp_Gain`, `VideoProcAmp_WhiteBalance`, `VideoProcAmp_PowerLineFrequency`. Where the
  `IAM` interface rejects a control, use `IKsControl::KsProperty` with `KSPROPERTY_TYPE_GET` and
  `KSPROPERTY_TYPE_SET` [proto mf.py `read_ctl`, `set_ctl`].
- Flags: `CameraControl_Flags_Auto` (1) and `CameraControl_Flags_Manual` (2) [proto mf.py
  `apply_set`].
- One bounded call does read before, set, read back [proto mf.py `apply_set`]. Measured: 194 control
  sets returned `S_OK` in 1.0 to 3.0 ms and read back correctly
  [M `research/usb_cameras/docs/startup_rate_check_20261119.md`].
- After a control call times out, the source does not touch the interfaces again [proto mf.py
  `run_controls`]. The camera fails (section 6.6).

### 6.9 Close order

This is the order of the prototype [proto mf.py `close_session`]. Each step is bounded. A step that
does not return stops the close there, and section 6.6 applies:

1. Stop issuing reads. Wait for a `ReadSample` issue that is in progress (bounded, waits of 1 ms).
2. `IMFSourceReader::Flush(MF_SOURCE_READER_ALL_STREAMS)`, then wait for `OnFlush`.
3. Release the reader.
4. Release `IAMCameraControl`, `IAMVideoProcAmp` and `IKsControl`.
5. `IMFMediaSource::Shutdown`.
6. `IMFActivate::ShutdownObject`.

Measured: stop to released took 272 to 1,122 ms on the four test cameras
[M `research/usb_cameras/docs/windows_results_20261113.md` §2.1].

## 7. Detection, `camera_id` and modes

### 7.1 Detection on Windows [D11]

- In step 3a, `detect_available_cameras` on Windows uses Media Foundation (6.2 step 1), not
  `cv2_enumerate_cameras` [D11].
- For each device, it activates the source and lists the native types (6.3 step 1) to fill
  `supported_modes`, then closes in the order of 6.9.
- These calls are bounded. Detection runs in a short-lived child process. The child returns the result
  to the main process and ends itself hard after a hang, so that a hung camera cannot block the main
  process [agent 17].
- `CameraDeviceInfo` keeps its fields. `index` is the enumeration index (for display only [D12]),
  `name` the friendly name, `path` the symbolic link, `vendor_id` and `product_id` from the link [proto
  parse.py `parse_usb_ids`].
- A detection result in which two cameras have the same `camera_id` is refused, as the code does
  today [D13].
- `path` is the link as the OS gives it [W6]. `modes_read` is true when detection read the native
  mode list [agent 80].
- Detection shows a virtual camera (its friendly name contains "virtual") with `virtual: true`, on
  each OS. A request that names a virtual camera gets HTTP 422 [W5].
- The main process keeps the last detection result, by `camera_id`, for the whole-request check of
  8.3 and 7.5 [U17]. When that result does not hold each selected camera of a request, the apply
  request runs the detection first [agent 79].

### 7.2 `camera_id` [D11]

- `camera_id` uses the same hash function as today (`CameraDeviceInfo.camera_id`: SHA-256, the first 2
  bytes as 4 hex digits) of the Media Foundation symbolic link [D11].
- The input is the symbolic link in lower case [agent 13]. The prototype matches links without case
  [proto mf.py `open_session`]. Only the hash input is in lower case; `path` keeps the case of the OS
  [W6].
- Every Windows camera gets a new ID one time [D11].

### 7.3 `supported_modes` (3a) [D14]

`CameraDeviceInfo.supported_modes` has the shape of upstream `sfn26` (`CaptureMode` in
`detect_cameras_devices.py`):

```json
"supported_modes": [
  {"width": 1920, "height": 1080, "framerates": [30.0]},
  {"width": 1280, "height": 720, "framerates": [30.0, 60.0]},
  {"width": 640, "height": 480, "framerates": [29.97, 30.0]}
]
```

Rules [D14]:

- MJPG modes only. One entry for each size.
- Sizes by area, largest first; for equal areas, by width, largest first.
- Rates ascending. Duplicates merged after rounding.
- A rate is `fps_num / fps_den`, rounded to 2 decimal places [agent 18]. Thus 30.00003 reports as 30
  and 29.97 stays 29.97. JSON writes 30 as `30.0`. It is the same number for a JSON reader.
- Rates below 29.97 fps are left out. A size with no rate left is left out [U11].
- A camera whose mode list cannot be read has `supported_modes = []`, as on `sfn26`.

### 7.4 Full mode list (3c) [D14]

In step 3c, `CameraDeviceInfo` gets a second field, `capture_modes` [agent 19]. Each item has the
fields of `CameraMode` [ring 9] plus the rounded rate:

```json
"capture_modes": [
  {"width": 1280, "height": 720, "fps_num": 30, "fps_den": 1, "framerate": 30.0,
   "format": "MJPG", "uncompressed": false, "selectable": true, "reason": null},
  {"width": 1280, "height": 720, "fps_num": 10, "fps_den": 1, "framerate": 10.0,
   "format": "YUY2", "uncompressed": true, "selectable": false, "reason": "below 30 fps"},
  {"width": 1280, "height": 720, "fps_num": 30, "fps_den": 1, "framerate": 30.0,
   "format": "H264", "uncompressed": false, "selectable": false, "reason": "never opened"}
]
```

- MJPG, YUY2 and NV12 modes are listed. A size and rate in MJPG and YUY2 is listed two times [ring 9].
- YUY2, NV12 and RAW have `uncompressed: true` [ring 9].
- H.264 and RAW modes are listed with `selectable: false`. They are never opened [ring 9, D4, U8].
  `supported_modes` of 3a stays MJPG only.
- An NV12 type that comes immediately before an MJPG type of the same size and rate is left out: Media
  Foundation made it from the MJPG type [proto parse.py `flag_types`] [agent 19] [NV for cameras
  other than the four test cameras].
- Order: sizes as in 7.3, rates ascending, and for one size and rate MJPG first ("JPEG preferred")
  [D14] [agent 19].
- A mode below 29.97 fps is listed with `selectable: false` and the reason "below 30 fps" [U11]
  [agent 53]. The field `reason` is null for a selectable mode. H.264 and RAW modes have
  the reason "never opened" [agent 53].
- `supported_modes` stays as in 7.3.

### 7.5 Mode choice, auto rate, group rate

- **Mode choice** [D15]: exactly the requested size, in the requested format (MJPG unless 3b [D19]), at
  the rate nearest to the request within 0.5 fps. Of two equally near rates, the first in the native
  list wins [proto parse.py `select_native_type`]. No such mode: the camera fails, stage `set mode`,
  with a message that lists its modes in the form of 7.3.
- **Floor of 30 fps** [U11]: skellycam does not offer a mode below 30 fps. A mode at 29.97 fps counts
  as 30: the floor is 30000/1001 fps.
  - The floor applies to the exact rate of the chosen mode (`fps_num / fps_den`, before rounding for
    display), not to the requested number [agent 58].
  - A request of -1 or 0 is "auto". The floor never refuses it.
  - A request between 29.47 and 29.97 fps follows D15 (the nearest mode within 0.5 fps). It is
    accepted when the chosen mode is at the floor or above.
  - A request whose nearest mode is below the floor is refused. A request more than 0.5 fps below the
    floor can never choose a mode at the floor. The whole-request check refuses it on each source
    (HTTP 422) [agent 55].
  - Where each case is decided [agent 58]: in the whole-request check (HTTP 422) when the
    detection data already shows that the camera has no mode at the floor or above at that size, or
    that the nearest mode is below the floor; else at the open, stage `set mode`. A camera with
    `modes_read` and an empty `supported_modes` has no mode at the floor [agent 80]. The reason is "no
    mode at 30 fps or more" in both cases [U11].
- **Auto rate** [D16]: a requested rate of -1 or 0 means 30 fps if the camera has 30 in MJPG at the
  requested size, else the highest rate that it has there. No region rule. Only the modes at the
  floor or above count [U11]. Because 29.97 counts as 30, a camera with 29.97 and 60 but no 30 at
  the size gets 29.97 [agent 57].
- **Stored rate** [D17]: the config stores the mode rate, so -1 becomes the real rate.
- **Tolerance** [D17]: frame rates compare with a relative tolerance of 0.0001
  (`math.isclose(a, b, rel_tol=1e-4)`).
- **One rate per group** [D18]: while the gate exists, all cameras of a group must have the same mode
  rate. The rule compares mode rates, not measured rates. A request for a group with different mode
  rates is refused as a whole, and no camera is opened [U7].
- The rule runs in the whole-request check (8.3), before any open, on each source [U7, U10]
  [agent 20].
- Media Foundation: the check compares the mode rates that 7.5 gives from the detection data. For
  MJPG it uses `supported_modes`. For a YUY2 or NV12 request of 3b, it uses the full native type list
  that detection keeps: the list that 3c publishes as `capture_modes` [agent 20].
- OpenCV: the check compares the requested rates. They must be all equal (with the tolerance of D17)
  or all auto [agent 56]. On Windows during the build, the check uses the Media Foundation
  detection data for both sources [agent 56].
- After the open, OpenCV can report different real rates for the cameras. That gives a warning only.
  It is not a refusal, and no camera is closed [agent 56]. The warning is a log record at WARNING and
  an item of the kind `mixed_rate` in the `warnings` list of the apply response [W3]. Linux and macOS behaviour is not
  tested until phase 0 [D46].
- **Rate class 30** [U15]: the one-rate rule treats 30000/1001 (29.97) and 30/1 (30) as one rate
  class. This is the exception to the tolerance of 0.0001 of D17 for D18. Each other difference is
  still refused, for example 30 with 60, or 29.97 with 60. The rate check of each camera uses its own
  mode rate [U15].
- A group that mixes the two rates of the class is allowed, with a warning [U15]:
  - Under the gate, the group runs at the lower rate: 29.97 rounds per second. A camera at the higher
    rate delivers one frame more than the gate takes about every `1 / (r_high - r_low)` seconds.
    That frame is replaced, counted in `replaced_count` and in the gaps of `source_frame_number`
    (D27), and missing from the recording. No frame is repeated, because the gate waits for the next
    frame.
  - The interval uses the exact mode rates (`fps_num / fps_den`). For 30000/1001 and 30/1 it is
    1001/30 s = 33.4 s. The text gives it in whole seconds [agent 63].
  - The text has this form, with camera IDs: "Cameras a1b2 and c3d4 run at 29.97 fps, cameras e5f6
    and a7b8 at 30 fps. The group runs at 29.97 fps. Cameras e5f6 and a7b8 skip one frame about
    every 33 s; each skipped frame is counted and is missing from the recording." [U15]
  - The warning goes into the `warnings` list of the response of the apply request and into the
    log, in the form of 11.3, with the kind `mixed_rate` [U15] [agent 63].
- On a running group, the rule is part of the check of the whole request (8.3) [U10]. Example: three
  cameras run at 30 fps, and a request asks one of them for 60. The one-rate rule refuses the
  request, and all three cameras keep running at 30 [U10].
- **H.264** [D4]: never chosen and never opened.

## 8. Camera states

### 8.1 States

| State | Meaning | Preview | In the gate |
|---|---|---|---|
| `starting` | Open, mode, stream start, first frame, controls, read-back, warm-up, rate check [D20, D21, D22]. Also after "apply again" and after a resolution or rate change [D23, D31]. | no | no |
| `waiting` | Warm-up done and rate check passed. The camera waits paused for the other selected cameras [D21] [agent 51]. | no | no |
| `failed` | The start failed: cannot open, in use, no mode, not ready in 15 s, rate check failed [D23]; or the writer of the recorder stayed stuck past its limit (disk stall) [C6]. The camera is closed. | no | no |
| `checking` | The rate check after a live control change runs [D32, D33]. | yes | yes |
| `too_slow` | The rate check after a live change failed [D32]. The camera stays open. | yes | yes |
| `ready` | Open, checked, no recording. | yes | yes |
| `recording` | Recording runs. | yes | yes |
| `dead` | Device removed, or 2 s without a frame [D38]. The camera is closed. | no | no |

### 8.2 Transitions

| From | Event | To |
|---|---|---|
| (none) | group apply | `starting` |
| `starting` | a start failure (section 9, 10.1), also no first frame in 5 s (6.4) | `failed`; the close runs with its bounded steps |
| `starting` | device removed; 2 s without a frame after the first frame | `failed`, with the current stage [agent 23] |
| `starting` | a bounded call times out (a hang) | `failed`; the process ends hard (6.6) |
| `starting` | warm-up done and rate check passed | `waiting` [agent 51] |
| `waiting` | no selected camera is in `starting` | `ready` [D21] |
| `ready`, `too_slow`, `checking` | live change of exposure, gain or focus [D31] | `checking` |
| `checking` | rate check passed | `ready` |
| `checking` | rate check failed | `too_slow` [D32] |
| `ready`, `too_slow`, `checking` | change of resolution or rate [D31] | `starting` (only this camera) |
| `ready`, `too_slow`, `checking` | a live control change fails without a hang | the same state: the camera keeps running with its earlier values; the response reports the failed change [U14] |
| `failed`, `dead` | "apply again", with the same config or a changed config (8.3) | `starting` (only this camera) [D23] |
| `ready` | recording starts | `recording` |
| `recording` | recording stops | `ready` |
| `recording` | camera slows down | `recording`, with a warning [D39] |
| `recording` | the take ends because of a disk stall or a write error of any camera, and this camera's writer finished | `ready` [C5, C6] |
| `recording` | this camera's writer is stuck past the limit of [`recorder.md`](recorder.md) 5.3 | `failed`, stage `recording`, reason "disk stall"; the main process ends the process [C6] |
| `waiting`, `checking`, `too_slow`, `ready`, `recording` | device removed; 2 s without a frame | `dead` [D38] |
| `waiting`, `checking`, `too_slow`, `ready`, `recording` | a bounded call times out (a hang) | `dead`, stage `streaming`; the process ends hard (6.6) [agent 60]; a hung control call is on the control thread, so the loop does not stop before the hard end [U16] |
| `starting`, `waiting`, `failed`, `checking`, `too_slow`, `ready`, `dead` | unselect | removed from the group; an open camera is closed [D23] [agent 24] |

skellycam never moves a camera from `failed` or `dead` to `starting` by itself [D23]. A failed camera
records its diagnostics, is marked, and is never revived (Kiyo Pro wedge rule) [D23].

The camera process of a camera that fails at start reports the failure, closes the camera and ends.
The process of a camera that dies while no recording runs reports, closes the source with the bounded
steps of 6.9 and ends. During a recording, it first writes placeholders to the end of the recording
and ends its camera writer ([`recorder.md`](recorder.md) 7.3) [D38, M1]. After a hang, the process ends at once [R4]. "Apply again" starts a new camera process [agent 22].

A camera that dies while no recording runs is treated as a `failed` camera [U6].

### 8.3 What each state allows

| State | Start a recording | A changed config in an apply request | The same config in an apply request | Unselect |
|---|---|---|---|---|
| `starting` | blocked [agent 25] | refused [agent 45] | no effect [agent 45] | allowed |
| `waiting` | blocked [agent 25] | refused [agent 45] | no effect | allowed |
| `failed` | blocked [D23] | reopens only this camera with the new config [D23, D25] [agent 45] | reopens only this camera [D23] | allowed [D23] |
| `checking` | blocked [D33] | live change (restarts the check) [agent 27], or reopen for a resolution or rate | no effect | allowed |
| `too_slow` | blocked [D32] | live change, or reopen for a resolution or rate [D31, D32] | no effect | allowed |
| `ready` | allowed, when every selected camera is `ready` | live change, or reopen for a resolution or rate [D31] | no effect | allowed |
| `recording` | (runs) | refused [D36] | refused [D36] | refused [D36] |
| `dead` | blocked [U6] | reopens only this camera with the new config [U6] | reopens only this camera [U6] | allowed |

- A recording starts only when every selected camera is `ready` [D23, D32, D33] [agent 25].
- HTTP codes, one rule [agent 25]: 422 for a request that is not valid by its content (mixed rates, a
  rate below the floor, an unknown size or control); 409 for a valid request that the current state
  does not allow (recording, checking, starting). The detail names each camera that blocks and why.
- "Apply again" is a new request to `/camera/group/apply`. For a camera in `failed` or `dead`, the
  request can carry the same config or a changed config: rate, resolution, exposure or other
  controls. It reopens only that camera, with the config of the request [D23, D25]. The other cameras
  keep their process, rings and preview [D23].
- For a camera in `ready`, `checking` or `too_slow`, a changed config is a live change or a reopen of
  that camera (11.2) [D31].
- "Unselect" is `use_this_camera: false` for the camera in a request to `/camera/group/apply`. The
  group closes the camera and removes it from the gate and from the record check [agent 24]. A later
  request that selects it again starts it again [agent 87].
- The main process first checks a request as a whole: the config values, the one-rate rule (7.5) and
  the states of this table. A camera of the group that the request does not name counts with its
  current config [agent 87]. A refused request gets 422 or 409 by the rule above. It changes
  nothing, also on a running group [U10].
- After the check, the main process applies the change of each camera on its own. A camera whose
  reopen-type change fails (a resolution or rate change, "apply again") becomes `failed`, and the
  other cameras are not touched [U10].
- A live control change (exposure, gain, focus) that fails without a hang leaves the camera running
  in its earlier state. The set call returned an error, or the read-back differs from the value that
  was set. The response reports the failed change for that camera. The camera does not become
  `failed` [U14]. A change that needs a reopen and fails still gives a `failed` camera [U10].

### 8.4 Status report [agent 21]

`CameraStatus.serialize()` (in `CameraState.status`) keeps its keys and adds:

```json
{
  "state": "too_slow",
  "failure": null,
  "mode": {"width": 1280, "height": 720, "fps_num": 30, "fps_den": 1, "format": "MJPG"},
  "measured_fps": 28.71,
  "warnings": [],
  "controls": {
    "exposure": {"present": true, "auto": false, "value": -6},
    "gain": {"present": true, "auto": false, "value": 0},
    "focus": {"present": true, "auto": true, "value": 30}
  }
}
```

- `failure` is null or the object of section 12.
- `measured_fps` is the result of the last rate check, or null. It is not rounded [U17].
- `replaced_count` is the count of the stop line of 5.2: the frames replaced since the first frame
  that the camera took in the gate. The camera process sets it at each taken frame and at the stop
  [W4].
- `state` is one of the states of 8.1.
- `controls` holds `exposure`, `gain` and `focus` from 3a, read only. skellycam sets gain and focus
  through the config from 3c [D30, D43] [agent 31].
- `warnings` holds the items of 11.3 for the recording that runs [agent 33].
- The response of `/camera/group/apply` adds `camera_failures`: a dict from `camera_id` to the
  failure object of section 12 [agent 21].

## 9. Start-up

### 9.1 Order [D20]

1. Open (6.2).
2. Choose the mode (6.3).
3. Start the stream (6.4).
4. Wait for the first frame (6.4).
5. Set every control of the config (section 11). RECOMMEND runs here (11.1).
6. Read each control back. The config stores the read-back values, as today: the config comes from
   `extract_config_from_cv2_capture`, which reads the device [agent 44].
7. Count the warm-up frames (9.2).

Reason: on the C930e the gain read 6 before the stream started and 0 after it started [D20]
[M `research/usb_cameras/docs/startup_rate_check_20261119.md`].

### 9.2 Warm-up [D21]

- Each camera discards 90 warm-up frames [D21]. They do not go to the ring or the recorder.
- The loop takes each warm-up frame. The gate does not apply in `starting`.
- The warm-up counts the frames that the camera delivers (by `source_frame_number`), from the first
  frame after the controls are read back (9.1 step 6). A frame that the loop misses still counts.
  Thus the warm-up frames 6 to 90 of 10.1 are delivered frames [U17].
- In 3b, the range rule examines the discarded frames (section 13.3) [D21].

### 9.3 Ready limit [D21]

- Each camera must be ready within 15 s [D21]. The time counts from the start of the open (9.1 step 1)
  to the end of the rate check [agent 14].
- A camera that is not ready in time fails, stage `warm-up`, reason "not ready in 15 s"
  [agent 48].
- The shared loop in the camera process owns the 15 s timer. It checks the deadline between the steps
  of 9.1 and on each warm-up frame. A bounded call that runs at the deadline is not cut short. The
  camera fails when the call returns. If the call does not return, its own 5 s limit applies (6.6)
  [agent 14].
- The first frame has its own 5 s limit (6.4). A camera that fails it has the stage `first frame`.
- The warm-up stays 90 frames, and the ready limit stays 15 s [D21]. With the floor of 29.97 fps
  (U11), 90 frames take about 3 s, so 15 s is ample.

### 9.4 Wait for the others [D21]

- Cameras wait paused until all are ready [D21]. The state of a camera that waits is `waiting` (8.1). "All" means every selected camera that has not
  failed [D23].
- A camera that waits keeps its stream. Its waiting place keeps the newest frame only.

### 9.5 Stall watch

- After the first frame, the loop compares `perf_counter_ns()` with the arrival time of the last
  delivered frame on each pass. `read_frame` waits at most until 2 s after the last arrival.
- The watch does not depend on the gate. A camera that waits at the gate still sees its frames arrive.
- 2 s without a frame: `dead` in an open state, `failed` in `starting` [D38] [agent 23].
- A started camera that fails is `dead` at once, before its files and its close [agent 82].
- The watch restarts after each wait of the loop in the recorder ([`recorder.md`](recorder.md) 5.2), and after each wait at the
  gate [agent 32]. This applies to each source, push and pull (E of [ADR-JMS0](../decisions/entries/JMS0-connection-review-decisions.md), 2026-11-20).

## 10. Rate check

### 10.1 At start-up [D22]

- Window: warm-up frames 6 to 90 [D22].
- Rate = (frames - 1) / (last arrival time - first arrival time) [D22]. The loop computes it as
  `(s_b - s_a) / (t_b - t_a)`, where a and b are taken frames, `s` is `source_frame_number` and `t` is
  `arrival_ns`. Because `s` counts every delivered frame, this is the same number when the gate or a
  slow loop makes the loop miss a frame [agent 26].
- Limit: the camera fails when the rate is more than 3 % below or more than 3 % above the mode rate
  [D22]. At a mode rate of 30 fps, a rate from 29.1 to 30.9 passes.
- The reference is the mode rate (6.3 step 5), not the requested rate [D22].
- The start-up check has no early decision. The 15 s limit (9.3) bounds it [agent 27].
- A camera that fails gets the message of 10.4. The generic camera fails by design. There is no
  override [D24].
- With the OpenCV source and no reported rate (0 or less), the reference is the requested rate of
  the config, and 30 fps for "auto". The check runs as above, and the status reports the measured
  rate [W2]. This replaces the rule of D46 that runs the check only with a reported rate.
- When the first frame of the window is also frame 90 or later, the window ends at the next
  delivered frame, so that it is never empty [agent 26].

### 10.2 After a live control change [D32]

- Skip 15 frames, then measure over the next 60 frames with the formula and the 3 % limit of 10.1
  [D32].
- Early decision: the camera is too slow as soon as the 60 frames can no longer arrive in time
  [D32]. With `t_a` the arrival of the first frame of the window and `r` the mode rate, that is when
  `now - t_a > 59 / (0.97 x r)` and frame `s_a + 59` has not arrived. A frame that arrived in time and
  waits at the gate or in a pause gives no decision [agent 88].
- A rate above the limit is known when the window is complete. That is the earliest time.
- While the check runs, the state is `checking`. A recording cannot start [D33].
- A camera that fails is `too_slow`. It stays open with its preview, and recording is blocked until a
  later change passes the check [D32].
- A new change while a check runs starts a new check [agent 27].
- A change can lower the frame rate for a moment while the camera adjusts [D31]. A frame that a camera
  drops after a change is normal, with no warning [D34]. It shows only in the `DISCONTINUITY` flag
  (4.2). `source_frame_number` counts delivered samples, so it has no gap for such a frame.

### 10.3 During a recording [D39]

- The loop measures the rate over each block of 60 delivered frames with the formula of 10.1
  [agent 28].
- A block more than 3 % below the mode rate starts a "slow" period and gives one warning with the
  camera ID and the measured rate. The next block at a normal rate ends the period. Each new slow
  period gives one more warning [agent 28].
- The recording continues [D39].

### 10.4 Message of a slow camera [D25]

The reason gives the declared rate, the measured rate and two hints in this order [D25]:

`declared 30.00 fps, measured 25.76 fps. Add light or shorten the exposure, or choose a rate that the camera reaches.`

### 10.5 Why the median is forbidden, and the numbers [D22]

- Arrival times sit on a grid of about 16 ms. Intervals are about 32 ms or 48 ms, never 33.3 ms
  [M `research/usb_cameras/docs/startup_rate_check_20261119.md`].
- The generic camera has 56 % intervals of 32 ms and 43 % of 48 ms. Its median gives 31 fps. Its true
  rate is 25.8 fps. A median rule passed it in 564 of 564 opens. The elapsed-time rate caught it in
  all of them (same file).
- Good cameras over frames 6 to 90: the lowest rate was 29.64 fps in 1,432 opens (same file). That is
  0.54 fps above the 3 % limit of 29.1.
- After a live change, skip 15 and a window of 90 frames gave 0 false alarms in 119 changes and caught
  31 of 31 slower ones. A skip of 3 or more with a window of 30 to 90 gave the same result (same
  file).
- Steady rates at 30 fps declared (same file):

  | Exposure | C922 | C930e | Kiyo Pro | Generic camera |
  |---|---|---|---|---|
  | -7 | 30.0 | 30.1 | 29.9 | 25.74 |
  | -6 | 30 | 30 | 28.7 | 25.74 |
  | -5 | 30 | 30 | 23.1 | 25.74 |
  | -4 | 16.0 | 16.0 | 19.5 | 25.74 |
  | -3 | 8.0 | 8.0 | 14.7 | 25.74 |

## 11. Controls

### 11.1 Exposure [D29, D35]

- Modes: `MANUAL`, `AUTO` (the auto exposure of the camera) and `RECOMMEND` (a one-time search at
  open that ends in `MANUAL`) [D29].
- The value keeps the unit of today: a power of two in seconds (-7 = 1/128 s) [D35]. This is the unit
  of `CameraControl_Exposure`.
- The goal is that auto modes are off during a recording. Before a recording, a consumer can use the
  auto mode of the camera to set focus or exposure, then change to manual to lock it [D29].
- `RECOMMEND` runs in the shared loop through the capture interface, with its own range: -12 to -5
  (`RECOMMEND_MAX_EXPOSURE` of `camera_loop.py`), 10 frames to settle at each value, and the mean of
  the decoded image against 127.5. The old helper `recommend_camera_exposure_setting.py` tries -12 to
  -4. The loop then goes one step darker than the value nearest to 127.5 (offset -1, in the range),
  as `get_recommended_cv2_cap_exposure` does. Changed on
  2026-11-20 (H of [ADR-JMS0](../decisions/entries/JMS0-connection-review-decisions.md)): before, the range ended at -4, and there was no offset. It runs at step 5 of 9.1. Its frames are not
  warm-up frames [agent 29]. As today (`_apply_exposure` in
  `opencv_apply_config.py`), the stored config then holds `exposure_mode: MANUAL` and the value that
  the search found [agent 29].

### 11.2 Live changes [D31]

- A change of exposure, gain or focus is applied live, without a reopen, on the control thread of
  4.3 [D31, U16]. Then the check of 10.2 runs.
- A live change that fails without a hang leaves the camera in its earlier state (8.3) [U14]. The
  response of the apply request carries an item of the kind `control_change_failed` in its
  `warnings` list, in the form of 11.3 [agent 64].
- A change of resolution or frame rate reopens only that camera, recreates its rings [ring 7.5] and
  repeats the warm-up and the rate check [D31].
- During a recording, each setting change is refused [D36].

### 11.3 Auto mode at record start [D37]

- If a control is still in an auto mode when a recording starts, the recording starts, and the auto
  mode stays on [D37].
- The warning is machine-readable [D37]. The response of the record start carries a `warnings` list
  [agent 33]:

  ```json
  {"started": true,
   "warnings": [{"kind": "auto_control", "camera_ids": ["a1b2"], "control": "exposure",
                 "text": "Camera a1b2: exposure is in auto mode at the start of the recording"}]}
  ```

- Each warning item has the same form: `kind`, `camera_ids`, `text`, and `control` where a control
  applies [agent 33]. The kinds are `auto_control`, `mixed_rate` (7.5) and
  `control_change_failed` (11.2).
- The status (8.4) shows the same items in `warnings`, and `auto: true` for the control [agent 33].
- The camera process also logs the text as a warning.
- The capture info records it in `controls.<name>.auto` [D37].
- Today the endpoint returns `true`. The new response shape changes this for each consumer
  [agent 33].

### 11.4 Read-back and current values [D20, D30]

- Each control is read back after it is set [D20].
- While a camera is open, the status reports the current value of exposure, gain and focus, also
  when the control is in auto. Thus a consumer can show the value and set manual with exactly that
  value [D30].
- From 3a, the status reports exposure, gain and focus, read only. The control thread (4.3) reads them
  one time per second with `set_controls({})` [D30, U16] [agent 31]. Gain and focus are set through the config from 3c
  [D43].
- Whether a camera in auto mode reports its true current value is not known (section 17.3).

### 11.5 Gain, focus, white balance, power line frequency (3c) [D43, D44]

- `CameraConfig` gets `gain: int | None = None`, `gain_auto: bool = False`, `focus: int | None =
  None` and `focus_auto: bool = False` [D43] [agent 30]. `None` means that skellycam does not set the
  value.
- A control that a camera lacks is reported as absent (`present: false`). A request to set it gets HTTP
  422 with a clear message: `Camera {camera_id} has no {control} control` [D43] [agent 48].
- White balance is read only. Its value and auto flag go to the capture info (step 5d) [D43].
- The power line frequency control is never set in phase 3. Step 3c reads it; it goes to the
  capture info (step 5d) [D44].

### 11.6 Capture data of a recording [agent 32]

The capture data goes to the capture info JSON and the manifest ([`recorder.md`](recorder.md) 6.7). (Changed on 2026-11-20:
the recording info JSON of phase 3 is no longer written [R5].)

## 12. Failure reporting [D40]

- A camera failure is a structured object with the camera ID, the stage and the reason, and also a
  text in the wording of upstream [D40]:

  ```json
  {"camera_id": "a1b2", "stage": "rate check",
   "reason": "declared 30.00 fps, measured 25.76 fps. Add light or shorten the exposure, or choose a rate that the camera reaches."}
  ```

  `Camera a1b2 failed during rate check: declared 30.00 fps, measured 25.76 fps. ...`

- The first failure of each camera is kept [D40, U9].
- The failure is written before any shutdown flag is set [D40]. The current `report_setup_failure`
  (`camera_group/camera_group_ipc.py`) keeps this order. It must stop setting
  `shutdown_camera_group_flag` for a start failure, because the other cameras stay open [D23].
- For an exception, the reason is `{type}: {message}`, as `CameraSetupFailure.__str__` gives today
  [agent 35]. The diagnostics (each bounded step with its HRESULT and time, as the prototype records
  them) go to the log [D23] [agent 35].
- Stage names [agent 34]:

  | Stage | Covers |
  |---|---|
  | `detection` | the Media Foundation enumeration and the mode list (7.1) |
  | `open` | find the device by `camera_id`, `ActivateObject`, the reader creation |
  | `set mode` | the mode choice, `SetCurrentMediaType`, the read-back; no such mode |
  | `start stream` | the first `ReadSample` issue |
  | `first frame` | the wait for the first sample |
  | `set controls` | each control set and read-back at start, `RECOMMEND` |
  | `warm-up` | the 90 warm-up frames; not ready in 15 s; a stall in `starting` |
  | `rate check` | the start-up rate check |
  | `streaming` | device removed, 2 s without a frame, a hung control call while open |
  | `close` | a hung close step |
  | `recording` | the writer of the recorder stuck past its limit (disk stall) [C6] |

- "In use by another program" is the text of D13. The text of 10.4 follows D25. The texts "camera not
  found", "not ready in 15 s", "device removed", "no frame for 2 s", "end of stream" and the control
  error of 11.5
  are [agent 48].

## 13. Uncompressed modes (3b) [D2, D19]

[ring 8.7] and the design notes give the ring side, the encoder, the Quick Sync check and the range
rule [notes: Uncompressed modes, JPEG encoder, Encoder check, Encoder settings, Input range]. This
section adds only what capture adds.

### 13.1 Choice

- `capture_fourcc` asks for `YUY2` or `NV12`. The default is `MJPG` [D19]. The mode choice of 7.5
  uses the requested format. The floor of 29.97 fps applies to each format [U11].
- A synthesized NV12 type (7.4) is never chosen. A request with no native type of the format fails,
  stage `set mode` [agent 19].
- The full mode list of 3c then gives the proper choice [D19].

### 13.2 Frames

- The source gives the raw frame as one new object: YUY2 as `(height, width, 2)` uint8, NV12 as
  `(height x 3 / 2, width)` uint8, as `DecodeInput` expects [ring 8.7].
- A raw frame whose length is not the expected size is not encoded. Its slot is flagged
  `CAPTURE_ERROR` [agent 36]. Whether the contiguous buffer has row padding is [NV].
- The JPEG encoder runs at capture, also when not recording [notes: Uncompressed modes]. The settings
  are those of the notes: quality 90, the chroma of the source, Quick Sync at depth 2
  [notes: Encoder settings].
- The main process checks for Quick Sync one time per app run, only if a camera of the session is in
  an uncompressed mode, and tells the camera processes [notes: Encoder check].
- An encoder that fails during a take is replaced by `cv2.imencode`, the held frames are encoded
  again from the raw frames, and the first frame after the event gets `DISCONTINUITY` [notes: Encoder
  check] [ring 4].
- The recorder takes the encoded JPEG. A BGR conversion runs only for a BGR ring [ring 8.7].

### 13.3 Range rule

- The camera config gets `input_range: "auto" | "limited" | "full"`, default `auto`
  [notes: Input range] [agent 36 for the field name].
- `auto`: during the 90 discarded warm-up frames, count the Y values outside 16 to 235. If more than
  1 % are outside, the camera is full range. Else, the flag of the OS decides (limited if not set)
  [notes: Input range] [D21].
- The decision is made one time, before the first recorded frame, and never changes in a session. The
  camera process logs the range ([`recorder.md`](recorder.md) 6.7).

## 14. The OpenCV source

### 14.1 Linux and macOS [D46]

- The OpenCV source stays on Linux and macOS, with the JPEG re-encode of [ring 2.3, 8.8] [D6].
- The start-up rules apply to it: warm-up (9.2), the ready limit (9.3), the failed-camera flag
  (section 8) and one rate per group (7.5) [D46].
- The rate check runs on each OpenCV camera. The reference is the reported rate, or the requested
  rate (30 fps for "auto") when OpenCV reports no rate [W2].
- The floor of U11: a request below the floor is refused in the whole-request check, as on each
  source. When OpenCV reports a real rate above 0 and below 29.97 after the open, the camera fails,
  stage `set mode`, reason "no mode at 30 fps or more". When OpenCV reports no rate (0 or less), the
  floor is not checked (D46) [agent 59].
- The forced auto exposure on Linux (`opencv_apply_config.py`) stays. With D37, each Linux recording
  then gives the auto warning one time for each camera, until phase 7 (17.3).
- Linux and macOS behaviour is not tested on hardware until phase 0 [D46]. The fake-source tests and
  the tests with the OpenCV fake (`FakeCapture` of `skellycam/tests/frame_ring/ring_session.py`) run on
  the Linux and macOS CI runners [U20]. T-CAP-99 to T-CAP-104 check the rules of this section with
  the OpenCV fake [U23]. The hardware tests T-CAP-92 to T-CAP-98 run on Linux and macOS in phase 0
  [U21].

### 14.2 Windows: the temporary setting and the deletion [D8]

- While phase 3 is built, the environment variable `SKELLYCAM_WINDOWS_CAPTURE` chooses the source on
  Windows: `opencv` (the default) or `media_foundation` [D8] [agent 38].
- The last commit of phase 3 deletes the OpenCV source on Windows and the setting, after the
  comparison run passes [D8]. On Windows there is then no fallback [P §3, D8].
- The shared loop has no "reset after 30 slow frames" reopen (`check_framerate_reset`) and no
  burned-in frame stamp (`draw_doubled_text`), on each OS, from step 3a [D8, U2].
- While the setting chooses OpenCV on Windows, detection is Media Foundation [D11]. The OpenCV source
  finds its DirectShow device by the device instance part of the Media Foundation link: the part
  before the interface class GUID [U1] [NV: that both links hold the same instance part].

## 15. CI [D47]

- A new workflow `.github/workflows/capture.yml` [agent 39], made on the pattern of
  `.github/workflows/ring-arm64.yml`: the same pinned actions (by full SHA), uv `0.13.9`, Python
  `3.13.18`, `permissions: contents: read`, a concurrency group.
- Trigger: each push to `dom/native-jpeg` that changes `skellycam/core/camera/**`,
  `skellycam/core/camera_group/**`, `skellycam/core/device_detection/**`,
  `skellycam/core/recorders/**`, `skellycam/core/timestamps/**`, `skellycam/core/ipc/frame_ring/**`,
  `skellycam/api/**`, `skellycam/tests/**`, `specs/windows-capture.md`, `specs/frame-ring.md`,
  `pyproject.toml`, `uv.lock` or `.github/workflows/capture.yml`; and by hand [D47] [agent 39].
- The three jobs run the same selection: `uv run pytest skellycam/tests/capture -m "not camera_hardware
  and not capture_local"`. It holds the fake-source tests and the OpenCV-source tests [D47, U20].
- Job `capture-windows` on the runner label `windows-2025` [agent 39]. It also loads the Media
  Foundation module (T-CAP-46). The Windows-only tests of 16.1 run only in this job [U18].
- Job `capture-linux` on the runner label `ubuntu-24.04` [agent 39]: install PortAudio as the arm64
  job does, then run the selection [D47].
- Job `capture-macos` on the runner label `macos-15` (Apple Silicon) [U20] [agent 74]:
  `opencv-contrib-python` 5.1.0.95 has macOS wheels for macOS 15 and later only. The `sounddevice`
  wheel for macOS holds PortAudio, so the job has no install step for it. The job also runs the
  portable ring tests (`-m ring_portable`, with `SKELLYCAM_RING_FULL=1`, as `ring-arm64.yml`). Few such
  runners exist: no other job waits for this job, it has its own concurrency group with
  `cancel-in-progress`, and a time limit of 40 minutes [agent 74].
- The hosted runners do not run the tests with the marker `capture_local` (T-CAP-49, T-CAP-50).
  They need the Windows development machine [D48] [agent 2].
- The arm64 job stays as it is (ring tests only) [D47].
- The Media Foundation module loads `mfplat.dll` at the first Media Foundation call, not at import.
  Whether a hosted Windows runner has Media Foundation is [NV]. T-CAP-46 passes without it
  [agent 39].

## 16. Tests

### 16.1 Kinds

- **fake**: a test with `FakeSource` or the OpenCV fake. It runs on each OS and in CI [D3]. The fake
  source scripts: the native mode list; arrival times (also the generic-camera pattern on a 16 ms
  grid); control values (also a value that resets when the stream starts, as on the C930e); and faults
  (in use at open, a hang at a given call, device removed at frame k, a stall at frame k, a dropped
  frame with discontinuity, a missing control).
- **hardware**: needs the cameras. It has the marker `camera_hardware` and runs only when the user says
  so, with `SKELLYCAM_HARDWARE=1` [D3] [agent 2]. One camera process opens each camera. On a Kiyo Pro
  fault, the test records the diagnostics, marks the camera dead and does not use it again in that run
  [D23].
- **CI**: a check of the CI job itself.
- **local**: a test with the fake source that runs only on the Windows development machine. It has
  the marker `capture_local`, and the hosted runners leave it out (section 15) [agent 2]. T-CAP-49
  and T-CAP-50 are of this kind.

Systems [U18, U20, U21]:

- The package `media_foundation/` is Windows only [U18]. Thus T-CAP-22, T-CAP-23, T-CAP-24 and
  T-CAP-48 run on the Windows development machine and on the Windows CI job, and are skipped on
  other systems (a skip by platform). T-CAP-43 (the setting of 14.2) and T-CAP-46 (the Media
  Foundation module) are Windows only too. The kinds of these tests do not change.
- The other fake-source tests, the OpenCV-source tests and T-CAP-45 run on Windows, Linux and macOS
  [U20].
- The hardware tests T-CAP-51 to T-CAP-60 and T-CAP-88 run on Windows. T-CAP-92 to T-CAP-98 are their
  counterparts with the OpenCV source on Linux and macOS [U21]. They are skipped on Windows, and they
  run in phase 0 on the word of the user. 16.7 gives the state of each test on each system [U22].

Limits produced by the fake source:

- The first-frame limit (6.4) and the bounded-call limit (6.6) are inside the `open` and the calls of
  each source. With the fake source, the fake produces them: it waits `FIRST_FRAME_TIMEOUT_S` and
  `BOUNDED_CALL_LIMIT_S` as a source does, then raises its failure. Thus T-CAP-80, T-CAP-40, T-CAP-82
  and T-CAP-85 check how the loop, the camera process and the main process handle the failure.
- No hardware test checks the real limits of the Media Foundation source: no test can make a camera
  hang. T-CAP-52 and T-CAP-54 show only that normal opens stay under them. Section 17.2 item 13
  holds this point.

Switches of the hardware tests [agent 73]:

- `SKELLYCAM_HARDWARE=1`: each hardware test runs; without it, each is skipped [agent 2].
- `SKELLYCAM_HARDWARE_DARK=1`: T-CAP-55 and T-CAP-96 run; they need a dark room.
- `SKELLYCAM_HARDWARE_UNPLUG=1`: T-CAP-58 and T-CAP-95 run; they need a person who unplugs a camera.
- `SKELLYCAM_HARDWARE_RESULTS`: the file of the recorded results (JSON lines). The default is a file
  in the temporary folder of the system. It is not in the repository.

Run rules [agent 2]:

- T-CAP-43 runs only before the last commit of phase 3. That commit deletes it with the setting.
- T-CAP-76 comes in the last commit of phase 3. It runs only after that commit.

The pass thresholds that this table adds to the decisions (for example the times of T-CAP-03 and
T-CAP-36) are [agent 41]. They can be changed when the tests are written.

### 16.2 Test list

| ID | Step | Kind | What it does | Pass criterion |
|---|---|---|---|---|
| T-CAP-01 | 3a | fake | Read 100 frames from a fake source. | Each `CapturedFrame` has every field of 4.2 with its type; `source_frame_number` increases by 1 per delivered frame; `arrival_ns` increases. |
| T-CAP-02 | 3a | fake | The fake delivers frames 0 to 4 before the first `read_frame`, then frame 5 after it. | The read gives frame 4; `replaced_count` is 4; the next read waits and gives frame 5. |
| T-CAP-03 | 3a | fake | A consumer holds the waiting place busy; the producer puts 1,000 frames. | Each put takes at most 1 ms at p99; no put waits on the consumer. |
| T-CAP-04 | 3a | fake | `read_frame(2.0)` with no frame. | It returns `None` after 2.0 s (±0.1 s); the thread uses under 2 % of one core while it waits. |
| T-CAP-05 | 3a | fake | Three fake cameras, each in a 30 fps mode, in one group. The frames of each fake are on one 100 ms grid of the clock. One fake delivers 60 frames per second from 20 s to 30 s of the clock while the two others hold the gate at 30 rounds per second; at 30 s it drops one frame and goes back to 30 fps. Each fake delivers its last frame at 40 s [agent 65]. | Equal ring frame counts; for each camera, the sum of the gaps of `source_frame_number` between taken frames, from the first frame taken in the gate, equals the increase of `replaced_count` from that frame; the fast camera has 200 or more replaced frames; one log line per camera at stop with that count; the last frames of the three fakes are on one gate round. The window ends at 29.995 s, because the fake rounds each interval to whole ns ([ADR-6EKB](../decisions/entries/6EKB-choices-of-the-3a-review-fixes.md)). |
| T-CAP-06 | 3a | fake | Run, change the resolution, run again. | Ring `frame_number` is 0, 1, 2, ... in each ring; `source_frame_number` is the source count; the gate count continues across the change. |
| T-CAP-07 | 3a | fake | Fake with scripted arrival and sample times; record 30 frames. | Slot `arrival_ns` and `sample_ns` equal the source values; the CSV time of each recorded frame is the recorder CSV `arrival_ns` (note of 2026-11-20); a source with no sample time writes `NO_SAMPLE_NS`. |
| T-CAP-08 | 3a | fake | Spy on the recorder, the JPEG ring write and the BGR hand-over. | For each frame: recorder, then JPEG ring, then BGR [ring 5.3]; a ring write that raises leaves the recorder and the next frame unaffected. |
| T-CAP-09 | 3a | fake | MJPG fake, with and without recording, with and without a BGR ring; count `cv2.imdecode` calls. | Replaced by T-REC-41 (note of 2026-11-20). |
| T-CAP-10 | 3a | fake | The fake delivers a cut-off JPEG during a recording. | Replaced by T-REC-42 (note of 2026-11-20). |
| T-CAP-11 | 3a | fake | (1) The fake drops a frame on the camera side: the next delivered sample has the discontinuity attribute. (2) A sample with the attribute is replaced in the waiting place before the loop takes it. | In both cases the next taken frame has `DISCONTINUITY`; in case 1, `source_frame_number` has no gap; no warning is logged up to frame 200 (the fake then stops, and the dead camera logs a warning). |
| T-CAP-12 | 3a | fake | Fake with an exposure that resets to -5 when the stream starts; config `MANUAL -7`. | Call order: open with first frame, set controls, read back, warm-up; the config holds the read-back value -7. |
| T-CAP-13 | 3a | fake | Two fake cameras; one opens 3 s later. | The first 90 frames after read-back reach neither the ring nor the recorder; the first camera is `waiting` and paused until the second has passed its check; then both are `ready`. |
| T-CAP-14 | 3a | fake | One fake with mode rate 30. Its first frame comes 0.2 s after the first `ReadSample`; from then on it delivers 5 fps, so that 90 warm-up frames need 18 s. | Failed, stage `warm-up`, reason "not ready in 15 s", at 15.0 to 15.5 s after the open. |
| T-CAP-15 | 3a | fake | Fake with scripted arrival times; the loop misses frames 40 to 45. | The start-up rate equals `(n - 1) / (t_90 - t_6)` over the delivered frames 6 to 90, to 0.001 fps. |
| T-CAP-16 | 3a | fake | Each fake camera in its own group: fakes at 29.2, 29.0, 30.8 and 31.0 fps with mode rate 30; a fake with no 30 at the size, whose auto rate (-1) gives mode rate 60, and that delivers 60 fps. | 29.2 and 30.8 pass; 29.0 and 31.0 fail; the auto case passes against 60, not against 30. |
| T-CAP-17 | 3a | fake | Arrival times on a 16 ms grid: 56 % 32 ms and 43 % 48 ms (generic camera); 92 % 32 ms and 8 % 48 ms (good camera). | The generic pattern fails, the good pattern passes; a median of the same intervals gives above 29.1 fps for the generic pattern (proves the pattern). |
| T-CAP-18 | 3a | fake | The generic pattern of T-CAP-17 at start. | The reason is the text of 10.4 with 30.00 and the measured rate, the light hint first. |
| T-CAP-19 | 3a | fake | Three fakes; one is in use at open. | That camera is `failed` with "in use by another program"; the other two reach `ready` with preview; a record start returns 409 and names it; after 60 s, its open count is still 1. |
| T-CAP-20 | 3a | fake | After T-CAP-19: (1) apply the same configs again; (2) fail the camera again and apply it with a changed exposure; (3) apply a request that gives all three cameras the rate 60. | (1) and (2): only the failed camera opens again, in (2) with the new exposure; the ring names and the process IDs of the others do not change. (3): each camera reopens at 60. |
| T-CAP-21 | 3a | fake | After T-CAP-19, apply with `use_this_camera: false` for the failed camera. | The camera leaves the group; a record start succeeds with two cameras. |
| T-CAP-22 | 3a | fake | Map each HRESULT of 6.7 (pure function, no COM). Windows only [U18]. | In-use codes give "in use by another program"; device-removed codes give "device removed"; other codes give their name: `0x80004005` gives `E_FAIL`, `0xC00D3E85` gives `MF_E_SHUTDOWN` [agent 70]. |
| T-CAP-23 | 3a | fake | A detection result with two links that give the same `camera_id`. Windows only [U18]. | Refused with an error that names both links. |
| T-CAP-24 | 3a | fake | Hash known Media Foundation links in mixed case. Windows only [U18]. | `camera_id` equals the SHA-256 rule of today on the lower-case link. |
| T-CAP-25 | 3a | fake | Build `supported_modes` from native types with MJPG, YUY2, a synthesized NV12, H.264, duplicates, 30000/1001, 10000000/333333, 60/1, 24/1 and 15/2. | The exact JSON of the 7.3 rules: MJPG only, order, 29.97, 30.0 and 60.0; no 24 and no 7.5; no duplicates; a size with only low rates is left out. |
| T-CAP-26 | 3a | fake | Choose modes: request 30 when the camera has 29.97 and 30; request 60 at a size that has only 30; a size it lacks; a size that only H.264 has. | 30; no mode for the other three, and each failure lists the modes; H.264 is never chosen or opened. |
| T-CAP-27 | 3a | fake | Requests of -1 and 0: with 30 at the size; with 60 but no 30; with only 15 and 24. | 30; 60; failed with "no mode at 30 fps or more". |
| T-CAP-28 | 3a | fake | Open with -1; compare 30.0 and 30.00003, 30 and 29.97. | The config stores the mode rate; the first pair is equal, the second is not. |
| T-CAP-29 | 3a | fake | Group of two with mode rates 30 and 60; group of two with -1 that both give 30. | The first apply fails and opens no camera; the second opens both. |
| T-CAP-30 | 3a | fake | Change the exposure, then the resolution, of one camera of two. | Exposure: no reopen, same ring name, state `checking`; resolution: only that camera reopens, new rings, warm-up and rate check again; the other camera keeps its preview. |
| T-CAP-31 | 3a | fake | After a live change, the fake goes to 20 fps; after a later change, to 30 fps. | State `checking`, then `too_slow` at t_a + 59 / (0.97 x 30) s = t_a + 2.0275 s, within ±25 ms, where t_a is the arrival of the first frame of the window; this is before the window could end at 20 fps (t_a + 2.95 s); preview continues; record start returns 409; the next change at 30 fps gives `ready`. |
| T-CAP-32 | 3a | fake | Start a recording while a camera is `checking`. | 409, the detail names the camera and `checking`. |
| T-CAP-33 | 3a | fake | Apply a change during a recording. | 409; the camera config and the ring name do not change. |
| T-CAP-34 | 3a | fake | Start a recording with exposure in `AUTO`. | The recording starts; the response `warnings` holds the camera, `exposure` and the text of 11.3; the status shows the same item; the log has the text; the capture info has `controls.exposure_us.auto` true (note of 2026-11-20). |
| T-CAP-35 | 3a | fake | Three fakes record; one gives device removed at its next frame after 60 recorded frames [agent 68]. | That camera is `dead` at once; its files are finished; its timing file ends at its last frame; the multi-frame rows after it hold the two live cameras: the time of each such row is the mean of the times of the two live cameras [agent 68]; the two keep recording to the stop; `dead_cameras` holds its ID and `last_frame_number`. Replaced by T-REC-43 (note of 2026-11-20). |
| T-CAP-36 | 3a | fake | One fake stops delivering after `ready`. | `dead` between 2.0 and 2.25 s after its last arrival, not before. |
| T-CAP-37 | 3a | fake | During a recording, one fake goes to 27 fps for 5 s, then back to 30. | One warning with the camera and the rate, from 27 to under 29.1 fps (the first block below the limit can hold slow and normal frames) [agent 72]; the recording continues; a later slow period gives one more warning. |
| T-CAP-38 | 3a | fake | Two failures of one camera, then a group shutdown. | The object has `camera_id`, `stage`, `reason`; the text is `Camera {id} failed during {stage}: {reason}`; the first failure stays; it is in the queue before the flag changes. |
| T-CAP-39 | 3a | fake | Record with the fake source and with the OpenCV fake; give the recorder a frame with a wrong camera ID. | The wrong camera ID is refused with an error (note of 2026-11-20: the CSV column part goes with the old CSV; the refusal is of a take spec whose `camera_id` is not the camera of the process). |
| T-CAP-40 | 3a | fake | A fake source in a real camera process hangs in `open` past the limit, at the reopen after a resolution change, while a second camera streams in `ready` [agent 69]. | The failure arrives with stage `open`; the process exits within the limit plus 2 s; the main process cleans up only that camera; the second camera has no gap above 100 ms. |
| T-CAP-41 | 3a | fake | `MANUAL -7`, `AUTO`, `RECOMMEND` with a brightness model in the fake. | The fake gets the values in log2 seconds; `RECOMMEND` ends in `MANUAL` with the value nearest to 127.5. |
| T-CAP-42 | 3a | fake | Exposure in `AUTO`; the fake changes its exposure from -6 to -5, its gain from 0 to 4 and its focus from 30 to 40, with no set through the config. | Within 2 s, the status shows `exposure` with `auto: true` and `value: -5`, and the new gain and focus values. |
| T-CAP-43 | 3a | fake | On Windows: no setting, `opencv`, `media_foundation`, a wrong value. Runs only before the last commit of phase 3. | OpenCV, OpenCV, Media Foundation, an error that names the allowed values. |
| T-CAP-44 | 3a | fake | The OpenCV fake under the shared loop, with a reported rate of 30 and of 0. | Warm-up and rate check in both: with 0, against the requested rate, and `ready` with `measured_fps` within 3 % of 30 [W2]; the ring gets a q90 JPEG with no burned-in stamp (it decodes to the fake image); the BGR ring gets the OpenCV image. |
| T-CAP-45 | 3a | CI | Read `pyproject.toml` and `uv.lock`. | `comtypes==1.5.0` with the marker `sys_platform == "win32"`; locked at 1.5.0. |
| T-CAP-46 | 3a | CI | On the Windows runner: import the Media Foundation module; if `mfplat.dll` loads, call `MFStartup`, enumerate, `MFShutdown`. | The import passes; the interface declarations exist; an enumeration returns a list. |
| T-CAP-47 | 3a | fake | Search the package. | No compiled extension of its own and no `_skellycam_rust` import. |
| T-CAP-48 | 3a | fake | Detection with a fake enumeration that hangs for one device. Windows only [U18]. | The detection child ends; the call returns within the limit plus 2 s with an error; the main process keeps running. |
| T-CAP-49 | 3a | local | Marker `capture_local`. Run the rule of T-RING-31 with the shared loop on the Windows development machine: a camera process paused for 10 s. | Process CPU under 2 % of one core [D48]. It replaces T-RING-31 [W8]. |
| T-CAP-50 | 3a | local | Marker `capture_local`. Run T-RING-46 on the Windows development machine. | It passes [D42, D48]. |
| T-CAP-51 | 3a | hardware | Detect with four cameras connected; then detect again while two of them stream. | Four cameras with new IDs and the `supported_modes` of 7.3; the streaming cameras show no arrival gap above 100 ms. |
| T-CAP-52 | 3a | hardware | Open the C922, the C930e and the Kiyo Pro at 1280x720 MJPG 30 through Media Foundation, one at a time. | Each reaches `ready`; for 300 frames the ring payload is byte-equal to the bytes that the callback copied; the rate check passes. |
| T-CAP-53 | 3a | hardware | Open the generic camera at 1280x720 MJPG 30. | `failed`, stage `rate check`, the reason of 10.4 with a measured rate within 0.5 fps of 25.76 [D24] [agent 71]. |
| T-CAP-54 | 3a | hardware | Each camera at each offered MJPG rate at 1280x720: 30 on each camera, 60 on the C922 and the Kiyo Pro [D49, U11]. | For each rate: the measured rate and the check result are recorded; a camera that fails gives the reason of 10.4. |
| T-CAP-55 | 3a | hardware | Each camera opened in a dark room with auto exposure [D49]. | For each camera: state, measured rate and reason are recorded; no traceback. |
| T-CAP-56 | 3a | hardware | Another program holds the C930e; apply a group with it and the C922. | The C930e is `failed` with "in use by another program"; the C922 is `ready`. |
| T-CAP-57 | 3a | hardware | Exposure steps -7, -6, -5, -4 on each camera while open. | Each change gives `checking`, then `ready` or `too_slow` as table 10.5 predicts; the Kiyo Pro at -6 is recorded. |
| T-CAP-58 | 3a | hardware | Record with the C922 and the C930e; the user unplugs the C922 at 20 s. | The C922 is `dead` at once; the C930e records to the stop; the manifest has `camera_dead` for the C922, and its file has placeholders to the stop (note of 2026-11-20). |
| T-CAP-59 | 3a | hardware | Compare `sample_ns` and `arrival_ns` for 300 frames per camera. | The difference is recorded per camera; the source applies the `NO_SAMPLE_NS` rule of 4.2 as the recorded values require. |
| T-CAP-60 | 3a | hardware | The comparison run of 16.4 [D48]. | 16.4. |
| T-CAP-61 | 3b | fake | Request YUY2 and NV12 where the fake lists native and synthesized types. | Native types are chosen; a synthesized NV12 is never chosen; a missing format fails at `set mode`. |
| T-CAP-62 | 3b | fake | YUY2 and NV12 fakes with `cv2.imencode`. | The ring gets a q90 JPEG with the chroma of the source (4:2:2 from YUY2, 4:2:0 from NV12). |
| T-CAP-63 | 3b | fake | Sessions with and without an uncompressed camera; count the Quick Sync checks. | One check per app run, only with an uncompressed camera; each camera process gets the result. |
| T-CAP-64 | 3b | fake | The encoder fails at frame 200 of a take. | Later frames use `cv2.imencode`; held frames are encoded from the raw frames; no frame is lost; the first frame after the event has `DISCONTINUITY`; the event is counted and logged. |
| T-CAP-65 | 3b | fake | Warm-up frames with 0.5 % and 2 % of Y values outside 16 to 235, with the OS flag "limited". | 0.5 %: limited; 2 %: full; the decision does not change later in the session; the log holds it (note of 2026-11-20). |
| T-CAP-66 | 3b | fake | A YUY2 frame that is 100 bytes short. | Not encoded; slot flagged `CAPTURE_ERROR`. |
| T-CAP-67 | 3b | fake | Record in YUY2 with Quick Sync on and the BGR ring off. | The recorder gets the encoded JPEG (note of 2026-11-20). |
| T-CAP-68 | 3b | hardware | YUY2 640x480 at 30 on the C922 and the C930e; YUY2 1280x720 at 30 on the Kiyo Pro; NV12 1280x720 at 30 on the generic camera. | Each reaches `ready` or fails with a reason; the range decision agrees with the yuy2_range evidence; Quick Sync is used on the development machine. |
| T-CAP-69 | 3b | hardware | The 3b recording of 2.2 item 3. | 2.2 item 3. |
| T-CAP-70 | 3b | fake | A group with one fake in YUY2 at a mode rate of 30 and one in MJPG at 60. | The apply fails and opens no camera (D18 with D19). |
| T-CAP-71 | 3c | fake | Build `capture_modes` from the native types of T-CAP-25. | The JSON of 7.4: MJPG and YUY2 both listed, MJPG first; H.264 and RAW `selectable: false` with "never opened"; modes below 29.97 fps `selectable: false` with "below 30 fps"; synthesized NV12 left out. |
| T-CAP-72 | 3c | fake | Set gain and focus, manual and auto, live. | Each value is set and read back; no reopen; state `checking`. |
| T-CAP-73 | 3c | fake | A fake without focus; config with `focus: 40`. | Status `present: false`; the set returns the error text of 11.5. |
| T-CAP-74 | 3c | fake | Record with white balance and power line frequency values in the fake. | Both are in the capture info (step 5d); the fake gets no set call for either (note of 2026-11-20). |
| T-CAP-75 | 3c | fake | Gain and focus in auto; the fake changes their values. | The status shows the new values with `auto: true`. |
| T-CAP-76 | 3c | fake | Comes in the last commit of phase 3 and runs only after it: import the OpenCV source on Windows; search for `SKELLYCAM_WINDOWS_CAPTURE`, `check_framerate_reset`, `draw_doubled_text`. | The import fails on Windows; no name is left outside history documents. |
| T-CAP-77 | 3c | hardware | With auto exposure and auto focus on, read the reported values; set manual with those values; compare the mean image before and after [D49]. | For each camera: whether the reported values are true, and the image difference, are recorded. |
| T-CAP-78 | 3c | hardware | Set and read back gain and focus; read white balance and power line frequency, on four cameras. | Each control that a camera has reads back the set value; absent ones show `present: false`; the read-only values are recorded. |
| T-CAP-79 | 3c | hardware | Detect the four cameras. | `capture_modes` agrees with the descriptor list of the prototype for each camera. |
| T-CAP-80 | 3a | fake | A fake whose first frame comes 6 s after the first `ReadSample`. | Failed, stage `first frame`, 5.0 to 5.25 s after the first `ReadSample`; the close runs with its bounded steps; the process does not end hard. |
| T-CAP-81 | 3a | fake | Two fakes, no recording; one stops delivering. | It is `dead` and treated as `failed` [U6]: a record start returns 409; an apply reopens only it. |
| T-CAP-82 | 3a | fake | Two fakes are `ready`; a control read of one hangs past its limit, on the control thread [U16]. | That camera reports stage `streaming` and its process ends hard; the main process cleans up only it; the other camera has no gap above 100 ms [U16]. |
| T-CAP-83 | 3a | fake | Each fake camera in its own group: (1) a request of 25; (2) a request of 30 for a camera whose detection data has only 15 and 24 at the size; (3) the same, but the detection data shows 30 and the open finds only 24; (4) a request of 29.97 where the camera has 29.97; (5) auto for a camera with 29.97 and 60 at the size. | (1) and (2) get 422 and change nothing; (3) fails, stage `set mode`, "no mode at 30 fps or more"; (4) opens at 29.97; (5) opens at 29.97 [U11]. |
| T-CAP-84 | 3a | fake | Three fakes run at 30 fps: (1) a request asks one for 60; (2) a request changes the size of two cameras, and the open of one fails in the fake. | (1) gets 422, and all three keep running at 30 with unchanged rings; (2) the failing camera is `failed`, the other has the new size, and the third is not touched [U10]. |
| T-CAP-85 | 3a | fake | During a recording, a bounded call of one fake hangs (the control read on the control thread [U16]). Case 1: the recorder of that camera needs 1 s to close its file. Case 2: it needs 8 s. | The failure is reported; case 1: the file is finished, and the process ends hard within 1.5 s of the report; case 2: the process ends hard 5.0 to 5.5 s after the report; in both cases the other cameras keep recording with no gap above 100 ms [U12, U16]. Replaced by T-REC-44 (note of 2026-11-20). |
| T-CAP-86 | 3a | fake | Three fakes with preview; reopen one camera by a change of its resolution. Capture relay messages during the reopen. | Each message holds the newest frame of each camera that has one; the frames of the other two cameras keep advancing while the third is `starting`; the third comes back after `ready` [U13]. |
| T-CAP-87 | 3a | fake | Shared loop with the OpenCV fake on each OS: 60 frames, each 70 ms late (more than 2 x the period). | No reopen: the open count stays 1; each ring JPEG decodes to the fake image, with no stamp [U2]. |
| T-CAP-88 | 3a | hardware | With `SKELLYCAM_WINDOWS_CAPTURE=opencv` in the new loop, open the C922, the C930e and the Kiyo Pro. | Each opens the DirectShow device whose device instance part equals that of the Media Foundation link that detection named for its `camera_id`, and the friendly names agree [U1]. |
| T-CAP-89 | 3b | fake | A YUY2 request at 1280x720 for a fake with YUY2 only at 10 fps there; then at 640x480 where it has 30. | The first gets 422 with "no mode at 30 fps or more"; the second opens [U11]. |
| T-CAP-90 | 3a | fake | A camera is `ready` with `MANUAL -7`. (1) A live exposure change to -5: the fake set call returns an error. (2) The same change: the set returns success, but the read-back is -6. | In both cases: the camera stays `ready`; its config keeps exposure -7 (the test does not check the value that the status reads) [agent 67]; the ring name stays; the apply response has a `control_change_failed` item for that camera; no other camera changes [U14]. |
| T-CAP-91 | 3a | fake | One group: a fake at 30000/1001 and a fake at 30/1; run for a simulated 100 s. Then a request that adds a camera at 60. | The apply response has one `mixed_rate` item with the camera IDs, "29.97 fps", "30 fps" and "about every 33 s"; the log has the text; the group rate is 29.97; the `replaced_count` of the 30 fps camera is 3 (±1); the request with 60 gets 422 [U15]. |

| T-CAP-92 | 3a | hardware | Linux and macOS, counterpart of T-CAP-52 [U21]: open the C922, the C930e and the Kiyo Pro at 1280x720 30 through the OpenCV source, one at a time. | Each reaches `ready`; for 300 frames the ring JPEG decodes to a 1280x720 image; `measured_fps` is within 3 % of 30, also with no reported rate [W2]. |
| T-CAP-93 | 3a | hardware | Linux and macOS, counterpart of T-CAP-54 [U21]: each camera at 1280x720: 30 on each camera, 60 on the C922 and the Kiyo Pro. | For each rate: state, measured rate and failure are recorded; a rate-check failure gives the reason of 10.4. No pass value. |
| T-CAP-94 | 3a | hardware | Linux and macOS, counterpart of T-CAP-53 [U21]: open the generic camera at 1280x720 30. | `failed`, stage `rate check`, the reason of 10.4 with a measured rate within 0.5 fps of 25.76; with no reported rate, the check uses the requested rate [W2]. |
| T-CAP-95 | 3a | hardware | Linux and macOS, counterpart of T-CAP-58 [U21]: record with the C922 and the C930e; the user unplugs the C922 at 20 s. | OpenCV gives no device-removed event: the C922 is `dead` 2.0 to 2.5 s after its last ring frame [agent 76]; the C930e records to the stop; the manifest has `camera_dead` for the C922, and its file has placeholders to the stop (note of 2026-11-20). |
| T-CAP-96 | 3a | hardware | Linux and macOS, counterpart of T-CAP-55 [U21]: each camera opened in a dark room with auto exposure. | For each camera: state, measured rate and reason are recorded; no traceback. |
| T-CAP-97 | 3a | hardware | Linux and macOS, counterpart of T-CAP-57 [U21]: open at `MANUAL -8`; exposure steps -7, -6, -5, -4 while open. | Each change gives `checking`, then `ready` or `too_slow`; with no reported rate, the check uses the requested rate [W2]. States, rates and read-back values are recorded; no predicted state, because table 10.5 holds Media Foundation values and Linux forces auto exposure (14.1) [agent 76]. |
| T-CAP-98 | 3a | hardware | Linux and macOS, counterpart of T-CAP-60 [U21]: the C922, the C930e and the Kiyo Pro at 1280x720 30 through the OpenCV source, lockstep, one recording of 60 s. | Equal frame counts; a group rate from 29.7 to 30.3; for each camera, the gaps of `source_frame_number` equal its replaced count of the stop line. The reference run with the OpenCV loop of today is a separate run. |
| T-CAP-99 | 3a | fake | OpenCV fake [U23]: (1) a request of 25; (2) a request of 30, and OpenCV reports a real rate of 24 after the open; (3) a request of 30, and OpenCV reports no rate. | (1) 422, and no camera opens; (2) failed, stage `set mode`, "no mode at 30 fps or more"; (3) `ready`, with no floor check, and `measured_fps` within 3 % of 30: the check uses the requested rate [W2, agent 59]. |
| T-CAP-100 | 3a | fake | Two OpenCV fakes [U23]: (1) requests of 30 and 60; (2) both requests auto, and OpenCV reports 30 for one and 60 for the other after the open. | (1) 422, and no camera opens; (2) both reach `ready`; a log record at WARNING names both camera IDs, and the apply response has one `mixed_rate` item with both [agent 75, W3]; no camera is closed [agent 56]. |
| T-CAP-101 | 3a | fake | The OpenCV fake delivers 25 fps [U23]. (1) OpenCV reports 30. (2) OpenCV reports no rate. | (1) failed, stage `rate check`, the reason of 10.4 with declared 30.00 and a measured rate within 0.75 fps of 25 [agent 78]; (2) the same: the check uses the requested rate [W2]. |
| T-CAP-102 | 3a | fake | Three OpenCV fakes; one cannot open [U23]. | That camera is `failed` with stage `open`; the other two reach `ready` with preview; a record start returns 409 and names it [D23]. |
| T-CAP-103 | 3a | fake | Two OpenCV fakes record; the grabs of one start to fail, as after an unplug [U23]. | That camera is `dead` 2.0 to 2.25 s after its last ring frame [agent 78]; the other camera keeps recording to the stop; the manifest has `camera_dead` for it [D38, M8] (note of 2026-11-20). |
| T-CAP-104 | 3a | fake | Two OpenCV fakes, two recordings [U23]. (1) The config asks for `AUTO`. (2) The config asks for `MANUAL`; Linux only, because the OpenCV source forces auto exposure there (14.1). | Each record start gives the `auto_control` warning for `exposure` one time for each camera [D37]. |
| T-CAP-105 | 3a | fake | Two fakes; the friendly name of one contains "virtual". (1) Detect, then apply both. (2) Apply both with no detection result. | Detection shows `virtual: true`; both requests get 422 that names the camera; no camera opens; in (2), the apply request ran the detection [W5, agent 79]. |
| T-CAP-106 | 3a | fake | A Media Foundation link in mixed case, in `CameraDeviceInfo` and in `MediaFoundationDeviceInfo` (the second on Windows only [U18]). | The mixed-case and the lower-case link give one `camera_id`, the rule of 7.2; `path` keeps the case [W6]. |
| T-CAP-107 | 3a | fake | Two fakes on a 100 ms grid; one delivers 60 fps from 8 s to 12 s of the clock. | The status shows `replaced_count` above 0; at the end, it equals the count of the stop line and the gaps of `source_frame_number` [W4]. |
| T-CAP-108 | 3a | fake | Three fakes record; one gives device removed, and its close takes 2 s. | It is `dead` before its close starts; the two others record on with no gap above 100 ms [D38, agent 82]. Note of 2026-11-20: the close comes after the end of the recording [M1]. |
| T-CAP-109 | 3a | fake | Two fakes in camera processes; the process of one ends with `os._exit(3)`: (1) at the open; (2) at frame 300 during a recording. | (1) `failed`, stage `open`, and the apply response holds it; the other is `ready`. (2) `dead`, stage `streaming`; the other records on; the stop returns 200 and the manifest has `camera_dead` for it with the exit code (note of 2026-11-20). The reason is "camera process ended (exit code 3)" [agent 81]. |
| T-CAP-110 | 3a | fake | A recording of 10 s; then the control read of one fake hangs. | The process ends hard; after the stop, the manifest has `camera_dead` with the reason "hang" and the `last_frame` of the last row of its sidecar with a block, not `none`, and `camera_file_short` [R4, M5, M8] (note of 2026-11-20; before, the files message of U12). |
| T-CAP-111 | 3a | fake | `OpenCVSource` with a stand-in capture: the loop thread reads 300 frames while a second thread reads the controls. | No two calls on the capture overlap [agent 85]. |
| T-CAP-112 | 3a | fake | Frames 2 to 95 arrive together, 94 ms after frame 1. | `ready`, with `measured_fps` within 3 % of 30; no failure of an empty window [agent 26]. |
| T-CAP-113 | 3a | fake | Two fakes are `ready`; the second delivers 1.6 fps for 12 s, so the first waits at the gate. A live exposure change of the first. | The check ends `ready`, with `measured_fps` within 3 % of 30, not `too_slow` [agent 88]. |

T-CAP-92 to T-CAP-104 come from the answers U21 and U23 of the user; their step is 3a. T-CAP-105 to
T-CAP-113 come with the fixes of the review of the 3a code (W4 to W6, [ADR-6EKB](../decisions/entries/6EKB-choices-of-the-3a-review-fixes.md)); their step is 3a.

### 16.3 Hardware tests of D49

T-CAP-54 (each offered MJPG rate at 720p: 30 on each camera, and 60 on the C922 and the Kiyo Pro
[U11]), T-CAP-55 (a dark room with auto exposure) and T-CAP-77
(auto values and the image after the switch to manual) are the hardware tests of D49. They record
results. They have no fixed pass value, because the decisions do not give one.

### 16.4 Comparison run [D48]

- Three cameras: the C922, the C930e and the Kiyo Pro, at 1280x720 MJPG 30 fps, lockstep, lights on,
  one recording of 60 s for each run [agent 40].
- The reference run uses the OpenCV loop of today: the last commit of `dom/native-jpeg` before phase
  3, in a second worktree, as the comparison of step 2a did [agent 40].
- The native run uses the shared loop with the Media Foundation source.
- Pass, for the native run: equal frame counts across cameras; a group rate within 1 % of 30 fps
  (29.7 to 30.3); for each camera, the gaps of `source_frame_number` equal the increase of its
  `replaced_count`, both from the first frame that the camera takes in the gate (5.2) [D48]. The OpenCV run is the reference
  [U3].
- The result goes to an evidence entry, as the summary of the 2026-11-18 comparison in
  `decisions/open-work.md`.

### 16.5 Decision to tests

| Decision | Tests |
|---|---|
| D1 | T-CAP-46, T-CAP-47 |
| D2 | T-CAP-52, T-CAP-62, T-CAP-63, T-CAP-64, T-CAP-66, T-CAP-68, T-CAP-69 |
| D3 | no test: the method of the spec; section 16.1 applies it |
| D4 | T-CAP-26, T-CAP-71 |
| D5 | no test: the order of the phases |
| D6 | T-CAP-01, T-CAP-08, T-CAP-44 |
| D7 | T-CAP-45, T-CAP-46 |
| D8 | T-CAP-43, T-CAP-76 |
| D9 | T-CAP-09, T-CAP-10, T-CAP-67 |
| D10 | T-CAP-40, T-CAP-48, T-CAP-80, T-CAP-82, T-CAP-85 |
| D11 | T-CAP-24, T-CAP-51 |
| D12 | T-CAP-52 (opens by path); no index call exists in the source |
| D13 | T-CAP-19, T-CAP-22, T-CAP-23, T-CAP-56 |
| D14 | T-CAP-25, T-CAP-51, T-CAP-71, T-CAP-79 |
| D15 | T-CAP-26, T-CAP-83 |
| D16 | T-CAP-27, T-CAP-83 |
| D17 | T-CAP-28 |
| D18 | T-CAP-29, T-CAP-70, T-CAP-84, T-CAP-91 |
| D19 | T-CAP-61, T-CAP-70 |
| D20 | T-CAP-12 |
| D21 | T-CAP-13, T-CAP-14, T-CAP-65 |
| D22 | T-CAP-15, T-CAP-16, T-CAP-17 |
| D23 | T-CAP-19, T-CAP-20, T-CAP-21 |
| D24 | T-CAP-17, T-CAP-53 |
| D25 | T-CAP-18, T-CAP-20, T-CAP-53 |
| D26 | T-CAP-02, T-CAP-03, T-CAP-04, T-CAP-05 |
| D27 | T-CAP-05, T-CAP-06 |
| D28 | T-CAP-07, T-CAP-59 |
| D29 | T-CAP-41 |
| D30 | T-CAP-42, T-CAP-75, T-CAP-77 |
| D31 | T-CAP-30, T-CAP-72, T-CAP-90 |
| D32 | T-CAP-31, T-CAP-57 |
| D33 | T-CAP-32 |
| D34 | T-CAP-11 |
| D35 | T-CAP-41 |
| D36 | T-CAP-33 |
| D37 | T-CAP-34 |
| D38 | T-CAP-35, T-CAP-36, T-CAP-58, T-CAP-81, T-CAP-82, T-CAP-108, T-CAP-109 |
| D39 | T-CAP-37 |
| D40 | T-CAP-38 |
| D41 | T-CAP-39 |
| D42 | T-CAP-50 |
| D43 | T-CAP-72, T-CAP-73, T-CAP-74, T-CAP-78 |
| D44 | T-CAP-74, T-CAP-78 |
| D45 | no test: not in phase 3 |
| D46 | T-CAP-44; hardware: no test until phase 0 [D46] |
| D47 | T-CAP-46; the jobs of section 15 run the fake tests |
| D48 | T-CAP-49, T-CAP-50, T-CAP-52, T-CAP-53, T-CAP-60 |
| D49 | T-CAP-54, T-CAP-55, T-CAP-77 |
| U1 | T-CAP-88 |
| U2 | T-CAP-87; T-CAP-76 (names gone on Windows) |
| U3 | T-CAP-60 |
| U4 | T-CAP-35 |
| U5 | T-CAP-10 |
| U6 | T-CAP-81 |
| U7 | T-CAP-29, T-CAP-70 |
| U8 | T-CAP-71 |
| U9 | T-CAP-38 |
| U10 | T-CAP-84 |
| U11 | T-CAP-25, T-CAP-27, T-CAP-54, T-CAP-71, T-CAP-83, T-CAP-89 |
| U12 | T-CAP-85 |
| U13 | T-CAP-86 |
| U14 | T-CAP-90 |
| U15 | T-CAP-91 |
| U16 | T-CAP-82, T-CAP-85, T-CAP-42 |
| U17 | T-CAP-15 (warm-up count, `measured_fps`), T-CAP-29 and T-CAP-83 (detection data), T-CAP-50 (T-RING-46) |
| U18 | T-CAP-22, T-CAP-23, T-CAP-24, T-CAP-48 (Windows only) |
| U19 | no test: the API entry [ADR-HP7D](../decisions/entries/HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md) |
| U20 | the jobs of section 15; T-CAP-45 and the OpenCV-source tests on three systems |
| U21 | T-CAP-92 to T-CAP-98 |
| U22 | no test: the parity table of 16.7 |
| U23 | T-CAP-99 to T-CAP-104 |
| W1 | no test: the acceptance of items 65 to 78 |
| W2 | T-CAP-44, T-CAP-99, T-CAP-101; hardware: T-CAP-92, T-CAP-94, T-CAP-97 |
| W3 | T-CAP-100 |
| W4 | T-CAP-107 |
| W5 | T-CAP-105 |
| W6 | T-CAP-106 |
| W7 | `skellycam/tests/test_utf8_console.py` |
| W8 | T-CAP-49 (T-RING-31 is retired) |

### 16.6 Counts

By step and kind. A cell gives the tests on Windows / Linux / macOS (16.1, 16.7) [U18, U20, U21].

| Step | fake | hardware | CI | local | Total |
|---|---|---|---|---|---|
| 3a | 71 (71 / 66 / 66) | 18 (11 / 7 / 7) | 2 (2 / 1 / 1) | 2 (2 / 0 / 0) | 93 (86 / 74 / 74) |
| 3b | 9 (9 / 9 / 9) | 2 (2 / 0 / 0) | 0 | 0 | 11 (11 / 9 / 9) |
| 3c | 6 (6 / 5 / 5) | 3 (3 / 0 / 0) | 0 | 0 | 9 (9 / 5 / 5) |
| All | 86 (86 / 80 / 80) | 23 (16 / 7 / 7) | 2 (2 / 1 / 1) | 2 (2 / 0 / 0) | 113 (106 / 88 / 88) |

T-CAP-80 to T-CAP-113 are at the end of the table; their step is in the table. T-CAP-106 runs on each
system; its case for `MediaFoundationDeviceInfo` runs on Windows only. 25 tests run on
Windows only: T-CAP-22, 23, 24, 43, 46, 48, 49, 50, the 11 Windows hardware tests of 3a, and T-CAP-68,
69, 76, 77, 78 and 79. 7 tests run on Linux and macOS only: T-CAP-92 to T-CAP-98.

### 16.7 Parity of the systems [U22]

One row for each test: its state on Windows, Linux and macOS. "runs": the test runs on that
system (the hardware tests on the word of the user). "counterpart": another test checks the same
rule there. "no counterpart until phase 7": no test there yet, with the reason below. "not
applicable": the rule does not exist on that system [agent 77]. This table is the to-do list of
phase 7 for Linux and macOS [U22].

Reasons:

- (a) The package `media_foundation/` is Windows only [U18]. On Linux and macOS, detection is
  `cv2_enumerate_cameras`, with no mode list and no device link.
- (b) A local test of the Windows development machine. T-RING-31, the test of the phase 2 loop on each
  system, is retired [W8].
- (c) The setting and its deletion exist on Windows only (14.2).
- (d) OpenCV gives no sample time (`NO_SAMPLE_NS`) and no in-use reason; they come from Media
  Foundation.
- (e) Uncompressed modes, the full mode list and the `IAM`/`IKsControl` controls come through the
  Media Foundation source. The OpenCV source gives BGR and no mode list.
- (f) The DirectShow device path exists on Windows only (U1).
- (g) On Linux and macOS, the limit of libjpeg warnings already works in the camera process; T-RING-46
  runs there in the ring tests.

| ID | Windows | Linux | macOS |
|---|---|---|---|
| T-CAP-01 | runs | runs | runs |
| T-CAP-02 | runs | runs | runs |
| T-CAP-03 | runs | runs | runs |
| T-CAP-04 | runs | runs | runs |
| T-CAP-05 | runs | runs | runs |
| T-CAP-06 | runs | runs | runs |
| T-CAP-07 | runs | runs | runs |
| T-CAP-08 | runs | runs | runs |
| T-CAP-09 | runs | runs | runs |
| T-CAP-10 | runs | runs | runs |
| T-CAP-11 | runs | runs | runs |
| T-CAP-12 | runs | runs | runs |
| T-CAP-13 | runs | runs | runs |
| T-CAP-14 | runs | runs | runs |
| T-CAP-15 | runs | runs | runs |
| T-CAP-16 | runs | runs | runs |
| T-CAP-17 | runs | runs | runs |
| T-CAP-18 | runs | runs | runs |
| T-CAP-19 | runs | runs | runs |
| T-CAP-20 | runs | runs | runs |
| T-CAP-21 | runs | runs | runs |
| T-CAP-22 | runs | no counterpart until phase 7 (a) | no counterpart until phase 7 (a) |
| T-CAP-23 | runs | no counterpart until phase 7 (a) | no counterpart until phase 7 (a) |
| T-CAP-24 | runs | no counterpart until phase 7 (a) | no counterpart until phase 7 (a) |
| T-CAP-25 | runs | runs | runs |
| T-CAP-26 | runs | runs | runs |
| T-CAP-27 | runs | runs | runs |
| T-CAP-28 | runs | runs | runs |
| T-CAP-29 | runs | runs | runs |
| T-CAP-30 | runs | runs | runs |
| T-CAP-31 | runs | runs | runs |
| T-CAP-32 | runs | runs | runs |
| T-CAP-33 | runs | runs | runs |
| T-CAP-34 | runs | runs | runs |
| T-CAP-35 | runs | runs | runs |
| T-CAP-36 | runs | runs | runs |
| T-CAP-37 | runs | runs | runs |
| T-CAP-38 | runs | runs | runs |
| T-CAP-39 | runs | runs | runs |
| T-CAP-40 | runs | runs | runs |
| T-CAP-41 | runs | runs | runs |
| T-CAP-42 | runs | runs | runs |
| T-CAP-43 | runs | not applicable (c) | not applicable (c) |
| T-CAP-44 | runs | runs | runs |
| T-CAP-45 | runs | runs | runs |
| T-CAP-46 | runs | no counterpart until phase 7 (a) | no counterpart until phase 7 (a) |
| T-CAP-47 | runs | runs | runs |
| T-CAP-48 | runs | no counterpart until phase 7 (a) | no counterpart until phase 7 (a) |
| T-CAP-49 | runs | no counterpart until phase 7 (b) | no counterpart until phase 7 (b) |
| T-CAP-50 | runs | not applicable (g) | not applicable (g) |
| T-CAP-51 | runs | no counterpart until phase 7 (a) | no counterpart until phase 7 (a) |
| T-CAP-52 | runs | counterpart T-CAP-92 (phase 0) | counterpart T-CAP-92 (phase 0) |
| T-CAP-53 | runs | counterpart T-CAP-94 (phase 0) | counterpart T-CAP-94 (phase 0) |
| T-CAP-54 | runs | counterpart T-CAP-93 (phase 0) | counterpart T-CAP-93 (phase 0) |
| T-CAP-55 | runs | counterpart T-CAP-96 (phase 0) | counterpart T-CAP-96 (phase 0) |
| T-CAP-56 | runs | no counterpart until phase 7 (d) | no counterpart until phase 7 (d) |
| T-CAP-57 | runs | counterpart T-CAP-97 (phase 0) | counterpart T-CAP-97 (phase 0) |
| T-CAP-58 | runs | counterpart T-CAP-95 (phase 0) | counterpart T-CAP-95 (phase 0) |
| T-CAP-59 | runs | no counterpart until phase 7 (d) | no counterpart until phase 7 (d) |
| T-CAP-60 | runs | counterpart T-CAP-98 (phase 0) | counterpart T-CAP-98 (phase 0) |
| T-CAP-61 | runs | runs | runs |
| T-CAP-62 | runs | runs | runs |
| T-CAP-63 | runs | runs | runs |
| T-CAP-64 | runs | runs | runs |
| T-CAP-65 | runs | runs | runs |
| T-CAP-66 | runs | runs | runs |
| T-CAP-67 | runs | runs | runs |
| T-CAP-68 | runs | no counterpart until phase 7 (e) | no counterpart until phase 7 (e) |
| T-CAP-69 | runs | no counterpart until phase 7 (e) | no counterpart until phase 7 (e) |
| T-CAP-70 | runs | runs | runs |
| T-CAP-71 | runs | runs | runs |
| T-CAP-72 | runs | runs | runs |
| T-CAP-73 | runs | runs | runs |
| T-CAP-74 | runs | runs | runs |
| T-CAP-75 | runs | runs | runs |
| T-CAP-76 | runs | not applicable (c) | not applicable (c) |
| T-CAP-77 | runs | no counterpart until phase 7 (e) | no counterpart until phase 7 (e) |
| T-CAP-78 | runs | no counterpart until phase 7 (e) | no counterpart until phase 7 (e) |
| T-CAP-79 | runs | no counterpart until phase 7 (e) | no counterpart until phase 7 (e) |
| T-CAP-80 | runs | runs | runs |
| T-CAP-81 | runs | runs | runs |
| T-CAP-82 | runs | runs | runs |
| T-CAP-83 | runs | runs | runs |
| T-CAP-84 | runs | runs | runs |
| T-CAP-85 | runs | runs | runs |
| T-CAP-86 | runs | runs | runs |
| T-CAP-87 | runs | runs | runs |
| T-CAP-88 | runs | not applicable (f) | not applicable (f) |
| T-CAP-89 | runs | runs | runs |
| T-CAP-90 | runs | runs | runs |
| T-CAP-91 | runs | runs | runs |
| T-CAP-92 | not applicable: Windows runs T-CAP-52 | runs (phase 0) | runs (phase 0) |
| T-CAP-93 | not applicable: Windows runs T-CAP-54 | runs (phase 0) | runs (phase 0) |
| T-CAP-94 | not applicable: Windows runs T-CAP-53 | runs (phase 0) | runs (phase 0) |
| T-CAP-95 | not applicable: Windows runs T-CAP-58 | runs (phase 0) | runs (phase 0) |
| T-CAP-96 | not applicable: Windows runs T-CAP-55 | runs (phase 0) | runs (phase 0) |
| T-CAP-97 | not applicable: Windows runs T-CAP-57 | runs (phase 0) | runs (phase 0) |
| T-CAP-98 | not applicable: Windows runs T-CAP-60 | runs (phase 0) | runs (phase 0) |
| T-CAP-99 | runs | runs | runs |
| T-CAP-100 | runs | runs | runs |
| T-CAP-101 | runs | runs | runs |
| T-CAP-102 | runs | runs | runs |
| T-CAP-103 | runs | runs | runs |
| T-CAP-104 | runs (case 1) | runs (cases 1 and 2) | runs (case 1) |
| T-CAP-105 | runs | runs | runs |
| T-CAP-106 | runs | runs (`CameraDeviceInfo` case) | runs (`CameraDeviceInfo` case) |
| T-CAP-107 | runs | runs | runs |
| T-CAP-108 | runs | runs | runs |
| T-CAP-109 | runs | runs | runs |
| T-CAP-110 | runs | runs | runs |
| T-CAP-111 | runs | runs | runs |
| T-CAP-112 | runs | runs | runs |
| T-CAP-113 | runs | runs | runs |

Short form: Windows runs 106 tests, Linux 88 and macOS 88. 7 Windows hardware tests have a counterpart
on Linux and macOS. 14 tests have no counterpart there until phase 7 (reasons a, b, d, e), and 4 tests
are not applicable there (reasons c, f, g).

## 17. Measurements, open points, weak points

### 17.1 Measurements still to make

| ID | Measurement | Step |
|---|---|---|
| M-CAP-1 | CPU per camera process with the native loop and the interim decode, four cameras at 720p30, recording and not recording | 3a |
| M-CAP-2 | Time from open to `ready` per camera (open, first frame, warm-up, check) | 3a |
| M-CAP-3 | The relation of `sample_ns` to `arrival_ns` (T-CAP-59) | 3a |
| M-CAP-4 | Detection time with activation of each device, and its effect on streaming cameras (T-CAP-51) | 3a |
| M-CAP-5 | Whether the hosted Windows runner has Media Foundation | 3a |
| M-CAP-6 | Rates of each camera at each offered rate (30, and 60 where offered) and in a dark room (T-CAP-54, T-CAP-55) | 3a |
| M-CAP-7 | Whether a camera in auto mode reports its true value (T-CAP-77) | 3c |

### 17.2 Open points

Differences from the ring spec. The ring spec is accepted, so this spec does not edit it. The user
decides each one:

1. [ring 4] lists two events that set `DISCONTINUITY`. D34 adds a third: a discontinuity that capture
   reports, also when it came with a replaced frame (4.3).
2. [ring 5.1] says "+1 per frame that capture delivers" [A17]. With a push source, this spec counts
   the frames that the loop takes (5.3), and `source_frame_number` counts the delivered frames [D27].
3. [ring 5.3] and its open question 3 (the skip trigger). While the gate exists, this spec never sets
   `newer_frame_waiting` (5.1 step 7). Phase 8 decides.
4. [ring 9] says that in 2a the mode list holds only the opened mode. In 3c, `capture_modes` fills it,
   with the format from the Media Foundation subtype.
5. Resolved by step 5a.
6. [ring 8.9] reads the libjpeg pipe in the camera process. On Windows, D42 puts the read end in the
   main process (5.6).
7. [ring 2.3] fills the relay at the newest frame number that all cameras have. U13 sends the newest
   frame of each camera on its own (5.8).

Other open points:

8. The child monitor of the worker registry treats an unexpected exit as a crash of the backend today
   (comment in `opencv_camera_worker_method.py`). Section 6.6 needs it to treat a reported failure as
   a camera failure.
9. How a spawned camera process gets a pipe as its standard error handle on Windows (5.6) [NV].
10. `RECOMMEND` searched exposures from -12 to -4. At -4 the Logitech cameras give 16 fps (10.5), so a
    recommended value could fail the rate check after the open. Resolved on 2026-11-20: the range ends at
    -5 (H of [ADR-JMS0](../decisions/entries/JMS0-connection-review-decisions.md)).
11. The in-use codes at stages other than the first frame are [NV]. Only `0xC00D3704` at the first
    frame is measured.
13. No test checks the real time limits of the Media Foundation source: the first-frame limit of 6.4
    and the bounded-call limit of 6.6. No hardware test can make a camera hang, and the fake source
    produces these limits itself (16.1). T-CAP-52 and T-CAP-54 show only that normal opens stay under
    them.
14. The parity table of 16.7 is the to-do list of phase 7 for Linux and macOS [U22].

### 17.3 Known weak points (from the decisions)

- The 3 % limit rests on about 2,000 opens of four cameras on one machine.
- The Kiyo Pro slows down at exposure -6 (28.7 fps) and longer, so it fails the check at settings
  that the Logitech cameras accept.
- Whether a camera in auto mode reports its true current value is unknown until the hardware test.
- The cause of the 25.76 fps of the generic camera is not known.
- Opens during control changes showed dips to 20 to 25 fps on the C930e and the Kiyo Pro in a few
  percent of opens in older data. The cause is not known.

- No test camera declares 29.97 fps. All four declare 30.00003 and 60.0002 fps (frame intervals
  333333 and 166666 in units of 100 ns) in the USB descriptors of the suite run of 2026-11-19
  (`research/usb_cameras/results/windows/`, branch `dom/research`). Thus the rate class of U15 rests
  on fake-source tests only.

A known effect of this spec: until phase 7, each Linux recording gives the auto warning of D37 one
time for each camera, because the OpenCV source forces auto exposure on Linux (14.1).

## 18. Choices of the agent

Each item fills a gap that the decisions, the answers of the user, the ring spec and the plan do
not fix. The body marks each one [agent n].

1. The module layout and names of section 3.
2. The fake source in `skellycam/tests/capture/fake_source.py`; the markers `camera_hardware` (with
   `SKELLYCAM_HARDWARE=1`) and `capture_local` (the kind "local"); the run rules of T-CAP-43 and
   T-CAP-76.
3. `set_controls({})` reads all controls, so the interface keeps the four calls of D6.
4. The source uses the rules of `WaitingPlace` of the ring package for "newest wins" (D26), with two
   additions (items 46 and 50).
5. Ring `frame_number` counts the frames that the loop takes; the OpenCV source count is its grab
   count; the gate count continues across a ring recreation; a camera that joins the gate again
   takes the largest gate count of the group.
6. `newer_frame_waiting=False` while the gate exists.
7. The old frame record gets `arrival_ns` in both grab stamps.
8. The interim decode runs only for a recorded frame or a camera with a BGR ring.
9. The old recorder gets the mode rate as its frame rate.
10. `sample_ns = 100 x GetSampleTime`, and the `NO_SAMPLE_NS` rule of 4.2.
11. `driver_error` is always `False` for Media Foundation.
12. The source opens the device whose hashed link equals the `camera_id` of the config (no new
    config field); a second match is a failure.
13. `camera_id` hashes the lower-case link.
14. A time limit of 5 s for each bounded call and for the first frame; the 15 s of D21 count from
    the open to the end of the rate check; the shared loop owns this timer, and a call that runs at
    the deadline is not cut short.
15. The HRESULT sets for "in use" and "device removed" (from `parse.py` of the prototype).
16. On a hang: report, then `os._exit` with a non-zero code; the main process treats this as a
    camera failure. During a recording, the files are first finished (U12).
17. Detection runs in a short-lived child process.
18. Rates rounded to 2 decimal places.
19. The field name `capture_modes`, its fields, its order, and leaving out a synthesized NV12; a 3b
    request never takes a synthesized NV12.
20. The one-rate rule runs in the whole-request check before any open, on each source; it uses the
    mode rates from the detection data (Media Foundation; `supported_modes`, or the full native type
    list for a 3b request).
21. The state names, the status fields and `camera_failures` in the apply response.
22. A camera that fails at start ends its process; a dead camera process ends after its close steps;
    "apply again" starts a new process.
23. Device removed or a 2 s stall in `starting` is `failed` with the current stage, not `dead`.
24. "Unselect" is `use_this_camera: false` in an apply request.
25. A recording starts only when every selected camera is `ready`; one HTTP rule: 422 for a request
    that is not valid by its content, 409 for a valid request that the state does not allow.
26. The rate formula through `source_frame_number` differences.
27. No early decision at start-up; a new live change restarts the check.
28. The rule of the slow warning during a recording (blocks of 60 frames, one warning per slow
    period).
29. `RECOMMEND` runs in the shared loop with today's range and settle count, before the read-back;
    the stored config then holds `MANUAL` and the found value, as today.
30. The config names `gain`, `gain_auto`, `focus`, `focus_auto`; `None` means "not set".
31. The status reports exposure, gain and focus from 3a, read only; the loop reads them one time per
    second.
32. Phase 3 writes the camera data into the existing recording info JSON (`capture`,
    `dead_cameras`).
33. The `warnings` list in the responses of the record start and the apply request and in the
    status: one item form (`kind`, `camera_ids`, `text`, `control`), the kind `auto_control`, and the
    fixed text of D37.
34. The stage names of section 12.
35. The reason of an exception is `{type}: {message}`; the diagnostics go to the log.
36. 3b: the field `input_range`; a raw frame of the wrong length is flagged `CAPTURE_ERROR`; one BGR
    conversion for each recorded frame, shared by the old recorder and the BGR ring.
37. The done lists of 3b and 3c.
38. The setting of D8 is the environment variable `SKELLYCAM_WINDOWS_CAPTURE`.
39. The CI file name, the runner labels `windows-2025` and `ubuntu-24.04`, the test selection, and
    the late load of `mfplat.dll`.
40. The comparison run: three cameras, 60 s for each run, the OpenCV loop of today in a second
    worktree as the reference.
41. The pass thresholds that the test table adds.
42. The main process reads the error pipe of each camera process and limits the lines.
43. COM: the MTA in the loop thread and in the bounded-call workers; `MFStartup` in each camera
    process.
44. The config stores the read-back values (today's behaviour).
45. The cells of `starting`, `waiting` and `failed` in table 8.3.
46. A discontinuity of a replaced frame moves to the frame that replaces it.
47. The states that the gate counts (5.2); `should_grab_by_id` and `all_ready` change for them.
48. The reason texts "camera not found", "not ready in 15 s", "device removed", "no frame for 2 s",
    "end of stream" and the control error of 11.5.
49. `replaced_count` is reported from the first frame that the camera takes in the gate, so that it
    covers the span of the gaps exactly.
50. A source error puts an error marker in the waiting place, which wakes the loop.
51. The state `waiting` between the passed rate check and `ready`.
52. `last_frame_number` in the recording info is the gate count of the last recorded frame.
53. The field `reason` of `capture_modes`, and its texts "below 30 fps" and "never opened".
54. The relay leaves out a camera with no frame to show; the message header carries the largest
    frame number.
55. A request more than 0.5 fps below the floor gets HTTP 422 on each source.
56. OpenCV: the one-rate check compares the requested rates (all equal or all auto); on Windows
    during the build it uses the Media Foundation detection data; different real rates after the open
    give a warning only.
57. Auto chooses 29.97 when a camera has 29.97 and 60 but no 30 at the size (a reading of U11).
58. The floor applies to the exact rate of the chosen mode; where each floor case is decided (422 in
    the whole-request check, or stage `set mode` at the open).
59. OpenCV and the floor: a real rate above 0 and below 29.97 after the open fails the camera; no
    reported rate: the floor is not checked.
60. A bounded call that times out while the camera is open gives `dead`, stage `streaming`.
61. The interim decode runs on the loop thread.
62. A stream error or the end of the stream makes the camera dead at once, not after 2 s.
63. The kind `mixed_rate`, and the interval in whole seconds in its text.
64. A failed live change is reported as a `warnings` item of the kind `control_change_failed`.

Items 65 to 78 came with the answers U16 to U23 ([ADR-HB4Z](../decisions/entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md)). The user accepted them on 2026-11-20 [W1], with the changes of W2 (item 76) and W3 (item 75).

65. The script of T-CAP-05: a 100 ms grid, one fake at 60 fps from 20 s to 30 s of the clock, one
    dropped frame at 30 s, the last frame at 40 s, and 200 or more replaced frames.
66. An error marker waits behind a frame that waits; the marker never replaces a frame (4.3).
67. T-CAP-90 case 2 checks the exposure of the config, not the value that the status reads.
68. T-CAP-35: the removal at the next frame after 60 recorded frames; a multi-frame row after the dead
    camera has the mean time of the two live cameras.
69. T-CAP-40: the hang is at the reopen after a resolution change.
70. T-CAP-22: `0x80004005` gives `E_FAIL`, `0xC00D3E85` gives `MF_E_SHUTDOWN`; no text for an unknown
    code is tested.
71. T-CAP-53 and T-CAP-94: "near 25.76" is within 0.5 fps.
72. T-CAP-37: the warned rate is from 27 to under 29.1 fps.
73. The switches `SKELLYCAM_HARDWARE_DARK`, `SKELLYCAM_HARDWARE_UNPLUG` and `SKELLYCAM_HARDWARE_RESULTS`.
74. The macOS job: the label `macos-15`, its own job and concurrency group with `cancel-in-progress`, a
    time limit of 40 minutes, and the portable ring tests in that job.
75. T-CAP-100: the warning of different real rates is a log record at WARNING that names both cameras.
    W3 adds the `mixed_rate` item of the apply response.
76. The criteria of T-CAP-92 to T-CAP-98 where OpenCV cannot give what the Windows test needs: no rate
    check with no reported rate, an unplug is dead 2.0 to 2.5 s after the last frame, no predicted
    state from table 10.5. W2 rejects the first part: the check uses the requested rate.
77. The state "not applicable" of the parity table (16.7).
78. The OpenCV fake has `supported_modes = []` in its detection result (as on Linux and macOS);
    T-CAP-101 accepts 25 +/- 0.75 fps; T-CAP-103 accepts 2.0 to 2.25 s.

Items 79 to 90 came with the fixes of the review of the 3a code. [ADR-6EKB](../decisions/entries/6EKB-choices-of-the-3a-review-fixes.md) holds them in full. They wait
for a decision of the user.

79. An apply request runs the detection first when the kept result does not hold each selected camera.
80. `CameraDeviceInfo.modes_read`; with an empty `supported_modes` it gives 422 "no mode at 30 fps or
    more".
81. A camera process that ends with no final state: `failed` (stage `open`) in `starting`, else
    `dead` (stage `streaming`), reason "camera process ended (exit code N)".
82. A started camera that fails is `dead` at once; then its files, its control thread and its close.
83. The main process takes each files message from its queue at once; the hard end flushes the queue
    within the 5 s of U12, in one thread.
84. "Apply again" waits 10 s for the old camera process, then kills it.
85. The OpenCV source: one lock for the capture; gain and focus are absent when OpenCV reads -1.
86. One WARNING for each run of failed periodic control reads.
87. A camera selected again after an unselect starts again with its status; the whole-request check
    uses the current config of each camera that a request does not name.
88. The early decision of 10.2 comes only from a frame that did not come in time.
89. A paused camera sleeps 50 ms between its passes.
90. The phase 2 loop stays until the user decides the tests that also call it (W8).

## 19. Questions for the user

None open. The user answered Q-e and Q-f of the third draft on 2026-11-19 (U14, U15).

## 20. Decisions of the user (D1 to D49)

The user decided these on 2026-11-19
([ADR-EN7A](../decisions/entries/EN7A-phase-3-windows-capture-decisions.md)). They are binding. D23
and D38 replace the two older plan statements of 1.4.

**Route and steps**

- D1: Phase 3 is next. Pure-Python Media Foundation through comtypes, no compiled extension, built on
  `development-streaming`. It is meant to replace the Python capture work of the upstream branch
  `sfn26` later. No Rust. No merge of `sfn26` is planned; `sfn26` is a source of ideas only.
- D2: Three steps, each with its own tests and its own camera run. 3a: MJPG modes, the camera's JPEG
  passes untouched to the recorder path and the JPEG ring. 3b: uncompressed modes (YUY2, NV12):
  encoder, central Quick Sync check, range rule (already decided in the ring spec and the design
  notes). 3c: the full mode list and the controls.
- D3: A new spec `specs/windows-capture.md` before any code. Two kinds of tests: fake-source tests
  that run everywhere and in CI; hardware tests with a marker that need the cameras and run only on
  the user's word.
- D4: No H.264 modes in phase 3: not listed as selectable, not opened.
  - Note: the user corrected the wording on 2026-11-19 ([ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md), U8). H.264 and RAW
    modes are listed as not selectable in the 3c list, and never opened. `supported_modes` of 3a
    stays MJPG only.
- D5: Phase order: 3, 4, 5, 6, the certify part of skellycam, phase 0 (Linux and macOS hardware runs,
  done through the certify suite), 7, 8. Passing certify is the gate before phase 8.

**Structure**

- D6: One shared camera loop that knows the lockstep gate, the recorder and the rings; a small
  capture interface (open, read a frame, set controls, close) with three sources: Media Foundation
  (Windows), OpenCV (Linux and macOS, kept, with the JPEG re-encode of the ring spec 8.8), and a fake
  source for tests.
- D7: A new, smaller product module in the implementation worktree, written from the proven calls of
  the research prototype (`research/usb_cameras/suite/windows/pymf/` on branch `dom/research`). The
  prototype stays where it is. `comtypes` becomes a Windows-only dependency with an exact pin (the
  prototype pins 1.5.0; check the latest version before pinning).
- D8: While phase 3 is built, a setting chooses the source on Windows (OpenCV stays the default). The
  OpenCV source on Windows and that setting are deleted in the last commit of phase 3, after the
  comparison run passes. (Earlier decisions of the plan: OpenCV capture is deleted on Windows, no
  fallback; the "reset after 30 slow frames" reopen and the burned-in frame stamp go with it.)
- D9: Recorder during phase 3: the old recorder (decoded image in, H.264 out) stays until phase 5.
  The camera process decodes each JPEG once to feed it. When a BGR ring is on, the same decoded image
  feeds the BGR ring (no second decode). Phase 5 removes this decode. Measured decode cost: 2.60 ms at
  720p, 5.42 ms at 1080p (`cv2.imdecode`, one thread).
- D10: Every Media Foundation call that can hang (open, set mode, first frame, flush, release) has a
  time limit. On a hang the camera process reports the failure, then ends itself hard; the main
  process cleans up. Other cameras are not touched.
  - Note: for a hang during a recording, the user added an interim rule on 2026-11-19
    ([ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md), U12): finish the files of that camera for at most 5 s, then end hard.

**Detection, identity, modes**

- D11: Camera detection on Windows moves to Media Foundation in step 3a. `camera_id` = the same hash
  function as today, of the Media Foundation device path (symbolic link). Every Windows camera gets a
  new ID once.
- D12: A camera is opened by its device path, never by its index.
- D13: A camera that another program holds is reported as failed with the reason "in use by another
  program". A detection result in which two cameras get the same `camera_id` is refused.
- D14: `supported_modes` is filled from Media Foundation already in step 3a, in the shape of upstream
  `sfn26`: a list of `{width: int, height: int, framerates: list[float]}`, MJPG modes only, one entry
  per size, sizes ordered by area descending then width descending, rates ascending, duplicates
  merged. Rates are rounded so that 30.00003 reports as 30 and 29.97 stays 29.97 (the freemocap UI
  matches a rate by exact number). The richer list (format, "uncompressed" label, both MJPG and YUY2
  listed, JPEG preferred; see ring spec section 9) comes in step 3c as a second field.
- D15: Mode choice: exactly the requested size, in MJPG, at the nearest frame rate within 0.5 fps. If
  no such mode exists, the camera fails with a message that lists its modes.
- D16: "Auto" frame rate (requested rate -1 or 0): 30 fps if the camera has it in MJPG at the
  requested size, else the highest rate it has there. No region rule.
- D17: The config stores the rate of the chosen mode (so -1 becomes the real rate). Frame rates are
  compared with a relative tolerance of 0.0001.
- D18: While the lockstep gate exists, all cameras of a group must have the same mode frame rate; a
  group with different rates is refused. The rule compares mode rates, not measured rates.
  - Note: the user added on 2026-11-19 ([ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md), U15) that 29.97 and 30 fps are one
    rate class for this rule. A group that mixes them is allowed, with a warning.
- D19: Step 3b: the existing `capture_fourcc` setting asks for YUY2 or NV12 (default MJPG), until the
  mode list of 3c gives a proper choice.

**Start-up**

- D20: Order: open; choose the mode; start the stream; wait for the first frame; set every control;
  read each control back; then count the warm-up frames. Reason: on the C930e the gain read 6 before
  the stream started and 0 after it started.
- D21: Each camera discards 90 warm-up frames and must be ready within 15 s. Cameras wait paused until
  all are ready. (The range rule of step 3b examines discarded start frames.)
- D22: Start-up rate check. Rate = (frames - 1) / (last arrival time - first arrival time) over
  warm-up frames 6 to 90. The camera fails when the rate is more than 3 % below or above the rate of
  the mode that Media Foundation reports as set after the open (not the requested rate). The median
  interval must not be used: arrival times sit on a grid of about 16 ms, and the generic camera (56 %
  32 ms intervals, 43 % 48 ms) has the median of a 31 fps camera at a true 25.8 fps. Evidence:
  `research/usb_cameras/docs/startup_rate_check_20261119.md` on `dom/research`.
- D23: A camera that fails at start (cannot open, in use, no mode, not ready in 15 s, rate check
  failed) is flagged with its reason. The other cameras stay open and keep their preview. The start
  of a recording is blocked while a selected camera is failed. Two ways out: "apply again" reopens
  only the failed camera; or the user unselects it, and recording is allowed with the rest. skellycam
  never reopens a failed camera by itself (Kiyo Pro wedge rule: record the diagnostics, mark it dead,
  never revive it). This replaces the earlier plan decision "a camera that fails at open stops the
  session from starting".
- D24: The generic test camera (declares 30, delivers 25.76) fails the rate check by design. No
  override setting.
- D25: The failure message of a slow camera gives the declared rate, the measured rate, and two hints
  in this order: add light or shorten the exposure; or choose a rate the camera reaches.

**While cameras are open (no recording)**

- D26: Lockstep with a camera that pushes frames: when the gate opens for a camera, it gives the
  newest frame that has not been taken yet; if there is none, it waits for the next one. Frames that
  arrive while the gate is closed are replaced by newer ones and counted.
- D27: `source_frame_number` in the ring = the camera's own running count of delivered frames (a gap
  shows frames that lockstep did not take). The number of replaced frames per camera is logged at
  stop.
- D28: Frame time for the recorder and the ring lookup = arrival time, `perf_counter_ns` at callback
  entry. The Media Foundation sample time is carried in `sample_ns` and not used yet (phase 5
  decides).
- D29: Exposure modes MANUAL, AUTO (the camera's own auto exposure) and RECOMMEND (a one-time search
  at open that ends in MANUAL) stay. The goal is that auto modes are off during a recording. Before a
  recording, a consumer (freemocap) may use the camera's auto mode to set focus or exposure, then flip
  to manual to lock it.
- D30: The camera status reports the current value of exposure, gain and focus while cameras are
  open, also when the control is in auto, so a consumer can show it and set manual with exactly that
  value.
- D31: A change of exposure, gain or focus is applied live, without reopening. A change of resolution
  or frame rate reopens only that camera, recreates its rings, and repeats the warm-up and the rate
  check. A change can lower the frame rate for a moment while the camera adjusts.
- D32: After a live control change: skip 15 frames, then measure the rate over the next 60 frames with
  the formula of D22 and the 3 % limit, and decide early when the result is certain (a too-slow camera
  is declared as soon as the 60 frames can no longer arrive in time). A camera that fails is marked
  "too slow": it stays open with its preview, and recording is blocked until a later change passes
  the check. Evidence: the camera test in `startup_rate_check_20261119.md` (194 live changes;
  disturbance 0 to 16 frames; exposure -6 gives 28.7 fps on the Kiyo Pro, -4 gives 16 fps on the
  Logitech cameras).
- D33: The start of a recording is blocked while a rate check runs; status "checking".
- D34: A frame that a camera drops after a control change (Kiyo Pro: 5 in 51 changes) is normal:
  visible in the frame counter gap and the `DISCONTINUITY` flag, no warning.
  - Note: the body corrects "visible in the frame counter gap" (4.2, 10.2). `source_frame_number`
    counts the samples that the camera delivers, so a frame that the camera drops leaves no gap. It
    shows only in the `DISCONTINUITY` flag. A gap shows only frames that lockstep replaced (D27).
- D35: The exposure value keeps today's unit: a power of two in seconds (-7 = 1/128 s).

**During a recording**

- D36: Setting changes are refused during a recording.
- D37: If a control is still in an auto mode when a recording starts: start the recording anyway,
  leave the auto mode on, send a warning that names the camera and the control (so freemocap can catch
  it), and record in the capture info that the control was in auto for that take. Ideally freemocap
  never does this.
- D38: A camera is dead at once on a device-removed error from Media Foundation, and after 2 s without
  a frame otherwise. The dead camera leaves the gate, its files are finished, and the session reports
  the camera and its last frame. The other cameras keep recording (upstream stops the whole group;
  this differs on purpose). The recording must state the dead camera and its last frame clearly,
  because frame counts are then unequal across cameras.
- D39: A camera that slows down during a recording: a warning with the camera and the measured rate;
  the recording continues.

**Reporting, controls, smaller items**

- D40: A camera failure is reported as a structured object (camera ID, stage, reason) and also as a
  text in the wording of upstream: `Camera {id} failed during {stage}: {reason}`. The first failure is
  kept, and it is written before any shutdown flag is set.
- D41: A timestamp column is written only when that stage was stamped. A frame whose camera ID does
  not match the config is refused.
- D42: The Windows fix for T-RING-46 (libjpeg warning limit) is in step 3a: the main process gives
  each camera process a pipe as its error output before OpenCV loads ([ADR-E817](../decisions/entries/E817-choices-of-the-2b-code.md) item 7).
- D43: Step 3c adds gain and focus to the camera config (each a manual value and the camera's auto
  flag). White balance is read only and written to the capture info. A control that a camera lacks is
  reported as absent; setting it is an error with a clear message.
- D44: The UVC power line frequency control is not changed in phase 3. Step 3c reads it and writes it
  to the capture info. A flicker measurement and exposure advice are a later item outside phase 3.
- D45: Not in phase 3 (later, with the camera identity work of phase 5): the USB link display (USB 2
  or 3 per camera) and the Windows event-log check that explains a start failure as a USB removal.
- D46: The start-up rules (warm-up, rate check, failed-camera flag, one rate per group) apply to the
  OpenCV source too (Linux, macOS), but the rate check runs there only when OpenCV reports a real
  frame rate (> 0) for the camera. Linux and macOS behaviour is not tested until phase 0.
  - Note: W2 replaces "the rate check runs there only when OpenCV reports a real frame rate": with no
    reported rate, the check uses the requested rate, and 30 fps for "auto" ([ADR-PDD3](../decisions/entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md)).
  - Note: U21 writes the Linux and macOS hardware tests now; they run in phase 0. U20 and U23 run the
    OpenCV-source tests with the OpenCV fake on Linux and macOS in CI ([ADR-HB4Z](../decisions/entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md)).

**Tests, CI, done**

- D47: A new GitHub Actions job runs the fake-source tests and loads the Media Foundation module on a
  Windows runner, and runs the fake-source tests on a plain Linux runner, on pushes to
  `dom/native-jpeg`, with pinned versions (pattern: `.github/workflows/ring-arm64.yml`). The arm64 job
  stays as it is (ring tests only).
  - Note: U20 adds a macOS runner (Apple Silicon) to the CI of phase 3, with the fake-source tests,
    the OpenCV-source tests and the portable ring tests. For CI, this replaces the earlier plan that
    macOS stays out until phase 0 ([ADR-HB4Z](../decisions/entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md)).
- D48: Step 3a is done when: (1) all fake-source tests pass on the Windows development machine, the
  Windows CI runner and the plain Linux runner; (2) the hardware tests pass on the C922, C930e and
  Kiyo Pro, and the generic camera is refused by the rate check; (3) a three-camera recording, OpenCV
  loop against native loop, gives equal frame counts across cameras, a group rate within 1 % of 30
  fps, and no camera frame lost that the replaced-frame count does not explain; (4) T-RING-31 (idle
  CPU under 2 % of one core) and T-RING-46 pass on Windows. Matching lists for 3b and 3c.
  - Note: U20 adds the macOS CI runner to item (1). The Linux and macOS hardware tests of U21 are not
    in this list; they wait for phase 0. By W8, T-CAP-49 replaces T-RING-31 in item (4). By U17,
    T-RING-46 changes with the 3a code ([ADR-HB4Z](../decisions/entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md)).
- D49: Hardware tests that the spec must hold (they run on the user's word): each camera at each of
  its declared MJPG rates at 720p (does it deliver that rate?); each camera opened in a dark room with
  auto exposure; with auto exposure and auto focus on, does each camera report its true current
  value, and does the image stay the same after the switch to manual with that value?

**Answers of the user to the three drafts, 2026-11-19 ([ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md))**

- U1: While OpenCV is the default on Windows during the build, the OpenCV source finds its camera by
  the device part of the Media Foundation link.
- U2: The shared loop has no burned-in frame stamp and no "reopen after 30 slow frames" on any OS,
  from step 3a.
- U3: The pass limits of the comparison run apply to the native run. The OpenCV run is the reference.
- U4: A dead camera during a recording: the timing file of each camera ends at its own last frame;
  the multi-frame rows continue with the cameras that are alive; the recording info names the dead
  camera and its last frame. This is an interim rule of phase 3. It must change back in phase 5.
- U5: A flagged frame gives the old recorder the last good image again, and the count is logged at
  stop. This is an interim rule of phase 3. It must change back in phase 5.
- U6: A camera that dies while no recording runs is treated as a failed camera.
- U7: A request for a group with different mode rates is refused as a whole, and no camera is opened.
- U8: The 3c list holds H.264 and RAW modes with `selectable: false`. They are never opened. This
  corrects the wording of D4.
- U9: The first failure is kept for each camera.
- U10: A request is checked as a whole first. A refused request (409 or 422) changes nothing, also on
  a running group. Then the change of each camera is applied on its own. A camera whose change fails
  becomes `failed`, and the other cameras are not touched. Example: three cameras run at 30 fps, a
  request asks one of them for 60; the one-rate rule refuses the request, and all three keep running
  at 30.
- U11: skellycam does not offer modes below 30 fps. They are left out of `supported_modes` and are not
  selectable in the 3c list. A request for one is refused. A mode at 29.97 fps counts as 30 (the floor
  is 29.97). A camera with no mode at 30 fps or more at the requested size fails with the reason "no
  mode at 30 fps or more". The D49 test of each declared rate at 720p shrinks to 30 on each camera and
  60 on the C922 and the Kiyo Pro. The warm-up stays 90 frames and the ready limit 15 s.
- U12: On a hang during a recording, try to finish the files of that camera for at most 5 s, then end
  the process hard. This is an interim rule. It goes with the recorder of phase 5, whose files survive
  a hard stop.
- U13: The interim preview relay sends the newest frame of each camera on its own, without waiting for
  equal frame numbers. Preview frames of different cameras can then be one gate round apart. Phase 4
  replaces this relay.
- U14: A live control change that fails without a hang leaves the camera running in its earlier
  state. The failed change is reported for that camera in the response. The camera does not become
  `failed`. A change that needs a reopen and fails still gives a `failed` camera (U10).
- U15: A group with a camera in a 29.97 fps mode and a camera in a 30 fps mode is allowed, and
  skellycam warns the user. The warning says that the 30 fps cameras skip one frame about every
  1 / (30 - 29.97) s (1001/30 s = 33.4 s for the exact rates), that each skipped frame is counted and
  is missing from the recording, and that the group runs at 29.97 fps. The interval comes from the
  exact mode rates. The warning goes into the `warnings` list of the apply response and into the log.
  The one-rate rule treats 29.97 and 30 as one rate class; each other difference is refused.

**Answers of the user to the review of the failing tests of step 3a, 2026-11-19 ([ADR-HB4Z](../decisions/entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md))**

- U16: The control read of one time per second and each live control change run on a separate
  thread of the camera process, not on the loop thread. A hung control call can never hold the gate.
  The thread sleeps between reads. On a hang the camera still dies as specified (report, U12 during a
  recording, hard end), and the other cameras lose no frames.
- U17: (a) The warm-up counts the frames that the camera delivers, from the first frame after the
  controls are read back. (b) `measured_fps` in the status is not rounded. (c) The main process keeps
  the last detection result, by `camera_id`, for the whole-request check. (d) T-RING-46 and its
  expected-failure mark change with the product code of step 3a, because the warning pipe moves to
  the main process.
- U18: The whole package `media_foundation/` is Windows only and can load `comtypes` anywhere. Its
  tests (T-CAP-22, 23, 24, 48) run on Windows only and are skipped on other systems.
- U19: The user accepts [ADR-HP7D](../decisions/entries/HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md),
  as corrected by U18.
- U20: CI on three systems: the capture workflow gets an Apple Silicon macOS job (macOS 15 or later)
  with the fake-source tests, the OpenCV-source tests and the portable ring tests. The arm64 Linux job
  stays.
- U21: Each Windows hardware test that does not depend on Media Foundation gets a counterpart with
  the OpenCV source on Linux and macOS (T-CAP-92 to T-CAP-98). They use the same switches, select by
  platform, and run in phase 0 on the word of the user.
- U22: A parity table of the tests on Windows, Linux and macOS (16.7). It is the to-do list of phase 7.
- U23: More fake-source tests for the OpenCV source (T-CAP-99 to T-CAP-104): the floor, the one-rate
  rule on requested rates and the warning for different real rates, the start-up rate check with and
  without a reported rate, a camera that fails at open, a camera that stops during a recording, and
  the auto-exposure warning on Linux. They run on the three CI systems.

**Decisions of the user after the review of the 3a code, 2026-11-19 and 2026-11-20 ([ADR-PDD3](../decisions/entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md))**

- W1: Items 65 to 78 of section 18 are accepted as written, except as W2 and W3 change them.
- W2: The first part of item 76 is rejected. When OpenCV reports no frame rate, the start-up check
  still measures the rate over the warm-up frames 6 to 90 and compares it with the requested rate of
  the config (30 for "auto"), with the 3 % limit. A slower camera fails at start-up, as on Windows.
  The status reports the measured rate.
- W3: Item 75: the warning of different real rates on OpenCV is a log record at WARNING and an item
  of the `warnings` list of the apply response, with the kind `mixed_rate`.
- W4: Step 3a adds `replaced_count` to the status of each camera, counted from the first frame that
  the camera takes in the gate.
- W5: Detection shows a virtual camera with `virtual: true`. A request that names one is refused
  with 422. The support of virtual cameras is a later task.
- W6: The device `path` is stored and shown as the OS gives it. Only the input of the `camera_id`
  hash is in lower case.
- W7: `stdout` and `stderr` are reconfigured to UTF-8 at the entry point of skellycam and in each
  worker, before the logging is configured.
- W8: The phase 2 camera loop is dead code. It is deleted, with the code that only it uses, together
  with T-RING-31, which tests only that loop. T-CAP-49 covers the same rule on the shared loop.
