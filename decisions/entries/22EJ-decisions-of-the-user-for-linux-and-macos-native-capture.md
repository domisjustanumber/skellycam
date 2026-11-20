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
   here." The per-camera OpenCV fallback never runs inside certify.
3. The Media Foundation folder is Windows only: "everything in that folder is Windows only". Linux and
   macOS each get their own folder.
4. Parity of the tests: "ensure there are similar parity tests for linux and mac, not just detailed
   tests for Windows and none for other platforms". macOS has fake tests of the same depth as Linux,
   and Windows gets tests for each thing that the spec adds to Media Foundation.
5. Exposure: "I never want to allow the camera to set it's own exposure". On Linux and macOS, the
   forced camera auto exposure of today's OpenCV path ends with this step: manual exposure goes
   through the native control APIs. Windows changes the same way, in a separate commit.
6. Exposure modes (ruling of 2026-11-20):
   - "Auto" always means that SkellyCam finds a manual value by its one-shot search on the open
     stream. The camera's own auto exposure is never a mode.
   - Auto stays the stored mode. A camera in Auto searches at every open, when the user changes the
     frame rate, and when the user asks. Manual keeps the user's value and never searches.
   - A new camera starts in Auto.
   - During the search the state is `adjusting`, the preview shows, and no recording can start.
   - The search never keeps a value at which the frame rate falls. On failure it restores the old
     settings.
   - Exposure never changes during a take.
   - The slow-camera text is exactly "Camera is slow. Try adding more light".
   - Nothing below 30 fps; one frame rate (30 or 60) for all cameras.
7. The default source on Linux and macOS: the setting, then a local passed full certify run on this
   machine, then a `verified` row of the evidence file, else OpenCV.
8. A camera counts as certify-checked once per model (USB vendor id and product id) per system;
   skellycam keeps that record.
9. The product restores the controls of each camera to their values before the open at its own close.
   This is on by default, on all three systems.
10. The certify checks are the hardware tests of the Linux and macOS sources. T-CAP-92 to T-CAP-98
    are retired.
11. Earlier decisions bind the spec: pure Python, no own compiled extension, no Rust; exact pins; a
    justified dependency; byte-true MJPG, with a DHT inserted when the camera sends none; no mode
    below 30 fps; one group rate, 60 fps only when proven; virtual cameras shown, not selectable; a
    USB link label; a hung camera costs the others at most 100 ms; `spawn` on each system; a fixed
    failure code; no hot-unplug test; OpenCV stays as the fallback until a system is verified.
12. A camera that failed is never opened again in the same certify run.
13. The certify spec owns the names and values of each key, value, check name and reason code that
    certify reads; the capture spec uses them.
14. Accepted recommendations of draft 2: a macOS camera with no manual exposure gets no Auto and no
    exposure control (warning `no-manual-exposure`; camera item `partial`), and "Auto by lock" goes;
    a `no-native-jpeg` macOS camera opens with OpenCV for now, never inside certify; the eight PyObjC
    13.0 pins; the one-time `camera_id` change; the 2 s main-process stall watch; macOS 12.3 or later;
    endpoint-0 requests only as a certify probe.
15. The V4L2 layout is not fixed to 64-bit. Each struct layout and ioctl number is computed for the
    system that runs the code, so that native capture can run on 32-bit Linux too. A test checks the
    computed 64-bit values against the known constants (88 bytes, 0xC0585611, 0xC0205648). A 32-bit
    system is unverified like any other and keeps OpenCV until a certify run passes there.
16. On macOS, every approach that might work for exposure control and for the delivery of the
    camera's own JPEG is tried in a certify run for now; the test is trimmed once a working one is
    found. The product uses only the approaches that the earlier rulings allow; the others are
    certify probes.
17. The apply or open request answers when the cameras are open and streaming. The exposure search
    then runs with the camera in `adjusting`, and its result arrives through the status. The request
    does not wait for the search.
18. The certify contract is format 1.3.0: the results are `pass`, `fail`, `record-only`, `partial`
    and `skipped`; a camera that another program holds is `skipped` with the reason `busy`; there is
    one camera item for each camera model.
19. The macOS approach probes run once per camera model. The longer macOS full run is accepted until
    one approach is proven.

## Reason

The user wants one certify run on a real system to give the most information, and to make native
capture usable on that system at once when it passes. OpenCV capture is already proven.

## Consequences

- Each assumption of the native sources needs a run-time check, a diagnostic and a certify check.
- The exposure rules change the Windows spec (D29, the states, the slow text and some tests).
- Five points wait for the user: section 9 of the spec and
  [ADR-AT04](AT04-choices-of-the-linux-and-macos-capture-spec.md).
