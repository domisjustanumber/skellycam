# 8MTY — Answers V1 to V7 of the user to the 3b and 3c tests

**Status:** accepted, 2026-11-19 (user; relayed by the supervisor; commit to dom/3bc-tests).

## Decision

The user read the report on the failing tests of steps 3b and 3c on 2026-11-19, and gave seven
answers. They correct [`specs/windows-capture.md`](../../specs/windows-capture.md), which marks each
one [Vn] and lists them in section 20. They add to
[ADR-4CQC](4CQC-phase-3-windows-capture-spec-and-test-list.md).

1. **V1.** `capture_modes` (the full mode list) comes in step 3b, not 3c. This changes the step of D14
   for the second field. T-CAP-71 and T-CAP-79 move to step 3b.
2. **V2.** An auto frame rate (-1 or 0) with a YUY2 or NV12 request looks at the modes of the
   requested format at the requested size: 30 if that format has 30, else 29.97, else its highest
   rate at the floor or above.
3. **V3.** The status has the field `jpeg_encoder`: `"quick_sync"`, `"cv2"`, or null for MJPG. A
   fallback from Quick Sync to `cv2.imencode` during a take gives one WARNING log line, a count at
   stop, and an item in the API `warnings` list.
4. **V4.** OpenCV source (Linux, macOS): a YUY2 or NV12 request gives a `cv2.imencode` JPEG at quality
   90 of the image that OpenCV delivers. No Quick Sync check runs. `jpeg_encoder` is `"cv2"`.
   `input_range` is null in the recording info. Parity test T-CAP-105.
5. **V5.** OpenCV source: gain and focus are set and read back through the OpenCV properties. A
   read-back that does not match is reported as a failed change, as on Windows. White balance and
   power line frequency are read through OpenCV where it gives a value, else null. `capture_modes` is
   `[]` on OpenCV detection. Parity tests T-CAP-106, T-CAP-107 and T-CAP-108.
6. **V6.** Two tests for the range: a limited-range raw input gives a full-range JPEG (T-CAP-109),
   and the BGR ring image of that JPEG matches it within a small stated error (T-CAP-110). The
   conversion that passes both is the one the product keeps. The conflict between section 8.7 of
   [`specs/frame-ring.md`](../../specs/frame-ring.md) and
   [ADR-467Z](467Z-step-2b-self-check-stop-opencv-threads-and-yuv-conversion.md) item 4 is an open
   point of the spec (17.2 item 15), and these tests decide it.
7. **V7.** The hardware control tests (T-CAP-78 and the like) run on the C922, the C930e and the
   Kiyo Pro. The generic camera fails the 30 fps check and never reaches `ready`; for it, the test
   records only its status.

The agent choices that came with this pass are items 79 to 90 of section 18 of the spec and
[ADR-3WCA](3WCA-python-api-of-capture-as-the-3b-and-3c-tests-assume-it.md). They are not decided by
this entry.

## Reason

- V1: the whole-request check of a YUY2 or NV12 request (7.5) needs the full mode list in step 3b.
- V2: a YUY2 or NV12 request opens that format, so its auto rate must come from that format.
- V3: a consumer must see that a take changed its encoder.
- V4, V5: the user wants parity of the 3b and 3c rules on Linux and macOS, with tests in CI.
- V6: the two rules disagree for a full-range camera; a measured result decides.
- V7: the generic camera can never reach `ready` at 30 fps (D24), so its controls cannot be set live.

## Open work

See [open-work.md](../open-work.md).
