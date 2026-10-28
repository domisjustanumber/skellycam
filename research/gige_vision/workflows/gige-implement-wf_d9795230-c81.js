export const meta = {
  name: 'gige-implement',
  description: 'Implement GigE Vision backend in SkellyCam (viva-genicam), standalone hardware tests, review and fix',
  phases: [
    { title: 'Prep', detail: 'viva-genicam API deep-dive + standalone hardware test suite (parallel)' },
    { title: 'Implement', detail: 'backend + config + metadata + detection + sync, then UI pass-through' },
    { title: 'Review', detail: 'three adversarial reviewers with distinct lenses' },
    { title: 'Fix', detail: 'apply confirmed findings, rerun tests' },
  ],
}

const SCRATCH = 'C:/Users/Dom/AppData/Local/Temp/claude/c--Users-Dom-GitHub-freemocap-skellycam/f77e9c4e-e1ea-4406-8a36-bef826a63a0e/scratchpad'
const REPO = 'C:/Users/Dom/GitHub/freemocap/skellycam'
const DIGEST = `${SCRATCH}/digest`
const RESEARCH = `${SCRATCH}/research`
const NOTES = `${SCRATCH}/impl`

const CONTEXT = `
PROJECT: SkellyCam (repo ${REPO}, branch development, Python >=3.11, uv-managed, Windows/macOS/Linux, AGPL-3.0). Currently capture is OpenCV-only and hard-wired. We are adding GigE Vision camera support.

RESEARCH ALREADY DONE (read these, they are verified with links): ${DIGEST}/*.md — especially skellycam-arch.md (repo map + proposed design), ptp-sync.md, frame-transport.md, rust-cpp-vendor.md (viva-genicam + telegenic), from-scratch.md, harvesters-gentl.md. Fuller notes and prior scripts live in ${RESEARCH}/ (e.g. ${RESEARCH}/ptp-sync-tests/gev_ptp_sync_test.py, ${RESEARCH}/scripts-ft/gvsp_pcap_report.py, ${RESEARCH}/tests/gev_scratch_probe.py, ${RESEARCH}/udp_recv_benchmark.py, ${RESEARCH}/scripts/rust-cpp-vendor/, ${RESEARCH}/scripts/harvesters-gentl/). These are our own agents' scripts and may be reused/adapted.

KEY FACTS:
- PTP (IEEE 1588-2008) + scheduled action commands arrived in GigE Vision 2.0; GigE Vision 3.0 (2026) adds optional RDMA/RoCEv2 streaming (GVRSP, 10G+) and larger control packets; GEV 3.0 devices report Version register major=3 and DeviceTLVersionMajor=3; SFNC 2.8 GevStreamingMode {GVSP,GVRSP}. The user calls their cameras "GigE Vision 3" — support must work with GEV 2.x AND 3.0 cameras over GVSP; GVRSP/RDMA is out of scope (no open-source library supports it).
- PTP feature names differ: SFNC PtpEnable/PtpStatus/PtpDataSetLatch/PtpOffsetFromMaster/TimestampLatch/TimestampLatchValue vs deprecated GevIEEE1588/GevIEEE1588Status/GevIEEE1588OffsetFromMaster/GevTimestampControlLatch/GevTimestampValue; Allied Vision PtpMode; LUCID PtpSlaveOnly. Read enumerations by NAME. Bootstrap fallbacks: capability 0x0934 bit 0x00080000 (1588), 0x00020000 (scheduled action), 0x00000040 (action); 1588 enable 0x0954 bit 0x00080000; status 0x096C; timestamp latch write 2 to 0x0944, read 0x0948/0x094C; tick freq 0x093C/0x0940.
- ACTION_CMD = GVCP command 0x0100 to UDP 3956: header 0x42, flags (0x01 ack-required, 0x80 scheduled), cmd 0x0100, length 12 or 20, req_id; payload device_key u32, group_key u32, group_mask u32, [action_time u64]. Camera side: TriggerSelector=FrameStart, TriggerMode=On, TriggerSource=Action1 (some vendors Action0), ActionDeviceKey, ActionSelector, ActionGroupKey, ActionGroupMask.
- Enable PTP BEFORE creating streams (tick frequency cached at stream creation in some stacks; Basler ace classic changes tick 125MHz->1GHz).
- Frames arrive uncompressed (PFNC Mono/Bayer/RGB). OpenCV Bayer naming gotcha: PFNC BayerRG8 (RGGB) -> cv2.COLOR_BayerBG2BGR (verified empirically in skellycam-arch.md). Prefer 8-bit pixel formats.
- SkellyCam pairs frames across cameras by host frame_number lockstep (orchestrator gate); device timestamps / block ids must be stored SEPARATELY from host lifecycle timestamps (do NOT put device-clock values into the lifecycle timestamp dtype that gets host recording start subtracted).
- Package is beartype-checked at runtime (beartype_this_package in skellycam/__init__.py) — all new annotated code must satisfy runtime type checks; use @runtime_checkable Protocols if using Protocols as hints.
- The repo's .venv is broken (missing polars). Do NOT modify it. For running tests create/use a separate env: in Bash, \`UV_PROJECT_ENVIRONMENT="${SCRATCH}/venvs/skellycam-impl" uv sync --all-extras\` (add dev groups as defined in pyproject) then run \`"${SCRATCH}/venvs/skellycam-impl/Scripts/python.exe" -m pytest ...\`. pytest may hang on exit (known) — use timeouts / -p no:cacheprovider and run test files selectively.
- Docker Desktop + WSL2 Ubuntu are available for Linux tests (Aravis fake camera: apt aravis-tools -> arv-fake-gv-camera-0.8 -i lo; use a dedicated \`docker network create\` network or --network none to avoid discovering other containers' fake cameras).
- No real GigE cameras are available. Anything not testable must be clearly marked as untested.
- Do NOT git commit, push, or create branches. Leave changes in the working tree.
- Match surrounding code style (naming, comment density, module layout mirroring skellycam/core/camera/opencv/).
`

