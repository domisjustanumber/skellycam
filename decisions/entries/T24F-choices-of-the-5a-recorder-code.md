# T24F — Choices of the 5a recorder code

**Status:** superseded by [P98T](P98T-step-5a-choices-of-the-recorder-and-its-connection.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent; commit to dom/recorder; revised the same day after an independent review)).

## Decision

The code in `skellycam/core/take_recorder/` follows [`specs/recorder.md`](../../specs/recorder.md),
[ADR-Q03C](Q03C-phase-5-step-5a-recorder-spec-and-test-list.md) and
[ADR-QEQ8](QEQ8-python-api-of-the-recorder-as-the-5a-tests-assume-it.md). An agent made these
choices, which those texts do not fix. The user decides them.

Camera level:

1. After a write error, the writer thread discards each queued item until the end marker. The next
   `give` raises `RecorderWriteError` and never waits.
2. A `give` wait that ends with `RecorderStalled` counts in the wait counts of 5.2.
3. A short CSV write is a write error. PyAV writes the MKV through a wrapper that writes each byte
   or raises (FFmpeg ignores a short count).
4. The last block not found after the close is a write error: no last row, no `# end` line.
5. The fsync clock is checked after each row write, also in `end`.
6. A good frame whose SOF does not parse is stored as a damaged frame (7.2), with one log warning.
   With no layout it does not end the wait of 6.4. `parse_sof` refuses a short SOF segment, a size
   of 0, no component and a factor outside 1 to 4.
7. Rows that wait for the layout at `end` get the 4:2:2 placeholder and its warning.
8. `end` logs the counts of 5.2.
9. `give` raises ValueError, and queues nothing, when `frame_number` does not increase (4.1).
10. When `end` returns `disk stall`, the writer thread closes both files after its current item
    and ends (no padding, no `# end` line), so that the process can end.

Take level:

11. `finish` completes each pair with no `# end` line, and gives it `camera_file_short`. A pair
    with `# repair` and `# end` lines (an earlier `finish`) is not changed and gets
    `camera_file_short` again.
12. The completion maps the camera file into memory. Its walk stops at an element of unknown size,
    a wrong Cluster CRC-32 or a child that does not parse. A cut EBML header cuts nothing. With no
    kept block, the cut is at the first Cluster. Both files are forced to disk.
13. A CSV with no complete column line, or none: the process ended in `start` and wrote no block.
    The camera file is replaced by one with no block; the CSV is written again from the header of
    `camera_spec`, with `missing` rows, `# repair cut_bytes=<old size> media_cut_bytes=0` and
    `# end`; `camera_file_short` has `blocks=0`.
14. Each camera is completed and read on its own. A fault is logged and gives `take_error` for that
    camera; the other cameras, the manifest and the stop response are still done.
15. `last_frame` of `camera_dead` comes from the CSV after the completion.
16. `camera_key` of `take_error`: the camera of the new `finish` keyword `error_camera`, else the
    first camera whose result holds an error, else null. A wrong row count (7.6) adds a
    `take_error` for that camera.
17. `detail` of `camera_gap` is null.
18. A manifest write keeps the `files` items, warnings and `privacy` fields of others,
    `calibration`, each `calibration_camera`, `summary.calibration`, `summary.processing_runs`
    and unknown members. `files` is sorted by `path`.
19. One lock hold covers the capture info and the manifest. The lock is tried again only for
    `EACCES`, `EAGAIN` and `EDEADLK`. A replace that fails with `PermissionError` (a reader holds
    the file on Windows) is tried again every 50 ms up to `lock_timeout_s`, then its `.tmp` file
    is removed. Any `OSError` there leaves the manifest `recording`; `finish` logs it and still
    gives the stop response.
20. JSON: indent 2, characters not escaped, LF at the end.
21. A stop statistic with no value is NaN, also `total_duration_sec` (the response model accepts
    it; the summary `duration_s` is null). A pair whose time does not increase is left out. A fault
    of the statistics is logged and gives NaN.
22. `stored_px` is the mode size when its SOF does not parse.
23. SFF-715: a control character is Unicode category `Cc`; device names are compared in upper case.
24. `TakeCamera` checks nothing; `start_take` refuses.
25. `TakeSummary`: `stop_response`, `results`, `warnings`. `CameraTakeSpec`: the paths, the header
    pairs, the take start, the rate, the size, the layout, the queue size and the stall limit.

Rejected from the review: one CSV `write` for the whole header. Spec 6.5 and T-REC-13 require one
`write` for each line; item 13 covers a kill during the header.

The user decided the questions of the review on 2026-11-20
([ADR-C6DE](C6DE-stall-as-no-progress-limits-and-no-fat-disk.md)): a stall is no progress (D1), the
two limits stay as starting values (D2), no FAT disk (D3).

## Reason

- Each choice is the smallest one that completes the spec with no data loss.
- 3, 4: no row points at bytes that are not its block (6.3). 6: a block that no decoder reads
  breaks the readers.
- 10: a non-daemon thread that waits for ever keeps the process alive.
- 12: one hour of 1080p60 is tens of GB. 14, 19, 21: the stop request must give its response;
  step 5c repairs a take that stays `recording`.

## Open work

See [open-work.md](../open-work.md).
