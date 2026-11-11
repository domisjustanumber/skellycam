# GF08 notes (2026-11-10)

Gap-fill for G9: a multi-camera master-clock player that picks frames by capture timestamp. Functional only; no timing recorded. Full write-up: `GF08_ts_sync.md`.

- What ran: 4 cameras (real c930e/c922 720p timestamps on one shared clock, with late start, drops, gaps and early end); 456 fixed ticks; rules PREV and NEAREST; 3 paths (camera JPEG bytes in MKV, barcoded JPEG in MKV, h264_nvenc all-intra at target A in MP4); E35.7.5 and E45.2.3.
- measured: 0 mismatches in all 48 path × rule × Electron × camera cells (`GF08_ts_sync.json` → `mismatch_table`).
- measured: the existing harness helpers `floorIdx` / `nearestIdx` have no "none" result. They also differ from the integer rules at 1 ns before a frame (tolerance) and on exact ties (float) (`harness_helpers`).
- measured, offline: frame-index sync and container-pts selection do not reproduce the timestamp rule (`offline`).
- Encoder: NVENC opened, so there was no libx264 fallback (`GF08_generation.json` → `cameras.*.files.h264.encoder`).
- Harness: `scripts/chromium_sync_scrub/gapfill/GF08/harness/` is a copy with `test=tssync` added. The shared harness was not edited.
- Media: under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/chromium_sync_scrub/gapfill/GF08/` (523 MB per `du -sh`, rebuildable with `gen_gf08.py`).
- Rebuildable, do not commit: `GF08_ts_sync.json` (1.4 MB, raw rows), `GF08_ticks.json`, `GF08_sidecars.json`.
