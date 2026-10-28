# USB camera investigation — progress and resume notes

Last updated: 2026-10-28 ~04:55Z (night of 2026-10-27 local), after the unattended overnight rerun. Before that: 2026-10-25 ~18:45 local (EDT), when work was paused at Dom's request.

- **Report (Claude Doc):** https://claude.ai/artifact/WrpwyyMF7yU1amEB9pQYgE
- **Harness and results:** this directory (`research/usb_cameras/`), committed on branch `dom/research` on 2026-10-28 (commit dba82026; build outputs, venvs and binaries left out) (corrected 2026-10-28; was "uncommitted on branch `development`").
- **Test machine:** "Gerald", Windows 11.
- **Workflow scripts:** repo copies of all earlier workflow scripts are now in `research/usb_cameras/workflows/` (phase 1 `usb-camera-investigation-phase1-wf_85e88d5f-25b.js`, phase 2 `usb-camera-phase2-winusb-wf_15b731da-b8e.js`, `verify-timing-flash-wf_8bdc03a7-5c0.js`, `mjpeg-finish-and-rust-verify-wf_a3292d44-9ab.js`, and the overnight `overnight_rerun_workflow.js`). The originals are still under `C:\Users\Dom\.claude\projects\c--Users-Dom-GitHub-freemocap-skellycam\96d4d83a-4013-4e95-a9bd-1cfedc6522c8\workflows\scripts\`.

## Machine state (as of 2026-10-28 ~04:55Z, after the overnight rerun)

| Item | State |
| --- | --- |
| Camera drivers | All four on their normal drivers: parent `usbccgp`, video `usbvideo`. No camera is on WinUSB. Unchanged overnight. |
| Camera health | Read-only check at 2026-10-28T04:53Z: C922, C930e, generic and Kiyo functions 0x0180200A, parents 0x0180600A, problem 0, no DN_NEED_RESTART. Healthy at every check through the night. |
| C930e (046D:0843) | Restored from WinUSB at 22:16Z on 10-25. Its function IDs changed to `...&1&0000`, so its MF path is now `\\?\usb#vid_046d&pid_0843&mi_00#8&39dec205&1&0000#...`. Its ContainerId also changed (new v1 UUID). It is now MF index 6 / DShow index 2. |
| Generic 4C4A:4A55 | Re-arrived twice during the overnight run without explanation (LastArrivalDate 03:18:48Z and 04:12:37Z on 10-28), each time healthy with only the USB address changed. Watch for this. |
| Reboots | Two unattributed reboots on 10-27: power-off 00:01Z / boot 14:26Z, and an unexpected shutdown ~17:46Z / boot 18:39:40Z (`results/windows/Gerald/naming_rerun_20261027/boot_events_since_20261025.json`). |
| Camera controls | Left at manual exposure -7 (C930e reads back -5), WB 4500 K (nokhwa set 4000 K), AE priority 0 by the overnight agents. Not reverted. |
| Display | Primary now 1920x1080; the flash monitor (monitor 0) moved to x=1920, still 1440x2560 @ 59.95 Hz. |
| UVC metadata registry | `MetadataBufferSizeInKB0=5` set on the Kiyo, C922 and C930e interface keys. The C930e's new `&1&` keys were set at 22:30Z on 10-25. Confirmed overnight: every C922/C930e MF frame carries PTS/SCR; the generic camera (not set) has none. Revert: `timing/scripts/revert_uvc_metadata.ps1`, elevated. |
| Old C930e phantom devnodes | `...&0&0000` / `&0&0003` children and `7&7DCC7CE&0&1` parent are non-present. Harmless. |
| LogiTune / Razer Synapse | `LogiTuneAgent` was closed three times overnight and respawned within seconds each time via `LogiTuneUpdaterService` (service left alone). `RazerAppEngine` not running; `razer_elevation_service` running. |
| Rebuilt harness binaries | `mjpeg/.../mf_mjpeg_capture.exe` and `bandwidth/build/mf_multi_open.exe` were rebuilt with new options. The 10-25 binaries are backed up in the scratchpad of session 7c9d3345 (`C:\Users\Dom\AppData\Local\Temp\claude\c--Users-Dom-GitHub-freemocap-skellycam\7c9d3345-0e7f-4af6-bb14-20fd851edd1a\scratchpad\mf_mjpeg_capture_20261025.exe` and `...\scratchpad\orig_harness\mf_multi_open_20261025.exe`). |
| Rust | User-level rustup installed in `%USERPROFILE%\.cargo` (rustc 1.99.1). |
| Timers / agents | None scheduled or running. All overnight agents reported their child processes gone. |

