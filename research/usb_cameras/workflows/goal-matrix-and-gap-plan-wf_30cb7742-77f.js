export const meta = {
  name: 'usb-camera-goal-matrix-and-gap-plan',
  description: 'Build a verified method-by-goal matrix for the USB camera research, research RocSync and an ESP32 sync rig, and write a gap-filling test plan',
  phases: [
    { title: 'Extract', detail: 'one agent per method group builds evidence-backed goal/must-have cells' },
    { title: 'Verify', detail: 'adversarial verifier per group re-checks every cell against result files' },
    { title: 'Research', detail: 'RocSync web research; ESP32 sync-rig design' },
    { title: 'Sketch', detail: 'draft ESP32 sketch + host clock-sync script' },
    { title: 'Plan', detail: 'gap-filling test plan, completeness critic, revision' },
  ],
}

const BASE = 'C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras'
const ARD = 'C:/Users/Dom/GitHub/freemocap/skellycam/research/arduino_sync'

const CTX = `
CONTEXT. You are working on Dom's USB (UVC) webcam research for skellycam (multi-camera markerless motion capture).
Research folder: ${BASE} (read-only for you unless told otherwise). Key documents:
- ${BASE}/REPORT.md (the main consolidated report; findings 1-29, technique tables, further-investigation list)
- ${BASE}/PROGRESS.md (status, machine state, hazards, unfinished work)
- ${BASE}/docs/usb_camera_report.md, ${BASE}/docs/usb_camera_tests_summary.md, ${BASE}/docs/mjpeg_passthrough_summary.md,
  ${BASE}/docs/capture_backends_review.md, ${BASE}/docs/windows_timer_resolution.md
- ${BASE}/mjpeg/RESULTS.md, ${BASE}/prior_art/SURVEY.md, ${BASE}/timing/VERIFY_method.md, ${BASE}/naming/README.md
- ${BASE}/results/windows/Gerald/RERUN_20261027.md (claim -> rerun -> verifier verdict tables) and the result folders under results/windows/Gerald/
- ${BASE}/results/agent_reports/*.json (earlier agent reports and verifier verdicts)
- ${ARD}/REPORT.md and ${ARD}/PLAN.md (Arduino FSIN hardware-trigger plan; nothing built or measured)
Only one Windows machine ("Gerald") has been measured; Linux/macOS harnesses are drafts never run on hardware.
Cameras: Logitech C922 (has serial), Logitech C930e (no serial), generic 4C4A:4A55 "USB Camera" (no serial), Razer Kiyo Pro (excluded, faulty).

THE USER'S GOALS for any capture method:
 G1 SYNC: does it make inter-camera synchronisation better, specifically does it tighten when light hits the lens/sensor across cameras (exposure alignment)? Dom's assumption: no, USB interfaces cannot control this; only a hardware trigger (FSIN) could. Distinguish "aligns exposures" from "only measures/timestamps them".
 G2 TIMESTAMP ACCURACY: does it give a per-frame timestamp closer to when light hit the sensor (vs host arrival)? Cite the best measured error vs ground truth and its caveats (flash method floor ~0.5 ms; rolling shutter ~30 ms per frame; PTS marks readout on C922).
 G3 NATIVE MJPEG: does it return the camera's own JPEG bytes without decode/re-encode?
 G4 UNIQUE CAMERA IDs: does the method expose (or let us map to) a stable unique identity (USB serial, else physical port path), rather than an index or friendly name?
 G5 BANDWIDTH CONTROL: does it let the app control USB isochronous bandwidth (alt setting) so more cameras fit on one controller/link?
MUST-HAVES for any adopted solution:
 M1 shutter speed / exposure control (manual exposure, reliably applied and read back)
 M2 format control (resolution, fps, pixel format)
 M3 focus control (manual focus / autofocus off, where the camera has autofocus)

RATING RULES for each cell: rating is one of yes | partial | no | unknown | n/a.
 - 'yes'/'partial'/'no' only when backed by a result file (basis 'measured') or by source/doc reading (basis 'inferred') or external sources (basis 'web'). Say which.
 - If nothing in the research tested it, rating 'unknown' with basis 'not tested' — do NOT guess from general knowledge as if measured. You MAY add your expectation in 'note' clearly labelled "expected:".
 - 'value' is a short table-ready phrase (<= 12 words), e.g. "~0.5 ms (method floor), needs admin registry value", "No: decodes to BGR".
 - 'evidence' lists repo-relative paths (relative to research/usb_cameras/) or URLs that actually support the cell. Open them; do not cite files you did not read.
 Important nuance: in the MJPEG matrix, exposure/WB controls were set via the DirectShow filter (IAMCameraControl/IAMVideoProcAmp/IKsControl) even for MF cells — so an MF row's exposure control is NOT demonstrated by that. C930e manual exposure was unreliable on every API; on libusb, exposure set before stream COMMIT was not applied. Check what (if anything) ever tested focus control.
`

