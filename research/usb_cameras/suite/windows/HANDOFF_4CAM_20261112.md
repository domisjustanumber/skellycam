# Handoff: four cameras streaming together, unattended, Gerald (2026-11-12, 23:00)

For a fresh Claude session that starts and watches tonight's run, and for the morning write-up. Read this whole file first. Everything needed is here or linked.

**Context:**
- Last night's run: [`docs/windows_results_20261112.md`](../../docs/windows_results_20261112.md). Read §0, §1.2, §5, §6, §7 and §11.
- Plan of record: `research/CAPTURE_AND_RECORDING_PLAN.md` rev 3.4. Start at `research/HANDOFF_20261111_capture_recording.md` §0.
- No product code is changed by this run.

**Why this run:**
- On 11-11/12 the C922 and the generic camera shared one USB 2.0 bandwidth domain (Intel root port 13, through the hub chain on the Thunderbolt port). Every API refused that pair at 720p30.
- So no test had all four cameras streaming at once, and T-BUMP's recordings failed to start.
- **Dom moved the C922 to Intel root port HS04 (direct, no hub) on 2026-11-12.** W-TOPO at 10:20 confirmed it: C922 alone on HS04 (31.9 %), C930e alone on HS08 (49.3 %), generic on HS13 (49.3 %), Kiyo Pro on its own SuperSpeed domain. Every domain fits at 720p30 [M].
- Tonight checks that with real streams.

**Status when written:** ready to run, written 2026-11-12 ~10:50. **Not started.**

## 1. What tonight answers

| Question | Test | Pass looks like |
|---|---|---|
| Is the topology still as moved? | **W-TOPO** | `camera_domains`: the C922 on an Intel `hs|…#4` domain alone; `scenarios.all_cameras_720p30` all `fits` |
| 1.3: does **one pymf process carry all four cameras at 720p30** for 10 min without lost frames? | **W-PYMF-ALL** | 4/4 cameras streaming; 0 lost frames (MF sample-time slots); no refusal; mid-stream exposure sets on all 4 (the C922 was untested); in-use detection. The 60 fps part covers the Kiyo Pro and C922 |
| 1.0: package bump, **skellycam recording with all four cameras**, baseline vs phase-1 HEAD | **W-TBUMP** | both recordings run 60 s; equal frame counts; inter-camera spread < 1 ms; clean shutdown. 11-11/12: both failed at connect (HTTP 500) when OpenCV couldn't open the generic camera |
| 1.3/1.11: **all four started at once** through MF, DirectShow (ffmpeg CLI) and PyAV; is the unmeasured **three-USB-2.0-root-port load** (≈ 49 + 49 + 32 %) OK? | **W-MULTI** | all-at-once and staggered starts stream on every API with no bandwidth refusal (`0x800718CF` / `OSError(5)`) |
| Environment record | **W-ENV** | processes and power as found |
| Kiyo Pro control poller | **W-KIYO** (background) | as on previous nights |

