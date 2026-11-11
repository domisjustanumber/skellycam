# freemocap reader B: how realtime, calibration, triangulation, filtering, skellytracker and skellyforge use frame timing

Written 2026-11-09. Code read from development-streaming snapshots: freemocap `c27fc299` (paths relative to `freemocap/` repo root), skellycam `169caf63`, skellytracker `03b9c1dc`, skellyforge `f5404db` (shallow clone, 2026-10-12). Nothing was run. Labels: **code** (read from source), **measured** (a result file in `research/usb_cameras` supports it), **inferred** (reasoned, not tested).

## 1. Summary

- **Realtime pairs cameras by frame index only. No capture timestamp reaches any realtime computation.** The 1€ filter, velocity gate and XCoM use `time.perf_counter()` taken when the aggregator processes a frame, not when it was captured. (**code**)
- **Posthoc is now timestamp-aware in time, but not across cameras.** Gap filling, Butterworth filtering, alignment, CoM derivatives and MediaPipe VIDEO timestamps all use the recording's multiframe timestamps (the mean over cameras of each camera's grab midpoint). Triangulation and calibration still treat "same frame index" as "same instant". (**code**) This corrects the earlier review (`docs/skellycam_timestamps_review.md` §1, last bullet), which read older code: on development-streaming, skellytracker no longer gets `frame_number / fps` in the posthoc path.
- **Every stage assumes equal frame counts and lockstep indices.** Several hard checks raise errors otherwise (table in §5). So skellycam cannot simply start delivering per-camera rates or per-camera drops. It would have to keep giving freemocap a multiframe contract, or freemocap would need a new time-alignment stage. (**code**)
- **Better per-frame timestamps alone do not improve triangulation**, because nothing pairs or interpolates by time. They improve the temporal stages (filter dt, Butterworth resampling, velocities) at once. Improving triangulation also needs either (a) skellycam building multiframes by time, or (b) freemocap interpolating each camera's 2D observations to a common time before DLT. (**inferred** from the code)
- **Scale (inferred):** an inter-camera offset of e ms on a point moving at v m/s puts the views v·e mm apart (2–5 mm per ms for a wrist at 2–5 m/s). Today's worst case of up to one frame period (~33 ms) is 66–165 mm for a wrist. Rolling-shutter row timing (measured upper bound ~30–31 ms per frame height on the C922) is the same size and no frame-level timestamp removes it.

## 2. How frames and timestamps reach freemocap

| Step | What travels | Timestamp? | Source |
| --- | --- | --- | --- |
| skellycam → freemocap | In-process `CameraGroup`. Per-camera shared-memory ring buffers, read by index. Not a websocket. | Frame metadata holds the lifecycle stamps, but realtime code reads only `frame_number` | `core/pipeline/realtime/realtime_pipeline.py:20-23`; `realtime_aggregator_node.py:422` (**code**) |
| "Latest multiframe" | `min` of every camera's latest frame number | none | skellycam `core/ipc/shared_memory/camera_group_shared_memory.py:32-33` (**code**) |
| Aggregator → camera nodes | `ProcessFrameNumberMessage(frame_number)`, always the **newest** multiframe, so the realtime pipeline skips frames when it is slow | none | `realtime_aggregator_node.py:671-686, 845-853` (**code**) |
| Camera node | `camera_shm.get_data_by_index(index=frame_number)` on **each camera's own ring**, the same index for every camera; warns if the slot holds another number | none | `realtime/camera_node.py:287-310` (**code**) |
| Pubsub topics | `CameraNodeOutputMessage`, `AggregationNodeOutputMessage` and friends carry `frame_number` only. The aggregator output validator requires every camera output to have the same frame number. | none | `pubsub/pubsub_topics.py:43-176` (no timestamp field in the file) (**code**) |
| Inference service | `InferenceRequest.timestamp_ms` exists but realtime never sets it | realtime: none; posthoc: recording ms | `pipeline/inference_service.py:45, 204`; `realtime_skeleton_inference_node.py:235`; `dataflow/tracker_adapter.py:120` (**code**) |
| Websocket to the UI | `FrameMessage.envelope.timestamp` = the mean over cameras of the (pre+post grab)/2 `perf_counter_ns` | display only | `api/websocket/websocket_server.py:353-364`; skellycam `core/types/frontend_payload_bytearray.py:133, 154-155` (**code**). The UI framerate meter ignores it and uses `perf_counter_ns()` on arrival (`websocket_server.py:499-521`) |

