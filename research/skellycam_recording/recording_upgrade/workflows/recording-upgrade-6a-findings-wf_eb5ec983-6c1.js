export const meta = {
  name: 'recording-upgrade-6a-findings',
  description: 'Recording upgrade study 6A.4: FINDINGS draft -> provenance + method verifiers -> revise, for 7 topics (text returned, saved by main session)',
  phases: [
    { title: 'Findings', detail: 'draft FINDINGS text per topic' },
    { title: 'Verify', detail: 'provenance + method verifiers per topic' },
    { title: 'Revise', detail: 'apply verifier reports, return final text' },
  ],
}

const ROOT = 'C:/Users/Dom/GitHub/freemocap/skellycam'
const STUDY = 'research/skellycam_recording/recording_upgrade'
const RAWD = 'C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109'
const SCR = 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad'
const OLD_E45 = 'C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/106dc0c8-f977-4082-9d8d-367e9a9f721d/scratchpad/shared/electron-latest/node_modules/electron/dist/electron.exe'

const CTX = `You are one agent in a research study for skellycam. Repo root ${ROOT} (branch dom/research), Windows 11 machine "Gerald". The study handoff is ${STUDY}/HANDOFF.md - read sections 1, 3, 4 and 5 first (requirements in section 1 override anything else). Goals G1-G9 and the hardware target are listed there.
BACKGROUND (verified against code - treat as true, do not re-check): research/skellycam_recording/REPORT.md and research/skellycam_recording/results/real_recording_20261109/ describe today's recording system.

EVIDENCE RULE (hardest requirement): no assertion without hard evidence or a test result. Label every claim: measured (a result file - cite its path), source (primary source - URL, exact short quote, accessed 2026-11-09), code (file:line), inferred (minimal, clearly marked). No numbers from memory. Blogs/forums are leads only. Unverifiable -> NOT VERIFIED. Load WebFetch/WebSearch via ToolSearch when needed.

VERSIONS: the implementation under test is PyAV 19.0.2 (its bundled FFmpeg). Results made with PyAV 18.0.0 (skellycam venv) are BACKGROUND ONLY - label them so ("measured, PyAV 18 - background"). Quick functional re-checks with PyAV 19.0.2 are allowed: uv run --script with PEP 723 "# dependencies = [\\"av==19.0.2\\", \\"numpy\\"]". ffmpeg/ffprobe 9.0.2 on PATH may only INSPECT files. Never modify the skellycam venv, skellycam-ui or the freemocap repo. Electron 35.7.5: ${ROOT}/skellycam-ui/node_modules/electron/dist/electron.exe; Electron 45.2.3: ${OLD_E45}; unset ELECTRON_RUN_AS_NODE before launching.
BENCH STATE: timed benches for most topics have NOT run yet; they run tonight from 23:00 on a quiet machine, PyAV 19.0.2 only. write_throughput's BENCH.md and uncompressed_intra's bench are CONTAMINATED (other agents/sessions loaded the CPU): their numbers are lower bounds / indicative only and must be flagged; python_integration's bench was killed. In FINDINGS, put timing questions in a 'Pending tonight's bench' list instead of guessing. The Intel UHD 770 iGPU was absent during the earlier investigations (QSV failures were caused by that) and is present again now.
TIMING RULE NOW: other agents run concurrently. Do NOT produce timing numbers. Functional checks < 1 min CPU only.
PATHS: media only under ${RAWD}/<topic>/; temp in ${SCR}/<topic>/. Do not git commit. Never use SendMessage. Research stays local Markdown, never Claude Docs.
WRITE GUARD: a harness guard blocks subagent writes to files named FINDINGS.md. Never write FINDINGS.md and never work around it (no Bash/other-name tricks). Return FINDINGS text in your structured output. VERIFY_*.md files are fine to write.
STYLE: plain, concise Markdown; tables for comparisons; one claim per bullet with label and citation.`

const TOPICS = [
  { key: 'jpeg_passthrough', goals: 'G1, G5' },
  { key: 'write_throughput', goals: 'G5' },
  { key: 'crash_resilience', goals: 'G2' },
  { key: 'overlays', goals: 'G3' },
  { key: 'gpu_encode', goals: 'G6, G7' },
  { key: 'chromium_sync_scrub', goals: 'G9' },
  { key: 'python_integration', goals: 'G1-G9 integration' },
]

const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    findings_md: { type: 'string', description: 'the COMPLETE FINDINGS.md text' },
    summary: { type: 'string', description: '15-line summary' },
  },
  required: ['findings_md', 'summary'],
}
const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    refuted: { type: 'array', items: { type: 'object', properties: { claim: { type: 'string' }, why: { type: 'string' }, correction: { type: 'string' } }, required: ['claim', 'why', 'correction'] } },
    weak: { type: 'array', items: { type: 'object', properties: { claim: { type: 'string' }, why: { type: 'string' }, fix: { type: 'string' } }, required: ['claim', 'why', 'fix'] } },
    bench_requests: { type: 'array', items: { type: 'string' }, description: 'timed checks to add to tonight\'s queue (complete commands), max 2' },
    verdict: { type: 'string' },
  },
  required: ['refuted', 'weak', 'bench_requests', 'verdict'],
}

