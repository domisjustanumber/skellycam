# W-MULTI and W-TOPO analysis (Gerald, run 2, suite_20261106T224912Z)

Scope: G-BW cells from W-MULTI (rated per API), the W-TOPO `mapper` and G-BW cells, the Kiyo's state up to and at its 19:04 local fault (it faulted during W-MULTI), and the user messages the run generated.

Sources:
- Results: `W-MULTI.json` (`measurements.runs`, `events`, `messages`, `learned_costs`, `pairs`, `timeline`, `arrival_attribution`, `settle_waits`, `retry_budget`, `summary_by_api`, `verdicts`), `W-TOPO.json`, `W-KIYO.json` (`polls`, `transitions`), `run_suite.json` (`faults`, `kiyo_onset`), `suite_log.txt` lines 953-1230.
- Code: `suite/windows/tests/w_multi.py`, `w_topo.py`, `w_kiyo.py`, `common/rating.py`, `common/topology_model.py`, `windows/suitectx.py`, `windows/helpers/pyav_ds.py`.
- Run 1 for comparison: `../suite_20261106T181941Z/analysis/multi_topo.md` (with its verifier notes), `../suite_20261106T181941Z/reanalysis/W-MULTI.json` and `reanalysis/messages.md`.

Labels: **measured** = read from a result file (file and field cited). **Inferred** = reasoned from the data or the code.
Times are UTC (Z) unless marked local; local = UTC-5. No camera was opened and no suite or result file was changed.

Camera shorthand: C922 = `046d:085c:sn=C922SN01` (HS13 hub), GEN = generic `4c4a:4a55` (HS13 hub port 2), C930e = `046d:0843` (alone on HS07), Kiyo = `1532:0e05` (SuperSpeed on the Thunderbolt xHCI).
Run tags carry a 1-based number; `runs[i]` in the JSON has tag number i+1 (e.g. `runs[36]` = `ds_staggered_037`).

## 0. What ran

W-MULTI ran 18:55:20-19:11:00 local (23:55:20Z-00:11:00Z, 940 s; run 1: 650 s). Measured (`W-MULTI.json` `measurements`):
- **Learn step:** 8 (camera, mode) costs through MF alone. All captured, including the Kiyo (91 frames MJPG, 81 frames YUY2). In run 1 the Kiyo was already dead here.
- **69 concurrent runs, 23 per API** (mf = wincam/MF, ds = ffmpeg CLI with `-vcodec mjpeg`, pyav_ds = PyAV as-is). Per API:
  - 10 all-at-once runs with the four cameras at MJPG 1280x720@30;
  - 5 staggered runs (C922 at t=0, Kiyo 2.5 s, GEN 5.0 s, C930e 7.5 s);
  - 8 pair runs on HS13. In each, C922 ran at one of 1280x720@30, 1920x1080@30, 1280x720@60 or 960x720@30, with GEN at 1280x720@30, two runs per mode.
- **Mode scope.** The plan's `>= 30 fps, >= 720 lines` scope replaced run 1's 640x480@30 and 1080p@5 "fits" pairs. `pairs[0].predicted`: three C922 modes are `over` (81.1%, 98.4%, 98.4% of a microframe), and 960x720@30 is `marginal` (75.2%). `pairs_note` reads "fits-side not testable under mode scope".

## 1. Every rating cell

### 1.1 G-BW `all` / `mf` = **yes** (`W-MULTI.json` `verdicts["G-BW|all|mf"]`)

`rate_bw` (`common/rating.py:524-580`). All 7 criteria are met (measured):

| Criterion | met | detail |
| --- | --- | --- |
| no false "fits" for an observed refusal | true | 0 |
| every refusal classified as bandwidth | true | refusals 21, misattributed 0, device_not_ready_excluded 0 |
| message lists only ports in other domains | true | 0 |
| retry works (final try) | true | final_try_failed 0, first_try_failed_final_ok 0 |
| no false "over" | true | 0 (all 21 "over" events refused) |
| labels better than raw | true | `labels_raw` false (tier `controller_port_number`) |
| classification unambiguous | true | [] (every refusal is 0x800718CF, `bandwidth_certain`) |

**Real.**
- Every MF refusal is `0x800718CF` USB_INSUFFICIENT_BANDWIDTH at `first_sample`: 21/21, with 0 zero-frame starts and 0 re-arrivals (measured: `runs[0..22].cameras[*].error`).
- **Caveat (harness):** the "no false fits" criterion is vacuous under the mode scope. No HS13 event was predicted `fits`. The one `marginal` pair is not scored by `rate_bw`, and cameras alone in their domain produce no event (`w_multi.py:300`). See H13.

### 1.2 G-BW `all` / `ds` = **partial** (`verdicts["G-BW|all|ds"]`)

Same criteria. Six are met (refusals 21, misattributed 0, false fits 0, false over 0, ports OK, labels OK).
- **Failing criterion:** "classification unambiguous on every API" = false, `["ds"]`. Every DS refusal is `OSError(5)`/EIO, so it can only be `bandwidth_probable`.
- `rating.py:578-579` turns that into partial. This matches the plan's section 3 wording: "classification ambiguous on one API" → partial.
- Retry: 9 retried, 9 final OK. **1 first-try failure** (`events.ds[3]` = `ds_all_together_027`, see section 4), reported in `detail` but not penalised (final try decides).

**Real.**
- The rule run 1 inferred holds on 59 DS-family failures: "Could not run graph" means a refusal; "Could not RenderStream to connect pins" or a hang means the device is not ready. Measured from `runs[*].cameras[*].error.ffmpeg_log`:
  - "Could not run graph" in 42/42 HS13 refusals (GEN 25, C922 17);
  - RenderStream in 16/16 Kiyo failures, plus 1 Kiyo hang with an empty log.
