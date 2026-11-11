# freemocap development-streaming: how skellycam timestamps and frame indices are used

Reader A (recording, post hoc, data contract). Snapshots: freemocap `c27fc299`, skellycam `169caf63`, skellyforge and skellytracker development-streaming (paths in the run context). Labels: **code** = read from source (path:line, relative to that repo), **measured** = result file below, **inferred** = reasoning, not run. No camera was opened for this note.

Correction to the earlier review (`research/usb_cameras/docs/skellycam_timestamps_review.md` §1, which read older code): development-streaming freemocap **does** use skellycam's timestamps now, but only after triangulation and in storage/playback. Triangulation still pairs frames by index. The tracker gets recording time, not `frame_number / fps`, on the default path.

## 1. Short answer

- **freemocap reads exactly one timestamp column**, `timestamp.from_recording_start.sec`, from each per-camera CSV and from the multiframe CSV, plus `recording_frame_number` / `multiframe_number` (skellycam `skellycam/core/timestamps/recording_timing_reader.py:86-114`). It also reads `connection_frame_number` in the legacy pipeline only. Extra CSV columns are ignored. **code**
- **Frame index is the join key everywhere before 3D.** Frame *k* of every camera is triangulated together, and every frame-count check requires all cameras to be equal. **code**
- **The group ("synchronized") timeline is the multiframe CSV**: the mean of the cameras' grab midpoints (skellycam `create_multi_frame_csvs.py:44-45`). It feeds gap filling, Butterworth filtering, alignment, tracker timestamps, every 3D row in Parquet, the exports and Blender. **code**
- **Per-camera timestamps are stored, not used scientifically.** They label 2D overlay/box rows, a per-camera `capture` TIMESTAMPS channel, and the playback video timelines. **code**
- **So more accurate per-camera stamps (DirectShow revisions or MF) would flow straight into Parquet with no freemocap change**, because the column name and meaning ("seconds from recording start, one row per frame") stay the same. They would improve the group timeline (filtering, gap filling, time labels on outputs). **They would not change any 3D point**, because triangulation never looks at time. **code + inferred**
- **Dropped frames, unequal counts and different camera rates all fail loudly today** (frame-count validators). Duplicated placeholder frames would pass and be **silently wrong**. **code + inferred**
- **VFR containers would break the frame-count probe and UI playback; raw MJPEG in a CFR AVI works** (synthetic test, §10). **measured + code**

## 2. What skellycam hands over (development-streaming)

| Item | Content | Source (skellycam) |
| --- | --- | --- |
| `<rec>.camera<id>.timestamps.csv` | `recording_frame_number` 0..N-1, `connection_frame_number`, `timestamp.from_recording_start.sec` = (pre-grab + post-grab)/2 − recording start, plus diagnostic columns | `core/timestamps/numpy_timestamps/create_camera_csvs.py:49-57` |
| `<rec>_timestamps.csv` (multiframe) | `multiframe_number`; `timestamp.from_recording_start.sec` = **mean over cameras** | `create_multi_frame_csvs.py:36-45` (raises unless all cameras share the same frame numbers) |
| `recording_info.json` | `camera_timing` {camera_id: relative path}, `multiframe_timing` path, `videos` map | `core/recorders/videos/recording_info.py:93-97` |
| Videos | Constant frame rate. cv2 writer fps = that camera's **median measured rate over the last ≤1000 loop intervals before recording**, so it differs per camera. The PyAV writer uses `round(fps)`. | `core/camera/opencv/opencv_camera_loop.py:40-41,81-84`; `opencv_helpers/handle_recording_updates.py:42-46`; `core/recorders/videos/video_recorder.py:80,121-127`; `pyav_video_writer.py:14` |
| Frame counts | Equal across cameras by construction (lockstep grab gate) | review §2.6 |

A code comment in freemocap reports one take with container rates of 34.28 / 34.48 / 34.66 / 34.74 fps and identical frame counts (`freemocap/core/tasks/mocap/mocap_helpers/recording_framerate.py:9-13`). That is a comment, not a result file.

## 3. Consumers in freemocap

Default post hoc path is the typed dataflow graph (`freemocap/core/tasks/mocap/mocap_task_config.py:31-32`). The legacy path is `pipeline_implementation="current"`.

