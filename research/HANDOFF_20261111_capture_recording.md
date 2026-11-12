# Handoff: camera capture and recording work (2026-11-11)

Start here in a new session. This covers everything from the 2026-11-11 planning session except the skellysync JPEG work, which has its own handoff at the top of [`skellysync_jpeg/SCOPE.md`](skellysync_jpeg/SCOPE.md).

**Status:** research and planning are done; none of the phase-1 test plans (TP1–TP4) has been run.

## 0. Update: second session, later on 2026-11-11 (read this first)
- **Overnight hardware run (11-11/12):** set up and smoke-tested; a fresh session starts it from [`usb_cameras/suite/windows/HANDOFF_OVERNIGHT_20261111.md`](usb_cameras/suite/windows/HANDOFF_OVERNIGHT_20261111.md). Its results answer the 1.3 backend, reliability, controls-lock, gain-rule and package-bump questions. The suite now enforces the Kiyo Pro dead rule. Morning write-up: `usb_cameras/docs/windows_results_20261112.md`.
- **Pre-existing failures on upstream `main`** (23 tests + 4 errors; `tsc` baseUrl): leave them for now (Dom, 11-11). Local uv is 0.13.7.
- **Decisions made** (plan rev 3.3, §6 D8–D12; all of §3 below is now resolved):
  - **D8: phase 1 is built on upstream `main`.** freemocap pins skellycam `branch = "main"` (`freemocap/pyproject.toml:43`), not `development-streaming`; the claim in §2 below was wrong.
  - **D9: no per-model gain caps.** The exposure step measures noise against gain on the live image (`usb_cameras/docs/exposure_gain_tradeoff.md` new §5.2a); T1 checks that rule instead of producing a cap table.
  - **D10/D11: white balance, zoom, pan, tilt and the image controls** (brightness, contrast, saturation, sharpness, gamma, backlight compensation) are **locked at whatever value the camera starts with**, not defaults. They're recorded with the config and the calibration. When a loaded calibration's values differ, skellycam lists the differences and asks the user. AWB is switched off, holding its value at start.
  - **D12: power-line frequency = local mains; AE priority = 0.**
- **Upstream `sfn26`** (Jon, 10-30 to 11-10) makes a Rust/OpenPNP backend (`skellycam-rust`) a required build dependency; its recorder pipes MJPEG to ffmpeg and re-encodes to libx264. Phase 1 doesn't build on it (plan §5). It's a merge risk if it reaches `main`.
- **Code: package 1.0 started** in worktree `C:/Users/Dom/GitHub/freemocap/skellycam-phase1`, branch `dom/capture-recording-phase1` (off `upstream/main` 06771043b; local only, not pushed):
  1. `2992e64f9` fixes test collection and ruff on `main` (a missing `import multiprocessing.queues`; TC001 `noqa`s as upstream did). **`main` itself then has 23 failing tests + 4 errors** (mostly skellylogs: `Logger.success` missing, websocket log queue not created). They're unrelated to 1.0; each bump is judged on new failures against that baseline.
  2. `7a9b82c9`: Python 3.13 floor, `av>=19.0.2`, `setproctitle>=1.3.8`, `opencv-contrib-python>=4.12,<6`, CI 3.13 on Linux/Windows/macOS.
  3. `528456dd`: runtime minors (fastapi 0.162, pydantic 2.14, uvicorn 0.54, …).
  4. `2e19444a`: numpy 2.5 + OpenCV 5.0 (coupled by the resolver); `.item()` fix in `timebase_mapping.py`; VFW/QT backends dropped from the diagnostics script.
  5. `d50129a50`: **every version pinned exactly (D13)**: Python 3.13.13 in `.python-version` and `requires-python`, all direct and dev dependencies `==`, skellylogs/skellypings by commit, setuptools 84.2.1.
  6. `777b123b6`: CI actions pinned to exact tags; uv 0.13.7, Node 20.20.2 / 22.23.5, Python 3.13.13 in CI. Local uv is still 0.11.8.
  7. `7d06ba2e1`: skellycam-ui packages pinned to their locked versions; `.npmrc` sets `save-exact`. The old lock had already installed TypeScript 6.0.3 despite the `~5.9.3` range. **`tsc --noEmit` fails on `main` before and after** (TS 6 deprecates `baseUrl` in `tsconfig.json`).
  - Every step: ruff clean, no new test failures. The PyAV libx264 writer was smoke-tested on PyAV 19.
  - **Polars is pinned at 1.43.0, which is yanked;** the polars 2 step must move it.
  - **Still to do in 1.0:** each bump now edits one exact pin. Majors one at a time (`numpydantic` 2, `pillow` 13, `polars` 2, `websockets` 17), the dev tools (ruff 0.17 may add lint findings), then skellycam-ui npm (Electron 45 and the other majors), then T-BUMP.
  - **T-BUMP's real recordings haven't been run.** The Kiyo Pro is wedged, and connecting cameras through skellycam could re-probe it, which isn't allowed. A replug is needed first; then one recording per major-bump commit.
