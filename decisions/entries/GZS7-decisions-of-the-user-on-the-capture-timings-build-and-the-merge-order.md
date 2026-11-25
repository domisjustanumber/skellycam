# GZS7 — Decisions of the user on the capture timings build, the merge order and the test branches

**Status:** accepted, 2026-11-25 (user; Q800 to Q841, to which the user answered "otherwise agree to all" with
Q811 apart; this entry holds Q814 to Q816 and Q837 to Q841; commit to dom/capture-timings-build).

## Decision

Each answer accepts the recommendation of the question.

1. **Q837.** Item 1 of [ADR-JFG4](JFG4-choices-of-the-capture-timings-build.md) stays: the publish that applies a
   change to on starts the first window and sends `timings = None`; the next publish sends the first summary, up
   to about 2 s after the change. The publish that applies a change to off sends None.
2. **Q838.** The read budget of ADR-JFG4 item 3: at most 10 clock reads of the loop thread for each frame for the
   steps of cadence `frame`, plus one for each refused pass and three for each granted pass that gives no frame; a
   step of cadence `event` adds its own 2 reads on its frame. Brackets that follow one another share one read;
   `should_record_frame_number` stays outside each bracket; the OpenCV `camera_wait` ends at `pre_ns`. The two
   spec corrections of ADR-JFG4 item 13 stand: the route is `/skellycam/camera/timings` also in skellycam alone,
   and the three reads of a granted pass with no frame.
3. **Q839.** In step 4b, the `preview_send` bracket of `PreviewRelay` starts after the send lock: the server's
   locked send takes the bracket, as for the interim relay (ADR-JFG4 item 8, in this form).
4. **Q840.** Rounding is half up in integers: `ms = ((ns + 500) // 1000) / 1000`, and `window_s` the same way
   (ADR-JFG4 item 6).
5. **Q841.** `dom/capture-timings-build` merges into `dom/integration` first, then the clean-up lane of Q814, then
   the other branches. Each merge runs the tests that no CI job runs on a push.
6. **Q814.** One decision-log clean-up lane before the next merges: it absorbs the Active entries that the specs
   state, moves DC43, KY81 and 8CP7 to accepted, and resolves the overlapping absorbs.
7. **Q815.** A branch of failing tests (JPEG encode, 4b) stays unmerged. Each code lane builds on its test
   branch; the tests and the code merge together when they pass.
8. **Q816.** `dom/legacy-player`, `dom/exclusive-access-spec` and `dom/jpeg-encode-tests` are pushed to the fork
   as a backup, with no PR.

Items 1 to 4 are in [`capture-timings.md`](../../specs/capture-timings.md) sections 2, 5.2, 5.3 and 6.5. Items 5
to 8 are process rules and actions; [open-work.md](../open-work.md) holds items 5 to 7.

## Reason

The user gave no reason other than the answers. The agent gave these with the questions: item 1 keeps each summary
on a window that was on from its start to its end; item 2 counts the steps that run on each frame, and the take
and the search never share a frame; item 4 gives the same JSON in Python and TypeScript (Q569).

## Open work

See [open-work.md](../open-work.md).
