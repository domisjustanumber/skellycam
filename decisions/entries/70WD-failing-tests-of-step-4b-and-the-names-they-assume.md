# 70WD — The failing tests of step 4b, and the names and choices that they assume

**Status:** accepted, 2026-11-25 (user: Q824 of [ADR-NA1N](NA1N-answers-of-the-user-to-the-questions-of-the-step-4b-tests.md); agent choices for the tests of the go-ahead of
[ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)).

## Decision

The tests of 7.4 of [`specs/preview-4b.md`](../../specs/preview-4b.md) are written, with the helpers of 7.2. There
is no product code of 4b. Each test name starts with its spec ID. The user accepted these choices (Q824).

1. **Files.** `tools/write_camera_message_fixture.py`, its test and the fixture `camera-messages.json`; in
   `skellycam/tests/preview/`: `test_endpoint.py`, `test_ring_close_on_loop.py`, `test_old_format_deleted.py`,
   `test_interface_note.py`, `barcode_jpegs.py`, `ui_server.py`. UI: `src/services/server/preview/tests/unit/`,
   `src/components/camera-views/tests/` and `src/player/tests/harness/observer.ts` (the bench observer, moved).
2. **Names that the tests assume.** `camera-message.ts` and `PreviewTiles` are as 5.2 and 5.3 give them. Also:
   - `server-messages.ts`: `appStateValues(message, cameraList)` gives `{overlays, gridCameraIds,
     connectedCameraIds}`, with `overlays[id]` = `{label, cameraState}`; `rateTexts(message)`;
     `isFramerateUpdate(data)`.
   - `FramerateStore`: `recordFramerateUpdate`, `recordAppState`, `recordDrawn(cameraId, atMs)`, `cameraIds()`,
     `clear()`, `getCamera(id)`: `null`, or `{captured, displayed, notShown, ringSkipped, oversize, replaced}`, where
     `captured` and `displayed` are `{current, aggregate}` of `DetailedFramerate`.
   - `cameraLabel` and `labelText` of `camera-labels.ts`. `camera-requests.md` 1.8 replaced `withCameraLabels`
     with `labelText`. `cameraLabel` is the code name of `cameraListLabel` of 5.4; no document renamed it.
   - `useServer()` gets `getPreviewTiles()` and `gridCameraIds`; each tile canvas has `data-camera-id`. The viewer
     keeps `.framerate-viewer` and `.framerate-collapsed-summary`; its series are `svg [data-camera-id][data-series]`
     (colour: the fill of a `rect`, else the stroke); the labels are in the SVG texts or an HTML legend; each count
     header starts with its text of 5.8; the collapsed text is `<label>: Captured <x> fps, Displayed <y> fps`.
3. **Displayed in T-PRV-53 is the recent value** (`displayed.current`). The window mean after both parts is 40 fps,
   not 60. A value over the last 1 s of drawn frames passes. `displayed.aggregate` shows that the gap, the flagged
   message and the overlay update add no value.
4. **T-PRV-26 is split** into a blocking and a `pace` test on one run, as Q670 of
   [ADR-F4N7](F4N7-decisions-of-the-user-on-the-pace-tests-of-fix-lane-6.md) splits the 4a tests.
5. **T-PRV-30 matches whole words**, else `FRAME_HEADER_SIZE` matches `CAMERA_FRAME_HEADER_SIZE` (5.2). A 4b test
   file builds an old key at run time (`['backend', 'framerate'].join('_')`). `test_group_watch.py` of the capture
   tests uses `get_latest_ring_payload`: 3.2 does not list it, but the 4b code must change it.
6. **T-PRV-33**: a second give of a bad message writes no `console.error`; the seven messages write 4 to 7.
7. **T-PRV-29** uses PROCESS workers; B ends with `on_arm="exit"`; the restart is an apply with a retry of B.
   **T-PRV-28** uses 1920 x 1080 rings, and closes the client inside the test client context, whose exit cancels
   each task itself.
8. **Helpers.** `FakeRing` takes `width` and `height`. `WsClient.texts` keeps each text that is not JSON.
9. **`ui_server.py`** reads one JSON command for each stdin line and replies on lines that start with
   `@ui_server `. It counts the ready messages with a subclass of `PreviewRelay` (4a API only). Its fake manager is
   also a `CameraGroupManager` (beartype). Its scripted `alive` follows
   [ADR-NYT6](NYT6-choices-of-fix-lane-2.md). The capture mode runs the group on the uvicorn loop (4.3).
10. **Component tests.** T-PRV-44 holds A on its second open (a retry), because a camera cannot join a running
    group; it records `alive` and does not check it (item 13). T-PRV-47 accepts `DISCONNECTED` or `FAILED` and
    allows only connection errors in the console. T-PRV-48 checks D, B, C, A, in the DOM and on the screen.
    T-PRV-50 reads "3, 1 and 7" as Oversize, Ring skipped, Replaced. T-PRV-49 checks window 1 against the frames
    written.
11. **Harness and configs.** `PLAYER_HARNESS_PRODUCT_THROTTLING=1` and `openWindow(name, {productThrottling})` give
    the product throttling (T-PRV-49). `tsconfig.json` excludes `src/components/camera-views/tests` and
    `src/services/server/preview/tests`, as the player tests; `npx tsc --noEmit` has 0 errors. The npm script and
    the Playwright configs change as 7.8 says.
12. **Player tests of 7.6.** A `frame: null` check in `format.test.ts` (T-PLAY-37) and a last step of T-PLAY-44.
13. **T-PRV-44 and `alive`.** Since ADR-NYT6 the group is alive while one selected camera lives (4.5). T-PRV-44
    now reads "three tiles, with no filter on `alive`" (Q830).
14. **T-PRV-25 and CI.** `doc-checks.yml` syncs only the dev group, and T-PRV-25 imports `skellycam`. The test
    stays in `tools/tests/` and runs only in the capture jobs (Q836, 7.8).

## Reason

The rule "a spec and a test list before code". The names fill gaps of the spec, so the code agent has one list.

## Consequences

- The 4b code must use the names of item 2, or this entry changes first.
- The component tests and the benchmarks did not run (real time). Their first run can show faults in the tests.

## Open work

See [open-work.md](../open-work.md).
