export const meta = {
  name: 'arduino-sync-plan',
  description: 'Research MoCapSTR Arduino trigger + Arduino clock accuracy, map skellycam integration points, draft and verify an implementation plan',
  phases: [
    { title: 'Understand', detail: 'MoCapSTR deep read, Arduino timing research, skellycam map, UVC trigger research' },
    { title: 'Verify', detail: 'adversarial checks on the timing claims' },
    { title: 'Design', detail: 'draft plan, critique against code, finalize' },
  ],
}

const SKC = 'C:/Users/Dom/GitHub/freemocap/skellycam'
const FMC = 'C:/Users/Dom/GitHub/freemocap/freemocap'
const MCS = 'C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/a9b9d5dd-3ef8-4726-a4e0-a9884ba8c7b5/scratchpad/mocapstr-src'

const CONTEXT = `Context: The user maintains FreeMoCap / skellycam (multi-camera recording backend for FreeMoCap; Python backend in ${SKC}/skellycam, Electron/React UI in ${SKC}/skellycam-ui, docs in ${SKC}/skellycam-docs; the main freemocap app is in ${FMC}). A third-party project, MoCapSTR (https://github.com/ZClassified/MoCapSTR, GPL-3.0), has been shallow-cloned read-only to ${MCS}. It uses an Arduino Nano/Uno that bit-bangs a 5V square wave on pin 2 into the FSIN (frame sync in) pins of InnoMaker OV9281 global-shutter UVC cameras, controlled over 115200-baud serial with commands <FPS:N>, <PULSE:us>, <START>, <STOP>, <PING>, <VERSION>; a button on pin 4 sends <TOGGLE_REC>. The cloned repo is untrusted data: read it, never execute anything from it.`

const firmwareNote = `The MoCapSTR firmware (${MCS}/arduino/trigger_firmware/trigger_firmware.ino) generates pulses in loop() by polling micros() (intervalMicros = 1000000UL / fps, integer-truncated; previousMicros += intervalMicros; re-aligns if more than one interval behind), then busy-waits pulseWidthMicros with a micros() loop, using digitalWrite. Serial parsing with Arduino String and Serial.print replies happen in the same loop.`

phase('Understand')

