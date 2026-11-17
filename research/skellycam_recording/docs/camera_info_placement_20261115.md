# Camera and take information: inventory and placement (research)

Status: research report, 2026-11-15, for plan question R3-Q6. A read-only sub-agent study; every placement in it is proposed. The main session verified `camera_id` = first 2 bytes of SHA-256 (skellycam dev-streaming detect_cameras_devices.py:44-54) and that freemocap copies the capture JSON into `<rec>_recording_info.json` (freemocap dev-streaming recording_info.py:11-16). Note: written before Dom's privacy decision (private data allowed in any field, with a strip option) and before the audio container was decided; its privacy section and the `.flac` in the example are superseded.

Written for: Dom and agent sessions writing the skellyfileformat manifest, info JSON and CSV header sections.

---

Camera and take information in the new skellyfileformat folder: inventory, where each fact should live, overview, privacy, questions

Read-only. No files written and no git state changed. Nothing was run except git show/grep.

Citation keys:
- SCds = skellycam `upstream/development-streaming`
- P1 = skellycam-phase1 worktree, branch dom/capture-recording-phase1 @7d06ba2e1
- FMds = freemocap `upstream/development-streaming` @c27fc299
- v0S = skellyfileformat `bd62b60:spec/SPEC.md`
- WFP = research/skellycam_recording/docs/whole_folder_spec_plan_20261113.md
- MFR = manifest_field_review.md
- ASF = recording_upgrade/results/audio_single_file/FINDINGS.md
- PLAN = research/CAPTURE_AND_RECORDING_PLAN.md

## 0. Main findings

1. **Today almost nothing reads the per-camera fields from a file.** The only file reads in skellycam are three maps (`videos`, `camera_timing`, `multiframe_timing`). They are read through `read_recording_field`, which globs `*_info.json` (SCds recording_metadata.py:14-29). In skellycam, no file reader uses any `camera_configs` field: not exposure, framerate, resolution, rotation, camera_name or camera_index. In freemocap, I found no file reader of these fields either (git grep on FMds, excluding tests). Readers take resolution and fps from the container (FMds video_group_helper.py:133-140).
2. **freemocap copies the whole skellycam info JSON into `<rec>_recording_info.json`.** `existing = path if path.exists() else legacy`; it loads that file, then adds a `processed` block (FMds core/recording/recording_info.py:12-16, 31). So every capture field exists twice today, absolute path included. This conflicts directly with the accepted rule "two info JSONs, no copied fields" (WFP:486, Q6).
3. **A `# key=value` header breaks both of today's CSV readers.**
   - `read_recording_timing` takes the first line as the column names. It strips only a leading `"# "` and requires `recording_frame_number` plus `timestamp.from_recording_start.sec` (SCds recording_timing_reader.py:95-101).
   - freemocap reads the CSV with its own `csv.DictReader` (FMds video_node.py:501-505).
   - Both must change before freemocap can read the new sidecar.
4. **`camera_id` is a 16-bit hash.** It is the first 2 bytes of SHA-256 over the device path, or over `vid_pid_index` (SCds detect_cameras_devices.py:44-54). It is the key of every map, the `id-` in file names, and the key freemocap uses to bind calibrations, with `camera_index` as the fallback (FMds calibration_camera_binding.py:10-14). The index is not stable (usb_cameras/REPORT.md:54, finding 23).
5. **`camera_name` is the OS device name, not a user name.**
   - Path: cv2_enumerate_cameras `CameraInfo.name` (SCds detect_cameras_devices.py:57-60) → UI default config (skellycam-ui cameras-types.ts:123-131; cameras-thunks.ts:68-72) → saved in localStorage (cameras-thunks.ts:44-61).
   - If unset it becomes `Camera-<id>` (camera_config.py:125-129).
   - No UI lets the user edit it: both UIs only display `camera.name` (skellycam-ui CameraTreeItem.tsx:95; freemocap-ui CameraTreeItem.tsx:132). So user-entered names do not exist in code yet.
6. **Phase 1 records nothing more than dev-streaming.**
   - P1's CameraConfig is identical (git diff of camera_config.py is empty). P1's RecordingInfo lacks even the three maps (P1 recording_info.py:77-86).
   - Locked controls are not implemented. P1 sets only exposure mode and exposure (opencv_apply_config.py:34-47), plus resolution, fps and fourcc (:75-84).
   - White balance, focus, zoom, pan, tilt, gain and power-line exist only as plan decisions D10–D12 (PLAN:443-445).
