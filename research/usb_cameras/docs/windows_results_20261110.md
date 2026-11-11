# Windows results, Gerald, 2026-11-10/11

Full write-up of the third unattended `suite/windows` run on Gerald, the first under the plan in
[capture_stack_options_plan.md](capture_stack_options_plan.md) §6 and Dom's decisions in its §8. The short
version is the executive summary [WINDOWS_RUN_20261110_EXEC_SUMMARY.md](../WINDOWS_RUN_20261110_EXEC_SUMMARY.md).
Every number below was re-read from the result JSONs. Where the executive summary and the raw data disagree, this
document uses the raw data; §12 lists the differences. The previous run's write-up is
[windows_results_20261106.md](windows_results_20261106.md) ("11-06" below).

Labels, as in the 11-06 doc: *measured* (a result file and field support it) and *inferred* (reasoning). Times are
local (UTC−5) with UTC in brackets where it matters. Plug-in ages are minutes since the camera's last PnP arrival.

**What was run.** `suite/windows`, full profile, 2026-11-10 23:00:05 → 2026-11-11 04:24:24 local
(04:00:05Z → 09:24:24Z, 5 h 24 min; the summed estimate was 7.0 h) ([run_suite] `utc_started`, `utc_finished`,
`eta_s`). All 18 tests plus the background Kiyo poller (W-KIYO) ended `ok` with 0 errors ([summary] Tests table).
- **Scope:** tier 0 only. No registry or driver change; no UVC PTS/SCR. W-ENV finds the metadata value on none of
  the four current camera instances, so the 11-09 revert held ([W-ENV] `metadata_registry.current_instances`).
  Streaming tests used only modes with exactly 720 lines at ≥ 30 fps, raw formats included ([W-RAW] `mode_scope`).
- **Cameras, as found** ([summary] "USB link at run start"; [W-ENV] `cameras_health`):
  - Kiyo Pro (1532:0e05), SuperSpeed on the Thunderbolt xHCI, replugged 17:07:35 on 11-10, plug-in age 352.5 min at
    the start;
  - C930e (046d:0843), high-speed on port 8 of the Intel xHCI, replugged 17:07:46, age 352.3 min;
  - generic 4c4a:4a55, high-speed behind the HS13 hub, age 1825.2 min (since the 11-09 boot);
  - C922 (046d:085c, serial key), behind the same HS13 hub, age 1825.2 min.
- **Machine state** (*measured*, [W-ENV] `power`, `processes`): Balanced plan, USB selective suspend on, USB 3 LPM
  "Moderate power savings". Of the vendor software only `razer_elevation_service.exe` was running. No LogiTune
  process and no RazerAppEngine. Firefox was open. Policy traps: none found ([W-POLICY] `policy_traps` yes).
- **Order:** W-ENV, W-POLICY, W-TOPO, W-ID, W-FMT, W-FMT-NOGRAB, W-CTRL-LIST, W-MJPEG, W-RAW, W-TS, W-PYMF,
  W-CTRL-EFFECT, W-AUTO, W-OCV-CTRL, W-CYC-KIYO, W-MULTI, W-PYAV-LIST, W-CYC ([run_suite] `test_order`). The Kiyo's
  cycles ran before W-MULTI, so they were complete before it wedged.

**Bottom line.**
- **MF native is still the best Windows path, and now with a per-camera ≥ 99 % reliability claim.** MF in-process
  passed 400/400 open/close cycles on each of the four cameras. 400 failure-free cycles give a Wilson 95 % lower
  bound of 0.9905, above the 0.99 threshold (*measured*, §3). MF with a new process per cycle passed 100/100 per
  camera, which bounds it only at 0.963.
- **The pure-Python MF probe (pymf) is equivalent to the C++ probe (wincam)** on the Kiyo, C930e and C922: same
  formats, controls, JPEG header bytes, frame rate, latency and cycle results. Its CPU is higher (2.8–4.4 % vs
  1.9–2.8 % of one core) but within the criterion. The generic's pymf cycles were not scored because the camera fell
  off the bus during both tools' cycles (*measured*, §4).
- **DirectShow works as a fallback only through the ffmpeg CLI** (400/400 cycles on all four cameras). PyAV still
  silently streams YUY2 on the Kiyo (*measured*, §2, §3).
- **OpenCV is not a candidate.** 0 of 180 OpenCV cycles reached a first frame within 2 s, its raw path returns BGR,
  and through `CAP_MSMF` `get()` does not report the camera's value (*measured*, §5).
- **Timestamps: no ground truth this run.** MF sample times sit on a 16 ms grid, PyAV pts are synthesized, and the
  frame-index fits stay untested until the A5 rig exists (*measured*, §7).
- **The Kiyo wedged twice on 11-10/11, at plug-in ages of about 4 min and 525 min.** This rules out the
  "about 210–224 min after plug-in" theory. The 01:52 wedge began in a round that opened all four cameras at once
  through DirectShow (ffmpeg CLI). The 17:04 wedge began on an MF open of the Kiyo alone (*measured*). A concurrent
  multi-camera DirectShow open as the trigger fits 2 of the 4 recorded onsets, not all of them (*inferred*, §9).

## 1. Formats, controls and listing without opening

**MF, DirectShow and the descriptors list the same MJPEG modes on every camera** (*measured*, [W-FMT]
`verdicts.fmt_equivalence` yes). These are the same counts as 11-06:

| Camera | Descriptor modes | MF / DS capture modes | MJPEG modes, descriptors = MF = DS | NV12 types synthesized by MF |
| --- | --- | --- | --- | --- |
| Kiyo | 112 | 112 / 112 | 28 | 0 |
| C930e | 218 | 454 / 454 (incl. 238 H.264 entries) | 119 | 119 |
| generic | 14 (+5 still) | 14 / 14 (+5 still) | 10 | 13 |
| C922 | 218 | 218 / 218 | 120 | 120 |

The C930e's YUY2 2304x1536@2 and 2304x1296@2 are still in the descriptors but in no Windows listing
([W-FMT-NOGRAB] `os_exposed_reference.descriptor_only_modes`).

**Controls are identical through MF and DirectShow** (*measured*, [W-CTRL-LIST] `ctrl_list_equivalence` yes): Kiyo
16, C930e 16, generic 11, C922 16 supported controls, 0 missing against the descriptors, 0 MF-vs-DS differences.

**Listing formats without opening the camera** (*measured*, [W-FMT-NOGRAB] `results.<method>.<condition>`; three
conditions: idle, the camera streaming in another process through its native API, and through the second API):

| Method | Complete | Works while another process streams | Disturbs that stream / opens a pipe / blocks an open | Time |
| --- | --- | --- | --- | --- |
| Hub IOCTL descriptor read | 4/4 (it is the reference) | yes | no / no / no | 71–84 ms |
| MF `ActivateObject` + `GetNativeMediaType`, no `Start` | 4/4 against the OS-exposed list | yes | no / no / no | 34–76 ms to list, then a 2.5 s hold |
| DirectShow bound filter + `IAMStreamConfig` | 4/4 against the OS-exposed list | yes | no / no / no | 33–70 ms to list |
| `ffmpeg -list_options` | 1/4 (generic only). MJPEG listed: Kiyo 8/28, C930e 34/119, C922 34/120. 1280x720@30 MJPEG is missing on the Kiyo and C922 | yes | no / no / no | 360–423 ms |
| OpenCV, WinRT | "no" by assertion: no listing API without opening a capture | – | – | – |

