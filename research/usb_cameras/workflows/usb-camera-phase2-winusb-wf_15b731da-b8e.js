export const meta = {
  name: 'usb-camera-phase2-winusb',
  description: 'Phase 2: test libuvc / py-libusb1 / pyuvc / Rust uvc_iso on the WinUSB-bound C930e (bandwidth, timing, naming), then adversarially verify',
  phases: [{ title: 'Test', detail: '4 agents share the C930e via camlock' }, { title: 'Verify', detail: 'skeptic per topic' }],
}

const COMMON = `Context: skellycam USB camera investigation, PHASE 2. Repo C:\\Users\\Dom\\GitHub\\freemocap\\skellycam; work under research\\usb_cameras\\ (read README.md first: layout, frame-log schema, result JSON conventions). Windows 11, not elevated, Git Bash + PowerShell (pwsh available). Do not modify the skellycam package; do not git commit; SendMessage nobody.
Goals: (1) native MJPEG; (2) accurate time light hits the sensor; (3) app-controlled USB bandwidth so more cameras fit per bus (user's Linux reference: 'modprobe uvcvideo quirks=128' — but phase 1 found from source that FIX_BANDWIDTH applies only to uncompressed formats since 2009); (4) stable naming; (5) cross-platform with minimal branching.
USER RULE: no assertion without a test result + reproducible harness; cite result files + exact commands; docs-only facts are 'documented-untested'.

STATE NOW (verified 20:55Z): the Logitech C930e 046D:0843 composite parent USB\\VID_046D&PID_0843\\7&7DCC7CE&0&4 is bound to Microsoft inbox WinUSB (its usbvideo/usbaudio children are gone). libuvc (libusb 1.0.30 + libuvc d07de4fa + patches/0001, binaries research/usb_cameras/libusb/build/cmake/bin/Release/uvc_capture_test.exe) opens it and streamed 1280x720@30 MJPEG for 5 s at default alt 11 (3072 B/microframe) AND at forced alt 6 (944 B): 151/151 valid JPEG, 0 seq gaps, 0 error payloads each (results/windows/Gerald/winusb_install/verify_stream_*). C930e alts: 192,384,512,640,800,944,1280,1600,1984,2688,3072 B per microframe; VC clock 30 MHz; bcdUVC 1.00; no serial number. The C930e shares a Genesys 05e3:0610 USB 2.0 hub (root port 13 of Intel xHCI DEV_7A60) with the generic 'USB Camera' 4C4A:4A55 (usbvideo, single alt 3x1023=3069 B). Under usbvideo, C930e MJPEG 720p30 took alt 11 and could not coexist with the generic camera (second starter got 0x800718CF); threshold was alt 8 pass / alt 9 fail. Other cameras: Logitech C922 046D:085C on root port 1 (usbvideo; MF delivers UVC PTS/SCR metadata because MetadataBufferSizeInKB0=5 is set) — it and the C930e both see monitor 0 (DISPLAY1, portrait 1440x2560 @59.951 Hz, not primary) for screen-flash tests; Razer Kiyo Pro 1532:0E05 has a firmware fault (stops answering EP0 a few minutes after plug-in) — ignore it.
Known phase-1 timing facts: Windows MF/host-arrival timestamps are quantized in 16 ms steps (~4.6 ms std); the screen-flash method floor is ~0.4-0.5 ms; the C930e's UVC PTS is a synthetic counter (fixed 997222 ticks/frame) drifting ~0.1% and jumping one period every ~24 s, so map via SCR/STC instead; rolling shutter ~31 ms per frame height, so use a FIXED ROI (timing/scripts/flash_roi_rows.py, flash_verify_extra.py) when comparing cameras; flash_analyze.py's auto-ROI and self-referential GT are known weaknesses (see timing/VERIFY_method.md and results/windows/Gerald/timing/flash_verify_tools/NOTES.txt). Unprivileged xHCI IOCTLs IOCTL_USB_GET_FRAME_NUMBER_AND_QPC_FOR_TIME_SYNC give (USB frame, microframe) <-> QPC; uvc_capture_test --frame-qpc logs them (usb_frame_qpc.jsonl).
HARD RULES: wrap every command that opens a camera in: uv run --script research/usb_cameras/tools/camlock.py -- <cmd>  (≤ ~3 min per hold; 3 other agents share the C930e). NEVER change drivers, registry, or restart/disable devices; trigger NO UAC prompts (the user declines them). If the C930e stops being openable, record evidence and stop camera work. Keep your total work to roughly 90 minutes — the orchestrator must roll the driver back later today. Raw MJPEG/large data -> C:\\Users\\Dom\\AppData\\Local\\Temp\\claude\\c--Users-Dom-GitHub-freemocap-skellycam\\96d4d83a-4013-4e95-a9bd-1cfedc6522c8\\scratchpad\\runs\\phase2\\ ; results JSON -> results/windows/Gerald/phase2_<topic>/. Frames show the user's room: keep saved images minimal, don't describe contents.
Toolchain: uv run --script (PEP 723); Rust at %USERPROFILE%\\.cargo\\bin (full path); MSVC via "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat".
Return the structured findings object.`

