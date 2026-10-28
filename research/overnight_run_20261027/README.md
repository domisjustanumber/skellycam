# Overnight run, 2026-10-27

On the evening of 2026-10-27 Dom asked for two unattended re-runs once the machine went idle after 23:00 local.
An idle watcher started them one after the other, and both finished without errors:

| Run | Workflow script (current location) | What it did | Outcome |
| --- | --- | --- | --- |
| `wf_ef322d5c-d99` | `research/usb_cameras/workflows/overnight_rerun_workflow.js` | Re-ran every USB camera test that needs no UAC, replug or reboot, on the C922, C930e and generic camera (Kiyo excluded). Six areas, each with an adversarial verifier. | 23:03 to 00:57 local, 13/13 agents. Summary: `research/usb_cameras/results/windows/Gerald/RERUN_20261027.md` |
| `wf_8fd1ec97-b0e` | `research/frame_ring_buffer/study_state/overnight_workflow.js` | Re-ran the frame ring buffer baseline on the idle machine, finished the remaining study stages, then filled and audited the report doc. | 00:57 to 07:32 local, 10/10 agents. Report: https://claude.ai/artifact/Cz1otkZxAjLTHfP1WeE9it |

A third, later workflow (`wf_264799ca-33d`) wrote three short summary docs from these results.

## Files

| File | What it is |
| --- | --- |
| `PLAN.md` | The step-by-step plan the session followed that night (as-run copy). |
| `OVERNIGHT_LOG.md` | The timestamped log the session appended to during the night (as-run copy). |
| `idle_watch.ps1` | Waits until after 23:00 for 15 min with no input and CPU below 25%, then prints IDLE (or TIMEOUT at 06:00). |
| `keep_display_awake.ps1` | Keeps the display on for the camera flash timing tests until a stop file appears. |
| `workflows/summary-reports-three-docs-wf_264799ca-33d.js` | The `wf_264799ca-33d` script that filled the MJPEG passthrough, USB camera tests and frame ring buffer summary docs, then fact-checked them. Its paths point to the current locations. |

## Historical paths

`PLAN.md` and `OVERNIGHT_LOG.md` are copies of the files as they were used that night. They were not edited when they were copied here:

- `S = C:\Users\Dom\AppData\Local\Temp\claude\...\scratchpad\overnight` is the session scratchpad where the originals were written and where the two `.ps1` scripts ran from. It may be gone.
- `<REPO>\research\usb_cameras\overnight_rerun_workflow.js` is now `research/usb_cameras/workflows/overnight_rerun_workflow.js`.
- `<REPO>\benchmarks\frame_pipeline\study_state\overnight_workflow.js` is now `research/frame_ring_buffer/study_state/overnight_workflow.js`.

Committed on the `dom/research` branch on 2026-10-28.
