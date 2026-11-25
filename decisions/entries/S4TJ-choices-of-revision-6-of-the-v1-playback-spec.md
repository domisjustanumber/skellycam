# S4TJ — Choices of revision 6 of the v1 playback spec: the skellyspecs pin, the details of F6, the secret header and the default token

**Status:** proposed, 2026-11-25 (agent; applies the answers of the owner in
[ADR-EM6A](EM6A-answers-of-the-owner-to-the-v1-playback-questions-of-revision-5.md)).

## Decision

Revision 6 of [`player-legacy.md`](../../specs/player-legacy.md) and its test list T-LEG-01 to
T-LEG-76 (73 tests; 3 of them later). Items 42 to 49 of section 15 of the spec list the choices of
the agent. The owner did not decide them:

1. **The skellyspecs pin (2.1).** Where the spec and skellyspecs at the pinned commit differ on a
   file rule, skellyspecs wins. A new skellyspecs commit needs a new pin and an entry of this
   repository. The texts and warnings that the host shows stay in this spec. Section 2.1 lists each
   rule that left the spec, with its section of revision 5. The pin is the placeholder
   `SKELLYSPECS-PIN` until the supervisor puts in the commit.
2. **The details of F6 (3.4).** The late tile of a refresh behind the clock is each live tile whose
   newest ready frame is k*; two can be late at once. The count starts 2 s after each start of play.
   A seek, a pause, a speed change and the end of the file stop it. The rule checks only after 10 s
   of counted play, on the last 10 s. "The number of H.264 tiles" counts the H.264 tiles on either
   route. F6 applies only to a WebCodecs tile. The log line gives the share. A new module
   `legacy/late-switch.ts` holds the count.
3. **The state and report fields (10.5, 11.2).** `lateShare` (null before a full window) and
   `switchAt` (k* and the play time, `playMs` null outside play) in the camera state. The certify
   check plays 30 s on each set, reports the share for each window, and a format check of the report
   fails when a field is missing.
4. **The secret header (4.4 item 4).** The variable `SKELLYCAM_PLAYBACK_KEY`. A server started by
   hand writes `playback.key` in its app data folder (mode 0600 on Linux and macOS), with a new value
   at each start, and the main process reads that file for a server that it did not start. The check
   order is Host, secret, origin, token. The 403 text is "key missing or wrong". The compare is
   `hmac.compare_digest`. A preflight is answered with no secret and reads no file. The secret is in
   no URL, log line or report. The page also sends it on the `list_recordings` call.
5. **The default token (10.3).** Job permissions `contents: write`, `pull-requests: write`,
   `issues: write`; the refusal text when GitHub refuses the PR; the `github-actions[bot]` identity.
6. **The `dependabot.yml` repair of 10.6 is later too.** The owner accepted the repair with Q700 on
   2026-11-24. The agent reads "keep implementation for later" (Q746, Q747) as all the Dependabot
   work, so the repair waits with 10.2.
7. **`player-legacy-decode` goes into `specs/certify.md` at the acceptance of this spec**, not in
   revision 6. Another lane drafts changes of `certify.md` now, and the name has no use before the
   check exists.
8. **The tests.** New: T-LEG-73 (server: the secret at start), T-LEG-74 (unit: the main process and
   the bridge), T-LEG-75 (unit: F6), T-LEG-76 (component: a late tile switches). Changed: T-LEG-14
   (the header on each request), T-LEG-17 (the secret on each origin), T-LEG-53 (the report of
   Q766), T-LEG-62 (the default token). The kind "later" for T-LEG-60, T-LEG-62 and T-LEG-63.

## Reason

1. Each choice is the smallest rule that makes an answer of the owner testable.
2. One source for each file rule: skellyspecs is the place that freemocap and skellysync pin too
   (Q765).
3. A count with no reset after a seek or a pause would mix the late refreshes of two plays.

## Alternatives rejected

- Keep a copy of the moved rules in this spec: two texts drift apart.
- A link to a skellyspecs heading below section 21: the skellyspecs branch is not committed yet, so
  its anchors are not known. The spec links section 21 and the annex.
- Add `player-legacy-decode` to `specs/certify.md` now: it would collide with the certify spec lane.

## Open work

See [open-work.md](../open-work.md).
