# JMS0 — Decisions of the user after the review of the connection

**Status:** accepted, 2026-11-20 (user).

## Decision

The user decided these items on 2026-11-20, after the independent review of the connection of the
take recorder to the shared loop:

- **A.** Spec `specs/recorder.md` 7.6 and the glossary: the frame count of a take is last frame
  number − first frame number (rows = last − first). Remove the "+ 1"; update 8.1 and 8.2 where
  they repeat it. The code is right.
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
