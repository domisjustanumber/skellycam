# JMS0 — Decisions of the user after the review of the connection

**Status:** accepted, 2026-11-20 (user).

## Decision

The user decided these items on 2026-11-20, after the independent review of the connection of the
take recorder to the shared loop:

- **A.** The frame count of a take is last frame number − first frame number (rows = last − first):
  the "+ 1" would invent a row. The spec text (`specs/recorder.md` 7.6 and the glossary) changes to
  this rule. The code is right.
- **B.** A take that an error ended is ended at once for all cameras; the next stop request returns
  the stored summary; a stop with no take answers 409 "No recording runs".
- **C.** Record start pauses the cameras for up to 10 s until each camera has started its writer,
  then unpauses.
- **D.** A record start that fails finishes the take folder at once with zero rows (manifest not
  left in state `recording`).
- **E.** The "no frame for 2 s" stall watch counts from the later of the last frame and the end of
  the last wait, for every capture source.
- **F.** The `camera_gap` warning in the manifest gets a detail: the row number and the two source
  frame numbers.
- **G.** The 100 ms hang promise (U16) stays as it is and is tested in the hang test of the new
  recorder.
- **H.** Exposure search (`_recommend` in `skellycam/core/camera/capture/camera_loop.py`, spec
  `windows-capture.md` 11.1): (1) the brightest value it tries is -5, not -4 (upstream sfn26 has
  `MAX_MANUAL_EXPOSURE = -5`; -4 gives about 16 fps on the Logitech cameras); (2) after it picks the
  value whose mean brightness is nearest the target, it goes one step darker (offset -1, clamped to
  the range), as the old helper `get_recommended_cv2_cap_exposure(offset_from_midrange=-1)` and sfn26
  do.
- **I.** The two upstream author-credit lines (line 1 of `skellycam-ui/src/hooks/floatingOnboarding.tsx`
  and of `skellycam-ui/src/hooks/useDraggableTooltips.tsx`) stay as upstream wrote them, and pass the
  private-data check through an allow-list with the reason "upstream author credit"
  ([ADR-PEJ0](PEJ0-scope-of-the-private-data-check.md)). Not done: the check has no allow-list form
  that does not copy the address. How (for example a path-and-line form of the check) is a question
  for the user.
- **J.** `skellycam/tests/reference_recordings/README.md` line 36: the absolute home folder path of an
  upstream developer changes to the words "the user's home folder".
- **K.** The secret scan gets three narrow allow-list rules for the classified false positives. The
  result is accepted only at zero hits in CI.
