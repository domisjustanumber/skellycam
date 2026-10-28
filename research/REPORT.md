# SkellyCam Research — Compiled Report

As of 2026-10-28. `research/` holds five studies that sit beside the skellycam package. None of them is imported by skellycam. This document condenses the five per-study reports. The index, with status and Claude Docs links, is in [README.md](README.md).

Labels used throughout: **measured** = run and logged on our hardware; **sourced** = from specs, vendor documents or source code; **computed** = arithmetic; **inferred/hypothesis** = a judgement not yet tested. Hardware for everything measured is one Windows 11 PC, "Gerald": Intel Core i7-14700K (20 cores, 28 logical), 64 GB DDR5 running at 4000 MT/s, Windows 11 Home 10.0.26300 ([overnight report](overnight_run_20261027/REPORT.md)). No Linux or macOS hardware run exists in any study.

## Executive summary

The biggest near-term win for skellycam is in the capture path it already has. Today skellycam captures through OpenCV, and OpenCV always decodes MJPEG. That costs 24.6–40% of one CPU core per camera (DirectShow) or 46–156% (Media Foundation), whereas Media Foundation or PyAV/DirectShow can hand over the camera's own JPEG bytes for about 1–2% of a core ([usb_cameras](usb_cameras/REPORT.md)). In the ring buffer benchmark, with the decode in the capture loop and synthetic cameras, the current code (HEAD, commit 23ccbf20) reaches only 53.56 / 53.57 fps at 5 cameras × 1080p against a 60 fps target. It loses 10.7% of sensor frames without reporting it. A small set of Python-only changes gets a prototype to 59.82 / 59.95 fps, and porting to C++ is not needed ([frame_ring_buffer](frame_ring_buffer/REPORT.md)). Timing is the second theme. Windows OS timestamps sit on a ~16 ms grid. The camera's own UVC timestamp is accurate to at most about 0.5 ms, but true cross-camera sync has not been established by any study. Hardware sync is planned two ways and has not been tested on hardware either way: an Arduino pulse to the FSIN (frame-sync input) pin of each camera ([arduino_sync](arduino_sync/REPORT.md), plan only) and PTP-synced GigE Vision cameras ([gige_vision](gige_vision/REPORT.md), emulators only). Two studies independently found the same skellycam bugs, and those are worth fixing now regardless of the rest: a stale frame is published after 30 failed grabs, and a camera config change can stall or end a recording (a failed config apply kills the backend). The decisions these studies point to are listed under [Recommended next steps](#recommended-next-steps).

## Status at a glance

| Study | Question | Status (2026-10-28) | Headline result | Report |
| --- | --- | --- | --- | --- |
| `usb_cameras/` | How can skellycam get native MJPEG, accurate timestamps, more cameras per USB bus and stable names from cheap UVC webcams? | In progress. Goals 1–4 measured on Windows only; goal 5 (cross-platform) not written | MF/PyAV MJPEG passthrough at ~1–2% of a core vs OpenCV 24.6–156%; UVC PTS at most ~0.5 ms error vs 4.4–5.0 ms for OS timestamps; one MJPEG camera per USB 2.0 link unless the driver is swapped to WinUSB | [usb_cameras/REPORT.md](usb_cameras/REPORT.md) |
| `frame_ring_buffer/` | Can SkellyCam move 5 × 60 fps frames to FreeMoCap through its shared-memory ring buffer, and would C++ help? | Done; audited and reproduced | HEAD 53.56 / 53.57 fps at 5×1080p, with silent drops; prototype 59.82 / 59.95 fps; C++ not needed | [frame_ring_buffer/REPORT.md](frame_ring_buffer/REPORT.md) |
| `gige_vision/` | How would SkellyCam support GigE Vision cameras with PTP clock sync? | Paused since 2026-10-25; test suite ready, backend not started | Use viva-genicam, one process per camera; PTP is a GEV 2.0 feature (not 3.0); nothing tested on a real camera | [gige_vision/REPORT.md](gige_vision/REPORT.md) |
| `arduino_sync/` | Can skellycam support an Arduino FSIN trigger box (as in MoCapSTR), and does Arduino clock accuracy matter? | Draft plan, not reviewed by a maintainer; nothing run | No Nano/Uno has a TCXO, and this does not matter for camera-to-camera sync; it plans 48 Hz Timer1 firmware at ~10 engineer-weeks; it found five existing skellycam bugs | [arduino_sync/REPORT.md](arduino_sync/REPORT.md) |
| `overnight_run_20261027/` | How did the unattended overnight run of 2026-10-27/28 go, and how far can its numbers be trusted? | Finished | Both workflows completed with 0 errors. The idle gate only checked at the start, the excluded Kiyo Pro was still contacted, and the per-benchmark load rule is the method to copy | [overnight_run_20261027/REPORT.md](overnight_run_20261027/REPORT.md) |

## Per-study summaries

### 1. USB (UVC) cameras — in progress

**Summary.** The study covers five goals: native MJPEG, capture timing, USB bandwidth, naming, and cross-platform design. Goals 1–4 were measured on Gerald with a Logitech C922, a Logitech C930e and a generic "USB Camera" 4C4A:4A55 on 2026-10-25. They were re-run and adversarially re-verified unattended on 2026-10-27/28. A Razer Kiyo Pro was excluded from the re-run as faulty. Goal 5 is not written, and Linux and macOS are unmeasured. Terms: UVC = USB Video Class, the standard webcam protocol. MF = Windows Media Foundation. PTS/SCR = timestamps on the camera's own clock in each UVC payload header. An "alt setting" is one of the fixed reserved-bandwidth slot sizes a camera offers. WinUSB is a generic driver that must replace the normal camera driver before libusb can drive the camera ([usb_cameras/REPORT.md](usb_cameras/REPORT.md)).

**Key findings.**
- **Native MJPEG (measured).** MF IMFSourceReader with the native MJPG type returned valid camera JPEGs on all three cameras at 720p30 and 1080p30, using 0.7–2.2% of one core. PyAV/FFmpeg DirectShow with `vcodec=mjpeg` returned byte-identical JPEG headers at 0.9–1.6%. OpenCV 4.12 never returns JPEG bytes. It used 24.6–40% of a core on CAP_DSHOW and 46–156% on CAP_MSMF, and CAP_MSMF takes 39–41 s to open each Logitech camera ([mjpeg/RESULTS.md](usb_cameras/mjpeg/RESULTS.md)). The generic camera delivers about 25.7 fps when asked for 30.
- **Timing (measured against a screen-flash ground truth).** Windows OS timestamps and host arrival times are quantized in ~16 ms steps, with 4.4–5.0 ms error on the C922. The C922's UVC PTS, read through MF after a one-time admin registry setting per camera, scores 0.47–0.68 ms. That is the floor of the test method, so it is an upper bound and the true accuracy is not yet known. The C930e PTS is a synthetic counter with two unexplained frame-period modes, and manual exposure set through MF is not reliably applied on that camera.
- **Bandwidth (measured).** Every camera requests its largest alt setting (about 24.5 MB/s, ~62% of the USB 2.0 periodic budget), and Windows grants it. So only one MJPEG camera fits per USB 2.0 link. The only working control found is to swap the driver to WinUSB and pick the alt in the app (libusb). The C930e then ran 30 fps on a static scene in 800 B slots at 720p and 1600 B slots at 1080p. With screen noise, 1080p at that slot fell to 19.2 fps.
- **Naming (measured).** Key cameras by USB serial when it is present and unique (only the C922 has one); otherwise use the physical port path. Device indices, MF paths and serial-less ContainerIds all changed during the study.
- **Open issue (measured drift, effect unknown).** The xHCI frame-number/QPC mapping that underpins libusb SCR timing is exact for only ~2–3.5 s and drifted by up to −641 µs over 20 s. The libusb result (SCR agrees with back-dated arrival to 46–66 µs robust sigma) therefore needs a longer re-check. Cross-camera sync is not established: the C930e−C922 offset varied with a standard deviation of 0.54–0.79 ms, which is at the method floor.

**Comparison (condensed).**

| Technique | Result | Cost / constraint | Verdict |
| --- | --- | --- | --- |
| MF IMFSourceReader, native MJPG | Camera's own JPEG, full rate, 0.7–2.2% core | Windows-only API | **Best** on Windows |
| PyAV / FFmpeg DirectShow `vcodec=mjpeg` | Same bytes, 0.9–1.6% core | PTS are nominal, not capture times | Python-friendly fallback |
| OpenCV CAP_DSHOW / CAP_MSMF (skellycam today) | Decoded BGR, 24.6–40% / 46–156% core | MSMF opens Logitech cameras in 39–41 s | Rejected for passthrough |
| Timestamp: OS / host arrival | 4.4–5.0 ms std error | none | Rejected (16 ms grid) |
| Timestamp: UVC PTS via MF metadata | ≤ 0.47–0.68 ms (method floor) | admin registry value once per camera; a camera with a real PTS | **Best** on the stock driver |
| Bandwidth: app-forced alt via libusb on WinUSB | 2 cameras on one link measured; 3–6 estimated by model, untested | driver swap, UAC prompt, replug; camera hidden from other apps | Only working method, unvalidated past 2 cameras |
| Native core: Rust `uvc_iso` on libusb | Streamed every run, 0.6–2.9% core | WinUSB | Best native candidate |

**Top further investigation.**
1. Re-check libusb SCR→QPC timing over 30–60 s runs.
2. Run WinUSB phase 3 with 3 or more cameras on one USB 2.0 link at forced alts.
3. Run the Linux drafts on real hardware, including `quirks=128` with MJPEG.
4. Run the macOS AVFoundation native-format probe.
5. Run controlled naming tests (reboot, replug, port move).

### 2. Frame ring buffer — done

**Summary.** This study looked at how frames move from SkellyCam's camera processes, through the shared-memory ring buffer, to recording and the UI, and whether C++ would help. All stages ran idle in the 2026-10-27/28 overnight run. A critique raised 34 issues (30 resolved, 4 partly), and a reproducibility re-run put 130 of 136 throughput rows within ±15%, with all 18 pass/fail rows unchanged ([frame_ring_buffer/REPORT.md](frame_ring_buffer/REPORT.md), [study_state/RESUME.md](frame_ring_buffer/study_state/RESUME.md)). **All 5 × 60 fps numbers use synthetic cameras**, because no attached real camera delivered more than 30.1 fps.

**Key findings (measured).**
- **HEAD misses 60 fps at 5×1080p** with the MJPEG decode in the capture loop: 53.56 / 53.57 fps, and 964 sensor frames (10.7%) never grabbed. SkellyCam does not count this loss, and its finalizer still passes. 5×720p holds 60.00 fps ([baseline/README.md](frame_ring_buffer/baseline/README.md)).
- **Where the time goes.** The loop body takes 15.77 ms (retrieve 10.04, put_frame 3.56, record 1.14 ms). With 2.49 ms of lockstep-gate idle, that gives an 18.69 ms group interval.
- **Removing `copy.copy` from `put_data` is the largest single gain:** 58.84 / 58.98 fps, against 54.14 for HEAD in the same session. A prototype with a seqlock ring and a decoupled recorder, keeping lockstep, reaches 59.82 / 59.95 fps. Add 3 ms more CPU per frame and it falls to 58.08 fps ([p8v_e2e_summary.md](frame_ring_buffer/prototypes/results/p8v_e2e_summary.md)).
- **Crash safety.** A killed MSMF .mp4 file has 0 of 300 frames readable, while MJPEG-in-MKV keeps 298 ([p11_crash_container.md](frame_ring_buffer/prototypes/results/p11_crash_container.md)). If one recorder stalls for 3500 ms without lockstep, that camera drifts by up to 606–639 ms, and frame-count checks miss it. `cv2.setNumThreads(1)` halves recorder CPU (1826% → 896%) at the same encode rate.
- **C++ is not needed.** A C++ port of put_frame is only 2–7% faster. With the same one-copy write, numpy takes 0.1466 ms and C++ 0.1456 ms ([cpp_comparison.md](frame_ring_buffer/cpp/results/cpp_comparison.md)). cv2 4.12 also decodes 1.57x and encodes 4.9x faster than the C++ OpenCV 4.8 SDK.

**Comparison (condensed).**

| Variant (5×1080p MJPEG, synthetic) | fps per camera | Verdict |
| --- | --- | --- |
| HEAD (23ccbf20) | 53.56 / 53.57 | Misses 60, with silent drops |
| HEAD minus `copy.copy` in put_data | 58.84 / 58.98 | Cheapest big win (rank 9) |
| Prototype: seqlock ring + decoupled recorder + lockstep | 59.82 / 59.95 | Recommended design (ranks 6, 7) |
| C++ put_frame / one-copy write | 2–7% faster; 0.1456 vs 0.1466 ms | Not worth it |

**Recommended build order** (rank titles from [recommend_result.json](frame_ring_buffer/study_state/recommend_result.json)):
1. Ranks 9, 3, 4, 5 and 2: remove `copy.copy`, never re-publish stale frames after 30 failed grabs, guard recording state, count sensor drops live, and use crash-tolerant containers.
2. Rank 1: contain failures so that a UI error cannot end a recording.
3. Ranks 6, 11 and 7 together with 13 and 10: the seqlock ring v2, the decoupled recorder, and `setNumThreads(1)`.
4. Ranks 12, 14 and 15.

Rank 8, MJPEG passthrough, is a separate project.

**Top further investigation.**
1. Test with real 5 × 60 fps cameras: measure capture CPU, USB bandwidth, which thread decodes on DSHOW, and whether the drop counter is accurate.
2. Ship the first build group and re-measure, and check that FreeMoCap reads MKV or fragmented MP4.
3. Make a 10+ minute recording through the real encoders, with Defender on and a nearly full disk, to size the ring.

### 3. GigE Vision with PTP — paused

**Summary.** Nine research topics were fact-checked: 161 claims, of which 132 were supported, 27 partly supported and 2 refuted. A stand-alone hardware test suite ([hardware_tests/](gige_vision/hardware_tests/)) is ready, but it has only been verified against emulators. **No real GigE camera, NIC or switch was used.** Everything ran on Gerald, natively and in Docker on WSL2, against the Aravis and viva-genicam camera emulators ([gige_vision/REPORT.md](gige_vision/REPORT.md), [RESUME.md](gige_vision/RESUME.md)). PTP = IEEE 1588 Precision Time Protocol. GIL = Python's global interpreter lock.

**Key findings.**
- **The starting premise was wrong (sourced).** PTP and scheduled action commands arrived in GigE Vision 2.0 (2011), not 3.0. GEV 3.0 (May 2026) mainly adds RDMA streaming for 10 GbE and faster links. PTP is optional in every version.
- **Frames arrive as raw Bayer or Mono pixels over UDP, so bandwidth is the limit (computed).** 1920×1200 BayerRG8 at 60 fps is 1105.9 Mbit/s, which is 0.86 cameras per 1 GbE link. 1440×1080 at 60 fps is 746.5 Mbit/s, or 1.28 per link.
- **The host socket buffer decides whether frames arrive complete (measured, emulators).** With the 425,984 B cap of Linux in Docker, three runs gave 23/77, 73/76 and 64/76 complete frames. A forced 64 MiB buffer gave 76/76. The numbers vary a lot between runs, but the direction is consistent.
- **Python threads collapse under the GIL; one receiver per process is fine (measured, loopback).** With 4 simulated 1 GbE cameras on threads in one process, 74.77% of packets were lost on WSL2 and 39.33% on Windows ([bench_multicam_windows.txt](gige_vision/scratch/research/bench_multicam_windows.txt)). A single receiver lost 0% using 21–34% of a core. SkellyCam already runs one process per camera by default. N processes have not been benchmarked beyond 2.
- **Library pick: viva-genicam 0.10.0 (MIT, PyPI wheels).** It is the only open-source library found that sends scheduled action commands, and it releases the GIL. Its gaps: no PTP helpers, no socket-buffer control from Python, a fixed 4-frame queue, no open-by-IP, and a `ts_host` that is not a receive time.
- **What SkellyCam would need (from code reading):** a `CameraBackend` protocol (OpenCV is hard-wired today), a separate `device_timing` record, and host `frame_number` kept as the pairing key.

**Comparison (condensed).**

| Option | Scheduled actions | Python threading | Verdict |
| --- | --- | --- | --- |
| viva-genicam 0.10.0 | Yes (encoding verified on the wire; acknowledged only by its own emulator) | Releases GIL (measured) | **Chosen** |
| telegenic 2.1.0 | No | Not measured | Fallback, plus a separate action sender |
| Aravis / Harvesters / pyGigEVision / vendor SDKs | No, producer-dependent, no, mostly yes | Harvesters holds the GIL in `fetch()` | Rejected: packaging, GIL, bugs, vendor lock-in |
| Receive design: threads in one process (CPython 3.12) | — | 39–75% loss at 4 cameras | Fails |
| Receive design: one receiver per process | — | 0% loss for one receiver | **Chosen**, not benchmarked at N > 2 |
| Exposure alignment: scheduled ACTION_CMD / vendor PTP free-run / post-hoc pairing | — | — | Primary / per-vendor / fallback (none tested on hardware) |

**Top further investigation.**
1. Run `hardware_tests/` on two or more real PTP cameras on one PoE switch. The test passes if the p95 spread in exposure start is ≤ 100 µs.
2. Run two-PC, real-NIC receive tests with N cameras in N processes.
3. Resume the implementation workflow: the backend protocol, the viva backend and the `device_timing` record.

### 4. Arduino FSIN hardware sync — draft plan

**Summary.** The question was how skellycam could support an Arduino "sync box" like the one in the third-party project MoCapSTR (GPL-3.0). The box sends one pulse per frame to each camera's FSIN pin (the InnoMaker OV9281 in MoCapSTR's case). The user also asked whether Arduino clock accuracy matters. A 10-agent workflow produced [PLAN.md](arduino_sync/PLAN.md). **No hardware was used, no code was written, and no maintainer has reviewed the plan.** Every number is a datasheet value, a third-party measurement, MoCapSTR's own claim, or a calculation ([arduino_sync/REPORT.md](arduino_sync/REPORT.md)).

