# Capture timings specification: the time of each slow step of the frame path, once per second

Status: accepted by the user on 2026-11-23 (Q587,
[ADR-8B85](../decisions/entries/8B85-acceptance-of-the-capture-timings-spec.md)), draft 2 with the six
edits of a second review. An agent wrote it. The user decided Q565 to Q571, Q576 to Q578, Q580 to
Q583 and Q586 on 2026-11-23
([ADR-MX8V](../decisions/entries/MX8V-decisions-of-the-user-on-capture-timings.md)). Section 14 gives
each one. The user accepted the choices of the agent as a set (Q587); section 13 and
[ADR-8Z0Q](../decisions/entries/8Z0Q-choices-of-the-capture-timings-spec.md) list them. Steps 1 to 6
of section 11 are built; the user decided the open choices of that build in Q837 to Q840 ([ADR-GZS7](../decisions/entries/GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md)).
The tile part (step 8) comes with step 4b [U Q571, Q587].

## 0. How to read this spec

Marks:

- **[U Qnnn]**: decision Qnnn of the user, 2026-11-23 (section 14).
- **[U Q587 n]**: choice n of the agent, which the user accepted as a set in Q587 (section 13, and
  the same item number in ADR-8Z0Q).
- **[M source]**: measured; the source holds the result. **[NV]**: not verified.
- **[ring x.y]**, **[cap x.y]**, **[unix x.y]**, **[prv x.y]**, **[4b x.y]**, **[player x.y]**,
  **[rec x.y]**: section x.y of [`frame-ring.md`](frame-ring.md),
  [`windows-capture.md`](windows-capture.md), [`unix-capture.md`](unix-capture.md),
  [`preview.md`](preview.md), [`preview-4b.md`](preview-4b.md), [`player.md`](player.md),
  [`recorder.md`](recorder.md).

The file and line citations are for commit c6532a21d of `dom/integration`. The build checks each
line again after the merge of `dom/fix-lane-3`. Section 8 is the interface note for FreeMoCap. It
repeats what a FreeMoCap display needs, so that it can be read alone. This spec uses British
spelling.

## 1. Purpose, scope, non-goals, terms

### 1.1 Purpose

The request of the user (2026-11-23): "I want to be able to see capture timings in the realtime
pipeline UI in FreeMoCap, that is - any codec work - anything else you think might take more than
1ms to complete".

skellycam measures the time of each slow step of the path of a frame. It publishes one summary for
each camera once per second. FreeMoCap shows the summaries [U Q565].

### 1.2 Scope

| Part | In this spec |
|---|---|
| The switch `log_capture_times` (section 2) | yes |
| The fixed list of steps and their measurement (sections 3 and 5) | yes |
| The end-to-end delays (section 4) | yes |
| The summary shape, the Python call, the route and the websocket message (section 6) | yes |
| The decode and draw timing of the shared tile (`skellycam-ui/src/player/tile/`), built with step 4b (section 7) | yes [U Q586] |
| The interface note for the FreeMoCap session (section 8) | yes [U Q565, Q576] |
| The display in FreeMoCap | no. The freemocap session does it after FreeMoCap moves to the new skellycam [U Q577]. |

### 1.3 Non-goals

- One event for each frame to another process [U Q568].
- A display in skellycam-ui [U Q577].
- A measurement in the interim worker files `frame-decode.worker.ts` and
  `offscreen-renderer.worker.ts`. Step 4b deletes them [U Q586].
- A per-frame bar in the FreeMoCap timeline for a capture step [U Q576].
- The times of an open or a close. The diagnostics keys D-6 (`t_*_ms`) give them [unix 4.6.2].
- The control thread (`_ControlThread`, `camera_loop.py:979-1069`). It reads the controls once per
  second on its own thread. It is not on the path of a frame.
- The decode of the prefetch of the player [player 9.1]. The player is not live capture.
- The arrival intervals and the frame rate. `framerate_update` and certify give them (section 9).
- A new dependency, in Python or in skellycam-ui.

### 1.4 Terms

- **Step.** One named part of the path of a frame, with a fixed id (section 3).
- **Bracket.** The exact code between the two clock reads of a step. No time is in two samples
  [U Q587 6]. Two brackets can nest: `opencv_retrieve` is inside the `_read` calls of `camera_wait`, and
  `mkv_mux`, `csv_row` and `fsync` are inside `_finish` of `mkv_close`. Then the sample of the outer
  step is the time of its bracket minus the samples of the inner steps, and table 3.1 says so.
- **Work and wait** [U Q567] [U Q587 4]. The kind of a step comes from the job of the step:
  - A **wait** step has the job to wait for another part: the camera frame, the other cameras (the
    lockstep gate), space in the recorder queue, or the end of the recorder thread.
  - A **work** step has the job to do the work itself: a decode, an encode, a copy, a check, a
    write to a file or a socket, a draw. A disk call that blocks in the operating system is work. An
    awaited call whose job is the step itself is work (`preview_send`, `ui_jpeg_decode`).
  - The time of an awaited step can contain the time of other tasks of the same event loop or page.
    The summary does not take it out.
- **Cadence** [U Q587 4]. `frame`: the step runs at most one time for each frame. `second`: the step runs
  one time in each second. `event`: the step runs at an event (a take start, a take end, a trial of
  the exposure search).
- **Window.** The time between two summaries of one source, about 1 s [U Q568].
- **Summary.** For one camera (or one group) and one window: for each step, `n`, `p50_ms`,
  `p95_ms` and `max_ms` [U Q568]. One shape for each source [U Q569].
- **Delay.** A time from one point of the path of a frame to a later point, maybe in another
  process (section 4) [U Q570].
- **Writer instance.** One object that has its own thread or callback and writes step samples: a
  source (its callback thread), a `DecodeStage`, a `CameraTakeWriter`, a websocket connection.

## 2. The switch [U Q578, Q581, Q582]

The user refused "always on": "this must be toggle-able like all other metrics in skellytracker"
[U Q578]. The pattern of skellytracker and FreeMoCap:

- skellytracker: `start_pipeline(..., timing_sink=..., timing="on")` and the config field
  `instrumentation.timing_spans` (default: empty, so no span is on). The run fixes its spans at its
  start (repository `skellytracker`, `skellytracker/core/pipelines/run.py` and
  `skellytracker/core/pipelines/_runtime/executor.py`). Each span costs one set look-up when off.
- FreeMoCap: `RealtimePipelineConfig.log_pipeline_times: bool = False`. The pipeline reads it at its
  start. A change applies when the real-time processing starts again (repository `freemocap`,
  `freemocap/core/pipeline/realtime/realtime_pipeline_config.py`,
  `freemocap/core/pipeline/realtime/realtime_pipeline.py`).

The rules of skellycam:

1. **Name and default.** `log_capture_times: bool`, default `False`, as `log_pipeline_times` [U Q587 2].
2. **One switch for the whole app** [U Q581]. `CameraGroupManager` holds it, for all groups and all
   cameras. Each `CameraStatus` gets one shared scalar `log_capture_times`
   (`multiprocessing.Value("b", False, lock=False)`, as the other scalars of `CameraStatus`,
   [ADR-QJH6](../decisions/entries/QJH6-choices-of-the-fix-lane.md) item 3). The manager writes it into
   each status of a new group and at each change. `CameraStatus.reset_for_start` does not reset it
   [U Q587 2].
3. **How a host sets it** [U Q582]. Python: `CameraGroupManager.set_log_capture_times(on: bool) ->
   None`, and the read-only property `CameraGroupManager.log_capture_times`. HTTP: `POST /timings` on
   `camera_router`, body `{"log_capture_times": true}`, answer `{"log_capture_times": true}`. The path
   is `/skellycam/camera/timings` in skellycam alone and in FreeMoCap: both mount `camera_router` with
   the prefix `/skellycam` (Q838, [ADR-GZS7](../decisions/entries/GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md)). A body with no boolean
   gets HTTP 422 [U Q587 2].
4. **When a change takes effect** [U Q587 2]. The camera loop reads its shared scalar at each publish of
   its diagnostics, on its own thread. A change takes effect at the next such publish:
   - normally within 1 s;
   - during the start-up of an open or of a reopen, at the publish at the end of that open (up to
     15 s, `READY_LIMIT_NS`), because the start-up publishes nothing before it;
   - during the end of a take that waits for the recorder thread (`take_end`), after that wait.
   The main process applies a change at its next window. The tile applies it at its next step
   (section 7).
5. **When it is off** [U Q587 3]. The camera process sends `timings = None` (section 6.2). The main
   process drops each kept summary at once. The Python call and the websocket message give
   `"log_capture_times": false` and `"summaries": []` at once. The websocket message still comes once
   per second. Thus a display can show "timing off".
