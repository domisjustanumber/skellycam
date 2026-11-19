# HP7D — Python API of capture, as the 3a tests assume it

**Status:** proposed, 2026-11-19 (agent).

## Decision

[ADR-4CQC](4CQC-phase-3-windows-capture-spec-and-test-list.md) accepts
[`specs/windows-capture.md`](../../specs/windows-capture.md). The spec does not give each Python
name of step 3a. The failing tests of step 3a in `skellycam/tests/capture/` use the names below. An
agent chose them. `capture` is `skellycam.core.camera.capture`, with the modules of spec section 3.

What a consumer sees:

1. `measured_fps` in the status is not rounded.
2. `CameraGroupManager.detected_cameras` keeps the last result of `/camera/detect` by `camera_id`.
   The whole-request check (8.3) uses its `supported_modes` when each camera of the request has a
   list that is not empty. Else it compares the requested rates (7.5).
3. `CaptureMode(width, height, framerates)` (pydantic) in `detect_cameras_devices.py`, and
   `CameraDeviceInfo.supported_modes: list[CaptureMode] = []`.
4. Log lines. The stop line of 5.2 holds the camera ID, then `replaced`, then the count as the first
   number after that word. The stop line of 5.5 holds the camera ID, `flagged` and the count. The
   warning of 10.3 holds the camera ID and the measured rate.
5. The reason of a missing mode (7.5) holds `json.dumps` of the `supported_modes` dicts.

The Python names:

6. `capture.source`: `CapturedFrame` (a frozen dataclass with the fields of 4.2 in that order);
   `OpenedMode(width, height, fps_num, fps_den, format, device_path)`;
   `CaptureRequest(camera_id, width, height, framerate, capture_fourcc="MJPG")`;
   `ControlSetting(auto, value)` for each item of `changes`; `ControlValue(present, auto, value)`;
   `ControlState = dict[str, ControlValue]`; `CaptureFailure(stage, reason, *, hung=False)`, an
   `Exception`; `CaptureWaitingPlace` with `put(frame)`, `put_error(failure)`, `take(timeout_s)` and
   the int `replaced` (`take` raises the failure of an error marker); the `CaptureSource` protocol;
   `FIRST_FRAME_TIMEOUT_S = 5.0` and `BOUNDED_CALL_LIMIT_S = 5.0`.
7. A source raises `CaptureFailure(..., hung=True)` when its bounded call does not return in time.
   The camera process then reports and ends hard (6.6). A source raises stage `set controls` for a
   failed or hung control call. After the start-up, the loop reports such a failure with stage
   `streaming` (table 12).
8. `capture.modes`: `NativeMode(width, height, fps_num, fps_den, format)`,
   `supported_modes(native) -> list[CaptureMode]`, `choose_mode(native, request) -> NativeMode` (it
   raises `CaptureFailure("set mode", ...)`) and `rates_equal(a, b)`.
9. `capture.media_foundation`: `errors.hresult_reason(hresult) -> str` for the unsigned value.
   `detect.detect_media_foundation_cameras(*, backend=None) -> list[CameraDeviceInfo]`. A backend has
   `devices() -> [(friendly name, link)]` and `native_modes(link) -> list[NativeMode]`; `None` is
   `detect.MediaFoundationBackend`. A hang raises `CaptureFailure` with stage `detection`. A
   `camera_id` collision raises `ValueError`. `errors.py` and `detect.py` import on each OS. `com.py`
   has the interfaces of 6.2, 6.5 and 6.8 by their COM names, and `startup()` and `shutdown()`.
10. `CameraGroupManager.source_factory: Callable[[CameraConfig], CaptureSource] | None = None`. The
    group gives it to each camera process, so it can be pickled. `None` is the source of 14.2.
11. `camera_worker.select_capture_source() -> str` gives `"opencv"` or `"media_foundation"`. A wrong
    value raises `ValueError`.
12. The shared loop reads the time only through the name `camera_loop.perf_counter_ns`, so that a
    test can replace it. The loop calls `should_grab_by_id` while it waits at the gate.
13. `OpenCVSource(config)`. `opencv_source.py` calls `create_cv2_video_capture(config)` by its module
    name.
14. `CameraSetupFailure(camera_id, stage, reason)`; `str()` gives the text of D40.
    `report_setup_failure` keeps the first failure of each camera and does not set the shutdown
    flag. `take_setup_failure()` stays.
15. `VideoRecorder.record_frame` raises `ValueError`, which names both IDs, for a frame of another
    camera (D41).
16. These stay, because the tests read them: `CameraStatus.serialize()`, `CameraStatus.frame_count`,
    `CameraGroup.ring_infos`, `CameraGroup.cameras.camera_workers`, `CameraGroup.configs` and
    `CameraGroup.get_latest_ring_payload()`.
17. Hardware test switches: `SKELLYCAM_HARDWARE_DARK=1` (T-CAP-55), `SKELLYCAM_HARDWARE_UNPLUG=1`
    (T-CAP-58) and `SKELLYCAM_HARDWARE_RESULTS` (the result file, outside the repository).

## Reason

- The tests must fix one name for each call that they make. The user decides the API before the
  code, as for [ADR-9G2W](9G2W-python-api-of-the-frame-ring-as-the-2a-tests-assume-it.md) and
  [ADR-5MYA](5MYA-python-api-of-the-bgr-ring-and-the-decode-stage-as-the-2b-tests-assume-it.md).
- Each choice is the smallest that the tests need. The spec fixes the rest.
- Items 10, 12 and 13 are the seams that let the tests run the product loop with fake sources and a
  virtual clock. Item 7 lets a fake source show a hang to the product as a source does.

## Alternatives rejected

- Put the names into the spec: the spec is accepted. A new choice goes in a proposed entry.
- A clock argument through the group, the manager and the worker: one module name is enough.
- A fake source with its own waiting place and mode choice: the tests would then check the fake.

## Open work

See [open-work.md](../open-work.md).
