export const meta = {
  name: 'recording-upgrade-evidence',
  description: 'Gather tested evidence for skellycam recording upgrade (JPEG passthrough, crash-safe containers, vector overlays, intra codecs, GPU encode, licensing, Chromium playback/sync)',
  phases: [
    { title: 'Investigate', detail: '10 topic agents: sources + functional tests + bench scripts (no timing)' },
    { title: 'Bench', detail: 'timed benchmarks, one at a time under a lock' },
    { title: 'Findings', detail: 'per-topic FINDINGS.md from notes + bench' },
    { title: 'Verify', detail: 'provenance + methodology skeptics per topic, repro runs under lock, revise' },
    { title: 'Gaps', detail: 'completeness critic across goals, gap-fill tests' },
    { title: 'Index', detail: 'evidence index per goal' },
  ],
}

const ROOT = 'C:/Users/Dom/GitHub/freemocap/skellycam'
const STUDY = 'research/skellycam_recording/recording_upgrade'
const RAWD = 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109'
const SCR = 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad'

const GOALS = `User goals for the recording upgrade (G1-G9):
G1 Transcode-less JPEG storage for USB camera recordings when raw JPEG is extracted from the cameras (assume raw JPEG bytes are received; extraction is done elsewhere).
G2 Resumable / crash-tolerant file wrappers: if a session crashes part-way, what was recorded can still be played.
G3 Overlays stored as a secondary layer or separate vector files (SVG?) instead of burned into source images - to avoid overlap and for performance (vector write vs burn-in).
G4 Support other uncompressed camera formats (RAW/Bayer, NV12, others) and record them in an I-frame-only format, compressed or uncompressed.
G5 Wrapper optimized for recording throughput, if relevant: folder of JPEGs vs single (fragmented) MP4/MKV etc. - or show it is not significant / not worth the compatibility trade-off.
G6 GPU-accelerated encode on as many platforms as possible.
G7 Ideally royalty-free codecs (avoid H.264/H.265 where possible).
G8 Ideally native playback in the Chromium (Electron) UI.
G9 Easy synchronized, frame-accurate playback and scrubbing in the Chromium (Electron) UI.
Implementation will be Python; ideas from the Rust implementation (upstream/sfn26 skellycam-rust) may be reused.`

