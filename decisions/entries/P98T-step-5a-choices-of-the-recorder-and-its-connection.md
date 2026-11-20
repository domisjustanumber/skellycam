# P98T — Step 5a choices of the recorder and its connection to the shared loop

**Status:** accepted, 2026-11-20 (user: three rulings on review sheet 3 of 2026-11-20; the other
items accepted through the review sheets of 2026-11-20; commit to dom/integration).

## Decision

This entry supersedes [ADR-Q03C](Q03C-phase-5-step-5a-recorder-spec-and-test-list.md),
[ADR-QEQ8](QEQ8-python-api-of-the-recorder-as-the-5a-tests-assume-it.md),
[ADR-T24F](T24F-choices-of-the-5a-recorder-code.md),
[ADR-YNM2](YNM2-connection-of-the-take-recorder-to-the-shared-loop.md) and
[ADR-P5VE](P5VE-review-fix-choices.md). Each of their items is below. R is
[`recorder.md`](../../specs/recorder.md); "item n" is in R
[16](../../specs/recorder.md#16-choices-of-the-agent).

Ruled by the user:

- Q03C F-1 to F-10 (R [13](../../specs/recorder.md#13-proposed-format-changes-one-list-for-the-recorder-and-the-player)):
  one change request to skellyfileformat. The user sees its text first. Not sent
  ([open-work.md](../open-work.md)).
- [ADR-82AA](82AA-stop-last-frame-survivor-files-and-stuck-writer-limit.md) records items 1 to 3:
  no stop pauses (YNM2 11, P5VE 4 are stale), P5VE 7 and P5VE 10.
- P5VE 7: R [8.1](../../specs/recorder.md#81-order-of-the-steps) step 4.
- P5VE 10: a stop or an exit gives up on a writer after 15 s (`RECORDING_SAVE_LIMIT_S`) with no
  progress since the later of the wait start and the last progress, and logs an error.

Accepted through the review sheets, by link:

- Q03C 1 to 9, 11 to 30, 32 to 34: items 1 to 9, 11 to 30, 32 to 34. YNM2 1: item 11.
- T24F 5: R [5.6](../../specs/recorder.md#56-what-goes-to-disk-and-when). QEQ8 4, 5, T24F 25: R [4.2](../../specs/recorder.md#42-take-level-main-process). P5VE 6, QEQ8 9: R
  [4.3](../../specs/recorder.md#43-camera-level-camera-process). YNM2 10: R
  [8.2](../../specs/recorder.md#82-the-stop-response-r5). P5VE 9, T24F 17: R
  [6.6](../../specs/recorder.md#66-the-manifest).
- YNM2 4, 8, P5VE 8, 12: R
  [10](../../specs/recorder.md#10-connection-to-the-shared-loop-after-step-3a), items 10 and 13.
- QEQ8 12: [T-REC-35](../../skellycam/tests/take_recorder/test_queue_and_writer.py),
  [benchmarks](../../skellycam/tests/take_recorder/test_benchmarks.py),
  [600 kB](../../skellycam/tests/take_recorder/jpeg_tools.py),
  [T-REC-37](../../skellycam/tests/take_recorder/test_conformance.py). QEQ8 13: item 28, [adapter](../../skellycam/tests/take_recorder/sff_adapter.py). QEQ8 10:
  [fake disk](../../skellycam/tests/take_recorder/fake_disk.py).
- P5VE 18: [`check_private_data.py`](../../tools/check_private_data.py) (`ALLOWED_LINES`).

Accepted through the review sheets, as text:

- QEQ8 1: the package root exports the names of R 3 and R 4, with `JpegLayout` and
  `build_placeholder`; `stop_stats` has
  `stop_response_fields(csv_paths, *, recording_name, recording_path, frame_count)`.
- QEQ8 2: `TakeCamera` keywords: the fields of R 4.2, `os_name`, `vendor_id`, `product_id`, `backend`, `os_index`, `requested` (`width`, `height`, `framerate`, `capture_format`,
  `exposure_mode`; -1 or 0 gives `"camera_default"`) and `controls` (`exposure` in log2 s, `gain`,
  `focus`: `(value, auto)`); a refusal raises `ValueError`.
- QEQ8 3, 6 to 8, 11: `JpegLayout(width, height, factors)`;
  `Take.finish(..., dead_cameras={id: reason})` writes `camera_dead` only for them; stats `std` is the population value; `CameraTakeWriter(spec)`
  is not started, `start(spec, *, clock=None)` is, `writer.queue` is a `queue.Queue`; loggers under `skellycam.core.take_recorder`.
- T24F 1 to 10: a write error discards the queue to the end marker; a stalled wait counts; a short
  CSV or MKV write and a lost last block are write errors; an
  unparsable SOF is a damaged frame (one warning); rows with no layout at `end` get the
  4:2:2 placeholder; `end` logs the counts; a frame number that does not increase raises
  `ValueError`; `disk stall`: the writer closes the files and ends.
- T24F 11 to 16: `finish` completes each pair with no `# end` (repeatable); the walk
  maps the file and stops at an unknown size, a bad CRC or a bad child; no column line: an empty
  camera file, `blocks=0`; each camera alone; `last_frame` from the completed CSV; `camera_key` of
  `take_error` from `error_camera`, else the first error, else null.
- T24F 18 to 25: a manifest write keeps the fields of other tools, `files` sorted; one lock hold,
  retries for `EACCES`, `EAGAIN`, `EDEADLK` and a replace `PermissionError`; JSON indent 2, LF; no
  value is NaN; `stored_px` falls back to the mode size; control characters are `Cc`;
  `TakeCamera` checks nothing.
- YNM2 1 to 3, 5 to 9, 12 to 15: no frame is recorded when the first frame is -1; the SOF `layout`
  at the pause; `writer_progress_at`; the error texts; the `camera_dead` reasons "hang", "exit code
  `<n>`" or the failure; no camera in the gate: last frame = largest gate count; the start
  waits up to 10 s; 409 for a folder with files, 422 with the `ValueError` text; a stuck camera's
  flags before its end; the close stops only a set `take`; `TakeCamera` facts (30 for auto with no
  OpenCV rate); a new take lists its media size and folder time.
- P5VE 2, 3, 5, 11, 14, 15, 17: the recording flag of an ended process clears; the first take error
  goes to `finish`; `stop_recording` holds the end lock; in THREAD tests a held writer ends by the
  stop flag; the member and removed statuses; `RECOMMEND_MAX_EXPOSURE`, `RECOMMEND_OFFSET` in the loop, search at the open;
  three `.gitleaks.toml` tables, a machine folder is `[^/]+`.

Overturned: P5VE 1 by R
[8.4](../../specs/recorder.md#84-the-state-ended-with-an-error-added-on-2026-11-20); the
`recording` folder of YNM2 8, Q03C 32 and T24F 17 by D, E and F of
[ADR-JMS0](JMS0-review-decisions.md); `MANUAL` after `RECOMMEND` (YNM2 14) and the mode names
(P5VE 15) by G6 of [ADR-JK79](JK79-exposure-search-at-each-open-and-camera-requests.md).

Done: YNM2 16 to 18, P5VE 13. P5VE 16: no change (100 ms). Dropped as stale: Q03C
10, 31 (now C3, M5); YNM2 11, P5VE 4 (no stop pauses).

## Reason

The rulings of the user. The old entries hold the reasons.

## Open work

See [open-work.md](../open-work.md).
