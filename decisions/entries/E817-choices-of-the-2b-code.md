# E817 — Choices of the 2b code that the spec and ADR-5MYA do not fix

**Status:** accepted, 2026-11-19 (user; commit to dom/native-jpeg; was proposed, 2026-11-19 (agent)).

## Decision

The code of step 2b follows [`specs/frame-ring.md`](../../specs/frame-ring.md),
[ADR-5MYA](5MYA-python-api-of-the-bgr-ring-and-the-decode-stage-as-the-2b-tests-assume-it.md) and
[ADR-467Z](467Z-step-2b-self-check-stop-opencv-threads-and-yuv-conversion.md). An agent made the
choices below. Items 1 to 4 answer the four points that ADR-5MYA leaves to the code.

1. The BGR creator of a camera is the attribute `bgr` of its JPEG `FrameRingCreator` (`None` when
   the config does not ask for one). `set_closed()` and `close_and_unlink()` also apply to it. Thus
   `create_session_rings` keeps its return type, and `CameraGroup` does not change. Both rings of a
   camera have the same generation in their names.
2. `await_ring_writer` returns the JPEG ring writer and the BGR ring writer (or `None`) from the
   same `CameraRingInfo`. `setup_opencv_camera_loop` returns the BGR ring writer as a fifth value.
   A change of `resolution`, `framerate` or `bgr_ring` recreates the rings (7.5): the loop stops
   the decode stage, closes both writers, attaches the new ones and starts a new stage.
   `apply_camera_configuration` copies `bgr_ring` into the extracted config, because the device
   does not give it.
3. The new call `FrameRingWriter.set_skipped_count(count)` copies the skips of the waiting place to
   `skipped_count`. It does nothing on a closed ring. The decode thread gives `write` the payload
   `None` for a flagged frame and for a failed decode. `FrameRingWriter.shape` is
   `(height, width, 3)` from the ring header.
4. `opencv_camera_worker_method` calls `cv2.setNumThreads(1)` and `limit_libjpeg_warnings()` as its
   first steps.
5. The shape check of 8.4 step 4 applies to each source (JPEG, BGR, YUY2 and NV12). An exception
   in the decode or the conversion gives `DECODE_ERROR`. It logs at debug level only, because
   `decode_error_count` records each failure.
6. `limit_libjpeg_warnings()` on Linux and macOS: descriptor 2 goes to a pipe, and `sys.stderr`
   goes to a copy of the old descriptor 2, so that tracebacks are not limited. A count that waits
   is logged with the next line of the same text, not by a timer. A second call does nothing.
7. `limit_libjpeg_warnings()` on Windows does nothing and logs one line. The OpenCV 5.1.0 wheel
   has its own C runtime with its own copy of the stderr handle. `os.dup2` closes that handle.
   Then libjpeg writes to a closed handle, which the OS can give to another object. Thus
   T-RING-46 fails on Windows. The user decided on 2026-11-19: the limit stays off on Windows
   until phase 3, and T-RING-46 is an expected failure on Windows until then. Until phase 3, the
   decode stage gets BGR frames and decodes no JPEG, so libjpeg gives no warning there.
8. In the OpenCV loop, the hand-over to the waiting place is in the same `try` as the JPEG ring
   write. When that write raises, the BGR ring does not get the frame, and no skip is counted.
9. The three test helpers that replace `setup_opencv_camera_loop` in
   `skellycam/tests/reference_recordings/` return `None` as the fifth value.

## Reason

- Each choice is the smallest that the tests and the spec need.
- Item 1 keeps the return type of `create_session_rings` of
  [ADR-9G2W](9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md) item 12.
- Item 3 keeps one writer of the ring header: only the decode thread writes `skipped_count` (8.3).
- Item 7: a write into a handle that the OS gave again can go into a recording file.

## Evidence

- Windows 11, OpenCV 5.1.0, Python 3.13.18: `cv2.utils.logging.setLogLevel(LOG_LEVEL_SILENT)` does
  not stop the libjpeg line. The `cv2.pyd` file imports no C runtime DLL. After `os.dup2(w, 2)`,
  `GetHandleInformation` on the old handle fails, and the libjpeg line goes nowhere.
- Ubuntu in WSL 2, Python 3.12.3: the code of item 6, with `fputs` to `stderr` through `ctypes`,
  forwarded 1,000 lines of two texts as two log lines with `(count 1)`. `sys.stderr` still wrote to
  the old descriptor 2. OpenCV was not installed there.

## Alternatives rejected

- A second dict of BGR creators in `CameraGroup`: more code in four methods.
- The fd redirect on Windows: it does not reach the OpenCV C runtime, and it leaves a closed handle.

## Open work

See [open-work.md](../open-work.md).