**Key findings.**
- **No Nano or Uno has a TCXO** (temperature-compensated crystal oscillator). Genuine boards use a ceramic resonator rated ±0.5% initial (sourced). Clock error does not affect camera-to-camera sync, because one edge drives every camera (inferred).
- **Clock error does affect the absolute rate:** at 48 Hz, ±0.5% is ±0.3 s per minute or ±18 s per hour (computed). The plan's fix is to measure the real rate on the host and wire the same pulse into other instruments.
- **Clock error can break sync near the camera's re-trigger lockout.** MoCapSTR reports that the InnoMaker ignores pulses within ~18–20 ms of a triggered frame (their measurement, not ours). A resonator 0.5% fast turns a nominal 50 Hz into a 19.90 ms period, but at 48 Hz the period is 20.73 ms, hence the 48 Hz default (computed).
- **Design:** "skellysync" firmware on Timer1 fast PWM mode 14, giving cycle-exact edges on D9 and D10 at −8 ppm quantization for 48 Hz. Trigger mode is verified by stopping the pulses and checking that frames stop. v1 targets the InnoMaker on Windows and Linux at about 10 engineer-weeks. The time from FSIN edge to exposure start is unknown, possibly up to ~1 ms.
- **Five existing skellycam bugs (P1–P5) block sync work** and are worth fixing anyway. P1: the config round-trip drops fields. P2: a config-apply failure kills the backend. P5: pause and unpause have no timeout. These three are confirmed in code. P3, the 30-retry grab give-up, is partly confirmed. P4, the `to_json` breakage, is plausible but has not been run.

