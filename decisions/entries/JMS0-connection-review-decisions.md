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
- **H.** Exposure search (`_recommend` in `skellycam/core/camera/capture/camera_loop.py`, spec
  `windows-capture.md` 11.1): (1) the brightest value it tries is -5, not -4 (upstream sfn26 has
  `MAX_MANUAL_EXPOSURE = -5`; -4 gives about 16 fps on the Logitech cameras); (2) after it picks the
  value whose mean brightness is nearest the target, it goes one step darker (offset -1, clamped to
  the range), as the old helper `get_recommended_cv2_cap_exposure(offset_from_midrange=-1)` and sfn26
  do. When the search runs (at open) and the mode names do not change.
- **I.** Private-data check: the two upstream author-credit comment lines (line 1 of
  `skellycam-ui/src/hooks/floatingOnboarding.tsx` and of
  `skellycam-ui/src/hooks/useDraggableTooltips.tsx`) stay exactly as upstream wrote them. They go on
  the allow-list of the check with the reason "upstream author credit"
  ([ADR-PEJ0](PEJ0-scope-of-the-private-data-check.md)). The address is not copied into a new file,
  entry, commit message or report.
- **J.** `skellycam/tests/reference_recordings/README.md` line 36: the absolute home folder path of an
  upstream developer changes to the words "the user's home folder".
- **K.** Secret scan: the 14,551 gitleaks hits (rule `generic-api-key` only, all under `research/` in
  the history) are false positives. `.gitleaks.toml` gets three `[[allowlists]]` tables for that
  rule: the Windows camera key shape; the synthetic keys of the rig anchor self-test; the sample keys,
  codec paths and file hash of three research notes. A folder that is named after a machine is
  `[^/]+` in a path pattern.
