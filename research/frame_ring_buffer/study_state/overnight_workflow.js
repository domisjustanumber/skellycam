export const meta = {
  name: 'frame-ring-buffer-overnight',
  description: 'Re-run all ring buffer benchmarks on an idle machine, finish the study (prototypes, C++, recommend, critique), fix critic issues, fill and audit the report doc',
  phases: [
    { title: 'Baseline', detail: 're-run baseline benchmarks on the idle machine' },
    { title: 'Benchmark', detail: 'continue_workflow.js: prototypes -> C++' },
    { title: 'Recommend', detail: 'continue_workflow.js' },
    { title: 'Critique', detail: 'continue_workflow.js: evidence, priorities, reproducibility' },
    { title: 'Revise', detail: 'address blocker/major critic issues' },
    { title: 'Report', detail: 'fill the Claude Doc, then audit it against the result files' },
  ],
}

// Overnight run requested 2026-10-27. Wraps continue_workflow.js (same folder) with a fresh baseline
// before it and revise + report stages after it. args: { stamp: 'YYYYMMDD' }

const STAMP = (args && args.stamp) || '20261027'
const SK = 'C:\\Users\\Dom\\GitHub\\freemocap\\skellycam'
const BENCH = SK + '\\research\\frame_ring_buffer'
const STATE = BENCH + '\\study_state'
const DOC_URL = 'https://claude.ai/artifact/Cz1otkZxAjLTHfP1WeE9it'

const BASE = `Context: the SkellyCam frame ring buffer study. Read ${STATE}\\RESUME.md first (goal, priorities, pinned commits, files) and ${BENCH}\\PROVISIONAL.md.
HARD RULE: make no assertion without a code reference (file + line range, preferably a permalink at the pinned commit) or a pointer to a benchmark output file plus the script and command that reproduce it.
Do NOT modify any source file in the skellycam or freemocap repos; do not commit or push; do not install packages into the repos' own venvs (bench-only packages go in ${BENCH}\\.venv-bench). Do not use SendMessage. Kill every child process you start before you finish.
This is an overnight run (${STAMP}) on a machine that was idle when it started; nobody is at the machine.`

const BENCH_SCHEMA = {
  type: 'object',
  properties: {
    stage: { type: 'string' },
    environment: { type: 'string' },
    scripts: { type: 'array', items: { type: 'object', properties: { path: { type: 'string' }, purpose: { type: 'string' }, command: { type: 'string' } }, required: ['path', 'purpose', 'command'] } },
    results: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, config: { type: 'string' }, metric: { type: 'string' }, value: { type: 'string' },
      meets_5x60: { type: 'string', enum: ['yes', 'no', 'n/a'] }, output_file: { type: 'string' }, script: { type: 'string' } },
      required: ['name', 'config', 'metric', 'value', 'meets_5x60', 'output_file', 'script'] } },
    findings: { type: 'array', items: { type: 'object', properties: { statement: { type: 'string' }, evidence: { type: 'string' } }, required: ['statement', 'evidence'] } },
    limitations: { type: 'array', items: { type: 'string' } },
  },
  required: ['stage', 'environment', 'scripts', 'results', 'findings', 'limitations'],
}

phase('Baseline')
await agent(`${BASE}
You are the BASELINE RE-RUN agent. The baseline in ${BENCH}\\baseline\\ was measured on 2026-10-25 under heavy background load (62% CPU), so every number is provisional. Re-run it on tonight's idle machine.
1. Preserve the old results: copy ${BENCH}\\baseline\\results\\ to ${BENCH}\\baseline\\results_provisional_20261025\\ and ${STATE}\\baseline_result.json to ${STATE}\\baseline_result_provisional_20261025.json (skip if the copies already exist).
2. Read baseline\\README.md and run every benchmark it documents (bench_a_write .. bench_g_decode_ref, summarize_e2e, repro_type_overloads_spawn) exactly as documented, same configs (5 cameras, 1280x720 and 1920x1080 BGR, 60 fps target). Fix README steps that do not work as written and note each fix.
3. Record machine load (CPU %, memory %, top processes) at the start and end of every benchmark. A run is "idle" only if background CPU stayed under about 10%; otherwise label it provisional.
4. Compare every headline number with the provisional run (table: metric, 2026-10-25 value, ${STAMP} value, change).
5. Write the new structured result to ${STATE}\\baseline_result.json (same shape as before) and add a "${STAMP} idle re-run" section to baseline\\README.md with the comparison table.
6. Update ${BENCH}\\PROVISIONAL.md: say which runs were measured idle on ${STAMP} and which stay provisional.`, { label: 'bench:baseline', phase: 'Baseline', schema: BENCH_SCHEMA })

