export const meta = {
  name: 'usb-camera-unattended-rerun',
  description: 'Re-run every USB camera test that needs no UAC, replug or reboot (Kiyo excluded); finish goal-1 MJPEG; verify each area; consolidate',
  phases: [
    { title: 'Rerun', detail: 'one agent per test area; hardware serialized by camlock' },
    { title: 'Verify', detail: 'adversarial check of each area against its earlier results' },
    { title: 'Consolidate', detail: 'rerun summary + PROGRESS.md update' },
  ],
}

// Overnight re-run of the unattended tests in research/usb_cameras (requested 2026-10-27; ran as wf_ef322d5c-d99).
// Lives at research/usb_cameras/workflows/overnight_rerun_workflow.js (moved from research/usb_cameras/ on 2026-10-28).
// args: { stamp: 'YYYYMMDD', scratch: '<session scratchpad>' }

const STAMP = (args && args.stamp) || '20261027'
const SCRATCH = (args && args.scratch) || 'C:\\Users\\Dom\\AppData\\Local\\Temp\\claude\\c--Users-Dom-GitHub-freemocap-skellycam\\7c9d3345-0e7f-4af6-bb14-20fd851edd1a\\scratchpad'
const UC = 'C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\research\\usb_cameras'
const RES = UC + '\\results\\windows\\Gerald'
// Earlier workflow scripts: repo copies in research/usb_cameras/workflows/. The originals are still in
// C:\Users\Dom\.claude\projects\c--Users-Dom-GitHub-freemocap-skellycam\96d4d83a-4013-4e95-a9bd-1cfedc6522c8\workflows\scripts
const OLD_WF = UC + '\\workflows'

const COMMON = `Context: skellycam USB camera investigation (multi-camera mocap with low-cost UVC webcams). Repo C:\\Users\\Dom\\GitHub\\freemocap\\skellycam; all work under research\\usb_cameras\\. Read ${UC}\\README.md (layout, per-frame log schema, result JSON conventions) and ${UC}\\PROGRESS.md (state, hazards, where results live) first.
Goals: (1) native MJPEG extraction without decode/re-encode; (2) most accurate time light hits the sensor per frame; (3) USB bandwidth allocation control; (4) consistent device naming; (5) cross-platform with minimal platform branching.
USER RULE: no assertion without a test result + reproducible harness. Cite result files and exact commands.

THIS RUN: an UNATTENDED overnight re-run (${STAMP}) on the Windows 11 test machine "Gerald". Nobody is at the machine. Re-run the existing tests so the earlier results can be confirmed or corrected. Windows, NOT elevated; Git Bash + PowerShell.
- Cameras in scope (all on their normal drivers, usbccgp + usbvideo, all healthy at setup): Logitech C922 046D:085C, Logitech C930e 046D:0843 (MF path ...mi_00#8&39dec205&1&0000#...), generic "USB Camera" 4C4A:4A55 (same hub as the C930e). These three are pointed at the monitor, which is kept on for the flash tests.
- EXCLUDED: Razer Kiyo Pro 1532:0E05. The user excluded it as known flaky. Never open it, and leave it out of "all cameras" runs. If a harness opens every camera by default, pass an explicit device list or filter.
- SKIP any test that needs a human or admin: UAC/elevation, WinUSB driver install or rollback (libusb/winusb/*, phase2_windows.ps1, phase3*), replug, port move, reboot, covering a lens, or registry writes (enable/revert_uvc_metadata.ps1, ETW *_elevated.ps1). List each skipped test and why.
- NEVER restart, disable or remove devices (no pnputil, no devrestart.exe, no win_restart_*_admin.ps1). LogiTune/Razer vetoes leave cameras broken until a replug, and nobody can replug tonight. Closing the LogiTuneAgent/RazerAppEngine processes is approved; stopping services is not.
- Hardware discipline: wrap every command that opens a camera in: uv run --script research/usb_cameras/tools/camlock.py -- <cmd>; hold at most about 3 min per invocation. Other agents test concurrently.
- Broken camera: if a camera fails, record evidence (Get-PnpDeviceProperty DEVPKEY_Device_DevNodeStatus; DN_NEED_RESTART = 0x100; MF HRESULTs) and move on. Do not try to fix it.
- Night conditions: the room may be dark. For each capture, record mean frame luma and the exposure mode/value you can read (auto-exposure priority can lower fps in low light). When fps differs from the earlier run, check whether low light explains it before calling it a regression.
- Load: other agents run concurrently, so CPU% numbers carry load. Record machine CPU% at the start and end of CPU-sensitive runs and label them.
- Results: write NEW timestamped result dirs (e.g. ${RES}\\<test>\\${STAMP}T<hhmmss>Z_<what>\\ or <test>_rerun_${STAMP}\\). Never delete or overwrite earlier results. Big raw data goes to ${SCRATCH}\\runs\\, not the repo.
- Do not modify the skellycam package; do not git commit; do not use SendMessage.
- Privacy: frames show the user's room; keep saved sample images minimal; don't describe room contents.
- Time box: finish within about 3 hours. If something hangs, kill the processes you started, record it, and move on. Kill every child process you started before you return.
Toolchain: PEP 723 scripts via 'uv run --script'; Rust at %USERPROFILE%\\.cargo\\bin (use the full path); MSVC via "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat".
Earlier evidence to compare against: ${UC}\\results\\agent_reports\\phase1_reports_and_verifications.json and phase2_reports_and_verifications.json (every earlier claim and its verification), the workflow journals next to them, and the earlier workflow scripts in ${OLD_WF} (the exact prompts and commands used before).`

