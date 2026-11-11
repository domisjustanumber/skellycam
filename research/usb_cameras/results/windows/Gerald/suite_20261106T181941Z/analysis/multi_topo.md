# W-MULTI and W-TOPO analysis (Gerald, suite_20261106T181941Z)

Scope: the G-BW cells (W-MULTI, rated per API), the W-TOPO `mapper` and G-BW cells, and W-CYC context for bandwidth.
Sources: `W-MULTI.json` (measurements.runs, events, messages, learned_costs, re_arrivals_by_run, verdicts), `W-TOPO.json`, `W-MULTI/mode_alt_cache.json`, `mode_alt_cache.json`, `suite_log.txt`, `W-CYC.json`; code in `suite/windows/tests/w_multi.py`, `w_topo.py`, `common/rating.py`, `common/topology_model.py`, `windows/capkit.py`, `windows/helpers/pyav_ds.py`, `windows/helpers/win_topology.py`.
Labels: **measured** means read from a result file, and the file and field are cited. **Inferred** means reasoned from the data or the code.
Times are UTC (Z) unless marked local. Local time is UTC-5.

Camera shorthand: C922 = `046d:085c:sn=C922SN01`, GEN = generic `4c4a:4a55` (HS13 hub port 2), C930e = `046d:0843` (HS07), Kiyo = `1532:0e05` (SuperSpeed, Thunderbolt xHCI).
Run index `#n` = position in `W-MULTI.json` `measurements.runs`. The run tag number is n+1, so `#21` = `ds_all_together_022`.

## 1. Every rating cell

### 1.1 G-BW, `all`, `mf` = **yes** (W-MULTI.json `verdicts["G-BW|all|mf"]`)

`common/rating.py:253-287` (`rate_bw`). All six criteria are met (measured):

| Criterion | `met` | `detail` |
| --- | --- | --- |
| no false "fits" prediction for an observed refusal | true | 0 |
| every refusal detected and classified as bandwidth | true | refusals 17, misattributed 0 |
| message lists only ports in other domains | true | 0 |
| retry after a refusal works | true | 0 bad (6 retries, all first-try ok) |
| labels better than raw | true | `labels_raw` false |
| classification unambiguous on every API | true | [] |

Verdict: **real**, with two harness caveats.
- **Labels.** "Labels better than raw" passes only because W-MULTI's raw-label rule (`w_multi.py:298-299`: raw only if every label contains `PCIROOT` or `#`) is looser than W-TOPO's (`w_topo.py:234-235`: raw if every root-port label starts with `port `). Both judged the same labels. Under W-TOPO's rule, and the plan's "labels raw → partial", this cell would be **partial**. See bug B7.
- **Retry coverage.** Retries were exercised only for the C922 loser. The retry budget (6 per API, `w_multi.py:136`) was spent on the first six simultaneous runs, so the generic camera as MF loser (staggered runs `#10–#14`) was never retried. See bug B6.

### 1.2 G-BW, `all`, `ds` = **no** (`verdicts["G-BW|all|ds"]`)

| Criterion | `met` | `detail` | Cause |
| --- | --- | --- | --- |
| no false "fits" | **false** | 1 | `ds_pair_..._640x480_30_039` (`#38`): GEN failed during a pair predicted "fits" (59.7%) |
| every refusal classified as bandwidth | **false** | refusals 18, misattributed 1 | same event: class `other` |
| ports in other domains | true | 0 | |
| retry works | **false** | 2 | events `ds_all_together_022/023`: GEN retry try 0 failed ("Could not RenderStream to connect pins"), try 1 succeeded (48 frames) |
| unambiguous | **false** | ["ds"] | every DS refusal is `bandwidth_probable` (OSError 5) |

`rate_bw` returns "no" because `false_fits` and `misattrib` are non-empty (`rating.py:281-282`).

Verdict: **mostly a harness artefact**. The single event that produces "no" is not a bandwidth refusal:
- `#38`: GEN took 3.87 s to fail with "Could not RenderStream to connect pins". That is a graph-build failure, not the "Could not run graph" signature of a refusal. GEN re-arrived at 19:41:04.585Z, 0.7 s after that failure ended. The trigger was GEN's fast DirectShow refusal in `#37` at about 19:40:53.6Z (11.0 s before; see section 4). (Measured: `runs[38].cameras[1].error.ffmpeg_log`, `runs[38].re_arrivals`.)
- The same pair streamed fine in `#39`: C922 150 frames, GEN 125.
- The classifier said `other`, which was correct. But the harness counts any non-NOT_BW failure while another camera streams as a refusal (`w_multi.py:240-241`). It also hard-codes `expected_bandwidth: True` (`w_multi.py:266`), so the event becomes both a "false fits" and a "misattributed" refusal.

The remaining "no" inputs are real:
- **Ambiguity.** FFmpeg dshow gives only EIO. The plan's table makes this a partial.
- **Retry first-try failures.** These come from the camera re-enumerating (section 4).

A fair rating is **partial**.

### 1.3 G-BW, `all`, `pyav_ds` = **no** (`verdicts["G-BW|all|pyav_ds"]`)