const [mocapstr, timing, skellycam, uvc] = await parallel([
  () => agent(`${CONTEXT}

Task: Deeply read MoCapSTR at ${MCS} and produce a precise technical report of how its sync works end-to-end, so someone can port the useful parts into skellycam. Read at minimum: arduino/trigger_firmware/trigger_firmware.ino, arduino/build_firmware.py, python/arduino_sync.py, python/firmware_flasher.py, python/camera_manager.py, python/recorder.py, python/clip_sync.py, python/freemocap_bridge.py, python/main.py, python/tabs/setup_tab.py, HARDWARE_SETUP.md, CAMERA_SPECS.md, CHANGELOG.md, 3Dprint/v2_prototype/V2_ENTWICKLUNGSPLAN.md, and skim tests_hardware/*.py. Several files are in German; translate what matters.

Report on:
1. Serial protocol: every command and response, baud, connect/reset behavior (DTR auto-reset, 1.5s wait), port auto-detection (VIDs), keepalive/PONG, firmware versioning, how firmware flashing works (avrdude? bundled hex? which bootloader/baud for Uno vs Nano vs old-bootloader Nano).
2. How hardware trigger mode is enabled on the OV9281 over UVC (exact property/control used, e.g. CAP_PROP_AUTOFOCUS hijack or an extension unit), which backend (MSMF/DirectShow/PyAV dshow), Windows-only assumptions, and what happens on Linux/macOS.
3. Recording pipeline: how frames from triggered cameras are matched across cameras (frame index? timestamps?), how they guarantee identical frame counts, how dropped/extra frames are handled, what clip_sync.py does, what timestamps are written and their format, how output maps into FreeMoCap's recording folder layout (freemocap_bridge.py).
4. Known limitations and lessons recorded in docs/changelog/hardware tests: trigger lockout (~18-20ms, 50fps cap), sub-harmonics, USB bandwidth (max 3 cams per controller), exposure settings, start/stop sequencing (do cameras need to be streaming before pulses start? first-frame handling), what happens if Arduino disconnects mid-recording.
5. Weaknesses / bugs you notice in their approach (e.g. firmware jitter sources, race conditions, Windows-only code).
6. Licensing note: MoCapSTR is GPL-3.0; check skellycam's license at ${SKC}/LICENSE and state whether code can be copied vs. reimplemented from the documented protocol.

Cite file:line for every concrete claim. Be exhaustive; this is the source of truth for downstream planning.`, { label: 'mocapstr-deep-read', phase: 'Understand' }),

  () => agent(`${CONTEXT}

Task: Investigate timing/clock accuracy of Arduino Nano and Arduino Uno boards for use as a camera frame-sync trigger, using web research (WebSearch/WebFetch: Arduino official schematics and hardware docs, ATmega328P datasheet, Murata CSTCE16M0V53 resonator datasheet, forum measurements, blog posts that measured drift). Also answer the user's question: "how accurate is the clock on those boards? Do they have TCXOs?" and, crucially, "does it matter?" for this application.

${firmwareNote}

Cover:
1. Clock source per board: genuine Uno R3 (ATmega328P clock source vs the 16U2's), Uno R4 Minima/WiFi (RA4M1, different MCU), genuine Nano V3, common Nano clones (CH340, crystal vs resonator), Nano Every (ATmega4809 internal oscillator), Nano 33/ESP32 variants if relevant. Give tolerance (ppm or %), temperature coefficient, aging. State clearly whether any of them have a TCXO (expected: no) and what TCXO/GPS-disciplined options cost/look like if absolute accuracy were needed.
2. Firmware-induced timing error, which likely dominates crystal error: micros() 4us resolution on 16MHz AVR, Timer0 overflow ISR and Serial RX/TX ISRs jitter, digitalWrite latency (~3-5us), the integer-truncation frequency error of 1000000/fps (compute for 30, 50, 60, 90, 120 fps), blocking busy-wait pulse, String parsing/Serial.print stalls during recording. Contrast with a hardware-timer approach (Timer1 CTC/PWM output on OC1A pin 9 or OC1B pin 10, input capture) which gives cycle-exact edges; give expected jitter numbers.
3. Does it matter? Separate (a) inter-camera sync — all cameras share the same electrical edge, so oscillator frequency error is common-mode and irrelevant; only edge propagation/sensor trigger latency differences matter; (b) frame-rate accuracy — e.g. a ±0.5% resonator means 50 fps is really 49.75-50.25 fps; quantify drift in frames over 1 min / 10 min / 1 hr and say when that matters (pairing with audio, force plates, EMG, IMUs, other systems' clocks; FreeMoCap computing fps from timestamps); (c) jitter — how many microseconds of jitter matters relative to a 1-2 ms exposure and 20 ms frame period; (d) mapping trigger edges to host timestamps (USB serial latency is ms-scale, so the Arduino clock can't be used for host-side absolute timestamps without a handshake/regression).
4. Practical recommendations: whether to require a crystal board, whether to use hardware timers, whether to have the firmware count pulses and report counts/its own micros at start/stop so the host can measure the actual rate against its own clock (perf_counter_ns) and correct, and how to calibrate.

Every numeric claim must have a source URL or a shown calculation. Flag anything you could not verify.`, { label: 'arduino-timing-research', phase: 'Understand' }),

  () => agent(`${CONTEXT}

Task: Map the skellycam codebase for where external hardware-trigger sync support would plug in. Read the code; do not modify anything. Cover:
1. Camera capture path: skellycam/core/camera/** (camera_worker, opencv camera loop, create_cv2_video_capture, opencv_apply_config, opencv_get_frame, determine_backend), what OpenCV backend is used per OS, how config is applied, how frames are grabbed (grab/retrieve split?), and how per-frame timestamps are captured.
2. Multi-camera coordination: skellycam/core/camera_group/** (camera_orchestrator, camera_group, camera_group_manager, camera_group_ipc). Explain exactly how skellycam currently achieves "frame-perfect sync" in software (read skellycam-docs/docs/core/frame-perfect-sync.mdx, docs/technical/frame-synchronization.mdx, docs/core/precise-timestamps.mdx too). How would it behave if cameras were driven by an external trigger instead (would the orchestrator's grab-gating fight with it, deadlock if no pulses arrive, etc.)?
3. Config model: skellycam/core/camera/config/camera_config.py — fields, validation, how the UI sets them; where a new "trigger mode" / "external sync" setting would live (per-camera vs per-group).
4. Timestamps & recording output: skellycam/core/timestamps/** (timebase_mapping, full_timestamp, csv outputs), recorders/** — what files are written per recording, and where trigger metadata (pulse count, trigger fps, arduino-reported timing) could be recorded.
5. Device detection and process model: skellycam/core/device_detection/**, skellycam/core/ipc/** (managed_worker, worker_registry, pubsub topics) — how a new long-lived "sync device" worker (serial port owner) should be structured to match existing patterns. Note how microphone detection/audio recorder were integrated recently (commit d0455d10 "improved microphone detection in UI") as a template for adding a new device type end-to-end (backend detection -> API router -> UI selector).
6. API & UI: skellycam/api/** routers and websocket message types; skellycam-ui/src components for camera config and recording settings (e.g. MicrophoneSelector.tsx, RecordingSettingsSection.tsx, CameraConfigPanel.tsx) and redux/state if present — where an "External Sync" panel would go.
7. Dependencies: pyproject.toml — is pyserial present? Packaging (PyInstaller workflow) implications of adding pyserial/avrdude.
8. Briefly check ${FMC}: how freemocap consumes skellycam recordings/timestamps (search for skellycam imports, timestamps csv reading, framerate inference), so the plan knows what metadata freemocap needs.
9. Existing TODOs/refactors that would interact: read ${SKC}/TODO-desired-state-refactor.md.

Return a structured map with file:line references, the exact function/class names to hook, and a list of risks/constraints for adding hardware-triggered capture.`, { label: 'skellycam-integration-map', phase: 'Understand' }),

  () => agent(`${CONTEXT}

Task: Web-research the camera side of external hardware triggering, to determine scope and constraints for supporting it in skellycam (cross-platform: Windows, Linux, macOS).
1. InnoMaker OV9281 USB (and Arducam OV9281/OV9782 UVC global-shutter cameras): how external trigger / FSIN mode is enabled over UVC (vendor extension unit, or a repurposed standard control such as focus/autofocus/exposure-auto-priority), electrical requirements of FSIN (voltage level — is 5V from an Arduino within spec or does it need a level shifter/resistor divider since OV9281 is a 1.8/3.3V part?), pulse polarity/width, trigger lockout and max triggered fps, whether the camera keeps streaming stale frames when no pulses arrive. Find vendor docs/GitHub (e.g. INNO-MAKER/cam-ov9281usb, Arducam UVC trigger docs) and quote them.
2. How to set those controls from Python on each OS: OpenCV CAP_PROP_* with MSMF vs DSHOW on Windows, v4l2-ctl / V4L2 on Linux, AVFoundation on macOS (likely cannot set vendor controls) — and alternatives like libuvc / openpnp-capture (note: a sibling openpnp-capture-python checkout exists at C:/Users/Dom/GitHub/freemocap/openpnp-capture-python; glance at whether it exposes arbitrary UVC controls).
3. Other affordable trigger-capable cameras a FreeMoCap user might use (e.g. other Arducam/ELP global shutter UVC, FLIR/Basler machine vision with GPIO, Raspberry Pi GS camera) and how the same Arduino pulse train would generalize. Ordinary webcams cannot be triggered — state the fallback sync options for them (LED flash / audio clap visual sync, host timestamps).
4. Any prior art for Arduino-triggered multi-camera mocap rigs (e.g. open-source projects, Pose2Sim/anipose community rigs) and lessons learned.

Give source URLs for every claim and flag uncertainty.`, { label: 'uvc-trigger-research', phase: 'Understand' }),
])

