# 6EKB — Choices of the fixes of the review of the 3a code

**Status:** proposed, 2026-11-20 (agent; waits for the user).

## Decision

The fixes of the review of the step 3a code follow
[`specs/windows-capture.md`](../../specs/windows-capture.md),
[ADR-HP7D](HP7D-python-api-of-capture-as-the-3a-tests-assume-it.md) and the decisions W1 to W8 of
[ADR-PDD3](PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md). Section 18 of the
spec lists these choices as items 79 to 90. An agent made them.

1. **Detection in the apply request (79).** When the kept detection result does not hold each
   selected camera of a request, the apply request runs the detection first. Thus the 422 for a
   virtual camera (W5) and the mode checks of 7.5 hold also with no earlier `/camera/detect`.
2. **`modes_read` (80).** `CameraDeviceInfo` gets `modes_read: bool = False`. Detection sets it when
   it read the native mode list. A camera with `modes_read` and an empty `supported_modes` has no
   mode at the floor, and the whole-request check refuses it with 422 "no mode at 30 fps or more"
   (7.5). For this case the spec wins over item 2 of ADR-HP7D, by decision of the user.
3. **A camera process that ends with no final state (81).** The main process sets `failed`, stage
   `open`, when the camera was `starting`, and `dead`, stage `streaming`, in each other state. The
   reason is "camera process ended (exit code N)". The watch thread of the group and the waits of
   the apply request set it.
4. **End of a camera that fails or dies (82).** A started camera is `dead` at once in the failure
   report, so that it leaves the gate. Then the camera process finishes its files, stops the control
   thread and closes the source (8.2). A camera that fails at start is `failed` after its close.
   This replaces item 19 of [ADR-S6HT](S6HT-choices-of-the-3a-loop-code.md).
5. **Files message after a hang (83).** The watch thread of the main process takes each files
   message from its queue at once. The hard end closes that queue and waits for its feeder thread,
   within the 5 s of U12. Only one thread of the camera process runs the hard end. This replaces item
   9 of ADR-S6HT.
6. **Apply again (84).** The main process waits 10 s for the old camera process, then kills it.
7. **OpenCV source (85).** One lock around `grab` with `retrieve` and around `set_controls`. Gain or
   focus is absent (`present: false`) when `cv2.VideoCapture.get` reads -1 [NV for each backend].
8. **Failed control reads (86).** One WARNING for each run of failed periodic reads, then DEBUG
   until a read passes.
9. **Unselect and select again (87).** An unselected camera keeps its status, because the other
   camera processes keep it. A request that selects it again starts a new camera process with that
   status. Another camera that is not in the running group is still left out. The whole-request
   check uses the current config of each camera of the group that the request does not name.
10. **Early decision of 10.2 (88).** Only a frame that did not come decides `too_slow`: a read that
    gives no frame by the deadline, or a taken frame that arrived after the deadline and is not yet
    frame s_a + 59. A frame that waits at the gate or in a pause gives no decision.
11. **Paused loop (89).** A paused camera sleeps 50 ms between its passes.
12. **The phase 2 loop (90).** W8 deletes it with T-RING-31. T-RING-31 is deleted. The loop and the
    `state is None` rules stay: T-RING-23 (two tests), T-RING-38, T-RING-39, T-RING-40, T-RING-47,
    five tests of `skellycam/tests/reference_recordings/` and `test_camera_startup_failure.py` also
    call it or its helpers. The user decides these tests first.

The review finding about the stall watch at the gate (9.5) has no change: the waiting place keeps the
newest delivered frame, so the first read after a gate wait gives a frame, and a true stall shows at
that read.

## Reason

- Each choice is the smallest change that fixes a finding of the review and agrees with the spec.
- Items 1 and 2: the main process cannot know a virtual camera or a camera with no mode at the floor
  without detection data.
- Item 5: a large files message waits in the feeder thread until the main process reads it, and
  `os._exit` drops it.
- Item 12: a deletion of the loop breaks tests that this task must not change.

## Alternatives rejected

- Item 1: refuse a virtual camera at the open. The camera would be `failed`, not refused with 422.
- Item 2: keep the modes below the floor in `supported_modes`. That breaks the shape of 7.3.

## Open work

See [open-work.md](../open-work.md).
