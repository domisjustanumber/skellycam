# G651 — Phase 4 decisions: live preview (P1 to P7)

**Status:** accepted, 2026-11-19 (user; questions Q233 to Q239 of 2026-11-19).

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

- The user, 2026-11-19. Only these decisions are accepted. The spec of step 4a waits for the user.

## Consequences

- The spec of step 4a applies these decisions.
- P1 and P5 together need a rule for the time between 4a and 4b. Question Q1 of the spec asks the
  user.

## Open work

See [open-work.md](../open-work.md).
