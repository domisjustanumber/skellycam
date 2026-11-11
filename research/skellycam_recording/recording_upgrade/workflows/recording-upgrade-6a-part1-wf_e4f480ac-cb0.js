export const meta = {
  name: 'recording-upgrade-6a-part1',
  description: 'Recording upgrade study 6A part 1: Jellyfin-guided HW accel sources + PyAV 19 functional tests, jellyfin-ffmpeg options, chromium_codecs NOTES, revise licensing/uncompressed_intra',
  phases: [
    { title: 'Daytime functional + sources', detail: '7 agents, no timing numbers' },
  ],
}

const ROOT = 'C:/Users/Dom/GitHub/freemocap/skellycam'
const STUDY = 'research/skellycam_recording/recording_upgrade'
const RAWD = 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109'
const SCR = 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad'
const OLD_E45 = 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe'

const GOALS = `User goals for the recording upgrade (G1-G9):
G1 Store USB camera JPEGs without transcoding (raw JPEG bytes arrive; extraction is done elsewhere).
G2 Resumable, crash-tolerant files: a crashed session's recording still plays.
G3 Overlays as a separate layer or vector files instead of burned in.
G4 Other uncompressed camera formats (Bayer RAW, NV12, others) recorded I-frame-only, compressed or uncompressed.
G5 A wrapper optimized for recording throughput (folder of JPEGs vs one MP4/MKV), or proof it doesn't matter enough to give up compatibility.
G6 GPU-accelerated encode on as many platforms as possible.
G7 Royalty-free codecs where possible (avoid H.264/H.265).
G8 Native playback in the Chromium (Electron) UI.
G9 Easy synchronized, frame-accurate playback and scrubbing in the Electron UI.
HARDWARE TARGET (user requirement): a format whose ENCODE is hardware-accelerated on NVIDIA RTX 3000-series and newer, and supported on most CPUs from 2020 onwards (Intel, AMD, Apple, including CPUs with no iGPU). Use Jellyfin's hardware acceleration docs as the guide (https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/ and its /intel, /nvidia, /amd, /apple, /rockchip, /known-issues sub-pages) and check Jellyfin's per-generation claims against vendor primary sources before relying on them.`

const CTX = `You are one agent in a research study for skellycam. Repo root ${ROOT} (branch dom/research), Windows 11 machine "Gerald". The study handoff is ${STUDY}/HANDOFF.md - read sections 1, 3, 4 and 5 first (requirements there override anything else).

${GOALS}

EVIDENCE RULE (hardest requirement): no assertion without hard evidence or a test result. Label every claim: measured (a result file - cite its path), source (primary source: vendor docs, spec, licence text, library source at a pinned tag - URL, exact short quote, accessed 2026-11-09), code (file:line), inferred (kept to a minimum, clearly marked). No numbers from memory. Blogs/forums/StackOverflow are leads only. If something cannot be verified write NOT VERIFIED. Load WebFetch/WebSearch via ToolSearch when you need the web.

TESTS USE PyAV 19.0.2 ONLY (its bundled FFmpeg): uv run --script with a PEP 723 header "# dependencies = [\\"av==19.0.2\\", \\"numpy\\"]" (add other exact pins if needed). Do NOT test with PyAV 18 / the skellycam venv (results from it are background only). The ffmpeg/ffprobe 9.0.2 CLI on PATH may be used only to INSPECT files. Never modify the skellycam venv, skellycam-ui, or the freemocap repo.

MACHINE: i7-14700K (Raptor Lake-S); Intel UHD Graphics 770 iGPU is NOW PRESENT (Get-PnpDevice showed Status OK, Present True at 16:36 today, after being phantom earlier - earlier QSV failures in results/gpu_encode were caused by its absence). RTX 3070 (Ampere), driver 610.88. Parsec/Sunshine installed (may use NVENC): record nvidia-smi --query-gpu=encoder.stats.sessionCount,utilization.gpu --format=csv around GPU tests. No BIOS, driver, registry, Defender or system-setting changes. Do not open any camera.
Electron 35.7.5: ${ROOT}/skellycam-ui/node_modules/electron/dist/electron.exe. Electron 45.2.3: ${OLD_E45} (if missing, npm install electron@45.2.3 into ${SCR}/shared/electron-latest then node node_modules/electron/install.js). Unset ELECTRON_RUN_AS_NODE before launching Electron. Chrome 156: C:/Program Files/Google/Chrome/Application/chrome.exe.
INPUT FRAMES: corpus ${RAWD}/corpus/ (read index.json). Real camera MJPEG sets (4:2:2 baseline with DHT) and two real YUY2 1080p sets.

TIMING RULE: other agents run concurrently right now. Do NOT report timing/throughput/CPU numbers. Functional tests only. Timed benchmarks run tonight from 23:00, one at a time.
PATHS: scripts in ${STUDY}/scripts/<topic>/, text results in ${STUDY}/results/<topic>/, media ONLY under ${RAWD}/<topic>/ (it shows the room), temp/envs in ${SCR}/<topic>/. Do not git commit. Never use SendMessage. Research stays local Markdown - never Claude Docs.
WRITE GUARD: a harness guard blocks subagent writes to files named FINDINGS.md. Never write FINDINGS.md and never work around the guard; when asked for FINDINGS, return the full text in your structured output. NOTES.md and other files are fine.
STYLE: plain, concise Markdown; tables for comparisons; one claim per bullet with its label and citation. Keep scope tight; aim to finish in about an hour.`