## 3. Per-stage timing assumptions

### 3.1 Realtime keypoint filtering (1€ filter, velocity gate, XCoM)

- **They use real elapsed time, but the time is processing time.** `frame_time = time.perf_counter()` is taken after collecting the camera outputs (`realtime_aggregator_node.py:897`). It is passed as `t` to `RealtimeKeypointFilter.filter` (`:970`) and `RealtimePointGate.gate` (`:992`). XCoM velocity uses another `perf_counter()` (`:248-258`). (**code**)
- `OneEuroFilter1D` computes `dx = Δx/Δt` and the smoothing factors from `Δt` (`tasks/mocap/realtime_filtering/one_euro_filter.py:65-84`). `predict` extrapolates `x + dx·Δt` (`:96-121`). The config comment says variable frame rate "is handled automatically" (`realtime_filter_config.py:39-40`). That holds only if `t` is the capture time. (**code**)
- **What goes wrong today (inferred):**
  - The aggregator always jumps to the newest multiframe, so consecutive processed frames are 1, 2 or more capture periods apart. `Δt` follows processing cadence and inference-latency jitter instead. Example: two processed frames 40 ms apart in processing time can be 33 or 67 ms apart in capture time, so the velocity estimate is off by up to about 2×. That moves the adaptive cutoff (`min_cutoff + β|v|`) and the gap-fill extrapolation.
  - The gate's 50 m/s threshold (`realtime_filter_config.py:101`, 50000 mm/s) is generous enough that this rarely matters there.
- **Fix that needs no skellycam change (inferred):** pass the multiframe's capture time (already in the ring-buffer frame metadata) as `t`, instead of `perf_counter()` at processing. Even today's grab midpoint would record a skipped frame as a ~67 ms step. A slot-fitted per-camera time (§6) would be better.
- **Frame-count windows:** model-scale fitting uses a 30-**frame** window, documented as "about a second at 30 fps" (`realtime_filter_config.py:72-89`). `RealtimeKeypointFilter.max_prediction_frames = 3` counts processed frames, not time (`realtime_keypoint_filter.py:60, 124`). These assume roughly constant fps. (**code**)

### 3.2 Realtime detection (skellytracker inside freemocap)

- **MediaPipe in VIDEO mode** (default `running_mode="video"`, skellytracker `core/sessions/mediapipe_session.py:22`) needs a timestamp per image. When none is given it uses `int(time.monotonic()*1000)` at detect time (`core/detectors/keypoint_detectors/mediapipe/body/mediapipe_pose_detector.py:105-110`, and the same in hands and face). Realtime never passes one (`camera_node.py:316-318`; `realtime_skeleton_inference_node.py:235`). So MediaPipe's internal temporal tracking runs on processing time. (**code**)
- **RTMPose path:** `video_fps=30.0` is hard-coded for the realtime tracker (`realtime_skeleton_inference_node.py:140`). It only sets the bbox redetect interval, `round(5.0·fps)` frames (`core/tracking/tracker_factory.py:194, 218`). It counts frame numbers, so skipped frames make redetects come sooner. Harmless. (**code**)
- **skellytracker's own 1€ keypoint smoothing assumes constant fps.** `_dt_from_context` always returns 1.0: "min_cutoff and beta are therefore in frames⁻¹ rather than Hz" (`core/tracker/detection_stage.py:810-818`). It is **off** in freemocap: `keypoint_smoothing` defaults to `None` (`core/config/detection_stage_config.py:27`) and freemocap never sets it (grep). Bbox smoothing is a per-frame EMA, `alpha=0.4` (`tracker_factory.py:251`). (**code**)
- **`Observation.timestamp`** (`core/data_primitives/observation.py`, field `timestamp: float | None`) is never set by the tracker. freemocap sets it only when it rehydrates saved observations (`core/recording/result_processing/saved_observations.py:91`). No tracking code reads it. (**code**)

### 3.3 Camera matching (live camera ↔ calibration identity)

- `MatchingSampleLayout.extract` raises unless every observation has the same `frame_number`: "Matching requires observations from one synchronized frame" (`tasks/calibration/camera_matching/observation_sampling.py:52-53`). (**code**)
- `MatchingSampleWindow` time is "elapsed monotonic time, not a camera's capture clock" (`:72-75`). The aggregator feeds `perf_counter()` (`realtime_aggregator_node.py:881-884`). Recorded matching uses the list index as time (`observation_sampling.py:113-114`). It is used only for sampling interval and is harmless. (**code**)
- **Effect of timing error (inferred):** cross-view samples of a moving subject carry the v·e displacement as epipolar error. That lowers matching fitness, but the matcher picks the best camera assignment rather than measuring, so it is tolerant.

