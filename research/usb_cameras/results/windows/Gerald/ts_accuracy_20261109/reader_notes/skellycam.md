# skellycam development-streaming: what timestamps it writes, and what a backend change would touch

Code read: skellycam `development-streaming` @ `169caf63` (2026-10-18), the snapshot freemocap pins. Paths are relative to the skellycam repo root unless prefixed `freemocap/`.
Labels: **measured** (a result file supports it), **code** (read from source), **inferred** (reasoned, not tested).
Harness for the one measured item: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad/notes/harness/iso8601_double_offset.py` (run line in its docstring), output in `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad/notes/harness/iso8601_double_offset.out.txt`. No camera was opened for this report.

## 0. Summary

- **The timing model is the same as the code the 11-08 review read.** Of the 72 files that differ, none changes how a frame gets its stamp. The changes are shutdown/error handling, startup-failure reporting, playback, and a new timing *reader* (code; old-vs-new `diff`, §3).
- **One stamp per frame:** the midpoint of `perf_counter_ns()` taken just before and just after `cap.grab()` (`core/timestamps/numpy_timestamps/create_camera_csvs.py:50-51`). On OpenCV DirectShow `grab()` does nothing (11-08 review §2.3, `cap_dshow.cpp`). The loop takes it right after the lockstep gate opens, so **in practice the stamp is the gate-open time** (code + inferred).
- **That stamp now reaches freemocap directly.** The new `recording_timing_reader.py` reads `timestamp.from_recording_start.sec` (grab midpoint minus recording start) from the per-camera CSV. freemocap's playback, post-hoc video node and reconstruction timing all call it (code; §2.4).
- **Equal frame counts are enforced in at least 12 places**, from the capture gate to the finaliser, the shared-memory reader and freemocap's realtime nodes. Cameras cannot run at different rates. A dropped hardware frame is invisible: the loop index is not a camera frame index (code; §4).
- **The local ISO 8601 double-offset bug is still there** (`core/timestamps/timebase_mapping.py:31`, `:42`). **measured**: at UTC−5, a true 06:06 is written as 01:06 in the per-camera CSV and as 06:06 in the multiframe CSV.
- **New findings (code; size inferred):**
  - The frame rate given to the video writer is measured over only part of each loop iteration, so it reads high (§2.6).
  - The "frame-rate reset" times shm-copy + video-write, not the frame interval (§1.6).
  - If one camera dies mid-recording, finalisation can fail its equal-count check (§4.3).
- **Swapping in an MF raw-MJPEG backend:**
  - *Decode at source:* if the capture process decodes the JPEG into the existing BGR slot, the change stays inside about 12 capture/config/detection modules plus the metadata dtype and CSV writers.
  - *JPEG end to end:* carrying JPEG bytes through shared memory changes about 8 more skellycam modules and 3–4 freemocap realtime modules.
  - *Different rates or real drops:* allowing either one also needs the 12+ equal-count sites in §4 rewritten (§5).

## 1. Capture path on Windows

### 1.1 Backend
- `core/camera/determine_backend.py:29-42`: `cv2.CAP_DSHOW` on Windows (code). The comment at 34–35 and 39 still claims DSHOW honours `CAP_PROP_BUFFERSIZE` and MSMF does not. OpenCV DSHOW has no `CAP_PROP_BUFFERSIZE` setter (11-08 review §2.1).
- The worker target is hard-wired to OpenCV: `core/camera/camera_worker.py:7, 51` (`target=opencv_camera_worker_method`). There is no backend abstraction (code).

### 1.2 VideoCapture setup order
`core/camera/opencv/opencv_helpers/create_cv2_video_capture.py` (code):

| Step | Line | Notes |
| --- | --- | --- |
| `cv2.VideoCapture(index, CAP_DSHOW)`, 5 retries 1 s apart | 35–50 | |
| `CAP_PROP_FOURCC = MJPG` | 57–58 | default `capture_fourcc="MJPG"` (`core/camera/config/camera_config.py:28`) |
| width, height | 59–60 | default 1280x720 (`camera_config.py:16-17`) |
| `CAP_PROP_FPS` only if `framerate > 0` | 61–62 | default `-1.0` (`camera_config.py:26`), so normally never set |
| `CAP_PROP_BUFFERSIZE = 1` | 66 | rejected by DSHOW; only logs at debug |
| first `read()` | 75 | retried |
| `apply_camera_configuration` | 92–94 | see below |

Then `opencv_helpers/opencv_apply_config.py:71-85`:
1. Exposure. Manual `-7` by default (`camera_config.py:24-25`); Linux forces auto (29–35).
2. Width and height again.
3. FPS skipped (`should_apply_framerate = False`, line 62).
4. **FOURCC again**.

The final order is FOURCC → size → read → size → FOURCC. This is the sequence the 11-08 review flagged as a plausible route to MJPG at ~10 fps; it is still untested on the real code path. `extract_config_from_cv2_capture` (`opencv_extract_config.py:21-24`) then sets `config.framerate = CAP_PROP_FPS`, the nominal rate of the negotiated format.

### 1.3 Pre-loop
`setup_opencv_camera_loop.py:58-60`: until all cameras are ready, each camera calls `read()` + `sleep(10 ms)` to keep its buffer drained. The first `frame_number` is `-1` (`create_initial_frame_recarray.py:14`) (code).

### 1.4 Per-frame loop
`core/camera/opencv/opencv_camera_loop.py` + `opencv_helpers/opencv_get_frame.py` (code):

| Order | What | Lines |
| --- | --- | --- |
| 1 | config/pause/recorder checks | loop 44–58 |
| 2 | gate: `orchestrator.should_grab_by_id()`, else `time.sleep(1e-5)` and re-poll (~0.5 ms real sleep per the 11-08 review) | loop 67–69 |
| 3 | `pre_frame_grab_ns`, `cap.grab()`, `post_frame_grab_ns` | get_frame 53–55 |
| 4 | `pre_frame_retrieve_ns`, `cap.retrieve(image=preallocated BGR)`, `post_frame_retrieve_ns` | get_frame 71–73 |
| 5 | `frame_number += 1` only on success | get_frame 79 |
| 6 | text overlay `camera.id…idx…fr…` **drawn into the image** | get_frame 80–84, 89–91 |
| 7 | `current_tik`; append to the 1000-sample duration deque; `framerate = 1/median` after 30 samples | loop 80–84 |
| 8 | read `should_record` flags | loop 96–98 |
| 9 | `pre_copy_to_camera_shm_ns`, `camera_shm.put_frame`, `post_copy_to_camera_shm_ns` | loop 102–104 |
| 10 | video write; `pre/post_frame_record_ns` around `video_writer.write` | loop 106–112; `core/recorders/videos/video_recorder.py:105-107` |
| 11 | frame-rate reset check | loop 113–119, 160–180 |
| 12 | zero every lifecycle stamp; set `initialized_ns` | loop 120, 143–157 |
| 13 | publish `frame_count` (this releases the peers' gate) | loop 123 |
| 14 | `previous_tik` | loop 124 |

### 1.5 Retries and failure
- A failed grab or retrieve retries inside the same gate pass. `fail_count` counts across retries, and every retry overwrites the stamps (loop 72–85).
- After 30 failures the loop raises (88–92). The exception handler sets `ipc.should_continue = False` (129), which **stops every camera in the group**. That is new on this branch.
- On DSHOW, `grab()` fails only on disconnect. `retrieve()` times out after 1 s (11-08 review §2.3), so 30 failures stall for about 30 s (inferred).
- Failed attempts also push durations into the frame-rate deque (80–84) (code).

### 1.6 Frame-rate reset (changed reading)
`check_framerate_reset` (loop 160–180) hard-codes 30 fps, so a 66.7 ms limit. It is passed `previous_tik` from line 82, which is set *after* `opencv_get_frame`, so `frame_duration_ms` (169) measures **shm copy + video write + reset bookkeeping, not the frame interval** (code).
- **When it fires:** only if that post-processing exceeds 66.7 ms for more than 30 consecutive frames after frame 100. In practice that means a slow video encoder.
- **What it does:** it releases and recreates the capture (177–178) while `frame_number` carries on. Peers wait at the gate for the whole reopen, and the timestamps show the gap (inferred).

### 1.7 Lockstep gate
`core/camera_group/camera_orchestrator.py:118-131` (code):
- A camera may grab only when every camera is `ready` (`camera_status.py:22-31`) and its `frame_count` is ≤ every other camera's.
- `frame_count` is published only after retrieve, shm copy, recording and the reset check (loop 123). Frame *k+1* on any camera therefore waits for every camera's full iteration *k*. Counts never differ by more than 1.

## 2. Every timestamp written or sent

### 2.1 In-memory per-frame record (shared memory and finaliser input)
`core/types/numpy_record_dtypes.py:17-33, 222-228` (code):
- `FRAME_METADATA_DTYPE` holds `camera_info`, `frame_number`, `timebase_mapping` (utc_ns, perf_ns, utc_offset), and lifecycle stamps:
  - `initialized`
  - `pre/post_frame_grab`
  - `pre/post_frame_retrieve`
  - `pre/post_copy_to_camera_shm`
  - `pre/post_frame_record`
- Every stamp is `time.perf_counter_ns()` (QPC on Windows).
- The image is a fixed `(H, W, C)` uint8 field (`core/types/frame_dtype_factories.py:16-26`).
- **No camera, driver or OS sample time is captured anywhere.** `grep CAP_PROP_POS_MSEC` finds only a test mock (code).

### 2.2 Files written at recording finalisation
Order: `RecordingFinalizer.finalize_recording` (`core/recorders/recording_finalizer.py:53-67`) runs `save_to_file`, then `process_and_save_recording_timestamps`, then the README, then `validate_recording`. The VFR remux is still commented out (63) (code).

Folders (`system/default_paths.py:6-8`) and paths (`core/recorders/videos/recording_info.py`, `core/timestamps/recording_timing_reader.py:15`):

| File | Rows | Main time columns and how they are computed |
| --- | --- | --- |
| `synchronized_videos/timestamps/camera_timestamps/<rec>.camera<id>.timestamps.csv` | one per recorded frame | **`timestamp.perf_counter_ns.ns`** = `(pre_frame_grab_ns + post_frame_grab_ns)//2` (`create_camera_csvs.py:50-51, 58`).<br>**`timestamp.from_recording_start.sec`** = that minus `recording_start_time_ns` (56–57).<br>`timestamp.utc.seconds` via the timebase mapping (61–63).<br>`timestamp.local.iso8601` via the buggy function (66–68).<br>`from_previous.frame_duration.ms`, `framerate.hz` = diff of midpoints (71–83).<br>`frame.<stage>.ns` = each raw lifecycle stamp minus recording start (86–89).<br>`duration.*` (92–99), from `calculate_durations` (`calculate_timestamps_numpy.py:35-80`).<br>`recording_frame_number` = `arange(N)` (54); `connection_frame_number` = loop frame number (55). |
| `synchronized_videos/timestamps/<rec>_timestamps.csv` (multiframe) | one per multiframe | `timestamp.from_recording_start.sec`, `utc.seconds`, `perf_counter_ns.ns` = **mean across cameras** of the per-camera values (`create_multi_frame_csvs.py:44-45`).<br>`local.iso8601` from the UTC seconds, correct (48–52).<br>`inter_camera.frame_grab_range.ms` = max − min of the per-camera midpoints (55–58).<br>`from_previous.*` = nanmean across cameras (61–71).<br>For each `frame.*`/`duration.*`/`total.*` column: mean, median, std, range, CV across cameras (74–111). |
| `synchronized_videos/timestamps/<rec>_stats.json` / `_stats.txt` | summary | `RecordingTimestampsStats.from_multiframe_rows` (`core/timestamps/recording_timestamp_stats.py:64-121`):<br>stats of multiframe `framerate.hz`, `frame_duration.ms` and `inter_camera.frame_grab_range.ms`;<br>stats of the **per-frame cross-camera median** of each stage duration;<br>`total_duration_sec` = last row's `from_recording_start.sec` (80). |
| `<rec>/<rec>_info.json` | 1 | `RecordingInfo.model_dump()` plus `videos`, `camera_timing`, `multiframe_timing` (relative paths) and `camera_configs` (`recording_info.py:80-104`).<br>`recording_start_timestamp` is a `FullTimestamp.now()` taken **when the `RecordingInfo` object is built** (`recording_info.py:27`), i.e. at the HTTP start request (`api/http/cameras/camera_router.py:147-148`), not at the first frame. |
| `synchronized_videos/<...>.mp4` | video | CFR (§2.6). |
| `synchronized_videos/synchronized_videos_README.md` | text | States that frame *k* is the same moment on every camera (`recording_finalizer.py:27-31`). |