**Comparison (condensed, on paper only).**

| Option | Edge jitter | Verdict |
| --- | --- | --- |
| MoCapSTR firmware: `loop()` polls `micros()` | ~4–20 µs estimated; +16 ppm rate error at 48 fps | Kept as a legacy protocol only |
| Timer1 mode 15 | Cycle-exact | Rejected (loses pin D9) |
| **Timer1 mode 14, D9 + D10** | Cycle-exact, −8 ppm at 48 Hz | **Chosen** |
| Trigger check by measuring frame intervals | — | Rejected: lockstep makes a free-running camera look triggered |
| **Trigger check by pulse removal** (`<STOP>`, then `<BURST:10>`) | — | **Chosen** |

**Top further investigation.**
1. Maintainer review of PLAN.md's six open questions.
2. Ship P1–P5 as standalone PRs.
3. A 1-week hardware spike, to find out:
   - whether DirectShow accepts the trigger control on a camera that is already streaming;
   - how the lockout varies;
   - the skew from FSIN edge to exposure start.
4. Copy the surviving research out of a temp scratchpad into the repo before it is deleted.

### 5. Overnight run 2026-10-27 — finished

**Summary.** On 2026-10-27, after 23:00, two unattended jobs ran. The USB camera re-run (`wf_ef322d5c-d99`) ran 23:03–00:57 with 13 of 13 agents and 0 errors. The ring buffer completion (`wf_8fd1ec97-b0e`) ran 00:57–07:32 with 10 of 10 agents and 0 errors ([overnight_run_20261027/REPORT.md](overnight_run_20261027/REPORT.md), [OVERNIGHT_LOG.md](overnight_run_20261027/OVERNIGHT_LOG.md)). This study is about how far the run's numbers can be trusted, not about cameras.

