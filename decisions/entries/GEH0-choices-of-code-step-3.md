# GEH0 — Choices of code step 3 (auto exposure on Windows)

**Status:** proposed, 2026-11-20 (agent).

## Decision

Code step 3 builds part 1 of [`camera-requests.md`](../../specs/camera-requests.md) on the Media
Foundation source and the fake source. The spec does not make these choices. The agent made them:

1. The response of `POST /camera/group/exposure/auto` adds the list `not_streaming`: the named cameras
   that are not `ready`, `too_slow` or `checking` (1.9 says "the response names the others in its
   detail").
2. The camera process writes the result of a search into its status with the key `held` (the search
   count, `exposure_mode`, `exposure`, `exposure_found_at_fps`). The main process copies it into its config
   one time for each search: at the state route, at the websocket state, at each apply and at the end of
   the endpoint. No config message goes on the queue of the apply after a search at an open.
3. The endpoint asks for a search with the shared flag `CameraStatus.search_requested`. The camera
   process clears it after the search starts. A record start counts a camera with the flag as
   `adjusting`.
4. Each open reads the controls (`set_controls({})`) before the first set. A camera whose exposure is
   not present gets no exposure set (1.9).
5. The camera process writes `searches` into the status. The endpoint gives HTTP 422 from it (the OpenCV
   source of Linux and macOS). The button gives HTTP 422 only when no named camera can search.
6. The 409 of the endpoint applies when any selected camera of the group is `starting`, `waiting` or
   `adjusting`, also a camera that the body does not name.
7. A value whose rate is more than 3 % above the mode rate keeps the rate (only `is_slow` decides). The
   early decision always gives `kept_rate: false`.
8. When the last set of a search (the result) fails, the search fails with `set-failed` or
   `readback-differs`, and the camera sets the held value one more time.
9. A switch from `MANUAL` to `AUTO` answers with `AUTO` and the manual value as the held value. A failed
   search then sets `MANUAL` and its value again (1.3 item 6).
10. A camera that dies or closes during its search has `exposure_search.state` `failed` with the reason
    `camera-closed`.
11. The main process writes `start_failure` into `group_warnings` of each camera that the item names.
12. The UI copies a held value only when the desired config and the server config are both `AUTO`. After
    the button, the UI sets each camera with a `done` search to `AUTO` first. The row uses the desired
    frame rate as the mode rate for the `rate-high` text.

## Reason

Each choice keeps the spec rules with the smallest change to the code of step 2. Items 2 and 3 keep
the queue of the apply free of a late config message, which a later apply could take as its answer.

## Not done in this step

The 60 fps fall back and `rate_fallback` (step 4): `CameraGroup.clear_group_warnings` must not run for
its reopen. The steps of a route with no time unit (step 7b). The tile text "Setting exposure…" over the
preview, the text of the OpenCV source of Linux and macOS in the settings, and the live change of gain of
T-REQ-68.

## Evidence

Tests: `skellycam/tests/capture/test_camera_requests.py`, `skellycam/tests/capture/test_exposure_search.py`,
`skellycam-ui/src/store/slices/cameras/exposure-row.test.ts`.