const LENSES = [
  { key: 'provenance', text: `PROVENANCE lens: for every claim, check the cited evidence exists and says exactly that - open result files/JSON and compare numbers, re-open source URLs (WebFetch) and check quotes and that the source is primary, open code at the cited file:line. Flag unlabelled claims, inferred-presented-as-fact, numbers from memory, secondary sources, quotes that don't match, and PyAV 18 results presented as primary.` },
  { key: 'method', text: `METHODOLOGY lens: look for confounders and wrong conclusions - background load, warm caches, looped tiny corpora (19-frame 1080p sets) unrepresentative of real compressibility, PyAV vs ffmpeg CLI differences, PyAV 18 vs 19 differences, a functional pass mistaken for compatibility, Chromium tests that did not verify decoded pixels, truncation tests that miss realistic failure points, single-run numbers, conclusions that don't follow, alternative explanations. You may re-run quick functional checks (< 1 min CPU each, PyAV 19.0.2, no timing). For decisive TIMED numbers you doubt, add up to 2 bench_requests with complete commands for tonight's queue.` },
]

const results = await pipeline(
  TOPICS,
  t => agent(`${CTX}

Write the FINDINGS for topic ${t.key} (goals ${t.goals}) by merging ${STUDY}/results/${t.key}/NOTES.md, all other result files in ${STUDY}/results/${t.key}/ (read the raw JSON/MD, don't trust summaries), and, if present, BENCH.md + bench/*.json. The topic's investigator summary and open questions are in ${STUDY}/results/bench_queue_from_wf_2e122ed0.json under key "${t.key}".
Structure: 1) Question(s) answered, 2) Findings (each bullet labelled + cited; numbers exactly as in result files with units and conditions; PyAV 18-only results marked background), 3) Comparison table(s), 4) Implications for the plan - each tied to specific findings, 5) Pending tonight's bench (timed questions and which bench_manifest ids answer them), 6) Not tested / limits / NOT VERIFIED, 7) How to reproduce (commands). Drop or relabel anything without evidence. If a quick functional check (< 1 min CPU, PyAV 19.0.2, no timing) settles a loose end or confirms a PyAV 18-only functional result on 19, run it, save its output under results/${t.key}/ and cite it.
Return the COMPLETE text in findings_md (do not write FINDINGS.md) and a 15-line summary.`, { label: `findings:${t.key}`, phase: 'Findings', schema: FINDINGS_SCHEMA }),
  (draft, t) => {
    if (!draft) return null
    return parallel(LENSES.map(l => () => agent(`${CTX}

You are an adversarial verifier for topic ${t.key}. The draft FINDINGS.md (not on disk - it is below) is built from ${STUDY}/results/${t.key}/ (NOTES.md, other result files, BENCH.md, bench/*.json) and scripts in ${STUDY}/scripts/${t.key}/. Default to skepticism: a claim survives only with evidence.
${l.text}
Do NOT run timed benchmarks. Write your report to ${STUDY}/results/${t.key}/VERIFY_${l.key}.md (if one exists from an earlier run, rename it to VERIFY_${l.key}.prev.md first), then return the structured verdict.

===== DRAFT FINDINGS.md =====
${draft.findings_md}`, { label: `verify:${t.key}:${l.key}`, phase: 'Verify', schema: VERIFY_SCHEMA }))).then(vs => ({ draft, vs: vs.filter(Boolean) }))
  },
  (prev, t) => {
    if (!prev) return null
    return agent(`${CTX}

Revise the draft FINDINGS.md for topic ${t.key} (below) using the verifier reports ${STUDY}/results/${t.key}/VERIFY_provenance.md and VERIFY_method.md and these structured verdicts:
${JSON.stringify(prev.vs, null, 1).slice(0, 14000)}
Check each refutation yourself against the evidence before applying it (verifiers can be wrong). Correct or remove refuted claims, relabel weak ones, add verifier bench_requests to the 'Pending tonight's bench' section, and add a final 'Verification' section: what was challenged, what changed, what remains NOT VERIFIED. Quick functional checks (< 1 min CPU, PyAV 19.0.2, no timing) allowed. Return the COMPLETE revised text in findings_md (do not write FINDINGS.md) and a 10-line summary in summary including the most decisive verified findings.

===== DRAFT FINDINGS.md =====
${prev.draft.findings_md}`, { label: `revise:${t.key}`, phase: 'Revise', schema: FINDINGS_SCHEMA }).then(r => ({ ...prev, r }))
  },
)

const out = {}
TOPICS.forEach((t, i) => {
  const r = results[i]
  out[t.key] = r ? {
    revised: !!r.r,
    summary: r.r ? r.r.summary : (r.draft ? r.draft.summary : 'no draft'),
    bench_requests: r.vs ? r.vs.flatMap(v => v.bench_requests || []) : [],
    n_refuted: r.vs ? r.vs.reduce((a, v) => a + (v.refuted || []).length, 0) : null,
  } : 'FAILED'
})
return out