**Key findings (measured).**
- **The idle gate checked only once.** It fired at 23:02:07, when there had been no input for 8,697 s and CPU was at 3.3%. After that, up to six camera agents shared the machine. camlock waits reached 472 s, and agents changed each other's camera controls (exposure was seen flipping mid-run).
- **The "excluded" Razer Kiyo Pro was contacted by both workflows.** The camera run reached it through libusb/rawusb enumeration and GStreamer `ksvideosrc`. The ring buffer prototypes opened DirectShow indices 0–3, probably including the Kiyo (the mapping is not recorded), and tried to open it by name. The exclusion was never passed to the second workflow.
- **The in-scope cameras stayed healthy at every check up to 04:53Z.** The generic camera re-arrived twice with no cause recorded. LogiTune respawned within seconds every time it was stopped.
- **Every ring buffer measuring step but one met a per-run idle rule:** background CPU below 10%, and background mean 1.6–4.6% in practice. The exception, a row hit by a Defender scan, was marked provisional and superseded. On a quiet machine the headline moved from 44.01 / 46.78 fps (loaded, 10-25) to 53.56 / 53.57 fps, but the verdict did not change.
- **The camera verifiers** returned 66 confirmed, 19 weakened, 2 refuted and 2 unverifiable verdicts. They listed 27 tests that could have run unattended but did not.