### 3.4 Calibration (realtime ChArUco recorder → posthoc Anipose)

- **Recorder:** keyed by `CameraNodeOutputMessage.frame_number`, the connection frame number (`realtime/charuco_recorder_node.py:96-104, 152-159`). Frames the realtime pipeline skipped are simply absent. (**code**)
- **Posthoc reuse:** each camera's `recording_frame_number → connection_frame_number` map comes from that camera's timestamps CSV (`pipeline/posthoc/video_node.py:491-509`). Cached observations are re-keyed to recording frame numbers (`:380-385`). No time is used. (**code**)
- **Anipose:** rows carry `framenum=(0, frame_number)` (skellytracker `core/detectors/keypoint_detectors/charuco/anipose_export.py:60, 68`). `merge_rows` groups cameras by equal `framenum` (`tasks/calibration/anipose_calibration/helpers/freemocap_anipose.py:437-452`). Bundle adjustment fits **one rigid board pose per merged frame** (`helpers/bundle_adjust.py:570-591`). It drops points above a percentile threshold each iteration (`:195-207`). (**code**)
- **Assumption:** same index = same board pose in every camera. No stillness gate (also noted in `research/rolling_shutter/README.md`).
- **Effect of timing error (inferred):**
  - A board moved at 0.2–0.5 m/s with e = 33 ms is 7–17 mm off between views, about 2–5 px at 3 m (f ≈ 900 px at 720p).
  - That is several times a good calibration's sub-pixel residual. It is either absorbed into the extrinsics or rejected as outliers by the percentile filter.
  - Accurate timestamps would allow pairing calibration frames by time, or gating on board speed × inter-camera offset. The still-board proposal in `research/rolling_shutter/still_charuco_issue/` makes calibration insensitive to both timing and rolling shutter, so it is the cheapest fix.

### 3.5 Triangulation and reconstruction

- **Realtime:** `calibration.try_angulate(frame_number=..., frame_observations_by_camera=...)` runs per multiframe (`realtime_aggregator_node.py:906-955`; `tasks/calibration/shared/calibration_state.py:396-470`). It is plain DLT via SVD (`tasks/triangulation/helpers/triangulate_simple.py:5-26`). There is a reprojection gate at `max_reprojection_error_px = 60` (`realtime_filter_config.py:94`). (**code**)
- **Posthoc:** "Camera observation frame numbers must match exactly" (`core/reconstruction/posthoc_reconstruction.py:85-90`). The frame join needs exact, consecutive coverage per camera (`pipeline/dataflow/camera_join.py:37-38, 54-62, 73-74`). Sources must have equal frame counts and full coverage (`pipeline/dataflow/video_sources.py:45-56`). Posthoc inference needs consecutive frame numbers (`pipeline/inference_service.py:125-126`). (**code**)
- **Assumption:** index *k* in every camera is the same instant, and every image is captured all at once (no rolling-shutter row term).
- **Effect (inferred):** see §4. Fast limbs can also be **rejected** outright. A 165 mm separation at 3 m is ~50 px, close to the 60 px realtime gate. So timing error first shows up as missing wrists and feet in fast motion, then as bias.

### 3.6 Posthoc temporal processing (freemocap + skellyforge)

