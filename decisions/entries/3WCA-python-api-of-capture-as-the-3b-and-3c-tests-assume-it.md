# 3WCA — Python API of capture, as the 3b and 3c tests assume it

**Status:** proposed, 2026-11-19 (agent).

## Decision

[ADR-4CQC](4CQC-phase-3-windows-capture-spec-and-test-list.md) accepts
[`specs/windows-capture.md`](../../specs/windows-capture.md). The spec and
[ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md) do not give each name and shape
that the failing tests of steps 3b and 3c in `skellycam/tests/capture/` use. An agent chose the
items below. `capture` is `skellycam.core.camera.capture`.

What a consumer sees:

1. The status (8.4) gets `jpeg_encoder`: `"quick_sync"` or `"cv2"` for a camera whose JPEG is
   encoded at capture, `null` for a camera that gives its own JPEG (MJPG).
2. `CameraDeviceInfo.capture_modes: list[CaptureModeEntry] = []` comes in step 3b, not 3c. The
   whole-request check of a YUY2 or NV12 request uses it (7.5). `CaptureModeEntry` (pydantic, in
   `detect_cameras_devices.py`) has the fields of 7.4 in the order of its JSON.
3. `capture_modes` (7.4): an exact duplicate (size, `fps_num`, `fps_den`, format) is listed one time.
   For one size, the rounded rates ascend. For one size and rounded rate, MJPG comes first, then the
   other formats in the order of the native list. H.264 and RAW have the reason "never opened" at
   each rate.
4. Log lines. When the encoder fails, one WARNING line holds the camera ID and `cv2.imencode`. At
   stop, each camera with an encoder logs a line with the camera ID, then `encoder fallbacks`, then
   the count.
5. A request to set a control that the status of a running camera shows as absent gets 422 with the
   text of 11.5.

The Python names:

6. `capture.encoder.quick_sync_works() -> bool` is the central check (13.2). The
   `CameraGroupManager` keeps its result for its lifetime: one app run. It calls the check at most
   one time, and only for a request with a YUY2 or NV12 camera.
7. `capture.encoder.open_quick_sync_encoder(format, width, height, *, quality)` gives an encoder with
   `encode(raw) -> list[bytes]` (the JPEGs that came out, in input order), `flush() -> list[bytes]`
   and `close()`. An exception from `encode` or `flush` is an encoder failure. After a failure, the
   loop does not use that encoder again. It encodes the held frames again from their raw frames.
8. `OpenedMode.os_range: str | None = None`: the range flag of the OS for the opened type
   (`"limited"`, `"full"`, or `None` when not set).
9. A raw frame of the wrong length is a 1-D uint8 array of the delivered bytes. `delivered_len` is
   its length.
10. `capture.modes.capture_modes(native) -> list[CaptureModeEntry]`. `choose_mode` uses
    `request.capture_fourcc` and never takes a synthesized NV12 type.
11. The control names `white_balance` and `power_line_frequency` in `ControlState`. `set_controls({})`
    reads them (11.4).
12. Hardware switch `SKELLYCAM_HARDWARE_PROTOTYPE_MODES` (T-CAP-79): a JSON file outside the
    repository, with the native types of the prototype for each camera label, in the form of
    `flag_types` of its `parse.py` (`subtype`, `width`, `height`, `fps_num`, `fps_den`, `flags`).
13. T-CAP-76: the "history documents" are the files under `decisions/` and `specs/`. The test is in
    the tree now with a skip mark. The last commit of phase 3 removes the mark.

## Reason

- The tests must fix one name for each call that they make. The user decides the API before the
  code, as for [ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md).
- Items 1 and 4 make the encoder visible to a test in each worker mode: T-CAP-63, T-CAP-64, T-CAP-68
  and T-CAP-69 need them.
- Item 2: 7.5 needs the full native list in 3b, but 7.4 adds the field in 3c. One field for both is
  the smallest choice.
- Items 6 and 7 are the seams that replace Quick Sync with a fake in CI, so that no test needs an
  Intel GPU. Quick Sync at `async_depth` 2 holds one frame, so `encode` can give no JPEG or one
  JPEG.
- Item 5: the main process can refuse a whole request (8.3) only with data that it has. Before the
  first open, it does not know the controls of a camera.

## Alternatives rejected

- A status count of the encoder fallbacks: a log line is enough for the tests, and it adds no key.
- An encoder object with one JPEG out for each frame in: Quick Sync holds a frame.
- A module-level cache of the check result: then one test run would be one app run for each test.

## Open work

See [open-work.md](../open-work.md).
