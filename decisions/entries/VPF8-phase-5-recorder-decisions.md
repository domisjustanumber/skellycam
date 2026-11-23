# VPF8 — Phase 5 decisions R1 to R12: steps, dead and hung cameras, damaged frames, old files

**Status:** absorbed into
[`specs/recorder.md#18-decisions-of-the-user`](../../specs/recorder.md#18-decisions-of-the-user),
[`specs/recorder.md#14-edits-needed-in-specswindows-capturemd`](../../specs/recorder.md#14-edits-needed-in-specswindows-capturemd),
2026-11-23 (commit to dom/absorb-2; was accepted, 2026-11-19 (user; grilling of Q205 to Q216; commit to
dom/recorder)).

## Decision

The user decided R1 to R12 for phase 5 on 2026-11-19. In short (section 18 of
[`specs/recorder.md`](../../specs/recorder.md) gives each one in full):

1. **R1. Steps.** Four steps, in this order, each with tests first: 5a the video writer, the timing
   CSV, the manifest and the end of a take; 5d camera identity from the OS and the full capture info;
   5b Opus audio and the timestamp fit; 5c repair after a crash. Step 5a replaces the old recorder and
   removes the interim decode and the interim rules U4, U5 and U12 of
   [ADR-QKX1](QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md).
2. **R2. Dead camera.** The other cameras keep recording (D38). Every camera's CSV keeps the same
   number of rows: the dead camera gets a gap row for each remaining frame of the take. The manifest
   names the dead camera and its last real frame. This replaces U4 and the plan sentence "one camera
   fails mid-take: the whole take stops".
3. **R3. Damaged frame.** A frame with an error flag gets a gap row, and no image is stored. The last
   good image is not repeated (this removes U5). The damaged bytes are not kept. The count of gaps is
   in the end line of the CSV.
4. **R4. Hung camera.** The camera process ends at once after its report, with no attempt to finish
   the files (this removes U12). The main process completes that camera's files, with gap rows to the
   end of the take, as R2. Step 5a holds this part of the repair.
5. **R5. Old files.** No H.264 MP4, no 28-column timestamp CSVs, no multi-frame CSV, no statistics
   files, no WAV. The stop response of the HTTP API keeps its fields, computed from the new CSVs.
6. **R6. Format changes.** This work may propose changes to skellyfileformat where the recorder needs
   them, as local commits there, pushed only on the user's word. The first one is the rule for a dead
   camera's rows (SFF-754 has no rule for a dead camera).
7. **R7.** The old recording upgrade study is closed. Its evidence stays and is cited.
8. **R8. Names before 5d.** Each camera's files are named from today's `camera_id`, and the capture
   info marks that as provisional. Step 5d switches to the identity from the OS. A reader finds the
   files through the manifest.
9. **R9. Player gap.** The app's player cannot show new takes until the canvas player of phase 6; the
   user accepts that, on the condition that the player is built as its own parallel line.
10. **R10. Module.** Step 5a is a self-contained module with its own tests, on branch `dom/recorder`
    (off `dom/native-jpeg`), fed by synthetic JPEG frames, and joined to the camera loop only after
    step 3a is joined. Its input is the list of the ring spec: payload, `frame_number`, `arrival_ns`,
    `sample_ns`, `source_frame_number`, flags, delivered length, rotation.
11. **R11. Measurements.** On synthetic frames with no camera, step 5a runs T-REC-STALL, a kill with a
    full queue, the cost of an fsync once per second with 16 writers (SFF-788), and T-REC-GIL. They
    decide the queue of about 3 s and the stall limit of 10 s. The results go to the user before the
    numbers are fixed.
12. **R12.** The spec and the test list of step 5a come first, and the user accepts them before any
    code.

Decided earlier and not repeated here: the skellyfileformat format (draft v2), the writer design of
the plan (one writer thread per camera process, a bounded queue, a full queue slows capture, a stall
ends the take with an error, a write error finishes the files written), PyAV 19.0.2, recorder first,
read old formats and never write them, and Opus in fragmented MP4.

## Reason

- The user, 2026-11-19, grilling of Q205 to Q216.
- U4 and U5 "must change back once we have the new recorder"
  ([ADR-QKX1](QKX1-answers-of-the-user-to-the-phase-3-spec-questions.md)). R2 and R3 are that
  change: the files have equal lengths again.

## Consequences

- R2 and R3 need a format rule for the "gap row". The draft has none (R6). The later decisions M1 to
  M5 of [ADR-J3QP](J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md) give it: a
  black placeholder block on a row flagged `missing`.
- No audio is recorded between steps 5a and 5b (R5 with R1). C1 of ADR-J3QP refuses a start with a
  microphone.
- The decisions D9, D38 and D41 and the answers U4, U5 and U12 of phase 3 keep their text. R1 to R5
  replace their effect from the connection of step 5a.

## Open work

See [open-work.md](../open-work.md).