const CTX = `You are one agent in a research workflow for skellycam. Repo root ${ROOT} (branch dom/research), Windows 11 machine "Gerald". Work from the repo root.

${GOALS}

BACKGROUND (already verified against code - treat as true, do not re-check): ${STUDY}/../REPORT.md and research/skellycam_recording/results/real_recording_20261109/RESULTS.md describe today's recording system (per-camera cv2->MSMF->NVENC H.264 inside the lockstep capture loop, overlay burned in, CFR header ~10% fast, timestamps only after clean stop, plain MP4 that loses everything on hard kill). Related prior measurements you should reuse and cite rather than redo: research/frame_ring_buffer/prototypes/results/{p3_lossless_record,p4_mjpeg_passthrough,p5_nvenc,p6_ui_path,p8_e2e_summary,p11_crash_container,p12_disk_sustained}.md, research/usb_cameras/docs/mjpeg_passthrough_summary.md, research/usb_cameras/docs/skellycam_timestamps_review.md, research/usb_cameras/docs/timestamp_accuracy_options.md. Rust reference implementation: read with git show upstream/sfn26:<path> (skellycam-rust/src/recording/recorder.rs, recording_thread.rs, finalizer.rs, audio.rs, camera_group/dispatcher.rs, jpeg_transform.rs, frontend_encoder.rs, timestamps/csv_writer.rs). Current UI playback: skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx, skellycam-ui/src/contexts/PlaybackContext.tsx, skellycam/api/http/playback/playback_router.py (and the upstream/sfn26 versions).

EVIDENCE RULE (the user's hardest requirement): no assertion without hard evidence or test results. Label every claim:
- measured: a result file written in this study (cite its path) or a prior study's result file;
- source: a primary source (spec, RFC, standard, vendor documentation, licence text, library source at a pinned version/tag) - cite URL or file:line, an exact short quote, accessed 2026-11-09;
- code: repo source (file:line);
- inferred: reasoning, clearly marked, kept to a minimum, never presented as fact.
No numbers from memory. Blogs/forums/StackOverflow are leads only, never evidence. If something cannot be verified write NOT VERIFIED.

MACHINE: Intel i7-14700K (the Intel iGPU is NOT listed by Win32_VideoController - verify read-only before claiming QSV is absent), NVIDIA RTX 3070 (Ampere), driver 610.88. Parsec virtual display and Sunshine are installed and may use the GPU/NVENC - record nvidia-smi --query-gpu=encoder.stats.sessionCount,utilization.gpu --format=csv around GPU tests. C: is the only data drive (787 GB free).
TOOLS: ffmpeg/ffprobe 9.0.2 (gyan full build, on PATH). skellycam venv ${ROOT}/.venv/Scripts/python.exe: Python 3.12, PyAV 18.0.0 (libavcodec 62.28.102; its codec list includes av1_nvenc, av1_qsv, av1_amf, av1_mf, h264/hevc nvenc/qsv/amf/mf, libsvtav1, libvpx-vp9, libdav1d, ffv1, mjpeg, prores_ks, dnxhd), OpenCV 4.12.0, numpy - READ ONLY, never pip install into it. Node in C:/Program Files/nodejs. Electron 35.7.5 at ${ROOT}/skellycam-ui/node_modules/electron/dist/electron.exe (the version the skellycam and freemocap UIs pin). Newest stable Electron 45.2.3 already installed at ${SCR}/shared/electron-latest/node_modules/electron/dist/electron.exe (read-only shared; get its Chromium version from process.versions). Chrome 156 at C:/Program Files/Google/Chrome/Application/chrome.exe. Newest PyPI: av 19.0.2, opencv-python 5.0.0.93.
VERSION BUMPS: the user allows bumping versions (Electron, PyAV, OpenCV, codec libs...) if a newer version gives better video/image/audio format support. Test newer versions in isolation (uv run --script with PEP 723 inline deps pinned to exact versions; npm installs only inside the scratchpad), record exact versions, and compare against the pinned versions where it matters.

INPUT FRAMES (real camera data; DO NOT open or touch any camera): corpus ${RAWD}/corpus/ - read index.json first. MJPEG sets hold the cameras' own unmodified JPEG bytes (frame_NNNNNN.jpg): c930e_720p_flash and c922_720p_flash (~890 frames each, 1280x720, ~57 KB and ~77 KB/frame), c922_1080p and c930e_1080p (19 frames, ~192 KB / ~133 KB), c922_1600x896 (19), c922_720p60 (10), generic_1080p (11, has extra bytes before EOI on some frames). All are baseline (SOF0) 4:2:2 with DHT present. Loop frames for longer streams and say so. Two YUY2 sets (c930e_1080p_yuy2, c922_1080p_yuy2; 8 frames, packed yuyv422 1920x1080) are real uncompressed camera frames; NV12/Bayer/gray/RGB inputs may be derived from them or from decoded JPEGs (state how). Corpus builder: ${STUDY}/scripts/common/build_corpus.py.

PATHS: study folder ${STUDY}/ - your scripts in scripts/<topic>/, your text results in results/<topic>/. Media/large outputs (videos, images, frame dumps) ONLY under ${RAWD}/<topic>/ - they show the room and must never go in the repo. Temporary envs/downloads/node_modules: ${SCR}/<topic>/. Record third-party downloads by URL + exact version. Do not git commit. Never use SendMessage. No camera, driver, registry, BIOS, Defender or system-setting changes. Do not modify skellycam package code, skellycam-ui, or the freemocap repo (C:/Users/Dom/GitHub/freemocap/freemocap, read-only).
STYLE for result files: plain, concise Markdown; tables for comparisons; one claim per bullet with its label and citation.`

const NO_TIMING = `TIMING RULE FOR THIS STAGE: other agents run concurrently, so do NOT report timing/throughput/CPU numbers from this stage. Functional tests are fine and expected (does it encode, open, play, round-trip byte-exact, survive truncation, which error). Write benchmark scripts for anything timing-related, smoke-test each with a tiny run so it works, and list them in bench_manifest; they will be run later one at a time on a quiet machine by a runner who only has your NOTES.md and the manifest - so make commands complete and self-describing (they must write JSON results into ${STUDY}/results/<topic>/bench/).`

