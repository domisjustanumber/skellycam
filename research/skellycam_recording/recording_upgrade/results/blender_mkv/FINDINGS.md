# DT-B1: Blender 5.2 and per-camera MJPEG MKV (2026-11-13)

Desk test DT-B1 from `docs/spec_v0_revival_tracking_sidecars_20261113.md`. freemocap itself was not tested (Dom, 11-13: our reader will be implemented in freemocap).

## Result

**Index (constant-rate) PTS: pass.** For all 4 files, all three Blender loaders report the true frame count, and 20 of 20 rendered frames are the expected frame.

**Real (capture-time) PTS: fail.** Three of the four files report 888 frames when they hold 891, 831 or 874. Of 20 rendered frames, 11 are the wrong frame, including frame 2 repeating frame 1 in the c922 file. This matches the OpenCV result in GF02 (EVIDENCE_INDEX.md:54).

| File (GF02 Part A, `mkv_fp`) | Packets | `images.load` size, frame_duration | `movieclips.load` frames @ fps | VSE strip frames @ fps | Identity (5 frames) |
|---|---|---|---|---|---|
| c930e_full index | 891 | 1280×720, 891 | 891 @ 30 | 891 @ 30 | 5/5 |
| gap60 index | 831 | 1280×720, 831 | 831 @ 30 | 831 @ 30 | 5/5 |
| drop50 index | 874 | 1280×720, 874 | 874 @ 30 | 874 @ 30 | 5/5 |
| c922_full index | 893 | 1280×720, 893 | 893 @ 30 | 893 @ 30 | 5/5 |
| c930e_full real | 891 | 1280×720, 888 | 888 @ 30 | 888 @ 30 | 2/5 |
| gap60 real | 831 | 1280×720, 888 | 888 @ 30 | 888 @ 30 | 2/5 |
| drop50 real | 874 | 1280×720, 888 | 888 @ 30 | 888 @ 30 | 2/5 |
| c922_full real | 893 | 1280×720, 893 | 893 @ 30 | 893 @ 30 | 3/5 |

Details for the index files:
- Rendered Blender frames differ from PyAV 19.0.2's decode of the expected packet by a mean of 0.40–0.64 levels (0–255 scale).
- The next-closest packet within ±3 is at least 1.98× further away (the "margin"). It is lowest on each file's last frame.

Raw data: `DTB1_result.json`.

## Method

- Blender 5.2.3 LTS (build e13b728c6880), installed at `C:\Program Files\Blender Foundation\Blender 5.2`. freemocap's tests use `blender='5.2'` (freemocap `upstream/development-streaming` tests/test_blender_preparation.py:61).
  - Blender's FFmpeg: avformat 62.12.100, avcodec 62.28.100.
  - Run with `-b --factory-startup` and no add-ons.
- Inputs: GF02 Part A clean-closed MKVs, as written by PyAV 19.0.2 (MJPEG passthrough, 1280×720, flush_packets).
  - Index PTS are at 1/30. Real PTS are the captured times, at 1/1e6.
  - They are in `Documents/skellycam-raw/.../GF02/partA`. How they were made is in `results/crash_resilience/gapfill/GF02_NOTES.md`.
- Loaders: the two calls the freemocap addon makes, plus a VSE strip. The addon is at the commit freemocap dev-streaming locks, 73e1b3e.
  - `bpy.data.images.load` (the addon's `parquet_scene.py:167`);
  - `bpy.data.movieclips.load` (`add_capture_cameras.py:207`);
  - a VSE movie strip.
- Identity check:
  - The VSE strip was rendered to PNG at frames {1, 2, N/2, N−1, N}, with the Standard view transform and the scene at 30 fps.
  - Each PNG was matched by mean absolute RGB difference against PyAV decodes of packets f−1±3. A pass means the closest packet is f−1.
- Scripts: `scripts/blender_mkv/dtb1_blender.py` (runs inside Blender) and `dtb1_compare.py` (driver). Run with `uv run --script research/skellycam_recording/recording_upgrade/scripts/blender_mkv/dtb1_compare.py <work_dir>`. The renders stay in the work dir, since they can be rebuilt.

## Not covered

- **Pixel identity** was checked only through the VSE strip. For `images.load` (the image-texture path the addon uses) and `movieclips.load`, only size, frame count and fps were checked.
- **The addon was not run** on an `.mkv` take. That is DT-B3, and it needs the addon's `.mp4` filters patched (`parquet_scene.py:161,165`; `add_capture_cameras.py:142`).
- **Scene fps different from file fps**, repeated (filled) frames, and files from killed or recovered recordings were not tested (DT-B2).
- **Rotation metadata** was not tested. Dom chose sensor orientation on 11-13, so the addon would have to rotate the plane itself. That is DT-B4.
- **Blender versions other than 5.2.3** were not tested.

## Consequence for the spec

- Blender needs the MKV PTS to count frames (SFF-104 in spec v0 rev 2), the same as OpenCV.
- With index PTS the MKV time is not capture time, so true times must live in the `.skvt` timing sidecar.
- Any gap is squeezed out of the Blender timeline unless the frame grid is filled before export.
