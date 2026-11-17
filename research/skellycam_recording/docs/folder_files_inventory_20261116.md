# Folder files inventory (freemocap c27fc299, skellycam 169caf637, addon 73e1b3e)

Status: research report, 2026-11-16, for the skellyfileformat spec draft v2 (sections 13, 14, 15 and 18). A read-only sub-agent study of freemocap c27fc299, skellycam 169caf637 and the Blender addon 73e1b3e. The main session saved it; spot-checks are noted at the end.

**How to read the citations.** All code was read from `git archive` exports of the fixed revisions, plus the addon cache copy. No file in any repository was changed.
- `fm:` is freemocap at c27fc299.
- `sc:` is skellycam at 169caf637.
- `addon:` is the Blender addon at `…/bc66ecde1d0b8425/73e1b3e`.
- `st:` is skellytracker at 03b9c1dc. That is the revision pinned for c27fc299 in `fm:uv.lock`, read with `git show` in the local skellytracker clone.
- `sf:` is skellyforge at f5404db. Also pinned in `fm:uv.lock`; read from the uv cache checkout `9974341064142b12/f5404db`.
- `fm:uv.lock` pins skellycam to 169caf6379… (checked by grep).
- "[inferred]" marks a conclusion drawn from code and not stated by it. "[tested]" marks a behaviour I confirmed with a 5-line script in the freemocap venv (pydantic 2.13.4, pyarrow 25.0.0, numpy 2.4.6). `uv.lock` pins pydantic 2.14.1, pyarrow 26.0.0 and numpy 2.2.6/2.4.6, so the tested versions differ slightly.

---

## 1. Calibration TOML `<rec>_camera_calibration.toml`

### 1.1 File model
- **Encoding and codec.**
  - Written by `tomli_w.dumps(model_dump(mode="json", by_alias=True, exclude_none=True, round_trip=True))` (fm:freemocap/core/tasks/calibration/shared/calibration_toml.py:221-224).
  - The file write is `path.write_text(..., encoding="utf-8")` after `mkdir(parents=True)` (fm:freemocap/utilities/toml_mixin.py:48-52).
  - It is read with stdlib `tomllib` (toml_mixin.py:61-67).
  - `CalibrationResult.save_toml` and `load_toml` both go through `CalibrationToml` (fm:freemocap/core/tasks/calibration/shared/calibration_result.py:65-81).
- **Top level.** One `metadata` table plus one table per camera, keyed by camera ID.
  - `CalibrationToml` has `extra="allow"`, and every extra top-level key is typed `CameraToml` (calibration_toml.py:180-188).
  - At least one camera is required (calibration_toml.py:195-199).
  - Camera IDs must be unique, and an ID equal to a reserved field name (`metadata`) is rejected on write (calibration_toml.py:202-213).
  - [inferred] Any non-camera top-level key, including a scalar, fails validation on read, because extras are typed `CameraToml`.
- **Table order.** `metadata` is dumped first, then the cameras in `cameras` list order [inferred: pydantic dumps declared fields before extras; tomli_w keeps insertion order].
- **Camera order on read.** Cameras are read in **sorted table-key order**. A missing `index` defaults to the camera's position in that sorted order (calibration_toml.py:215-219).

### 1.2 Camera table `[<camera_id>]` (`CameraToml`, calibration_toml.py:123-177; `extra="ignore"`, line 126)

| key | type | written value | read rule |
|---|---|---|---|
| `name` | str, **required on read** | `camera.id` (line 142) | Used as the ID if `id` is absent (line 164) |
| `id` | str, optional | `camera.id` (143) | Overrides `name` (164) |
| `index` | int, optional | `camera.index` (144) | Default: position in sorted key order (165, 218) |
| `size` (alias `image_size` accepted on read) | `[int, int]` | `camera.image_size` = **(width, height)** (145; fm:…/shared/camera_model.py:20) | |
| `matrix` | 3×3 array of finite floats (rows) | K = `[[fx,0,cx],[0,fy,cy],[0,0,1]]` (146; fm:…/shared/camera_intrinsics.py:44-51) | Only `[0][0]`=fx, `[1][1]`=fy, `[0][2]`=cx, `[1][2]`=cy are kept (camera_intrinsics.py:83-86) |
| `distortions` | array of finite floats, any length | 5 values `[k1,k2,p1,p2,0.0]` (147; camera_intrinsics.py:57-59) | The first 4 are read as k1,k2,p1,p2; missing values become 0.0 (camera_intrinsics.py:81-90) |
| `rotation` | 3 finite floats | OpenCV **Rodrigues vector** of R (148; fm:…/shared/camera_extrinsics.py:45-50) | Rodrigues, then matrix, then quaternion wxyz (camera_extrinsics.py:63-81) |
| `translation` | 3 finite floats | t (149) | |
| `world_orientation` | 3×3, optional | Rᵀ, camera-to-world (150; camera_extrinsics.py:58-60) | If present, stored **as given** with no consistency check against rotation; otherwise derived (169-176) |
| `world_position` | 3 floats, optional | −Rᵀt (151; camera_extrinsics.py:53-55) | Same rule as `world_orientation` |

- **Model.** OpenCV pinhole camera, `P = K [R|t]` (camera_model.py:72-80). R maps world to camera (camera_model.py:105: "R, world→camera").
- **Distortion.** Brown–Conrady with k1, k2, p1, p2 only (camera_intrinsics.py:12-19).
- **Units.** Translation and world position are in **millimetres** (camera_model.py:104, 109).
  - [inferred] This follows from the board being measured in mm: `CharucoBoardDefinition.square_length_mm` is passed to the OpenCV board as `squareLength` (st:skellytracker/core/detectors/keypoint_detectors/charuco/charuco_board_definition.py:68-73).
- **Unaligned world frame.** Camera 0's frame: `pin_camera_zero_to_origin` runs by default (fm:freemocap/core/tasks/calibration/anipose_calibration/run_anipose_calibration.py:41, 91-93; helper at fm:…/anipose_calibration/helpers/anipose_calibration_helpers.py:44-64).
- **Axis convention used for transforms.** When reconstruction-frame transforms are applied to cameras, the code treats the calibration world as the skellyforge `ros` convention (+X forward, +Y left, +Z up). The reconstruction frame is `blender` (+X right, +Y forward, +Z up).
  - Sources: fm:freemocap/core/reconstruction/coordinate_conventions.py:8-14; sf:skellyforge/definitions/coordinate_systems/coordinate_systems.yaml:23-45.
- **Camera naming.** Camera IDs are the keys of the posthoc `video_metadata` (run_anipose_calibration.py:47-58). These come from the `videos` map in `*_info.json` when one exists; otherwise the **full video filename** is used as the label (fm:freemocap/core/pipeline/posthoc/video_group_helper.py:336-343, 384-401, 440-442).
  - The `*_info.json` glob in `sc:skellycam/core/recorders/videos/recording_metadata.py:16` also matches freemocap's `<rec>_recording_info.json`. Conflicting values raise an error (recording_metadata.py:26-27).