const CELL = {
  type: 'object',
  properties: {
    rating: { type: 'string', enum: ['yes', 'partial', 'no', 'unknown', 'n/a'] },
    value: { type: 'string' },
    basis: { type: 'string', enum: ['measured', 'inferred', 'web', 'not tested'] },
    evidence: { type: 'array', items: { type: 'string' } },
    note: { type: 'string' },
  },
  required: ['rating', 'value', 'basis', 'evidence'],
}
const ROW = {
  type: 'object',
  properties: {
    method: { type: 'string' },
    stack: { type: 'string', description: 'API/library + driver, e.g. "IMFSourceReader on usbvideo.sys"' },
    platform: { type: 'string' },
    test_status: { type: 'string', enum: ['measured', 'partly measured', 'inferred only', 'not tested', 'plan only'] },
    sync: CELL, timestamp: CELL, mjpeg: CELL, unique_id: CELL, bandwidth: CELL,
    exposure: CELL, format: CELL, focus: CELL,
    costs: { type: 'string', description: 'deployment cost / blockers, e.g. driver swap, admin, native code' },
    verdict: { type: 'string', description: 'one-line verdict for skellycam' },
  },
  required: ['method', 'stack', 'platform', 'test_status', 'sync', 'timestamp', 'mjpeg', 'unique_id', 'bandwidth', 'exposure', 'format', 'focus', 'costs', 'verdict'],
}
const ROWS = {
  type: 'object',
  properties: {
    rows: { type: 'array', items: ROW },
    gaps: { type: 'array', items: { type: 'object', properties: { method: { type: 'string' }, item: { type: 'string' }, why_unknown: { type: 'string' } }, required: ['method', 'item', 'why_unknown'] } },
  },
  required: ['rows', 'gaps'],
}
const VERIFIED = {
  type: 'object',
  properties: {
    rows: { type: 'array', items: ROW },
    changes: { type: 'array', items: { type: 'object', properties: { method: { type: 'string' }, field: { type: 'string' }, before: { type: 'string' }, after: { type: 'string' }, reason: { type: 'string' } }, required: ['method', 'field', 'before', 'after', 'reason'] } },
    missed_methods: { type: 'array', items: { type: 'string' } },
    gaps: { type: 'array', items: { type: 'object', properties: { method: { type: 'string' }, item: { type: 'string' }, why_unknown: { type: 'string' } }, required: ['method', 'item', 'why_unknown'] } },
  },
  required: ['rows', 'changes', 'missed_methods', 'gaps'],
}