- The C930e MF/DS cells moved from 3/4 (11-06) to 4/4 because the harness now rates against the modes Windows
  exposes and reports descriptor-only modes separately. The camera did not change (*measured*,
  `os_exposed_reference.applied` true).
- The idle "no pipe opened" check still covers only part of the 2.5 s hold: 0.145–0.437 of it on MF/DS. The
  streaming conditions cover 0.95–1.0 (*measured*, `hold_coverage_fraction_with_blocker`).

**Device listing and identity** (*measured*, [W-ID]):
- Six enumeration APIs (MF, DirectShow, PyAV dshow, ffmpeg CLI dshow, OpenCV MSMF, OpenCV DSHOW) map 1:1 to camera
  keys with the same order over 20 runs.
- p50 times: MF 2.09 ms, DS 4.58 ms, OpenCV MSMF 1.78 ms, PyAV 134 ms, ffmpeg CLI 172 ms (`timing_ms`).
- G-ID stays **partial (provisional)**. Reboot persistence for port keys is still null. Same-port replug now counts
  as true from natural evidence: all four cameras re-arrived on the same port since the 11-09 run and kept their
  keys. The serial-keyed C922 also kept its key over the 11-09 reboot (`persistence_inputs`,
  `natural_replug_evidence`).

**PyAV and ffmpeg device listing touch every camera** (*measured*, [W-PYAV-LIST]; rating "partial (touches but
harmless)" on every cell):
- Every call returned, no stream in another process lost a frame, and no isochronous pipe opened on an idle camera.
- **The calls were slow with the wedged Kiyo attached.** `list_devices` took 8.40 s (PyAV) and 8.55 s (ffmpeg CLI)
  p50 idle, max 14.8 s, and 8.42–9.27 s while another camera streamed (`results[*].elapsed_ms`). In W-ID, with the
  Kiyo healthy, the same listing took 134 and 172 ms p50.
- `list_options` took 0.29–0.61 s on the three healthy cameras and 3.5–19.5 s on the wedged Kiyo. One PyAV call
  returned 0 options for the Kiyo.
- *Inferred:* a wedged camera slows FFmpeg's DirectShow listing about 50-fold, because FFmpeg binds every capture
  filter. W-PYAV-LIST had no healthy-Kiyo control, so this is not proven.

## 2. Raw JPEG and uncompressed frames

**Raw JPEG (the camera's MJPEG bytes, unchanged), in-scope modes** (*measured*, [W-MJPEG] `verdicts`,
`measurements.cameras[*].modes[].apis`):

| Camera | Mode | MF | DS via ffmpeg CLI | DS via PyAV | Delivered rate (MF = DS) | Rate honoured |
| --- | --- | --- | --- | --- | --- | --- |
| Kiyo | 1280x720@30 | MJPEG, strict decode 1.0 | MJPEG, same header SHA-1 | **YUY2 (`yuyv422`), 0 JPEG frames** | 30.10 fps | yes |
| Kiyo | 1280x720@60 | MJPEG | MJPEG | **YUY2** | 30.33 fps | **no** |
| C930e | 1280x720@30 | MJPEG | (not needed) | MJPEG, same SHA-1 | 30.02 fps | yes |
| generic | 1280x720@30 | MJPEG | (not needed) | MJPEG, same SHA-1 | 25.76 fps | **no** |
| C922 | 1280x720@30 | MJPEG | (not needed) | MJPEG, same SHA-1 | 30.00 fps | yes |
| C922 | 960x720@30 | MJPEG | (not needed) | MJPEG, same SHA-1 | 30.00 fps | yes |
| C922 | 1280x720@60 | MJPEG | (not needed) | MJPEG, same SHA-1 | **59.43 fps** (steady) | yes |

- **Ratings:** MF yes ×4; DS ("best DS route") yes ×4; PyAV **no** on the Kiyo, yes on the other three
  ([summary] G-MJPEG). The ffmpeg CLI ran only where PyAV fell back (`pyav_format_fallback_modes`: the Kiyo's 2
  modes).
- **First Kiyo MJPEG rating.** 11-06 left the Kiyo's MJPEG modes unrated in both runs. Here it streamed both
  in-scope modes at plug-in ages of 356–359 min. Its 720p60 mode delivers 30.3 fps on MF and on the ffmpeg CLI,
  and its YUY2 in PyAV's fallback runs at 30.0 fps at the same request (`rate_control_experiment`). So the camera,
  not the API, caps the rate. The Kiyo reports `auto_exposure_priority` 0 (`control_state.before`).
- **First 60 fps stream verified at 60 fps.** The C922 at 720p60 delivered 59.43 fps (MF `fps_steady`) and 59.43
  fps (PyAV). In 11-06 it delivered 30.5 fps. MF's whole-capture rate is 40.2 fps because it includes a slow start
  (`fps_measured_tool`). The C922 now reports `auto_exposure_priority` 0; in 11-06 it was 1. *Inferred:* with
  priority off the camera no longer lowers the rate in low light. This is one capture.
- **The generic** delivers 25.76 fps at @30 on every API. *Inferred:* auto exposure lengthens the exposure in room
  light (the same 25.7 fps as in the 11-06 daytime run).
- **CPU, % of one core** (`cpu_pct_one_core`): MF 1.55–2.65 %. PyAV 1.87–3.12 % where it got MJPEG. The ffmpeg CLI
  process on the Kiyo used 9.4 % at 720p30 and 20.2 % at 720p60; the files do not show why it costs more than MF.
- **Open to first frame** (`timings.open_to_first_frame_ms`): MF 965 ms (Kiyo), 519 (C930e), 102 (generic),
  284–335 (C922). PyAV 548–816 ms on the three it served. ffmpeg CLI on the Kiyo 1264–1273 ms.

**Uncompressed frames (W-RAW).** Only the Kiyo has a raw mode in scope. The other three are "untested (no raw mode
in scope)": the fastest 720-line raw mode is YUY2 720p@10 on the C930e and 960x720@15 on the C922, and the generic
has no 720-line raw mode ([W-RAW] verdicts). Kiyo, 4 modes (NV12 and YUY2 at 1280x720@30 and @60) (*measured*,
[W-RAW] `cameras[Kiyo].modes[*]`):

| Route | Rating | What it delivered |
| --- | --- | --- |
| MF | yes | the requested subtype, 1,382,400 B (NV12) and 1,843,200 B (YUY2) frames, 100 % at the expected length |
| PyAV `pixel_format` | yes | same subtypes and lengths |
| ffmpeg CLI | yes | same subtypes and lengths |
| OpenCV `CAP_DSHOW` | **no** | 720×1280×3 = 2,764,800 B frames (converted BGR) in all 4 modes |
| OpenCV `CAP_MSMF` | partial | YUY2 at the right length for the 2 YUY2 requests; YUY2 again for the 2 NV12 requests |

