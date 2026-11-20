# 22EJ — Decisions of the user for Linux and macOS native capture

**Status:** accepted, 2026-11-20 (user; relayed by the supervisor session on 2026-11-20).

## Decision

The user decided these points for the native capture of Linux (V4L2) and macOS (AVFoundation). The
spec [`specs/unix-capture.md`](../../specs/unix-capture.md) builds on them.

1. The native sources are written now, before a Linux or macOS machine is at hand, and certify
   validates their assumptions: "certify runs to validate assumptions about linux and mac code.
   Ideally as much real code is implemented as possible now so a single test run provides as much
   information as possible and can be used there and then if the tests pass."
2. Certify tests the native capture only: "the aim of this is to use certify to test out the native
   capture features and see if they work. OpenCV is already fairly proven to work, so no need to test
   here."
3. The Media Foundation folder is Windows only: "everything in that folder is Windows only". Linux and
   macOS each get their own folder.
4. Parity of the tests: "ensure there are similar parity tests for linux and mac, not just detailed
   tests for Windows and none for other platforms".
5. Exposure: "I never want to allow the camera to set it's own exposure". The exposure modes are
   Manual and Auto. Auto is SkellyCam's own one-shot search on the open stream with a frame-rate
   guard. The camera's own auto exposure is never a mode. On Linux and macOS, the forced camera auto
   exposure of today's OpenCV path ends with this step: manual exposure goes through the native
   control APIs.
6. These earlier decisions bind the spec and are not reopened: pure Python, no compiled extension of
   our own, no Rust; exact pins; each dependency must be justified; MJPG frames pass through byte-true
   (the recorder stores the camera's JPEG bytes, with a DHT inserted when the camera sends none); no
   mode below 30 fps is offered; one frame rate for the group, and 60 fps only when proven; virtual
   cameras are shown (label "virtual") but cannot be selected; each camera shows a USB link label (USB
   2, USB 3 or unknown); a camera process that hangs costs the other cameras at most 100 ms; the
   camera processes use `spawn` on every system; a camera failure reason gets a fixed failure code
   beside the text; hot-unplug tests are not run; the OpenCV source stays in the tree as the fallback
   until a system is verified.
7. A camera that failed is never opened again in the same certify run.

## Reason

The user wants one certify run on a real system to give the most information, and to make native
capture usable on that system at once when it passes. OpenCV capture is already proven.

## Consequences

- Each assumption of the native sources needs a run-time check, a diagnostic and a certify check.
- The proposal to restore the camera controls at the close of the product is asked of the user and
  not decided. [ADR-AT04](AT04-choices-of-the-linux-and-macos-capture-spec.md) holds it as an option.
