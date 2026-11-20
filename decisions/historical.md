# Decision log: historical entries

These entries are `rejected`, `superseded by XXXX`, `absorbed into <path>#<anchor>`,
`evidence; used by XXXX` or `done`. They are not in the read path. Read an entry here only to find
the reason for a decision. The [index](README.md) has the Active and Proposed entries and the
[Rules](README.md#rules).

### Historical

| # | Decision | Status |
|---|----------|--------|
| [PEJ0](entries/PEJ0-scope-of-the-private-data-check.md) | Private-data check: skip `.ai` and `package-lock.json`, `/home/user` is a placeholder, the hook checks the commit files | absorbed into [`AGENTS.md#8-private-data`](../AGENTS.md#8-private-data), [`tools/check_private_data.py`](../tools/check_private_data.py) |
| [G5S0](entries/G5S0-no-camera-recordings-or-frames-in-git.md) | No camera recordings or camera frames in git, except golden reference files | absorbed into [`AGENTS.md#8-private-data`](../AGENTS.md#8-private-data), [`.claude/skills/commit-files/SKILL.md#camera-recordings-and-camera-frames`](../.claude/skills/commit-files/SKILL.md#camera-recordings-and-camera-frames), [`tools/check_camera_media.py`](../tools/check_camera_media.py) |
| [S222](entries/S222-bootstrap-answers-of-the-kit-adoption.md) | Answers to the bootstrap questions of the kit adoption | superseded by 2S1P |
| [C4FZ](entries/C4FZ-camera-requests.md) | Exposure Manual and Auto (a SkellyCam search, E1 to E9), one frame rate for all cameras (F1 to F4), USB link label (L1 to L5); answers Q1 to Q14 | superseded by JK79 |
| [379P](entries/379P-answers-on-the-choices-after-the-search-at-each-open.md) | Answers on B4 to B13: the apply does not wait for the search (B4 rejected); B5 to B7, B10, B13 accepted; row text; pause stays | superseded by 6QFG |
| [S6HT](entries/S6HT-choices-of-the-3a-loop-code.md) | Choices of the 3a loop code: shared status, join of the gate, one stop flag per camera, Windows warning pipe, apply response | superseded by 2GS1 |
| [MA22](entries/MA22-choices-of-the-media-foundation-source-of-step-3a.md) | Choices of the Media Foundation source of step 3a that the spec and ADR-HP7D do not fix | superseded by 2GS1 |
| [6EKB](entries/6EKB-choices-of-the-3a-review-fixes.md) | Choices of the fixes of the 3a review: detection in the apply request, `modes_read`, end order, files message after a hang | superseded by 2GS1 |
| [037V](entries/037V-completion-of-w8-the-phase-2-loop-and-its-tests.md) | Completion of W8: phase 2 loop deleted; its tests moved to the shared loop or retired for a capture test or a changed rule | superseded by 2GS1 |
| [BM73](entries/BM73-fixes-of-the-first-ci-run-of-the-capture-workflow.md) | Fixes of the first capture CI run: stats float, codec alarm on the main thread, test fixes, OpenCV fake on a virtual clock, macOS timing step, group watch | superseded by 2GS1 |
| [R60B](entries/R60B-fixes-of-the-first-hardware-run-of-step-3a.md) | Fixes of the first 3a hardware run: DirectShow device path of the OpenCV source, hardware test labels by USB IDs | superseded by 2GS1 |
| [FTC3](entries/FTC3-fixes-of-the-second-capture-ci-run-and-the-first-hardware-run.md) | Fixes of the second capture CI run and the 3a hardware run: virtual clock step, T-CAP-86 clock join, empty timing values, virtual camera links | superseded by 2GS1 |
| [162X](entries/162X-step-4a-preview-spec-and-agent-choices.md) | Step 4a spec `specs/preview.md`: per-camera preview message, its sender and 24 tests, with 27 agent choices; no open question | superseded by 68JT |
| [24FZ](entries/24FZ-python-api-of-the-preview-sender-as-the-4a-tests-assume-it.md) | Python API of the preview sender, as the 4a tests assume it: duck-typed readers, `msgspec` JSON, tick reads with no frame, log records, calculator deque | superseded by 68JT |
| [MZ02](entries/MZ02-choices-of-the-4a-code.md) | Choices of the 4a code: `no_type_check` on the sender constructor, the loop order of `run`, `closing` per camera, a send error ends `run` | superseded by 68JT |
| [EE0E](entries/EE0E-step-4b-preview-spec-and-agent-choices.md) | Step 4b spec `specs/preview-4b.md`: UI parser, flow control, shared tile, deletion, 8 x 60 fps measurement, 27 tests; 6 questions | superseded by RA16 |
| [R1TD](entries/R1TD-revision-2-of-the-step-4b-preview-spec.md) | Revision 2 of the 4b spec: grid list without `alive`, ring close on the loop, outside-observer limits; replaces 5 items of EE0E; 9 questions | superseded by RA16 |
| [W674](entries/W674-choices-of-revision-3-of-the-step-4b-spec-and-its-test-list.md) | Revision 3 of the 4b spec: choices for the answers, the full list of 27 tests, no canvas read-back; Q14 on `os_index` | superseded by RA16 |
| [Q03C](entries/Q03C-phase-5-step-5a-recorder-spec-and-test-list.md) | Step 5a spec `specs/recorder.md` and its test list; the merged format list F-1 to F-10; agent choices; no question open | superseded by P98T |
| [QEQ8](entries/QEQ8-python-api-of-the-recorder-as-the-5a-tests-assume-it.md) | Python API of the recorder as the 5a tests assume it; `dead_cameras` of `finish`; the test interpretations | superseded by P98T |
| [T24F](entries/T24F-choices-of-the-5a-recorder-code.md) | Choices of the 5a recorder code: the writer after a write error, the completion walk, the manifest merge, the lock hold, empty statistics | superseded by P98T |
| [YNM2](entries/YNM2-connection-of-the-take-recorder-to-the-shared-loop.md) | Take recorder joined to the shared loop; U4, U5, U12 and old writer gone | superseded by P98T |
| [P5VE](entries/P5VE-review-fix-choices.md) | Choices of the connection review fixes: app state, error end, abandon, kill, writer start, gap detail, save limit, status union, exposure constants, scan | superseded by P98T |
| [4K7V](entries/4K7V-phase-6a-player-spec-and-test-list.md) | Phase 6a spec `specs/player.md` (revision 2) and its test list (72 tests), with 39 agent choices | superseded by 4D94 |
| [4MJ4](entries/4MJ4-typescript-names-of-the-player-as-the-6a-tests-assume-them.md) | TypeScript names of the player, as the 6a tests assume them: test seams, pure functions, bridge, host view, test set-up | superseded by 4D94 |
| [1ACK](entries/1ACK-corrections-and-choices-of-the-6a-player-code.md) | Corrections and choices of the 6a player code: back to black, decoded prefetch images in the tile, EXIF orientation undone, manifest warnings | superseded by 4D94 |
| [5FBS](entries/5FBS-fixes-of-the-6a-code-review.md) | Fixes of the 6a code review: hard links, UNC paths, streamed reads, decode failure mark, loading message, refused take folders, unreadable `take_uuid` | superseded by 4D94 |
| [NMM1](entries/NMM1-design-of-the-camera-media-check.md) | Camera media check: types, first bytes, `GOLDEN_PATHS`, image reminder, `commit-files` skill, per-worktree hook install | superseded by XT31 |
| [4A7H](entries/4A7H-other-fills-of-the-kit-adoption.md) | Other fills of the kit adoption; `CLAUDE.md` stays untracked | superseded by XT31 |
