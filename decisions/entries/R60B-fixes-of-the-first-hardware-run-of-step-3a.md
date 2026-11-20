# R60B — Fixes of the first hardware run of step 3a

**Status:** superseded by [2GS1](2GS1-step-3a-choices-of-the-capture-code-and-its-fixes.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent; waits for the user)).

## Decision

The first run of the 3a hardware tests on the Windows development machine found two faults. An
agent made the choices below. The user decides them.

1. **Product.** `OpenCVSource.open` gave the index of the detection result as
   `OpenedMode.device_path`. Section 4.1 of
   [`specs/windows-capture.md`](../../specs/windows-capture.md) asks for the device path. On Windows
   the source now gives the DirectShow device path of the index that the lookup by link opened (14.2,
   U1). `opened_device_path` in `create_cv2_video_capture.py` finds it. On Linux and macOS the device
   path stays the index. The device that opens does not change: the lookup by link was already
   correct. T-CAP-88 failed on the C922 and the C930e only for this field. A fake test
   (`test_opencv_source_reports_the_directshow_path_it_opened`) fails without the fix on each
   system.
2. **Test.** The hardware tests found each camera by its friendly name. Media Foundation names the
   Kiyo Pro "USB Video Device". Thus the Kiyo Pro, the generic camera and the NDI software cameras
   all got the label "generic", and T-CAP-53 could open the Kiyo Pro as the generic camera.
   `label_of` in `capture_hardware.py` now uses the USB vendor and product IDs first, then the name.
   A camera with no USB vendor ID (for example NDI) is not a test camera. No criterion changed. A
   self-test in `test_helpers.py` checks the labels.

## Reason

- Item 1 is a product fault: the value is wrong in the product, not only in a test.
- Item 2: the test was the faulty side. Without the fix, a test can open the wrong camera.

## Evidence

- Detection (7.1) on the development machine listed 8 devices: the 4 test cameras and 4 NDI
  software cameras ("NDI Webcam Video 1" to "4"). The NDI cameras have a link under `root#media`,
  no USB IDs, `virtual: false` and `supported_modes: []`.
- Before the fix, T-CAP-88 gave the device paths "6", "0" and "7": the detection indexes.
