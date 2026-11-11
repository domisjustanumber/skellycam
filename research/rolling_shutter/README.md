# Rolling shutter

How freemocap and skellycam could compensate for rolling-shutter readout on USB webcams. Started 2026-11-06.

The measurements this work relies on (readout time, timestamp sources, the ESP32 sync rig design) live in [`../usb_cameras/`](../usb_cameras/).

## Findings so far (2026-11-06)

- **Neither skellytracker nor freemocap compensates for rolling shutter.** Every stage treats "same frame number" as "same instant" and every image as captured all at once.
  - Triangulation is plain DLT per frame index.
  - Both calibration solvers (pyceres and Anipose) fit one rigid board pose per frame index.
  - No calibration frame is gated for stillness or blur.
  - skellytracker makes up timestamps from `frame_number / fps`, and its `Observation.timestamp` is never set.
- **Readout time is not cleanly measured yet.** The C922's 30–31 ms per frame height (720p30 MJPEG) from the screen-flash method includes display scan-out (`../usb_cameras/timing/VERIFY_method.md` §1), so treat it as an upper bound.
  - Two equipment-free methods are proposed: mains-flicker banding, and repeating the flash test with the camera rotated 180°.
- **No light-to-timestamp anchor is known for any source.** C922 PTS appears to sit near the end of exposure (REPORT finding 12, provisional). Settling anchors needs the ESP32 strobe rig. RocSync could do part of it, but there is no board.

## Contents

| Path | What it is |
| --- | --- |
| [`still_charuco_issue/issue.md`](still_charuco_issue/issue.md) | Draft GitHub issue for freemocap: calibrate only from still ChArUco frames, with the realtime overlay yellow while the board moves and green when it is still. Not posted. |
| [`still_charuco_issue/proposed_changes.patch`](still_charuco_issue/proposed_changes.patch) | Proposed freemocap changes for that issue. Paths are relative to the freemocap repo root; applies to `development` @ `5632778a`. |

**Patch verification (2026-11-06):**
- **Passed:** applies cleanly (`git apply --check`); 38 tests pass in a scratch copy (15 of them new); the UI type-checks (`tsc --noEmit`, 0 errors).
- **Not run:** the end-to-end pipeline tests and a live realtime check. The local `.venv` has an outdated skellytracker.
