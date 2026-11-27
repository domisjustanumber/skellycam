# D6YZ — Decisions of the user on the server spawn lane, Q961 and Q973 to Q975

**Status:** accepted, 2026-11-27 (user, Q961, Q973 to Q975).

## Decision

The user answered on 2026-11-27. A "yes" accepts the recommendation of its question.

1. **Q961.** Yes: the branch `dom/server-spawn` merges under the usual rule.
2. **Q973.** Yes: the app keeps dropping the stdout of the server, with no copy in the log of the app
   ([`recorder.md`](../../specs/recorder.md) 9.3 item 2).
3. **Q974.** Yes: [ADR-YR3G](YR3G-choices-of-the-server-spawn-lane.md) is accepted once the review says that the
   branch is safe. The supervisor changes its status at the merge.
4. **Q975.** The user tries the packaged Windows app by hand (a start, a take, a quit) after the merge, not before.

## Reason

The words of the user, above.

## Open work

See [open-work.md](../open-work.md).
