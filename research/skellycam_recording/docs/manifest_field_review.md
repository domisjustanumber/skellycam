# Recording manifest: a field-by-field review

2026-11-12. Dom's rule: *if a synced recording in the new format cannot be opened or played without the JSON manifest, the manifest is part of skellyfileformat and its spec, covering only the fields the new format needs; legacy stays in skellycam.* This review checks every manifest field against that rule. Builds on `recording_folder_files.md` (same folder).

*Written by a sub-agent (read-only; local files only; one local Python check); saved by the main session. Before saving, the main session checked these claims against the code: rotation is baked into the pixels with `cv2.rotate` (`video_recorder.py:91-95`); `camera_id` is the first 2 bytes of a SHA-256 (`detect_cameras_devices.py:53-54`); `unix_timestamp_local` is the same epoch value as `unix_timestamp_utc` (`full_timestamp.py:60-61`); the plan records PortAudio's clock as QPC, the video sidecar's timebase (plan §2.8, [M]).*

**Labels:** [C] code or doc read (file:line), [I] inferred, [NV] not verified, [M] measured in an existing result file. Paths: `sc` = `skellycam-phase1` (upstream `main`, 7d06ba2e1); `sfn26` = `git show upstream/sfn26:` (f486d3882); `fm` = freemocap `development`; `plan` = `research/CAPTURE_AND_RECORDING_PLAN.md` rev 3.8.

## 0. Short answer
**No manifest is needed to open or play a synced new-format recording, if the spec adds a few header fields.** By Dom's rule the manifest then stays out of skellyfileformat. The recording info JSON stays a skellycam file (skellycam's own spec): a convenience index, skellycam's settings and the freemocap contract.

- **Finding and binding files:** a folder scan finds conforming MKV/MKA files; the Segment UID in each sidecar header binds the sidecar to its file (already planned: plan row 1.5, §2.7 [C]).
- **Shared time base:** arrival and fitted times are host-clock ns (QPC on Windows), the same clock for every camera and for PortAudio (plan §2.8 [C]), so fitted times compare across cameras with no recording-level data [I].
- **The only display need with no source today is rotation:** passthrough JPEGs will be stored unrotated, while today's writer bakes rotation into the pixels (`sc video_recorder.py:52, 92-95` [C]). The recording-upgrade summary already says "record the rotation in the sidecar" (`EXECUTIVE_SUMMARY.md:62` [C], untested).

**What the spec must guarantee instead of a manifest** (new header requirements; ADR-69YS lists only `header_size` and `n_records` today):

MUST:
1. Segment UID of the file's final bytes (decided, ADR-77Z3 §4).
2. Format version u16 ×3 and the writer string (decided, ADR-M4DF).
3. `camera_label`: the short camera id in today's file name; freemocap's key.
4. `display_rotation` ∈ {0, 90, 180, 270}; skellysync also writes `rotation_applied` for rotation it bakes in (`SCOPE.md:172` [C]).
5. Nominal rate as a rational (skellysync already plans it, `SCOPE.md:220` [C]).
6. A `time_base` kind: host monotonic clock, or a synthetic aligned timeline (skellysync). Files of one take that say "host" MUST share one clock.
7. A discovery rule: file and attachment names (S6), the separate sidecar's name, and "embedded wins over separate".

SHOULD (robustness, not playability):
8. `take_uuid`, identical in every camera sidecar and the `.skau` of one take; replaces `recording_uuid`; lets a reader ignore stale files (freemocap warns about these today, `fm video_group_helper.py:406-420` [C]).
9. `group_size`, so a reader can tell a camera file is missing.
10. A take anchor `{take_start_host_ns, take_start_utc_ns, utc_offset_min}`, identical in all files of the take; replaces `recording_start_timestamp`; gives a stable t0 and the wall-clock start.
11. A stable camera key, stored hashed (§C).

Items 1–7 make a recording playable; 8–11 make it robust against stale files, a missing camera, and "when was this recorded".