All three working routes deliver 30.0 fps at the @60 requests, so the Kiyo caps raw 720p at 30 fps too.

## 3. Reliability: open/close cycles

**Every cycle opened, delivered a first frame and closed: 0 hangs, 0 unreleasable readers, 0 device resets, no
re-arrival during W-CYC or W-CYC-KIYO** (*measured*, [W-CYC-KIYO] and [W-CYC] `verdicts.reliability|*`,
`measurements.arrivals.changes` []). The Kiyo ran 05:40–06:47Z (00:40–01:47 local), at plug-in ages of 453–520
min. The other three ran 07:08–09:24Z (02:08–04:24 local).

| Route (cycles per camera) | Kiyo | C930e | generic | C922 |
| --- | --- | --- | --- | --- |
| MF in-process (400) | 400/400, yes | 400/400, yes | 400/400, yes | 400/400, yes |
| DS via ffmpeg CLI, in-process (400) | 400/400, yes | 400/400, yes | 400/400, yes | 400/400, yes |
| MF, new process per cycle (100) | 100/100, partial (n) | 100/100, partial (n) | 100/100, partial (n) | 100/100, partial (n) |
| DS via PyAV, in-process / new process (50 / 15) | 50/50, 15/15, **YUY2 in all**, partial | yes / yes | yes / yes | yes / yes |
| Mode switch, MF / PyAV-DS (25 each) | yes / partial (YUY2) | – (one in-scope mode) | – | yes / yes |
| OpenCV, three variants (15 each) | **no (latency)** | **no** | **no** | **no** |

Open to first frame, p50 in ms, and the delivered rate (*measured*, `evidence.p50_open_to_first_frame_ms`; rates
from the rows files `W-CYC*/<camera>/*_cycles.json` `fps_measured`):

| Camera | MF in-process / new / switch | ffmpeg-DS in-process | PyAV-DS in-process / new / switch | MF close p50 | MF fps p50 |
| --- | --- | --- | --- | --- | --- |
| Kiyo | 972 / 964 / 975 | 1275 | 1112 / 866 / 1128 (YUY2, 22.4 fps) | 1090 | 30.22 |
| C930e | 527 / 515 / – | 828 | 1086 / 820 / – | 359 | 29.72 |
| generic | 121 / 100 / – | 371 | 693 / 405 / – | 272 | 25.88 |
| C922 | 339 / 328 / 338 | 650 | 903 / 640 / 874 | 341 | 29.72 |

- **Rate flags are camera behaviour, not reliability.** The generic ran below 90 % of 30 fps in every cycle on every
  route (25.4–25.9 fps p50), so its cells carry "rate < 90 % of requested". The Kiyo's MF mode switch flags 12/25
  cycles; *inferred:* these are the 720p60 half, which delivers about 30 fps (§2). The rating rule does not count
  rate (`fps_rule`).
- **The PyAV "partial" cells on the Kiyo are the format check.** PyAV delivered `rawvideo` (YUY2) in 50/50, 15/15
  and 25/25 cycles. MF and the ffmpeg CLI delivered MJPEG in every Kiyo cycle.
- **Latency.** MF reaches the first frame 250–310 ms sooner than the ffmpeg CLI on the four cameras (the ffmpeg
  time includes its process start). The Kiyo needs about 1 s to open and about 1.1 s to close on MF, as in 11-06.

**What the cycle counts can claim** (*measured* counts; Wilson 95 % lower bound for n failure-free cycles is
n / (n + 1.96²)):
- A per-camera "≥ 99 %" claim needs at least 381 failure-free cycles.
- **MF in-process and ffmpeg-DS in-process: 400/400 per camera → lower bound 0.9905.** This meets the plan's
  W-CYC-381 bar on all four cameras, for both routes. It is the first per-camera ≥ 99 % result in the study.
- MF new process: 100/100 per camera → 0.963. Pooled over the four cameras, 400/400 → 0.9905, but that is not a
  per-camera claim.
- Pooled MF in-process, 1,600/1,600 → 0.9976.
- PyAV-DS 50/50 → 0.929; 15/15 → 0.796. pymf 60/60 → 0.940 (§4).
- **The 0.9905 bound holds only for these conditions:** one camera at a time, the camera lock held, the cameras as
  found, and the Kiyo between 453 and 520 min of plug-in age. It says nothing about the Kiyo's wedge, which came
  in a different pattern (§9).

## 4. W-PYMF: pure-Python MF (pymf 0.2) vs the C++ probe (wincam 1.2)

W-PYMF ran 04:16–04:27Z (23:16–23:27 local). For each camera it compares listing, native types, controls, a
control set/restore, a 5 s capture and 60 open/close cycles per tool (*measured*, [W-PYMF] `verdicts`,
`measurements.cameras[*]`).

| Check | Kiyo | C930e | generic | C922 |
| --- | --- | --- | --- | --- |
| Listed by both, same name and order | yes | yes | yes | yes |
| Native types equal, in order, synthesized NV12 flagged alike | 140 = 140 | 811 = 811 | 32 = 32 | 338 = 338 |
| Control readback equal | 0 diffs | 0 diffs | 0 diffs | 0 diffs |
| pymf sets, reads back and restores | 4 controls | 4 | 3 | 4 |
| JPEG header SHA-1 equal to wincam's | yes | yes | yes | yes |
| fps ratio pymf / wincam | 1.0002 | 1.0004 | 1.0000 | 1.0000 |
| Open to first frame, pymf − wincam | −1.2 ms | +1.3 ms | +63.3 ms | +0.8 ms |
| CPU % of one core, wincam → pymf | 1.87 → 4.04 | 2.81 → 3.12 | 1.87 → 2.81 | 1.87 → 4.37 |
| Arrival-delay std off the sample-time grid, wincam / pymf | 0.355 / 0.425 ms | 0.288 / 0.363 | 0.361 / 0.444 | 0.388 / 0.369 |
| Frames lost (wincam / pymf) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Cycles, wincam / pymf (first-frame p50) | 60/60 / 60/60 (964 / 965 ms) | 60/60 / 60/60 (519 / 522) | **39/60 / 40/60** | 60/60 / 60/60 (334 / 336) |
| `pymf_equivalence` | **yes** | **yes** | **partial (cycles untested)** | **yes** |

- **pymf matches wincam on everything measured** for the Kiyo, C930e and C922. Its CPU is 1.1–2.3 times
  wincam's. The criterion allows max(2×, +5 points), and pymf stays at or below 4.4 % of one core.
