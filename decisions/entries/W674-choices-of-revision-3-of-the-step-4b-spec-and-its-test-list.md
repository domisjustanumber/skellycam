# W674 — Choices of revision 3 of the step 4b spec, its full test list and four new questions

**Status:** proposed, 2026-11-20 (agent).

## Decision

Revision 3 of [`specs/preview-4b.md`](../../specs/preview-4b.md) puts the answers of
[ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md) into the
body, and gives the full test list (section 7.4): 27 tests, with the file, the set-up, the steps,
the pass criterion, the CI jobs and what each test must not do. An agent made these choices.
Section 11 of the spec states each one (items 20 to 30). They replace items 10, 11 and 17 of
section 11 of the spec: items of [ADR-EE0E](EE0E-step-4b-preview-spec-and-agent-choices.md), as
changes 6 and 9 of [ADR-R1TD](R1TD-revision-2-of-the-step-4b-preview-spec.md) changed them.

1. The camera list label comes from `index` and `name` of the camera list of the store, else from
   `camera_index` and `camera_name` of the config. `cameraListLabel` in `camera-labels.ts` makes it,
   with the separator `" · "`.
2. The grid order: ascending camera list number, then the camera id.
3. Displayed: `PreviewTiles` gets `onDrawn` and `now`. `FramerateStore.recordDrawn` keeps the time
   between drawn frames in the windowed statistics of today. A time longer than 1 s is not added.
4. The viewer: one colour for each camera, a solid Captured line, a dashed Displayed line, one
   histogram panel for each series.
5. The statistics table: two rows for each camera, the counts in the Captured row. The collapsed
   view gives both values.
6. The i18n keys `capturedFramerate` and `displayedFramerate`. The wire field stays
   `delivered_framerate`.
7. The targets for the split of Q9: B-1a at 30 fps only (a lag of at most 2 frames, and at least
   0.9 x min(30, C) distinct frames each second); B-1b, B-2 and B-3 at 30 and 60 fps. Two
   benchmarks: T-PRV-51 (30 fps) and T-PRV-52 (60 fps).
8. No test reads a tile canvas back. The tests check images with the outside observer only, and
   read the overlay from `Tile.overlay`. This replaces the line "Component tests may read tile
   pixels" of revision 2. The observer moves to `src/player/tests/harness/observer.ts`. T-PLAY-35
   allows a test file to import `src/player/tests/`. T-PLAY-37 and T-PLAY-44 change for
   `frame: null`.
9. The helpers: barcode camera numbers 1 to 8; 640 x 360 JPEGs for the component tests; new
   commands of `ui_server.py`; a camera list in the harness page.
10. The new unit test T-PRV-53 for Displayed. T-PRV-29 has only its first part, because Q4 is
    settled.
11. Section 2 states the base branch `dom/integration` as a note of the supervisor, with the sections
    that it changes.
12. The unit glob also runs `src/store/slices/cameras/**/*.test.ts`, so that the label test of the
    demo commits, changed for Q13, runs in CI.

The user answered the four new questions Q10 to Q13 on 2026-11-20
([ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)). The spec
asks one question (section 12.3): Q14, the take writes the list number of the apply request as
`os_index`. An agent read the code: the take value and the list number come from the same
detection in the normal case, and can differ after a new detection on the server, a detection by
another window, or a stale `camera_index` in a kept `desiredConfig` (section 12.2 of the spec).

## Reason

- Each choice is the smallest that makes the answers of the user testable. No option, setting or
  feature beyond the answers is added.
- Item 8: in the player benchmark, `getImageData` reads of the tile canvases slowed play from 57 to
  20 display refreshes each second and gave false results.
- Item 7: at about 30 captures each second, the observer cannot prove 60 frames each second.

## Open work

See [open-work.md](../open-work.md).