7. **Rotation is baked into the pixels today.** The writer calls `cv2.rotate` (SCds video_recorder.py:52, 96-99). The posthoc reader honours only the container's rotation (sequential_video_reader.py:49-53). Live freemocap rotates frames from the shared-memory `camera_info.rotation` (FMds camera_node.py:292-295; realtime_skeleton_inference_node.py:327-331). None of these reads a file field.

## 1. Inventory: writer and readers of every field (SCds unless marked)

### 1a. Files a take folder gets today

| File | Writer | When |
|---|---|---|
| `<rec>/<rec>_info.json` | recording_info.py:80-104 | At finalisation only (recording_finalizer.py:55); written with plain `open`, not atomic (:103-104) |
| `synchronized_videos/<rec>.id-<id>.idx-<idx>.<ext>` | video_recorder; name pattern video_filename.py:7 | — |
| `sv/timestamps/camera_timestamps/<rec>.camera<id>.timestamps.csv` | create_camera_csvs.py:101-105; path recording_timing_reader.py:15 | — |
| `sv/timestamps/<rec>_timestamps.csv` (multiframe) | create_multi_frame_csvs.py:113-119 | — |
| `sv/timestamps/<rec>_stats.json` and `.txt` | save_timestamps_statistics_summary.py:19-27 | — |
| `sv/<rec>.audio.wav` and `sv/<rec>.audio_timestamps.json` | audio_recorder.py:121-163; paths recording_info.py:128-134 | — |
| `sv/synchronized_videos_README.md` | recording_finalizer.py:24-31, 69-71 | Static prose |

### 1b. CameraConfig (camera_config.py:63-123; identical in P1), written as `camera_configs` in the info JSON (recording_info.py:98-101)

| Field | Origin | File readers | In-memory / live users |
|---|---|---|---|
| `camera_id` (map key) | detect_cameras_devices.py:44-54 | Key of `videos` and `camera_timing` (recording_info.py:86-96). Read via VideoAssociations (video_associations.py:14-16) and recorded_camera_timing_path (recording_timing_reader.py:18-24). FMds: video_group_helper.py:440-442 and 364-371 (source IDs → videos); playback_router.py:75-84, 760-806; recording_timing.py:29-31; video_node.py:496 | Name stem (video_filename.py:7); CSV name (recording_timing_reader.py:15); FMds Parquet `camera_id` (observation_inputs.py:178-183, 167-171); TOML table name (calibration_toml.py:140-144); calibration binding |
| `camera_index` | OS enumeration | None from a file. It is in the file name (`idx-`), but FMds no longer parses names (no `ParsedVideoFilename`/`try_extract` hits; it uses whole file names, video_group_helper.py:337-343) | FMds live: websocket_server.py:215, 225; realtime_aggregator_node.py:435-445 (calibration binding fallback, calibration_camera_binding.py:10-14); TOML `index` (calibration_toml.py:144) |
| `camera_name` | OS device name (finding 5) | None | Display in UI trees; logs (opencv_apply_config.py:90) |
| `use_this_camera` | UI | None | Runtime flag |
| `resolution` | UI request | None. Readers probe the container | Finalizer shape check (recording_finalizer.py:161-163); remux metadata (disabled, :98-110) |
| `color_channels`, `pixel_format` ("RGB" placeholder, :90-92) | defaults | None | Shared-memory shapes; per-frame camera_info (numpy_record_dtypes.py:10-14) |
| `exposure_mode`, `exposure` (OpenCV log2 units, :100-106) | UI | None | opencv_apply_config.py:34-47 |
| `framerate` (−1 = camera default, :26, 108) | UI | None | create_cv2_video_capture.py:58 |
| `rotation` (int; rewritten to an enum name in the JSON, recording_info.py:100-101) | UI | None | Writer bake (video_recorder.py:96-99); live freemocap rotation (shared memory); UI mismatch check (freemocap-ui cameras-selectors.ts:160-164) |
| `capture_fourcc` | default MJPG | None | create_cv2_video_capture.py:54 |
| `writer_fourcc` | default X264 | None | Picks the extension (camera_config.py:182-187; recording_info.py:106-121) |

### 1c. RecordingInfo (recording_info.py:21-27) plus the added maps