### 1.3 `[metadata]` table (`CalibrationMetadata`, fm:…/shared/calibration_metadata.py:15-52; `extra="forbid"`, `populate_by_name`)

| key in file | type | notes |
|---|---|---|
| `board` (sub-table) | CharucoBoardDefinition | See 1.4 |
| `reprojection_error_px` | float | Anipose total error (run_anipose_calibration.py:121) |
| `initial_cost` | float | Anipose writes 0.0 (122) |
| `final_cost` | float | = error (123) |
| `n_iterations` | int | 0 (124) |
| `solver_time_seconds` | float | Python name `time_seconds`; the alias is what is written (line 23) |
| `n_observations_used` | int | frames × cameras (126) |
| `n_observations_rejected` | int | 0 (127) |
| `aligned` | bool, default false | |
| `solver_method` | enum, optional | Only member: `"anipose"` (fm:…/calibration/calibration_task_config.py:16-18) |
| `recording_info` (sub-table) | skellycam `RecordingInfo`, optional | See note below |
| `alignment_method` | `"charuco"` \| `"person"`, optional | fm:…/shared/groundplane_alignment.py:13-15 |
| `alignment_recording_id` | str, optional | |
| `alignment_result` (sub-table) | `GroundPlaneResult`, optional | `origin` (3 floats), `rotation_matrix` (3×3, "charuco_to_world"), `method` (groundplane_alignment.py:18-29; anipose_calibration_helpers.py:113-130) |
| `transformation_history` (array of tables) | `CalibrationTransform` list, default `[]` | Each entry has `operation` ∈ {`charuco`,`person`,`manual`}, `quaternion_wxyz` (4, scalar-first), `translation_mm` (3). These are reconstruction axes, X right/Y forward/Z up, in mm, ordered oldest first (fm:…/shared/calibration_transform.py:1, 21-38) |

- **`recording_info` note.** It contains `recording_name`, `recording_directory` (absolute path), `recording_uuid`, `mic_device_index` and a `recording_start_timestamp` sub-table (sc:skellycam/core/recorders/videos/recording_info.py:21-27).
  - For posthoc calibration it is a **fresh** `RecordingInfo` (fm:freemocap/api/http/calibration/calibration_router.py:126-134). So the UUID and timestamp are new defaults (sc recording_info.py:24, 27), not the capture's [inferred].
- **Validation.** Alignment fields require `aligned=true`, and `alignment_result.method` must equal `alignment_method` (calibration_metadata.py:37-52).
- **Omission.** `exclude_none` drops unset optional keys (calibration_toml.py:223).
- **Who sets what.** `_save_result` sets `solver_method`, `recording_info` and the alignment fields (fm:freemocap/core/tasks/calibration/posthoc_calibration_task.py:127-148). Ground-plane alignment appends one history entry (run_anipose_calibration.py:128-135).
- **Legacy read path** (`_read_legacy_metadata`, calibration_toml.py:84-120):
  - Accepts historical names: `groundplane_applied`/`groundplane_aligned`→`aligned`, `groundplane_method`, `groundplane_recording_id`, `groundplane_result` (89-98).
  - Defaults the required numbers to 0 / 0.0, so the whole `[metadata]` table is optional on read (100-109, 186-188).
  - Copies only known names or aliases; **unknown metadata keys are dropped** (113-118).

### 1.4 ChArUco board, `[metadata.board]` (st:…/charuco_board_definition.py:21-34; `extra="forbid"`)

- **Fields written:** `squares_x` (int), `squares_y` (int), `square_length_mm` (float), `marker_length_ratio` (float, default 0.8), `aruco_dictionary_enum` (int OpenCV constant, default `DICT_4X4_250`, which is 2 in the cv2 build tested).
- **Not written.** The computed field `aruco_marker_length_mm` (st:…:36-39) is **not** written: `round_trip=True` drops computed fields [tested].
- **Constraints:** marker length < square length; squares ≥ 2×2 (st:…:41-53).
- **Legacy read** (`_read_legacy_board`, calibration_toml.py:38-81):
  - Defaults 7×5, 1.0 mm.
  - Maps `marker_bits`+`dict_size` to `DICT_{4,5}X{4,5}_{50,100,250,1000}` (default (4,250)).
  - Accepts `marker_length_mm` or `aruco_marker_length_mm` when the ratio is absent.
- **Presets:** `create_letter_size_5x3` is 5×3, 54 mm; it is the posthoc config default (st:…:196-197; fm:…/calibration_task_config.py:28). `create_test_data_7x5` is 7×5, 58 mm (st:…:192-193).

### 1.5 Lookup (read)
`find_recording_calibration` (fm:…/shared/calibration_paths.py:28-39):
1. `<folder>/<folder.name>_camera_calibration.toml` if it exists.
2. Otherwise, files in the folder only (not recursive) with suffix `.toml` (case-insensitive) and `"calibration"` in the stem (case-insensitive), sorted.
3. More than one match raises `ValueError`; none returns `None`.

Used by the API (calibration_router.py:88-94) and recording status (fm:freemocap/system/recording_status/recording_status.py:148-149). Mocap processing needs an **explicitly selected** TOML (fm:freemocap/core/tasks/mocap/mocap_task_config.py:130-131). "Most recent" is `<base>/calibrations/last_successful_camera_calibration.toml` (calibration_router.py:44-50).

### 1.6 Writes

| writer | location / name | atomic? | prod at c27fc299 |
|---|---|---|---|
| `save_calibration_copies` (calibration_save.py:21-51), called from `_save_result` (posthoc_calibration_task.py:142-146) | (1) `<take>/<recording_name>_camera_calibration.toml`; (2) `<base>/calibrations/<recording_name>_camera_calibration.toml`; (3) `<base>/calibrations/last_successful_camera_calibration.toml` (calibration_paths.py:10-25). `<base>` is `$FREEMOCAP_BASE_FOLDER`, else `~/freemocap_data` (fm:freemocap/system/default_paths.py:6, 11, 39-43) | **No**: direct `write_text` (toml_mixin.py:52) | Yes (posthoc calibration) |
| `PreparedCalibrationUpdate.commit` (fm:…/shared/calibration_update.py:33-53), via the `/transform` API (calibration_router.py:60-79) and realtime state (fm:…/shared/calibration_state.py:316-324) | Rewrites the selected TOML in place | Yes: temp `.<stem>-XXXX.toml` in the same folder, then `os.replace`, guarded by an mtime check and FileLock `<toml>.lock` (calibration_update.py:22-24, 37-50, 77) | Yes (explicit user apply) |
| `save_aligned_calibration` (fm:…/shared/calibration_exports.py:17-61), called after every graph-pipeline save (fm:freemocap/core/pipeline/dataflow/recording_pipeline.py:296-299) | `<take>/exports/calibration_copies/<source_stem>__aligned__<YYYY-MM-DD_HH-MM-SS-ffffffZ>__<sha256[:12]>.toml`; for run N≠0: `<take>/exports/run-N/calibration_copies/…__<hash>.run-N.toml` (lines 37-50) | Yes: temp `.calibration-XXXX.toml`, reload-verify, `replace`; FileLock `.calibration-export.lock` (43, 51-57) | Yes, only when the transforms change geometry (27-31); reuses an identical existing file (44-48) |
| Legacy "current" mocap pipeline | `shutil.copy2` of the selected TOML into `<take>/<toml name>` (fm:freemocap/core/tasks/mocap/posthoc_mocap_task.py:170-177) | No | Only with `pipeline_implementation="current"`; the default is `typed_dataflow` (mocap_task_config.py:31-33; fm:…/posthoc/mocap_pipeline.py:88-91) |

