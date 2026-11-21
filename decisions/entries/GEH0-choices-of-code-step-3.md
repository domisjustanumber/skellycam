# GEH0 — Choices of code step 3 (auto exposure on Windows)

**Status:** proposed, 2026-11-20 (agent); items 9 and 12 to 21 changed on 2026-11-21 after the two reviews.

## Decision

Code step 3 builds part 1 of [`camera-requests.md`](../../specs/camera-requests.md) on the Media
Foundation source and the fake source. The spec does not make these choices. The agent made them:

1. The response of `POST /camera/group/exposure/auto` adds the list `not_streaming`: the named cameras
   that are not `ready`, `too_slow` or `checking` (1.9 says "the response names the others in its
   detail").
2. The camera process writes the result of a search into its status (key `held`, with the search
   count). The main process copies it into its config one time for each search. No config message goes
   on the queue of the apply after a search at an open.
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
   search keeps the mode `AUTO` and sets the old value and the old `exposure_found_at_fps` again (1.3 item
   6): `AUTO` is the stored mode (the ruling of the user, relayed by the review of 2026-11-21).
10. A camera that the group closes or unselects during its search has the reason `camera-closed`. A camera
    that fails or dies during its search has its failure code as the reason.
11. The main process writes `start_failure` into `group_warnings` of each camera that the item names.
12. The UI copies a held value only when the desired config and the server config are both `AUTO`. After
    the button, the UI sets each camera with a `done` search to `AUTO` first. The row uses the mode rate of
    the server for the `rate-high` text. "Search again" and the button are off while a camera is `starting`,
    `waiting` or `adjusting`.
13. Correction of fact, for the confirmation of the user: the search tries only the values of -12 to -5 in
    the exposure range that the source reads at the open (`exposure_range()`). The C922, the C930e and the
    Kiyo Pro have -11 to -2; the generic camera has -7 to 3. No value in the range: the new reason
    `no-value-in-range`. A held value outside the range opens at the nearest end of the range.
14. An apply and the endpoint get HTTP 409 also while a record start, a stop or an error end holds the lock
    of the take. The loop starts no search while the camera is paused or has a take writer.
15. A live change that waits in the queue lands before a requested search starts. During a search, a live
    change sets no state and starts no check.
16. Only the reply of the last set ends a search. The brightness comes from the checked bytes; a bad frame
    passes to the next frame. The limit of 20 s starts at the first set.
17. The endpoint waits at most `SEARCH_WAIT_LIMIT_S` (35 s). At that limit, it marks no camera `failed`
    whose process is alive and `adjusting`, and the reason of a camera that it gives up names this limit.
    "Apply again" clears `search_requested`.
18. Choice of the supervisor (2026-11-21): with no range (OpenCV, the default source of Windows), a value
    whose set fails or reads back different is skipped and listed in `skipped`; `no-value-in-range` only
    when no value could be set. With a range, such a set fails the search. A value off the step grid of
    `GetRange` is left out.
19. Each failed set of a search gives a reply, also an error that is not a `CaptureFailure`. The last set
    has a bounded wait (the limit of a bounded call and 1 s); then the search fails with `set-failed`.
20. A live change that lands during a search keeps its other fields; the search keeps its held fields. A
    reopen ends a search as `camera-closed`. A camera whose search is asked for refuses a changed config.
21. The two reader-kill tests of the frame ring give the killed reader its own `stop` Event and share
    `phase` with no lock: a process killed while it holds the lock of a shared Value or Event leaves it
    taken, and the run of 2026-11-21 hung on it.

## Reason

Each choice keeps the spec rules with the smallest change to the code of step 2. Items 2 and 3 keep
the queue of the apply free of a late config message, which a later apply could take as its answer.

## Not done in this step

The 60 fps fall back and `rate_fallback` (step 4): `CameraGroup.clear_group_warnings` must not run for
its reopen. The steps of a route with no time unit (step 7b). The tile text "Setting exposure…" over the
preview, the text of the OpenCV source of Linux and macOS in the settings, and the live change of gain of
T-REQ-68.

## Evidence

Item 13: `research/usb_cameras/docs/exposure_gain_tradeoff.md` 1.1 on branch `dom/research` (run
`suite_20261111T040003Z`).

Tests: `skellycam/tests/capture/test_camera_requests.py`, `skellycam/tests/capture/test_exposure_search.py`,
`skellycam-ui/src/store/slices/cameras/exposure-row.test.ts`.
