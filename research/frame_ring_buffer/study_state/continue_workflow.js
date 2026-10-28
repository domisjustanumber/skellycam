export const meta = {
  name: 'frame-ring-buffer-analysis-continue',
  description: 'Continue the frame ring buffer study from saved state: prototypes -> C++ -> recommend -> critique',
  phases: [
    { title: 'Benchmark', detail: 'serialized: prototypes -> C++' },
    { title: 'Recommend', detail: 'optimisation plan against the 3 priorities' },
    { title: 'Critique', detail: 'evidence critic, priority critic, reproducibility re-run' },
  ],
}

// Continuation of original_workflow.js (run wf_c08d445c-b09, stopped 2026-10-25 during bench:prototypes).
// Map, Verify, Research and bench:baseline are finished; their outputs live in STATE as JSON files.
// Every stage agent here reads its inputs from STATE and writes its own result to STATE/<stage>_result.json,
// so a later run can skip finished stages: pass args = {skip: ['prototypes', 'cpp', ...]}.

const SK = 'C:\\Users\\Dom\\GitHub\\freemocap\\skellycam'
const FMC = 'C:\\Users\\Dom\\GitHub\\freemocap\\freemocap'
const BENCH = 'C:\\Users\\Dom\\GitHub\\freemocap\\skellycam\\research\\frame_ring_buffer'
const STATE = BENCH + '\\study_state'
const SCRATCH = 'C:\\Users\\Dom\\AppData\\Local\\Temp\\skellycam_frame_pipeline_tmp'
const skip = new Set((args && args.skip) || [])

const CONTEXT = `
CONTEXT (shared by every agent in this study)
Goal of the overall study: a report on how the SkellyCam frame ring buffer (shared memory) moves images from cameras to disk, to the UIs, and from SkellyCam into FreeMoCap; and an evidence-backed plan to raise throughput.
Solution priorities, in order: (1) disk writes must NEVER drop frames; (2) highest possible throughput, benchmark goal 5 cameras at 60+ fps (1280x720 and 1920x1080 BGR are the two reference sizes; say which you used); (3) do not copy video frames unless absolutely necessary.
HARD RULE: make no assertion without either a code reference (file + line range, preferably a GitHub permalink) or a pointer to a benchmark/test output file plus the script and command that reproduce it. If you cannot back a statement, mark it as an open question instead.

Repositories (local checkouts; Windows 11, Git Bash and PowerShell available):
- SkellyCam: ${SK}  branch development, study pinned to HEAD 23ccbf208e43879bfc74fc01049e5af2a623933d. If the checkout has moved past that commit, measure against 23ccbf20 (git worktree in ${SCRATCH}) or state the commit you used.
  Permalink form: https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/<path>#L<a>-L<b>
- FreeMoCap: ${FMC}  study pinned to 5632778af10e22befd4ec0a719ba844f14a84e93; its .venv runs skellycam 2.0.0a6 at commit 777b058ceafb578c55092179506cd8a925a38b50.
  Permalink form: https://github.com/freemocap/freemocap/blob/5632778af10e22befd4ec0a719ba844f14a84e93/<path>#L<a>-L<b>
- Sibling prior art only (label it if mentioned): C:\\Users\\Dom\\GitHub\\freemocap\\skellycam-shm-ui, skellycam-opnpc-mf, openpnp-capture, openpnp-capture-python.
Toolchain: Python 3.12 via uv (SkellyCam venv at ${SK}\\.venv). Bench-only packages go in ${BENCH}\\.venv-bench (already exists). MSVC: "C:\\Program Files\\Microsoft Visual Studio\\2022\\Community\\VC\\Auxiliary\\Build\\vcvars64.bat". GPU: NVIDIA RTX 3070. CPU i7-14700K, 28 logical.
Do NOT modify any source file in either repo. Do not commit, push, or install packages into the repos' own venvs. Scratch space: ${SCRATCH} (create it).

SAVED STUDY STATE (read these files; they are the outputs of the earlier stages):
- ${STATE}\\verified_digest.json : verified code map (claims with refs, frame copies, flow steps, risks) for 5 areas. Full map + verifier output: verified_maps.json.
- ${STATE}\\research.json : two research results (best practices; Python vs C++ hypotheses), with sources.
- ${STATE}\\baseline_result.json : baseline benchmark result; scripts and outputs under ${BENCH}\\baseline\\ (read its README.md).
- Later stages, when present: prototypes_result.json, cpp_result.json, recommend_result.json.
PROVISIONAL: read ${BENCH}\\PROVISIONAL.md. Record the machine load (CPU %, memory %, top processes) at the start and end of every benchmark, and say whether the machine was idle. Results measured with background load must be labelled provisional.
`