The hash in the aligned file name is sha256 of the canonical JSON dump (`sort_keys`, compact separators) of the TOML model (calibration_exports.py:34-36).

### 1.7 Dropped or altered on round trip
- **Distortion.** k3 is always written as 0.0, and any 5th-or-later coefficient on read is ignored. Only 4 coefficients are kept (camera_intrinsics.py:57-59, 81-90).
- **Camera matrix.** Skew `K[0][1]` and other off-pattern matrix entries are ignored (83-86).
- **Unknown keys.** Unknown camera keys are ignored (calibration_toml.py:126); unknown metadata keys are dropped (113-118).
- **Rotation.** Stored internally as a quaternion; the Rodrigues vector is re-derived on write (camera_extrinsics.py:45-50, 63-81). [inferred] Float round-off is possible; calibration_exports.py:32-33 says so explicitly.
- **Legacy board fields.** `marker_bits`, `dict_size` and `*_marker_length_mm` are converted to the current fields.
- **Table key.** The camera table key itself is **not** used as the ID; `id`, else `name`, is (calibration_toml.py:164).

### 1.8 `charuco_board_info.json`
- **Writers:** dataset tools only. `fm:freemocap/tools/datasets/preparation.py:371`, `stage_matrix.py:207` and `workflow.py:180` copy a `board_metadata` dict.
- **Reader:** `fm:freemocap/tools/datasets/inspection.py:92-98`. Fields checked: `square_size_mm` (58), `num_squares_height` (5), `num_squares_width` (7). The default is used when the file is absent.
- **App code:** no reader or writer in freemocap/core, api or system (`git grep` over the whole repo at c27fc299).
- **Contract:** calls it "an optional calibration input" (fm:RECORDING_CONTRACT.md:55).
- **Where board parameters live in production:** the TOML `[metadata.board]`; the posthoc config `charuco_board` (calibration_task_config.py:27-30); the realtime charuco cache `board_definition` (pickled, §4.6).

---

## 2. freemocap `<rec>_recording_info.json` (fm:freemocap/core/recording/recording_info.py:9-47)

- **Path:** `RecordingStructure.recording_info_path` = `<take>/<rec>_recording_info.json` (fm:freemocap/system/recording_structure/recording_structure.py:119-122).
- **Base object (lines 11-18):**
  - If `<rec>_recording_info.json` exists, it is loaded.
  - Otherwise, if skellycam's `<rec>_info.json` exists, it is loaded **verbatim**. Every capture key and unknown key is kept; the source file is not modified.
  - Otherwise the base is `dict(metadata.recording_info)`. That descriptor field defaults to `{}` (fm:…/data_descriptors/recording_descriptor.py:195), and new descriptors are created without setting it (fm:…/result_processing/observation_publication.py:244-245). So the base is normally `{}` [inferred].
  - Symlinks are refused; a non-object JSON value raises an error.
- **Added or replaced key `processed`** (lines 31-36). The whole block is replaced on every write.

| field | value |
|---|---|
| `schema_version` | `1` |
| `parquet_sha256` | sha256 hex of `<rec>_data.parquet` (29-30) |
| `recording_id` | descriptor `recording_id` |
| `parquet` | Parquet file name (`<rec>_data.parquet`) |
| `selected_run_id` | int |
| `runs` | `{ "<run_id>": {sensor_groups, cameras, reference_frames, data} }` (19-28) |
| `runs.*.sensor_groups` | `{group: {clock_description: str, sample_count: int}}` (recording_descriptor.py:22-24) |
| `runs.*.cameras` | Source keys with `kind == "camera"`, with the `camera:` prefix removed |
| `runs.*.reference_frames` | Run `reference_frames` dict as stored |
| `runs.*.data` | List of `{channel, source, sensor_group, reference_frame, names, components}` for channel kinds LANDMARKS_3D, KEYPOINTS_3D, RAW_KEYPOINTS_3D, OVERLAY_2D, SEGMENT_ORIGINS, ROTATIONS_WORLD. `components` maps component → units (recording_descriptor.py:39-46) |
| `conventions` | `quaternion_order:"wxyz"`, `segment_pose:"saved origin and world orientation"`, `units:"per component"`, `coordinates:"per reference frame"`, `array_order:"frames, names, components"` |
| `export_inventories` | Sorted take-relative POSIX paths of `exports/**/*_recording_info.json` |

- **Write (lines 37-47):** `tempfile.mkstemp(dir=<take>, suffix='.info.tmp')`; JSON with `ensure_ascii=False`, `allow_nan=False`, `indent=2`, a trailing newline and `fsync`; then `Path.replace` (atomic). The caller holds `.processing.lock`.
- **Callers:**
  - After every Parquet publish (fm:…/parquet_storage/parquet_writer.py:63).
  - After every scientific export, under the recording lock (fm:…/exports/wide_csv.py:361-368).

---

## 3. skellycam capture output

### 3.1 Folder layout written today (sc:skellycam/system/default_paths.py:5-10; recording_info.py:40-134)

```text
<recording_directory>/<recording_name>/
    <recording_name>_info.json                                  # recording_info.py:68-70
    synchronized_videos/                                        # default_paths.py:6
        <recording_name>.id-<camera_id>.idx-<camera_index>.<ext>   # video_filename.py:7, 26-28
        <recording_name>.audio.wav                              # recording_info.py:128-130 (only if mic_device_index >= 0)
        <recording_name>.audio_timestamps.json                  # recording_info.py:132-134; audio_recorder.py:133
        synchronized_videos_README.md                           # recording_finalizer.py:24, 69-71
        timestamps/                                             # default_paths.py:7
            <recording_name>_timestamps.csv                     # recording_info.py:58-60 (multiframe)
            <recording_name>_stats.json                         # recording_info.py:76-78
            <recording_name>_stats.txt                          # recording_info.py:72-74
            camera_timestamps/                                  # default_paths.py:8
                <recording_name>.camera<camera_id>.timestamps.csv   # sc:…/timestamps/recording_timing_reader.py:13-15
```