| Field | Writer | Readers | Use |
|---|---|---|---|
| `recording_name` | User / folder name | In memory everywhere (FMds recording_info.X call sites, e.g. mocap_pipeline.py:210) | Paths and file stems |
| `recording_directory` (absolute) | recording_info.py:23 | In memory: FMds calibration_router.py:179-180. Leaks into: TOML metadata via `result.recording_info = recording_info` (posthoc_calibration_task.py:137, 142-146; CalibrationMetadata.recording_info, calibration_metadata.py:30); freemocap's recording info copy (finding 2); `_stats.json`, whose dataclass serialises `recording_info` (recording_timestamp_stats.py:44, 155-156; inferred, not run) | Path building |
| `recording_uuid` | uuid4 with dashes (:24) | In memory: FMds charuco_recorder_node.py:223 (into a pickle, never read back). UI calibration-types.ts:78-97 expects it inside TOML metadata | Take id. freemocap builds fresh RecordingInfo objects from paths (calibration_router.py:130-134; mocap_router.py:46-50), each with a new random uuid |
| `mic_device_index` | UI | Live only: camera_group.py:207-214 | PortAudio device index |
| `recording_start_timestamp` (FullTimestamp, 13 fields incl. IANA `local_time_zone`; full_timestamp.py:18-52) | Taken when RecordingInfo is constructed, not at the first frame (MFR §F) | UI type only (calibration-types.ts:83-96) | Wall clock |
| `videos` {id → file relative to `sv/`} | :86-91 | VideoAssociations users (1b row 1) | The freemocap seam |
| `camera_timing` {id → CSV path relative to the take} | :93-96 | recording_timing_reader.py:18-24 → FMds playback_router.py:82, 801; recording_timing.py:30; video_node.py:496; tools/datasets/full_recording_comparison.py:51-53 | Timing lookup |
| `multiframe_timing` | :97 | recording_timing_reader.py:27-31 → recording_statistics.py:13-23 → FMds playback_router.py:340-342 (recording list: frames, duration, fps); FMds recording_timing.py:36-41 (synchronized timeline, method RECORDED) | Timeline and stats |

### 1d. Other files

- **Per-camera CSV.** Columns come from CAMERA_TIMESTAMPS_CSV_ROW_DTYPE (numpy_record_dtypes.py:49-78), filled in create_camera_csvs.py:54-99:
  - `recording_frame_number`, `connection_frame_number`;
  - `timestamp.from_recording_start.sec`, `timestamp.perf_counter_ns.ns` (the midpoint of pre-grab and post-grab, :50-51), `timestamp.utc.seconds`, `timestamp.local.iso8601`;
  - `from_previous.*`, 9 `frame.*.ns` and 10 `duration.*`/`total.*` columns.
  - **No per-camera constant columns.**
  - Readers: `read_recording_timing` (the two columns above); FMds video_node.py:504-505 (the two frame numbers); the finalizer counts rows (recording_finalizer.py:190-198).
- **Multiframe CSV:** per-frame means and stats across cameras (create_multi_frame_csvs.py:41-111). Readers are listed in the `multiframe_timing` row above.
- **`_stats.json`:** `RecordingTimestampsStats` (recording_timestamp_stats.py:44-62), serialised at :123-156. FMds has no reader (no `_stats.json` or `framerate_stats` hits). The in-memory object feeds skellycam's stop-recording response (camera_router.py:76-86, 170-183).
- **Audio JSON:** `audio_file`, `mic_device_index`, `sample_rate`, `channels`, `chunk_size`, counts, start/end perf ns, duration, chunk statistics, `timebase_mapping{utc_time_ns, perf_counter_ns, local_time_utc_offset}`, and per-chunk ns (audio_recorder.py:140-159). Its only reader is `load_audio_start_time` (video_audio_remuxer.py:159-163), whose caller is commented out (recording_finalizer.py:63).
- **freemocap UI schema** for `<rec>_recording_info.json`: `recording_name`, `recording_types`, `created_at`, `camera_configs`, `notes`, passthrough (freemocap-ui recording-structure.ts:104-110). It is defined, but git grep found no user.
- **freemocap recording list:** "created" comes from the folder's mtime (FMds playback_router.py:345-353); frames, duration and fps come from the multiframe CSV, or else from the container.

