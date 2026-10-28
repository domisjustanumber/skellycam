export const meta = {
  name: 'frame-ring-buffer-analysis',
  description: 'Map + verify SkellyCam/FreeMoCap frame ring buffer, research best practices, benchmark baseline/prototypes/C++, recommend and critique',
  phases: [
    { title: 'Map', detail: '5 parallel code readers over write/read/control/UI/FreeMoCap paths' },
    { title: 'Verify', detail: 'adversarial check of every code-referenced claim' },
    { title: 'Research', detail: 'web research: pipeline best practices, Python vs C++' },
    { title: 'Benchmark', detail: 'serialized: baseline -> prototypes -> C++' },
    { title: 'Recommend', detail: 'optimisation plan against the 3 priorities' },
    { title: 'Critique', detail: 'evidence critic, priority critic, reproducibility re-run' },
  ],
}

const SK = 'C:\\Users\\Dom\\GitHub\\freemocap\\skellycam'
const FMC = 'C:\\Users\\Dom\\GitHub\\freemocap\\freemocap'
const BENCH = 'C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\research\\frame_ring_buffer'
const SCRATCH = 'C:\\Users\\Dom\\AppData\\Local\\Temp\\claude\\c--Users-Dom-GitHub-freemocap-skellycam\\ad23e4da-d956-400c-b95c-1c7166f96ad9\\scratchpad'

const CONTEXT = `
CONTEXT (shared by every agent in this study)
Goal of the overall study: a report on how the SkellyCam frame ring buffer (shared memory) moves images from cameras to disk, to the UIs, and from SkellyCam into FreeMoCap; and an evidence-backed plan to raise throughput.
Solution priorities, in order: (1) disk writes must NEVER drop frames; (2) highest possible throughput, benchmark goal 5 cameras at 60+ fps (assume 1280x720 and 1920x1080 BGR as the two reference sizes unless the code shows a different native format, and say which you used); (3) do not copy video frames unless absolutely necessary.
HARD RULE: make no assertion without either a code reference (file + line range, preferably a GitHub permalink) or a pointer to a benchmark/test output file plus the script and command that reproduce it. If you cannot back a statement, mark it as an open question instead.

Repositories (local checkouts; Windows 11, Git Bash and PowerShell available):
- SkellyCam: ${SK}  branch development, HEAD 23ccbf208e43879bfc74fc01049e5af2a623933d (pushed to upstream github.com/freemocap/skellycam).
  Permalink form: https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/<path>#L<a>-L<b>
  Key dirs: skellycam/core/ipc/shared_memory/ (ring_buffer_shared_memory.py, camera_shared_memory_ring_buffer.py, shared_memory_element.py, shared_memory_number.py, camera_group_shared_memory.py), skellycam/core/ipc/pubsub/, skellycam/core/ipc/process_management/, skellycam/core/camera_group/camera_group_ipc.py, skellycam/api/, skellycam-ui/ (Electron + React/TS frontend), skellycam/system/diagnostics/ (check_shm_speed.py, check_image_queue_speeds.py), skellycam/tests/.
- FreeMoCap: ${FMC}  branch development, HEAD 5632778af10e22befd4ec0a719ba844f14a84e93 (pushed to upstream github.com/freemocap/freemocap).
  Permalink form: https://github.com/freemocap/freemocap/blob/5632778af10e22befd4ec0a719ba844f14a84e93/<path>#L<a>-L<b>
  Key dirs: freemocap/core/pipeline/realtime/ (camera_node.py, realtime_pipeline.py, realtime_aggregator_node.py, ...), freemocap/api/websocket/ (websocket_server.py, binary_keypoints_protocol.py), freemocap/app/, freemocap-ui/.
  IMPORTANT: freemocap's pyproject pins skellycam from git branch main; its .venv has skellycam 2.0.0a6 at commit 777b058ceafb578c55092179506cd8a925a38b50 (installed under ${FMC}\\.venv\\Lib\\site-packages\\skellycam). The SkellyCam checkout may have that commit via upstream/main (git -C ${SK} log -1 777b058c). Where the two versions differ in the ring-buffer/IPC code, say so.
- Sibling repos in C:\\Users\\Dom\\GitHub\\freemocap\\ that are prior art only (NOT the code under study, label them clearly if mentioned): skellycam-shm-ui (fork; last commit "feat(shm): add control SHM buffer for local-UI-only delivery"), skellycam-opnpc-mf (fork using openpnp-capture / Media Foundation), openpnp-capture and openpnp-capture-python (C++ capture library + Python bindings).
Toolchain: Python 3.12 via uv (SkellyCam venv at ${SK}\\.venv; run with "uv run" from ${SK} or ${SK}\\.venv\\Scripts\\python.exe). MSVC: "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat". GPU: NVIDIA RTX 3070. 28 logical CPUs.
Do NOT modify any source file in either repo. Do not commit, push, or install packages into the repos' own venvs. Scratch space: ${SCRATCH}.
`