const MANIFEST_SCHEMA = {
  type: 'object',
  properties: {
    summary: { type: 'string', description: '10-25 line summary of what was established, with labels' },
    notes_path: { type: 'string' },
    bench_manifest: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, purpose: { type: 'string' },
      command: { type: 'string', description: 'complete command from repo root, PyAV 19.0.2 via uv run --script; writes JSON into results/<topic>/bench/' },
      est_minutes: { type: 'number' }, priority: { type: 'integer' }, smoke_tested: { type: 'boolean' } },
      required: ['id', 'purpose', 'command', 'est_minutes', 'priority', 'smoke_tested'] } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['summary', 'notes_path', 'bench_manifest', 'open_questions'],
}
const NOTES_SCHEMA = {
  type: 'object',
  properties: { summary: { type: 'string' }, notes_path: { type: 'string' }, open_questions: { type: 'array', items: { type: 'string' } } },
  required: ['summary', 'notes_path', 'open_questions'],
}
const REVISE_SCHEMA = {
  type: 'object',
  properties: {
    findings_md: { type: 'string', description: 'the COMPLETE revised FINDINGS.md text, ready to save as-is' },
    summary: { type: 'string', description: '10-line summary of the final state and what changed' },
  },
  required: ['findings_md', 'summary'],
}

const MATRIX_SPEC = `Build a per-generation matrix of hardware ENCODE and DECODE support for H.264, HEVC, AV1, VP9, MJPEG/JPEG and (where relevant) FFV1 via Vulkan compute. For each cell: Y / N / partial (with constraint: profile, bit depth, chroma 4:2:0/4:2:2/4:4:4, max res), the Jellyfin claim (quote + URL) and the vendor primary source (quote + URL), and mark AGREE / DISAGREE / vendor-only / Jellyfin-only. Note 4:2:2 specifically (cameras emit 4:2:2 MJPEG) and session/stream limits. Also record which FFmpeg API exposes each path (nvenc/cuvid, qsv, vaapi, amf, videotoolbox, d3d12va, mediafoundation, vulkan) per OS.`

