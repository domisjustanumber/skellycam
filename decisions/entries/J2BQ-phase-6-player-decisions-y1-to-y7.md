# J2BQ — Phase 6 player decisions Y1 to Y7: steps, file access, tile, gaps, unfinished takes, module, tests

**Status:** accepted, 2026-11-19 (user; grilling session of 2026-11-19, Q217 to Q226; commit to dom/player).

## Decision

The user decided Y1 to Y7 for phase 6 (the player) on 2026-11-19. In short (section 18 of
`specs/player.md` gives each one in full):

1. **Steps** (Y1). Four steps, tests first: 6a the player for new takes, video only (the take reader
   for the manifest and the CSVs, the master clock, the canvas tiles, play, pause, step and scrub);
   6b audio (needs recorder step 5b); 6c the switch between the new player and the old video-element
   path, and old takes; 6d the "upgrade recording" converter. 6a closes the playback gap of recorder
   step 5a, so the two can land together.
2. **File access** (Y2). Option A now: a handler in the Electron main process serves the bytes,
   limited to the opened take folder, behind a small page interface, so that a server path can come
   later with no change of the player. Open work, not 6a: review option B (the Python server serves
   the files), with threads and process splits, for performance on par with the Electron handler.
3. **Tile** (Y3). One "JPEG to canvas" tile with `ImageDecoder`, for the player now and for the live
   preview of phase 4. One place for rotation and for the frame label.
4. **Gaps** (Y4). When the frame at time t is a gap row, the tile keeps the last real image and marks
   it clearly as "no frame". For a dead camera, the tile shows "camera lost at frame N" from that point
   to the end.
5. **Unfinished takes** (Y5). Until the repair step (recorder 5c) exists, the player opens such a take
   read only, plays the complete rows and frames, and shows an "unfinished" mark. No repair yet.
6. **Module** (Y6). A self-contained TypeScript module inside `skellycam-ui`, on branch `dom/player`
   (off `dom/native-jpeg`), with no dependency on the rest of the UI, so that the freemocap UI can take
   it later.
7. **Tests** (Y7). The tests build their own small takes in the new format, from the format spec,
   with synthetic JPEGs. The idea to convert the freemocap sample data is dropped. The tests run on
   Windows, Linux and macOS.

The decision list also cites earlier decisions (E1 to E9 in section 18.2 of the spec): the canvas
player with range reads at the CSV offset, `ImageDecoder` and one master clock; a `<video>` path for
old recordings; skellycam owns the JavaScript reader; SFF-783, SFF-706 and SFF-781 of
skellyfileformat; `display_rotation`; the label from the sidecar fields; the recorder decisions R2 and
R3.

## Reason

The user gave these answers in the grilling of 2026-11-19, so that the spec of step 6a can be written
before any code.

## Evidence

`research/skellycam_recording/recording_upgrade/results/range_transport/FINDINGS.md` on branch
`dom/research` (Electron 35.7.5 and 45.2.3): `protocol.handle` served 16 cameras × 60 fps × 150 kB
with 0 dropped ticks; the FastAPI route was 4 % short (bare) and 25 % short behind the logging
middleware; `file://` gives 200 with no `Content-Range`; concurrent ranges need
`Cache-Control: no-store`.

## Alternatives rejected

- Option B now (the Python server serves the files): slower in the measurement above. It stays open
  work.
- Fixtures converted from the freemocap sample data (Y7): dropped by the user.

## Open work

See [open-work.md](../open-work.md).