const TOPICS = [
  { key: 'jpeg_passthrough', goals: 'G1, G5 (compat side)', benchCap: 20, prompt: `Transcode-less storage of camera JPEG bytes. Determine by test:
(a) Which containers can store the camera JPEG bytes as packets WITHOUT decode/re-encode from Python: PyAV (av.Packet muxed into an mjpeg stream - what codec-context setup is needed, time_base, per-frame PTS from real timestamps, VFR) and ffmpeg -c:v copy from image2pipe as reference. Candidates: MKV, WebM (spec allows MJPEG? test), MP4 (ISO BMFF sample entry for JPEG), fragmented MP4, MOV, AVI (OpenDML), NUT, raw concatenated .mjpeg + binary index sidecar, folder of .jpg files.
(b) Byte-exactness: extract packets back (PyAV demux and ffmpeg -c copy -f image2) and compare SHA-256 per frame to the input.
(c) What each muxer does to JPEG headers (APP segments, DHT, AVI1 marker, mjpeg2jpeg/mjpega bsfs).
(d) Readability by ffprobe, PyAV, OpenCV 4.12 cv2.VideoCapture (find FreeMoCap's video reader in C:/Users/Dom/GitHub/freemocap/freemocap and test it the way FreeMoCap opens files), and frame-accurate seek in cv2 (CAP_PROP_POS_FRAMES then read; verify against the k-th input JPEG decoded).
(e) Whether real per-frame timestamps (VFR, use capture jitter) are preserved and reported by each reader.
(f) Lossless JPEG rotation in Python (PyTurboJPEG transform / jpegtran) as in Rust jpeg_transform.rs - prove losslessness (decode and compare pixels with a rotated decode).
(g) Cheap Chromium check of MJPEG in each container in Electron 35.7.5 and 45.2.3 (another topic goes deep).
(h) Camera JPEG edge cases: generic_1080p frames with extra bytes before EOI; a frame with DHT stripped (UVC MJPEG may omit DHT) - store and decode in each path.
Bench manifest: per-container mux cost per frame (CPU us/frame) via PyAV at 720p and 1080p, 1 camera per process (another topic covers multi-camera disk throughput).` },
  { key: 'write_throughput', goals: 'G5', benchCap: 35, prompt: `Recording wrapper throughput: folder of JPEG files vs single-file containers vs segmented files, for camera-JPEG passthrough (and one intra codec stream for comparison). Identify the drive (Get-PhysicalDisk model/media type, NTFS) and Defender real-time status (Get-MpComputerStatus, read-only, do NOT change it). Build benches measuring per-frame write latency distribution (p50/p99/p99.9/max), sustained throughput, CPU per camera, and frame drops at 1/4/8/16 cameras x 720p30/1080p30/1080p60 (corpus frame sizes, looped), for: (1) one .jpg per frame (open/write/close), with/without per-file fsync, one dir vs subdirs; (2) raw append .mjpeg + index sidecar (flush, optional periodic fsync); (3) MKV via PyAV packet passthrough; (4) fragmented MP4 via PyAV; (5) segmented MKV (e.g. 10 s). Compare threading models: write inside the capture loop vs one writer thread per camera vs a writer process (read the ring buffer study p4/p8/p12 for lockstep stall evidence and cite it). Also usability costs after recording: time to enumerate/open/read N frames from a folder vs a container, and copy time of a 1-hour-equivalent recording as 108k files vs one file (same disk; delete after). Check whether cv2.VideoCapture can read a JPEG folder as an image sequence (functional).` },
  { key: 'crash_resilience', goals: 'G2', benchCap: 15, prompt: `Resumable / crash-tolerant recording files. For each container x payload (MJPEG passthrough; FFV1; one inter codec such as AV1 via libsvtav1 or VP9; NVENC H.264 only as reference): MKV (PyAV defaults; cluster size/time options; reserve_index_space), WebM, fragmented MP4 (movflags frag_keyframe+empty_moov+default_base_moof; frag_every_frame / frag_duration), plain MP4 (baseline), segment muxer (segment_time, segment_list), NUT, AVI, raw .mjpeg+index, folder of JPEGs. Simulate: (a) hard kill of the writer process mid-recording (Popen.kill / taskkill /F) at several points; (b) power-loss emulation by truncating at >=20 random byte offsets per format, including mid-packet; (c) clean close as reference. For each: frames recoverable by ffprobe -count_frames, a PyAV decode loop, a cv2.VideoCapture read loop, and Electron 35.7.5 <video> playback (only for formats Chromium plays at all), and whether duration/seek work without repair. Then repair: remux to a finalized file (PyAV / ffmpeg -c copy); check result. Define and prototype 'resumable' in Python: on restart detect the incomplete file, keep it playable, and continue recording into a new segment with continuous frame numbers/timestamps. Also streaming timestamp sidecar durability (per-frame CSV vs binary append, flush vs fsync) under kill and truncation. Build on p11_crash_container.md. Note how sfn26 recorder.rs writes (plain MP4, no movflags) and what that implies (cite code). Bench manifest: CPU/size overhead of fragmenting vs fragment duration, fsync cost per N frames, remux/repair time per GB.` },
  { key: 'overlays', goals: 'G3', benchCap: 20, prompt: `Overlays as a separate layer instead of burned in. First inventory what overlays exist: skellycam's burned-in camera id/frame text (skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py around lines 79-89), anything skellycam-ui draws over live/playback video, and what FreeMoCap draws (search C:/Users/Dom/GitHub/freemocap/freemocap and its freemocap-ui for annotators/overlay drawing: ChArUco corners, skeletons, boxes, text) with the per-frame data shape. Evaluate storage options by test: (a) per-frame SVG files; (b) one SVG per recording with per-frame groups; (c) JSON Lines / MessagePack / compact binary sidecar of vector primitives keyed by frame number + timestamp, rendered to SVG/Canvas at playback; (d) WebVTT metadata track (kind=metadata, JSON payloads) - cue timing precision vs frames in Chromium; (e) subtitle stream in MKV (ASS) - check whether Chromium renders it; (f) a secondary alpha video layer (VP9 alpha in WebM; PNG/QTRLE in MOV) - generation cost and size. Functional test in Electron 35.7.5: SVG/Canvas overlay synced to <video> with requestVideoFrameCallback - verify overlay-to-frame alignment by drawing the frame number in the overlay and comparing to a frame index pattern encoded in the video (read canvas pixels). Overlap avoidance: propose and demonstrate a deterministic layout (e.g. label lanes / collision-free label placement) on a sample with many labels. Also an 'export with overlays burned in' path for sharing (PyAV/ffmpeg or canvas). Bench manifest: per-frame cost to generate+write each format vs cv2.putText burn-in at 720p/1080p for (i) today's text and (ii) a realistic FreeMoCap overlay (33-point skeleton with lines; ~100 ChArUco corners with ids), plus bytes per hour.` },
  { key: 'uncompressed_intra', goals: 'G4', benchCap: 35, prompt: `Uncompressed camera formats (NV12, YUY2/YUYV, UYVY, GRAY8, GRAY16/Y16, Bayer RAW8/10/12/16 incl. packed variants, RGB24/BGR24, I420, P010) recorded intra-only (every frame a keyframe), compressed or uncompressed. By test (PyAV 18 from numpy arrays; ffmpeg CLI as reference): which codecs accept which pixel formats natively vs needing conversion: rawvideo (in MKV, NUT, AVI), FFV1 (v1/v3, slices, CRC), FFVHuff/HuffYUV, UTVideo, MagicYUV, JPEG via libjpeg-turbo from Python (cv2.imencode, simplejpeg, PyTurboJPEG encode from YUV planes without RGB conversion), ffmpeg mjpeg encoder, JPEG XL (libjxl lossless/lossy), JPEG 2000, AV1 all-intra (libsvtav1 keyint 1, libaom), VP9 intra (libvpx-vp9 -g 1, lossless), ProRes/DNxHR (reference), H.264/HEVC intra (reference only). Bayer: store raw (bayer_* pix_fmts in NUT/MKV rawvideo), losslessly packed as gray/gray16 in FFV1, or debayer first (cost, information loss) - test each. Verify lossless round trips bit-exact (hash decoded vs input). Note which outputs Chromium plays natively (cheap check; another topic goes deep). Also check whether PyAV 19.0.2 (isolated) adds relevant pixel formats/codecs. Bench manifest: encode fps (single stream, 1 thread and all threads), CPU per stream, bytes/frame, decode fps, at 1080p NV12 and YUY2 (real frames), 720p, Bayer 1080p 12-bit derived from real frames.` },
  { key: 'gpu_encode', goals: 'G6, G7', benchCap: 35, prompt: `GPU-accelerated encode on as many platforms as possible, preferring royalty-free codecs (AV1, VP9, JPEG, FFV1 via Vulkan compute) with H.264/HEVC only as reference. On Gerald functional-test every hardware encoder in ffmpeg 9.0.2 and in PyAV 18 (av1_nvenc, av1_qsv, av1_amf, av1_mf, av1_d3d12va, av1_vulkan, h264/hevc nvenc/qsv/amf/mf/d3d12va/vulkan, vp9_qsv, mjpeg_qsv, ffv1_vulkan, prores_ks_vulkan): does it open, exact error; for those that work, configure all-intra (g=1 / forced keyframes) and a short-GOP variant, check with ffprobe. Check Intel iGPU presence read-only (Get-PnpDevice -Class Display) - no BIOS/driver changes. GPU JPEG encode from Python: NVIDIA nvImageCodec (nvidia-nvimgcodec-cu12) and/or torchvision.io.encode_jpeg on CUDA, in an isolated uv env (record versions). Check whether PyAV 19.0.2 differs. Cross-platform support table from PRIMARY sources only: NVIDIA Video Encode and Decode GPU Support Matrix / Video Codec SDK docs (AV1/HEVC/H.264 encode per GPU generation; GeForce concurrent session limit), Intel media driver / oneVPL docs per generation (AV1/VP9/JPEG encode), AMD AMF docs (AV1 per RDNA gen), Apple VideoToolbox (which codecs can be encoded on which Macs; whether ffmpeg exposes av1/vp9 videotoolbox encoders - check ffmpeg source at a pinned tag), Linux VAAPI and Vulkan Video encode (VK_KHR_video_encode_av1 driver support), plus which hardware encoders the PyPI PyAV wheels ship per OS (PyAV build scripts at the pinned tag). Bench manifest: per-stream fps at 720p/1080p from NV12 input and from MJPEG input (CPU decode vs mjpeg_cuvid/NVDEC), concurrent-stream scaling 1->8->16 (actual session limit with driver 610.88), CPU cost, numpy->frame upload cost from Python.` },
  { key: 'chromium_codecs', goals: 'G8', benchCap: 10, prompt: `Native playback support in Chromium/Electron - test, don't assume. In Electron 35.7.5, Electron 45.2.3 and Chrome 156, for each codec {AV1 main 8/10-bit 4:2:0, AV1 high/professional 4:4:4/4:2:2, VP9 profiles 0/1/2/3 incl. lossless, VP8, H.264 (reference), HEVC (reference), MJPEG, FFV1, rawvideo} x container {MP4, fragmented MP4, WebM, MKV, MOV, AVI, Ogg}: HTMLMediaElement.canPlayType, MediaSource.isTypeSupported, MediaCapabilities.decodingInfo (smooth/powerEfficient), WebCodecs VideoDecoder.isConfigSupported (prefer-hardware/prefer-software), ImageDecoder.isTypeSupported (image/jpeg, image/jxl, image/avif, image/webp) - AND an actual play test: load in <video>, play, draw to canvas, verify decoded pixels against a per-frame binary index pattern encoded into each test clip (made from real corpus content + pattern). Report hardware decode where detectable (MediaCapabilities powerEfficient, chrome://gpu / media logs via --enable-logging). Check by test whether Electron's bundled ffmpeg plays H.264/HEVC (proprietary codecs). Serving: file:// vs a custom protocol (protocol.handle) with HTTP Range support - test which seeks. Output a full support matrix, every cell measured. Bench manifest: probably none (functional topic) - only list decode-throughput checks if decisive.` },
  { key: 'chromium_sync_scrub', goals: 'G9', benchCap: 35, prompt: `Synchronized, frame-accurate multi-camera playback and scrubbing in Chromium/Electron. Build a harness for Electron 35.7.5 and 45.2.3 with 3-8 test clips (real corpus content + a per-frame binary index pattern; 720p/1080p; 30/60 fps) in: AV1 GOP (g=30/60) and all-intra, VP9 GOP and all-intra, H.264 as reference, a JPEG-sequence path (MJPEG frames from a raw .mjpeg + index via Range requests or a folder, decoded with createImageBitmap / WebCodecs ImageDecoder), and a WebCodecs VideoDecoder path with demux (mp4box.js for MP4 or a WebM demuxer, or the recorder's own index - record package versions/URLs). Functional now, timed later: (a) seek accuracy - request frame k (currentTime=(k+0.5)/fps for <video>, by index for WebCodecs/JPEG), read back the index pattern; % exact over >=200 random seeks per path, including VFR files whose frame times are real capture jitter; (b) seek latency p50/p95/max per path and GOP length; (c) single-frame step forward/back latency; (d) sync across N videos while playing: per-rendered-frame index spread across N <video> elements using requestVideoFrameCallback vs a single master clock driving WebCodecs/JPEG frames; (e) scrub smoothness (frames shown per second while dragging, simulated input); (f) CPU/memory at N=4 and 8 at 1080p. Read the current UI player (SyncedVideoPlayer.tsx, PlaybackContext.tsx, and upstream/sfn26 versions) and describe how it syncs today (code). Cite the HTML spec / WICG requestVideoFrameCallback spec / WebCodecs spec for currentTime precision and frame-exactness guarantees (source).` },
  { key: 'licensing', goals: 'G7', benchCap: 0, prompt: `Royalty and licence status from primary sources only (patent licence texts, standards bodies, licensors' own pages, RFCs; exact quotes with URL, accessed 2026-11-09). Use WebSearch/WebFetch (load via ToolSearch). Codecs: AV1 (AOMedia Patent License 1.0; plus third-party pool claims such as Sisvel's AV1 and VP9 programmes and any public decisions - report as those parties' claims without judgement), VP8/VP9 (Google WebM patent licence / cross-licence), FFV1 (RFC 9043 and IETF IPR disclosures), JPEG baseline (ISO/IEC 10918-1; JPEG committee royalty-free statement), Motion JPEG (no single spec - note), JPEG XL (ISO/IEC 18181 royalty-free declarations), JPEG 2000 Part 1, UT Video, MagicYUV, HuffYUV/FFVHuff, ProRes (Apple licensing), DNxHD/DNxHR (SMPTE VC-3, Avid), H.264 and HEVC (Via LA AVC/HEVC programmes, Access Advance, Avanci Video - incl. terms for free software / below-threshold units; Cisco OpenH264 binary arrangement). Containers: Matroska/WebM (RFC 9559), ISO BMFF/MP4 (ISO/IEC 14496-12/14), AVI, NUT. Audio if relevant (Opus RFC 6716, FLAC, PCM/WAV, AAC). Software licences constraining distribution of the Python implementation: PyAV wheels' bundled FFmpeg build (LGPL vs GPL; which external libs: libx264 GPL, libsvtav1, libvpx, libdav1d, libaom - check the PyAV build scripts at tags v18.0.0 and v19.0.2 AND test locally av.library_configuration / codec list), opencv-python wheels' bundled ffmpeg, NVIDIA redistributable terms for nvImageCodec/nvJPEG, Electron/Chromium codec licensing (proprietary_codecs). OS codecs (Windows Media Foundation, Apple VideoToolbox) - who bears royalties per Microsoft/Apple docs, NOT VERIFIED if not stated. Output a table: format, royalty/licence status (quoted), source URL, caveats. No timing work.` },
  { key: 'python_integration', goals: 'G1-G9 integration', benchCap: 15, prompt: `How the upgrades fit the Python implementation. Map with file:line citations: the current recorder path (skellycam/core/recorders/**, camera loop, handle_recording_updates, recording finalizer, timestamps), the playback router and UI player; the same on upstream/sfn26 (Python path and the opt-in Rust backend: recording/*, camera_group/dispatcher.rs, jpeg_transform.rs, frontend_encoder.rs, timestamps/csv_writer.rs, pyo3_bridge). Identify where raw JPEG bytes would enter the Python recorder; what changes to record packets instead of decoded frames; where per-frame PTS come from (timestamps review + timestamp_accuracy_options); how the live UI still gets decoded frames (decode cost per JPEG in Python: cv2.imdecode vs simplejpeg vs PyTurboJPEG vs nvJPEG - cite prior p4/p8 numbers; list a bench for missing ones); a threading model that keeps writes out of the lockstep camera loop (cite ring buffer evidence); streaming timestamps; recovery on startup. Functional prototype: a minimal Python RecordingWriter taking (jpeg_bytes, frame_number, timestamp_ns) that writes MJPEG-in-MKV (or the best container found) with real PTS plus a per-frame binary/CSV sidecar, and a matching reader; verify byte-exact JPEG and timestamp round trips. FreeMoCap compatibility: find how FreeMoCap reads synchronized_videos (video reading code, VIDEO_EXTENSIONS) and test whether opencv-python 4.12 opens MJPEG-in-MKV, FFV1-in-MKV, AV1 and VP9 in WebM/MKV/MP4 - and whether opencv-python 5.0.0.93 (isolated) changes that. Check PyAV 19.0.2 release notes (primary source) vs 18.0.0 for relevant changes. Bench manifest: Python JPEG decode cost per library at 720p/1080p if not already measured by prior studies.` },
]

