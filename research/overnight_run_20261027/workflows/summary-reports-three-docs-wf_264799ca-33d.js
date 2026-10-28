export const meta = {
  name: 'summary-reports-three-docs',
  description: 'Fill three summary docs (MJPEG, USB camera tests, frame ring buffer) from the result files, then fact-check each doc',
  phases: [
    { title: 'Write', detail: 'one writer per doc, one section per call' },
    { title: 'Verify', detail: 'adversarial fact-check of each doc against the result files; fixes in place' },
  ],
}

const SK = 'C:\\Users\\Dom\\GitHub\\freemocap\\skellycam'
const UC = SK + '\\research\\usb_cameras'
const RES = UC + '\\results\\windows\\Gerald'
const BENCH = SK + '\\research\\frame_ring_buffer'  // was benchmarks\\frame_pipeline before 2026-10-28
const STATE = BENCH + '\\study_state'

const DOCS_HOWTO = `HOW TO WRITE IN THE DOC (Claude Docs MCP tools): load them with ToolSearch (query "+claude_ai_Claude_Docs" or select:mcp__claude_ai_Claude_Docs__guide,mcp__claude_ai_Claude_Docs__update,mcp__claude_ai_Claude_Docs__batch,mcp__claude_ai_Claude_Docs__read). Before any other docs call, call guide with items ["topic.index"], then guide ["topic.charts"] and guide ["topic.diagram"] as separate calls if your doc needs a chart or diagram, and follow them exactly (call shapes, ids, chart wiring, look, screenshot read after each widget write). The doc is already open on Dom's screen: fill ONE section per update call (replace its pending block with "## <heading>" + body, "as":"markdown"), prose sections first in reading order, charts/diagrams after. Do not add or remove sections; do not touch the title or byline.
Writing rules: written for Dom (the skellycam maintainer) and his collaborators; each section opens with its point and number; short sentences, plain words, specifics (numbers + units, camera names, dates); tables for items x attributes; a chart for five or more values of one measure across items; no restating a chart's values in prose. Sized as a SUMMARY: each section a few short paragraphs or one table/chart. Every number must come from a file you opened; cite result files as repo-relative paths in an Evidence section. Label provisional or synthetic-camera numbers as such. Facts only from the files listed; if a fact is missing, write it as a one-line open question.
Do not run any camera, benchmark or test; read files only. Do not modify repo files. No git. Do not use SendMessage.`

