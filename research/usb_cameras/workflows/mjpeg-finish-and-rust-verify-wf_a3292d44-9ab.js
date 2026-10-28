export const meta = {
  name: 'mjpeg-finish-and-rust-verify',
  description: 'Fresh MJPEG agent consolidates + completes goal-1 tests, then is verified; Rust findings adversarially verified in parallel',
  phases: [{ title: 'Finish', detail: 'MJPEG consolidation + remaining matrix' }, { title: 'Verify', detail: 'skeptics for MJPEG and Rust' }],
}

const COMMON = `Context: skellycam USB camera investigation (multi-camera mocap with low-cost UVC webcams). Repo C:\\Users\\Dom\\GitHub\\freemocap\\skellycam; all work under research\\usb_cameras\\ — read research\\usb_cameras\\README.md first (layout, per-frame log schema, result JSON conventions). Windows 11, NOT elevated; Git Bash + PowerShell. Do not modify the skellycam package; do not git commit; use SendMessage to nobody.
Goals: (1) native MJPEG extraction without decode/re-encode; (2) most accurate time light hits the sensor per frame; (3) USB bandwidth allocation control; (4) consistent device naming; (5) cross-platform with minimal platform branching. OpenCV is only a baseline.
USER RULE: no assertion without a test result + reproducible harness. Cite result files and exact commands. Docs-only facts are 'documented-untested'.
Cameras on this machine (all usbvideo.sys, all healthy after a replug at ~14:45 local): Razer Kiyo Pro 1532:0E05 (SuperSpeed; cannot see the monitor); Logitech C922 046D:085C; Logitech C930e 046D:0843 (composite parent uses a Logitech-supplied INF; RESERVED for a later WinUSB swap — do not change drivers); generic 'USB Camera' 4C4A:4A55 (new, on the same hub as the C930e, ports 3/4; include it). UVC metadata registry value MetadataBufferSizeInKB0=5 is set on the Kiyo/C922/C930e interfaces (not the generic camera).
Hardware discipline: wrap any command that opens a camera in: uv run --script research/usb_cameras/tools/camlock.py -- <cmd>; hold ≤ ~3 min per invocation; other agents test concurrently. NEVER restart/disable/remove devices (LogiTune/Razer vetoes leave cameras broken) and trigger NO UAC prompts (the user will decline them). If a camera is in a broken state, record it with evidence (DevNodeStatus via Get-PnpDeviceProperty DEVPKEY_Device_DevNodeStatus; DN_NEED_RESTART = 0x100) and move on.
Toolchain: PEP 723 scripts via 'uv run --script'; Rust at %USERPROFILE%\\.cargo\\bin (full path); MSVC via "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat". Big raw data goes to C:\\Users\\Dom\\AppData\\Local\\Temp\\claude\\c--Users-Dom-GitHub-freemocap-skellycam\\96d4d83a-4013-4e95-a9bd-1cfedc6522c8\\scratchpad\\runs\\, not the repo.
Privacy: frames show the user's room; keep saved sample images minimal; don't describe room contents.`

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    summary: { type: 'string' },
    findings: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, status: { type: 'string', enum: ['verified-here', 'refuted-here', 'documented-untested', 'inconclusive'] },
      platform: { type: 'string' }, evidence_files: { type: 'array', items: { type: 'string' } }, command: { type: 'string' },
      numbers: { type: 'string' }, sources: { type: 'array', items: { type: 'string' } } },
      required: ['claim', 'status', 'platform', 'evidence_files', 'command'] } },
    harness_files: { type: 'array', items: { type: 'string' } },
    drafted_tests: { type: 'array', items: { type: 'object', properties: {
      platform: { type: 'string' }, path: { type: 'string' }, run: { type: 'string' }, measures: { type: 'string' }, needs: { type: 'string' } },
      required: ['platform', 'path', 'run', 'measures'] } },
    candidate_assessment: { type: 'array', items: { type: 'object', properties: {
      approach: { type: 'string' }, language: { type: 'string' }, windows: { type: 'string' }, linux: { type: 'string' }, macos: { type: 'string' }, verdict: { type: 'string' } },
      required: ['approach', 'verdict'] } },
    system_changes: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['topic', 'summary', 'findings', 'harness_files', 'drafted_tests', 'candidate_assessment', 'system_changes', 'open_questions'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    verdicts: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, verdict: { type: 'string', enum: ['confirmed', 'weakened', 'refuted', 'unverifiable'] },
      reason: { type: 'string' }, rerun_numbers: { type: 'string' } }, required: ['claim', 'verdict', 'reason'] } },
    harness_bugs: { type: 'array', items: { type: 'string' } },
    drafted_test_issues: { type: 'array', items: { type: 'string' } },
    corrected_summary: { type: 'string' },
  },
  required: ['topic', 'verdicts', 'harness_bugs', 'drafted_test_issues', 'corrected_summary'],
}