**Recording start time:**
- `recording_start_time_ns` = the minimum `pre_frame_grab_ns` over each camera's *first recorded frame* (`process_and_save_recording_timestamps.py:81-84`). The first camera's `from_recording_start.sec` is therefore half a grab duration (~µs), not 0.
- Which loop frame is the first recorded frame: `start_recording` sets `first_recording_frame_number = max(frame_count) + 3` (`core/camera_group/camera_group.py:196-201`), and `stop_recording` sets `last = max + 3` (235–240). Recording is gated per frame by `should_record_frame_number` (`camera_orchestrator.py:102-116`) (code).

### 2.3 Time base and wall-clock mapping
- **One mapping per camera group.** `TimebaseMapping` is created once per `CameraGroupIPC` (`core/camera_group/camera_group_ipc.py:28`). It is one `(time.time_ns(), time.perf_counter_ns())` pair (`timebase_mapping.py:22-24`), copied into every frame (`create_initial_frame_recarray.py:15`) and checked identical across frames at finalisation (`process_and_save_recording_timestamps.py:59-65`). The audio recorder gets the same mapping (`camera_group.py:208-212`) (code).
- **The UTC anchor is one sample.** Any error in `time.time_ns()` at that instant (one system-timer tick on Python 3.12 per `docs/windows_timer_resolution.md`) offsets every UTC value. The pyproject allows `>=3.11` (`pyproject.toml:5`) (code / inferred).
- **Local ISO 8601 bug: still present.** `convert_perf_counter_ns_to_unix_ns(local_time=True)` adds the UTC offset (31). `convert_perf_counter_ns_to_local_iso8601` then formats that with `tz=LOCAL_TIMEZONE` (42), applying the offset a second time. **measured** (`notes/harness/iso8601_double_offset.out.txt`, zone America/New_York):
  - true local time: `2026-11-09T06:06:00-05:00`
  - per-camera CSV path: `2026-11-09T01:06:00-05:00`
  - multiframe CSV path: `06:06:00-05:00`

  The test (`tests/test_timestamps_and_framerate.py:118-125`) only checks for a `"T"`.
