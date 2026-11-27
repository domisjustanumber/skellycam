# W3VD — Choices of the tile timings lane: step 8 of `specs/capture-timings.md`

**Status:** proposed, 2026-11-27 (agent, tile timings lane of Q870 of
[ADR-BPP8](BPP8-answers-of-the-user-q864-to-q873-on-the-step-4b-code.md); waits for the user).

## Decision

What is built: step 8 of section 11 of [`capture-timings.md`](../../specs/capture-timings.md): the module
`skellycam-ui/src/player/tile/timings.ts`, the `timing` handle of the tile, `receivedAtMs` of `TileUpdate` and its
stamp in `PreviewTiles`, and the tests T-TIM-24 (the TypeScript part) to T-TIM-26. The spec did not decide these
items. Section 7 of the spec states them, with a link to this entry.

1. **The summary function.** Its name is `buildSummary`. It takes the same named fields as the Python
   `build_summary`, with the same snake_case names, so that it reads the `input` of the shared fixture
   `skellycam/tests/capture_timings/summary_fixture.json` as it is. The durations are integer nanoseconds. The
   handle changes its milliseconds to nanoseconds with `Math.round(ms * 1_000_000)` before the call.
2. **A copy of the step table.** `timings.ts` holds a copy of `STEPS` and `DELAYS` of
   `skellycam/core/capture_timings.py`, because the fixture has steps that the tile does not measure. The
   TypeScript part of T-TIM-24 also compares the copy with the two Python tables, which it reads from the Python
   file. Thus the copy cannot drift.
3. **One handle for each camera id.** A second `handle()` call with the same camera id gives the same handle and
   sets its group id. Thus a tile that mounts again adds no second summary. No call removes a handle: the handle
   of a camera that leaves keeps a summary with `n` 0 in each `takeSummaries()`.
4. **The window of a handle.** It starts at the creation of the handle: `handle()` reads `now()` one time.
   `takeSummaries()` reads `now()` one time for all handles. It gives a summary for each handle also when `on` is
   false (T-TIM-25). `seq` is for each handle and starts at 0.
5. **A decode that is not drawn.** A decode whose update a newer update supersedes, and a JPEG that does not
   decode, give a `ui_jpeg_decode` sample: the bracket is the call to its result (table 3.1). They give no
   `ui_draw` and no `receive_to_draw` sample. An update that a newer update replaces before its decode starts
   gives no sample.
6. **The switch in a bracket.** A bracket reads `on` at its start. A bracket that starts with `on` true stores its
   sample, also when `on` becomes false before its end.
7. **`ui_draw` of an `image` update.** An update with `image` (the player) sets a new decoded image, so it gives a
   `ui_draw` sample and no `ui_jpeg_decode` sample. A `blank` update gives no `ui_draw` sample.
8. **The interface between the tile and its handle.** `TileTimingHandle` has `on` (the `on` of its
   `TileTimings`), `now()` and `add(id, ms)`. The handle keeps one `Float64Array` of 512 values and one total for
   each of `ui_jpeg_decode`, `ui_draw` and `receive_to_draw`.
9. **The host in skellycam-ui.** `ServerContextProvider` makes one `TileTimings`. `useServer()` gives it with
   `getTileTimings()`, as `getPreviewTiles()`. `CameraView` makes its tile with
   `{timing: getTileTimings().handle(cameraId, null)}`. The group id is `null`, because skellycam-ui reads no
   summary (8.4 permits `null`). The guard `isCaptureTimings` of `server-messages.ts` finds the message, and the
   provider sets `on` to its `log_capture_times`. A disconnect does not change `on`; the next message sets it.
10. **The stamp.** `PreviewTiles.receive` stamps each camera message with the `now` of `PreviewTiles` (the clock of
    `onDrawn`), also when the timings are off: `PreviewTiles` does not know the switch. That is one
    `performance.now()` call for each message.
11. **Test parts in addition to 10.2.** T-TIM-26 gets a Node part in `preview-tiles.test.ts`: the stamp, its pass to
    the update, and a replaced message whose stamp never reaches the tile. It gets one more in `timings.test.ts`: the
    window of a handle, the newest 512 samples, `seq` and one handle for each camera id. T-TIM-25 gets a Node part in
    `server-messages.test.ts`: the guard of item 9.

## Reason

Each item is the smallest choice that agrees with sections 5.2, 6.1, 7 and 10 of the spec and with the 4b code.
Items 1 and 2 make one fixture prove one JSON shape for each id (Q569, Q840). Item 3 keeps one summary for each
camera when React mounts a tile again. Items 5 and 7 follow the words of the brackets in table 3.1. Item 9 follows
the `getPreviewTiles()` pattern of [`preview-4b.md`](../../specs/preview-4b.md) 5.5 and 5.6. No item changes the
websocket message, a Python API or a file format.

## Alternatives rejected

- A summary function that takes milliseconds: the fixture holds nanoseconds, and a second change of units in the
  test would hide a rounding fault.
- Only the two `ui_*` steps in the TypeScript table: the fixture would fail, and a host could not build a summary
  of another id.
- A new handle for each call: a remount would give two summaries for one camera.
- The group id from `app_state` in `CameraView`: more code for a field that nothing in skellycam-ui reads.

## Open work

See [open-work.md](../open-work.md).
