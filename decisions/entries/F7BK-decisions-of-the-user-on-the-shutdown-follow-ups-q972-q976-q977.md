# F7BK — Decisions of the user on the shutdown follow-ups, Q972, Q976 and Q977

**Status:** accepted, 2026-11-27 (user, Q972, Q976, Q977).

## Decision

The user wrote on 2026-11-27: "Otherwise agree to Q964-975" (Q972) and "Q976 & 977 agree".

1. **Q972.** `ManagedThread.join` returns at once for a thread that was never started.
2. **Q976.** The strict `xfail` test for the known fault of the THREAD mode stays, with the fault in open work. When
   a change fixes that fault, the strict mark shows it, and the mark goes.
3. **Q977.** The server forces its exit (`os._exit`) only when both hold: a second Ctrl-C arrived, and 5 s later a
   thread still runs. Test first: the test shows that the camera processes end and that the port is free after it.

## Reason

The words of the user, above. A disk call that hangs inside a take start or stop holds the exit with no bound
(ADR-4W3H); after a second Ctrl-C the user wants every process to stop (Q934). The rules are in
[`recorder.md`](../../specs/recorder.md) 9.1 items 8 and 9; the choices of the agent are in
[ADR-M5PJ](M5PJ-choices-of-the-shutdown-follow-ups-q934-q935.md).