**Comparison (condensed).**

| Run design | Load control | Trust |
| --- | --- | --- |
| Ring buffer, 2026-10-25 daytime | None (one snapshot: 62% CPU) | Provisional; superseded |
| Camera re-run, overnight | Idle check at start only; up to 6 agents at once | Good for function and fps; weak for CPU% and control-dependent results |
| Ring buffer, overnight | Per-benchmark idle rule; stages run one at a time | **Best design**: 130/136 rows reproduced within ±15% |

**Top further investigation.**
1. Make exclusions enforceable: unplug the device, or keep one shared list that every workflow reads.
2. Isolate or reset camera controls for each capture.
3. Re-run the CPU-sensitive camera tests one at a time, plus the 27 missed tests.
4. Log PnP events, power state and Defender activity.
5. Add per-step timeouts to the harness.

## Cross-cutting themes

- **MJPEG passthrough links the USB and ring buffer studies.** The ring buffer's 5×1080p shortfall is dominated by retrieve and decode (10.04 ms of a 15.77 ms loop body). The USB study shows that the decode is avoidable on Windows: MF or PyAV hand over camera JPEGs for ~1–2% of a core, where OpenCV takes 24.6–156%. The ring buffer ranks this as a separate project (rank 8). Together the two studies suggest passthrough is the largest remaining CPU lever once ranks 9 and 6/7 land (inferred). It depends on FreeMoCap accepting MKV or fragmented MP4, which is still unchecked.
- **Lockstep is not sync, and no study has measured true sync.** The ring buffer finds that lockstep aligns `grab()` calls, not exposures, and frames of the same index differ by 7–13 ms median, up to 20.2 ms. The USB study's best cross-camera estimate is at its ~0.5 ms method floor and is not established. The Arduino plan notes that lockstep can make a free-running camera look triggered. GigE PTP sync is entirely untested. All three timing efforts need an independent ground truth, such as an LED or a flash with no display scan-out.
- **Device timestamps need their own record.** The USB study wants UVC PTS, the GigE study wants device/PTP ticks, and the Arduino plan wants a pulse counter. GigE's code review warns against putting device-clock values into the lifecycle-timestamp dtype, which subtracts a host offset. One shared `device_timing` record and a `CameraBackend` protocol would serve all three.
- **Two studies found the same skellycam bugs independently.** The ring buffer's rank 3 (never re-publish a stale frame after 30 failed grabs) and rank 4 (no config apply while recording) overlap the Arduino plan's P3 and P2. The ring buffer's rank 5 (count sensor drops) addresses the silent 10.7% loss. These are fixable now, without any new hardware.
- **Frame pairing by host frame number is fragile.** Both the GigE study (device-dropped frames would be mis-paired) and the ring buffer study (uncounted sensor drops; a stalled recorder without lockstep drifts 606–639 ms undetected) show that frame-count checks miss real loss.
- **Limits common to all five studies.**
  - Everything ran on one Windows PC, Gerald, or nothing was run at all.
  - There are no Linux or macOS hardware results.
  - Real-camera rates never exceeded 30.1 fps, so every 60 fps number is synthetic.
  - Several key results are at the floor of their measurement method.
  - Much of the review was done by AI agents, and some intermediate research survives only in temp folders.