## 2. Proposed placement: "one fact, one home" (all proposed)

| Fact | Home (authoritative) | Allowed copies, and why | Not anywhere else |
|---|---|---|---|
| Format version, writer | Every file states its own (Q2) | — (per-file self-description, not a copy) | |
| `take_uuid` | CSV header of each media file: the file's take membership (needed when the manifest is missing, R3-Q4) | Manifest: the take's file list. Info JSONs, TOML and Parquet carry it as a link key. On disagreement the file is not a member (warning) | Drop `recording_uuid`. If a reader needs it, map `recording_uuid` to `take_uuid` as 32 lowercase hex (WFP:242) |
| Take anchor `take_start_host_ns`, `take_start_utc_ns`, `utc_offset_min`, `clock`, `clock_hz` | CSV headers (v0S SFF-650/651; identical in all) | Manifest `take_start_utc` ISO string (for readability; informative) | Drop FullTimestamp and the IANA zone (SFF-651 forbids a zone name) |
| `group_size`, `group_position` | CSV header (detects a missing camera without the manifest) | Manifest camera-array order follows `group_position` | Today order is dict order (recording_info.py:86-89 → FMds video order) |
| `camera_key` (MUST, C12) | CSV header | Link key in the manifest, info JSON, TOML camera table and Parquet camera source: foreign keys, not facts | |
| `camera_label` | CSV header (v0S:290, SFF-161) | Device-file name stem (B4, SHOULD); manifest copy for readability | Info JSON map key → use `camera_key` |
| Nominal rate (rational) | CSV header | MKV DefaultDuration (container-required; must agree) | Parquet `nominal_fps` (Q11) |
| `display_rotation` | CSV header (restates 68Z6 for the CSV era) | None, unless Dom allows the overview echo (Q4) | Drop `camera_configs.rotation` (C14(a)); no container flag; no EXIF |
| Stored resolution | MKV/JPEG itself | Overview (derived); Parquet ImageReference width/height (the 2D coordinate space, Q9) | CSV header: not needed to read timing |
| Frame count, gaps/filled frames | CSV rows plus a `# end rows=… gaps=… filled=…` footer | Manifest overview (derived) | Delete the multiframe CSV and the stats files (REV decision 3) |
| Requested settings (resolution, framerate incl. "camera default", capture format, exposure mode) | Info JSON `camera_configs[key].requested` | — | |
| Locked control values, read back (exposure, gain, WB, focus, zoom, pan, tilt, power-line, AE priority, image controls; whether auto was on at start, D10/D11) | Info JSON `camera_configs[key].controls`, units in names (e.g. `exposure_us`; MFR notes the OpenCV→MF unit change) | TOML camera table `controls_at_calibration`: a different fact (the setup), used for the D11 mismatch prompt | |
| Exposure-step results (D14) | Info JSON | — | The per-device cache stays in skellycam's app data, outside the take |
| Device identity (model, OS name, vid/pid, serial or port path, backend, OS index at capture) | Info JSON `camera_configs[key].device` (privacy: §4) | Inputs of `camera_key`, which is derived from them | CSV headers and file names |
| User-entered camera name | Info JSON `camera_configs[key].user_name` | Overview (Q5) | |
| Links camera → video → CSV → calibration camera; roles of all files; original recording name | Manifest (R3-Q3) | — | Drop `videos` and `camera_timing` from the info JSON; drop `multiframe_timing` |
| Audio rate, channels, codec | The audio file's own header | CSV header copy (needed to read the CSV alone; a killed WAV may have a stale header, ASF §1.3) | |
| Mic device name, host API | Info JSON `audio` block | — | ASF's proposed `# device=` CSV line (ASF:119) should move here |
| Processed summary (runs, Parquet hash) | `<rec>_recording_info.json` (FMds recording_info.py:31-36) | — | It must stop copying the capture JSON (:12-16) |
| Calibration identity | TOML `[metadata]`: `calibration_uuid`, `source_take_uuid`, version (R3-Q5); camera tables: `camera_key`, `camera_label`, size | Manifest records the take's copy, with its hash (R3-Q5) | Replace the embedded RecordingInfo (calibration_metadata.py:30) |
| Parquet camera source | `camera_key`, video file name, CSV file name, `timing_method` (schema_version 2, Q8) | — | |

### Per-camera CSV header (proposed sketch)

