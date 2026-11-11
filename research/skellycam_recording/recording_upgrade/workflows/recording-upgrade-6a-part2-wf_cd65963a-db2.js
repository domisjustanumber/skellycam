export const meta = {
  name: 'recording-upgrade-6a-part2',
  description: 'Recording upgrade 6A part 2: matched-quality JPEG vs H.264/HEVC intra sweep, Chromium intra playback check, 23:00 queue + runner, FINDINGS/verify/revise for hw_accel_target, jellyfin_ffmpeg, chromium_codecs',
  phases: [
    { title: 'Functional', detail: 'quality sweep + Chromium intra check (no timing)' },
    { title: 'Queue', detail: 'runner + BENCH_QUEUE_2300.md, smoke-tested' },
    { title: 'Findings', detail: 'draft -> verify -> revise for 3 topics' },
  ],
}

const ROOT = 'C:/Users/Dom/GitHub/freemocap/skellycam'
const STUDY = 'research/skellycam_recording/recording_upgrade'
const RAWD = 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109'
const SCR = 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad'
const OLD_E45 = 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe'

const CTX = `You are one agent in a research study for skellycam. Repo root ${ROOT} (branch dom/research), Windows 11 machine "Gerald". The study handoff is ${STUDY}/HANDOFF.md - read section 1 (requirements 1-11, including the decisions Dom added today at 17:20 and 17:35 - they override everything), 3, 4 and 5.
KEY DECISIONS: the hardware target applies to the RECORDING format; only INTRA-ONLY formats are in scope (no GOP variants); GPU-compute JPEG encode (nvJPEG on CUDA) counts as hardware-accelerated; H.264 intra and HEVC intra are tested head to head against JPEG at MATCHED QUALITY.
STATE SINCE THE HANDOFF: the Intel UHD 770 is present (QSV works). New today: ${STUDY}/results/hw_accel_target/ (NOTES_sources_nvidia_intel.md, NOTES_sources_amd_apple_cpu.md, NOTES_functional.md, functional_pyav19.md, sw_encoders_pyav19_win_amd64.json, wheel_hw_pixfmts_19.0.2.json; bench scripts scripts/hw_accel_target/bench_encode_stream.py and bench_concurrent.py, smoke-tested), ${STUDY}/results/jellyfin_ffmpeg/NOTES.md, ${STUDY}/results/chromium_codecs/NOTES.md (+ regenerated tables.md, Chrome 156 column). FINDINGS.md files now exist for most topics (some still being revised by another workflow).
Functional facts already measured today (cite the files): h264/hevc/vp9/mjpeg_qsv encode from software frames; mjpeg_qsv and hevc_qsv accept yuyv422; QSV HWAccel frames-context mode fails; mjpeg_qsv decodes the cameras' 4:2:2 MJPEG; NVDEC can't; no AV1 hw encode works; MF picks the NVIDIA MFT; d3d12va works (MP4 yes, MKV no). Pitfalls handled in the bench scripts: decoded MJPEG frames carry pict_type=I (reset to NONE), reformat to nv12 keeps full range unless dst_color_range=1. Chromium: MJPEG never plays in <video>; camera JPEGs decode via ImageDecoder/createImageBitmap; libx264/libx265 clips with B-frames had seek/frame-index errors.

EVIDENCE RULE: no assertion without a result file, primary source (URL + quote, accessed 2026-11-09), or code file:line; inferred claims minimal and marked; NOT VERIFIED otherwise. No numbers from memory.
VERSIONS: implementation under test is PyAV 19.0.2: uv run --script with PEP 723 "# dependencies = [\\"av==19.0.2\\", \\"numpy\\", ...exact pins]". PyAV 18 / skellycam venv results are background only and must not be used for new tests. ffmpeg/ffprobe CLI only to inspect. Never modify the skellycam venv, skellycam-ui or the freemocap repo. Electron 35.7.5: ${ROOT}/skellycam-ui/node_modules/electron/dist/electron.exe; Electron 45.2.3: ${OLD_E45}; unset ELECTRON_RUN_AS_NODE. Record nvidia-smi encoder sessions around GPU work (Parsec/Sunshine may hold sessions).
TIMING RULE NOW: other agents run concurrently; do NOT report timing numbers. Size, quality (PSNR/SSIM), correctness, seek exactness are fine.
PATHS: scripts ${STUDY}/scripts/<topic>/, text results ${STUDY}/results/<topic>/, media ONLY under ${RAWD}/<topic>/, temp ${SCR}/<topic>/. No git commit. Never SendMessage. Local Markdown only, never Claude Docs. No camera, BIOS, driver, registry, Defender or system-setting changes.
WRITE GUARD: never write a file named FINDINGS.md and never work around that guard; return FINDINGS text in structured output.
STYLE: plain, concise Markdown; tables; one labelled claim per bullet.`

