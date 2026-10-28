export const meta = {
  name: 'mf-vs-dshow-reliability',
  description: 'Gather and adversarially verify evidence on Media Foundation vs DirectShow camera capture reliability on Windows',
  phases: [
    { title: 'Gather', detail: 'local research evidence + 3 web sweeps (MF flakiness, DShow downsides/future, what apps chose)' },
    { title: 'Verify', detail: 'one adversarial verifier per gather report re-checks every claim against its source' },
  ],
}

const CONTEXT = `Context: skellycam (repo at C:\\Users\\Dom\\GitHub\\freemocap\\skellycam, branch dom/research) is a Python multi-camera capture app for cheap USB UVC webcams (Logitech C922, C930e, generic 4C4A:4A55) streaming MJPEG, often several cameras at once, one OS process per camera, for motion capture where per-frame timestamps and long-run stability matter. On Windows we are deciding between two capture stacks:
- Media Foundation (MF): IMFSourceReader with the camera's native MJPG media type and MF_READWRITE_DISABLE_CONVERTERS, likely via a small C++ Python extension. On Win10+ MF capture goes through the Windows Camera Frame Server service.
- DirectShow (DS/DShow): e.g. PyAV/FFmpeg dshow input with vcodec=mjpeg, or a custom DS graph. OpenCV CAP_DSHOW is skellycam's current path.
The user has heard reports that MF capture routes are flaky / less reliable than DirectShow, and wants pros/cons. Today is 2026-10-28.
Rules: never open, stream or restart any camera, never run pnputil or device restarts, and do not modify any files. Read-only research.`

const CLAIMS = {
  type: 'object',
  properties: {
    claims: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string', description: 'one specific factual claim' },
          favours: { type: 'string', enum: ['MF', 'DS', 'neutral'] },
          topic: { type: 'string', description: 'short tag e.g. open-latency, frame-server, timestamps, bandwidth, controls, multi-app, deprecation, virtual-cams, mjpeg, stability, enumeration, app-choice' },
          evidence: { type: 'string', description: 'exact quote, number or observation backing it' },
          source: { type: 'string', description: 'URL, or repo-relative file path (with line if possible)' },
          source_date: { type: 'string', description: 'date of the source/report if known, else unknown' },
          windows_version_or_scope: { type: 'string', description: 'Windows version, library version or camera this applies to, if known' },
          strength: { type: 'string', enum: ['measured-locally', 'official-doc', 'maintainer-statement', 'bug-report', 'anecdote', 'inferred'] },
        },
        required: ['claim', 'favours', 'topic', 'evidence', 'source', 'strength'],
      },
    },
    gaps: { type: 'array', items: { type: 'string' }, description: 'things searched for but not found, or open questions' },
  },
  required: ['claims', 'gaps'],
}

const VERDICTS = {
  type: 'object',
  properties: {
    verified: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          claim: { type: 'string' },
          verdict: { type: 'string', enum: ['confirmed', 'weakened', 'refuted', 'unverifiable'] },
          corrected_claim: { type: 'string', description: 'the claim restated so that it is exactly what the source supports' },
          favours: { type: 'string', enum: ['MF', 'DS', 'neutral'] },
          topic: { type: 'string' },
          source: { type: 'string' },
          source_date: { type: 'string' },
          strength: { type: 'string' },
          note: { type: 'string', description: 'why weakened/refuted, staleness (e.g. fixed in a later version), or scope limits' },
        },
        required: ['claim', 'verdict', 'corrected_claim', 'favours', 'topic', 'source', 'note'],
      },
    },
    missed: { type: 'array', items: { type: 'string' }, description: 'important counter-evidence or angles the gatherer missed, with sources' },
  },
  required: ['verified', 'missed'],
}

const WEB_NOTE = `Use WebSearch and WebFetch (load them with ToolSearch query "select:WebSearch,WebFetch" if they are not already available). Prefer primary sources: GitHub issues/PRs/commit messages, Chromium bug tracker and source comments, Microsoft Learn docs, maintainer statements. Fetch pages to get exact quotes; do not cite a page you have not read. Record dates and versions, because many MF complaints are from Windows 7/8/early Win10 and may be fixed.`