- **Default names.** Directory: `~/skellycam_data/recordings/<name>` (default_paths.py:33-42; sc:skellycam/api/http/cameras/camera_router.py:37-49). Name: `get_iso6201_time_string(timespec="seconds")` with `:`→`_` and `.`→`ms`, then `_gmt±H`, then an optional `_<tag>` (default_paths.py:64-80).
- **Side effect.** Reading the `RecordingInfo` path properties creates directories (`mkdir`, recording_info.py:40-66).
- **Finalize order** (recording_finalizer.py:53-67):
  1. `save_to_file` (info JSON).
  2. Timestamp CSVs, then stats.
  3. README.
  4. Validation: equal frame counts, frame shape, timestamp files, CSV row count = video frame count (126-208).
- **Remux disabled.** Remuxing with audio and VFR timestamps is commented out (line 63).

### 3.2 `<rec>_info.json` (`RecordingInfo.save_to_file`, recording_info.py:80-104)
- **Write:** `open(path, "w")` plus `json.dumps(..., indent=4)`. Not atomic; default `ensure_ascii`; platform text mode [inferred: CRLF on Windows]. Written once at finalize.
- **Top-level fields:**

| field | type | source |
|---|---|---|
| `recording_name` | str | recording_info.py:22 |
| `recording_directory` | str (parent folder path, absolute as given) | 23 |
| `recording_uuid` | str, uuid4 | 24 |
| `mic_device_index` | int, default −1 (−1 means no audio) | 25; camera_group.py:207 |
| `recording_start_timestamp` | FullTimestamp object | 27 |
| `videos` | `{camera_id: filename}`. Values are **relative to `synchronized_videos/`**, validated as recording-relative POSIX paths, and must resolve to existing distinct files (86-91; sc:…/videos/video_associations.py:26-48) | |
| `camera_timing` | `{camera_id: take-relative POSIX path}` to the per-camera CSV (93-96) | |
| `multiframe_timing` | take-relative POSIX path to `<rec>_timestamps.csv` (97) | |
| `camera_configs` | `{camera_id: CameraConfig}`; the key must equal `config.camera_id` (83-85, 98-101) | |

- **FullTimestamp** (sc:…/timestamps/full_timestamp.py:18-72):
  - `unix_timestamp_utc` (float, s); `unix_timestamp_local` (float); `unix_timestamp_utc_isoformat` (str); `unix_timestamp_local_isoformat` (str); `local_time_zone` (str, tz name); `human_friendly_utc` / `human_friendly_local` (str, `%Y-%m-%d %H:%M:%S.%f`); `day_of_week` (str); `calendar_week` (int, ISO); `day_of_year` (int); `is_leap_year` (bool); `perf_counter_ns` (int).
- **CameraConfig** (sc:skellycam/core/camera/config/camera_config.py:63-123; defaults 16-29):

| field | type | default / enum |
|---|---|---|
| `camera_id` | str | "000" |
| `camera_index` | int | 0 |
| `camera_name` | str | "Default Camera", replaced by `Camera-<camera_id>` (125-129) |
| `use_this_camera` | bool | true |
| `resolution` | `{height:int, width:int}` (sc:…/config/image_resolution.py:6-8) | 720 × 1280 |
| `color_channels` | int | 3 |
| `pixel_format` | str | "RGB" |
| `exposure_mode` | str | "MANUAL". Members of ExposureModes: AUTO (0.75), MANUAL (0.25), RECOMMEND (−1) (sc:…/opencv_helpers/recommend_camera_exposure_setting.py:15-18) |
| `exposure` | int | −7 (OpenCV log2 exposure convention, line 102) |
| `framerate` | float | −1.0 (camera default) |
| `rotation` | **string name in this JSON** | One of `NO_ROTATION` (−1), `CLOCKWISE_90` (0), `ROTATE_180` (1), `COUNTERCLOCKWISE_90` (2), or `UNKNOWN_ROTATION`. The serializer gives an int (361-363); `save_to_file` converts it to the name (recording_info.py:100-101; sc:…/config/image_rotation_types.py:6-16). Integer values from the cv2 build tested |
| `capture_fourcc` | str | "MJPG" |
| `writer_fourcc` | str | "X264". This is the **requested** codec; the codec actually used may be a fallback that is not recorded [inferred: sc:…/videos/video_recorder.py:58-68 resolves `working_fourcc` locally] |

- **Video files.**
  - Writer: `cv2.VideoWriter(fourcc)`, or `PyavVideoWriter` (libx264, yuv420p, crf 18, preset fast, PTS = frame index, rate = round(fps)) for the `X264_PYAV` fallback (video_recorder.py:120-134; sc:…/videos/pyav_video_writer.py:11-18, 30-36).
  - Codec order: requested, then web codecs, then mp4v/XVID/MJPG (sc:…/videos/fourcc_codec_helpers.py:155-195).
  - Extension: X264/H264/avc1/mp4v/MP4V/X264_PYAV → mp4; XVID/DIVX/MJPG → avi (fourcc_codec_helpers.py:54-79).
  - Frames are rotated before writing (video_recorder.py:96-102).
  - An existing `<stem>.*` file is reused; more than one match raises an error (recording_info.py:106-121).
- **`camera_id` derivation** (sc:skellycam/core/device_detection/detect_cameras_devices.py:44-54):
  - If a device path exists: the first 2 bytes of sha256(path) as 4 lowercase hex characters.
  - Else, if vendor and product IDs exist: the same hash of `f"{vid:04x}_{pid:04x}_{index}"`.
  - Else: `format(index,'04x')`.
  - Collisions raise an error (107-108). The UI uses the server's `camera_id` (sc:skellycam-ui/src/store/slices/cameras/cameras-thunks.ts:63-72).

### 3.3 Per-camera timestamps CSV `camera_timestamps/<rec>.camera<camera_id>.timestamps.csv`
- **Write:** `np.savetxt(fmt='%s', delimiter=',', header=<names>, comments='')`. The header has no `#`; NaN is printed as `nan` [tested: numpy 2.4.6] (sc:…/numpy_timestamps/create_camera_csvs.py:101-105).
- **One row per recorded frame.** Columns, exactly as in the dtype (sc:skellycam/core/types/numpy_record_dtypes.py:49-79):
  - `recording_frame_number` (int, 0..N−1)
  - `connection_frame_number` (int)
  - `timestamp.from_recording_start.sec` (float)
  - `timestamp.utc.seconds` (float)
  - `timestamp.local.iso8601` (U32)
  - `timestamp.perf_counter_ns.ns` (int)
  - `from_previous.frame_duration.ms` (float; NaN on row 0)
  - `from_previous.framerate.hz` (float; NaN on row 0 or when the duration ≤ 0)
  - `frame.initialized.ns`, `frame.pre_frame_grab.ns`, `frame.post_frame_grab.ns`, `frame.pre_frame_retrieve.ns`, `frame.post_frame_retrieve.ns`, `frame.pre_copy_to_camera_shm.ns`, `frame.post_copy_to_camera_shm.ns`, `frame.pre_frame_record.ns`, `frame.post_frame_record.ns` (ints, **relative to the recording start**, create_camera_csvs.py:85-89)
  - `duration.idle_before_frame_grab.ns`, `duration.during_frame_grab.ns`, `duration.idle_before_retrieve.ns`, `duration.during_frame_retrieve.ns`, `duration.idle_before_copy_to_camera_shm.ns`, `duration.during_copy_to_camera_shm.ns`, `duration.idle_before_frame_record.ns`, `duration.during_frame_record.ns`, `total.frame_processing_time.ns`, `total.camera_idle_time.ns` (ints)