## Recommended next steps

Ordered by value for effort. Studies are tagged in brackets.

1. **Fix the known skellycam bugs now.** These are the ring buffer's ranks 9, 3, 4, 5 and 2 and the Arduino plan's P1–P5, with the overlaps merged: the copy in put_data, the stale frame after 30 failed grabs, config-apply killing the backend, the dropped config fields, no pause timeout, silent sensor drops, and crash-tolerant containers. Trace P3 and run P4 first. *[frame_ring_buffer, arduino_sync]*
2. **Prototype MJPEG passthrough on Windows** through MF IMFSourceReader (or PyAV DirectShow), and confirm that FreeMoCap reads MKV or fragmented MP4. *[usb_cameras, frame_ring_buffer]*
3. **Test with real 60 fps cameras.** Measure 5 × 60 fps capture CPU, USB bandwidth admission and drop-counter accuracy, and run a 10+ minute recording to size the ring. *[frame_ring_buffer, usb_cameras]*
4. **Add a `CameraBackend` protocol and a `device_timing` record**, then feed UVC PTS (MF metadata) into it. This unblocks both GigE and hardware-sync work. *[gige_vision, usb_cameras]*
5. **Build an independent sync ground truth** (an LED, no display) and measure real cross-camera alignment for lockstep, UVC PTS and, later, FSIN or PTP. *[usb_cameras, frame_ring_buffer, arduino_sync]*
6. **Close the open USB timing and bandwidth questions:** the long-run SCR→QPC re-check, and WinUSB phase 3 with 3 or more cameras per link. These need one UAC prompt and replugs. *[usb_cameras]*
7. **Hardware spikes for the sync options:**
   - the 1-week Arduino M0 spike on InnoMaker cameras, after maintainer review of PLAN.md;
   - `hardware_tests/` on two or more real PTP GigE cameras.

   *[arduino_sync, gige_vision]*
8. **Cover the other platforms:** Linux uvcvideo (`quirks=128`, the V4L2 metadata node) and the macOS AVFoundation native-format probe. *[usb_cameras, gige_vision]*
9. **Harden unattended runs:**
   - enforce device exclusions in every workflow, or unplug the device;
   - reset camera controls for each capture;
   - apply the per-benchmark load rule to camera CPU tests;
   - add per-step timeouts;
   - save journals for every workflow.

   *[overnight_run_20261027]*
10. **Housekeeping:**
    - copy the Arduino scratchpad research into the repo;
    - fix the stale lines in `frame_ring_buffer/study_state/RESUME.md` (rank 13, run end time);
    - finish the empty sections in the USB and GigE Claude Docs.

    *[arduino_sync, frame_ring_buffer, usb_cameras, gige_vision]*
