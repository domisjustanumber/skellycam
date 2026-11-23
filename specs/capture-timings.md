# Capture timings specification: the time of each slow step of the frame path, once per second

Status: draft 1 of 2026-11-23. It waits for the acceptance of the user. An agent wrote it. The user
decided Q565 to Q571 and Q576 to Q578 on 2026-11-23
([ADR-MX8V](../decisions/entries/MX8V-decisions-of-the-user-on-capture-timings.md)). Section 14 gives
each one. The choices of the agent are in section 13 and in
[ADR-8Z0Q](../decisions/entries/8Z0Q-choices-of-the-capture-timings-spec.md). They wait for the user.
Nothing in this spec is built. The code comes only after the user accepts this spec and after branch
`dom/fix-lane-3` merges [U Q571].

## 0. How to read this spec

Marks:

- **[U Qnnn]**: decision Qnnn of the user, 2026-11-23 (section 14).
- **[A n]**: choice n of the agent (section 13, and the same item number in ADR-8Z0Q).
- **[M source]**: measured; the source holds the result. **[NV]**: not verified.
- **[ring x.y]**, **[cap x.y]**, **[unix x.y]**, **[prv x.y]**, **[rec x.y]**: section x.y of
  [`frame-ring.md`](frame-ring.md), [`windows-capture.md`](windows-capture.md),
  [`unix-capture.md`](unix-capture.md), [`preview.md`](preview.md), [`recorder.md`](recorder.md).

The file and line citations are for commit c6532a21d of `dom/integration`. The build checks each
line again after the merge of `dom/fix-lane-3`. This spec uses British spelling.

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
| The summary shape, the Python call and the websocket message (section 6) | yes |
| The measurement in skellycam-ui (section 7): only the measurement and the summary, no display | yes [U Q577] |
| The interface note for the FreeMoCap session (section 8) | yes [U Q565, Q576] |
| The display in FreeMoCap | no. The freemocap session does it after FreeMoCap moves to the new skellycam [U Q577]. |

### 1.3 Non-goals

- One event for each frame to another process [U Q568].
- A display in skellycam-ui [U Q577].
- A per-frame bar in the FreeMoCap timeline for a capture step [U Q576].
- The times of an open or a close. The diagnostics keys D-6 (`t_*_ms`) give them [unix 4.6.2].
- The arrival intervals and the frame rate. `framerate_update` and certify give them (section 9).
- A new dependency. A configuration file [A 3].

### 1.4 Terms

- **Step.** One named part of the path of a frame, with a fixed id (section 3).
- **Work step.** A step in which the thread does the job itself. Disk input and output is work.
- **Wait step.** A step in which the thread waits for another part: the camera, the other cameras
  (the lockstep gate), the recorder queue or the network [U Q567] [A 5].
- **Window.** The time between two publishes of one summary, about 1 s [U Q568].
- **Summary.** For one camera (or one group) and one window: for each step, `n`, `p50_ms`,
  `p95_ms` and `max_ms` [U Q568]. One shape for each source of summaries [U Q569].
- **Delay.** A time from one point of the path of a frame to a later point, maybe in another
  process (section 4) [U Q570].

## 2. The switch [U Q578]

The user refused "always on": "this must be toggle-able like all other metrics in skellytracker"
[U Q578]. skellycam follows the pattern of skellytracker and FreeMoCap:

- skellytracker: `start_pipeline(..., timing_sink=..., timing="on")` and the config field
  `instrumentation.timing_spans` (default: empty, so no span is on). The run fixes its spans at the
  start (repository `skellytracker`, `skellytracker/core/pipelines/run.py` and
  `skellytracker/core/pipelines/_runtime/executor.py`). Each span costs one set look-up when off.
- FreeMoCap: `RealtimePipelineConfig.log_pipeline_times: bool = False`. The pipeline reads it at its
  start. A change applies when the real-time processing starts again (repository `freemocap`,
  `freemocap/core/pipeline/realtime/realtime_pipeline_config.py`).

The rules of skellycam [A 3]:

1. **Name and default.** `log_capture_times: bool`, default `False`, as `log_pipeline_times`.
2. **Where it lives.** `CameraGroupManager` holds the one value of the app. It is for all groups and
   all cameras. Each `CameraStatus` gets one shared scalar `log_capture_times`
   (`multiprocessing.Value("b", False, lock=False)`, as the other scalars of `CameraStatus`,
   [ADR-QJH6](../decisions/entries/QJH6-choices-of-the-fix-lane.md) item 3). The manager writes it into
   each status of a new group and at each change.
3. **How a host sets it.** Python: `CameraGroupManager.set_log_capture_times(on: bool) -> None`, and
   the read-only property `CameraGroupManager.log_capture_times`. HTTP: `POST /camera/timings` of
   `camera_router`, body `{"log_capture_times": true}`, answer `{"log_capture_times": true}`. A body
   with no boolean gets HTTP 422. FreeMoCap mounts `camera_router`, so the route is also there.
4. **A change while the cameras run.** Yes. The camera loop reads its shared scalar one time in each
   window, at the publish. The change applies at the next window, so within about 1 s. No camera
   opens again. The main process and the UI apply a change at their next window too.
5. **When it is off.** The camera process sends `timings = None` (section 6.2). The Python call and
   the websocket message give `"log_capture_times": false` and `"summaries": []`. The websocket
   message still comes once per second. Thus a display can show "timing off" [A 4].
6. **Cost when off.** One branch on a plain Python attribute (`StepTimes.on`) at each step. No clock
   read, no store.
7. **First window after a change to on.** It holds only the samples since the change. `window_s`
   gives the real length of the window.

## 3. The steps

### 3.1 The step table [U Q566]

