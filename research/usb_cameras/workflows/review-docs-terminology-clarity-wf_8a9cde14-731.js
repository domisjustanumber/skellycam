export const meta = {
  name: 'review-usb-docs-terminology-clarity',
  description: 'Review the new USB camera research docs for consistent terminology and clarity, verify each fix, apply them, and re-check cross-document consistency',
  phases: [
    { title: 'Glossary', detail: 'cross-document term and rating consistency audit' },
    { title: 'Review', detail: 'per-document clarity and terminology review' },
    { title: 'Verify', detail: 'adversarial check of each proposed fix' },
    { title: 'Apply', detail: 'one editor per document applies accepted fixes' },
    { title: 'Final check', detail: 'cross-document consistency, links and anchors' },
  ],
}

const R = 'C:/Users/Dom/GitHub/freemocap/skellycam/research/usb_cameras'
const DOCS = [
  { key: 'readme', path: `${R}/README.md`, scope: 'Only the "## Method comparison (2026-10-30)" section (all its tables, legend, ranking, overall paragraph) and the two new Layout lines (sync_rig/, docs/). Leave the rest of README.md untouched.' },
  { key: 'plan', path: `${R}/docs/test_gap_plan.md`, scope: 'Whole file (about 810 lines).', split: true },
  { key: 'rocsync', path: `${R}/docs/rocsync_review.md`, scope: 'Whole file.' },
  { key: 'rig-readme', path: `${R}/sync_rig/README.md`, scope: 'Whole file. Check that commands, pin names, GPIO numbers, modes and file names it states match the code in sync_rig/esp32_sync_rig/esp32_sync_rig.ino and sync_rig/host/esp32_clock_sync.py (read them; do NOT propose code edits).' },
  { key: 'rig-design', path: `${R}/sync_rig/DESIGN.md`, scope: 'Whole file. Where it differs from what was implemented, that is expected (README lists deviations) — only flag places where the DESIGN is internally inconsistent or unclear, or where a reader would be misled about what exists.' },
]

const AUDIENCE = `
AUDIENCE AND STYLE. The reader is Dom, the researcher who owns this study: technical (USB/UVC, Windows capture APIs, embedded), but reading these docs cold weeks later. The existing study docs (REPORT.md, PROGRESS.md, docs/*.md written earlier) use: short sentences; bullets with bold lead-ins; tables over prose; labels "measured / inferred / web / est."; abbreviations defined once (REPORT.md "Terms used below" paragraph). Keep that house style. Do not pad, do not add marketing tone, do not shorten by dropping facts, numbers, caveats, file paths or links.

CURRENT GOAL NUMBERING (Dom's brief of 2026-10-30): G1 sync (exposure alignment, i.e. when light hits the sensor), G2 timestamp accuracy, G3 native MJPEG, G4 unique camera IDs, G5 USB bandwidth control; must-haves M1 exposure/shutter, M2 format (resolution, fps, pixel format), M3 focus. REPORT.md and older docs use a different, older numbering (1 MJPEG, 2 timing, 3 bandwidth, 4 naming, 5 cross-platform). The new docs must use the new numbering consistently and say so where confusion is possible; do NOT edit REPORT.md/PROGRESS.md/older docs except the single pointer line added to REPORT.md "Where to look".

Files in scope (all under ${R}): README.md (Method comparison section + 2 layout lines), docs/test_gap_plan.md, docs/rocsync_review.md, sync_rig/README.md, sync_rig/DESIGN.md, and the REPORT.md "Where to look" pointer line that starts "[README.md § Method comparison]". Supporting evidence for ratings: results/agent_reports/goal_matrix_gap_plan_wf_30cb7742-77f.json (key "matrix": verified rows per method with rating/basis/value/evidence/note for sync,timestamp,mjpeg,unique_id,bandwidth,exposure,format,focus), REPORT.md, timing/VERIFY_method.md.
Links: REPORT.md and test_gap_plan.md link to the README anchor "#method-comparison-2026-10-30" — that heading text must not change.
`

const GLOSSARY = {
  type: 'object',
  properties: {
    glossary: { type: 'array', items: { type: 'object', properties: {
      concept: { type: 'string' }, canonical: { type: 'string' }, first_use_form: { type: 'string', description: 'how to introduce it on first use in each doc, e.g. "Media Foundation (MF)"' },
      variants_seen: { type: 'array', items: { type: 'string' } }, note: { type: 'string' } }, required: ['concept', 'canonical', 'variants_seen'] } },
    cross_doc_issues: { type: 'array', items: { type: 'object', properties: {
      file: { type: 'string', description: 'one of readme, plan, rocsync, rig-readme, rig-design, report-pointer' },
      line: { type: 'integer' }, quote: { type: 'string' }, problem: { type: 'string' }, fix: { type: 'string' },
      category: { type: 'string', enum: ['terminology', 'rating-mismatch', 'numbering', 'naming', 'fact-mismatch', 'link'] } },
      required: ['file', 'quote', 'problem', 'fix', 'category'] } },
  },
  required: ['glossary', 'cross_doc_issues'],
}