const API_SCHEMA = {
  type: 'object',
  properties: {
    notes_file: { type: 'string' },
    example_script: { type: 'string' },
    windows_fake_camera_works: { type: 'boolean' },
    summary_markdown: { type: 'string' },
    gaps: { type: 'array', items: { type: 'string' } },
  },
  required: ['notes_file', 'example_script', 'windows_fake_camera_works', 'summary_markdown', 'gaps'],
}

const WORK_SCHEMA = {
  type: 'object',
  properties: {
    files_changed: { type: 'array', items: { type: 'string' } },
    summary_markdown: { type: 'string', description: 'What was built, design decisions, with repo-relative file:line refs' },
    tests_run: { type: 'array', items: { type: 'object', properties: { command: { type: 'string' }, result: { type: 'string' } }, required: ['command', 'result'] } },
    untested: { type: 'array', items: { type: 'string' } },
    notes_file: { type: 'string' },
  },
  required: ['files_changed', 'summary_markdown', 'tests_run', 'untested', 'notes_file'],
}

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' }, line: { type: 'integer' },
          severity: { type: 'string', enum: ['critical', 'major', 'minor'] },
          summary: { type: 'string' }, failure_scenario: { type: 'string' }, suggested_fix: { type: 'string' },
          evidence: { type: 'string', description: 'command output / code / doc link proving it' },
        },
        required: ['file', 'severity', 'summary', 'failure_scenario', 'suggested_fix', 'evidence'],
      },
    },
    tests_run: { type: 'array', items: { type: 'string' } },
  },
  required: ['findings', 'tests_run'],
}

