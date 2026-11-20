# AT04 — Choices of the Linux and macOS capture spec

**Status:** proposed, 2026-11-20 (agent).

## Decision

The spec [`specs/unix-capture.md`](../../specs/unix-capture.md) (draft 1) and its test list
T-UNX-01 to T-UNX-60 are proposed. Section 8 of the spec lists 30 choices of the agent that the
decisions of the user ([ADR-22EJ](22EJ-decisions-of-the-user-for-linux-and-macos-native-capture.md))
do not fix. The main ones:

1. Linux: V4L2 through the standard library only (`fcntl.ioctl`, `mmap`, `select.poll`, `ctypes`
   structs, ported from the research layer with its reference values). No new dependency; linuxpy is
   rejected.
2. macOS: AVFoundation through eight PyObjC 13.0 packages, each pinned with `==` and marked
   `sys_platform == "darwin"`; IOKit through `ctypes`.
3. The `camera_id` input: Linux, the USB serial when it is present and unique, else the USB port
   chain from sysfs; macOS, `uniqueID`.
4. The open order of V4L2 with `REQBUFS(0)` first to find "in use"; `O_NONBLOCK` with `poll`; four mmap
   buffers; `EIO`, `ENOSPC` and `ENOMEM` at `STREAMON` give `usb-bandwidth`.
5. The exposure unit map `floor(2^v × 10000 + 0.5)` between log2 seconds and 100 µs units, clamped to
   the range; read-back compared in native units.
6. The native sources run SkellyCam Auto for a config that asks for the camera's auto exposure.
7. macOS controls through CoreMediaIO first; "Auto by lock" when a camera has no CoreMediaIO exposure
   control; endpoint-0 requests never in the product without the user's word.
8. The macOS JPEG variants `{}` then `'dmb1'`; the code `no-native-jpeg` after both, and a fallback to
   OpenCV for that camera.
9. The fixed failure codes of section 4.6.3 of the spec, taken from the certify reason codes.
10. One `diagnostics()` dict with the fixed keys of section 4.6.2 on each source, carried in the
    camera status.
11. An option to restore the controls at the close, with the setting `SKELLYCAM_RESTORE_CONTROLS`.
12. The settings `SKELLYCAM_LINUX_CAPTURE` and `SKELLYCAM_MACOS_CAPTURE`, and the default order:
    the setting, a local certify pass record, a `verified` evidence row, else OpenCV.
13. The modules of `v4l2/` and `avfoundation/` import only the standard library at module level, so
    that their fake tests run on each OS.
14. No new CI job; markers `capture_linux_runner`, `capture_macos_runner` and `v4l2_vivid`; a build
    test of the frozen macOS app.

## Reason

Each choice keeps the native sources testable on Windows with fake layers, gives certify one fixed
form of facts on each system, and adds the fewest dependencies.

## Alternatives rejected

- linuxpy 0.25.0 for V4L2: a dependency that the research never tested, for code the research
  already has.
- `ctypes` to the Objective-C runtime: a delegate class and blocks made by hand, with no test.
- The `/dev/v4l/by-id` names as identity: they collide for identical cameras with no serial.
