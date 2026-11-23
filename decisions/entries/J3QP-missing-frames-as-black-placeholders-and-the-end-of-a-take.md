# J3QP — Missing frames as black placeholders (M1 to M10) and the end of a take (C1 to C7)

**Status:** absorbed into
[`specs/recorder.md#18-decisions-of-the-user`](../../specs/recorder.md#18-decisions-of-the-user),
2026-11-23 (commit to dom/absorb-2; was accepted, 2026-11-19 (user; relayed after the first spec drafts and
their reviews; commit to dom/recorder; the second case of M5 added 2026-11-20 by the user)).

## Decision

The user decided these on 2026-11-19, after the first draft of
[`specs/recorder.md`](../../specs/recorder.md) and its independent review. Section 18 of the spec
gives each one in full. M1 to M5 replace the "row with no image" reading of R2, R3 and R4 of
[ADR-VPF8](VPF8-phase-5-recorder-decisions.md). The player decisions of the same day belong to the
player spec and are not in this entry.

1. **M1.** A missing frame (a damaged frame, or each frame of a dead camera whose process still runs)
   is a black placeholder JPEG block on its row. Each camera file has one block for each group
   frame, block times with no jump, and equal block counts.
2. **M2.** The placeholder has the width, height and sampling factors of the camera's first frame
   (its SOF), is made once for each camera file, with optimised Huffman tables.
3. **M3.** Its row has a new flag `missing`; `gap` keeps its format meaning. The end line gets a
   `missing=` count at a place that SFF-745 allows. The manifest gives the count for each camera. The
   byte fields point at the placeholder. Times and source frame number are kept for a damaged frame
   and empty for a dead camera. A row with no time has no player time.
4. **M4.** "The stored bytes are the camera's bytes" gets two exceptions: the placeholder (M1) and the
   inserted DHT (M6).
5. **M5.** A killed or hung camera process leaves a short video file. The main process completes its
   timing rows (`missing`, no block) only after the process has ended. The manifest says that the
   file is shorter than the rows. Step 5c may fill it later. This is the one exception to "one block
   for each row". **Second case (user, 2026-11-20, answer to Q1 of the second spec draft):** a write
   error on one file gives that camera a short pair (rows to the frame count, the MKV cut after its
   last block with a row, `missing` rows with no block, `# repair`, `# end`), with the warnings
   `camera_file_short` and `take_error` and no `camera_dead`. The camera stays `ready`. The other
   cameras get normal finished pairs. A full disk leaves the take unfinished (`state` `recording`).
6. **M6.** The recorder stores the JPEG with the DHT that the ring inserted.
7. **M7.** A take starts at the first group frame; the first block is never smaller than the camera
   frames.
8. **M8.** A dead camera gets the manifest warning `camera_dead` with `last_frame`. The player shows
   "camera lost at frame N", N the first group frame with no image.
9. **M9.** The player never shows the placeholder as a picture; it shows the last real image with
   the "no frame" mark. Other programs see black.
10. **M10.** `SequentialVideoReader` needs no change. The interface notes for freemocap and
    skellytracker state the placeholder, its flag and the short-file exception.
11. **C1.** A record start with a microphone gets HTTP 422 until step 5b.
12. **C2.** The program that records a take may complete that take's files without asking, and marks
    a completed file `repaired` (a new format rule; no fit lines until 5b).
13. **C3.** Until 5d, `camera_key` = `camera_id` + 12 hexadecimal characters of its SHA-256, marked
    `"provisional"`.
14. **C4.** CI runs the 5a tests on Windows, Linux and macOS on each push to the recorder branch.
15. **C5.** A disk stall or a write error on one camera's file ends the take for all cameras, with a
    clear error.
16. **C6.** Only a camera whose writer is stuck past the limit has its process ended; it becomes
    `failed` with the reason "disk stall". A plain write error returns normally, and the camera stays
    `ready`. The limit counts from the moment that the camera was told to end, plus a margin.
17. **C7.** Today's playback list shows new-format takes with the mark "needs the new player"; they
    are not playable there and not hidden.

## Reason

- The user, 2026-11-19, after the first drafts and their reviews.
- Missing blocks make OpenCV and Blender give wrong frames or counts; placeholders of the camera's
  size and layout are exact in each tool tested (Evidence).

## Evidence

- skellycam `dom/research`: `research/skellycam_recording/mkv_time_jumps/FINDINGS.md` and
  `research/skellycam_recording/mkv_black_placeholder/FINDINGS.md` (synthetic frames; PyAV 19.0.2,
  OpenCV 5.1.0, Blender 5.2.3 LTS, Windows 11).

## Open work

See [open-work.md](../open-work.md).