const REF_SCHEMA = {
  type: 'object',
  properties: {
    repo: { type: 'string', enum: ['skellycam', 'freemocap', 'skellycam-ui', 'freemocap-ui', 'freemocap-venv-skellycam-777b058c', 'sibling-prior-art'] },
    path: { type: 'string' },
    lines: { type: 'string', description: 'e.g. 120-148' },
    permalink: { type: 'string' },
  },
  required: ['repo', 'path', 'lines'],
}

const MAP_SCHEMA = {
  type: 'object',
  properties: {
    area: { type: 'string' },
    summary: { type: 'string', description: '3-6 sentence plain-English summary of this area' },
    claims: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string', description: 'short unique id, prefixed by area, e.g. W3' },
          statement: { type: 'string' },
          refs: { type: 'array', items: REF_SCHEMA, minItems: 1 },
          importance: { type: 'string', enum: ['critical', 'high', 'medium', 'low'] },
        },
        required: ['id', 'statement', 'refs', 'importance'],
      },
    },
    frame_copies: {
      type: 'array',
      description: 'every place a full image buffer is copied or re-materialised (memcpy, np.copy, .tobytes, encode, decode, pickle, queue put, websocket send)',
      items: {
        type: 'object',
        properties: {
          where: { type: 'string' },
          kind: { type: 'string', description: 'memcpy / numpy copy / encode / decode / serialize / IPC transfer / other' },
          necessary: { type: 'string', description: 'why it exists and whether it could be avoided' },
          refs: { type: 'array', items: REF_SCHEMA, minItems: 1 },
        },
        required: ['where', 'kind', 'necessary', 'refs'],
      },
    },
    flow_steps: {
      type: 'array',
      description: 'ordered steps of the frame/control flow in this area, for a diagram: actor (process/thread), action, next actor',
      items: { type: 'object', properties: { process_or_thread: { type: 'string' }, action: { type: 'string' }, to: { type: 'string' }, ref: { type: 'string' } }, required: ['process_or_thread', 'action'] },
    },
    risks_for_priorities: {
      type: 'array',
      description: 'anything that threatens: P1 never dropping disk writes, P2 5x60fps throughput, P3 zero-copy',
      items: { type: 'object', properties: { priority: { type: 'string', enum: ['P1', 'P2', 'P3'] }, risk: { type: 'string' }, refs: { type: 'array', items: REF_SCHEMA } }, required: ['priority', 'risk', 'refs'] },
    },
    version_diffs_777b058c: { type: 'string', description: 'differences relevant to this area between skellycam 23ccbf20 and the 777b058c FreeMoCap actually runs; "none found" if none' },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['area', 'summary', 'claims', 'frame_copies', 'flow_steps', 'risks_for_priorities', 'version_diffs_777b058c', 'open_questions'],
}

