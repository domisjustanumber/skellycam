# 53VB — Decision of the user on the exact skip after a live change (Q663)

**Status:** absorbed into
[`specs/windows-capture.md#102-after-a-live-control-change-d32`](../../specs/windows-capture.md#102-after-a-live-control-change-d32),
[`specs/windows-capture.md#162-test-list`](../../specs/windows-capture.md#162-test-list),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-23 (user; the coordinator asked the question and relayed the answer)).

## Decision

The user chose option B of Q663 on 2026-11-23: the skip count of the check after a live change is exact,
counted from the change; the test T-CAP-31 is strict.

Section 10.2 of [`windows-capture.md`](../../specs/windows-capture.md) states the rule. The choices of the agent
that build it (the anchor of the count and the mechanism) are in
[ADR-0R76](0R76-choices-of-the-exact-skip-after-a-live-change.md) (proposed).

## Reason

Fix lane 5 ([ADR-DC43](DC43-choices-of-fix-lane-5.md)) found that the product skipped 15 + k frames, where k is
the count of frames that the loop took after the change and before it read the check signal. T-CAP-31 then
failed by one frame. The spec named no first frame.

## Open work

[open-work.md](../open-work.md)