const GROUPS = [
  { key: 'win-os-apis', title: 'Windows OS capture APIs on the normal usbvideo driver',
    methods: 'OpenCV CAP_DSHOW (what skellycam uses today); OpenCV CAP_MSMF; Media Foundation IMFSourceReader with native MJPG and converters off (mjpeg/msmf/mf_mjpeg_capture.cpp and the timing tool timing/build mf_uvc_timing / timing/src) including UVC PTS/SCR via MF capture metadata (MetadataBufferSizeInKB0); MF with its own decoder (NV12); PyAV/FFmpeg DirectShow vcodec=mjpeg (include what DirectShow sample times are worth); WinRT MediaFrameReader.',
    focus: 'mjpeg/RESULTS.md, docs/mjpeg_passthrough_summary.md, timing/VERIFY_method.md, docs/capture_backends_review.md, naming/README.md + naming/win_api_names.py (how each API name maps to USB identity), results/windows/Gerald/RERUN_20261027.md' },
  { key: 'third-party', title: 'Third-party capture libraries on the normal driver',
    methods: 'nokhwa (Rust, MSMF backend); GStreamer mfvideosrc; GStreamer ksvideosrc; SDL3 camera API; pygrabber; openpnp-capture (stock v0.0.30 and Dom\'s skellycam branches dom/openpnp-capture and dom/openpnp-capture-mf as described in docs/capture_backends_review.md); also any other library row in prior_art/SURVEY.md that was actually probed (e.g. librealsense-style approaches only if probed; otherwise list them as inferred-only rows).',
    focus: 'prior_art/SURVEY.md, prior_art/*.py, docs/capture_backends_review.md section 1, results/windows/Gerald/prior_art_*, RERUN_20261027.md prior-art tables' },
  { key: 'libusb-winusb', title: 'User-space UVC over libusb on the WinUSB driver (driver swap)',
    methods: 'libuvc + patch 0001 (C); pure-Python libusb1 streamer (libusb/py_libusb1); pyuvc 1.0.8 from PyPI and the locally patched pyuvc (bandwidth_factor); Rust uvc_iso with the libusb backend; Rust uvc_iso with the rawusb backend; nusb (Rust). Also capture the WinUSB driver-swap cost and the xHCI frame-number/QPC IOCTL timing basis and its weakening.',
    focus: 'REPORT.md findings 13,14,18,19,25,26; PROGRESS.md; results/windows/Gerald/phase2_*; libusb/ (uvc_capture_test.c, patches, py_libusb1, pyuvc); rust/; bandwidth/libuvc_forced_alt; results/windows/Gerald/winusb_install' },
  { key: 'linux-macos-hw', title: 'Linux, macOS (drafts) and hardware-trigger approaches',
    methods: 'Linux V4L2 + uvcvideo (buffer timestamps, UVC metadata node /dev/videoN+1, quirks=128 FIX_BANDWIDTH, /dev/v4l/by-path naming); libuvc on Linux via udev rule; macOS AVFoundation; libusb on macOS; hardware trigger via FSIN pin driven by an Arduino (research/arduino_sync, InnoMaker OV9281 with CT_FOCUS_AUTO trigger hack, MoCapSTR) — note this is plan-only; and UVC still-image trigger / vendor extension-unit trigger if anything in the research mentions them. For the hardware-trigger row, G1 is the key cell: explain that it is the only approach that could align exposure starts, and what is known/unknown (FSIN-to-exposure skew, lockout).',
    focus: 'timing/linux, timing/macos, mjpeg/drafts, bandwidth/linux, bandwidth/macos, libusb/linux, libusb/macos, naming/linux_*.py/sh, naming/macos_*, rust/platform/RUN_LINUX_MACOS.md, prior_art/SURVEY.md (Linux/macOS sections), results/linux/, docs/usb_camera_report.md Linux/macOS notes, ' + ARD + '/REPORT.md and PLAN.md' },
]

function extractPrompt(g) {
  return `${CTX}
YOUR TASK: build evidence-backed matrix rows for the method group "${g.title}".
Methods to cover (one row each; split or merge only if the research clearly treats them as distinct/identical): ${g.methods}
Start from these files (paths relative to ${BASE} unless absolute): ${g.focus}. Follow citations into results/windows/Gerald/ as needed to confirm numbers, and grep the results tree for control-related evidence (exposure, focus, IAMCameraControl, KSPROPERTY, CT_, uvc_set, readback) for M1-M3.
For G1 SYNC: report any measured cross-camera alignment (e.g. REPORT finding 15) and be explicit whether the method can ALIGN exposure (it almost certainly cannot for free-running UVC) or only MEASURE it. Also note whether per-camera frame-period drift (free-running clocks, e.g. C930e STC +42..+49 ppm vs QPC) was measured, since it makes inter-camera phase walk over time.
For G4 UNIQUE IDs: what identity does this API expose natively (index, friendly name, symbolic link/device path containing instance ID, USB bus/port, serial descriptor), and can it be mapped to the serial/port key from naming/camera_identity.py? Cite naming results.
Also list in 'gaps' every cell you had to mark unknown and why.
Do not modify any files. Return the structured output.`
}

