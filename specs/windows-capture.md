# Phase 3 capture specification: Windows native capture (3a, 3b, 3c)

Status: proposed by an agent on 2026-11-19. It waits for the review of the user
([ADR-4CQC](../decisions/entries/4CQC-phase-3-windows-capture-spec-and-test-list.md)). No product
code and no test code is written before the user accepts it. The decisions D1 to D49 are accepted
by the user ([ADR-EN7A](../decisions/entries/EN7A-phase-3-windows-capture-decisions.md)). Section
20 gives each one in full. The user gave thirteen answers on 2026-11-19, to the questions of the two
drafts and to one agent choice
([ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)).

## 0. How to read this spec

Marks:

- **[Dn]**: decision n of the user, 2026-11-19 (section 20,
  [ADR-EN7A](../decisions/entries/EN7A-phase-3-windows-capture-decisions.md)).
- **[Un]**: answer n of the user to a question of a draft or to an agent choice, 2026-11-19 (section 20,
  [ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)).
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
- The recorder of phase 5. The old recorder (decoded image in, H.264 out) stays [D9].
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

1. All fake-source tests pass on the Windows development machine, the Windows CI runner and the plain
   Linux runner. The tests of the kind "local" (T-CAP-49, T-CAP-50) pass on the Windows development
   machine; they do not run in CI.
2. The hardware tests pass on the C922, the C930e and the Kiyo Pro, and the rate check refuses the
   generic camera. T-CAP-54 and T-CAP-55 (D49) are part of this item. They record results and have
   no pass value (16.3).
3. A three-camera recording, OpenCV loop against native loop, gives equal frame counts across
   cameras, a group rate within 1 % of 30 fps, and no lost camera frame that the replaced-frame count
   does not explain. Both counts start at the first frame that the camera takes in the gate (5.2).
   Section 16.4 gives the run [agent 40].
4. T-RING-31 (idle CPU under 2 % of one core) and T-RING-46 pass on Windows.

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
4. T-RING-47 passes, and T-RING-31 still passes on Windows.

### 2.3 Step 3c [agent 37]

Step 3c is done when:

1. All fake-source tests of 3a, 3b and 3c pass on the three platforms of 2.1 item 1.
2. The 3c hardware test of D49 (T-CAP-77) runs on the C922, the C930e and the Kiyo Pro, and its
   results are recorded (16.3). Gain and focus set and read back on each camera that has them. White
   balance and power line frequency are read and written to the recording info.
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
| `skellycam/core/camera/capture/camera_loop.py` | The shared loop. It replaces `opencv/opencv_camera_loop.py`. |
| `skellycam/core/camera/capture/rate_check.py` | The rate formula, the limits, the early decision (section 10). Pure functions. |
| `skellycam/core/camera/capture/modes.py` | `supported_modes`, the mode choice, the auto rate, the rate tolerance, the group rate rule (section 7). Pure functions. |
| `skellycam/core/camera/capture/media_foundation/` | `com.py` (interface declarations), `bounded.py`, `errors.py` (HRESULT to reason, pure), `detect.py`, `source.py` (`MediaFoundationSource`). Windows only. |
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
| Waiting place | One place per source, at most one frame. A new frame replaces a waiting frame, and the replaced frame counts in `replaced_count` [D26]. When the replaced frame carried a discontinuity, the frame that replaces it carries it too. Thus the next taken frame has the flag [D34] [agent 46]. A source error puts an error marker in the place. The marker wakes the loop at once, and `read_frame` raises `CaptureFailure` [agent 50]. The source uses the rules of `WaitingPlace` of the ring package (`skellycam/core/ipc/frame_ring/decode.py`), with these two additions [agent 4]. The put never waits longer than the time to take the lock [ring 8.3]. |
| Camera loop thread | Waits only in `read_frame`, on the condition of the waiting place, with a timeout [ring 8.10]. It never polls in a loop without a block or a sleep of at least 1 ms. |
| Bounded-call workers | One short-lived thread per bounded call [proto bounded.py]. Each joins the multithreaded apartment (MTA) first [agent 43]. |
| Decode thread (BGR ring) | As [ring 8.2, 8.3]. |

No thread of the camera process spins [ring 8.10]. T-RING-31 applies to the shared loop [D48].

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
6. **Recorder.** If the frame is recorded, decode it (5.5) and give it to the old recorder [ring 5.3,
   D9].
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
- `sample_ns` goes into the slot header, and nothing uses it yet [D28]. Phase 5 decides.
- The old frame record gets `arrival_ns` in both `pre_frame_grab_ns` and `post_frame_grab_ns`. Thus
  the midpoint that `create_camera_csvs.py` computes is the arrival time [agent 7].
- The Media Foundation and fake sources do not stamp `pre_frame_retrieve_ns` and
  `post_frame_retrieve_ns`.
- A timestamp column is written only when that stage was stamped [D41]. The rule is that of upstream
  `sfn26` (`stamped_stage_columns` in `create_camera_csvs.py`): a lifecycle column is stamped when
  any camera stamped it on any frame; a duration column is written only when each of its inputs is
  stamped.
