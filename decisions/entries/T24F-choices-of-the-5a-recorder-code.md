# T24F — Choices of the 5a recorder code

**Status:** proposed, 2026-11-20 (agent; commit to dom/recorder).

## Decision

The code of step 5a is in `skellycam/core/take_recorder/`. It follows
[`specs/recorder.md`](../../specs/recorder.md),
[ADR-Q03C](Q03C-phase-5-step-5a-recorder-spec-and-test-list.md) and
[ADR-QEQ8](QEQ8-python-api-of-the-recorder-as-the-5a-tests-assume-it.md). These texts do not fix
the choices below. An agent made them. The user decides them.

The camera level (`camera_writer.py`):

1. After a write error, the writer thread takes each item from the queue and discards it, until the
   end marker. Thus a `give` never waits after a write error. The next `give` raises
   `RecorderWriteError`.
2. A `give` wait that ends with `RecorderStalled` counts in `give_wait_count` and
   `give_wait_ms_max`.
3. A CSV `write` call that writes fewer bytes than the line is a write error (5.4).
4. When the writer does not find the last block after `container.close()` (6.3 item 3), it is a
   write error. The writer writes no last row and no `# end` line. The take level completes the
   pair (7.4).
5. The writer checks the fsync clock after each row write, also for the rows that `end` writes.
   Thus `end` can force the files to disk two times.
6. A good frame whose SOF does not parse: with no layout, the rows continue to wait (6.4); with a
   layout, it counts as a frame with another layout (one warning).
7. When `end` comes while rows wait for the layout, the writer uses the 4:2:2 placeholder of 6.4
   and logs its warning.
8. `end` logs one line with the counts of 5.2 (rows, `missing` rows, queue high-water, `give`
   waits, error).

The take level (`take.py`, `completion.py`, `folder_files.py`, `stop_stats.py`):

9. `finish` completes each pair whose sidecar has no `# end` line (7.4). Each completed pair gets
   `camera_file_short`.
10. The completion walk stops at an element of unknown size, at a Cluster with a wrong CRC-32 and
    at a child that does not parse. It keeps the blocks before that point. A cut EBML header cuts
    nothing. With no kept block, the cut is at the first Cluster. The completion forces both files
    to disk.
11. `last_frame` of `camera_dead` comes from the CSV after the completion, not from the result.
12. `camera_key` of `take_error` is the key of the camera whose result holds the error text, or
    null. A row count that is not the frame count (7.6) gives one more `take_error` with the key of
    that camera and the text `camera <camera_id>: <n> rows, expected <frame count>`.
13. `detail` of `camera_gap` is null.
14. A manifest write keeps, from the manifest on disk: each `files` item of another owner, each
    warning of another source, each `privacy` field of another file or field, `calibration`, each
    `calibration_camera`, and each member that the format does not name. `files` is sorted by
    `path` (UTF-8 bytes).
15. One hold of the lock covers the capture info write and the manifest write of `start_take` and
    of `finish`. After a lock timeout in `finish`, neither file is written.
16. JSON files have an indent of 2, characters that are not escaped and an LF at the end.
17. A statistic of the stop response with no value (for example, a take of one group frame) is
    NaN. `total_duration_sec` and `duration_s` are null when no row holds an `arrival_ns`.
18. `stored_px` is the mode size when the SOF of its block does not parse.
19. SFF-715: a control character is a character of the Unicode category `Cc`. The Windows device
    names are compared in upper case.
20. `TakeCamera` does no check. `start_take` makes each refusal.
21. `TakeSummary` has `stop_response`, `results` (the `CameraTakeResult` or `None` of each camera,
    as given) and `warnings` (the warnings that `finish` wrote).
22. `CameraTakeSpec` has `camera_id`, `mkv_path`, `csv_path`, `header` (the key and value pairs of
    6.5), `take_start_host_ns`, `num`, `den`, `width`, `height`, `layout`, `queue_size` and
    `stall_limit_s`.

## Reason

- Each choice is the smallest one that completes the spec with no data loss.
- 1: without it, a `give` after a write error waits for the stall limit, and the error looks like a
  disk stall.
- 3 and 4: no row points at a block that is not on disk (6.3).
- 10: a damaged Cluster or an unknown size cannot occur in a file of the pinned FFmpeg after a
  process kill. Step 5c walks such files when it repairs a take.
- 12: F-5 allows null when the camera is not known.

## Open work

See [open-work.md](../open-work.md).