const AREAS = [
  {
    key: 'write',
    title: 'Write path: frames into the ring buffer (SkellyCam)',
    prompt: `Map exactly how images get INTO the shared-memory ring buffer. Cover: camera capture backends and worker processes/threads (which process owns each camera, how cv2/other backends read frames); how the shared memory is allocated (sizes, number of slots, dtype/record layout incl. metadata/timestamps, who creates vs attaches); the write call chain from camera read to the slot (every function hop, with line refs); index/counter handling (write index, read indices, SharedMemoryNumber, wraparound); synchronisation and memory-ordering (locks, flags, seqlocks, or none - and whether a torn read is possible); how frame-perfect multi-camera sync (same frame count for every camera, "multi-frame") is enforced at write time; and every copy of image bytes on the way in (e.g. cv2 read allocates a new ndarray then it is copied into shm). Also find and read the existing tests (skellycam/tests/test_shared_memory.py) and diagnostics that exercise this path.`,
  },
  {
    key: 'read',
    title: 'Read paths: frames out of the ring buffer (SkellyCam)',
    prompt: `Map every READER of the ring buffer in SkellyCam. For each reader (video recorder / disk writer, frontend/websocket streamer, multi-frame assembler, anything else): which process/thread it runs in; whether it reads "latest" or "next unread" frame; how it tracks its read position; what happens when it falls behind (overwrite? detection? error? silent drop?) - this is central to priority P1 "disk writes must never drop"; whether it reads a view or copies (np.copy, .copy(), slicing into a new array, tobytes, pickle); how the video file is written (cv2.VideoWriter? ffmpeg? codec/fourcc, container, per-camera thread/process, timestamps file) and whether the recorder can block the producer or vice versa; how recording start/stop is applied relative to frame numbers. Trace with exact line refs. Read the existing tests and diagnostics that exercise this path.`,
  },
  {
    key: 'control',
    title: 'Control plane: control messages (SkellyCam)',
    prompt: `Map how CONTROL messages work in SkellyCam: the pubsub system (skellycam/core/ipc/pubsub/: topics, manager, transport - multiprocessing Queue/Pipe/Manager?), process management (managed_worker, worker_registry), shared flags/numbers used as control signals (kill/pause/record flags), the HTTP and websocket API endpoints that originate commands (connect cameras, update config, start/stop recording, close, shutdown), and how each command travels to the camera workers and recorder. For each control message type: origin, transport, receiver, how the receiver polls/blocks for it (inside the frame loop? separate thread?), and whether it can stall the frame loop. Also: what control-ish metadata travels alongside frames (frame numbers, timestamps, camera configs) and how. Exact line refs throughout.`,
  },
  {
    key: 'ui',
    title: 'UI tap: SkellyCam UI and its server side',
    prompt: `Map where and how the SkellyCam UI taps frames. Server side: which code reads from the ring buffer for the UI, how frames are selected (latest? every Nth? throttled to a UI fps?), resized, encoded (JPEG/PNG/raw? which library, quality), packaged (binary websocket protocol layout? JSON?), and sent; backpressure handling when the client is slow; what else is sent (fps stats, logs). Client side (skellycam-ui/, Electron + React/TS): where the websocket is opened, how binary frames are parsed and decoded (createImageBitmap? <img> blob URLs? canvas? worker?), rendered, and acknowledged; any frame-request/ack handshake. Cite exact lines in both Python and TS. Also briefly (2-4 claims max, labelled sibling-prior-art) summarise what the sibling fork C:\\Users\\Dom\\GitHub\\freemocap\\skellycam-shm-ui changes about UI delivery (git -C that repo log --oneline -15 and its diff vs upstream/development if available) - do not mix it with the main code.`,
  },
  {
    key: 'fmc',
    title: 'SkellyCam -> FreeMoCap handoff and FreeMoCap UI tap',
    prompt: `Map how FreeMoCap consumes SkellyCam frames. Cover: how freemocap embeds/launches skellycam (imports, same process, app composition in freemocap/app/), exactly where frames cross from SkellyCam's ring buffer into FreeMoCap code (the realtime pipeline camera_node / realtime_pipeline / aggregator / skeleton inference nodes): which skellycam API/class they call, whether they attach to the same shared memory, read latest vs next, copy or view, per-camera processes, how results (keypoints, charuco observations) flow onward; what control messages FreeMoCap sends to SkellyCam (start/stop recording, camera config) and how; how the FreeMoCap UI (freemocap-ui/ + freemocap/api/websocket/websocket_server.py, binary_keypoints_protocol.py) taps outputs - does it receive images, keypoints, or both, and from where; posthoc pipelines that read recorded videos back from disk (video_node etc.) only as far as they touch frame transport. IMPORTANT: freemocap's venv runs skellycam at commit 777b058c (installed copy in ${FMC}\\.venv\\Lib\\site-packages\\skellycam); read the skellycam code FreeMoCap actually calls from that installed copy, and note where it differs from SkellyCam HEAD 23ccbf20. Exact line refs throughout (use repo freemocap-venv-skellycam-777b058c for refs into the installed copy, with a permalink to github.com/freemocap/skellycam/blob/777b058ceafb578c55092179506cd8a925a38b50/...).`,
  },
]

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    area: { type: 'string' },
    claim_verdicts: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          verdict: { type: 'string', enum: ['confirmed', 'corrected', 'refuted', 'unverifiable'] },
          final_statement: { type: 'string', description: 'the statement as it should appear in the report (corrected if needed)' },
          refs: { type: 'array', items: REF_SCHEMA },
          note: { type: 'string' },
        },
        required: ['id', 'verdict', 'final_statement', 'refs'],
      },
    },
    copy_verdicts: { type: 'array', items: { type: 'object', properties: { where: { type: 'string' }, verdict: { type: 'string', enum: ['confirmed', 'corrected', 'refuted'] }, final: { type: 'string' }, refs: { type: 'array', items: REF_SCHEMA } }, required: ['where', 'verdict', 'final', 'refs'] } },
    missed: { type: 'array', description: 'important facts the mapper missed', items: { type: 'object', properties: { statement: { type: 'string' }, refs: { type: 'array', items: REF_SCHEMA, minItems: 1 } }, required: ['statement', 'refs'] } },
    corrected_flow_steps: { type: 'array', items: { type: 'object', properties: { process_or_thread: { type: 'string' }, action: { type: 'string' }, to: { type: 'string' }, ref: { type: 'string' } }, required: ['process_or_thread', 'action'] } },
    risk_verdicts: { type: 'array', items: { type: 'object', properties: { priority: { type: 'string' }, risk: { type: 'string' }, verdict: { type: 'string', enum: ['confirmed', 'corrected', 'refuted'] }, refs: { type: 'array', items: REF_SCHEMA } }, required: ['priority', 'risk', 'verdict', 'refs'] } },
  },
  required: ['area', 'claim_verdicts', 'copy_verdicts', 'missed', 'corrected_flow_steps', 'risk_verdicts'],
}