const INVEST_SCHEMA = {
  type: 'object',
  properties: {
    summary: { type: 'string', description: '10-25 line summary of what was established, with labels' },
    notes_path: { type: 'string' },
    bench_manifest: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          purpose: { type: 'string' },
          command: { type: 'string', description: 'complete command from repo root' },
          est_minutes: { type: 'number' },
          priority: { type: 'integer', description: '1 = decisive for the plan, 3 = nice to have' },
        },
        required: ['id', 'purpose', 'command', 'est_minutes', 'priority'],
      },
    },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['summary', 'notes_path', 'bench_manifest', 'open_questions'],
}

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    refuted: { type: 'array', items: { type: 'object', properties: { claim: { type: 'string' }, why: { type: 'string' }, correction: { type: 'string' } }, required: ['claim', 'why', 'correction'] } },
    weak: { type: 'array', items: { type: 'object', properties: { claim: { type: 'string' }, why: { type: 'string' }, fix: { type: 'string' } }, required: ['claim', 'why', 'fix'] } },
    repro_requests: { type: 'array', items: { type: 'object', properties: { claim: { type: 'string' }, command: { type: 'string' }, expected: { type: 'string' } }, required: ['claim', 'command', 'expected'] } },
    verdict: { type: 'string' },
  },
  required: ['refuted', 'weak', 'repro_requests', 'verdict'],
}