6. **Cost when off.** One branch on a plain attribute at each step: under 0.05 µs p50, 0.1 µs p99 in
   Python [M ADR-3TYP]. No clock read and no store.
7. **First window after a change to on.** The publish that applies a change to on starts the first window
   and sends `timings = None`; the next publish sends the first summary, up to about 2 s after the change. The
   publish that applies a change to off sends None (Q837). The window holds only the samples since the change.
   `window_s`
   gives the real length of the window.

Three differences from the pattern of skellytracker and FreeMoCap. Each one is deliberate [U Q587 2]:

| Difference | Reason |
|---|---|
| The switch changes while the cameras run. skellytracker and FreeMoCap fix it at the start. | A change at open would need a reopen of each camera: up to 15 s of start-up, and an exposure search of about 10 s (ADR-TFD7). The live change costs one read of a shared scalar each second. |
| One boolean. skellytracker has a list of spans. | Each step costs one branch when off [M ADR-3TYP], so a choice of steps saves nothing. FreeMoCap also has one boolean. |
| Summaries once per second. skellytracker sends one event for each span to a sink. | Decided by the user [U Q568]. |

## 3. The steps

### 3.1 The step table [U Q566]

`where` is the thread or the process that runs the step [U Q587 5]: `camera_loop` (the loop thread of
the camera process), `camera_callback` (the Media Foundation callback thread of the camera process),
`decode_thread`, `recorder_thread` (both in the camera process), `main_process` (the event loop of
the server), `ui_tile` (the main thread of the page that shows the shared tile [player 8.1]). The
ids are stable `snake_case` [U Q587 5].

| id | kind | cadence | where | Bracket (commit c6532a21d) | Known cost | Platform |
|---|---|---|---|---|---|---|
| `camera_wait` | wait | frame | `camera_loop` | Each call `frame = self._read()` in `CameraLoop._pass` (`camera_loop.py:233`). The sample of a frame is the sum of the calls since the last frame, also the calls that gave no frame. On the OpenCV source, minus the `opencv_retrieve` sample of the frame [U Q587 6]. The reads of the start-up are not measured. | Up to one frame period. Not measured as its own number. | all |
| `gate_wait` | wait | frame | `camera_loop` | In each pass that reaches the gate: from a clock read before `should_grab_by_id` (`camera_loop.py:229`) to the read after `time.sleep(0.001)` that exists (`:231`) for a refused pass, or to the read after `should_grab_by_id` for the granted pass. The sample of a frame is the sum over its passes. `_publish_diagnostics`, `_check_updates` and `_search_step` are outside it [U Q587 6]. | Not measured in this loop. Prototype gate: median 0.03 to 6.4 ms for each camera [M `research/frame_ring_buffer/docs/frame_ring_buffer_report.md`, 5 cameras, 60 fps]. | all |
| `camera_sample_copy` | work | frame | `camera_callback` | All of `MediaFoundationSource._frame` (`skellycam/core/camera/capture/media_foundation/source.py:338-363`): `ConvertToContiguousBuffer`, `_copy` (`:413-420`), `GetSampleTime`, the discontinuity flag, `FrameLog.add`. | Not measured. | Windows (Media Foundation) |
| `opencv_retrieve` | work | frame | `camera_loop` | `self._capture.retrieve()` between `pre_ns` and `post_ns` (`skellycam/core/camera/capture/opencv_source.py:84-86`); both reads come from the clock of `TimingControl`. It holds the hidden MJPG decode of OpenCV. On Windows DirectShow, `grab()` returns at once, so it also holds the camera wait. | About 32 ms median at 720p on DirectShow, camera wait included [M `research/frame_ring_buffer/prototypes/results/p9_real_camera.md`]. | OpenCV source (Linux, macOS; Windows only with `SKELLYCAM_WINDOWS_CAPTURE=opencv`) |
| `jpeg_encode` | work | frame | `camera_loop` | `cv2.imencode(".jpg", image, JPEG_Q90)[1].tobytes()` (`camera_loop.py:506`). | 1.53 / 2.97 ms median at 720p / 1080p, q90 4:2:0 [M ring 11.1] | OpenCV source |
| `capture_check` | work | frame | `camera_loop` | `check_jpeg(...)` (`camera_loop.py:511`; `skellycam/core/ipc/frame_ring/capture_check.py:28-43`). A DHT insertion copies the full frame (`:43`). | 2.8 µs p50 with a DHT; 7.4 / 12.6 µs p50 with a DHT insertion, 720p / 1080p [M ADR-3TYP] | all |
| `frame_hash` | work | frame | `camera_loop` | `self._hash(...)` (`camera_loop.py:519`, `:908-912`): two SHA-256 and `dqt_segments`. Only the first 30 frames after each trigger (D-11). | 124 / 274 µs p50 at 720p / 1080p [M ADR-3TYP] | all |
| `recorder_give` | wait | frame | `camera_loop` | `self._give(...)` (`camera_loop.py:524`, `:713-730`) to `CameraTakeWriter._put` (`skellycam/core/take_recorder/camera_writer.py:145-162`). It waits when the queue is full. Only during a take. | Longest wait 6.97 to 6.99 s in a 10 s disk stall test [M ADR-8RES]. Normal: not measured. | all |
| `ring_write` | work | frame | `camera_loop` | `self.ring_writer.write(payload, **fields)` of the JPEG ring (`camera_loop.py:532`; `skellycam/core/ipc/frame_ring/writer.py:59-116`). | 600 kB: p50 185 µs, p99 224 µs in a tight loop; p99 744 µs paced by a sleep [M ring 14 item 66] | all |
| `exposure_search_brightness` | work | event | `camera_loop` | All of `CameraLoop._brightness` (`camera_loop.py:474-481`), called by `search.frame` (`:544-545`): `decode_jpeg` when the source gives a JPEG, then `np.mean`. About one call for each trial of a search. Each source that searches; the OpenCV source of Windows has its BGR image and does only the mean. | Mean: 1.36 / 3.07 ms p50 at 720p / 1080p; decode and mean: 4.89 / 11.00 ms p50, synthetic JPEGs [M ADR-3TYP]. Decode of camera JPEGs: 2.60 / 5.42 ms median [M ring 11.1]. | all |
| `diagnostics_publish` | work | second | `camera_loop` | All of `CameraLoop._publish_diagnostics` (`camera_loop.py:937-952`), only when the loop thread calls it: `source.diagnostics()`, `_loop_diagnostics()`, the build of the summary, `pickle.dumps` and the publish. Its sample goes into the next window. | The pickle with a summary: 24.5 µs p50; the summary build (20 steps): 56.9 µs p50 [M ADR-3TYP]. `source.diagnostics()`: not measured. | all |
| `take_start` | work | event | `camera_loop` | `start_take_writer(...)` in `_start_take` (`camera_loop.py:701-702`): the file opens, the MKV header, the CSV header, the thread start. | Not measured. | all |
| `take_end` | wait | event | `camera_loop` | `writer.end(...)` or `writer.abandon()` in `_end_take` (`camera_loop.py:763`, `:747`). It waits for the recorder thread to write each queued frame and to finish the files. | Up to the stall limit of the take (10 s) [rec 5.3]. Not measured. | all |
| `bgr_decode` | work | frame | `decode_thread` | `self._to_bgr(item)` in `DecodeStage._run` (`decode.py:107`, `:122-128`): `cv2.imdecode` of a JPEG, or `cv2.cvtColor` of YUY2 or NV12. No sample for a BGR input, which needs no work. Only with a BGR ring. | 2.60 / 5.42 ms median [M ring 11.1]; 8 processes: 3.17 / 7.11 ms | all |
| `bgr_ring_write` | work | frame | `decode_thread` | `writer.write(bgr, ...)` of the BGR ring (`decode.py:115-117`; `writer.py:59-116`). Only with a BGR ring. | 0.79 / 1.83 ms median, 1.24 / 2.46 ms p99 at 720p / 1080p [M ADR-ETJ1] | all |
| `mkv_mux` | work | frame | `recorder_thread` | `self._mkv.mux(block, self._k)` (`camera_writer.py:290`; `skellycam/core/take_recorder/mkv.py:49`). | One write call: p50 0.01 ms, p99 0.09 to 0.10 ms, max 3.7 to 46 ms [M ADR-8RES] | all |
| `csv_row` | work | frame | `recorder_thread` | `_write_row` without its fsync (`camera_writer.py:300-308`): `sidecar.row_line` and `_write_line`. | `row_line`: 1.1 µs p50 [M ADR-3TYP]. The write: not measured. | all |
| `fsync` | work | second | `recorder_thread` | `self._fsync_both()` (`camera_writer.py:311`, `:348`): `os.fsync` of the MKV and of the CSV. | p50 2.0 to 2.1 ms, max 29 to 182 ms with 16 writers at 1080p60 [M ADR-8RES] | all |
| `mkv_close` | work | event | `recorder_thread` | All of `_finish` (`camera_writer.py:325-351`) minus the samples of `mkv_mux`, `csv_row` and `fsync` that it records: `close_container()`, the search of the last block in the file, the end line and the two file closes. | Not measured. | all |
| `preview_ring_read` | work | frame | `main_process` | The ring read of the preview sender: `reader.read` in `PreviewRelay._newest_unsent` (`skellycam/api/websocket/preview_relay.py:163`, `:167`), or `reader.read_newest()` in `CameraGroup.read_latest_ring_frames` (`skellycam/core/camera_group/camera_group.py:559`) [U Q587 11]. | 0.08 / 0.25 ms median, 0.16 / 0.44 ms p99 at 720p / 1080p [M ADR-HDC9] | all |
| `preview_pack` | work | frame | `main_process` | `pack_camera_frame(camera_id, read)` (`preview_relay.py:146`), or the build of the group message in `CameraGroup.get_latest_ring_payload` after its reads (`camera_group.py:573-596`) [U Q587 11]. | `pack_camera_frame`: 0.005 / 0.11 ms median [M ADR-HDC9]. Group message: not measured. | all |
| `preview_send` | work | frame | `main_process` | `await self.websocket.send_bytes(data)` inside `_send_bytes`, after the send lock (`skellycam/api/websocket/websocket_server.py:102`). The wait for the send lock is outside it. | 0.13 / 0.23 ms median, 0.63 / 1.11 ms p99 with compression off [M ADR-HDC9] | all |
| `ui_jpeg_decode` | work | frame | `ui_tile` | The call `this.#decode(p.u.jpeg!)` in `Tile.#next` to its result (`skellycam-ui/src/player/tile/tile.ts:170`): `decodeJpeg` with `ImageDecoder`, the EXIF undo and the decoder close (`tile.ts:73-87`, [player 8.1]). Only an update with `jpeg` and no `image`. | Not measured live. The player `ImageDecoder`: 2.7 ms median at 1080p, 1 tile; 3.7 ms at 4 tiles [M `decisions/evidence/1ACK-findings-of-the-6a-player-code.md`]. | all |
| `ui_draw` | work | frame | `ui_tile` | The call `this.#draw()` in `Tile.#apply` (`tile.ts:179-182`, `#draw` at `:184`, [player 8.2]) after an update that set a new decoded image. A redraw for a resize or an overlay-only update gives no sample. | Not measured live. The player draw at tile size: 0.4 to 0.5 ms [M same]. | all |

