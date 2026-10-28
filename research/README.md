# Research

Studies and investigations that sit beside the skellycam package. Nothing here is imported by skellycam. Committed on the `dom/research` branch (2026-10-28) without build outputs, virtual environments or compiled binaries.

**Start with [REPORT.md](REPORT.md)**, a condensed report across all studies. Each study folder also has its own `REPORT.md` with the full findings, comparison tables and proposed next steps.

| Folder | What it is | Status (2026-10-28) | Read first | Claude Docs |
| --- | --- | --- | --- | --- |
| `usb_cameras/` | Low-cost UVC webcams: native MJPEG, capture timing, USB bandwidth, device naming, cross-platform. Test harnesses plus results from the Windows machine "Gerald". | In progress. Overnight rerun done 2026-10-27; goals 2–4 written in the report (2, 3 and 4 need corrections; corrected 2026-10-28, was "2 and 3"), goals 1 and 5 and the summary still to write; WinUSB phase 3 needs a human. | `usb_cameras/PROGRESS.md` | [USB camera report](https://claude.ai/artifact/WrpwyyMF7yU1amEB9pQYgE) · [MJPEG passthrough summary](https://claude.ai/artifact/5QePjWZ3RA8xovd8kQqo26) · [USB camera tests summary](https://claude.ai/artifact/7JPrCGRtZ59LpSj1qdum5E) |
| `frame_ring_buffer/` | How frames move from SkellyCam to FreeMoCap through the shared-memory ring buffer, with benchmarks, prototypes and a C++ comparison. Was `benchmarks/frame_pipeline/`. | Done. The map, verify and research stages finished on 2026-10-25; the benchmark (baseline re-run, prototypes, C++), recommend, critique, revision and report stages finished in the 2026-10-27 overnight run (corrected 2026-10-28; was "All stages finished in the 2026-10-27 overnight run"); report complete and audited. | `frame_ring_buffer/study_state/RESUME.md` | [Frame ring buffer report](https://claude.ai/artifact/Cz1otkZxAjLTHfP1WeE9it) · [Frame ring buffer summary](https://claude.ai/artifact/H1dJaFNr9cbuQD3XNU78fq) |
| `gige_vision/` | GigE Vision camera support with PTP sync: research notes, workflows, and a stand-alone hardware test suite (`hardware_tests/`). Was `plans/gige-vision/` and `skellycam/system/diagnostics/gige/`. | Paused 2026-10-25. Report 4 of 8 sections filled; skellycam backend not started. | `gige_vision/RESUME.md` | [GigE Vision report](https://claude.ai/artifact/SPKjXcBjS5kJmGwtbXGPWZ) |
| `arduino_sync/` | Plan for Arduino FSIN hardware sync (skellysync firmware, based on a review of MoCapSTR). Was `plans/arduino-sync-PLAN.md`. | Draft plan from 2026-10-25, not yet reviewed by a maintainer. | `arduino_sync/PLAN.md` | None (the plan is the Markdown file) |
| `overnight_run_20261027/` | Record of the 2026-10-27 unattended overnight run that re-ran the USB camera tests (`wf_ef322d5c-d99`) and finished the ring buffer study (`wf_8fd1ec97-b0e`). | Finished. | `overnight_run_20261027/README.md` | See the docs above |

Each study keeps the Workflow scripts that drove it in its own `workflows/` folder (the ring buffer's main scripts are in `frame_ring_buffer/study_state/`).

## Moved paths

On 2026-10-28 these folders were moved here from `benchmarks/frame_pipeline/`, `plans/` and `skellycam/system/diagnostics/gige/`. Guides, scripts and study-state files were updated to the new paths. Files under `results/` folders, `*.log` files, `*.jsonl` journals and other raw records keep the paths they were recorded with.
