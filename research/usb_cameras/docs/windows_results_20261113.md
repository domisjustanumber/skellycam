# Windows results, Gerald, 2026-11-12/13 (four cameras together)

Write-up of the unattended run started from
[HANDOFF_4CAM_20261112.md](../suite/windows/HANDOFF_4CAM_20261112.md). It answers that handoff's §1, one section per row.
The previous run's write-up is [windows_results_20261112.md](windows_results_20261112.md) ("11-11/12" below).

**Labels:**
- [M] measured: a result file and field support it.
- [C] code: read from the source.
- [I] inferred: reasoning.
- [NV] not verified.

**Conventions:**
- Times are local (UTC−5), with UTC in brackets where it matters.
- `R/` = [`results/windows/Gerald/suite_20261113T035946Z/`](../results/windows/Gerald/suite_20261113T035946Z/).
- Camera keys are shortened: Kiyo Pro `1532:0e05`, C930e `046d:0843`, C922 `046d:085c`, generic `4c4a:4a55`.

**The results were redacted** with `tools/redact_run.py --apply`: 7 serials, 488 serial and 264 container-MAC replacements in 62 files, 0 paths renamed, 0 media files. A re-check finds 0 serials and 0 media files left.

## 0. Summary

| Question (handoff §1) | Verdict tonight | Short reason |
|---|---|---|
| W-TOPO: topology still as moved? | **Yes** | Each of the C922, C930e and generic has its own Intel HS root port (#4, #8, #13), and the Kiyo Pro has its own SS domain. All four fit at 720p30. The domain table matches 10:20 exactly. |
| 1.3: one pymf process, all four at 720p30, 10 min, no loss | **Yes** | All 4 streamed together for 600 s: 69,525 frames, all valid JPEG, **0 lost frames on every camera**, no refusal. 8.4 % of one core for the whole process (2.1 % per camera). Mid-stream exposure sets worked on all 4, including the C922 for the first time. In-use detection: yes. |
| 1.3: the 60 fps part | **C922 yes (59.43 fps). Kiyo Pro died here** | The Kiyo Pro's first sample at 720p60 never came. That fault marked it dead (§5). |
| 1.0: skellycam recording, baseline vs phase-1 HEAD | **Yes with 3 cameras; the 4-camera recording is untested** | The Kiyo Pro was dead by then and left out. Both recordings ran 60 s with equal frame counts. Inter-camera spread: median 0.26 / 0.28 ms, max 1.18 / 1.06 ms. Clean shutdown, 0 errors. The generic camera opened through OpenCV this time. **HEAD ran on Python 3.13.18, not the pinned 3.13.13** (§3.3). |
| 1.3/1.11: all at once on MF, DS, PyAV; the 3-root-port USB 2.0 load | **Yes for the three HS cameras on every API: 0 bandwidth refusals.** Four at once only through pymf | 38 rounds streamed all three HS cameras at once. The generic camera dropped off the bus once, in PyAV round 039, and re-enumerated (§4). |
| Kiyo Pro | **Died at 23:13:01 (04:13:01Z)** in W-PYMF-ALL, `all_720p60`, stage `first_sample`, plug-in age 345.6 min | A different test and API from both previous nights. The dead rule held, apart from the known queued-poll gap (§5, §6). |

**The run itself:**
- 22:59:46 → 23:23:08 (03:59:46Z → 04:23:08Z), 23 min 22 s against a 47 min 19 s estimate. `interrupted` false, exit 0 [M] (`R/run_suite.json` `elapsed_s` 1,402).
- Every test ended `ok` with 0 errors [M] (`status[]`).
- It finished early mostly because the Kiyo Pro was dead for W-TBUMP and W-MULTI, and W-MULTI found no conflict pairs to test [I].

**Before the run** [M]:
- **Kiyo Pro replug:** Dom replugged it at about 17:27 (22:27:22Z) into the same hub port (`…/4.4`). That was earlier than the planned ~22:45, so its plug-in age at launch was 332.4 min.
- **Pre-flight at 22:59:39:** 4 cameras listed, the Kiyo Pro at SS, the C930e, generic and C922 at HS.

**Machine state** [M] (`R/W-ENV.json`, and a read-only `Get-Process` at 22:59):
- Balanced plan, USB selective suspend enabled, USB 3 LPM "Moderate power savings". All 4 cameras on `usbvideo`, problem code 0.
- Dom closed Firefox, Signal and WhatsApp. **Universal Control (PreSonus, the Revelator's mixer app) was still open.**
  - W-ENV's process scan matched nothing, because Universal Control isn't in its patterns [C].
  - Dom confirmed the Revelator wasn't streaming audio.
  - Obsidian (4 processes) was also open.
- No python, uv, ffmpeg or VLC processes from other sessions were running at launch.
- **Scene and lighting:** as Dom set them (static target, lights on). Not checked by the suite [NV].

## 1. W-TOPO: topology (22:59:47)

**Unchanged from the 10:20 check** [M] (`R/W-TOPO.json measurements.camera_domains`, `.scenarios.all_cameras_720p30`):

| Camera | Domain | Load at 720p30 (% of a microframe) | Verdict |
|---|---|---|---|
| C922 | Intel `hs|…#4`, alone | 31.9 % | fits |
| C930e | Intel `hs|…#8`, alone | 49.3 % | fits |
| generic | Intel `hs|…#13` (via the Genesys hub chain), alone | 49.3 % | fits |
| Kiyo Pro | Thunderbolt controller `ss|…#4`, alone | – | fits |

- No predicted conflicts for `all_cameras_720p30` [M] (`verdicts.G-BW.evidence.predicted_conflicts`).
- The mapper verdict is yes. The G-BW cell is untested because nothing was refused (§4).

## 2. Decision 1.3: one pymf process, all four cameras (W-PYMF-ALL, 22:59:47–23:13:50)

### 2.1 720p30, one 600 s session: the 1.3 headline

**Yes: one pymf process carried all four cameras at 720p30 for 10 minutes without a lost frame** [M] (`R/W-PYMF-ALL.json measurements.cameras[*].all_720p30`, `verdicts["pymf_multi|*|720p30"]` all `yes`):

| | Kiyo Pro | C930e | generic | C922 |
|---|---|---|---|---|
| fps (fit) | 30.02 | 30.05 | 25.76 | 30.00 |
| frames, all valid JPEG | 18,013 | 18,032 | 15,469 | 18,011 |
| lost frames (MF sample-time slots) | 0 | 0 | 0 | 0 |
| sample-time gaps > 1.5 periods | 0 | 0 | 0 | 0 |
| arrival gaps > 50 ms: count / max | 8 / 64.3 ms | 0 / – | 0 / – | 0 / – |
| first frame, ms | 597 | 470 | 75 | 299 |
| stop → released, ms | 1,122 | 420 | 272 | 362 |
| 11-11/12, same row order | 29.38 fps, 17,626, 10 gaps / 79 ms, 888, 1,117 | 30.05, 18,041, 0, 474, 374 | 25.76, 15,478, 2 / 50 ms, 88, 305 | refused (bandwidth) |

- **CPU:** 8.39 % of one core for the whole process over the 600 s window. That's 2.1 % per camera, without JPEG decode [M] (`parts.all_720p30.cpu`). 11-11/12 was 7.3 % for 3 cameras.
- **Writer and session:** the frame writer queued 536 and dropped 0 [M]. The open phase took 642 ms for all 4, all released, 0 hung threads [M] (`parts.all_720p30.session`, `.release`).
- **No USB re-arrival during the test** [M] (`arrivals.changes` empty).
- **The Kiyo Pro's 8 arrival gaps** are not lost frames: its sample times have 0 gaps [M].
  - One gap is at 2.6 s, the per-stream stall from handoff §7.
  - At least 4 are at 300.3–302.4 s, right after the 300 s exposure set [M] (`metrics.arrival_gaps.largest`).
  - So these are late deliveries, not dropped frames [I].
- **Kiyo Pro rate:** 30.02 fps tonight against 29.38 on 11-11/12, so it no longer needs the low-rate exemption [M]. Why it changed is [NV].
- **The generic camera's 25.76 fps** is its own rate, as on every API before [M].
- **The C930e and C922 report each other in `same_hub_streaming`** [M]. They share the Intel root hub but sit on separate root ports, which are separate bandwidth domains (W-TOPO). This is not a shared-domain warning [I].

### 2.2 720p60, 180 s (the Kiyo Pro and C922)

[M] (`cam[*].all_720p60`, `parts.all_720p60`)

| | Kiyo Pro | C922 |
|---|---|---|
| negotiated | 60/1, read back ok | 60/1, read back ok |
| result | **`first_sample` timeout (5 s): unreleasable, reader closed, thread abandoned** | 10,939 frames, all valid JPEG |
| delivered fps | – | 59.43 steady (fit 59.43); 11-11/12: 59.21 |
| first frame / release, ms | – | 235 / 318 |

- **The C922 at 60 fps is "yes".** Its 563 sample-time gaps are the 16 ms host-clock grid at 60 fps (`grid_limited` true). They aren't rated (handoff §7) [M].
- **The Kiyo Pro died here** (§5). The session went on and streamed the C922 for its full 180 s. The part exited with rc 5 and 1 abandoned thread [M].
- **So the Kiyo Pro's 60 fps behaviour is untested tonight.** On 11-11/12 it gave 30 fps from this mode.

### 2.3 Exposure sets mid-stream (at 120 s and 300 s)

[M] (`verdicts["pymf_streaming_set|*|exposure"]`)

| | start value | call, ms | frames to change | ms to change | ROI luma, set 1 / set 2 | rating |
|---|---|---|---|---|---|---|
| Kiyo Pro | −7 manual | 2.0, 2.5 | 5, 4 | 191, 174 | 114 → 71 / 71 → 114 | yes |
| C930e | −5 auto | 2.1, 1.8 | 2, 2 | 95, 95 | 117 → 38 / 38 → 112 | yes |
| generic | −7 auto | 1.8, 3.2 | 2, 2 | 111, 109 | 147 → 59 / 58 → 26 | partial |
| **C922** (first time tested) | −5 auto | 3.3, 2.0 | 2, 2 | 95, 110 | 112 → 42 / 42 → 108 | **yes** |

- Every set returned S_OK, read back the value it set, and was restored with readback [M].
- **The generic camera is partial on direction only, the same as on 11-11/12.**
  - Set 1 went from auto (reading −7) to manual −5. That's a longer exposure, yet luma *fell* (147 → 59).
  - Set 2 (−5 → −7) darkened, as expected.
  - Read-back in auto mode is probably not the exposure AE was really using [I].

### 2.4 In-use detection: yes

[M] (`cam[C930e].in_use`, `verdicts["pymf_in_use|046d:0843…"]`)
- The target was the C930e, held by the pymf session.
- IMFSensorActivityMonitor listed it as in use by the pymf process.
- A second wincam open and a second pymf open were both refused with `0xC00D3704` at `first_sample`, class `in_use`.
- The running stream wasn't disturbed: max gap 47.9–49.1 ms, against a limit of 83.3.
- This is the same result as 11-11/12. Only the C930e was in this part; the Kiyo Pro was gated by then.

### 2.5 Verdict for 1.3

- **The question 11-11/12 couldn't answer is now answered: yes** [M].
  - One pure-Python MF process streams all four cameras at 720p30 for 10 min with 0 lost frames.
  - That's about 2 % of a core per camera, with ms-level control sets mid-stream and bounded release (≤ 1.1 s).
  - The 11-11/12 refusal was the topology, now fixed by the move.
- The overall `pymf_multi` label is "partial (Kiyo Pro faulted)" only because of the 720p60 part [M].
- **Still open:**
  1. Product code must keep the other cameras running when one camera hangs at open. pymf multi already does this: it closed the Kiyo Pro's reader and kept the C922 streaming [M].
  2. The Kiyo Pro at 60 fps.
  3. JPEG decode cost is not in the CPU figure (`not_covered`).
  4. Runs longer than 10 min.

## 3. Decision 1.0: the package bump (W-TBUMP, 23:13:50–23:16:44)

### 3.1 Result: yes on 3 cameras

Both recordings ran this time [M] (`R/W-TBUMP.json`, every `T-BUMP` verdict `yes`, `errors` empty).
- **The camera set** was the C930e, generic and C922. The Kiyo Pro was dead and excluded [M] (`measurements.excluded`).
- **skellycam's detect step reads device property bags only and opens no camera** [C] (`tests/w_tbump.py:14`). The connected group was exactly the 3 eligible cameras [M] (`runs.*.cameras`).

| | baseline `2992e64f9` | HEAD `7d06ba2e1` |
|---|---|---|
| versions | Py 3.12.13, OpenCV 4.12.0, numpy 2.2.6, PyAV 18.0.0 | **Py 3.13.18**, OpenCV 5.0.0, numpy 2.5.4, PyAV 19.0.2 |
| health / connect, s | 2.56 / 7.53 | 2.53 / 7.58 |
| frames per camera (equal across cameras) | 1,547 | 1,548 |
| group fps | 25.760 | 25.764 |
| inter-camera grab range, ms: median / p95 / max | 0.261 / 0.535 / 1.178 | 0.278 / 0.521 / 1.063 |
| file size, MB: C930e / generic / C922 | 171.9 / 175.0 / 166.9 | 173.2 / 176.1 / 166.5 |
| codec | h264 mp4 yuv420p 1280×720, 49 keyframes each | same |
| max frame interval per camera, ms | 57.8 / 57.2 / 58.3 | 50.5 / 50.2 / 50.6 |
| server-log errors / tracebacks | 0 / 0 | 0 / 0 |
| shutdown | clean, 0 leftover | clean, 0 leftover |

Source: `comparison.{baseline,head}` [M].
- **Group fps is 25.76** because skellycam runs the cameras in lockstep, and the generic camera's own rate is 25.76 [I].
- **The < 1 ms spread target** is met at the median and p95. The single worst frame-set is 1.18 / 1.06 ms [M].
- **No bump regression is visible** on fps, frame count, spread, sizes (within 0.7 %), codec, CSV headers, errors or shutdown [M].
- As-found controls were restored on all 3 cameras [M] (`restore`).

### 3.2 The 11-11/12 failure didn't recur

- **On 11-11/12**, the generic camera failed to read frames through OpenCV DSHOW with all 4 connected, and both runs died with HTTP 500.
- **Tonight**, it opened and recorded on both trees. The C922 was streaming on its own root port alongside it [M].
- **That fits the bandwidth explanation from 11-11/12** [I]. Tonight's camera set differs (no Kiyo Pro), so it doesn't prove it.
- **The whole-group failure bug was not exercised** (handoff §8 to-do). It's still open [C].

### 3.3 New: HEAD didn't run on the pinned Python

- **Pinned:** the phase-1 worktree pins Python 3.13.13 (`.python-version` and `requires-python = "==3.13.13"`), and its `.venv/pyvenv.cfg` says `version_info = 3.13.13` [C].
- **What ran:** HEAD's server reported **Python 3.13.18** [M] (`comparison.head.versions.python`). The venv's interpreter answers 3.13.18 [M], checked read-only after the run.
- **Why** [M]:
  - The venv's `home` is uv's floating link `…\uv\python\cpython-3.13-windows-x86_64-none`.
  - At **20:14 tonight** that link was moved to `cpython-3.13.18-windows-x86_64-none`, a new install.
  - The 3.13.13 install is still there.
- **What did it** [I]: probably another session installing Python 3.13.18 with uv. W-TBUMP's driver runs the server with `uv run --no-sync`, so uv doesn't re-check the pin [C/I].
- **Effect on tonight's verdict:** it's a patch-level difference and nothing failed. But "HEAD" was not exactly the pinned environment (D13), so tonight's T-BUMP compares baseline with HEAD on 3.13.18 [I].
- **Not changed tonight** (no worktree edits during the run's write-up). The fix is Dom's call: recreate the phase-1 venv against the 3.13.13 install, and have W-TBUMP's preflight fail when the interpreter differs from `.python-version`.

### 3.4 Still open for 1.0

- A **4-camera** skellycam recording. It needs a live Kiyo Pro.
- One T-BUMP recording per major-bump commit (handoff 11-11 §0).

## 4. Decisions 1.3 / 1.11: several cameras at once, MF vs DirectShow (W-MULTI, 23:16:44–23:23:08)

**Three HS cameras at once streamed on every API with no bandwidth refusal.** The Kiyo Pro was dead and left out: 0 of the 45 round spec files name it [M] (`R/W-MULTI/spec_*.json`, `R/W-MULTI.json measurements.runs`).

| API | all-at-once rounds (all 3 HS cameras streamed) | staggered rounds (2.5 s) | refusals | fps: C930e / generic / C922 |
|---|---|---|---|---|
| MF (wincam) | 10/10 | 5/5 | 0 | 29.95–30.05 / 25.68–25.80 / 29.95–29.97 |
| DS (ffmpeg CLI) | 10/10 | 5/5 | 0 | 29.88–30.05 / 25.63–25.81 / 29.83–30.03 |
| PyAV DS | 8/9 with the generic (round 039: generic failed at open, the other 2 streamed); round 040 had 2 cameras | 5/5 with 2 cameras (generic faulted) | 0 | 29.96–30.09 / 25.77–25.82 / 29.96–30.09 |

- **The three-USB-2.0-root-port load is fine** [M]: 38 rounds streamed all three HS cameras at once, and none was refused (no `0x800718CF`, no `OSError(5)`).
  - The predicted loads were 49.3 + 49.3 + 31.9 %, on root ports #8, #13 and #4.
  - Predicted costs matched the observed ones (`predicted_vs_observed`).
- **The G-BW ratings are "untested" by design** [C] (`common/rating.py:557-558`).
  - G-BW rates how refusals are classified, and there were 0 refusal events (`summary_by_api.*.events` 0).
  - No HS domain holds two cameras, so W-MULTI had no conflict pairs to test (`pairs_note`).
  - The label hides that every round fit (§6).
- **Four cameras at once on DS and PyAV: untested.** Four at once through MF: yes, via pymf (§2.1). That session opened all 4 in 642 ms and streamed 600 s.
- **Compared with 11-11/12 §6** [M+I]:
  - That night, the C922+generic pair on the shared HS13 hub was refused in 19/21 events on every API.
  - Tonight, with the C922 on its own root port, there were 0 refusals.
  - So the refusals were the topology.
  - The Kiyo Pro died in the DS all-at-once loop on both previous nights. Tonight it was already dead before W-MULTI.

**The generic camera dropped off the bus once** [M] (`non_bandwidth_failures`, `arrival_attribution`, `run_suite.json faults`):
- 23:22:00.64 (04:22:00.64Z): PyAV round 039. `av.open` didn't return within 6.0 s (class `device_not_ready`). The C930e and C922 streamed.
- 04:22:11.54Z: the generic re-enumerated, 0.4 s after the round ended.
- 04:22:15.83Z: the 1-frame health check failed at plug-in age 4.3 s, so it was faulted (watchdog timeout / hang) and left out of rounds 040–045.
- At the end of the run it was present with problem code 0 [M] (`arrivals.after`).
- That's 4 drop-offs in two nights (3 on 11-11/12). Recorded, not diagnosed (handoff §7).

## 5. The Kiyo Pro

Facts only. No diagnosis (Dom's rule).

**Timeline** [M] (`R/KIYO_PRO_DEAD_20261113T041301Z.json`, `R/W-KIYO.json`, `R/W-PYMF-ALL.json`, `suite_log.txt`):

| UTC | local | event |
|---|---|---|
| 22:27:22 (11-12) | 17:27 | last arrival: Dom's replug, same hub port `…/4.4` |
| 03:59:46 | 22:59:46 | W-KIYO poller starts; poll 0 answered on MF and DS (exposure −7); plug-in age 332.4 min |
| 03:59:49–04:09:51 | | W-PYMF-ALL 720p30, 600 s: 18,013 frames, 0 lost, 30.02 fps; both exposure sets yes |
| 04:09:51–04:09:52 | | polls 1–2 answered on MF and DS (poll 1 MF had waited 594.8 s on camlock behind the pymf session) |
| ≈ 04:09:55 | | the `all_720p60` part starts (Kiyo Pro and C922). The Kiyo Pro negotiates 60/1 (read back ok); its first sample doesn't return within 5 s. pymf records the hang, closes its reader and never re-opens it. The C922 streams on for 180 s. The timeout itself was at ≈ 04:10:00, plug-in age ≈ 342.6 min [I, from the part's start and its 5.3 s open phase] |
| 04:10:02 | | W-KIYO MF poll 3 requested; it waits on camlock (held by the 720p60 part) |
| **04:13:01.098** | **23:13:01** | the part ends; **fault (timeout, unreleasable) and dead mark**; plug-in age 345.6 min (20,738 s) |
| 04:13:01.195 | | poll 3 gets camlock 0.097 s after the mark and reaches the camera; it fails at `activate` (timeout) after 3.0 s |
| 04:13:04 | 23:13:04 | the poller stops ("every polled Kiyo Pro is dead"); its activity check lists the camera in use by process `?:19036` [M; which process that was is NV] |

**State at the dead mark** [M]:
- plug-in age 345.6 min;
- no LogiTune, Logi Options+ or Razer process;
- present, problem code 0, devnode `0x0180600a` (also at the end of W-MULTI);
- `repeats` 0.

**After the dead mark** [M]:
- 0 commands to the Kiyo Pro after poll 3 (`suite_log.txt`; no `vid_1532` command after 23:13:04).
- W-TBUMP excluded it ("dead rule: no command reaches it").
- W-MULTI left it out of all 45 rounds. Its two re-probe slots (04:18:58Z, 04:21:06Z) were recorded as "dead (Kiyo Pro dead rule): not probed".
- **Poll 3** is the known queued-poll gap (11-11/12 §9.1): it was queued before the mark and reached the camera 0.1 s after it. It's not a breach to act on (handoff §5). See §6.

**W-KIYO** [M]:
- 3/4 MF and 3/3 DS polls answered, so the verdict is no.
- Only 7 polls in 23 min, because the poller waits on camlock during W-PYMF-ALL's long sessions (§6).

**Compared with the previous nights** [M]:

| | 11-10 | 11-11/12 | tonight |
|---|---|---|---|
| test / step | W-MULTI `ds_all_together_028` | W-MULTI `ds_all_together_029` | **W-PYMF-ALL `all_720p60`** |
| API | DS (ffmpeg CLI) | DS (ffmpeg CLI) | **MF (pymf)** |
| first failure | DS open timeout, device_not_ready | the same | **`first_sample` timeout at 720p60, unreleasable** |
| what it had just done | – | – | a 600 s 720p30 pymf session, clean |
| poller failure before the fault mark | yes | yes | no (the poller was blocked on camlock; its first failure came 0.1 s after the mark) |
| plug-in age at the mark | 525.8 min | 379.0 min | 345.6 min |
| vendor processes | razer_elevation_service | none | none |
| fault repeats | 4 (no dead rule then) | 0 | 0 |

**Pattern** [I]: this is the first death outside the DS all-at-once loop, the first in an MF path, and the first at a 60 fps request. No further reading of this is offered.

## 6. Harness notes from this run (suite fixes to consider)

1. **W-KIYO is blind during long single-process sessions** [M].
   - The poller takes camlock like any camera command. During W-PYMF-ALL's 600 s and 180 s parts it waited 594.8 s and 179.0 s.
   - So it can't show onset there. It made only 7 polls in 23 min.
2. **The queued-poll gap again** (11-11/12 §9.1) [M].
   - The dead check runs before the camlock wait, not after acquiring it. Poll 3 was requested 3 min before the mark and ran 0.097 s after it.
3. **W-PYMF-ALL marks a Kiyo Pro fault only when the part ends** [M].
   - The hang was at ≈ 04:10:00 [I], the mark at 04:13:01, a 3 min window in which queued commands still pass the dead check.
   - Marking at the hang (pymf multi already knows) would close it.
4. **The G-BW rating shows "untested" when everything fits** [C]. A "fits observed" rating would show that 38 rounds streamed.
5. **W-ENV doesn't match Universal Control** (PreSonus). Add it, since the Revelator shares root port 13 with the generic camera.
6. **W-TBUMP doesn't check that the worktree's interpreter equals `.python-version`** [M]. HEAD ran 3.13.18 against a 3.13.13 pin (§3.3).

## 7. What changes, and what's still open

**No plan decision changes** (plan rev 3.4 stands). What tonight adds:
- **1.3:** the "one pymf process for all cameras" claim now holds for all four cameras at 720p30 [M]. The open items are per-camera fault handling in product code, the Kiyo Pro at 60 fps, the decode cost, and longer runs.
- **1.0:** T-BUMP passes on 3 cameras. The 4-camera recording waits for a live Kiyo Pro. Recreating the phase-1 venv on 3.13.13 (§3.3) is Dom's call.
- **1.11:** the moved topology streams three HS cameras at once on every API without refusal. The 11-11/12 refusals were the topology.
- **The Kiyo Pro** needs a replug again. Its cycling night (W-CYC-KIYO) and the 60 fps checks are still untested.
- **The generic camera** dropped off the bus once more. It's recorded, not diagnosed.
