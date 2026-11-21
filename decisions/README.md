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
| [2S1P](entries/2S1P-bootstrap-answers-with-binding-specs.md) | Answers to the bootstrap questions of the kit adoption; supersedes S222: the specs in `specs/` are normative (item 4) | accepted |
| [N2NH](entries/N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md) | Index limit 24,000 characters until the clean-up; no agent shortens the row of an entry it did not write; specs are binding | accepted |
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
| [PDD3](entries/PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md) | W1 to W8 after the 3a review: items 65 to 78, OpenCV rate check without a reported rate, virtual cameras, phase 2 loop | accepted |
| [VPF8](entries/VPF8-phase-5-recorder-decisions.md) | Phase 5 decisions R1 to R12: steps 5a, 5d, 5b, 5c; equal rows for dead and hung cameras; no image for a damaged frame; no old files | accepted |
| [J3QP](entries/J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md) | Missing frames as black placeholder blocks on `missing` rows (M1 to M10); recorder rules C1 to C7 (microphone, completion, key, CI, disk stall) | accepted |
| [C6DE](entries/C6DE-stall-as-no-progress-limits-and-no-fat-disk.md) | Recorder decisions D1 to D3: a stall is no writer progress for the limit; 3 s and 10 s stay as starting values; no take on a FAT disk | accepted |
| [4HNY](entries/4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md) | Missing frames as black placeholder blocks with the flag `missing` (M1 to M10); player decisions L1 to L8 | accepted |
| [YV3V](entries/YV3V-acceptance-of-the-phase-6a-player-spec-and-test-list.md) | The user accepted `specs/player.md` and its test list (step 6a) | accepted |
| [JMS0](entries/JMS0-review-decisions.md) | Connection review: frame count, error end, start wait, failed start, stall watch, gap detail, hang rule, exposure, allow-lists, dead server, summary rate | accepted |
| [G651](entries/G651-phase-4-live-preview-decisions-p1-to-p7.md) | Phase 4 decisions P1 to P7 and answers A1 to A8: steps, flow control and safety net, header, tile, counts, reader properties, deletion, parity | accepted |
| [VYS7](entries/VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md) | Answers Q1 to Q13 to the 4b spec: Captured and Displayed, list label, 30 fps outside proof; PR to `development`; go-ahead for tests | accepted |
| [EQY4](entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md) | Base the work on upstream `sfn26`: keep our camera layer and recorder, remove each Rust part, four ports, PRs to upstream `development` | accepted |
| [V8RS](entries/V8RS-pause-freezes-the-ui-display-only.md) | Pause freezes the UI display only: no public pause route; the internal pause of the record start stays (Q495) | accepted |
| [JK79](entries/JK79-exposure-search-at-each-open-and-camera-requests.md) | Supersedes C4FZ: Auto searches at each open, at a rate change and on request (G1); one slow-camera text; camera number; `usb_link`; virtual links | accepted |
| [6QFG](entries/6QFG-pause-in-the-ui-search-on-native-sources-and-restore-at-close.md) | Supersedes 379P: pause is a UI display freeze, no server route (K1); search on native sources; no manual exposure; restore at close | accepted |
| [22EJ](entries/22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md) | Linux and macOS native capture: certify validates it; own OS folders; test parity; SkellyCam Auto only; restore at close; checked per model | accepted |
| [SC3Y](entries/SC3Y-later-rulings-of-the-user-for-native-capture-on-linux-and-macos.md) | Later native capture rulings: widest macOS control route; named checks turn native on; restore may re-enable auto; spec owners | accepted |
| [GVC0](entries/GVC0-certify-decisions-of-the-user.md) | Certify run of skellycam: levels, quick camera checks and 3 s take, camera summary list, rules that hold everywhere, fake cameras, functions, draft 1 answers | accepted |
| [KG00](entries/KG00-certify-decisions-of-the-user-on-draft-2.md) | Certify decisions of the user on draft 2: C1 to C9 as recommended; OpenCV fallback for now; one check per model; cancel, progress, run order, exposure rule | accepted |
| [C5BR](entries/C5BR-macos-approach-probes-in-certify.md) | macOS certify run tries each approach for exposure and for the camera's JPEG, for now; trimmed when one works | accepted |
| [BVK7](entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md) | Certify rulings of the user: one test one row, native gate at the base mode, macOS widest route, probes pass/fail, 29.97 is 30 | accepted |
| [H0BQ](entries/H0BQ-user-rulings-of-the-spec-integration.md) | Spec integration rulings: summary item, progress of each check, re-check after a cancel, sequence gate, probe module, take error state, 30 s quick | accepted |
| [2GS1](entries/2GS1-step-3a-choices-of-the-capture-code-and-its-fixes.md) | Supersedes S6HT, MA22, 6EKB, 037V, BM73, R60B, FTC3: step 3a choices; virtual by link; macOS timing step; loop, source, review and CI fixes | accepted |
| [68JT](entries/68JT-step-4a-choices-of-the-preview-sender.md) | Supersedes 162X, 24FZ, MZ02: step 4a choices of the preview sender; spec section 13 items, Python API of the 4a tests, code choices | accepted |
| [RA16](entries/RA16-step-4b-choices-of-the-preview-ui.md) | Supersedes EE0E, R1TD, W674: step 4b choices of the preview UI; Q14 yes (list number, order only); Displayed rate leaves out gaps over 1 s | accepted |
| [P98T](entries/P98T-step-5a-choices-of-the-recorder-and-its-connection.md) | Supersedes Q03C, QEQ8, T24F, YNM2, P5VE: step 5a recorder and connection choices; F-1 to F-10 as one request; 15 s writer limit | accepted |
| [4D94](entries/4D94-step-6a-choices-of-the-canvas-player.md) | Supersedes 4K7V, 4MJ4, 1ACK, 5FBS: step 6a player choices; picked folders only for the app run, no list file; test names; review fixes | accepted |
| [XT31](entries/XT31-kit-adoption-choices-camera-media-check-and-fills.md) | Supersedes NMM1, 4A7H: kit adoption choices; the media check refuses PNG, GIF, WebP, SVG with an allow by path; index limit 24,000 | accepted |
| [6T78](entries/6T78-choices-of-the-sfn26-integration.md) | Choices of the `sfn26` integration: OpenCV helpers stay ours, kept and dropped items, forms of the four ports, Rust removal | accepted |
| [82AA](entries/82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) | The stop sets the last frame with no pause, plus 2, under its lock; a surviving process leaves its files to the repair step; the stuck-writer limit is 15 s | accepted |
| [F2KY](entries/F2KY-rulings-of-the-user-after-the-third-consistency-check.md) | Native capture turns on per camera model, not per OS; one Update Cameras button, off in a take; audio line; step k of 8 | accepted |