| Consumer | file:line | Uses | Same count? | Same constant fps? | Frame *k* simultaneous? |
| --- | --- | --- | --- | --- | --- |
| Timing resolver | `freemocap/core/reconstruction/recording_timing.py:20-47` | Per camera: CSV via `recorded_camera_timing_path`, else `k/fps` (`INFERRED_FROM_FPS`). Group: multiframe CSV (`RECORDED`), else mean of cameras (`MEAN_CAMERA_TIMES`) | yes: CSV must equal `range(frame_count)` (skellycam `recording_timing_reader.py:65-68`); selected frames must equal each video's range (`:27-28`) | no (fallback uses each video's own fps) | assumed (group time = mean per index) |
| Video group | `freemocap/core/pipeline/posthoc/video_group_helper.py:133-142, 321-334` | cv2 reported count/fps | **raises if counts differ** | no | – |
| Dataflow sources | `freemocap/core/pipeline/dataflow/video_sources.py:46-56, 65-71, 161-174` | Frame *k* keyed with that camera's timestamp | **raises** | no | key is one ordinal for all cameras |
| Camera join | `freemocap/core/pipeline/dataflow/camera_join.py:37-38, 58-64, 73-74` | Ordinal | requires full consecutive coverage per camera | – | frame ready when every camera has ordinal *k* |
| Observation check | `freemocap/core/pipeline/dataflow/scientific_recording.py:76-81` | Observation timestamp must equal that camera's timeline entry | yes | – | – |
| Tracker time | `freemocap/core/pipeline/dataflow/tracker_adapter.py:37-49, 120` | **Group** time → integer ms; must strictly increase | yes | no | yes (one time per multiframe) |
| Legacy detection | `freemocap/core/pipeline/posthoc/mocap_detection.py:73-89, 107-137` | Ordinal loop; timing resolved only to check the filter's Nyquist limit; **no `timestamp_ms` passed to the tracker** (`:115`) | **raises** | no | yes |
| Triangulation | `freemocap/core/reconstruction/posthoc_reconstruction.py:88-91`; `freemocap/core/tasks/mocap/posthoc_mocap_task.py:144-150, 207-213`; `scientific_recording.py:111-135` | Ordinal only | **raises** ("frame numbers must match exactly") | – | **yes, implicitly** |
| Gap filling | `freemocap/core/reconstruction/trajectory_gap_filling.py:35-39` → skellyforge `skellyforge/core/trajectories/gap_filling.py:7, 64-65, 78-84` | Group timestamps. Fills a gap only if the bracketing samples are ≤ 100 ms apart. | – | no | – |
| Filtering | `freemocap/core/reconstruction/posthoc_filtering.py:50-62, 87-115` | Group timestamps. Rate = 1/median interval; a split wherever an interval > 1.5 × median; resample to a uniform grid, Butterworth, back to the observed times; runs ≤ 15 samples (order 4) left unfiltered | – | **no, time-aware** | – |
| Alignment | `freemocap/core/reconstruction/mocap_alignment.py:117`; `alignment_evidence.py:43-44` | Group timestamps (strictly increasing) | – | no | – |
| Persistence | `freemocap/core/recording/result_processing/observation_publication.py:75-127, 172-233` | 2D overlay/box rows: **per-camera** time with the group ordinal. `capture` TIMESTAMPS per camera. `synchronized` TIMESTAMPS for the group. All 3D/reconstruction/diagnostic rows: **group** time | checks every camera's frame number equals the group ordinal (`:100-102`) | stores `nominal_fps` = container fps, `inferred_offset_s=0` (`:89-95`) | – |
| Saved reload | `freemocap/core/recording/result_processing/saved_observations.py:61-68, 99-110` | Rebuilds per-camera and group timing from Parquet | **raises** if cameras' frames differ or aren't consecutive | – | – |
| Exports | `freemocap/core/recording/exports/arrays.py:137, 156-177`; `exports/wide_csv.py:204-206, 256` | `frame_number`, `timestamp_s` (group) from Parquet. Wide CSV/NPY require identical frame axes and timestamps across selected arrays. No invented times for absent frames. | per table | – | – |
| Blender | `freemocap/core/blender/helpers/validate_saved_scene.py:36-41` | Scene frames = group frame numbers. Scene fps = 1/median(Δt). Times kept as a custom property | – | **yes** (uniform scene rate) | – |
| Playback (server) | `freemocap/api/http/playback/playback_router.py:69-87, 784, 793-806` | Per-video timeline from the camera CSV or `k/fps`. Group is "valid" only if frame counts are equal | yes | no | – |
| Playback (UI) | `freemocap-ui/src/components/playback/usePlaybackController.ts:38-41, 54, 83-89, 111, 141` | Leader = first video. Frame = `round(mediaTime × leader_fps)`. **Every** video is seeked to `frame / leader_fps` seconds. Recording time = leader's capture time[frame]. | yes (`:54`) | **yes (leader's)** | yes |
| 3D in playback | `freemocap-ui/src/components/viewport3d/RecordingPlaybackProvider.tsx:112`; `freemocap-ui/src/services/recording/playback-data.ts:61-68` | Last group sample with time ≤ leader capture time (binary search) | – | no | – |
| Calibration | `freemocap/core/pipeline/posthoc/posthoc_aggregation_node.py:135-171`; `calibration_pipeline.py:75-79` | Ordinal only, no timestamps | **raises** on mismatched ranges | – | yes |
| Realtime cache reuse (legacy) | `freemocap/core/pipeline/posthoc/video_node.py:359-384, 488-509` | `recording_frame_number` → `connection_frame_number` from the camera CSV | – | – | – |
| `get_recording_framerate` | `freemocap/core/tasks/mocap/mocap_helpers/recording_framerate.py:91` | Multiframe `from_previous.framerate.hz` median | – | – | – |