- The recorder refuses a frame whose camera ID does not match its config [D41].
- The frame rate given to the old recorder is the mode rate, not the median of the frame intervals
  [agent 9].

### 5.5 Interim decode for the old recorder and the BGR ring [D9]

- The old recorder takes a decoded image until phase 5 [D9]. The camera process decodes each JPEG
  one time with `cv2.imdecode`, into the image of the old frame record.
- When the camera has a BGR ring, the same decoded image goes to the BGR ring, as a new copy through
  the waiting place (`DecodeInput` with `source="BGR"`) [ring 8.8]. There is no second decode [D9].
- The loop decodes a frame only when the frame is recorded or the camera has a BGR ring
  [agent 8]. The decode runs on the loop thread [agent 61]. Thus, while a recording runs, it delays capture by
  the decode time [D9]. Section 17.2 lists this difference from [ring 8.2 to 8.4].
- A frame with an error flag never reaches the decoder [ring 4]. The old recorder then gets the last
  good image again, and the camera process logs the count of such frames at the stop of the
  recording [U5]. This is an interim rule of phase 3. It must change back in phase 5 [U5].
- Cost: 2.60 ms at 720p, 5.42 ms at 1080p, one thread
  [M `research/frame_ring_buffer/decode_bench/FINDINGS.md`]. Phase 5 removes this decode [D9].

### 5.6 libjpeg warnings on Windows [D42]

- The main process gives each camera process a pipe as its error output before OpenCV loads [D42].
  This applies the fix of [ADR-E817](../decisions/entries/E817-choices-of-the-2b-code.md) item 7 and [ring 8.9] on Windows.
- The main process holds the read end. One thread per camera process reads the pipe and logs each
  different line one time per minute at most, with a count [ring 8.9] [agent 42]. In [ring 8.9] the
  camera process reads the pipe. Section 17.2 lists this difference.
- How a spawned process gets the pipe as its standard error handle is [NV]. `multiprocessing` does
  not pass standard handles on Windows by default. The code must show a method, and T-RING-46 must
  pass on Windows [D48].

### 5.7 A recording with a dead camera (interim rule of phase 3) [U4]

- The timing file of each camera ends at its own last frame [U4].
- The multi-frame timing rows after the last frame of a dead camera continue with the cameras that
  are still alive [U4].
- The recording info names the dead camera and its last frame (11.6) [D38, U4].
- `last_frame_number` is the frame number of the last recorded frame of that camera in the old frame
  record. This is the gate count of 5.3, the counter of the timing files [agent 52].
- This is an interim rule of phase 3. It must change back when the recorder of phase 5 comes [U4].
- The finaliser (`recorders/recording_finalizer.py`) and the timing files need equal frame counts
  today. Phase 3 changes them for this rule.

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
- On a hang during a recording, the camera process reports, then tries to finish the recording files
  of that camera for at most 5 s. Then it ends hard [U12]. The hung call is on a worker thread, so the
  loop thread can still close the files.
- This is an interim rule of phase 3. The recorder of phase 5 writes files that survive a hard stop.
  Then the rule goes [U12].
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

### 7.2 `camera_id` [D11]

- `camera_id` uses the same hash function as today (`CameraDeviceInfo.camera_id`: SHA-256, the first 2
  bytes as 4 hex digits) of the Media Foundation symbolic link [D11].
- The input is the symbolic link in lower case [agent 13]. The prototype matches links without case
  [proto mf.py `open_session`].
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
    that the nearest mode is below the floor; else at the open, stage `set mode`. The reason is "no
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
  It is not a refusal, and no camera is closed [agent 56]. Linux and macOS behaviour is not
  tested until phase 0 [D46].
- A group with one camera in a 29.97 fps mode and one in a 30 fps mode is open (section 19, Q-f).
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
| `failed` | The start failed: cannot open, in use, no mode, not ready in 15 s, rate check failed [D23]. The camera is closed. | no | no |
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
| `ready`, `too_slow`, `checking` | a live control change fails without a hang | open: section 19, Q-e |
| `failed`, `dead` | "apply again", with the same config or a changed config (8.3) | `starting` (only this camera) [D23] |
| `ready` | recording starts | `recording` |
| `recording` | recording stops | `ready` |
| `recording` | camera slows down | `recording`, with a warning [D39] |
| `waiting`, `checking`, `too_slow`, `ready`, `recording` | device removed; 2 s without a frame | `dead` [D38] |
| `waiting`, `checking`, `too_slow`, `ready`, `recording` | a bounded call times out (a hang) | `dead`, stage `streaming`; the process ends hard (6.6) [agent 60] |
| `starting`, `waiting`, `failed`, `checking`, `too_slow`, `ready`, `dead` | unselect | removed from the group; an open camera is closed [D23] [agent 24] |

skellycam never moves a camera from `failed` or `dead` to `starting` by itself [D23]. A failed camera
records its diagnostics, is marked, and is never revived (Kiyo Pro wedge rule) [D23].