const RESEARCH_SCHEMA = {
  type: 'object',
  properties: {
    topic: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          practice: { type: 'string' },
          why_it_matters: { type: 'string' },
          applicability_to_skellycam: { type: 'string' },
          quantitative_evidence: { type: 'string', description: 'numbers from the sources, with units; empty if none' },
          sources: { type: 'array', items: { type: 'object', properties: { title: { type: 'string' }, url: { type: 'string' } }, required: ['title', 'url'] }, minItems: 1 },
        },
        required: ['practice', 'why_it_matters', 'applicability_to_skellycam', 'sources'],
      },
    },
    bandwidth_math: { type: 'string', description: 'worked numbers for 5 cams x 60 fps at 720p and 1080p: raw bytes/s, memcpy cost, disk bytes/s raw vs MJPEG vs H.264' },
    caveats: { type: 'array', items: { type: 'string' } },
  },
  required: ['topic', 'findings', 'bandwidth_math', 'caveats'],
}

const BENCH_SCHEMA = {
  type: 'object',
  properties: {
    stage: { type: 'string' },
    environment: { type: 'string', description: 'CPU model, cores, RAM, disk model/type, OS build, Python, numpy, opencv, compiler versions; where recorded on disk' },
    scripts: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, purpose: { type: 'string' }, command: { type: 'string' } }, required: ['path', 'purpose', 'command'] } },
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          config: { type: 'string', description: 'cameras, resolution, fps target, frames, repetitions' },
          metric: { type: 'string' },
          value: { type: 'string', description: 'median (and p99 / min-max where relevant) with units' },
          meets_5x60: { type: 'string', enum: ['yes', 'no', 'n/a'] },
          output_file: { type: 'string' },
          script: { type: 'string' },
        },
        required: ['name', 'config', 'metric', 'value', 'meets_5x60', 'output_file', 'script'],
      },
    },
    findings: { type: 'array', items: { type: 'object', properties: { statement: { type: 'string' }, evidence: { type: 'string', description: 'result names + output files and/or code refs' } }, required: ['statement', 'evidence'] } },
    limitations: { type: 'array', items: { type: 'string' } },
  },
  required: ['stage', 'environment', 'scripts', 'results', 'findings', 'limitations'],
}

const BENCH_RULES = `
BENCHMARK RULES
- Put all scripts, a README.md for your sub-folder, and all result files (JSON + a human-readable .txt/.md) under ${BENCH}\\<your-subfolder>\\. Create the folders. Large temporary video files go under ${SCRATCH}\\bench_tmp\\ and must be deleted when done (record their sizes in results first). Never write into the repos' source trees outside ${BENCH}.
- Import and exercise the REAL SkellyCam classes/functions wherever the thing being measured is SkellyCam behaviour (from the SkellyCam venv: run from ${SK} with "uv run python <script>" or ${SK}\\.venv\\Scripts\\python.exe). If something needs a package not in that venv, create a separate venv under ${BENCH}\\.venv-bench with uv (uv venv + uv pip install) and say so.
- Use synthetic frames (random or gradient uint8) unless real cameras are attached; you may check (e.g. a quick cv2 probe or skellycam detection) and if cameras exist, a short real-camera run is a bonus, not a requirement.
- Each measurement: warm-up, >=5 repetitions or >=10 s of steady state, report median and p99 (or min/max), units, and frames/s and GB/s where meaningful. Record environment (CPU model via PowerShell Get-CimInstance Win32_Processor, RAM, disk model via Get-PhysicalDisk, OS build, package versions) into an environment file.
- Benchmarks of multi-process pipelines must use real separate processes (multiprocessing spawn on Windows) the way SkellyCam does.
- For every finding, the evidence must name the result row and output file. Be honest: if something could not be measured, say so in limitations. Do not extrapolate without labelling it as extrapolation.
- Nothing else heavy is running on the machine while you benchmark; do not start background jobs that outlive your task.
`

