# 1ACK — Corrections and choices of the 6a player code

**Status:** proposed, 2026-11-20 (agent; waits for the user).

## Decision

[ADR-YV3V](YV3V-acceptance-of-the-phase-6a-player-spec-and-test-list.md) accepts
[`specs/player.md`](../../specs/player.md). The code of step 6a showed gaps in the spec. An agent made
the corrections and the choices below. U3 is a decision of the user, so it is in
[ADR-4HNY](4HNY-missing-frames-m1-to-m10-and-player-decisions-l1-to-l8.md), not here.

Spec corrections (2026-11-20):

1. Back to black (section 8.3): `TileUpdate` gets the optional member `blank`. With `blank` true, the
   tile closes its image and draws black with the new overlay. Before, the tile had no way to go back
   to black after an image, and a seek to a frame before the first real row of a camera needs it.
2. The prefetch queue holds decoded images (sections 8.3 and 9.1). The player decodes them and gives
   each one to the tile in the optional member `image` of `TileUpdate`, with its JPEG bytes in `jpeg`.
   The tile then draws it at once with no decode, and it owns the image. Before, section 9.1 spoke of
   decoded images and `Tile.update` took only JPEG bytes. With `jpeg` only, the tile decodes, as for
   the preview.
3. EXIF orientation (section 8.1): Chromium applies the tag. `ImageDecoder` of Electron 45.3.4 gives a
   `VideoFrame` with `rotation` and `flip`, and has no option to ignore the tag. The decoder undoes it
   with `new VideoFrame(frame, {rotation: r, flip})`, r = `rotation` when `flip` is true, else
   (360 − `rotation`) mod 360.
4. A `camera_dead` detail that does not parse (section 7.3): the rule of the run of `missing` rows
   for that camera, and the take warning `camera_dead` with no frame number (F-5 of the recorder
   spec).
5. Manifest warnings (section 6.2): the code of each warning of the manifest goes into
   `take.warnings`.
6. The root `.gitignore` ignores each `index.ts` and `tsconfig.json` (section 4.1): add the files of
   the module with `git add -f`.

Choices of the code that the spec, ADR-4K7V and ADR-4MJ4 do not fix:

7. The reader finds the device pairs by the scan of section 6.4 in each case. With a manifest that
   it uses, it keeps only the pairs whose sidecar path is in `cameras[].timing`.
8. A pair whose `take_uuid` does not have the form of SFF-703 joins the first take as a refused
   camera, so that its tile shows "camera file not readable: bad_metadata" (T-PLAY-08). SFF-889
   puts such a file in `other_files`, which the player does not have. This needs the decision of the
   user.
9. A complete data row with a wrong number of fields is handled as a row with a wrong CRC: the file
   is `damaged` with `crc_mismatch`.
10. A finished or repaired file with a row whose block ends after the snapshot size is `invalid` with
    `bad_metadata` (SFF-759).
11. The handler answers 500 for a read that fails for another reason than a changed or deleted file.
    Table 5.6 has no row for it. The read fault hook of the tests uses the same answer.
12. A second open of the same folder from the same window keeps the earlier token of that window
    (T-PLAY-58). An open of another folder closes them (T-PLAY-63). `close(token)` closes only a
    token of the window that asks. A token also closes when the renderer process of its window ends.
13. The list of picked folders holds real paths, in `picked-take-folders.json` in the user data
    folder.
14. The prefetch looks ahead with a display rate of 60 Hz. It closes the queued images that are older
    than the image that applies at t, except the newest one during play.
15. During play, the first `state` and `frame` events come 200 ms after `play()`. A pause sends a
    `frame` event only when k* changed since the last `frame` event.
16. The loading message of the host view is `<drawn> / <total>`, with the translated text as its
    title. It goes away when each camera has drawn its first image, as today (F18).
17. The host view mounts the grid after it measured its size, so the tiles do not move from a default
    size.
18. `TileTexts` is a record by mark kind and camera state name, plus `time_title`. `{reason}` and
    `{frame}` are replaced. The overlay uses a 12 CSS pixel monospace font on dark boxes.
19. The module has no `react/` folder: section 4.1 names none, and section 4.2 forbids React in the
    module.
20. The recording browser routes before its backend video call, and the playback page shows the
    canvas player for a take folder. It does not show the `needs_new_player` mark yet: the backend of
    recorder step 5a is not on this branch.

## Reason

Each correction makes the spec agree with itself, with the tests or with Chromium. Items 1 and 2
add optional members only, so the preview of phase 4 does not change. Each choice is the smallest
rule that the tests and the spec allow.

## Evidence

Item 3: a scratch Electron 45.3.4 app (Chrome 156.0.8078.100) decoded the flat-block barcode JPEG of
the fixtures with the EXIF orientations 1 to 8. For orientation 6 the frame had `rotation` 90, coded
size 256 × 128 and display size 128 × 256, and `drawImage` turned it. The rule of item 3 gave
`rotation` 0 and `flip` false for each orientation (2026-11-20, Windows test machine).

Electron 45.3.4, harness of the 6a tests (2026-11-20): a `protocol.handle` handler that the main
process installs after a page loaded does not serve that page; the page keeps the handler of its
load. After a reload, the page client refused the 200 answer with the whole file and the 206 answer
with a wrong start, and it accepted the 200 answer with the exact length. In the hidden harness
window under Playwright 1.65.1, `requestAnimationFrame` ran about 4 times per second; in the shown
window (`PLAYER_HARNESS_SHOW=1`), about 62 times per second.

## Open work

See [open-work.md](../open-work.md).
