# 5MYA — Python API of the BGR ring and the decode stage, as the 2b tests assume it

**Status:** accepted, 2026-11-19 (user; commit to dom/native-jpeg; was proposed, 2026-11-19 (agent)).

## Decision

[ADR-50G8](50G8-phase-2-frame-ring-spec.md) accepts section 8 of
[`specs/frame-ring.md`](../../specs/frame-ring.md). The spec and
[ADR-9G2W](9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md) do not give each Python
name of step 2b. The failing tests of step 2b (T-RING-36 to 47) use the names below. An agent chose
them. Items 3 to 7 are in `skellycam.core.ipc.frame_ring`.

1. `CameraConfig.bgr_ring: bool = False` (item 39 of the spec). `create_session_rings` reads it
   from each config. It logs the size of each BGR ring and adds it to the session total.
   `CameraRingInfo.bgr_ring_name` is the name of that ring, or `None`.
2. The BGR writer is `FrameRingWriter`, with the `write` call of ADR-9G2W item 3. The writer reads
   `pixel_format` from the header. On a BGR ring, `payload` is an `ndarray` of shape
   `(height, width, 3)`, uint8, C-contiguous, and it can be read-only. The BGR reader is
   `FrameRingReader`. On a BGR ring, `FrameRead.payload` is the array of 6.6. Its annotation is
   `bytes | numpy.ndarray | None`.
3. `DecodeInput`: a frozen dataclass with the fields `payload`, `source`, `frame_number`,
   `arrival_ns`, `sample_ns`, `source_frame_number`, `flags` and `rotation_cw_deg`. `source` is
   `"JPEG"` (`payload` is `bytes`), `"BGR"` (`(h, w, 3)` uint8), `"YUY2"` (`(h, w, 2)` uint8) or
   `"NV12"` (`(h * 3 // 2, w)` uint8). `flags` are the flags of the JPEG frame.
4. `WaitingPlace()` with `put(item) -> None`, `take(timeout_s) -> DecodeInput | None` and the int
   `skipped` (the replacements of 8.3).
5. `decode_jpeg(payload) -> numpy.ndarray | None`: the call of 8.4, step 3.
6. `DecodeStage(writer, *, decode=decode_jpeg)` with `waiting_place`, `start()` and `stop()`.
   `start()` starts the one decode thread. `stop()` stops it and joins it. It does not decode a
   frame that waits, and it does not close the writer. The stage gets the shape from the ring
   header. After each frame, and one time at `stop()`, the decode thread copies `skipped` to
   `skipped_count`. Until phase 3 fixes the range rule (8.7), YUY2 and NV12 use `cv2.cvtColor`
   with `COLOR_YUV2BGR_YUY2` and `COLOR_YUV2BGR_NV12`.
7. `limit_libjpeg_warnings() -> None`: the call of 8.9 at the start of the camera process. A
   forwarded log line is `<line> (count <n>)`. `n` is the number of times that the line came
   since the last log line for it.
8. `run_opencv_camera_loop` has the optional argument `bgr_ring_writer`. When it is given, the
   loop makes and starts a `DecodeStage` on it. After each JPEG ring write, the loop puts a
   `DecodeInput` with `source="BGR"`, a new copy of the OpenCV frame and the flags of
   `check_jpeg` (8.8, item 42). When the loop ends, it stops the stage and closes the writer.

The tests do not fix these points. The code chooses them, and the review of 2b examines them:

- how `create_session_rings` gives the BGR creators to `CameraGroup`;
- how the camera process gets the BGR ring name, and the BGR ring on a mode change (7.5);
- how the decode thread writes `skipped_count`, and what it gives `write` for a flagged frame;
- where the camera process calls `cv2.setNumThreads(1)`. T-RING-45 checks only the process.

## Reason

- The tests must fix one name for each call that they make. The user decides the API before the
  code, as for ADR-9G2W.
- Each choice is the smallest that the tests need. One writer class and one reader class keep
  the one read path of 6.2 for both formats.
- `decode` is an argument, because T-RING-38, 39 and 44 need a decoder stub or a timed decoder.
- `bgr_ring_writer` follows `ring_writer` of ADR-9G2W item 14. It lets the tests run the
  production loop with a fake camera.

## Alternatives rejected

- Put the names into the spec: the spec is accepted. A new choice goes in a proposed entry.
- A second writer class for BGR: a second copy of steps W1 to W7.

## Open work

See [open-work.md](../open-work.md).