const RERUN_SCHEMA = {
  type: 'object',
  properties: {
    area: { type: 'string' },
    summary: { type: 'string' },
    tests: { type: 'array', items: { type: 'object', properties: {
      test: { type: 'string' }, command: { type: 'string' }, cameras: { type: 'string' },
      outcome: { type: 'string', enum: ['pass', 'fail', 'error', 'skipped'] },
      result_dir: { type: 'string' }, earlier_result: { type: 'string' },
      comparison: { type: 'string', description: 'new vs earlier numbers and whether the earlier claim still holds' },
      conditions: { type: 'string', description: 'luma/exposure, machine load, camera health' } },
      required: ['test', 'command', 'outcome', 'result_dir', 'comparison'] } },
    claims: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, status: { type: 'string', enum: ['reconfirmed', 'changed', 'refuted', 'new', 'inconclusive'] },
      evidence_files: { type: 'array', items: { type: 'string' } }, numbers: { type: 'string' } },
      required: ['claim', 'status', 'evidence_files'] } },
    skipped: { type: 'array', items: { type: 'object', properties: { test: { type: 'string' }, reason: { type: 'string' } }, required: ['test', 'reason'] } },
    camera_health: { type: 'string' },
    harness_fixes: { type: 'array', items: { type: 'string' } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['area', 'summary', 'tests', 'claims', 'skipped', 'camera_health', 'harness_fixes', 'open_questions'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    area: { type: 'string' },
    verdicts: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, verdict: { type: 'string', enum: ['confirmed', 'weakened', 'refuted', 'unverifiable'] },
      reason: { type: 'string' }, rerun_numbers: { type: 'string' } }, required: ['claim', 'verdict', 'reason'] } },
    harness_bugs: { type: 'array', items: { type: 'string' } },
    missed_tests: { type: 'array', items: { type: 'string' }, description: 'unattended tests in this area that the rerun agent should have run but did not' },
    corrected_summary: { type: 'string' },
  },
  required: ['area', 'verdicts', 'harness_bugs', 'missed_tests', 'corrected_summary'],
}