const FINDINGS = {
  type: 'object',
  properties: {
    findings: { type: 'array', items: { type: 'object', properties: {
      line: { type: 'integer' }, quote: { type: 'string', description: 'exact text from the file, short but unique' },
      category: { type: 'string', enum: ['terminology', 'clarity', 'structure', 'consistency', 'accuracy', 'undefined-term'] },
      severity: { type: 'string', enum: ['major', 'minor'] },
      problem: { type: 'string' }, fix: { type: 'string', description: 'concrete replacement text or precise instruction' } },
      required: ['quote', 'category', 'severity', 'problem', 'fix'] } },
  },
  required: ['findings'],
}

const VERDICTS = {
  type: 'object',
  properties: {
    accepted: { type: 'array', items: { type: 'object', properties: {
      quote: { type: 'string' }, fix: { type: 'string', description: 'final fix, possibly revised' }, reason: { type: 'string' } }, required: ['quote', 'fix'] } },
    rejected: { type: 'array', items: { type: 'object', properties: { quote: { type: 'string' }, reason: { type: 'string' } }, required: ['quote', 'reason'] } },
  },
  required: ['accepted', 'rejected'],
}

phase('Glossary')
const glossaryP = agent(`${AUDIENCE}
TASK: cross-document terminology and consistency audit. Read every in-scope file fully (and skim REPORT.md's "Terms used below" paragraph and the matrix JSON for ratings).
1. Build a canonical glossary for concepts that appear in more than one place or in more than one form. Examples to check (not exhaustive): Media Foundation / MF / MSMF / IMFSourceReader; DirectShow / DS / DShow / dshow; usbvideo / usbvideo.sys / "normal driver"; WinUSB / "driver swap"; alt / alt setting / isochronous slot; PTS / SCR / STC / SOF / QPC; "method floor" / "floor" / "ground-truth floor"; ground truth / GT; the rig names ("ESP32 rig", "sync rig", "strobe rig", P0/P1, R0/R1/R2, "RocSync-lite", LED bar / time-code bar); strobe "band"; s0, E, L, t_light; "ping hypotheses" / "offset hypotheses"; ratings Yes/Part./partial/No/?/unknown/n/a and bases measured/inferred/web/est./derived/(m)/(i); test IDs (S1–S6, T1–T5, C1–C3, B1–B4, I1–I3, V0–V7, X1–X2, U1, H1, LX*, MX*) and session IDs (D0–D7) and UAC #1–#6; camera names (C922, C930e, generic 4C4A:4A55 / "generic camera" / "usbcam"); "exposure alignment" vs "sync" vs "phase"; "Gerald".
2. List concrete cross-document issues with file key, approximate line, exact short quote, problem and fix. Especially:
   - the same method rated differently in README's comparison tables vs the plan's §2 gap table (e.g. README might say MF exposure "Part. (m)" while the plan says "?"), checking which one the matrix JSON supports;
   - numbers stated differently across docs (phase walk ~14 min, 39 ppm, floor 0.5 ms, rig floor estimates 10–30 µs, ping ambiguity ~0.27 ms, RocSync 1 ms / 1.34 ms);
   - goal numbering mixups (any place using the old REPORT.md numbering, or "goal 1" meaning MJPEG);
   - the same test/session/rig piece called by different names;
   - broken or wrong relative links and anchors (verify target files exist).
Do not edit files. Return the structured output.`, { label: 'glossary+cross-doc', phase: 'Glossary', schema: GLOSSARY })

function reviewPrompt(d, part, glossary) {
  const mine = glossary.cross_doc_issues.filter(i => i.file === d.key || (d.key === 'readme' && i.file === 'report-pointer'))
  return `${AUDIENCE}
TASK: review ${d.path} for CONSISTENT TERMINOLOGY and CLARITY. Scope: ${d.scope}${part ? ' ' + part : ''}
Use this canonical glossary (prefer its canonical forms; first use in each doc should introduce abbreviations as in first_use_form):
${JSON.stringify(glossary.glossary, null, 1)}

Cross-document issues already found for this file (include them in your findings if you agree, with an exact quote and fix):
${JSON.stringify(mine, null, 1)}

Look for: undefined abbreviations or IDs at first use; one concept with several names; jargon that needs a word of explanation; sentences a cold reader must parse twice; cells/bullets that bury the point; inconsistent rating vocabulary/notation; inconsistent units/number formats (µs vs us, en-dash ranges, "~" vs "about"); headings that don't say what the section is; references to things that don't exist (sections, tests, files). Also flag accuracy problems you notice in passing (numbers that contradict the evidence), as category 'accuracy'.
Each finding: exact quote (copyable, unique), problem, concrete fix (replacement text where possible). Prefer fewer, high-value findings over nitpicks, but be thorough on terminology. Do not edit files.`
}

