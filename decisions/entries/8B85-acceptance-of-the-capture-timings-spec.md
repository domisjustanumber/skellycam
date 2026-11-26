# 8B85 — The user accepts the capture timings spec and its build order

**Status:** absorbed into
[`specs/capture-timings.md#11-build-order`](../../specs/capture-timings.md#11-build-order),
[`specs/capture-timings.md#14-decisions-of-the-user`](../../specs/capture-timings.md#14-decisions-of-the-user),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-23 (user; question Q587, to which the user answered "Q587 agree"; commit to
dom/timings-spec)).

## Decision

The user decided this on 2026-11-23. It is not built.

1. **Q587.** The user accepts [`specs/capture-timings.md`](../../specs/capture-timings.md) (draft 2, with
   the six edits of the second review), with its test list T-TIM-01 to T-TIM-26, and the choices of the
   agent of [ADR-8Z0Q](8Z0Q-choices-of-the-capture-timings-spec.md) as a set. The spec now marks those
   choices [U Q587 n].
2. **Build order.** The build starts after `dom/fix-lane-3` merges into `dom/integration`. The capture
   side comes first (steps 1 to 7 of section 11 of the spec). The tile part (step 8) comes with step 4b.

The earlier decisions of the user on this subject are in
[ADR-MX8V](MX8V-decisions-of-the-user-on-capture-timings.md).

## Reason

The user gave no reason other than the answer above. The spec had passed a second independent review,
which found it ready for the user with six small edits. The user was told of the six edits.

## Open work

See [open-work.md](../open-work.md).
