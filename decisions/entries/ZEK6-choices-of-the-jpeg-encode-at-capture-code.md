# ZEK6 — Choices of the code of the JPEG encode at capture (step 3b)

**Status:** absorbed into
[`specs/windows-capture.md#133-range-rule`](../../specs/windows-capture.md#133-range-rule),
[`specs/windows-capture.md#222-rules-of-step-3b`](../../specs/windows-capture.md#222-rules-of-step-3b),
[`specs/windows-capture.md#226-python-api-and-rules-of-the-port`](../../specs/windows-capture.md#226-python-api-and-rules-of-the-port),
[`specs/capture-timings.md#53-cost-budget-of-the-measurement-u-q587-9`](../../specs/capture-timings.md#53-cost-budget-of-the-measurement-u-q587-9),
[`specs/capture-timings.md#54-steps-that-apply`](../../specs/capture-timings.md#54-steps-that-apply),
[`specs/capture-timings.md#85-the-step-ids`](../../specs/capture-timings.md#85-the-step-ids),
[`skellycam/core/ipc/frame_ring/decode.py`](../../skellycam/core/ipc/frame_ring/decode.py),
[`skellycam/tests/capture/test_uncompressed.py`](../../skellycam/tests/capture/test_uncompressed.py),
2026-11-26 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-26 (user, Q886 and Q887,
[ADR-25VS](25VS-decisions-of-the-user-on-the-later-opens-and-the-size-floor.md))).

## Decision

Section 22 of [`specs/windows-capture.md`](../../specs/windows-capture.md) and its tests leave these
details open. An agent chose them when it wrote the code (Q815, Q855). The code is in
`skellycam/core/camera/capture/encoder.py`, `modes.py`, `camera_loop.py`, the Media Foundation source,
`camera_group_manager.py` and `skellycam/core/ipc/frame_ring/decode.py`. The user accepted items 1, 6, 9 and
12, and parts of items 4, 7 and 11, on 2026-11-26 (Q876 to Q881, [ADR-4TBY](4TBY-decisions-of-the-user-on-the-review-of-the-3b-code.md)), and the other items with
Q886 and Q887 ([ADR-25VS](25VS-decisions-of-the-user-on-the-later-opens-and-the-size-floor.md)), except the Quick Sync test frame
of item 2: it is 1280x720, not 320x240 (Q887).

1. **The raw mode of Q807.** Accepted (Q881).
2. **The Quick Sync check.** The manager runs the check in a worker thread, after the whole-request check
   of a request that it accepts, at the first such request in which a camera opens YUY2 or NV12 by the
   detection data; then it runs the whole-request check again. Thus the check of `request_runs` and its
   set have no wait between them (camera-requests.md 2.4a item 7; T-CAP-156). (The text that the user
   accepted with Q887 gave the earlier order: the check before the whole-request check.) A camera with
   no `capture_modes` (the OpenCV detection) never starts the check. With no source factory and
   `SKELLYCAM_WINDOWS_CAPTURE=opencv`, the check does not run. The test frame was NV12 at 320x240; Q887 made it 1280x720.
3. **The result in the camera processes.** Each status has a flag `quick_sync`. The manager writes it
   with the capture-timings switch, before the camera processes start and before an apply to a group
   that runs.
4. **The input range.** One time for each camera loop is accepted (Q881). It is decided at the end of the
   warm-up of the first raw open. The share is over all Y values of the warm-up frames together. The log line is
   "Camera `<id>`: input range `full` or `limited` (`<why>`)". The config field `input_range` (13.3)
   does not reopen the camera.
5. **The full-range conversion.** A full-range frame goes to limited range by a table (BT.601), then
   the default OpenCV conversion gives the full-range BGR. The JPEG of `cv2` and the BGR ring use the
   decided range, as ring 8.7 says (this closes 22.4: T-CAP-152 and T-CAP-153 pass with it). With `cv2`,
   the BGR ring gets the image that `cv2` encoded. With Quick Sync, the decode thread converts the raw
   frame (`DecodeInput.full_range`).
6. **Held frames.** Accepted (Q881).
7. **Reports.** That a Quick Sync encoder that does not open at the start is no fallback is accepted
   (Q881); it gives a WARNING and `cv2`. Each camera loop that had an encoder logs
   "Camera `<id>` stop: encoder fallbacks `<n>`" at its end. The `encoder_fallback` item goes at the end
   of the take. After one fallback, each later open of that camera loop uses `cv2`.
8. **The status `jpeg_encoder`.** `"cv2"` for each camera of the OpenCV source, also in MJPG.
9. **The take format.** Accepted (Q877).
10. **Media Foundation.** The range flag of the OS is `MF_MT_VIDEO_NOMINAL_RANGE` of the current type
    (1 full, 2 limited, else not set). A raw frame is a NumPy view of the copied bytes (no second copy).
11. **Capture timings.** That a raw camera reports `jpeg_encode` is accepted (Q880). Proposed: one sample for
    each call of `feed` (each taken frame), also when Quick Sync holds the frame. The bracket starts at the
    read that ends `camera_wait` and ends with a read of its own; `_process` reads the clock again after
    `should_record_frame_number`, which stays outside each bracket. The read budget of 5.3 counts the taken
    frames: at most 10 reads in a pass that gives a ring frame, 4 in a pass whose frame Quick Sync holds
    (T-TIM-23).
12. **A stalled encoder.** Accepted (Q878): a call gives no JPEG and more than 2 frames wait.
13. **The pairing test.** T-CAP-67 and T-CAP-158 check that each Quick Sync JPEG belongs to its own
    frame: a spy keeps the source frame number of each frame given to `feed`, and the ring frame of the
    JPEG with input number k has the k-th of them. T-CAP-157 checks that the ring frames are exactly the
    frames given to `feed`. A temporary shift of the pairing by one frame, and a temporary drop of the
    oldest held frame at a fallback, each made the test fail.
14. **The range tables.** `map_levels` uses `cv2.LUT` (a two-channel table for YUY2, one call per plane
    for NV12). At 1080p it took 2.38 ms (YUY2) and 1.33 ms (NV12), against 8.54 and 5.71 ms with NumPy
    indexing, with the same bytes (median of 200 runs, synthetic frames, one OpenCV thread, OpenCV of
    the lock file, development machine only).
15. **T-CAP-26.** Resolved (Q876).
16. **Short frames behind a held frame.** A frame of the wrong length is not encoded, but it waits in the
    queue behind a frame that Quick Sync holds. Thus the limit of Q878 counts the whole queue: when a
    call gives no JPEG, the oldest frame waits for its JPEG and the queue holds more than 2 frames, the
    camera falls back. Else frames of the wrong length could pile up for ever behind one held frame.

## Reason

- Items 1 to 3: the smallest rule that meets 13.2 and 22.2 and passes T-CAP-61 to T-CAP-155.
- Item 5: one table and the existing OpenCV conversion. A mean difference of 3 levels is the limit.
- Item 6: a flush would end the Quick Sync stream, and a frame with no number is not lost from a take.
- Items 7 to 11: no rule of the spec covers them; each is a small choice that a test or a reader can
  check.

## Alternatives rejected

- A UI flag for the raw-mode open: the user said no (Q846).
- `flush` after each frame: Quick Sync then blocks about 17 ms per call (design notes, Encoder
  settings).

## Open work

See [open-work.md](../open-work.md).