// ---------- Research (independent; starts immediately) ----------
const researchP = parallel([
  () => agent(`${CONTEXT}
You are a research agent. Use WebSearch (load it with ToolSearch "select:WebSearch,WebFetch" first) and WebFetch to OPEN every page you cite (a search snippet is not a source).
Topic: BEST PRACTICES FOR HIGH-THROUGHPUT MULTI-CAMERA VIDEO CAPTURE/RECORDING PIPELINES, specifically as they apply to a Python app that captures 5 USB webcams at 60+ fps, keeps them frame-synchronised, writes every frame to disk (no drops allowed), and streams previews to a UI and to a realtime pose-estimation pipeline.
Cover at least: zero-copy capture (Media Foundation / DirectShow on Windows, V4L2 mmap/DMABUF on Linux, capturing directly into a preallocated/shared buffer, e.g. OpenCV VideoCapture.read(image=preallocated)); shared-memory ring buffer design (SPSC/SPMC, lock-free, seqlocks/sequence counters, cache-line padding, per-reader cursors, slot sizing, hugepages/large pages); lossless-recording design (separating the must-not-drop record path from best-effort preview paths, backpressure vs overwrite policies, sizing buffers from worst-case writer stalls, detecting and accounting drops); MJPEG passthrough (recording the camera's compressed MJPEG stream without decode/re-encode) vs decode+re-encode; hardware encoders (NVENC on the RTX 3070, QSV, AMF) via FFmpeg/PyAV/GStreamer and their per-session limits; disk throughput (raw BGR vs MJPEG vs H.264/H.265 byte rates, sequential-write behaviour on NVMe, write-behind buffering, unbuffered I/O on Windows); preview path best practices (downscale before encode, GPU JPEG, libjpeg-turbo/TurboJPEG vs cv2.imencode, latest-frame-wins, WebCodecs/createImageBitmap in the browser); how established systems do it (GStreamer, FFmpeg, NVIDIA DeepStream/Holoscan, ROS 2 with iceoryx/zero-copy loaned messages, OBS) and Python-specific constraints (GIL, multiprocessing.shared_memory, numpy views, pickling cost of mp.Queue).
Do the bandwidth math for 5x60 fps at 1280x720 and 1920x1080.`, { label: 'research:best-practices', phase: 'Research', schema: RESEARCH_SCHEMA }),
  () => agent(`${CONTEXT}
You are a research agent. Use WebSearch (load it with ToolSearch "select:WebSearch,WebFetch" first) and WebFetch to OPEN every page you cite.
Topic: WOULD PORTING PARTS OF A PYTHON MULTI-CAMERA FRAME PIPELINE TO C++ RAISE THROUGHPUT, AND WHERE? Find evidence on: Python per-call/per-frame interpreter overhead vs the cost of the bulk work (numpy memcpy and cv2 calls already run in C and release the GIL - which ones do and don't); the GIL and its effect on multi-threaded capture loops (and the free-threaded 3.13/3.14 builds); multiprocessing.shared_memory overheads vs native shm (CreateFileMapping on Windows); pybind11 / nanobind / Cython zero-copy buffer-protocol bindings and their call overhead; lock-free C++ IPC libraries (iceoryx2, Boost.Interprocess, cpp-ipc) and their measured latencies; existing C++ capture libraries with Python bindings (openpnp-capture - note local copies at C:\\Users\\Dom\\GitHub\\freemocap\\openpnp-capture and openpnp-capture-python, read their READMEs and binding approach) and whether they allow capture into caller-owned memory; documented case studies where moving a Python video pipeline to C++/Rust changed throughput (with numbers). Also: memory bandwidth ceilings (memcpy GB/s on a modern desktop) which bound BOTH languages equally. Conclude with a hypothesis list of exactly which hot paths could gain from C++ and which cannot, for the benchmark agent to test.`, { label: 'research:python-vs-cpp', phase: 'Research', schema: RESEARCH_SCHEMA }),
])