- This rating equals run 1's offline re-rating (`reanalysis/W-MULTI.json` `ratings`: ds partial).
- Run 1's live "no" was a harness artefact: B1/B2/B8 have now been fixed in the live code (`w_multi.py:171-193`, `topology_model.py:1077-1110`).

### 1.3 G-BW `all` / `pyav_ds` = **partial** (`verdicts["G-BW|all|pyav_ds"]`)

Identical criteria outcome to ds: ambiguous `["pyav_ds"]`; 21 refusals, 0 misattributed, 0 false fits. 10 retried, 10/10 OK on the first try.

**Real.**
- B9 is fixed: 36/36 PyAV failures now carry an FFmpeg log (measured: `runs[46..68].cameras[*].error.ffmpeg_log`). In run 1, 36/36 were empty.
- The format-prediction fix (B3) was **not exercised on HS13**. Every in-scope C922/GEN/C930e mode resolves to MJPG under PyAV (`measurements.pyav_formats`), and `format_fallback_events` = 0.
  - The only YUY2 prediction was the Kiyo's (`pyav_formats[Kiyo]["MJPG 1280x720@30"] = "YUY2"`), but the Kiyo was already wedged in the pyav_ds phase.
  - So run 1's PyAV YUY2 problem is untested here, not solved. Inferred: it is out of scope, because it only appeared at 640x480@30 and 1080p@5.

### 1.4 W-TOPO `G-BW` = **untested** (`W-TOPO.json` `verdicts["G-BW"]`)