const AREAS = [
  { key: 'naming', prompt: `AREA: goal 4, device naming (research/usb_cameras/naming/). Re-run the Windows identity tests: win_identity_dump.py, win_api_names.py, camera_identity.py, libusb_identity.py (descriptor read only, no streaming), identity_diff.py against the earlier dumps in ${RES}\\naming\\ (the C930e's instance IDs changed on 2026-10-25 after the WinUSB rollback; check the identity rules still give stable keys), and the unit tests test_parsers.py, test_linux_fake_sysfs.py, test_macos_fake_ioreg.py. Skip win_stability_workflow / the reboot, replug and port-move steps, and the *_admin.ps1 scripts.` },
  { key: 'mjpeg', prompt: `AREA: goal 1, native MJPEG (research/usb_cameras/mjpeg/ and ${RES}\\mjpeg_*). This area was never finished: on 2026-10-25 the finishing agent was stopped part-way, so its partial edits are on disk, and an unverified compile-only hand-back is in mjpeg/HANDBACK_earlier_instance.md. Take it over and finish it:
1. Inventory: read every file in mjpeg/ (pyav/, msmf/, winrt/, opencv/, drafts/, mjpeg_common.py, summarize.py, resummarize.py, aggregate.py, run_matrix.py, run_one.py, list_formats.py) and every ${RES}\\mjpeg_* dir. Make the code coherent (one version of each tool; keep good additions such as silent-format-fallback detection). Mark earlier results invalidated by the 2026-10-25 device-state incidents (MF_E_REBOOT_REQUIRED 14:04 to about 14:17 and about 14:33 to 14:45 local; Kiyo 0x8007001F from about 14:30) with an INVALID.txt if not already marked.
2. Run the full Windows matrix fresh on the C922, C930e and generic camera: (a) PyAV dshow vcodec=mjpeg passthrough, (b) Media Foundation IMFSourceReader native MJPG, (c) WinRT MediaFrameReader MJPG subtype, (d) OpenCV CAP_DSHOW/CAP_MSMF MJPG decode baseline (+ raw mode if it yields JPEG). Modes: a common 1280x720@30 and each camera's max MJPEG mode; single camera and all three at once. Per cell: frames, fps achieved, % valid JPEG (SOI..EOI and decodes), payload size stats, process CPU%, whether the bytes are camera-native (compare JPEG headers/DQT tables byte-for-byte across APIs; detect any re-encode), and which timestamps each API attaches. One cell per camlock hold.
3. Linux/macOS drafts under mjpeg/drafts/: make sure they exist, are complete, parse (python -m py_compile / bash -n), write results in the README layout, and have one runner per OS (V4L2 via PyAV input_format=mjpeg and pure-Python mmap V4L2; macOS PyAV avfoundation and a pyobjc AVCaptureVideoDataOutput native-format check).
4. Write mjpeg/RESULTS.md: a matrix table (approach x camera x mode -> fps, valid %, CPU%, native?) linking the result dirs. Note that the Kiyo was excluded on purpose.` },
  { key: 'timing', prompt: `AREA: goal 2, capture timing (research/usb_cameras/timing/: build/*.exe, scripts/, src/, tests/, VERIFY_method.md). The monitor is on and the three in-scope cameras face it, so the flash tests can run. Re-run: MF UVC metadata timing (mf_uvc_timing.exe; check PTS/SCR are present on the C922 and C930e; the generic camera has no metadata registry value), the flash timecode / flash verify method (flash_timecode.exe, flash_verify_method.py, flash_verify_extra.py, flash_analyze.py, flash_rows.py, flash_roi_rows.py, flash_step_response.py, flash_impulse_response.py, flash_exposure_scan.py, display_model_check.py) on each in-scope camera, the dshow open probe, and the unit tests in timing/tests. Compare against ${RES}\\timing\\ (incl. flash_verify_*, metadata_check_c930e_after_rollback). Skip the kiyo_* probes, devrestart.exe, usb_ep0_probe if it needs exclusive device access that would require a driver change, the flash_libuvc_* scripts (they need WinUSB), and enable/revert_uvc_metadata.ps1. The flash window must be in front: if another window covers it, record that the run is invalid rather than reporting its numbers.` },
  { key: 'bandwidth', prompt: `AREA: goal 3, USB bandwidth on the normal usbvideo driver (research/usb_cameras/bandwidth/). Re-run: win_usb_topology.py (incl. --pipes-only snapshots while streaming), run_concurrency.py (which camera combinations stream together at which modes; C922, C930e, generic only), headroom.py, hs_budget_model.py, mf_multi_open (build with build.bat if needed), coexist_hold.sh/coexist_summarize.py, the verify/ hold scripts that do not need WinUSB, and strict_jpeg_check.py on what you capture. Compare against ${RES}\\bw_* dirs. Skip libuvc_forced_alt, alt_sweep_* and anything else that needs WinUSB, and the ETW capture (it needs elevation).` },
  { key: 'libusb_rust', prompt: `AREA: libusb/libuvc and Rust stacks, usbvideo-compatible parts only (research/usb_cameras/libusb/ and rust/). Re-run: libuvc build (build_windows.ps1) and its unit tests (libusb/tests, patch unit test), libuvc list and the libuvc-on-usbvideo capture/example (expected to fail to stream; confirm the same failure mode), py_libusb1 list + unit tests, pyuvc probe/clock check (earlier: pyuvc 1.0.8 crashes on Windows; confirm), phase3_analyze.py self-test, Rust workspace build, compile checks (incl. cross-checks), nokhwa list + capture at 1280x720@30 on the C922, C930e and generic camera (rust/run_windows_nokhwa.sh, filtered to exclude the Kiyo), mf_native_types, uvc_iso list via libusb and rawusb (descriptors only), and the devnode status check. Compare against ${RES}\\{libuvc_*,py_libusb1_*,pyuvc_*,rust_*,verify_rust,phase3_analyze_selftest.json}. Skip every WinUSB install/stream step (phase2_windows.ps1, libusb/winusb/*, rust run_windows_phase2.sh streaming).` },
  { key: 'prior_art', prompt: `AREA: prior-art capture libraries (research/usb_cameras/prior_art/ and verify_prior_art/). Re-run every probe on the C922, C930e and generic camera: cv2_enumerate_probe.py, gst_probe.py (ksvideosrc and mfvideosrc if GStreamer is installed), openpnp_capture_probe.py, pyav_dshow_probe.py (incl. listopts and wallclock variants), pygrabber_probe.py, sdl3_camera_probe.py, repo_metadata.py (network: refresh only if reachable), and the verify_prior_art checks. Compare against ${RES}\\prior_art_* and verify_prior_art, and update prior_art/SURVEY.md only where a number changed (mark the change with the date ${STAMP}).` },
]