The camera process of a camera that fails at start reports the failure, closes the camera and ends.
The process of a dead camera reports, finishes its recording files [D38], closes the source with the
bounded steps of 6.9 and ends. Thus a dead process lives until its files are finished and its close
steps end. After a hang during a recording, the file finish has a limit of 5 s (U12), and then the
process ends hard. "Apply again" starts a new camera process [agent 22].

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
  group closes the camera and removes it from the gate and from the record check [agent 24].
- The main process first checks a request as a whole: the config values, the one-rate rule (7.5) and
  the states of this table. A refused request gets 422 or 409 by the rule above. It changes
  nothing, also on a running group [U10].
- After the check, the main process applies the change of each camera on its own. A camera whose
  reopen-type change fails (a resolution or rate change, "apply again") becomes `failed`, and the
  other cameras are not touched [U10].
- A live control change that fails without a hang is open (section 19, Q-e).

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
- `measured_fps` is the result of the last rate check, or null.
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
- The OpenCV source runs the check only when OpenCV reports a rate above 0 [D46].

### 10.2 After a live control change [D32]

- Skip 15 frames, then measure over the next 60 frames with the formula and the 3 % limit of 10.1
  [D32].
- Early decision: the camera is too slow as soon as the 60 frames can no longer arrive in time
  [D32]. With `t_a` the arrival of the first frame of the window and `r` the mode rate, that is when
  `now - t_a > 59 / (0.97 x r)` and frame `s_a + 59` has not arrived.
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
- `RECOMMEND` runs in the shared loop through the capture interface: the same exposure range (-12 to
  -4), 10 frames to settle at each value, and the mean of the decoded image against 127.5, as
  `recommend_camera_exposure_setting.py` does today. It runs at step 5 of 9.1. Its frames are not
  warm-up frames [agent 29]. As today (`_apply_exposure` in
  `opencv_apply_config.py`), the stored config then holds `exposure_mode: MANUAL` and the value that
  the search found [agent 29].

### 11.2 Live changes [D31]

