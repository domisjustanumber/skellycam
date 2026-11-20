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

## Reason

Each correction makes the spec agree with itself, with the tests or with Chromium. Items 1 and 2
add optional members only, so the preview of phase 4 does not change.

## Evidence

Item 3: a scratch Electron 45.3.4 app (Chrome 156.0.8078.100) decoded the flat-block barcode JPEG of
the fixtures with the EXIF orientations 1 to 8. For orientation 6 the frame had `rotation` 90, coded
size 256 × 128 and display size 128 × 256, and `drawImage` turned it. The rule of item 3 gave
`rotation` 0 and `flip` false for each orientation (2026-11-20, Windows test machine).

## Open work

See [open-work.md](../open-work.md).