- **The timeline:** `RecordingGroupTiming.resolve` reads each camera's `timestamp.from_recording_start.sec` and the multiframe CSV's (`core/reconstruction/recording_timing.py:20-47`, via skellycam `core/timestamps/recording_timing_reader.py`). In skellycam that column is the per-camera grab midpoint (`core/timestamps/numpy_timestamps/create_camera_csvs.py:49-58`) and, for the multiframe, the mean of those across cameras (`create_multi_frame_csvs.py:44-45`). Without a sidecar it falls back to `frame/fps` (`recording_timing_reader.py:72-77`, method `INFERRED_FROM_FPS`). (**code**)
- **Where the synchronized (multiframe) timestamps are used:** (**code**)

  | Use | Source |
  | --- | --- |
  | MediaPipe VIDEO timestamps, ms from the first frame; raises unless strictly increasing at 1 ms resolution | `pipeline/dataflow/tracker_adapter.py:37-49, 120` |
  | Gap filling (skellyforge): linear interpolation in time; bridges a gap only if its bracketing samples are ≤ 100 ms apart; a frame where every keypoint is missing is a hard boundary | skellyforge `core/trajectories/gap_filling.py:7, 49-103`; freemocap wrapper `core/reconstruction/trajectory_gap_filling.py:35-39` |
  | Butterworth (freemocap): rate = 1/median interval; Nyquist check; splits runs at intervals > 1.5× median; interpolates each run onto a uniform grid, runs `sosfiltfilt`, interpolates back to the observed times | `core/reconstruction/posthoc_filtering.py:52-63, 66-119`; called at `pipeline/dataflow/recording_pipeline.py:208-210` |
  | Body/ground alignment: gaps > `maximum_gap_seconds` break episodes; time-weighted means | skellyforge `core/biomechanics/body_alignment.py:191-221`, `ground_alignment.py:105-125`; `recording_pipeline.py:218` |
  | CoM velocity/acceleration: central differences over real `Δt` | skellyforge `core/biomechanics/derived_kinematics.py:18-79` |

- **Per-camera timestamps** are stored with each observation (`pipeline/dataflow/saved_observation_source.py:28`; `scientific_recording.py:80`) but are never used to pair cameras. (**code**)
- **Assumptions:** one shared timeline for all cameras, strictly increasing. Equal `Δt` is **not** assumed; drops are handled as time gaps.
- **Effect of better timestamps (inferred):**
  - The Butterworth resample puts each sample at its stamped time. A stamp error δ moves the sample by about v·δ.
  - With the mean of four grab midpoints the error is already averaged, but the lockstep bias (up to one period, §6) is common to all cameras and does not average out.
  - A slot-fitted multiframe time would remove most of that, and drops would show up as exact 2P gaps. Those already split filter runs correctly (`posthoc_filtering.py:93`).
  - **Hazard:** if skellycam ever fills a dropped slot with a duplicate frame and a duplicate timestamp, `tracker_adapter.py:47-48`, `posthoc_filtering.py:56-58` and `gap_filling.py:64` all raise on non-increasing time.

## 4. Size of the effect: inter-camera offset → 3D error (inferred)

The two views of a point moving at v are d = v·e apart. DLT puts the 3D point somewhere between them. The error is on the order of d: about ½·d when the motion is across both rays, and up to ~1/sin(θ)·d along the epipolar direction for a ray angle θ (≈ 2·d at 30°). Pixel error ≈ f·d/Z with f ≈ 900 px (720p) and Z = 3 m. The e values come from §6.

| Inter-camera offset e | Where it comes from | d at 2 m/s (wrist, normal) | d at 5 m/s (wrist, fast) | d at 10 m/s (hand, throw) | px at 3 m, 5 m/s |
| --- | --- | --- | --- | --- | --- |
| 33 ms | today's worst case, lockstep index pairing (~1 period) | 66 mm | 165 mm | 330 mm | ~50 |
| 30 ms | rolling-shutter row term, top vs bottom of frame (C922 upper bound, **measured**) | 60 | 150 | 300 | ~45 |
| 16.7 ms | best possible nearest-neighbour pairing at 30 fps (P/2), no interpolation | 33 | 83 | 167 | ~25 |
| 8 ms | max error of a raw MF/DS host stamp (16 ms grid) | 16 | 40 | 80 | ~12 |
| 4.6 ms | std of a raw 16 ms-grid stamp (**measured**, C922) | 9 | 23 | 46 | ~7 |
| 1 ms | slot-fitted stamp, a plausible tier-0 target | 2 | 5 | 10 | ~1.5 |
| 0.5 ms | method floor of the flash test (**measured** upper bound for PTS and for a frame-counter fit on the C922) | 1 | 2.5 | 5 | ~0.8 |

- **Per ms: 2 mm at 2 m/s, 5 mm at 5 m/s, 10 mm at 10 m/s.**
- A slow board (0.3 m/s) costs 0.3 mm/ms, so 10 mm at 33 ms.
- For comparison, a typical static triangulation error from detector noise is ~5–15 mm (not measured here).

**Interpolation error, if freemocap resampled each camera's 2D track to a common time (inferred).** Linear interpolation over h = 33 ms has a worst case of a·h²/8: 2.8 mm at 20 m/s², 14 mm at 100 m/s² (a fast hand reversal). A cubic or 1€-predicted interpolant reduces this. So with accurate stamps, interpolation could leave a few mm, instead of 10–165 mm, in fast motion. Rolling shutter adds a per-keypoint time of row/height × ~30 ms. The same interpolation could handle that if freemocap used the keypoint's row. Neither exists today.

