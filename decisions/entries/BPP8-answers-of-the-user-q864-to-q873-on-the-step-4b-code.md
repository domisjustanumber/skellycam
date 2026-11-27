# BPP8 — Answers of the user Q864 to Q873, Q885, Q893 to Q897, Q906, Q907 and Q909 on the step 4b code

**Status:** absorbed into
[`specs/preview-4b.md#32-tests`](../../specs/preview-4b.md#32-tests),
[`specs/preview-4b.md#41-the-connection-of-previewrelay-to-the-endpoint`](../../specs/preview-4b.md#41-the-connection-of-previewrelay-to-the-endpoint),
[`specs/preview-4b.md#52-the-parser`](../../specs/preview-4b.md#52-the-parser),
[`specs/preview-4b.md#53-flow-control-previewtiles-p2-a6-agent-5`](../../specs/preview-4b.md#53-flow-control-previewtiles-p2-a6-agent-5),
[`specs/preview-4b.md#54-the-tile-for-each-camera`](../../specs/preview-4b.md#54-the-tile-for-each-camera),
[`specs/preview-4b.md#55-text-messages-in-the-provider`](../../specs/preview-4b.md#55-text-messages-in-the-provider),
[`specs/preview-4b.md#56-the-grid-and-the-camera-list`](../../specs/preview-4b.md#56-the-grid-and-the-camera-list),
[`specs/preview-4b.md#58-the-frame-rate-viewer-a7-p4-q3`](../../specs/preview-4b.md#58-the-frame-rate-viewer-a7-p4-q3),
[`specs/preview-4b.md#59-docs`](../../specs/preview-4b.md#59-docs),
[`specs/preview-4b.md#62-method-agent-9`](../../specs/preview-4b.md#62-method-agent-9),
[`specs/preview-4b.md#72-helpers-agent-11-agent-27-agent-28`](../../specs/preview-4b.md#72-helpers-agent-11-agent-27-agent-28),
[`specs/preview-4b.md#74-test-list`](../../specs/preview-4b.md#74-test-list),
[`specs/preview-4b.md#75-parity-of-the-systems-p7`](../../specs/preview-4b.md#75-parity-of-the-systems-p7),
[`specs/capture-timings.md#65-the-preview-sender-u-q587-11`](../../specs/capture-timings.md#65-the-preview-sender-u-q587-11),
2026-11-26 (commit to dom/preview-4b-tests; the open work of items 7, 8, 10, 16, 18 and 19 is in open-work.md; was accepted, 2026-11-26 (user; the supervisor relayed the answers)).

## Decision

This entry supersedes [ADR-8WX9](8WX9-choices-of-the-step-4b-code.md): the user accepted its item 1 (Q865) and its
other items (Q872), and Q864 replaces its item 9. Each answer accepts the recommendation of its question.

1. **Q864.** Spec 5.8 stays: Displayed is the rate over the frames drawn in the last 1 s of `now`. The
   `FramerateStore` gets a clock, and T-PRV-53 changes with it. A camera that stops drawing drops to 0 within 1 s.
   [`specs/preview-4b.md`](../../specs/preview-4b.md) 5.8 and 7.4 state it.
2. **Q865.** The relay form of the send lock is accepted: the lock and the `preview_send` bracket are in the relay,
   and the server passes its lock in. Spec 4.1 item 1 and [`capture-timings.md`](../../specs/capture-timings.md) 6.5
   state it. This is the form of the bracket of Q839 (item 3 of
   [ADR-GZS7](GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md)).
3. **Q866.** T-PRV-29 waits until B has sent at least 3 frames before the end of its process (7.4).
4. **Q867.** T-PRV-47 forces one page capture during the reconnect window (7.2, 7.4).
5. **Q868.** A small test-fix try: T-PRV-49 minimises window 2 in place of the hide, and the result goes to the user
   before anything else changes.
6. **Q869.** The benchmarks first turn off the copy of the websocket frames of the test tool (`Network.disable`). If
   that fails, the benchmark page runs without the tool and gives its counts through the Electron main process. The
   first clean numbers go to the user.
7. **Q870.** The tile timings (step 8 of `capture-timings.md`) are a lane of their own after the merge of 4b, tests
   first.
8. **Q871.** A later small lane deletes `read_latest_ring_frames` and `_send_json`, with the spec line and the probe
   of the three tests that use them.
9. **Q872.** The other choices of ADR-8WX9 are accepted, with the two fixes of the test support: no new session
   fixture (3.2, 7.2); the interim relay tests and the changed tests (3.2); one log line for each distinct error text
   (5.2); the choices of `PreviewTiles`, with the failed update (5.3); `setTile` and the clears at `DISCONNECTED` or
   `FAILED` (5.4); `cameraLabels` and a new camera list (5.5); `statsOf`, the hex id in the viewer and the other
   choices of the viewer (5.8); the docs copies (5.9); the keywords of the counting relay of `ui_server.py` and the
   pace-marker lists (3.2).
10. **Q873.** A later docs lane rewrites the first section of the real-time streaming page.
11. **Q885.** T-PRV-49 checks that drawing stops (`requestAnimationFrame` gives no frame) in place of the visibility
    flag, and keeps its checks of the server message count and of window 1 (7.4, 7.5).
12. **Q893.** `PreviewTiles.tick` turns the camera that gets its update first at each refresh, so that no camera is
    always last (5.3 rule 6); then the 60 fps benchmark runs again.
13. **Q894.** B-1a at 30 fps is accepted as passing, after three clean runs; the bench keeps its per-second record
    ([ADR-0ZKW](0ZKW-first-run-of-the-step-4b-preview-benchmarks.md)).
14. **Q895.** The camera grid has no grow-and-slide animation (5.6, 7.4).
15. **Q896.** `PreviewKit.close` gives each step a time limit, kills the app or the server at a time-out and logs the
    step that hung; before the branch merges (7.2).
16. **Q897.** CI gets a second type check that covers the test code of the UI, in the next CI lane (open work).
17. **Q906.** The test server `ui_server.py` sets the graceful-shutdown limit of uvicorn to 5 s, so that its stop ends
    on its own; the time limit of Q896 stays as the backstop (7.2).
18. **Q907.** A small lane, soon, spec and test first: does the product server hang at its shutdown when a client
    resets its connection (uvicorn waiting for a lost connection), and if so a shutdown time limit; the same lane
    looks at the blocked queue feeder thread (open work).
19. **Q909.** A browser test whose server had to be killed after the time limit keeps passing, with the note
    "hung step" in its report, until the lane of Q907 fixes the cause; then a kill fails the test (7.2, open work).

## Reason

The user, 2026-11-26: "agree to all Q864-Q881", and the answers Q885 and "agree to all Q893-Q902" of the same day; "Q906-907 agree" and Q909 "agree" of 2026-11-27.

## Open work

See [open-work.md](../open-work.md).