- By design: `w_topo.py:325` always writes `untested("W-TOPO predicts only; W-MULTI observes refusals and rates G-BW")`.
- Evidence `predicted_conflicts`: all_cameras_default_mode 0, all_cameras_720p30 1, pair 720p30 1, pair 640x480@30 0, pair 1080p@5 0.
- **Real; not a defect** (run 1's verifier: presentation only).
- One wrinkle (H12): "all_cameras_default_mode" uses descriptor defaults. These are C922 640x480@30, GEN 1080p30 and Kiyo 640x480@60 (`measurements.default_modes`). They are outside the mode scope and differ from W-MULTI's default plan (all MJPG 1280x720@30), which was refused 30/30 times.

### 1.5 W-TOPO `mapper` = **yes** (`verdicts.mapper`)

All six criteria are met (measured):
- **no admin, 0 requests to devices:** `collector.elevated` false, `requests_to_devices` 0, 0.054 s, 9 hubs, 63 ports;
- **every camera has a domain:** C922 and GEN on `...#13`, C930e on `...#7`, Kiyo on `ss|...8086&DEV_1138...#4`;
- **alt tables for all four cameras;**
- **the three 10-27 Gerald pairs agree:** 81.1% over, 59.7% fits, 62.2% fits;
- **suggested ports are never in the conflict domain** (`suggestion_checks[*].ports_in_conflict_domain` = [] for both scenarios, 13 ports each);
- **labels are not raw** under the shared `label_tier` rule. All nine free root-port labels are tier `controller_port_number`.

**Real**, with one definitional caveat.
- Run 1 rated this cell **partial** only because W-TOPO had a stricter, different raw-label rule (run 1 B7).
- The rule is now shared (`w_topo.py:303-311`, `topology_model.label_tier`), and run 1's re-rating also gives `mapper: yes` (`reanalysis/W-TOPO.json`).
- Whether tier-3 labels ("port 1 (HS01, ...)") count as "better than raw" is a definition choice (run 1 verifier note 8). The board's `_PLD` gives no panel or position.

## 2. Did the predictions hold? (HS13: C922 + GEN)

**Learned costs** (measured: `learned_costs`, `mode_alt_cache`):

| Camera, mode | Alt, packet | Cost µs | Source |
| --- | --- | --- | --- |
| C922 MJPG 1280x720@30 | 9, 992x2 | 39.85 | = 10-27 seed |
| C922 MJPG 1920x1080@30 | 11, 1020x3 | 61.41 | new |
| C922 MJPG 1280x720@60 | 11, 1020x3 | 61.41 | new |
| C922 MJPG 960x720@30 | 8, 800x2 | 32.39 | new |
| GEN MJPG 1280x720@30 | 1, 1023x3 | 61.58 | = seed |
| C930e MJPG 1280x720@30 | 11, 1024x3 | 61.64 | = seed |
| Kiyo MJPG / YUY2 1280x720@30 (SS) | 1, 1024 (+burst) | 6.32 | new (run 1: capture failed) |

The predicted cost equals the open pipe read mid-run in **149/149** streaming observations (mf 55, ds 54, pyav_ds 40; measured: `predicted_vs_observed`). Run 1: 113/113 plus two YUY2 fallbacks.

**Outcome per API and scenario** (measured: `runs[*].cameras[*]`):

| Scenario (prediction, % of microframe) | MF | DS (ffmpeg CLI, MJPEG) | PyAV as-is |
| --- | --- | --- | --- |
| 4 cameras together, 720p30 (over, 81.1) ×10 | 10/10 refused, C922 lost 10 | 10/10: C922 6, GEN 4 | 10/10: C922 7, GEN 3 |
| staggered 2.5 s (over, 81.1) ×5 | 5/5, GEN (t=5.0 s) lost 5 | 5/5 GEN | 5/5 GEN |
| pair C922 720p30 + GEN (over, 81.1) ×2 | 2/2, C922 | C922 1, GEN 1 | GEN 2 |
| pair C922 1080p30 + GEN (over, 98.4) ×2 | 2/2, C922 | GEN 2 | C922 2 |
| pair C922 720p60 + GEN (over, 98.4) ×2 | 2/2, C922 | GEN 2 | C922 1, GEN 1 |
| pair C922 960x720@30 + GEN (marginal, 75.2) ×2 | **both streamed 2/2** | **2/2** | **2/2** |

- **Every "over" prediction was refused on every API: 63/63** (inferred from the table; `summary_by_api.*.false_over` = 0).
- **The marginal 75.2% pair streamed 6/6 on all three APIs.** This reproduces the 10-27 lower edge of the bracket ("pass at 75.2%, refuse at 80.9%", plan section 5) with a different camera mode. Measured: `runs[21,22,44,45,67,68]`.
  - The model calls it "marginal" only because its default fits limit is 93.75 µs (`MARGINAL_FRACTION`, `topology_model.py:60`), and this pair needs 93.97 µs. See H9.
- **Loser pattern** (measured):
  - **MF is deterministic:** the C922 lost all 16 simultaneous over runs (10 all-together + 6 pairs) and GEN lost all 5 staggered runs. In MF the generic commits first: its `first_frame_ms` is 56 ms, against the C922's first-sample failure at 0.34-0.38 s (`runs[0].cameras[2].timings`).
  - **DS and PyAV are mixed:** C922 lost 13 and GEN 7 of the 20 all-together runs; in the pairs, C922 lost 4 and GEN 8.
  - **With a stagger, the camera opened first always wins** (GEN lost 15/15 staggered runs). Same as run 1.
- **Cross-domain "fits" side** (the plan's substitute under the mode scope, section 6 "Mode scope"):
  - The C930e on HS07 streamed in 45/45 four-camera runs at 29.9-30.1 fps.
  - In every MF all-together run it streamed next to GEN on HS13: 61.64 + 61.58 µs = 98.4% of one microframe if the two ports were one domain.
  - So per-root-port domains are confirmed again (measured: `runs[0..9]`, inferred arithmetic).
  - The Kiyo (SS) streamed in 28/28 runs before its onset (MF 15/15, DS 13/13; 29.8-30.0 fps).
  - None of this enters `rate_bw` (H13).
- **Side observations (measured; inferred cause):**
  - GEN delivers 17.1-19.7 fps at MJPG 720p30 in this run (39 successful runs). In run 1 it delivered 25-25.8 fps. The C922 at "1280x720@60" delivered 30.0-30.6 fps (learn: 93 frames in 3 s; `runs[42,43,66]`).
  - Both look exposure-limited (an evening scene: 17:49-19:13 local), not bandwidth-limited: the granted alts are unchanged. The C922 720p60 rate was never verified at 60 fps here.

## 3. How each API surfaced the refusal; device_not_ready classification

- **MF:**
  - `MFCreateDeviceSource` and `SetCurrentMediaType` succeed;
  - the first `ReadSample` fails with `0x800718CF`, at 0.34-0.38 s (C922) or 0.05 s after launch (GEN, staggered);
  - the class is `bandwidth_certain`, and `retry_advised` is true.
- **DS (ffmpeg CLI):**
  - process rc 4294967291; "Could not run graph (sometimes caused by a device already in use by other application)", then "Error opening input: I/O error";
  - open-to-failure time: GEN 0.51-0.75 s, C922 1.17-1.33 s;
  - class `bandwidth_probable`; reason text now ends "[FFmpeg log: 'Could not run graph']".
- **PyAV:**
  - `OSError: [Errno 5] I/O error` at `av.open`, with the same "Could not run graph" dshow log line (now captured);
  - `open_duration_ms`: GEN 327-497 ms, C922 971-1105 ms. The helper's own `error.class` says `in_use` (from the dshow wording). W-MULTI re-classifies this to `bandwidth_probable` with the topology (`runs[48].cameras[2]`). The helper label is misleading but overridden.
- **device_not_ready** (`topology_model.py:1077-1110`; the override applies to `bandwidth_probable`/`other`/`timeout`). It fired 17 times, all on the Kiyo (`non_bandwidth_failures`, 17 entries), and **0 times on HS13** (`summary_by_api.*.device_not_ready_events` = 0):
  - `ds_staggered_037`: hang, 35.27 s open, empty log. Overridden from `timeout` by duration > 2 s.
  - `ds_staggered_038`: RenderStream after 3.14 s.
  - `pyav_ds_*` ×15: RenderStream at **0.33-0.42 s** open.
- **New finding vs run 1:** run 1's verifier found that open duration alone separated the two cases (refusals ≤ 1.47 s, not ready ≥ 3.66 s). That does **not** hold for a wedged device: the 15 Kiyo PyAV RenderStream failures (330-422 ms open) were as fast as GEN's PyAV refusals (327-497 ms) and faster than any C922 refusal. The FFmpeg log is required, and duration is only a backstop (measured `open_duration_ms`; inferred conclusion).
- **Misleading reason text (H3):** every Kiyo failure is labelled "camera not ready (**re-enumerating**)". But the Kiyo never re-enumerated (no arrival in `timeline`), and from 00:04:02 it was registered as faulted with 0x8007001F. The class should say "device fault", not "re-enumerating".

## 4. Generic re-enumeration after DirectShow refusals, and the wait-for-re-arrival policy

**Counts and timing** (measured: `timeline`, `arrival_attribution`, `runs[*].cameras[*].utc_end`):
- **GEN had 25 DirectShow-family run refusals** (ds 14, pyav_ds 11). 18 were followed by a new `LastArrivalDate` **10.03-10.11 s after the failure end** (spread 0.08 s). GEN was seen absent at a check 0.1-0.35 s before each arrival.
- 7 refusals had no arrival within 30 s: ds 032, 034, 037, 043; pyav_ds 057, 060, 061. 72% re-enumerated; run 1 had about 13/19.
  - Inferred: 5 of the 7 started within 6.1 s of a previous arrival. However, 040, 041 and 063 also started 3.5-3.6 s after one and did re-enumerate, so there is no clean predictor.
- **0 of 5 GEN MF refusals** and **0 of 33 C922 refusals** (16 MF, 17 DS-family) were followed by any arrival. Same as run 1: the reset is specific to a DirectShow Run failure on this camera.
- **Timing is now exact.** Run 1's timing came from spec-file mtimes, giving 10.4-10.5 s as an upper bound (±0.3 s). Run 2 has absolute per-camera `utc_end` (`w_multi.py:602-622`). The true delay is about 10.1 s.

**Did the new policy work?** (`w_multi.py:722-764` retry, `696-711` settle; `REARRIVAL_WAIT_S` 25 s)
- **Contamination is gone.** Run 1 had 5 G-BW events contaminated by a device dropping off the bus (`#30`, `#34`, `#38`, `#53`, `#59`). Run 2 has **0**: no slow or RenderStream failure on HS13. The settle wait after each DS-family failure (15 waits) kept the next run from meeting a resetting device (measured: `settle_waits`, `summary_by_api`).
- **Retries:**

  | API | retried | first try OK | waited for re-arrival |
  | --- | --- | --- | --- |
  | mf | 6 (C922 simultaneous 2, GEN staggered 2, C922 pair 2) | 6/6 (C922 61-62 frames, GEN 35 frames in 2 s) | n/a |
  | ds | 9 | 8/9 | 6 tries: arrival in 0.5-4.5 s (5), timed out 16.0 s (1) |
  | pyav_ds | 10 | 10/10 | 6 tries: arrival (5), timed out 17.0 s (1) |

  - The one first-try failure is `ds_all_together_027`, GEN's first DS refusal. At that moment GEN was not yet known as re-enumerating, so try 0 did not wait (`w_multi.py:734`).
  - Try 0 started 00:00:25.96. It failed with RenderStream after 2.50 s, GEN was absent at the check right after it, and it arrived at 00:00:29.158, 10.1 s after the run refusal. Try 1 waited 0.5 s, saw the arrival and got 46 frames.
  - Every retry that waited succeeded, including the two whose wait timed out with no reset.
  - Run 1's MF GEN loser was never retried (budget). It is now covered under the per-key budget (`retry_budget.used`).
- **Answer to plan section 5 ("retry once"):**
  - On MF, retrying the loser once, immediately, works: 6/6.
  - On DirectShow, an immediate retry works only if the camera is not resetting. After a DS refusal of a camera of GEN's kind, wait for its re-arrival (about 10.1 s here) or a short timeout, then retry once: 18/18 OK (ds 8 + pyav 10).
  - No zero-frame start (REPORT finding 19) was seen on any API.
- **Cost of the policy:** settle waits 98.2 s plus retry waits 67.1 s = about 165 s of the 290 s by which W-MULTI grew over run 1. The 7 waits that timed out cost 16-19.5 s each, against a measured reset delay of 10.1 s. See H10.

## 5. The Kiyo up to and at its 19:04 local fault

Measured from `W-MULTI.json` `runs`, `W-KIYO.json` `polls`/`transitions`, `suite_log.txt` 1140-1165 and `run_suite.json` `faults`:

| UTC | Local | What |
| --- | --- | --- |
| 23:56:10 → 00:02:59 | 18:56-19:02 | Kiyo streams in learn (MJPG 91 frames, YUY2 81), 15/15 MF runs (151-302 frames, 30.0 fps) and 13/13 DS runs (`runs[23..35]`, 29.8-30.0 fps). W-KIYO polls run between runs (they share the camera lock, with lock waits up to 18 s) and answer 16/16 controls. |
| 00:03:00.26 | 19:03:00 | Last good poll (`polls` i=189 ds: 16 answered, exposure -7). |
| 00:03:01.28 | 19:03:01 | `ds_staggered_037` starts: C922 at t=0, Kiyo at 2.5 s, GEN at 5.0 s, C930e at 7.5 s. |
| **00:03:03.78** | **19:03:03.8** | **Kiyo DirectShow open (ffmpeg CLI, `-vcodec mjpeg`, MJPG 1280x720@30) starts and hangs for 35.27 s.** The helper's own timeout ends it ("ffmpeg timed out", `runs[36].cameras[1]`). Plug-in age **210.6 min**. The mid-run snapshot (t ≈ 11.5 s) shows the Kiyo's iso pipe open at alt 1 (`observed_pipe` 1024, the only failing camera with a pipe). So the alternate setting was committed and no frame reached FFmpeg (inferred). GEN refused (EIO, 0.52 s); C922 and C930e streamed. |
| 00:03:39.2-00:03:42.5 | 19:03:39 | W-KIYO poll i=190 **mf**: timeout, no codes. Its record says `utc` 00:03:01.219, but that is the request time: `lock_wait_s` 38.0, `elapsed_s` 41.28. |
| 00:03:42.5-00:03:47.7 | 19:03:42 | Poll i=190 **ds**: timeout (5.2 s). |
| 00:03:50.52 | 19:03:50 | `ds_staggered_038`: Kiyo DS open fails after 3.14 s with "Could not RenderStream to connect pins" (`runs[37].cameras[1]`). |
| 00:04:01.9-00:04:02.35 | 19:04:02 | Poll i=191 **mf** (`wincam.exe controls --api mf --read-only`; queued at 00:03:48.37, lock wait 13.5 s): **0x8007001F on 15 of 16 controls** (+0x80070490), 1 answered. `camcmd_scan` marks the Kiyo **faulted at 00:04:02.348704, stage `control_get`**, plug-in age 211.6 min (`run_suite.json` `faults.first_failure`). |
| 00:04:02 → | | Every later poll returns 0x8007001F. W-MULTI keeps opening the Kiyo in all 15 pyav_ds runs: all fail with RenderStream at 0.33-0.42 s (H2). W-MJPEG then gates it. |

Answers:
- **What was running at the fault?** Nothing on the Kiyo. W-MULTI was between `ds_staggered_038` (ended 00:04:01.97) and the first DS pair run (00:04:04), which does not include the Kiyo.
- **Which API returned 0x8007001F?** The **W-KIYO background poller's read-only MF control query**, not a W-MULTI stream.
- **The real onset** was 58 s earlier: a **DirectShow (FFmpeg CLI) open that hung 35 s** at 00:03:03.8. MF never saw a streaming failure, because the MF phase had already finished.
- **Concurrency:** the poller cannot have overlapped a W-MULTI stream. Both take the camera lock, and the 38.0 s and 13.5 s lock waits equal the multi_launch durations (inferred from `suite_log.txt` 1151-1160).
- **Comparison with run 1** (inferred): run 1 wedged 200-224 min after its 09:59 plug-in, in a different test. Run 2's first streaming symptom came at **210.6 min** after the 20:32:29Z replug.
  - Two plug-ins wedged at nearly the same age, under different workloads.
  - That points to plug-in age or cumulative use, not to something specific to W-MULTI. It is the cyc_kiyo group's question; the onset timestamps above should be used, not the summary's 00:03:01.219 (H4).
  - `kiyo_onset.first_failure_activity_processes` lists `LogiTuneAgent.exe` and `RazerAppEngine.exe` at the failed poll. This is noted, not investigated here.
- The Kiyo is alone in its SuperSpeed domain, so it produced no G-BW event before or after the fault. No G-BW cell is affected. Run 1 had 45/45 Kiyo failures in W-MULTI; run 2 got 28 good Kiyo runs and confirmed its SS prediction ("fits", 6.32 µs).

## 6. The generated user messages (verbatim) and judgement

63 message records, **11 distinct texts, 0 null**. Every refusal was foreseen; run 1 had 5 null records (`measurements.messages`). Representative texts follow; the other texts differ only in the noted line.

**(a) MF, C922 loser, 720p30 pair or 4 cameras** (12 records: mf 001-010, 016, 017):
```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, c922 Pro Stream Webcam failed with a USB bandwidth error (0x800718CF: not enough USB bandwidth).
At these settings they need about 101% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 5 (HS05, USB 3, not USB-C), port 6 (HS06, USB 3, not USB-C), port 9 (HS09, USB-C), port 15 (HS15, USB 2.0-only), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 640x480 MJPEG 30 fps (about 13%).
```
**(b) Staggered** (MF 011-015; DS/PyAV staggered 034-038, 057-061), line 2:
"When I opened them both one after another, 2.5 s apart, USB Camera (opened last) failed with a USB bandwidth error (0x800718CF: not enough USB bandwidth)."
For DS/PyAV the line ends "...failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error)."

**(c) DS/PyAV, simultaneous**, line 2 (C922 or USB Camera as loser):
"When I tried to open them both at the same time, USB Camera failed with an error that is probably a USB bandwidth error (a DirectShow start error, FFmpeg: I/O error)."

**(d) 1080p30 and 720p60 pairs**, line 3:
"At these settings they need about 123% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1920x1080 MJPEG 30 fps: 61%, USB Camera 1280x720 MJPEG 30 fps: 62%)."
The 720p60 variant reads "1280x720 MJPEG 60 fps: 61%".

**(e) 720p60 pair stay-here line** (6 records: mf 020, 021; ds 043, 044; pyav 066, 067):
"Or, to keep both where they are, lower c922 Pro Stream Webcam to 1920x1080 MJPEG 5 fps (about 16%)."

The "5 more" hidden ports are HS16, then HS10 hub ports 1, 2 and 4, then HS10 hub port 3 (evidence `header`) last (`messages[0].suggested_ports`).

**Judgement against the plan template (section 5) and the verifier corrections** (inferred unless cited):

| Check | Result |
| --- | --- |
| Template lines 1, 3, 4 and 6 | **Followed.** `shared_hop` names the HS13 Genesys hub. "101%" is relative to the 80% periodic budget, the same load as the plan's 81.1% of a microframe. 40+62 vs 101 is rounding (39.85+61.58 = 101.4 µs). |
| Line 2 code text | **Fixed vs run 1.** EIO now reads "a DirectShow start error, FFmpeg: I/O error", not "access denied". No timeout message this run (no HS13 timeout). |
| Staggered wording | **Partly fixed.** "one after another" is right. But "**2.5 s apart**" is wrong for the four-camera staggered runs: the Kiyo starts between them, so GEN started **5.0 s** after the C922 (`runs[10..14,33..37,56..60].cameras[GEN].t_start_s` = 5.00). See H7. |
| Never HS13 hub/dock ports, never HS07 | **Met.** No HS13 hub port (0424:2137 ports 1/3/4, 05E3:0610 ports 1/3/4) appears in any message, and HS07 has no free port. |
| Expected HS01/02/04/05/06/09/12, HS15/16 last | **Met in substance.** All 7 expected ports are in the visible 8. The order is HS01, 02, 04, 12 (strong evidence), then HS05, 06, 09, 15 (weak). HS16 and the HS10 internal hub ports are hidden. Run 1's misplaced HS10 hub port 3 (PSU phantom) is now last. Minor: HS09 (Type-C `_UPC` flag) sorts after HS05/06, which have no socket evidence at all. Within the weak tier the sort is by port number. |
| "user-accessible" only with evidence beyond `_UPC` | **Met** (corrected vs run 1). It is shown only on HS01/02/04/12 (`_PLD user_visible` plus phantom history or USB-C geometry). |
| No "Type-A" claim for TypeC=0 | Met ("USB 3, not USB-C", "USB 2.0-only"). |
| Group by the controller of the USB 2.0 half | Met. HS12, the USB 2.0 half of TB USB-C #1, is listed under the PCH xHCI. |
| Stay-here, 720p30 / 1080p30 conflicts | Keeps format and 30 fps (B13 fix): "640x480 MJPEG 30 fps (about 13%)". **But** 960x720@30 (32.39 µs) **measurably fits** (6/6 streamed) and keeps ≥ 720 lines. The model excludes it as `marginal` by 0.22 µs (H9). For motion capture, 960x720@30 is the better advice. |
| Stay-here, 720p60 conflict | **Wrong**: offers **1080p@5** (a 12× frame-rate drop, and a mode with a non-deterministic real rate, REPORT finding 20) instead of 640x480@30. `_stay_score` falls back to the largest area once no mode keeps 60 fps (H8). |
| Identical to the offline re-generation | Texts (a)-(c) for 720p30 are word-for-word run 1's `reanalysis/messages.md` Texts 1-5. The live builder equals the offline fixed builder. |

## 7. Run 1 → run 2: what changed and why

| Item | Run 1 (live → re-rated) | Run 2 | Cause |
| --- | --- | --- | --- |
| G-BW mf | yes → yes | yes | unchanged (real) |
| G-BW ds | **no** → partial | partial | **fixes** (device_not_ready, refusal rule) plus the settle wait preventing contamination |
| G-BW pyav_ds | **no** → partial | partial | **fixes** plus **mode scope**: no YUY2 fallback mode is in scope, so the run 1 false fits cannot recur |
| mapper | partial → yes | yes | **fix** B7 (shared label rule) |
| Events contaminated by GEN reset | 5 | 0 | **fix** (settle wait) |
| GEN DS retry first-try failures | 6 of 7 | 1 of 18 | **fix** (wait for re-arrival) |
| MF GEN loser retried | never | 2/2 | **fix** B6 (per-key budget) |
| PyAV FFmpeg logs | 0/36 | 36/36 | **fix** B9 |
| Null messages | 5 | 0 | **fix** plus no unforeseen refusals |
| Fits-side pairs | 640x480 / 1080p@5 fit (MF 4/4) | none in scope; marginal 75.2% fits 6/6 | **mode scope** |
| Kiyo in W-MULTI | 0/45 (dead from the start) | 28/28 until the 00:03:03.8 hang, then 0/17 | **camera** (replug at 15:32 local; wedged again at about 210 min) |
| GEN fps at 720p30 | 25-25.8 | 17.1-19.7 | **scene** (inferred exposure) |
| GEN reset delay | 10.4-10.5 s (upper bound) | 10.03-10.11 s | **fix** (absolute timestamps) |

## 8. Remaining harness bugs

| # | File:line | Bug | Fix | Severity |
| --- | --- | --- | --- | --- |
| H1 | `w_multi.py:354-359` (`_outcome`); `w_multi.py:689` | `timed_out` comes only from the launcher watchdog (`cmd.timed_out`). The pyav_ds helper's own timeout (`pyav_ds.py:757-767`, summary `timed_out` true, "ffmpeg timed out") is dropped. The Kiyo's 35.27 s hang in `ds_staggered_037` was recorded `timed_out: false`, so the hang → health check → `mark_fault` path never ran, and W-MULTI never gated the Kiyo itself. | `timed_out = cmd.timed_out or s.get("timed_out") or s.get("hung")`; also trigger the health check on `code == "timeout"` | medium |
| H2 | `w_multi.py:471-483` (`faulted`) with `suitectx.py:268-273` (`camera_gated`) | `camera_gated` returns a record only for cameras gated at `begin_test`. The suite scanner faulted the Kiyo mid-test at 00:04:02, but W-MULTI did not see it: it opened the Kiyo in 15 more pyav_ds runs (`runs[46..60]`) and skipped the phase re-probe (`w_multi.py:949-950`). `measurements.device_faults` is `{}`. | In `faulted()`, also consult `ctx.camera_faulted(key)` (`suitectx.py:262`); record the gate in `fault_log` | medium |
| H3 | `topology_model.py:1104-1109` | The device_not_ready reason hard-codes "(re-enumerating)". The wedged Kiyo (0x8007001F on polls, no arrival) gets "camera not ready (re-enumerating)" 17 times. | Say "re-enumerating" only when `device_gone` or an arrival is attributed; else "the camera did not start (DirectShow graph not built)". If the camera is faulted in ctx, use class `device_error` / "device fault" | low |
| H4 | `w_kiyo.py:178-183` (`poll_once`) | The poll `utc` is taken before `get_controls` waits for the camera lock. During W-MULTI the waits were 13.5-38 s. So the summary's "first unanswered control poll 00:03:01.219" is about 38 s before the poll actually ran (00:03:39.2), and before the Kiyo's DS open even began (00:03:03.8). | Store `utc_exec = t_utc + lock_wait_s` (or take the timestamp after lock acquisition) and use it in onset/transitions | medium (onset accuracy) |
| H5 | `w_multi.py:664-694` (`classify_run`); summary "First failed camera command per camera (any class)" | Failures inside multi_launch children are never passed to `ctx.record_failure`. The C922 (33 W-MULTI failures) has no entry. GEN's listed first failure is a retry try 0 at 00:00:28.87, although GEN was refused at 23:57:38 (`mf_staggered_011`). | `_ctx_call(ctx, "record_failure", cam, ..., cls=cl["class"], utc=oc["utc_end"], source="W-MULTI multi_launch child")`, or relabel the list as "camcmd-visible failures, bandwidth refusals excluded" | low |
| H6 | `w_multi.py:235-251` (`attribute_arrivals`), `756-757` | The latest failure wins, and retry-try failures are stored with `class: None` (not classified). GEN's arrival at 00:00:29.158 is attributed to `ds_027` retry try 0 (0.285 s), which was itself a not-ready failure (RenderStream, 2.5 s), instead of the run refusal 10.1 s earlier. | Classify retry tries with `classify_camera`; exclude `device_not_ready` failures as causes; prefer the failure whose delay matches the camera's learned reset delay | low |
| H7 | `w_multi.py:795-806` (`message_failure`) → `topology_model.py:1697-1698` | Line 2 uses the run's stagger step (2.5 s), not the start gap between the two colliding cameras (5.0 s with the Kiyo in between). | Pass `loser.t_start_s - first_domain_camera.t_start_s` as `stagger_s` | low |
| H8 | `topology_model.py:1659-1662` (`_stay_score`) | When no mode keeps the requested fps, the score falls through to the largest w·h. For C922 720p60 it offers 1080p@5 instead of 640x480@30 (6 messages). | Score `(same format, fps >= want, min(fps, want), w*h, fps)` | low-medium (user-facing) |
| H9 | `topology_model.py:60` (`MARGINAL_FRACTION`), `135-150`; W-MULTI never feeds `LearnedPolicies` (`topology_model.py:227-281`) | 93.97 µs (75.2%) is predicted `marginal`, yet it streamed 6/6 here and passed on 10-27. The Intel 8086:7A60 policy has no seeded bracket, so stay-here never offers 960x720@30. | Seed the 7A60 bracket `{max_pass_us: 94.0, min_fail_us: 101.1}` from 10-27, or record W-MULTI's observed passes and refusals into `LearnedPolicies` | low |
| H10 | `w_multi.py:73` (`REARRIVAL_WAIT_S` 25 s) | All 18 re-arrivals came 10.03-10.11 s after the failure. The 7 waits that saw no reset cost 16-19.5 s each (about 120 s in total). | Per-camera learned delay; deadline = learned delay + 2 s (about 12 s), and 25 s only before the first reset is seen | low (efficiency) |
| H11 | `w_multi.py:734` | The first DS retry of a camera not yet known to re-enumerate does not wait. `ds_027` try 0 hit the reset (RenderStream). As a test this is fine (it discovers the behaviour), but the product policy derived from it should wait after any DS EIO refusal. | Document it; optionally wait on the first refusal too (bounded by H10) | low |
| H12 | `w_topo.py:219-246` | The "all_cameras_default_mode" scenario uses descriptor defaults (C922 640x480@30, GEN 1080p30, Kiyo 640x480@60), outside the mode scope and unlike W-MULTI's default plan. It predicts 0 conflicts while W-MULTI's default plan was refused 30/30. | Use the scoped default (`ck.scoped` + `ck.default_mode`), as W-MULTI does, or rename it "descriptor_default_mode" | low |
| H13 | `rating.py:547, 558`; `w_multi.py:300` | Under the mode scope the "no false fits" criterion is vacuously met (no `fits` event). The marginal pair's 6/6 success is not scored, and cameras alone in their domain (C930e, Kiyo) produce no event, so the plan's "fits side covered by other domains" leaves no trace in the rating. | Report `met: None` ("fits side untested under mode scope") when no fits/marginal event exists; score marginal outcomes informationally; add a cross-domain criterion ("streamed while the shared domain refused") | low |
| H14 | `w_multi.py:997` (`ck.arrivals_after`) | `arrivals.unexplained_re_arrival` is true for GEN, although all 18 of its arrivals are attributed to its own refusals. The summary bolds GEN as "(re-arrived)". | Mark a change explained when every new arrival appears in `arrival_attribution` with a failure | cosmetic |

**What needs a re-run:** none of the G-BW ratings depend on H1-H14.
- H8/H9 change the message text only. They can be regenerated offline with `w_multi.py --reanalyze`.
- H1/H2 matter for the Kiyo gate (fewer pointless opens after a wedge).
- H4 matters for the Kiyo onset timing used by the cyc_kiyo analysis.
- **Still open:** attended A2 (move a camera to a suggested port and confirm the conflict clears).

## Verifier notes

Every number below was recomputed with scripts from `W-MULTI.json`, `W-TOPO.json`, `W-KIYO.json`, `run_suite.json`, `summary.md`, `suite_log.txt` and one raw poll file (`skellycam-raw/.../W-KIYO/usbvideodevice_1532-0e05_4/poll_00190_mf_change.json`). Each cited code line was checked against the current suite source. No camera was opened, and no suite or result file other than this one was changed.

### Rating cells
All five cells are **confirmed**: the ratings, the failing criteria and the real-vs-artefact calls.
- G-BW mf: 7/7 criteria met.
- G-BW ds and pyav_ds: only `ambiguous_apis` fails. The partial comes from `rating.py:578`.
- ds `first_try_failed_final_ok` is 1 (ds_027); pyav_ds is 0.
- mapper: 6/6 criteria met.
- W-TOPO G-BW: `untested` by design (`w_topo.py:325`).

The outcome table in section 2 is right in every cell. Per API there are 21 over events + 2 marginal = 23 events.

### Findings: confirmed, weakened, corrected
- **F1, F2, F5, F7, F8, F11-F17, F19, F20: confirmed.**
  - F8: delays are 10.029-10.106 s (18/18 attributed arrivals; 7 GEN DS-family refusals had none).
  - F12: the faulting command started at 00:04:02.0756Z (`faults...command_utc_started`). The fault utc 00:04:02.3487 is its end time, which happens to equal the utc of W-KIYO poll i=191 ds.
  - F14: confirmed independently. The raw wincam JSON of poll 190 mf has `utc_started` 00:03:39.4547Z and `utc_finished` 00:03:42.482Z (pan call timed out at 3.0 s).
- **F3 weakened (count and novelty).**
  - The 149 matching pipe observations are 148 streaming cameras (mf 55, ds 53, pyav 40) plus the hung Kiyo in ds_staggered_037 (`ok` false, `observed_cost_us` 6.32). There are no mismatches.
  - C922 MJPG 1080p30 at alt 11 (1020x3) is **not new**: it was a 10-27 seed in run 1's `mode_alt_cache.json` (`source` seed_measured_20261027). W-MULTI re-observed it.
  - Only C922 720p60, C922 960x720@30 and the Kiyo (MJPG and YUY2 720p30) are first observations.
- **F4 weakened (detail).** GEN's MF `first_frame_ms` in the 10 all-together runs is **56-216 ms**, not always 56 ms. The C922 fails at `t_end_s` 0.371-0.379 s. GEN's first frame always precedes the C922 failure, so "MF is deterministic" stands.
- **F6 weakened (numbers); the conclusion stands.**
  - Kiyo PyAV RenderStream `open_duration_ms` is **330-530 ms**, not 330-422.
  - The classifier uses `t_end_s - t_start_s` (`w_multi.py:182-183`), not the helper's `open_duration_ms`. On that measure the Kiyo has 509-748 ms and GEN's PyAV refusals 510-713 ms, so the ranges overlap either way.
  - The DS-family refusal ranges by `open_duration_ms` are GEN 327-533 ms (ds 349-533) and C922 971-1121 ms. Section 3's "GEN 0.51-0.75 s, C922 1.17-1.33 s" uses the t_end - t_start measure.
- **F9 weakened (arithmetic).**
  - There are **19** DS-family retries: ds 9 (3 C922 + 6 GEN) and pyav_ds 10 (4 C922 + 6 GEN). 19/19 succeeded on the final try and 18/19 on the first. Not "18/18 / 17/18", and not "ds 8 + pyav 10" as section 4 says.
  - 12 retries waited for re-arrival (all GEN): 10 saw the arrival and 2 timed out (16.02 s, 17.03 s). All 12 succeeded.
- **F10 weakened.**
  - The sums are right: settle 98.17 s + retry waits 67.11 s; elapsed 649.9 s → 940.3 s.
  - However, only **6** waits ran to the timeout with a real cost: settle after 032 (18.53 s), 043 (19.53 s), 060 (17.03 s) and 061 (17.04 s); retry after 034 (16.02 s) and 057 (17.03 s). They total **105.2 s**, not about 120 s.
  - Three more settle records are `timed_out` with 0 s waited:
    - after 034 and 057, because the retry had already used the 25 s window;
    - after 037, because the Kiyo's 35 s hang had already used it.
- **F18 weakened (arithmetic).** C930e + GEN = 61.64 + 61.58 = 123.22 µs = **98.6%** of a microframe. The 98.4% figure is the C922 1080p30/720p60 + GEN pair. The cross-domain conclusion holds: C930e 45/45, and GEN streamed in all 10 MF all-together runs.
- **Section 4 detail weakened:** "GEN was seen absent at a check 0.1-0.35 s before each arrival" holds for only **12 of 18** arrivals, each within 0.09-0.34 s. The timeline has exactly 12 `absent` events.
  - For the arrivals at 00:04:25, 00:05:30, 00:09:49, 00:10:03 and 00:10:45, no check saw GEN absent.
  - At 00:04:53.657, the only earlier absence belongs to the previous reset cycle (14.6 s before).

### Harness bugs
- **H1-H9 and H11-H14: confirmed in code at the cited lines.**
  - H1: `runs[36].cameras[1]` has `error.class` "timeout", reason "ffmpeg timed out", but `timed_out` false and no `health_check_after_hang`. `_outcome` (`w_multi.py:350`) copies only `cmd.timed_out`.
  - H2: `camera_gated` returns only for keys in `_gated`, which is set at `begin_test` (`suitectx.py:271,434`).
  - **H2 has a further consequence:** the `G-BW|<kiyo>|all` untested verdict (`w_multi.py:998-999`) is never written, and the same file is internally inconsistent. Top-level `device_faults.faulted_at_end` lists the Kiyo, while `measurements.device_faults` is `{}`.
  - H4: a better fix is to take the time from the wincam JSON's own `utc_started`, which is already in the poll output.
  - H5: this also explains why the summary's Kiyo "first failed command" is the 00:04:02 control query and not the 00:03:03.8 DS hang.
- **H10 weakened.**
  - Run 1 saw GEN **removed and re-arrive about 24.6 s** after a refusal (`../suite_20261106T181941Z/analysis/multi_topo.md:291`). The `REARRIVAL_WAIT_S` comment (`w_multi.py:73`) cites that case.
  - A flat 12 s deadline would have missed it.
  - Fix: wait for the learned delay + 2 s, and extend to 25 s only when the camera was seen absent or removed during the wait.

### Missed by the analyst
- **M1 (harness, low; `suitectx.py:493-494`).** `_scan_camcmd` records a failure only when the JSON has `"ok": false`. The wincam `controls` JSON for a timed-out query has `exit_code` 5 and an `error` block but no `ok` key.
  - So the Kiyo's poll-190 control timeouts (mf 00:03:42.48, ds 00:03:47.7) never reached `record_failure`.
  - Together with H5, the suite-wide Kiyo "first failure" is pushed from 00:03:03.8 (DS hang) to 00:04:02.35.
  - Fix: treat `obj.get("ok") is False or (isinstance(err, dict) and obj.get("exit_code") not in (0, None))` as a failure.
- **M2 (scope caveat).** The retry criterion rests on a sample. `RETRIES_PER_KEY` = 2 means only 6/21 (mf), 9/21 (ds) and 10/21 (pyav_ds) refusals were retried, and each retry opens the loser alone. "Retry works" means "the loser streams alone afterwards"; it does not test retrying while the winner keeps streaming.
- **M3 (noted).** The C922's "720p60" delivered 30.5 fps in all 3 runs where it streamed. Bandwidth is unaffected, because the reservation follows the alt (11, 1020x3), not the delivered rate. But no in-scope 60 fps stream was actually verified at 60 fps on Gerald in this run.