- **Semantics:**
  - The main timestamp is the midpoint of pre-grab and post-grab (perf_counter ns), lines 50-51.
  - The recording start is the minimum first `pre_frame_grab_ns` across cameras (sc:…/process_and_save_recording_timestamps.py:81-84).
  - UTC = `utc_time_ns + (perf − mapping.perf)` (sc:…/timestamps/timebase_mapping.py:26-32).
  - [inferred] The local ISO string adds `local_time_utc_offset` to the epoch and then formats it in the local timezone, so the local offset appears to be applied twice (timebase_mapping.py:34-47).
  - All cameras must have equal frame counts, equal frame numbers and one shared timebase mapping (process_and_save_recording_timestamps.py:21-69).

### 3.4 Multiframe CSV `timestamps/<rec>_timestamps.csv`
- **Write:** same `np.savetxt` format (sc:…/numpy_timestamps/create_multi_frame_csvs.py:113-119).
- **Columns:** `multiframe_number`, `timestamp.from_recording_start.sec`, `timestamp.perf_counter_ns.ns` (float), `timestamp.utc.seconds`, `timestamp.local.iso8601`, `from_previous.frame_duration.ms`, `from_previous.framerate.hz`, `inter_camera.frame_grab_range.ms`. Then, for each of the 19 `frame.*`/`duration.*`/`total.*` bases, five columns: `<base>.ms.mean`, `<base>.ms.median`, `<base>.ms.standard_deviation`, `<base>.ms.range`, `<base>.proportion.coefficient_of_variation` (numpy_record_dtypes.py:81-205). That is 8 + 95 = 103 columns [counted from dtype].
- **Values:**
  - Times are means across cameras (44-45).
  - The local ISO string is computed from UTC seconds via `astimezone()` (47-52).
  - The grab range is max − min of the per-camera perf_counter values, in ms (55-58).
  - Statistics are across cameras, with ns converted to ms (77-111).

### 3.5 Stats files
- **`<rec>_stats.json`:** `RecordingTimestampsStats.to_json(indent=4)` (sc:…/numpy_timestamps/save_timestamps_statistics_summary.py:19-22).
  - Keys: `recording_info`, `number_of_cameras`, `number_of_frames`, `total_duration_sec`, `framerate_stats`, `frame_duration_stats`, `inter_camera_grab_range_ms`, `idle_before_frame_grab_ms`, `during_frame_grab_ms`, `idle_before_retrieve_ms`, `during_frame_retrieve_ms`, `idle_before_copy_to_camera_shm_ms`, `during_copy_to_camera_shm_ms`, `idle_before_frame_record_ms`, `during_frame_record_ms`, `total_frame_processing_time_ms`, `total_camera_idle_time_ms` (sc:…/timestamps/recording_timestamp_stats.py:44-62).
  - Each stats object has `mean`, `median`, `standard_deviation`, `coefficient_of_variation`, `min`, `max`, `range`, with the `_value` suffix stripped (recording_timestamp_stats.py:133-143; numpy_record_dtypes.py:212-220; sc:…/calculate_timestamps_numpy.py:83-114).
  - The duration stats are computed over the per-frame `.ms.median` columns (recording_timestamp_stats.py:90-120).
  - [inferred] `recording_info` is serialized through `default=lambda o: o.__dict__` (line 156).
- **`<rec>_stats.txt`:** `str(stats)`, a human-readable report (save_timestamps_statistics_summary.py:25-27).

### 3.6 Audio (sc:skellycam/core/recorders/audio/audio_recorder.py)
- **When:** only if `mic_device_index >= 0` (sc:skellycam/core/camera_group/camera_group.py:207-213).
- **WAV:** PCM int16, 44100 Hz, channels = min(2, device max), block 1024 (16-19, 60, 121-128).
- **`<rec>.audio_timestamps.json`** (`indent=2`, lines 140-162). Fields:
  - `audio_file` (basename), `mic_device_index`, `sample_rate`, `channels`, `chunk_size`, `total_chunks`, `total_samples`
  - `start_perf_counter_ns`, `end_perf_counter_ns`, `duration_seconds`, `mean_chunk_duration_seconds`, `std_chunk_duration_seconds`
  - `timebase_mapping{utc_time_ns, perf_counter_ns, local_time_utc_offset (seconds)}`
  - `chunk_timestamps_perf_ns` (list of int; perf_counter at callback time)
- **Not referenced** in the info JSON.
- **Nothing written** if no chunks were captured (91-93).

### 3.7 `synchronized_videos_README.md`
Fixed text stating that all videos have the same frame count and that frame *i* is the same moment in every camera (recording_finalizer.py:27-31).

---

## 4. Derived outputs freemocap writes into a take (c27fc299)

### 4.1 Scientific exports: wide CSV / NPY / NPZ / notebook (fm:freemocap/core/recording/exports/wide_csv.py)
- **Enabled?**
  - Off by default: `formats=()`, `data=('LANDMARKS_3D',)` (fm:…/exports/requests.py:24-25).
  - Runs after processing if selected (fm:freemocap/core/pipeline/posthoc/export_completion.py:21-23, 50-58), or on demand via the API (fm:freemocap/api/http/posthoc/export_jobs.py:56).
  - Supported formats are `wide_csv`, `npy`, `npz`, `notebook` (requests.py:27-37).
  - Selectable data: `LANDMARKS_3D`, `RAW_KEYPOINTS_3D`, `KEYPOINTS_3D`, `OVERLAY_2D`, `SEGMENT_POSES` (requests.py:24). Segment poses pair `SEGMENT_ORIGINS` with `ROTATIONS_WORLD` (fm:…/exports/arrays.py:30-45).
- **Directory and prefix:**
  - Directory: `exports/`, or `exports/run-<id>/` when `keep` or run ≠ 0.
  - Prefix: `<rec>`, or `<rec>.run-<id>` (wide_csv.py:161-166).
  - Lock: `exports/.exports.lock` (167).