Values are illustrative. The per-frame columns belong to the timing spec, not to this review. The rows need **no per-camera constants**: today's rows have none either (numpy_record_dtypes.py:49-78).

```
# skellyfileformat_video_timing=1.0.0
# writer=skellycam 2.0.0
# take_uuid=6f1c2c1e1d7e4c479a3e2f2b3c4d5e6f
# take_start_host_ns=812345678901234
# take_start_utc_ns=1794751407412305000
# utc_offset_min=0
# clock=QPC
# clock_hz=10000000
# group_size=3
# group_position=0
# camera_label=3fa2
# camera_key=9c41d07a55e2b318
# nominal_rate=30/1
# display_rotation=90
frame,source_frame_number,arrival_ns,sample_time_ns,flags,crc32
...
# end rows=18342 gaps=2 filled=2
```

A `segment_uid=` line binding the CSV to the MKV is optional. Whether PyAV can set the Segment UID before the first frame is not verified.

### Manifest and info JSON content

- **Manifest:** see §3 for the full layout. Each file appears exactly once:
  - in `cameras[]` (camera_key, label, video, timing, calibration camera id);
  - or in `files[]` (path, role, owner, sha256 where useful).
- **`<rec>_info.json`:**
  - top level: `skellyfileformat`, `writer`, `take_uuid` (link);
  - `camera_configs` keyed by `camera_key`, each with `device`, `user_name`, `requested`, `controls`, `exposure_step`;
  - an `audio` block;
  - no `recording_directory`, `mic_device_index`, FullTimestamp, rotation, `use_this_camera`, `color_channels`, `pixel_format` or `writer_fourcc` (MFR verdicts).
  - Written at take start and at finish, atomically (MFR O2(i); R3-Q9).

### Conflicts with accepted decisions

- TDB5 item 2 (no manifest) and item 5 (info JSON not in the format) are reversed by R3-Q3 and A1.
- 68Z6 cites MCAP "camera file metadata". It needs restating for the CSV sidecar, and its item 3 forbids any overview echo of rotation.
- MFR O1(a) (no manifest) and its "drop S8 sidecar path" verdict are reversed: CSVs are separate and never embedded now, so the paths do not go stale. MFR's other verdicts hold (drop `recording_directory`, `camera_name` skellycam-only, `take_uuid` header-authoritative).
- v0S SFF-653 and DK8S item 8 are reversed for camera identity by R4-Q2 (WFP:508).
- REV decision 2 (binary) is replaced by R3-Q1/Q2.

### Code that must change (from today's reads)

**skellycam:**
- Writer: recording_info.py:80-104 (new shape, atomic, start and finish); a new manifest writer; a CSV writer replacing create_camera_csvs.py, create_multi_frame_csvs.py and save_timestamps_statistics_summary.py.
- Readers: recording_metadata.py:14-29 (glob → manifest); video_associations.py:14-16; recording_timing_reader.py:18-31 and 95-101 (skip `#` lines, new columns); recording_statistics.py:13-23; playback_router.py:303-311; sequential_video_reader.py:49-53 (apply CSV `display_rotation`, 68Z6 item 4).

**freemocap:**
- recording_info.py:12-16 (stop copying the capture JSON).
- video_group_helper.py:384-401, 440-442; playback_router.py:75-84, 340-353, 760-806; recording_timing.py:29-47 (no multiframe file → MEAN_CAMERA_TIMES); video_node.py:491-509.
- calibration_metadata.py:30 and posthoc_calibration_task.py:137 (the embedded RecordingInfo); calibration_toml.py:123-152. `extra="ignore"` and `from_camera` would drop `camera_key` on round-trip.
- calibration_camera_binding.py (bind by `camera_key`); observation_inputs.py:178-183 plus the strict validation at playback_queries.py:131 (WFP:157).
- freemocap-ui recording-structure.ts:104-110 and calibration-types.ts:78-97.
- The live rotation paths (camera_node.py:292-295) stay; the shared memory is not a file.

## 3. Human-readable overview

**Recommendation: one file. Put a derived `summary` block first in `recording_manifest.json`, and write no generated README.**