const BENCH_RULES = `
BENCHMARK RULES
- Put all scripts, a README.md for your sub-folder, and all result files (JSON + a human-readable .txt/.md) under ${BENCH}\\<your-subfolder>\\. Large temporary video files go under ${SCRATCH}\\bench_tmp\\ and must be deleted when done (record their sizes first). Never write into the repos' source trees outside ${BENCH}.
- Import and exercise the REAL SkellyCam classes/functions wherever the thing measured is SkellyCam behaviour (run from ${SK} with "uv run python <script>" or ${SK}\\.venv\\Scripts\\python.exe).
- Synthetic frames unless real cameras are attached (a short real-camera run is a bonus).
- Each measurement: warm-up, >=5 repetitions or >=10 s of steady state, report median and p99 (or min/max), units, frames/s and GB/s where meaningful. Record environment into an environment file.
- Multi-process pipelines must use real separate processes (multiprocessing spawn on Windows) the way SkellyCam does.
- For every finding, the evidence must name the result row and output file. Say what could not be measured. Label extrapolations.
- Do not start background jobs that outlive your task; kill any child processes you started before you finish.
- When finished, ALSO write your complete structured result (the same object you return) as JSON to ${STATE}\\<stage>_result.json.
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

const BENCH_SCHEMA = {
  type: 'object',
  properties: {
    stage: { type: 'string' },
    environment: { type: 'string', description: 'CPU, RAM, disk, OS, Python/numpy/opencv/compiler versions, machine load at start/end, provisional or not' },
    scripts: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, purpose: { type: 'string' }, command: { type: 'string' } }, required: ['path', 'purpose', 'command'] } },
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          name: { type: 'string' },
          config: { type: 'string' },
          metric: { type: 'string' },
          value: { type: 'string', description: 'median (and p99 / min-max) with units' },
          meets_5x60: { type: 'string', enum: ['yes', 'no', 'n/a'] },
          output_file: { type: 'string' },
          script: { type: 'string' },
        },
        required: ['name', 'config', 'metric', 'value', 'meets_5x60', 'output_file', 'script'],
      },
    },
    findings: { type: 'array', items: { type: 'object', properties: { statement: { type: 'string' }, evidence: { type: 'string' } }, required: ['statement', 'evidence'] } },
    limitations: { type: 'array', items: { type: 'string' } },
  },
  required: ['stage', 'environment', 'scripts', 'results', 'findings', 'limitations'],
}

const REC_SCHEMA = {
  type: 'object',
  properties: {
    headline: { type: 'string' },
    current_state_verdict: { type: 'string' },
    recommendations: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          rank: { type: 'integer' },
          title: { type: 'string' },
          priorities_served: { type: 'array', items: { type: 'string', enum: ['P1', 'P2', 'P3'] } },
          change: { type: 'string' },
          code_refs: { type: 'array', items: REF_SCHEMA },
          expected_impact: { type: 'string' },
          evidence: { type: 'string' },
          risks_tradeoffs: { type: 'string' },
          effort: { type: 'string', enum: ['S', 'M', 'L', 'XL'] },
        },
        required: ['rank', 'title', 'priorities_served', 'change', 'code_refs', 'expected_impact', 'evidence', 'risks_tradeoffs', 'effort'],
      },
    },
    cpp_verdict: { type: 'string' },
    not_recommended: { type: 'array', items: { type: 'object', properties: { idea: { type: 'string' }, why_not: { type: 'string' } }, required: ['idea', 'why_not'] } },
    open_questions: { type: 'array', items: { type: 'string' } },
  },
  required: ['headline', 'current_state_verdict', 'recommendations', 'cpp_verdict', 'not_recommended', 'open_questions'],
}

const CRIT_SCHEMA = {
  type: 'object',
  properties: {
    lens: { type: 'string' },
    issues: { type: 'array', items: { type: 'object', properties: { target: { type: 'string' }, severity: { type: 'string', enum: ['blocker', 'major', 'minor'] }, problem: { type: 'string' }, fix: { type: 'string' }, evidence: { type: 'string' } }, required: ['target', 'severity', 'problem', 'fix', 'evidence'] } },
    reproduced: { type: 'array', items: { type: 'object', properties: { result: { type: 'string' }, original: { type: 'string' }, rerun: { type: 'string' }, within_tolerance: { type: 'boolean' }, command: { type: 'string' } }, required: ['result', 'original', 'rerun', 'within_tolerance', 'command'] } },
    summary: { type: 'string' },
  },
  required: ['lens', 'issues', 'reproduced', 'summary'],
}

phase('Benchmark')
if (!skip.has('prototypes')) {
  await agent(`${CONTEXT}${BENCH_RULES}