- **File names:**
  - Labels: OVERLAY_2D→`2d_overlay`, RAW_KEYPOINTS_3D→`3d_keypoints_raw`, KEYPOINTS_3D→`3d_keypoints_filtered`, LANDMARKS_3D→`3d_landmarks`, SEGMENT_POSES→`3d_segment_poses` (30-36).
  - Table name: `<label>--<source after first ':'>`, plus `--<video stem>` for OVERLAY_2D. Characters `<>:"/\|?*` and control characters become `-`; case-insensitive collisions get `--2`, `--3`… (39-57).
  - CSV: `csv/<prefix>.<table>[.rows-K][.columns-K].csv`. Files split at 500,000 rows and at 1,024 value columns (26-27, 252-262).
  - NPY: `npy/<prefix>.<table>.npy`, plus one shared `npy/<prefix>.frames.npy` and `npy/<prefix>.timestamps.npy` taken from the first context (218-227).
  - NPZ: `<prefix>.npz` (ZIP_DEFLATED, zip64). Members are `<table>.values.npy`, `frames.npy`, `timestamps.npy`, `recording_info.json` (189-190, 237-241, 299-304).
  - Notebook: `<prefix>.explorer.ipynb` at the **take root**, not under `exports/`. This holds even for run-N (309-319; fm:…/exports/publication.py:67-80).
  - Inventory: `<prefix>_recording_info.json` (168). The legacy name `<prefix>.wide.metadata.json` is still read (174-176).
- **Wide CSV format:**
  - UTF-8 with BOM (`utf-8-sig`), `csv.writer` defaults: comma, minimal quoting, CRLF [tested] (267-272).
  - Header: `frame_number,timestamp_s,<name>.<component>…`. Static tables have no clock columns and one row (71-73, 256-257).
  - Floats are boxed to Python floats and written with `repr`, i.e. shortest round-trip [tested] (79-95).
  - Recorded null → `NaN`; absent entry → empty field (86-88).
  - Every file is reloaded and compared bit-exactly, including the sign bit (98-134).
  - Component order: `x,y,z` when the set is {x,y,z}; `w,x,y,z` when {w,x,y,z}; otherwise descriptor order (arrays.py:149-153).
  - OVERLAY_2D `visibility` is exported as `confidence` (arrays.py:222-224).
  - Segment-pose components are `x,y,z,qw,qx,qy,qz`, with quaternion units `"1"` (arrays.py:40-44, 140-147).
- **NumPy arrays:**
  - Values: float64, shape `(frames, names, components)`, NaN where unavailable.
  - Frames are the **sorted union** of frame numbers seen in that context; no frames are invented.
  - Frames int64; timestamps float64 (arrays.py:154-188; wide_csv.py:200-208).
  - Timestamps must strictly increase (arrays.py:176-177).
  - All selected arrays must share frames, and timestamps within 4 ULP (wide_csv.py:144-147, 203-206).
  - Written with `np.save(allow_pickle=False)` and reloaded for verification (227-231).
- **Inventory (`ExportManifest`, publication.py:37-45):**
  - `version` (3, or 4 when the notebook lives at the take root), `status:"complete"`, `artifacts{}`, `snapshots{source_sha256: snapshot}`, and `csv{encoding, delimiter, absent, null, float_precision, column_order}` (wide_csv.py:339-342).
  - `ExportArtifact` fields: `filename`, `location` (`exports`|`recording`), `sha256`, `rows`, `columns`, `source_sha256`, `source_revision`, `run_id`, `format` (tall_csv|static_tall_csv|wide_csv|static_wide_csv|npy|npz|notebook|metadata), `details` (publication.py:13-24).
  - Snapshot fields: `revision`, `exported_at` (UTC ISO), `recording_id`, `run_id`, `source_sha256`, `source_file`, `conventions{quaternion_order, segment_pose, missing_values}`, `reference_frames`, `channels{key: {context, names, components, source_components, units, shape, axes, missing_values, numpy_key, timing{frame_count, first_frame, last_frame, first_timestamp_s, last_timestamp_s}}}`, `selection`, and `numpy_timeline{…}` (wide_csv.py:209-217, 285-297; arrays.py:123-128).
  - The context key is the first 24 hex characters of sha256 of the selection JSON (requests.py:16-17).
  - `source_revision` is sha256 of `st_dev:st_ino:st_size:st_mtime_ns`. It identifies the file on disk, not its content (fm:…/parquet_storage/recording_view.py:41-43).
- **Publication:**
  - Staging dir `.staging-XXXX/` inside the export dir.
  - Journal `.publication.json` = `{version:1, staging, files:[{filename, sha256, no_clobber, location}]}`.
  - Files are replaced one at a time with `os.replace`; with `keep`, `os.link` is used so existing files are never clobbered. The manifest is written last (publication.py:150-163, 112-147).
  - Temporary arrays live in `arrays-XXXX/values.npy` and `present.npy` memmaps inside staging (arrays.py:181-188).
- **Guides:** `README.md`, `csv/README.md`, `npy/README.md` are created only if absent (fm:…/exports/guides.py:208-223).
- **Notebook content:**
  - nbformat 4.5 with the snapshot in `metadata.freemocap`.
  - It uses the relative path `.`, checks the Parquet sha256 before reading, and has cell IDs `freemocap-<i>` (fm:…/exports/notebook.py:141-203, 18-27).
- **Not wired.** `organize_exports` (relocating flat legacy files into csv/ and npy/) has no production caller (fm:…/exports/organize.py:14; grep found only its definition).

### 4.2 Tall CSV (fm:freemocap/core/recording/exports/tall_csv.py)
- **Enabled?** Default off (mocap_task_config.py:141). Runs post-processing when enabled (export_completion.py:24, 60-64), or via the API (fm:freemocap/api/http/posthoc/exports_router.py:93).
- **Files:**
  - `csv/<prefix>.tall.csv` and `csv/<prefix>.static.tall.csv`. The static file is always written, header-only if empty (79-81).
  - Inventory: `<prefix>.metadata.json`, `ExportManifest` version 1 (69, 136).
- **Format:**
  - BOM, then `pyarrow.csv.CSVWriter` (92-94, 116-119).
  - Columns = `SAMPLE_SCHEMA`: `timestamp_s,sensor_group,frame_number,source,reference_frame,channel,name,component,value,units,run_id` (fm:…/sample_encoding/arrow_schema.py:15-27). Static files omit `timestamp_s` and `frame_number` (tall_csv.py:26).
  - [tested, pyarrow 25.0.0] Header names and all string values are double-quoted; numbers are unquoted with shortest round-trip floats; nulls are empty; the line ending is LF.
- **Snapshot:** `revision`, `exported_at`, `software{freemocap, pyarrow}`, `recording_descriptor` (the full embedded descriptor), `static_channels_by_run` (130-134).
- **Publication and lock:** same as 4.1 (`.exports.lock`, staging, journal).

