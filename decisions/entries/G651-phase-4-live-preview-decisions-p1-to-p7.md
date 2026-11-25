# G651 — Phase 4 decisions: live preview (P1 to P7)

**Status:** absorbed into
[`specs/preview.md#15-decisions-and-answers-of-the-user`](../../specs/preview.md#15-decisions-and-answers-of-the-user),
[`specs/preview.md#84-targets-of-4a-each-one-to-measure-in-4a`](../../specs/preview.md#84-targets-of-4a-each-one-to-measure-in-4a),
[`specs/preview-4b.md#2-the-base-branch-q2-s`](../../specs/preview-4b.md#2-the-base-branch-q2-s),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-19 (user; questions Q233 to Q239 of 2026-11-19)).

## Decision

The user decided P1 to P7 for phase 4 (live preview) on 2026-11-19. These earlier statements of the
user stay binding: one websocket message for each camera frame; the JPEG untouched, no resize, no
re-encode; the preview does not depend on the group gate; the UI rotates when it draws; the tile
decodes with ImageDecoder and is shared with the player (Y3); the UI runs on the machine with the
cameras.

1. **P1, two steps.** 4a is the new websocket message and its sender in Python, tested against fake
   rings, with no dependency on phase 3. 4b is the UI side: the parser, the shared tile, the overlay.
2. **P2, flow control for each camera.** The UI says "camera X is ready" after it has drawn a frame.
   The server then sends the newest frame of camera X that it has not sent, and it skips all older
   frames. A slow tile does not hold back the others. No rate setting.
3. **P3, message header.** The camera id, the frame number of the camera, the arrival time, the
   rotation, the ring flags and the JPEG length. Width and height come from the JPEG. The server
   copies ring data and adds nothing.
4. **P4, tile and counts.** The tile shows the camera label, the delivered frame rate of the camera,
   its phase 3 state (starting, ready, too_slow, failed, dead, recording) and a mark for a flagged
   frame. The counts (skipped, replaced, oversize) go in the existing frame rate viewer, not on the
   tile.
5. **P5, deletion.** 4b deletes the old group message and its code. No period with both formats. An
   interface note for the FreeMoCap session is written at the end of 4b.
6. **P6, shared tile.** The player spec (`specs/player.md`, branch `dom/player`) specifies the shared
   tile one time, as its own module. 6a or 4b, whichever starts first, builds it.
7. **P7, parity.** The Python tests of 4a run on Windows, Linux and macOS in CI with fake rings. The
   UI tests of 4b run in the TypeScript test runner of the player, on the three systems.

## Reason

- The user, 2026-11-19. Only these decisions and the answers below are accepted. The spec of step 4a
  waits for the user.

## Answers of the user to the first draft of the step 4a spec (2026-11-19)

The user answered the four questions of the first draft, gave three more rules, and answered the
question of the revised draft (A8), on 2026-11-19:

1. **A1.** 4a adds the sender and its tests with no route. The endpoint keeps the old relay. 4b
   connects the sender, deletes the old code and changes the UI together. The branch goes to
   `development-streaming` only after 4b.
2. **A2.** Step 3a adds `replaced_count` to the status of each camera, counted from the first frame
   that the camera takes in the gate. The app state carries it. The sender does not compute it.
3. **A3.** The frame rate of the tile is the rate at which the camera delivers frames to skellycam,
   not the rate that reaches the screen. It must not depend on the client.
4. **A4.** The tile shows all eight states of the capture spec.
5. **A5.** The ring reader gets one new read-only property, `oversize_count`. No `head` property: the
   sender uses `reader.read(last_sent + 1)` and its `NOT_YET_WRITTEN` result. This adds to the
   reader API of [ADR-9G2W](9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md) by
   decision of the user.
6. **A6.** Safety net: when a camera has had no ready message for 1 s, the server sends its newest
   unsent frame anyway.
7. **A7.** The frame rate viewer shows two separate numbers with clear names: "not shown" (frames
   that the server did not send because the screen was slower than the camera) and the ring's own
   skipped count. Never one mixed number.
8. **A8** (answer to question Q1 of the spec). The ring reader gets a second read-only property,
   `skipped_count`, of the same kind as `oversize_count`, for display only. This adds to the reader
   API of ADR-9G2W by decision of the user.
9. **Tile thread.** The shared tile runs on the main thread of the page with ImageDecoder. 4b
   measures 8 cameras at 60 fps. A worker only if the target is missed.

## Answers of the user to the measurements of step 4a (2026-11-20)

The user answered on 2026-11-20, after the measurements of step 4a
([ADR-HDC9](HDC9-measurements-m-prv-1-to-m-prv-5-of-the-preview-sender.md)):

1. **A9.** Turn off websocket compression. The server starts uvicorn with
   `ws_per_message_deflate=False`. A JPEG does not compress, and permessage-deflate cost 12.7 to
   16.9 ms of the event loop for each 1080p frame.
2. **A10.** The target "event-loop time of the sender, 4 cameras at 1080p30, one client that keeps
   up" of section 8.4 of the spec becomes the number measured in step 4a with compression off. The
   user saw 12 %. That run used the legacy websockets implementation of uvicorn. With the
   implementation of the product (`ws="auto"`), six runs gave 13 to 19 %, median 16 %. The spec
   target is thus "at most 19 % of one core". This correction waits for the confirmation of the
   user.

## Consequences

- [`specs/preview.md`](../../specs/preview.md) applies these decisions and answers to step 4a. It is
  proposed ([ADR-162X](162X-step-4a-preview-spec-and-agent-choices.md)).
- A2 changes step 3a: the capture spec and the 3a tests must get `replaced_count`.
- A8 gives the ring `skipped_count` that A7 needs. No question of the spec is open.

## Open work

See [open-work.md](../open-work.md).