const MJPEG = `${COMMON}

TASK: you take over goal 1 (native MJPEG extraction) and finish it. Directory: research/usb_cameras/mjpeg/ and results/windows/Gerald/mjpeg_* . Earlier, two or three agent instances worked here concurrently by accident and were stopped; the code and results on disk are a mix of their work. Steps:
1. Inventory: read every file in mjpeg/ (incl. pyav/, msmf/, winrt/, drafts/, mjpeg_common.py, summarize.py, run_matrix.py if present) and every results/windows/Gerald/mjpeg_* dir. Make the code coherent (one version of each tool; fix inconsistencies; keep good additions such as silent-format-fallback detection). Note which earlier results are invalid because of the device-state incidents (MF_E_REBOOT_REQUIRED 14:04–~14:17 local and ~14:33–14:45; Kiyo ERROR_GEN_FAILURE 0x8007001F from ~14:30 until the replug) and mark them with an INVALID.txt.
2. Complete the Windows matrix with fresh runs (all 4 cameras): approaches (a) PyAV dshow vcodec=mjpeg passthrough, (b) Media Foundation IMFSourceReader native MJPG, (c) WinRT MediaFrameReader MJPG subtype, (d) OpenCV CAP_DSHOW/CAP_MSMF MJPG decode baseline (+ raw mode if it yields JPEG); modes: a common 1280x720@30 and each camera's max MJPEG mode; single camera and all cameras at once. Per cell: frames, fps achieved, % valid JPEG (SOI..EOI and decodes), payload size stats, process CPU%, whether bytes are camera-native (e.g. compare byte-identical JPEG headers/quantization tables across APIs; detect any re-encode), plus which timestamps each API attaches. Keep camlock holds short (one cell per hold).
3. Linux/macOS drafts under mjpeg/drafts/: make sure they exist, are complete, parse (python -m py_compile / bash -n), write results in the README layout, and have a single runner per OS. Include V4L2 (PyAV v4l2 input_format=mjpeg; pure-Python mmap V4L2), macOS (PyAV avfoundation; pyobjc AVCaptureVideoDataOutput native format check for compressed 'dmb1'/'jpeg' buffers).
4. Write mjpeg/RESULTS.md: a matrix table (approach × camera × mode → fps, valid %, CPU%, native?) with links to result dirs.
Return the structured findings.`