const NOTES_SCHEMA = { type: 'object', properties: { summary: { type: 'string' }, notes_path: { type: 'string' }, open_questions: { type: 'array', items: { type: 'string' } } }, required: ['summary', 'notes_path', 'open_questions'] }
const FINDINGS_SCHEMA = { type: 'object', properties: { findings_md: { type: 'string', description: 'the COMPLETE FINDINGS.md text' }, summary: { type: 'string' } }, required: ['findings_md', 'summary'] }
const VERIFY_SCHEMA = { type: 'object', properties: {
  refuted: { type: 'array', items: { type: 'object', properties: { claim: { type: 'string' }, why: { type: 'string' }, correction: { type: 'string' } }, required: ['claim', 'why', 'correction'] } },
  weak: { type: 'array', items: { type: 'object', properties: { claim: { type: 'string' }, why: { type: 'string' }, fix: { type: 'string' } }, required: ['claim', 'why', 'fix'] } },
  verdict: { type: 'string' } }, required: ['refuted', 'weak', 'verdict'] }
const QUEUE_SCHEMA = { type: 'object', properties: {
  summary: { type: 'string' }, queue_path: { type: 'string' }, runner_command: { type: 'string', description: 'exact command the 23:00 session runs (in background) from repo root' },
  total_minutes: { type: 'number' }, items: { type: 'array', items: { type: 'object', properties: { order: { type: 'integer' }, id: { type: 'string' }, topic: { type: 'string' }, est_minutes: { type: 'number' }, timeout_minutes: { type: 'number' }, smoke_ok: { type: 'boolean' } }, required: ['order', 'id', 'topic', 'est_minutes', 'timeout_minutes', 'smoke_ok'] } },
  dropped: { type: 'array', items: { type: 'string' } } }, required: ['summary', 'queue_path', 'runner_command', 'total_minutes', 'items', 'dropped'] }

