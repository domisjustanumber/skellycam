# ZEK6 — Choices of the code of the JPEG encode at capture (step 3b)

**Status:** proposed, 2026-11-26 (agent).

## Decision

Section 22 of [`specs/windows-capture.md`](../../specs/windows-capture.md) and its tests leave these
details open. An agent chose them when it wrote the code (Q815, Q855). The code is in
`skellycam/core/camera/capture/encoder.py`, `modes.py`, `camera_loop.py`, the Media Foundation source,
`camera_group_manager.py` and `skellycam/core/ipc/frame_ring/decode.py`.

1. **The raw mode of Q807.** An MJPG request opens a raw mode only when the size has no MJPG mode at the
   floor and has a YUY2 or NV12 mode at the floor. Else the request keeps the MJPG rules of 7.5 and
   their failure. The order is `RAW_ORDER` in `modes.py`.
2. **The Quick Sync check.** The manager runs the check in a worker thread, after the detection and
   before the whole-request check, at the first request in which a camera opens YUY2 or NV12 by the
   detection data. Thus the check of `request_runs` and its set have no wait between them
   (camera-requests.md 2.4a item 7; T-CAP-156). A camera with
   no `capture_modes` (the OpenCV detection) never starts the check. With no source factory and
   `SKELLYCAM_WINDOWS_CAPTURE=opencv`, the check does not run. The test frame is NV12 at 320x240.
3. **The result in the camera processes.** Each status has a flag `quick_sync`. The manager writes it
   with the capture-timings switch, before the camera processes start and before an apply to a group
   that runs.
4. **The input range.** It is decided one time for each camera loop, at the end of the warm-up of the
   first raw open. The share is over all Y values of the warm-up frames together. The log line is
   "Camera `<id>`: input range `full` or `limited` (`<why>`)". The config field `input_range` (13.3)
   does not reopen the camera.
5. **The full-range conversion.** A full-range frame goes to limited range by a table (BT.601), then
   the default OpenCV conversion gives the full-range BGR. The JPEG of `cv2` and the BGR ring use the
   decided range, as ring 8.7 says (this closes 22.4: T-CAP-152 and T-CAP-153 pass with it). With `cv2`,
   the BGR ring gets the image that `cv2` encoded. With Quick Sync, the decode thread converts the raw
   frame (`DecodeInput.full_range`).
6. **Held frames.** A frame that Quick Sync holds at a close or a reopen is dropped: the loop gave it no
   frame number yet. The loop never calls `flush`.
7. **Reports.** A Quick Sync encoder that does not open at the start of a camera gives a WARNING and
   `cv2`; it is not a fallback of a take. Each camera loop that had an encoder logs
   "Camera `<id>` stop: encoder fallbacks `<n>`" at its end. The `encoder_fallback` item goes at the end
   of the take. After one fallback, each later open of that camera loop uses `cv2`.
8. **The status `jpeg_encoder`.** `"cv2"` for each camera of the OpenCV source, also in MJPG.
9. **The take format.** The opened format of the status mode, in the names of SFF-800: `YUY2` is
   `YUYV`; `NV12` is `NV12` (skellyspecs main has it, Q849).
10. **Media Foundation.** The range flag of the OS is `MF_MT_VIDEO_NOMINAL_RANGE` of the current type
    (1 full, 2 limited, else not set). A raw frame is a NumPy view of the copied bytes (no second copy).
11. **Capture timings.** The encode of a raw frame is the step `jpeg_encode`, one sample for each call
    of `feed` (each taken frame). A raw camera lists it in its step IDs. The bracket starts at the read
    that ends `camera_wait`, and its end is the first read of the next frame. The read budget of 5.3
    counts the taken frames; a pass whose frame Quick Sync holds reads the clock 4 times (T-TIM-23).
12. **A stalled encoder.** When more than `ASYNC_DEPTH` (2) frames wait for their JPEG with no error, the
    camera falls back to `cv2.imencode` as after an error (T-CAP-157). Real Quick Sync gave one JPEG for
    each frame from the second frame on, in a smoke run on the development machine.
13. **The pairing test.** T-CAP-67 also checks that each Quick Sync JPEG belongs to its own frame: the
    input number in the fake JPEG equals the place of its source frame among the taken frames, counted
    from input 0. This is stronger than "the sfn minus the first sfn": a frame that a newer frame
    replaced is never taken.
14. **The range tables.** `map_levels` uses `cv2.LUT` (a two-channel table for YUY2, one call per plane
    for NV12). At 1080p it took 2.38 ms (YUY2) and 1.33 ms (NV12), against 8.54 and 5.71 ms with NumPy
    indexing, with the same bytes (median of 200 runs, synthetic frames, one OpenCV thread, OpenCV of
    the lock file, development machine only).
15. **T-CAP-26.** The test fails with the code: its fixture `NATIVE_26` has a native NV12 type at
    1920x1080 at 30 fps, against its spec row "a size that only H.264 has". By Q807 an MJPG request there
    opens NV12. The test stays as it is until the user decides (open work).

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