- **The generic camera dropped off the bus during both tools' cycles** (*measured*, `cycles.wincam/pymf.summary`,
  rows in `W-PYMF/usbcamera_4c4a-4a55_2_*_cycles.jsonl`, `arrivals.changes`):
  - wincam: cycles 0–38 ok. Cycle 39 timed out at the first sample (04:24:35Z), and cycles 40–59 failed at once
    with `0x8007048F` (ERROR_DEVICE_NOT_CONNECTED).
  - pymf: cycle 0 timed out at `activate` (04:24:41Z), cycles 1–40 ok. Cycle 41 timed out at the first sample
    (04:25:20.37Z), and cycles 42–59 failed with `0x8007048F`.
  - The camera re-arrived at 04:25:20.74Z, and the suite's 1-frame probe right after pymf failed too. The fault
    was cleared by the next test's probe at 04:27:39Z ([run_suite] `faults`).
  - Only the second re-arrival is recorded, because the arrival check keeps only the latest time. A first drop near
    04:24:35Z is *inferred* from the wincam rows.
  - Both tools failed the same way at about the same cycle count. So the camera is the suspect, not either tool
    (*inferred*; the harness drew the same conclusion and left the cell untested).
  - The same camera passed 400 MF and 400 ffmpeg-DS cycles later in W-CYC with no re-arrival.
- **Answer for plan §8.** On three of four cameras a pure-Python MF capture is equivalent to the C++ probe, so
  this run supports "native Python where possible" on Windows (*measured* on 3 cameras). The generic's pymf cycles
  need a rerun (§14).

## 5. OpenCV variants

**Cycles** (*measured*, [W-CYC], [W-CYC-KIYO] `opencv_*`; 15 cycles each; variant details in
`variants.<v>.info.tool_summary`):
- `opencv_inproc`: `CAP_DSHOW`, the simple set order.
- `opencv_skellycam`: skellycam's real two-step sequence, with skellycam's default framerate −1 (no FPS set).
- `opencv_skellycam_fps30`: the same sequence with FPS = 30.

| Camera | `opencv_inproc` p50, final format | `opencv_skellycam` p50 | `opencv_skellycam_fps30` p50 | Within 2 s |
| --- | --- | --- | --- | --- |
| Kiyo | 8537 ms, YUY2 22.6 fps | 11098 ms, MJPG 29.9 fps | 13187 ms, MJPG 30.1 fps | 0/45 |
| C930e | 5411 ms, YUY2 10.0 fps | 6867 ms, MJPG 30.1 fps | 8204 ms, MJPG 29.9 fps | 0/45 |
| generic | 3194 ms, MJPG 25.7 fps | 3228 ms, MJPG 25.7 fps | 4117 ms, MJPG 25.7 fps | 0/45 |
| C922 | 4190 ms, YUY2 10.0 fps | 5387 ms, MJPG 30.2 fps | 6468 ms, MJPG 29.7 fps | 0/45 |

- **0 of 180 OpenCV cycles reached a first frame within 2 s**, so all 12 cells rate "no (latency)". Every cycle
  did open, stream and close.
- skellycam's default framerate −1 is 0.9–2.1 s faster than FPS = 30. This confirms the 11-06 caveat that the
  harness's FPS = 30 was pessimistic. Both variants are still 3.2–13.2 s to the first configured frame.
- The skellycam sequence reached MJPG only because FOURCC is set last. The simple order ended in YUY2 at 10 fps
  on both Logitech cameras.
- The exposure restore now restores value and flag on all four cameras (`exposure_restore.opencv_skellycam`).

**Controls through OpenCV** (*measured*, [W-OCV-CTRL]; exposure and focus only):

| Camera | `CAP_DSHOW` G-CTRL | `CAP_MSMF` G-CTRL | AE back on, DSHOW / MSMF | AF back on, DSHOW / MSMF |
| --- | --- | --- | --- | --- |
| Kiyo | partial | partial | inconclusive / inconclusive (manual −4 did not move luma out of the ±15 % band) | yes (recovery 2.2–2.4 s) / inconclusive (sharpness baseline CV 0.39–0.41) |
| C930e | partial | partial | yes / yes | yes / yes |
| generic | **yes** | partial | yes / yes | n/a (no focus control) |
| C922 | partial | partial | yes / yes | **no**: 1 of 3 toggles failed, the flag read back but sharpness did not recover / yes |

- **Why partial:** on DSHOW, a value set before the first frame did not hold or did not reach the image (Kiyo,
  C930e, C922). On MSMF, in addition, `get()` does not return the camera's value on any camera.
- **OpenCV's raw path** gives converted BGR through `CAP_DSHOW` and the wrong subtype for NV12 requests through
  `CAP_MSMF` (§2).

**Answer.** OpenCV fails the first-frame criterion on every camera and variant. It gives no JPEG bytes (11-06) and
no true raw frames through DSHOW, and its controls need workarounds (*measured*). It stays out of the capture path.

## 6. Controls: effect in the image, auto modes, before and after stream start

**Effect in the image, MF and DirectShow paths, 3 runs per control** (*measured*, [W-CTRL-EFFECT]
`measurements.cameras[*].paths.{mf,ds}.controls.*`; ratio = metric at the last value over the first, "after" =
the part of the sweep set after the stream started):

| Camera | Rating MF / DS | Exposure | Gain | White balance | Focus (sharpness max/min) | Before and after stream start |
| --- | --- | --- | --- | --- | --- | --- |
| Kiyo | **yes / yes** | luma ×1.79 (after start ×1.13) | ×1.27 (after ×1.13) | R/B ×4.9 (after ×1.53) | ×55.7 MF, ×11.4 DS | all hold through start; all persist |
| C930e | partial / partial | after start ×4.1–4.4; **reset to −5 at the first frame in 3/3 runs on both paths** | ×2.6–4.2; held through start in 1/3 runs per path | ×1.40 | ×77.7 MF, ×80.5 DS | exposure and gain do not hold |
| generic | partial / partial | ×4.45–4.60 (after ×1.46) | **no effect (×1.00); reads 4 at the first frame in 3/3 runs** | **no effect**: MF 1/3 runs (×1.106 once), DS 0/3 | – (no focus control) | gain does not hold |
| C922 | **yes / yes** | ×14.9–15.5 (after ×3.6) | ×2.31–2.33 | ×2.13 | ×286 MF, ×290 DS | all hold; all persist |

- **The Kiyo now passes gain.** The whole sweep gives ×1.27 (required ×1.15) and the post-start part ×1.13. In
  11-06 the post-start part was ×1.004–1.012. Its exposure ratio is lower than in 11-06 (×1.79 vs ×3.6). Both
  depend on the scene, which changed (*inferred*).
- **The C930e and generic findings repeat 11-06**: the C930e resets exposure at stream start, and the generic's gain
  and WB do nothing visible.
- **The Kiyo's DS focus ratio is a fifth of its MF ratio** (×11.4 vs ×55.7). The sharpness metric on the DS path is
  not validated (11-06 saw the same direction).
- **Restore is clean on all 8 paths**, and every swept control persisted across a reopen (`restore.restored`,
  `persisted_after_reopen`).

**Turning auto exposure and autofocus back on, verified on the image** (*measured*, [W-AUTO] `G-CTRL-AUTO|*`;
3 in-stream toggles × 3 runs, plus auto switched on before the stream starts):