- **`FullTimestamp.from_timebase_mapping` is also wrong.** It adds `perf_counter_ns/1e9` to the UTC anchor (`core/timestamps/full_timestamp.py:81-83`). Only its `__main__` block (129) and a test (`tests/test_timestamps_and_framerate.py:180`) call it, so it doesn't reach recordings (code).

### 2.4 `recording_timing_reader.py` (new): what consumers get
`core/timestamps/recording_timing_reader.py` (code):
- **Path lookup:** `recorded_camera_timing_path` and `recorded_multiframe_timing_path` (18–31) take the paths from `_info.json` (`recording_metadata.py:14-29`).
- **`read_recording_timing(path, kind)`** (80–117) returns `{frame_index: seconds}` from:
  - frame index: `recording_frame_number` (camera) or `multiframe_number` (multiframe);
  - seconds: **`timestamp.from_recording_start.sec`**.

  It requires frame indices and times to be strictly increasing (105–112). It applies no rebasing and no smoothing.
- **`resolve_camera_timing(path, frame_count, fps, offset_s)`** (51–77):
  - CSV present: it must cover exactly `range(frame_count)` of the video (65–68), and it returns `TimingMethod.RECORDED`.
  - No sidecar: it returns `offset_s + k/fps`, `TimingMethod.INFERRED_FROM_FPS`.
  - `TimingMethod.MEAN_CAMERA_TIMES` (37) is defined here but used only by freemocap (`freemocap/core/reconstruction/recording_timing.py:46`).