## A. What the canvas player (row 1.9) needs
| Need | From the files, no manifest | Manifest needed? |
|---|---|---|
| Which files make up the recording | Folder scan for `*.mkv`/`*.mka` with a skellyfileformat sidecar (3 range reads each, plan §2.7 [C]); skellycam's player already scans and parses names (`sc playback_router.py:362-389` [C]); robust with `take_uuid` (8) | No |
| Which camera each file is | Header `camera_label` (3); file name `{rec}.id-{id}.idx-{idx}` (`sc parse_video_filename.py:12-15` [C]) keeps a copy for people and freemocap | No |
| Binding sidecar ↔ MKV | Embedded = bound; header UID = MKV SegmentUID guards against a remux; separate sidecar found by its spec name and checked the same way (row 1.9 [C]). A manifest UID adds no check | No |
| Shared time base | Host ns for every camera and the `.skau`; `time_base` (6) states it; t0 = `take_start_host_ns` (10) or the minimum first fitted time [I]. Multi-PC rigs need clock-domain alignment (future) | No |
| Audio pairing | `<rec>.audio.mka`, its `.skau` header (UID, same clock), `take_uuid` | No |
| Rotation | Header `display_rotation` (4); Matroska `ProjectionPoseRoll` could hold a copy for VLC/ffmpeg [NV] | No, but the field is missing today |
| Display name | `camera_label`; a friendlier name optional (Matroska track `Name` or a header string); user renames belong in skellycam's JSON | No |
| Order | Sort by `camera_label`; optional header `group_position`; freemocap orders by file-name `idx` (`fm video_group_helper.py:422-423` [C]) | No |
| Wall-clock start | Take anchor (10). Today `FullTimestamp` is taken when `RecordingInfo` is constructed (`sc recording_info.py:24` [C]), not at the first frame | No |
| Resolution, frame count, duration | JPEG SOF or Matroska PixelWidth/Height; header `n_records` | No (derive) |
| Nominal rate, timecode | Header (5); Matroska DefaultDuration a consistent copy | No |
| Crashed recording | The separate sidecar header carries the same fields | No |

What only a recording-level file gives is convenience: a fast browser that need not open every MKV, user-edited names, skellycam's settings, the freemocap `videos` map — all skellycam-only. skellysync writes the format without an info JSON; its group sync record JSON (`SCOPE.md:221-225` [C]) is skellysync-only.

## B. Every field
Facts for the whole table: nothing reads the info JSON file in skellycam `main` or skellycam-ui (grep [C]); freemocap reads only `videos` from it (`fm video_group_helper.py:539-561`, read at :559 [C]); "API" readers below use the in-memory object, not the file.