| Camera | AE, MF / DS | AE recovery after auto on | AF, MF / DS | AF recovery |
| --- | --- | --- | --- | --- |
| Kiyo | partial / partial | 442–491 ms MF, 529–546 ms DS | untested (inconclusive) / same | – |
| C930e | yes / yes | 201–236 ms MF, 210–227 ms DS | yes / yes | 390–448 ms MF, 452–490 ms DS |
| generic | yes / yes | 157–331 ms MF, 177–420 ms DS | n/a (no focus control) | – |
| C922 | partial / partial | 634–843 ms MF, 712–860 ms DS | yes / yes | 163–208 ms MF, 211–282 ms DS |

- **No transition failed.** The flag read back at every switch (12/12 per cell). Auto on before the stream starts
  reached the image in 3/3 runs on every camera and path.
- **"Partial" means inconclusive toggles, not failures.** On the Kiyo and C922, one of the three manual extremes
  (−5) did not move luma out of the ±15 % band, so 6 of 9 toggles were conclusive, with 0 failures.
- **The Kiyo's AF is unmeasured.** Its sharpness baseline varied too much (CV 0.35 on MF, 0.45 on DS, limit 0.35).
  The harness names lighting change, motion or AE/AF hunting as causes; which one is not known.
- **The image after the final restore** matched the as-found image: luma ×0.93–1.06 on the four cameras
  (`restore_image_check.luma_mean.ratio`).