const DOCS = [
  {
    key: 'mjpeg',
    title: 'MJPEG passthrough summary',
    ids: `Doc id (project) 23b1b477-ff4a-4306-9607-91ea32e17d47 · tab file id (lids.f) aff2b3c1-4363 · tab body node id (lids.n) dee2a781-ba3b · container {"kind":"project","id":"23b1b477-ff4a-4306-9607-91ea32e17d47"}.
Pending blocks (full ids) in order: mv3qbhyxq48.32 Summary · mv3qbhyxq48.33 What was tested · mv3qbhyxq48.34 Results matrix (approach x camera x mode -> fps, valid JPEG %, CPU %, native or not: a pipe table is right here since attributes differ in kind) · mv3qbhyxq48.35 Per-camera findings and quirks · mv3qbhyxq48.36 What changed since the 25 Oct run + verifier verdicts · mv3qbhyxq48.37 Recommendation for skellycam's capture path, limits, open questions · mv3qbhyxq48.38 Evidence.`,
    sources: `Goal 1 of the USB camera investigation: native MJPEG extraction on Windows without decode/re-encode. Sources: ${UC}\\mjpeg\\RESULTS.md (the matrix, written overnight 2026-10-27/28), ${RES}\\mjpeg_* result dirs (INVALID.txt marks bad earlier runs), ${UC}\\results\\agent_reports\\rerun_20261027_reports_and_verifications.json (the 'mjpeg' area: rerun result + adversarial verification; also the 'rust' and 'prior_art' areas for nokhwa / GStreamer passthrough claims), ${RES}\\RERUN_20261027.md, ${UC}\\PROGRESS.md, earlier claims in ${UC}\\results\\agent_reports\\phase1_reports_and_verifications.json. Cameras: Logitech C922, Logitech C930e, generic 'USB Camera' 4C4A:4A55; the Razer Kiyo Pro was excluded on purpose (known flaky). Runs were at night with other agents running; say where CPU% carries load. The full investigation report (other goals) is https://claude.ai/artifact/WrpwyyMF7yU1amEB9pQYgE — link it in Evidence.`,
  },
  {
    key: 'camera_tests',
    title: 'USB camera tests summary',
    ids: `Doc id (project) 33048e86-733d-433e-bb3f-5982b3d1fb85 · tab file id (lids.f) d7134f94-f348 · tab body node id (lids.n) 8c630d14-7fd6 · container {"kind":"project","id":"33048e86-733d-433e-bb3f-5982b3d1fb85"}.
Pending blocks (full ids) in order: mzqms63g4te.31 Summary · mzqms63g4te.32 What ran and what was skipped (and why) · mzqms63g4te.33 Re-confirmed findings per area · mzqms63g4te.34 Changed or refuted findings, and whether light/load explains them · mzqms63g4te.35 Camera health through the night · mzqms63g4te.36 What still needs a person + next steps · mzqms63g4te.37 Evidence.`,
    sources: `The overnight (2026-10-27 23:03 to 2026-10-28 00:57 local; 03:03Z-04:50Z) unattended re-run of the USB camera tests on the Windows machine 'Gerald' (run wf_ef322d5c-d99): areas naming, timing, bandwidth, libusb/Rust, prior-art libraries (MJPEG has its own summary doc, 'MJPEG passthrough summary'; mention it in one line and leave MJPEG detail out). Sources: ${RES}\\RERUN_20261027.md, ${UC}\\results\\agent_reports\\rerun_20261027_reports_and_verifications.json (per area: rerun result + adversarial verification), ${UC}\\PROGRESS.md (incl. the new 'Overnight rerun 20261027' section), earlier claims in ${UC}\\results\\agent_reports\\phase1_reports_and_verifications.json and phase2_reports_and_verifications.json, and the new result dirs under ${RES}. Skipped by design: anything needing UAC/elevation, WinUSB driver swaps (phase 2/3), replug, port move, reboot. Razer Kiyo Pro excluded (known flaky); note that libusb enumeration and GStreamer ksvideosrc still contacted it but it stayed healthy. The full investigation report is https://claude.ai/artifact/WrpwyyMF7yU1amEB9pQYgE — link it in Evidence.`,
  },
  {
    key: 'ring_buffer',
    title: 'Frame ring buffer summary',
    ids: `Doc id (project) 81a89750-63d7-4b3b-93db-b1d792ebcb08 · tab file id (lids.f) 5b8d5c94-b9f5 · tab body node id (lids.n) 58f81689-cfc7 · container {"kind":"project","id":"81a89750-63d7-4b3b-93db-b1d792ebcb08"}.
Pending blocks (full ids) in order: mmzs7nfwx0r.32 Summary · mmzs7nfwx0r.33 How frames move today (a DIAGRAM: write path, read paths, UI and FreeMoCap handoff, copies per frame) · mmzs7nfwx0r.34 Measured baseline on the idle machine vs the provisional 25 Oct run · mmzs7nfwx0r.35 What raises throughput (a CHART of fps per variant against the 60 fps target: HEAD, copy.copy removed, seqlock ring + recorder with lockstep, +3 ms CPU sensitivity, etc., with the synthetic-camera caveat) · mmzs7nfwx0r.36 Disk-write safety (P1) · mmzs7nfwx0r.37 C++ port verdict · mmzs7nfwx0r.38 Ranked recommendations (table: rank, change, priority served, effect, effort, risk; top items) · mmzs7nfwx0r.39 Open questions and next tests · mmzs7nfwx0r.40 Evidence.`,
    sources: `The SkellyCam -> FreeMoCap frame ring buffer study, finished overnight 2026-10-28 on an idle machine (run wf_8fd1ec97-b0e). Priorities: P1 disk writes never drop, P2 5 cameras at 60 fps, P3 no unnecessary frame copies. Sources in ${STATE}: RESUME.md, verified_digest.json, baseline_result.json (idle re-run) and baseline_result_provisional_20261025.json, prototypes_result.json, cpp_result.json, recommend_result.json (post-revision, authoritative), revision_result.json, critic_*_result.json; also ${BENCH}\\PROVISIONAL.md, ${BENCH}\\baseline\\README.md, ${BENCH}\\revision\\README.md, ${BENCH}\\prototypes\\results\\*.md and ${BENCH}\\reproducibility\\. The full report is the Claude Doc https://claude.ai/artifact/Cz1otkZxAjLTHfP1WeE9it (doc id 610a6b1c-1f2a-4bb4-95ef-02f4b8ca0a15) — you may read it with the docs read tool for structure, but take numbers from the JSON/result files; link it in Evidence. Known corrections: rank 13's lockstep gate wait is 0.03-6.4 ms median per camera; no attached camera exceeds 30 fps, so 60 fps results are synthetic-camera only. Note in one line that the benchmark machine's RAM runs at 4000 MT/s against a 6400 rating (from baseline_result.json environment), which lowers memory-copy numbers.`,
  },
]

const results = await pipeline(
  DOCS,
  d => agent(`You are the WRITER of the Claude Doc "${d.title}" — a summary report.
${d.ids}
CONTENT: ${d.sources}
${DOCS_HOWTO}
Read the sources first (enough to write the Summary), write the Summary section, then read on and fill each next section as soon as you have it. After any chart or diagram, take a screenshot read and fix what falls short (title states the finding, nothing clipped or overlapping, units, grey-first colour). Return a plain list: sections filled (with their new heading ids from the acks), widgets created (ids), and every number you used with its source file.`, { label: `write:${d.key}`, phase: 'Write' }),
  (w, d) => agent(`You are an adversarial FACT-CHECKER for the Claude Doc "${d.title}".
${d.ids}
CONTENT AND SOURCES: ${d.sources}
${DOCS_HOWTO}
The writer has filled the doc; its notes are below. Read the whole doc (docs read tool: read the project, then the body node with projection outline, then views of each section). Try to find errors: any number that does not match its source file (open the files and check each one), claims without a source, mislabelled provisional/synthetic results, wrong camera or config names, a chart whose rows disagree with the files, sections still pending, prose that restates a chart, sections longer than a summary needs. Take a screenshot read of each widget and check it as the guide says. Fix each problem directly in the doc with the smallest edit (find/replace text edits, or draft-edit + publish for widgets). Return a short list: each error found -> the fix made, and anything you could not verify.
Writer notes:
${typeof w === 'string' ? w : JSON.stringify(w)}`, { label: `verify:${d.key}`, phase: 'Verify' }).then(v => ({ key: d.key, writer: w, check: v })),
)
return results.filter(Boolean).map(r => ({ key: r.key, check: r.check }))