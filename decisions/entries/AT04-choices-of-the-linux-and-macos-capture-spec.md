# AT04 — Choices of the Linux and macOS capture spec

**Status:** proposed, 2026-11-20 (agent).

## Decision

The spec [`specs/unix-capture.md`](../../specs/unix-capture.md) (draft 2) and its test list
T-UNX-01 to T-UNX-88 are proposed. Section 8 of the spec lists 30 choices of the agent that the
decisions of the user ([ADR-22EJ](22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md))
do not fix. Section 9 lists four points that wait for the user; the spec is written to the
recommendation of each. ADR-22EJ item 14 holds the seven recommendations that the user accepted. The main choices:

1. Linux: V4L2 through the standard library only (`fcntl.ioctl`, `mmap`, `select.poll`, `ctypes`
   structs and ioctl numbers computed for the host, LP64 and 32-bit, with the 64-bit time layout;
   ported from the research layer, whose LP64 values become test values). No new dependency; the x32
   ABI keeps OpenCV.
2. macOS: AVFoundation through eight PyObjC 13.0 packages pinned with `==` and marked
   `sys_platform == "darwin"` (accepted by the user); IOKit through `ctypes`; macOS 12.3 and later.
3. The `camera_id` input: Linux, the USB serial, else the USB port chain from sysfs; macOS,
   `uniqueID` (accepted by the user).
4. The V4L2 open order with `REQBUFS(0)` first; `O_NONBLOCK` with `poll`; four mmap buffers; a limit of
   11 s for the probe-and-commit ioctls; `EIO`, `ENOSPC`, `ENOMEM` and `EFBIG` at `STREAMON` give
   `usb-bandwidth`; `ENODEV` at any streaming call, or `EIO` with the sysfs node gone, gives
   `device-removed`.
5. The exposure map `floor(2^v × 10000 + 0.5)`, clamped; CoreMediaIO exposure only with an absolute
   value in seconds; else no manual exposure on that macOS camera (accepted by the user); certify
   tries every other approach as a probe.
6. The exposure rules of the user on each source, with Auto opening at -7 for the start-up check,
   `exposure_found`, and `exposure_search: true` in an apply request.
7. The macOS JPEG variants `{}` then `'dmb1'`; `no-native-jpeg` after both; OpenCV for that camera
   outside certify (accepted by the user).
8. One `diagnostics()` dict per source with the names of the certify spec, plus the keys that it does
   not name; the D-11 hashes in the shared loop after `ready` and at each record start.
9. The local record `camera_checks.json` per camera model, OS key, ABI and backend, written by full
   runs.
10. The settings `SKELLYCAM_LINUX_CAPTURE`, `SKELLYCAM_MACOS_CAPTURE` and `SKELLYCAM_RESTORE_CONTROLS`.
11. Fake-testable modules that import only the standard library at module level.
12. A main-process stall watch of 2 s (accepted by the user).
13. No new CI job; markers `capture_linux_runner`, `capture_macos_runner`, `v4l2_vivid` and
    `capture_timing`; a build test of the frozen macOS app.

## Reason

Each choice keeps the native sources testable on Windows with fake layers, gives certify one fixed
form of facts on each system, and adds the fewest dependencies.

## Alternatives rejected

- linuxpy 0.25.0 for V4L2: a dependency that the research never tested, for code it already has.
- `ctypes` to the Objective-C runtime: a delegate class and blocks made by hand, with no test.
- The `/dev/v4l/by-id` names as identity: they collide for identical cameras with no serial.
- "Auto by lock" on macOS: it keeps the camera's own auto value, which the user forbids.