**Order** (the runner's): W-ENV, W-TOPO, W-PYMF-ALL, W-TBUMP, W-MULTI, with the W-KIYO poller in the background.
- **W-MULTI is last on purpose.** Its DirectShow all-at-once loop is where the Kiyo Pro died on both previous nights (rounds 028 and 029).
- **Estimate:** 47 min (`--plan` with the 11-11/12 discovery). On 11-11/12, tests ran at 54–80 % of their estimates.

**Not in scope tonight:** the board run (it needs Dom's new rig, §8), Kiyo Pro cycling (W-CYC-KIYO), the gain tests, and any OpenCV-only test (OpenCV is off by default since 11-12: `--with-opencv`).

## 2. Rules (Dom's; non-negotiable)

- **Kiyo Pro wedges: handle, record, don't revive, don't diagnose.** The suite enforces this (the dead rule in `suitectx.py`; since 11-12 it also covers descriptor reads). The first Kiyo Pro fault marks it dead for the rest of the run. W-PYMF-ALL, W-TBUMP and W-MULTI leave a dead Kiyo Pro out of their camera lists.
  - **The session must not revive or diagnose it either:** no replug requests mid-run, no `pnputil`, no extra probes.
  - If it dies: check that `KIYO_PRO_DEAD_*.json` was written and that no later command reached it; note the time, the test and the stage.
- **Say "Kiyo Pro", never bare "Kiyo"** (a different model). Test ids like `W-KIYO` keep their names.
- **Tier 0 only:** no driver or registry changes, no UVC PTS/SCR.
- **Device restarts are vetoed on Gerald** (LogiTune/Razer block `pnputil`). Never restart a device; a dropped camera needs Dom to replug it.
- **One camera user at a time.** Run no other camera command while the suite runs. Don't wrap `run_suite.py` in camlock.
- **Quiet machine:** no other heavy work during the run.
- **Privacy:**
  - Results contain the real C922 serial. Run `research/usb_cameras/tools/redact_run.py RUN_DIR --apply` before anything is committed (§6).
  - Never commit images or video.
  - **Ask Dom before pushing anything.**
- **Versions pinned exactly** (no ranges) in anything you add.
- **Evidence labels in the write-up:** [M] measured, [C] code, [I] inferred, [NV] not verified.

## 3. Preconditions (check each; ask Dom for the physical ones before setting the timer)

1. **The Kiyo Pro must be replugged by Dom** before the run.
   - It has been wedged since 2026-11-12 00:46 (05:46:24Z), when it died in W-MULTI.
   - Replug it into **the same hub port** (the Genesys hub chain on the Thunderbolt port), so the topology is unchanged.
   - In the pre-flight output, its plug-in age should be from today's replug. Its last arrival before the replug was 2026-11-11T23:27:22Z.
   - **If Dom says it wasn't replugged:** run without it, with `--kiyo-pro-dead 2026-11-12T05:46:24.269472+00:00` added to the launch command. Report the results as three cameras.
2. **Ports unchanged since 10:20:** the C922 directly on HS04, the C930e on HS08, the generic and the Kiyo Pro on the hub chain. Ask Dom to confirm nothing was moved.
3. **Revelator IO 24 not streaming audio** (no DAW or audio app using it). It shares root port 13 with the generic camera, and its audio load is unmeasured.
4. **Scene:**
   - every camera sees a static, textured target in the centre half of the frame;
   - room lights on all night, no daylight, nobody walking through;
   - mid-grey brightness.

   W-PYMF-ALL's mid-stream exposure check needs luma to move visibly.
5. **Close camera apps:** Camera, Teams, Zoom, OBS, Signal, Discord, WhatsApp, browsers (Firefox was open on 11-11 until Dom closed it), NVIDIA Broadcast. **Close LogiTune, Logi Options+ and Razer Synapse.** Check with a read-only `Get-Process`; if any stay open, W-ENV records it and the report says so.
6. **No sleep:** read-only `powercfg /query SCHEME_CURRENT SUB_SLEEP`. Standby and hibernate were "never" on AC on 11-11. Don't change power settings.
7. **Disk:** ≥ 30 GB free on C:. 729 GB was free on 11-11.
8. **Repo state:**
   - branch `dom/research` in `C:\Users\Dom\GitHub\freemocap\skellycam`, clean, at or after `825a979cd`;
   - worktrees `C:\Users\Dom\GitHub\freemocap\skellycam-phase1` (branch `dom/capture-recording-phase1`) and `C:\Users\Dom\GitHub\freemocap\skellycam-tbump-baseline` (`2992e64f9`) present and clean (W-TBUMP uses both).

## 4. Start

**Timer:** set a one-shot timer for 23:00 (CronCreate, `0 23 12 11 *`, `recurring: false`; it may fire up to 90 s early). **Keep this Claude Code session open all night:** the timer and the background run belong to it.

**At 23:00:**

1. Read-only `Get-Process` check for camera apps (§3.5). Note anything still open.
2. **Pre-flight, in its own tool call** (enumeration only, opens no camera):

   ```text
   cd C:\Users\Dom\GitHub\freemocap\skellycam
   uv run --python 3.12 --script research/usb_cameras/suite/windows/run_suite.py --plan --only W-ENV,W-TOPO,W-PYMF-ALL,W-TBUMP,W-MULTI,W-KIYO --min-fps 30 --min-height 720 --max-height 720
   ```

   Check:
   - **all four cameras listed:** the Kiyo Pro (`1532:0e05`) at `speed SS` with a fresh plug-in age; the C930e, the generic `4c4a:4a55` and the C922 (`046d:085c:sn=…`) at HS;
   - the order and the ≈ 47 min total.

   Ignore Kiyo Pro "wedge window" warnings and exit code 3 (the old age check).

   **If a camera is missing,** run a read-only `Get-PnpDevice -PresentOnly | ? InstanceId -match 'VID_xxxx&PID_yyyy'` for it, and don't launch until Dom answers. A camera with problem code 10 needs a physical replug.
3. **Launch** with the **PowerShell tool, `run_in_background: true`**:

   ```powershell
   Set-Location C:\Users\Dom\GitHub\freemocap\skellycam
   $log = "$env:USERPROFILE\Documents\skellycam-raw\fourcam_20261112_console.txt"
   "=== run $(Get-Date -Format o)" | Out-File $log -Encoding utf8
   uv run --python 3.12 --script research/usb_cameras/suite/windows/run_suite.py --only W-ENV,W-TOPO,W-PYMF-ALL,W-TBUMP,W-MULTI,W-KIYO --min-fps 30 --min-height 720 --max-height 720 *>> $log
   "=== exit $LASTEXITCODE $(Get-Date -Format o)" | Out-File $log -Append -Encoding utf8
   ```

   (Add `--kiyo-pro-dead 2026-11-12T05:46:24.269472+00:00` only in the §3.1 fallback.)
4. About 2 minutes after launch, read the head of the console log **once**. Check that:
   - the cameras are listed;
   - you have the results folder name (`research/usb_cameras/results/windows/Gerald/suite_<UTC stamp>/`);
   - `W-KIYO: background control poller started` appears;
   - W-TOPO's result line is there.

## 5. While it runs

- **The run's exit fires a task notification.** Don't poll in a loop.
- **For alerts,** arm one Monitor (≤ 30 min, re-arm on expiry). Use a **wall-clock deadline**: on 11-12 a loop counted in iterations overran its 30-min limit and never printed a status. Template (fill in the run folder):

  ```bash
  R="/c/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras/results/windows/Gerald/suite_<stamp>"
  C="/c/Users/Dom/Documents/skellycam-raw/fourcam_20261112_console.txt"
  dead_seen=0; tb_seen=0; end=$((SECONDS+1620))
  while [ $SECONDS -lt $end ]; do
    if [ $dead_seen = 0 ] && ls "$R"/KIYO_PRO_DEAD_*.json >/dev/null 2>&1; then echo "ALERT Kiyo Pro dead record: $(ls "$R"/KIYO_PRO_DEAD_*.json | xargs -n1 basename)"; dead_seen=1; fi
    if [ $tb_seen = 0 ] && grep -q "Traceback" "$C" 2>/dev/null; then echo "ALERT Traceback in console log"; tb_seen=1; fi
    if grep -q "=== exit" "$C" 2>/dev/null; then echo "RUN EXITED: $(grep '=== exit' "$C" | tail -n1)"; exit 0; fi
    sleep 5
  done
  echo "STATUS $(date +%H:%M): $(grep -E 'run_suite: (\[|W-[A-Z-]+ (ok|partial|failed|error|crash))' "$R/suite_log.txt" | tail -n1 | cut -c1-170)"
  ```

- **If the Kiyo Pro dies:** nothing to do except record it (§2). On both previous nights the poller saw the failure about 6 s before the fault was marked. On 11-11/12, one already-queued poll also reached the camera 0.2 s after the mark. That poll is a known suite gap (results 11-12 §9.1), not a breach to act on.
- **If the runner crashes:** read the traceback first. Restart only the unfinished tests (`--only` the remaining ids), and add `--kiyo-pro-dead <UTC from KIYO_PRO_DEAD_*.json>` if the Kiyo Pro had died.
- **Ctrl-C (or TaskStop) stops cleanly** and keeps partial results.

## 6. As soon as the run exits: analyse and write up

Do this straight after the exit notification (Dom, 2026-11-12). Don't wait for the morning or for a prompt. Then stop and leave the result for Dom.

1. **Redact first:** `uv run --python 3.12 --script research/usb_cameras/tools/redact_run.py research/usb_cameras/results/windows/Gerald/suite_<stamp> --apply`.
   - Move any media files it lists to `C:\Users\Dom\Documents\skellycam-raw\` with mirrored paths (`skellycam-raw\research\usb_cameras\results\…`, as the 11-11/12 run did).
   - Re-run without `--apply` and confirm 0 serials and 0 media files.
2. Read `summary.md`, `run_suite.json` (faults, dead, stream starts) and each `<TEST>.json`.
3. Write `research/usb_cameras/docs/windows_results_20261113.md` (Markdown in `research/`, never Claude Docs), in the style of `windows_results_20261112.md`. One section per row of §1, each with a verdict, the evidence (file + JSON path, [M]) and what's still open. Specifically:
   - **W-TOPO:** the domain table; is it unchanged from 10:20?
   - **W-PYMF-ALL:** per camera fps, frames, lost frames, arrival gaps, first-frame and release times, CPU per camera; the C922's mid-stream set (first time tested); in-use detection; the 60 fps part (Kiyo Pro 30.0 and C922 59.2 on 11-11/12). **Does one pymf process carry all four at 720p30 without loss?** That is the 1.3 headline.
   - **W-TBUMP:** baseline vs HEAD: fps, frame counts, inter-camera spread, errors, file sizes, shutdown. If it fails again, quote the server log lines (raw logs are in skellycam-raw) and say whether the failing camera was the generic again.
   - **W-MULTI:** per API, all-at-once, staggered and pairs: streamed or refused, the refusal codes, MF vs DS classification. Compare with 11-11/12 §6.
   - **The Kiyo Pro:** alive all run, or dead at what time, in which test and stage, at what plug-in age (facts only).
4. **Update** `research/HANDOFF_20261111_capture_recording.md` §0. Update the plan only if a decision changed.
5. **Commit** the redacted results and the write-up on `dom/research`. **Don't push; ask Dom.**

## 7. Known behaviour to expect (from 11-11/12)

- **Host clocks and MF sample times tick in 16 ms on Gerald.** Judge gaps against the fitted frame period. At 60 fps, arrival gaps are not rated.
- **The generic camera delivers 25.76 fps** at "30 fps" on every API. That is its real rate; a "rate < 90 %" note is expected.
- **The Kiyo Pro delivers about 30 fps from its 720p60 mode**, through pymf too.
- **The Kiyo Pro stalls once per stream,** about 300 ms after its 1.2 s control re-apply.
- **The generic camera dropped off the bus 3 times on 11-11/12** (it re-enumerated and recovered). Record any re-arrival; don't diagnose it.
- **W-PYMF's "all: partial" cap and W-PYMF-ALL's low-rate exemption** produce "partial" ratings without lost frames (results 11-12 §1.2, §9). Read the criteria, not just the label.
- **The 6 `msedgewebview2` processes** aren't matched by W-ENV's patterns. Note them if seen.

## 8. Open to-do items (not for tonight)

- **The board run needs a new rig.** Dom is building a new rig (a ChArUco board stand) for the attended board run. Until it exists, the D14 thresholds stay provisional: d_min 0.80, r_max 1.5, j_max unset. That run is specified in `research/usb_cameras/docs/exposure_gain_tradeoff.md` §6 ("Validating §5.2b"). It also covers the focus tests F1–F11, T3 and T5.
- **Kiyo Pro cycling (W-CYC-KIYO):** no result since it died before its turn on 11-11/12. It needs a fresh replug and its own night.
- **Suite gaps** from results 11-12 §9: the dead-rule check before camlock, multi-camera commands not mapped to a camera, stream starts counted per command, the stale W-PYMF cap, W-GAIN's ρ criterion, W-GAIN's 60 fps legs through wincam, W-NODRIFT and the C930e reset, W-ENV patterns, and the stale plug-in age after a re-arrival.
- **W-GAIN rewrite for D14:** the matched-brightness steps with pymf at 60 fps.
- **skellycam fails the whole camera group when one camera fails to open** (seen 11-11/12 in W-TBUMP, on `main`/baseline and phase-1 HEAD alike) [C]:
  - `setup_opencv_camera_loop.py:69-77` sets `ipc.should_continue = False` for the whole group;
  - `camera_group_manager.py:51-64` tears the group down;
  - the API then answers HTTP 500 from `validate_camera_configs` (`camera_config.py:380-382`, a `None` config).

  The server itself survives. **Not changed tonight:** T-BUMP compares package versions on today's code, and a behaviour fix in HEAD would muddle that. Fix it as its own phase-1 commit (packages 1.3/1.11): keep the other cameras streaming, and report the failed camera with its reason (bandwidth / in use / not found; pymf gives exact HRESULTs).
- **OpenCV in tonight's run:** only inside skellycam during W-TBUMP. Both baseline and phase-1 HEAD still capture through OpenCV until package 1.3 (pymf) is built. No suite test uses OpenCV tonight.