A summary holds only the steps that apply to its camera (section 5.4). A step that applies but did
not run in the window has `n` 0.

### 3.2 Parts left out [U Q566] [U Q587 12]

Each part below is far below 1 ms. Each number is from one run on synthetic data [M ADR-3TYP]. The
delay `arrival_to_published` (section 4) holds each part of the camera loop up to the ring commit.
Thus a part that becomes slow still shows in that delay.

| Part | Code | p50 / p99 for each call |
|---|---|---|
| The status update | `status.frame_count.value`, `status.replaced_count.value` (`camera_loop.py:540-541`) | 0.1 / 0.2 µs (two stores) |
| The frame decision of a take | `should_record_frame_number` (`camera_loop.py:502`) | 0.5 / 0.5 µs, with no other holder of the lock. A lock that a killed process holds waits up to 1.5 s one time (ADR-QJH6 item 3); `arrival_to_published` shows it. |
| The hand-over to the decode thread | `decode_stage.waiting_place.put(item)` (`camera_loop.py:537`) | 0.5 / 0.6 µs |
| The rate checks | `_feed_check`, `_feed_block` (`camera_loop.py:542`, `:546`) | 0.4 / 1.1 µs. The end of a check writes the status one time for each live change. |
| The waiting place of the callback | `CaptureWaitingPlace.put` (`source.py:123-130`) | 0.5 / 0.6 µs |
| The SOF parse of the recorder | `parse_sof(payload)` (`camera_writer.py:275`) | 2.8 / 3.3 µs |
| The tick of the preview sender | `PreviewRelay._tick` (`preview_relay.py:178`) | Four times per second, not for each frame. Its reads are `read_newest` calls: 0.08 / 0.16 ms at 720p, 0.25 / 0.44 ms at 1080p [M ADR-HDC9]. |

## 4. End-to-end delays and clocks [U Q570] [U Q587 10]

| id | where | From | To | Clock |
|---|---|---|---|---|
| `arrival_to_published` | `camera_loop` | `arrival_ns` of the frame | the clock read at the end of the bracket of `ring_write` | `time.perf_counter_ns`, one process |
| `published_to_send` | `main_process` | `published_ns` of the slot header (`FrameRead.published_ns`) | the clock read at the start of the bracket of `preview_send` | `time.perf_counter_ns`, two processes of one machine |
| `receive_to_draw` | `ui_tile` | `receivedAtMs` of the update: `PreviewTiles.receive` stamps it when the camera message comes ([4b 5.3]) | the end of `ui_draw` | `performance.now()` of the page, one thread |

Rules and limits:

- `arrival_ns` is the time of the Media Foundation callback, or the time just after `grab()` of
  OpenCV. It is not the time of the sensor [cap 4.2]. On Windows DirectShow, `grab()` returns at once,
  so `arrival_ns` is the call time [M `research/frame_ring_buffer/prototypes/results/p9_real_camera.md`].
- The Media Foundation callback reads `arrival_ns` after it gets the GIL. When another thread of the
  camera process holds the GIL (for example a copy of the decode thread, 0.2 to 0.9 ms at 1080p,
  ADR-ETJ1 M7), `arrival_ns` is late by that time.
- `arrival_to_published` ends later than `published_ns`: after `published_ns` the ring write also
  packs the header, computes its CRC, stores the header and the head, updates the counters and can
  log one line (`writer.py:95-116`). Thus the ring API does not change [U Q587 10].
- `time.perf_counter_ns` is one clock for all processes of one machine on Windows, Linux and macOS.
  The product already compares `arrival_ns` of different camera processes (the spread). Thus
  `published_to_send` is valid on one machine. It is not valid across machines.
- The clock of Python and the clock of the browser have different origins. Thus no delay goes from
  a point in Python to a point in the UI: the time from the send to the receipt is not measured.
- `receive_to_draw` uses one clock, because `PreviewTiles` and the tile run on the main thread of the
  page [player 8.1]. If the tile moves to a worker by the rule of [4b 6.4], the stamp crosses two
  contexts, and the delay must then use `performance.timeOrigin + performance.now()` and a check of
  the skew between them.
- The player gives no `receivedAtMs`, so a player update gives no `receive_to_draw` sample.
- A delay is a summary of the same shape as a step, in `delays`, not in `steps`. A display never
  adds a delay to the time of the steps.

## 5. Measurement

### 5.1 Threads, buffers and the clock [U Q587 7]

- `TimingControl`: the flag `on` and the method `clock()`. `clock()` forwards to a clock function
  that the `CameraLoop` gives when it makes the `TimingControl`: its module name `perf_counter_ns`,
  so a test gives one virtual clock to each bracket of the camera process (ADR-HP7D item 12). The
  `CameraLoop` gives the same `TimingControl` to each source, each `DecodeStage` and each
  `CameraTakeWriter` that it makes. Each bracket reads `control.clock()`, and only a bracket calls
  it. The other jobs of the loop (the stall watch, the diagnostics interval) still read
  `perf_counter_ns` directly. Thus a test counts the calls of `clock()` to count the reads of the
  measurement only.
- `StepSamples`: a fixed `array.array("q")` of `CAPACITY = 512` durations in nanoseconds, and an
  integer `total` of all samples since its creation. `add(duration_ns)` stores at `total % 512`,
  then increases `total`.
- `StepSet`: the `StepSamples` of one writer instance. Each writer instance makes its own `StepSet`
  when it starts: each source, each `DecodeStage`, each `CameraTakeWriter`, each websocket
  connection. The `CameraLoop` has its own `StepSet` for the steps of the loop thread.
- One thread writes each `StepSet`. A new take, a new decode stage or a new open makes a new
  `StepSet`. An old thread that still runs (a writer thread after a stall, a callback after a close
  with no `OnFlush`) writes only into its own old `StepSet`.
- **Retire.** When `end()` or `abandon()` returns, when a source closes and when a decode stage stops,
  the loop moves its `StepSet` to a retired list. The next summary reads the retired sets and the
  current sets, then drops the retired sets. A sample that an old thread writes after that is lost.
- **Merge.** In one window, the samples of a retired set and of the current set with the same step
  id go into one step entry: one `n`, and one sort for the percentiles.
