# Decision log

This log records the technical decisions of SkellyCam, with their reasons and evidence. Read this
file and [open-work.md](open-work.md) before you change the code, the CI or the agent instructions. The
[Rules](#rules) tell you which entries to read
([ADR-0001](entries/0001-decision-log-agents-md-and-private-data.md)).

Each entry gives the decision, its reason, the evidence (when there is evidence), the alternatives
rejected and a "Not repeated" section for pitfalls already found. When a decision changes, add a new
entry that supersedes the old entry in full. The body of a decided entry changes only by the edits
that the [Rules](#rules) allow. To write an entry, use [template.md](template.md).

## Index

### Active

These entries are `accepted`.

| # | Decision | Status |
|---|----------|--------|
| [0001](entries/0001-decision-log-agents-md-and-private-data.md) | Decision log and its rules; `AGENTS.md` files hold the instructions; `plans/` is local; no private data | accepted |
| [S222](entries/S222-bootstrap-answers-of-the-kit-adoption.md) | Answers to the bootstrap questions of the kit adoption | accepted |
| [50G8](entries/50G8-phase-2-frame-ring-spec.md) | Phase 2 follows `specs/frame-ring.md`: two rings per camera, copy then CRC-32 reads, recorder first; the 2b build is approved | accepted |
| [9G2W](entries/9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md) | Python API of the frame ring, as the 2a tests assume it; clarifications, corrections and decisions on the 2a code (items 52 to 67) | accepted |
| [7DE6](entries/7DE6-arm64-ci-job-for-the-portable-frame-ring-tests.md) | CI job that runs the portable frame ring tests on an arm64 Linux runner, on pushes to `dom/native-jpeg` | accepted |
| [5MYA](entries/5MYA-python-api-of-the-bgr-ring-and-the-decode-stage-as-the-2b-tests-assume-it.md) | Python API of the BGR ring and the decode stage, as the 2b tests assume it | accepted |
| [467Z](entries/467Z-step-2b-self-check-stop-opencv-threads-and-yuv-conversion.md) | Step 2b: no BGR self-check log, `stop()` drops and counts a waiting frame, `cv2.setNumThreads(1)` in each camera process, default YUY2 and NV12 conversion | accepted |
| [E817](entries/E817-choices-of-the-2b-code.md) | Choices of the 2b code: `bgr` on the JPEG creator, `set_skipped_count`, `None` payload for a flagged BGR frame, no libjpeg limit on Windows until phase 3 | accepted |
| [CE8C](entries/CE8C-count-line-of-the-bgr-ring-at-the-stop-of-the-decode-stage.md) | `DecodeStage.stop()` logs one count line for its BGR ring: frames committed, skipped, decode errors | accepted |
| [EN7A](entries/EN7A-phase-3-windows-capture-decisions.md) | Phase 3 decisions D1 to D49: Media Foundation through `comtypes`, one shared loop, start-up rate check, failed and dead cameras | accepted |
| [QKX1](entries/QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md) | Fifteen answers U1 to U15 of the user to the phase 3 spec drafts; three interim rules of phase 3 that phase 5 removes | accepted |
| [4CQC](entries/4CQC-phase-3-windows-capture-spec-and-test-list.md) | Phase 3 spec `specs/windows-capture.md` and its test list (91 tests), with the 64 agent choices of its section 18 | accepted |
| [HP7D](entries/HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md) | Python API of capture, as the 3a tests assume it: names, seams for fake sources and a virtual clock, log line forms | accepted |
| [HB4Z](entries/HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md) | Answers U16 to U23: control thread, warm-up count, Windows-only `media_foundation/`, CI and tests on Linux and macOS, parity table | accepted |
| [G651](entries/G651-phase-4-live-preview-decisions-p1-to-p7.md) | Phase 4 decisions P1 to P7 and answers A1 to A8: steps, flow control and safety net, header, tile, counts, reader properties, deletion, parity | accepted |
| [WB08](entries/WB08-acceptance-of-the-step-4a-preview-spec-and-its-test-list.md) | The user accepted the step 4a spec `specs/preview.md` and its test list T-PRV-01 to T-PRV-24 | accepted |

### Evidence

These entries are `evidence`: measurements. They are not in the read path. Scan these rows before
you make a measurement ([Rules](#rules)).

| # | Decision | Status |
|---|----------|--------|
| [ETJ1](entries/ETJ1-measurements-m5-to-m7-of-the-bgr-ring.md) | Measurements M5 to M7 of the BGR ring: CRC-32 cost, decode thread CPU and skip rate, capture jitter and the GIL (Windows) | evidence |

### Proposed

These entries wait for a decision of the user. Section is the section or area of the change, or
`none`.

| # | Decision | Section | Status |
|---|----------|---------|--------|
| [NMM1](entries/NMM1-design-of-the-camera-media-check.md) | Camera media check: types, first bytes, `GOLDEN_PATHS`, image reminder, `commit-files` skill, per-worktree hook install | none | proposed |
| [4A7H](entries/4A7H-other-fills-of-the-kit-adoption.md) | Other fills of the kit adoption; `CLAUDE.md` stays untracked | none | proposed |
| [162X](entries/162X-step-4a-preview-spec-and-agent-choices.md) | Step 4a spec `specs/preview.md`: per-camera preview message, its sender and 24 tests, with 27 agent choices; no open question | `preview` | proposed |

The entries that are `rejected`, `superseded by XXXX`, `absorbed into <path>#<anchor>`,
`evidence; used by XXXX` or `done` are in [historical.md](historical.md).

## Open work

The open work is in [open-work.md](open-work.md).

## Rules

- Read the Active entries that apply to your task. Then you do not repeat a settled question. Before
  you make a measurement, scan the rows of the Evidence table of each log, and read the entries that
  apply. Then you do not repeat a completed measurement. The Evidence entries are not in the read
  path. Read a Proposed entry only for work in its section, or when a skill
  tells you to. Read an entry of [historical.md](historical.md) only to find the reason for a
  decision.
- The body of an entry that is not `proposed` changes only by four edits: a link or anchor repair, a
  typo that does not change the meaning, the redaction of private data, and a change of ID with the
  repair of its citations. Each edit adds `_Edited YYYY-MM-DD (#PR): <kind>._` at the end of the
  entry, for example `re-ID from XXXX`. For a
  change of ID, the renamed entry gets `re-ID from XXXX`, and each repaired entry gets
  `citation repair`. Add these two lines only to an entry that is on `development-streaming`. A plain-text
  old path in a decided entry or a script stays, and means the same file at
  its new path.
- An entry in a commit that is not pushed to a remote can change in that commit, in each part. Make
  the correction and report it to the user. Do not write a new entry for it, and do not ask. The
  four edits apply from the first push.
- A decision that a document or code refers to must be in an entry. "This log" in an older entry or
  in the Rules means all logs.
- An absorb document is one of these: the root or a nested `AGENTS.md`, the skills, the Rules of this file with [template.md](template.md), and the docstring of a
  tool in `tools/` for the rules that it checks. A test in `tools/tests/` or in the
  tests of the package is a tool here: its docstring states the rules that it checks.
  `pyproject.toml` is an absorb document for a rule that a test checks. Its `absorbed into` link
  stands beside the link of that test. An accepted entry is absorbed when the absorb
  documents together state all of its rules. Open work of the entry does not stop the absorb when
  `open-work.md` states that work in full. A link to the entry is not
  enough.
- Absorb at landing. The commit group that writes or lands an entry, or that writes the rules of an
  entry into the absorb documents, absorbs the entry in its last commit when the absorb documents
  state all of its rules. This applies in each log, in each skill and without a skill. If an absorb
  document does not state a rule, the entry stays `accepted`. Do not ask the user.
- The status `absorbed into` has one link for each heading that states a rule of the entry. Link a
  heading one time, also when it states two or more rules. Link a file with no anchor only when the
  rule is not under a heading, for example in a tool docstring or a YAML file. When the status
  paragraph is longer than `STATUS_EXEMPTION_LIMIT`, replace the headings of one file with the title
  heading of that file. Start with the file that has the most links. If the paragraph is still too
  long, replace the files of one document with the title heading of its
  main file. A commit that renames a heading repairs each status link to that heading. A change from
  a file link to heading links is a link repair.
- The entry that supersedes an old entry restates each rule of the old entry that stays. A link can
  restate a rule. The link must go to a heading of an absorb document, and that heading must state
  the rule. Link the heading of each kept rule that a heading states. Write text only for a changed
  rule and for a kept rule that no heading states. The commit that changes the text under such a heading cites its own entry next to the
  changed rule. That change does not supersede the entry that links the heading.
- Only these status changes are allowed: `proposed` to `accepted` or `rejected`; `accepted` to
  `superseded by XXXX`, `absorbed into <path>#<anchor>` or `done`; `absorbed into <path>#<anchor>`
  to `superseded by XXXX`; and `evidence` to
  `evidence; used by XXXX`, when an accepted entry cites the `evidence` entry for its decision.
  `done` is for an accepted entry that records a one-off action, with no rule that stays, when the
  action is complete. Each status change adds its date and the PR that made it. In the same PR,
  change the status in the index and move the row to the table for the new status.
- `tools/check_decision_log.py` checks the tables, the status forms, the Section cell, the ID
  alphabet and the size limits. Its docstring states them. `tools/check_links.py` checks the links
  and the full-SHA permalinks. A tool is the source of a rule that it checks.
- A consolidation entry states the rules that stay from a group of entries, and it supersedes each
  entry of the group. It changes no decision.
- When the read path is at 90% of its limit or more, first absorb each accepted entry whose rules
  the absorb documents state. Then
  write each rule that no absorb document states in the absorb document where it belongs, and
  absorb its entry.
- A commit that only makes a workflow, skill, template or tool copy agree with a landed entry
  cites that entry. It needs no entry of its own. A new rule is not a copy.
- Delete an open-work item when the work is done. Put a dated fact in `open-work.md` or in an
  entry, not in `AGENTS.md`.
- Put long evidence in a tracked file in `evidence/` of the log folder, and link to it. A PR that raises a limit
  of `tools/check_decision_log.py` must add an entry.
- An ID changes only on a `re-ID:` line of `tools/check_decision_log.py`, to the ID of a new `--new`
  run.
- Until a commit is on `development-streaming`, cite its PR number and the file path, not its SHA.
  The `ADR-` prefix is for citations only: a file name, a
  heading, an index row and a status line hold the bare ID. Cite a provisional entry of another repo
  by the repo name, the PR number and the slug. Do not edit a decided entry only to add or move the
  prefix or the link.