phase('Verify')

const VERDICT = {
  type: 'object',
  properties: {
    claims_checked: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, verdict: { type: 'string', enum: ['confirmed', 'wrong', 'unverifiable', 'overstated'] },
      correction: { type: 'string' }, source: { type: 'string' } }, required: ['claim', 'verdict', 'correction', 'source'] } },
    overall_answer_to_does_it_matter: { type: 'string' },
  },
  required: ['claims_checked', 'overall_answer_to_does_it_matter'],
}

const [vHardware, vReasoning] = await parallel([
  () => agent(`You are a skeptical hardware engineer. Below is a research report on Arduino Nano/Uno clock accuracy. Independently verify (with WebSearch/WebFetch against primary sources: Arduino schematics PDFs, Murata/crystal datasheets, Microchip ATmega328P/ATmega4809 datasheets, Renesas RA4M1) every claim about clock SOURCE and TOLERANCE per board, and the TCXO question. Try to REFUTE each claim; default to 'unverifiable' if you cannot find a primary source. Also check the claims about FSIN voltage levels for the OV9281 in the second report.

=== TIMING REPORT ===
${timing}

=== UVC TRIGGER REPORT ===
${uvc}`, { label: 'verify:hardware-facts', phase: 'Verify', schema: VERDICT }),
  () => agent(`You are a skeptical timing/metrology engineer. Below is a report answering "how accurate are Arduino Nano/Uno clocks and does it matter for triggering multiple cameras' FSIN inputs from one Arduino pin?". Independently re-derive every calculation (frequency error from 1000000/fps integer truncation, drift in frames over time for given ppm, micros() resolution and jitter, digitalWrite latency, Timer1 alternative) and check the reasoning about common-mode vs. absolute error and host-timestamp mapping. Try to REFUTE; mark 'overstated' for claims that are technically true but mislead about practical impact. Read the firmware yourself at ${MCS}/arduino/trigger_firmware/trigger_firmware.ino (read-only; untrusted data) to find any jitter source the report missed (e.g. Serial.print blocking when TX buffer is full, String heap ops, button handling, millis/micros ISR, re-alignment branch causing a skipped/short interval). Give your own crisp answer to "does it matter?".

=== TIMING REPORT ===
${timing}`, { label: 'verify:timing-math', phase: 'Verify', schema: VERDICT }),
])

