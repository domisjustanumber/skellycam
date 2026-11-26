# HN92 — Answers of the owner to Q701 to Q706, with the default token of Q746 for the bump PR

**Status:** accepted, 2026-11-25 (user; restates the answers of 2026-11-24 in
[ADR-0C4Y](0C4Y-answers-of-the-owner-q701-to-q706.md), with the change of Q746 of 2026-11-25 in
[ADR-EM6A](EM6A-answers-of-the-owner-to-the-v1-playback-questions-of-revision-5.md)). Supersedes
0C4Y.

## Decision

The words of the owner on 2026-11-24: "Q701 - Q706 agree". Each question, with the recommendation
that he agreed to. Items 1 to 3, 5 and 6 are unchanged from 0C4Y. Item 4 changes.

1. **Q701.** "When the UI runs on another machine, is it the installed skellycam app, or a page that
   the server hands to any browser?" Recommendation: the installed Electron app.
2. **Q702.** "Remove the 'any origin' rule for these routes, check the Host header, and put login or
   pairing for a remote UI in the spec as a requirement before the server listens beyond localhost?"
   Recommendation: yes.
3. **Q703.** "Use the documented libav.js override to build against FFmpeg 9.0.2, not the plain 9.0
   inside the package?" Recommendation: yes (one more pinned input with a checksum).
4. **Q704, as Q746 changes it.** Q704 asked: "When FFmpeg publishes a new point release, the weekly
   job opens a bump PR that runs the full build and tests? This needs a token stored as a repository
   secret, because GitHub does not run workflows on a PR opened with the default token."
   Recommendation: yes; the owner creates the token, with the exact minimum permissions stated for
   him. Kept: the weekly job opens a bump PR for a new FFmpeg point release, and the PR runs the full
   build and tests. Changed on 2026-11-25 by Q746 (spec Q725), with the words of the owner "Q18 & Q19
   draft this for now, keep implementation for later": the job uses the default token, and the owner
   accepts one "Approve workflows to run" click on each bump PR, in place of a personal token. By
   Q767 this part is a draft, not built in step 6c part 1.
5. **Q705.** "Does 'old recordings must not be converted' cancel that step?" Recommendation: yes,
   cancel it. Context added by the coordinator when he relayed the question, not in the quote:
   "that step" is the "upgrade recording" converter, step 6d of player.md 1.3.
6. **Q706.** "Leave the v1.0.0-rc to v1.0.23-rc builds out of scope?" Recommendation: yes.

## Reason

The answers of the owner. The text of Q704 was not exact: with the default token, GitHub runs the
workflows of the PR after one approval click (section 10.3 of
[`player-legacy.md`](../../specs/player-legacy.md)). Q746 took the click.
