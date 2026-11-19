# 467Z — Step 2b: BGR ring self-check, decode stage stop, one OpenCV thread and the YUY2 and NV12 conversion

**Status:** accepted, 2026-11-19 (user; commit to dom/native-jpeg).

## Decision

The user decided these four points of step 2b of
[`specs/frame-ring.md`](../../specs/frame-ring.md) on 2026-11-19. They apply to the API of
[ADR-5MYA](5MYA-python-api-of-the-bgr-ring-and-the-decode-stage-as-the-2b-tests-assume-it.md).

1. A BGR ring has no 50 % slot warning and no largest-frame log line (5.8). The payload size of a
   BGR ring is constant. The warning and the log line stay on the JPEG ring only.
2. `DecodeStage.stop()` drops a frame that waits in the waiting place. The dropped frame counts as
   skipped (8.3).
3. Each camera process calls `cv2.setNumThreads(1)` at its start (8.2), with or without a BGR ring.
4. Until phase 3, YUY2 and NV12 inputs use the default OpenCV conversion: `cv2.cvtColor` with
   `COLOR_YUV2BGR_YUY2` and `COLOR_YUV2BGR_NV12`. The range rule (8.7) waits for phase 3.

## Reason

- Item 1: each BGR frame fills its slot exactly (table 3.6). A warning at 50 % would come on each
  first frame, and a fraction of 1.00 tells nothing. Table 3.3 already gives
  `largest_payload_len` as the largest JPEG.
- Item 2: a frame that waits at stop has no reader that waits for it. A count of each frame that
  the BGR ring does not get keeps `frames_committed + skipped_count` equal to the frames that came.
- Item 3: one call for each camera process keeps one rule for each camera. OpenCV threads in each
  of many camera processes compete for the cores.
- Item 4: the range rule needs the input range of the camera, which phase 3 decides. The default
  conversion is enough for the tests of 2b.

## Open work

See [open-work.md](../open-work.md).
