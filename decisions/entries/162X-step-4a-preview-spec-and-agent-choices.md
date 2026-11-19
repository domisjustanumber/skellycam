# 162X — Step 4a spec: the per-camera preview message and its sender, with the agent choices

**Status:** proposed, 2026-11-19 (agent).

## Decision

[`specs/preview.md`](../../specs/preview.md) is the spec of step 4a of phase 4, with its test list
T-PRV-01 to T-PRV-25. It follows P1 to P7 of
[ADR-G651](G651-phase-4-live-preview-decisions-p1-to-p7.md), the ring spec and the capture spec.

An agent made these choices where the sources leave a gap. Section 12 of the spec states each one
in full, and the body marks each one [agent n]:

1. Module `skellycam/api/websocket/preview_relay.py` (`PreviewRelay`, `pack_camera_frame`); tests in
   `skellycam/tests/preview/`.
2. Byte 0 is `version` = 1, also the message type.
3. A 48-byte header, little-endian, each field aligned: flags, frame number, arrival time, rotation,
   JPEG length, camera id; then the JPEG.
4. Camera id in 16 ASCII bytes; an id that does not fit gets no message and one ERROR record.
5. The frame number of P3 is the ring `frame_number`.
6. All 32 flag bits are copied.
7. Rotation as a u32.
8. A flagged or oversize frame goes out as a header-only message with JPEG length 0.
9. Ready message `{"message_type": "camera_ready", "camera_id": ...}`.
10. Each camera starts ready on a new connection.
11. No time limit for a client that never answers.
12. A new ring resets the last sent frame and keeps the ready state.
13. A pass at most every 10 ms, and at once after a ready message.
14. Reads on the event-loop thread of the main process, through `CameraGroup.ring_readers`.
15. Two read-only properties of `FrameRingReader`: `head` and `oversize_count`. This adds to the
    reader API of [ADR-9G2W](9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md).
16. A failed read sends nothing and logs nothing.
17. Each connection has its own sender, state and reads.
18. "Skipped" is the count of frames not sent; the UI counts it from frame-number gaps.
19. Delivered rate from `source_frame_number` and `arrival_ns`, every 0.25 s.
20. A new shape of `framerate_update`: per camera rate and oversize count.
21. Bad ready messages: one WARNING; an unknown camera is ignored.
22. 4a does not change the live endpoint; the tests use a test route.
23. The 4a tests join the three jobs of `capture.yml`, in a CI PR of its own.
24. The pass thresholds of the test list.
25. One `bytes` object per message.
26. No reads while the manager closes.
27. Sends of one connection in series.

Four questions wait for the user (section 13 of the spec): Q1 the time between 4a and 4b, Q2 the
replaced count in the camera status, Q3 the meaning of "delivered frame rate", Q4 the eight states.

## Reason

- P1 and the rule "a spec and a test list before code": the user reviews the spec first.
- Each choice is the smallest that makes the spec complete. No option, setting or feature beyond P1
  to P7 is added.

## Open work

See [open-work.md](../open-work.md).
