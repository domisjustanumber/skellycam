# Calibrate only from still ChArUco frames; overlay yellow while moving, green when still

## Summary

Calibration currently uses every ChArUco detection, including frames where the board is being waved around. On our rolling-shutter webcams those frames are geometrically wrong in a way the solvers can't see. This issue proposes:

1. **Posthoc:** before either solver runs, drop every frame index where the board was moving, using a per-camera 2D motion metric and a multi-camera rule.
2. **Realtime:** compute the same metric in each camera node and colour the ChArUco overlay **yellow while the board is moving** and **green once it is still**, plus a text status line. This tells the person calibrating to hold each pose.

A patch against `development` (`5632778a`) is attached as `proposed_changes.patch`. It touches freemocap only. skellytracker needs no changes.

## Motivation

- **Rolling shutter.** Common freemocap webcams such as the Logitech C922/C930e are rolling-shutter. Skellycam's screen-flash tests put the C922's readout at up to ~30–31 ms of a 33 ms frame at 720p30. That figure is an upper bound, because display scan-out is mixed into it, but readout is clearly a large fraction of the frame. A moving board is sheared and stretched within one image. It also sits at different image heights in different cameras, so each camera captures it at a different instant.
- **Both solvers assume one rigid board per frame.**
  - pyceres registers **one board pose per `frame_index`**, shared by all cameras (`pyceres_calibration/helpers/solver.py` ~L303–330). The Huber loss and the 15 px → 2 px outlier passes only down-weight the resulting error, and that error is systematic rather than random.
  - pyceres initialization runs `cv2.calibrateCamera` / `cv2.solvePnP` on every frame with enough corners (`pyceres_calibration/helpers/initialization.py`).
  - anipose (`anipose_calibration/helpers/bundle_adjust.py`, `freemocap_anipose.py::resample_points`) also uses one pose per frame. It samples frames for camera-pair coverage, not for stillness.
- **No gating exists today.** `charuco_board/charuco_observation_aggregator.py` and `posthoc_calibration_task.py` keep every detection.
- **Motion blur** while the board is waved also degrades corner accuracy.

## Proposed behaviour

**Realtime overlay** (per camera):

