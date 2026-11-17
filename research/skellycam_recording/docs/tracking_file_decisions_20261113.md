# Tracking file and Lichtblick layout: grilling decisions (2026-11-13)

Provenance: a grilling session between Dom and the main agent on 2026-11-13, after the skellyfileformat spec v1 review. Facts came from read-only sub-agents; the main session spot-checked the key claims in the Lichtblick v1.30.0 source (commit fcfc7d5) and the freemocap/skellycam code. Nothing here is an accepted skellyfileformat entry yet: the entries are written after the grilling ends and Dom confirms the shared understanding.

## Background facts (sub-agent research, spot-checked)

- freemocap's realtime pipeline (freemocap `development` @5632778a) makes 2D keypoints per camera (RTMPose wholebody 133 points, MediaPipe body 33 / wholebody 211, ChArUco corners) and an aggregated 3D result (triangulated points, rigid skeleton, CoM, XCoM). It processes only the newest frame (sparse), 1€-filters the 2D points and sets low-confidence x,y to NaN. Results carry only skellycam's connection frame number. Nothing is saved during mocap recordings; calibration recordings pickle ChArUco observations to `output_data/charuco_observations_realtime.pkl`.
- skellycam's frame number counts from camera connection (`connection_frame_number` in the timestamps CSV). Shared memory holds grab/retrieve times but not the new format's arrival time. freemocap receives the full frame metadata but keeps only frame number, camera id and rotation.
- Lichtblick v1.30.0: the Image panel draws `foxglove.ImageAnnotations` from any topic, also from another MCAP file opened at the same time. "Sync annotations" (off by default) pairs by the image `timestamp` field and each annotation's own `timestamp`; with it off, pairing is by `log_time`. An unset image `timestamp` becomes {0,0}. The 3D panel draws `foxglove.SceneUpdate` and `foxglove.PointCloud` (colour by any field, per-point hover). The Image panel draws only annotation schemas; 3D data appears on the image only with a calibration topic.
- Lichtblick layouts: internal JSON (`configById`, react-mosaic `layout`, `globalVariables`, `playbackConfig`, optional `version`); v1.30.0 accepts version ≤ 1; the mrkbac audio fork writes version 2. Lichtblick never loads a layout from the data source. Dropping a folder installs every `.json` in it as a layout and opens the `.mcap` files together. Each import adds a layout named after the file base name. Annotation and SceneUpdate topics are hidden unless the layout sets `visible: true`. The Image panel ignores `display_rotation`; the layout sets `rotation`.
- Standard fields: `foxglove.PointCloud` (typed packed fields, FLOAT64 allowed) holds x, y, z, confidence and NaN losslessly. No standard schema has per-point names; vision_msgs has no keypoint message.

## Why sync mode does not work with our files

1. SFF-188/189: the image `timestamp` is the driver sample time, or unset. Unset becomes key 0 in Lichtblick, so every frame shares one key.
2. Tracking is sparse: sync mode shows only the newest frame that has both an image and a matching annotation, so the video would freeze at the tracking rate.
Default mode pairs by `log_time`: copy the source frame's `log_time` into each 2D tracking message. (A hands-on desk test of this is running.)

## Decisions