`where` is the thread or the process that runs the step [A 5]: `camera_loop` (the loop thread of
the camera process), `camera_callback` (the Media Foundation callback thread of the camera process),
`decode_thread` (the BGR decode thread of the camera process), `recorder_thread` (the take writer
thread of the camera process), `main_process` (the preview sender on the event loop of the server),
`ui` (skellycam-ui). The ids are stable `snake_case` [A 5].

| id | kind | where | Code that the step wraps (commit c6532a21d) | Known cost | Platform |
|---|---|---|---|---|---|
| `camera_wait` | wait | `camera_loop` | `CameraLoop._read`: the call `self.source.read_frame(...)` (`skellycam/core/camera/capture/camera_loop.py:245`); on Media Foundation it waits in `CaptureWaitingPlace.take` (`skellycam/core/camera/capture/source.py:137-144`). One sample for each call that gives a frame. On the OpenCV source, the time of `retrieve()` is taken out (see `opencv_retrieve`) [A 6]. | Up to one frame period. Not measured as its own number. | all |
| `gate_wait` | wait | `camera_loop` | `CameraLoop._pass`: `should_grab_by_id` and `time.sleep(0.001)` (`camera_loop.py:229-231`). One sample for each frame: from the first refused pass to the pass that reads the frame; 0 when no pass was refused [A 7]. | Not measured in this loop. Prototype gate: median 0.03 to 6.4 ms for each camera [M `research/frame_ring_buffer/docs/frame_ring_buffer_report.md`, 5 cameras, 60 fps]. | all |
| `camera_sample_copy` | work | `camera_callback` | `MediaFoundationSource._frame`: `ConvertToContiguousBuffer`, `_copy` (`string_at`), `GetSampleTime`, the discontinuity flag and `FrameLog.add` (`skellycam/core/camera/capture/media_foundation/source.py:338-363`, `_copy` at `:413-420`). | Not measured. | Windows (Media Foundation) |
| `opencv_retrieve` | work | `camera_loop` | `OpenCVSource.read_frame`: `self._capture.retrieve()` between `pre_ns` and `post_ns` (`skellycam/core/camera/capture/opencv_source.py:84-86`). It holds the hidden MJPG decode of OpenCV. On Windows DirectShow, `grab()` returns at once, so this step also holds the camera wait [A 6]. | About 32 ms median at 720p on DirectShow, camera wait included [M `research/frame_ring_buffer/prototypes/results/p9_real_camera.md`]. The decode alone: not measured. | OpenCV source (Linux, macOS; Windows only with `SKELLYCAM_WINDOWS_CAPTURE=opencv`) |
| `jpeg_encode` | work | `camera_loop` | `CameraLoop._process`: `cv2.imencode(".jpg", image, JPEG_Q90)` (`camera_loop.py:506`). | 1.53 / 2.97 ms median at 720p / 1080p, q90 4:2:0 [M ring 11.1] | OpenCV source |
| `capture_check` | work | `camera_loop` | `check_jpeg` (`camera_loop.py:511`; `skellycam/core/ipc/frame_ring/capture_check.py:28-43`). With a DHT insertion, the `b"".join(...)` at `:43` copies the full frame. | Not measured alone. The 2a step with the encode and the check: median 1.81 to 1.87 ms, p95 3.39 to 3.41 ms [M `decisions/evidence/four-camera-timing-of-step-2a-20261118.md`]. | all |
| `frame_hash` | work | `camera_loop` | `CameraLoop._hash`: two SHA-256 and `dqt_segments` (`camera_loop.py:518-519`, `:908-912`). Only the first 30 frames after each trigger (D-11); `n` is 0 after them. | About 0.2 ms for 200 kB [NV, unix 4.6.1]. | all |
| `recorder_give` | wait | `camera_loop` | `CameraLoop._give` (`camera_loop.py:524`, `:713-730`) to `CameraTakeWriter._put` (`skellycam/core/take_recorder/camera_writer.py:145-162`). It waits when the queue is full. Only during a take; `n` is 0 with no take. | Longest wait 6.97 to 6.99 s in a 10 s disk stall test [M ADR-8RES]. Normal: not measured. | all |
| `ring_write` | work | `camera_loop` | `FrameRingWriter.write` of the JPEG ring: CRC-32 and the copy (`camera_loop.py:532`; `skellycam/core/ipc/frame_ring/writer.py:59-116`). | 600 kB: p50 185 µs, p99 224 µs in a tight loop; p99 744 µs paced by a sleep [M ring 14 item 66]. | all |
| `exposure_search_decode` | work | `camera_loop` | `CameraLoop._brightness`: `decode_jpeg(payload)` (`camera_loop.py:480`; `skellycam/core/ipc/frame_ring/decode.py:64-66`). About one sample for each search trial. Only when the payload is a JPEG; the OpenCV source uses its BGR image and has no such step. `n` is 0 with no search. | 2.60 / 5.42 ms median at 720p / 1080p [M ring 11.1] | Media Foundation (and each later native JPEG source) |
| `diagnostics_publish` | work | `camera_loop` | `CameraLoop._publish_diagnostics`: `source.diagnostics()`, `_loop_diagnostics()`, the build of this summary, `pickle.dumps` for the size check and the publish (`camera_loop.py:213-215`, `:937-952`). One sample for each window. The sample of a publish goes into the next window. | Not measured. | all |
| `bgr_decode` | work | `decode_thread` | `DecodeStage._to_bgr`: `cv2.imdecode` of a JPEG, or `cv2.cvtColor` of YUY2 or NV12 (`decode.py:122-128`). No sample for a BGR input, which needs no work. Only with a BGR ring. | 2.60 / 5.42 ms median [M ring 11.1]; 8 processes: 3.17 / 7.11 ms | all |
| `bgr_ring_write` | work | `decode_thread` | `writer.write(bgr, ...)` of the BGR ring (`decode.py:109-111`; `writer.py:59-116`). Only with a BGR ring. | 0.79 / 1.83 ms median, 1.24 / 2.46 ms p99 at 720p / 1080p [M ADR-ETJ1] | all |
| `mkv_mux` | work | `recorder_thread` | `self._mkv.mux(block, self._k)` (`camera_writer.py:290`; `skellycam/core/take_recorder/mkv.py:49`). | One write call: p50 0.01 ms, p99 0.09 to 0.10 ms, max 3.7 to 46 ms [M ADR-8RES] | all |
| `csv_row` | work | `recorder_thread` | `_write_row` up to the fsync check: `sidecar.row_line` and `_write_line` (`camera_writer.py:299-308`). | Not measured. | all |
| `fsync` | work | `recorder_thread` | `_fsync_both`: `os.fsync` of the MKV and of the CSV, once per second (`camera_writer.py:310-318`). | p50 2.0 to 2.1 ms, max 29 to 182 ms with 16 writers at 1080p60 [M ADR-8RES] | all |
| `preview_ring_read` | work | `main_process` | The ring read of the preview sender: `FrameRingReader.read` or `.read_newest` (`skellycam/core/ipc/frame_ring/reader.py:89`, `:134`), called by `PreviewRelay._newest_unsent` (`skellycam/api/websocket/preview_relay.py:161`) or by `CameraGroup.read_latest_ring_frames` (`skellycam/core/camera_group/camera_group.py:550-562`) [A 13]. | 0.08 / 0.25 ms median, 0.16 / 0.44 ms p99 at 720p / 1080p [M ADR-HDC9] | all |
| `preview_pack` | work | `main_process` | `pack_camera_frame` (`preview_relay.py:40-45`), or the build of the group message in `CameraGroup.get_latest_ring_payload` (`camera_group.py:564-597`) [A 13]. | `pack_camera_frame`: 0.005 / 0.11 ms median [M ADR-HDC9]. Group message: not measured. | all |
| `preview_send` | wait | `main_process` | `await self._send_bytes(message)` (`preview_relay.py:155`; `skellycam/api/websocket/websocket_server.py:98`, called at `:167`). It is an `await`: other tasks of the event loop run in it [A 5]. | 0.13 / 0.23 ms median, 0.63 / 1.11 ms p99 with compression off [M ADR-HDC9] | all |
| `ui_jpeg_decode` | work | `ui` | `createImageBitmap(blob, BITMAP_OPTIONS)` in the decode worker (`skellycam-ui/src/services/server/server-helpers/frame-processor/frame-decode.worker.ts:156`). One sample for each camera image. | Not measured live. The player `ImageDecoder`: 2.7 ms median at 1080p, 1 tile [M `decisions/evidence/1ACK-findings-of-the-6a-player-code.md`]. | all |
| `ui_draw` | work | `ui` | `ctx.transferFromImageBitmap(frame)` in the render worker (`skellycam-ui/src/services/server/server-helpers/offscreen-renderer.worker.ts:80`; the worker already times it at `:70` and `:85`). | Not measured live. The player draw at tile size: 0.4 to 0.5 ms [M same]. | all |

