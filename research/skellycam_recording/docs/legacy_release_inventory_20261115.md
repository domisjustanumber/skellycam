# Legacy recording folders in freemocap releases (inventory)

Status: research report, 2026-11-15. A read-only sub-agent scan of the 87 non-alpha freemocap release tags (v0.0.1 to v1.8.2) and the skellycam/skellytracker versions they pin. The main session spot-checked two v1.x claims: skellycam v2025.09.1097 `save_synchronized_videos.py:101` (`Camera_{id:03}_synchronized.mp4`) and freemocap v1.0.25 `data_loader.py:88-101` (timestamps `*.npy`, nanmean across cameras). Nothing was run.

Written for: Dom and agent sessions writing the skellyfileformat legacy-recognition rules (plan decision A6).

---

FreeMoCap legacy recording-folder inventory, all non-alpha releases (read-only research)

I read the code at local tags only: freemocap, skellycam, skellytracker. Nothing was run, and nothing was written or changed in git. Citations are tag:path:line, and "NV" means not verified. I did the v1.x and skellycam/skellytracker work myself. Two sub-agents covered v0.0.x and v0.1.0, and I spot-checked four of their claims (v0.0.17 recordingconfig.py:11, v0.0.1 initialization.py:24, v0.0.50 timesync.py:136-138, v0.1.0 src/cameras/save_synchronized_videos.py:103).

TAG SET (87)
- v0.0.1 … v0.0.54 (43 tags), v0.1.0, and v1.0.25 … v1.8.2 (43 tags, including '1.1.0').
- v0.0.1b/c/d and v0.0.2b are same-day patch letters, not betas. They are included, and none changes the output compared with the tag before it.
- '1.1.0' (2024-01-01) is a different commit from 'v1.1.0' (2024-02-26). '1.1.0' is v1.0.34 plus one logging line and still reports `__version__ = "v1.0.34"` (1.1.0:freemocap/__init__.py). Treat it as v1.0.34.
- Excluded: v1.0.0-rc … v1.0.23-rc and v2.0.0-alpha.*.

