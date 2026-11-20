# 6T78 — Choices of the sfn26 integration

**Status:** proposed, 2026-11-20 (agent).

## Decision

An agent merged `dom/recorder-connection`, upstream `sfn26` and `dom/preview` into
`dom/integration`, ported four items and removed the Rust parts
([ADR-EQY4](EQY4-base-the-work-on-upstream-sfn26-without-rust.md)). The user did not decide these
choices:

1. **OpenCV open helpers.** `create_cv2_video_capture.py` and `opencv_apply_config.py` stay ours,
   because our OpenCV source opens through them. The `sfn26` DirectShow order (frame rate first,
   MJPG last), its boolean DirectShow exposure and their two tests are dropped. The two files change
   together: one of them alone leaves a DirectShow stream in YUY2. The open order fix of `sfn26`
   2e29f8cbc is dropped by this choice. Not verified: whether OpenCV 5.1.0.95 with DirectShow falls
   back to YUY2 without that order (sfn26 saw it on OpenCV 4.12); a check on the cameras is open. The
   user accepted this item on 2026-11-20, subject to that check.
2. **RECOMMEND at the open.** `opencv_apply_config.py` skips `RECOMMEND`. The camera loop runs the
   search (11.1). Before, the OpenCV source also ran the old helper search at the open.
3. **Constants.** `MIN_EXPOSURE`, `NUMBER_OF_FRAMES_TO_SETTLE` and `TARGET_BRIGHTNESS` are in
   `camera_loop.py`, because `sfn26` deletes `recommend_camera_exposure_setting.py`.
4. **Pins.** Our exact pins stay, also the `skellylogs` and `skellypings` revisions. The version is
   `v2.0.0-alpha.6` of `sfn26`.
5. **Kept from `sfn26`** (not camera layer, not recorder): `publish` with no `overwrite`,
   `signal.raise_signal` in the worker monitor, the timebase shape check, `ms_to_ns`, the frame-rate
   helpers of `camera_config.py` (our manager does not call them), the `skellycam.spec` changes for
   `cv2_enumerate_cameras` and `jaraco`, the server folder of `app-paths.ts`, exposure maximum -5 in
   the UI, the `hardware` marker, the logging fixture of the tests, `CITATIONS.md` and the
   `references.bib` keys of `usb_connection.py`.
6. **Ours, not `sfn26`:** `AGENTS.md`, `__main__.py`, `skellycam-ui/package-lock.json`, the
   router, the detection and the manager tests.
7. **Shutdown.** `CameraGroupManager` gets `close_camera_groups()` for `app.py` and `shutdown.py`.
8. **Removed with the dropped items:** the RECOMMEND task (`camera_group/tasks/`), its doc and test;
   the `sfn26` tests of its manager; the tests that import deleted modules
   (`test_camera_startup_failures`, `test_camera_startup_responsiveness`,
   `test_opencv_loop_measured_frame_rate`, `test_recording_timestamp_identity`,
   `test_timestamp_stamped_stages`, `test_rust_pixel_builder`).
9. **USB link.** `CameraDeviceInfo.usb_version`: `"USB 3"`, `"USB 2"`, `"USB 1"` or `None`. The UI
   does not show it.
10. **Start-failure explanation.** One warning item of kind `start_failure` in the apply response,
    also logged. A USB reset (Windows events, or a camera that a device list does not find) has
    its own text. The device list activates no camera; the USB links come from the detection before
    the start; `start stream`, `first frame` and `warm-up` give "no frames"; `open` gives "cannot
    open". Other stages give no item. The failure objects of section 12 do not change. The UI does
    not show apply warnings.
11. **Pause and stop.** `pause_all_groups` and `unpause_all_groups` called a method that did not
    exist; they are gone. No 409 for a state conflict. The translated docs get only the new methods,
    paths and anchors. The pause route of the port and its methods are gone again
    ([ADR-V8RS](V8RS-pause-freezes-the-ui-display-only.md)): the UI freezes its display through
    `setStreamPaused`, and the `paused` field of the group snapshot is gone (only the UI read it).
12. **Exposure restore.** The search reads the exposure with `set_controls({})` and sets it back on
    an exception, except after a hung control call. A hung set-back call ends the camera as hung.
    Limit: the OpenCV source reports `auto` False until skellycam sets auto, so an OpenCV camera in
    auto mode goes back to MANUAL at its read value.
13. **Empty close.** `close_all_camera_groups` with no group keeps `closing` False (a `sfn26` test
    found it).
14. **Rust removal.** `camera_errors.py` goes (only Rust and the backend manager used it). The
    `imageio_ffmpeg` and `_sounddevice_data` collection of `skellycam.spec` goes: its comment ties it
    to the Rust recorder. `exclude = ["skellycam-ui*"]` stays.
15. **Commits.** While `skellycam-rust` was in `pyproject.toml`, the commit hooks ran with
    `UV_NO_SYNC=1`: the Rust build fails on the test machine.
16. **PR target.** Only `AGENTS.md` changes to upstream `development`. `TARGET_BRANCH` of
    `tools/check_decision_log.py` and the Rules of the index still name `development-streaming`.

## Reason

Each choice is the smallest change that keeps our camera layer and recorder, obeys
[ADR-EQY4](EQY4-base-the-work-on-upstream-sfn26-without-rust.md) and keeps the tests green.

## Open work

See [open-work.md](../open-work.md).
