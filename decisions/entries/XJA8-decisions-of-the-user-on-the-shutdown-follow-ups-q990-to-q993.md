# XJA8 — Decisions of the user on the shutdown follow-ups, Q990 to Q993

**Status:** absorbed into
[`specs/recorder.md#91-the-end-of-the-server-process`](../../specs/recorder.md#91-the-end-of-the-server-process),
2026-11-27 (commit to dom/shutdown-followups; was accepted, 2026-11-27 (user, Q990 to Q993)).

## Decision

The user answered "yes" to each of Q990 to Q993. Each answer accepts the recommendation of its question.

1. **Q990.** A later lane, test first, makes a second close of the same camera group do nothing. Today it raises
   `ValueError` in `CameraGroup._take_diagnostics`. It is not built now (open work).
2. **Q991.** The process test "two signals 0.1 s apart is an ordinary quit" stays a `pace` test; the blocking unit
   tests with a fake clock carry the rule.
3. **Q992.** [ADR-M5PJ](M5PJ-choices-of-the-shutdown-follow-ups-q934-q935.md) is accepted.
4. **Q993.** Only a Ctrl-C or a Ctrl-Break counts as the first press; a SIGTERM does not.

## Reason

The words of the user, above. The rules are in [`recorder.md`](../../specs/recorder.md) 9.1 item 9.