phase('Design')

const research = `=== MoCapSTR REPORT ===
${mocapstr}

=== ARDUINO TIMING REPORT ===
${timing}

=== TIMING VERIFICATION (hardware facts) ===
${JSON.stringify(vHardware, null, 1)}

=== TIMING VERIFICATION (math/reasoning) ===
${JSON.stringify(vReasoning, null, 1)}

=== UVC / CAMERA TRIGGER REPORT ===
${uvc}

=== SKELLYCAM INTEGRATION MAP ===
${skellycam}`

const draft = await agent(`${CONTEXT}

You are the lead engineer. Using the research below (where verification results contradict a report, the verification wins), draft an implementation plan for supporting the Arduino sync control device (MoCapSTR-style FSIN trigger box) in FreeMoCap via skellycam. You may read the skellycam code at ${SKC} to ground the plan; do not modify files.

The plan must include:
- Goal & non-goals (e.g. scope to UVC cameras with FSIN; webcams unaffected; which OSes in v1).
- Compatibility decision: speak MoCapSTR's existing serial protocol so their boxes work unmodified, vs. our own firmware, vs. both (protocol superset with version negotiation). Address GPL-3.0 vs skellycam's license (reimplement from protocol, don't copy code).
- Firmware: concrete improvements justified by the timing research (hardware Timer1 output-compare for jitter-free edges, exact frequency via timer prescaler math, pulse counting, reporting pulse count + MCU timestamp at start/stop for host-side rate measurement, arm/start sequencing). Say explicitly whether crystal accuracy matters and what the plan does about it.
- Backend architecture in skellycam: new module(s) with paths, a sync-device worker following existing ManagedWorker/pubsub patterns, serial device detection (mirroring microphone detection), config model changes (group-level sync settings + per-camera trigger-mode flag), how the camera loop/orchestrator changes for triggered capture (start order: put cameras in trigger mode -> start streams -> arm -> start pulses; stop order; timeouts when no pulses; frame matching across cameras), timestamps and recording metadata (pulse count, nominal vs measured rate), failure handling (Arduino disconnect mid-recording, camera misses a pulse).
- Camera control: how trigger mode is set per OS/backend, and what's unsupported.
- API + UI: endpoints/websocket messages, UI panel location and states.
- FreeMoCap downstream: what freemocap needs to read.
- Testing: unit tests with a mock serial device, hardware-in-the-loop tests, a measurement procedure (e.g. scope or photodiode/LED-in-frame test) to validate sync.
- Phased milestones (M0 spike -> M1 ... ) with rough size, risks, open questions for the maintainer.
- A short, direct section titled "Does clock accuracy matter?" answering the user's question with numbers.

Reference real skellycam files/functions (file:line where possible). Be concrete, not generic.

${research}`, { label: 'draft-plan', phase: 'Design' })

