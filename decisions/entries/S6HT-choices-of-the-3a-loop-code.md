# S6HT — Choices of the 3a loop code

**Status:** proposed, 2026-11-19 (agent; waits for the user). Items 4, 6, 9, 12, 14, 17 and 19 corrected
on 2026-11-20 after the review of the 3a code ([ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md)).

## Decision

The product code of step 3a (all of the step except `skellycam/core/camera/capture/media_foundation/`)
follows [`specs/windows-capture.md`](../../specs/windows-capture.md) and
[ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md). The spec and HP7D do not fix
the items below. An agent chose them.

1. **Shared status.** `CameraStatus` keeps the state as an index in `state_index`. The camera process
   writes the failure, the mode, `measured_fps`, the controls and the source name as JSON in the
   shared array `info`. The main process writes the warning items in the shared array `warnings`.
   `recording` is `ready` with `recording_in_progress`. `replaced_count` is a shared integer.
2. **Join of the gate.** The gate holds each camera while a camera is `waiting` and no camera is
   `starting`. Thus the cameras that wait join the gate at the same time, with one gate count.
3. **One stop flag for each camera.** The shutdown flag of a camera worker is the `should_close` of
   its status, not the flag of the group. A camera process that fails, crashes or ends hard stops
   only that camera.
4. **Windows warning pipe.** The main process makes a named pipe for each camera process and puts
   its name in the environment variable `SKELLYCAM_STDERR_PIPE` while it starts the process.
   `skellycam/__init__.py` sets the pipe as the standard error handle of the child before OpenCV
   loads. The relay calls `_forward_lines` of the ring package, which reads UTF-8. T-RING-46 on
   Windows starts its child with this pipe.
5. **Apply response.** `/camera/group/apply` returns when each new or reopened camera is past its
   rate check or failed, so `camera_failures` holds a rate check failure. A live change returns when
   the camera has set and read back its controls.
6. **A camera that is not in the running group.** The apply request leaves it out, as before phase
   3. The whole-request check still includes it. A camera that was unselected starts again
   ([ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md) item 9).
7. **Mode choice.** `choose_mode` gives "no mode at 30 fps or more" when the requested size has modes
   but none at 29.97 fps or more.
8. **Relay.** A camera that is not `checking`, `too_slow`, `ready` or `recording` is left out.
9. **Files after a hang.** Replaced by [ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md) item 5:
   the files message is not lost. The main process stops to wait for the files message of a camera
   1 s after its process ended. Then the recording info names that camera in `dead_cameras` with
   `last_frame_number` null.
10. **Auto warning.** In 3a, only exposure gives the `auto_control` warning (gain and focus are set
    from 3c).
11. **Failed reads and live changes.** A periodic control read that fails without a hang gives a log
    warning, and the camera keeps running. A live change fails when the set raises, or when a camera
    in manual mode reads back another value. The forced auto exposure of Linux is not a failure.
12. **OpenCV source.** It reports exposure as present, and gain and focus as present when
    `cv2.VideoCapture.get` does not read -1 ([ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md) item 7). Its `retrieve_ns` attribute gives the retrieve stamps of the timing file.
    The Windows device is found by `directshow_index` in `create_cv2_video_capture`.
13. **Mixed-rate text for other rates.** For two rates that are not one rate class (OpenCV after the
    open), the text says "skips about N frames per second".
14. **Phase 2 loop.** `opencv/opencv_camera_loop.py` and its helpers stay, because the frame ring
    tests and the reference recording tests call them (W8 of
    [ADR-PDD3](PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md) waits for them;
    [ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md) item 12). No camera process uses them. A status with no
    state (the phase 2 loop sets none) keeps the phase 2 rules of the gate, the pause and `ready`, and
    the record start does not check it. `await_extracted_configs` stays for its tests, and it stops at
    the first reported failure, because a failure no longer sets the shutdown flag.
15. **A new source for each open.** The loop calls the source factory at each open, also at a
    reopen (`FakeSourceFactory` gives a new `FakeSource` for each call).
16. **`waiting` without rings.** A camera in `waiting` reads no frame until its rings are attached.
    The main process makes the rings at once. Then it reads frames, with the stall watch, until it
    joins the gate.
17. **Log level of a failure.** The camera process logs its failure line at WARNING, as the spec
    says for a dead camera. T-CAP-11 counts each line at WARNING that names the camera, up to the
    stall after its frame 200.
18. **Recorder rate.** When the rate is "auto" (-1 or 0) or unknown, the old recorder writes the
    video at 30 fps.
19. **End order.** Replaced by [ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md) item 4.

## Reason

- Each item is the smallest choice that the tests and the spec need.
- Items 1 and 3 work for THREAD and PROCESS workers with no new message type.
- Item 2: T-CAP-05 needs equal ring frame counts. A camera that joined first would take frames alone.
- Item 4: a probe on the development machine showed that the libjpeg warnings follow
  `SetStdHandle` only when it runs before OpenCV loads.

## Alternatives rejected

- A redirect of descriptor 2 after the start: the OpenCV runtime keeps its own handle ([ADR-E817](E817-choices-of-the-2b-code.md)).
- A state message from each camera process to the main process: a second channel for the same data.

## Open work

See [open-work.md](../open-work.md).