Reasons:
- **One atomic file.** It is written at start and finish (crash-safe) and updated by freemocap under `.processing.lock`. A README would be a second file to keep in step, and it goes stale on every crash or partial update.
- **One fact, one home.** The summary is the single declared copy-for-readability. The spec marks it informative ("readers MUST NOT use summary values for processing; on disagreement the home wins; the validator warns `summary_stale`").
- **The apps need it too.** freemocap's recording list currently opens the multiframe CSV and uses the folder mtime as "created" (playback_router.py:340-353). It could read the summary instead.
- **JSON reads well enough** in Notepad or a browser if the key order is fixed, units are in the names, and ISO strings sit beside ns values.
- **The existing README is static prose** (recording_finalizer.py:27-31). Drop it in new takes, or replace it with one static line pointing at the manifest and the spec.
- A Markdown rendering can come later as a reader command (proposed; not to build now).

Example layout (values realistic, abbreviated):

```json
{
  "skellyfileformat": "1.0.0",
  "take_uuid": "6f1c2c1e1d7e4c479a3e2f2b3c4d5e6f",
  "original_recording_name": "2026-11-15_14-03-27_gait_trial_03",
  "take_start_utc": "2026-11-15T14:03:27.412Z",
  "state": "finished",
  "summary": {
    "_note": "Derived for people. Not authoritative.",
    "duration_s": 611.40,
    "frames_per_camera": 18342,
    "cameras": [
      {"label": "3fa2", "user_name": "left tripod", "model": "HD Pro Webcam C920",
       "stored_px": "1280x720", "display_rotation_deg": 90, "nominal_fps": 30,
       "measured_fps_median": 29.98, "gaps": 2, "filled": 2, "exposure_us": 4000, "gain": 32},
      {"label": "b71c", "user_name": "front", "model": "Kiyo Pro",
       "stored_px": "1920x1080", "display_rotation_deg": 0, "nominal_fps": 30,
       "measured_fps_median": 30.00, "gaps": 0, "filled": 0, "exposure_us": 3000, "gain": 48}
    ],
    "audio": {"file": "2026-11-15_14-03-27_gait_trial_03.audio.flac", "sample_rate_hz": 48000, "channels": 2, "duration_s": 611.38},
    "calibration": {"calibration_uuid": "…", "source_take": "2026-11-15_13-50-02_calib", "reprojection_error_px": 0.41},
    "processing_runs": [{"run_id": 0, "origin": "realtime", "finished_utc": "2026-11-15T14:13:40Z"},
                        {"run_id": 1, "origin": "posthoc", "tracker": "mediapipe", "finished_utc": "2026-11-15T14:31:02Z"}],
    "warnings": [{"code": "camera_gap", "camera": "3fa2", "count": 2}]
  },
  "cameras": [
    {"camera_key": "9c41d07a55e2b318", "camera_label": "3fa2",
     "video": "synchronized_videos/2026-11-15_14-03-27_gait_trial_03.3fa2.mkv",
     "timing": "synchronized_videos/2026-11-15_14-03-27_gait_trial_03.3fa2.csv",
     "calibration_camera": "3fa2"}
  ],
  "files": [
    {"path": "2026-11-15_14-03-27_gait_trial_03_info.json", "role": "capture_info", "owner": "skellycam"},
    {"path": "2026-11-15_14-03-27_gait_trial_03_recording_info.json", "role": "processing_info", "owner": "freemocap"},
    {"path": "2026-11-15_14-03-27_gait_trial_03_camera_calibration.toml", "role": "calibration", "sha256": "…"},
    {"path": "2026-11-15_14-03-27_gait_trial_03_data.parquet", "role": "tracking", "owner": "freemocap"}
  ]
}
```

## 4. Privacy: fields that can hold user-entered or identifying text (no decision made)