function verifyPrompt(g, extracted) {
  return `${CTX}
YOU ARE AN ADVERSARIAL VERIFIER for the method group "${g.title}". Another agent produced the rows below. For EVERY cell:
 - open the cited evidence files and confirm the rating, value and basis are actually supported (numbers, units, which camera, which API set the control);
 - downgrade overclaims (e.g. 'measured' that was really inferred; 'yes' for exposure where the control was actually set via a different API; timestamp accuracies stated without the method-floor caveat; sync 'yes' for a method that only timestamps);
 - fill cells the extractor marked unknown if you find real evidence, and mark as unknown anything unsupported;
 - check for methods in this group that the research tested but the extractor omitted (list them in missed_methods AND add rows for them).
Keep 'value' strings short and table-ready. Record every change in 'changes'. Default to the more conservative rating when uncertain.
Do not modify any files.

ROWS TO VERIFY:
${JSON.stringify(extracted, null, 1)}`
}

const ROCSYNC_PROMPT = `${CTX}
YOUR TASK: research RocSync (https://github.com/BAL-ROCS-BUT-COOL/RocSync) and how it could help this research. Use WebFetch/WebSearch (load them with ToolSearch first: query "select:WebFetch,WebSearch"). Read the repo README, hardware files, firmware, any linked paper/preprint (likely from Balgrist ROCS / ETH), and its license.
Answer, citing URLs:
1. What RocSync is and how it works (hardware: LEDs/display/IR?, microcontroller, how it encodes time, how cameras are synchronised or timestamped after the fact, what software analyses the video).
2. Claimed accuracy and how it was validated; whether it handles rolling-shutter cameras and short/long exposures; frame-rate limits.
3. What it needs: BOM, cost, PCB availability, firmware toolchain, whether it can be built from an ESP32 or Arduino Dom already has (Dom has an ESP32 available).
4. License and whether skellycam (AGPL-3.0-or-later) could use its designs/code.
5. Concretely, how it could fill gaps in THIS research: (a) G1 measuring real inter-camera exposure alignment (the screen-flash method in timing/VERIFY_method.md cannot: display scan-out, ~0.5 ms floor, ~35 ms block offset variation), (b) G2 scoring per-frame timestamp sources (UVC PTS, SCR, OS time, arrival) against a ground truth that does not depend on a monitor, (c) measuring rolling-shutter row timing and exposure duration, i.e. verifying M1 exposure control actually took effect, (d) long-run drift between free-running cameras.
6. Limitations or reasons it would not fit (e.g. needs global shutter, needs IR, accuracy floor vs our needs).
Read ${BASE}/timing/VERIFY_method.md first so you understand the current ground-truth method and its limits.
Return a thorough markdown report (no files written). Mark anything you could not confirm from a primary source as unconfirmed.`

