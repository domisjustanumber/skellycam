# CE8C — Count line of the BGR ring at the stop of the decode stage

**Status:** accepted, 2026-11-19 (user; commit to dom/native-jpeg).

## Decision

At `DecodeStage.stop()`, the decode stage writes one log line at the info level for its BGR ring.
The line gives the name of the ring, the frames committed, the frames skipped and the decode
errors. This adds to item 6 of
[ADR-5MYA](5MYA-python-api-of-the-bgr-ring-and-the-decode-stage-as-the-2b-tests-assume-it.md).
It does not change item 1 of
[ADR-467Z](467Z-step-2b-self-check-stop-opencv-threads-and-yuv-conversion.md): the line is not a
largest-frame log line.

## Reason

- The counters are in the ring header. The header goes away when the ring is unlinked. Without
  the line, the skips of a session cannot be seen after the session.
- An agent added the line for a four-camera run on 2026-11-19. The user decided to keep it.

## Alternatives rejected

- A line for each skipped frame: it can flood the log when the machine is busy.

## Open work

See [open-work.md](../open-work.md).