### 4.3 `annotated_videos/` (fm:freemocap/core/pipeline/posthoc/annotation_output.py)
- **Enabled?** Yes by default: `graph_annotate=True` (mocap_task_config.py:36), passed in at fm:…/dataflow/application_pipeline.py:150 and used at recording_pipeline.py:320-331.
- **Path:**
  - `<take>/annotated_videos/<source video file name>.annotated.mp4`, e.g. `X.mp4.annotated.mp4` (annotation_output.py:36-38; fm:freemocap/system/default_paths.py:13).
  - Run N≠0: `annotated_videos/run-N/<source name>.annotated.run-N.mp4` (fm:freemocap/core/recording/run_output_path.py:5-10).
  - This is the legacy folder name, not the canonical `videos/annotated`.
- **Temp file:** `.<source name>.<pipeline_id>.partial.mp4`, then `Path.replace` on success; deleted on close (41, 99-110, 121-122).
- **Codec:** skellycam `PyavVideoWriter` with H.264 libx264, yuv420p, crf 18, preset fast, CFR at `round(fps)`, PTS = frame index, BGR input (annotation_output.py:58-61; sc pyav_video_writer.py:11-18).
- **Container metadata:**
  - `comment = "skellycam.video_derivation:" + {"source_video": <take-relative POSIX path>, "frame_count": N}` (annotation_output.py:62-65; sc:skellycam/core/recorders/videos/video_derivation.py:11-23).
  - Frames must be complete and contiguous (75-76, 90-91).
- **Drawn content:** skellytracker `KeypointAnnotator` and the ChArUco annotator, coloured by body region (centre, left, right, hands, face) to match the realtime UI (fm:…/posthoc/annotation_style.py:1-28; fm:…/dataflow/annotation_workers.py:41-56).

### 4.4 Blender `.blend` and add-on outputs
- **freemocap side** (fm:freemocap/core/blender/export_to_blender.py:14-70):
  - Enabled by default: `export_to_blender=True`, `auto_open_blend_file=True` (mocap_task_config.py:149-163). It runs after the graph via `complete_mocap` (application_pipeline.py:95-98, 171; export_completion.py:26-27, 66-75).
  - Route `auto` → `parquet_segments` if exactly one `*_data.parquet` exists, else `legacy_npy`. Routes: `auto`, `legacy_npy`, `parquet_segments`, `parquet_constraints` (11, 30-38).
  - Output after processing: `<take>/<take>.blend`, or `<take>/run-N/<take>.run-N.blend` for run N≠0 (45-47). The API `/blender/export` always uses `<take>/<take>.blend` (fm:freemocap/api/http/blender/blender_router.py:74-77, 161-179).
  - Request and result JSON go to a system temp dir `freemocap-blender-*`, not the take (fm:freemocap/core/blender/runtime.py:115-121).
  - Blender stores custom scene property `freemocap_source_sha256` and saves again (fm:…/blender/helpers/run_blender_export.py:137-141).
  - Options: `formats ⊂ {fbx,bvh}`, `rest_pose ∈ {tpose,apose}`, `apply_foot_locking`, `limit_hand_markers_range_of_motion` (fm:…/blender/blender_export_config.py:5-18).
- **Add-on, Parquet routes** (addon:freemocap_blender_addon/export_api.py:26-39):
  - Writes `.blend` via `save_as_mainfile`. [inferred] Overwriting creates `<name>.blend1` under Blender's default save-versions setting.
  - Only when `formats` is non-empty: `<take>/exports/3d_models/<root>.fbx` and/or `<take>/exports/3d_models/<root>.bvh`. Here `<root>` = `FreeMoCap_<route>` (addon:…/core_functions/parquet_import.py:209; addon:…/core_functions/export_3d_model/parquet_export.py:58-104).
  - For `parquet_segments` BVH, also `<root>.bvh.metadata.json` = `{import_route, run_id, sensor_group, source, missing_sample_policy, missing_frames_by_bone}` (parquet_export.py:45-49).
- **Add-on, `legacy_npy` route** (`MainController.load_data`, addon:…/core_functions/main_controller.py:481-596). It reads `output_data/*` NPYs, which freemocap no longer writes [inferred], and writes:
  - `<take>/output_data/joint_angles.csv` (`%.8f`, plain header) and `joint_angles.npy` (223-228; addon:…/calculate_joint_angles/calculate_joint_angles.py:241-251).
  - `<take>/saved_data/`: `_FREEMOCAP_DATA_README.md`; `info/freemocap_data_handler.pkl` (pickle); `info/trajectory_names.json`; `info/metadata.json`; `npy/{body,right_hand,left_hand,face,<other>,all}_frame_name_xyz.npy`; `csv/<component>_trajectories.csv`; `all_trajectories.csv`. The CSVs use `np.savetxt fmt='%s'` with a `# `-prefixed header like `name_x, name_y, name_z,` (addon:…/freemocap_data_handler/helpers/saver.py:18-171).
  - `<blend dir>/saved_data/<rec>_bone_and_joint_data.csv` plus `_BONE_AND_JOINT_DATA_README.md` (main_controller.py:278-291; addon:…/create_rig/save_bone_and_joint_angles_from_rig.py:10-48).
  - `<take>/exports/3d_models/<rec>.fbx|.bvh` when formats are set (main_controller.py:452-466; addon:…/export_3d_model/export_3d_model.py:49-153).
- **Add-on, UI-only video render:** `<take>/video_export/<take><suffix>.mp4` and `video_export/render_cameras/*` (addon:…/export_video/helpers/composite_video.py:80-85, 142). Not called by `export_api`.
- **Scene contents (Parquet route, brief):**
  - Root empty `FreeMoCap_<route>` with custom properties `timestamps_s`, `model_snapshot`, `scene_build_report`, `animation_cleanup`.
  - Rig `<root>_Blender_skeleton_rig`.
  - Video planes from `annotated_videos/`, else `synchronized_videos/`.
  - Cameras `Capture_<id>` from Parquet `camera_geometry`, positioned at world_position/1000 (metres), with a `calibration` JSON property.
  - `FreeMoCap_overview` camera and `FreeMoCap_light`.
  - Sources: parquet_import.py:209-217; addon:…/core_functions/parquet_scene.py:157-237, 273-282, 327.

### 4.5 `.processing.lock`, temp names, other operational files

| file | writer | notes |
|---|---|---|
| `<take>/.processing.lock` | `recording_write_lock` (fm:…/parquet_storage/parquet_writer.py:28-33) | FileLock, timeout 0; `mkdir`s the take |
| `<take>/tmpXXXX.parquet.tmp` | `publish_parquet` (parquet_writer.py:70-91) | zstd; fsync; `ReplaceFileW` on Windows, else `os.replace` (fm:…/parquet_storage/shared_file.py:43-60) |
| `<take>/tmpXXXX.info.tmp` | `write_recording_info` (recording_info.py:37) | |
| `exports/.exports.lock`, `.staging-*`, `.publication.json` | exporters (4.1, 4.2) | Left behind if publication is interrupted |
| `exports/run-N/` (possibly empty) | `RunSaveSession.resolve` reserves the ID with `mkdir` (fm:…/result_processing/run_save_session.py:30-44) | Also scans `<take>/run-*` and `annotated_videos/run-*` |
| `<toml>.lock`, `exports/[run-N/]calibration_copies/.calibration-export.lock` | §1.6 | [inferred] filelock may leave these files behind |
| `annotated_videos/.<src>.<id>.partial.mp4` | §4.3 | |