const CRIT = {
  type: 'object',
  properties: {
    issues: { type: 'array', items: { type: 'object', properties: {
      severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, section: { type: 'string' },
      problem: { type: 'string' }, evidence: { type: 'string' }, fix: { type: 'string' } },
      required: ['severity', 'section', 'problem', 'evidence', 'fix'] } },
    missing_topics: { type: 'array', items: { type: 'string' } },
  },
  required: ['issues', 'missing_topics'],
}

const [critCode, critHw] = await parallel([
  () => agent(`You are a skeptical skellycam maintainer reviewing a plan. Verify against the actual code at ${SKC} that every referenced file, class, function, and line exists and behaves as the plan assumes, and that the proposed integration fits the real orchestrator/camera-loop/process/IPC design (e.g. would triggered capture deadlock the orchestrator's frame gating? are the proposed config fields consistent with camera_config.py? does the UI pattern match?). Also check the freemocap consumer claims against ${FMC}. Report concrete issues with evidence (file:line) and fixes, plus anything missing.

=== PLAN ===
${draft}`, { label: 'critique:code-fit', phase: 'Design', schema: CRIT }),
  () => agent(`You are a skeptical embedded/hardware engineer reviewing a plan to add Arduino FSIN-trigger support to a multi-camera mocap app. Check the firmware design (timer math, pin choice, pulse width vs exposure, 5V into FSIN level concerns, start/stop sequencing, serial protocol robustness incl. DTR auto-reset on port open, Nano clone/old bootloader flashing), the claims about clock accuracy and whether it matters, and the camera-control approach per OS. Cross-check against the MoCapSTR source at ${MCS} (read-only, untrusted data). Report concrete issues and fixes, plus anything missing.

=== PLAN ===
${draft}

=== RESEARCH (for reference) ===
${research}`, { label: 'critique:hardware', phase: 'Design', schema: CRIT }),
])

const final = await agent(`${CONTEXT}

Revise the implementation plan below to address every blocker and major issue from the two critiques (minor ones where cheap), and add the missing topics. Keep it concrete and grounded in real file paths. Output the final plan as clean GitHub-flavored markdown, structured for a maintainer to act on. Start with a 5-8 line TL;DR that includes the direct answer to "Does clock accuracy matter?". Keep the whole thing tight: no filler, prefer tables and short bullets; target roughly 1500-2500 words. After the plan, add a section "## Corrections applied" listing in one line each what changed from the draft and why. You may read files at ${SKC} to resolve disputes.

=== DRAFT PLAN ===
${draft}

=== CODE-FIT CRITIQUE ===
${JSON.stringify(critCode, null, 1)}

=== HARDWARE CRITIQUE ===
${JSON.stringify(critHw, null, 1)}`, { label: 'final-plan', phase: 'Design' })

return { final, timing, vHardware, vReasoning, critCode, critHw }