## 5. What breaks or improves under each skellycam change

| skellycam delivers… | Realtime | Calibration | Posthoc triangulation | Posthoc filtering / tracker |
| --- | --- | --- | --- | --- |
| **Accurate per-camera timestamps, same lockstep multiframes** | No change: nothing reads them. Easy win: use them as filter `t` (§3.1) and as MediaPipe `timestamp_ms` | No change | No change (pairs by index) | Better: filter grid, velocities and MediaPipe times follow capture time. Inter-camera spread becomes measurable (skellycam already writes `inter_camera.frame_grab_range.ms` in the multiframe CSV; freemocap does not read it: grep) |
| **Multiframes built by time** (nearest frame per camera to a group tick; same index contract) | Works unchanged: one index, one frame per camera. A 25.7 fps camera paired with 30 fps cameras repeats a frame in ~1 of 7 multiframes. Repeats must carry a flag, or the filter sees stale 2D data as new | Works; a repeated board view is a duplicate observation (harmless with a still board) | Works; offset bounded by half the **slower** camera's period (≤19.5 ms at 25.7 fps) instead of up to a full period | Works if the multiframe time is strictly increasing |
| **Independent per-camera frame indices and rates** | **Breaks:** `latest_multiframe_number = min(...)` plus `get_data_by_index(same index)` on every camera (`camera_node.py:287-310`); payload "Camera frame numbers must agree" (skellycam `frontend_payload_bytearray.py:94-95`); aggregator validator (`pubsub_topics.py:169-176`) | **Breaks** Anipose `framenum` merge (pairs unrelated frames) | **Breaks** `video_sources.py:45-56` (equal counts), `camera_join.py:73-74`, `posthoc_reconstruction.py:89-90` | Needs a new stage: interpolate each camera's 2D track to the group timeline before DLT |
| **Dropped frames visible** (gap in index or time) | Realtime already tolerates skipped multiframes (it processes the newest). A per-camera drop under lockstep is invisible today | A missing view drops that camera from the frame (the Anipose merge allows partial frames, `min_cameras=2`) | A per-camera hole in a video breaks the equal-count rule unless skellycam writes a placeholder plus a validity flag | Time gaps already split filter runs and gap-fill spans correctly; duplicate timestamps raise |

## 6. Bottom line for the user's two options (inferred, from this reader's side only)

Measured inputs (from `research/usb_cameras`):
- every Windows host stamp sits on an exact 16 ms grid (`docs/windows_results_20261106.md` §4);
- a frame-index fit leaves a residual equal to that grid's quantisation floor (4.58–4.66 ms; true error unscored except on the C922, where a frame-counter model scored at the 0.5 ms method floor: REPORT finding 9 and timestamp table);
- excess jitter above the floor: C930e 0.475 ms, Kiyo 1.645 ms.

| | Per-frame stamp error (per camera) | Inter-camera offset that freemocap actually triangulates with |
| --- | --- | --- |
| Today (OpenCV DS, grab midpoint, lockstep) | up to ~1 period, both signs (never measured) | up to ~33 ms, and sweeping 0–33 ms when rates differ (25.7 vs 30 fps beat ≈ 0.23 s) |
| 1. Revised DS (post-retrieve stamps + slot fit with drop detection) | ~1 ms on regular cameras if enough retrieves block; worse on Kiyo-like cameras | **unchanged** unless the multiframe is built by time (then ≤ P/2) or freemocap interpolates (then ~stamp error + a few mm) |
| 2. Custom MF, raw MJPEG, tier 0 (sample time/arrival + slot fit) | same fit floor, but on a real delivery event per frame, with no DS decode or lockstep wait. Drops seen directly. Different rates possible without forcing lockstep | same as 1: unchanged with index pairing; ≤ P/2 with time-built multiframes; ~1 ms + interpolation error with 2D resampling |

- **Neither option improves 3D accuracy by itself.** Both make the timing measurable, fix the temporal stages and remove the lockstep stall.
- **The 3D gain needs a freemocap change.** Either pair by time or interpolate 2D tracks by time; ideally per keypoint row, for rolling shutter.
- **An unmeasured constant per-camera latency (exposure → arrival) remains.** No tier-0 method can see it. It probably differs between camera models (REPORT finding 15: cross-camera sync not established). Settling it needs the sync rig.
