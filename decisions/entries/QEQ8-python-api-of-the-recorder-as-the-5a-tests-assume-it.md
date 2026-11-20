# QEQ8 — Python API of the recorder, as the 5a tests assume it

**Status:** superseded by [P98T](P98T-step-5a-choices-of-the-recorder-and-its-connection.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent; commit to dom/recorder)).

## Decision

[ADR-Z3Y7](Z3Y7-acceptance-of-the-step-5a-recorder-spec-and-test-list.md) accepts
[`specs/recorder.md`](../../specs/recorder.md). The spec does not fix each Python name. The failing
tests of step 5a in `skellycam/tests/take_recorder/` use the names below. An agent chose them. The
user decides them.

1. The package root `skellycam.core.take_recorder` exports `RecorderFrame`, `TakeCamera`,
   `JpegLayout`, `parse_sof`, `build_placeholder`, `start_take`, `Take`, `CameraTakeSpec`,
   `TakeSummary`, `CameraTakeWriter`, `CameraTakeResult`, `RecorderStalled` and
   `RecorderWriteError`. The module `skellycam.core.take_recorder.stop_stats` has
   `stop_response_fields(csv_paths, *, recording_name, recording_path, frame_count) -> dict`.
2. `TakeCamera` takes these keywords: `camera_id`, `nominal_rate` (a tuple `(num, den)`), `width`,
   `height`, `rotation_cw_deg`, `capture_format` (`"MJPG"`, `"YUYV"` or `"H264"`), `layout` (a
   `JpegLayout` or `None`), `os_name`, `vendor_id`, `product_id`, `backend`, `os_index`, `requested`
   and `controls`. `requested` is a dict with `width`, `height`, `framerate` (the requested number;
   -1 or 0 gives `"camera_default"` in the capture info), `capture_format` and `exposure_mode`.
   `controls` is a dict with the keys `exposure` (the log2 value of skellycam, in seconds), `gain`
   and `focus`, each a tuple `(value, auto)`. A refusal can come from the `TakeCamera` constructor
   or from `start_take`; both raise `ValueError`.
3. `JpegLayout(width, height, factors)`: `factors` is a tuple of `(h, v)` for each component, in SOF
   order. `parse_sof(payload) -> JpegLayout`. `build_placeholder(layout) -> bytes`.
4. The `clock` of `start_take` is a pair of callables: the host clock, then the UTC clock.
5. `CameraTakeSpec.queue_size` is the queue size in items. `CameraTakeSpec` pickles.
6. `Take.finish(results, *, frame_count, ended_by_error=None, dead_cameras=None)`. `results` is a
   list in the order of the cameras. `dead_cameras` is a dict `{camera_id: reason}` of each camera
   that stopped during the take (7.3, 7.4, 5.3). `finish` writes `camera_dead` with the detail
   `last_frame=<p> reason=<reason>` only for these cameras (F-5). The spec gives `finish` no input
   that names a dead camera or its reason. This keyword fills that gap.
7. `TakeSummary.stop_response` is a dict with the ten fields of `StopRecordingResponse`. Each stats
   field is a dict with `median`, `mean`, `std` (the population deviation, as `np.nanstd` today),
   `min` and `max`. `stop_response_fields` returns the same dict.
8. `CameraTakeWriter(spec)` makes a writer that is not started (the "before `start`" case of
   T-REC-32). `CameraTakeWriter.start(spec, *, clock=None)` makes and starts one. `clock` returns
   the time in ns for the fsync schedule; the default is `time.perf_counter_ns`.
   `writer.queue` is the `queue.Queue` of 5.1. Its items are the `RecorderFrame` objects given, or
   objects whose `payload` is the same `bytes` object.
9. `CameraTakeResult` takes the fields of 4.3 as keywords.
10. The product opens each file with the built-in `open`, and calls `os.fsync`, `os.replace`,
    `os.truncate` or the `truncate` method of the file, and `msvcrt.locking` or `fcntl.flock` as
    attributes of their modules. The fake disk and the file-action spy of the tests replace these
    names. The product needs no other test seam.
11. The product logs through loggers whose names start with `skellycam.core.take_recorder`
    (`logging.getLogger(__name__)`). T-REC-35 counts one warning; T-REC-16 finds an error.
12. The test interpretations, where the spec text leaves a choice:
    - T-REC-35 case 1 checks rows 0 and 1 before frame 3 is given. By 6.3 row 2 waits for block 3.
    - The short CI form of T-REC-STALL scales the stalls by 10 with the queue and the stall limit:
      stalls of 0.05 s and 1.5 s, a queue of 0.3 s, a limit of 1.0 s, two camera processes at
      720p30 for 6 s, the stall at frame 30.
    - The short form of T-REC-KILL is 5 kills at 720p30 during normal writing. `SKELLYCAM_BENCH=1`
      gives the 20 + 20 kills of each case.
    - `SKELLYCAM_BENCH_OUT` is a folder. Each benchmark writes `<name>.json` in it.
    - T-REC-36 pads synthetic JPEGs after EOI to 600 kB (SFF-738).
    - T-REC-37 exports the pinned commit with `git archive` from `../skellyfileformat` or from
      `SKELLYFILEFORMAT_DIR`. It does not change that checkout. The CI jobs check out the
      repository at the pinned commit into `.skellyfileformat`; when that step fails, T-REC-37 is
      skipped with its reason.
13. The test adapter `sff_adapter.py` (agent 28): `camera_id` is `device.os_index` as 4 lowercase
    hexadecimal characters; `take_start_host_ns` is the value that the host clock of `start_take`
    returned; `trace` comes from the file-action spy; audio, a conversion run, a raw YUYV frame and
    `add_warning` raise `NotImplementedError`.

## Reason

- R12: the tests come before the code. The tests need names to call.
- Each name is the smallest one that the spec text and the tests need.

## Open work

See [open-work.md](../open-work.md).
