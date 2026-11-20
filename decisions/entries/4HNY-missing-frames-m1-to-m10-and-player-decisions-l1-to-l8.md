# 4HNY — Missing frames M1 to M10 and player decisions L1 to L8

**Status:** accepted, 2026-11-19 (user; relayed by the supervisor after the first drafts of the recorder and player specs and their reviews; answers U1, U2 and U3 on 2026-11-20; commit to dom/player).

## Decision

The user decided these on 2026-11-19. Section 18 of [`specs/player.md`](../../specs/player.md) gives
each one in full. M1 to M10 are shared with the recorder spec of step 5a.

**Missing frames** (they replace the "row with no image" reading of R2, R3 and Y4 of
[ADR-J2BQ](J2BQ-phase-6-player-decisions-y1-to-y7.md)):

1. M1, M2: a missing frame (a damaged frame, or a dead camera whose process still runs) is a black
   placeholder JPEG block on its row, with the size and chroma layout of the camera's first frame, made
   once for each camera file. Each camera file has one block for each group frame, constant block times
   and equal block counts.
2. M3: the row has the new flag `missing`; the `# end` line gets `missing=`; the manifest counts the
   placeholder rows; the byte fields point at the placeholder; times and source frame number are kept
   for a damaged frame and empty for a dead camera; a row with no time has no player time.
3. M4, M6: two stated exceptions to "the stored bytes are the camera's bytes": the placeholder, and
   the DHT table that the ring inserted.
4. M5: the file of a killed or hung camera process is short. The main process completes its files
   only after the process has ended: its late `missing` rows have empty byte fields and no block, and
   the manifest says that the file is shorter. This is the one exception to "one block for each row"
   (U2 adds a write error as a second case of the same short pair).
5. M7: a take starts at the first group frame.
6. M8: a dead camera has the manifest warning `camera_dead` with `last_frame`; in the player, N of
   "camera lost at frame N" is the first group frame with no image.
7. M9: the player never shows a placeholder; it shows the last real image with "no frame".
8. M10: the shared Python reader needs no change; the interface notes say that a placeholder row is
   black and flagged `missing`.

**Player** (step 6a):

1. L1: a take folder in the new format opens in the new player; each other folder in the player of
   today. The rest of the switch is step 6c.
2. L2: 6a builds only the reader parts that the player needs; the full reader result and the
   conformance run come with 6c.
3. L3: three more tile marks: "camera file not readable: <reason>", "damaged at frame N", "read
   error"; the other tiles keep playing; damage is found from the timing file.
4. L4: the "may not be frame-perfect" warning is hidden in the new player; each tile shows the time of
   its own frame; pause moves to a whole frame, as today.
5. L5: no restructuring of the player of today; the new view uses today's controls component as it is.
6. L6: the shared tile runs on the main thread with `ImageDecoder`; step 4b measures 8 cameras at
   60 fps, a worker only if it misses its target; the tile also serves the live preview (no take
   reader, a frame rate text, the eight camera states, a flagged-frame mark that keeps the last image).
7. L7: the file handler opens a folder only inside the recordings folder or a folder that the user
   picked in the system folder dialog.
8. L8: Y2 stands; one shared check suite runs against both `TakeFiles` implementations.

**Answers of 2026-11-20** (relayed by the supervisor):

1. U1: a folder that the user picked in the system folder dialog is remembered across restarts. A
   page must not be able to add to the list without a dialog pick.
2. U2: a write error on one camera file is a second short-file case: the same short pair as a killed
   process (`missing` rows with empty byte fields and no block, `# repair`, `# end`), with the
   manifest warnings `camera_file_short` and `take_error`, and no `camera_dead`.
3. U3 (2026-11-20): `PlaybackControls` of today gets one optional prop that hides the "may not be
   frame-perfect" sync button. The player of today does not give it, so nothing changes there. The
   view of the new player gives it. No other change of the player of today (L5).

## Reason

The answers of the user to the questions of the first drafts and to their reviews.

## Evidence

`research/skellycam_recording/mkv_time_jumps/FINDINGS.md` and
`research/skellycam_recording/mkv_black_placeholder/FINDINGS.md` on branch `dom/research` (M1, M2,
M10, as the decision list cites them; this entry did not re-read them).

## Alternatives rejected

- A row with no image and no block for each missing frame (revision 1 of both specs): replaced by M1.
- "Pause keeps t" (revision 1 of the player spec, agent choice 21): rejected by L4.

## Open work

See [open-work.md](../open-work.md).