// ---- a mutex so timed work never overlaps ----
let lockTail = Promise.resolve()
function withLock(fn) {
  const run = lockTail.then(fn, fn)
  lockTail = run.then(() => {}, () => {})
  return run
}

const BENCH_PROTOCOL = `BENCH PROTOCOL: you hold the machine's timing lock - no other timed work runs now (light LLM agents may still run; they do no heavy compute). Before measuring: record 10 s of total CPU (typeperf "\\Processor(_Total)\\% Processor Time" -si 1 -sc 10), the top 10 CPU processes, nvidia-smi utilization + encoder sessions, free disk, Defender real-time status (read-only). If average CPU > 15%, re-check for up to 5 minutes, then proceed and flag it. Discard a warm-up run; >= 3 repetitions; report median and min-max; record versions and environment in every result JSON. Save raw JSON under ${STUDY}/results/<topic>/bench/ and a BENCH.md summary with tables (labels: measured, with file paths). Fix broken scripts if needed and note the fixes. Respect the wall-time cap: run priority-1 items first; reduce reps/resolutions rather than overrun; log anything dropped in BENCH.md. Delete large temporary media when done unless another topic needs it (media only under ${RAWD}).`

async function investigate(t) {
  return agent(`${CTX}

TOPIC: ${t.key} (goals ${t.goals}). Your scripts: ${STUDY}/scripts/${t.key}/ ; text results: ${STUDY}/results/${t.key}/ ; media: ${RAWD}/${t.key}/ ; temp: ${SCR}/${t.key}/.

${t.prompt}

${NO_TIMING}

Deliverable: ${STUDY}/results/${t.key}/NOTES.md - everything you established (labelled, cited), the exact commands/scripts used, functional test results tables, and limits. Then return the structured summary (notes_path, bench_manifest with complete commands, open questions).`, { label: `investigate:${t.key}`, phase: 'Investigate', schema: INVEST_SCHEMA })
}

