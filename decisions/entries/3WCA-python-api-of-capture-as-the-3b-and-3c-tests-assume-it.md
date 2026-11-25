# 3WCA — Python API of capture, as the 3b and 3c tests assume it

**Status:** absorbed into
[`specs/windows-capture.md#222-rules-of-step-3b`](../../specs/windows-capture.md#222-rules-of-step-3b),
[`specs/windows-capture.md#226-python-api-and-rules-of-the-port`](../../specs/windows-capture.md#226-python-api-and-rules-of-the-port),
2026-11-25 (commit to dom/jpeg-encode-tests; was accepted, 2026-11-25 (user: [ADR-B95N](B95N-decisions-of-the-user-on-the-raw-mode-open-the-yuyv-format-and-the-3b-choices.md), Q810); was proposed, 2026-11-19 (agent)).

## Decision

[ADR-4CQC](4CQC-phase-3-windows-capture-spec-and-test-list.md) accepts
[`specs/windows-capture.md`](../../specs/windows-capture.md).
[ADR-8MTY](8MTY-answers-v1-to-v7-of-the-user-to-the-3b-and-3c-tests.md) (V1 to V7) corrects steps 3b
and 3c. The spec, [ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md) and V1 to V7 do
not give each name and shape that the failing tests of steps 3b and 3c in `skellycam/tests/capture/`
use. An agent chose the items below. `capture` is `skellycam.core.camera.capture`.

On `dom/integration` (2026-11-25, [ADR-0Z2F](0Z2F-choices-of-the-port-of-the-3b-tests-to-dom-integration.md)):
section 22 of the spec marks each 3b item as [3WCA n]. Items 5, 11, 13 and 14 belong to the tests
that stay on `dom/3bc-tests` (3c and hardware). They do not apply on `dom/integration` until those
tests move.

What a consumer sees:

1. `CaptureModeEntry` (pydantic, in `detect_cameras_devices.py`) is the item of `capture_modes` (V1),
   with the fields of 7.4 in the order of its JSON.
2. `capture_modes` (7.4): an exact duplicate (size, `fps_num`, `fps_den`, format) is listed one time.
   For one size, the rounded rates ascend. For one size and rounded rate, MJPG comes first, then the
   other formats in the order of the native list. H.264 and RAW have the reason "never opened" at
   each rate.
3. An encoder fallback (V3): the `warnings` item has the kind `encoder_fallback`. It is in the status
   `warnings` while the take runs. The WARNING line holds the camera ID and `cv2.imencode`. At stop,
   each camera with an encoder logs a line with the camera ID, then `encoder fallbacks`, then the
   count.
4. A request to set a control that the status of a running camera shows as absent gets 422 with the
   text of 11.5.
5. (3c, kept on `dom/3bc-tests`.) OpenCV source (V5): "no white balance value" means that `CAP_PROP_WB_TEMPERATURE` reads 0 or less.
   The power line frequency is null, because OpenCV has no property for it.

The Python names and the test rules:

6. `capture.encoder.quick_sync_works() -> bool` is the central check (13.2). The
   `CameraGroupManager` keeps its result for its lifetime: one app run. It calls the check at most
   one time, and only for a request with a YUY2 or NV12 camera of the Media Foundation source.
7. `capture.encoder.open_quick_sync_encoder(format, width, height, *, quality)` gives an encoder with
   `encode(raw) -> list[bytes]` (the JPEGs that came out, in input order), `flush() -> list[bytes]`
   and `close()`. An exception from `encode` or `flush` is an encoder failure. After a failure, the
   loop does not use that encoder again. It encodes the held frames again from their raw frames. "The
   first frame after the event" is the first ring frame written after it.
8. `OpenedMode.os_range: str | None = None`: the range flag of the OS for the opened type
   (`"limited"`, `"full"`, or `None` when not set).
9. A raw frame of the wrong length is a 1-D uint8 array of the delivered bytes. `delivered_len` is
   its length.
10. `capture.modes.capture_modes(native) -> list[CaptureModeEntry]`. `choose_mode` uses
    `request.capture_fourcc`, the auto rate of V2, and never takes a synthesized NV12 type.
11. (3c, kept on `dom/3bc-tests`.) The control names `white_balance` and `power_line_frequency` in `ControlState`. `set_controls({})`
    reads them (11.4).
12. T-CAP-152 and T-CAP-153 (V6; T-CAP-109 and T-CAP-110 on `dom/3bc-tests`) accept a mean absolute difference of 3 levels.
13. (Hardware, kept on `dom/3bc-tests`.) Hardware switch `SKELLYCAM_HARDWARE_PROTOTYPE_MODES` (T-CAP-79): a JSON file outside the
    repository, with the native types of the prototype for each camera label, in the form of
    `flag_types` of its `parse.py` (`subtype`, `width`, `height`, `fps_num`, `fps_den`, `flags`).
14. (3c, kept on `dom/3bc-tests`.) T-CAP-76: the "history documents" are the files under
    `decisions/` and `specs/`. On `dom/3bc-tests` the test is in the tree with a skip mark, and the
    last commit of phase 3 removes the mark. On `dom/integration` the test is not in the tree.

## Reason

- The tests must fix one name for each call that they make. The user decides the API before the
  code, as for [ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md).
- Item 3 makes the fallback visible to a test in each worker mode (T-CAP-64, T-CAP-69).
- Items 6 and 7 are the seams that replace Quick Sync with a fake in CI, so that no test needs an
  Intel GPU. Quick Sync at `async_depth` 2 holds one frame, so `encode` can give no JPEG or one
  JPEG.
- Item 4: the main process can refuse a whole request (8.3) only with data that it has. Before the
  first open, it does not know the controls of a camera.
- Item 12: on the synthetic frames of the tests, a correct conversion measured under 0.4 levels and a
  wrong one about 6.9 levels.

## Alternatives rejected

- A status count of the encoder fallbacks: the log line and the `warnings` item are enough.
- An encoder object with one JPEG out for each frame in: Quick Sync holds a frame.
- A module-level cache of the check result: then one test run would be one app run for each test.

## Open work

See [open-work.md](../open-work.md).