// ---------- Map -> Verify (pipelined per area) ----------
const mapP = pipeline(
  AREAS,
  a => agent(`${CONTEXT}
You are a code-mapping agent. Area: ${a.title}.
${a.prompt}
Read the code yourself (Grep/Read/Glob, git log/git show allowed). Every claim needs refs with exact line ranges you actually read; give permalinks in the forms above. Count frame copies precisely. Prefer many small precise claims over a few vague ones (aim for 15-40 claims). If something is ambiguous, you may write and run a tiny throwaway script in ${SCRATCH} to confirm behaviour (e.g. whether a function returns a view or a copy) and cite the script path + output.`, { label: `map:${a.key}`, phase: 'Map', schema: MAP_SCHEMA }),
  (m, a) => agent(`${CONTEXT}
You are an adversarial VERIFIER for the area "${a.title}". Another agent produced the map below. Your job is to try to REFUTE each claim: open every cited file at the cited lines and check the statement is exactly what the code does (right function, right line numbers, right repo/version, no overstated generalisation). Fix line numbers that are off. Mark refuted any claim the code does not support. Check every frame_copies entry (is it really a full-image copy? are there copies missed?) and every risk. Then add important facts the mapper MISSED (with refs), especially anything relevant to: dropping frames on the disk-write path, throughput limits at 5x60fps, and avoidable copies. You may run tiny scripts in ${SCRATCH} to confirm view-vs-copy behaviour; cite script + output. Default to "unverifiable" rather than "confirmed" if you could not check it.
MAP TO VERIFY (JSON):
${JSON.stringify(m)}`, { label: `verify:${a.key}`, phase: 'Verify', schema: VERIFY_SCHEMA }).then(v => ({ area: a.key, title: a.title, map: m, verification: v })),
)

const [research, maps] = await Promise.all([researchP, mapP])
const verifiedMaps = maps.filter(Boolean)
log(`Mapped+verified ${verifiedMaps.length}/${AREAS.length} areas; research agents returned ${research.filter(Boolean).length}/2`)

// Compact verified view for downstream agents
const verifiedDigest = verifiedMaps.map(x => ({
  area: x.title,
  summary: x.map ? x.map.summary : '',
  claims: x.verification ? x.verification.claim_verdicts.filter(c => c.verdict !== 'refuted') : [],
  missed: x.verification ? x.verification.missed : [],
  copies: x.verification ? x.verification.copy_verdicts.filter(c => c.verdict !== 'refuted') : [],
  flow: x.verification ? x.verification.corrected_flow_steps : [],
  risks: x.verification ? x.verification.risk_verdicts.filter(r => r.verdict !== 'refuted') : [],
  version_diffs: x.map ? x.map.version_diffs_777b058c : '',
}))
const DIGEST = JSON.stringify(verifiedDigest)
const RESEARCH = JSON.stringify(research.filter(Boolean))

// ---------- Benchmarks (strictly sequential to avoid timing contention) ----------
phase('Benchmark')
const baseline = await agent(`${CONTEXT}${BENCH_RULES}
You are the BASELINE benchmark agent. Sub-folder: baseline\\. Measure the CURRENT SkellyCam pipeline as it exists at HEAD 23ccbf20, using its real classes, to establish what throughput it achieves today and where the time goes. Use the verified code map below to pick the exact classes/functions. At minimum:
 (a) ring-buffer WRITE: per-frame write latency and max sustained frames/s for 1..5 cameras at 1280x720 and 1920x1080 BGR (one writer process per camera as SkellyCam does), through the real SkellyCam shared-memory classes;
 (b) ring-buffer READ for each reader style the code uses (latest vs next, view vs copy, multi-frame assembly), per-frame cost;
 (c) the record path: the real SkellyCam video-writing code/settings (codec, container) for 5 cameras at both sizes - can it sustain 60 fps per camera? CPU % used;
 (d) the UI path: the real encode/serialisation used to send frames to the UI, per multi-frame cost at 5 cameras;
 (e) an end-to-end synthetic run that mimics SkellyCam's real process topology: 5 producer processes at 60 fps into the shm ring buffer + the recorder consumer (+ UI consumer if feasible) for >=30 s; report achieved fps per camera, frames written to disk vs frames produced (any drops/overwrites?), latency, and how large the writer lag got;
 (f) count bytes copied per frame on the record path and the UI path, by instrumenting or by measurement, and cross-check against the verified frame_copies list.
Also run SkellyCam's existing diagnostics/tests that touch this path (skellycam/system/diagnostics/check_shm_speed.py, skellycam/tests/test_shared_memory.py) if runnable, and record their output.
VERIFIED CODE MAP (JSON): ${DIGEST}`, { label: 'bench:baseline', phase: 'Benchmark', schema: BENCH_SCHEMA })