async function bench(t, inv) {
  const items = (inv && inv.bench_manifest) || []
  if (!t.benchCap || items.length === 0) return 'no bench'
  return withLock(() => agent(`${CTX}

You are the BENCHMARK RUNNER for topic ${t.key}. Read ${STUDY}/results/${t.key}/NOTES.md and the scripts in ${STUDY}/scripts/${t.key}/. Manifest:
${JSON.stringify(items, null, 1)}

${BENCH_PROTOCOL.replace(/<topic>/g, t.key)}
Wall-time cap for this topic: ${t.benchCap} minutes of benchmark runtime.
Return a short text summary of what was measured and where the files are.`, { label: `bench:${t.key}`, phase: 'Bench' }))
}

async function findings(t, inv, benchRes) {
  return agent(`${CTX}

Write ${STUDY}/results/${t.key}/FINDINGS.md for topic ${t.key} (goals ${t.goals}) by merging ${STUDY}/results/${t.key}/NOTES.md and, if present, ${STUDY}/results/${t.key}/BENCH.md + bench/*.json. Read the raw files; do not trust summaries. Bench runner summary: ${typeof benchRes === 'string' ? benchRes.slice(0, 3000) : 'none'}.
Structure: 1) Question(s) answered, 2) Findings (each bullet labelled + cited; numbers exactly as in result files with units and conditions), 3) Comparison table(s), 4) Implications for the plan - each recommendation tied to specific findings, 5) Not tested / limits / NOT VERIFIED items, 6) How to reproduce (commands). Drop or relabel anything that lacks evidence. If a quick functional check (< 1 min CPU, no timing) settles a loose end, you may run it and add it. Return a 15-line summary.`, { label: `findings:${t.key}`, phase: 'Findings' })
}