DEPENDENCY PINS THAT AFFECT THE RECORDING FOLDER (from each tag's pyproject.toml)
| freemocap | skellycam | skellytracker | skelly_synchronize | blender addon |
|---|---|---|---|---|
| v0.0.x, v0.1.0 | none (own camera code) | none | none | own megascript |
| v1.0.25 | 2023.9.1086 | none | 2023.10.1027 | "*" |
| v1.0.26-28 | unpinned | none | >=2023.9.1026 | git / unpinned |
| v1.0.29-30 | zip of branch philip/pyside6-change (not present locally) | none | >=2023.9.1026 | unpinned |
| v1.0.31 | 2023.12.1087 | none | >=2023.9.1026 | unpinned |
| v1.0.32-34, 1.1.0 | 2023.12.1090 | none | 2023.12.1029 | 2023.10.1016 |
| v1.1.0 | 2023.12.1090 | 2024.1.1008 | 2023.12.1029 | 2023.10.1016 |
| v1.1.1 | 2023.12.1090 | 2024.3.1009 | 2023.12.1029 | 2023.10.1016 |
| v1.2.x | 2023.12.1090 | 2024.04.1014 | 2023.12.1029 | 2023.10.1017 |
| v1.3.0 | 2024.07.1092 | 2024.06.1016 | 2024.07.1032 | v2024.07.1022 |
| v1.3.1-1.4.5 | 1092 / 1093 / 1094 | 2024.08.1018 | 2024.07.1032 | v2024.09.1024 |
| v1.4.6-1.5.4 | 2024.09.1094 | 2024.09.1019 | 2024.07.1032 | 2024.12-2025.1 |
| v1.6.x | 2025.1.1096 | 2025.5.1022 | 2025.04.1037 | v2025.1.1035 |
| v1.7.0-1.7.1 | 2025.09.1097 | 2025.6.1023 | 2025.04.1037 | v2025.8.1037 |
| v1.7.2-1.8.2 | 2025.09.1097 | 2025.10.1024 | 2025.04.1037 | 2025.8 / 2025.11 / 2026.04.1039 |

skellyforge is pinned too, but it writes no files during processing.

Availability of these repos:
- skellycam: the writer code is byte-identical across every pinned tag from v2023.09.1086 to v2025.09.1097. I checked with git diff on skellycam/opencv/video_recorder, diagnostics and frame_payload.py.
- skelly_synchronize: not available locally (no repo, not in any venv). Its output for "import + synchronize" is NV.
- Blender addon: there is no repo. Only freemocap_blender_addon 2026.4.1041 is installed in freemocap/.venv, and no release pins that exact version.

======================================================================
1. ERA TABLE
======================================================================

------------------------------------------------------------
v0.0.x eras (2021-06-27 to 2022-07-16), from the sub-agent report
------------------------------------------------------------
Folder layout:
- Data root: `<cwd>/Data/` (eras A-C), then `<path>/FreeMocap_Data/` (D onward; from v0.0.43 the default path is ~).
  - v0.0.17:freemocap/recordingconfig.py:11; v0.0.43:freemocap/session.py:46-48.
- Session folder: `sesh_%y-%m-%d_%H%M%S` (A-D), e.g. sesh_21-06-27_153012 (v0.0.1:freemocap/initialization.py:24).
- From v0.0.18: `sesh_%Y-%m-%d_%H_%M_%S` (v0.0.18:freemocap/webcamGUI.py:34). The ID is editable in the GUI.

Files present in every v0.0.x era:
- `RawVideos/raw_cam{N}.mp4`, N 1-based. OpenCV writer, fourcc from user parameters (DIVX by default), .mp4 container, default 640x480 at 25 fps (v0.0.1:freemocap/runcams.py:24; webcam/startcamrecording.py:58,67).
- `SyncedVideos/{sid}_synced_Cam{N}.mp4`, with rotation applied (v0.0.1:freemocap/webcam/videotrim.py:29,40).
- `CalVideos/{sid}_trimmed_Cam{N}.mp4`, DIVX (v0.0.1:freemocap/calibrate.py:180-200).
- Timestamps CSV from pandas: unnamed index column, then Cam1..CamN.
  - Float seconds relative to `beginTime = time.time()`; NaN-padded where cameras differ in length (v0.0.1:freemocap/runcams.py:14,67-73).
- Per-camera timestamp pickles named `Cam{N}` with no extension (v0.0.1:freemocap/webcam/startcamrecording.py:79-80).
- `{sid}_config.yaml` (ruamel) in the session root.
- Calibration file: anipose `CameraGroup.dump` TOML (v0.0.1:freemocap/fmc_anipose.py:1770-1776).
  - Tables `[cam_0]`… have keys name, size, matrix, distortions, rotation (Rodrigues), translation.
  - `name` holds "1","2"… (1-based strings, v0.0.1:freemocap/calibrate.py:22).
  - `[metadata]` defaults to `{}`; whether it is ever written is NV.
- 2D arrays: [cam, frame, point, 3] = x px, y px, confidence.
- 3D arrays: [frame, marker, xyz] in charuco square units (mm). The square size was 82 mm up to v0.0.17 and 36 mm from v0.0.18 (v0.0.17 / v0.0.18 freemocap/fmc_runme.py:141 / :41,166).
- Reprojection-error arrays: [frame, marker], in pixels.

| Era | Tags | What changes |
|---|---|---|
| A | v0.0.1-1d (and the v0.0.2 old entry point) | Folders RawVideos, SyncedVideos, CalVideos, OpenPoseData, MediaPipeData, `DLCdata`, imOut, and `Data Arrays` (with a space) (recordingconfig.py:26-56). Root: `{sid}.csv` timestamps, `sessionSettings.txt`, `{sid}_calibration.yaml` (TOML content despite the .yaml name, calibrate.py:29-31,80), `merged.npy` (object array), `{sid}_outVid.mp4`. Yaml keys `CamInputs` / `Paths`. Pickles and `parameters.yaml` go to the cwd, outside the session. |
| B | v0.0.2b, v0.0.4-v0.0.12 | `DataArrays` (no space), `DLCData`. Yaml keys `recording_parameters` / `session_paths` (v0.0.2:freemocap/session.py:86-126). v0.0.12 adds `DataArrays/charuco_2d_points.npy` (object array) and `charuco_3d_points.npy` [24,3]. |
| C | v0.0.13-v0.0.15 | Timestamps move to `RawVideos/{sid}_timestamps.csv`; pickles move to `RawVideos/Cam{N}` (v0.0.13:freemocap/runcams.py:74-75). v0.0.15 adds `OpenPoseData/openPoseVideo_cam{0..}.mp4` (0-based). |
| D | v0.0.17 | Root folder becomes `FreeMocap_Data` (lower-case c). |
| E1 | v0.0.18-v0.0.37 | Long session ID format. Adds `*_reprojErr.npy`, `charuco_3d_reprojErr.npy`, `{sid}_animVid.mp4`. `charuco_2d_points.npy` becomes a float [cam, frame, 24, 2] array (v0.0.18:freemocap/calibrate.py:79-80,144-145). MediaPipe PNG output stops; the empty folders remain. |
| E2 | v0.0.39-v0.0.42 | `mediaPipe_2d.npy` renamed `mediaPipeData_2d.npy` (v0.0.39:freemocap/fmc_mediapipe.py:305). v0.0.41-42 leave CalVideos/ empty. |
| F1 | v0.0.43 | `{sid}_calibration.toml` plus `{sid}_calibration.pickle` (v0.0.43:freemocap/calibrate.py:60,111-117). No MediaPipeData folder. Optional misnamed Blender files `DataArraysskeletal_animation_session.{blend,fbx,gltf,usdc}` in the root. |
| F2 | v0.0.45-v0.0.48 | Adds `*_3d_smoothed.npy` (v0.0.45:freemocap/fmc_runme.py:241,263), `DataArrays{sid}.blend`, and `DataArrays{sid}_local_bone_rotations.csv`. |
| G | v0.0.50-v0.0.51 | Adds `RawVideos/Cam{N}_unix_timestamps` (pickle), `RawVideos/{sid}_unix_timestamps.csv`, and root `unix_synced_timestamps.csv`. Padded frames become a copy of the previous frame instead of black (v0.0.50:freemocap/webcam/videotrim.py:30,55,66). |
| H | v0.0.52 | `{sid}.blend` correctly placed (v0.0.52:freemocap/freemocap_blender_megascript.py:1270-1273). |
| I | v0.0.54 | cam0 pinning (calibrate.py:25-35). Optional `Annotated_Videos/{sid}_annotated_video_{1..}.mp4` (mp4v), `mediaPipeSkel_3d_raw.npy`, `_smoothed_unrotated.npy` (v0.0.54:freemocap/fmc_runme.py:225-262). |

What v0.0.x reads back: the config yaml, the timestamps CSVs, the calibration file, and DataArrays/*.npy (v0.0.18:freemocap/session.py:165-188; v0.0.54:freemocap/reconstruct3D.py:17).

------------------------------------------------------------
v0.1.0 era (2023-02-03), from the sub-agent report; own src/ code, no skellycam
------------------------------------------------------------
Base folder `~/freemocap_data/` (v0.1.0:src/config/home_dir.py:10,86-92) holds:
- `logs/log_%m-%d-%Y-%H_%M_%S.log`
- `most_recent_session_id.toml` (one key, `session_id`)
- `last_successful_calibration.toml`

Session folder `session_%Y-%m-%d-%H_%M_%S` (note the dash before the hour; editable; home_dir.py:43-49) holds:
- `synchronized_videos/Camera_000.mp4`: MP4V; fps = per-camera median of 1/diff (video_recorder.py:42-49,82-96).
- `synchronized_videos/timestamps/Camera_000_binary.npy` and `Camera_000_timestamps_human_readable.csv` (video_recorder.py:146-164).
- `synchronized_videos/diagnostic_plots/timestamp_diagnostic_plots.png`
- `calibration_videos/`: same layout. If missing, the whole synchronized_videos tree is copied in (main_window.py:651-663).
- `camera_calibration_data.toml` in the session root.
  - `[cam_N]` with `name` = "Camera_000".
  - `[metadata]` charuco_square_size, plus charuco_board_object, which actually holds the session id because of a bug (anipose_camera_calibrator.py:64-74).
- `annotated_videos/Camera_000_mediapipe.mp4`
- `output_data/raw_data/mediapipe_2dData_numCams_numFrames_numTrackedPoints_pixelXY.npy`: [cam, frame, 553, xy].
- `.../mediapipe_3dData_numFrames_numTrackedPoints_spatialXYZ.npy` and `..._reprojectionError.npy`
- `output_data/partially_processed_data/mediaPipeSkel_3d_origin_aligned.npy`
- `.../center_of_mass/{segmentCOM_frame_joint_xyz,total_body_center_of_mass_xyz}.npy`
- `output_data/mediapipe_{body,right_hand,left_hand,face}_3d_xyz.{npy,csv}`
- Optional: `skeleton_segment_lengths.json`, `<session>.blend` in the root, and a copied log.

Marker order is body 33, right hand 21, left hand 21, face 478 (mediapipe_skeleton_detector.py:46-56,120-132).

Batch/notebook processing writes a different layout, with no partially_processed_data (process_session_folder.py:155-163).

------------------------------------------------------------
v1.x common layout (skellycam writer + freemocap pipeline)
------------------------------------------------------------
Base folder `~/freemocap_data/` (v1.0.25:freemocap/system/paths_and_filenames/path_getters.py:54-63). The folder became user-configurable through gui_state from v1.2.0 (v1.2.0:…/path_getters.py, `gui_state.freemocap_data_folder_path`).
- `logs_info_and_settings/logs/log_%m-%d-%Y-%H_%M_%S.log` (path_getters.py:36-44; unchanged in v1.8.2:42-43)
- `logs_info_and_settings/most_recent_recording.toml`, key `most_recent_recording_path` (path_getters.py:159-188)
- `logs_info_and_settings/last_successful_calibration.toml` (path_getters.py:191-192)
- `logs_info_and_settings/gui_state.json` (path_getters.py:163-164). By v1.8.2 it lives in the package folder, and the old location is read as a fallback (v1.8.2 path_getters diff).
- `calibrations/<calib_recording_name>_camera_calibration.toml` (path_getters.py:47-48,66-72; anipose_camera_calibrator.py:89-95)
- `recording_sessions/session_%Y-%m-%d_%H_%M_%S/<recording_name>/` (path_getters.py:75-78,104-137)
  - There is one session folder per app launch: the path is cached in a module global (path_getters.py:120-128).
- Recording name: `recording_HH_MM_SS_gmt±H` (path_getters.py:81-101), plus optional suffixes:
  - `_calibration` when the "Record Calibration Videos" radio button is on;
  - `__<user tag>` (double underscore) (v1.0.25:freemocap/gui/qt/widgets/camera_controller_group_box.py:213-222; v1.8.2 same file:305-313).
  - Example: `recording_15_47_37_gmt-4` (v1.0.25:freemocap/data_layer/data_saver/data_saver.py:110).
- Imported videos go to `recording_sessions/import_<source folder name>/` with no session_ level (v1.8.2:freemocap/gui/qt/widgets/import_videos_wizard.py:71,86-87).

Recording folder contents, files written by skellycam (identical for all pinned versions):

synchronized_videos/Camera_{i:03d}_synchronized.mp4
- Writer: skellycam save_synchronized_videos.py:98-102 (v2025.09.1097).
- fourcc mp4v, MPEG-4 Part 2 in .mp4 (v2023.09.1086:skellycam/opencv/video_recorder/video_recorder.py:95-104).
- fps metadata = nanmedian(1/diff(timestamp_ns))*1e9, computed per camera (video_recorder.py:49-54), so cameras can get different nominal fps.
- BGR frames from OpenCV, optionally cv2.rotate'd at capture (v2025.09.1097:skellycam/opencv/camera/internal_camera_thread.py:116-120).
- Read back by freemocap: yes, as the 2D tracking input. For a calibration recording, these same files are the calibration videos (v1.0.25:freemocap/gui/qt/widgets/control_panel/calibration_control_panel.py:288).

synchronized_videos/timestamps/Camera_000_synchronized_binary.npy
- 1-D float64, one value per written synced frame (video_recorder.py:150-171).
- Values are `time.perf_counter_ns()` taken right after grab+retrieve (internal_camera_thread.py:116-118). Units are ns on an arbitrary monotonic epoch, not Unix and not relative to the recording start.
- Read back: yes. DataLoader globs `*.npy` here, keys each camera by file stem, and takes the nanmean across cameras (v1.0.25:freemocap/data_layer/data_saver/data_loader.py:88-101).

synchronized_videos/timestamps/Camera_000_synchronized_timestamps_human_readable.csv
- `pd.DataFrame(arr).to_csv()`: header `,0`, then index and value columns (video_recorder.py:174-179).
- Not read back.

synchronized_videos/timestamp_diagnostic_plots.png and first_and_last_frames.png
- Written on Windows only (save_synchronized_videos.py:106-117; create_diagnostic_plots.py:40-47).

Recording folder contents, files written by freemocap: v1.0.25 baseline (era V1a). Pipeline in v1.0.25:freemocap/core_processes/process_motion_capture_videos/process_recording_folder.py.

annotated_videos/Camera_000_synchronized_mediapipe.mp4
- skellycam VideoRecorder.save_image_list_to_disk (mp4v), fps = source fps (v1.0.25:…/mediapipe_skeleton_detector.py:180-191).

output_data/raw_data/mediapipe2dData_numCams_numFrames_numTrackedPoints_pixelXY.npy
- [cam, frame, 553, 3]. Despite the "pixelXY" name, channel 2 is mediapipe z*image_width, not confidence (mediapipe_skeleton_detector.py:402-460).
- Marker order: body 33, right hand, left hand, face 478 (FACEMESH_NUM_LANDMARKS_WITH_IRISES, :62).
- NaN where not detected.
- Read back: yes, when 2D tracking is skipped (process_recording_folder.py:85-92).

output_data/raw_data/mediapipeBodyWorld_numCams_numFrames_numTrackedPoints_XYZ.npy
- Pose world landmarks multiplied by pixel width/height, so the scaling is meaningless (:419-428, 292-295).
- Written in V1a only.

output_data/raw_data/mediapipe3dData_numFrames_numTrackedPoints_spatialXYZ.npy
- [frame, marker, xyz]: raw triangulation in the calibration world frame, mm (triangulate_3d_data.py:159).
- Read back: yes (skip-triangulation path, :134-141).

output_data/raw_data/mediapipe3dData_numFrames_numTrackedPoints_reprojectionError.npy
- [frame, marker], mean pixel error across cameras.

output_data/mediaPipeSkel_3d_body_hands_face.npy
- The raw 3D data rotated to (x, z, -y) (process_recording_folder.py:182; rotate_by_90_degrees_around_x_axis.py:11-12).
- Then skellyforge: gap fill, Butterworth (fs 30, cutoff 7, order 4 by default), "good frame" step. Skeleton rotation is turned off (post_process_skeleton.py, `PARAM_ROTATE_DATA = False`).
- Saved at :192-196. Read back by DataLoader and Blender.

output_data/center_of_mass/segmentCOM_frame_joint_xyz.npy and total_body_center_of_mass_xyz.npy
- Shapes [frame, segment, xyz] and [frame, xyz] (:203-216).

output_data/mediapipe_{body,right_hand,left_hand,face}_3d_xyz.npy and .csv
- Writer: convert_mediapipe_npy_to_csv.py:97-171, run twice by duplicated code at :246-320.
- CSV header columns:
  - body: `nose_x, nose_y, nose_z…` (:113)
  - hands: `right_hand_wrist_x…` / `left_hand_…` (:119,125)
  - face: `face_0000_x…`
- index=False. body.csv is read back.

output_data/mediapipe_skeleton_segment_lengths.json and mediapipe_names_and_connections_dict.json
- Written at process_recording_folder.py:245-255.

output_data/recording_parameters.json
- The processing-parameter model dumped as a dict, excluding recording_info_model (v1.0.25:freemocap/gui/qt/workers/process_motion_capture_data_thread_worker.py:40-49).
- V1a top-level keys: mediapipe_parameters_model {mediapipe_model_complexity, min_detection/tracking_confidence, static_image_mode, skip_2d_image_tracking, use_multiprocessing}, anipose_triangulate_3d_parameters_model {confidence_threshold_cutoff, use_triangulate_ransac_method, skip_3d_triangulation}, post_processing_parameters_model {framerate, butterworth_filter_parameters, max_gap_to_fill, skip_butterworth_filter}.
- Not read back.

<recording>/<name>_by_frame.json, <name>_by_trajectory.csv, <name>_frame_name_xyz.npy
- Writer: DataSaver (v1.0.25:freemocap/data_layer/data_saver/data_saver.py:51-82).
- by_frame.json: `{"info":{segment_lengths, schemas}, "data_by_frame":{…}}`.
- by_trajectory.csv: `timestamp` (mean perf_counter ns), `timestamp_by_camera` (stringified dict), then `<point>_x/_y/_z`.
- frame_name_xyz.npy: a copy of the skeleton array.

<recording>/<recording_name>_camera_calibration.toml
- Calibration recordings: always written (anipose_camera_calibrator.py:100-103).
- Mocap recordings: copied in only if the folder has no *.toml yet, keeping the source filename. So it can be named after another recording, or be `last_successful_calibration.toml` (v1.0.25:…/process_motion_capture_data_panel.py:228-238).

Calibration TOML content (V1a)
- `[cam_i]` keys name (video stem, e.g. "Camera_000_synchronized"), size [w,h] (freemocap_anipose.py:1849-1855), matrix, distortions, rotation, translation.
- `[metadata]` (anipose_camera_calibrator.py:53-59):
  - charuco_square_size: mm; GUI default 39 (save_and_load_gui_state.py:11).
  - charuco_board_object: `str(CharucoBoardDefinition(...))`, which includes a cv2 Dictionary memory address.
  - path_to_recorded_videos: absolute path.
  - date_time_calibrated: `str(np.datetime64("now"))`, a naive UTC ISO string.
- Board 7x5, 4x4_250 dictionary, marker length 0.8*square (charuco_board_definition.py; anipose_camera_calibrator.py:61-68).

Optional outputs in V1a
- `<name>.blend` in the recording root (path_getters.py:205-210).
- `<name>.ipynb` (generate_jupyter_notebook.py:15).

------------------------------------------------------------
v1.x eras (deltas against the V1a baseline)
------------------------------------------------------------
| Era | Tags (dates) | Changes |
|---|---|---|
| V1a | v1.0.25-v1.0.34, '1.1.0' (2023-11-09 to 2024-01-01) | baseline above |
| V1b | v1.1.0 (2024-02-26) | 2D now from skellytracker 2024.1.1008 (v1.1.0:…/image_tracking_pipeline_functions.py), see list below |
| V1c | v1.1.1 (2024-03-18) | same files as V1b; marker order fixed to body/right/left/face (skellytracker commit 09e207e0, 2024-03-13, in v2024.03.1009) |
| V1d | v1.2.0-v1.3.0 (2024-04-29 to 2024-08-01) | `mediapipe_skeleton_segment_lengths.json` no longer written (commit cb72f4b5 #571; v1.2.0 data_saving_pipeline_functions.py has only names_and_connections at :60-62) |
| V1e | v1.3.1-v1.4.7 (2024-09-04 to 2024-10-10) | tracker-prefixed names (commit c83c8bd9 #536), see list below |
| V1f | v1.5.0-v1.5.4 (2024-12-23 to 2025-03-11) | adds `<name>_by_frame.csv`, tidy format: columns frame, timestamp, timestamp_by_camera, model, keypoint, x, y, z (commit 93759263; v1.8.2:…/data_saver.py:115-147) |
| V1g | v1.6.0-v1.6.3 (2025-06-05/06) | same files; calibration content changes, see list below |
| V1h | v1.7.0-v1.7.3 (2025-09-17 to 2025-11-07) | groundplane and coordinate change (commit 4c4248ee #691), see list below |
| V1h' | v1.7.4 (2025-12-04) | tidy by_frame.csv gains a `reprojection_error` column (v1.7.4:…/data_saver.py:134; commit 6b0c62a4) |
| V1i | v1.8.0-v1.8.2 (2026-04-22) | outlier rejection (commit 4e87df3a #758), see list below |

V1b details (v1.1.0):
- `mediapipeBodyWorld…npy` is no longer written.
- Same 2D filename, written by skellytracker (v2024.01.1008:skellytracker/process_folder_of_videos.py:28-30,96). Annotated videos keep the `_mediapipe.mp4` suffix (:118). mp4v at source fps (trackers/base_tracker/video_handler.py:16,27-29).
- New: `raw_data/mediapipe3dData_numCams_numFrames_numTrackedPoints_reprojectionError.npy`, shape [cam, frame, marker] (v1.1.0:…/save_mediapipe_3d_data_to_npy.py:34).
- Optional, when run_reprojection_error_filtering is on (default False, post_processing_parameter_models.py:16): `raw_data/reprojection_filtered_mediapipe3dData_{numFrames…spatialXYZ, numFrames…reprojectionError, numCams…reprojectionError}.npy` and `raw_data/debug_reprojection_error_filtering.png` (by_camera_reprojection_filtering.py:61,255-280).
- recording_parameters.json keys: skip_* became run_image_tracking / run_3d_triangulation, and run_reprojection_error_filtering was added (V1b/c/d).
- Marker-order bug: skellytracker 2024.01.1008 orders landmarks pose, face, left_hand, right_hand (mediapipe_model_info.py:24-29; recorder process_tracked_objects). freemocap still splits the array as body/right/left/face. So v1.1.0 hand and face CSV/npy outputs are mislabelled.

V1e details (v1.3.1-v1.4.7):
- `raw_data/mediapipe_2dData_numCams_numFrames_numTrackedPoints_pixelXY.npy` (v2024.08.1018:skellytracker/process_folder_of_videos.py:79)
- `raw_data/mediapipe_3dData_numFrames_numTrackedPoints_spatialXYZ.npy`, `…_reprojectionError.npy`, `mediapipe_3dData_numCams_…_reprojectionError.npy` (v1.3.1:…/save_3d_data_to_npy.py:28-33)
- Optional `reprojection_filtered_mediapipe_3dData_*` (:38-46)
- `output_data/mediapipe_skeleton_3d.npy`, `output_data/mediapipe_rigid_bones_3d.npy`, `center_of_mass/mediapipe_segmentCOM_frame_joint_xyz.npy`, `center_of_mass/mediapipe_total_body_center_of_mass_xyz.npy` (v1.3.1:…/data_saving_pipeline_functions.py:42-70)
- CSV names unchanged (`mediapipe_body_3d_xyz.csv`), but the body columns become `body_nose_x…` (v1.3.1:…/split_and_save.py:85)
- `mediapipe_names_and_connections_dict.json` is gone.
- recording_parameters.json: tracking_parameters_model and tracking_model_info replace mediapipe_parameters_model.
- freemocap reads the old V1a-V1d names as fallbacks (v1.8.2:freemocap/data_layer/recording_models/recording_info_model.py:116-184).

V1g details (v1.6.0-v1.6.3), calibration content:
- pin_camera_0_to_origin now rotates and shifts all extrinsics into cam0's frame, so cam_0 rotation ≈ 0 and translation ≈ 0 (v1.6.0:…/anipose_camera_calibrator.py, pin_camera_zero_to_origin / align_rotations_to_cam0 / shift_origin_to_cam0; commit 0194d220 #686).
- Before this, only translations were shifted by subtracting t0 (v1.0.25 same file:112-124).
- get_video_paths is now sorted (v1.6.0:freemocap/utilities/get_video_paths.py; commit 5a577b19).

V1h details (v1.7.0-v1.7.3):
- The 90-degree x rotation is applied only to single-camera data. Multi-camera skeleton outputs stay in the calibration (cam0) frame (v1.6.3:…/process_recording_folder.py:109 vs v1.7.0, where only process_single_camera_skeleton_data.py uses it).
- TOML gains per-camera world_orientation (3x3) and world_position (camera-to-world) (v1.8.2:…/freemocap_anipose.py:539-549; anipose_camera_calibrator.py:306-330), and `[metadata] groundplane_calibration = bool` (:103,113).
- charuco_board_object now contains `name='7x5 Charuco'` or `'5x3 Charuco'` (v1.7.0:…/charuco_board_definition.py:27-50).
- Optional (GUI checkbox "Use initial board position as origin", default off): the calibration recording gets `output_data/charuco_3d_xyz.npy`, shape [frame, corner, xyz], gap-filled (anipose_camera_calibrator.py:277-280). There is no mkdir, so it may fail if output_data does not exist (NV at runtime).

V1i details (v1.8.0-v1.8.2):
- The reprojection-filtered files can no longer appear (REPROJECTION_FILTERED_PREFIX removed).
- Optional (default off, post_processing_parameter_models.py:17): `raw_data/mediapipe_outlier_rejection_normalized_camera_weights.npy` (triangulation_pipeline_functions.py:98-100).
- recording_parameters.json gains use_triangulate_outlier_rejection, minimum_cameras_for_triangulation, maximum_cameras_to_drop, target_reprojection_error.

Single-camera recordings (all v1 eras)
- No calibration is needed.
- 3D = 2D pixels projected to a z plane, reprojection error all zeros, then rotated (v1.0.25 / v1.8.2:…/process_single_camera_skeleton_data.py).

Blender addon outputs (from the installed 2026.4.1041 only; NV per pinned version)
- `<name>.blend`, `output_data/joint_angles.{csv,npy}`, `saved_data/` (README, info, npy, csv, `<name>_bone_and_joint_data.csv`), `video_export/…mp4`, `video_export/render_cameras/…`, `<name>_video_output.mp4`, and optionally `3d_models/` (fbx/bvh).
- Sources in freemocap_blender_addon: core_functions/main_controller.py:66,211,270; freemocap_data_handler/helpers/saver.py:21; core_functions/export_video/helpers/composite_video.py:80-81; core_functions/export_3d_model/export_3d_model.py:46.

======================================================================
2. QUIRKS
======================================================================

Camera naming
- v0.0.x:
  - `Cam1..`, `raw_cam1..` and annotated videos are 1-based.
  - The anipose `[cam_0..]` tables are 0-based, but their names are "1"..
  - `openPoseVideo_cam0` is 0-based.
- v0.1.0: `Camera_000` = zero-padded OpenCV index.
- v1.x: `Camera_{i:03d}_synchronized`, where i = position among the cameras that recorded at least one frame, NOT the OS device id (skellycam v2025.09.1097:…/save_synchronized_videos.py:83-89,98-102; camera_group_thread_worker.py:228-230). The device id and the rotation setting are not saved anywhere in the recording.
- Imported videos (v0.1.0 and v1.x) keep arbitrary original names. The official sample data is itself legacy-named: `sesh_2022-09-19_16_16_50_in_class_jsm_synced_Cam1.mp4` inside a v1-style `synchronized_videos/`.

Camera order
- Calibration and 2D tracking both use unsorted glob('*.mp4')+glob('*.MP4') before v1.6.0 (v1.5.4:freemocap/utilities/get_video_paths.py). skellytracker sorts only in v2025.10.1024 (utilities/get_video_paths.py:13).
- On non-NTFS filesystems, the camera order in the calibration and in the 2D array may differ (NV at runtime).
- TOML load sorts keys lexicographically, so cam_10 comes before cam_2 (v1.8.2:…/freemocap_anipose.py:2244-2247; also in v0.1.0).

Timestamps
- v0.0.x: float seconds relative to the record start. Unix seconds are added only in v0.0.50+, and that CSV's row 0 is beginTime.
- v0.1.0: seconds from the raw perf_counter, despite the "from record start" name.
- v1.x: raw perf_counter_ns as float64. They differ per OS and are not comparable across machines or reboots.

Dropped frames
- v0.0.x: master timeline. Duplicates are marked -1 and written black (≤v0.0.48) or as the previous frame (v0.0.50+).
- v0.1.0 and v1.x: clip to the overlap, then take the camera with the fewest frames as reference and match the nearest frame in every other camera (skellycam save_synchronized_videos.py:35-89).
  - Duplicates are written silently and no mask is saved.
  - In v1.x, duplicated frames show up as repeated values in `*_binary.npy`, which is a usable signal.

Calibration location and naming
| Release | Calibration file(s) |
|---|---|
| v0.0.x | `{sid}_calibration.yaml` (TOML content) up to v0.0.42, then `.toml` plus `.pickle`. Cross-session reuse only in v0.0.54, via the package folder `fmc_calibration/previous_calibration.toml`. |
| v0.1.0 | `camera_calibration_data.toml` in the session, plus global `last_successful_calibration.toml` |
| v1.x | three dumps per calibration: `calibrations/`, the calibration recording, `logs_info_and_settings/last_successful_calibration.toml` (anipose_camera_calibrator.py:89-110) |

- In v1.x, a mocap recording's TOML may be missing, may have someone else's name, or may not be the file that was actually used. The GUI copies only when no *.toml is present (process_motion_capture_data_panel.py:228-238). The loader copies only over an existing, different, same-named file (get_anipose_calibration_object.py:36-42). Which TOML was used is not recorded in recording_parameters.json.

Coordinate frames
- pin-to-cam0 by tvec subtraction alone, which is not a rigid world transform: v0.0.54, v0.1.0, v1.0.25-v1.5.4. Fixed in v1.6.0 (#686).
- Output skeleton rotated to (x, z, -y): v1.0.25-v1.6.3. v1.7.0+ is unrotated for multi-camera data.
- Units: mm if the square size was entered in mm. A square size of 1 gives "board units" (anipose_camera_calibrator.py:34-37).

Folder-name formats
- v1 GMT offset: int(tm_gmtoff/3600), so half-hour zones are truncated, e.g. +5:30 becomes `gmt+5` (path_getters.py:81-84).
- Session folder formats differ: v0.1.0 uses `-HH_MM_SS`, v1 uses `_HH_MM_SS`.

Conditional files
- annotated_videos: always, when 2D tracking runs.
- Calibration recordings carry `_calibration` in the name and contain no output_data, except the v1.7+ charuco npy.
- Diagnostic PNGs from skellycam: Windows only.
- Optional: by_camera filtering (V1b-V1h), outlier weights (V1i), .blend, .ipynb.

Known bugs that produce malformed files
- v1.0.25 detector: the 2D third channel is z*width, not confidence. The per-frame 0.5 visibility mask is applied to a temporary array and then discarded (mediapipe_skeleton_detector.py:160-171,198-205). Mediapipe gets BGR frames (no cvtColor).
- Face slots: 478 allocated; Holistic without refine returns 468 (plausible, NV).
  - v1.0.25: the last 10 face columns are NaN (arrays NaN-filled).
  - skellytracker: the array is zeros-initialised and landmarks are written sequentially (v2024.01.1008:…/mediapipe_holistic_recorder.py:20-58). So the trailing slots are 0, not NaN. In v1.1.0, where face is second, both hands would be shifted by 10 (NV at runtime).
- v1.1.0: marker-order mismatch (see V1b).
- v0.0.x bugs (sub-agent report):
  - v0.0.2-v0.0.11: calibration crash; fixed by 24cff4de.
  - v0.0.1-v0.0.17: mediaPipe_2d.npy index offset and x/y scaling swap; fixed by 0f6be5d6.
  - OpenPose/DLC 2D arrays use uninitialised `np.ndarray` (v0.0.1:freemocap/fmc_openpose.py:136).
  - v0.0.34: recording broken.
  - v0.0.43-v0.0.51: misnamed Blender output.
  - `charuco_2d_points.npy`: object array in v0.0.12-v0.0.17, float array afterwards.
- v0.1.0 bugs (sub-agent report): metadata charuco_board_object holds the session id; the .blend path mismatch; CSVs written twice.

======================================================================
3. DETECTION RULES (content first, then names)
======================================================================

Detect a folder's family:
1. v0.0.x: CamelCase `SyncedVideos/` / `RawVideos/`, and `{sid}_config.yaml` + `sessionSettings.txt`. Then use the v0.0.x era signatures: `Data Arrays` with a space or `DLCdata` → A; yaml keys `CamInputs` → A vs `recording_parameters` → B+; `RawVideos/*_timestamps.csv` → C+; `*_reprojErr.npy` → E+; `mediaPipeData_2d.npy` → E2+; `.toml` + `.pickle` → F+; `*_smoothed.npy` → F2+; `*unix_timestamps*` → G+; `{sid}.blend` → H+; `Annotated_Videos/` or `_3d_raw.npy` → I.
2. v0.1.0: `synchronized_videos/Camera_NNN.mp4` (no `_synchronized` suffix), plus `timestamps/Camera_NNN_binary.npy`, plus `synchronized_videos/diagnostic_plots/`, plus `camera_calibration_data.toml` whose metadata charuco_board_object looks like a session id, plus `output_data/partially_processed_data/`.
3. v1.x: `synchronized_videos/*_synchronized.mp4` and/or `timestamps/*_synchronized_binary.npy`. The TOML is named `*_camera_calibration.toml` or `last_successful_calibration.toml`, and its metadata has `charuco_board_object = "CharucoBoardDefinition(…"`, `path_to_recorded_videos`, `date_time_calibrated`.

Then the v1 sub-era. The best single discriminator is `output_data/recording_parameters.json`:
| JSON content | Era(s) |
|---|---|
| `mediapipe_parameters_model` with `skip_2d_image_tracking` | V1a |
| `mediapipe_parameters_model` with `run_3d_triangulation` and `run_reprojection_error_filtering` | V1b-V1d |
| `tracking_parameters_model` + `run_reprojection_error_filtering` | V1e-V1h |
| `use_triangulate_outlier_rejection` | V1i |

File presence:
- `raw_data/mediapipeBodyWorld_*` → V1a.
- `raw_data/mediapipe3dData_numCams_*` → V1b-V1d.
- `mediapipe_skeleton_segment_lengths.json` → ≤V1c.
- `mediapipe_names_and_connections_dict.json` → ≤V1d.
- `mediapipe_skeleton_3d.npy` / `mediapipe_rigid_bones_3d.npy` / `mediapipe_2dData_*` → ≥V1e.
- `<name>_by_frame.csv` → ≥V1f; with a `reprojection_error` column → ≥V1h'.

CSV content: body CSV first header `nose_x` → ≤V1d; `body_nose_x` → ≥V1e.

TOML content:
- cam_0 rotation ≈ 0 → ≥V1g (≤V1f has translation 0 but rotation ≠ 0).
- `world_position` keys / `groundplane_calibration` / a board `name=` → ≥V1h.

Cannot be told apart by files alone:
- V1b vs V1c. Possible signal: the skellytracker static_image_mode default changed in 2024-03 (commit 5af0fd21), so it may differ in recording_parameters.json (NV).
- v1.0.25 vs v1.0.26-v1.0.34; v1.6.x vs v1.5.x except by the TOML; v0.0.52 vs v0.0.54 without the optional files.

Releases never write their version number into the recording (v1.8.2 grep of `__version__` shows only GUI uses).

======================================================================
4. SAMPLE / TEST DATA
======================================================================

URLs in code (not fetched)
- v0.0.39-v0.0.54: https://figshare.com/ndownloader/files/30913897, which unpacks to sesh_21-07-20_165209 (v0.0.39:freemocap/fmc_demo.py:14-15).
- v1.0.25-v1.1.1: sample …/files/41368323, test …/files/40293973 (file_and_folder_names.py:42-44).
- v1.2.0-v1.5.4: …/45797067 and …/45797073.
- v1.6.0+: …/53681960 and …/53682050.
- v0.1.0: none.

Local copies (paths only; small text files were read)
- C:\Users\Dom\Downloads\freemocap_sample_data
  - Legacy-named synced mp4s; `freemocap_sample_data_camera_calibration.toml` (V1a-V1g style: no world_position or groundplane keys, date_time_calibrated 2025-06-12, size [720, 1280]); `charuco_board_info.json` {square_size_mm 58, 7x5}.
  - No release I found writes charuco_board_info.json. It is only read by the v1.7+ CI diagnostics (v1.8.2:freemocap/diagnostics/calibration/calculate_calibration_diagnostics.py:17).
- C:\Users\Dom\Downloads\freemocap_sample_data_h264\freemocap_sample_data
- C:\Users\Dom\Nextcloud\FMC\freemocap_sample_data
- C:\Users\Dom\.cache\skellytracker\test_data\freemocap_test_data
- C:\Users\Dom\.cache\freemocap\test_data\freemocap_test_data: also holds a parquet and charuco_observations output that look like a v2-alpha write, not legacy (NV).

Real recordings from legacy releases
- None found. C:\Users\Dom\freemocap_data has only empty `calibrations/` and `logs_info_and_settings/logs` with ISO-style log names, which come from v2 alphas.
- The C:\Users\Dom\Documents\skellycam-raw\skellycam_recording\real_recording_20261109\…\synchronized_videos folders are 2026 skellycam / freemocap-v2 runs, not legacy.

======================================================================
5. GAPS
======================================================================
- Nothing was executed, so every runtime claim (face 468 vs 478, the v1.1.0 hand shift, the charuco npy save failing, cross-OS glob order) is inferred from code.
- skelly_synchronize (v1 "import + synchronize" output and debug plots) is not available locally.
- Blender addon outputs are known only for one unpinned installed version. The v0.1.0 and v0.0.x megascript internals were only partly read.
- The skellycam philip/pyside6-change branch (v1.0.29/30) is not in the local clone. Unpinned skellycam in v1.0.26-28 could resolve to any later PyPI version.
- Exact column sets of by_trajectory.csv and by_frame.json, and the shape of rigid_bones_3d.npy, were not traced. The tracking_model_info serialisation in recording_parameters.json is NV.
- v0.0.x gaps (sub-agent): DLC/OpenPose exact file names, `[metadata]` contents, and the intermediate tags v0.0.30-36 were not individually diffed for output.

Not done: per-tag full reads of all 87 tags. Eras come from diffing the name constants and writer files between consecutive tags, so a writer added outside the grepped patterns could be missed. One risk for the spec: a v1 recording's TOML is not guaranteed to be the calibration that produced its 3D data.