phase('Prep')
const [api, hwtests] = await parallel([
  () => agent(`${CONTEXT}
TASK: Produce an exact, TESTED reference for the viva-genicam Python package (PyPI 'viva-genicam', latest release, MIT, https://github.com/VitalyVorobyev/viva-genicam) so another engineer can build a SkellyCam backend on it without guessing. Install it into a NEW venv at ${SCRATCH}/venvs/viva (uv venv + uv pip install viva-genicam numpy). Clone the repo (release tag matching the PyPI version) into ${RESEARCH}/src/viva-api/ and read the Python binding source (crates/viva-pygenicam, python package files, .pyi stubs, book/src/python/*).
Document with exact signatures + permalinks: discovery (per-interface, timeouts), opening a camera by IP/serial/MAC, control privilege/heartbeat, feature get/set/execute by name incl. enumerations and listing nodes/checking availability, reading/writing raw registers (needed for bootstrap fallbacks), streaming API (start/stop, how frames are delivered: blocking call / iterator / callback / async; frame object fields: width, height, pixel format, payload type, data as bytes/memoryview/numpy, zero-copy?, device timestamp (units/ticks?), block id, completeness/missing packets, host timestamp), stream tuning (packet size negotiation, packet delay, socket buffer size, resend), whether calls release the GIL (test: measure a busy Python thread while a stream runs), threading rules (can the camera object be used from one thread while frames are pulled in another?), send_action (scheduled), time_calibrate, PTP helpers if any, error/exception types, closing/cleanup, and the testing module (FakeGigeCamera: how to start it, which pixel formats/resolutions/features it supports, whether it supports PTP nodes / actions / TriggerSource=Action1 / timestamps; can several fakes run at once on different ports/IPs?).
RUN on this Windows machine natively: start viva's FakeGigeCamera (if available on Windows) and capture 100 frames from Python, also with 2-3 fake cameras simultaneously, and send a scheduled action. If Windows firewall blocks, try binding to 127.0.0.1 and report. Also run the same in Docker (python:3.12) against Aravis arv-fake-gv-camera-0.8 for comparison. Save a clean, commented example script to ${NOTES}/viva_api_example.py and full notes to ${NOTES}/viva_api.md. List gaps (e.g. pixel formats not decoded, missing PTP helpers) honestly.`,
    { label: 'viva-api', phase: 'Prep', schema: API_SCHEMA }),
  () => agent(`${CONTEXT}
TASK: Build the STAND-ALONE GigE Vision hardware test suite that the user will run on OTHER machines (Windows/macOS/Linux) that have real GigE Vision (2.x and 3.0) PTP-capable cameras. Put it in the repo at ${REPO}/research/gige_vision/hardware_tests/ (this mirrors existing diagnostics scripts in skellycam/system/diagnostics/). Requirements:
- Each script runnable directly: \`python <script>.py --help\`; no dependency on the rest of skellycam. Prefer stdlib-only; scripts that need viva-genicam must say so and fail with a clear install hint.
- Scripts (adapt/improve the research prototypes listed above rather than starting from zero; fix the bugs the verifiers found, e.g. the gev_scratch_probe 'frames reassembled' check passing with 0 complete frames):
  1. gev_probe.py (stdlib): discover cameras on all interfaces (or --ip), read bootstrap Version (report GEV major.minor; flag 3.x), device info, GVCP capability bits (1588, 1588 extended/2.1 profiles, scheduled action, unconditional action, action, packet resend, extended IDs, etc.), current 1588 enable/status, tick frequency, SCPS packet size; print a human table + --json output. Must not change camera state unless --enable-ptp is passed.
  2. gev_ptp_sync_test.py (stdlib): for N cameras: optionally enable PTP (bootstrap register path; document that GenICam feature path is in the viva test), wait for one Master + others Slave with timeout, latch timestamps on all cameras with host-time bracketing and report inter-camera clock offsets and stability over --duration, send unconditional + scheduled ACTION_CMD (configurable keys/mask, broadcast or unicast) and report ACK/ACTION_LATE status. Clear PASS/FAIL/SKIP per check with reasons.
  3. gvsp_capture_report.py: answers "raw or compressed?" — either from a pcap/pcapng (stdlib parser, adapt ${RESEARCH}/scripts-ft/gvsp_pcap_report.py) or live: starts a stream on a camera via GVCP (stdlib, adapt gev_scratch_probe), receives GVSP, and reports payload types, pixel formats (PFNC names), packet size/jumbo, extended-ID usage, frame completeness, resends, device-timestamp deltas and an explicit compressed/uncompressed verdict. Set SO_RCVBUF large and report the effective size and warn when capped.
  4. viva_sync_capture_test.py (needs viva-genicam): open all (or listed) cameras via GenICam features; report GEV version / DeviceTLVersionMajor / GevStreamingMode if present; enable PTP using whichever feature set exists (PtpEnable or GevIEEE1588, latch with PtpDataSetLatch if present), wait for lock, report PtpOffsetFromMaster; then two modes: (a) free-run at --fps and pair frames by device timestamp, reporting inter-camera timestamp spread stats (median/p95/max) and dropped frames by block id; (b) --mode scheduled-action: configure TriggerSource=Action1 (fallback Action0) + keys, send scheduled actions at T0+k*period via viva send_action (fallback: stdlib ACTION_CMD), and report exposure-start spread across cameras per triggered frame. Save a CSV of per-frame device timestamps.
  5. udp_recv_benchmark.py (stdlib, adapt research version): host NIC/socket receive capability test, optional --host for cross-machine test.
  6. README.md: what each test checks, prerequisites per OS (Windows firewall rules for UDP from cameras, jumbo frames/MTU, NIC receive buffers, Linux net.core.rmem_max sysctl, macOS kern.ipc.maxsockbuf, link-local/static IP setup, PoE switch, PTP-capable or at least IGMP-snooping-disabled switch, power-cycling cameras), exact commands, how to interpret results, and what to send back to the developers (JSON/CSV outputs). Explain these are drafts verified only against software-emulated cameras.
- VERIFY every script as far as possible WITHOUT real cameras: run each with --help on Windows; run the stdlib scripts in Docker against Aravis arv-fake-gv-camera-0.8 (it reports Version=0, no PTP/action — scripts must degrade to SKIP gracefully, not crash) and against viva-genicam's FakeGigeCamera (pip install viva-genicam; it has PTP-like nodes and acks actions) — both on Windows natively if the fake runs there and in Docker. Also add a pure-unit selftest mode (e.g. --selftest) for packet encode/decode (ACTION_CMD, PACKETRESEND, GVSP leader parsing) that runs anywhere. Record all commands and outputs in ${NOTES}/hwtests.md.`,
    { label: 'hardware-tests', phase: 'Prep', schema: WORK_SCHEMA }),
])

