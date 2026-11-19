# 162X — Step 4a spec: the per-camera preview message and its sender, with the agent choices

**Status:** proposed, 2026-11-19 (agent).

## Decision

[`specs/preview.md`](../../specs/preview.md) is the spec of step 4a of phase 4, with its test list
T-PRV-01 to T-PRV-24. It follows P1 to P7 and the answers A1 to A7 of
[ADR-G651](G651-phase-4-live-preview-decisions-p1-to-p7.md), the ring spec and the capture spec. The
second revision of 2026-11-19 applies A1 to A7 and the faults of an independent review.

An agent made these choices where the sources leave a gap. Section 13 of the spec states each one
in full, and the body marks each one [agent n]:

1. Module `skellycam/api/websocket/preview_relay.py` (`PreviewRelay`, `pack_camera_frame`); tests in
   `skellycam/tests/preview/`.
2. Byte 0 is `version` = 1, also the message type.
3. A 48-byte header, little-endian, each field aligned: flags, frame number, arrival time, rotation,
   JPEG length, camera id; then the JPEG.
4. Camera id in 16 ASCII bytes; an id that does not fit gets no message and one ERROR record.
5. The frame number of P3 is the ring `frame_number`.
6. All 32 flag bits are copied.
7. The probe starts after the last frame read with any result (`last_tried`).
8. A flagged or oversize frame goes out as a header-only message with JPEG length 0.
9. Ready message `{"message_type": "camera_ready", "camera_id": ...}`.
10. Each camera starts ready on a new connection.
11. The safety net counts 1 s from the last send, on `time.monotonic()`.
12. The fields that a new ring resets and keeps.
13. A pass 10 ms after the previous pass, and at once after a ready message.
14. Reads on the event-loop thread through `CameraGroup.ring_readers`; loops over copies of the
    dicts; each reader looked up again after each `await`.
15. `read(last_tried + 2)` tells with no copy if the probe frame is the newest.
16. The state of a camera changes before the `await` of its send.
17. Each connection has its own sender, state and reads.
18. A failed read sends nothing and logs nothing.
19. A new shape of `framerate_update`; the frame rate also fed by one tick read for each camera; the
    move of `ServerFramerateCalculator` to `framerate_tracker.py`; `clear()` keeps the last
    observation; a bounded duration loop.
20. "Not shown" is the gap of `frame_number` minus the increase of the ring `skipped_count`.
21. Bad ready messages: one WARNING; an unknown camera is ignored.
22. The test route cancels `run` when the client disconnects.
23. Loose pass thresholds for slow CI runners.
24. The 4a tests join the three jobs of `capture.yml`, in a CI PR of its own.
25. One `bytes` object per message.
26. No reads while the manager closes.
27. Sends of one connection in series.

One question waits for the user (section 14 of the spec): Q1, the read-only reader property
`skipped_count`, which A7 needs and A5 does not name.

## Reason

- P1 and the rule "a spec and a test list before code": the user reviews the spec first.
- Each choice is the smallest that makes the spec complete. No option, setting or feature beyond the
  decisions and the answers is added.

## Open work

See [open-work.md](../open-work.md).
