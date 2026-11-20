# Z3Y7 — Acceptance of the step 5a recorder spec and its test list

**Status:** absorbed into
[`specs/recorder.md#phase-5-step-5a-specification-the-new-video-recorder`](../../specs/recorder.md#phase-5-step-5a-specification-the-new-video-recorder),
[`specs/recorder.md#2-done-list`](../../specs/recorder.md#2-done-list),
[`specs/recorder.md#13-proposed-format-changes-one-list-for-the-recorder-and-the-player`](../../specs/recorder.md#13-proposed-format-changes-one-list-for-the-recorder-and-the-player),
[`specs/recorder.md#16-choices-of-the-agent`](../../specs/recorder.md#16-choices-of-the-agent),
2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user; relayed to the agent that
writes the failing tests; commit to dom/recorder)).

## Decision

The user accepted [`specs/recorder.md`](../../specs/recorder.md) and its test list (step 5a) on
2026-11-20. The spec is the one of
[ADR-Q03C](Q03C-phase-5-step-5a-recorder-spec-and-test-list.md), at its revision of 2026-11-20. It
follows R1 to R12 of [ADR-VPF8](VPF8-phase-5-recorder-decisions.md) and M1 to M10 and C1 to C7 of
[ADR-J3QP](J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md).

- The failing tests of step 5a come next, then the product code (R12).
- The format changes F-1 to F-10 of section 13 still wait for a decision of the user (R6, item 4 of
  the done list of section 2).
- One stale sentence is corrected in the same commit: agent choice 13 of section 16 now says that
  `last_frame` is the position of the last row that is not `missing`. Sections 4.3 and 7.3 and
  T-REC-23 already state this rule.

## Reason

- R12: the user accepts the spec and its test list before any code.

## Open work

See [open-work.md](../open-work.md).
