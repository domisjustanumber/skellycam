# EM6A — Answers of the owner to Q733 to Q749 and Q764 to Q767: the v1 playback questions of revision 5 (Q699, Q707 to Q716, Q723 to Q728)

**Status:** accepted, 2026-11-25 (user; the supervisor asked the questions in a grilling session and
relayed the answers).

## Decision

The supervisor put the open questions of section 16 of
[`player-legacy.md`](../../specs/player-legacy.md) revision 5 to the owner as session questions Q5 to
Q21, and four follow-ups as Q36 to Q39. The global number of session question Qn is Q(728 + n). Each
question was worded so that "yes" accepts its recommendation. The words of the owner on the first
round: "Q8 explain this further", "Q15 - in skellyspecs, and yes", "Q17 yes and ensure that certify
test is written", "Q18 & Q19 draft this for now, keep implementation for later", "Otherwise agree to
all". On the round with Q36 to Q39: "otherwise agree to all" (his only other words in that round were
on Q41, which is not part of this entry).

The answers:

1. **Q733 (session Q5), spec Q699, patents: yes.** The build holds the MPEG-4 Part 2 and H.264
   decoders. Their patent position is a separate decision of the owner. The work does not wait.
2. **Q734 (Q6), spec Q707, CSP: yes.** Add `'wasm-unsafe-eval'` and `worker-src 'self' blob:`.
3. **Q735 (Q7), spec Q708, timing on other systems: yes.** A certify check `player-legacy-decode`
   reports the route, the decoder information and the seek, step and play times of each camera.
4. **Q736 (Q8), spec Q709, the macOS replace path: "explain this further".** Q764 gave the
   explanation, and the owner accepted Q764 (item 18).
5. **Q737 (Q9), spec Q710, required checks: yes.** No `paths:` filter; the jobs skip by the changed
   paths.
6. **Q738 (Q10), spec Q711, the time map: yes.** The mean of the time files from the base, made
   non-decreasing; else the median header rate and `~`; a gap plays as a gap in real time.
7. **Q739 (Q11), spec Q712, synthetic test media: yes.** Made at test time with PyAV 19.0.2; the
   reference from the x86-64 Linux CI job; no media committed.
8. **Q740 (Q12), spec Q713, other eras: yes.** A v2 alpha folder is refused with a clear text. A
   v0.1.0 folder is not refused, and it gets no test and no support.
9. **Q741 (Q13), spec Q714, the demuxer: yes.** FFmpeg's demuxer in the worker; the TypeScript MP4
   reader for the frame table and the route, with a cross-check at open.
10. **Q742 (Q14), spec Q715, the tile text: yes.** After the acceptance, 6a 8.3 gets the sentence
    of spec 11.3, the fields `timeEstimated` and `detail`, and the mark `decoder_failed`.
11. **Q743 (Q15), spec Q716, the place of the spec: "in skellyspecs, and yes".** With Q765 (item 19).
12. **Q744 (Q16), spec Q723, the `Origin: null` hole: yes.** A secret header: at each start the
    Electron main process makes a 128-bit secret for the server and the page; a request without it
    gets 403 and no bytes. Not taken: a custom scheme for the UI, a fetch through the main process.
13. **Q745 (Q17), spec Q724, a switch for play that is behind: "yes and ensure that certify test is
    written".** An H.264 tile that is late on more than 20 % of the refreshes in 10 s of play switches
    to WASM once, with at least 4 cores and as many cores as H.264 tiles. The values are guesses.
    With Q766 (item 20).
14. **Q746 (Q18), spec Q725, the token of the upstream watch: "draft this for now, keep
    implementation for later".** The draft uses the default token and one approval click on each
    bump PR. With Q767 (item 21). This changes item 4 of ADR-0C4Y (Q704);
    [ADR-HN92](HN92-answers-of-the-owner-q701-to-q706-with-the-default-token.md) supersedes 0C4Y.
15. **Q747 (Q19), spec Q726, where the watch and Dependabot run: as Q746.** On the fork of the owner
    now, on the upstream repository later. With Q767.
16. **Q748 (Q20), spec Q727, the WebSocket and the other routes: yes.** `/connect` and the other
    routes get the same Origin and Host checks, in a separate spec change, owed.
17. **Q749 (Q21), spec Q728, a reclaimed codec: yes.** A new WebCodecs decoder, no switch.
18. **Q764 (Q36), the macOS replace path explained: yes.** The user who replaces the decoder file
    signs the app again with their own identity (`codesign --force --deep -s -` gives an ad-hoc
    signature), or runs it unsigned. The `README.md` of the decoder tells how. This meets LGPL 2.1,
    which has no "installation information" clause. Not taken: a replacement decoder from a folder in
    the app data of the user (a planted decoder). The question said it was not legal advice.
19. **Q765 (Q37), what moves to skellyspecs: B.** The v1 file rules go into the module
    `recording-files/` of skellyspecs: the time map (Q711), the refused eras (Q713) and the frame
    table. The player behaviour stays in `specs/player-legacy.md`. Not taken: A (the whole spec) and
    C (every skellycam spec). By Q798 (session Q70), an agent writes the rules on the skellyspecs
    branch `dom/v1-player-rules` (`SPEC.md` section 21 and the legacy annex), the player spec pins a
    commit, and nothing is pushed without a yes.
20. **Q766 (Q38), the certify test of the switch: yes.** `player-legacy-decode` also reports, for
    each tile, its late share, its route, and whether and when a switch fired.
21. **Q767 (Q39), "draft for now": yes.** The watch, token and Dependabot sections and their tests
    stay, marked "later, not built in step 6c part 1". Nothing is set up on GitHub now. This defers
    a part of Q693 of ADR-X5MZ: "suitable dependabot scripts to monitor upstream repos".

## Reason

The answers of the owner.

## Consequences

- Revision 6 of [`player-legacy.md`](../../specs/player-legacy.md) applies these answers. It stays a
  draft until the owner accepts it. It cites skellyspecs at commit `fd41818e4`.
- The choices of the agent are in [ADR-S4TJ](S4TJ-choices-of-revision-6-of-the-v1-playback-spec.md).

## Open work

See [open-work.md](../open-work.md).
