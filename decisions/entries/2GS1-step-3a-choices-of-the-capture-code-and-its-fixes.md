# 2GS1 — Step 3a choices of the capture code and its fixes

**Status:** accepted, 2026-11-20 (user: two rulings on review sheet 1 of 2026-11-20; the other items
accepted through the review sheets of 2026-11-20; commit to dom/integration).

## Decision

This entry supersedes [ADR-S6HT](S6HT-choices-of-the-3a-loop-code.md),
[ADR-MA22](MA22-choices-of-the-media-foundation-source-of-step-3a.md),
[ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md),
[ADR-037V](037V-completion-of-w8-the-phase-2-loop-and-its-tests.md),
[ADR-BM73](BM73-fixes-of-the-first-ci-run-of-the-capture-workflow.md),
[ADR-R60B](R60B-fixes-of-the-first-hardware-run-of-step-3a.md) and
[ADR-FTC3](FTC3-fixes-of-the-second-capture-ci-run-and-the-first-hardware-run.md). Each of their
items is below. W is [`windows-capture.md`](../../specs/windows-capture.md).

Ruled by the user:

- FTC3 6: a camera is virtual also by its device link. W
  [7.1](../../specs/windows-capture.md#71-detection-on-windows-d11) states it.
- BM73 7: T-CAP-40 and T-CAP-82 (100 ms gaps) have the marker `capture_timing`. The macOS job runs
  them in a separate step. The 100 ms rule stays. The line "The three jobs run the same selection"
  of W [15](../../specs/windows-capture.md#15-ci-d47) must change ([open-work.md](../open-work.md)).

Accepted through the review sheets, by a link to the heading that states it:

- 6EKB 1 to 11: W [18](../../specs/windows-capture.md#18-choices-of-the-agent), items 79 to 89.
- MA22 1, 9: W 7.1, [7.2](../../specs/windows-capture.md#72-camera_id-d11). S6HT 7: W
  [7.5](../../specs/windows-capture.md#75-mode-choice-auto-rate-group-rate). S6HT 8: W
  [5.8](../../specs/windows-capture.md#58-the-interim-preview-relay-until-phase-4-u13); the relay
  leaves out each camera that is not `checking`, `too_slow`, `ready` or `recording`.
- BM73 8: [`preview-4b.md` 4.3](../../specs/preview-4b.md#43-the-ring-reader-close-on-the-event-loop-q4).

Accepted through the review sheets, as text:

- S6HT 1: `CameraStatus` has `state_index`, the shared JSON array `info` (failure, mode,
  `measured_fps`, controls, source name; written by the camera process), `warnings` (written by the
  main process) and the shared integer `replaced_count`. `recording` is `ready` with
  `recording_in_progress`.
- S6HT 2: the gate holds each camera while one is `waiting` and none is `starting`. Thus the waiting
  cameras join together, with one gate count.
- S6HT 3: the stop flag of a worker is `should_close` of its status. A failure stops only that camera.
- S6HT 4: each camera process gets a named pipe in `SKELLYCAM_STDERR_PIPE`. `skellycam/__init__.py`
  sets it as stderr before OpenCV loads; `_forward_lines` relays it (UTF-8), also in T-RING-46.
- S6HT 5: the apply returns when each new or reopened camera passed or failed its rate check; a live
  change, after its set and read-back.
- S6HT 6: the apply leaves out a camera outside the running group; the whole-request check keeps it.
- S6HT 10: only exposure gives `auto_control` until 3c sets gain and focus; a native source gives
  none for exposure (W [11.3](../../specs/windows-capture.md#113-auto-mode-at-record-start-d37)).
- S6HT 11: a failed periodic read with no hang logs a warning. A live change fails when the set
  raises or a manual camera reads back another value. The forced auto exposure of Linux is no failure.
- S6HT 12: OpenCV gives exposure present, gain and focus present when `get` is not -1, and
  `retrieve_ns`; on Windows it finds the device by `directshow_index`.
- S6HT 13: for two rates of no one rate class, the text says "skips about N frames per second".
- S6HT 15: a new source at each open and reopen. S6HT 16: a `waiting` camera reads no frame before
  its rings are attached. S6HT 17: the failure line is at WARNING (T-CAP-11 counts these lines).
- MA22 1: `MediaFoundationDeviceInfo` hashes the lower-case path until `CameraDeviceInfo` does.
  MA22 9: detection keeps a device with no VID and PID.
- MA22 2: `MediaFoundationSource()` has no argument. MA22 3: an HRESULT with no name in
  `errors.NAMES` shows as eight hex digits. MA22 4: one bounded call for each `set_controls` (sets,
  then `Get` of exposure, focus, gain); during the close each control is absent. MA22 5: no
  `OnFlush` 5 s after `Flush`: the close goes on. MA22 6: a failed `GetSampleTime` starts the
  `NO_SAMPLE_NS` rule of W 4.2. MA22 7: a failed `open` runs the close; a hang there raises with
  `hung=True`. MA22 8: `MF_SOURCE_READERF_ERROR` with a success HRESULT gives `E_FAIL`. MA22 10: a
  late `ActivateObject` shuts down only the new source. MA22 11: each message of the detection child
  has `BOUNDED_CALL_LIMIT_S` + 2 s; then the child stops, stage `detection`.
- BM73 2: `_probe_codec` sets `SIGALRM` only on the main thread. R60B 1: OpenCV on Windows gives the
  DirectShow path that it opened. FTC3 5: the early `too_slow` sets `measured_fps` to the window rate.
- Tests, criteria unchanged: BM73 3 (default context); BM73 4 (T-CAP-13 waits for the first ring
  write); BM73 5 (T-CAP-46 in a fresh process); BM73 6 (OpenCV fakes on a `VirtualClock`); R60B 2
  (labels by USB IDs; no vendor ID, no test camera); FTC3 1 (a forced clock step is at most 10 ms);
  FTC3 2 (T-CAP-86 joins the clock); FTC3 7 (T-CAP-51 counts labelled real cameras); FTC3 8
  (T-CAP-60 checks frames / elapsed time).

Done: 037V 1 to 6 (the phase 2 loop and its helpers are deleted; its tests moved, retired or
merged; the English doc changed).

Dropped as stale: S6HT 9, 19, 6EKB 12 (replaced by 6EKB 4, 5 and 037V); S6HT 14 (the loop is
deleted); S6HT 18, BM73 1, FTC3 4 (the old recorder and its files are deleted); FTC3 3 (T-CAP-85 is
deleted; the 100 ms rule is decided).

## Reason

The rulings of the user on the review sheets. Each old entry keeps the reasons of its items.

## Open work

See [open-work.md](../open-work.md).