const ESP32_PROMPT = `${CTX}
YOUR TASK: design an ESP32-based timing/sync test rig to replace or complement the monitor-flash ground truth used in this research. Dom has an ESP32 available (assume a classic ESP32-WROOM-32 DevKit with Arduino-ESP32 core 3.x unless stated; note what changes for ESP32-S3/C3). Read ${BASE}/timing/VERIFY_method.md, ${BASE}/REPORT.md (goal 2 findings 7-15 and further investigation 1, 6, 7) and ${ARD}/PLAN.md section 1 first. You may use WebSearch/WebFetch (load via ToolSearch "select:WebFetch,WebSearch") to check ESP32 timer/GPIO/RMT/LEDC/MCPWM APIs, ESP32 crystal accuracy (40 MHz, typ +-10 ppm), and existing open designs (e.g. LED-timecode clocks used for camera sync, RocSync https://github.com/BAL-ROCS-BUT-COOL/RocSync).
Design must address:
 A. A time-code display all cameras can image: e.g. a row/ring of LEDs encoding a counter (binary/Gray code) at a fine time step plus a coarse counter, so each frame's capture time can be decoded from the image without depending on a monitor's scan-out. Specify LED count, update rate, encoding, how to make it robust to rolling shutter (decode per row band; orient LEDs along a single row band or column so rolling-shutter row time is known), LED rise/fall time (choose LEDs + drive so edges are << 100 us), brightness vs short exposure.
 B. A strobe mode: a very short LED pulse (e.g. 50-200 us) at a programmable phase, to measure (1) which cameras are exposing at a given instant -> real inter-camera exposure phase alignment (G1), (2) exposure duration and start/end per row by sweeping the strobe phase (M1 verification: did the requested exposure apply?), (3) rolling-shutter line time.
 C. Host clock correlation: how ESP32 time is tied to the host's QPC/CLOCK_MONOTONIC so camera timestamps (UVC PTS/SCR, OS times, arrival) can be scored in host time. Compare options: USB-serial ping exchange with min-RTT filtering (expected accuracy with CP210x/CH340 vs native USB on S3), a GPIO edge into something the host timestamps precisely, or decoding the LED counter only (relative scoring with per-run offset fit, as today). Be honest about expected accuracy of each.
 D. Optional FSIN trigger output for cameras that have one (InnoMaker OV9281), sharing the same timebase, so the rig can later measure FSIN-to-exposure skew.
 E. Expected ground-truth floor of the rig vs the current ~0.5 ms flash-method floor, with the arithmetic.
 F. A concrete test protocol per goal (G1 sync phase/drift, G2 timestamp scoring, M1 exposure verification incl. C930e post-stream-start re-apply, rolling-shutter line time) and what analysis code is needed on the host (decoder steps).
 G. BOM with cheap parts, wiring, pin assignment for a classic ESP32 DevKit (avoid strapping/input-only pins), and safety notes (LED current, use transistor/driver).
Return a detailed markdown design (no files written). Keep claims about accuracy labelled as estimates.`

function sketchPrompt(design) {
  return `${CTX}
YOUR TASK: implement a first draft of the ESP32 sync/timing rig from the design below. Write files ONLY under ${BASE}/sync_rig/ (create it):
 - ${BASE}/sync_rig/esp32_sync_rig/esp32_sync_rig.ino — Arduino-ESP32 (core 3.x API: timerBegin(freq), timerAttachInterrupt, etc.; avoid deprecated 2.x timer API, or guard with ESP_ARDUINO_VERSION_MAJOR) sketch implementing: LED time-code display mode, strobe mode with programmable phase/width, optional FSIN/trigger output, a line-based serial command protocol (e.g. "MODE CODE", "MODE STROBE <period_us> <width_us> <phase_us>", "PING <host_ns>" -> "PONG <host_ns> <esp_us_rx> <esp_us_tx>", "STATUS"), and 64-bit microsecond timebase via esp_timer_get_time() or a hardware timer. Use hardware-driven or ISR-driven edges for timing-critical outputs (GPIO set via direct register write or dedicated peripheral), keep serial handling out of the ISR. Pin assignment for classic ESP32 DevKit per the design; put all pins/constants at the top.
 - ${BASE}/sync_rig/host/esp32_clock_sync.py — PEP 723 single-file script (run with "uv run --script"), using pyserial, that runs the PING/PONG exchange, uses min-RTT filtering to estimate offset and drift between ESP32 microseconds and the host clock (time.perf_counter_ns on Windows = QPC; CLOCK_MONOTONIC on Linux), and writes JSON matching the research conventions in ${BASE}/README.md ("test", "platform", "hostname", "utc_started", "command", "environment", measurements) to results/<platform>/<hostname>/sync_rig_clock/.
 - ${BASE}/sync_rig/README.md — what it is, status (DRAFT, not compiled on hardware / not run unless you compiled it), BOM, wiring table, serial protocol, how to flash, how it maps to the test plan goals, known limitations.
Match the research conventions in ${BASE}/README.md. Keep the code readable and commented at a moderate density.
COMPILE CHECK: if an arduino-cli exists (check PATH and "C:/Program Files/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe" and "%LOCALAPPDATA%/Programs/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe") AND an esp32 core is already installed (arduino-cli core list), compile for esp32:esp32:esp32 with build output in a temp dir outside the repo and report the result. Do NOT install cores, libraries or tools, and do NOT flash any device. Python: check the host script at least parses (uv run --script with --help, or python -m py_compile) without opening any serial port.
Do not touch any other files. Return a summary: files written, compile/parse result (exact), design deviations, open TODOs.

DESIGN:
${design}`
}

