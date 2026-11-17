# Work items 2026-11-13: freemocap phase 2, the tracking file, and the new recording format

Written for a fresh agent session that investigates these items, most likely working in the freemocap repo. The owner is "Dom". Use they/them for anyone not named. Each item is a question for Dom to decide or a piece of work to plan. Nothing here is decided unless it says so.

Paths:
- `<sc>` = `~\GitHub\freemocap\skellycam`, branch `dom/research` (research notes, plan, desk tests);
- `<sff>` = `~\GitHub\freemocap\skellyfileformat`, branch `main` (format spec and decision log);
- `<fmc>` = `~\GitHub\freemocap\freemocap`, branch `development` (read at 5632778a).

## 1. Rules for this work

- Spec and test list first, then implementation, each after Dom's approval. A decision is not a go-ahead to build.
- Pin every dependency, tool and CI action to an exact version (`==`, exact git revs), at least 14 days old.
- Research reports are Markdown files in `<sc>/research/`, never Claude Docs. Never commit rebuildable files.
- Ask Dom before every push or any action visible outside this machine. Commits use the GitHub noreply address, with no AI attribution in `<sff>`.
- Never print or publish Dom's email address.
- Say "Kiyo Pro", never a bare "Kiyo".
- Sub-agents: brief them read-only, limit their network use, ask for plain-text reports, then check their key claims in the source before relaying them. Do not use SendMessage on workflow agents.
- Use the `mattpocock-skills:grilling` skill to put decisions to Dom in rounds, each with a recommendation.

## 2. Read first

1. `<sc>/research/CAPTURE_AND_RECORDING_PLAN.md`: section 4 (phase 2 rows 2.1–2.8 and exit tests), section 3.1 (the contract with freemocap, which phase 2 reviews), section 6 (D2, D3, D6, D25, D26, D27). Row 2.4 still says "JPEG in MKV with a sidecar": that is obsolete; the format is now MCAP (D27).
2. `<sc>/research/skellycam_recording/docs/tracking_file_decisions_20261113.md`: the grilling decisions Q1–Q42 for the freemocap tracking file and the Lichtblick layout. They are not yet written as decision entries.
3. `<sff>/spec/SPEC.md` (draft v1) and `<sff>/decisions/open-work.md` (next step: spec draft v2). Accepted entries that matter here: DK8S, TDB5, 752H, MG7C, PV6S, D9N1, 5G42, T24G, WG08, W4PF, X1G6, 7K3C.
4. Desk-test evidence under `<sc>/research/skellycam_recording/recording_upgrade/results/`: `tracking_sync/` (Lichtblick sync-mode test, 2026-11-13), `lichtblick_check/`, `mcap_kill/`, `mcap_electron/`, `mcap_single_writer/`.
5. `<sc>/research/skellycam_recording/docs/spec_v1_review_20261113.md` and `mcap_check_20261113.md`.

## 3. Facts found on 2026-11-13 (checked in code; re-verify before relying on line numbers)

