# S4TJ — Choices of revision 6 of the v1 playback spec: the skellyspecs pin, the details of F6, the secret header and the default token

**Status:** proposed, 2026-11-25 (agent; applies the answers of the owner in
[ADR-EM6A](EM6A-answers-of-the-owner-to-the-v1-playback-questions-of-revision-5.md), with the fixes
of an independent review of the same day).
**Depends on:** skellyspecs 3XYN (accepted on 2026-11-25) and 91PB (proposed on 2026-11-25), in
`recording-files/decisions/`, at commit `fd41818e472f93325f833eed15184bb4c51d879b` of the branch
`dom/v1-player-rules`; no permalink until the owner approves its push.

## Decision

Revision 6 of [`player-legacy.md`](../../specs/player-legacy.md) and its test list T-LEG-01 to
T-LEG-80 (77 tests; 3 later; T-LEG-77 and T-LEG-78 are alternatives for QNEW-1). Items 42 to 52 of
section 15 list the choices. The owner did not decide them:

1. **The skellyspecs pin (2.1).** skellyspecs wins on a file rule. A new commit needs a new pin and
   an entry here. Section 2.1 maps each moved rule to SFF-896 to SFF-903. 6.3 (K) and the gap rule
   are links too. The texts that the host shows stay here; the codes follow skellyspecs (`no_index`
   in place of `no_moov`, and `no_video_track`, `no_frames`).
2. **F6 (3.4).** The late tiles of a refresh behind the clock are the live tiles whose newest ready
   frame is k*. The count runs only in play at speed 1, from 2 s after each start of play at speed 1.
   A seek, a pause, the end, a loop and a speed change stop it. The check needs 10 s of counted play.
   `lateShare` is kept for each tile on either route, also when the core rule stops a switch. "The
   number of H.264 tiles" counts both routes. Only a WebCodecs tile switches. Module
   `legacy/late-switch.ts`.
3. **The state and report fields (10.5, 11.2).** `lateShare` and `switchAt`. The certify check plays
   30 s at speed 1 and reads `lateShare` at 12 s and 22 s (windows 2 s to 12 s and 12 s to 22 s).
4. **The secret header (4.4 item 4).** `SKELLYCAM_PLAYBACK_KEY` must be 32 lower-case hexadecimal
   characters, else the server does not start; the server removes it from `os.environ`. The server
   always writes `playback.key` (mode 0600 from its creation: `os.open` with `O_EXCL` and the mode, a
   temporary file, `os.replace`). The bridge reads the file at each call; the page asks at each open,
   and once more after a 403, then repeats once. Check order Host, secret, origin, token. An empty
   header is no header; a header not of the form is wrong before the compare; the compare is of ASCII
   bytes with `hmac.compare_digest`. 403 text "key missing or wrong"; a 403 carries
   `Access-Control-Allow-Origin` only for an allowed origin. The preflight needs no secret.
5. **The default token (10.3).** Permissions `contents`, `pull-requests` and `issues` write; the
   refusal text; the `github-actions[bot]` identity.
6. **The `dependabot.yml` repair of 10.6 is later too**, with the rest of the Dependabot work.
7. **`player-legacy-decode` goes into `specs/certify.md` at the acceptance of this spec**: another
   lane drafts `certify.md` now.
8. **QNEW-1** (section 16): the three old playback routes, with the recommendation A (remove them
   in step 6c part 1).
9. **The tests.** New: T-LEG-73 to T-LEG-80. Changed: T-LEG-06, 08, 14, 17, 26, 53, 62. The kind
   "later" for T-LEG-60, 62, 63.

## Reason

1. Each choice is the smallest rule that makes an answer of the owner testable.
2. One source for each file rule: freemocap and skellysync pin skellyspecs too (Q765).
3. A count that runs through a seek, a pause or another speed mixes plays that differ.
4. The checks of item 4 turn a bad value into a refusal, not a 500, and keep the secret out of child
   processes and out of a file with a wider mode.

## Alternatives rejected

- Keep a copy of the moved rules in this spec: two texts drift apart.
- Make a new secret when the variable is bad: the page would hold a value that the server refuses.
- Add `player-legacy-decode` to `specs/certify.md` now: it would collide with the certify spec lane.