function planPrompt(matrix, rocsync, esp32, sketch) {
  return `${CTX}
YOUR TASK: write a test plan that fills the gaps in the existing USB camera research so that every candidate method can be ranked on G1-G5 and M1-M3. Output markdown (no files written) intended to be saved as research/usb_cameras/docs/test_gap_plan.md and read by Dom.

Inputs:
(1) VERIFIED METHOD x GOAL MATRIX (rows with ratings, evidence, and gaps):
${JSON.stringify(matrix, null, 1)}

(2) ROCSYNC RESEARCH:
${rocsync}

(3) ESP32 RIG DESIGN:
${esp32}

(4) ESP32 SKETCH DRAFT SUMMARY (files under research/usb_cameras/sync_rig/):
${sketch}

Also read ${BASE}/PROGRESS.md "Unfinished work" and ${BASE}/REPORT.md "Proposed further investigation" so the plan absorbs (not duplicates) existing open items, and ${BASE}/docs/usb_camera_tests_summary.md "What still needs a person".

Constraints the plan must respect (from the research hazards):
 - Test machine Gerald, Windows 11. Never restart devices programmatically (LogiTune vetoes pnputil; ask Dom to replug). Announce every UAC prompt. Wrap camera access in tools/camlock.py. Razer Kiyo Pro excluded (faulty). WinUSB swaps need a UAC prompt + replug and hide the camera from other apps.
 - Results go to results/<platform>/<hostname>/<test>/ as JSON with the standard fields; reports as .md under research/ (never Claude Docs); never commit build outputs.
 - Every claim needs a reproducible harness; say which harness exists and which must be written.
 - Linux/macOS hardware is not yet available on Gerald; plan those runs as separate machine sessions, and say what hardware Dom needs.

Plan structure:
 1. Summary: the gaps that matter most for the decision (which capture stack skellycam moves to), and the 5-8 tests that close them, in priority order.
 2. Gap table: method x (G1..G5, M1..M3) cell -> current state -> test ID that fills it (or "out of scope: reason").
 3. Ground-truth upgrade: ESP32 rig (and where RocSync fits / whether to build RocSync instead or alongside); validation of the rig itself before using it (e.g. photodiode/scope or logic analyzer check of LED edges, serial clock-sync accuracy check, comparison against the existing flash method on the C922).
 4. Test specs grouped by goal: ID, question it decides, methods/cameras, hardware, procedure, analysis, pass/fail criteria, harness (existing path or new), attended/unattended, admin/UAC/replug needs, estimated time.
    G1 must include: inter-camera exposure phase measurement with the strobe, phase walk/drift over >= 30 min between free-running cameras, effect (if any) of simultaneous stream start, and the FSIN hardware-trigger spike (InnoMaker OV9281 if acquired) as the only route that could actually align exposures. Also say whether any UVC-level mechanism (still-image trigger, vendor XU) is worth probing on the cameras on hand (check descriptors already dumped in results for bTriggerSupport).
    G2: score every timestamp source per method against the rig, long runs for SCR->QPC (xHCI IOCTL re-anchoring), C930e period modes, generic camera timing.
    G3: Kiyo/Linux/macOS gaps only (Windows is done).
    G4: controlled reboot/replug/port-move, identical-camera pair, per-API mapping.
    G5: phase 3 WinUSB, 3+ cameras per link, Linux quirks=128 MJPEG vs YUYV, driver-swap strategy.
    M1-M3: a control-matrix test: for each candidate stack (MF, PyAV DShow, libusb/libuvc, V4L2, AVFoundation) set manual exposure, resolution/fps, and manual focus/autofocus-off; verify by readback AND by the rig (exposure) or a focus target (focus: e.g. Siemens star sharpness metric), including set-before-start vs set-after-start; and LogiTune interference.
 5. Equipment/shopping list and Dom's time needed (attended steps batched into as few sessions as possible).
 6. Order of execution with dependencies.
Be concrete and terse; tables over prose where possible. Do not invent results.`
}