- **What the new format replaces.** Only skellycam's half of a recording folder: the MP4s, the timestamp CSVs and stats, the WAV and its JSON, the README. freemocap's posthoc outputs, the calibration TOML, annotated videos, `.blend` and the Blender addon's data are untouched.
- **Equal frame counts.** skellycam enforces lockstep and equal counts today (`<sc>/skellycam/core/timestamps/numpy_timestamps/process_and_save_recording_timestamps.py`), and freemocap posthoc refuses unequal counts (`<fmc>/freemocap/core/pipeline/posthoc/video_group_helper.py`, `_frame_count_mismatch_detail`). The new format allows gaps and per-camera timing.
- **Frame rate for filters.** Read from skellycam's multi-frame timestamp CSV or `*_stats.json` (`<fmc>/freemocap/core/tasks/mocap/mocap_helpers/recording_framerate.py`). New takes have no CSV.
- **Rotation.** Today skellycam rotates pixels before encoding, so old calibrations and 2D are in rotated space. New files store unrotated pixels plus `display_rotation`.
- **Root `.json` files.** freemocap writes and reads `tracker_schema.json` at the recording root (`<fmc>/freemocap/api/http/playback/playback_router.py`, posthoc_mocap_task.py); sample data also has `charuco_board_info.json` there. Lichtblick installs every `.json` in a dropped folder as a layout.
- **Recording info.** freemocap looks for `<rec>_recording_info.json` or `<rec>_info.json` at the root (video_group_helper.py).
- **Realtime saves.** Only `output_data/charuco_observations_realtime.pkl` on calibration takes (`<fmc>/freemocap/core/pipeline/realtime/charuco_recorder_node.py`), keyed by connection frame number and joined through the per-camera CSV.
- **Posthoc 2D is not saved at all today.**
- **Shared memory.** freemocap's realtime nodes get the full skellycam frame metadata but keep only frame number, camera id and rotation. The new format's arrival time is not in shared memory today.
- **Camera ids.** USB indices are not stable across driver changes (`<sc>/research/usb_cameras/REPORT.md` finding 23). freemocap matches calibration cameras to runtime ids with a heuristic fallback (`camera_id_resolution.py`).
- **Lichtblick v1.30.0** (source, commit fcfc7d5): opens a folder's files with `Promise.all`, so one file that fails to open may fail the whole take (not tested); every drop or import adds a new layout entry; `layoutUrl` replaces same-named layouts.

## 4. Open questions from the tracking-file grilling (round 11, not yet answered)

Recommendations are the main session's, not decisions.

| # | Question | Recommendation |
|---|---|---|
| Q43 | Where do the MCAPs and the layout go? | In `synchronized_videos/` under the recording folder: camera, audio and tracking MCAPs plus the layout; that is the folder users drop onto Lichtblick. freemocap's root files stay apart. The recording info JSON stays at the recording root (replaces Q15's "move it to a subfolder"). |
| Q44 | Do realtime CoM and XCoM go into storage? | Yes: `/tracking/<tracker>/com` (`foxglove.PointCloud`, mm), total CoM, segment CoMs and XCoM as rows named in `nodes`, NaN when absent. |
| Q45 | Does the calibration take's tracking file replace the realtime ChArUco pickle? | Yes, in phase 2: posthoc calibration reads the `charuco` tracker's 2D from the tracking MCAP and joins frames by the copied `log_time`. |
| Q46 | Does the calibration TOML stay the source of truth? | Yes: `foxglove.CameraCalibration` and transforms in the tracking file are display-only, derived from the TOML. New calibrations use stored (unrotated) pixel space; old rotated calibrations are converted. |
| Q47 | Park the remaining freemocap questions (section 5) as phase-2 work? | Yes. This document is that list. |

## 5. Phase-2 questions raised by the format comparison

1. **Frame grid for posthoc.** Who turns an MCAP take into the common frame grid that posthoc needs (the skellyfileformat reader, skellysync, or freemocap)? On which time: fitted, sample or arrival? How are gaps (breakpoints, `frame_gap` Log messages) handled? Relates to plan rows 2.2 and 2.7.
2. **Posthoc outputs.** Do posthoc 2D and 3D, CoM and reprojection error move into an MCAP (like the tracking file), or stay `.npy`/`.csv`/`.parquet`? Should posthoc start saving 2D?
3. **MP4 and Blender.** What replaces double-click playback and the Blender addon's video planes: an MP4 export from skellycam's converter, an MCAP reader in the addon, or both? The addon reads `synchronized_videos/*.mp4` and `output_data/mediapipe_*_3d_xyz.npy` (freemocap .venv `freemocap_blender_addon`).
4. **Diagnostics.** Do skellycam's per-frame lifecycle and duration columns and the stats survive anywhere (a debug sidecar, the info JSON, Log messages), or are they dropped?
5. **Filter frame rate.** Replace the CSV-based rate with the fitted `period_ps` or `nominal_rate` from the camera files.
6. **Root `.json` files.** Confirm Q43 removes the conflict; otherwise rename or move `tracker_schema.json` and `charuco_board_info.json`.
7. **freemocap's unused target layout** (`<fmc>/freemocap/system/recording_structure/recording_structure.py`): drop it, or align it with the MCAP take folder?
8. **Annotated video writer** (`video_node.py`) names its output after the source suffix; a `.mcap` source would break it. Plan row 2.4 (JPEG-only) must be restated for MCAP: what format do annotated videos use?
9. **3D frame consistency.** Realtime 3D is in the calibration world frame; posthoc may move the skeleton onto the floor when there is no ground plane. Should realtime and posthoc agree?
10. **Old recordings.** Design freemocap's reader for both old (MP4 + CSV) and new (MCAP) takes (D19, ADR-X1G6).
11. **File names** of the camera, audio and tracking MCAPs inside the take folder (the spec leaves names to the writer, ADR-DK8S item 12).