- **Housekeeping:** the 74 untracked media files (10.2 MB) were moved to `C:/Users/Dom/Documents/skellycam-raw/` with mirrored paths, sha1 verified; that README has a new row.
- **Privacy: fixed 2026-11-11 by rewriting `dom/research` (force-pushed to the fork with Dom's approval: `55f851e4` → `0f689fc1`; no PRs reference the branch).**
  - Every commit after `development` was rewritten with git-filter-repo (`development` is unchanged). Removed from all history: the raw session transcript, all 57 webcam JPEGs, and the camera-consent dumps. Replaced in all history: Dom's email, the C922 serial (now `C922SN01`, in file names too), two peripheral serials, the MAC fragment in the ContainerIds, the real host LAN addresses, the skellycam telemetry IDs, the private claude.ai artifact IDs, and a chat app's name in the suite's process lists. A scan of all 18 commits finds none left. Every changed file equals the old file with the rules applied, and no JSON broke.
  - The removed files are in `C:/Users/Dom/Documents/skellycam-raw/` (mirrored paths; serial renamed there too). The full pre-rewrite branch is in `skellycam-raw/git-backup/dom-research-pre-privacy-20261111.bundle`, which holds the private data, so it must never be pushed.
  - `.gitignore` now keeps raw media, consent dumps, transcripts and the privacy report out of `research/`.
  - **Still open:** (1) the old commits stay reachable on GitHub by SHA until GitHub Support purges cached views (Dom's call whether to ask); (2) the suite writes the real C922 serial into new result paths on every run. A local pre-commit guard was proposed but blocked pending Dom's OK; until then, check new results before committing.
  - The review itself is `research/PRIVACY_REVIEW_20261111.md` (ignored, local only).

## 1. Read first
1. [`CAPTURE_AND_RECORDING_PLAN.md`](CAPTURE_AND_RECORDING_PLAN.md) (rev 3.2). It is the plan of record:
   - §1: Dom's rules;
   - §3.2: the phase-1 work packages 1.0–1.12;
   - §3.3: the test plans TP1–TP4 and the release checks;
   - §4: phase 2;
   - §6: the decisions.
2. This file's §3 (open decisions) and §6 (working rules).

## 2. What is decided (summary; the plan has the detail and evidence)
- **Format:**
  - JPEG only, I-frames only, everywhere. No H.264, HEVC, AV1 or VP9 anywhere, and no long-GOP.
  - JPEG frames in MKV with `flush_packets=1`; container timestamps are the frame index; a binary per-frame sidecar (capture times in integer ns, CRC, byte offset, size); overlays in a separate `.skov` sidecar.
  - MJPEG cameras are stored passthrough. Raw-format cameras are encoded to JPEG at target A, with `mjpeg_qsv` first (needs full-range input) and libjpeg-turbo as the fallback.
- **Capture (Windows):**
  - A pure-Python Media Foundation source reader (comtypes) replaces OpenCV.
  - The decoded BGR frame still goes to the ring buffer; the JPEG bytes go to the recorder.
  - Linux and macOS keep OpenCV until their native backends pass hardware runs (phase 1b).
- **Controls:**
  - No auto modes during a mocap session. Auto-exposure, auto gain and autofocus are off, and only manual control is used.
  - **Gain** is pinned inside the exposure step, never a separate control.
  - **Focus** is automatic, with no manual focus UI. skellycam runs its own contrast autofocus on the ChArUco board region (held where the subject will stand), with the camera's AF off. It then locks the value and stores it with the calibration; any focus change means recalibrating.
- **Playback:**
  - A canvas player in skellycam-ui: byte-range fetch by sidecar offset, `ImageDecoder` in the UI, one master clock, frames picked by capture timestamp.
  - No `<video>` for recordings, no WebCodecs video decode, no server-side or Python decode, and no `.web.mp4` transcode.
- **Packages:**
  - Python 3.13 and every package bumped to latest (PyAV 19.0.2, Electron 45).
  - `opencv-contrib-python>=4.12,<6` in phase 1; OpenCV 5 waits for phase 2.
- **Phases:**
  - **Phase 1 changes skellycam only.** The ring layout, the lockstep gate, the meaning of the existing CSV columns and `camera_id` naming stay as they are.
  - **Phase 2** is handled by a session in the freemocap repo:
    - the raw-JPEG ring option;
    - the new timing sync with the gate removed;
    - the freemocap-ui canvas player port;
    - freemocap's Python 3.13 floor;
    - OpenCV 5;
    - stable camera keys in file names;
    - 2D time interpolation;
    - imported-camera sync (skellysync).
  - freemocap keeps its current skellycam pin until then.
- **Tests:**
  - **TP1: controls and frame extraction.** Manual control only. Includes the exposure-step tests T1–T5 and the board-autofocus tests F1–F11.
  - **TP2: real-camera recording.** Lockstep only, with all cameras at the lowest common frame rate. Mixed resolutions are allowed; mixed frame rates are phase 2.
  - **TP3: simulated-camera throughput and CPU load.**
  - **TP4: playback.**
  - **Release checks:** T-FMC and T-BUMP.
- **Kiyo Pro:** expect it to wedge, roughly once per ~1,000 stream starts. On a wedge:
  - record the diagnostics;
  - mark it dead for the rest of the run;
  - **never** try to revive it (no re-probe, re-open or reset);
  - **don't** diagnose it further.

## 3. Open decisions (ask Dom)

| # | Question | Recommendation | Where |
|---|---|---|---|
| 1 | **Gain in the exposure step:** raise it up to a per-camera cap in dim light (study's proposal: Kiyo Pro 128, C922/C930e 230), or keep it pinned at default and only warn about light? | Raise up to a cap; pinning means 19–48 px of blur in normal room light | plan package 1.3; `usb_cameras/docs/exposure_gain_tradeoff.md` |
| 2 | **Kiyo Pro picture settings:** pin brightness, contrast and backlight compensation to defaults in the exposure step? They were non-default (159, 201, 1) during the tests | Yes | same doc, "Not determined" |
| 3 | **Which skellycam branch phase 1 is built on.** `dom/research` holds research only. freemocap pins skellycam `development-streaming`, which differs from `dom/research` in 72 files; the main branch is `development`. | Ask; likely a feature branch off the branch freemocap will eventually consume | `usb_cameras/docs/timestamp_accuracy_options.md` preamble |
| 4 | Housekeeping in §5 (move raw media; force-add ignored evidence) | Do both | §5 |

The skellysync decisions are in its own handoff.

## 4. Suggested order of work (phase 1)
1. **Package 1.0 (Python 3.13 + bumps) and T-BUMP.** Re-run `uv tree --outdated` after the floor moves: the 2026-11-11 listing only showed versions that support 3.11. Take the majors one at a time.
2. **1.1 small fixes and 1.2 ring-study reliability items.** Mostly no camera needed.
3. **Bring the Windows suite up to the new TP1 rules.** It predates them (§7).
4. **1.3 MF backend** with the exposure step and board autofocus; **1.11 bandwidth guidance**. Then **run TP1** on Gerald.
5. **1.4 encoder choice, then 1.5–1.8: writer, sidecars, timestamps, crash recovery, overlays. Then run TP2.**
6. **TP3** with simulated cameras: quiet machine, plus a low-end machine.
7. **1.9 skellycam-ui canvas player, then run TP4. Then 1.10 export.**
8. **1.12 Linux and macOS,** after their hardware suites run.
9. **T-FMC** before release.

## 5. Housekeeping left over
- **Raw media and samples, untracked under `usb_cameras/results/`:** 12 `.mjpeg` files (5 are 0 bytes) and about 62 sample JPEGs that may show the room. The repo convention is to move them to `C:/Users/Dom/Documents/skellycam-raw/` with mirrored paths. Not done; needs Dom's OK.
- **Evidence the root `.gitignore` catches:**
  - 138 bench stdout/stderr logs under `skellycam_recording/recording_upgrade/results/bench_runner/logs/`;
  - 8 small harness `package.json` files under `recording_upgrade/scripts/**`.
  
  They are evidence and source, not rebuildable; force-add them if Dom agrees.
- **[`REPORT.md`](REPORT.md),** the cross-study report, still dates from 2026-10-28 and covers only the first five studies.
- **Nothing is pushed.** `dom/research` is several commits ahead of Dom's fork. Push only when asked.

## 6. Working rules (from Dom; also in Claude's memory)
- **Evidence:** no assertion without evidence. Label claims [M] measured, [S] source, [C] code, [I] inferred, [NV] not verified, [arith]. Write research as Markdown under `research/`, never in Claude Docs.
- **Commits:** never commit rebuildable files (builds, binaries, venvs, caches). Keep raw camera media outside git.
- **Camera tests:**
  - tier 0 only: no driver changes and no registry changes (the `MetadataBufferSizeInKB0` values were removed on 11-09);
  - include the Kiyo Pro;
  - reliability means open/close cycling, and ≥ 381 failure-free cycles are needed for a ≥ 99 % claim;
  - streaming scope is 720 lines at ≥ 30 fps by default; the runner's `--max-height` widens it;
  - hold the cameras through `usb_cameras/tools/camlock.py`;
  - run timed benches on a quiet machine, one item at a time.
- **Device restarts are vetoed on Gerald:** LogiTune and Razer software block programmatic restarts (`pnputil`). Ask Dom for a physical replug.
- **The Windows SDK was removed from Gerald;** `wincam` builds only via the Microsoft.Windows.SDK.CPP NuGet packages.
- **Workflow agents:** don't `SendMessage` to them, as that spawns a duplicate; steer them through a shared file or resume instead. Regular sub-agents can be messaged.

## 7. Known gaps in the current Windows suite (`usb_cameras/suite/windows/`) against the new rules
- **`W-AUTO` tests auto-mode recovery,** which is no longer a product test. Replace it with the "auto stays off" drift check: 10 minutes plus stop/start, with readbacks and image metrics constant. Keep the as-found restore as housekeeping.
- **`W-KIYO`'s background poller kept polling and re-probing after a wedge** (11-11 run). It must stop, record the diagnostics in the plan's TP1 list and mark the camera dead.
- **Cycle counts are below the threshold:** 400 in-process cycles only bounds the claim at ≥ 99.05 %, and the new-process count is 100. Bring both to ≥ 381 failure-free cycles under the same harness for every camera and API in scope.
- **New tests to add:**
  - exposure T1–T5 (`docs/exposure_gain_tradeoff.md`);
  - focus F1–F11 (`docs/focus_setting_options.md`), which need a ChArUco board and a stand;
  - the TP2 recording sets;
  - the TP3 replay harness.

## 8. Corrections made on 11-11 (don't reuse the old claims)
- **"H.264 intra is the same size as MJPEG passthrough" (17.0 vs 17.7 GB/h) compared different captures.** The same-source figure is `h264_nvenc` intra at 0.69–0.76× passthrough, at lower fidelity. Notes are in the recording study's executive summary §4.3 and evidence index §2.12. Moot now that the rule is JPEG only.
- **The 11-10 Windows run's executive summary has errors.** Use [`usb_cameras/docs/windows_results_20261110.md`](usb_cameras/docs/windows_results_20261110.md) instead (its §12 lists them):
  - the 17:04 Kiyo wedge was a single-camera MF open;
  - the generic camera dropped off the bus in W-PYMF, where both probes failed about a third of their cycles;
  - the generic camera's gain and white balance have no visible effect.
- **Kiyo Pro focus does not persist:** it ignores a set focus value for about 1 s after each stream start. **The generic camera's 25.7 fps is not caused by auto-exposure.** Both are corrected in the write-up.
- **Auto-exposure priority off does not protect the frame rate.** Exposure must stay at or below the frame period: −5 at 30 fps, −6 at 60 fps.

## 9. Key files

| Topic | File |
|---|---|
| Plan of record | `CAPTURE_AND_RECORDING_PLAN.md` |
| 11-10/11 Windows run (corrected) | `usb_cameras/docs/windows_results_20261110.md`; results `usb_cameras/results/windows/Gerald/suite_20261111T040003Z/` |
| Capture stack choice | `usb_cameras/docs/capture_stack_options_plan.md` (§9 has the 11-10 results), `xplat_capture_plan.md` |
| Timestamps | `usb_cameras/docs/timestamp_accuracy_options.md`, `skellycam_timestamps_review.md` |
| Exposure / gain | `usb_cameras/docs/exposure_gain_tradeoff.md`, `skellycam_exposure_review.md`; script `usb_cameras/tools/exposure_rescore/` |
| Focus | `usb_cameras/docs/focus_setting_options.md`; scripts `usb_cameras/tools/focus_rescore/` |
| Kiyo Pro wedge (reference only) | `usb_cameras/docs/kiyo_pro_wedge_research.md` |
| Recording format evidence | `skellycam_recording/recording_upgrade/results/EVIDENCE_INDEX.md`, `intra_compare/FINDINGS.md`, `intra_playback/FINDINGS.md` (+ `gapfill/GF10_*`), `chromium_codecs/FINDINGS.md` |
| Today's recorder | `skellycam_recording/docs/skellycam_recording_report.md` |
| Ring buffer | `frame_ring_buffer/docs/frame_ring_buffer_summary.md` |
| Other platforms | `usb_cameras/docs/chromium_comparison.md`, `macos_uvc_controls_review.md`, `windows_timer_resolution.md` |
| Windows suite | `usb_cameras/suite/windows/` (`run_suite.py`, `RUNBOOK_20261109.md`, `pymf/`, `native/wincam`) |
| skellysync (separate session) | `skellysync_jpeg/SCOPE.md` |
| Raw media (outside git) | `C:/Users/Dom/Documents/skellycam-raw/` |

## 10. Hardware and people needed
- **Gerald:** i7-14700K, RTX 3070, UHD 770, Windows 11 build 26300.
  - The **Kiyo Pro is wedged** and needs a replug before any camera test.
  - Cameras: the Kiyo Pro on SuperSpeed through the Thunderbolt xHCI and a Genesys hub; the C930e on Intel root port 8; the C922 and the generic camera on the HS13 hub.
- **A ChArUco board and a stand** for the focus tests. At 3 m the letter-size board is near OpenCV's detection limit; beyond about 4 m a larger board is needed.
- **A low-end Windows laptop** for TP3 and TP4.
- **Linux and macOS machines** for phase 1b.
- **The A5 strobe rig** (`usb_cameras/sync_rig/`): firmware compiles but has never been flashed. It's needed for timestamp accuracy and for phase-2 2D time interpolation.