**Hazards learned (also in Claude memory):**
- **Device restarts:** never restart devices programmatically. LogiTune vetoes it and leaves `DN_NEED_RESTART` (bit `0x100`), which makes MF fail with `MF_E_REBOOT_REQUIRED`. Ask Dom to replug instead.
- **Messaging workflow agents:** never SendMessage a running Workflow subagent; it spawns a duplicate instance.
- **Kiyo Pro:** it stops answering EP0 a few minutes after each plug-in. Every API then fails with `0x8007001F`. This is device/firmware, not our settings.
- **UAC:** Dom declines unannounced UAC prompts, so announce each one in chat first.

## Status by goal

| Goal | Doc section | Status |
| --- | --- | --- |
| 1 Native MJPEG | pending | Windows matrix re-run and adversarially verified on 20261027 (`results/windows/Gerald/mjpeg_rerun_20261027/`, `mjpeg/RESULTS.md`): MF native MJPG and PyAV dshow passthrough give byte-identical camera-native JPEG on all 3 in-scope cameras; nokhwa too; WinRT and OpenCV never return JPEG bytes. Harness consolidated. Doc section still to write; Kiyo, Linux and macOS unmeasured. |
| 2 Timing | written (needs corrections) | Phase 1 + 2 verified; 20261027 rerun reconfirms the C922 results. Doc needs updates: C930e manual exposure via MF is unreliable (refuted), C930e PTS step follows a frame-period mode, and the xHCI frame/QPC "residual 0 / causal" basis holds only ~2–3.5 s (weakened). |
| 3 Bandwidth | written (needs corrections) | usbvideo results re-run 20261027 for C922, C930e and generic: alt choice, alt 8/9 threshold and budget model hold. C922 1080p@5 rate is non-deterministic (5/15.8/30 fps). Generic 1080p fails strict JPEG decode. WinUSB phase 3 (C922, generic) still not run. |
| 4 Naming | written (needs corrections) | Windows reconfirmed 20261027 (46/46 claim checks), plus opportunistic reboot evidence and the C930e rollback identity change. Doc needs updates: MF/DShow indices are not stable (C930e MF 7→6, DShow 7→2; Kiyo MF 6→7, DShow 2→3), and the C930e's MF/DShow paths and ContainerId changed after its WinUSB rollback; the doc's "0.29–0.37 s" listing time includes `uv` start-up (in-process 0.095–0.102 s). (Status corrected 2026-10-28; was "written".) Controlled reboot, replug and port-move tests are still only drafted (`naming/win_stability_workflow.ps1`). |
| 5 Cross-platform | pending | Not written. Inputs are in the phase 1 and 2 results. |
| Summary, comparison matrix, open questions | pending | Not written. |

## Overnight rerun 20261027

Unattended rerun of every test that needs no admin rights, no human and no driver change, on 2026-10-28 03:03Z–~04:50Z (night of 10-27 local). Cameras: C922, C930e, generic 4C4A:4A55. The Kiyo was excluded. Six areas, each with a rerun agent and an adversarial verifier that re-ran key hardware tests.

- **Workflow script:** `workflows/overnight_rerun_workflow.js` (run `wf_ef322d5c-d99`; moved from `research/usb_cameras/overnight_rerun_workflow.js` on 2026-10-28). As-run plan and log: `research/overnight_run_20261027/`.

- **Consolidated report:** `results/windows/Gerald/RERUN_20261027.md` (claim → tonight → verdict tables, skipped tests, camera health, light/load attribution).
- **Structured output:** `results/agent_reports/rerun_20261027_reports_and_verifications.json`; journal `results/agent_reports/journal_wf_ef322d5c-d99.jsonl`.
- **Result dirs:** `naming_rerun_20261027/`, `mjpeg_rerun_20261027/` (+ `mjpeg_resummarized_20261025_data{,_b}/`, `mjpeg_adversarial_verify_20261028/`), `timing/rerun_20261027{,_verify}/`, `bw_concurrency_rerun_20261027/`, `bw_topology_rerun_20261027/`, `bw_rerun_20261027_analysis/`, `bw_adversarial_verify_20261028/`, `*/20261028T03*_rerun20261027*` for libusb/Rust (+ `verify_rust/20261028T034322Z_adversarial_rerun20261027/`, `uvc_capture_frame_qpc_only/20261028T035*Z_verifier_*`), `prior_art_rerun_20261027{,_adversarial_verify}/`. All under `results/windows/Gerald/`.