- **Consumers:**
  - skellycam: `api/http/playback/playback_router.py:309`, `core/recorders/videos/recording_statistics.py:13-22` (fps = (N−1)/duration of the multiframe times).
  - freemocap: `freemocap/api/http/playback/playback_router.py:81, 800`; `freemocap/core/pipeline/posthoc/video_node.py:496`; `freemocap/core/reconstruction/recording_timing.py:29-46`; `freemocap/core/recording/result_processing/{observation_inputs,saved_observations}.py`; `freemocap/tools/datasets/full_recording_comparison.py:51-53`.
- **Consequence:** whatever skellycam writes into `timestamp.from_recording_start.sec` flows straight into freemocap's "recorded" timing. Change that column's source (better stamps) and those consumers pick it up without code changes, as long as there is still exactly one row per video frame, with indices 0..N−1 and strictly increasing times (inferred from code).

### 2.5 Live/frontend timestamps
- **Frontend image payload:** `create_frontend_payload` (`core/types/frontend_payload_bytearray.py:136-159`) gives each frame `timestamp = mean(pre_grab, post_grab)` (154–155). `encode_image_payload` returns the **mean across cameras** (133).
  - The binary wire format has no timestamp field, only frame numbers (20–50, 104–132).
  - The websocket server uses the mean only for the "backend framerate" (`api/websocket/websocket_server.py:216-227`). Its docstring claims `frame_number` "increments by 1 for every camera capture at the hardware level" (38–42). It is the loop count, so hardware drops never appear (code).
- **Performance data:** grab midpoint per camera (`api/websocket/performance_data.py:67`), plus cross-camera `grab_range_ms` and `grab_stddev_ms` (88–93).
- **`browser_stream.py`** (new) re-encodes a recorded file for browser playback. Its pts come from the source file's pts (`core/recorders/videos/browser_stream.py:89-99`) and its rate from `average_rate` (79), so it inherits the CFR pts. It reads no CSV (code).
- **freemocap does not read the in-shared-memory lifecycle stamps** (grep finds no use of `frame_metadata.timestamps` or `timebase_mapping` in `freemocap/`) (code).

