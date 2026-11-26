# 8WX9 — Choices of the step 4b code that the user did not decide

**Status:** superseded by [BPP8](BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md), 2026-11-26 (commit to dom/preview-4b-tests; was proposed, 2026-11-26 (agent: the code lane of step 4b, go-ahead Q815 and Q855); the user accepted item 1 in Q865 and the other items in Q872, and Q864 replaced item 9).

## Decision

The product code of step 4b ([`specs/preview-4b.md`](../../specs/preview-4b.md)) is on `dom/preview-4b-tests`. The
spec and the tests are accepted. These choices fill gaps.

1. **Where the send lock and the `preview_send` bracket are.** This differs in form from item 3 of
   [ADR-GZS7](GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md) (Q839) and from
   `capture-timings.md` 6.5, which put the bracket after the lock in the server's send. Here the lock and the bracket
   are inside the relay: `PreviewRelay` gets the keyword `send_lock`, holds it around `send_bytes`, and starts the
   `preview_send` bracket and the end of `published_to_send` after it. The measured result is the same: the wait for
   the lock is not in `preview_send`. It waits for a decision of the user. With no lock (the 4a tests), nothing
   changes. `WebsocketServer` gives `_send_bytes_in_lock` (a send that needs the lock held), its `_send_lock` and the
   steps of its `PreviewTimings`. `_send_bytes` and its `preview_group` argument go: no other code sends bytes.
   Spec 4.1 item 1 states it.
2. **The interim relay tests of capture timings.** Two T-TIM-19 tests of the interim relay go with the relay
   (`capture-timings.md` 6.5: "or the interim `_frontend_image_relay` before it"). The send-lock test of T-TIM-19 now
   runs through `WebsocketServer.__init__` and its `PreviewRelay`. `StepSet.pending` goes: only the interim relay
   used it.
3. **Tests outside the list of 3.2 that used deleted names.** `test_group_watch.py` reads with
   `read_latest_ring_frames` in place of `get_latest_ring_payload` (the rule of the test does not change).
   `test_websocket_internals.py` imports `ServerFramerateCalculator` from `framerate_tracker`, not from
   `websocket_server`.
4. **No new session fixture (3.2, 7.2).** The `logging_runtime` fixture of `skellycam/tests/conftest.py` (from
   `dom/integration`) already gives `logger.success`. The endpoint tests pass with it.
5. **The counting relay of `ui_server.py`** passes each keyword of the constructor on. Without it, each connection of
   the component tests failed with a `TypeError`.
6. **The parser texts.** One `console.error` for each distinct error text and connection. A too-long and a too-short
   message have one text; the seven bad messages of T-PRV-33 write 6.
7. **`PreviewTiles`.** A tile with no label yet gets `camera: ''` (the tile draws no camera part). The state of a
   camera is made at its first message or overlay. The last frame number and mark are those of the last message given
   to the tile. A tile update that rejects clears `busy`, writes one `console.error` and sends no ready message;
   the safety net of the server sends the next message.
8. **The provider.** `useServer()` adds `setTile(id, tile)`: it calls `PreviewTiles.setTile` and gives a new tile the
   kept overlay values, because rule 9 of 5.3 drops the state at a removal. It adds `cameraLabels` for the viewer. A
   change of the camera list of the store computes the overlays and the lists again from the last `app_state`.
   `clearPending()` runs at each state that is not `CONNECTED`. At `DISCONNECTED` or `FAILED`, the provider also
   clears the `FramerateStore` and its kept overlay values (5.4 names only the camera lists).
9. **Displayed (5.8, Q826): a deviation from the spec, not a gap that is filled.** Spec 5.8 says "the rate over the
   frames drawn in the last 1 s of `now`". Test T-PRV-53 gives the store no clock: `recordDrawn(cameraId, atMs)` is
   its only time. The two conflict, and the code follows the test: the current value is the statistics of the times
   between the frames drawn in the 1 s up to the last drawn frame, so it does not fall when the window stops drawing.
   This waits for a decision of the user. Captured and Displayed store `performance.now()` times, so that the timeline
   has one clock.
10. **The viewer.** `viewer-cameras.ts` gives the cameras of the grid with their label and colour. A camera with
    no camera list label (no list entry and no config) shows its hex camera id in the viewer. One HTML legend
    names each camera with both series. The two histogram panels are one component with a `series` property. The
    table has the four count columns in each row; only the Captured row fills them. The new i18n keys are
    `capturedFramerateTooltip`, `displayedFramerateTooltip`, `<count>CountTooltip` and `framerateSourceTooltip`,
    in English only [Q8].
11. **The docs (5.9).** The copies keep their translated headings and prose, except the replaced sections, which
    are English.
12. **`statsOf`.** One function `statsOf(values, source)` gives the statistics of a set of durations, for the
    Captured and the Displayed values, in place of the class `WindowedStats` that spec 5.8 names.

## Reason

Q855 is the go-ahead of the user of 2026-11-26 for the two code lanes. The rule "smallest code that meets the spec". Item 1 is the smallest way to start the bracket after the lock with the
4a constructor. Items 2 and 3 keep each rule of a changed test.

## Alternatives rejected

- Item 1: set the private attributes of the relay after its construction, so that the constructor keeps three
  arguments: it hides the lock from the reader of the code.
- Item 8: keep the overlay values only in `PreviewTiles`: rule 9 drops them, and `app_state` comes only at a change.

## Open work

See [open-work.md](../open-work.md).