| State | Corners / segments | Status line |
|---|---|---|
| No board | unchanged | `⚠ NO BOARD DETECTED` (red, unchanged) |
| < 4 corners | unchanged | `⚠ INSUFFICIENT CORNERS` (orange, unchanged) |
| Board moving / not yet settled | **yellow** `#FFFF00` | `⟳ BOARD MOVING — HOLD STILL` |
| Board still | **green** `#00FF00` (today's colour) | `✔ BOARD STILL` |
| Stillness not reported (disabled / older backend) | green | `✔ BOARD DETECTED` (today's behaviour) |

ArUco markers stay orange. The info line gains `| Motion: 0.4 px/frame`, which also helps when tuning thresholds. Because every state has its own text label, the overlay doesn't rely on colour alone.

**Posthoc calibration:** moving-board frames are removed before both solvers. The task logs how many frames were kept per camera. If too few still frames remain, it fails with a message that tells the person to hold the board still.

## Design

**Metric (per camera, per frame).** Take the ChArUco corner IDs seen in both this frame and the reference frame (the previous usable frame). The board motion is the **median** displacement of those corners in pixels, divided by the frame-number gap. This is the same median-over-shared-corners idea as the existing `groundplane_math.find_stable_window`, but applied in 2D image space because no calibration exists yet.

- **Why px/frame and not px/s:** rolling-shutter shear and blur both scale with how far the board moves *during one frame*. Frame numbers are also already available in both paths: the connection frame number in realtime and the recording frame index in posthoc.
- **Dropped realtime frames:** dividing by the gap handles them. Gaps larger than `max_frame_gap` discard the reference.

**Hysteresis.**
- A transition counts as still when motion ≤ `max_motion_px_per_frame`.
- The board is reported still only after `min_still_transitions` consecutive still transitions.
- Going from still to moving is immediate.
- The first sighting, or the first frame after a gap, has no reference and so is not still.
- A frame with fewer than `min_shared_corners` corners reports not-still but keeps the reference and the still-run count. A one-frame detection dropout therefore doesn't restart the count, and the gap check still catches a stale reference.

**Multi-camera rule (posthoc).** Board motion is physical, so a frame index is kept only if **every camera with at least `min_shared_corners` corners reports it still**. If any of those cameras sees motion, the frame is dropped for all cameras. Cameras that barely see the board don't vote, and a frame no camera sees well is dropped. Dropped frames keep their `charuco` stage, but every point is blanked (NaN, visibility 0). Frame indices therefore stay aligned, and both solvers see an ordinary "board not detected" frame.

**Config** (`BoardStillnessConfig`, a frozen pydantic model in the same style as `PyceresCalibrationSolverConfig`):

| Field | Default | Meaning |
|---|---|---|
| `enabled` | `True` | Realtime: `False` keeps today's always-green overlay. Posthoc: `False` uses every frame (old behaviour). |
| `max_motion_px_per_frame` | `1.0` | Still threshold |
| `min_still_transitions` | `3` | Hysteresis length (about 100 ms at 30 fps) |
| `min_shared_corners` | `4` | Minimum corners to judge motion and to vote |
| `max_frame_gap` | `3` | A larger gap resets the reference |
| `min_still_frames_per_camera` | `10` | Posthoc fails below this number of still frames per camera |

The config is added as `CameraNodeConfig.board_stillness_config` and as `PosthocCalibrationPipelineConfig.board_stillness_config` (alias `boardStillnessConfig`). This mirrors how `charuco_board` already lives in both configs. The UI doesn't send the new field yet, so both configs use the defaults.

**Where the code lives.**
- **New file `freemocap/core/tasks/calibration/charuco_board/board_motion.py`.** It holds the pure metric, a small stateful `BoardStillnessTracker`, and the posthoc filter. It does no IO, so realtime and posthoc share one implementation.
- **Why freemocap and not skellytracker:** this is calibration policy (thresholds, the multi-camera rule, the posthoc frame-index semantics, freemocap config objects). skellytracker detectors are per-camera and per-frame, and the code only reads skellytracker's existing `Observation`/`Keypoints` primitives. If other consumers want it later, it could move into skellytracker's `temporal_processing`.
- **Posthoc choke point: `run_posthoc_calibration_task`**, directly after observation validation. It feeds `_convert_all_observations` (used by pyceres, the health check and `charuco_observations.json`) and `_run_anipose_path`. The observation aggregator is not a choke point because only anipose uses it. The unfiltered list still feeds `charuco_model_from_observations`, the board trajectory export.
- **Realtime path:** `CameraNode` → `CameraNodeOutputMessage.charuco_board_motion` → `AggregationNodeOutputMessage.charuco_overlay_data` → `CharucoOverlayData.board_still` / `board_motion_px_per_frame`. These travel in the **JSON** `FrontendPayload`. ChArUco overlays don't use the binary keypoints protocol: `BlockKind.CHARUCO_OVERLAY_2D` is defined but never encoded. So no wire-protocol change is needed.

## Proposed code changes

All changes are in the freemocap repo; see `proposed_changes.patch`. It passes `git apply --check` against `development` @ `5632778a`.

| File | Change |
|---|---|
| `freemocap/core/tasks/calibration/charuco_board/board_motion.py` (new) | `BoardStillnessConfig`, `BoardMotionSample`, `charuco_corner_pixels`, `board_motion_px_per_frame`, `BoardStillnessTracker`, `compute_board_motion_by_camera`, `still_frame_mask`, `filter_moving_charuco_frames` (returns `StillFrameFilterReport`, raises `CharucoStillnessError`) |
| `.../calibration/calibration_task_config.py` | add `board_stillness_config` (alias `boardStillnessConfig`) |
| `.../calibration/posthoc_calibration_task.py` | filter after validation; pass `calibration_observations_by_frame` to `_convert_all_observations` and `_run_anipose_path`; log the report; leave the board-model export unfiltered |
| `.../pipeline/realtime/camera_node_config.py` | add `board_stillness_config` |
| `.../pipeline/realtime/camera_node.py` | add `_build_board_stillness_tracker`; one tracker per camera, rebuilt or reset whenever the ChArUco tracker is; `update()` after each ChArUco detection |
| `freemocap/pubsub/pubsub_topics.py` | `CameraNodeOutputMessage.charuco_board_motion: BoardMotionSample \| None = None`; pass it into `CharucoOverlayData.from_observation` |
| `freemocap/core/viz/image_overlay/charuco_overlay_data.py` | add `board_still: bool \| None` and `board_motion_px_per_frame: float \| None` (default `None`); new `board_motion` kwarg |
| `freemocap-ui/.../image-overlay/charuco-types.ts` | `board_still` and `board_motion_px_per_frame` as `.nullable().optional()` (older backends still type-check) |
| `freemocap-ui/.../image-overlay/charuco-overlay-renderer.ts` | yellow `movingCharucoStyle` and yellow segments when `board_still === false`; status text; motion readout. `null`/`undefined` keeps today's green |
| `freemocap/tests/calibration/test_board_motion.py` (new) | unit tests (below) |

## Testing plan

**Unit tests** (`freemocap/tests/calibration/test_board_motion.py`, 15 tests, no IO):
- Metric: 0 for identical corners; normalised by frame gap; the median ignores one bad corner; `None` with too few shared corners; invisible and ArUco points are skipped.
- Hysteresis: the first frame is not still; still only after N transitions; moving is immediate; slow drift below the threshold counts as still; a one-frame dropout keeps the run; a gap larger than `max_frame_gap` resets; the config rejects nonsense values.
- Posthoc filter: one moving camera drops the frame for all cameras; a camera that can't see the board doesn't veto; dropped frames keep the `charuco` stage with blank points, the input is not mutated, and anipose sees an all-NaN row; too few still frames raises `CharucoStillnessError`.

**Regression:** run `tests/pipelines/test_posthoc_calibration_pipeline.py` (e2e, `freemocap_test_data`) with `enabled=True` and with `enabled=False`. Compare kept/dropped counts, reprojection error, and the board-reconstruction health metrics.

**Manual realtime check:**
1. Start realtime with 2+ cameras and ChArUco tracking on.
2. Wave the board: the corners are yellow and the status line reads `HOLD STILL` in every camera.
3. Hold the board still: about 100 ms later it turns green / `BOARD STILL`, and the motion readout settles at ≤ 1 px/frame.
4. Cover the board: `NO BOARD DETECTED` shows in red, as today.
5. Set `board_stillness_config.enabled=false`: the overlay is always green, as today.
6. Record a calibration while holding each pose for about 0.5 s, and check the log line `Charuco still-frame filter kept N/M frames ...`.
7. Record one while waving the board continuously, and check that it fails with the "Hold the board still" message.

## Open questions

1. **Thresholds.** Is 1.0 px/frame with 3 transitions right for 720p/1080p? It needs tuning on real recordings; the motion readout in the overlay makes that easy. Should it scale with image size?
2. **Realtime is per-camera, posthoc is all-cameras.** One camera can show green while another shows yellow, and the frame is dropped either way. Should the aggregator also compute a group-level flag, so the overlays only go green when calibration would actually keep the frame?
3. **Per-camera filtering for intrinsics.** The joint rule is required for extrinsics and bundle adjustment (shared board pose). Per-camera intrinsics (`initialization.py`'s `calibrateCamera`) could use each camera's own still frames and keep more data. Is that worth splitting out?
4. **Default on.** People who calibrate by waving the board continuously will now get an error instead of a calibration. Should we ship default-on with the clear error, or warn-only for one release?
5. **UI.** Expose an on/off toggle (and maybe the threshold) in `calibration-settings.tsx` / the calibration slice? The UI also doesn't send `pyceresSolverConfig` today, so this patch uses defaults only.
6. **`charuco_observations.json`** now holds only the kept frames, so comparison tools see what the solver saw. Should it also save the unfiltered set?
7. **Unrelated thing found on the way:** `charuco-types.ts` declares `metadata.has_pose`, but `CharucoMetadataModel` never sends it, so `POSE ✔` never shows. Fix separately?