const QUALITY = `TOPIC intra_compare (new; results in ${STUDY}/results/intra_compare/, scripts in ${STUDY}/scripts/intra_compare/, media in ${RAWD}/intra_compare/). FUNCTIONAL quality-matching sweep - no timing.
Inputs (state how each is derived): (1) the two real YUY2 1080p corpus sets (8 frames each) as yuyv422 and converted to nv12 (limited range, dst_color_range handled); (2) decoded camera MJPEG at 720p (c930e_720p_flash and c922_720p_flash, use >= 120 frames each) and 1080p (c922_1080p, c930e_1080p, all 19 frames). For MJPEG-sourced inputs, also report the camera's own JPEG bytes/frame as the passthrough reference (no re-encode).
Encode paths, ALL intra-only (verify every frame is a keyframe): JPEG via libjpeg-turbo on CPU (simplejpeg and/or PyTurboJPEG - encode from YUV planes where possible; record versions), FFmpeg mjpeg (PyAV 19), mjpeg_qsv (PyAV 19), nvJPEG on CUDA (nvidia-nvimgcodec-cu12 - reuse ${STUDY}/scripts/gpu_encode/nvimgcodec_jpeg.py approach; record version); H.264 intra and HEVC intra via h264_nvenc/hevc_nvenc, h264_qsv/hevc_qsv (PyAV 19), and any CPU H.264/HEVC encoder present in the PyAV 19.0.2 wheel (check av.codecs_available for libx264/libx265/libopenh264 - results/hw_accel_target says libopenh264 is absent; check whether libx264/libx265 are present and note results/licensing on their GPL status). Also chroma: 4:2:2 where the encoder supports it (mjpeg, mjpeg_qsv, hevc_qsv yuyv422, nvJPEG 4:2:2 if supported) vs 4:2:0.
For each path sweep the quality knob (JPEG quality ~50..95; NVENC constqp / cq QP ~15..35; QSV global_quality / CQP ~15..35; CPU crf/qp) at 5-7 points; for each point record bytes/frame and PSNR-Y, PSNR-YUV and SSIM (Y) against the pre-encode source frame (compute with numpy/skimage-free code or a pinned scikit-image; for MJPEG-sourced inputs, the source is the decoded camera frame - note that this measures generation loss on top of the camera's JPEG). Produce rate-quality curves per path and input (JSON + a Markdown table; optional SVG/PNG plots under results).
Then choose MATCHED SETTINGS for tonight's timed bench: for each path, the knob value that gives (a) SSIM-Y closest to a common target (pick the target as the quality the camera's own JPEGs reach vs a fair reference, or e.g. SSIM-Y 0.98 / PSNR-Y 40 dB - justify the choice in the notes) and (b) one 'high quality' point (e.g. PSNR-Y 45 dB). Write ${STUDY}/results/intra_compare/matched_settings.json in a simple machine-readable form {path: {input_class: {knob, value, bytes_per_frame, psnr_y, ssim_y}}} that bench scripts can read.
Also verify decode-back: each output decodes in PyAV 19 software decode with the right frame count; for H.264/HEVC, check stream has no B-frames (has_b_frames=0) and every frame is IDR/I.
Write ${STUDY}/results/intra_compare/NOTES.md. Return the structured summary.`

const CHROME = `TOPIC intra_playback (new; results ${STUDY}/results/intra_playback/, scripts ${STUDY}/scripts/intra_playback/, media ${RAWD}/intra_playback/). FUNCTIONAL - no timing.
Question: can intra-only H.264 and HEVC from the hardware encoders be played and scrubbed frame-exactly in Electron 35.7.5 and 45.2.3 (and Chrome 156 if the existing harness makes it cheap), compared with the JPEG-sequence path?
Reuse the harnesses in ${STUDY}/scripts/chromium_codecs/ and ${STUDY}/scripts/chromium_sync_scrub/ (read their NOTES/FINDINGS first: results/chromium_codecs/NOTES.md, results/chromium_sync_scrub/NOTES.md and FINDINGS.md). Make clips with PyAV 19.0.2 from real corpus content plus a per-frame binary index pattern (like the existing clips), 720p30 and 1080p30, >= 300 frames, CFR and VFR (real capture jitter): h264_nvenc intra, hevc_nvenc intra, h264_qsv intra, hevc_qsv intra (no B-frames, every frame IDR/I - verify with ffprobe), in mp4, fragmented mp4 and mkv (webm cannot carry H.264/HEVC); mjpeg_qsv 4:2:2 in mkv (expected not to play - confirm once); and the JPEG-sequence path (MJPEG frames in a raw .mjpeg or MKV + the recorder-style index; fetch frame k by HTTP Range and decode with ImageDecoder / createImageBitmap). Also a JPEG-in-MKV byte-range test: can the UI fetch single JPEG frames out of an MKV by byte offset using an index sidecar (G1 + G9 together; chromium_codecs listed this as untested)?
Tests per clip x browser: plays (decoded index pattern correct for every displayed frame); >= 100 random paused seeks via currentTime=(k+0.5)/fps for <video> and by index for WebCodecs VideoDecoder (H.264/HEVC intra: each chunk is a key frame, so any frame decodes alone - verify) and for JPEG path; % exact; single-frame step forward/back exactness; hardware vs software decoder used (media logs / MediaCapabilities powerEfficient). Note HEVC support differences between E35 and E45.
Then make sure the chromium_sync_scrub bench suite can run tonight's TIMED comparison for intra-only paths at N=4 and 8, 1080p: JPEG-sequence (single master clock) vs H.264 intra and HEVC intra via <video> (requestVideoFrameCallback sync) and via WebCodecs. Extend/configure the suite (new suite names; don't break existing ones) and smoke-test it with a tiny run (discard numbers). Record the exact commands. Write ${STUDY}/results/intra_playback/NOTES.md. Return the structured summary; put tonight's bench commands (complete, smoke-tested, with est minutes) at the end of the summary under a heading 'BENCH COMMANDS'.`

