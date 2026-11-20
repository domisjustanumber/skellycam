# 4D94 — Step 6a choices of the canvas player: spec items, test names, code and review fixes

**Status:** accepted, 2026-11-20 (user: one ruling on review sheet 4 of 2026-11-20; the other items
accepted through the review sheets of 2026-11-20; commit to dom/integration).

## Decision

This entry supersedes [ADR-4K7V](4K7V-phase-6a-player-spec-and-test-list.md),
[ADR-4MJ4](4MJ4-typescript-names-of-the-player-as-the-6a-tests-assume-them.md),
[ADR-1ACK](1ACK-corrections-and-choices-of-the-6a-player-code.md) and
[ADR-5FBS](5FBS-fixes-of-the-6a-code-review.md). Each of their items is below. P is
[`player.md`](../../specs/player.md); "item n" is in P
[16](../../specs/player.md#16-choices-of-the-agent).

Ruled by the user:

- 1ACK 13 and the list file of 4K7V 6: in 6a the player keeps the picked folders only for the app
  run. It writes no `picked-take-folders.json`. The list file waits for step 6c. This overturns the
  list file of item 6 and of P
  [5.3](../../specs/player.md#53-which-folders-open-l7-agent-6) ([open-work.md](../open-work.md)).

Accepted through the review sheets, by link:

- 4K7V 1 to 5, 7 to 25, 27 to 39: items 1 to 5, 7 to 25, 27 to 39. 4K7V 6 (the rest): item 6.
- 4K7V 26: item 26, except the label text (overturned below).
- 1ACK 1, 2: P [8.3](../../specs/player.md#83-the-tile-interface-l6-agent-25-agent-26). 1ACK 3: P
  [8.1](../../specs/player.md#81-decode-and-thread-l6). 1ACK 4: P
  [7.3](../../specs/player.md#73-the-frame-choice-sff-783-e4-m9-agent-20-agent-21). 1ACK 5: P
  [6.2](../../specs/player.md#62-the-manifest).
- 5FBS 1, 3: P [5.4](../../specs/player.md#54-open-tokens-and-close-agent-5-agent-7-agent-12).
  5FBS 2: P 5.3. 5FBS 4: P [5.6](../../specs/player.md#56-responses-m-rt-6-agent-9). 5FBS 7: P
  [6.10](../../specs/player.md#610-reading-a-frame-trust-the-csv-check-the-block-header-sff-739-sff-757-agent-17).
  5FBS 8, 9: P [10](../../specs/player.md#10-host-integration-in-skellycam-ui-l1-l4-l5-agent-31).
  5FBS 10: P [6.4](../../specs/player.md#64-device-pairs-takes-and-counts).

Accepted through the review sheets, as text:

- 4MJ4 1 to 3: `openTake(files, options?)`, `OpenTakeOptions` `{initialFrame?, decode?, frameLoop?}`;
  `JpegDecoder` `(jpeg: Uint8Array) => Promise<DecodedImage>`, `DecodedImage`
  `{displayWidth, displayHeight, close()}`, default `ImageDecoder`; `FrameLoop`
  `{now(), request(cb), cancel(id)}`, default `performance.now` and `requestAnimationFrame`.
- 4MJ4 4 to 7: `new Tile(canvas, options?, seams?)`, `seams` `{decode?}`, `ResizeObserver` and
  `devicePixelRatio` only when they exist; `tile.overlay` `{frame, camera, time, rate, state, mark}`
  (string or null); `PlayerEvent` `{type, state, error?}`, `error` `{camera: number | null,
  message}`; `index.ts` also exports `OpenTakeOptions`, `JpegDecoder`, `DecodedImage`, `FrameLoop`,
  `PlayerEvent`, `TileUpdate`, `TileMark`, `CameraState`, `PlayerState`, `TakePlayer`.
- 4MJ4 8, 9: `tile/format.ts` `formatFrame(frame, frameDigits)`,
  `formatTime(timeNs | null, format, nominalFps)`; `clock/choose.ts` `frameTimes(times, frameCount)`,
  `frameAt(frameTimes, t)`, `chooseImage(times, missing, t, frameCount)`,
  `chooseMark(missing, deadFrom, k)`; times in ns, null for no time.
- 4MJ4 10 to 12: `window.skellycamTake` `open(folderPath)` gives `{token, folderName, entries}`, a
  refusal holds "folder not allowed", `close(token)`; `main/bridge.ts` exports `TAKE_CHANNELS`;
  `installTakeHandler(options)` gives `{recordPick(folder), setReadFault(relativePath | null)}`.
- 4MJ4 13, 14: `CanvasTakePlayer` (named export) props `{folderPath, manualColumns, resetKey,
  initialFrame?, onFrameChange?}`, `data-testid="take-grid"`, `data-camera-label` on each canvas,
  loading text `<drawn> / <total>`, empty state "no videos loaded"; `chooseTakePlayer(folderPath)` in
  `take-route.ts` gives `'canvas'` or `'video'`.
- 4MJ4 15 to 18: `verbatimModuleSyntax` only in `src/player/tsconfig.json`; the root `tsconfig.json`
  has `allowImportingTsExtensions` and leaves out the two test folders; harness and Playwright
  configs in `skellycam-ui/`, build to `dist-player-harness/`; a `tests/` folder outside the module
  can import the module `tests/`; 60 Chromium JPEGs per camera, results to `PLAYER_BENCH_OUT`.
- 1ACK 7: pairs by the scan of P 6.4; with a manifest, only the pairs in `cameras[].timing`. 1ACK 9:
  a row with a wrong field count is `damaged`, `crc_mismatch`. 1ACK 10: a finished or repaired file
  with a block past the snapshot size is `invalid`, `bad_metadata`. 1ACK 11: other read failures get
  500. 1ACK 12: a second open of a folder from one window keeps its token; another folder closes it;
  `close(token)` only for the asking window; a token closes with its renderer process.
- 1ACK 14 to 19: a 60 Hz look-ahead, older queued images closed; the first events 200 ms after
  `play()`, a pause sends `frame` only when k* changed; the loading message `<drawn> / <total>`; the
  grid mounts after it measured its size; `TileTexts` by mark kind and state, plus `time_title`,
  overlay 12 CSS px monospace on dark boxes; no `react/` folder.
- 1ACK 6, changed by the sheet: a `.gitignore` exception for `skellycam-ui/src/player/` in place of
  `git add -f`.
- 5FBS 5: a failed `openTake` closes its files. 5FBS 6: `setReadFault` stays in the handler
  interface (main process only). 5FBS 11: the Linux job takes `xvfb` from the `ubuntu-24.04` image,
  prints and checks its version; the test steps run only when `npm ci` passed. 5FBS 12: the sidecar
  reader decodes no unused string; the decoder closes the first frame when `VideoFrame` fails.

Overturned: the label text of 4K7V 26 by Q11 of
[ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)
(`Camera <os_index> · <os_name>`).

Dropped as stale: 1ACK 8 (5FBS 10 replaces it); 1ACK 20 (the 5a backend is on this branch now;
the `needs_new_player` mark is work of the merge).

## Reason

The rulings of the user. The old entries hold the reasons.

## Open work

See [open-work.md](../open-work.md).
