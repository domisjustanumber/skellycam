# AC5B — Choices of the third consistency check of the specs

**Status:** proposed, 2026-11-20 (supervisor and agent).

## Decision

A third check compared [`camera-requests.md`](../../specs/camera-requests.md) (A),
[`unix-capture.md`](../../specs/unix-capture.md) (B), [`certify.md`](../../specs/certify.md) (C),
[`windows-capture.md`](../../specs/windows-capture.md) (W) and
[`recorder.md`](../../specs/recorder.md) (R) with the code. These choices close its points. The specs
state each one in full.

Choices of the supervisor:

1. Stall watch (B 4.10, W 9.5): the shared `Value` `alive_count` of `CameraStatus`, which the main
   process creates. The shared loop adds one at each pass, so each source counts with no change; a
   push source may add too. The watch trips after 2 s with no change while the process is alive, in
   `waiting`, `adjusting`, `checking`, `too_slow` or `ready`; it is off in `starting` and during the
   close. The in-process rule of W 9.5 normally comes first; both give `stalled`. `delivered_count`
   goes.
2. Diagnostics (B 4.2 item 2, 4.6.1): not in `CameraStatus.info`. One message kind `diagnostics` each
   second on the channel of a take error (`TopicTypes.RECORDING_FINISHED`, read by
   `CameraGroup._take_finished`); the main process keeps the newest dict;
   `CameraGroup.diagnostics(camera_id)` and `CameraGroupManager.diagnostics()`; `serialize()` holds a
   counter subset only.
3. A code table for each raise site and each failure dict of the main process (B 4.6.3); the default
   is `open-failed` before streaming and `stream-error` after.
4. `camera_checks.json` is `{"format": 1, "rows": [...]}`; a missing or unreadable file is no rows,
   logged one time (C 2.5).
5. Exposure (A 1.3 to 1.7): the apply answers when each `AUTO` camera is `adjusting`, `ready`,
   `too_slow`, `failed` or `dead`; `same_config` ignores `exposure_found_at_fps`, `camera_index` and
   `camera_name`; the camera process owns `add_light`, `exposure_search_failed` and
   `no_manual_exposure`, the main process `rate_fallback` and `start_failure`, stored apart and
   joined in `serialize()`; a failed search sets the held value again, a closing camera gets no set,
   no `auto=True` but the restore at the close; `opencv_apply_config` sets no auto for `AUTO` on
   Windows; the main process keeps `exposure_search.count`; a fixed vocabulary of
   `exposure_search.reason`; the waits fit in `PARENT_WAIT_LIMIT_S`; the `MANUAL` clamp only for a
   time unit, and T-REQ-75 in step 7b; the sweep of C 5.2 ends at -5.
6. `paused` leaves the state; the removed route was `PUT /camera/group/all/pause`; T-REQ-48 checks
   that no pause route exists; the freeze stays `setStreamPaused`.
7. The second case of B7 (a failed check after a search at 60 fps) starts the fall back: F2 and Q10
   decide it. `rate_fallback` survives the reopen of the fall back.
8. The USB label is built in step 5 (L1); no lookup for a virtual camera; T-REQ-55 names 9 s;
   T-REQ-50, 51, 52, 54 extend `test_usb_connection.py`; `labelText` replaces `withCameraLabels`.
9. R 8.4: the "today" sentence, the order after 8.3, the field `ended_take_summary`, the state after
   a failed record start; the field design is proposed (item 16 of
   [ADR-FC1C](FC1C-choices-of-the-spec-integration.md)), only the behaviour is the user's.
10. `rate-high` has its own text; the slow-stop test gets `capture_timing`; the stale lines of W and C;
    an npm script `test:cameras` and a CI step.

Choices of the agent:

11. A wait of the loop in the recorder adds to `alive_count` at least each 0.5 s; a reopen sets
    `starting` before it closes the source; the search and the check run inside the passes. Else a
    slow disk or a slow close would trip the watch.
12. The kind `diagnostics` is a `RecordingFinishedMessage` with a new field `diagnostics`; the
    message is at most 32 KiB (the largest dict is about 14 kB); a larger dict is not sent and is
    logged one time.
13. The rows of the code table: a granted mode that differs (`media_foundation/source.py`) is
    `no-mode`; `end of stream` is `stream-error`; `_give_up` is `open-failed` at `open` and
    `not-ready` at `warm-up`.
14. An accepted request still stores its `camera_index` and `camera_name` (H6).
15. `count` is the `Value` `search_count` of `CameraStatus`; `reset_for_start` keeps it.
16. `reason`: `no-value-kept-rate` (it starts the fall back at 60 fps), `set-failed`,
    `readback-differs`, `timed-out`, `camera-closed`, each with a text.
17. The arrays `camera_warnings` and `group_warnings`; `start_failure` clears at the next apply of
    the user.
18. The `rate-high` text: `declared 30.00 fps, measured 31.42 fps. The camera delivers more frames
    than its mode rate`.
19. The clamp stays in the main process until step 7b, which moves it into the source.
20. On macOS the OpenCV source takes the Linux branch of `_apply_exposure`.
21. A record start refused before `start_take` returns keeps `ended_with_error`; a later failure
    gives `none`.
22. `test:cameras` runs `src/store/slices/**/*.test.ts` in the jobs of `player.yml`, whose triggers
    get the slices and A.
23. The sentence of W 16.2 on the two pause test files stays: both files still check the 404.
24. Step 5 UI: "Update Cameras" closes a group camera with no row; only it and Connect with no group
    close all to add a camera; Auto goes as `RECOMMEND` until the server Auto step; a take error shows
    while `ended_with_error`.

## Reason

Each choice makes a step buildable from the spec with no guess, with the smallest change to the code.

## Evidence

Code facts on `dom/integration`: `CameraStatus.info` and `update_info` (`camera_status.py`);
`CameraLoop._pass`, `_reopen`, `_recommend` (`camera_loop.py`); `CameraTakeWriter.give` and `end`
(`camera_writer.py`); `same_config`, `_take_finished`, `to_state` (`camera_group.py`); the clamp in
`create_or_update_camera_group`; `_apply_exposure` (`opencv_apply_config.py`); the pause tests of
`test_camera_control_contract.py` and `test_camera_router.py`.
