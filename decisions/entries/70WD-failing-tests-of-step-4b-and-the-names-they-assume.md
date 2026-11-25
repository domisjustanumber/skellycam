# 70WD — The failing tests of step 4b, and the names and choices that they assume

**Status:** proposed, 2026-11-25 (agent; the tests of the go-ahead of
[ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)).

## Decision

The tests of section 7.4 of [`specs/preview-4b.md`](../../specs/preview-4b.md) are written, with the helpers of
7.2. There is no product code of step 4b. Each test name starts with its spec ID. The choices below are of the
agents. The user did not decide them.

1. **Files.** Python: `tools/write_camera_message_fixture.py` with its test, the fixture
   `skellycam-ui/src/services/server/preview/tests/camera-messages.json`, and these files in `skellycam/tests/preview/`:
   `test_endpoint.py`, `test_ring_close_on_loop.py`, `test_old_format_deleted.py`, `test_interface_note.py`,
   `barcode_jpegs.py` and `ui_server.py`. UI: the unit tests in `src/services/server/preview/tests/unit/`, the
   component tests, the harness page and the benchmark in `src/components/camera-views/tests/`, and
   `src/player/tests/harness/observer.ts` (the observer of the player bench, moved with no change of method).
2. **TypeScript names that the tests assume.** `camera-message.ts` and `PreviewTiles` are as 5.2 and 5.3 give them.
   The spec gives no other names, so the tests use these:
   - `server-messages.ts`: `appStateValues(message, cameraList)` gives `{overlays, gridCameraIds,
     connectedCameraIds}`, where `overlays[id]` is `{label, cameraState}`. `rateTexts(message)` gives a rate text
     or `null` for each camera id. `isFramerateUpdate(data)` is the guard of 5.5.
   - `FramerateStore`: `recordFramerateUpdate(message)`, `recordAppState(message)`, `recordDrawn(cameraId, atMs)`,
     `cameraIds()`, `clear()`, and `getCamera(id)`. `getCamera` gives `null` for an unknown camera. Else it gives
     `{captured, displayed, notShown, ringSkipped, oversize, replaced}`, where `captured` and `displayed` are each
     `{current, aggregate}` of the type `DetailedFramerate`.
   - The label functions are `cameraLabel` and `labelText` of `camera-labels.ts`. `camera-requests.md` 1.8
     replaced `cameraListLabel` and `withCameraLabels` with these names, and T-REQ-28 fails when any file names
     `withCameraLabels`.
   - `useServer()` gets `getPreviewTiles()` and `gridCameraIds`. The canvas of each tile has
     `data-camera-id="<id>"`. The frame rate viewer keeps `.framerate-viewer` and `.framerate-collapsed-summary`.
     Its series are `svg [data-camera-id][data-series]`, its count columns are under the header texts of 5.8,
     and its collapsed text is `<label>: Captured <x> fps, Displayed <y> fps`.
3. **The Displayed value of T-PRV-53 is the recent value** (`displayed.current`). It is not the mean of the window:
   after the two parts, the mean of the window is 40 fps, not 60 fps. A value over the last 1 s of drawn frames
   passes, and so does the last interval. The window (`displayed.aggregate`) shows that the gap of 2 s, the
   flagged message and the overlay update add no value.
4. **T-PRV-26 is split** into a blocking test and a `pace` test on one run, as
   [ADR-F4N7](F4N7-decisions-of-the-user-on-the-pace-tests-of-fix-lane-6.md) (Q670) splits the 4a ws tests. That
   decision came after the spec. The blocking test checks for more camera messages than the safety net gives.
5. **T-PRV-30 matches a whole word.** Else `FRAME_HEADER_SIZE` matches `CAMERA_FRAME_HEADER_SIZE` of the new
   parser (5.2), and the test can never pass.
6. **T-PRV-33**: the second give of a bad message writes no `console.error`. The seven bad messages write 4 to 7
   errors, because the spec does not say whether version 0 and version 2 are one reason.
7. **T-PRV-29** uses PROCESS workers. Camera B ends with `os._exit(3)` at the next frame after `FakeLog.arm()`
   (`on_arm="exit"`). The restart is an apply with `retry_camera_ids` of B. The relay runs on the loop of the test
   client, where the group starts. T-PRV-28 uses 1920 x 1080 rings, so that a payload of 607,032 bytes fits.
8. **Helpers that changed.** `FakeRing` takes `width` and `height`. `WsClient` keeps each text that is not JSON
   (`pong`) in `texts`.
9. **`ui_server.py`.** It reads one JSON command for each line of stdin, and writes each reply line with the prefix
   `@ui_server `. The first event names the port. It counts the ready messages through a subclass of
   `PreviewRelay` that uses only the 4a constructor and `handle_text`. The fake manager is also a
   `CameraGroupManager`, for the beartype check of `WebsocketServer`. The capture mode runs the group on the event
   loop of uvicorn, so that the rule of 4.3 holds.
10. **The component tests.** T-PRV-44 holds A in `starting` on its second open (a failed first open, then an apply
    with a retry), because a camera cannot join a running group. T-PRV-47 accepts `DISCONNECTED` or `FAILED`
    after the give-up. It allows only the connection errors in the console. T-PRV-48 checks D, B, C, A after the
    add. T-PRV-50 reads "3, 1 and 7" as Oversize 3, Ring skipped 1 and Replaced 7.
11. **Harness.** With `PLAYER_HARNESS_PRODUCT_THROTTLING=1`, the harness app has no switch against backgrounding,
    and `openWindow(name, {productThrottling: true})` opens a window with the default `backgroundThrottling`
    (T-PRV-49). `tsconfig.json` excludes `src/components/camera-views/tests`, as it excludes the other UI tests.
12. **Player tests of 7.6.** T-PLAY-37 gets a unit check of `frame: null` in `format.test.ts`. T-PLAY-44 gets a
    last step. `npm run test:player:unit` adds the two globs of 7.8. `playwright.player.config.ts` and
    `playwright.player-bench.config.ts` change as 7.8 says.

## Reason

The rule "a spec and a test list before code". The names fill gaps of the spec, so the code agent has one list.

## Consequences

- The product code of 4b must use the names of item 2, or this entry changes first.
- The component tests and the benchmarks did not run (real time). Their first run can show faults in the tests.

## Open work

See [open-work.md](../open-work.md).