- **One reader.** Only the loop thread reads the `StepSet`s of the camera process, in
  `_publish_diagnostics`. When another thread calls `_publish_diagnostics` (the control thread calls
  `_fail` at a hang, `camera_loop.py:1009`), that publish reads no buffer and records no sample: it
  sends the last summary again, with the same `seq`. When there is no earlier summary (for example a
  hang during the start-up), it sends `timings = None`.
- The reader keeps the `total` of its last read of each buffer. The samples of the window are the
  samples from that `total` to the new `total`. The reader writes nothing into a buffer. Thus there
  is no reset and no race with the writer.
- With the GIL of Python 3.13 (the product build), the store and the increase of `total` keep their
  order for the reader.
- The main process: the `WebsocketServer` of each connection has one `TimingControl` and one
  `StepSet`, written and read on the event loop thread. The preview steps of the interim relay
  are in the shared methods `CameraGroup.read_latest_ring_frames` and `get_latest_ring_payload`, and
  in `CameraGroupManager.get_latest_frontend_payloads`. Each of them gets the `StepSet` of the
  connection as an argument (`step_set=None` means no measurement) [U Q587 11].
- The tile: section 7.

### 5.2 Window and statistics [U Q568] [U Q587 8]

- The window of a camera is from one summary to the next. The loop thread makes a summary at each
  publish of `_publish_diagnostics` (`DIAGNOSTICS_INTERVAL_NS`, 1 s, `camera_loop.py:71`), also at
  the end of an open, at a failure on the loop thread and at the close (`:322`, `:821`, `:861`). The
  camera loop publishes also when the camera is paused or in `waiting` (`:212-215`). The publish at
  the end of an open holds the callback samples of the warm-up. The main process window is from one
  `capture_timings` message to the next. The window of the tile is from one read of the host to the
  next (section 7).
- `n` is the count of samples in the window.
- The percentile is the nearest rank: sort the samples of the window from low to high; `pq` is
  the sample at index `ceil(q * n) - 1`. `p50_ms` uses q = 0.5; `p95_ms` uses q = 0.95. `max_ms` is
  the largest sample.
- When `n` is 0: `p50_ms`, `p95_ms` and `max_ms` are `null`. The step stays in the summary.
- When `n` is more than 512: `n` is the full count; `p50_ms`, `p95_ms` and `max_ms` use the newest
  512 samples. At 120 frames per second a step of cadence `frame` gives 120 samples in a window.
- Each `_ms` value is a float in milliseconds, rounded to 0.001 ms [U Q587 13], half up in integers:
  `((ns + 500) // 1000) / 1000`; `window_s` the same way to 0.001 s. The tile gives the same JSON (Q840).
- The statistics are computed once per window, by the reader. No sample is sent.

### 5.3 Cost budget of the measurement [U Q587 9]

- When off: one branch for each step (section 2 item 6). No clock read.
- When on, the camera loop thread reads the clock at most 10 times for each frame, plus one read for
  each refused pass of the gate, plus three reads for each granted pass that gives no frame. The limit
  counts the steps of cadence `frame`; a step of cadence `event` (`take_start`, `take_end`,
  `exposure_search_brightness`) adds its own 2 reads on its frame (Q838). Adjacent brackets share one read,
  so a few short lines between two brackets fall into the next one; `should_record_frame_number` stays outside
  each bracket, and the OpenCV `camera_wait` ends at `pre_ns`.
  The gate uses the read that exists at `camera_loop.py:231`. The OpenCV source uses its `pre_ns` and
  `post_ns`. For a YUY2 or NV12 camera, the limit counts the frames that the loop takes: the
  `jpeg_encode` bracket starts at the read that ends `camera_wait`, and its end is the first read of the
  next frame; a pass whose frame Quick Sync holds reads the clock 4 times [U Q880]. [U Q880] is
  decision Q880 of the user ([ADR-4TBY](../decisions/entries/4TBY-decisions-of-the-user-on-the-review-of-the-3b-code.md)).
- When on, each other thread reads the clock at most 2 times for each step.
- Measured costs [M ADR-3TYP]: one `perf_counter_ns` call under 0.05 µs p50 and 0.1 µs p99; one
  sample store 0.1 µs p50 and 0.2 µs p99. Thus about 1.5 µs for each frame in the loop thread: under
  0.01 % of a frame period at 60 fps.
- No list, dict or other container grows for each frame. The buffers have a fixed size.
- The summary build runs once per window: 56.9 µs p50 for 20 steps of 60 samples [M ADR-3TYP].
- The summary of one camera is at most 4 KiB pickled; 20 steps and 1 delay measured 1,577 bytes
  [M ADR-3TYP]. The diagnostics message of a camera has a limit of 32 KiB, and the largest dict today
  is about 14 kB [unix 4.2]. Thus the summary fits.
- Measurement M-TIM-1 (section 11) measures the cost on the real path.

### 5.4 Steps that apply

| Condition | Steps |
|---|---|
| Each camera | `camera_wait`, `gate_wait`, `capture_check`, `frame_hash`, `recorder_give`, `ring_write`, `exposure_search_brightness`, `diagnostics_publish`, `take_start`, `take_end`, `mkv_mux`, `csv_row`, `fsync`, `mkv_close` |
| Media Foundation source | also `camera_sample_copy` |
| OpenCV source | also `opencv_retrieve`, `jpeg_encode` |
| A YUY2 or NV12 camera of a native source ([`windows-capture.md`](windows-capture.md) 13.2) | also `jpeg_encode` [U Q880] |
| A BGR ring | also `bgr_decode`, `bgr_ring_write` |
| The preview sender of a connection | `preview_ring_read`, `preview_pack`, `preview_send` |
| A tile with a `TileTimings` handle (section 7) | `ui_jpeg_decode`, `ui_draw` |

A source that does not search (the OpenCV source of Linux and macOS) has `n` 0 for
`exposure_search_brightness`. A later native source (Linux V4L2, macOS AVFoundation) gets the steps
of the Media Foundation source. Its callback copy step, if it has one, uses `camera_sample_copy`
[U Q587 5].

## 6. Publication

### 6.1 The summary shape [U Q569] [U Q587 15]

| Field | Type | Meaning |
|---|---|---|
| `source` | `"camera"` \| `"preview"` \| `"ui"` | Who made the summary. |
| `camera_group_id` | string or `null` | The group. `null` when the source does not know it. |
| `camera_id` | string or `null` | The camera. `null` for a step of the whole group: the group message of the interim relay (6.5). |
| `clock` | `"perf_counter_ns"` \| `"performance.now"` | The clock of the durations and of `window_end_ns`. |
| `seq` | int | The number of this summary. The source starts at 0 and adds 1 for each new summary. A repeat has the same `seq`. A new camera process starts again at 0. |
| `window_end_ns` | int | The clock read at the end of the window, in nanoseconds of `clock` (for the tile: `performance.now()` × 1,000,000, rounded). |
| `window_s` | float | The real length of the window, in seconds, 3 decimals. |
| `steps` | object | Step id to step entry. |
| `delays` | object | Delay id to delay entry. |

A step entry: `{"kind": "work" | "wait", "cadence": "frame" | "second" | "event", "where": <where>,
"n": int, "p50_ms": float | null, "p95_ms": float | null, "max_ms": float | null}`. A delay entry
has `where`, `n`, `p50_ms`, `p95_ms` and `max_ms`; its `where` is the place of its end point.

### 6.2 Camera process to main process [U Q587 1]

- `DiagnosticsMessage` (`skellycam/core/ipc/pubsub/pubsub_topics.py:42-47`) gets one field:
  `timings: dict | None = None`. It holds the summary of the camera for the window that just ended,
  or `None` when the switch is off.
- The message goes with each publish of the diagnostics, on the topic `TopicTypes.DIAGNOSTICS`.
  No new topic, no new queue, no new pipe.
- The diagnostics dict does not change. Thus the D-keys of [unix 4.6.2], the counter subset and
  certify do not change.
- `CameraGroup._take_diagnostics` (`camera_group.py:491-502`, the watch thread) keeps the newest
  summary of each camera and the main-process `perf_counter_ns` at its receipt. It builds a new dict
  for each change and replaces the attribute `camera_timings` with it (a snapshot swap). A reader
  reads the attribute one time and uses that dict [U Q587 7].

### 6.3 The Python call [U Q582] [U Q587 12]

`CameraGroupManager.capture_timings() -> dict` gives:

```python
{"version": 1, "log_capture_times": bool, "summaries": [<summary>, ...]}
```

- One summary for each camera of each open group, the newest one. Only `source` `"camera"`.
- It leaves out a summary that came more than 3 s ago, and each summary of a closed group. Thus a
  camera that is absent has no summary in the last 3 s: it is closed, it is in a start-up, it waits
  for its recorder thread, or it has stopped.
