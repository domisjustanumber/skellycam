# EE0E — Step 4b spec: the UI side of the preview, the connection of the sender, the deletion, with the agent choices

**Status:** superseded by [RA16](RA16-step-4b-choices-of-the-preview-ui.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent)).

## Decision

[`specs/preview-4b.md`](../../specs/preview-4b.md) is the proposed spec of step 4b of phase 4, with
its test list T-PRV-25 to T-PRV-51 (7 Python, 11 unit, 8 component, 1 benchmark). It follows
[ADR-G651](G651-phase-4-live-preview-decisions-p1-to-p7.md), the accepted step 4a spec
[`specs/preview.md`](../../specs/preview.md)
([ADR-WB08](WB08-acceptance-of-the-step-4a-preview-spec-and-its-test-list.md)), section 8 of
`specs/player.md` on branch `dom/player`, and section 8 of `specs/windows-capture.md` on branch
`dom/native-jpeg`. It does not change the 4a spec.

An agent made these choices where the sources leave a gap. Section 11 of the spec states each one
in full:

1. A task `_preview_relay` wraps `PreviewRelay.run` with the `except` clauses of the other tasks of
   `WebsocketServer`.
2. `CameraGroup._ring_lock` of phase 3a becomes the public `ring_lock`.
3. New UI files in `skellycam-ui/src/services/server/preview/`: `camera-message.ts` and
   `preview-tiles.ts`.
4. The parser throws with a reason; one `console.error` for each reason and connection; no ready
   message for a refused message.
5. `PreviewTiles`: one tile update in flight for each camera; `requestAnimationFrame` drives the
   draws; an overlay update sends no ready message.
6. The tile label: `frameDigits` 6, no time part.
7. The rate text: one decimal and " fps".
8. `connectedCameraIds` comes from `app_state`, so that a camera with no frame has a tile.
9. The measurement: the real server with fake rings, barcode JPEGs of about 190 kB, observers
   outside the page, 3 runs of 60 s.
10. The targets B-1 to B-4.
11. A tool writes one shared fixture of camera messages; `ui_server.py` serves the UI tests.
12. The UI tests join the runners of the player; a CI change in its own PR.
13. The `FRAMERATE` subscription of `CameraGroupManager` stays.
14. `measured_fps` is not shown.
15. The interface note is `specs/preview-interface-note.md`.
16. The UI component tests use the real Python server.
17. One row for each camera in the statistics table.
18. New i18n keys in English only; the docs copies get English prose.

The spec asks six questions (section 12): `frame: null` in the shared tile (Q1); the merge of
`dom/native-jpeg` and `dom/player` into `dom/preview` (Q2); one chart series for each camera (Q3);
the ring lock in the sender (Q4); the label `<camera_name> · <camera id>` (Q5); the targets and the
worker rule (Q6).

The user answered the questions and accepted the spec in principle on 2026-11-20
([ADR-VYS7](VYS7-answers-of-the-user-to-the-step-4b-spec-and-go-ahead-for-its-tests.md)).
[ADR-W674](W674-choices-of-revision-3-of-the-step-4b-spec-and-its-test-list.md) replaces items 10,
11 and 17.

## Reason

- The rule "a spec and a test list before code": the user reviews the spec before the tests.
- Each choice is the smallest that makes the spec complete. No option, setting or feature beyond
  the decisions is added.
- Item 2 and Q4: the watch thread of phase 3a closes rings on another thread, so the rule of
  section 5.1 of the 4a spec does not hold after the merge.
- Item 8: the tile must show `starting` and `failed` (A4), and such a camera sends no frame.

## Open work

See [open-work.md](../open-work.md).