const queuePrompt = (q, c) => `${CTX}

You BUILD TONIGHT'S BENCH QUEUE (HANDOFF section 6A.5 as amended by section 1 items 9-11). Tonight's run starts at 23:00 (triggered in the main session); it must stop by 05:00 but the queue is capped at about 3 h of estimated runtime (more repetitions on decisive items rather than more items).
Inputs: ${STUDY}/results/bench_queue_from_wf_2e122ed0.json (old manifests; all point at the PyAV 18 venv - every Python bench must switch to PyAV 19.0.2 via uv run --script PEP 723 pins; add the headers to the scripts if missing); the hw_accel_target bench manifest in ${STUDY}/results/hw_accel_target/NOTES_functional.md (drop gop30 - intra only); the software bench list SW1-SW6 in results/hw_accel_target/NOTES_sources_amd_apple_cpu.md; the matched-quality sweep just completed (results/intra_compare/NOTES.md + matched_settings.json) - summary: ${q ? q.summary.slice(0, 3000) : 'FAILED - use sensible fixed settings and say so'}; the intra playback work (results/intra_playback/NOTES.md) - summary incl. BENCH COMMANDS: ${c ? c.summary.slice(0, 4000) : 'FAILED - use existing chromium_sync_scrub suites limited to intra-only clips'}.
Priority order for the ~3 h (decisive first):
 1. Head-to-head intra encode at the MATCHED settings: JPEG (libjpeg-turbo CPU, FFmpeg mjpeg, mjpeg_qsv, nvJPEG) vs H.264 intra and HEVC intra (NVENC, QSV, plus CPU libx264/libx265 if present in the wheel), 720p and 1080p, sources NV12, YUY2 (native where supported) and MJPEG (CPU decode and mjpeg_qsv decode); per-stream fps, process CPU ms/frame, GPU/iGPU utilisation if obtainable; 1 warm-up + >= 3 reps.
 2. Stream scaling at 1080p30 intra, paced (30 fps per stream: can N streams keep up, dropped frames, CPU) and unpaced: 1/4/8/16 for h264_nvenc, hevc_nvenc, h264_qsv, hevc_qsv, mjpeg_qsv, nvJPEG, CPU JPEG (one worker per stream); record the session limits hit.
 3. Chromium intra playback/sync/seek timing: JPEG-sequence vs H.264/HEVC intra, N=4/8, 1080p, E35 and E45 (decode cost per frame, seek latency, sync spread).
 4. Passthrough recording costs: jp_mux_cost (PyAV 19), cr_fsync, cr_fragment_overhead (MJPEG payload only).
 5. A reduced write_throughput confirmation (e.g. 16 cameras x 1080p30 MJPEG passthrough: MKV vs raw+index vs folder-of-JPEGs, one model, 3 reps) and a reduced usability check (folder read-back incl. Defender cost) only if time remains.
 6. Intra-only uncompressed_intra items that bear on the target (e.g. mjpeg/ffv1 from NV12/YUY2/Bayer at 1080p), python_integration pi_jpeg_decode_cpu (UI live-view decode cost), overlays cost - only if time remains.
Write a RUNNER ${STUDY}/scripts/bench_runner/run_queue.py (uv run --script, PEP 723 pins incl. psutil) that reads a machine-readable queue file ${STUDY}/results/bench_queue_2300.json and: runs items strictly one at a time; before each item records 10 s typeperf total CPU, top 10 processes, nvidia-smi utilization + encoder sessions, free disk, and flags the item if mean CPU > 15% (waits/re-checks up to 5 min first); enforces a hard per-item timeout (kill the whole process tree); stops starting new items after a deadline (default 05:00 local) and logs skipped items; checks Intel UHD 770 presence once (skip items tagged qsv if absent, log it); records the active power plan (powercfg /getactivescheme) and Defender schedule (Get-MpPreference ScanScheduleDay/ScanScheduleTime/ScanScheduleQuickScanTime, read-only) at start; optionally sets CPU affinity to P-cores where practical (detect via GetLogicalProcessorInformationEx EfficiencyClass or document why not); appends a line per item to ${STUDY}/results/BENCH_RUN_2300_LOG.jsonl (start/end/exit code/flags/load) and writes stdout/stderr per item under ${STUDY}/results/bench_runner/logs/. It must support --smoke (tiny frame counts, every item) and --dry-run. Order the queue so the Defender scheduled scan time (read it now, read-only) falls in a gap or after the run; note it.
SMOKE-TEST every item via the runner's --smoke mode now and fix failures (smoke numbers are meaningless - delete them or keep them out of results/<topic>/bench/). Then write ${STUDY}/results/BENCH_QUEUE_2300.md: ordered table (order, id, topic, purpose, command, est minutes, timeout, smoke result), total, what was dropped vs the old manifests and why, and the runner command. Return the structured result.`