A summary holds only the steps that apply to its camera: its source, its BGR ring, its platform
(section 5.4). A step that applies but did not run in the window has `n` 0.

When step 4b replaces the UI decode and draw path, `ui_jpeg_decode` and `ui_draw` wrap the new
decode call and the new draw call. The ids stay [A 12].

### 3.2 Steps left out [U Q566] [A 14]

These parts of the frame path are left out. Each one is far below 1 ms, or it is not on the frame
path. The delay `arrival_to_published` (section 4) holds each part of the camera loop up to the ring
commit. Thus a slow part that this table leaves out still shows in that delay.

| Part | Code | Reason |
|---|---|---|
| The status update | `status.frame_count.value`, `status.replaced_count.value` (`camera_loop.py:540-541`) | Two stores of a shared scalar with no lock. Not measured. A ring header field read through `struct` takes 53 ns [M ring 2.1, study rank 13]. |
| The frame decision of the take | `should_record_frame_number` (`camera_loop.py:502`) | A lock with a short hold. Its longest wait (1.5 s, ADR-QJH6 item 3) is a fault case, and it shows in `arrival_to_published`. |
| The hand-over to the decode thread | `decode_stage.waiting_place.put(item)` (`camera_loop.py:537`) | A lock and a notify. Not measured [NV]. |
| The rate checks | `_feed_check`, `_feed_block` (`camera_loop.py:542`, `:546`) | Integer arithmetic for each frame. |
| The waiting place of the callback | `CaptureWaitingPlace.put` (`source.py:123-130`) | A lock and a notify, after `camera_sample_copy`. |
| The SOF parse of the recorder | `parse_sof(payload)` (`camera_writer.py:275`) | A parse of the header bytes, no decode. Not measured (ADR-8RES, last paragraph). |
| The control thread | `_ControlThread` (`camera_loop.py:979-1069`) | Not on the frame path. It reads the controls once per second. |
| The tick of the preview sender | `PreviewRelay._tick` (`preview_relay.py:178`) | Four times per second, not for each frame. Its ring reads are the same calls as `preview_ring_read`. |

## 4. End-to-end delays and clocks [U Q570] [A 11]

| id | where | From | To | Clock |
|---|---|---|---|---|
| `arrival_to_published` | `camera_loop` | `arrival_ns` of the frame | the end of the step `ring_write` | `time.perf_counter_ns`, one process |
| `published_to_send` | `main_process` | `published_ns` of the slot header (`FrameRead.published_ns`) | the start of `preview_send` | `time.perf_counter_ns`, two processes of one machine |
| `receive_to_draw` | `ui` | the `message` event of the websocket in the main thread of the UI | the end of `ui_draw` in the render worker | `performance.timeOrigin + performance.now()`, three contexts of one browser |

Rules:

- `arrival_ns` is the time of the Media Foundation callback, or the time just after `grab()` of
  OpenCV. It is not the time of the sensor. On Windows DirectShow, `grab()` returns at once, so
  `arrival_ns` is the call time [cap 4.2] [M `research/frame_ring_buffer/prototypes/results/p9_real_camera.md`].
- `arrival_to_published` uses the clock read at the end of `ring_write`. It is later than
  `published_ns` only by steps W4 to W7 of the ring write (a CRC of 60 bytes and four stores). Thus
  the ring API does not change [A 11].
- `time.perf_counter_ns` is one clock for all processes of one machine on Windows, Linux and macOS.
  The product already compares `arrival_ns` of different camera processes (the spread). Thus
  `published_to_send` is valid on one machine. It is not valid across machines.
- The clock of Python and the clock of the browser have different origins. Thus no delay goes from
  a point in Python to a point in the UI: the time from the start of the send to the receipt is not
  measured.
- `performance.now()` of a worker has the origin of that worker. `performance.timeOrigin +
  performance.now()` gives one base for the main thread and the workers of one page. The browser can
  make the value coarse (for example 0.1 ms). That is enough for a delay in milliseconds.
- A delay is a summary of the same shape as a step, in `delays`, not in `steps`. A display never
  adds a delay to the time of the steps.

## 5. Measurement

### 5.1 Samples [A 8]

- `StepSamples`: a fixed `array.array("q")` of `CAPACITY = 512` durations in nanoseconds, and an
  integer `total` of all samples since its creation. `add(duration_ns)` writes at `total % 512`,
  then increases `total`.
- One thread writes each `StepSamples`. The camera loop thread reads it at its publish.
- The reader keeps the `total` of its last read. The samples of the window are the samples from
  that `total` to the new `total`. The reader writes nothing into the buffer. Thus there is no
  reset and no race of a reset with the writer.
- `StepTimes`: one `StepSamples` for each step id that applies, and the flag `on`.
- The `CameraLoop` makes one `StepTimes` when it starts. It gives the same object to each source
  that it opens, to its `DecodeStage` and to each `CameraTakeWriter`. Thus a new open, a new decode
  stage or a new take loses no sample of the window.
- The main process preview sender and the UI workers each have their own `StepTimes`.
- With the GIL of Python 3.13 (the product build), a store into the array and the increase of
  `total` keep their order for the reader.

### 5.2 Window and statistics [U Q568] [A 9]

- The window of a camera is from one publish of `_publish_diagnostics` to the next one
  (`DIAGNOSTICS_INTERVAL_NS`, 1 s, `camera_loop.py:71`). The camera loop publishes also when the
  camera is paused or in `waiting` (`camera_loop.py:212-215`). The main process window is from one
  send of `capture_timings` to the next. The UI window is 1 s of `performance.now()`.
- `n` is the count of samples in the window.
- The percentile is the nearest rank: sort the samples of the window from low to high; `pq` is
  the sample at index `ceil(q * n) - 1`. `p50_ms` uses q = 0.5; `p95_ms` uses q = 0.95. `max_ms` is
  the largest sample.
- When `n` is 0: `p50_ms`, `p95_ms` and `max_ms` are `null`. The step stays in the summary.
- When `n` is more than 512: `n` is the full count; `p50_ms`, `p95_ms` and `max_ms` use the newest
  512 samples. At 120 frames per second a step for each frame gives 120 samples in a window.
- Each `_ms` value is a float in milliseconds, rounded to 0.001 ms.
- The statistics are computed once per window, by the publisher. No sample is sent.

### 5.3 Cost budget of the measurement [A 10]

- When off: one branch for each step, as section 2 item 6. No clock read.
- When on, the camera loop thread reads `perf_counter_ns` at most 10 times for each frame. Adjacent
  steps share one read: the end of a step is the start of the next one. The gate wait uses the read
  that exists at `camera_loop.py:231`. The OpenCV source uses its existing `pre_ns` and `post_ns`.
- When on, each other thread reads the clock at most 2 times for each step.
- No list, dict or other container grows for each frame. The buffers have a fixed size.
- The sort and the percentiles run once per window: one sort of at most 512 integers for each step
  and each delay of the summary.
- The summary of one camera with all steps is at most 4 KiB pickled. The diagnostics message of a
  camera has a limit of 32 KiB, and the largest dict today is about 14 kB [unix 4.2]. Thus the
  summary fits in the message.
- The cost of one `perf_counter_ns` call is not measured [NV]. Measurement M-TIM-1 (section 11)
  measures the cost of the measurement on the real path.

### 5.4 Steps that apply

| Condition | Steps |
|---|---|
| Each camera | `camera_wait`, `gate_wait`, `capture_check`, `frame_hash`, `recorder_give`, `ring_write`, `diagnostics_publish`, `mkv_mux`, `csv_row`, `fsync` |
| Media Foundation source | also `camera_sample_copy`, `exposure_search_decode` |
| OpenCV source | also `opencv_retrieve`, `jpeg_encode` |
| A BGR ring | also `bgr_decode`, `bgr_ring_write` |
| The preview sender of a connection | `preview_ring_read`, `preview_pack`, `preview_send` |
| skellycam-ui | `ui_jpeg_decode`, `ui_draw` |

A later native source (Linux V4L2, macOS AVFoundation) gets the steps of the Media Foundation
source. Its callback copy step, if it has one, uses `camera_sample_copy` [A 5].

## 6. Publication

### 6.1 The summary shape [U Q569]

One summary has these fields. It is the same shape for each source [U Q569].

| Field | Type | Meaning |
|---|---|---|
| `source` | `"camera"` \| `"preview"` \| `"ui"` | Who made the summary. |
| `camera_group_id` | string or `null` | The group. `null` in the UI when the UI does not know it. |
| `camera_id` | string or `null` | The camera. `null` for a step of the whole group: the group message of the interim relay (section 6.5). |
| `clock` | `"perf_counter_ns"` \| `"performance.now"` | The clock of the durations. |
| `window_s` | float | The real length of the window, in seconds, 3 decimals. |
| `steps` | object | Step id to step entry. |
| `delays` | object | Delay id to delay entry. |