You are the PROTOTYPE benchmark agent (stage name: prototypes). Sub-folder: prototypes\\.
A previous prototype agent was stopped part-way. Its scripts are already in ${BENCH}\\prototypes\\ (proto_common.py, p1_write_variants.py, p2_seqlock_read.py, p3_lossless_record.py, p4_mjpeg_passthrough.py, p5_nvenc.py, p6_ui_path.py) with partial results in prototypes\\results\\, and its transcript is ${STATE}\\prototypes_partial_transcript.jsonl. Review those scripts, fix or extend them as needed, and RE-RUN all of them in this run so every result comes from the same machine state (overwrite the partial results). Then finish the remaining work.
Using the verified code map, the baseline results and the research, build small standalone Python prototypes of the most promising optimisations and MEASURE them against the baseline on the same configs (5 cameras, 1280x720 and 1920x1080, 60 fps target). Candidates (at least 5; add others the evidence suggests):
 - capture/write directly into the shared-memory slot with no intermediate ndarray (cv2.VideoCapture.read(image=slot_view) with a real camera if attached; otherwise decode-into-preallocated, e.g. cv2.imdecode into a preallocated dst, and say so). The baseline found MJPEG decode inside retrieve() is the 1080p bottleneck (44-47 fps per camera), so measure decode-off-the-capture-loop options too;
 - removing the copy.copy in put_frame (baseline: 2 full copies per frame);
 - zero-copy reads: numpy views on slots + sequence-counter (seqlock) validation, and its torn-read safety;
 - lossless record path: per-camera writer with a guaranteed-no-overwrite policy (producer blocks or spills when the recorder lags, explicit drop accounting) vs the current synchronous in-loop encode; measure the worst-case writer stall tolerated for a given slot count;
 - MJPEG passthrough recording (store the camera's JPEG bytes; bytes/s and CPU vs decode+encode), simulating MJPEG frames with cv2.imencode quality 90;
 - hardware encode: NVENC h264/hevc via PyAV or an ffmpeg subprocess fed from shm vs the current MSMF writer (baseline: about 11.7 logical CPUs at 5x1080p60); check the NVENC concurrent-session limit on this driver;
 - UI path: moving copy+resize+JPEG off the event-loop thread, downscale-before-encode, TurboJPEG vs cv2.imencode, latest-frame-wins throttling (baseline: 43.7 payloads/s at 5x1080p);
 - process/thread topology alternatives (writer threads vs processes; GIL impact).
Every prototype must report the same metrics as the baseline so they are directly comparable, plus copies per frame.`, { label: 'bench:prototypes', phase: 'Benchmark', schema: BENCH_SCHEMA })
}

if (!skip.has('cpp')) {
  await agent(`${CONTEXT}${BENCH_RULES}
You are the C++ COMPARISON benchmark agent (stage name: cpp). Sub-folder: cpp\\. Read prototypes_result.json and baseline_result.json in ${STATE} first.
Question to answer with code and measurements: would porting SkellyCam hot paths to C++ yield higher throughput, and if so where and why?
Build with MSVC (vcvars64.bat then cl /O2 /std:c++20 /EHsc, or CMake if available). Provide a build script (build.bat or build.ps1). Implement C++ equivalents of the SAME workloads the Python baseline/prototypes measured, with identical configs and frame counts, and compare head-to-head:
 1. shared-memory ring buffer write + read across processes (CreateFileMapping/MapViewOfFile), SPSC with per-slot sequence counters, 5 producers x 60 fps and an unthrottled max-rate run, at 1280x720 and 1920x1080, against the real SkellyCam Python ring buffer numbers;
 2. raw memcpy bandwidth (single and multi-threaded), the hardware ceiling both languages share, vs numpy np.copyto / slot assignment;
 3. per-frame fixed overhead: tiny frames (e.g. 64x64) at max rate to isolate interpreter/call overhead vs bulk-copy cost;
 4. the decode/encode/record step if a fair C++ comparison is possible; if no C++ OpenCV/FFmpeg/libjpeg-turbo SDK is available, say so and explain with evidence that encode/decode is the same native code in both languages;
 5. optionally a pybind11/nanobind or ctypes-exposed C++ ring buffer called from Python (install into ${BENCH}\\.venv-bench), to show the hybrid option.
Test each hypothesis from the Python-vs-C++ research (research.json) explicitly: confirmed/refuted with result rows. Verdict: where C++ wins, by how much, whether that matters for 5x60fps given the baseline, and where it does not.`, { label: 'bench:cpp', phase: 'Benchmark', schema: BENCH_SCHEMA })
}

phase('Recommend')
let rec = null
if (!skip.has('recommend')) {
  rec = await agent(`${CONTEXT}
You are the SYNTHESIS agent (stage name: recommend). Read verified_digest.json, research.json, baseline_result.json, prototypes_result.json and cpp_result.json in ${STATE}, and check numbers against the output files under ${BENCH}. Produce a ranked optimisation plan for the frame ring buffer process. Rank strictly by priority: P1 disk writes never drop first, then P2 throughput toward 5x60 fps, then P3 removing frame copies. Every recommendation cites code refs for what changes and benchmark result rows/output files for its impact (or is labelled an estimate). Carry the provisional label on any number measured under load. Include the C++ verdict. Be concrete about file/class/function changes.
When finished, ALSO write your result as JSON to ${STATE}\\recommend_result.json.`, { label: 'recommend', phase: 'Recommend', schema: REC_SCHEMA })
}

phase('Critique')
const INPUTS = `Read ${STATE}\\recommend_result.json, baseline_result.json, prototypes_result.json, cpp_result.json and verified_digest.json.`
const critiques = await parallel([
  () => agent(`${CONTEXT}
You are an adversarial EVIDENCE critic. ${INPUTS} Try to break the recommendations and benchmark findings: assertions without a code ref or reproducible result; numbers that do not match the output files under ${BENCH} (open them); benchmarks that do not measure what they claim (synthetic setups that skip a real SkellyCam step, unfair C++ vs Python comparisons, caching effects, files landing in RAM cache rather than disk, too-short runs, background load); recommendations whose code refs do not support them (open the files). Leave "reproduced" empty. Also write your result as JSON to ${STATE}\\critic_evidence_result.json.`, { label: 'critic:evidence', phase: 'Critique', schema: CRIT_SCHEMA }),
  () => agent(`${CONTEXT}
You are an adversarial PRIORITY critic focused on P1 (disk writes must never drop) and P3 (no unnecessary copies). ${INPUTS} Does the plan guarantee no dropped disk frames under writer stalls (disk hiccup, antivirus scan, GC pause, NVENC session failure, process crash, the app-wide kill flag)? Which overwrite/drop paths in the code does it leave unaddressed? Does any recommendation trade P1 for P2, or add a copy? Is frame-perfect sync (same frame count on all cameras) preserved? Cite code refs. Leave "reproduced" empty. Also write your result as JSON to ${STATE}\\critic_priorities_result.json.`, { label: 'critic:priorities', phase: 'Critique', schema: CRIT_SCHEMA }),
])
const repro = await agent(`${CONTEXT}${BENCH_RULES}
You are the REPRODUCIBILITY checker (stage name: critic_reproduce). Re-run the headline benchmarks from their READMEs exactly as documented (fresh shell, documented commands only) and compare to the reported values: at minimum the baseline end-to-end 5-camera run, the best record-path prototype, the best UI-path prototype, and the C++ vs Python ring-buffer comparison (rebuild C++ with its build script). Record each re-run in ${BENCH}\\reproducibility\\ (outputs + summary.md). Tolerance: within 15% for throughput, same pass/fail at 5x60. Note machine load for each run, since load differences can explain variance. Report any README step that did not work as written.`, { label: 'critic:reproduce', phase: 'Critique', schema: CRIT_SCHEMA })

return { rec, critiques: critiques.filter(Boolean), repro, note: 'Stage results are also in ' + STATE }