`get_recording_framerate` has **no callers** in the snapshot (grep). It is dead code. **code**

## 4. What "sync" means

- **`sync_job.py`** runs the external `skelly_synchronize` (`pyproject.toml:54`, skellysync `philip/rewrite` @ `2aea71b7`; its source was **not read**) in a worker (`freemocap/core/pipeline/posthoc/sync_job.py:101-117`). The router calls it "aligns/trims a group of videos to a shared frame count" by audio cross-correlation or brightness flash (`freemocap/api/http/mocap/mocap_router.py:234-282`). It produces trimmed videos. **It produces no timestamps.** A whole-recording start offset is the only correction (**inferred** from the router and docstrings).
- **`/recording/check_sync`** defines "synchronized" as **equal reported frame counts** and nothing else (`mocap_router.py:153-178`, `:171`).
- Inside freemocap, "synchronized" means **same ordinal = same instant** (`current-work-plans/02-pipeline/mocap-multiprocessing-alignment.md:32`, `posthoc-architecture-review.md:42-43`, `client-playback-design.md:195-197`: "Mocap input synchronization is assumed; select the same ordinal in every source. Do not infer a different per-camera frame from capture timestamps.").

## 5. How times reach the 3D outputs

1. Parquet rows (`timestamp_s, sensor_group, frame_number, …`). Every 3D, reconstruction and diagnostic row gets the **group** time for its ordinal. 2D rows get that camera's time with the same ordinal (`observation_publication.py:172-233`). **code**
2. The sensor group declares `clock_description="recording-relative seconds; timing method declared per source"`. Each camera source stores `timing_method` (`recorded` / `inferred_from_fps`) and `nominal_fps` (`observation_publication.py:89-95, 152-158`). **code**
3. Tall CSV, wide CSV, NPY and NPZ copy `frame_number` and `timestamp_s` from Parquet (`exports/arrays.py:156-177`, `wide_csv.py:256`). The group time is the time of every 3D sample. **code**
4. Blender plays frames at the uniform rate 1/median(Δt) and keeps the true times only as metadata (`validate_saved_scene.py:36-41`). **code**

## 6. Imported (non-skellycam) videos

- `/recording/import` copies the files into `synchronized_videos/`. They must have equal reported frame counts, or come out of a finished sync job (`mocap_router.py:299-357`). Synced outputs are renamed `<stem>.mp4` (`:357`). **code**
- No `recording_info` timing fields → each camera gets `k / its own container fps`, starting at 0, labelled `inferred_from_fps`. The group gets the **mean** of those (`recording_timing.py:42-46`). **code**
- If imported videos have different container fps but equal counts, their inferred times drift apart and the group time is a blend. Triangulation still pairs by index, so 3D is unaffected, but the time labels are a compromise. **inferred**

## 7. Defects found in the current code (independent of any capture change)

