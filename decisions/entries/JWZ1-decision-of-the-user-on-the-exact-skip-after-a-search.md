# JWZ1 — Decision of the user on the exact skip after an exposure search (Q666)

**Status:** absorbed into
[`specs/windows-capture.md#102-after-a-live-control-change-d32`](../../specs/windows-capture.md#102-after-a-live-control-change-d32),
[`specs/camera-requests.md#111-tests`](../../specs/camera-requests.md#111-tests),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-24 (user; the coordinator asked the question and relayed the answer)).

## Decision

The question of 2026-11-24: "Should it get the same exact rule, spec and test first, as a separate small
change?" The words of the user: "Q666 yes".

The check after an exposure search uses the same exact skip rule as the check after a live change
([ADR-53VB](53VB-decision-of-the-user-on-the-exact-skip-after-a-live-change.md)). The spec and the test come first.
Section 10.2 of [`windows-capture.md`](../../specs/windows-capture.md) states the rule, and T-REQ-99 of
[`camera-requests.md`](../../specs/camera-requests.md) tests it. The choices of the agent that build it are in
[ADR-0R76](0R76-choices-of-the-exact-skip-after-a-live-change.md) (proposed).

## Reason

After ADR-53VB, the check after a search still started at the return time of the last set and counted no frame
that the loop took before it read that result: it skipped 15 + k frames.

## Open work

[open-work.md](../open-work.md)
