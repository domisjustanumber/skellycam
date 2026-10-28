export const meta = {
  name: 'verify-timing-flash',
  description: 'Three-lens adversarial verification of the screen-flash timing results and the Kiyo MF failure',
  phases: [{ title: 'Verify', detail: 'method/circularity, independent re-run, Kiyo/metadata side effect' }],
}

const CTX = `Context: skellycam USB camera investigation, repo C:\\Users\\Dom\\GitHub\\freemocap\\skellycam, work under research\\usb_cameras\\ (read its README.md first). Windows 11, not elevated, Git Bash + PowerShell. Cameras: Razer Kiyo Pro 1532:0E05 (cannot see any monitor), Logitech C922 046D:085C and C930e 046D:0843 (both pointed at monitor 0, DISPLAY1, portrait 1440x2560 @59.951 Hz, not primary). Usbvideo MetadataBufferSizeInKB0=5 was set on all three cameras' interface keys today so Media Foundation delivers UVC payload-header metadata (PTS/SCR). Any command that opens a camera MUST be wrapped: uv run --script research/usb_cameras/tools/camlock.py -- <cmd>, max ~3 minutes per hold; other agents are testing concurrently. Never restart/disable devices (LogiTune/Razer apps veto it and leave cameras broken). Do not change drivers or registry. Do not git commit. Use SendMessage to nobody.
The user's rule: no assertion without a test result and reproducible harness. You are a skeptic: default to 'refuted' or 'weakened' when evidence is insufficient.

The timing agent claims (from results/windows/Gerald/timing/flash_run1_repositioned/, produced by timing/build/flash_timecode.exe displaying a QPC timecode on monitor 0, the MF capture tool in timing/, timing/scripts/flash_analyze.py and tools/analyze_frames.py; raw MJPEG in C:\\Users\\Dom\\AppData\\Local\\Temp\\claude\\c--Users-Dom-GitHub-freemocap-skellycam\\96d4d83a-4013-4e95-a9bd-1cfedc6522c8\\scratchpad\\runs\\flash1\\capture\\):
 1280x720@30 MJPEG, manual exposure 7.81 ms, WB 4500K, 30 s. Std of per-frame error vs flash ground truth:
   C930e: uvc_pts_mapped_direct 0.52 ms (offset -52.08 ms); uvc_pts_via_scr_lsq_envelope 0.48 ms (offset -21.0); host_arrival 4.50 ms (offset -61.06); MF os_timestamp 4.55 ms.
   C922:  uvc_pts_mapped_direct 0.45 ms (offset -52.10 ms); uvc_pts_via_scr_lsq_envelope 0.50 ms (offset -18.94); host_arrival 4.66 ms (offset -59.48); MF os_timestamp 4.83 ms.
 Cross-camera: uvc_pts_mapped_direct offsets agree to 0.02 ms -> best source for multi-camera sync. No dropped frames (891/893). Method floor on synthetic data ~75 us. Kiyo Pro: 0 frames, 21 MF errors at start in this tool.`

const SCHEMA = {
  type: 'object',
  properties: {
    lens: { type: 'string' },
    verdicts: { type: 'array', items: { type: 'object', properties: {
      claim: { type: 'string' }, verdict: { type: 'string', enum: ['confirmed', 'weakened', 'refuted', 'unverifiable'] },
      reason: { type: 'string' }, numbers: { type: 'string' }, evidence_files: { type: 'array', items: { type: 'string' } } },
      required: ['claim', 'verdict', 'reason'] } },
    corrected_statement: { type: 'string', description: 'what CAN be asserted, precisely, with numbers and caveats' },
    new_files: { type: 'array', items: { type: 'string' } },
    harness_bugs: { type: 'array', items: { type: 'string' } },
  },
  required: ['lens', 'verdicts', 'corrected_statement', 'new_files', 'harness_bugs'],
}

const LENSES = [
  { key: 'method', prompt: `LENS: method and circularity (no camera needed). Read flash_timecode.cpp, the MF capture tool source, flash_analyze.py and analyze_frames.py line by line. Answer precisely: (1) What is the ground truth exactly — how is each camera frame's displayed QPC time decoded, and how is it related to when photons hit the sensor (vsync/scanout timing of the timecode row, compositor / independent flip on a non-primary portrait monitor, rolling shutter row of the ROI, exposure midpoint vs start)? Is ground truth computed independently of the timestamps being judged? (2) How is 'uvc_pts_mapped_direct' computed — is the PTS->host mapping fitted using the ground truth or the flash data itself (which would make the 0.5 ms std and the 0.02 ms cross-camera agreement circular)? Is it fitted per camera with free offset+slope against something? Same for the SCR envelope variants. (3) Is 'std of error vs GT' computed after removing a per-source fitted offset (and slope?) — if slope is fitted per source, a regular device clock would trivially score well; does host_arrival get the same treatment (fair comparison)? (4) Is the 'periodic-fit residual' in analyze_frames meaningful for accuracy or only for regularity? (5) Do units/clock domains (QPC ticks vs ns, device clock Hz from descriptors) check out? Write a short markdown note research/usb_cameras/timing/VERIFY_method.md with your findings and, if you find circularity, write and run a corrected non-circular analysis on the existing data (e.g. fit mapping on first half, evaluate on second half; or map PTS only via SCR without GT) and report those numbers.` },
  { key: 'rerun', prompt: `LENS: independent reproduction. (1) Re-run flash_analyze.py and analyze_frames.py on the existing flash_run1_repositioned data and check the reported numbers reproduce exactly. (2) Then do a FRESH repeat of the flash test (open issue: only one 30 s run): first grab one frame each from C922 and C930e under camlock and look at it to confirm monitor 0 is still in view (if not, report and stop the fresh run); then run the same display + capture procedure (find how the timing agent ran it in results/.../flash_run1_repositioned/NOTES.txt and capture.log), 30 s, twice if time allows, at 1280x720@30 MJPEG and once at a different exposure (e.g. ~2 ms if settable) to see whether offsets shift by half the exposure change (tests whether PTS marks exposure start). Store under results/windows/Gerald/timing/flash_verify_<n>/. Report run-to-run stability of std and offsets per source, per camera. Raw MJPEG goes to the scratchpad, not the repo.` },
  { key: 'kiyo', prompt: `LENS: the Kiyo Pro failure and possible side effects of the metadata registry change. The Kiyo Pro yielded 0 frames / 21 MF errors in the timing capture tool. Determine (under camlock, short holds) whether the Kiyo streams MJPEG via: OpenCV CAP_MSMF, OpenCV CAP_DSHOW, PyAV dshow, and the timing agent's MF tool with metadata reading disabled (if it has such a switch, or a minimal MF SourceReader you write), at 1280x720@30 and its other MJPEG modes. Capture the exact HRESULTs. Check whether the C922/C930e behave differently with vs without requesting metadata. Look in the System/Application event logs and the timing agent's registry logs (results/windows/Gerald/timing/registry_*.log) for clues. Do NOT revert the registry; instead, report whether evidence suggests MetadataBufferSizeInKB0 breaks the Kiyo in MF (and if so what test would confirm — e.g. revert script run elevated + replug, which the user would do). Also check if Razer Synapse being closed or LogiTune matters. Report the mechanism as far as evidence allows.` },
]

const out = await parallel(LENSES.map(l => () => agent(`${CTX}\n\n${l.prompt}`, { label: `verify:${l.key}`, phase: 'Verify', schema: SCHEMA })))
return out