A step entry: `{"kind": "work" | "wait", "where": <where>, "n": int, "p50_ms": float | null,
"p95_ms": float | null, "max_ms": float | null}`. A delay entry has the same fields, with no `kind`;
its `where` is the place of its end point.

### 6.2 Camera process to main process [A 1]

- `DiagnosticsMessage` (`skellycam/core/ipc/pubsub/pubsub_topics.py:42-47`) gets one field:
  `timings: dict | None = None`. It holds the summary of the camera for the window that just ended,
  or `None` when the switch is off.
- The message goes with each publish of the diagnostics, on the topic `TopicTypes.DIAGNOSTICS`.
  No new topic, no new queue, no new pipe.
- The diagnostics dict does not change. The `timings` field is not in it. Thus the D-keys of
  [unix 4.6.2], the counter subset and certify do not change.
- The diagnostics publish at the end of an open, at a failure and at the close also carries
  `timings`. A summary of a window shorter than 1 s is valid: `window_s` gives its length.
- `CameraGroup._take_diagnostics` (`camera_group.py:491-502`) keeps the newest `timings` of each
  camera, and the main-process time at which it came.

### 6.3 The Python call [A 1] [A 15]

`CameraGroupManager.capture_timings() -> dict` gives:

```python
{"version": 1, "log_capture_times": bool, "summaries": [<summary>, ...]}
```

- One summary for each camera of each open group, the newest one. Only `source` `"camera"`.
- It leaves out a summary that came more than 3 s ago, and each summary of a closed group.
- It reads no ring and no shared memory. It never raises for a missing camera. It is safe to call
  from any thread of the main process.
- FreeMoCap calls it (section 8).

### 6.4 The websocket message [A 1] [A 2]

- A new JSON message kind: `capture_timings` (`WebsocketMessageType.CAPTURE_TIMINGS`).
- The loop of `_app_state_sender` (`websocket_server.py:264`) sends it once per second, after the
  app state check. No new task.
- The body is the body of `capture_timings()`, plus `"message_type": "capture_timings"`, plus the
  summary of the preview sender of this connection (`source` `"preview"`), when the switch is on.
- When the switch is off, the message is
  `{"message_type": "capture_timings", "version": 1, "log_capture_times": false, "summaries": []}`.
- **`performance_data` goes** [A 2]: the module `skellycam/api/websocket/performance_data.py`,
  `CameraGroupManager.get_latest_performance_data`, `WebsocketMessageType.PERFORMANCE_DATA` and the
  classes `TestPerformanceDataHelpers` and `TestExtractPerformanceData` of
  `skellycam/tests/test_websocket_internals.py`. No code sends it, and skellycam-ui has no handler
  for it. Its row `arrival_to_published_ms` becomes the delay `arrival_to_published`. Its row
  `sample_to_arrival_ms` is in the diagnostics keys D-2 of each camera. Its inter-camera rows
  (`grab_range_ms`, `grab_stddev_ms`) have no live successor; the stop response keeps
  `inter_camera_grab_range_ms_stats` (open question 1). Item 5 of [ring 14] said that the
  performance page reads only the slot-header times "until phase 4". `read_latest_ring_frames`
  stays for the interim relay [prv 2.3].

### 6.5 The preview sender [A 13]

- The preview sender that is wired measures `preview_ring_read`, `preview_pack`, `preview_send` and
  `published_to_send`: the per-camera `PreviewRelay` after step 4b, or the interim
  `_frontend_image_relay` before it.
- With `PreviewRelay`, each step is for one camera. With the interim relay, `preview_ring_read` is
  for one camera, and `preview_pack` and `preview_send` are for the group (`camera_id` `null`);
  `published_to_send` uses the `published_ns` of each camera of the group message.
