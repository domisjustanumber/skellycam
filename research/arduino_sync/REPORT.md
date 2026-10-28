# Arduino FSIN hardware sync — Report

Status as of 2026-10-28: a **draft plan dated 2026-10-25**, not reviewed by a maintainer, with **no experiments run and no code written**. The plan is [PLAN.md](PLAN.md). The Workflow script that produced it is [workflows/arduino-sync-plan-wf_1cd252bb-775.js](workflows/arduino-sync-plan-wf_1cd252bb-775.js). The only intermediate research that survives is in an earlier session's temp scratchpad, outside the repo (see [Where to look](#where-to-look)).

## Executive summary

The question was how skellycam could support an Arduino "sync box" like the one in the third-party project [MoCapSTR](https://github.com/ZClassified/MoCapSTR) (GPL-3.0). The box sends one electrical pulse per frame to the FSIN (frame-sync input) pin of each camera; MoCapSTR uses it with InnoMaker OV9281 global-shutter USB cameras. The user also asked how accurate the clocks on Arduino Nano/Uno boards are, whether they have a TCXO (temperature-compensated crystal oscillator), and whether it matters.

A Workflow of ten AI agents did the work. They read the MoCapSTR source, researched board clocks and UVC (USB Video Class) camera triggering on the web, mapped skellycam's code, checked the clock research, drafted a plan, critiqued it against the code and from a hardware angle, and rewrote it. The output is a plan, not findings. Every number in it comes from a datasheet, a third-party measurement, MoCapSTR's own documentation, or a calculation. None was measured on skellycam hardware.

**The answer on clocks.** No Nano or Uno has a TCXO. Genuine boards use a ceramic resonator rated ±0.5% initial. This does not matter for keeping cameras in sync with each other, because one edge drives every camera. It does matter in two places:
- the absolute frame rate, which can drift by ±18 s per hour at the resonator's ±0.5% initial tolerance (about ±36 s at its ±1% worst case);
- the InnoMaker's reported ~18–20 ms re-trigger lockout, which is why the plan defaults to 48 Hz and measures the real rate on the host.

**The proposed design** has four parts:
- new "skellysync" firmware that drives the trigger pins from the ATmega328P's Timer1 hardware;
- a skellycam serial-device manager;
- trigger settings owned by the server;
- a verification step that stops the pulses and checks that the cameras stop.

v1 targets the InnoMaker OV9281 on Windows and Linux, at about 10 engineer-weeks.

**The most useful result for skellycam right now has nothing to do with sync.** The plan lists five existing skellycam bugs (P1–P5) that it says must be fixed first. The code lines it cites match; P1, P2, P3 and P5 are confirmed by reading the code, while P4 was only partly checked (see finding 10).

## Key findings

All items below come from a plan. "Measured" here only ever means measured by a third party; nothing was measured for this study. "Computed" means the arithmetic was redone for this report.

1. **No Nano or Uno board has a TCXO.** Genuine Uno R3 and Nano V3 boards clock the ATmega328P from a Murata CSTCE16M0V53 ceramic resonator: ±0.5% initial, about ±1% worst case once temperature and aging are included. Clones may have a ±20–100 ppm crystal or a resonator. This varies by board, so each board has to be checked. *Confidence: provisional. The web research was checked against Arduino schematics and datasheets by a verifier agent; the clone claim was marked unverifiable.* Source: [PLAN.md §TL;DR](PLAN.md).
2. **Clock error does not affect inter-camera sync, as long as every camera accepts every pulse.** One edge drives all FSIN inputs, so oscillator error is the same for every camera. *Confidence: inferred (reasoning, not measured).* Source: [PLAN.md §TL;DR](PLAN.md).
3. **Clock error does affect the absolute rate.** At a nominal 48 Hz, ±0.5% is ±0.24 Hz, which is ±0.3 s per minute and ±18 s per hour. A 20 ppm crystal gives 1.2 ms per minute and 72 ms per hour. *Confidence: computed (re-derived; the plan's figures match).* Source: [PLAN.md §1 table](PLAN.md). The plan fixes this in two ways. The host fits the real rate from its `perf_counter_ns` frame timestamps and the firmware's pulse counter. Any other instrument (audio, EMG, force plates) gets the same TTL edge wired into it.
4. **Clock error can break inter-camera sync near the lockout.** MoCapSTR reports that the InnoMaker OV9281's USB bridge ignores any pulse arriving within ~18–20 ms of a triggered frame, which caps triggered capture at 50 fps. In their sweeps, 60 Hz gave 30 fps, 90 Hz gave 45 fps and 120 Hz gave 40 fps. A resonator running 0.5% fast turns a nominal 50 Hz into a 19.90 ms period, which falls inside that window, so cameras could reject *different* pulses. At 48 Hz the fast-case period is 20.73 ms, which clears it. *Confidence: the lockout figure is MoCapSTR's own measurement on their cameras, not ours; the periods are computed.* Sources: [PLAN.md §1](PLAN.md); MoCapSTR `README.md` lines 42–43 and `CHANGELOG.md` lines 49–50 and 116 (local clone, see [Where to look](#where-to-look)). The first clock-research report missed this failure mode; the timing verifier added it.
5. **The −761 ppm and 8.7 ppm/°C figures come from one board.** That board was a single Pro Mini with a resonator of unspecified make. A third party (Joris van Rijn) measured it against a GPS PPS signal while it was warm. The verifier notes that the temperatures were read from the AVR's internal sensor (±10 °C accuracy), so the per-°C coefficient is rough. *Confidence: measured by a third party, n = 1.* Source: [PLAN.md §1](PLAN.md); scratchpad `timing_report.md` and `verify.json`.
6. **Timer1 quantization is negligible.** 48 Hz at prescaler 8 is 41 667 ticks, which gives 47.9996 Hz (−8 ppm). MoCapSTR instead computes the interval with integer division, `1000000/fps`, which gives 0 ppm at 50 fps, +16 ppm at 48 fps and +40 ppm at 60 and 120 fps. *Confidence: computed.* Sources: [PLAN.md §4 Timing](PLAN.md) for the −8 ppm; scratchpad `timing_report.md` §2 for MoCapSTR's 50, 60 and 120 fps figures; the 48 fps truncation figure was computed for this report.
7. **115200 baud at 16 MHz with U2X is +2.1% off.** The plan says this stays inside the 8N1 limit even with a −0.5% resonator. *Confidence: the +2.1% is computed; the claim that it stays under the limit is the plan's.* Source: [PLAN.md §1](PLAN.md).
8. **Inter-camera skew from FSIN edge to exposure start is unknown.** The plan says it "could be up to about 1 ms" and may be set by the camera's bridge firmware. No vendor or third-party figure was found. *Confidence: unverified estimate.* Source: [PLAN.md §1](PLAN.md); scratchpad `timing_report.md` line 83.
9. **One ATmega pin can drive one camera.** The OV9281's FSIN is an opto-isolated input that draws about 19 mA at 5 V. The plan's reference wiring options are:
   - 2 cameras driven directly (D9 + D10);
   - 7–8 cameras through a ULN2803 low-side sink;
   - 4–6 cameras through a 74ACT541 buffer (±24 mA per output; the plan originally also listed 74AHCT541, which is rated only ±8 mA);
   - any number with one transistor per camera.

   A 74HCT541 is not suitable, because its outputs are rated ±6 mA. By these figures, MoCapSTR's 4-way splitter from a single pin needs a buffer. *Confidence: provisional (datasheet and vendor figures via the plan; not measured).* Source: [PLAN.md §4 Electrical](PLAN.md).
10. **Five existing skellycam bugs block sync work (P1–P5).** Each was checked against the code for this report:
    - **P1.** `extract_config_from_cv2_capture` builds a fresh `CameraConfig` without `use_this_camera`, `capture_fourcc` or `writer_fourcc`, so those fields fall back to their defaults. *Confirmed in code* ([opencv_extract_config.py](../../skellycam/core/camera/opencv/opencv_helpers/opencv_extract_config.py) lines 35–47).
    - **P2.** `apply_camera_configuration` re-raises any exception as `FailedToApplyCameraConfigurationError`. `check_for_new_config` does not catch it, so it reaches the camera loop's `kill_everything()` at line 122. *Confirmed in code* ([opencv_apply_config.py](../../skellycam/core/camera/opencv/opencv_helpers/opencv_apply_config.py) lines 99–103, [check_for_new_config.py](../../skellycam/core/camera/opencv/opencv_helpers/check_for_new_config.py) lines 33–41, [opencv_camera_loop.py](../../skellycam/core/camera/opencv/opencv_camera_loop.py) line 122).
    - **P3.** The grab retry loop gives up after `MAX_FAIL_COUNT = 30` failures and then carries on to publish and record. `frame_durations_seconds` is also appended inside the retry loop. *Confirmed in code by static reading* ([opencv_camera_loop.py](../../skellycam/core/camera/opencv/opencv_camera_loop.py) lines 24 and 72–86). The loop exits after 30 failures without checking `frame_success`, the frame number only advances on a successful grab, and `VideoRecorder._validate_frame_number` ([video_recorder.py](../../skellycam/core/recorders/videos/video_recorder.py) lines 149–156) raises on the repeated number, which kills the backend (the same chain as the ring buffer's rank 3). It has not been reproduced on a camera (traced 2026-10-28).
    - **P4.** `RecordingTimestampsStats.to_json` falls back to `o.__dict__` for anything that is not a dataclass, list or dict. The plan says this breaks on numpy recarrays and `RecordingInfo`. *Plausible from the code; not run* ([recording_timestamp_stats.py](../../skellycam/core/timestamps/recording_timestamp_stats.py) lines 123–143).
    - **P5.** `pause()` and `unpause()` wait in a loop with no timeout. *Confirmed in code* ([camera_orchestrator.py](../../skellycam/core/camera_group/camera_orchestrator.py) lines 58–78). This is a risk of hanging rather than crashing.

    Note: the plan's TL;DR said four prerequisite fixes while §5.1 and milestone M1 list five; the TL;DR was corrected to five on 2026-10-28. Source: [PLAN.md §5.1](PLAN.md).

## Techniques compared

No technique was built or measured. The options below were compared on paper by the workflow's research, verifier and critique agents. Each verdict is the plan's decision. The numbers are datasheet figures, estimates or calculations.

**Pulse generation (firmware)**

| Option | Edge jitter | Rate error from firmware | Trigger outputs | Pulse counting | Verdict |
|---|---|---|---|---|---|
| MoCapSTR 1.5.0: `loop()` polls `micros()`, `digitalWrite` on D2, `String` serial parsing in the same loop | ~4–20 µs estimated, with larger outliers during serial traffic (not measured) | Integer `1000000/fps`: 0 ppm at 50 fps, +16 ppm at 48 fps, +40 ppm at 60 and 120 fps | 1 pin (D2) | None; a stall can drop a pulse via the re-align branch | Kept only as a legacy protocol, so existing boxes keep working |
| Timer1 fast PWM mode 15 (TOP = OCR1A), output on OC1B/D10. This was the first research recommendation. | Cycle-exact (62.5 ns steps); only oscillator phase noise remains, inferred to be well under 1 µs | Prescaler/TOP quantization only | 1 (OCR1A is used as TOP, so D9 is lost) | TOV1 overflow ISR; the hardware critique found this racy | Rejected: loses D9 |
| **Timer1 fast PWM mode 14 (TOP = ICR1), OC1A/D9 + OC1B/D10** | Cycle-exact, as above | −8 ppm at 48 Hz | 2 | Counted in the `TIMER1_COMPA` ISR with a 64-bit tick base; STOP and BURST are decided there | **Chosen** |

The research preferred mode 15 because ICR1, unlike OCR1A, is not double-buffered. The final plan refuses RATE, PERIOD and PULSE changes while pulses are running. The plan gives prescaler glitches and one-off short periods as its reason; the link to ICR1 is this report's inference. Sources: [PLAN.md §4](PLAN.md), [§Corrections applied](PLAN.md); scratchpad `timing_report.md` lines 39–65; [workflow script](workflows/arduino-sync-plan-wf_1cd252bb-775.js) line 17 (description of the MoCapSTR firmware).

**Clock source**

| Clock | Spec / measured | Drift at 48 Hz per hour | On Nano/Uno? | Verdict |
|---|---|---|---|---|
| Ceramic resonator (genuine Uno R3 / Nano V3) | ±0.5% initial (spec); −761 ppm on one Pro Mini | ±18 s (spec); 2.7 s (that unit) | Yes | Accepted; the host measures the real rate |
| Crystal (some clones) | ±20–100 ppm typical | 72 ms at 20 ppm | Some clones | Free improvement, not required |
| TCXO (e.g. DS3231 module) | ±2 ppm | 7.2 ms | No | Deferred until after v1 as optional PPS/DS3231 calibration (not part of any planned milestone) |
| Uno R4 (RA4M1 HOCO) / Nano Every (internal RC) | ±1% / up to ±4% | — | — | Unsupported: no ATmega328P Timer1 |

Sources: [PLAN.md §1, §2, §TL;DR](PLAN.md); scratchpad `timing_report.md` table and `verify.json`. The Nano Every's ±4% at 5 V is the verifier's correction.

**Verifying that a camera is really in trigger mode**

| Option | What it checks | Problem | Verdict |
|---|---|---|---|
| Measure frame intervals and compare them with the pulse rate | Whether the rates match | skellycam's lock-step grab gating, its BUFFERSIZE setting and a matching stream fps make a free-running camera look triggered. Frames also stop flowing while `updating` is set. | Rejected by both critiques (the hardware critique rated it a blocker) |
| **Pulse removal while paused**: send `<STOP>` and wait 2T (two pulse periods); every camera's probe count must stay 0. Then send `<BURST:10>`; every count must reach 10 (protocol 2). | Whether the camera produces frames only when pulsed | Needs a new probe counter in the paused loop; the burst tolerance is not yet known | **Chosen** |

Source: [PLAN.md §5.5 step 5, §Corrections applied](PLAN.md).

The winner in each table is a design choice that still needs the M0 hardware spike to confirm it. In particular, nobody has tested whether Windows DirectShow (DSHOW) accepts the trigger control on a camera that is already streaming.

## Areas of interest

- **Trigger mode is switched on through a standard UVC control.** On the InnoMaker U20CAM-9281M, setting `CT_FOCUS_AUTO` (autofocus) puts the camera into FSIN trigger mode. A camera left in trigger mode after a crash will look dead to free-running software. The plan therefore switches it back in the camera worker's `finally` block and keeps a `triggered_cameras.json` recovery list. Source: [PLAN.md §2, §5.4](PLAN.md).
- **Lock-step gating interacts with triggering.** skellycam's orchestrator stalls the healthy cameras while one camera is late. So "starvation" must be measured only from time spent inside `grab()`. A grab that returns instantly gives only an upper bound on when the frame arrived. Source: [PLAN.md §5.5, §5.6](PLAN.md).
- **Stream fps is fixed when the camera opens.** Changing the framerate on a config update is disabled, so changing the trigger rate means re-creating the camera group. Source: [PLAN.md §5.4](PLAN.md).
- **Opening the serial port resets the board.** Opening an Arduino's port triggers a DTR auto-reset. So detection must never open a port, "Identify" must refuse to run on the port in use, and every open re-sends the full config. CH340 clones have no USB serial number, so port keys fall back to VID:PID plus the port's location. Source: [PLAN.md §5.2](PLAN.md).
- **Downstream framerate.** freemocap would read the measured rate from `{rec}_info.json → sync.measured_rate_hz` first, because `_stats.json` is unreliable today (bug P4). Source: [PLAN.md §7](PLAN.md).
- **Licensing.** MoCapSTR is GPL-3.0 and skellycam is AGPL-3.0-or-later. The plan reimplements from a written protocol spec, copies no code and does not ship MoCapSTR's `.hex`. The plan notes that this is not legal advice. Source: [PLAN.md §3](PLAN.md).

## Limitations and caveats

- **No hardware, no code, no measurements.** Nothing in this folder was run on skellycam hardware or on any OS. Every performance figure is a datasheet value, a third-party measurement, a claim by MoCapSTR about their own setup, or a calculation.
- **All review was by AI agents.** The "independent reviewers" mentioned in [PLAN.md](PLAN.md) are the workflow's verifier and critique agents. The two verifiers checked only the clock-timing report and the FSIN voltage claims. The MoCapSTR read and the skellycam code map were checked only indirectly: the hardware critique cross-checked the plan against the MoCapSTR source, and the code-fit critique against skellycam's code. No maintainer has reviewed the plan ([README.md](../README.md)).
- **The third-party clock data comes from a single unit.** The −761 ppm, 8.7 ppm/°C and 286 ppm wander figures all come from one warm Pro Mini, and its temperatures came from the AVR's ±10 °C internal sensor (scratchpad `verify.json`).
- **The lockout is MoCapSTR's figure.** The ~18–20 ms window and the 50 fps cap come from MoCapSTR's own sweeps at 1280×720 and 640×400. MoCapSTR attributes it to the camera's bridge firmware. It has not been reproduced.
- **The electrical figures are unmeasured.** Nobody has tested the ~19 mA FSIN current or the camera count for each wiring option.
- **Most of the intermediate research is not in the repo.** Only the clock-timing report (`timing_report.md`) and the verifier and critique output (`verify.json`) survive, in a temp scratchpad. The MoCapSTR deep read, the UVC trigger research, the skellycam code map and the first draft were not saved there.
- **Code line references were valid on 2026-10-28** (commit `23ccbf20`) and will drift as the code changes.

## Proposed further investigation

1. **Get a maintainer to review [PLAN.md](PLAN.md) and answer its six open questions (§11).** The most important are whether an InnoMaker-only v1 on Windows and Linux is acceptable, and whether the firmware should live in this repo. *Decides* whether the 10-week project goes ahead, and its scope.
2. **Ship P1–P5 as standalone PRs now (milestone M1, 1.5 weeks).** They are bugs today, whether or not sync goes ahead. P1, P2, P3 and P5 are confirmed by reading the code. Before fixing P4, run its `to_json` on a real recording. *Decides* nothing about sync, but removes crash paths that would block it.
3. **Run the 1-week M0 hardware spike (§9) before writing any sync code.** It should answer four questions:
   - Does a DSHOW `AUTOFOCUS` write on the streaming camera handle actually switch on trigger mode? If not, the plan falls back to MSMF or ships Linux first (risk 1).
   - How does the lockout vary with stream fps, exposure and resolution?
   - What is each camera's skew from FSIN edge to exposure start? The plan's method is a 0–25 ms sweep with a 50 µs flash.
   - How long does each loop pass take at 48 Hz × 4 cameras while recording?

   *Decides* go/no-go on each item, the default rate and the UI's rate cap.
4. **Measure the board clock instead of assuming it.** Put a logic analyzer on D2 running the current MoCapSTR firmware and on a Timer1 prototype, to confirm the ~4–20 µs jitter estimate against cycle-exact edges. Also measure the actual rate of the boards on hand against the host clock. *Decides* whether a fast resonator near 50 Hz is a real risk on the boards users actually have.
5. **Move the surviving research into the repo before the temp folder is cleaned up.** That means `timing_report.md` and `verify.json` from the scratchpad listed below. The downloaded InnoMaker manual and control scripts, the Arduino schematic PDFs and the MoCapSTR clone in the same folder are also useful references for M0.

## Where to look

- [PLAN.md](PLAN.md) — the plan:
  - TL;DR and the clock-accuracy table (§1);
  - scope (§2), protocol and licensing (§3), firmware (§4);
  - backend, including P1–P5 (§5);
  - API and UI (§6), freemocap changes (§7), tests (§8);
  - milestones (§9), risks (§10), open questions (§11);
  - a list of the corrections made after the critiques.
- [workflows/arduino-sync-plan-wf_1cd252bb-775.js](workflows/arduino-sync-plan-wf_1cd252bb-775.js) — the Workflow that produced the plan: 4 research agents, 2 verifiers, 1 draft, 2 critiques and 1 final rewrite.
- [../README.md](../README.md) — index of all research studies.
- Outside the repo, in a temp folder that may be deleted: `C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/a9b9d5dd-3ef8-4726-a4e0-a9884ba8c7b5/scratchpad/`. It holds:
  - `timing_report.md` — the clock research;
  - `verify.json` — the verifier verdicts and both critiques;
  - `final_plan.md` — the same as PLAN.md apart from the header;
  - `mocapstr-src/` — a read-only clone of MoCapSTR;
  - `innomaker-dl/`, `arducam-dl/` and `pdfs/` — vendor manuals and Arduino schematics.
