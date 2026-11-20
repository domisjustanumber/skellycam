# YV3V — Acceptance of the phase 6a player spec and its test list

**Status:** accepted, 2026-11-20 (user; relayed by the supervisor; commit to dom/player).

## Decision

The user accepted [`specs/player.md`](../../specs/player.md) and its test list (step 6a) on
2026-11-20. This is revision 2 of the spec, with the tests T-PLAY-01 to T-PLAY-72 (40 unit, 16
component, 10 electron, 6 benchmark).

The failing tests of step 6a come next. The product code of step 6a comes after the failing tests.

The agent choices of the spec stay in
[ADR-4K7V](4K7V-phase-6a-player-spec-and-test-list.md) (section 16 of the spec). The decisions that
the spec applies are in [ADR-J2BQ](J2BQ-phase-6-player-decisions-y1-to-y7.md) and
[ADR-4HNY](4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md).

## Reason

Y1 and the rule "spec and tests before code" need an accepted spec and test list before the tests and
the code of step 6a.