const FINDINGS = {
  type: 'object',
  properties: {
    topic: { type: 'string' }, summary: { type: 'string' },
    findings: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, status: { type: 'string', enum: ['verified-here', 'refuted-here', 'documented-untested', 'inconclusive'] },
      platform: { type: 'string' }, evidence_files: { type: 'array', items: { type: 'string' } }, command: { type: 'string' },
      numbers: { type: 'string' } }, required: ['claim', 'status', 'platform', 'evidence_files', 'command'] } },
    harness_files: { type: 'array', items: { type: 'string' } },
    candidate_assessment: { type: 'array', items: { type: 'object', properties: {
      approach: { type: 'string' }, language: { type: 'string' }, windows: { type: 'string' }, linux: { type: 'string' }, macos: { type: 'string' }, verdict: { type: 'string' } }, required: ['approach', 'verdict'] } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['topic', 'summary', 'findings', 'harness_files', 'candidate_assessment', 'open_questions'],
}
const VERDICT = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    verdicts: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, verdict: { type: 'string', enum: ['confirmed', 'weakened', 'refuted', 'unverifiable'] },
      reason: { type: 'string' }, rerun_numbers: { type: 'string' } }, required: ['claim', 'verdict', 'reason'] } },
    harness_bugs: { type: 'array', items: { type: 'string' } },
    corrected_summary: { type: 'string' },
  },
  required: ['topic', 'verdicts', 'harness_bugs', 'corrected_summary'],
}

