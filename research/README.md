# Research

Studies and investigations that sit beside the skellycam package. Nothing here is imported by skellycam. Committed on the `dom/research` branch (2026-10-28) without build outputs, virtual environments or compiled binaries.

**Start with [REPORT.md](REPORT.md)**, a condensed report across all studies. Each study folder also has its own `REPORT.md` with the full findings, comparison tables and proposed next steps.

| Folder | What it is | Status (2026-10-28) | Read first | Docs |
| --- | --- | --- | --- | --- |
| `usb_cameras/` | Low-cost UVC webcams: native MJPEG, capture timing, USB bandwidth, device naming, cross-platform. Test harnesses plus results from the Windows machine "Gerald". | In progress. Overnight rerun done 2026-10-27; goals 2–4 written in the report (2, 3 and 4 need corrections; corrected 2026-10-28, was "2 and 3"), goals 1 and 5 and the summary still to write; WinUSB phase 3 needs a human. | `usb_cameras/PROGRESS.md` | [USB camera report](usb_cameras/docs/usb_camera_report.md) · [MJPEG passthrough summary](usb_cameras/docs/mjpeg_passthrough_summary.md) · [USB camera tests summary](usb_cameras/docs/usb_camera_tests_summary.md) |
| `frame_ring_buffer/` | How frames move from SkellyCam to FreeMoCap through the shared-memory ring buffer, with benchmarks, prototypes and a C++ comparison. Was `benchmarks/frame_pipeline/`. | Done. The map, verify and research stages finished on 2026-10-25; the benchmark (baseline re-run, prototypes, C++), recommend, critique, revision and report stages finished in the 2026-10-27 overnight run (corrected 2026-10-28; was "All stages finished in the 2026-10-27 overnight run"); report complete and audited. | `frame_ring_buffer/study_state/RESUME.md` | [Frame ring buffer report](frame_ring_buffer/docs/frame_ring_buffer_report.md) · [Frame ring buffer summary](frame_ring_buffer/docs/frame_ring_buffer_summary.md) |
| `gige_vision/` | GigE Vision camera support with PTP sync: research notes, workflows, and a stand-alone hardware test suite (`hardware_tests/`). Was `plans/gige-vision/` and `skellycam/system/diagnostics/gige/`. | Paused 2026-10-25. Report 4 of 8 sections filled; skellycam backend not started. | `gige_vision/RESUME.md` | [GigE Vision report](gige_vision/docs/gige_vision_report.md) |
| `arduino_sync/` | Plan for Arduino FSIN hardware sync (skellysync firmware, based on a review of MoCapSTR). Was `plans/arduino-sync-PLAN.md`. | Draft plan from 2026-10-25, not yet reviewed by a maintainer. | `arduino_sync/PLAN.md` | None (the plan is [PLAN.md](arduino_sync/PLAN.md)) |
| `overnight_run_20261027/` | Record of the 2026-10-27 unattended overnight run that re-ran the USB camera tests (`wf_ef322d5c-d99`) and finished the ring buffer study (`wf_8fd1ec97-b0e`). | Finished. | `overnight_run_20261027/README.md` | See the docs above |

Each study keeps the Workflow scripts that drove it in its own `workflows/` folder (the ring buffer's main scripts are in `frame_ring_buffer/study_state/`).

## Moved paths

On 2026-10-28 these folders were moved here from `benchmarks/frame_pipeline/`, `plans/` and `skellycam/system/diagnostics/gige/`. Guides, scripts and study-state files were updated to the new paths. Files under `results/` folders, `*.log` files, `*.jsonl` journals and other raw records keep the paths they were recorded with.

The path-fix workflow's own result is in [moved_paths_20261028/](moved_paths_20261028/).

### Temp scratchpads (deleted 2026-10-28)

Earlier sessions worked in temp folders named `%LOCALAPPDATA%/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/<session>/scratchpad/`. Many raw records still cite those paths. Before the folders were deleted, everything the research needs from them was copied here. Build trees, venvs and third-party clones and downloads were not kept. Two sets of raw captures with room images, the C930e/C922 flash-run `.mjpeg` files and the generic camera's strict-decode-failing frames, are kept outside git in `C:/Users/Dom/Documents/skellycam-raw/` with mirrored paths.

| Session | Study | Where its kept files are now |
| --- | --- | --- |
| `ad23e4da` | frame ring buffer, 2026-10-25 | `frame_ring_buffer/study_state/scratchpad_evidence_20261025/` (paths cited in `study_state/*.json` map to this folder) |
| `7c9d3345` | USB rerun prep, ring buffer overnight run | verifier work and driver logs under `usb_cameras/results/windows/Gerald/` (`naming_verify_20261027/`, `*_adversarial_verify_*/`, `mjpeg_rerun_20261027/drivers/`, `timing/rerun_20261027/tools/`), `usb_cameras/bandwidth/orig_20261025/`, `usb_cameras/naming/orig_20261025/`, `frame_ring_buffer/revision/pre_edit_scripts_20261028/`, workflow results in `overnight_run_20261027/workflows/` |
| `96d4d83a` | USB phases 1 and 2 | raw run text under `usb_cameras/results/windows/Gerald/` (`phase2_bw_alt/raw/`, `phase2_bw_alt_verify/raw/`, `verifier_20261025/`, `naming/verifier_20261025/`, `verify_rust/phase1_verifier_20261025/`, `timing/flash_run2_expseries_capture/`), `usb_cameras/bandwidth/phase2_hold_scripts/` |
| `f77e9c4e` | GigE Vision | `gige_vision/scratch/` (digests, notes, packet captures) |
| `a9b9d5dd` | Arduino sync | `arduino_sync/research/` (with `SOURCES.md` for what was not kept) |
