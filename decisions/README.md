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
| [EQY4](entries/EQY4-base-the-work-on-upstream-sfn26-without-rust.md) | Base the work on upstream `sfn26`: keep our camera layer and recorder, remove each Rust part, four ports, PRs to upstream `development` | accepted |
| [GVC0](entries/GVC0-certify-decisions-of-the-user.md) | Certify run of skellycam: levels, quick camera checks and 3 s take, camera summary list, rules that hold everywhere, fake cameras, functions, draft 1 answers | accepted |
| [2GS1](entries/2GS1-step-3a-choices-of-the-capture-code-and-its-fixes.md) | Supersedes S6HT, MA22, 6EKB, 037V, BM73, R60B, FTC3: step 3a choices; virtual by link; macOS timing step; loop, source, review and CI fixes | accepted |
| [68JT](entries/68JT-step-4a-choices-of-the-preview-sender.md) | Supersedes 162X, 24FZ, MZ02: step 4a choices of the preview sender; spec section 13 items, Python API of the 4a tests, code choices | accepted |
| [P98T](entries/P98T-step-5a-choices-of-the-recorder-and-its-connection.md) | Supersedes Q03C, QEQ8, T24F, YNM2, P5VE: step 5a recorder and connection choices; F-1 to F-10 as one request; 15 s writer limit | accepted |
| [4D94](entries/4D94-step-6a-choices-of-the-canvas-player.md) | Supersedes 4K7V, 4MJ4, 1ACK, 5FBS: step 6a player choices; picked folders only for the app run, no list file; test names; review fixes | accepted |
| [XT31](entries/XT31-kit-adoption-choices-camera-media-check-and-fills.md) | Supersedes NMM1, 4A7H: kit adoption choices; the media check refuses PNG, GIF, WebP, SVG with an allow by path; index limit 24,000 | accepted |
| [6T78](entries/6T78-choices-of-the-sfn26-integration.md) | Choices of the `sfn26` integration: OpenCV helpers stay ours, kept and dropped items, forms of the four ports, Rust removal | accepted |
| [X1T8](entries/X1T8-two-way-kit-sync-adoption.md) | Two-way kit sync: skellycam is the pilot; values in `kit.toml`; Python 3.13; the winners of 19 differences; CI runs only `check`; kit uv | accepted |
| [0AMX](entries/0AMX-propose-from-skellycam-and-review-in-the-kit.md) | Q657: a skellycam agent runs `propose`; the kit session reviews and commits the result in its own repository | accepted |
| [4CAF](entries/4CAF-choices-of-the-close-of-the-queues-of-a-group.md) | Choices of fix lane 8: a closed group closes its queues and leaves the pubsub registry (windows-capture.md 5.9, T-CAP-114) | accepted |
| [JC4X](entries/JC4X-choices-of-the-gate-probe-of-a-second-app-on-the-test-clock.md) | Choices of fix lane 8: a second app of one test wraps the product gate probe, so `shut` never calls the test clock (T-UNX-98 stuck thread) | accepted |
| [GZS7](entries/GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md) | Q837 to Q841, Q814 to Q816: capture timings choices (first summary, read budget, rounding, send lock); merge order; clean-up lane; test branches | accepted |
| [ZEX9](entries/ZEX9-decisions-of-the-user-on-the-housekeeping-of-2026-11-25.md) | Q729 to Q732, Q751: untrack 65 media files of `dom/research`, trim plan section 15, push two branches, delete the H.264 temp files | accepted |
| [N6X6](entries/N6X6-decisions-of-the-user-on-the-build-lanes-of-2026-11-25.md) | Q750, Q772, Q775, Q776, Q780: three build lanes, two certify lanes, quick tests only around fix lane 7; ask before performance tests | accepted |
| [6YGH](entries/6YGH-acceptance-of-the-as-built-choices-of-fix-lanes-4-and-5-and-of-certify.md) | Q752 to Q757, Q759 to Q762, Q770: HQE5 Q-A to Q-C, DC43 1 to 4, KY81 rest, items of 8CP7 and FC1C accepted as built | accepted |
| [ZRA6](entries/ZRA6-choices-of-the-certify-test-lane.md) | Certify test lane (Q772, Q773, Q775): `no-frame`, the dark rule as pure functions, `bad-output`, `exit_code` of a crash, the native choice, Q624 names | accepted |
| [X5MZ](entries/X5MZ-rules-of-the-owner-for-the-playback-of-freemocap-v1-recordings.md) | v1 playback rules of the owner: reliable first, short seek second; play as-is; UI on another machine; no server decode; only v1; Q693 libav.js with Dependabot | accepted |
| [8EBK](entries/8EBK-answers-of-the-owner-q685-q688-q697-q698-q700.md) | v1 playback answers Q685, Q688, Q697, Q698, Q700: server route, one player, decoder built in CI, sample data in CI, HEVC refused, K, warnings | accepted |
| [HN92](entries/HN92-answers-of-the-owner-q701-to-q706-with-the-default-token.md) | Supersedes 0C4Y: v1 playback answers Q701 to Q706; Q704 bump PR with the default token and one approval click (Q746, draft) | accepted |
| [VHD3](entries/VHD3-answers-of-the-owner-q694-q717-q718.md) | v1 playback answers Q694, Q717, Q718: WebCodecs for H.264 in each phase, WASM for `mp4v`, WASM `h264` fallback per tile, 8-bit 4:2:0 H.264 later | accepted |
| [A56K](entries/A56K-choices-of-the-v1-playback-spec.md) | Draft `specs/player-legacy.md` rev. 5, T-LEG-01 to 72: WebCodecs route and WASM fallback, frame table and seek rules, locked play, decoder build, Dependabot | accepted |
| [EM6A](entries/EM6A-answers-of-the-owner-to-the-v1-playback-questions-of-revision-5.md) | v1 playback answers Q733 to Q749, Q764 to Q767: file rules to skellyspecs, secret header, F6 too slow, macOS re-sign, default token, watch later | accepted |
| [8CP7](entries/8CP7-certify-spec-draft-3-choices-of-the-agent.md) | Certify spec draft 3 on format 1.4.0, tests T-CERT-01 to 67, 15 agent choices: split checks, model item, gate roll-ups, local record, macOS probes | accepted |
| [PA3A](entries/PA3A-decision-of-the-user-on-the-test-workflow-on-dom-integration.md) | "Yes": `test.yml` runs on each push to `dom/integration`: ruff, the test suite and the UI typecheck | accepted |
| [88HQ](entries/88HQ-decisions-of-the-user-on-q842-to-q856.md) | Q842 to Q856: J1HD and TYH0 accepted, the stall watch at 2 s, the player label and picked folders, absorb sentences, N72V, push rule | accepted |