const TOPICS3 = [
  { key: 'hw_accel_target', goals: 'G6, G7 + hardware target', extra: `Merge NOTES_sources_nvidia_intel.md, NOTES_sources_amd_apple_cpu.md, NOTES_functional.md and functional_pyav19.md, and results/intra_compare/NOTES.md if it exists by the time you read it. The core deliverable is the per-generation matrix (NVIDIA Turing/Ampere/Ada/Blackwell; Intel 2020+ iGPUs and Arc; AMD 2020+ APUs and RDNA1-4; Apple M1-M4; CPUs without iGPU) for hardware encode/decode of H.264, HEVC, AV1, VP9, JPEG (incl. nvJPEG CUDA, which Dom counts as hardware-accelerated) and FFV1 via Vulkan, with Jellyfin vs vendor agreement, then the candidates that meet the target (intra-only, recording format), compared with G7, with the trade-off stated plainly.` },
  { key: 'jellyfin_ffmpeg', goals: 'requirement 4 (standard FFmpeg vs jellyfin-ffmpeg)', extra: `From results/jellyfin_ffmpeg/NOTES.md and its evidence files. Must contain the pros/cons table standard FFmpeg (PyAV 19.0.2 wheels) vs jellyfin-ffmpeg, every cell labelled, and what options it could provide for skellycam's recording path (e.g. mjpeg_videotoolbox for macOS hardware JPEG).` },
  { key: 'chromium_codecs', goals: 'G8', extra: `From results/chromium_codecs/NOTES.md, tables.md and raw/ (incl. Chrome 156 and the PyAV 19 clip cross-check), and results/intra_playback/NOTES.md if it exists by the time you read it. Emphasise intra-only formats per Dom's decision; GOP results are background.` },
]

const LENSES = [
  { key: 'provenance', text: `PROVENANCE lens: check every claim's cited evidence exists and says exactly that (open result files and compare numbers; re-open source URLs via WebFetch and check quotes and primacy; open code at file:line). Flag unlabelled claims, inferred-as-fact, numbers from memory, secondary sources, mismatched quotes, PyAV 18 results presented as primary.` },
  { key: 'method', text: `METHODOLOGY lens: confounders and wrong conclusions - functional pass mistaken for compatibility, Linux-only sources applied to Windows, Jellyfin claims not checked against vendors, per-generation generalisation from one SKU, Chromium tests without decoded-pixel checks, intra vs GOP confusion, quality comparisons not at matched quality. Quick functional re-checks (< 1 min CPU, PyAV 19.0.2, no timing) allowed.` },
]