- A change of exposure, gain or focus is applied live, without a reopen [D31]. Then the check of
  10.2 runs.
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
   "warnings": [{"camera_id": "a1b2", "control": "exposure",
                 "text": "Camera a1b2: exposure is in auto mode at the start of the recording"}]}
  ```

- The status (8.4) shows the same items in `warnings`, and `auto: true` for the control [agent 33].
- The camera process also logs the text as a warning.
- The recording info records that the control was in auto for this take (11.6) [D37].
- Today the endpoint returns `true`. The new response shape changes this for each consumer
  [agent 33].

### 11.4 Read-back and current values [D20, D30]

- Each control is read back after it is set [D20].
- While a camera is open, the status reports the current value of exposure, gain and focus, also
  when the control is in auto. Thus a consumer can show the value and set manual with exactly that
  value [D30].
- From 3a, the status reports exposure, gain and focus, read only. The loop reads them one time per
  second with `set_controls({})` [D30] [agent 31]. Gain and focus are set through the config from 3c
  [D43].
- Whether a camera in auto mode reports its true current value is not known (section 17.3).

### 11.5 Gain, focus, white balance, power line frequency (3c) [D43, D44]

- `CameraConfig` gets `gain: int | None = None`, `gain_auto: bool = False`, `focus: int | None =
  None` and `focus_auto: bool = False` [D43] [agent 30]. `None` means that skellycam does not set the
  value.
- A control that a camera lacks is reported as absent (`present: false`). A request to set it gets HTTP
  422 with a clear message: `Camera {camera_id} has no {control} control` [D43] [agent 48].
- White balance is read only. Its value and auto flag go to the recording info [D43].
- The power line frequency control is never set in phase 3. Step 3c reads it and writes it to the
  recording info [D44].

### 11.6 Recording info in phase 3 [agent 32]

Until phase 5 brings the capture info, the camera data of D37, D38, D43, D44 and the range of 13.3 go
into the existing recording info JSON (`RecordingInfo.save_to_file`):

```json
"capture": {
  "a1b2": {
    "source": "media_foundation",
    "mode": {"width": 1280, "height": 720, "fps_num": 30, "fps_den": 1, "format": "MJPG"},
    "controls_at_start": {"exposure": {"auto": false, "value": -7}},
    "auto_controls_at_start": [],
    "white_balance": {"auto": true, "value": 4600},
    "power_line_frequency": 2,
    "input_range": null
  }
},
"dead_cameras": [
  {"camera_id": "c3d4", "last_frame_number": 1234, "stage": "streaming", "reason": "device removed"}
]
```

`white_balance` and `power_line_frequency` are present from 3c. `input_range` is set from 3b.

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
- The old recorder takes BGR in phase 3 (D9). In an uncompressed mode, the loop converts each
  recorded frame to BGR on the path of the recorder, also with Quick Sync, until phase 5 [agent 36].
  The loop converts a frame to BGR one time. The old recorder and the BGR ring share that image: the
  ring gets its copy as in [ring 8.7]. A frame is never converted two times [agent 36].

### 13.3 Range rule

- The camera config gets `input_range: "auto" | "limited" | "full"`, default `auto`
  [notes: Input range] [agent 36 for the field name].
- `auto`: during the 90 discarded warm-up frames, count the Y values outside 16 to 235. If more than
  1 % are outside, the camera is full range. Else, the flag of the OS decides (limited if not set)
  [notes: Input range] [D21].
- The decision is made one time, before the first recorded frame, and never changes in a session. The
  range goes into the recording info (11.6) [notes: Input range].

## 14. The OpenCV source

### 14.1 Linux and macOS [D46]

- The OpenCV source stays on Linux and macOS, with the JPEG re-encode of [ring 2.3, 8.8] [D6].
- The start-up rules apply to it: warm-up (9.2), the ready limit (9.3), the failed-camera flag
  (section 8) and one rate per group (7.5) [D46].
- The rate check runs only when OpenCV reports a rate above 0 for the camera [D46]. The reported rate
  is the reference.
- The floor of U11: a request below the floor is refused in the whole-request check, as on each
  source. When OpenCV reports a real rate above 0 and below 29.97 after the open, the camera fails,
  stage `set mode`, reason "no mode at 30 fps or more". When OpenCV reports no rate (0 or less), the
  floor is not checked (D46) [agent 59].
- The forced auto exposure on Linux (`opencv_apply_config.py`) stays. With D37, each Linux recording
  then gives the auto warning one time for each camera, until phase 7 (17.3).
- Linux and macOS behaviour is not tested on hardware until phase 0 [D46]. The fake-source tests and
  the tests with the OpenCV fake (`FakeCapture` of `skellycam/tests/frame_ring/ring_session.py`) run on
  the Linux CI runner.

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
  `skellycam/api/**`, `skellycam/tests/**`, `specs/windows-capture.md`, `pyproject.toml`, `uv.lock` or
  `.github/workflows/capture.yml`; and by hand [D47] [agent 39].
- Job `capture-windows` on the runner label `windows-2025` [agent 39]: run the fake-source tests
  (`uv run pytest skellycam/tests/capture -m "not camera_hardware and not capture_local"`), and load the Media Foundation
  module (T-CAP-46) [D47].
- Job `capture-linux` on the runner label `ubuntu-24.04` [agent 39]: install PortAudio as the arm64
  job does, then run the same fake-source tests [D47].
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
| T-CAP-05 | 3a | fake | Three fake cameras at 30 fps in one group for 10 s; one delivers late by 10 ms per frame. | Equal ring frame counts; for each camera, the sum of the gaps of `source_frame_number` between taken frames, from the first frame taken in the gate, equals the increase of `replaced_count` from that frame; one log line per camera at stop with that count. |
| T-CAP-06 | 3a | fake | Run, change the resolution, run again. | Ring `frame_number` is 0, 1, 2, ... in each ring; `source_frame_number` is the source count; the gate count continues across the change. |
| T-CAP-07 | 3a | fake | Fake with scripted arrival and sample times; record 30 frames. | Slot `arrival_ns` and `sample_ns` equal the source values; the CSV time of each recorded frame is its `arrival_ns`; a source with no sample time writes `NO_SAMPLE_NS`. |
| T-CAP-08 | 3a | fake | Spy on the recorder, the JPEG ring write and the BGR hand-over. | For each frame: recorder, then JPEG ring, then BGR [ring 5.3]; a ring write that raises leaves the recorder and the next frame unaffected. |
| T-CAP-09 | 3a | fake | MJPG fake, with and without recording, with and without a BGR ring; count `cv2.imdecode` calls. | One decode per recorded frame or per frame with a BGR ring, else none; the BGR ring frame equals the decoded image. |
| T-CAP-10 | 3a | fake | The fake delivers a cut-off JPEG during a recording. | The slot is flagged `NO_SOI_EOI`; the decoder call count is 0 for it; the recorder gets the previous image; the count is logged at stop. |
| T-CAP-11 | 3a | fake | (1) The fake drops a frame on the camera side: the next delivered sample has the discontinuity attribute. (2) A sample with the attribute is replaced in the waiting place before the loop takes it. | In both cases the next taken frame has `DISCONTINUITY`; in case 1, `source_frame_number` has no gap; no warning is logged. |
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
| T-CAP-22 | 3a | fake | Map each HRESULT of 6.7 (pure function, no COM). | In-use codes give "in use by another program"; device-removed codes give "device removed"; other codes give their name. |
| T-CAP-23 | 3a | fake | A detection result with two links that give the same `camera_id`. | Refused with an error that names both links. |
| T-CAP-24 | 3a | fake | Hash known Media Foundation links in mixed case. | `camera_id` equals the SHA-256 rule of today on the lower-case link. |
| T-CAP-25 | 3a | fake | Build `supported_modes` from native types with MJPG, YUY2, a synthesized NV12, H.264, duplicates, 30000/1001, 10000000/333333, 60/1, 24/1 and 15/2. | The exact JSON of the 7.3 rules: MJPG only, order, 29.97, 30.0 and 60.0; no 24 and no 7.5; no duplicates; a size with only low rates is left out. |
| T-CAP-26 | 3a | fake | Choose modes: request 30 when the camera has 29.97 and 30; request 60 at a size that has only 30; a size it lacks; a size that only H.264 has. | 30; no mode for the other three, and each failure lists the modes; H.264 is never chosen or opened. |
| T-CAP-27 | 3a | fake | Requests of -1 and 0: with 30 at the size; with 60 but no 30; with only 15 and 24. | 30; 60; failed with "no mode at 30 fps or more". |
| T-CAP-28 | 3a | fake | Open with -1; compare 30.0 and 30.00003, 30 and 29.97. | The config stores the mode rate; the first pair is equal, the second is not. |
| T-CAP-29 | 3a | fake | Group of two with mode rates 30 and 60; group of two with -1 that both give 30. | The first apply fails and opens no camera; the second opens both. |
| T-CAP-30 | 3a | fake | Change the exposure, then the resolution, of one camera of two. | Exposure: no reopen, same ring name, state `checking`; resolution: only that camera reopens, new rings, warm-up and rate check again; the other camera keeps its preview. |
| T-CAP-31 | 3a | fake | After a live change, the fake goes to 20 fps; after a later change, to 30 fps. | State `checking`, then `too_slow` at t_a + 59 / (0.97 x 30) s = t_a + 2.0275 s, within ±25 ms, where t_a is the arrival of the first frame of the window; this is before the window could end at 20 fps (t_a + 2.95 s); preview continues; record start returns 409; the next change at 30 fps gives `ready`. |
| T-CAP-32 | 3a | fake | Start a recording while a camera is `checking`. | 409, the detail names the camera and `checking`. |
| T-CAP-33 | 3a | fake | Apply a change during a recording. | 409; the camera config and the ring name do not change. |
| T-CAP-34 | 3a | fake | Start a recording with exposure in `AUTO`. | The recording starts; the response `warnings` holds the camera, `exposure` and the text of 11.3; the status shows the same item; the log has the text; the recording info lists `exposure` in `auto_controls_at_start`. |
| T-CAP-35 | 3a | fake | Three fakes record; one gives device removed at frame 300. | That camera is `dead` at once; its files are finished; its timing file ends at its last frame; the multi-frame rows after it hold the two live cameras; the two keep recording to the stop; `dead_cameras` holds its ID and `last_frame_number`. |
| T-CAP-36 | 3a | fake | One fake stops delivering at frame 100. | `dead` between 2.0 and 2.25 s after its last arrival, not before. |
| T-CAP-37 | 3a | fake | During a recording, one fake goes to 27 fps for 5 s, then back to 30. | One warning with the camera and the rate; the recording continues; a later slow period gives one more warning. |
| T-CAP-38 | 3a | fake | Two failures of one camera, then a group shutdown. | The object has `camera_id`, `stage`, `reason`; the text is `Camera {id} failed during {stage}: {reason}`; the first failure stays; it is in the queue before the flag changes. |
| T-CAP-39 | 3a | fake | Record with the fake source and with the OpenCV fake; give the recorder a frame with a wrong camera ID. | Native CSV has no retrieve columns; OpenCV CSV has them; the wrong frame is refused with an error. |
| T-CAP-40 | 3a | fake | A fake source in a real camera process hangs in `open` past the limit; a second camera streams. | The failure arrives with stage `open`; the process exits within the limit plus 2 s; the main process cleans up only that camera; the second camera has no gap above 100 ms. |
| T-CAP-41 | 3a | fake | `MANUAL -7`, `AUTO`, `RECOMMEND` with a brightness model in the fake. | The fake gets the values in log2 seconds; `RECOMMEND` ends in `MANUAL` with the value nearest to 127.5. |
| T-CAP-42 | 3a | fake | Exposure in `AUTO`; the fake changes its exposure from -6 to -5, its gain from 0 to 4 and its focus from 30 to 40, with no set through the config. | Within 2 s, the status shows `exposure` with `auto: true` and `value: -5`, and the new gain and focus values. |
| T-CAP-43 | 3a | fake | On Windows: no setting, `opencv`, `media_foundation`, a wrong value. Runs only before the last commit of phase 3. | OpenCV, OpenCV, Media Foundation, an error that names the allowed values. |
| T-CAP-44 | 3a | fake | The OpenCV fake under the shared loop, with a reported rate of 30 and of 0. | Warm-up in both; rate check only with 30; the ring gets a q90 JPEG with no burned-in stamp (it decodes to the fake image); the BGR ring gets the OpenCV image. |
| T-CAP-45 | 3a | CI | Read `pyproject.toml` and `uv.lock`. | `comtypes==1.5.0` with the marker `sys_platform == "win32"`; locked at 1.5.0. |
| T-CAP-46 | 3a | CI | On the Windows runner: import the Media Foundation module; if `mfplat.dll` loads, call `MFStartup`, enumerate, `MFShutdown`. | The import passes; the interface declarations exist; an enumeration returns a list. |
| T-CAP-47 | 3a | fake | Search the package. | No compiled extension of its own and no `_skellycam_rust` import. |
| T-CAP-48 | 3a | fake | Detection with a fake enumeration that hangs for one device. | The detection child ends; the call returns within the limit plus 2 s with an error; the main process keeps running. |
| T-CAP-49 | 3a | local | Marker `capture_local`. Run T-RING-31 with the shared loop on the Windows development machine. | Process CPU under 2 % of one core [D48]. |
| T-CAP-50 | 3a | local | Marker `capture_local`. Run T-RING-46 on the Windows development machine. | It passes [D42, D48]. |
| T-CAP-51 | 3a | hardware | Detect with four cameras connected; then detect again while two of them stream. | Four cameras with new IDs and the `supported_modes` of 7.3; the streaming cameras show no arrival gap above 100 ms. |
| T-CAP-52 | 3a | hardware | Open the C922, the C930e and the Kiyo Pro at 1280x720 MJPG 30 through Media Foundation, one at a time. | Each reaches `ready`; for 300 frames the ring payload is byte-equal to the bytes that the callback copied; the rate check passes. |
| T-CAP-53 | 3a | hardware | Open the generic camera at 1280x720 MJPG 30. | `failed`, stage `rate check`, the reason of 10.4 with a measured rate near 25.76 [D24]. |
| T-CAP-54 | 3a | hardware | Each camera at each offered MJPG rate at 1280x720: 30 on each camera, 60 on the C922 and the Kiyo Pro [D49, U11]. | For each rate: the measured rate and the check result are recorded; a camera that fails gives the reason of 10.4. |
| T-CAP-55 | 3a | hardware | Each camera opened in a dark room with auto exposure [D49]. | For each camera: state, measured rate and reason are recorded; no traceback. |
| T-CAP-56 | 3a | hardware | Another program holds the C930e; apply a group with it and the C922. | The C930e is `failed` with "in use by another program"; the C922 is `ready`. |
| T-CAP-57 | 3a | hardware | Exposure steps -7, -6, -5, -4 on each camera while open. | Each change gives `checking`, then `ready` or `too_slow` as table 10.5 predicts; the Kiyo Pro at -6 is recorded. |
| T-CAP-58 | 3a | hardware | Record with the C922 and the C930e; the user unplugs the C922 at 20 s. | The C922 is `dead` at once; the C930e records to the stop; the recording info names the C922 and its last frame. |
| T-CAP-59 | 3a | hardware | Compare `sample_ns` and `arrival_ns` for 300 frames per camera. | The difference is recorded per camera; the source applies the `NO_SAMPLE_NS` rule of 4.2 as the recorded values require. |
| T-CAP-60 | 3a | hardware | The comparison run of 16.4 [D48]. | 16.4. |
| T-CAP-61 | 3b | fake | Request YUY2 and NV12 where the fake lists native and synthesized types. | Native types are chosen; a synthesized NV12 is never chosen; a missing format fails at `set mode`. |
| T-CAP-62 | 3b | fake | YUY2 and NV12 fakes with `cv2.imencode`. | The ring gets a q90 JPEG with the chroma of the source (4:2:2 from YUY2, 4:2:0 from NV12). |
| T-CAP-63 | 3b | fake | Sessions with and without an uncompressed camera; count the Quick Sync checks. | One check per app run, only with an uncompressed camera; each camera process gets the result. |
| T-CAP-64 | 3b | fake | The encoder fails at frame 200 of a take. | Later frames use `cv2.imencode`; held frames are encoded from the raw frames; no frame is lost; the first frame after the event has `DISCONTINUITY`; the event is counted and logged. |
| T-CAP-65 | 3b | fake | Warm-up frames with 0.5 % and 2 % of Y values outside 16 to 235, with the OS flag "limited". | 0.5 %: limited; 2 %: full; the decision does not change later in the session; the recording info holds it. |
| T-CAP-66 | 3b | fake | A YUY2 frame that is 100 bytes short. | Not encoded; slot flagged `CAPTURE_ERROR`. |
| T-CAP-67 | 3b | fake | Record in YUY2 with Quick Sync on and the BGR ring off. | The old recorder gets a BGR image for each recorded frame. |
| T-CAP-68 | 3b | hardware | YUY2 640x480 at 30 on the C922 and the C930e; YUY2 1280x720 at 30 on the Kiyo Pro; NV12 1280x720 at 30 on the generic camera. | Each reaches `ready` or fails with a reason; the range decision agrees with the yuy2_range evidence; Quick Sync is used on the development machine. |
| T-CAP-69 | 3b | hardware | The 3b recording of 2.2 item 3. | 2.2 item 3. |
| T-CAP-70 | 3b | fake | A group with one fake in YUY2 at a mode rate of 30 and one in MJPG at 60. | The apply fails and opens no camera (D18 with D19). |
| T-CAP-71 | 3c | fake | Build `capture_modes` from the native types of T-CAP-25. | The JSON of 7.4: MJPG and YUY2 both listed, MJPG first; H.264 and RAW `selectable: false` with "never opened"; modes below 29.97 fps `selectable: false` with "below 30 fps"; synthesized NV12 left out. |
| T-CAP-72 | 3c | fake | Set gain and focus, manual and auto, live. | Each value is set and read back; no reopen; state `checking`. |
| T-CAP-73 | 3c | fake | A fake without focus; config with `focus: 40`. | Status `present: false`; the set returns the error text of 11.5. |
| T-CAP-74 | 3c | fake | Record with white balance and power line frequency values in the fake. | Both are in the recording info; the fake gets no set call for either. |
| T-CAP-75 | 3c | fake | Gain and focus in auto; the fake changes their values. | The status shows the new values with `auto: true`. |
| T-CAP-76 | 3c | fake | Comes in the last commit of phase 3 and runs only after it: import the OpenCV source on Windows; search for `SKELLYCAM_WINDOWS_CAPTURE`, `check_framerate_reset`, `draw_doubled_text`. | The import fails on Windows; no name is left outside history documents. |
| T-CAP-77 | 3c | hardware | With auto exposure and auto focus on, read the reported values; set manual with those values; compare the mean image before and after [D49]. | For each camera: whether the reported values are true, and the image difference, are recorded. |
| T-CAP-78 | 3c | hardware | Set and read back gain and focus; read white balance and power line frequency, on four cameras. | Each control that a camera has reads back the set value; absent ones show `present: false`; the read-only values are recorded. |
| T-CAP-79 | 3c | hardware | Detect the four cameras. | `capture_modes` agrees with the descriptor list of the prototype for each camera. |
| T-CAP-80 | 3a | fake | A fake whose first frame comes 6 s after the first `ReadSample`. | Failed, stage `first frame`, 5.0 to 5.25 s after the first `ReadSample`; the close runs with its bounded steps; the process does not end hard. |
| T-CAP-81 | 3a | fake | Two fakes, no recording; one stops delivering. | It is `dead` and treated as `failed` [U6]: a record start returns 409; an apply reopens only it. |
| T-CAP-82 | 3a | fake | Two fakes are `ready`; a control read of one hangs past its limit. | That camera reports stage `streaming` and its process ends hard; the main process cleans up only it; the other camera has no gap above 100 ms. |
| T-CAP-83 | 3a | fake | Each fake camera in its own group: (1) a request of 25; (2) a request of 30 for a camera whose detection data has only 15 and 24 at the size; (3) the same, but the detection data shows 30 and the open finds only 24; (4) a request of 29.97 where the camera has 29.97; (5) auto for a camera with 29.97 and 60 at the size. | (1) and (2) get 422 and change nothing; (3) fails, stage `set mode`, "no mode at 30 fps or more"; (4) opens at 29.97; (5) opens at 29.97 [U11]. |
| T-CAP-84 | 3a | fake | Three fakes run at 30 fps: (1) a request asks one for 60; (2) a request changes the size of two cameras, and the open of one fails in the fake. | (1) gets 422, and all three keep running at 30 with unchanged rings; (2) the failing camera is `failed`, the other has the new size, and the third is not touched [U10]. |
| T-CAP-85 | 3a | fake | During a recording, a bounded call of one fake hangs. Case 1: the recorder of that camera needs 1 s to close its file. Case 2: it needs 8 s. | The failure is reported; case 1: the file is finished, and the process ends hard within 1.5 s of the report; case 2: the process ends hard 5.0 to 5.5 s after the report; in both cases the other cameras keep recording [U12]. |
| T-CAP-86 | 3a | fake | Three fakes with preview; reopen one camera by a change of its resolution. Capture relay messages during the reopen. | Each message holds the newest frame of each camera that has one; the frames of the other two cameras keep advancing while the third is `starting`; the third comes back after `ready` [U13]. |
| T-CAP-87 | 3a | fake | Shared loop with the OpenCV fake on each OS: 60 frames, each 70 ms late (more than 2 x the period). | No reopen: the open count stays 1; each ring JPEG decodes to the fake image, with no stamp [U2]. |
| T-CAP-88 | 3a | hardware | With `SKELLYCAM_WINDOWS_CAPTURE=opencv` in the new loop, open the C922, the C930e and the Kiyo Pro. | Each opens the DirectShow device whose device instance part equals that of the Media Foundation link that detection named for its `camera_id`, and the friendly names agree [U1]. |
| T-CAP-89 | 3b | fake | A YUY2 request at 1280x720 for a fake with YUY2 only at 10 fps there; then at 640x480 where it has 30. | The first gets 422 with "no mode at 30 fps or more"; the second opens [U11]. |

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
| D18 | T-CAP-29, T-CAP-70, T-CAP-84 |
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
| D31 | T-CAP-30, T-CAP-72 |
| D32 | T-CAP-31, T-CAP-57 |
| D33 | T-CAP-32 |
| D34 | T-CAP-11 |
| D35 | T-CAP-41 |
| D36 | T-CAP-33 |
| D37 | T-CAP-34 |
| D38 | T-CAP-35, T-CAP-36, T-CAP-58, T-CAP-81, T-CAP-82 |
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

### 16.6 Counts

| Step | fake | hardware | CI | local | Total |
|---|---|---|---|---|---|
| 3a | 54 | 11 | 2 | 2 | 69 |
| 3b | 9 | 2 | 0 | 0 | 11 |
| 3c | 6 | 3 | 0 | 0 | 9 |
| All | 69 | 16 | 2 | 2 | 89 |

T-CAP-80 to T-CAP-89 are at the end of the table; their step is in the table.

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
5. [ring 8.2 to 8.4] put each decode on the decode thread. By D9, the decode of a recorded MJPG frame
   moves to the loop thread (5.5). While a recording runs, capture is then delayed by the decode.
6. [ring 8.9] reads the libjpeg pipe in the camera process. On Windows, D42 puts the read end in the
   main process (5.6).
7. [ring 2.3] fills the relay at the newest frame number that all cameras have. U13 sends the newest
   frame of each camera on its own (5.8).

Other open points:

8. The child monitor of the worker registry treats an unexpected exit as a crash of the backend today
   (comment in `opencv_camera_worker_method.py`). Section 6.6 needs it to treat a reported failure as
   a camera failure.
9. How a spawned camera process gets a pipe as its standard error handle on Windows (5.6) [NV].
10. `RECOMMEND` searches exposures from -12 to -4. At -4 the Logitech cameras give 16 fps (10.5), so a
    recommended value can fail the rate check after the open. The search range is today's.
11. The in-use codes at stages other than the first frame are [NV]. Only `0xC00D3704` at the first
    frame is measured.
12. Phase 5 must remove the three interim rules of phase 3: 5.5 (the last good image for a flagged
    frame, U5), 5.7 (a recording with a dead camera, U4) and 6.6 (finish the files for at most 5 s
    before the hard end, U12).

### 17.3 Known weak points (from the decisions)

- The 3 % limit rests on about 2,000 opens of four cameras on one machine.
- The Kiyo Pro slows down at exposure -6 (28.7 fps) and longer, so it fails the check at settings
  that the Logitech cameras accept.
- Whether a camera in auto mode reports its true current value is unknown until the hardware test.
- The cause of the 25.76 fps of the generic camera is not known.
- Opens during control changes showed dips to 20 to 25 fps on the C930e and the Kiyo Pro in a few
  percent of opens in older data. The cause is not known.

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
33. The `warnings` list in the response of the record start and in the status, and its fixed text.
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

## 19. Questions for the user

Each question gives the options and a recommended answer. "Yes" accepts the recommendation.

**Q-e. A live control change that fails without a hang.** The set call of exposure, gain or focus
returns an error, or the read-back differs from the value that was set.

- Option 1: the camera keeps running in its earlier state. The response reports the change as failed
  for that camera. The camera does not become `failed`.
- Option 2: the camera becomes `failed` and is closed, as the wording of U10 says literally.
- Recommended: option 1.

**Q-f. A group with one camera in a 29.97 fps mode and one in a 30 fps mode.**

- Option 1: allowed, because 29.97 counts as 30 (U11). The rate check of each camera uses its own
  mode rate. Under lockstep the group runs at 29.97 fps, and about one frame of the 30 fps camera is
  replaced every 33 s.
- Option 2: refused by the one-rate rule (D18, with the tolerance of 0.0001 of D17).
- Recommended: option 1.

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

**Tests, CI, done**

- D47: A new GitHub Actions job runs the fake-source tests and loads the Media Foundation module on a
  Windows runner, and runs the fake-source tests on a plain Linux runner, on pushes to
  `dom/native-jpeg`, with pinned versions (pattern: `.github/workflows/ring-arm64.yml`). The arm64 job
  stays as it is (ring tests only).
- D48: Step 3a is done when: (1) all fake-source tests pass on the Windows development machine, the
  Windows CI runner and the plain Linux runner; (2) the hardware tests pass on the C922, C930e and
  Kiyo Pro, and the generic camera is refused by the rate check; (3) a three-camera recording, OpenCV
  loop against native loop, gives equal frame counts across cameras, a group rate within 1 % of 30
  fps, and no camera frame lost that the replaced-frame count does not explain; (4) T-RING-31 (idle
  CPU under 2 % of one core) and T-RING-46 pass on Windows. Matching lists for 3b and 3c.
- D49: Hardware tests that the spec must hold (they run on the user's word): each camera at each of
  its declared MJPG rates at 720p (does it deliver that rate?); each camera opened in a dark room with
  auto exposure; with auto exposure and auto focus on, does each camera report its true current
  value, and does the image stay the same after the switch to manual with that value?

**Answers of the user to the two drafts, 2026-11-19 ([ADR-QKX1](../decisions/entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md))**

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