- When the switch is off, `summaries` is `[]`.
- It reads no ring and no shared memory. It never raises for a missing camera. It is safe to call
  from any thread of the main process.

### 6.4 The websocket message [U Q587 1] [U Q580]

- A new JSON message kind: `capture_timings` (`WebsocketMessageType.CAPTURE_TIMINGS`).
- The loop of `_app_state_sender` (`websocket_server.py:264`) sends it once per second, after the
  app state check. The interval is a module constant `CAPTURE_TIMINGS_INTERVAL_S = 1.0`.
- The body is the body of `capture_timings()`, plus `"message_type": "capture_timings"`, plus the
  summaries of the preview sender of this connection (`source` `"preview"`) when the switch is on.
- When the switch is off, the message is
  `{"message_type": "capture_timings", "version": 1, "log_capture_times": false, "summaries": []}`.
- **`performance_data` goes** [U Q580], with its live inter-camera rows (`grab_range_ms`,
  `grab_stddev_ms`). The build deletes: the module `skellycam/api/websocket/performance_data.py`;
  `CameraGroupManager.get_latest_performance_data` and its import
  (`camera_group_manager.py:11`); `WebsocketMessageType.PERFORMANCE_DATA`; in
  `skellycam/tests/test_websocket_internals.py`, the import of the module (`:5-9`) and the classes
  `TestPerformanceDataHelpers` and `TestExtractPerformanceData`. `TestServerFramerateCalculator`
  stays. The stop response keeps `inter_camera_grab_range_ms_stats` for each take.
- `read_latest_ring_frames` stays for the interim relay. This spec changes the two specs that named
  `get_latest_performance_data`: [prv 2.3] and the table of [ring 2.1].

### 6.5 The preview sender [U Q587 11]

- The preview sender that is wired measures `preview_ring_read`, `preview_pack`, `preview_send` and
  `published_to_send`: the per-camera `PreviewRelay` after step 4b, or the interim
  `_frontend_image_relay` before it.
- With `PreviewRelay`, each step is for one camera: one `"preview"` summary for each camera. Its
  `preview_send` bracket starts after the send lock, as for the interim relay: the server's locked send takes
  the bracket (Q839, step 4b).
- With the interim relay: `preview_ring_read` is for one camera, in a `"preview"` summary for each
  camera. `preview_pack` and `preview_send` are for the group: one more `"preview"` summary with
  `camera_id` `null`. `published_to_send` uses the `published_ns` of each camera of the group
  message, in the summary of that camera.
- Each connection has its own summaries. Only the message of that connection carries them. The
  Python call does not carry them.

### 6.6 Full example

Two cameras of group `g1`, Media Foundation, 720p30, during a take, with the switch on, over a
connection with the per-camera preview sender. The numbers are an example, not a measurement.

```json
{
  "message_type": "capture_timings",
  "version": 1,
  "log_capture_times": true,
  "summaries": [
    {
      "source": "camera",
      "camera_group_id": "g1",
      "camera_id": "a1b2",
      "clock": "perf_counter_ns",
      "seq": 812,
      "window_end_ns": 81234567890123,
      "window_s": 1.0,
      "steps": {
        "camera_wait": {"kind": "wait", "cadence": "frame", "where": "camera_loop", "n": 30, "p50_ms": 31.912, "p95_ms": 33.105, "max_ms": 34.877},
        "gate_wait": {"kind": "wait", "cadence": "frame", "where": "camera_loop", "n": 30, "p50_ms": 0.0, "p95_ms": 1.071, "max_ms": 1.982},
        "camera_sample_copy": {"kind": "work", "cadence": "frame", "where": "camera_callback", "n": 30, "p50_ms": 0.041, "p95_ms": 0.077, "max_ms": 0.130},
        "capture_check": {"kind": "work", "cadence": "frame", "where": "camera_loop", "n": 30, "p50_ms": 0.003, "p95_ms": 0.004, "max_ms": 0.009},
        "frame_hash": {"kind": "work", "cadence": "frame", "where": "camera_loop", "n": 0, "p50_ms": null, "p95_ms": null, "max_ms": null},
        "recorder_give": {"kind": "wait", "cadence": "frame", "where": "camera_loop", "n": 30, "p50_ms": 0.004, "p95_ms": 0.006, "max_ms": 0.011},
        "ring_write": {"kind": "work", "cadence": "frame", "where": "camera_loop", "n": 30, "p50_ms": 0.092, "p95_ms": 0.140, "max_ms": 0.410},
        "exposure_search_brightness": {"kind": "work", "cadence": "event", "where": "camera_loop", "n": 0, "p50_ms": null, "p95_ms": null, "max_ms": null},
        "diagnostics_publish": {"kind": "work", "cadence": "second", "where": "camera_loop", "n": 1, "p50_ms": 0.620, "p95_ms": 0.620, "max_ms": 0.620},
        "take_start": {"kind": "work", "cadence": "event", "where": "camera_loop", "n": 0, "p50_ms": null, "p95_ms": null, "max_ms": null},
        "take_end": {"kind": "wait", "cadence": "event", "where": "camera_loop", "n": 0, "p50_ms": null, "p95_ms": null, "max_ms": null},
        "mkv_mux": {"kind": "work", "cadence": "frame", "where": "recorder_thread", "n": 30, "p50_ms": 0.031, "p95_ms": 0.090, "max_ms": 0.240},
        "csv_row": {"kind": "work", "cadence": "frame", "where": "recorder_thread", "n": 30, "p50_ms": 0.012, "p95_ms": 0.020, "max_ms": 0.035},
        "fsync": {"kind": "work", "cadence": "second", "where": "recorder_thread", "n": 1, "p50_ms": 2.050, "p95_ms": 2.050, "max_ms": 2.050},
        "mkv_close": {"kind": "work", "cadence": "event", "where": "recorder_thread", "n": 0, "p50_ms": null, "p95_ms": null, "max_ms": null}
      },
      "delays": {
        "arrival_to_published": {"where": "camera_loop", "n": 30, "p50_ms": 0.210, "p95_ms": 1.402, "max_ms": 2.330}
      }
    },
    {
      "source": "preview",
      "camera_group_id": "g1",
      "camera_id": "a1b2",
      "clock": "perf_counter_ns",
      "seq": 95,
      "window_end_ns": 81234571000456,
      "window_s": 1.001,
      "steps": {
        "preview_ring_read": {"kind": "work", "cadence": "frame", "where": "main_process", "n": 30, "p50_ms": 0.081, "p95_ms": 0.150, "max_ms": 0.300},
        "preview_pack": {"kind": "work", "cadence": "frame", "where": "main_process", "n": 30, "p50_ms": 0.005, "p95_ms": 0.012, "max_ms": 0.020},
        "preview_send": {"kind": "work", "cadence": "frame", "where": "main_process", "n": 30, "p50_ms": 0.130, "p95_ms": 0.580, "max_ms": 0.900}
      },
      "delays": {
        "published_to_send": {"where": "main_process", "n": 30, "p50_ms": 4.100, "p95_ms": 11.200, "max_ms": 13.050}
      }
    }
  ]
}
```

The summaries of camera `c3d4` have the same form. They are left out of the example.

### 6.7 Version [U Q587 15]

- `version` is 1 for this spec.
- A new step id, a new delay id or a new field does not change `version`. A display must show a
  step id that it does not know, with the id as its label.
- A change of a field name, a unit, a type or the meaning of a field or of an id increases
  `version` by one. A display that sees a `version` that it does not know shows no numbers and says
  so.

## 7. The shared tile [U Q586] [U Q587 16]

The player and the live preview of step 4b are built one time in skellycam, and the FreeMoCap UI
takes a copy of the folder `skellycam-ui/src/player/` [player 4.3], [4b 8] item 6. Thus the decode
and draw timing goes into the tile module, and FreeMoCap gets it with the folder [U Q586]. It is
built together with step 4b. The interim workers get no measurement (1.3).

- **Module.** `skellycam-ui/src/player/tile/timings.ts`, with no import outside `tile/`, so the
  boundary rule of [player 4.2] holds. It exports `TileTimings` and the summary function.
- **The host makes one `TileTimings`** for the page: `new TileTimings(now?: () => number)`; `now`
  defaults to `performance.now`. The host sets `timings.on` (a plain boolean, default `false`).
- **The tile gets a handle.** `timings.handle(cameraId: string, cameraGroupId: string | null)`
  gives one `TileTimingHandle` for each camera. The host gives it to the tile in the third argument
  of the constructor: `new Tile(canvas, options, {timing: handle})` (the argument that already holds
  the `decode` seam, `tile.ts:105`). A tile with no handle measures nothing.