**Camera health:** all in-scope devnodes healthy at every check (0x0180200A / 0x0180600A, no DN_NEED_RESTART). No restarts, no elevation. The generic camera re-arrived twice without explanation (03:18:48Z, 04:12:37Z), healthy each time.

**Kiyo contact (correction):** the Kiyo was never streamed or opened via MF/DShow/libusb. But libusb/rawusb enumeration sends hub IOCTLs including GET_DESCRIPTOR(config) to it, and GStreamer ksvideosrc opens a handle on every KS filter before matching the name (3 runs). Its devnode stayed healthy. While it is excluded, skip ksvideosrc as well as SDL3, openpnp and `gst --list`.

**Goal 1 MJPEG status:** done on Windows for the 3 in-scope cameras.
- MF IMFSourceReader native MJPG (converters disabled): 100% valid, 30.00/30.05/25.76 fps, 0.7–2.2% of one core.
- PyAV dshow `vcodec=mjpeg`: full JPEG header SHA-1 identical to MF, so neither path re-encodes. Table fingerprints are stable across days.
- nokhwa MSMF and GStreamer mfvideosrc/ksvideosrc also give native JPEG.
- WinRT MJPG subtype: E_INVALIDARG. OpenCV MSMF and DSHOW never return JPEG bytes (decode costs 25–156% of a core).
- Generic camera 1080p frames fail strict libjpeg decode on every frame (387–1195 extraneous bytes before EOI); lenient decoders accept them, OpenCV warns.
- Remaining: Kiyo, Linux and macOS runs, the doc section.

**Changed or refuted (details in RERUN_20261027.md; none explained by low light or load):**
- C922 MJPEG 1080p@5 delivers 5.01, 15.76 or 30.0 fps at the same alt 5 (non-deterministic; ~1.17x headroom at 30 fps).
- C930e manual exposure set through MF before streaming is not reliably applied (1 of 5 valid -7 runs); reads back -5 after capture.
- C930e PTS 2x step follows a frame-period mode (998,400 vs ~997,230 STC ticks/frame); trigger unknown. Its 8–12 ms OS-timestamp error was 4.7 ms in the one valid short-state run on 20261027, so the error is probably tied to the period mode, but that rests on 1 run and is untested (corrected 2026-10-28; was "2x step and 8–12 ms OS-timestamp error follow a frame-period mode").
- xHCI frame/QPC IOCTL "residual 0" holds only ~2–3.5 s after START_TRACKING; over 20 s the mapping shifts up to -641 µs and returned QPC is non-causal in up to 208/396 samples. Re-check the phase-2 SCR-SOF→QPC agreement.
- Shared-hub loser with simultaneous start is a race; with a 2.5 s stagger the second camera always loses.
- OpenCV MSMF "0 frames" was a harness open-wait bug. OpenCV DSHOW raw "10 fps YUY2" depends on property order.
- MF capture metadata now present on C922/C930e (registry value set after 10-25), which moved the C922 arrival-minus-sample median from 16 to ~1 ms. The median is a beat-phase artifact anyway; report both modes.
- rawusb now lists all cameras (patched crate). MF/DShow/OpenCV indices reordered. C930e ContainerId changed after rollback.
- C930e dshow drift is about −1.5 to −1.8 ms/s (−4.5 was an outlier). Wallclock offset is per-session (30 → 36 ms).
- MJPEG process CPU is 1.3–2.3x the 10-25 values at low machine load, unexplained.
- Generic camera timing accuracy is unmeasured (the 1.7–1.9 ms figure is circular).

**Harness fixes (additive, defaults unchanged):** Kiyo exclusion and `--out-dir`/fresh-root options across naming, MJPEG, bandwidth and prior-art scripts, so reruns never overwrite cited results; OpenCV `--open-wait`; luma, machine CPU and DevNodeStatus recorded per capture; `mf_multi_open --save-dir/--arrivals/--list-match`; timing `--mf-glob`; new comparison scripts per area. Full list and still-open harness bugs in RERUN_20261027.md.

**Missed tests (could run unattended next time):** pyav-dshow-graphclock; MF-NV12/DSHOW-raw at 1080p and 3-camera; CPU repeat runs; isolated C930e+generic pair with stagger and `--arrivals`; C922 720p60; `uvc_capture_test --frame-qpc-only` > 3 s; `verify_grid_phase.py`; C930e exposure re-apply-after-start; brighter-scene generic timing; non-Kiyo legs of `kiyo_lens`; JPEG marker-layout check; unpatched rawusb; Docker libuvc build; offline alt-sweep reproductions.