| # | Defect | Evidence | Effect |
| --- | --- | --- | --- |
| D1 | UI seeks **all** cameras to `frame / leader_fps` seconds and lets each `<video>` play at its own container rate. skellycam writes a different container fps per camera (§2). | `usePlaybackController.ts:40, 89, 111`; skellycam `opencv_camera_loop.py:81-84`, `video_recorder.py:124` | A follower shows frame ≈ *k*·fps_i/fps_leader. With the commented rates (34.28 vs 34.74), that is 13 frames off at *k* = 1000 (~29 s). This contradicts the plan's "every camera presents the same shared frame ordinal" (`current-work-plans/02-pipeline/app-workflow-todo.md:56`). **code; size inferred, not observed in the app** |
| D2 | 3D shown at the last group sample ≤ the **leader camera's** capture time. The group time is the mean over cameras. Whenever the leader camera's stamp for frame *k* is earlier than the mean, frame *k*−1 is drawn. | `usePlaybackController.ts:141`; `playback-data.ts:61-68` | Off-by-one 3D frame in playback for part of the frames. **inferred** |
| D3 | `recording_framerate.py` is dead. Its docstring describes a filter bug that the current code avoids (the filter derives its rate from timestamps). | grep; `posthoc_filtering.py:56` | Cleanup only. **code** |
| D4 | The legacy path never passes `timestamp_ms` to the tracker; the dataflow path does. | `mocap_detection.py:115` vs `tracker_adapter.py:120` | Temporal detectors (MediaPipe VIDEO mode) get detector-derived time on the legacy path. **code** |
| D5 | A truncated JPEG decodes without error and without `is_corrupt`. | §10 | A raw-MJPEG writer would carry bad frames into detection silently. **measured (synthetic)** |

## 8. Scenarios: what breaks, what goes silently wrong, what must change

### (a) Accurate per-camera, per-frame timestamps (equal counts, still index-aligned)

- **Breaks:** nothing, as long as the CSV keeps `recording_frame_number` 0..N-1 and a strictly increasing `timestamp.from_recording_start.sec` (`recording_timing_reader.py:105-112`), and `recording_info.json` keeps the `camera_timing` / `multiframe_timing` keys. If the keys are missing, freemocap silently falls back to `k/fps`, although it is labelled `inferred_from_fps` (`recording_timing_reader.py:18-31`). **code**
- **Improves:** the group timeline, if skellycam keeps writing it as the mean. That improves gap-filling decisions (100 ms rule), the filter's 1.5×median split rule and resampling, alignment timing, and the time labels in Parquet, CSV, NPZ and Blender. The size: a time-label error δ shifts a sample moving at *v* by *v*·δ along its true path. Averaging 4 cameras' independent errors divides δ's std by about 2; a common offset cancels out of all relative timing. **inferred**
- **Does not improve:** the 3D points. Triangulation pairs ordinal *k* across cameras (`posthoc_reconstruction.py:88-91`), so a capture-time difference Δ between cameras at frame *k* stays a ray mismatch of about *v*·Δ (up to about one period per review P3). Better labels don't move it. Only two things reduce it: capture that makes frame *k* simultaneous, or freemocap using the per-camera times. **inferred**
- **To use per-camera times:** interpolate each camera's 2D keypoints from its own times onto the group times before `observation_buffers(...)` (`scientific_recording.py:103-108`, `posthoc_mocap_task.py:144-150`). Every input is already in `RecordingGroupTiming.cameras`. The plans forbid picking a *different frame* per camera from timestamps (`client-playback-design.md:195-197`) and inventing equal timestamps as the join condition (`operation-readiness-inventory.md:33-34`); a declared temporal interpolation would need a plan change. Also add a `TimingMethod` value for the new source (only `recorded` / `inferred_from_fps` / `mean_camera_times` exist, skellycam `recording_timing_reader.py:34-37`), so provenance says what the clock is. **code + inferred**

### (b) Occasional dropped frames