### 4.6 `output_data/` writers

| file | writer | prod? |
|---|---|---|
| `output_data/charuco_3d_xyz.npy` | `set_charuco_board_as_groundplane` (anipose_calibration_helpers.py:138-146): (frames, corners, 3) float, interpolated, mm, aligned frame | Only when `alignment_method="charuco"`; default `None` (calibration_task_config.py:37-41, 52-54) |
| `output_data/charuco_observations_realtime.pkl` | `_flush_buffer` (fm:freemocap/core/pipeline/realtime/charuco_recorder_node.py:183-227): pickle `{board_definition, observations{camera_id:{connection_frame_number: Observation}}, frame_range, recording_uuid}` | **No.** `CharucoRecorderNode` is never constructed (fm:…/realtime/realtime_pipeline.py:255 sets it to None; grep found no `.create(` call). The reader is still active (fm:…/posthoc/video_node.py:412-440) |
| `output_data/joint_angles.*` | add-on legacy route (4.4) | Only with the legacy_npy route |

### 4.7 Other writes into a take
- **Video import** (`/mocap` import endpoint): copies videos into a **new** `<take>/synchronized_videos/` with no info JSON (fm:freemocap/api/http/mocap/mocap_router.py:327-365).
- **`logs/`:** no writer found. `create_on_disk` is the only code that makes `logs/` and is called only in tests (recording_structure.py:134-137; grep of freemocap/, the UI electron folder and skellycam). App logs go to `<base>/logs_info_and_settings/logs/` (fm default_paths.py:14-15, 59).
- **`output/`:** no writer found (canonical name in recording_structure.py:98-101).
- **Recording type tags:** claimed in the docstring (recording_structure.py:20, 24-25), but no writer was found (grep for `recording_type`).

---

## 5. Folder contract

- **RECORDING_CONTRACT.md** (fm:RECORDING_CONTRACT.md):
  - "Maintained target, version 1", independent of the Parquet schema version. It governs new code, and the current-state audit lives in `current-work-plans/03-transport/recording-folder-contract.md` (3-9).
  - **Canonical tree** (18-41):
    - `<id>_recording_info.json`, `<id>_calibration.toml`, `<id>_data.parquet`.
    - `videos/synchronized/timestamps/camera_timestamps/`, `videos/annotated/`, `logs/`.
    - `exports/csv/<id>.tall.csv`, `.static.tall.csv`, `<id>.landmarks_3d--standard_human.csv`, `npy/`, `<id>.npz`, `<id>_recording_info.json`.
    - `exports/run-0/` with run-qualified names.
  - **Rules:**
    - The tree is about locations; files may be absent (43-46).
    - `RecordingStructure` owns path construction (48-51).
    - The root `.blend` is a compatibility location; `charuco_board_info.json` is optional input; caches are disposable; `.processing.lock` and publication scratch files are operational (53-59).
  - **Ownership table** (61-70):
    - Capture identity, camera settings, media/timing: skellycam.
    - Processed samples and runs: Parquet.
    - Calibration solution: TOML.
    - Defaults: app config.
    - Used settings: stage provenance.
    - Exports: export metadata.
  - **Compatibility inputs:** `synchronized_videos/`, `annotated_videos/`, `<id>_info.json`, `<id>_camera_calibration.toml`, `output_data/`.
    - Resolve each artifact on its own, never pick an arbitrary first match, require explicit choice when ambiguous (81-88).
    - Never rename or move user data (90-94).
  - **Runs, export retention, acceptance:** lines 96-324.
- **paths.json** (fm:shared/recording-contract/paths.json:1-25):
  - `contract_version: 1`.
  - `canonical`: `videosSynchronizedDir` videos/synchronized, `videosAnnotatedDir` videos/annotated, `outputDir` output, `exportsDir` exports, `logsDir` logs, `calibrationTomlPath` `{recordingName}_calibration.toml`, `recordingInfoPath` `{recordingName}_recording_info.json`, `dataParquetPath` `{recordingName}_data.parquet`, `blendPath` `{recordingName}.blend`. Each maps to a Python attribute name.
  - `legacy_v1`: synchronized_videos, annotated_videos, output_data, exports, logs, `{recordingName}_camera_calibration.toml`, `{recordingName}_recording_info.json`, `output_data/freemocap_data_by_frame.parquet`, `{recordingName}.blend`.
- **Contract tests** (fm:freemocap/tests/test_recording_folder_contract.py):
  - Python paths equal the frontend YAML and paths.json for names with spaces and non-ASCII, and lookup creates nothing (17-26).
  - The legacy YAML matches (29-33).
  - `create_on_disk` leaves `exports/` lazy (36-41).
  - Hybrid inventory: legacy folder detected, `<id>_info.json` bytes unchanged, no files created (44-61).
  - An empty inventory creates nothing (64-68).
  - Implementation: `RecordingStructure` and `validate_layout` (recording_structure.py:68-184); frontend YAML at fm:freemocap-ui/src/store/slices/active-recording/layout-presets/layout-presets.yaml:13-33.

**Where the writers at c27fc299 do not match the canonical contract.** Facts above, compared side by side:
- **Calibration TOML.** Written as `_camera_calibration.toml`, not `_calibration.toml` (§1.6).
- **Annotated videos.** Written to `annotated_videos/`, not `videos/annotated/` (§4.3).
- **skellycam folders.** skellycam writes `synchronized_videos/…/timestamps/camera_timestamps/`, not `videos/synchronized/…` (§3.1).
- **Export label.** The code's export label is `3d_landmarks--…`, while the contract example says `landmarks_3d--…` (wide_csv.py:34 vs RECORDING_CONTRACT.md:32).
- **Tall CSV inventory.** The tall CSV inventory is `<prefix>.metadata.json`, which the contract tree does not list.
- **Notebook location.** The notebook is published at the take root (§4.1).
- **Blender exports.** The add-on writes `exports/3d_models/` and `saved_data/` outside any contract list (§4.4).

Not checked: the frontend's default export selections; the full scene structure of `.blend` files; the Parquet file (another agent covers it); behaviour of the exact locked library versions, since my formatting checks used the venv's slightly different versions.

Main-session spot-check (2026-11-16): `CameraToml.from_camera` keys (calibration_toml.py:140-152), the capture-JSON copy in `write_recording_info` (recording_info.py:11-18) and the annotated video name `<source>.annotated.mp4` (annotation_output.py:36-38) match the source.