const prototypes = await agent(`${CONTEXT}${BENCH_RULES}
You are the PROTOTYPE benchmark agent. Sub-folder: prototypes\\. Using the verified code map, the baseline results, and the research below, build small standalone Python prototypes of the most promising optimisations and MEASURE them against the baseline on the same machine and configs (5 cameras, 1280x720 and 1920x1080, 60 fps target). Candidates (pick at least 5, add others the evidence suggests):
 - capture/write directly into the shared-memory slot with no intermediate ndarray (e.g. cv2.VideoCapture.read(image=slot_view) - test with a real camera if one is attached, otherwise test the equivalent decode-into-preallocated path, e.g. cv2.imdecode into a preallocated dst, and note it);
 - zero-copy reads: numpy views on slots + sequence-counter (seqlock) validation instead of copying, and its torn-read safety;
 - lossless record path: per-camera writer with a guaranteed-no-overwrite policy (producer blocks or spills when the recorder lags, explicit drop accounting) vs the current policy; measure worst-case writer stall it tolerates given slot count;
 - MJPEG passthrough recording (store the camera's compressed JPEG bytes; measure bytes/s and CPU vs decode+encode) - simulate MJPEG frames by pre-encoding synthetic frames with cv2.imencode at quality 90;
 - hardware encode: NVENC h264/hevc via PyAV or an ffmpeg subprocess fed from shm (if ffmpeg/av available or installable into the bench venv) vs the current software writer; check how many concurrent NVENC sessions the RTX 3070 driver allows;
 - UI path: downscale-before-encode, TurboJPEG (PyTurboJPEG) vs cv2.imencode, latest-frame-wins throttling;
 - process/thread topology alternatives (writer threads vs processes; GIL impact).
Every prototype must report the same metrics as the baseline so they are directly comparable, plus copies per frame.
BASELINE RESULTS (JSON): ${JSON.stringify(baseline)}
RESEARCH (JSON): ${RESEARCH}
VERIFIED CODE MAP (JSON): ${DIGEST}`, { label: 'bench:prototypes', phase: 'Benchmark', schema: BENCH_SCHEMA })

const cpp = await agent(`${CONTEXT}${BENCH_RULES}
You are the C++ COMPARISON benchmark agent. Sub-folder: cpp\\. Question to answer with code and measurements: would porting SkellyCam hot paths to C++ yield higher throughput, and if so where and why?
Build with MSVC (call "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat" then cl /O2 /std:c++20 /EHsc; or CMake if available). Provide a build script (build.bat or build.ps1) so others can reproduce. Implement C++ equivalents of the SAME workloads the Python baseline/prototypes measured, with identical configs and frame counts, and compare head-to-head:
 1. shared-memory ring buffer write + read across processes (CreateFileMapping/MapViewOfFile), SPSC with per-slot sequence counters, 5 producers x 60 fps and an unthrottled max-rate run, at 1280x720 and 1920x1080 - compare against the real SkellyCam Python ring buffer numbers;
 2. raw memcpy bandwidth (single and multi-threaded) - the hardware ceiling both languages share; compare to numpy np.copyto / slot assignment;
 3. per-frame fixed overhead: tiny frames (e.g. 64x64) at max rate to isolate interpreter/call overhead vs bulk-copy cost;
 4. the encode/record step if a fair C++ comparison is possible (e.g. OpenCV C++ VideoWriter or libjpeg-turbo if available via the opencv-python bundled libs is NOT possible - if no C++ OpenCV/FFmpeg SDK is available, say so and explain that encode cost is the same native code in both languages, citing evidence);
 5. optionally a pybind11/nanobind or ctypes-exposed C++ ring buffer called from Python, to show the hybrid option (if pybind11/nanobind can be pip-installed into ${BENCH}\\.venv-bench).
Test the hypotheses from the Python-vs-C++ research below explicitly: for each, state confirmed/refuted with result rows. Give a clear verdict: where C++ wins, by how much, whether that matters for 5x60fps given the baseline numbers, and where it does not (because time is in memcpy/encode/disk that is already native).
BASELINE RESULTS (JSON): ${JSON.stringify(baseline)}
PROTOTYPE RESULTS (JSON): ${JSON.stringify(prototypes)}
RESEARCH (JSON): ${RESEARCH}`, { label: 'bench:cpp', phase: 'Benchmark', schema: BENCH_SCHEMA })

// ---------- Recommend ----------
const REC_SCHEMA = {
  type: 'object',
  properties: {
    headline: { type: 'string', description: 'the answer in 2-3 sentences with the key numbers' },
    current_state_verdict: { type: 'string', description: 'does the current pipeline meet 5x60 fps without drops? at which sizes? evidence' },
    recommendations: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          rank: { type: 'integer' },
          title: { type: 'string' },
          priorities_served: { type: 'array', items: { type: 'string', enum: ['P1', 'P2', 'P3'] } },
          change: { type: 'string', description: 'what to change, concretely, in which files' },
          code_refs: { type: 'array', items: REF_SCHEMA },
          expected_impact: { type: 'string', description: 'measured where possible (result rows + files), else labelled estimate' },
          evidence: { type: 'string' },
          risks_tradeoffs: { type: 'string' },
          effort: { type: 'string', enum: ['S', 'M', 'L', 'XL'] },
        },
        required: ['rank', 'title', 'priorities_served', 'change', 'code_refs', 'expected_impact', 'evidence', 'risks_tradeoffs', 'effort'],
      },
    },
    cpp_verdict: { type: 'string', description: 'port or not, which parts, why, with result rows' },
    not_recommended: { type: 'array', items: { type: 'object', properties: { idea: { type: 'string' }, why_not: { type: 'string' } }, required: ['idea', 'why_not'] } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['headline', 'current_state_verdict', 'recommendations', 'cpp_verdict', 'not_recommended', 'open_questions'],
}