const CRITIC_SCHEMA = {
  type: 'object',
  properties: {
    issues: { type: 'array', items: { type: 'object', properties: {
      severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, issue: { type: 'string' }, fix: { type: 'string' } }, required: ['severity', 'issue', 'fix'] } },
  },
  required: ['issues'],
}

// ---- run ----
phase('Extract')
const matrixP = pipeline(
  GROUPS,
  g => agent(extractPrompt(g), { label: `extract:${g.key}`, phase: 'Extract', schema: ROWS }),
  (ex, g) => agent(verifyPrompt(g, ex), { label: `verify:${g.key}`, phase: 'Verify', schema: VERIFIED })
    .then(v => ({ group: g.key, extracted: ex, verified: v })),
)
const rocsyncP = agent(ROCSYNC_PROMPT, { label: 'research:rocsync', phase: 'Research' })
const espP = agent(ESP32_PROMPT, { label: 'research:esp32-rig', phase: 'Research' })
  .then(design => agent(sketchPrompt(design), { label: 'sketch:esp32', phase: 'Sketch' }).then(sketch => ({ design, sketch })))

const [groups, rocsync, esp] = await Promise.all([matrixP, rocsyncP, espP])
const okGroups = groups.filter(Boolean)
log(`matrix groups verified: ${okGroups.length}/${GROUPS.length}`)
const matrix = okGroups.map(g => ({ group: g.group, rows: (g.verified || g.extracted).rows, gaps: (g.verified || g.extracted).gaps }))

phase('Plan')
const draft = await agent(planPrompt(matrix, rocsync || '(rocsync research failed)', esp ? esp.design : '(esp32 design failed)', esp ? esp.sketch : '(sketch failed)'), { label: 'plan:draft', phase: 'Plan' })
const critique = await agent(`${CTX}
You are a COMPLETENESS AND CORRECTNESS CRITIC for the draft test plan below. Check:
 - every 'unknown' or 'not tested' cell in the matrix (given below) for a candidate method has a test or an explicit out-of-scope reason;
 - M1-M3 (exposure, format, focus) are covered for every candidate stack, with readback AND physical verification;
 - G1 is framed correctly (measuring alignment vs achieving it; only hardware trigger can align exposure starts; free-running clock drift);
 - the ground-truth rig is itself validated before being trusted, and its accuracy claims are labelled estimates;
 - hazards respected (no programmatic device restarts, announced UAC, camlock, Kiyo excluded), results/ conventions, attended steps batched;
 - no invented results; file paths referenced exist (check under ${BASE}); existing open items from PROGRESS.md/REPORT.md are absorbed.
Return issues with concrete fixes.

MATRIX:
${JSON.stringify(matrix, null, 1)}

DRAFT PLAN:
${draft}`, { label: 'plan:critic', phase: 'Plan', schema: CRITIC_SCHEMA })
const finalPlan = await agent(`${CTX}
Revise the draft test plan below to address every critic issue (blockers and majors must be fixed; minors where cheap). Keep the structure. Output only the final markdown plan (no files written).

CRITIC ISSUES:
${JSON.stringify(critique, null, 1)}

DRAFT PLAN:
${draft}`, { label: 'plan:revise', phase: 'Plan' })

return { matrix, groups: okGroups, rocsync, esp32_design: esp && esp.design, sketch: esp && esp.sketch, critique, finalPlan }