### Proposed

These entries wait for a decision of the user. Section is the section or area of the change, or
`none`.

| # | Decision | Section | Status |
|---|----------|---------|--------|
| [Y6F6](entries/Y6F6-camera-request-choices.md) | Choices A1 to A23 of `specs/camera-requests.md`: search limits, held value, endpoint and texts, slow-camera texts, 60 fps check, fall back, `usb_link` | none | proposed |
| [4Z7T](entries/4Z7T-choices-after-the-search-at-each-open.md) | Choices B1 to B21 after the search at each open: order and limits of an open, held value, state route, search count, manager call | none | proposed |
| [AT04](entries/AT04-choices-of-the-linux-and-macos-capture-spec.md) | Spec `specs/unix-capture.md`, tests T-UNX: stdlib V4L2, PyObjC 13.0, identity, exposure map, controls, JPEG fallback, failure codes, diagnostics | `skellycam.core.camera.capture` | proposed |
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
| [0R76](entries/0R76-choices-of-the-exact-skip-after-a-live-change.md) | Choices of the exact skip after a live change and a search: anchors, the time-out anchor, replay of 1024 taken frames, limits | `skellycam.core.camera.capture` | proposed |
| [B7YV](entries/B7YV-choices-of-fix-lane-6.md) | Choices of fix lane 6: one run for the two halves, nominal values and loose checks, T-PRV-54, loop threads on the test clock, T-CAP-86 diagnostics | none | proposed |
| [7GC1](entries/7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md) | Choices of fix lane 6: a loop at an open gate holds the test clock until its next probe, forced steps still move it; T-CAP-05 checks the last ring frames | none | proposed |
| [JFG4](entries/JFG4-choices-of-the-capture-timings-build.md) | Choices of the capture timings build that the user did not decide: source sets, sets, main process, message loop, route, test seams, faults | none | proposed |
| [QF7V](entries/QF7V-choices-of-the-test-workflow-on-dom-integration.md) | Choices of the push run of `test.yml`: no run for log-only pushes, no macOS job on a push, pinned labels, PortAudio, no `capture_local`, no fail-fast, 60 min | none | proposed |
| [4PPS](entries/4PPS-choices-of-the-answers-lane-of-q842-to-q856.md) | Choices of the answers lane: the label from `<recording_name>_info.json` with a fall back, no `pickedFoldersFile`, the 2 s test bounds, Q852 sentences | none | proposed |

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