**Answer.** Exposure, AE and AF work through MF and DirectShow on the cameras that have them, verified on the image.
The 11-06 rules stand: apply controls after the first frame and verify them on the image (C930e), and keep a
per-camera capability table (the generic's gain and WB have no visible effect) (*measured*).

## 7. Timestamps (tier 0, no ground truth)

W-TS captured 30 s of MJPG 1280x720@30 per camera through three routes: MF, DirectShow via PyAV, and DirectShow via
the ffmpeg CLI (*measured*, [W-TS] `verdicts`, `measurements.cameras[*].apis.*`). `ground_truth` is null: the A5
strobe rig is not built.

| Route | Kiyo | C930e | generic | C922 | Rating |
| --- | --- | --- | --- | --- | --- |
| MF sample time | 16.0 ms grid (on-grid 0.9945) | 16.0 ms (1.000) | 16.0 ms (1.000) | 16.0 ms (0.9978) | **no** ×4 |
| PyAV pts | synthesized: constant 33.3383 ms (YUY2 fallback capture) | synthesized: 2 values, 33.3283 / 33.3333 ms | synthesized: 33.3383 ms; drifts +141.3 ms/s against arrival (camera runs at 25.76 fps) | synthesized: 33.3333 ms | **no** ×4 |
| ffmpeg CLI pts | wall clock at demux; interval std 8.87 ms | std 6.50 ms | std 10.85 ms | std 6.66 ms | untested ×4 |
| Frame-index fit to MF arrival, residual std | 10.10 ms | 4.69 ms | 4.62 ms | 4.71 ms | untested ×4 |
| Frame-index fit to PyAV arrival | 5.73 ms | 4.66 ms | 4.62 ms | 4.63 ms | untested ×4 |
| Frame-index fit to ffmpeg time | 11.23 ms | 6.98 ms | 7.69 ms | 7.44 ms | untested ×4 |

Sources: `grid_sample_time`, `pts_synthesized`, `grid_pts`, `arrival_minus_pts_drift_ms_per_s`,
`frame_index_fit_arrival.causal.residual_stats_ms.std`.

- **Every MF host stamp is on the 16 ms grid,** including the SuperSpeed Kiyo. Arrival minus sample time is
  bimodal, at about 0.75 ms and about 16.7 ms (plus a third mode at about 32.7 ms on the Kiyo and 33 ms on the
  generic) (`arrival_minus_sample_time_ms.modes`).
- **The regular cameras' fit residuals equal the quantisation floor**, 16/√12 = 4.62 ms. So, as in 11-06, the fit's
  real error against exposure time cannot be seen without ground truth.
- **The Kiyo's MF residual is twice the floor** (10.1 ms). Its arrival intervals vary more (std 7.1 ms, max 64.3 ms)
  than the Logitech cameras' (std 4.4 ms). *Inferred:* host-visible delivery jitter on the Kiyo, which a
  constant-period model will not absorb.
- **Drops:** 0 on every MF capture (`drops_sample_time.drops`). PyAV's synthesized pts cannot show a drop.
- **The ffmpeg CLI timestamps** are the CLI's wall clock at demux, not a device or QPC time. They are not
  synthesized and not on a grid, but they jitter 6.5–10.9 ms, worse than MF's arrival time.

**Answer.** Tier 0 on Windows still has no scored timestamp route. MF sample time and PyAV pts are ruled out; the
frame-index fits wait for the A5 rig (*measured*). Requirement 9c (UVC PTS/SCR) is out of scope (plan §8).

## 8. Bandwidth contention and the topology mapper

W-MULTI ran 06:47:31–07:01:00Z (01:47–02:01 local) with all four cameras at 720p30 MJPEG. The C922 and generic share
the HS13 hub; together they need 81.1 % of a microframe (C922 39.85 µs + generic 61.58 µs) (*measured*, [W-MULTI]
`predicted_vs_observed`, `summary_by_api`).

| | MF | DS (ffmpeg CLI) | DS (PyAV) |
| --- | --- | --- | --- |
| Rating | **yes** | partial | partial |
| Events / refusals | 21 / 19 | 21 / 15 (+1 excluded as device not ready) | 21 / 2 |
| False "fits" / false "over" | 0 / 0 | 0 / **3** | 0 / **17** |
| Retry after a refusal | 6/6 on the first try | 8/8 on the first try | 2/2 on the first try |
| Refusal code | `0x800718CF` at the first sample (`bandwidth_certain`) | `OSError(5)` (`bandwidth_probable`) | `OSError(5)` |

- **MF refused the 81.1 % HS13 pair in every attempt:** 10 all-together rounds, 5 staggered rounds, and 2 pairs at
  720p30. The C922 lost every time. The 98.4 % pair with the C922 at 720p60 was refused 2/2. The 75.2 % pair with
  the C922 at 960x720@30 streamed 2/2.
- **Later in the same test the 81.1 % pair streamed.** From `ds_staggered_036` (06:55:08Z) on, both HS13 cameras
  opened their pipes (39.85 + 61.58 µs observed) in 3 DS runs and in all 17 PyAV runs at 720p30. Before 06:55 the
  same pair was refused on MF and DS (PyAV had not run yet). The 98.4 % pair (C922 at 720p60) was still refused on DS (2/2) and PyAV (2/2).
- **The test cannot separate the API from the time.** MF ran first and was not repeated after 06:55. *Inferred:* the
  Intel xHCI's admission edge for this hub is not a fixed number near 81 %. The cause of the change is unknown.
  The generic re-enumerated at 06:52:17Z and 06:52:46Z, and the Kiyo wedged at 06:52:46Z on another controller; any
  link to the change is untested.
- **The generic re-enumerates after DirectShow-family failures**, 0.06 s and 10.2 s after them here, and never after
  an MF refusal (`timeline`, `arrival_attribution`). This repeats 11-06.
- **Messages:** 36, 9 distinct texts, 0 null. The stay-here advice now offers 960x720@30 ("about 32 %"), which
  fixes the 11-06 complaint that it dropped to 640x480 (`messages[*]`).
- **Mapper** (*measured*, [W-TOPO] `mapper` yes): 0.064 s, no admin, 0 device requests, 9 hubs, 63 ports, every
  camera in a bandwidth domain. Predicted costs equalled the observed open pipes (`predicted_vs_observed`).

## 9. Kiyo Pro: two wedges in 9 hours

**Healthy work before the wedge, this run** (*measured*):
- W-FMT, W-FMT-NOGRAB, W-MJPEG, W-RAW, W-TS and W-PYMF at plug-in ages of 352–380 min.
- W-CTRL-EFFECT, W-AUTO and W-OCV-CTRL.
- W-CYC-KIYO at 453–520 min: 1,060 cycles, all successful.
- W-MULTI: 15 MF multi-camera rounds and the first 6 DirectShow all-together rounds.
- In total at least 1,200 counted Kiyo stream starts (W-CYC-KIYO 1,060, W-PYMF 120, W-MULTI 21), plus the single
  captures in the other tests.
- The background poller answered 344 of its MF polls and 344 of its DS polls before the onset ([W-KIYO]
  `ok_per_api`). The last answered polls were at 06:52:46.24Z (MF) and 06:52:46.52Z (DS), 0.4–0.7 s before the
  round that wedged.

**The 01:52 onset** (*measured*, [W-MULTI] `runs[27]` = `ds_all_together_028`, `device_fault_log`; [W-KIYO]
`first_failure`, `transitions`; [run_suite] `status[*].probes`):

| Time, local (UTC) | Event |
| --- | --- |
| 01:52:15–01:52:17 (06:52:15Z) | DS round 4 (`_025`): the generic fails to open and re-enumerates 0.06 s after the round ends (06:52:17.80Z). The generic is on the Intel xHCI; the Kiyo is on the Thunderbolt xHCI |
| 01:52:35–01:52:46 | DS round 6 (`_027`): the generic is refused; it re-enumerates at 06:52:46.59Z |
| 01:52:46.94 (06:52:46.94Z) | DS round 7 (`_028`) opens all four cameras at once, one ffmpeg CLI process per camera. Plug-in age 525.2 min |
| 01:52:46.94–01:53:17.45 | The Kiyo's ffmpeg open does not return. Its isochronous pipe is open (alt 1, 6.32 µs). The child is killed after 30.27 s (`open_duration_ms` 30268.8). The C930e and generic stream; the C922 is refused |
| 01:53:17.54 | First unanswered poll (MF, requested 01:52:56, after a 21.3 s camera-lock wait): timeout at `activate` |
| 01:53:23.74 | The 1-frame health check fails (timeout at `activate`, 3.03 s). Fault recorded at 525.8 min |
| 01:53:23.84 | First unanswered DS poll |
| 01:53:39 onward | Polls also return `0x8007001F` / `0x80070490`. Over the rest of the run: 432 polls after the onset, 0 answered. Codes: timeouts (rc 5) 385, `0x800703E3` 37, `0x8007001F` 4 |
| 01:56:40, 02:01:07, 02:08:28 | Re-probes in W-MULTI's PyAV phase, W-PYAV-LIST and W-CYC fail (timeout, `0x800703E3`, timeout) |
| 04:24:20 | Last poll: still unanswered. Problem code 0 and the device present throughout |

- **Signature.** A stream start hangs with the pipe open, then calls fail and the devnode stays healthy, with no
  re-arrival. Only a replug is known to recover it. This matches 11-06 R2 (also a DS ffmpeg-CLI open in W-MULTI,
  35.3 s hang) (*measured*).
- **What was running.** The round ran under the camera lock: the launcher acquired ticket 2243 and released it
  after 30.6 s, and the poller's next query waited 21.3 s for the lock. Of the vendor software only
  `razer_elevation_service` ran, with no change all night ([W-KIYO] `vendor_process_changes`). The activity monitor
  listed one client process, `?:39608`, at the first failed poll. That process is not identified in the files.
- **Little was lost.** The Kiyo's own tests had all finished. It was gated out of W-PYAV-LIST streaming and W-CYC
  (`gated`).

**The 17:04 wedge, before the run** (*measured* from the files in [scene check]; the note is
[scene note], and these probes are not suite results):
- The Kiyo was replugged about 17:00 (absent from PnP at 16:59, per the note), so its plug-in age was about
  4–5 min.
- 17:04:18 (22:04:18Z): one wincam MF capture of the **Kiyo alone**, the first command of the check. Activate and
  set-type returned S_OK, no first sample came in 20.26 s, and the reader release took 5.26 s
  (`vid_1532/summary.json` `steps`).
- At that time, per the note, Signal's VideoCaptureService was a Frame Server client on the C930e, and LogiTuneAgent
  (pid 5744) was a client on all four cameras. `activity_after.json` (22:05:59Z) shows LogiTuneAgent on all four,
  not streaming; it does not show Signal.
- 17:06:16: retry after Dom closed Signal. The Kiyo returned `0x8007001F` at the first sample, the 11-06 signature
  (`retry_after_signal_closed/vid_1532/summary.json`). The C930e failed at `activate` with `0x800703E3` in both
  attempts.
- After Dom replugged the Kiyo and C930e (17:07:35 / 17:07:46), all four streamed at 17:09, with LogiTuneAgent still
  attached (note).

**Why the plug-in-age theory no longer fits** (*measured* ages; *inferred* conclusion):
- 11-06 R1 failed between 200.6 and 224.3 min after plug-in, and R2 at 210.6 min. The 11-06/07 control run (polls
  only) did not fail in 5 h, which already removed age alone as the trigger.
- On 11-10/11 the Kiyo wedged at about 4–5 min and at 525.2 min. In between it worked through more than 1,200
  stream starts at 352–525 min, including 1,060 cycles at 453–520 min.
- So age near 210 min is neither necessary nor sufficient. 11-06's "cumulative use" hypothesis is also weakened:
  the 17:04 wedge came at the first stream start after a replug.

**What the four recorded onsets have in common** (*inferred*, labelled as such):

| Onset | Plug-in age | API and pattern | Other camera activity |
| --- | --- | --- | --- |
| 11-06 R1 | 200.6–224.3 min | MF, first stream after 23.7 min idle, Kiyo alone | LogiTuneAgent and RazerAppEngine attached |
| 11-06 R2 | 210.6 min | DS (ffmpeg CLI) open in W-MULTI staggered round | other cameras opening |
| 11-10 17:04 | about 4–5 min | MF, Kiyo alone, first command | Signal on the C930e (note), LogiTuneAgent attached to all four |
| 11-11 01:52 | 525.2 min | DS (ffmpeg CLI) open, W-MULTI all-together round 7 | three other cameras opening at the same instant; the generic re-enumerated 0.35 s earlier |

- Every onset is a stream start.
- Two of four are DirectShow (ffmpeg CLI) opens during W-MULTI with other cameras opening. In this run the same DS
  all-together pattern had passed 6 times just before, and MF multi-camera rounds had passed 15 times.
- Two of four are MF opens of the Kiyo alone, both with another application attached to the cameras.
- The candidate trigger "concurrent multi-camera opens, especially DirectShow" therefore explains half the onsets.
  A second candidate, "another process attached to or using cameras at the Kiyo's stream start", covers 11-06 R1
  and 17:04 but not this run's 01:52 onset, where no vendor agent was attached.
- Neither candidate is proven. Rerunning W-MULTI on its own is the next test (§14).

**Windows' camera-usage record does not help.** The ConsentStore snapshots before and after the run are
byte-identical, and the newest entry is from 2026-10-13. It recorded neither the suite's tools nor Signal
(*measured*, [consent pre] vs [consent post]).

## 10. Ratings per goal and API

Cell counts are per camera (Kiyo / C930e / generic / C922). Sources: [summary] and the JSON named in each row.

| Goal (test) | MF (wincam) | pymf | DS via PyAV | DS via ffmpeg CLI | OpenCV | Other |
| --- | --- | --- | --- | --- | --- | --- |
| G-ID ([W-ID]) | one cell for all 6 APIs: **partial (provisional)**; 1:1 and stable over 20 runs; reboot of port keys not measured | ← | ← | ← | ← | key source stability: yes |
| Reliability ([W-CYC], [W-CYC-KIYO], [W-PYMF]) | in-process **yes** ×4 (400/400, ≥ 0.9905); new process partial ×4 (100/100, 0.963, n only); mode switch yes ×2 | yes (60/60, point estimate) / yes / untested (device fault) / yes | partial (YUY2) / yes / yes / yes | **yes** ×4 (400/400) | **no (latency)** ×12 | – |
| pymf equivalence ([W-PYMF]) | reference | **yes / yes / partial (cycles untested) / yes** | – | – | – | – |
| G-MJPEG ([W-MJPEG]) | yes ×4 (Kiyo and generic: rate not honoured in 1 mode) | equal header SHA-1 ×4 | **no** / yes / yes / yes | Kiyo yes (only route tested there) | no JPEG bytes (11-06) | – |
| G-RAW ([W-RAW]) | Kiyo yes; others untested (no raw mode in scope) | – | Kiyo yes | Kiyo yes | Kiyo: DSHOW **no**, MSMF partial | – |
| G-CTRL ([W-CTRL-EFFECT], [W-OCV-CTRL]) | yes / partial / partial / yes | 3–4 controls set and restored ×4 | same as MF (DirectShow filter) | – | DSHOW partial / partial / yes / partial; MSMF partial ×4 | lists: MF = DS on all 4 |
| G-CTRL-AUTO ([W-AUTO], [W-OCV-CTRL]) | AE: partial / yes / yes / partial; AF: inconclusive / yes / n/a / yes | – | DS path same as MF | – | see §5 | – |
| G-TS ([W-TS]) | sample time **no** ×4; frame-index fit untested ×4 | – | pts **no** ×4; fit untested ×4 | pts untested ×4; fit untested ×4 | – | no ground truth |
| G-BW ([W-MULTI], [W-TOPO]) | **yes** | – | partial (17 false "over") | partial (3 false "over") | – | mapper yes; W-TOPO G-BW untested by design; Kiyo cell untested (fault) |
| Format lists ([W-FMT]) | MF = DS = descriptors on every MJPEG mode: yes | 140 / 811 / 32 / 338 types equal to wincam | ← | – | – | – |
| Listing without grabbing ([W-FMT-NOGRAB], [W-PYAV-LIST]) | yes ×4 | – | list_devices / list_options: partial (touches but harmless) | `-list_options`: no / no / yes / no | no (asserted) | DS filter yes ×4; hub IOCTL yes ×4; WinRT no (asserted) |
| Kiyo polling ([W-KIYO]) | **no**: 344 of 558 MF and 344 of 556 DS polls answered; stopped at 525.7 min | – | – | – | – | – |

Notes on reading the table (*inferred*):
- **The generic's G-MJPEG "yes" hides a rate of 25.76 fps at @30.** The cell label now says "rate not honoured in
  1", as the 11-06 harness fix intended.
- **The PyAV and ffmpeg G-BW "partial" cells come from false "over" predictions that cluster in time** (§8). They
  do not show a classification fault.

## 11. Harness notes from this run

None of these change a conclusion; each one changes how a number reads.
- **Plug-in ages are stamped at the end of a failed command.** `summary.md` gives the Kiyo's first failed command
  at "525.7 min"; the open started at 525.2 min and timed out 30 s later ([summary], [W-MULTI] `runs[27]`).
- **Only the latest arrival time is kept**, so a camera that re-arrives twice in one test, like the generic in
  W-PYMF, shows one re-arrival ([W-PYMF] `arrivals`).
- **"Touches but harmless" does not report call time.** W-PYAV-LIST listing took 8.4–14.8 s with the wedged Kiyo
  attached; the rating does not show it.
- **W-MULTI runs the APIs in a fixed order** (MF, then DS, then PyAV). A change in the bus during the test (§8) is
  charged to whichever API runs later.
- **The activity monitor reported an unnamed client** (`?:39608`) at the Kiyo's first failed poll.

## 12. Differences between the executive summary and the raw data

| Executive summary says | Raw data |
| --- | --- |
| Generic camera controls: "partial: no focus control (fixed focus); same two misses as the C930e" | Also: **gain has no visible effect** (×1.00 in 3/3 runs on both paths) and reads 4 at every stream start; **white balance has no visible effect** (MF 1/3 runs, DS 0/3). The "effect shows in the image" criterion is not met ([W-CTRL-EFFECT]) |
| MF "passed 400/400 in-process open/close cycles with no hangs" on all four cameras | True for W-CYC. In W-PYMF the wincam MF cycles on the generic failed **21/60** (one first-sample timeout, then 20 × `0x8007048F`) at the same time as pymf's 20/60, when the camera dropped off the bus ([W-PYMF] `cycles.wincam`) |
| "25 s before the wedge, in round 4, the generic camera failed and re-enumerated" | The generic re-arrived at 06:52:17.80Z, 29.1 s before round 7 began, **and again at 06:52:46.59Z, 0.35 s before round 7 began** ([W-MULTI] `timeline`) |
| Wedge "plug-in age 8 h 46 min" | 525.2 min (8 h 45 min) when the open started; 525.7 min when the 30 s timeout expired |
| "Both [wedges] happened while several cameras were being opened or used at once" | The 17:04 wedge was an MF open of the Kiyo **alone**, the first command of the check. The other activity was Signal on the C930e (from the note only) and LogiTuneAgent attached without streaming ([scene check] `vid_1532/summary.json`, `activity_after.json`) |
| C922 AF through OpenCV DirectShow: "no, only sets the flag" | 1 of 3 toggles failed; the other 2 recovered in 702 and 790 ms ([W-OCV-CTRL]) |
| Kiyo AF "inconclusive (its focus kept hunting)" | The data says the sharpness baseline was unstable (CV 0.35 / 0.45). Hunting is one of three possible causes the harness names |
| Not mentioned | The C922 delivered **59.4 fps at 720p60**, the first verified 60 fps stream in the study (§2) |
| Not mentioned | The HS13 pair at 81.1 % **streamed in 20 DS/PyAV runs** after being refused 19/19 on MF earlier in the same test (§8) |
| Not mentioned | PyAV/ffmpeg `list_devices` took **8.4–9.3 s** with the wedged Kiyo attached (§1) |

## 13. What this changes

- **MF native stays the primary Windows path, and the reliability bar is now met per camera.** MF in-process 400/400
  on each camera (Wilson lower bound 0.9905). The new-process variant is at 0.963 and needs ≥ 381 cycles for the same
  claim (*measured*).
- **Plan §8 "native Python where possible" is supported on Windows.** pymf matches wincam on three cameras on every
  measured axis. Its CPU cost is up to 2.3× wincam's, still under 5 % of one core (*measured*). The fourth camera
  needs a rerun.
- **Plan §7 "W-CYC-381 shows MF-only failures → build C5" did not trigger.** MF had 0 failures in 1,600 in-process
  and 400 new-process cycles. The only MF failures in the run (W-PYMF, generic) hit wincam and pymf alike while the
  camera dropped off the bus, with no DS route running to compare. So they are not MF-only evidence (*inferred*).
  Both Kiyo wedges in a DS route (11-06 R2, 11-11) began on the ffmpeg CLI; this argues against leaning on
  DirectShow for the Kiyo, but does not prove MF is safe (*inferred*).
- **OpenCV is ruled out on Windows** on latency (0/180 within 2 s), raw output (BGR through DSHOW) and controls
  (pre-first-frame sets lost; MSMF `get()` wrong) (*measured*).
- **PyAV stays out of the capture path.** It still falls back to YUY2 on the Kiyo in every test that used it
  (W-MJPEG, W-CYC, W-TS) (*measured*).
- **Controls:** the per-camera rules and capability table from 11-06 stand. Auto on works on the image wherever the
  test was conclusive (*measured*).
- **Timestamps:** still undecided at tier 0; the A5 rig is the deciding measurement (*measured*: no route scored).
- **Bandwidth:** the same 81.1 % pair was refused and later admitted within 15 minutes. The topology model should
  treat about 80 % of a microframe as "may fail", and the app must handle a refusal at open time whatever the model
  predicts (*inferred*).
- **Kiyo:** the age theory is gone, and the trigger is unknown. The design rules from 11-06 stand: a first-frame
  watchdog, per-call timeouts, a "replug needed" state, no automatic device restart. Add one: a listing path that
  never binds a wedged camera (MF enumeration, not FFmpeg's) (*inferred* from §1 and §9).

## 14. Suggested next tests

1. **Replug the Kiyo** and confirm a 1-frame MF capture works. This is attended.
2. **W-MULTI on its own, repeated.** After a fresh replug, alternate rounds of DS (ffmpeg CLI) all-at-once and MF
   all-at-once with all four cameras, then the same with the Kiyo plus one other camera, and the Kiyo alone through
   DS. Log plug-in age, vendor processes and every re-arrival. Stop at the first wedge. If DS all-at-once wedges the
   Kiyo and MF all-at-once does not over the same number of rounds, that supports the multi-camera DirectShow
   trigger and MF-only capture. Repeat the MF HS13 pair after the DS rounds, so the §8 change can be separated from
   the API.
3. **Rerun `--only W-PYMF`** to score the generic camera's pymf cycles. If the camera drops off the bus again, run
   wincam alone for 60 cycles to see whether the drop follows the camera or the cycle pattern.
4. **Build and flash the A5 strobe rig** ([timing/rig/README.md](../timing/rig/README.md)). It is the only way to
   rate the frame-index-fit routes and decide G-TS at tier 0.
5. Optional: raise MF new-process cycles to ≥ 381 per camera if that claim is needed, and run W-PYAV-LIST once with
   a healthy Kiyo to confirm the listing slowdown is the wedge.

[summary]: ../results/windows/Gerald/suite_20261111T040003Z/summary.md
[run_suite]: ../results/windows/Gerald/suite_20261111T040003Z/run_suite.json
[W-ENV]: ../results/windows/Gerald/suite_20261111T040003Z/W-ENV.json
[W-POLICY]: ../results/windows/Gerald/suite_20261111T040003Z/W-POLICY.json
[W-TOPO]: ../results/windows/Gerald/suite_20261111T040003Z/W-TOPO.json
[W-ID]: ../results/windows/Gerald/suite_20261111T040003Z/W-ID.json
[W-FMT]: ../results/windows/Gerald/suite_20261111T040003Z/W-FMT.json
[W-FMT-NOGRAB]: ../results/windows/Gerald/suite_20261111T040003Z/W-FMT-NOGRAB.json
[W-CTRL-LIST]: ../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-LIST.json
[W-MJPEG]: ../results/windows/Gerald/suite_20261111T040003Z/W-MJPEG.json
[W-RAW]: ../results/windows/Gerald/suite_20261111T040003Z/W-RAW.json
[W-TS]: ../results/windows/Gerald/suite_20261111T040003Z/W-TS.json
[W-PYMF]: ../results/windows/Gerald/suite_20261111T040003Z/W-PYMF.json
[W-CTRL-EFFECT]: ../results/windows/Gerald/suite_20261111T040003Z/W-CTRL-EFFECT.json
[W-AUTO]: ../results/windows/Gerald/suite_20261111T040003Z/W-AUTO.json
[W-OCV-CTRL]: ../results/windows/Gerald/suite_20261111T040003Z/W-OCV-CTRL.json
[W-CYC-KIYO]: ../results/windows/Gerald/suite_20261111T040003Z/W-CYC-KIYO.json
[W-MULTI]: ../results/windows/Gerald/suite_20261111T040003Z/W-MULTI.json
[W-PYAV-LIST]: ../results/windows/Gerald/suite_20261111T040003Z/W-PYAV-LIST.json
[W-CYC]: ../results/windows/Gerald/suite_20261111T040003Z/W-CYC.json
[W-KIYO]: ../results/windows/Gerald/suite_20261111T040003Z/W-KIYO.json
[scene check]: ../results/windows/Gerald/scene_check_20261110/
[scene note]: ../results/windows/Gerald/scene_check_20261110/NOTE_SCENE_CHECK_NOT_RESULTS.txt
[consent pre]: ../results/windows/Gerald/camera_consent_20261109/consent_20261110_pre_run.json
[consent post]: ../results/windows/Gerald/camera_consent_20261109/consent_20261111_post_run.json