- **The switch state.** skellycam-ui sets `timings.on` from `log_capture_times` of each
  `capture_timings` message. FreeMoCap sets it from its own switch state (section 8.2). Each bracket
  of the tile reads `timings.on`: one branch when off. A change applies at the next step.
- **Brackets.** `ui_jpeg_decode` and `ui_draw` of table 3.1, read with `now()`.
  `receive_to_draw`: `TileUpdate` gets one optional field `receivedAtMs?: number`.
  `PreviewTiles.receive` stamps `now()` on each camera message, and `tick` passes it on with the
  update ([4b 5.3]). The tile records `now() - receivedAtMs` at the end of `ui_draw`. A message that a
  newer message replaces is never drawn and gives no sample.
- **Buffers.** Each handle keeps a `Float64Array` of 512 durations in milliseconds and a total for
  each step and delay, as 5.1. The page has one thread, so one writer and one reader.
- **Where the summaries go.** The host reads them: `timings.takeSummaries()` closes the window of each
  handle and gives one summary for each handle (`source` `"ui"`, `clock` `"performance.now"`,
  `where` `ui_tile`), by the rules of 5.2. The host calls it once per second. Nothing goes to the
  server. skellycam-ui has no reader now (no display, [U Q577]); a test reads it. FreeMoCap reads it
  in its own UI (section 8.7).
- **Not measured.** The decode of an image that the player made ahead (`image`, [player 8.3] and
  9.1): the tile does not decode it. A redraw for a resize or an overlay-only update.
- **Tests.** `TileTimings` and the summary function are plain TypeScript: unit tests with
  `node --experimental-strip-types --test`, as `npm run test:player:unit`. The brackets in the tile
  need a canvas: a test in `skellycam-ui/src/player/tests/browser/tile.spec.ts`, run by
  `npm run test:player:browser` (playwright). No new dependency.

## 8. Interface note for FreeMoCap

This section is for the freemocap session. It can be read alone.

### 8.1 When

FreeMoCap imports the old skellycam today: its `pyproject.toml` points `skellycam` at the local
checkout of `skellycam-sfn26-pins`, "until freemocap moves to skellycam's frame-ring API". That
skellycam has no capture timings. Thus the display can come only after FreeMoCap moves to the
frame-ring API of skellycam [U Q577].

### 8.2 The switch

- Python: `camera_group_manager.set_log_capture_times(on: bool)`; read it with
  `camera_group_manager.log_capture_times`. Default `False`. One switch for all groups and cameras.
- HTTP, in FreeMoCap: `POST /skellycam/camera/timings` with `{"log_capture_times": true}`. The answer
  is `{"log_capture_times": true}`. A body with no boolean gets HTTP 422.
- A change takes effect at the next summary of each camera: normally within 1 s. During the start-up
  of a camera (up to 15 s), and while a camera waits for its recorder at the end of a take, later.
- Recommendation [U Q583]: FreeMoCap sets the switch from `log_pipeline_times` when a real-time
  pipeline starts, and sets it off when the pipeline stops. Then the user has one switch.

### 8.3 How to read

- `camera_group_manager.capture_timings()` gives
  `{"version": 1, "log_capture_times": bool, "summaries": [...]}`. Call it once per second, for
  example in the relay that builds the `pipeline_timing` message. It never raises for a missing
  camera, and it is safe from any thread.
- Each summary is new at most once per second. Use `seq` to see a repeat (the same `seq`) or a skip
  (a gap). `seq` starts again at 0 when a camera process starts again; `window_end_ns` still
  increases.
- When the switch is off: `"log_capture_times": false` and `"summaries": []`. Show "capture timing
  off".
- An absent camera: it has no summary in the last 3 s. It is closed, in its start-up, waiting for
  its recorder at the end of a take, or stopped. Show its rows as "no data", not as 0.

### 8.4 One summary

| Field | Meaning |
|---|---|
| `source` | `"camera"` from this call; `"ui"` from the tile (8.7). |
| `camera_group_id`, `camera_id` | The group and the camera. `camera_group_id` is `null` in a tile summary when the host gave no group. |
| `clock` | `"perf_counter_ns"`: `time.perf_counter_ns` of the camera process. It is the clock of the FreeMoCap `PipelineTimingEvent` (`clock_domain` `"perf_counter"`) on the same machine. `"performance.now"` for the tile. |
| `seq` | The number of the summary, +1 for each new one. |
| `window_end_ns` | The end of the window, in nanoseconds of `clock`. |
| `window_s` | The real length of the window in seconds (about 1). |
| `steps` | Step id to `{kind, cadence, where, n, p50_ms, p95_ms, max_ms}`. |
| `delays` | Delay id to `{where, n, p50_ms, p95_ms, max_ms}`. |

- Units: milliseconds, float, 3 decimals. `n` is the count of samples in the window.
- Percentiles: nearest rank over the samples of the window. When `n` is more than 512, `n` is the
  full count and the three values use the newest 512 samples.
- `null`: `p50_ms`, `p95_ms` and `max_ms` are `null` when `n` is 0. The step applies to the camera
  but did not run in the window (for example `fsync` with no take).
- An absent step id: the step does not apply to that camera (for example `jpeg_encode` on a Media
  Foundation camera in MJPG).
- `version`: 1. A new step id or field keeps it; show an unknown step id with its id as the label. A
  change of a name, unit, type or meaning increases it; show no numbers for an unknown `version`.

### 8.5 The step ids

`kind`: `wait` is a wait for another part; `work` is the work of the step. `cadence`: `frame` (at
most once per frame), `second` (once per second), `event` (at a take start or end, or a trial of the
exposure search).

| id | kind | cadence | where | What it is |
|---|---|---|---|---|
| `camera_wait` | wait | frame | `camera_loop` | Wait for the next camera frame |
| `gate_wait` | wait | frame | `camera_loop` | Wait at the lockstep gate for the other cameras |
| `camera_sample_copy` | work | frame | `camera_callback` | Copy of the frame out of Media Foundation (Windows) |
| `opencv_retrieve` | work | frame | `camera_loop` | OpenCV `retrieve()`, with its hidden JPEG decode. On Windows DirectShow it also holds the wait for the camera. |
| `jpeg_encode` | work | frame | `camera_loop` | JPEG encode of an OpenCV frame, or of a YUY2 or NV12 frame: one sample for each frame that the loop takes, also when Quick Sync holds it and no JPEG comes out yet [U Q880] |
| `capture_check` | work | frame | `camera_loop` | JPEG marker check, and the DHT insertion |
| `frame_hash` | work | frame | `camera_loop` | Two SHA-256 of the first 30 frames after a ready or a record start |
| `recorder_give` | wait | frame | `camera_loop` | Hand-over to the recorder; a wait when its queue is full |
| `ring_write` | work | frame | `camera_loop` | CRC and copy into the frame ring |
| `exposure_search_brightness` | work | event | `camera_loop` | Decode and mean brightness for a trial of the exposure search |
| `diagnostics_publish` | work | second | `camera_loop` | Build and publish of the diagnostics and of this summary |
| `take_start` | work | event | `camera_loop` | Start of the take writer: file opens and headers |
| `take_end` | wait | event | `camera_loop` | Wait for the recorder thread at the end of a take |
| `bgr_decode` | work | frame | `decode_thread` | JPEG decode to BGR for the BGR ring |
| `bgr_ring_write` | work | frame | `decode_thread` | CRC and copy into the BGR ring |
| `mkv_mux` | work | frame | `recorder_thread` | MKV block write |
| `csv_row` | work | frame | `recorder_thread` | CSV row write |
| `fsync` | work | second | `recorder_thread` | `fsync` of the MKV and the CSV |
| `mkv_close` | work | event | `recorder_thread` | MKV close and file closes at the end of a take |
| `ui_jpeg_decode` | work | frame | `ui_tile` | JPEG decode in the tile (`ImageDecoder`), from 8.7 |
| `ui_draw` | work | frame | `ui_tile` | Draw of a new image in the tile, from 8.7 |

The delays: `arrival_to_published` (`camera_loop`): from the arrival of the frame to the end of its
ring write, one process. `receive_to_draw` (`ui_tile`, from 8.7): from the receipt of the camera
message in the page to the end of its draw, one page clock. skellycam measures `published_to_send`
and the steps `preview_*` only for its own websocket. FreeMoCap does not get them.

### 8.6 What the FreeMoCap display must do [U Q576]

- Show the capture steps as one "capture" block in the per-stage table of the Pipeline metrics
  window, fed by the summaries. No per-frame bar in the timeline for a capture step.
- One row for each camera and step: label, `p50_ms`, `p95_ms`, `max_ms`, and `n`. The table of today
  has the columns "ms/frame" (mean), "FPS", "range" and "frames". A summary has no mean and no
  minimum. Thus the capture block needs its own columns, or it shows `p50_ms` as "ms/frame" and
  `max_ms` as the top of the range. The freemocap session decides.
