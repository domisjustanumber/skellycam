# Handoff: unattended overnight run on Gerald (2026-11-11/12)

For a fresh Claude session that starts and watches tonight's run, and for the morning write-up. Read this whole file first. Everything needed is here or linked.

**Context:** `research/HANDOFF_20261111_capture_recording.md` §0 and `research/CAPTURE_AND_RECORDING_PLAN.md` (rev 3.3). Phase 1 is choosing and building skellycam's new capture and recording path. Tonight's run gathers the hardware evidence for the next decisions (§1). No product code is changed by this run.

**Status when written:** ready to run, written 2026-11-11 ~20:00 by the session that built it. **Not started.** Blockers and notes:
- **The C922 was down** (problem code 10 since 09:11). **Dom replugged it into the same port at 19:57;** it read OK (problem code 0) on the same Genesys hub, so the HS13 topology is unchanged. The 19:58 pre-flight found all four cameras (Kiyo Pro SS; C930e, generic, C922 HS) with a total estimate of **9h31m**, exit 3 (the old age check: ignore it). Re-check in your own pre-flight; the C922 was never streamed after the replug.
- **Every new test was smoke-tested on the real cameras** (quick profile, 3 cameras, outputs in the session scratchpad, not in the repo). Results are in §7. Offline tests: 324 passed.
- **Camera controls at hand-off:** the smoke runs left auto-exposure off on three cameras (skellycam's default MANUAL −7 during W-TBUMP). It was put back to **auto** at ~19:55 on the Kiyo Pro, C930e and generic. Read back: exposure flags `auto`; focus and WB were already auto (the generic has fixed focus and manual WB 4500, as found on 11-11). W-TBUMP now restores as-found controls after its recordings.

## 1. What tonight answers

| Decision (plan package) | Evidence tonight | Test |
|---|---|---|
| 1.3: pure-Python Media Foundation reader as skellycam's Windows capture backend | One pymf process streaming all cameras (720p30, 10 min) and the 60 fps cameras (3 min); control sets mid-stream; in-use detection | **W-PYMF-ALL** (new) |
| 1.3: reliability, at ≥ 381 failure-free open/close cycles per camera and API (≥ 99 % at the Wilson lower bound) | 400 MF in-process, 400 DirectShow-ffmpeg in-process and **400 MF new-process** (was 100) per camera; the Kiyo Pro about 1,360 | **W-CYC**, **W-CYC-KIYO** |
| 1.3: controls lock (D10–D12): everything locked at its start value, AE/AF/AWB off | 10 min stream + 3 stop/starts, readbacks and image constant | **W-NODRIFT** (new; replaces W-AUTO) |
| 1.3: exposure step, gain limit measured from noise (D9) | Gain × exposure grid (64 frames per cell), reference cap, the §5.2a in-step rule 10× per camera; delivered fps per exposure step (the ceiling) | **W-GAIN** (new) |
| 1.0: package bump (Python 3.13, PyAV 19, numpy 2.5, OpenCV 5) | Real skellycam recordings: `main` baseline vs phase-1 HEAD, 60 s, all live cameras | **W-TBUMP** (new) |
| 1.3/1.11: multi-camera all-at-once, MF vs DirectShow; bandwidth | as before | W-MULTI |
| Formats, real JPEG bytes, raw modes, host timestamps, pymf = wincam, controls change the image, OpenCV controls | as before (re-run on the current harness) | W-ENV … W-PYMF, W-CTRL-EFFECT, W-OCV-CTRL |

**Not possible unattended:**
- the focus tests F1–F11, which need the ChArUco board on a stand;
- the light-level and blur tests T3 and T5;
- TP2, TP3 and TP4 (the new writer and player aren't built).

## 2. Rules (Dom's; non-negotiable)

- **Kiyo Pro wedges (expect about one per ~1,000 stream starts): handle, record, don't revive, don't diagnose.** The suite enforces this itself (the dead rule in `suitectx.py`): the first Kiyo Pro fault marks it dead for the rest of the run.
  - Every later command addressed to it is skipped, whatever its kind; it is never re-probed, re-opened, reset or recovered; the W-KIYO poller stops polling it; W-PYAV-LIST is skipped.
  - One diagnostics snapshot is written: `KIYO_PRO_DEAD_<stamp>.json` in the run folder.
  - **The session must not try to revive or diagnose it either.** No replug requests mid-run, no `pnputil`, no extra probes.
- **Say "Kiyo Pro", never bare "Kiyo"** (the Kiyo is a different model). Test ids like `W-KIYO` keep their names.
- **Tier 0 only:** no driver or registry changes, no UVC PTS/SCR.
- **Device restarts are vetoed on Gerald** (LogiTune/Razer block `pnputil`). Never restart a device.
- **One camera user at a time.** Don't run any other camera command while the suite runs: the suite holds every camera command under `tools/camlock.py`, and concurrent access is suspected in Kiyo Pro wedges. Don't wrap `run_suite.py` itself in camlock.
- **Quiet machine:** no other heavy work on Gerald during the run (timed results).
- **Privacy:** results contain the real C922 serial and other identifiers. Before anything is committed, run `research/usb_cameras/tools/redact_run.py RUN_DIR --apply` (§6). Raw frames are written outside the repo; never commit images or video. **Ask Dom before pushing anything.**
- **Versions are pinned exactly** (no ranges) in anything you add.
- **Evidence labels** in the write-up: [M] measured, [C] code, [I] inferred, [NV] not verified.

## 3. Preconditions (check each; ask Dom for the physical ones)

1. **Kiyo Pro freshly replugged** by Dom on 2026-11-11 at ~19:00. Fine; no further replug.
2. **Scene:** every camera sees a static, textured target in the centre half of the frame, with steady light (room lights on all night, no daylight, nobody walking through). W-GAIN, W-NODRIFT and W-CTRL-EFFECT depend on it. Mid-grey brightness; a very dark or bright scene makes some ratings inconclusive.
3. **Close camera apps:** Camera, Teams, Zoom, OBS, Signal, Discord, WhatsApp, browsers with camera tabs, NVIDIA Broadcast. **Close LogiTune and Razer Synapse if possible** (they write controls and held the Kiyo Pro during earlier wedges); if they stay open, W-ENV records it and the report must say so.
4. **No sleep:** checked 2026-11-11 19:45: the Balanced scheme has standby and hibernate at "never" on AC (`powercfg /query SCHEME_CURRENT SUB_SLEEP`). Don't change power settings.
5. **Disk:** raw frames go to `C:\Users\Dom\Documents\skellycam-raw\results\windows\Gerald\suite_<stamp>\`. Check ≥ 30 GB free on C:.
6. **Repo state:** branch `dom/research` in `C:\Users\Dom\GitHub\freemocap\skellycam`, with the suite changes committed (§7). The phase-1 worktree `C:\Users\Dom\GitHub\freemocap\skellycam-phase1` (branch `dom/capture-recording-phase1`, local only) and the baseline worktree `C:\Users\Dom\GitHub\freemocap\skellycam-tbump-baseline` exist and are synced (W-TBUMP uses both).

## 4. Start

**Pre-flight first, in its own tool call** (opens no camera; enumeration only):

```text
cd C:\Users\Dom\GitHub\freemocap\skellycam
uv run --python 3.12 --script research/usb_cameras/suite/windows/run_suite.py --plan --cyc-profile reliability --reliability-cycles 400 --min-fps 30 --min-height 720 --max-height 720
```

Check in its output:
- **all four cameras** are listed: the Kiyo Pro (`1532:0e05`) at `speed SS`, the C930e, the C922 and the generic `4c4a:4a55`. If the C922 is missing, run a read-only check, `Get-PnpDevice -PresentOnly | ? InstanceId -match 'VID_046D&PID_085C'`. On 2026-11-11 it showed **problem code 10** (USB Composite Device, Status Error) and needed a physical replug: ask Dom; never restart it from software. Don't start a run without the C922 unless Dom says so.
- the order is W-ENV … W-PYMF, W-PYMF-ALL, W-NODRIFT, W-GAIN, W-CTRL-EFFECT, W-OCV-CTRL, W-TBUMP, W-MULTI, W-PYAV-LIST, W-CYC-KIYO, W-CYC; W-AUTO is not in it.
- the total estimate: **9h31m with 4 cameras** (2026-11-11 19:58 pre-flight). On 11-06 tests ran at 75–80 % of their estimates.
- Kiyo Pro "wedge window" age warnings come from the old 11-06 theory: **ignore them.** Exit code 3, if it appears, is that age check: ignore it too.

**Then launch the run** with the **PowerShell tool, `run_in_background: true`**. Keep this Claude Code session open all night: the background command belongs to it.

```powershell
Set-Location C:\Users\Dom\GitHub\freemocap\skellycam
$log = "$env:USERPROFILE\Documents\skellycam-raw\overnight_20261111_console.txt"
"=== run $(Get-Date -Format o)" | Out-File $log -Encoding utf8
uv run --python 3.12 --script research/usb_cameras/suite/windows/run_suite.py --cyc-profile reliability --reliability-cycles 400 --min-fps 30 --min-height 720 --max-height 720 *>> $log
"=== exit $LASTEXITCODE $(Get-Date -Format o)" | Out-File $log -Append -Encoding utf8
```

- **Don't wrap `run_suite.py` in camlock** (it takes camlock per command itself).
- About 2 minutes after launch, read the head of the console log **once**. Check:
  - the cameras are listed;
  - the results folder name (`research/usb_cameras/results/windows/Gerald/suite_<UTC stamp>/`);
  - `W-KIYO: background poller started`.

  Then don't poll: you're notified when the command exits. For a periodic check, use the Monitor tool on `summary.md`, no more often than every 30–60 min.
- **Restart after a runner crash only.** Restart only the tests not yet finished (`--skip` the finished ones, or `--only W-CYC` to finish cycles). **If the Kiyo Pro died before the crash, add `--kiyo-pro-dead <UTC from KIYO_PRO_DEAD_*.json>`**: the dead state lives in memory only, and the flag stops a restarted runner from touching it.

## 5. While it runs

- Progress: `summary.md` in the run folder refreshes after every test; `suite_log.txt` has every line.
- Use the Monitor tool (or the background-task notification) rather than polling in a loop. A long silence during W-CYC/W-CYC-KIYO is normal (a 400-cycle variant holds the camera lock for 15–25 min).
- **If the Kiyo Pro dies:** nothing to do. Check that `KIYO_PRO_DEAD_*.json` was written and that no later command reached it (`gate: skipped` lines for it in `suite_log.txt`). Note the time and test.
- **If the runner itself crashes:** don't restart blindly. Read the traceback, then restart as in §4: `--skip` the finished tests, and add `--kiyo-pro-dead <UTC>` if the Kiyo Pro had died.
- Ctrl-C (or TaskStop) stops cleanly: W-KIYO is written and partial results kept.

## 6. Morning: analyse and write up

1. **Redact first:** `uv run --python 3.12 --script research/usb_cameras/tools/redact_run.py research/usb_cameras/results/windows/Gerald/suite_<stamp> --apply`. It reports media files: move any found to skellycam-raw (mirrored paths). Re-run without `--apply` and confirm it finds nothing left.
2. Read `summary.md`, `run_suite.json` (faults, `dead`, `stream_starts`) and each `<TEST>.json`.
3. Write `research/usb_cameras/docs/windows_results_20261112.md` (Markdown in `research/`, never Claude Docs), with one section per §1 decision:
   - the verdict;
   - the evidence (file + JSON path, labelled [M]);
   - what's still open.

   Specifically:
   - **W-PYMF-ALL:** per-camera fps, gaps, jitter, CPU, refusals; control-set latency; in-use error class. Does one pymf process carry all four cameras at 720p30 without drops?
   - **W-CYC / W-CYC-KIYO:** per camera × API (MF in-process, DS-ffmpeg in-process, MF new-process): failures, Wilson lower bound, ≥ 99 % yes/no.
   - **W-NODRIFT:** any drift, and which cameras needed re-apply after start (expect the C930e).
   - **W-GAIN** (read the 60 fps caveat in §7 first): the reference cap per camera, the §5.2a g_lim over 10 runs (agreement), monotonic ρ, bytes vs gain, the delivered-fps ceiling per exposure step at 30/60 fps. Recommend thresholds for §5.2a.
   - **W-TBUMP:** baseline vs HEAD (fps, frame counts, errors, sizes).
   - **The Kiyo Pro:** alive all night, or dead at what time, in which test, and after how many stream starts (from the dead record). No diagnosis.
4. Update `research/HANDOFF_20261111_capture_recording.md` §0, and the plan if a decision changed.
5. Commit the redacted results and the write-up on `dom/research`. **Don't push; ask Dom.**

## 7. What changed in the suite for tonight (2026-11-11 evening)

All in `research/usb_cameras/suite/windows/` on `dom/research` (local commits; nothing pushed).

**Rules and runner**
- **Kiyo Pro dead rule** (`suitectx.py`): `camera_dead()`; `camcmd` refuses every command to a dead Kiyo Pro; `health_probe` / `clear_fault` / `begin_test` never probe or recover it; `KIYO_PRO_DEAD_<stamp>.json` holds the diagnostics (the plan's list: time, plug-in age, test, last command, error events, other running camera commands, stream starts this run, camera activity / Frame Server clients / process list, USB link). The W-KIYO poller (`w_kiyo.py`) stops polling it. `run_suite.py --kiyo-pro-dead UTC` marks it dead from the start on a restart.
- **Order** (`run_suite.py`): W-AUTO out of the default order (`--only W-AUTO` still works); W-PYMF-ALL, W-NODRIFT, W-GAIN after W-PYMF; W-TBUMP after W-OCV-CTRL; W-CYC-KIYO second-last; W-PYAV-LIST skipped whole when a Kiyo Pro is dead. `KIYO_STARTS_WARN` raised from 250 to 400 (advisory).
- **W-CYC:** MF new-process cycles 100 → **400**, so every camera × API can reach ≥ 381 failure-free cycles.
- **Exact pins** in the script headers (simplejpeg 1.9.0, pillow 13.0.0, numpy 2.5.4, comtypes 1.5.0, av 19.0.2, `opencv-contrib-python==5.0.0.93`; Python 3.12.13). The OpenCV helpers (W-OCV-CTRL, raw_ds, opencv_ds) now run OpenCV 5, as phase-1 skellycam does.
- `w_auto.restore_state`: controls with no auto/manual flag (AE priority) are verified by value. This was a false "restore not verified" in the W-GAIN smoke.

**New tests** (each with offline tests)
- **W-NODRIFT** (`tests/w_nodrift.py`): locks WB, exposure, focus and the image controls at their start values, sets AE priority 0 and power-line 60 Hz, soaks 10 min, then 3 stop/starts. Drops are counted from MF sample-time steps against the fitted frame period. Both host clocks tick in 16 ms on Gerald, so the first version's arrival-gap "drops" were false.
  - Smoke: Kiyo Pro **yes**, C930e **yes** (it needed gain re-applied after a restart, as known), generic **partial** (ROI luma/R/B wander slightly).
  - The Kiyo Pro showed **one ~290–300 ms stall (~8 frames) per stream**, around the control re-apply at 1.2 s [M, smoke].
- **W-GAIN** (`tests/w_gain.py`): a gain × exposure grid (64 frames per cell), the reference cap, the §5.2a rule (forced so gain is needed: 10 runs at 30 fps, 3 at 60 fps), and T4 delivered fps per exposure step.
  - Smoke T4: C930e ceiling −5 at 30 fps, as expected. **The Kiyo Pro dropped to 28.7 fps at −6 and 23.2 at −5**: its real ceiling at 30 fps looks like **−7**, not −5 [M, smoke, 3 steps].
  - The generic camera's gain has no effect, as known.
- **W-PYMF-ALL** (`tests/w_pymf_all.py`, `pymf/multi.py`, `pymf/framerec.py`, `pymf multi` CLI): one pymf process streams all cameras, then the 60 fps cameras; exposure is set mid-stream; in-use detection never touches the Kiyo Pro. A session that hangs with the Kiyo Pro in it marks it dead (conservative).
  - Smoke: 3 cameras at 720p30 in one process, every frame intact (Kiyo Pro 1,803 / C930e 1,819 / generic 1,568 in 60 s); mid-stream exposure sets yes; in-use detection yes.
  - The Kiyo Pro rated partial on 7 arrival gaps (max 64 ms) at 30 fps, likely the 16 ms host grid. Judge it in the morning.
- **W-TBUMP** (`tests/w_tbump.py`, `helpers/skellycam_record.py`): skellycam records 60 s through its HTTP API, at the baseline worktree `skellycam-tbump-baseline` (commit 2992e64f9: Py 3.12, OpenCV 4.12, numpy 2.2, PyAV 18) and at phase-1 HEAD (Py 3.13, OpenCV 5.0, numpy 2.5, PyAV 19). Detection doesn't open cameras (property bags only). It snapshots and restores the as-found controls.
  - Smoke (10 s): both ok on 3 cameras, equal frame counts, inter-camera spread < 1 ms, lockstep at 25.8 fps (the generic camera's 25.7 sets it), clean shutdown.
  - **Note:** skellycam sends its startup telemetry ping to FreeMoCap's server (dev builds use a placeholder secret, which the server rejects); it carries the install's telemetry id. That's the app's normal behaviour; Dom wasn't asked to opt out.

**C922 smoke after its replug** (20:00–20:06, quick profile, the C922 alone; every test ran, 0 errors, as-found controls restored):
- W-PYMF-ALL: all **yes**. pymf delivered **1,802 frames in 60 s at 720p30 and 1,725 in 30 s at 720p60 (≈ 57.5 fps)**.
- W-NODRIFT: **no** only on R/B ratio, −3.0 % and −3.4 % against a provisional ±3 % limit. Exposure, gain, focus, WB and luma held; 0 drops. Judge the threshold on tonight's 10-min soak.
- W-GAIN: T4 ceiling at 30 fps is −5, as expected; the forced rule gave g_lim 27 (30 fps) and 18 (60 fps). The as-written rule needed no gain in the night scene.
- W-TBUMP: both recordings ok. Rated partial for one new phase-1 log line at shutdown ("global_kill_flag is set (no worker death detected) — triggering parent shutdown"). It looks like a changed shutdown message, not a fault, but that isn't verified: check it in the morning.

**Caveat for the morning: 60 fps through wincam's MF path is not trustworthy on the C922 (and probably the Kiyo Pro).** wincam negotiated MJPG 1280×720 at 60/1 but delivered **30–35 fps**, whatever the exposure: as found with AE on 35.15; manual −7 29.75; manual −9 (1.95 ms) 29.66 [M, 20:08, 5 s each]. pymf (W-PYMF-ALL) delivered ≈ 57.5 from the same mode, and on 11-10 W-MJPEG got 122 MF frames against 180 DirectShow frames in 3 s. So W-GAIN's 60 fps T4 "ceiling" and any wincam 60 fps rate measure wincam, not the camera. Compare with pymf's rates before concluding anything about exposure at 60 fps. The Kiyo Pro's "60 fps" T4 numbers in the first smoke run matched its 30 fps ones exactly, which fits the same cause [I].

**Tool**
- `research/usb_cameras/tools/redact_run.py`: privacy redaction for results folders (§6).
