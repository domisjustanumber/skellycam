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