| Field | Purpose | Readers | Needed to play? | Verdict | Where | Notes |
|---|---|---|---|---|---|---|
| `recording_name` | Recording name | File: none. API: freemocap, ~38 uses [C] | No | derive (an echo in skellycam's JSON is fine) | Folder name / file stem | |
| `recording_directory` | Absolute parent path | File: none. API: `fm calibration_router.py:58,112` [C] | No | **drop from the file**; keep in the Python model, excluded from the dump | — | Local user path in a shared file (§C); also leaks via `fm posthoc_calibration_task.py:146` (`model_dump()` into calibration TOML) [C] |
| `recording_uuid` | Take id | File: none. API: `fm charuco_recorder_node.py:217` writes it into a pickle, never read back [C] | SHOULD (membership) | move to header as `take_uuid` (video + `.skau`) | Header authoritative; JSON may echo | freemocap builds fresh `RecordingInfo` objects from paths (`calibration_router.py:58`, `video_node.py:635` [C]), each with a new random UUID |
| `mic_device_index` | PortAudio index | File: none. Live: `sc camera_group.py:198-205` [C] | No | drop (legacy-only) | — | Not stable; rate and channels are in FLAC STREAMINFO; device name/host API optional in `.skau` as diagnostics |
| `rst.unix_timestamp_utc` + `rst.perf_counter_ns` | Wall clock ↔ host clock pair | None | Display | move to header take anchor | Header | Two clocks read one after the other: small skew (`full_timestamp.py:75-76` [C]) |
| `rst.unix_timestamp_local` | Meant as local time | None | No | drop | — | Equals the UTC value (checked) |
| `rst.local_time_zone` | IANA zone name | None | Local display | header `utc_offset_min` (SHOULD); zone name skellycam-only, optional | Header / JSON | Reveals a region (§C) |
| `rst.*_isoformat` ×2, `human_friendly_*` ×2 | Strings | None | No | derive | — | |
| `rst.day_of_week`, `calendar_week`, `day_of_year`, `is_leap_year` | Calendar values | None | No | derive | — | |
| `camera_configs` key = `camera_id` | Short camera id: display, freemocap key, `id-` in names, CSV names | Name parsing in both repos; `fm video_group_helper.py:425` [C] | **Yes** (identity) | **SPEC-required in header** as `camera_label` | Header authoritative; file name, JSON keys and CSV names consistent copies | 16-bit truncated SHA-256 of the device path (`sc detect_cameras_devices.py:44-54` [C]): ~0.2 % collision chance at 16 cameras [I, arithmetic]; a dict keyed by id would silently merge two cameras [I] |
| `camera_index` | OS enumeration index | File name `idx-`; freemocap orders by it (`video_group_helper.py:406-423`) [C] | Order only | skellycam-only (keep in file name for the contract); optional header `group_position` | File name / JSON | Not stable across sessions |
| `camera_name` | Device friendly name (`skellycam-ui cameras-types.ts:124-131` [C]) | None (file) | Nice to have | skellycam-only, or optional header string / Matroska track `Name` | JSON | Can contain a person's name (§C) |
| `use_this_camera` | Runtime flag | None | No | drop | — | |
| `resolution.{width,height}` | Requested size | None | Derivable | derive | — | Pre-rotation size |
| `color_channels` | Always 3 | None | No | drop | — | |
| `pixel_format` | `"RGB"` placeholder with a TODO (`camera_config.py:90-92` [C]) | None | No | drop | — | Misleading; the real source format belongs in the header encoder/source field (row 1.5) |
| `exposure_mode`, `exposure` | Settings | None | No | skellycam-only, with the full locked control set (D10–D12, D14) | skellycam JSON (O2) | Units change from OpenCV log2 to MF 100 ns; skellycam's spec must say which |
| `framerate` | Requested rate; −1 = camera default (`camera_config.py:26,108` [C]) | None | Nominal rate needed | move to header as a nominal-rate rational (SPEC); requested value skellycam-only | Header (DefaultDuration consistent) | |
| `rotation` | Rotation to apply; baked into pixels today (`video_recorder.py:91-95` [C]) | None (file) | **Yes**, once frames are unrotated | **SPEC-required in header** (`display_rotation`) | Header authoritative; optional JSON echo; ProjectionPoseRoll possible [NV] | Changes what freemocap sees (§D, O3) |
| `capture_fourcc` | Requested capture format | None | No | skellycam-only, superseded by the header source/encoder field | JSON | |
| `writer_fourcc` | Writer codec; picks the extension (`camera_config.py:182-187`, `recording_info.py:88-89` [C]) | None | No | legacy-only | — | JPEG-only rule fixes the codec |
| sfn26 `videos` | camera_id → file name relative to `sv/` (`sfn26 recording_info.py:86-91`) | `sfn26 playback_router.py:303-310`; `fm video_group_helper.py:559` [C] | No (a scan works) | skellycam-only, freemocap contract; keep writing | skellycam JSON | Base is `sv/`; keep as is, freemocap resolves it against `videos_dir` (`video_group_helper.py:490-496` [C]) |
| sfn26 `camera_timing` | camera_id → CSV path relative to the recording (`:92-96`) | `sfn26 recording_timing_reader.py:18-24` → `playback_router.py:309` [C] | No (new player uses sidecar fitted times, ADR-0YV1) | skellycam-only; legacy-only for playback | skellycam JSON | Works around the stem-match bug in `recording_folder_files.md` |
| sfn26 `multiframe_timing` | Multi-frame CSV path (`:97`) | `sfn26 recording_statistics.py:13` [C] | No | skellycam-only / derive | skellycam JSON | |
| sfn26 `read_recording_field` | Globs `*_info.json`, raises on conflict (`recording_metadata.py:16, 26-27`) [C] | — | — | change to the exact `<rec>_info.json` | — | The glob also matches freemocap's planned `<rec>_recording_info.json` (`fm recording_structure.py:110` [C]) |
| sfn26 `VideoAssociations` checks | Path safety (relative, no `..`, one owner per file) | — | — | keep, in skellycam's spec | — | |
| S8 per-camera MKV path | Index | Planned | No | skellycam-only; same as `videos`, no second map | skellycam JSON | |
| S8 per-camera sidecar path | Index | Planned | No | **drop** | — | Goes stale: D16 deletes the separate sidecar after the embed; the separate sidecar's name is fixed by spec S6 |
| S8 stable camera key | Device identity (calibration match, D14 device cache) | Planned | Not for play | move to header (hashed, §C); JSON echo optional | Header | Also row 2.6 (key in file names, phase 2) |
| S8 Segment UID | Binding | Planned | Binding uses the header copy | **drop** from the manifest | MKV's own SegmentUID authoritative; header copy must match | Goes stale after a remux or crash recovery (plan §2.7 [C]) |

**Duplicated facts and the authoritative copy:** camera id → header (new format), file name (legacy), writer keeps all copies consistent; Segment UID → the MKV's own SegmentUID (header copy binds the sidecar; nothing else stores it); camera key → header; rotation and nominal rate → header (container copies consistent, JSON echo optional); take id and start → header. Plan row 1.7 says recovery rebuilds the info JSON from the sidecar (`plan:270` [C]), so every JSON fact must be derivable from the files or written early (O2).

## Options
**O1. Manifest in the spec?**
- (a) **No manifest; self-describing headers (items 1–11). Recommended.** Single source of truth; skellysync and the converter need no JSON; a copied or partial folder still plays.
- (b) A small spec manifest `<rec>.sff.json` (version, `take_uuid`, `files[]`): membership and missing-file detection without header fields, but it duplicates the headers, every producer and crash recovery must write it, it goes stale on rename/delete/remux, and it is one more versioned artifact.
- (c) A spec object inside skellycam's JSON: two owners of one file.
- Amend ADR-83Y4 to (a): the info JSON stays a skellycam-only index; drop S8's sidecar-path and UID entries.

**O2. Where skellycam's per-camera settings go** (locked at start values, D10–D11, so known before the first frame):
- (i) **Recommended for phase 1:** write `<rec>_info.json` at record start (atomic replace) and update it at finalisation; survives a crash; a lone copied MKV loses its settings. Change row 1.7 from "rebuild" to "update".
- (ii) Matroska Tags written with the header: travel with the file, visible to ffprobe; [NV] whether PyAV/FFmpeg place Tags before the clusters and whether the appender leaves them intact. Consider later.
- (iii) An opaque writer-extension block in the sidecar header: the spec would define its framing, coupling skellycam data to format bytes.

**O3. Rotation.**
- (i) **Recommended:** store frames unrotated with `display_rotation` in the header. Free to write, but every consumer must apply it (canvas player, freemocap posthoc, other OpenCV users). Risk [I]: freemocap's realtime calibration cache (observations on rotated ring frames) could disagree with posthoc reads of unrotated video. Add an orientation clause to the §3.1 freemocap contract and test it.
- (ii) Bake it in with a lossless JPEG transform when rotation ≠ 0: 2.0–2.2 ms/frame at 720p, 6.8–8.9 ms at 1080p [M] (`EVIDENCE_INDEX.md:59`); partial-MCU edges (1080 is not a multiple of 16), TJERR_WARNING handling (`EVIDENCE_INDEX.md:71`).
- Either way Dom must decide this; the plan does not cover it today.

**O4. Camera key form.**
- (i) Raw serial or port path.
- (ii) **Recommended in files:** 64-bit truncated SHA-256 of a kind-tagged string over vid, pid and serial (or the port path). Stable across machines, hides the raw serial from casual view; short serials could be brute-forced, so it is pseudonymous, not anonymous. Raw values only in skellycam's local device cache. Keep `camera_id` as the short label.
- (iii) HMAC with a per-installation secret: unlinkable across users, but the same camera gets a different key on another machine.

## C. Privacy and portability
- `recording_directory`: an absolute path containing the OS user name. Stop writing it; resolve paths from the JSON's own location. sfn26's new fields are already relative, with different bases (`videos` → `sv/`; timing paths → the recording folder). freemocap copies the path into calibration TOML via `model_dump()` (`posthoc_calibration_task.py:146` [C]) — for the freemocap session to fix.
- `camera_index`, `mic_device_index`: not private, meaningless after the recording. Drop or skellycam-only.
- Serial numbers as keys link recordings: store hashed (O4); hash the port path too, for a uniform key.
- Device names can contain a person's name (phone continuity camera, Bluetooth headset) [I]: optional, never spec-required.
- Time-zone name reveals a region: the header stores only `utc_offset_min`.
- skellysync source file name (`SCOPE.md:220`): basename only, never a full path.

## D. freemocap compatibility (§3.1 fixed; freemocap keeps its pin until phase 2, D3)
| freemocap read | Change | How to keep it working |
|---|---|---|
| Info JSON `videos` (`video_group_helper.py:559`) | None; skellycam writes `videos` (main does not today, sfn26 does) | Same shape, relative to `sv/`; `.mkv` already in `VIDEO_EXTENSIONS` in both repos (`sc parse_video_filename.py:18`, `fm playback_router.py:47` [C]) |
| CSV `recording_frame_number`, `connection_frame_number` (`video_node.py:653-654`), `from_previous.framerate.hz` (`recording_framerate.py:39,82`) | None; CSVs built from the sidecar at finalisation, columns only added (row 1.6) | Derived data; skellycam can regenerate them |
| Stats JSON `framerate_stats.median` (`recording_framerate.py:72`) | None | Keep writing it |
| `RecordingInfo(recording_name, recording_directory)`, path methods, `model_dump`, `recording_uuid` | Drop `recording_directory` from the serialized file only | Keep the Python fields and methods |
| `ParsedVideoFilename`, `try_extract_camera_info`, `VIDEO_EXTENSIONS` | sfn26 deletes `parse_video_filename.py` | If phase 1 adopts sfn26's `video_filename.py`, keep a shim |
| File-name pattern, `idx` ordering | None | Keep `{rec}.id-{id}.idx-{idx}.mkv` |
| **Video orientation** (new) | With O3(i), posthoc OpenCV reads give unrotated frames | Phase-2 freemocap applies the header rotation; add orientation to §3.1 |

Side note: freemocap's planned layout (`videos/synchronized/`, `<rec>_recording_info.json`, `fm recording_structure.py:85,110` [C]) differs from skellycam's (`synchronized_videos/`, `<rec>_info.json`).

## E. Versioning
- With O1(a): no manifest in the spec, so no manifest version; the format version stays in the sidecar headers (ADR-M4DF). skellycam's info JSON gets its own version (e.g. `"info_version": "2.0"`, same rule: `major.minor` of the skellycam release that last changed the JSON) and a `writer` string; absent = legacy JSON; separate so a JSON edit never bumps the format version.
- If a manifest were in the spec (O1(b)): `"skellyfileformat": {"major", "minor", "prerelease"}` with the same rules; every listed header must share the major; headers win for file contents; any manifest edit becomes a format change.

## F. Other findings
- `unix_timestamp_local` always equals `unix_timestamp_utc` (`full_timestamp.py:60-61` [C]; confirmed by one local run).
- `recording_start_timestamp` is taken at `RecordingInfo` construction, not the first frame (`sc recording_info.py:24` [C]).
- S8 as accepted lists a sidecar path that D16 makes stale.
- ADR-69YS does not yet list the header fields row 1.5 promises (format, encoder, key, UID), nor `async_depth` (row 1.4).
- sfn26 calls the timestamps CSV a "camera sidecar" (`recording_timing_reader.py:14` [C]); it will be confused with the format's sidecar.