- Never add a `wait` step or a delay to work. Never add a step of cadence `second` or `event` to a
  step of cadence `frame`. Percentiles do not add: a sum of p50 values is not the p50 of the sum. A
  display can show the `work` steps of cadence `frame` of one `where` side by side.
- Show the delays apart, for example one line for each camera: "arrival to ring p50 / p95".

### 8.7 The UI steps come from the tile in the UI of FreeMoCap [U Q586]

- FreeMoCap takes a copy of the folder `skellycam-ui/src/player/` [player 4.3]. After step 4b, that
  folder has the live preview tile and `tile/timings.ts`.
- The FreeMoCap UI makes one `TileTimings`, gives a handle to each tile
  (`new Tile(canvas, options, {timing: timings.handle(cameraId, groupId)})`), sets `timings.on` from
  its switch state, and calls `timings.takeSummaries()` once per second.
- Each summary has the shape of 8.4 with `source` `"ui"`, `clock` `"performance.now"`, the steps
  `ui_jpeg_decode` and `ui_draw` and the delay `receive_to_draw`. FreeMoCap shows them in the same
  capture block. They never go to a server.
- Until FreeMoCap uses the tile, FreeMoCap measures its own decode and draw with its own timer, or
  shows no UI rows.

## 9. Relation to certify

Certify has its own frame timing fields ([`certify.md`](certify.md) section 3.5.6 on branch
`dom/certify-4`): the arrival intervals of the rate window and of the take (`interval_p95_ms`,
`interval_max_ms`), the jitter near arrival from `frame_log`, and the open and close times of the
diagnostics D-6. These fields describe the camera and the clock, for a report that a developer
reads later. The capture timings describe the cost of each step of skellycam, live, for a person who
looks at the app. The two share no code and no field. The two use `perf_counter_ns` as one clock
for all processes of one system. A later certify check can switch `log_capture_times` on during its
take and keep a `record-only` row with the p95 of the slow steps (for example `jpeg_encode`,
`ring_write`, `fsync`), through `CameraGroupManager.capture_timings()`. That needs a decision of the
user and a change of the certify spec. This spec does not change certify [U Q587 17].

## 10. Tests

### 10.1 Kinds and helpers [U Q587 18]

- No test needs a camera.
- One injected clock: each test gives a virtual clock to `TimingControl`. Each bracket of the camera
  process, the source, the decode stage and the take writer reads it. A virtual clock can advance by
  a scripted value at each read, so a sample has an exact value. A test that counts clock reads
  counts the calls of this clock. The tile tests give a fake `now` to `TileTimings`.
- The camera loop tests drive `CameraLoop` with a fake source on the virtual clock, in the test
  process, as the 3a tests do. The window ends when the virtual clock passes
  `DIAGNOSTICS_INTERVAL_NS`. No test waits for a real second.
- A full recorder queue: `queue_size` 1 and a fake mux that waits on an event that the test sets. The
  sample is the difference of the virtual clock, not a real time. No test uses a real queue timeout.
- The websocket test sets `CAPTURE_TIMINGS_INTERVAL_S` to a small value and waits for the next
  message, with no fixed sleep.
- The Python tests go in `skellycam/tests/capture_timings/`. The tile tests go in
  `skellycam-ui/src/player/tests/unit/` (node) and `skellycam-ui/src/player/tests/browser/tile.spec.ts`
  (playwright). No new dependency.

### 10.2 Test list

| ID | What it proves | Camera |
|---|---|---|
| T-TIM-01 | Statistics: nearest-rank `p50_ms`, `p95_ms` and `max_ms` for known lists (n = 1, 2, 20, 512); `n` 0 gives `null` for the three; rounding to 0.001 ms. | no |
| T-TIM-02 | Window: a window takes the samples between two totals; more than 512 samples give the full `n` and statistics over the newest 512. | no |
| T-TIM-03 | Order of store and total: a writer thread stores the consecutive integers 1 to 200,000 in groups of 400 and waits for the reader after each group; the reader closes windows at the same time. Each window holds consecutive integers, and the windows join with no gap and no overlap. A writer that increases `total` before its store gives a gap or a wrong value, and the test fails. | no |
| T-TIM-04 | Default off: a new `CameraGroupManager` has `log_capture_times` False; each status of a new group has False; `reset_for_start` keeps the value; `capture_timings()` gives `log_capture_times` false and `summaries` []. | no |
| T-TIM-05 | Off costs no clock read: with the switch off, a camera loop on the virtual clock calls `TimingControl.clock()` zero times; `DiagnosticsMessage.timings` is None. | no |
| T-TIM-06 | On: a fake source whose steps take scripted virtual times gives a summary with each step of 5.4 that applies, the expected `n` and values, and the `kind`, `cadence` and `where` of table 3.1. | no |
| T-TIM-07 | Change while running: on, then off, then on, through `set_log_capture_times`; the summaries start and stop at the next publish; the fake source opens one time only. | no |
| T-TIM-08 | When a change takes effect: a change during the start-up applies at the publish at the end of the open; a change during a `take_end` wait applies at the first publish after it. A group made after a change to on starts on. | no |
| T-TIM-09 | Step sets: the Media Foundation fake has `camera_sample_copy` and no `jpeg_encode` or `opencv_retrieve`; the OpenCV fake is the reverse; with no BGR ring there is no `bgr_*` step; both have `exposure_search_brightness`. | no |
| T-TIM-10 | Brackets: `camera_wait` plus `opencv_retrieve` equals the time of the `_read` calls of the frame; calls with no frame add to the next frame; `gate_wait` holds no time of `_check_updates`, `_search_step` or `_publish_diagnostics` (each fake advances the clock by a known value); a frame with no refused pass gives 0. | no |
| T-TIM-11 | Retire: after a reopen, a new decode stage and a new take, the next summary holds the samples of the old instances; an old writer thread that writes after that writes only into its own set, and the `n` of the new set is exact. | no |
| T-TIM-12 | Recorder: scripted mux and fsync times give `mkv_mux`, `csv_row` and `fsync`; a full queue gives a `recorder_give` sample equal to the virtual wait; a take gives one `take_start`, one `take_end` and one `mkv_close`; `mkv_close` holds no time of the `mkv_mux`, `csv_row` and `fsync` of `_finish`; no take gives `n` 0. | no |
| T-TIM-13 | Decode thread: a fake decode of scripted time gives `bgr_decode` and `bgr_ring_write`; a BGR input gives no `bgr_decode` sample. | no |
| T-TIM-14 | Delay: `arrival_to_published` equals the end of the `ring_write` bracket minus `arrival_ns`. | no |
| T-TIM-15 | One reader: a call of `_fail` from another thread sends the last summary again with the same `seq` and reads no buffer; the next loop publish has `seq` + 1 and each sample one time. | no |
| T-TIM-16 | The publishes at the end of the open, at a failure on the loop thread and at the close carry `timings`; `seq` increases by 1 at each; `window_end_ns` increases. | no |
| T-TIM-17 | Size: the diagnostics message with all camera steps, the largest dict of T-UNX-70 and the summary stays under 32 KiB; the summary is under 4 KiB pickled. | no |
| T-TIM-18 | Python call: the newest summary of each camera of each open group; a summary older than 3 s (a fake main clock) and the summaries of a closed group are left out; a switch to off gives `summaries` [] at once; a watch thread that replaces `camera_timings` 10,000 times while the call reads gives no error. | no |
| T-TIM-19 | Websocket: messages of the fields of 6.1 at the patched interval; when off, the message of 6.4; with `PreviewRelay`, one `"preview"` summary for each camera with `preview_ring_read`, `preview_pack`, `preview_send` and `published_to_send`; with the interim relay, one more summary with `camera_id` `null` for `preview_pack` and `preview_send`; the send-lock wait is not in `preview_send`. | no |
| T-TIM-20 | Route: `POST /camera/timings` sets the switch and answers its value; a body with no boolean gets HTTP 422. | no |
| T-TIM-21 | Removal: `WebsocketMessageType` has `CAPTURE_TIMINGS` and no `PERFORMANCE_DATA`; the module `performance_data` does not import; `CameraGroupManager` has no `get_latest_performance_data`; `test_websocket_internals.py` still imports and runs `TestServerFramerateCalculator`. | no |
| T-TIM-22 | Step registry: the `STEPS` constant (id, kind, cadence, where) equals table 3.1 and table 8.5; each id in each summary of T-TIM-06, T-TIM-12, T-TIM-13, T-TIM-19 and T-TIM-26 is in `STEPS`. | no |
| T-TIM-23 | Budget: with the switch on, the camera loop calls `TimingControl.clock()` at most 10 times for each frame plus one time for each refused pass. Also a YUY2 camera with the fake Quick Sync encoder: at most 10 reads for each taken frame, and one `jpeg_encode` sample for each [U Q880]. | no |
| T-TIM-24 | One shape (node): the summary function of `tile/timings.ts` and the Python function give the same JSON for one shared fixture file of samples. | no |
| T-TIM-25 | Tile off (playwright): with `timings.on` false, a tile with a handle calls `now` zero times; `takeSummaries()` gives summaries with `n` 0; a tile with no handle works as today. | no |
| T-TIM-26 | Tile on (playwright): a fake decode seam and a fake `now` give `ui_jpeg_decode`, `ui_draw` and `receive_to_draw` with the expected values; an update with `image` gives no `ui_jpeg_decode`; a resize redraw and an overlay-only update give no `ui_draw`; a replaced message gives no sample; a second `takeSummaries()` with no new step gives `n` 0 and `seq` + 1. | no |