### 2.6 Video writers: CFR, and the fps they are given
- **Writer fps source:** `VideoRecorder.create(framerate=...)` uses the loop-measured rate when available, otherwise `config.framerate` (`video_recorder.py:80`). The loop passes `framerate` (`opencv_camera_loop.py:57` → `handle_recording_updates.py:42-46`). Recording always starts long after 30 frames, so the loop-measured rate is what gets used.
- **Writers:**
  - cv2: `cv2.VideoWriter(path, fourcc, framerate, size)` (`video_recorder.py:129-134`), CFR. Windows default `X264` → mp4 (`camera_config.py:29`, `fourcc_codec_helpers.py:58`).
  - PyAV: `rate=int(round(fps))`, `pts = frame_count` (`core/recorders/videos/pyav_video_writer.py:14, 33`), CFR.
- **The measured rate is biased high (code; size inferred).**
  - Each duration is `current_tik` (after `get_frame`, loop 80) minus `previous_tik`, which is set at the end of the previous iteration (124). It therefore leaves out each iteration's shm copy, video write, reset check and recarray reset (102–123).
  - True period = measured + that post-processing, so `1/median` overstates the rate.
  - Size: during preview, the excluded part is mostly two copies of a 2.76 MB frame (inferred ≈1–2 ms), which puts the writer rate roughly 3–6 % high and makes CFR video durations correspondingly short.
  - Measurable from a real recording: compare the writer fps with `1/median(from_previous.frame_duration.ms)`.
- **No variable-frame-rate output.** The remux (`recording_finalizer.py:73-123`) would use `timestamp.perf_counter_ns.ns` (`core/recorders/video_audio_remuxer.py:147-156`), i.e. grab midpoints, but its call is commented out (63).

## 3. Status of the 11-08 review's findings on this branch

| Item | Status | New location / note |
| --- | --- | --- |
| P1 stamp brackets no delivery event | **still true** | backend `determine_backend.py:42`; stamps `opencv_get_frame.py:53-55`; midpoint `create_camera_csvs.py:50-51`, written 58 |
| P2 lockstep error both ways; BUFFERSIZE no effect | **still true** | gate `camera_orchestrator.py:118-131`; poll loop `opencv_camera_loop.py:67-69`; `frame_count` published at 123 (was 116); BUFFERSIZE `create_cv2_video_capture.py:66` |
| P3 index pairing assumes simultaneous capture | **still true, and now also feeds freemocap's "recorded" timing** | `validate_frame_metadatas` `process_and_save_recording_timestamps.py:34-48`; §2.4, §4 |
| P4 docstring assumptions wrong | **still true** (file unchanged) | `opencv_get_frame.py:12-51`. Correction to the 11-08 citation: readout "~10-20ms" is line 26, jitter "~0.1-1ms" is line 28 (swapped there). DSHOW `grab()` "calls IMediaSample delivery" and the buffer_size=1 claim: 36–39 |
| P5 better sources ignored | **still true** | no `CAP_PROP_POS_MSEC` read anywhere (grep); no MF path |
| §4 local ISO 8601 double offset | **still true, measured** | `timebase_mapping.py:31, 42`; harness above |
| §4 false buffer-size comments | **still true** | `determine_backend.py:34-35, 39`; `create_cv2_video_capture.py:21-27` |
| §4 dead `create_camera_frame_csv_row_recarray` | **still true** | `create_camera_csvs.py:110-178`; `(pre+pre)//2` at 127–128. It would also raise if called: it writes `frame.pre_grab.ns` etc. (151–163), which aren't in `CAMERA_TIMESTAMPS_CSV_ROW_DTYPE` |
| §4 dead `calculate_frame_grab_timestamps` | **still true** | `calculate_timestamps_numpy.py:15-32` |
| §4 format negotiation order | **unchanged** | create 58→59-60→66→75; apply 71-72→74-76→82-85 (§1.2) |
| §4 overlay burned into image | **still true** | `opencv_get_frame.py:80-84` |
| §4 hard-coded 30 fps reset | **still true; reading changed** | `opencv_camera_loop.py:160-180`; it times post-processing, not the frame interval (§1.6) |
| 2.4 other uses: perf view midpoint | unchanged | `performance_data.py:67` |
| 2.4 frontend mean of grabs | moved | `frontend_payload_bytearray.py:154-155`, cross-camera mean at 133 |
| 2.4 multiframe mean across cameras | unchanged | `create_multi_frame_csvs.py:44-45` |
| 2.4 recording start = min pre_grab | unchanged | `process_and_save_recording_timestamps.py:81-84` |
| 2.8 VFR remux disabled | unchanged | `recording_finalizer.py:63` |
| Retry behaviour | **changed** | after 30 failures the loop raises and stops the whole group (`opencv_camera_loop.py:86-92, 126-130`) |