const LENSES = [
  { key: 'provenance', text: `PROVENANCE lens: for every claim in FINDINGS.md, check the cited evidence exists and says exactly that - open result files/JSON and compare numbers, re-open source URLs (WebFetch via ToolSearch) and check quotes and that the source is primary, open code at the cited file:line. Flag unlabelled claims, inferred-presented-as-fact, numbers from memory, secondary sources, quotes that don't match.` },
  { key: 'method', text: `METHODOLOGY lens: look for confounders and wrong conclusions - background load during benches, warm caches, looped tiny corpora (19-frame 1080p sets) unrepresentative of real compressibility, PyAV vs ffmpeg CLI differences, a functional pass mistaken for compatibility, Chromium tests that did not verify decoded pixels, truncation tests that miss realistic failure points, single-run numbers, conclusions that don't follow from data, alternative explanations. You may re-run quick functional checks (< 1 min CPU each, no timing). For any decisive TIMED number you doubt, add a repro_request with a complete command (max 2) - it will be run under the timing lock.` },
]

async function verifyAndRevise(t) {
  const votes = await parallel(LENSES.map(l => () => agent(`${CTX}

You are an adversarial verifier for topic ${t.key}. Target: ${STUDY}/results/${t.key}/FINDINGS.md (and its NOTES.md, BENCH.md, bench/*.json, scripts). Default to skepticism: a claim survives only with evidence.
${l.text}
Do NOT run timed benchmarks (other timed work may be running). Write your report to ${STUDY}/results/${t.key}/VERIFY_${l.key}.md, then return the structured verdict.`, { label: `verify:${t.key}:${l.key}`, phase: 'Verify', schema: VERIFY_SCHEMA })))
  const vs = votes.filter(Boolean)
  const repros = vs.flatMap(v => v.repro_requests || []).slice(0, 3)
  let reproOut = 'none'
  if (repros.length) {
    reproOut = await withLock(() => agent(`${CTX}

You are a REPRODUCTION runner for topic ${t.key}. Verifiers doubt these timed results; re-run each (fix commands if needed) and compare to the original numbers in ${STUDY}/results/${t.key}/:
${JSON.stringify(repros, null, 1)}
${BENCH_PROTOCOL.replace(/<topic>/g, t.key)}
Cap: 15 minutes. Save results to ${STUDY}/results/${t.key}/bench/repro_*.json and append a 'Reproduction' section to ${STUDY}/results/${t.key}/BENCH.md. Return a short text summary: original vs reproduced numbers, agree/disagree.`, { label: `repro:${t.key}`, phase: 'Verify' }))
  }
  return agent(`${CTX}

Revise ${STUDY}/results/${t.key}/FINDINGS.md using the verifier reports ${STUDY}/results/${t.key}/VERIFY_provenance.md and VERIFY_method.md and these structured verdicts:
${JSON.stringify(vs, null, 1).slice(0, 12000)}
Reproduction results: ${typeof reproOut === 'string' ? reproOut.slice(0, 3000) : 'none'}
Check each refutation yourself against the evidence before applying it (verifiers can be wrong too). Correct or remove refuted claims, relabel weak ones, add a final section 'Verification' listing what was challenged, what changed, and what remains NOT VERIFIED. Quick functional checks (< 1 min CPU, no timing) allowed. Return a 10-line summary of the final state of the topic, including the most decisive verified findings.`, { label: `revise:${t.key}`, phase: 'Verify' })
}