// Prototypes -> C++ -> recommend -> critiques -> reproducibility (writes its own *_result.json files to STATE).
const cont = await workflow({ scriptPath: STATE + '\\continue_workflow.js' }, { skip: [] })

phase('Revise')
const revised = await agent(`${BASE}
You are the REVISION agent. The critics' output is below (also on disk as ${STATE}\\critic_*_result.json). For every blocker and major issue: fix it, by re-running or correcting the benchmark (scripts and outputs under ${BENCH}), correcting a wrong number or code ref, or adding the missing evidence. If it cannot be fixed tonight, record it as an open question. Then update ${STATE}\\recommend_result.json so it reflects the corrected evidence, and write ${STATE}\\revision_result.json listing each issue -> action taken -> evidence. Return that same object.
Critique output:
${JSON.stringify(cont, null, 1)}`, { label: 'revise', phase: 'Revise', schema: {
  type: 'object',
  properties: {
    actions: { type: 'array', items: { type: 'object', properties: { issue: { type: 'string' }, severity: { type: 'string' }, action: { type: 'string' }, evidence: { type: 'string' }, resolved: { type: 'boolean' } }, required: ['issue', 'action', 'resolved'] } },
    open_questions: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['actions', 'open_questions', 'summary'],
} })

phase('Report')
const DOC_RULES = `The report is a Claude Doc: ${DOC_URL} (doc id 610a6b1c-1f2a-4bb4-95ef-02f4b8ca0a15). Use the Claude Docs MCP tools (load them with ToolSearch: mcp__claude_ai_Claude_Docs__*). Before any docs call, call guide with items ["topic.index", "topic.editing", "topic.diagram", "topic.charts"] and follow it. Re-read the doc outline first: someone may have edited it.`

await agent(`${BASE}
${DOC_RULES}
You are the REPORT WRITER. Fill every pending section. The pending block ids and section names are in the table in RESUME.md (mvvytezepy4.74 Summary ... mvvytezepy4.84 Reproducing the results). Replace each pending block with "## <heading>" + body, one section per call, in order. Sources: verified_digest.json, verified_maps.json, research.json, baseline_result.json (tonight's idle re-run; mention the provisional 2026-10-25 numbers only for comparison), prototypes_result.json, cpp_result.json, recommend_result.json, revision_result.json, critic_*_result.json, and the reproducibility\\ summary, all in or under ${BENCH}.
- Every claim carries its code permalink or result file + command. Label any number that is still provisional.
- Architecture overview: a diagram of the write path, read paths, control messages, UI taps and the SkellyCam -> FreeMoCap handoff.
- Measured baseline / C++ / Recommendations: use tables; add a chart where a comparison is clearer as one (e.g. fps per config, baseline vs best prototype).
- Recommendations: ranked by P1 (no dropped disk writes), then P2 (5 cameras at 60 fps), then P3 (no copies), with effort and risk.
- Keep the prose short and plain.
Return a list of the sections you filled and any you could not fill, with the reason.`, { label: 'report:write', phase: 'Report' })

const audit = await agent(`${BASE}
${DOC_RULES}
You are the REPORT AUDITOR. Read the whole doc. Try to find errors: numbers that do not match the result JSON/output files under ${BENCH} (open them), claims without a code ref or result file, code refs that do not support the claim (open the files at the pinned commit), provisional numbers not labelled, recommendations that contradict revision_result.json, and sections still pending. Fix each error directly in the doc (smallest edit that makes it right). Then update ${STATE}\\RESUME.md: mark every stage done (or say what is left), record tonight's run (${STAMP}), and remove the "resume" instructions that no longer apply.
Return a short plain-text summary (under 200 words) for the user: headline result, whether 5x60 fps is reachable and how, the C++ verdict, what you corrected in the doc, and what is still open.`, { label: 'report:audit', phase: 'Report' })

return { audit, revision: revised }
