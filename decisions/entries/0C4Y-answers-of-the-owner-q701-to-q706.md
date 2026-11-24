# 0C4Y — Answers of the owner to Q701 to Q706 on the playback of FreeMoCap v1 recordings

**Status:** accepted, 2026-11-24 (user; the coordinator asked the questions and relayed the answers).

## Decision

The words of the owner on 2026-11-24: "Q701 - Q706 agree". The questions that he answered, each with
the recommendation that he agreed to:

1. **Q701.** "When the UI runs on another machine, is it the installed skellycam app, or a page that
   the server hands to any browser?" Recommendation: the installed Electron app.
2. **Q702.** "Remove the 'any origin' rule for these routes, check the Host header, and put login or
   pairing for a remote UI in the spec as a requirement before the server listens beyond localhost?"
   Recommendation: yes.
3. **Q703.** "Use the documented libav.js override to build against FFmpeg 9.0.2, not the plain 9.0
   inside the package?" Recommendation: yes (one more pinned input with a checksum).
4. **Q704.** "When FFmpeg publishes a new point release, the weekly job opens a bump PR that runs the
   full build and tests? This needs a token stored as a repository secret, because GitHub does not run
   workflows on a PR opened with the default token." Recommendation: yes; the owner creates the token,
   with the exact minimum permissions stated for him.
5. **Q705.** "Does 'old recordings must not be converted' cancel that step [the 'upgrade recording'
   converter, step 6d of player.md 1.3]?" Recommendation: yes, cancel it.
6. **Q706.** "Leave the v1.0.0-rc to v1.0.23-rc builds out of scope?" Recommendation: yes.

## Reason

The answers of the owner.