phase('Implement')
const impl = await agent(`${CONTEXT}
viva-genicam API reference (tested): ${api ? api.notes_file + ' and ' + api.example_script + '\n' + api.summary_markdown + '\nGaps: ' + JSON.stringify(api.gaps) : 'NOT AVAILABLE - read the package yourself'}

TASK: Implement GigE Vision capture support in SkellyCam. Read ${DIGEST}/skellycam-arch.md first, then the actual code. Design constraints:
1. Do not change OpenCV-path behaviour. Add a backend selector: CameraConfig gets \`backend\` (default "opencv"; "gige") plus GigE fields (e.g. device_address (IP), device_serial/MAC, source_pixel_format, sync mode enum: free_run | ptp_free_run | ptp_scheduled_action, ptp settings like action keys/lead time as needed). Keep camera_index unique (synthetic indices for GigE if needed) and keep existing validators working. CameraWorker.create picks the worker method by backend.
2. New package skellycam/core/camera/gige/ mirroring the opencv/ layout (worker method, loop, helpers). Wrap viva-genicam behind a thin adapter module (e.g. gige_device.py) so the library can be swapped later (telegenic/Harvesters); import viva lazily so skellycam works without it; add an optional extra \`gige = ["viva-genicam>=<tested version>"]\` in pyproject.toml (run \`uv lock\` and confirm only the new package(s) are added to uv.lock — revert lock changes otherwise and note it).
3. The GigE loop must reuse the existing orchestrator gate, all_ready start-up, shared-memory ring writes, recording handling and config-update flow exactly as the OpenCV loop does — reuse backend-agnostic helpers rather than copy-paste where practical; if the OpenCV loop needs a small refactor to share code, keep it behaviour-preserving and covered by existing tests.
4. Config apply: Width/Height (+ centered OffsetX/Y respecting increments), PixelFormat preference (BayerXX8 / Mono8 / RGB8 / BGR8; reject packed formats with a clear error), AcquisitionFrameRateEnable/AcquisitionFrameRate (fallback AcquisitionFrameRateAbs), ExposureAuto / ExposureTime (map SkellyCam's exposure value sensibly and document), and extract the actual applied config back into CameraConfig like the OpenCV path does.
5. Convert frames to the BGR uint8 HxWx3 image the pipeline expects, written in place into the shared-memory frame (cv2.cvtColor with dst=), using the correct PFNC->OpenCV Bayer mapping (verify with a synthetic RGGB test image in a unit test). Handle Mono8, Bayer RG/GR/GB/BG 8, RGB8, BGR8; 16-bit unpacked via shift if simple.
6. Device timing: add a separate per-frame record (e.g. device_timing: device_timestamp_ns int64, device_block_id uint64, ptp_status/offset if cheap, -1 when unknown) to the frame metadata dtype WITHOUT disturbing host lifecycle timestamps; thread it through recording finalization into explicit per-camera CSV columns (device.*) and a multi-camera device_timestamp spread column. OpenCV frames fill it with -1/0 sentinels. Update affected tests.
7. PTP + sync: on open, if sync mode uses PTP: enable PTP via feature names (PtpEnable or GevIEEE1588 [+ PtpMode/PtpSlaveOnly if present]) BEFORE starting the stream, then during start-up wait (bounded, configurable) for PTP status Master/Slave, logging status + offset. For ptp_scheduled_action: cameras configured for TriggerSource=Action1 (fallback Action0) with ActionDeviceKey/GroupKey/GroupMask; a single sender (in the camera-group/parent side, NOT per camera) issues scheduled ACTION_CMDs at T0 + k*period using PTP time read from a latched camera timestamp (+ lead time), via viva send_action with a stdlib fallback encoder. Keep this clearly marked experimental and fully covered by unit tests with a fake sender/clock. free_run (no PTP) must work with no PTP features present.
8. Device detection: extend detection to list GigE cameras (only when viva-genicam importable; errors must not break USB detection) with backend, IP, MAC, serial, model, vendor, and a stable camera_id derived from serial/MAC; expose via the existing detect endpoint (check the response model).
9. Tests: unit tests in skellycam/tests (pixel conversion, config mapping with a fake device adapter, ACTION_CMD encoding, scheduler timing, device_timing dtype + CSV columns, detection merge) that run without viva installed; plus an integration test (pytest marker, skipped if viva-genicam missing) that runs the real GigE worker loop against viva's FakeGigeCamera (if it runs on Windows — see the API notes) for a few seconds and checks frames land in shared memory with device timestamps; plus run it on Linux in Docker if feasible. Run the full existing suite before and after; report any new failures (pre-existing: ~15 failures + 4 errors from beartype/MagicMock — do not "fix" unrelated failures but do not add new ones).
10. Docs: add skellycam-docs/docs/core/gige-vision-cameras.mdx (English only) explaining setup, sync modes, PTP, limitations; link from sidebar if sidebars need explicit entries.
Write implementation notes to ${NOTES}/implementation.md.`,
  { label: 'implement-backend', phase: 'Implement', schema: WORK_SCHEMA })