**Still needs a human:** WinUSB phase 3; controlled reboot/replug/port-move naming tests; anything that needs the Kiyo unplugged (SDL3, openpnp, `gst --list`, ksvideosrc, libuvc example, `cv2.VideoCapture(index)` mapping); elevated Frame Server CPU and ETW; a LogiTune-free C930e test (needs the updater service stopped).

## Unfinished work and how to resume

### A. Goal 1 MJPEG consolidation (workflow `wf_a3292d44-9ab`)
- **Superseded 20261027:** the overnight MJPEG agent finished the harness consolidation and re-ran the full Windows matrix, and a verifier checked it (see "Overnight rerun 20261027" above and `mjpeg/RESULTS.md`). Do not resume `wf_a3292d44-9ab`. What remains for goal 1 is writing the doc section. The notes below are kept for history.
- `verify:rust` is DONE (cached). `finish:mjpeg` was stopped mid-run; its partial edits are on disk under `mjpeg/`. `verify:mjpeg` never ran.
- An unverified compile-only hand-back from an earlier instance is in `mjpeg/HANDBACK_earlier_instance.md`.
- Resume (all cameras must be on normal drivers):
  `Workflow({scriptPath: "C:\Users\Dom\.claude\projects\c--Users-Dom-GitHub-freemocap-skellycam\96d4d83a-4013-4e95-a9bd-1cfedc6522c8\workflows\scripts\mjpeg-finish-and-rust-verify-wf_a3292d44-9ab.js", resumeFromRunId: "wf_a3292d44-9ab"})`
  Resume only works in the same Claude session. In a new session, re-run that script file fresh (the finish:mjpeg prompt is self-contained) or hand its prompt to a new agent. A repo copy of the script is `workflows/mjpeg-finish-and-rust-verify-wf_a3292d44-9ab.js`.
- Phase 1's `verify:mjpeg` (workflow `wf_85e88d5f-25b`) is redundant; don't resume it.

### B. Phase 3: WinUSB coverage for the C922 and the generic 4C4A:4A55 camera
- **Stage 1** (generalized scripts, no admin) was partly done by an agent before it was stopped. Review these before use; they are unverified:
  - `libusb/winusb/{install_winusb.ps1, rollback_winusb.ps1, verify_winusb.ps1, run_elevated_winusb.ps1, winusb_common.ps1, selftest_winusb_common.ps1}`
  - `libusb/phase3_analyze.py`
  - The runner `libusb/phase3_windows.ps1` may not exist yet.
- **Requirements:**
  - Swap both cameras in one elevated call: one announced UAC prompt, then Dom replugs.
  - Rollback compares service/INF per function (MI_xx), because instance IDs change. After rollback Dom replugs again.
- **Coverage to run per camera:**
  - libuvc list/probe/stream and forced-alt sweep. The generic camera has a single alt (3069 B), so its sweep degenerates.
  - The python-libusb1 streamer, patched pyuvc, and Rust uvc_iso (libusb backend).
  - Strict JPEG decode (`bandwidth/verify/strict_jpeg_check.py`).
  - Pipe snapshots (`bandwidth/win_usb_topology.py --pipes-only`).
  - SCR/SOF-to-QPC timing (`--frame-qpc`).
- **Multi-camera cases:** generic on WinUSB alongside the C930e on usbvideo (same hub); C922 and generic both on libusb.
- Results go in `results/windows/Gerald/phase3_<camera>_*/`.
- After rollback, re-set `MetadataBufferSizeInKB0` on any new interface keys (`timing/scripts/enable_uvc_metadata.ps1 -Instances <new MI_00 id> -NoRestart`, elevated), then replug.

### C. Real-world driver-swap strategy (research, no hardware)
- Questions:
  - swap at app start and restore at close, or install once, or use a helper service;
  - UsbDk (libusb access without replacing the driver; does it support isochronous transfers?);
  - libusbK, Zadig/libwdi, or an INF that matches by hardware ID versus a per-instance install;
  - crash recovery UX;
  - whether a replug, a port move or a reboot restores the old driver.