## 4. Multiframe model

### 4.1 Grouping
Frames are grouped **by loop index**:
- `frame_number` is the count of successful `retrieve()` calls (`opencv_get_frame.py:79`).
- The ring-buffer write index equals `frame_number`, because every successful frame is put exactly once (`ring_buffer_shared_memory.py:124-133`).
- A multiframe is "slot *k* of every camera's ring buffer" (`camera_group_shared_memory.py:521-534`).

### 4.2 Where equal counts and identical indices are assumed (code)

| # | Site | Behaviour on mismatch |
| --- | --- | --- |
| 1 | Gate `camera_orchestrator.py:127-131` | prevents it (lockstep) |
| 2 | Shared recording window `camera_orchestrator.py:102-116`, `camera_group.py:196-201, 235-240` | one frame-number window for all cameras |
| 3 | `VideoRecorder._validate_frame_number` `video_recorder.py:153-160` | raises on any non-consecutive frame number |
| 4 | `validate_frame_metadatas` `process_and_save_recording_timestamps.py:34-48` | raises if counts or frame numbers differ |
| 5 | Multiframe CSV `create_multi_frame_csvs.py:36-45` | means across cameras per row (its own check at 36–38 is vacuous because rows are `arange(N)`) |
| 6 | `validate_recording` `recording_finalizer.py:168-170, 196-198` | raises if video frame counts differ, or the CSV row count ≠ video frames |
| 7 | `get_latest_multiframe` `camera_group_shared_memory.py:427, 531-533` | min over cameras; raises on mismatch |
| 8 | `get_images_by_frame_number` `camera_group_shared_memory.py:551-560` | warns |
| 9 | `ImagePayloadRequest` `frontend_payload_bytearray.py:94-95` | raises if frame numbers differ |
| 10 | `resolve_camera_timing` `recording_timing_reader.py:65-68` | raises unless the CSV covers exactly `range(video frames)` |
| 11 | README text `recording_finalizer.py:27-31` | documents the assumption |
| 12 | freemocap realtime: `freemocap/core/pipeline/realtime/camera_node.py:287-310`, `realtime_skeleton_inference_node.py:309-325` | read slot *k* from each camera; warn/skip on mismatch |

### 4.3 Dropped or failed frames
- **Hardware or driver drops:** invisible.
  - DSHOW's `SampleCB` keeps one unread frame and discards newer ones (11-08 review §2.3). A camera held at the gate loses frames silently and later returns a stale one.
  - A frame the camera never sends just makes `retrieve()` wait longer.
  - Either way the loop index advances by exactly 1, so a drop shows up only as a ~2P gap in that camera's `from_previous.frame_duration.ms`. Nothing flags it, and both cameras' frame *k* stay paired (code + inferred).
- **Software failure (grab or retrieve false):** retried in place (§1.5), and the index does not advance. After 30 failures the group stops.
- **A camera dying mid-recording:** its `finally` block flushes its recorder (`opencv_camera_loop.py:131-136`). Peers may be one frame ahead (gate allows ≤1), so the recordings can differ by one frame. `validate_frame_metadatas` then raises (37–39) after `_info.json` has already been written (`recording_finalizer.py:55-61`), leaving a recording without timestamp CSVs (inferred from code; not tested).

### 4.4 Different frame rates
Not possible:
- The gate runs the whole group at the slowest camera's delivery rate. Faster cameras' surplus frames are discarded by DSHOW (code + inferred).
- The DSHOW frame rate is never set (`framerate=-1`, `should_apply_framerate=False`).
- Every downstream check in §4.2 requires equal counts.