const TASKS = [
  { key: 'hw_src_nvidia_intel', label: 'hw_accel_target:sources-nvidia-intel', schema: NOTES_SCHEMA, prompt: `TOPIC hw_accel_target (new topic), part: SOURCES for NVIDIA and Intel.
Read first: ${STUDY}/results/gpu_encode/NOTES.md (sections 1 and 7 already establish: RTX 3070 has no AV1 hw encode; NVENC H.264/HEVC works incl. all-intra; NVENC session limit 12 on driver 610.88; NVDEC can't decode the cameras' 4:2:2 MJPEG but nvJPEG can; PyAV wheels have no Vulkan encoders; Intel media-driver lists VP9 and JPEG encode for Tiger Lake..Raptor Lake) - cite it, don't redo it.
Jellyfin pages: main hardware-acceleration page, /nvidia, /intel, /known-issues.
Vendor primary sources: NVIDIA Video Encode and Decode GPU Support Matrix (developer.nvidia.com) and Video Codec SDK docs/NVENC application note (session limits, 4:2:2 support on Blackwell); Intel media-driver README / supported features table (github.com/intel/media-driver), Intel VPL / oneVPL docs, Intel ark or product briefs, Intel Arc docs.
Generations: NVIDIA Turing, Ampere (RTX 3000), Ada, Blackwell. Intel iGPUs 2020+: Tiger Lake, Rocket Lake, Alder Lake, Raptor Lake, Meteor Lake, Lunar Lake, Arrow Lake; Intel Arc (Alchemist, Battlemage). ALSO: which Intel desktop CPUs from 2020+ have NO iGPU (F / KF SKUs) - cite Intel ark for a representative set and note the share is NOT VERIFIED unless a primary source gives it.
${MATRIX_SPEC}
Write ${STUDY}/results/hw_accel_target/NOTES_sources_nvidia_intel.md. Return the structured summary.` },
  { key: 'hw_src_amd_apple_cpu', label: 'hw_accel_target:sources-amd-apple-cpu', schema: NOTES_SCHEMA, prompt: `TOPIC hw_accel_target (new topic), part: SOURCES for AMD, Apple, Rockchip (brief) and CPUs without an iGPU.
Read first: ${STUDY}/results/gpu_encode/NOTES.md (cite, don't redo).
Jellyfin pages: main hardware-acceleration page, /amd, /apple, /rockchip, /known-issues.
Vendor primary sources: AMD AMF docs / AMF GitHub wiki (codec support per VCN version), AMD product pages for VCN version per APU/GPU, Mesa/RadeonSI VAAPI feature docs if needed; Apple VideoToolbox / developer docs and Apple product tech specs (which M-series encode HEVC/H.264/ProRes/AV1 in hardware; AV1 decode on M3+); FFmpeg source at tag n8.0 or the version PyAV 19.0.2 bundles (check libavcodec for *_videotoolbox encoders: is there av1/vp9 videotoolbox encode? cite file paths at the tag).
Generations: AMD APUs 2020+ (Zen 2 Renoir/Lucienne, Zen 3 Cezanne/Barcelo/Rembrandt, Zen 4 Phoenix/Hawk Point, Zen 5 Strix Point, Zen 4/5 desktop Raphael/Granite Ridge with the small RDNA2 iGPU), AMD GPUs RDNA1/2/3/4; Apple M1, M2, M3, M4.
CPUs WITH NO iGPU (2020+): AMD desktop Ryzen 3000/5000 non-G (Zen 2/3) and Intel F/KF - here encode falls to CPU software. Gather primary-source evidence (or cite existing measured files in ${STUDY}/results/uncompressed_intra/ and gpu_encode/ and research/frame_ring_buffer/prototypes/results/) on software encode options per candidate format: libsvtav1, libaom, libvpx-vp9, libopenh264, mjpeg (FFmpeg native / libjpeg-turbo), FFV1. Do NOT benchmark now; list what tonight's benches should measure.
${MATRIX_SPEC}
Write ${STUDY}/results/hw_accel_target/NOTES_sources_amd_apple_cpu.md. Return the structured summary.` },
  { key: 'hw_functional', label: 'hw_accel_target:functional-gerald', schema: MANIFEST_SCHEMA, prompt: `TOPIC hw_accel_target (new topic), part: FUNCTIONAL TESTS on Gerald through PyAV 19.0.2, now that the Intel UHD 770 is present.
First re-check read-only: Get-PnpDevice -Class Display | ft Status,Present,FriendlyName (save output to ${STUDY}/results/hw_accel_target/system_probe_1700.txt along with nvidia-smi -q -d ENCODER_STATS summary and Intel driver version from Get-CimInstance Win32_VideoController).
Reuse/adapt existing scripts in ${STUDY}/scripts/gpu_encode/ (pyav_functional.py, ff_functional.py, bench_pyav_concurrent.py, benchlib.py, common.py) - copy into ${STUDY}/scripts/hw_accel_target/ and adapt; don't edit gpu_encode's files.
Functional matrix via PyAV 19.0.2: encoders h264_qsv, hevc_qsv, av1_qsv, vp9_qsv, mjpeg_qsv; h264/hevc/av1_nvenc; h264/hevc/av1_d3d12va (if in the wheel); h264/hevc/av1_mf (Media Foundation - note which hardware MFT it picks if detectable); h264/hevc/av1_amf (expected to fail - record exact error). Inputs: NV12 and YUY2 derived from the real YUY2 1080p corpus frames, plus decoded MJPEG frames at 720p and 1080p (4:2:2 -> what conversion is needed). For each encoder that opens: (a) all-intra (gop_size=1 / forced keyframes; verify every frame is a keyframe with ffprobe -show_frames pict_type/key_frame), (b) short GOP (g=30); (c) does it accept 4:2:2 input natively or does it require 4:2:0/NV12 (record pix_fmt negotiation and errors); (d) decode-back check with PyAV software decoder (frames count, PSNR vs input - PSNR is a quality number, not timing, so it is fine); (e) container: write to MKV and MP4 (and WebM for vp9/av1), check ffprobe.
Hardware DECODE via PyAV 19 where relevant: mjpeg_qsv / hwaccel qsv for the cameras' 4:2:2 MJPEG (does QSV decode 4:2:2 JPEG?), mjpeg_cuvid, d3d11va/d3d12va hwaccel for mjpeg, av1/vp9/hevc decode via qsv/cuvid.
Record nvidia-smi encoder sessions around NVENC tests. Results: ${STUDY}/results/hw_accel_target/functional_pyav19.json + functional_pyav19.md.
Then WRITE BENCH SCRIPTS for tonight (do NOT run them for timing - smoke-test each with a tiny run, e.g. 10 frames, and discard any numbers): per-stream encode fps and CPU cost (process CPU time / frame) for each working QSV and NVENC encoder (and MF if it works, and the CPU software baselines libsvtav1 / libvpx-vp9 / mjpeg / ffv1 for the same inputs), at 720p and 1080p, from NV12, from YUY2 and from MJPEG (decode included, CPU decode vs hw decode where available); concurrent-stream scaling 1 -> 4 -> 8 -> 16 streams (QSV and NVENC separately; record the actual session limit hit). Each bench must record background load before it starts (10 s typeperf "\\Processor(_Total)\\% Processor Time", top processes, nvidia-smi encoder sessions) and write JSON into ${STUDY}/results/hw_accel_target/bench/. Give realistic est_minutes; mark priority 1 for the items decisive for the hardware target. Write ${STUDY}/results/hw_accel_target/NOTES_functional.md (everything, with commands). Return the structured summary with the bench_manifest.` },
  { key: 'jellyfin_ffmpeg', label: 'jellyfin_ffmpeg:sources', schema: NOTES_SCHEMA, prompt: `TOPIC jellyfin_ffmpeg (sources only - requirement 4 in HANDOFF section 1). DO NOT download, install or test jellyfin-ffmpeg.
From primary sources only - https://github.com/jellyfin/jellyfin-ffmpeg (README, debian/patches or the patch series, build scripts, LICENSE/COPYING, release notes / GitHub releases of the current release), Jellyfin hardware-acceleration docs where they say why jellyfin-ffmpeg is required - document: which upstream FFmpeg version the current release is based on; its patch list grouped by area (QSV, VAAPI, NVENC/CUDA, AMF, VideoToolbox, Vulkan, RKMPP, tonemapping/filters, other); extra hardware paths or fixes not in upstream FFmpeg (quote the patch names/commit messages); bundled/enabled external libraries and the resulting licence (GPL vs LGPL); supported platforms and distribution format (deb, portable builds, Windows builds?, macOS?). Check whether PyAV can be built against or bound to jellyfin-ffmpeg (PyAV docs on building with a custom FFmpeg - cite) and whether any public PyAV binding/wheel exists (if none found, say NOT FOUND with where you looked).
Then a draft pros/cons table: standard FFmpeg (via PyAV 19.0.2 wheels - cite results/licensing for what the wheel bundles) vs jellyfin-ffmpeg, rows: hardware paths, QSV/NVENC/VAAPI fixes, Python integration (PyAV in-process vs subprocess pipe - costs: process management, pipe copies, error handling, per-frame PTS passing), distribution (wheel size, separate binary per OS), licensing (GPL implications for distributing skellycam), update cadence, Windows/macOS support. Every cell labelled. Write ${STUDY}/results/jellyfin_ffmpeg/NOTES.md. Return the structured summary.` },
  { key: 'chromium_codecs_notes', label: 'chromium_codecs:notes', schema: NOTES_SCHEMA, prompt: `TOPIC chromium_codecs (G8). The investigator was cut off mid-run without writing NOTES.md. Files: ${STUDY}/results/chromium_codecs/tables.md (full play/seek matrix for Electron 35.7.5 and 45.2.3), raw/, make_clips_log.json, jpeg_warnings_generic_1080p.txt; scripts in ${STUDY}/scripts/chromium_codecs/. Read the raw files (don't trust tables.md blindly - spot-check at least 10 cells against raw/ and note the check).
Write ${STUDY}/results/chromium_codecs/NOTES.md: method (how clips were made, what each probe does: canPlayType, MediaSource.isTypeSupported, MediaCapabilities, WebCodecs isConfigSupported, ImageDecoder, actual play with decoded-pixel index check), the full support matrix (codec x container x Electron version), hardware decode where detected, serving (file:// vs protocol.handle + Range) if tested, limits and gaps. Add the Chrome 156 column ONLY if the existing harness can run against Chrome cheaply (under ~15 minutes of work, e.g. serve the same page over a local http server and drive Chrome headless with --remote-debugging or the same page with automatic result upload); otherwise list it under gaps. If you run it, save raw output under results/chromium_codecs/raw/chrome156/. Return the structured summary.` },
  { key: 'revise_licensing', label: 'revise:licensing', schema: REVISE_SCHEMA, prompt: `Revise ${STUDY}/results/licensing/FINDINGS.md using the verifier reports ${STUDY}/results/licensing/VERIFY_provenance.md and VERIFY_method.md (the revise step never ran in the first workflow). Note VERIFY_method refutes a NOTES claim about CAP_MSMF FourCC handling. Check each refutation yourself against the evidence before applying it (verifiers can be wrong). Correct or remove refuted claims, relabel weak ones; claims resting on PyAV 18.0.0 are background only - say so and keep PyAV 19.0.2 evidence primary. Add a final 'Verification' section: what was challenged, what changed, what remains NOT VERIFIED. Quick functional checks (< 1 min CPU, no timing) allowed. Return the COMPLETE revised FINDINGS.md text in findings_md (do not write it to disk) and a 10-line summary.` },
  { key: 'revise_uncompressed_intra', label: 'revise:uncompressed_intra', schema: REVISE_SCHEMA, prompt: `Revise ${STUDY}/results/uncompressed_intra/FINDINGS.md using ${STUDY}/results/uncompressed_intra/VERIFY_provenance.md and VERIFY_method.md (the revise step never ran). Check each refutation yourself before applying it. Rules for this revision: (1) PyAV 19.0.2 only: functional claims must rest on the pyav 19.0.2 result files; PyAV 18.0.0 results become background and are labelled as such. (2) The bench in results/uncompressed_intra/bench/ was CONTAMINATED (CPU ~50% busy from other agents): keep its numbers only as lower bounds, clearly flagged, and note they will be replaced by tonight's quiet re-run (23:00). (3) Add a final 'Verification' section. Quick functional checks (< 1 min CPU, no timing) allowed. Return the COMPLETE revised FINDINGS.md text in findings_md (do not write it to disk) and a 10-line summary.` },
]

phase('Daytime functional + sources')
const res = await parallel(TASKS.map(t => () => agent(`${CTX}\n\n${t.prompt}`, { label: t.label, phase: 'Daytime functional + sources', schema: t.schema })))

const out = {}
TASKS.forEach((t, i) => {
  const r = res[i]
  if (!r) { out[t.key] = 'FAILED'; return }
  out[t.key] = { summary: r.summary, notes_path: r.notes_path, open_questions: r.open_questions, bench_manifest: r.bench_manifest, findings_chars: r.findings_md ? r.findings_md.length : undefined }
})
return out