| Criterion | `met` | `detail` | Cause |
| --- | --- | --- | --- |
| no false "fits" | **false** | 4 | all four "fits" pairs (`#59–#62`) had a failure |
| classified as bandwidth | **false** | refusals 21, misattributed 5 | `#53` `timeout`; `#59–#62` `other` |
| ports | true | 0 | |
| retry | **false** | 4 | `pyav_ds_all_together_045–048`: GEN try 0 OSError(5), try 1 ok (53 frames) |
| unambiguous | **false** | ["pyav_ds"] | |

Verdict: **mixed**.
- **The four "false fits" are real refusals caused by PyAV's format fallback, not mapper errors.** PyAV negotiated YUY2 for the C922 even though `vcodec=mjpeg` was passed (`pyav_ds.py:311`). Inferred: PyAV does not forward that option to dshow.
  - `#59`: `format_fallback` true, observed pipe 896x3 = 54.18 µs.
  - `#61`: observed pipe 1020x3 = 61.41 µs.
  - Measured: `runs[59].cameras[0].observed_pipe`, `runs[61].cameras[0].observed_pipe`. Predicted costs were 13.08 µs and 16.19 µs.
  - With the format actually used, the domain load is 54.18+61.58 = 115.8 µs (92.6% of a microframe) and 61.41+61.58 = 123.0 µs (98.4%). Both are over (inferred arithmetic).
  - In `#60` and `#62` the C922 itself lost (1.02 s and 1.47 s, the C922's refusal signature) while GEN streamed.
  - `w_multi.py:43-44` states that such refusals "are format fallbacks, not mapper errors", but nothing in the rating implements this. See bug B3.
- **`#53` (`pyav_ds_staggered_054`) is a re-enumeration hang.** GEN's `av.open` hung for 10.33 s. GEN was absent at the next check and re-arrived at 19:43:43.7Z. Artefact (B1, B2).
- **The real part:** PyAV "as-is" can turn a fitting MJPEG plan into an over-budget YUY2 plan without saying so. The retry first-try failures and the ambiguity are also real.

Once the format effect is accounted for, the fair mapper rating is **partial**. The format fallback should be reported as a separate API finding against PyAV-as-is.

### 1.4 W-TOPO `mapper` = **partial** (W-TOPO.json `verdicts.mapper`)

Five criteria are met (measured):
- no admin and 0 requests to devices (`collector.elevated` false, `requests_to_devices` 0, 0.05 s);
- every camera has a domain;
- alt tables for all four cameras;
- the three Gerald pairs agree with 10-27 (81.1% over, 59.7% fits, 62.2% fits; `gerald_pairs[*].agrees` true);
- the suggested ports are never in HS13 (`suggestion_checks[*].ports_in_conflict_domain` = []).

The one failing criterion is "port labels better than raw ACPI names / port numbers" (`met` false). All 9 free root-port labels start with `port ` (`w_topo.py:234-235`, `measurements.labels_raw` true). The rating code turns a labels-only failure into partial (`w_topo.py:256-258`).

Verdict: **real**. The ASUS `_PLD` gives no panel or position (plan section 5: "Labels on this ASUS board are weak"), so the label falls back to tier 3, "controller and port number", e.g. `port 1 (HS01, USB 3, not USB-C, user-accessible)`. The heuristic is crude, but here it reaches the right answer.

### 1.5 W-TOPO `G-BW` = **untested**

This is by design: `w_topo.py:261-262` always writes `rating.untested("W-TOPO predicts only; W-MULTI observes refusals and rates G-BW")`. The evidence lists the predicted conflicts per scenario:
- `all_cameras_default_mode`: 0, because the descriptor defaults are C922 640x480@30 and GEN 1080p30, which gives 59.7%, fits;
- `all_cameras_720p30`: 1;
- the 720p30 pair: 1;
- the 640x480 and 1080p@5 pairs: 0.

Not a defect. The summary puts this cell in the G-BW table, which makes it look like a missing result. It should be shown as "predict only".

## 2. Did the predictions hold? (C922 + generic on HS13)

**Learned (granted) alts vs the cache seeded from 10-27** (measured: `measurements.learned_costs`, `W-MULTI/mode_alt_cache.json`, `mode_alt_cache.json`):

| Camera, mode | Seed (10-27) | Observed alone (MF learn) | Cost µs |
| --- | --- | --- | --- |
| C922 MJPG 1280x720@30 | alt 9, 992x2 | alt 9, 992x2 | 39.85 |
| C922 MJPG 640x480@30 | alt 4, 640x1 | alt 4, 640x1 | 13.08 |
| C922 MJPG 1920x1080@5 | alt 5, 800x1 | alt 5, 800x1 | 16.19 |
| GEN MJPG 1280x720@30 | alt 1, 1023x3 | alt 1, 1023x3 | 61.58 |
| C930e MJPG 1280x720@30 | alt 11, 1024x3 | alt 11, 1024x3 | 61.64 |
| Kiyo MJPG 1280x720@30 | none | capture failed, alt 0 | worst case 69.56 (SS) |

All five measurable entries match the seed exactly. During the concurrent runs, the open pipe read mid-stream equalled the predicted cost in 113 of 113 streaming MJPEG observations (mf 40, ds 39, pyav_ds 34). The only two mismatches are the pyav_ds YUY2 fallbacks above (measured: `predicted_vs_observed`).

**Outcome by API and scenario** (measured: `runs[*].cameras[*]`):

| Scenario (predicted, % microframe) | MF | DS (ffmpeg CLI, MJPEG) | PyAV as-is |
| --- | --- | --- | --- |
| all 4 together, 720p30 (over, 81.1) ×10 | 10/10 refused, C922 lost 10/10 | 10/10 refused: C922 6, GEN 4 (`#30` is re-enumeration) | 10/10 refused: C922 5, GEN 5 |
| staggered 2.5 s (over) ×5 | 5/5, GEN (started 5.0 s) lost | 5/5 GEN lost | 5/5 GEN lost (`#53` hang) |
| pair 720p30 + GEN (over) ×2 | 2/2, C922 lost | C922 1, GEN 1 | C922 1, GEN 1 |
| pair 640x480@30 + GEN (fits, 59.7) ×2 | 2/2 both stream | 1/2 (`#38` re-enumeration) | 0/2 (YUY2 fallback, actually 92.6) |
| pair 1080p@5 + GEN (fits, 62.2) ×2 | 2/2 both stream | 2/2 | 0/2 (YUY2 fallback, actually 98.4) |

- **The predictions held on every API once the format is known** (inferred from the table). 81.1% was always refused. 59.7% and 62.2% always fit with MJPEG; the one DS miss is a re-enumeration failure. 92.6% and 98.4% (YUY2) were refused. This agrees with the 75.2–80.9% bracket.
- **The C930e alone on HS07 streamed in all 63 runs at 30.0 fps**, and the HS13 conflict never touched it. Per-root-port domains are confirmed again (measured).
- **Side observation (measured):** in MJPEG 1920x1080@5 the C922 delivered 29.9 fps on MF (151 frames, `runs[19]`, `runs[20]`) and 29.9–30.0 fps on DS. With the YUY2 fallback it delivered 5.0 fps (`runs[61]`, 26 frames). This matches REPORT finding 20: the rate in that mode is non-deterministic.
- **The Kiyo failed all 45 attempts** (MF `0x8007001F` ×15; ds "Could not RenderStream" ×15; pyav OSError(5) ×15) and its learn step (`non_bandwidth_failures`). Its SuperSpeed domain prediction (61.8% of 112.5 µs, worst case) is untested. It was correctly excluded from G-BW.
- **W-CYC context (measured):** W-CYC opens one camera at a time. `W-CYC.json` contains no 0x800718CF; its only "bandwidth" strings are Kiyo EIO reason text. GEN re-arrived once during W-CYC, at 19:24:27Z (14:24:27 local, `W-CYC.json` `arrivals.changes`), during its OpenCV DSHOW cycles (log lines 1204–1206). So GEN can re-enumerate under DirectShow without any bandwidth contention.

## 3. How each API surfaced the refusal

- **MF (measured, e.g. `runs[0].cameras[0]`)**:
  - `MFCreateDeviceSource` (21–36 ms) and `SetCurrentMediaType` (0.3–1.0 ms) succeed.
  - The first `ReadSample` fails with `0x800718CF` (`hr_name` "HRESULT_FROM_WIN32(6351) USB_INSUFFICIENT_BANDWIDTH", stage `first_sample`).
  - The C922 process ends at 0.37 s; GEN in staggered runs ends at 0.05 s after its launch.
  - The class is always `bandwidth_certain`. No zero-frame start and no re-arrival in the 21 MF runs.
  - **Why the C922 loses every simultaneous MF start (inferred):** in the fitting pairs, GEN's first frame comes at 137 ms and the C922's at about 298 ms (`timings.first_frame_ms`, `runs[0]` GEN vs `runs[17]` C922). GEN commits its alt first, so with MF the race is deterministic (12/12), not random as on 10-27.
- **DS (ffmpeg CLI, `-vcodec mjpeg`)**:
  - Process rc 4294967291 (-5); open fails with "Could not run graph (sometimes caused by a device already in use by other application)" then "Error opening input: I/O error".
  - Signature time: GEN 0.50–0.68 s, C922 1.18–1.35 s.
  - A second signature, "Could not RenderStream to connect pins", appeared:
    - for GEN in `#30` and `#38`, both slow (3.66 s, 3.87 s) and followed within 0.7–1.5 s by a re-arrival;
    - in the GEN retries that failed;
    - for the dead Kiyo in all 15 runs.
  - So **RenderStream = device not ready, Run-graph = refusal** (inferred from 30 events). The classifier ignores the log and labels every case "('Could not run graph')" (`topology_model.py:1123`).
- **PyAV**: `OSError: [Errno 5] I/O error` at `av.open`, same signature times, but `ffmpeg_log` is empty in every pyav_ds failure. The discriminator above is lost (bug B9). One open hung for 10.33 s (`#53`, class timeout).
- **Stagger effects (measured)**: with a 2.5 s stagger the first-started camera of the domain (C922, t=0) streamed in 15/15 staggered runs, and the later one (GEN, t=5.0 s) lost 15/15 on all APIs. A stagger makes the loser deterministic (first admitted wins, REPORT finding 17). It does not make the pair fit.

## 4. Retry once, and the generic camera's re-enumeration

**Retries (measured: `verdicts[...].evidence.events[*].retry`)**:

| API | Retried events | First try ok | Second try ok |
| --- | --- | --- | --- |
| MF | 6, all C922 loser | 6/6 (61–62 frames in 2 s) | n/a |
| DS | 022, 023 GEN; 024–027 C922 | C922 4/4; GEN 0/2 | GEN 2/2 (48 frames) |
| PyAV | 043 C922; 044–048 GEN | C922 1/1; GEN 1/5 | GEN 4/4 (53 frames) |

- **Plan section 5 question ("retry once" on MF and DirectShow):** on MF the C922 never needed a second try. On DirectShow, an immediate retry of GEN failed 6 of 7 times. A second try about 1 s later always worked.
- **Mechanism (inferred from timing):** the retry falls into GEN's re-enumeration window, not a "zero-frame start". The plan's rule needs a DS variant: wait for the re-arrival, or retry twice.

**Re-arrivals of GEN during W-MULTI (measured: `re_arrivals_by_run`, 15 runs flagged; `suite_log.txt` 1311–1415)**:
- 13 new `LastArrivalDate` values, 19:38:07.9Z through 19:44:44.1Z. GEN was also absent at two checks (`#34`, `#53`: `present` true→false).
- **All 13 came in the DS (6) and PyAV (7) phases. There were none in the 21 MF runs**, including 5 MF refusals of GEN.
- No other camera re-arrived. The C922 lost 15 DirectShow-family starts and never re-enumerated.

**Timing (inferred, from log start times ±1 s plus the run-relative `t_end_s`):**
- 11 of GEN's 24 DirectShow-family failures were fast refusals followed by a re-arrival 10.5–11.4 s later: runs 21, 22, 29, 32, 37 (ds) and 44, 45, 46, 47, 55, 58 (pyav). A fixed delay of about 11 s suggests the GEN firmware or `usbvideo` resetting the device after a failed DirectShow Run.
- 5 failures were slow (3.66–10.36 s) and ended 0.7–1.5 s before a re-arrival: `#30`, `#34`, `#38`, `#53`, `#59`. In those cases the open met a device that was dropping off the bus.
- **The 10-27 rerun saw the same thing under MF:** transient `DeviceNotFound` after refusals.

**Effects of the re-enumeration:**
- **Contaminated events.** It contaminated 5 G-BW events: `#30` and `#34`, counted as correct bandwidth_probable refusals; `#38`, counted as a false "fits"; `#53`, counted as misattributed; `#59`, mixed with the YUY2 over-load.
- **Failed retries.** It made the first retry fail 6 times.
- **Wrong run attribution.** It shifted re-arrival attribution by one run, because the check runs before the retry (bug B5).
- **Not seen with MF.** The post-run health check showed GEN OK, problem code 0. The final re-arrival, at 19:44:44Z (14:44:44 local), is this mechanism.

**Real vs artefact:** the re-enumeration is a **camera/driver behaviour** (real; GEN under DirectShow). Counting its failures as bandwidth refusals is a **harness artefact**.

## 5. The generated user messages, verbatim

There are 56 message records: 51 messages, plus 5 null "no conflict predicted" notes for the false-fits events (`messages[34,52,53,54,55]`). Distinct texts, as stored in `measurements.messages[i].message`:

**(a) MF, C922 loser** (`messages[0..9,15,16]`):
```text
c922 Pro Stream Webcam and USB Camera share USB bandwidth: both connect through the same USB hub (USB2.1 Hub 05E3:0610) on port 13 (HS13) of the Intel(R) USB 3.20 eXtensible Host Controller.
When I tried to open them both at the same time, c922 Pro Stream Webcam failed with a USB bandwidth error (0x800718CF: not enough USB bandwidth).
At these settings they need about 101% of what that USB 2.0 link allows (c922 Pro Stream Webcam 1280x720 MJPEG 30 fps: 40%, USB Camera 1280x720 MJPEG 30 fps: 62%).
Suggest moving one of those cameras to any of the following controller ports:
  Intel(R) USB 3.20 eXtensible Host Controller: port 1 (HS01, USB 3, not USB-C, user-accessible), port 2 (HS02, USB 3, not USB-C, user-accessible), port 4 (HS04, USB 3, not USB-C, user-accessible), port 9 (HS09, USB-C, user-accessible), port 12 (HS12, USB-C, user-accessible), port 3 of the hub 'USB2.0 Hub' 05E3:0608 (on port 10 (HS10)), port 5 (HS05, USB 3, not USB-C, user-accessible), port 6 (HS06, USB 3, not USB-C, user-accessible), and 5 more
Or, to keep both where they are, lower c922 Pro Stream Webcam to 1920x1080 MJPEG 5 fps (about 16%).
```
**(b) MF, GEN loser (staggered)** (`messages[10..14]`): identical except line 2: "When I tried to open them both at the same time, USB Camera failed with a USB bandwidth error (0x800718CF: not enough USB bandwidth)."

**(c) DS/PyAV, probable** (`messages[17..]`, C922 or USB Camera as loser), line 2: "When I tried to open them both at the same time, USB Camera failed with an error that is probably a USB bandwidth error (access denied (probably bandwidth: see details))." The other lines are identical to (a).

**(d) PyAV timeout** (`messages[46]`), line 2: "When I tried to open them both at the same time, USB Camera failed with a USB bandwidth error (timeout)."

The "5 more" are HS15, HS16, and HS10 hub ports 1, 2 and 4, in that order (`suggested_ports`, all rank 1).

**Judgement against the plan's template and the verifier corrections (inferred unless cited):**

| Check | Result |
| --- | --- |
| Template lines 1, 3, 4 and 6 | Followed. `shared_hop` names the HS13 Genesys hub and controller. "101%" is the percentage of the 80% periodic budget (`build_message` docstring), which is the same load as the plan's 81.1% of a microframe. 40+62 vs 101 is rounding. |
| Never HS13 ports or HS07 | **Met.** No HS13 hub or dock port and no HS07 in any of the 51 messages. HS07 is excluded by load: C930e 61.64 µs + mover's cost exceeds 100 µs. Measured: `suggested_ports[*].domain_key`. |
| Expected HS01/02/04/05/06/09/12, HS15/16 last | **Partly met.** All 7 expected ports appear among the 8 shown. But HS10 hub port 3 is placed 6th, ahead of HS05/HS06. HS15/16 are hidden in "5 more" and followed by HS10 hub ports 1, 2 and 4, so they are not last. |
| HS10 hub port 3's rank | The rank comes from "socket evidence": `_PLD user_visible; phantom history: HX1500i Power Supply` (W-TOPO `free_ports`). A PSU's USB lead goes into an internal header, so this is evidence of a header, and the port should sort last. |
| Internal hub ports allowed? | Yes: the correction "Candidate ports include empty ports on hard-wired internal hubs" allows them. But the label "port 3 of the hub 'USB2.0 Hub' 05E3:0608 (on port 10 (HS10))" means nothing to a user. |
| "user-accessible" on HS05/06/15/16 | Comes from `_UPC` connectable (`topology_model.py:1286`), although their ACPI names are inferred (`acpi_name_inferred` true) and the correction says `_UPC` over-reports. HS15/16 are "likely headers" in the plan. |
| No "Type-A" claim for TypeC=0 | Met ("USB 3, not USB-C"). |
| DS line 2 | **Wrong code text.** OSError(5) is POSIX EIO ("I/O error", as FFmpeg prints), not Win32 ERROR_ACCESS_DENIED (also 5) (`topology_model.py:1500-1503`). The nested parentheses and "see details" point at nothing. |
| Timeout line 2 | **Wrong.** It asserts "a USB bandwidth error" for a hang that was a re-enumeration (`topology_model.py:1552-1556`). |
| "at the same time" | Inaccurate for the staggered runs: the cameras were opened 5.0 s apart. |
| "Stay where you are" | Suggests MJPEG 1080p@5. `stay_here_alternatives` scores by w·h·fps (`topology_model.py:1470`), so 10.4 Mpx/s at 5 fps beats 640x480@30 (9.2 Mpx/s, 59.7%). For motion capture a 5 fps mode is the wrong advice. The C922's real rate in that mode is non-deterministic (5.01/15.76/30.0; 29.9 today). It should prefer keeping the frame rate. |
| No message for unforeseen refusals | For the 5 false-fits events the user would get no explanation at all (`messages[34,52-55].message` null). |

## 6. Is G-BW yes for mf and no for ds/pyav_ds fair?

- **mf yes:** the core claim is fair. The mapper predicted every MF outcome. 0x800718CF is unambiguous at the first ReadSample. The ports avoid HS13 and HS07. Retrying the loser alone worked.
  - On the plan's own wording it is **partial**: the labels are tier 3 (W-TOPO says raw) and the message ranking has the HS10 and HS15/16 issues.
  - The retry evidence covers only the C922.
- **ds no:** **not fair**. One re-enumeration failure drives the "no", and the classifier had labelled it `other` correctly. The fair rating is **partial**: DS can only give `bandwidth_probable`, and an immediate retry fails on GEN.
- **pyav_ds no:** **not fair as a mapper rating** (format fallback plus one re-enumeration hang). It is **fair as a warning** that PyAV-as-is cannot be planned for, because it silently picks YUY2. Report it as mapper partial, plus a separate PyAV format finding.
- **Re-rating:** this can be done offline from the stored JSON for most of the fixes (section 7).

## 7. Harness bugs

| # | File:line | Bug | Fix | Severity |
| --- | --- | --- | --- | --- |
| B1 | `w_multi.py:266` | `expected_bandwidth` hard-coded True, so re-enumeration, timeout and format-fallback failures become "misattributed" | Set it per loser: False if the camera's re-arrival or absence falls within the run (+15 s), if the FFmpeg log has "RenderStream", or if the format actually used differs from the predicted one | high (flips ds and pyav_ds) |
| B2 | `w_multi.py:240-241` | `counts_as_refusal` true for any class not in NOT_BW (incl. `other`, `timeout`) when another camera streams | Count only `bandwidth_*`. Add a `device_not_ready` class (RenderStream, re-arrival, or open time over 2 s); report these separately | high |
| B3 | `w_multi.py:151-157`, `209`; `pyav_ds.py:311` | pyav_ds is predicted as the requested MJPEG mode, but PyAV negotiates YUY2 where offered (`vcodec` ignored). The docstring at `w_multi.py:43-44` says so, but `rate_bw` counts the result as false fits | Predict pyav_ds with the format it will get (W-FMT raw availability, YUY2 cost from the seed), or tag the event `format_fallback` and exclude it from false fits; report the fallback as its own finding | high |
| B4 | `w_multi.py:347` | W-MULTI creates a fresh `ModeAltCache` instead of extending the run-root cache W-TOPO seeded (`w_topo.py:12,158`), so seeded YUY2 and other modes are unavailable to prediction and to stay-here | `ModeAltCache.load(ctx.out_dir/"mode_alt_cache.json")`, add learned entries, save both | medium |
| B5 | `w_multi.py:250-256` vs `274-276` | Re-arrival check runs before the retry, so re-arrivals during the retry are pinned to the next run (e.g. 19:38:07.9Z during ds_022's retry is logged after ds_023) | Record UTC start and end per run and per retry; check arrivals after the retry; attribute by timestamp; also store `last_removal` | medium |
| B6 | `w_multi.py:136`, `274` | Retry budget of 6 per API is used up by the first 6 events (all C922 simultaneous), so the MF GEN loser and the pairs are never retried | Budget per (api, loser camera, run kind), e.g. 2 each | medium |
| B7 | `w_multi.py:298-299` vs `w_topo.py:234-235` | Two incompatible "raw label" rules: G-BW mf says not raw, mapper says raw | One shared `label_tier()` in `topology_model`; raw = tier "controller and port number" or lower; use it in both tests | medium (flips mf yes→partial) |
| B8 | `topology_model.py:1121-1125`; `capkit.py:406-421` | Classifier ignores `error.ffmpeg_log`; the reason text hard-codes "Could not run graph" even when the log says "Could not RenderStream to connect pins" | Pass the log lines to `classify`; RenderStream → `device_not_ready`; Run-graph plus contention → `bandwidth_probable` | medium |
| B9 | `pyav_ds.py:79-150`, `330-335` (`_StderrCapture`) | In-process PyAV open errors carry an empty `ffmpeg_log` (36 of 36 pyav_ds failures), so the B8 discriminator is unavailable | Capture through `av.logging` (callback or `Capture`) instead of stderr; check that the capture is non-empty in a self-test | medium |
| B10 | `topology_model.py:1500-1503` | OSError(5) (EIO) rendered as "access denied (probably bandwidth: see details)" | "a DirectShow start error (FFmpeg: I/O error)"; drop "see details" or add the detail | low |
| B11 | `topology_model.py:1552-1556`; `w_multi.py:268-270` | A `timeout` loser gets "failed with a USB bandwidth error (timeout)" | Use the bandwidth wording only for `bandwidth_*`; otherwise "did not start (timed out); this may be a bandwidth problem" | low |
| B12 | `topology_model.py:1551` | "at the same time" also for staggered starts | Pass the stagger and loser order to `build_message` | low |
| B13 | `topology_model.py:1470` | Stay-here score w·h·fps prefers MJPEG 1080p@5 over 640x480@30 | Score (same format, fps ≥ requested, w·h); fall back to lower fps only if no mode at the requested fps fits | low |
| B14 | `win_topology.py:302-308`; `topology_model.py:1412`, `1286` | Any phantom device counts as socket evidence (a PSU marks an internal header), and "user-accessible" comes from `_UPC`. HS10 hub port 3 ranks above HS05/06; HS15/16 are not last | Treat phantoms of internal-header devices (PSU, AIO, RGB and BT controllers) as header evidence and sort them last; omit "user-accessible" when only `_UPC` supports it; rank likely headers (HS15/16, internal hub ports) last | low |
| B15 | `w_topo.py:261` and the summary builder | The W-TOPO G-BW "untested" cell looks like a missing result | Label it "predict only", or omit it from the G-BW table | cosmetic |

**What has to run again:**
- **Offline re-rate** (no cameras) from the existing `W-MULTI.json` and `W-TOPO/snapshot.json`: B1, B2, B3 and B7, plus rebuilding the messages after B10–B14. All the needed data is already stored: `format_fallback`, observed pipes, re-arrivals and the ds FFmpeg logs.
- **Re-run W-MULTI** (about 11 min, cameras): B4, B5, B6, B8 and B9, which need new data (pyav logs, retry coverage, accurate re-arrival timing). Suggested extra: after any DirectShow refusal of GEN, wait for its re-arrival (up to 15 s) before the next run, so later events are not contaminated.
- **Re-run W-TOPO** (1 s, no camera opens): B7, B13 and B14.
- **W-CYC:** no re-run needed for bandwidth.
- **Attended A2:** move a camera to a suggested port and confirm the conflict clears. Still open.


## Verifier notes

Adversarial check, 2026-11-06. I recomputed every number in sections 1–5 from `W-MULTI.json`, `W-TOPO.json`, both `mode_alt_cache.json` files, `W-CYC.json` and `suite_log.txt` with throwaway scripts, and I read the cited code. No cameras were opened and no suite or result file was changed. To get run start times finer than the 1 s log, I used the mtime of each `W-MULTI/spec_<tag>.json`, which is written just before launch. Delays computed from it are therefore **upper bounds** (inferred precision about ±0.3 s).

### What holds (measured, recomputed)

- **Rating inputs.** These match `verdicts[...]` exactly:
  - mf: 17 refusals, 0 false fits, 0 misattributed, 6 retried, all first-try ok.
  - ds: 18 refusals, 1 false fit (`#38`), 1 misattributed, retry_bad 2.
  - pyav_ds: 21 refusals, 4 false fits (`#59–#62`), 5 misattributed (`#53` timeout, `#59–#62` class `other`), retry_bad 4.
  - 56 message records, 5 of them null.
  - Each API ran 17 runs predicted over, and every one had a refusal.
- **Learned costs.** All 5 learned (camera, mode) costs equal the seeded run-root cache entry for the same key. Predicted cost equals the observed open pipe in 113/113 streaming observations (mf 40, ds 39, pyav_ds 34). The only mismatches are the two pyav_ds YUY2 cases: 896x3 = 54.18 µs and 1020x3 = 61.41 µs. The domain loads 92.6% and 98.4% of a microframe are correct arithmetic.
- **Losers.**
  - MF: C922 lost 12/12 simultaneous starts; GEN lost 5/5 staggered.
  - DS all-together: C922 6, GEN 4. PyAV: C922 5, GEN 5.
  - Staggered: C922 streamed 15/15 and GEN lost 15/15.
  - Fitting MJPEG pairs: MF 4/4, DS 3/4.
- **Re-arrivals.** 13 distinct new `last_arrival` values (DS phase 6, PyAV phase 7), 15 runs flagged, GEN absent at 2 checks (`#34`, `#53`), none in MF. The W-CYC re-arrival at 19:24:27Z falls inside the 73 s `opencv_inproc` cycle run of GEN (log lines 1206–1207).
- **Error signatures.**
  - DS FFmpeg logs: Kiyo RenderStream 15; GEN run-graph 9 and RenderStream 2 (`#30`, `#38`); C922 run-graph 7.
  - PyAV failures: 36, all with an empty `ffmpeg_log`.
  - The failed DS retry of GEN logs "Could not RenderStream to connect pins".
- **Messages and code.**
  - Message wording, port order and the stay-here choice match the cited code (`topology_model.py:1286`, `1412`, `1470`, `1503`, `1551-1556`).
  - `w_topo.py:234-235`, `256-262` and `w_multi.py:136`, `240-241`, `250-256`, `266`, `274-276`, `298-299`, `347` are cited correctly.
  - `ModeAltCache.__init__` (`topology_model.py:584`) does not load from `path`, so B4 is real.

### Corrections to the findings

1. **HS07 is not "excluded by load"** (section 5 table). There is no free port in HS07's domain at all: the C930e is plugged straight into root port 7, and `W-TOPO.json` `free_ports` has no HS07 entry. The criterion passes trivially for HS07.
2. **The C930e ran in 45 runs, not "all 63"** (section 2). It is not part of the pair runs. It streamed in 45/45 at 29.84–30.08 fps.
3. **F10, re-enumeration timing.** It is tighter and less universal than reported:
   - After a fast GEN DirectShow refusal, the re-arrival comes **10.4–10.5 s** after the failure ended (not 10.5–11.4 s). Runs: 21, 22, 29, 32, 37, 44, 45, 46, 47, 55, 58 (11 runs).
   - Slow failures end **≤0.6 s** before a re-arrival (not 0.7–1.5 s). Runs: `#30`, `#34`, `#38`, `#53`, `#59`.
   - Missed: 8 of the 19 fast GEN refusals were **not** followed by an arrival at about +10.4 s:
     - `#33` and `#52` were followed by a **removal**: GEN was absent at the next check and re-arrived about **24.6 s** after the refusal. The next run's open hung for 10.3 s (`#34`, `#53`).
     - `#31`, `#35`, `#43`, `#54`, `#56` and `#61` had no attributable arrival. `#31` and `#54` also sit exactly 24.6 s before an arrival that a later refusal explains at +10.4 s, so they are ambiguous.
   - So the reset is frequent (about 13 of 19 refusals) but not certain. It is not triggered by the C922's refusals, or by GEN's own MF refusals.
4. **F8, retry mechanism.** Recomputed from the same timestamps:
   - GEN's first DS/PyAV retry fails in **exactly** the cases where a +10.4 s re-arrival follows: events ds_022/023 = runs `#21`/`#22`, pyav_ds_045–048 = runs `#44–#47`.
   - The one first-try success (pyav_ds_044 = run `#43`) is the one retried GEN refusal with no re-arrival.
   - Try 0 is a slow 3.7 s failure (the device dropping off, like `#30`/`#38`). Try 1 starts within about 0.1 s after the re-arrival (e.g. `#21`: re-arrival 19:38:07.885, try 1 at about 19:38:08). Try 1 works because the device is back.
   - "A second try 1 s later always works" is therefore a coincidence of timing (6.3 s run + 3.7 s failed try + 1 s sleep ≈ 10.4 s). The robust rule is: **after a DirectShow refusal of this camera, wait for its re-arrival (up to about 25 s) or retry for about 11 s**, not "retry twice".
   - Plan section 5's "retry once" cites a zero-frame start (finding 19). This is a different failure (an error at open), so the analyst's "needs a DS variant" stands.
5. **F5, RenderStream discriminator.** "RenderStream = not ready, run-graph = refusal" is sufficient but not necessary. `#34` failed with **"Could not run graph"** after 10.36 s, and GEN was gone at the next check. Open duration separates the two cleanly in this run:
   - refusals: GEN 0.50–0.68 s, C922 1.02–1.47 s;
   - not ready: 3.66–10.36 s.
6. **F12, YUY2 cause.** It is measured only for `#59` and `#61`, where the C922 streamed with `format_fallback` true. In `#60` and `#62` the C922 itself failed, so its format is unknown; "really over budget" is inferred there. `#59` is doubly confounded: GEN's failure was slow (3.9 s) and was followed 0.6 s later by a re-arrival, so it is device-not-ready as much as over-budget.
7. **F4, MF loser.**
   - GEN's first frame comes at 56–152 ms (not "about 137"); the C922's at 298–313 ms.
   - The deterministic loser is MF-specific: under DS and PyAV the all-together loser was mixed.
   - The 10-27 "start race" (RERUN_20261027 line 173) was the C930e + generic pair, so "not random as on 10-27" compares different pairs.
   - The 10-27 rerun saw transient MF `DeviceNotFound` of GEN after an MF refusal. Today GEN had 5 MF refusals and no re-arrival. That contrasts with today's DS behaviour rather than repeating it (section 4 says "saw the same thing").
8. **F15, label rule.** Under `rate_bw`'s own definition (`rating.py` docstring: raw = "ACPI names / location paths") the tier-3 labels are **not** raw, so mf yes is defensible. It is partial only under W-TOPO's stricter rule. The plan's fallback chain lists "controller and port number" as a legitimate tier and does not define "raw". So B7 (two rules) is real, but which rating is "fair" is a definition choice, not a fact.
9. **F18, socket evidence.**
   - HS10 hub port 3's socket evidence is `_PLD user_visible; phantom history: HX1500i`. An internal hub port reporting `_PLD user_visible` is itself the suspicious part, not only the PSU phantom.
   - HS09 also has `acpi_name_inferred` true.

### Missed findings

- **GEN delivers 25.0–25.8 fps at MJPEG 720p30**, both in the learn step (79 frames in 3 s) and in all 34 successful concurrent runs, while the C922 and C930e give 30. That makes it bandwidth-independent. Inferred: probably exposure-limited (scene light), worth checking against W-MJPEG before calling it a camera property.
- **Re-arrival attribution is shifted by one run systematically, not only during retries.** A 10.4 s reset after a refusal at t ≈ 0.6 s (simultaneous, run ≈ 6.3 s) or t ≈ 5.5 s (staggered, run ≈ 13.7 s) always lands after that run's arrival check. Every `re_arrivals_by_run` entry for a fast refusal names the *next* run. The comment at `w_multi.py:249` ("pinned to the run that caused them") is wrong in general. Runs also carry no absolute UTC start time, so this cannot be fixed offline except through spec-file mtimes.
- **`rate_bw` (`rating.py:253-287`) design gaps:**
  - `retry_ok` uses `tries[0]` only.
  - There is no criterion for "predicted over but both streamed". A mapper that always says "over" would pass. This has no effect today, because every over run was refused.
- **The B3 fix is incomplete.** The seeded cache has C922 YUY2 640x480@30 (alt 10, 896x3), which matches the observation exactly, but no C922 YUY2 1920x1080@5. That entry was observed at 1020x3, so it must be added for the 1080p@5 pair.

### Harness bug verdicts

- **B1 is real, but its fix is wrong.**
  - `rate_bw` computes `false_fits` from `observed_refused` and `predicted_verdict` only and ignores `expected_bandwidth`. So setting `expected_bandwidth` False would clear "misattributed" but leave `#38` (and `#59–#62`) as false fits.
  - A "re-arrival within run + 15 s" test would also mark the 11 genuine fast refusals as not-bandwidth, because they are followed by a reset at +10.4 s.
  - Correct fix: decide per loser at classification time (`w_multi.py:229-241`). `device_not_ready` = open failed after more than 2 s, or the FFmpeg log has RenderStream, or a removal or re-arrival of that camera happened within about 1 s of the failure end. Set `counts_as_refusal` False for it.
- **B2 is real, but its fix is wrong.** "Count only `bandwidth_*` classes" makes the false-fits criterion vacuous: `classify_failure` returns `bandwidth_*` only when the prediction is over, so an unforeseen refusal at a "fits" prediction would never be counted. Keep the others-streaming rule and add the `device_not_ready` exclusion above.
- **B8 is real.** The fix must also use open duration, or `#34` would still be `bandwidth_probable`.
- **B9 is real** (36/36 empty logs, measured), but the cause is unproven. `_setup_logging` deliberately restores FFmpeg's C log callback ("no GIL"), so switching to a Python `av.logging` callback may reintroduce what was avoided. Self-test it first.
- **B5 is real and broader** (see above).
- **B3, B4, B6, B7, B10, B11, B12 (the "at the same time" wording, part of the analyst's JSON entry for lines 1551-1556), B13 and B14 are real as stated.** For B14, the heuristic needs care: a device-name list for "internal-header" phantoms is brittle.
- **B15 is not a bug.** The cell is by design; it is a presentation choice.

### Fair ratings after the fixes (offline re-rate, my script)

| Cell | Fair rating | Why |
| --- | --- | --- |
| G-BW ds | partial | Excluding `#30`, `#34` and `#38` as device-not-ready leaves 15 refusals, 0 false fits, 0 misattributed. retry_bad is 2 (first-try rule) and the classification is ambiguous. |
| G-BW pyav_ds | partial | Same, provided `#60–#62` are predicted with the YUY2 cost. |
| G-BW mf | yes (or partial under W-TOPO's label rule) | Unchanged. |

All of this can be done offline from the stored JSON. That covers the durations, the DS logs and `format_fallback`; it does not recover the PyAV logs or the absolute timestamps. Re-runs:
- **W-MULTI:** for B4, B5, B6 and B9, ideally with "wait for GEN's re-arrival after each DS refusal".
- **W-TOPO:** for B7, B13 and B14.