phase('Rerun')
const results = await pipeline(
  AREAS,
  a => agent(`${COMMON}\n\n${a.prompt}\n\nReturn the structured rerun result.`, { label: `rerun:${a.key}`, phase: 'Rerun', schema: RERUN_SCHEMA }),
  (r, a) => r
    ? agent(`${COMMON}\n\nYou are an adversarial verifier for the ${a.key} area. Try to REFUTE the rerun result below. Open the new and earlier result files and check the numbers; re-run the two or three most important tests yourself (under camlock) and compare; check the comparisons are fair (same mode, same cameras, light level, load); check the agent did not skip unattended tests in its area that it could have run (list them in missed_tests); check nothing touched the Kiyo or needed elevation. Default to 'weakened' when the evidence is thin.\n\nRerun result:\n${JSON.stringify(r, null, 1)}`, { label: `verify:${a.key}`, phase: 'Verify', schema: VERDICT_SCHEMA })
        .then(v => ({ key: a.key, rerun: r, verification: v }))
    : { key: a.key, rerun: null, verification: null },
)

phase('Consolidate')
const done = results.filter(Boolean)
const summary = await agent(`${COMMON}

You are the consolidation agent. Below are the per-area rerun results and their adversarial verifications from tonight's unattended run. Do not run cameras.
1. Write ${RES}\\RERUN_${STAMP}.md: what ran, what was skipped and why, camera health through the night, and a per-area table of earlier claim -> tonight's result -> verifier verdict, with links to result dirs. Flag every claim that changed or was refuted, and say whether light level or load could explain it.
2. Copy the full structured results below into ${UC}\\results\\agent_reports\\rerun_${STAMP}_reports_and_verifications.json.
3. Update ${UC}\\PROGRESS.md: add a dated "Overnight rerun ${STAMP}" section (results, goal-1 MJPEG status, harness fixes, missed tests), update the goal status table and the "Machine state" table, and keep the rest. Do NOT edit the Claude Doc report.
Return a short plain-text summary (under 250 words) for the user: what was re-confirmed, what changed, what failed, and what still needs a human.

Results:
${JSON.stringify(done, null, 1)}`, { label: 'consolidate', phase: 'Consolidate' })

return { summary, areas: done.map(d => ({ key: d.key, ok: !!d.rerun, verified: !!d.verification })) }