| Field | Where today / proposed | Needed for | Options |
|---|---|---|---|
| Recording name (user-typed; may name a subject) | Folder, every file stem, `original_recording_name`, `recording_name` (recording_info.py:22) | Identity, file names | Keep as entered with a privacy note / warn on entry / user opt-in to a generic name |
| User camera name (planned, R3-Q7) | Proposed: info JSON plus overview | Telling cameras apart | Keep with a note / omit from overview / opt-in |
| OS device name (`camera_name`) | Info JSON `camera_configs` (finding 5). Can name a person, e.g. a phone camera named after its owner (inferred) | Identification (R4-Q2) | Keep with a note / hash / omit |
| Device model string | Not stored today; proposed in `device` | Identification; R4-Q2 says it is not safe either | Same as above |
| Serial number | Not stored. `camera_key` hashes it (v0S SFF-162); a short serial can be brute-forced (MFR O4) | Stable identity across takes | Raw with a warning (R4-Q2 direction) / hash only / HMAC per install |
| Device path, MF symlink, USB port path | `camera_id` hash input (detect_cameras_devices.py:47-48); not written | Identity when there is no serial | Hash / omit / raw with a note |
| vid/pid | UI only (cameras-thunks.ts:91-94) | Model identity | Keep (low risk) / omit |
| Absolute paths with the OS user name | `recording_directory` in the info JSON, freemocap's copy, TOML metadata, `_stats.json` (§1c) | Nothing on disk | Omit (MFR, WFP D4). Old files stay as written |
| Mic device name, host API | Not written today (logged only, audio_recorder.py:59-63); ASF proposes `# device=` | Diagnostics | Info JSON only / omit / opt-in |
| Time-zone name; UTC offset; local ISO column | FullTimestamp `local_time_zone`; `timebase_mapping.local_time_utc_offset`; CSV `timestamp.local.iso8601` | Local display | Offset only (SFF-651) / omit the column |
| Free text `notes` | freemocap-ui schema (recording-structure.ts:109) | User notes | Keep with a note |
| Hostname, OS user name | Not written (git grep for gethostname, getuser and similar: no hits) | — | Keep out (spec rule) |

Warning mechanism and scope are R4-Q3/Q4 (open).

## 5. Open questions for Dom (each with a recommendation)

1. **Cross-file link key.** Recommend `camera_key` everywhere (manifest, info JSON map key, TOML, Parquet). `camera_label` is only for people.
2. **`camera_label` form.** Today it is a 16-bit hash (about 0.2 % collision chance at 16 cameras, MFR). Recommend a hex prefix of `camera_key`, 6 to 8 digits, unique in the take, with user names carrying the meaning.
3. **Overview location.** Recommend the manifest `summary` block only. No generated README; drop `synchronized_videos_README.md` in new takes.
4. **Allow a declared informative copy?** The summary echoes rotation, exposure and counts, and 68Z6 item 3 forbids writing rotation anywhere else. Recommend amending 68Z6: the summary is the one allowed copy, and readers must not use it.
5. **User camera names.** Recommend the info JSON as their only home, plus the summary copy. Never in CSV headers or file names.
6. **Device identity detail under R4-Q2.** Recommend model, OS name, vid/pid and serial/port in the info JSON `device` block, with a privacy warning. `camera_key` is derived from these.
7. **Writer-observed warnings** (gaps, control read-back mismatch, AWB not converged). Recommend a manifest `warnings[]` list; skellycam appends at finish, freemocap appends later.
8. **Requested vs actual.** Recommend: requested settings and read-back control values in the info JSON. Actual resolution, rate and counts are not stored; they come from the MKV and the CSV.
9. **File-name pattern.** Recommend `<rec>.<camera_label>.mkv` with `.csv` beside it, dropping `idx-`: it is unstable (finding 23) and has no reader in FMds.
10. **Take start in the manifest.** Recommend an informative ISO copy; CSV headers stay authoritative.
11. **Parquet `nominal_fps` and `inferred_offset_s`.** Recommend dropping `nominal_fps` for new takes (the CSV is authoritative) and keeping `timing_method` and the offset as run provenance.
12. **`recording_types` and `notes`** (freemocap-ui schema). Recommend calibration/mocap purpose in the manifest (take-level, set at capture). `notes` go in freemocap's recording info, with a privacy note.
13. **Wall-clock columns in CSV rows.** Recommend none; derive them from the take anchor.
14. **Mic name.** Recommend moving ASF's `# device=` line from the audio CSV into the info JSON `audio` block.
15. **Calibration controls (D11).** Recommend the TOML camera tables hold `controls_at_calibration` (the setup fact) and the info JSON holds the take's values. They are separate facts, so neither is a copy.

Not checked:
- Each skellycam-ui and freemocap-ui component file was not read (I grepped the slices and components).
- The Blender addon was not re-opened.
- I did not verify that PyAV can set the MKV Segment UID before the first frame, or the exact collision maths.

Risk: the change touches about 20 freemocap read sites. `<rec>_recording_info.json` copying the capture JSON is live today, so the "no copied fields" rule needs a freemocap change before new takes ship.