| How skellycam represents it | What happens in freemocap |
| --- | --- |
| Unequal per-camera frame counts | **Hard failure** in `VideoGroupHelper` (`video_group_helper.py:328-334`), `RecordingVideoSources` (`video_sources.py:46-48`), playback validity (`playback_router.py:784`, UI `usePlaybackController.ts:54`), calibration (`posthoc_aggregation_node.py:135-140`), import check (`mocap_router.py:171`). skellycam's own multiframe writer also raises (`create_multi_frame_csvs.py:36-38`). **code** |
| Gaps in `recording_frame_number` | **Hard failure**: "Camera timing does not cover the video frame grid" (`recording_timing_reader.py:65-68`). **code** |
| Equal counts, missing slot filled with a **duplicate image** | Runs. **Silently wrong**: the stale image is detected and triangulated with the other cameras' fresh images at the wrong time. The filter treats it as a real sample. **inferred** |
| Equal counts, missing slot filled with a placeholder **and flagged** in a new CSV column | freemocap ignores the flag today, so this is the same as the duplicate case. Small change: read the flag in `RecordingGroupTiming.resolve` and replace that camera's observation with an all-missing one before triangulation. Triangulation already accepts missing per-camera points: absent or zero-visibility keypoints become NaN (`freemocap/core/tracking/observation_buffer.py:33-48`), and the triangulator masks NaN cameras per point (`freemocap/core/tasks/triangulation/triangulator.py:226-230`). Annotation and playback keep working because the video frame exists. **code + inferred** |
| A whole-group slot missing (no camera has it) | If the group simply has no row there, everything runs. The gap shows as a 2-period interval. Gap filling still bridges it (66 ms < 100 ms). The filter **splits the run** (66 ms > 1.5 × 33 ms, `posthoc_filtering.py:91`), and pieces ≤ 15 samples stay unfiltered. Exports keep the true times. Blender plays at a uniform rate, so the gap is **compressed silently**. **code + inferred** |

### (c) Cameras at different frame rates

- Free-running cameras give unequal counts: the same **hard failures** as (b). Today lockstep forces every camera to the slowest one's rate (review P2), which hides this. **code**
- Making it work needs a group timeline that is not "ordinal of each video". Places that hard-code the single shared ordinal: `VideoGroupHelper.frame_count` (`video_group_helper.py:321-334`); `RecordingGroupTiming.resolve(frame_numbers=…)` (`recording_timing.py:27-28`); `CameraFrameKey` / `CameraFrameJoin` (`camera_join.py:15-64`); `ObservationCollection` (`scientific_recording.py:76-81`); the legacy ordinal loop (`mocap_detection.py:110-137`); the publication check (`observation_publication.py:100-102`); saved reload (`saved_observations.py:61-65`); triangulation (`posthoc_reconstruction.py:88-91`); calibration aggregation; UI playback (`usePlaybackController.ts:89, 111`). Each camera needs its own ordinal → time map plus an association policy: nearest frame within a tolerance, or 2D interpolation to group times. **code + inferred**
- Cheapest skellycam-side route that needs no freemocap redesign: write the group at one rate. A camera that is slower for that slot gets a flagged placeholder (case (b) row 4); a faster camera is decimated by nearest slot. This wastes frames but keeps every invariant. **inferred**

### (d) VFR video files or MJPEG files

- **Raw MJPEG, CFR AVI** (pts = slot index): reported count and fps are correct, and PyAV decodes every frame. It works with today's readers (`.avi` is accepted, skellycam `core/recorders/videos/video_filename.py:8`). Playback is re-encoded to H.264 anyway (skellycam `browser_stream.py:79`). **measured (synthetic) + code**
- **Raw MJPEG, CFR MKV**: works (count 90/90 in the test). **measured**
- **VFR MKV**: cv2's reported count is **wrong** (92 for 90 frames with one gap). That breaks `resolve_camera_timing` (CSV 90 ≠ 92), the "more frames than declared" EOF check (`mocap_video_node.py:148-152`), and the equal-count checks. **measured + code**
- **VFR MP4**: the count is right but fps is the average (29.35). Anything using fps is then wrong for individual frames: the inferred-timing fallback, UI frame = `round(mediaTime × fps)`, the UI seek, and the `~F` label (`usePlaybackController.ts:89, 111`). Post hoc decoding ignores PTS and is fine. **measured + code**
- **VFR AVI** cannot be written (muxer error on repeated rounded ticks; AVI has one fixed period). **measured**
- **A folder of JPEG files** is not readable (only container extensions are accepted). **code**
- A truncated JPEG is silently concealed (D5). **measured**
- Recommendation from freemocap's side: keep CFR containers whose ordinal = group slot, and put true times in the CSV (today's contract). Do not switch to VFR containers until the UI and the frame-count probe use decoded PTS. **inferred**