| Q | Decision |
|---|---|
| Root | freemocap (FMC) writes a separate tracking MCAP per take. skellycam writes a Lichtblick layout file; FMC updates it to include the tracking data. |
| Q1 | Purpose: both review and reuse. FMC must be able to re-read the data; what it does with it is FMC's business. |
| Q2 | Same `freemocap` profile, new file kind `tracking`, same `take_uuid`; grouped with its take, not counted in `group_size`. |
| Q3/Q22 | Standard schemas only: `foxglove.PointCloud` storage channels plus Foxglove display channels. No `freemocap.*` protobuf schema. |
| Q4 | Keep SFF-188/189 unchanged; sync off; pair by copied `log_time`. (Dom asked for examples and a first-hand test: running.) |
| Q5 | In format 2.0 as its own spec part with its own gates, drafted after core spec draft v2 passes gate 1. |
| Q6 | Same writing rules as device files (chunks, CRCs, fsync, crash read, repair after consent); 1 message per chunk. |
| Q7 | Core spec v2: for a camera with no frame counter, `sequence` = skellycam's connection frame number modulo 2^32. |
| Q8 | A 2D tracking message links to its frame only by the copied image `log_time` (int64, exact). |
| Q9 | Store both raw and filtered 2D. |
| Q10 | 2D points in stored-JPEG pixel coordinates (before `display_rotation`); FMC converts. |
| Q11 | 3D in mm in the calibration world frame; a calibration ID identifies the calibration (mid-take reload = new ID). Dom: 3D points are tied to their own timing markers, only loosely coupled to image frames. |
| Q12 | Only frames of the take; `freemocap.recording` identical to the camera files; skellycam hands the take facts to FMC at record start; no tracking file when realtime is off. Calibration and main recording are separate takes. |
| Q13 | The layout is not part of the format spec: skellycam's own entry, FMC's spec for its additions; the format spec says a take folder MAY hold a viewer layout file. |
| Q14 | Layout version 1, pinned to Lichtblick v1.30.0, with a check that v1.30.0 loads it. |
| Q15 | The layout is the only top-level `.json` in the take folder; the recording info JSON moves to a subfolder. Users drop the take folder onto Lichtblick. |
| Q16 | Lichtblick v1.30.0 adds a new layout entry on every drop or import, whatever the name (verified in source); only `layoutUrl` replaces same-named layouts. See Q30. |
| Q17 | Baseline layout: one Image panel per camera (explicit `imageTopic`, `rotation` = `display_rotation`, sync off), speed 1, no audio panel. Dom adds: an errors panel that shows gaps in the recording, and the arrangement must match what skellycam shows during recording (sub-agent running). |
| Q18 | skellycam writes the layout atomically at take start; FMC edits it atomically after its tracking file finishes, finds panels by `imageTopic`, turns its annotation topics on, adds a 3D panel; never removes skellycam's panels. |
| Q19 | Dom: 3D points do not link to source frames; they are temporally separate, and the clock time is the only thing that syncs frames and 3D data. |
| Q20 | Spec in 2.0 after core v2 gate 1; implementation in phase 2 with the arrival time added to skellycam's shared-memory frame metadata. |
| Q21 | A 2D result with no matching image `log_time` is kept; the reader reports a per-camera count; no per-message warning. |
| Q23 | Write the display channels (`ImageAnnotations`, `SceneUpdate`); no Lichtblick extension needed. |
| Q24 | Topics: `/cameras/<label>/tracking/<tracker>/raw`, `.../filtered` (PointCloud), `.../annotations` (ImageAnnotations); `/tracking/<tracker>/points3d`, `/tracking/<tracker>/skeleton` (PointCloud), `/tracking/<tracker>/scene` (SceneUpdate). |
| Q25 | Primary-source check: channel metadata is the established place for per-channel facts (immutable per channel; Lichtblick ignores it); COCO and NWB ndx-pose define names + edges; `foxglove.Log` + JSON is only a convention; ROS 2 uses `ParameterEvent`; MCAP Metadata records have no time. See Q37, Q38. |
| Q26 | Float64. |
| Q27 | 3D storage keeps all N rows with NaN; no `point_index`. |
| Calibration overlay | See Q31. |
| Q28 | Dom asked for research on sync mode and 3D alignment; settled by Q33. |
| Q29 | Dom asked for primary-source research on Q25; settled by Q37 and Q38. |
| Q30 | Layout names describe what the layout shows, not the take (e.g. "3 cameras", "charuco", "person"), because one layout serves many recordings. (Follow-up Q41 open.) |
| Q31 | The tracking file carries per camera `/cameras/<label>/tracking/calibration` (`foxglove.CameraCalibration`, frame_id = label, unrotated size, `plumb_bob`, D = [k1,k2,p1,p2,0], K with cx+0.5 and cy+0.5, R = I, P = [K\|0]) and one `/tracking/tf` (`foxglove.FrameTransforms`, world → label, metres), at take start and on each reload (old copy repeated 1 ns before the new one). FMC converts its rotated-image calibration to the stored image. The layout sets each Image panel's `calibrationTopic`. |
| Q32 | 3D storage PointClouds stay in mm (bit-exact); display SceneUpdate is in metres; the layout hides the mm clouds from the image overlay. |
| Q33 | Per camera, a display-only `/cameras/<label>/tracking/<tracker>/scene` (SceneUpdate, metres): each frame gets the 3D result nearest its capture time, `log_time` = that frame's arrival, true time in `timestamp`. Written by FMC after the take from the fitted times. The 3D panel follows the first camera. Camera files and ADR-752H unchanged. |
| Q34 | Core spec v2: a WARNING `foxglove.Log` `skellyfileformat.frame_gap` on `/cameras/<label>/log` at the first frame after a sequence jump ("<label>: N frames missing (sequence a→b)" or "sequence reset"), not double-counting encoder skips; `encode_skip` text names camera and frame; reader warning code `frame_gap`; every camera file declares its log channel up front. |
| Q35 | Layout bottom strip: a "Gaps and errors" Plot (points, one series per camera on `/cameras/<label>/log.level`, whole take) and a Tab panel with one Log panel per camera. |
| Q36 | The UI that starts the recording sends its grid (columns, rows, tile order incl. drags); skellycam writes the layout from it; fallback = freemocap-ui's tiling rule at 16:9 in camera-index order; skellycam-ui's auto tiling switches to that rule (and its overlay column-count bug is fixed); short last rows stretch; Image panel titles "#index · label". |
| Q37 | Proposed: channel-metadata keys named after NWB ndx-pose (v0.4.0 schema checked: `Skeleton.nodes`/`edges` 0-indexed uint8; one `PoseEstimationSeries` per body part with float32 `confidence` and a `definition` attribute; `PoseEstimation` has `scorer`, `source_software` + `version`): `nodes`, `edges` (0-based), `source_software`, `source_software_version`, `scorer`, `confidence_definition` (our flat rename of the `definition` attribute). Agreed by Dom. |
| Q41 | Replaced by Q42 (the hash tag is dropped). |
| Q42 | skellycam labels cameras `cam1`…`camN` in the grid order at take start; `camera_key` (SFF-183) becomes a MUST for capture writers (core spec v2) and is the physical identity; FMC matches calibrations by `camera_key`, never by label (USB indices are not stable: usb_cameras REPORT finding 23). Layout names: `<N> cameras` + `charuco` / `person` as present, plus ` · rot a/b/c` only when a camera is rotated. |
| Q38 | Mid-take parameters: a `freemocap.ParameterEvent` protobuf schema mirroring ROS 2 `rcl_interfaces/ParameterEvent` on `/tracking/parameter_events`; all values as `new_parameters` at take start, then one event per change. (First custom schema; amends Q22.) |
| Q39 | 2D display: per camera, one `ImageAnnotations` for every frame; `log_time` = frame `log_time`; every annotation `timestamp` = image `timestamp`, or an explicit zero when unset (never unset: sync mode crashes); untracked frames get an empty POINTS placeholder. Layout keeps sync off. (Desk test `recording_upgrade/results/tracking_sync/`.) |
| Q40 | Live: FMC writes only storage channels (raw/filtered 2D, 3D, calibration, transforms, parameter events). After the take: FMC writes all display channels from the camera files and its storage, then updates the layout. Display channels can be rebuilt from storage. |