function verifyPrompt(d, findings, glossary) {
  return `${AUDIENCE}
TASK: adversarially check proposed edits to ${d.path} before they are applied. For each finding: open the file, confirm the quote exists, and decide whether the fix (a) is actually clearer/more consistent for the stated reader, (b) preserves every fact, number, caveat, path and link, (c) matches the glossary, (d) does not break the README anchor or other links, (e) is factually right (check the matrix JSON / REPORT.md / code when the finding touches a rating, number or command). Reject fixes that are churn, that drop information, or that conflict with another accepted fix. You may revise a fix. Merge duplicates.
GLOSSARY:
${JSON.stringify(glossary.glossary, null, 1)}
FINDINGS:
${JSON.stringify(findings, null, 1)}
Do not edit files.`
}

function applyPrompt(d, verdicts, glossary) {
  return `${AUDIENCE}
TASK: apply the accepted edits below to ${d.path} (scope: ${d.scope}). Use the Edit tool with exact strings; re-read the region before each edit. Apply only these edits plus mechanical follow-through they imply within this file (e.g. renaming a term everywhere in the file to the glossary's canonical form). Do not touch other files${d.key === 'readme' ? ', except that the REPORT.md "Where to look" pointer line (starts "- [README.md § Method comparison]") may be edited if an accepted edit targets it' : ''}. Do not change code files. Keep the house style. Do not change the README heading "## Method comparison (2026-10-30)".
After editing, re-read the whole in-scope part once and fix any inconsistency your edits introduced. If the file has markdown tables, make sure every row still has the same number of cells as its header.
Return: a short list of what you changed (and any accepted edit you could not apply, with why).
GLOSSARY:
${JSON.stringify(glossary.glossary, null, 1)}
ACCEPTED EDITS:
${JSON.stringify(verdicts.accepted, null, 1)}`
}

const glossary = await glossaryP
if (!glossary) throw new Error('glossary agent failed')
log(`glossary: ${glossary.glossary.length} concepts, ${glossary.cross_doc_issues.length} cross-doc issues`)

phase('Review')
const applied = await pipeline(
  DOCS,
  async d => {
    if (d.split) {
      const parts = await parallel([
        () => agent(reviewPrompt(d, 'Review ONLY from the top of the file through the end of section "## 3. Ground-truth upgrade" (i.e. stop before "## 4. Test specs").', glossary), { label: `review:${d.key}:1-3`, phase: 'Review', schema: FINDINGS }),
        () => agent(reviewPrompt(d, 'Review ONLY from "## 4. Test specs" to the end of the file.', glossary), { label: `review:${d.key}:4-6`, phase: 'Review', schema: FINDINGS }),
      ])
      return { findings: parts.filter(Boolean).flatMap(p => p.findings) }
    }
    return agent(reviewPrompt(d, '', glossary), { label: `review:${d.key}`, phase: 'Review', schema: FINDINGS })
  },
  (f, d) => agent(verifyPrompt(d, f.findings, glossary), { label: `verify:${d.key}`, phase: 'Verify', schema: VERDICTS })
    .then(v => ({ f, v })),
  (fv, d) => agent(applyPrompt(d, fv.v, glossary), { label: `apply:${d.key}`, phase: 'Apply' })
    .then(summary => ({ doc: d.key, found: fv.f.findings.length, accepted: fv.v.accepted.length, rejected: fv.v.rejected, summary })),
)

phase('Final check')
const final = await agent(`${AUDIENCE}
TASK: final cross-document check after edits were applied to the in-scope files. Re-read all of them fully. Check:
 - the glossary below is followed consistently across all files (list any remaining deviations);
 - README comparison ratings and the plan's §2 gap table agree for each method (or the difference is explained);
 - numbers repeated across docs agree;
 - every relative link and the "#method-comparison-2026-10-30" anchor resolve (check the files exist);
 - markdown tables have consistent cell counts;
 - nothing factual was lost: compare against git (run "git -C ${R} diff HEAD -- ." and read the diff) and flag any removed number, caveat, path or link that was not intentionally replaced.
FIX small remaining issues directly with the Edit tool (same constraints: no code files, no older docs, keep the README heading). Report what you fixed and anything left for a human decision.
GLOSSARY:
${JSON.stringify(glossary.glossary, null, 1)}`, { label: 'final-check', phase: 'Final check' })

return { glossary, applied: applied.filter(Boolean), final }