## 9. What already supports time-based association

- The storage model is timestamp-first. Every row carries `timestamp_s`. Per-camera `capture` and group `synchronized` TIMESTAMPS channels are kept separately (`observation_publication.py:119-127, 223-233`). Mixed-rate sensor groups round-trip (tests `freemocap/tests/test_recording_store.py:382`, `test_observation_samples.py:72`). That covers **different groups**, not cameras within one mocap group. **code**
- Filtering, gap filling and alignment use actual times and accept irregular intervals (`posthoc_filtering.py:104-115`; test `freemocap/tests/test_posthoc_filtering.py:20-21`). **code**
- UI 3D lookup is by time (`playback-data.ts:61-68`). **code**
- The plans already state the direction: "Different rates belong on timestamp timelines" (`current-work-plans/02-pipeline/media-identity-and-camera-matching.md:86`); dropped frames "require their actual mapping" (`:54`); "Mixed-rate fixtures retain all samples; playback aligns by timestamp without frame-number joins" (`posthoc-rebuild.md:354`). They also limit it: "This does not authorize asynchronous mocap video playback" (`posthoc-architecture-review.md:44-45`). **code (docs)**

## 10. Measured: raw-MJPEG and VFR containers through freemocap's probes

Harness: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad/notes/mjpeg_container_probe.py`. It muxes 90 synthetic 1280x720 JPEGs **without re-encoding**, then probes them the way skellycam's `VideoFileMetadata` (cv2 count/fps) and `SequentialVideoReader` (PyAV in-order decode, `is_corrupt`) do. The VFR cases use 33.3 ms ± 4 ms intervals with one skipped slot after frame 40. Output: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/d7b5ebd7-23e2-4038-b89c-9e7af70dd7af/scratchpad/notes/mjpeg_probe_out/probe_results.json` (cv2 4.12.0, PyAV 18.0.0, libavformat 62.12.102).

Reproduce: `C:/Users/Dom/GitHub/freemocap/skellycam/.venv/Scripts/python.exe -I mjpeg_container_probe.py <out_dir>`

| File | cv2 count | cv2 fps | PyAV decoded | Corrupt flagged | Note |
| --- | --- | --- | --- | --- | --- |
| mjpeg_cfr.avi | 90 | 30 | 90 | – | OK |
| mjpeg_cfr.mkv | 90 | 30 | 90 | – | OK |
| mjpeg_vfr_drop.mkv | **92** | 30 | 90 | – | count estimated from duration |
| mjpeg_vfr_drop.mp4 | 90 | **29.35** | 90 | – | fps is the average |
| mjpeg_vfr_drop.avi | – | – | – | – | mux error (AVI is fixed-period) |
| mjpeg_truncated_frame.avi (frame 45 cut to 1/3) | 90 | 30 | 90 | **none** | concealed silently |

Limits: synthetic content, one ffmpeg build, no camera-written file. A first run with a 1 ms time base in AVI produced 1000-fps files with 3000 index entries; that was a harness mistake, fixed by using a 1/30 s time base. It does show that an AVI writer must use the frame period as its time base.

## 11. What this means for the two options (freemocap side only)

| | 1. Revised OpenCV DirectShow stamps (post-retrieve, slot fit, drop detection) | 2. Custom MF with raw MJPEG (tier 0) |
| --- | --- | --- |
| freemocap change needed to ingest | None, if the CSV keeps its columns and meaning | None, if output stays CFR containers with ordinal = slot, plus the same CSVs |
| Where accuracy shows up | Group timeline: filter, gap fill, alignment, output time labels; per-camera 2D/capture rows; playback | Same |
| 3D accuracy | Unchanged unless lockstep/inter-camera offset improves or freemocap interpolates 2D in time (§8a) | Same; MF's real arrival/sample times make per-camera interpolation worthwhile |
| Drops / different rates | Need skellycam to keep equal-length, slot-aligned videos with a flag column, plus a small freemocap change to honour the flag (§8b) | Same; a free-running MF backend **must** do this or freemocap fails on unequal counts |
| Container | Unchanged | CFR AVI/MKV with raw JPEG passes today's probes. Avoid VFR (§10) and handle corrupt JPEGs explicitly (D5) |

Also fix D1 and D2 whichever option is chosen: they mis-show frames in playback today.
