# 2Z2D — Answers of the owner to Q800 to Q803: the old playback routes go in step 6c part 1, and acceptance of the v1 playback spec

**Status:** absorbed into
[`specs/player-legacy.md#phase-6-player-specification-step-6c-part-1-playback-of-freemocap-v1-recordings`](../../specs/player-legacy.md#phase-6-player-specification-step-6c-part-1-playback-of-freemocap-v1-recordings),
[`specs/player-legacy.md#44-network-exposure-q701-yes-q702-yes`](../../specs/player-legacy.md#44-network-exposure-q701-yes-q702-yes),
[`specs/player-legacy.md#52-what-goes-and-when-agent-12-q800-a-agent-53`](../../specs/player-legacy.md#52-what-goes-and-when-agent-12-q800-a-agent-53),
[`specs/player-legacy.md#105-decoder-timing-on-linux-and-macos-the-certify-check-q708-yes-q766-yes`](../../specs/player-legacy.md#105-decoder-timing-on-linux-and-macos-the-certify-check-q708-yes-q766-yes),
[`specs/player-legacy.md#106-the-dependabotyml-of-today-later-q700-yes-q802-yes`](../../specs/player-legacy.md#106-the-dependabotyml-of-today-later-q700-yes-q802-yes),
[`specs/certify.md#362-the-check-catalogue-for-each-level`](../../specs/certify.md#362-the-check-catalogue-for-each-level),
2026-11-25 (commit to dom/legacy-player; was accepted, 2026-11-25 (user; the supervisor asked the
questions and relayed the answers)).

## Decision

The words of the owner on 2026-11-25: "otherwise agree to all" (his other words in that round were
on Q811, which is not part of this entry). Each question below was answered with its
recommendation:

1. **Q800 (the open question QNEW-1 of the review fixes): A.** Remove `list_videos`, `stream_video`,
   `get_all_timestamps`, their URLs in `server-urls.ts` and the old `<video>` player branch in step
   6c part 1, in the PR that lands the v1 player. Test T-LEG-77; T-LEG-78 is dropped.
2. **Q801.** Revision 6 of [`player-legacy.md`](../../specs/player-legacy.md) (commit ab9ce3b81) is
   accepted, with the proposed choices of
   [ADR-S4TJ](S4TJ-choices-of-revision-6-of-the-v1-playback-spec.md) and
   [ADR-A56K](A56K-choices-of-the-v1-playback-spec.md).
3. **Q802.** The repair of the Dependabot folder (spec 10.6) is "later" too.
4. **Q803.** `player-legacy-decode` goes into [`specs/certify.md`](../../specs/certify.md) at the
   acceptance (now).

## Reason

The answers of the owner.

## Consequences

- The tests of step 6c part 1 can now be written. The code comes after them.
- With the acceptance, [`player.md`](../../specs/player.md) 8.3 gets the text of Q742
  ([ADR-EM6A](EM6A-answers-of-the-owner-to-the-v1-playback-questions-of-revision-5.md) item 10).
- The choices that the agent made to apply Q800 and Q803 are in
  [ADR-TYH0](TYH0-choices-after-the-acceptance-of-the-v1-playback-spec.md) (proposed).