- An agent started this and was stopped. Partial files: `driver_swap/inspect_driver_state.ps1`, `driver_swap/persistence_test.ps1`. `driver_swap/REPORT.md` is not written yet.
- Known facts:
  - WinUSB binding persisted across a same-port replug.
  - Rollback = `pnputil /remove-device /subtree` + `/scan-devices`, which gives new function instance IDs.
  - Serial-less cameras get a new instance per port, so moving ports probably falls back to usbvideo. Untested.

### D. Report sections still to write
- Goal 1, Goal 5, Summary, Comparison matrix, Open questions / tests for other machines.
- Optional chart for goal 3: delivered fps vs alt, from `results/windows/Gerald/phase2_bw_alt/summary.json`.

## Where results live
- **Phase 1** (naming, MJPEG, timing, bandwidth, rust, libusb, prior_art + verifiers): `results/windows/Gerald/{naming,timing,mjpeg_*,rust_*,bw_*,prior_art_*,winusb_install}/`.
  - Structured agent outputs: the workflow journals under `C:\Users\Dom\.claude\projects\c--Users-Dom-GitHub-freemocap-skellycam\96d4d83a-4013-4e95-a9bd-1cfedc6522c8\subagents\workflows\wf_85e88d5f-25b\journal.jsonl`.
  - Durable copies of every agent report, verification and workflow journal: `results/agent_reports/` (`phase1_reports_and_verifications.json`, `phase2_reports_and_verifications.json`, `journal_wf_*.jsonl`).
  - Raw MJPEG captures are in the session scratchpad and may be gone in a new session. The analyses in `results/` don't need them.
- **Timing verification:** `results/windows/Gerald/timing/flash_verify_*`, `timing/VERIFY_method.md`, `results/windows/Gerald/timing/kiyo_lens/`.
- **Phase 2** (C930e on WinUSB): `results/windows/Gerald/phase2_{bw_alt,bw_alt_verify,libusb_scr_timing,timing_verify,rust_uvc_iso,python_libusb,python_verify,pyuvc,naming_libusb}/`.
  - Journal: `...\subagents\workflows\wf_15b731da-b8e\journal.jsonl`.
- **Linux/macOS drafts, all unverified:**
  - `naming/linux_stability_workflow.sh`, `naming/macos_stability_workflow.sh`
  - `mjpeg/drafts/`
  - `timing/linux/run_linux_timing.sh`, `timing/macos/run_macos_timing.sh`
  - `bandwidth/linux/uvc_bw_probe.py`, `bandwidth/macos/avf_multi_open.py`
  - `libusb/linux/run_libuvc_linux.sh` (+ `70-skellycam-uvc.rules`), `libusb/macos/run_libusb_macos.sh`
  - `rust/platform/run_linux.sh`, `rust/platform/run_macos.sh`

## Key verified findings (one line each; details in the doc)
- **Windows MF/host timestamps** are quantized in 16 ms steps (~4.6 ms std). The C922 UVC PTS (via MF metadata) reaches the ~0.4–0.5 ms ground-truth floor. The C930e PTS is a synthetic counter; use its SCR/STC.
- **Rolling shutter** spans ~29–31 ms per frame height at 30 fps. C922 PTS sits near the end of exposure, not the start (tentative).
- **libusb on WinUSB:** unprivileged xHCI frame/QPC IOCTLs map SCR SOF to QPC causally (⚑ weakened 20261027: only for ~2–3.5 s after START_TRACKING; see the overnight rerun section). The SCR route and back-dated first-payload times agree to 46–66 µs (MAD). Cross-camera offset spread was 0.5–0.8 ms.
- **Bandwidth:** cameras always request the maximum alt (C930e 3072 B at 720p/1080p), and usbvideo grants it, so 1 camera per USB 2.0 link. An app-forced alt gives full-rate 720p at alt 5–7. Under-provisioning drops whole frames (0 corrupt in ~18k strictly decoded). The controller enforces admission (alt 8 pass / 9 fail next to the generic camera). Linux FIX_BANDWIDTH applies only to uncompressed formats, per kernel source; this conflicts with Dom's experience and is untested.
- **Naming:** only the C922 has a serial. Use the serial when it's usable and unique, else the port path (`naming/camera_identity.py`).
- **Libraries:**
  - libuvc builds on Windows with 3 shims, plus patch 0001 for PTS/SCR and alt override.
  - The pure-Python libusb1 streamer works (~4–8% of one core).
  - pyuvc 1.0.8 crashes on Windows.
  - Rust uvc_iso: the libusb backend is solid; rawusb is intermittent.
  - nusb has no isochronous transfers (PR #233 closed).
  - nokhwa gives native MJPEG on Windows.