With an MF source reader, frames would queue rather than be dropped (inferred; the research's MF probes cover this). Behind the current gate, a faster MF camera would build up latency unless the backend drains to the newest frame. So an MF backend that keeps the gate must deliberately drop, and should record that it did.

## 5. Coupling to OpenCV: what an MF raw-MJPEG backend must change

`import cv2` appears in 21 non-test, non-diagnostic modules (grep). Grouped by role:

### 5.1 Capture and config (always changes)

| Module | Coupling |
| --- | --- |
| `core/camera/camera_worker.py:7, 51` | hard-wired `opencv_camera_worker_method` |
| `core/camera/determine_backend.py` | returns a cv2 backend id |
| `core/camera/opencv/opencv_camera_loop.py` | generic loop logic (gate, shm put, recording, status, reset) interleaved with a `cv2.VideoCapture`; needs splitting into a backend-agnostic loop plus a capture interface (`open`, `read() → (bytes or image, sample metadata)`, `set_controls`, `close`) |
| `opencv_helpers/opencv_get_frame.py` | grab/retrieve stamps, BGR retrieve into the preallocated slot, overlay |
| `opencv_helpers/create_cv2_video_capture.py`, `setup_opencv_camera_loop.py` | open, set format, first read, drain loop (`read()` at 59) |
| `opencv_helpers/opencv_apply_config.py`, `opencv_extract_config.py`, `check_for_new_config.py`, `camera_loop_update_checks.py` | exposure via `CAP_PROP_AUTO_EXPOSURE`/`CAP_PROP_EXPOSURE`; extracted config from `cap.get`. MF would use IAMCameraControl / KS properties (`research/usb_cameras/suite/windows/pymf/mf.py` already has `read_ctl`/`set_ctl` via KS). The exposure units should carry over, since it's the same KS camera-control property (inferred) |
| `opencv_helpers/recommend_camera_exposure_setting.py` | reads frames through `cap.read()` to pick an exposure |
| `core/device_detection/detect_cameras_devices.py:86-110` | `cv2_enumerate_cameras` with DSHOW; `camera_index` is the DSHOW index; `camera_id` = SHA-256 of the device path (44–54). MF opens by symbolic link. If the MF symbolic link differs from the DSHOW `DevicePath` string, every `camera_id` changes, and saved configs and recordings are keyed by it (inferred; check on Gerald) |
| `core/camera/config/camera_config.py` | `capture_fourcc`, `framerate=-1` (MF needs an explicit native media type), `color_channels`, `image_shape` |

### 5.2 Frame data path: depends on the design

- **Design A, decode at source (keeps BGR in shared memory).** The capture process decodes each JPEG into the existing BGR slot (libjpeg-turbo or `cv2.imdecode`). It could optionally also write the raw JPEG to an MJPEG/AVI archive for a lossless copy.
  - **Unchanged:** shared memory, recording, frontend, freemocap realtime.
  - **Changes:** add fields to `FRAME_LIFECYCLE_TIMESTAMPS_DTYPE` / `FRAME_METADATA_DTYPE` (`numpy_record_dtypes.py:23-33, 222-228`), e.g. MF sample time, arrival QPC, decode start/end, MF stream flags/discontinuity, JPEG size. The CSV writer loops over the lifecycle dtype names (`create_camera_csvs.py:86-89`), but the target `CAMERA_TIMESTAMPS_CSV_ROW_DTYPE` (`numpy_record_dtypes.py:49-79`) and `MULTI_FRAME_TIMESTAMP_CSV_ROW` (81–208) are hand-written. Each new field needs matching entries there, plus a duration entry if wanted.
  - **Cost:** one extra decode per frame in the camera process. Today DSHOW already decodes on its own thread, so total CPU is about the same (inferred).
- **Design B, JPEG end to end.**
  - **Shared memory:** variable-length bytes in fixed slots. Needs a max-size byte field plus a length field in `create_frame_dtype` (`frame_dtype_factories.py:16-26`); the 1 GB/camera ring sizing (`ring_buffer_shared_memory.py:38-42`) changes.
  - **Recording:** `video_recorder.py:91-113` rotates with `cv2.rotate` on BGR and `write`s BGR. Writing the MJPEG bitstream untouched would be lossless and cheap, but rotation and the X264 output would need decoding.
  - **Finaliser:** `validate_recording` checks the shape with `cv2.VideoCapture(...).read()` (`recording_finalizer.py:150-164`).
  - **Frontend:** `frontend_payload_bytearray.py:136-159` rotates, resizes to ≤0.5 and re-encodes at q60, so it needs decode, or a protocol change to forward full-size JPEG.
  - **freemocap realtime:** `camera_node.py:287-297` and `realtime_skeleton_inference_node.py`, plus the charuco/aggregator nodes and `freemocap/tests/pipelines/mocks/mock_camera_group.py`, must decode.
- **Overlay (both designs):** the text is drawn into the BGR image (`opencv_get_frame.py:80-84`). It must be dropped, or applied to a decoded copy. Today it is burned into recorded videos and into the images freemocap's realtime trackers see, so dropping it is also a data-quality fix (code).

### 5.3 Timestamp outputs (any backend with better stamps)
- `create_camera_csvs.py:50-51`: choose the per-frame time (MF sample time or arrival, or a slot fit). Keep the column names so `recording_timing_reader` consumers keep working (§2.4). Add provenance columns: method, raw sources, fitted slot index, drop flag.
- `process_and_save_recording_timestamps.py:81-84`: recording start.
- `create_multi_frame_csvs.py:44-58`: "mean across cameras" and "inter-camera grab range" lose their meaning once stamps are per-camera capture times. The range then becomes a real sync measurement instead of the gate's self-consistency.
- `performance_data.py:67`, `frontend_payload_bytearray.py:154-155`, `websocket_server.py:36-72`: live stamps.
- `timebase_mapping.py:31, 42`: fix the bug.
- **Mapping MF to perf_counter:** MF sample times would need mapping into the `perf_counter_ns` base. On Windows both are QPC-based, but MF sample times have their own origin (the MF agent should confirm the mapping from the research) (inferred).

### 5.4 Different rates and real drops
This needs all of §4.2 rewritten:
- Replace the gate with free-running cameras.
- Give each camera its own recording window and frame index.
- Drop the consecutive-frame-number check, or turn it into gap recording.
- Allow unequal per-camera counts in validation.
- Build multiframes by time, not by slot index, in shared memory, the frontend and freemocap realtime.
- Write per-camera VFR pts (PyAV path; the cv2 writer can't set pts).

It also needs the freemocap side, which pairs frames by index post hoc; covered by the freemocap reader.

### 5.5 Scope estimate (inferred)

| Variant | skellycam files touched | New code |
| --- | --- | --- |
| A. MF capture, decode at source, keep lockstep, better stamps plus new columns | ~15 (§5.1 + dtype + CSV writers + start time + bug fixes) | MF capture module. The research's pure-Python MF (`pymf`) is ~3,100 lines including CLI/probe code; a production subset is perhaps 1,000–1,500. Plus a ~200-line loop refactor and tests. |
| B. A plus JPEG end to end | +8 skellycam (shm dtype/ring, recorder, finaliser validation, frontend, …) +3–4 freemocap realtime modules | decode helpers, MJPEG writer path |
| C. A or B plus independent rates and drops | +12 sites in §4.2 plus the freemocap post-hoc pairing | time-based multiframe assembly, per-camera recording windows, VFR writing |

## 6. Bearing on Dom's questions (skellycam side only; accuracy numbers belong to the measurement agents)

1. **Revisions to the OpenCV DSHOW path** can change *which instant* is stored, without a new backend (code-based; size unmeasured):
   - Use `post_frame_retrieve_ns` (frame ready after DSHOW's own decode, plus one copy) instead of the grab midpoint. Flag frames where `retrieve()` blocked (long `during_frame_retrieve`), since those are the trustworthy ones.
   - Fit `t_k = a + P·k` on the lower envelope per camera. A residual step of ≈P marks a dropped frame.
   - Fix the ISO bug, the fps bias (§2.6) and the reset trigger (§1.6). Stop burning in the overlay.
   - **Limit:** DSHOW gives no sample time (P5), and the one-slot latch keeps dropping frames silently while the gate holds a camera. Removing the gate is what lets each camera's retrieve block on every frame. That turns into the §5.4 rework.
2. **MF raw MJPEG (tier 0)** adds a per-sample MF time and an arrival callback without OpenCV's decode or latch. Design A slots it into skellycam with the changes in §5.1–5.3. The rest of skellycam keeps working unchanged as long as frames stay index-locked. Different rates or real drops need §5.4 in both skellycam and freemocap.
3. **Recordings made on this branch store no information beyond the grab-midpoint stamps.** A better stamp can't be reconstructed afterwards from these files. Only `post_frame_retrieve` is kept: it is in the CSV as `frame.post_frame_retrieve.ns`, relative to recording start, so a retrieve-based re-estimate of existing recordings is possible (code).

## 7. Open points (each needs a run with the camera lock)

- **fps bias.** One short skellycam recording on this branch (C930e alone, then C930e + C922). Compare the writer fps (ffprobe) with `1/median(from_previous.frame_duration.ms)` and with `duration.during_copy_to_camera_shm`.
- **What the stored stamp tracks.** In the same recording, compare `timestamp.perf_counter_ns.ns` with `frame.post_frame_retrieve.ns`. Next to an MF reference with UVC PTS on the C922 (tier-1 PTS used only as an independent reference, never as part of a tier-0 method), score both. This is the 11-08 review's open point 1.
- **The real negotiated mode** after skellycam's FOURCC→size→read→size→FOURCC sequence on each camera (11-08 review §4).
- **Symbolic link vs DSHOW path.** Whether MF's symbolic link equals the `cv2_enumerate_cameras` DSHOW path string on Gerald, since that decides whether `camera_id` survives the backend swap.