const RUST_CLAIMS = `Rust agent's reported findings (verify these):
1. nokhwa 0.10.11 (MSMF backend) delivers native MJPEG bytes unchanged at 1280x720@30: C922 593/593 valid, 30.02 fps, median 144 KB; C930e 589/589 valid, 30.06 fps, median 85 KB; Kiyo (18:03Z run) 424/424, 30.03 fps, 107 KB. nokhwa reports the format as '1280x720@1 MJPEG' (wrong fps field). Evidence: results/windows/Gerald/rust_nokhwa_capture/20261025T183903Z_camsall_1280x720/ etc. Command: bash research/usb_cameras/rust/run_windows_nokhwa.sh.
2. nokhwa Buffer::capture_timestamp on Windows = MF IMFSample time (QPC, 100 ns) + per-stream epoch, not Unix time; after epoch removal it is on the host QPC clock. host_arrival − sample_time median: C922 16.2 ms, C930e 0.41 ms, Kiyo 32.4 ms.
3. MF exposes NV12 alongside MJPEG with identical counts even with converters disabled (C922 120 MJPG/120 NV12/98 YUY2 ...); nokhwa's format list drops some native types. Evidence results/windows/Gerald/rust_mf_native_types/1792951371/summary.json (build/release/mf_native_types.exe).
4. rawusb 0.1.7 on Windows enumerates only the two Intel root hubs and never sees usbvideo-bound cameras.
5. libusb backend on Windows enumerates all devices and reads UVC descriptors without opening the camera (alt settings: Kiyo alt1 3072 B, alt2 33792 B; C922 11 alts 192..3060 B/microframe, dwClockFrequency 30 MHz, UVC 1.00; 4c4a:4a55 one alt 3069 B; C930e config descriptor read fails LIBUSB_ERROR_NOT_FOUND — Logitech composite INF oem74.inf).
6. Neither backend can stream while usbvideo owns the cameras.
7. Compile status: uvc_iso (rawusb) builds + cross-checks for x86_64-linux-gnu and aarch64-apple-darwin; uvc_iso+libusb builds on host; nokhwa_probe builds on host but cross-checks fail in v4l2-sys/objc build scripts; nusb has no Isochronous transfer type (E0425) so cannot do UVC iso; 'uvc' crate fails (mozjpeg-sys), 'libuvc' crate fails (libuvc-sys build). Evidence results/windows/Gerald/rust_compile_checks/*.
Code: research/usb_cameras/rust/ (Cargo workspace: nokhwa_probe, uvc_iso; compile_checks/; platform/run_linux.sh, run_macos.sh, run_windows_phase2.sh).`

const rustVerify = () => agent(`${COMMON}

You are an adversarial verifier. ${RUST_CLAIMS}
For each claim: open the cited evidence files and check numbers; re-run at least claims 1, 2, 5 and 7(nusb part) yourself (camera runs under camlock, include the Kiyo and the generic 4C4A:4A55 camera now that they are healthy); for 'native MJPEG' verify bytes are the camera's (e.g. compare JPEG header/DQT/APP segments with frames from PyAV dshow passthrough or MF native for the same camera/mode); for claim 2 check the epoch arithmetic in nokhwa source under %USERPROFILE%\\.cargo\\registry and that the 16 ms C922 latency is not an artifact (e.g. buffering, the metadata registry setting); for claim 7 check nusb's current release docs/source (docs.rs) for any isochronous support including unreleased branches — cite versions. Check drafted Linux/macOS scripts parse (bash -n). Return verdicts.`, { label: 'verify:rust', phase: 'Verify', schema: VERDICT_SCHEMA })

const mjpegChain = async () => {
  const r = await agent(MJPEG, { label: 'finish:mjpeg', phase: 'Finish', schema: FINDINGS_SCHEMA })
  if (!r) return { report: null, verification: null }
  const v = await agent(`${COMMON}

You are an adversarial verifier for goal 1 (native MJPEG). Try to REFUTE each finding below: open evidence files, check numbers, re-run the 3 most important verified-here claims under camlock and compare; for any 'native/no re-encode' claim independently check (byte-level JPEG segment comparison across APIs, or presence of decoder/encoder MFTs in the topology); check CPU% measurement method is fair across approaches; check drafted Linux/macOS tests parse and write where the README says. Return verdicts.

Findings:
${JSON.stringify(r, null, 1)}`, { label: 'verify:mjpeg', phase: 'Verify', schema: VERDICT_SCHEMA })
  return { report: r, verification: v }
}

const [mj, rv] = await parallel([mjpegChain, rustVerify])
return { mjpeg: mj, rust_verification: rv }