## 11. Build order

Each step has its tests first. The order starts after `dom/fix-lane-3` merges into
`dom/integration` [U Q571, Q587]. The capture side (steps 1 to 7) comes first; step 8 comes with
step 4b.

1. T-TIM-01 to T-TIM-03, T-TIM-22, and the Python part of T-TIM-24. Then the module
   `skellycam/core/capture_timings.py`: `STEPS`, `TimingControl`, `StepSamples`, `StepSet`, the
   summary function.
2. The switch: T-TIM-04, T-TIM-07, T-TIM-08 and T-TIM-20. The shared scalar of `CameraStatus`, the
   manager call and property, the route.
3. The camera loop: T-TIM-05, T-TIM-06, T-TIM-09, T-TIM-10, T-TIM-14 to T-TIM-17 and T-TIM-23. The
   steps of the loop thread, of the Media Foundation callback and of the OpenCV source; the field
   `DiagnosticsMessage.timings`; `seq` and `window_end_ns`; the one-reader rule.
4. The decode thread and the recorder thread: T-TIM-11 to T-TIM-13. The `StepSet` of each instance
   and the retire rule.
5. The main process: T-TIM-18. The snapshot swap in `_take_diagnostics`; `capture_timings()`.
6. The websocket: T-TIM-19 and T-TIM-21. The message; the `step_set` argument of the shared
   `CameraGroup` methods; the preview steps; the removal of `performance_data`; the message in
   `skellycam-docs/docs/technical/websocket-protocol.mdx`.
7. Measurement M-TIM-1, on the hardware of the user, not a test: the cost of the measurement with
   the switch on against off (the loop time of a frame and the capture lateness of ADR-8RES) at 4
   cameras, 1080p30. It also gives the first live numbers of the steps that table 3.1 marks "not
   measured". An evidence entry records it.
8. Built with step 4b [U Q586]: `skellycam-ui/src/player/tile/timings.ts`, the `timing` handle of the
   tile, `receivedAtMs` of `TileUpdate` and its stamp in `PreviewTiles`; T-TIM-24 (TypeScript part)
   to T-TIM-26.

## 12. Open questions for the user

No question is open. The questions of draft 1 are decided: Q580 to Q583 and Q586. The user accepted
the spec in Q587 (section 14).

## 13. Choices of the agent

[ADR-8Z0Q](../decisions/entries/8Z0Q-choices-of-the-capture-timings-spec.md) holds each choice with
the alternative that it rejects. The user accepted them as a set on 2026-11-23 [U Q587]. In short:

1. Transport: the field `timings` of `DiagnosticsMessage`, the Python call, one websocket message
   once per second from the loop of `_app_state_sender` (6.2 to 6.4).
2. The details of the switch: name, default, shared scalar not reset, the route body and 422, the
   effect at the next publish, and the three deliberate differences (section 2).
3. When off: the message still comes, `summaries` [] at once, the kept summaries go (2 item 5).
4. The kinds by the job of the step; disk calls and awaited calls are work; the field `cadence`
   (1.4).
5. The step ids, the values of `where`, the steps for each source (3.1, 5.4).
6. The brackets: no time is in two samples (an outer step subtracts its inner steps); the sums of
   `camera_wait` and `gate_wait`; the OpenCV split; `mkv_close` minus its enclosed steps (1.4, 3.1).
7. Threads: `TimingControl` with one clock; one `StepSet` for each writer instance; retire; one
   reader; the repeat from another thread; the snapshot swap; the `step_set` argument (5.1, 6.2).
8. Nearest-rank statistics, the window, `null` for `n` 0, the 512 rule (5.2).
9. The cost budget, with measured numbers (5.3).
10. The delays and their clocks; no change of the ring API; no delay from Python to the UI (4).
11. The preview steps in the wired sender; summaries for each connection; the group summary of the
    interim relay (6.5).
12. The 3 s age rule and the meaning of an absent camera (6.3).
13. Milliseconds with 3 decimals (5.2).
14. The parts left out, each with its measured number (3.2).
15. `seq`, `window_end_ns` and the version rule (6.1, 6.7).
16. The details of the tile timing: `TileTimings`, the handle in the third constructor argument,
    `receivedAtMs`, the pull by `takeSummaries()`, a draw only after a new image (section 7).
17. No reuse with certify now (section 9).
18. The test seams: one injected clock, no real sleep, no real queue timeout, `node --test` and
    playwright (10.1).

## 14. Decisions of the user

The user decided these items on 2026-11-23
([ADR-MX8V](../decisions/entries/MX8V-decisions-of-the-user-on-capture-timings.md)). For Q565 to
Q571 the user answered "agree to all". The user agreed Q576, Q577 and Q586. The user refused the
recommendation "always on" in Q578. For Q580 to Q583 the user answered "Q580-Q583 agree".

- **Q565.** The split of the work: skellycam measures and publishes; FreeMoCap displays. This spec
  covers the skellycam side and the interface that FreeMoCap reads.
- **Q566.** A fixed list of named steps. Each step that is codec work (a JPEG encode or decode, also
  the hidden decode in OpenCV `retrieve()`), and each other step that can take more than 1 ms, is in
  the list. A step known to be far below 1 ms can be left out, with the reason and the measured
  number.
- **Q567.** A step that is a wait (camera wait, gate wait, queue wait) is marked apart from a step
  that is work. Thus a display never adds waits into "time spent".
- **Q568.** skellycam does not send one event for each frame. Each process keeps the numbers of each
  step and publishes a summary once per second: for each camera and each step, `n`, p50, p95 and
  max, in milliseconds.
- **Q569.** One shared shape for each summary (capture process, recorder thread, main-process preview
  path, UI). Thus one display code path shows them all.
- **Q570.** An end-to-end delay is also given: from `arrival_ns` to `published_ns`, from
  `published_ns` to the start of the websocket send, and in the UI to the draw where the clocks
  permit it. The spec states the clock of each part, and the parts that cannot be compared across
  processes or machines.
- **Q571.** The spec now. The code only after the user accepts the spec and after branch
  `dom/fix-lane-3` merges.
- **Q576.** In FreeMoCap the capture steps appear as one "capture" block in the per-stage table of
  the Pipeline metrics window, fed by the summaries of each second. No per-frame bars in the
  timeline for capture steps.
- **Q577.** skellycam builds the measurement and the interface first. The FreeMoCap display is work
  of the freemocap session. It comes only after FreeMoCap moves to the new skellycam. Until then the
  numbers are readable from the skellycam websocket and a Python call. No display in skellycam-ui.
- **Q578.** Not always on. The words of the user: "this must be toggle-able like all other metrics
  in skellytracker". The measurement has an on and off switch. The details of the switch are agent
  choices (section 2, item 2 of section 13).
- **Q580.** `performance_data` goes, with its live inter-camera rows.
- **Q581.** One switch for the whole app (all groups and all cameras), not one switch for each
  camera.
- **Q582.** The route `POST /camera/timings`, together with the Python call.
- **Q583.** The interface note recommends that FreeMoCap sets the switch from its
  `log_pipeline_times`.
- **Q586.** The goal stands that the player and the 4b preview are built one time in skellycam, and
  the FreeMoCap UI takes a copy of the folder `skellycam-ui/src/player/` ([player 4.3], [4b 8]). No
  measurement in the two interim worker files, which step 4b replaces. The decode and draw timing goes
  into the shared tile module (`skellycam-ui/src/player/tile/`), behind the same switch, in the same
  summary shape, built together with step 4b. FreeMoCap gets it when it takes the folder.
- **Q587.** "Q587 agree": the user accepts this spec, with the choices of ADR-8Z0Q as a set. The
  build starts after `dom/fix-lane-3` merges into `dom/integration`: the capture side first, the
  tile part with step 4b ([ADR-8B85](../decisions/entries/8B85-acceptance-of-the-capture-timings-spec.md)).
