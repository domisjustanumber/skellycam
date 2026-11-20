# C4FZ — Exposure modes and search, one frame rate, USB link label

**Status:** accepted, 2026-11-20 (user, relayed by the supervisor).

## Decision

The user decided these points on 2026-11-20. The quoted text is the text of the user.
[`specs/camera-requests.md`](../../specs/camera-requests.md) cites them as [E1] to [E9], [F1] to
[F4] and [L1] to [L5].

Exposure:

- **E1.** The UI and the API have two modes only: Manual and Auto. "I never want to allow the camera
  to set it's own exposure, other than initial startup to pick a reasonable point - I always want
  auto to mean skellycam controls exposure." The auto exposure of the camera is never a mode that a
  user can select. The sfn26 label "Recommend" and the sfn26 "Auto" (the camera controls exposure)
  go away.
- **E2.** Auto is the exposure search of SkellyCam. It "must replicate the sfn26 implementation with
  the added guard of monitoring the frame rate and flagging if a reasonable exposure can't be reached
  without the frame rate dropping, then an "Add light" message."
- **E3.** "one shot, regardless of what upstream does, and keep the stream open while the change
  happens. Changing exposure during a take may change a frame rate so is to be avoided." The search
  runs on the open stream, with no reopen. It runs one time when the user asks. It ends with a manual
  value that SkellyCam holds. It never runs during a take: such a request is refused.
- **E4.** One button "Auto-set exposure (all cameras)", plus the mode of each camera.
- **E5.** The default for a new camera stays Manual -7.
- **E6.** The search tries the values -12 to -5. It takes the value whose mean brightness is nearest
  to mid-grey, then one step darker, as sfn26 and the old helper. When the search fails, it sets the
  old settings again.
- **E7.** While the search runs, it measures the delivered frame rate at each value. It never keeps a
  value at which the rate falls below the rate of the group, with the rate tolerance of 3 % of
  today. When the brightest allowed value is still too dark, the row of the camera says "Add light".
  The rate-check failure text of a camera, "Add light, or set the exposure to manual", is replaced by
  a text that fits the two modes.
- **E8.** The search measures the rate at each value. It does not assume that a shorter exposure is
  always faster.
- **E9.** While a camera searches, the other cameras keep streaming, and the gate still waits for
  each camera.

One frame rate:

- **F1.** "one frame rate choice for all cameras at the top of the stack" (the camera list).
- **F2.** It offers 60 fps only when each ticked camera passed a real 60 fps rate check. Else it
  stays at 30 fps and says which camera could not.
- **F3.** Nothing below 30 fps is ever offered.
- **F4.** A change of the frame rate during a take is refused.

USB link label:

- **L1.** A label USB 2 / USB 3 next to each camera in the camera list.
- **L2.** It shows the speed at which the camera is connected now. A USB 3 camera in a USB 2 port
  shows USB 2.
- **L3.** The value is a new field of the detection result.
- **L4.** Each operating system has a test.
- **L5.** Later, not now: a click opens a diagram of the cameras on their USB controllers.

## Reason

E3: "Changing exposure during a take may change a frame rate so is to be avoided."

## Open work

See [open-work.md](../open-work.md).
