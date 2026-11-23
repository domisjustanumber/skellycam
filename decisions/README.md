# Decision log

This log records the technical decisions of SkellyCam, with their reasons and evidence. Read this
file and [open-work.md](open-work.md) before you change the code, the CI or the agent instructions. The
[Rules](#rules) tell you which entries to read
([ADR-0001](entries/0001-decision-log-agents-md-and-private-data.md)).

Each entry gives the decision, its reason, the evidence (when there is evidence), the alternatives
rejected and a "Not repeated" section for pitfalls already found. When a decision changes, add a new
entry that supersedes the old entry in full. The body of a decided entry changes only by the edits
that the skill [`change-decision-log`](../.claude/skills/change-decision-log/SKILL.md) allows. To write an entry,
load that skill and use [template.md](template.md).

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
| [HP7D](entries/HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md) | Python API of capture, as the 3a tests assume it: names, seams for fake sources and a virtual clock, log line forms | accepted |
| [C6DE](entries/C6DE-stall-as-no-progress-limits-and-no-fat-disk.md) | Recorder decisions D1 to D3: a stall is no writer progress for the limit; 3 s and 10 s stay as starting values; no take on a FAT disk | accepted |
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
| [BVK7](entries/BVK7-certify-rulings-of-the-user-one-test-one-row.md) | Certify rulings of the user: one test one row, native gate at the base mode, macOS widest route, probes pass/fail, 29.97 is 30 | accepted |
| [H0BQ](entries/H0BQ-user-rulings-of-the-spec-integration.md) | Spec integration rulings: summary item, progress of each check, re-check after a cancel, sequence gate, probe module, take error state, 30 s quick | accepted |
| [2GS1](entries/2GS1-step-3a-choices-of-the-capture-code-and-its-fixes.md) | Supersedes S6HT, MA22, 6EKB, 037V, BM73, R60B, FTC3: step 3a choices; virtual by link; macOS timing step; loop, source, review and CI fixes | accepted |
| [68JT](entries/68JT-step-4a-choices-of-the-preview-sender.md) | Supersedes 162X, 24FZ, MZ02: step 4a choices of the preview sender; spec section 13 items, Python API of the 4a tests, code choices | accepted |
| [RA16](entries/RA16-step-4b-choices-of-the-preview-ui.md) | Supersedes EE0E, R1TD, W674: step 4b choices of the preview UI; Q14 yes (list number, order only); Displayed rate leaves out gaps over 1 s | accepted |
| [P98T](entries/P98T-step-5a-choices-of-the-recorder-and-its-connection.md) | Supersedes Q03C, QEQ8, T24F, YNM2, P5VE: step 5a recorder and connection choices; F-1 to F-10 as one request; 15 s writer limit | accepted |
| [4D94](entries/4D94-step-6a-choices-of-the-canvas-player.md) | Supersedes 4K7V, 4MJ4, 1ACK, 5FBS: step 6a player choices; picked folders only for the app run, no list file; test names; review fixes | accepted |
| [XT31](entries/XT31-kit-adoption-choices-camera-media-check-and-fills.md) | Supersedes NMM1, 4A7H: kit adoption choices; the media check refuses PNG, GIF, WebP, SVG with an allow by path; index limit 24,000 | accepted |
| [6T78](entries/6T78-choices-of-the-sfn26-integration.md) | Choices of the `sfn26` integration: OpenCV helpers stay ours, kept and dropped items, forms of the four ports, Rust removal | accepted |
| [TFD7](entries/TFD7-search-limit-stop-rate-median-role-flag-and-restore-after-a-failed-loop.md) | Decisions B1, B2, B7 to B9 of 2026-11-21: search limit stays 20 s; median stop rate, role flag, no restart, restore after a failed loop (not built) | accepted |
| [X1T8](entries/X1T8-two-way-kit-sync-adoption.md) | Two-way kit sync: skellycam is the pilot; values in `kit.toml`; Python 3.13; the winners of 19 differences; CI runs only `check`; kit uv | accepted |
| [81RE](entries/81RE-decisions-of-the-user-on-the-restore-file-the-take-rate-and-pace-tests.md) | Q608, Q609, Q619 of 2026-11-23: restore record on disk; take rate is frames over time; pace tests reported, not blocking, on CI | accepted |
| [T34M](entries/T34M-decision-of-the-user-on-the-start-method-of-camera-processes.md) | Q651 of 2026-11-23: no start method at import; the app sets spawn; a fork start is refused; nothing decided for FreeMoCap | accepted |
| [0AMX](entries/0AMX-propose-from-skellycam-and-review-in-the-kit.md) | Q657: a skellycam agent runs `propose`; the kit session reviews and commits the result in its own repository | accepted |

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
| [Q2NY](entries/Q2NY-choices-of-code-step-2.md) | Choices of code step 2: stall watch at 3 s and off in the pause, diagnostics topic and close dict, no OpenCV restore, no restore after a failure | none | proposed |
| [GEH0](entries/GEH0-choices-of-code-step-3.md) | Choices of code step 3: `not_streaming`, held value through the status, search flag, exposure range (`no-value-in-range`), 409 and 422 rules | none | proposed |
| [QJH6](entries/QJH6-choices-of-the-fix-lane.md) | Choices of the fix lane: held value at the nearest search value, `cameras_left_out`, status locks, failed start keeps the summary, OpenCV mode FOURCC | none | proposed |
| [Z7F3](entries/Z7F3-choices-of-fix-lane-3.md) | Choices of fix lane 3: restore record within one step, retry list, restore after a failure, one group creation, Media Foundation clock, median rate | none | proposed |
| [3SRX](entries/3SRX-choices-of-the-kit-sync-pilot.md) | Choices of the kit sync pilot: open-work clean-up, markers, `--replace`, Q655 value, other-systems values, uv pins in round 3, LF line ends | none | proposed |
| [0Z6Q](entries/0Z6Q-choices-of-the-certify-report-shape-build.md) | Certify build choices: B1 rows, failure facts, `total`, `not-reached`, named checks, `live-at-close` and its reasons, the build file in each build | `certify` | proposed |
| [HQE5](entries/HQE5-choices-of-fix-lane-4.md) | Choices of fix lane 4: spawn on Linux, skip guard, slow-stop gap, pace steps, restore file by hashed key, take rate sum over sum | none | proposed |
| [6RVC](entries/6RVC-choices-of-the-first-propose.md) | Choices of the first propose (other-systems rule): no entry citation in the units, hook place, a test moves, `--fill` and `--literal` | none | proposed |

The entries that are `rejected`, `superseded by XXXX`, `absorbed into <path>#<anchor>`,
`evidence; used by XXXX`, `evidence; replaced by XXXX` or `done` are in [historical.md](historical.md).
The entries that are `evidence` are in [evidence.md](evidence.md).

## Open work

The open work is in [open-work.md](open-work.md).

## Rules

<!-- kit:reading-rules -->
- Read the Active entries that apply to your task. Then you do not repeat a settled question. Before
  you make a measurement, scan the rows of `evidence.md` of each log, and read the entries that
  apply. Then you do not repeat a completed measurement. `evidence.md` and its entries are not in
  the read path. Read a Proposed entry only for work in its section, or when a skill
  tells you to. Read an entry of [historical.md](historical.md) only to find the reason for a
  decision.
- A decision that a document or code refers to must be in an entry. "This log" in an older entry or
  in the Rules means all logs.
- Delete an open-work item when the work is done. Put a dated fact in `open-work.md` or in an
  entry, not in `AGENTS.md`.
- Before you add or change an entry, a status or a row of a table, load the skill
  [`change-decision-log`](../.claude/skills/change-decision-log/SKILL.md). It gives the rules for
  each change to a log.
<!-- /kit -->