## 6. freemocap work that the tracking-file decisions imply (phase 2)

From `tracking_file_decisions_20261113.md`; spec part drafted in format 2.0 after core spec v2 passes gate 1 (Q5, Q20).
- **Arrival time in shared memory.** skellycam adds the arrival time (and sample time) to the shared-memory frame metadata, so freemocap can copy `log_time` exactly (Q8, Q20). This changes the plan's section 3.1 contract.
- **Take facts.** skellycam hands `take_uuid` and the take start facts to freemocap at record start, so the tracking file's `freemocap.recording` record matches the camera files (Q12).
- **Live writer.** freemocap writes storage channels live: raw and filtered 2D `PointCloud`s per camera (x, y, z, confidence, float64, NaN kept, stored-pixel coordinates), 3D points and rigid skeleton (mm), calibration and transforms, `freemocap.ParameterEvent` messages (Q9, Q10, Q22, Q24–Q27, Q31, Q38). Same writing rules as device files (Q6).
- **Post-take writer.** After the take, freemocap writes all display channels (per-frame `ImageAnnotations` with placeholders, per-camera 3D `SceneUpdate` re-stamped to each frame's arrival) from the camera files and its storage, then updates the layout (Q33, Q39, Q40).
- **Layout edits.** Turn on annotation topics, add a 3D panel, set `calibrationTopic`, rename the layout (e.g. `3 cameras + person`) (Q18, Q30, Q42).
- **Calibration.** Convert rotated calibrations to the stored image and add the 0.5 px shift for Lichtblick (Q31); match calibrations to cameras by `camera_key`, never by label (Q42, plan row 2.6).
- **Static facts.** Channel metadata keys named after NWB ndx-pose: `nodes`, `edges` (0-based), `source_software`, `source_software_version`, `scorer`, `confidence_definition` (Q37).

## 7. Plan phase-2 rows to restate for MCAP

Rows 2.1–2.8 in the plan's section 4. Restate each against the MCAP format and the decisions above: 2.1 (raw JPEG over the ring), 2.2 (timing and lockstep: slots on a time grid, `frame_status`), 2.3 (freemocap-ui canvas player), 2.4 (JPEG-only rule: was MKV, now MCAP), 2.5 (packaging: Python 3.13, OpenCV 5, relock), 2.6 (stable camera keys; now also Q42's `camera_key`), 2.7 (2D time interpolation; needs the A5 strobe rig), 2.8 (imported cameras with no sync; skellysync review of D-Q, D-FPS, D-HDR, D-DRIFT, D-AUDIO, D-PKG against MCAP is a separate session, see `<sc>/research/skellysync_jpeg/SCOPE.md`).

## 8. Desk tests still needed

- Lichtblick v1.30.0 with a take that has one unfinished (crashed) camera file: does the whole take fail to open?
- A skellycam layout (version 1) loads in v1.30.0 with no error (Q14), and opens by dropping the take folder.
- The overlay lead of about one display frame while playing (measured headless): check on a real display.
- The 3D calibration overlay with a real freemocap calibration and a ChArUco board (rotation direction and the 0.5 px shift are easy to get wrong silently).

## 9. Suggested order

1. Answer Q43–Q47 with Dom.
2. Grill section 5 items 1–3 first: they decide whether freemocap can run posthoc on MCAP takes at all.
3. Restate plan rows 2.1–2.8 for MCAP, then write freemocap's phase-2 spec and test list for Dom's review.