const ui = await agent(`${CONTEXT}
The Python GigE backend was just implemented (see ${NOTES}/implementation.md and \`git -C ${REPO} diff\`). Summary:\n${impl ? impl.summary_markdown : '(missing)'}

TASK: Make the Electron/React UI (${REPO}/skellycam-ui) carry GigE cameras end to end with the MINIMUM change: detection results containing GigE devices are shown as cameras, and the new CameraConfig fields (backend, device address/serial, sync mode, etc.) are preserved when the UI builds/sends camera configs (see skellycam-ui/src/store/slices/cameras/cameras-thunks.ts and the config types). Optionally show a small backend badge and a sync-mode selector only if it is simple and matches existing component patterns. Add i18n keys to en-english.json only (other locales fall back) if the codebase's i18n setup supports fallback — check. Run the UI type-check/lint/unit tests that exist (npm scripts in skellycam-ui/package.json; run \`npm ci\` only if node_modules is missing and it is safe) and report. Do not touch Python files except to fix an API-contract mismatch you find (explain it).`,
  { label: 'implement-ui', phase: 'Implement', schema: WORK_SCHEMA })

phase('Review')
const LENSES = [
  { key: 'correctness', p: 'Correctness & concurrency of the Python GigE backend: read every changed/new Python file (git diff + untracked files). Hunt for real bugs: wrong register/feature usage, wrong Bayer mapping, dtype/shape errors, shared-memory writes, orchestrator gate misuse, frame_number/device block id pairing, resource cleanup on errors, beartype violations, races in the action scheduler, behaviour changes to the OpenCV path. Prove each finding by running code (tests, small scripts in the scratch venv, viva FakeGigeCamera) where possible.' },
  { key: 'protocol', p: 'GigE Vision protocol/spec fidelity: check ACTION_CMD encoding, PTP feature handling (both SFNC and deprecated names, status enumeration by name), timestamp latch, tick-frequency handling, scheduled-time computation, packet size/buffer settings, and the stand-alone scripts in research/gige_vision/hardware_tests/ (register addresses, bit masks, GVSP parsing incl. extended IDs, PACKETRESEND layouts) against Wireshark packet-gvcp.c/packet-gvsp.c and Aravis sources (permalinks in ${DIGEST}). Run the scripts\' selftests and run them in Docker against Aravis arv-fake-gv-camera-0.8 and viva FakeGigeCamera.' },
  { key: 'usability', p: 'Usability for the user who will run the stand-alone tests on other Windows/macOS/Linux machines with real cameras, and for SkellyCam end users: read research/gige_vision/hardware_tests/README.md, the new docs page, and the UI changes. Actually follow the README instructions literally in a clean environment (fresh venv on Windows; python:3.12 Docker for Linux) and report every step that fails, is ambiguous, or would mislead (e.g. missing firewall guidance, wrong commands, scripts that report PASS when nothing was verified, missing --json outputs to send back). Also run the UI checks (type-check/lint) and look for broken contracts between UI and API.' },
]
const reviews = await parallel(LENSES.map(l => () => agent(`${CONTEXT}
You are an adversarial reviewer (lens: ${l.key}). The working tree of ${REPO} contains uncommitted changes adding GigE Vision support (see \`git -C ${REPO} status\` / \`git -C ${REPO} diff\`, notes in ${NOTES}/). ${l.p}
Report ONLY verified, real problems (no style nits), each with concrete evidence. Do not edit repo files.`,
  { label: `review:${l.key}`, phase: 'Review', schema: FINDINGS_SCHEMA })))

const allFindings = reviews.filter(Boolean).flatMap((r, i) => r.findings.map(f => ({ ...f, lens: LENSES[i].key })))
log(`${allFindings.length} review findings`)

phase('Fix')
const fix = allFindings.length === 0 ? null : await agent(`${CONTEXT}
Reviewers reported these findings on the uncommitted GigE Vision changes in ${REPO}:\n${JSON.stringify(allFindings, null, 1)}\n
TASK: For each finding, first re-check it is real (reviewers can be wrong). Fix the real ones with minimal, focused changes. Then re-run: the new unit tests, the full existing pytest suite (compare against the pre-existing failure set), the GigE integration test against viva FakeGigeCamera, the stand-alone scripts' --selftest and --help, and the UI checks. Append a findings table (finding -> fixed / not-a-bug (why) / deferred (why)) to ${NOTES}/implementation.md.`,
  { label: 'fix', phase: 'Fix', schema: WORK_SCHEMA })

return { api, hwtests, impl, ui, findings: allFindings, fix }