### Evidence

These entries are `evidence`: measurements. They are not in the read path. Scan these rows before
you make a measurement ([Rules](#rules)).

| # | Decision | Status |
|---|----------|--------|
| [ETJ1](entries/ETJ1-measurements-m5-to-m7-of-the-bgr-ring.md) | Measurements M5 to M7 of the BGR ring: CRC-32 cost, decode thread CPU and skip rate, capture jitter and the GIL (Windows) | evidence |
| [8RES](entries/8RES-r11-measurements-of-the-5a-recorder.md) | R11 measurements of the 5a recorder: disk stalls, kills with a full queue, fsync cost with 1 to 16 writers, the GIL (Windows) | evidence |
| [953T](entries/953T-r11-measurements-after-the-review-fixes.md) | R11 measurements again after the review fixes and D1; the kill window that loses a second frame | evidence |
| [HDC9](entries/HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md) | M-PRV-1 to M-PRV-5 of the preview sender: uvicorn deflate compresses each JPEG (16.9 against 0.23 ms at 1080p); targets met with it off (Windows) | evidence |

### Proposed

These entries wait for a decision of the user. Section is the section or area of the change, or
`none`.

| # | Decision | Section | Status |
|---|----------|---------|--------|
| [Y6F6](entries/Y6F6-camera-request-choices.md) | Choices A1 to A23 of `specs/camera-requests.md`: search limits, held value, endpoint and texts, slow-camera texts, 60 fps check, fall back, `usb_link` | none | proposed |
| [4Z7T](entries/4Z7T-choices-after-the-search-at-each-open.md) | Choices B1 to B21 after the search at each open: order and limits of an open, held value, state route, search count, manager call | none | proposed |
| [AT04](entries/AT04-choices-of-the-linux-and-macos-capture-spec.md) | Spec `specs/unix-capture.md`, tests T-UNX: stdlib V4L2, PyObjC 13.0, identity, exposure map, controls, JPEG fallback, failure codes, diagnostics | `skellycam.core.camera.capture` | proposed |
| [KY81](entries/KY81-certify-spec-choices-of-the-agent.md) | Certify spec draft 2 `specs/certify.md`, its test list T-CERT-01 to T-CERT-40 and 15 agent choices; 9 questions in its section 14 | `certify` | proposed |
| [8CP7](entries/8CP7-certify-spec-draft-3-choices-of-the-agent.md) | Certify spec draft 3 on format 1.4.0, tests T-CERT-01 to 67, 15 agent choices: split checks, model item, gate roll-ups, local record, macOS probes | `certify` | proposed |
| [FC1C](entries/FC1C-choices-of-the-spec-integration.md) | Spec integration choices: hash set, route results, no record in certify, model turn-on, waits, steps, quick order, take error state | none | proposed |
| [F8C0](entries/F8C0-third-review-choices.md) | Choices of the third review fixes: start and stop with no lost take, no stop pause, exit through the take level, Ctrl-C, dead-server end, summary rate | `recorder` | proposed |
| [AC5B](entries/AC5B-choices-of-the-third-consistency-check.md) | Choices of the third spec check: loop-pass stall counter, diagnostics message, code table, warning owners, apply wait, search reason, `ended_take_summary` | none | proposed |

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
  `citation repair`. Add these two lines only to an entry that is on upstream `development`. A plain-text
  old path in a decided entry or a script stays, and means the same file at
  its new path.
- An entry in a commit that is not pushed to a remote can change in that commit, in each part. Make
  the correction and report it to the user. Do not write a new entry for it, and do not ask. The
  four edits apply from the first push.
- A decision that a document or code refers to must be in an entry. "This log" in an older entry or
  in the Rules means all logs.
- An absorb document is one of these: the root or a nested `AGENTS.md`, the skills, the Rules of this file with [template.md](template.md), the specs in `specs/`, and the docstring of a
  tool in `tools/` for the rules that it checks. A test in `tools/tests/` or in the
  tests of the package is a tool here: its docstring states the rules that it checks.
  `pyproject.toml` is an absorb document for a rule that a test checks. Its `absorbed into` link
  stands beside the link of that test. An accepted entry is absorbed when the absorb
  documents together state all of its rules. Open work of the entry does not stop the absorb when
  `open-work.md` states that work in full. A link to the entry is not
  enough.
- A spec in `specs/` is binding text. Read each spec that applies to your task. Absorb an accepted
  entry into a spec heading only after you check, entry by entry, that the spec states each rule of
  that entry ([ADR-N2NH](entries/N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md)).
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
- Do not shorten the index row of an entry that you did not write
  ([ADR-N2NH](entries/N2NH-index-limit-24000-no-shortened-rows-and-binding-specs.md)).
- An ID changes only on a `re-ID:` line of `tools/check_decision_log.py`, to the ID of a new `--new`
  run.
- Until a commit is on upstream `development`, cite its PR number and the file path, not its SHA.
  The `ADR-` prefix is for citations only: a file name, a
  heading, an index row and a status line hold the bare ID. Cite a provisional entry of another repo
  by the repo name, the PR number and the slug. Do not edit a decided entry only to add or move the
  prefix or the link.