const findingsChain = (t) => agent(`${CTX}

Write the FINDINGS for topic ${t.key} (${t.goals}). ${t.extra}
Read the raw files; don't trust summaries. Structure: 1) Question(s) answered, 2) Findings (each bullet labelled + cited), 3) Comparison table(s), 4) Implications for the plan (tied to findings), 5) Pending tonight's bench, 6) Not tested / limits / NOT VERIFIED, 7) How to reproduce. Return the COMPLETE text in findings_md (do not write FINDINGS.md) and a 15-line summary.`, { label: `findings:${t.key}`, phase: 'Findings', schema: FINDINGS_SCHEMA })
  .then(draft => !draft ? null : parallel(LENSES.map(l => () => agent(`${CTX}

Adversarial verifier for topic ${t.key}. The draft FINDINGS.md is below (not on disk); evidence is in ${STUDY}/results/${t.key}/ and scripts in ${STUDY}/scripts/${t.key}/. Default to skepticism.
${l.text}
No timed benchmarks. Write your report to ${STUDY}/results/${t.key}/VERIFY_${l.key}.md (rename an existing one to VERIFY_${l.key}.prev.md first), then return the structured verdict.

===== DRAFT FINDINGS.md =====
${draft.findings_md}`, { label: `verify:${t.key}:${l.key}`, phase: 'Findings', schema: VERIFY_SCHEMA }))).then(vs => ({ draft, vs: vs.filter(Boolean) })))
  .then(prev => !prev ? null : agent(`${CTX}

Revise the draft FINDINGS.md for topic ${t.key} (below) using ${STUDY}/results/${t.key}/VERIFY_provenance.md, VERIFY_method.md and these verdicts:
${JSON.stringify(prev.vs, null, 1).slice(0, 14000)}
Check each refutation yourself before applying it. Correct/remove refuted claims, relabel weak ones, add a final 'Verification' section. Return the COMPLETE revised text in findings_md (do not write FINDINGS.md) and a 10-line summary.

===== DRAFT FINDINGS.md =====
${prev.draft.findings_md}`, { label: `revise:${t.key}`, phase: 'Findings', schema: FINDINGS_SCHEMA }))

// jellyfin_ffmpeg FINDINGS chain does not depend on new functional work: start immediately.
const jfChain = findingsChain(TOPICS3[1])

phase('Functional')
const [q, c] = await parallel([
  () => agent(`${CTX}\n\n${QUALITY}`, { label: 'intra_compare:quality-sweep', phase: 'Functional', schema: NOTES_SCHEMA }),
  () => agent(`${CTX}\n\n${CHROME}`, { label: 'intra_playback:chromium', phase: 'Functional', schema: NOTES_SCHEMA }),
])

const queueP = agent(`${CTX}\n\n${queuePrompt(q, c)}`, { label: 'queue:build+smoke', phase: 'Queue', schema: QUEUE_SCHEMA })
const otherChains = [findingsChain(TOPICS3[0]), findingsChain(TOPICS3[2])]

const [queue, jf, hw, cc] = await Promise.all([queueP, jfChain, otherChains[0], otherChains[1]])

return {
  quality: q ? { summary: q.summary, open: q.open_questions } : 'FAILED',
  playback: c ? { summary: c.summary, open: c.open_questions } : 'FAILED',
  queue: queue || 'FAILED',
  findings: {
    jellyfin_ffmpeg: jf ? jf.summary : 'FAILED',
    hw_accel_target: hw ? hw.summary : 'FAILED',
    chromium_codecs: cc ? cc.summary : 'FAILED',
  },
}
