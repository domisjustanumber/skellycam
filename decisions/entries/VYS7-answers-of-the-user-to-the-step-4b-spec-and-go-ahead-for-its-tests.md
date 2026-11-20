# VYS7 — Answers of the user to the nine questions of the step 4b spec; acceptance in principle and go-ahead for its tests

**Status:** accepted, 2026-11-20 (user).

## Decision

The user answered the questions Q1 to Q9 of section 12 of revision 2 of
[`specs/preview-4b.md`](../../specs/preview-4b.md) on 2026-11-20. Then he accepted the spec with
these answers, and gave the go-ahead for the failing tests of step 4b. The go-ahead is not for the
product code of step 4b.

1. **Q1, yes.** `TileLabel.frame` can be `null`. A tile shows its label and state with no frame
   part, before the first frame and for a failed camera.
2. **Q2, yes.** Merge `dom/native-jpeg` into `dom/preview` now, and `dom/player` before the first UI
   test commit. The 4b PR then also carries 3a and the 6a player, unless they land first.
3. **Q3, changed.** The user: "the intent of this is to show how fast the camera frames are being
   delivered to disk, the other is to show how fast the ui is updating." The accepted wording: two
   series for each camera, named for what they mean.
   - "Captured": the frames that the camera delivered to the server, measured where the frames
     enter the ring. During a take, this is what goes to disk. A problem of the recorder shows as a
     warning, not as a lower line.
   - "Displayed": the frames that the UI drew.
   - One colour for each camera, as the spec proposed.
4. **Q4, settled.** The fix F8 is in on the capture branch: the watch thread hands each close to
   the event loop. The question is removed. Part 1 of T-PRV-29 stays as the guard.
5. **Q5, changed.** The tile label is the list number and the name of the camera, as the camera
   list shows it (for example "Camera 6 · c922 Pro Stream Webcam"), not the hex camera id. This
   applies in the live view and in the player, in the same order as the camera list.
6. **Q6, yes.** The targets B-1a to B-3, and the rule of the worker: a worker only after B-1b, B-2
   or B-3 misses in the median of three runs, by a later spec.
7. **Q7, yes.** One tile for each camera in `cameras` of `app_state`, with no filter on `alive`.
   `connectedCameraIds` is the cameras in `checking`, `too_slow`, `ready` or `recording`.
8. **Q8, yes.** The new labels and the changed parts of the docs are in English only, until the
   translation process translates them.
9. **Q9, changed.** Test the UI with fake cameras at 30 fps with the full outside proof: the outside
   observer, which sees about 30 images each second, checks each picture. Test at 60 fps with the
   inside counts only: the ready messages that the server counts, and the draw count of the
   product.

## Reason

- The user, 2026-11-20. The rule "a spec and a test list before code": the failing tests of step 4b
  come next. The product code waits for a later go-ahead.
- Q3: the words of the user above.
- Q9: 30 fps is the frame rate of the cameras of the user, and his floor: "we will not be doing
  anything lower than 30fps".

## Consequences

- Revision 3 of the spec puts these answers into its body (section 12.1).
- Section 12.2 of the spec holds a note of the supervisor on the base branch. That note is not part
  of this entry.
- [ADR-EE0E](EE0E-step-4b-preview-spec-and-agent-choices.md),
  [ADR-R1TD](R1TD-revision-2-of-the-step-4b-preview-spec.md) and
  [ADR-W674](W674-choices-of-revision-3-of-the-step-4b-spec-and-its-test-list.md) hold the agent
  choices. Their status does not change here.

## Open work

See [open-work.md](../open-work.md).