const TOPICS = [
  { key: 'bandwidth', prompt: `TOPIC: goal 3 — does app-controlled alt selection recover bandwidth, and how far can it go? Use libuvc (uvc_capture_test --alt / --min-packet-bytes / --bandwidth-factor; also bandwidth/libuvc_forced_alt/uvc_multi_forced_alt.c if useful) and libusb/phase2_windows.ps1 (read it; run the parts relevant to you).
(a) Minimum viable alt: for MJPEG 1280x720@30, 1920x1080@30 and 640x480@30, sweep alts 1..11 (≥20 s each, fixed manual exposure/WB, a high-detail scene is the worst case — note what the camera views, then also test with a deliberately high-detail/high-motion condition if you can create one, e.g. auto-exposure noise or pointing at the flashing monitor), recording: delivered fps, % valid JPEG, seq gaps, error/truncated payloads, payload sizes (median/p99/max) vs alt capacity (alt_bytes*8000/fps per frame), and what failure looks like when a frame exceeds capacity (dropped? corrupt? FID errors?). Log the PROBE/COMMIT dwMaxPayloadTransferSize the camera requests at each mode.
(b) Shared-hub coexistence: with the generic 4C4A:4A55 streaming MJPEG via Media Foundation on the same hub (run bandwidth/run_concurrency.py or bandwidth mf_multi_open in a parallel process; it needs its own camlock?? — use ONE camlock hold wrapping a small script that starts both), test C930e via libuvc at alts 3,5,6,8,9,11: do both stream at full rate? Compare to the usbvideo result (alt 8 pass / 9 fail) and to hs_budget_model.py predictions. Use bandwidth/win_usb_topology.py --pipes-only during streaming to confirm the alt actually set.
(c) Try lowering wCompQuality / using --bandwidth-factor (pyuvc formula) and report whether the camera's own dwMaxPayloadTransferSize request changes.
(d) Estimate cameras-per-high-speed-link achievable with the minimum safe alt (with margin), vs usbvideo's reservation — from measurements, clearly labelled as an estimate.` },
  { key: 'timing', prompt: `TOPIC: goal 2 via libusb — PTS/SCR straight from UVC payload headers on Windows, mapped to QPC through the SOF counter, compared against screen-flash ground truth and against the C922 via Media Foundation metadata.
(a) Capture the C930e via libuvc (uvc_capture_test, with --frame-qpc so usb_frame_qpc.jsonl maps USB frames to QPC; save ALL JPEGs for flash analysis — add a flag if missing) while timing/build/flash_timecode.exe displays the flash pattern on monitor 0. First grab one frame to confirm the C930e still sees monitor 0. Use a FIXED ROI for analysis (see timing/scripts/flash_roi_rows.py / flash_verify_extra.py) and a ground truth that uses no device timestamp.
(b) Build/extend an analysis that maps each frame's SCR (STC + 11-bit SOF) to QPC via the frame-number/QPC samples, fits STC→QPC, then maps PTS (and, given the C930e's synthetic PTS, also the SCR-of-first-payload and host first/last payload times) to QPC; compare per-frame error vs GT: libusb host arrival (first and last payload), SCR-mapped times, PTS-mapped-via-STC. Is libusb arrival less quantized than MF's 16 ms steps? (32 packets/transfer = 4 ms granularity is expected; test --packets-per-transfer smaller if supported.)
(c) Simultaneously capture the C922 via the MF timing tool (timing/build/mf_uvc_timing.exe, see timing/scripts/run_flash_test.ps1; it gives MF PTS/SCR metadata) in the same flash run, so both cameras are judged against the same ground truth with fixed ROIs at the SAME image row; report cross-camera offset stability over ≥3 runs.
(d) Measure the C930e's STC rate vs QPC (ppm) and whether its STC is stable (unlike its PTS).
Be skeptical of your own method; state the method floor.` },
  { key: 'rust', prompt: `TOPIC: Rust from-scratch UVC streamer on WinUSB (research/usb_cameras/rust/uvc_iso, both backends: rawusb (default, pure Rust) and libusb (--features libusb)). Build: cd research/usb_cameras/rust && <cargo full path> build --release -p uvc_iso --features libusb. Run research/usb_cameras/rust/platform/run_windows_phase2.sh (read it first; it is written for the C930e 046d:0843). Report for each backend: open/claim success, alt selected, PROBE/COMMIT values, frames/fps, % valid JPEG, seq gaps, payload header parse (PTS/SCR), the --alt payload:N sweep (3060,1984,1024,640,384 — map to the nearest real alts 2688/1984/944-1280/640/384), the 60 s --sof-instance drift run, CPU%. Compare with libuvc's numbers from results/windows/Gerald/winusb_install/verify_stream_*. Fix bugs you hit (record them). Also re-check nusb: phase 1 found no Isochronous in the released nusb but an open PR #233 'Add cross-platform isochronous transfers' — check its current state (open the PR) and, if feasible in <20 min, build against that branch and try streaming; otherwise report status.` },
  { key: 'python', prompt: `TOPIC: Python user-space paths on WinUSB + naming via libusb.
(a) research/usb_cameras/libusb/py_libusb1/uvc_libusb1_stream.py (pure Python over python-libusb1 3.4.0): stream C930e MJPEG 1280x720@30 and 1920x1080@30 at default and forced smaller alts (e.g. 6, 4) for ≥20 s; report fps, % valid JPEG, seq gaps, CPU% of the Python process (is pure-Python iso handling fast enough? at what packet/transfer sizes?), PTS/SCR parse, host timestamps. Fix bugs you hit.
(b) pyuvc (pupil-labs-uvc 1.0.8, cp312 win_amd64 wheel) in an isolated uv env: does it now open the C930e on WinUSB? MJPEG frames (raw .jpeg_buffer?), bandwidth_factor effect on the alt chosen (verify via bandwidth/win_usb_topology.py --pipes-only while streaming), timestamps it provides (note phase-1 found a QPC-frequency bug in its Windows helper — check what its timestamps look like in practice), controls (exposure).
(c) Naming via libusb: what identity does libusb expose for each camera (bus number, port numbers path, device address, serial string, iProduct) for the WinUSB C930e vs the usbvideo cameras (libusb_get_port_numbers works without opening). Compare with the phase-1 naming results (research/usb_cameras/naming/, results/windows/Gerald/naming/) and state which identifier would let skellycam reopen the same physical camera across reconnects.` },
]

const results = await pipeline(
  TOPICS,
  t => agent(`${COMMON}\n\n${t.prompt}`, { label: `test:${t.key}`, phase: 'Test', schema: FINDINGS }),
  (r, t) => r ? agent(`${COMMON}\n\nYou are an ADVERSARIAL VERIFIER for phase-2 topic '${t.key}'. Try to refute each finding: open the evidence files and check the numbers; re-run the 3 most important verified-here claims under camlock and compare; for bandwidth claims confirm the alt actually set (win_usb_topology.py --pipes-only during streaming) and that 'valid JPEG' means complete decodable frames from the camera (not partial frames padded); for timing claims check the ground truth is independent of the timestamps judged, the ROI is fixed, fits are not circular, and run-to-run stability; for throughput/CPU claims check the measurement method. Return verdicts.\n\nFindings:\n${JSON.stringify(r, null, 1)}`, { label: `verify:${t.key}`, phase: 'Verify', schema: VERDICT }).then(v => ({ key: t.key, report: r, verification: v })) : { key: t.key, report: null, verification: null },
)
return results