phase('Recommend')
const ALL_BENCH = JSON.stringify({ baseline, prototypes, cpp })
const rec = await agent(`${CONTEXT}
You are the SYNTHESIS agent. Review the verified code map, research, and the three benchmark stages, then produce a ranked optimisation plan for the frame ring buffer process. Rank strictly by the priorities: P1 disk writes never drop (anything that fixes or guarantees this ranks first), then P2 throughput toward 5x60 fps, then P3 removing frame copies. Every recommendation must cite code refs for what changes and benchmark result rows/output files for its impact (or clearly label an estimate). Include the C++ verdict. You may read files under ${BENCH} to check the numbers. Be concrete about file/class/function changes.
VERIFIED CODE MAP: ${DIGEST}
RESEARCH: ${RESEARCH}
BENCHMARKS: ${ALL_BENCH}`, { label: 'recommend', phase: 'Recommend', schema: REC_SCHEMA })

// ---------- Critique ----------
const CRIT_SCHEMA = {
  type: 'object',
  properties: {
    lens: { type: 'string' },
    issues: { type: 'array', items: { type: 'object', properties: { target: { type: 'string', description: 'recommendation title / claim id / result name' }, severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, problem: { type: 'string' }, fix: { type: 'string' }, evidence: { type: 'string' } }, required: ['target', 'severity', 'problem', 'fix', 'evidence'] } },
    reproduced: { type: 'array', items: { type: 'object', properties: { result: { type: 'string' }, original: { type: 'string' }, rerun: { type: 'string' }, within_tolerance: { type: 'boolean' }, command: { type: 'string' } }, required: ['result', 'original', 'rerun', 'within_tolerance', 'command'] } },
    summary: { type: 'string' },
  },
  required: ['lens', 'issues', 'reproduced', 'summary'],
}

phase('Critique')
const critiques = await parallel([
  () => agent(`${CONTEXT}
You are an adversarial EVIDENCE critic. Go through the recommendations and the benchmark findings below and try to break them: any assertion without a code ref or a reproducible result; numbers that do not match the output files under ${BENCH} (open them); benchmarks that do not measure what they claim (e.g. synthetic setup that skips a real SkellyCam step, unfair C++ vs Python comparisons, caching effects, files written to RAM cache rather than disk, too-short runs); recommendations whose cited code refs do not support them (open the files). Leave "reproduced" empty.
RECOMMENDATIONS: ${JSON.stringify(rec)}
BENCHMARKS: ${ALL_BENCH}`, { label: 'critic:evidence', phase: 'Critique', schema: CRIT_SCHEMA }),
  () => agent(`${CONTEXT}
You are an adversarial PRIORITY critic focused on P1 (disk writes must never drop) and P3 (no unnecessary copies). Check the recommendations against the verified code map: does the plan actually guarantee no dropped disk frames under writer stalls (disk hiccup, antivirus scan, GC pause, NVENC session failure, process crash)? Are there remaining overwrite/drop paths in the code that the plan does not address? Does any recommendation trade P1 for P2? Does any add a copy? Are frame-perfect sync guarantees (same frame count on all cameras) preserved? Cite code refs. Leave "reproduced" empty.
RECOMMENDATIONS: ${JSON.stringify(rec)}
VERIFIED CODE MAP: ${DIGEST}`, { label: 'critic:priorities', phase: 'Critique', schema: CRIT_SCHEMA }),
])
const repro = await agent(`${CONTEXT}${BENCH_RULES}
You are the REPRODUCIBILITY checker. Re-run the headline benchmarks from their READMEs exactly as documented (fresh shell, documented commands only) and compare to the reported values: at minimum the baseline end-to-end 5-camera run, the best prototype for the record path, the best prototype for the UI path, and the C++ vs Python ring-buffer comparison (rebuild C++ with its build script). Record each re-run in ${BENCH}\\reproducibility\\ (outputs + a summary.md). Tolerance: within 15% for throughput, same conclusion for pass/fail at 5x60. Report any README step that did not work as written as an issue.
BENCHMARKS: ${ALL_BENCH}`, { label: 'critic:reproduce', phase: 'Critique', schema: CRIT_SCHEMA })

return { verifiedMaps, research: research.filter(Boolean), baseline, prototypes, cpp, rec, critiques: critiques.filter(Boolean), repro }
