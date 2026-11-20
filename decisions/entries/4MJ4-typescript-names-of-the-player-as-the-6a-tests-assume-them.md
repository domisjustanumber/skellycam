# 4MJ4 — TypeScript names of the player, as the 6a tests assume them

**Status:** superseded by [4D94](4D94-step-6a-choices-of-the-canvas-player.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent; waits for the user)).

## Decision

[ADR-YV3V](YV3V-acceptance-of-the-phase-6a-player-spec-and-test-list.md) accepts
[`specs/player.md`](../../specs/player.md). The spec does not fix each name that the failing tests of
step 6a use. An agent chose the names below. The tests are in `skellycam-ui/src/player/tests/` and
`skellycam-ui/src/components/playback/tests/`.

Test seams of the module:

1. `openTake(files, options?)`. `OpenTakeOptions` is `{initialFrame?, decode?, frameLoop?}`.
2. `JpegDecoder` is `(jpeg: Uint8Array) => Promise<DecodedImage>`. `DecodedImage` is
   `{displayWidth, displayHeight, close()}`, so a `VideoFrame` fits. The default decoder is
   `ImageDecoder`.
3. `FrameLoop` is `{now(): number; request(cb: (now: number) => void): number; cancel(id): void}`.
   The default is `performance.now` and `requestAnimationFrame`.
4. `new Tile(canvas, options?, seams?)`. `seams` is `{decode?: JpegDecoder}`. Under Node, the tile works
   with a canvas double: it uses `ResizeObserver` and `devicePixelRatio` only when they exist.
5. `tile.overlay` holds the text of the last overlay (8.4): `{frame, camera, time, rate, state, mark}`.
   Each value is a string, or null when the part does not show. `mark` is the text of 8.3.
6. `PlayerEvent` is `{type, state, error?}`. `error` is `{camera: number | null, message}`.
7. `index.ts` also exports the types `OpenTakeOptions`, `JpegDecoder`, `DecodedImage`, `FrameLoop`,
   `PlayerEvent`, `TileUpdate`, `TileMark`, `CameraState`, `PlayerState` and `TakePlayer`.

Pure functions:

8. `tile/format.ts`: `formatFrame(frame, frameDigits): string` and
   `formatTime(timeNs | null, format, nominalFps): string | null`.
9. `clock/choose.ts`: `frameTimes(times, frameCount)` gives T_k; `frameAt(frameTimes, t)` gives the
   largest k with T_k ≤ t; `chooseImage(times, missing, t, frameCount)` gives the image row or null
   (black); `chooseMark(missing, deadFrom, k)` gives a `TileMark` or null. `times` holds player times
   in nanoseconds, with null for a row with no time.

Main process and bridge:

10. The bridge is `window.skellycamTake` with `open(folderPath)` (it gives `{token, folderName, entries}`)
    and `close(token)`. A refused open rejects with a message that holds "folder not allowed".
11. `main/bridge.ts` exports `TAKE_CHANNELS`, the IPC channel names of the module.
12. `installTakeHandler(options)` gives `{recordPick(folder), setReadFault(relativePath | null)}`.
    `recordPick` is the call after a dialog pick. `setReadFault` is the test hook of 12.1.

Host view:

13. `CanvasTakePlayer` is a named export of `CanvasTakePlayer.tsx`, with the props
    `{folderPath, manualColumns, resetKey, initialFrame?, onFrameChange?}`. The grid has
    `data-testid="take-grid"`. Each tile canvas has `data-camera-label`. The loading text holds
    `<drawn> / <total>`. The empty state holds "no videos loaded".
14. The route of L1 is `chooseTakePlayer(folderPath)` in `take-route.ts`. It gives `'canvas'` or
    `'video'`.

Test set-up:

15. `src/player/tsconfig.json` adds `verbatimModuleSyntax` for the module only. The root
    `tsconfig.json` gets `allowImportingTsExtensions` and leaves out the two test folders. The flag
    `verbatimModuleSyntax` in the root file gives 73 errors in the code of today.
16. The harness Vite config and the Playwright configs are in `skellycam-ui/`, outside the module,
    because a module file must not import `vite`. The build goes to `dist-player-harness/`.
17. The boundary scan (T-PLAY-35) lets test code in a `tests/` folder outside the module import the
    `tests/` folder of the module.
18. The benchmarks use 60 Chromium JPEGs for each camera, in turn. Each writes its result as JSON to
    `PLAYER_BENCH_OUT`.

## Reason

The tests need fixed names before the code. Each name follows the style of the spec section that it
serves.

## Open work

See [open-work.md](../open-work.md).