const GATHERERS = [
  {
    key: 'local',
    prompt: `${CONTEXT}

Task: sweep the LOCAL evidence for every observation that bears on MF vs DirectShow reliability, behaviour or capability. Sources:
- research/usb_cameras/REPORT.md, PROGRESS.md, mjpeg/RESULTS.md, prior_art/SURVEY.md, timing/VERIFY_method.md, results/windows/Gerald/RERUN_20261027.md, docs/*.md, and results/agent_reports/ (grep for MSMF, Media Foundation, Frame Server, DirectShow, DSHOW, dshow, 0x8007, 0x800718CF, E_INVALIDARG, ReadSample, open time, exposure, timestamp).
- The MF and DS tools: mjpeg/msmf/mf_mjpeg_capture.cpp, timing/src/*.cpp (dshow_open_probe.cpp, mf_uvc_timing.cpp, kiyo_ks_mf_probe.cpp), prior_art/pyav_dshow_probe.py.
- The skellycam app code on branch development (use git show development:<path>; e.g. skellycam/core/camera/determine_backend.py and opencv helpers) and git log for any commit messages mentioning MSMF/DSHOW problems or backend choices.
Include things like: open latency per API, how bandwidth refusal surfaces on each API (error at open vs at ReadSample), timestamp quality per API, control setting reliability (exposure applied or not) per API, Frame Server effects, camera faults that hit all APIs, enumeration side effects, any crash/hang/stall seen on either path, multi-camera behaviour. Distinguish OpenCV's MSMF backend from raw IMFSourceReader, since OpenCV's MSMF wrapper problems are not MF problems. Cite file paths (and lines) for every claim; strength = measured-locally where a result file backs it.`,
  },
  {
    key: 'web-mf-flaky',
    prompt: `${CONTEXT}

Task: find and characterise the actual reports that Media Foundation camera capture is flaky or less reliable than DirectShow. ${WEB_NOTE}
Cover at least: OpenCV CAP_MSMF issues (slow open of 10-40 s, OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS, frame rate / format negotiation, MJPEG handling, property setting) and whether they are OpenCV-wrapper bugs or MF itself; Chromium/Chrome's move from DirectShow to MF video capture on Windows (which version, any rollbacks, blocklists, fallback-to-DirectShow logic, known bugs with specific cameras; look in chromium source media/capture/video/win/ comments and crbug); Windows Camera Frame Server problems (service crashes, the 2016 Anniversary Update MJPEG/H.264 breakage, latency, camera sharing, 'camera in use' errors); IMFSourceReader errors like MF_E_HW_MFT_FAILED_START_STREAMING, MF_E_VIDEO_RECORDING_DEVICE_INVALIDATED, 0xC00D3704, 0x800718CF bandwidth, device-lost handling; MF with multiple USB cameras at once. For each report record what exactly failed, on which Windows build, whether it was MF itself, a wrapper, a driver or a specific camera, and whether it was later fixed.`,
  },
  {
    key: 'web-ds-downsides',
    prompt: `${CONTEXT}

Task: find the evidence on DirectShow's downsides and its future, so the comparison is two-sided. ${WEB_NOTE}
Cover at least: Microsoft's official status of DirectShow (legacy/superseded wording on Microsoft Learn, recommendation to use MF), whether new Windows 11 camera features (Windows Studio Effects, camera sharing between apps, the Settings > Camera controls, Frame Server, network/IP cameras, 'Windows camera' virtual cameras via MFCreateVirtualCamera) are visible or not to DirectShow apps, and how DirectShow reaches cameras on Windows 10/11 (does DS capture go through the Frame Server via a bridge on recent builds? find Microsoft docs on 'DirectShow bridge' / KS proxy / 'MFT0' and camera sharing); DirectShow capture problems (sample timestamps synthesized or wrong, frame drops, slow or flaky filter graph building, MJPEG Decompressor insertion, crossbar/format negotiation issues, ARM64 support, devices that only expose MF formats such as some IR/depth/Surface cameras); multi-camera USB bandwidth behaviour on DS. Record dates and Windows versions.`,
  },
  {
    key: 'web-app-choices',
    prompt: `${CONTEXT}

Task: establish which Windows camera API major, well-maintained capture software actually uses, and why, with primary sources. ${WEB_NOTE}
Cover at least: Chromium/Chrome/Edge (MF vs DS selection logic, feature flags like MediaFoundationVideoCapture, fallback conditions, any per-camera blocklists, and the reasons stated in commits); Firefox (libwebrtc DirectShow capture module, any MF work); OBS Studio (libdshowcapture, any MF source, why); FFmpeg (only dshow and vfwcap inputs? any MF capture input proposed/rejected); GStreamer (mfvideosrc vs ksvideosrc vs dshowvideosrc, which is the default/recommended, maintainers' reasons, e.g. Seungha Yang's notes); OpenCV (default backend priority order on Windows across 4.x versions and why MSMF was demoted or promoted); libwebrtc's video_capture module on Windows; Zoom/Teams if any public info; machine-vision/mocap tools (e.g. librealsense uses MF + UVC metadata; Pupil Labs; any that switched away from MF due to flakiness). For each, state the API, the version/date, and the stated reason.`,
  },
]

const verifyPrompt = (g, report) => `${CONTEXT}

You are an adversarial verifier. Below is a report from another agent ("${g.key}") listing claims about Media Foundation vs DirectShow camera capture. For EVERY claim, try to refute it: re-open the cited source (fetch the URL with WebFetch, loading it via ToolSearch "select:WebSearch,WebFetch" if needed; or read the cited local file/line) and check that the source really says it, that the numbers match, that the scope is right (e.g. an OpenCV-wrapper bug being presented as an MF bug, a Windows 7-era problem presented as current, one camera generalised to all), and whether it was later fixed. Default to 'weakened' when the source only partly supports it and 'unverifiable' when you cannot reach the source. Restate each claim in corrected_claim so it says exactly what the evidence supports. Then list in 'missed' any important evidence on the other side that the report left out (search for it briefly), with sources.

REPORT:
${JSON.stringify(report, null, 1)}`

phase('Gather')
const results = await pipeline(
  GATHERERS,
  g => agent(g.prompt, { label: `gather:${g.key}`, phase: 'Gather', schema: CLAIMS }),
  (report, g) => report
    ? agent(verifyPrompt(g, report), { label: `verify:${g.key}`, phase: 'Verify', schema: VERDICTS })
        .then(v => ({ key: g.key, gaps: report.gaps, raw_count: report.claims.length, ...(v || { verified: [], missed: ['verifier failed'] }) }))
    : { key: g.key, error: 'gatherer failed' },
)
return results
