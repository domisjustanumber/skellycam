# 8WX9 — Choices of the step 4b code that the user did not decide

**Status:** proposed, 2026-11-26 (agent: the code lane of step 4b, go-ahead Q815 and Q855).

## Decision

The product code of step 4b ([`specs/preview-4b.md`](../../specs/preview-4b.md)) is on `dom/preview-4b-tests`. The
spec and the tests are accepted. These choices fill gaps.

1. **The send lock of the preview sender (Q839).** `PreviewRelay` gets the keyword `send_lock`. When it is given, the
   relay holds it around `send_bytes`, and the `preview_send` bracket and the end of `published_to_send` start after
   the lock. With no lock (the 4a tests), nothing changes. `WebsocketServer` gives `_send_bytes_in_lock` (a send that
   needs the lock held), its `_send_lock` and the steps of its `PreviewTimings`. `_send_bytes` and its `preview_group`
   argument go: no other code sends bytes. Spec 4.1 item 1 states it.
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
   to the tile.
8. **The provider.** `useServer()` adds `setTile(id, tile)`: it calls `PreviewTiles.setTile` and gives a new tile the
   kept overlay values, because rule 9 of 5.3 drops the state at a removal. It adds `cameraLabels` for the viewer. A
   change of the camera list of the store computes the overlays and the lists again from the last `app_state`.
   `clearPending()` runs at each state that is not `CONNECTED`.
9. **Displayed (5.8, Q826).** The current value is the statistics of the times between the frames drawn in the 1 s
   up to the last drawn frame. Captured and Displayed store `performance.now()` times, so that the timeline has one
   clock.
10. **The viewer.** `viewer-cameras.ts` gives the cameras of the grid with their label and colour. One HTML legend
    names each camera with both series. The two histogram panels are one component with a `series` property. The
    table has the four count columns in each row; only the Captured row fills them. The new i18n keys are
    `capturedFramerateTooltip`, `displayedFramerateTooltip`, `<count>CountTooltip` and `framerateSourceTooltip`,
    in English only [Q8].
11. **The docs (5.9).** The copies keep their translated headings and prose, except the replaced sections, which
    are English.

## Reason

The rule "smallest code that meets the spec". Item 1 is the smallest way to start the bracket after the lock with the
4a constructor. Items 2 and 3 keep each rule of a changed test.

## Alternatives rejected

- Item 1: set the private attributes of the relay after its construction, so that the constructor keeps three
  arguments: it hides the lock from the reader of the code.
- Item 8: keep the overlay values only in `PreviewTiles`: rule 9 drops them, and `app_state` comes only at a change.

## Open work

See [open-work.md](../open-work.md).
