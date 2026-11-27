# SKZ8 — Choices of the blocking half of T-PRV-17

**Status:** proposed, 2026-11-27 (agent; builds Q923 of [ADR-D2YZ](D2YZ-decisions-of-the-user-on-t-rec-36-t-prv-17-and-the-slow-holder-reading.md); waits for the user).

## Decision

1. **"B continues" in the blocking half** of T-PRV-17 (`test_t_prv_17_reader_removed_then_closed`): B gets 15 camera
   messages of frames written after the removal, with the loose limit of `preview.md` 9.1 for a count in a window
   (10 times the window: 10 s). This is not a check of the pace: it fails only when B stops or nearly stops.
2. **The window of the check of A** is at least 1 s after the removal, as before the split: the run reads until 1 s
   has passed and B has its 15 camera messages.

## Reason

1. "B continues" must mean that B still gets camera messages; the rule of 9.1 for the blocking half of a count gives
   that bound already (T-PRV-15, T-PRV-16).
2. The check of A must not get a shorter window than before.

## Open work

[open-work.md](../open-work.md)