// ---- run: pipeline per topic; benches serialize via the lock ----
const results = await pipeline(
  TOPICS,
  t => investigate(t),
  (inv, t) => bench(t, inv).then(b => ({ inv, b })),
  (prev, t) => findings(t, prev.inv, prev.b).then(f => ({ ...prev, f })),
  (prev, t) => verifyAndRevise(t).then(v => ({ ...prev, v })),
)

const topicSummaries = TOPICS.map((t, i) => {
  const r = results[i]
  return `## ${t.key} (${t.goals})\n${r ? (typeof r.v === 'string' ? r.v : '') : 'FAILED - no result'}\nOpen questions: ${r && r.inv ? JSON.stringify(r.inv.open_questions) : ''}`
}).join('\n\n')
const failed = TOPICS.filter((t, i) => !results[i]).map(t => t.key)
if (failed.length) log(`Topics that failed: ${failed.join(', ')}`)

// ---- completeness critic + gap fill ----
phase('Gaps')
const GAP_SCHEMA = {
  type: 'object',
  properties: {
    gaps: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, goal: { type: 'string' }, topic: { type: 'string', description: 'topic folder to append results to' },
      what_is_missing: { type: 'string' }, test_to_run: { type: 'string' }, timed: { type: 'boolean' }, priority: { type: 'integer' } },
      required: ['id', 'goal', 'topic', 'what_is_missing', 'test_to_run', 'timed', 'priority'] } },
  },
  required: ['gaps'],
}
const critic = await agent(`${CTX}

COMPLETENESS CRITIC. Read every ${STUDY}/results/*/FINDINGS.md. Topic summaries:
${topicSummaries.slice(0, 20000)}

For each goal G1-G9, ask: could a plan for this goal be written using only verified evidence here? List the missing evidence that would block or weaken a recommendation: an untested candidate that is plausibly the best option, a claim still NOT VERIFIED that the plan depends on, a cross-topic combination never tested end-to-end (e.g. the recommended container x codec x Chromium playback x crash survival x FreeMoCap cv2 read), a platform not covered by primary sources. Rank by how decisive it is. Max 8 gaps; each with a concrete test. Write ${STUDY}/results/COMPLETENESS_CRITIQUE.md and return the structured list.`, { label: 'critic', phase: 'Gaps', schema: GAP_SCHEMA })

const gaps = ((critic && critic.gaps) || []).sort((a, b) => a.priority - b.priority).slice(0, 8)
if (critic && critic.gaps && critic.gaps.length > 8) log(`Critic listed ${critic.gaps.length} gaps; filling top 8 only (rest remain in COMPLETENESS_CRITIQUE.md)`)
const gapPrompt = g => `${CTX}

GAP FILL ${g.id} for goal ${g.goal}. Missing: ${g.what_is_missing}
Test to run: ${g.test_to_run}
Put scripts in ${STUDY}/scripts/${g.topic}/gap_${g.id}/ and results in ${STUDY}/results/${g.topic}/gap_${g.id}.md (+ JSON). Then append a short 'Gap ${g.id}' section to ${STUDY}/results/${g.topic}/FINDINGS.md that links the file and states the result with labels. Then do a self-check: re-read your result file and confirm every number matches the raw output. ${g.timed ? BENCH_PROTOCOL.replace(/<topic>/g, g.topic) + ' Cap 25 minutes.' : NO_TIMING.replace('list them in bench_manifest', 'state that they were not run')} Return a 6-line summary.`
const gapResults = await parallel(gaps.map(g => () => g.timed
  ? withLock(() => agent(gapPrompt(g), { label: `gap:${g.id}`, phase: 'Gaps' }))
  : agent(gapPrompt(g), { label: `gap:${g.id}`, phase: 'Gaps' })))

// ---- evidence index ----
phase('Index')
const index = await agent(`${CTX}

Write ${STUDY}/results/EVIDENCE_INDEX.md: for each goal G1-G9, the verified findings a plan can rely on (one line each: finding, label, link to the FINDINGS.md section or result file), the options ruled out and why (with evidence links), and what remains NOT VERIFIED. Also a short machine/environment section (versions tested, incl. Electron 35.7.5 vs 45.2.3, PyAV 18 vs 19, OpenCV 4.12 vs 5.0). Read every ${STUDY}/results/*/FINDINGS.md, gap_*.md and COMPLETENESS_CRITIQUE.md. Do not add any claim that is not in those files. Return the full text of EVIDENCE_INDEX.md.`, { label: 'evidence-index', phase: 'Index' })

return { failed, gaps: gaps.map(g => g.id + ': ' + g.what_is_missing), gapResults, index }