- Each connection has its own summary. Only the message of that connection carries it. The Python
  call does not carry it.

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
      "window_s": 1.0,
      "steps": {
        "camera_wait": {"kind": "wait", "where": "camera_loop", "n": 30, "p50_ms": 31.912, "p95_ms": 33.105, "max_ms": 34.877},
        "gate_wait": {"kind": "wait", "where": "camera_loop", "n": 30, "p50_ms": 0.0, "p95_ms": 1.071, "max_ms": 1.982},
        "camera_sample_copy": {"kind": "work", "where": "camera_callback", "n": 30, "p50_ms": 0.041, "p95_ms": 0.077, "max_ms": 0.130},
        "capture_check": {"kind": "work", "where": "camera_loop", "n": 30, "p50_ms": 0.015, "p95_ms": 0.020, "max_ms": 0.031},
        "frame_hash": {"kind": "work", "where": "camera_loop", "n": 0, "p50_ms": null, "p95_ms": null, "max_ms": null},
        "recorder_give": {"kind": "wait", "where": "camera_loop", "n": 30, "p50_ms": 0.004, "p95_ms": 0.006, "max_ms": 0.011},
        "ring_write": {"kind": "work", "where": "camera_loop", "n": 30, "p50_ms": 0.092, "p95_ms": 0.140, "max_ms": 0.410},
        "exposure_search_decode": {"kind": "work", "where": "camera_loop", "n": 0, "p50_ms": null, "p95_ms": null, "max_ms": null},
        "diagnostics_publish": {"kind": "work", "where": "camera_loop", "n": 1, "p50_ms": 0.620, "p95_ms": 0.620, "max_ms": 0.620},
        "mkv_mux": {"kind": "work", "where": "recorder_thread", "n": 30, "p50_ms": 0.031, "p95_ms": 0.090, "max_ms": 0.240},
        "csv_row": {"kind": "work", "where": "recorder_thread", "n": 30, "p50_ms": 0.012, "p95_ms": 0.020, "max_ms": 0.035},
        "fsync": {"kind": "work", "where": "recorder_thread", "n": 1, "p50_ms": 2.050, "p95_ms": 2.050, "max_ms": 2.050}
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
      "window_s": 1.001,
      "steps": {
        "preview_ring_read": {"kind": "work", "where": "main_process", "n": 30, "p50_ms": 0.081, "p95_ms": 0.150, "max_ms": 0.300},
        "preview_pack": {"kind": "work", "where": "main_process", "n": 30, "p50_ms": 0.005, "p95_ms": 0.012, "max_ms": 0.020},
        "preview_send": {"kind": "wait", "where": "main_process", "n": 30, "p50_ms": 0.130, "p95_ms": 0.580, "max_ms": 0.900}
      },
      "delays": {
        "published_to_send": {"where": "main_process", "n": 30, "p50_ms": 4.100, "p95_ms": 11.200, "max_ms": 13.050}
      }
    }
  ]
}
```

The summaries of camera `c3d4` and its preview summary have the same form. They are left out of
the example.

### 6.7 Version [A 17]

- `version` is 1 for this spec.
- A new step id, a new delay id or a new field does not change `version`. A display must show a
  step id that it does not know, with the id as its label.
- A change of a field name, a unit, a type or the meaning of a field or of a step id increases
  `version` by one. A display that sees a `version` that it does not know shows no numbers and says
  so.

## 7. skellycam-ui [A 12]

- Only the measurement and the summary. No display [U Q577].
- The flag: the UI reads `log_capture_times` of each `capture_timings` message. The main thread
  sends `{type: "timings", on}` to the decode worker and the render worker when it changes. Off is
  the default until the first message.
- The decode worker measures `ui_jpeg_decode` around `await createImageBitmap(...)` with
  `performance.now()`. The render worker measures `ui_draw` around `transferFromImageBitmap`. The
  existing `stats` and the `console.warn` "Slow frame" of the render worker stay.
- `receive_to_draw`: the main thread stamps `performance.timeOrigin + performance.now()` on the
  payload at its `message` event. The stamp goes with the payload to the decode worker, with the
  bitmaps to the main thread, and with each bitmap to the render worker. The render worker computes
  the delay at the end of `ui_draw`. A frame that the newest-wins rule drops gives no sample.
- Each worker keeps its own fixed buffers (a `Float64Array` of 512 values and a total, as
  section 5.1). Once per second it computes its summary with the same rules as section 5.2 and posts
  it to the main thread. The main thread keeps the newest summary of each worker in a small store
  (`captureTimingsStore`, one module). A later display or a test reads it.
- One summary for each camera of the UI: `source` `"ui"`, `clock` `"performance.now"`. The
  `camera_group_id` is `null` when the frame header has no group.
- The UI does not send its summaries to the server.
- The summary function of the UI (TypeScript) and the summary function of Python give the same
  output for the same samples. A shared fixture file proves it (T-TIM-19).

## 8. Interface note for FreeMoCap

This section is for the freemocap session. It can be read alone.

### 8.1 What FreeMoCap must know

- **When.** FreeMoCap imports the old skellycam today: its `pyproject.toml` points `skellycam` at the
  local checkout of `skellycam-sfn26-pins`, "until freemocap moves to skellycam's frame-ring API".
  That skellycam has no capture timings. Thus the display can come only after FreeMoCap moves to the
  frame-ring API of skellycam [U Q577].
- **Switch.** `CameraGroupManager.set_log_capture_times(on: bool)`; read it with
  `CameraGroupManager.log_capture_times`. Default `False`. It can change while the cameras run; it
  applies within about 1 s. HTTP: `POST /camera/timings` with `{"log_capture_times": bool}` on the
  mounted `camera_router`. Recommendation: FreeMoCap sets it from `log_pipeline_times` when a
  real-time pipeline starts, and sets it off when the pipeline stops. Then the user has one switch
  (open question 4).
- **Read.** `CameraGroupManager.capture_timings()` gives
  `{"version": 1, "log_capture_times": bool, "summaries": [...]}`. Call it once per second, for
  example in the relay that builds the `pipeline_timing` message. Each summary is new at most once
  per second.
- **Summary.** `source` (`"camera"` from this call), `camera_group_id`, `camera_id`, `clock`
  (`"perf_counter_ns"`), `window_s`, `steps`, `delays`. A step entry: `kind` (`"work"` or `"wait"`),
  `where`, `n`, `p50_ms`, `p95_ms`, `max_ms`. A delay entry: the same, with no `kind`.
- **Units.** Milliseconds, float, 3 decimals. `n` is a count of samples in the window. `window_s`
  is seconds.
- **Clock.** `time.perf_counter_ns` of the camera process. This is the clock of FreeMoCap
  `PipelineTimingEvent` (`clock_domain` `"perf_counter"`) on the same machine. The delay
  `arrival_to_published` is in one process. No value compares clocks of two machines.
- **`null`.** `p50_ms`, `p95_ms` and `max_ms` are `null` when `n` is 0: the step applies to the
  camera, but it did not run in the window (for example `fsync` with no take, `frame_hash` after its
  30 frames). An absent step id means that the step does not apply to that camera (for example
  `jpeg_encode` on Media Foundation).
- **Off.** `"log_capture_times": false` and `"summaries": []`. Show "capture timing off".
- **Version.** Section 6.7. Show an unknown step id with its id. Show no numbers for an unknown
  `version`.
- **Step ids and labels.** The table of 3.1. FreeMoCap can give each id a label in its
  `pipelineTaskTopology.ts`.

### 8.2 What the FreeMoCap display must do [U Q576]

- Show the capture steps as one "capture" block in the per-stage table of the Pipeline metrics
  window, fed by the summaries. No per-frame bar in the timeline for a capture step.
- One row for each camera and step: label, `p50_ms`, `p95_ms`, `max_ms`, and `n` in the window. The
  table of today has the columns "ms/frame" (mean), "FPS", "range" and "frames". A summary has no
  mean and no minimum. Thus the capture block needs its own columns, or it shows `p50_ms` as
  "ms/frame" and `max_ms` as the top of the range. The freemocap session decides.
- Never add a `wait` step or a delay into a sum of "time spent". The sum of the `work` steps of one
  `where` is the time that this thread spends on the frame.
- Show the delays apart, for example as one line for each camera: "arrival to ring p50 / p95".
- FreeMoCap measures its own preview path, its own JPEG decode and its own draw in freemocap-ui with
  its own timer. FreeMoCap does not use the skellycam websocket.

## 9. Relation to certify

Certify has its own frame timing fields ([`certify.md`](certify.md) section 3.5.6 on branch
`dom/certify-4`): the arrival intervals of the rate window and of the take (`interval_p95_ms`,
`interval_max_ms`), the jitter near arrival from `frame_log`, and the open and close times of the
diagnostics D-6. These fields describe the camera and the clock, for a report that a developer
reads later. The capture timings describe the cost of each step of skellycam, live, for a person who
looks at the app. The two share no code and no field. The two use `perf_counter_ns` as one clock
for all processes of one system. A later certify check can turn `log_capture_times` on during its
take and keep a `record-only` row with the p95 of the slow steps (for example `jpeg_encode`,
`ring_write`, `fsync`), through `CameraGroupManager.capture_timings()`. That needs a decision of the
user and a change of the certify spec. This spec does not change certify.

## 10. Tests

### 10.1 Kinds and helpers

- No test needs a camera. Each test uses the fake sources, the virtual clock (the module name
  `perf_counter_ns` of `camera_loop.py`, ADR-HP7D item 12), the `clock` of `CameraTakeWriter`, the
  `decode` seam of `DecodeStage`, the fake rings of the preview tests
  (`skellycam/tests/preview/preview_helpers.py`), or a fake `performance.now` in the UI.
- The Python tests go in `skellycam/tests/capture_timings/`. The UI tests go next to the UI code,
  run by `vitest`.

### 10.2 Test list

| ID | What it proves | Camera |
|---|---|---|
| T-TIM-01 | Statistics: nearest-rank `p50_ms`, `p95_ms` and `max_ms` for known lists (n = 1, 2, 20, 512); `n` 0 gives `null` for the three; rounding to 0.001 ms. | no |
| T-TIM-02 | Window: a sample goes into exactly one window; a window takes the samples between two totals; more than 512 samples in a window give the full `n` and statistics over the newest 512. | no |
| T-TIM-03 | Single writer: a writer thread adds 100,000 samples while the reader closes windows in a loop; the sum of `n` over all windows equals the number of samples. | no |
| T-TIM-04 | Default off: a new `CameraGroupManager` has `log_capture_times` False; each camera status of a new group has False; `capture_timings()` gives `log_capture_times` false and `summaries` []. | no |
| T-TIM-05 | Off costs no clock read: with the switch off, a fake-source camera loop on the virtual clock reads the clock the same number of times for each frame as a loop with no timing code (count of the calls of the fake clock); `DiagnosticsMessage.timings` is None. | no |
| T-TIM-06 | On: a fake source whose steps take known virtual times gives a summary with each step of 5.4 that applies, the expected `n`, the expected values and the `kind` and `where` of table 3.1. | no |
| T-TIM-07 | Change while running: on, then off, then on again, through `set_log_capture_times`; the summaries start and stop within one window; no camera opens again (the open count of the fake source stays 1). | no |
| T-TIM-08 | A new group after a change to on starts with the switch on. | no |
| T-TIM-09 | Step sets: the Media Foundation fake has `camera_sample_copy` and `exposure_search_decode` and no `jpeg_encode` or `opencv_retrieve`; the OpenCV fake is the reverse; with no BGR ring there is no `bgr_*` step. | no |
| T-TIM-10 | OpenCV split: `camera_wait` plus `opencv_retrieve` equals the time of `read_frame` for each frame; `opencv_retrieve` uses `retrieve_ns`. | no |
| T-TIM-11 | Gate wait: a frame after three refused passes gives one sample equal to the time from the first refusal to the read; a frame with no refusal gives 0. | no |
| T-TIM-12 | Recorder: a take with a slow fake mux and a slow fake fsync gives `mkv_mux`, `csv_row` and `fsync` with the expected values; a full queue gives a `recorder_give` sample equal to the wait; no take gives `n` 0 for the four; the samples of the last window of a take are kept after `end`. | no |
| T-TIM-13 | Decode thread: a fake decode of known time gives `bgr_decode` and `bgr_ring_write`; a BGR input gives no `bgr_decode` sample. | no |
| T-TIM-14 | Delay: `arrival_to_published` equals the end of `ring_write` minus `arrival_ns`, on the virtual clock. | no |
| T-TIM-15 | Size: the diagnostics message with the largest step set and the largest dict of T-UNX-70 stays under 32 KiB; the summary alone is under 4 KiB pickled. | no |
| T-TIM-16 | Python call: `capture_timings()` gives the newest summary of each camera of each open group; it leaves out a summary older than 3 s and each summary of a closed group; it never raises for a camera with no summary. | no |
| T-TIM-17 | Websocket: a test client gets one `capture_timings` message each second with the fields of 6.1; when off, the message of 6.4 with `summaries` []; with the preview sender, one `"preview"` summary for each camera with `preview_ring_read`, `preview_pack`, `preview_send` and `published_to_send`. | no |
| T-TIM-18 | Route: `POST /camera/timings` sets the switch and answers its value; a body with no boolean gets HTTP 422. | no |
| T-TIM-19 | One shape: a shared fixture file of samples gives the same summary JSON from the Python function and from the TypeScript function. | no |
| T-TIM-20 | UI off: with `on` false, the decode worker and the render worker read `performance.now()` no more times than today and post no summary. | no |
| T-TIM-21 | UI on: a fake `createImageBitmap` and a fake draw of known time give `ui_jpeg_decode`, `ui_draw` and `receive_to_draw` with the expected values in `captureTimingsStore`. | no |
| T-TIM-22 | Removal: `WebsocketMessageType` has `CAPTURE_TIMINGS` and no `PERFORMANCE_DATA`; the module `performance_data` does not import; `CameraGroupManager` has no `get_latest_performance_data`. | no |
| T-TIM-23 | Step registry: the `STEPS` constant (id, kind, where) equals table 3.1; each id in each summary of T-TIM-06, T-TIM-12, T-TIM-13 and T-TIM-17 is in `STEPS`. | no |
| T-TIM-24 | Budget: with the switch on, the camera loop thread reads the fake clock at most 10 more times for each frame than with the switch off. | no |

## 11. Build order

Each step is small and has its tests first. The order starts after the user accepts this spec and
after `dom/fix-lane-3` merges [U Q571].

1. The failing tests T-TIM-01 to T-TIM-03, T-TIM-19 (Python part) and T-TIM-23. Then the module
   `skellycam/core/capture_timings.py`: `STEPS`, `StepSamples`, `StepTimes`, the summary function.
2. The switch: T-TIM-04, T-TIM-07, T-TIM-08 and T-TIM-18; the shared scalar of `CameraStatus`, the
   manager call and property, the route.
3. The camera loop: T-TIM-05, T-TIM-06, T-TIM-09 to T-TIM-11, T-TIM-14, T-TIM-15 and T-TIM-24; the
   steps of the loop thread, of the Media Foundation callback and of the OpenCV source, and the
   field `DiagnosticsMessage.timings`.
4. The decode thread and the recorder thread: T-TIM-12 and T-TIM-13.
5. The main process: T-TIM-16; `_take_diagnostics` keeps the summaries; `capture_timings()`.
6. The websocket: T-TIM-17 and T-TIM-22; the message, the preview steps, the removal of
   `performance_data`, and the message in `skellycam-docs/docs/technical/websocket-protocol.mdx`.
7. skellycam-ui: T-TIM-19 (TypeScript part), T-TIM-20 and T-TIM-21.
8. Measurement M-TIM-1, on the hardware of the user, not a test: the cost of the measurement with
   the switch on against off (the camera loop time of a frame and the capture lateness of ADR-8RES)
   at 4 cameras, 1080p30. It also gives the first live numbers of the steps that table 3.1 marks
   "not measured". An evidence entry records it.

## 12. Open questions for the user

Each question is worded so that "yes" accepts the recommendation.

1. Remove `performance_data` together with its live inter-camera rows (`grab_range_ms`,
   `grab_stddev_ms`)? The stop response keeps `inter_camera_grab_range_ms_stats` for each take. Yes?
2. One switch for the whole app (all groups and all cameras), not one switch for each camera. Yes?
3. One HTTP route `POST /camera/timings`, so that a client of the websocket, or freemocap-ui, can
   switch the timings on without Python. Yes?
4. The interface note recommends that FreeMoCap sets `log_capture_times` from its
   `log_pipeline_times` at each pipeline start, so that its user has one switch. Yes?

## 13. Choices of the agent

[ADR-8Z0Q](../decisions/entries/8Z0Q-choices-of-the-capture-timings-spec.md) holds each choice with
the alternative that it rejects. In short:

1. Transport: the field `timings` of `DiagnosticsMessage`, the Python call `capture_timings()`, one
   websocket message `capture_timings` once per second (sections 6.2 to 6.4).
2. `performance_data` goes. `capture_timings` replaces it (6.4).
3. The switch `log_capture_times`: default off, held by the manager, one shared scalar in each
   camera status, applied at the next window, set by Python or by one route (section 2).
4. When off, the message still comes once per second, with `summaries` [] (section 2 item 5).
5. The step ids, the two kinds, the definition of a wait, disk work is work, `preview_send` is a
   wait, the values of `where` (sections 1.4, 3.1, 5.4).
6. The OpenCV split: `camera_wait` without `opencv_retrieve` (3.1).
7. One `gate_wait` sample for each frame, 0 when no pass was refused (3.1).
8. Fixed buffers of 512 samples, one writer thread for each buffer, windows by totals, the loop
   owns the buffers (5.1).
9. Nearest-rank percentiles, the window of the publish, `null` when `n` is 0 (5.2).
10. The cost budget (5.3).
11. The delays and their clocks; no change of the ring API; no delay from Python to the UI
    (section 4).
12. The UI measurement in the two workers, posted once per second to a store, not sent to the
    server (section 7).
13. The preview steps in the sender that is wired; one summary for each connection (6.5).
14. The steps left out (3.2).
15. The Python call leaves out a summary older than 3 s and the summaries of a closed group (6.3).
16. Units: milliseconds, 3 decimals (5.2).
17. The version rule (6.7).
18. The recommendation to FreeMoCap: one switch with `log_pipeline_times` (8.1).
19. No reuse with certify now (section 9).

## 14. Decisions of the user

The user decided these items on 2026-11-23
([ADR-MX8V](../decisions/entries/MX8V-decisions-of-the-user-on-capture-timings.md)). For Q565 to
Q571 the user answered "agree to all". Q576 and Q577 the user agreed. Q578 the user refused the
recommendation "always on".

- **Q565.** The split of the work: skellycam measures and publishes; FreeMoCap displays. This spec
  covers the skellycam side and the interface that FreeMoCap reads.
- **Q566.** A fixed list of named steps. Each step that is codec work (a JPEG encode or decode, also
  the hidden decode in OpenCV `retrieve()`), and each other step that can take more than 1 ms, is in
  the list.
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
  choices (section 2, item 3 of section 13).
