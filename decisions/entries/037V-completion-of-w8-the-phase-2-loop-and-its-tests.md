# 037V — Completion of W8: the phase 2 loop and its tests

**Status:** superseded by [2GS1](2GS1-step-3a-choices-of-the-capture-code-and-its-fixes.md), 2026-11-20 (commit to dom/integration; was accepted, 2026-11-20 (user, through the review sheets of 2026-11-20); was proposed, 2026-11-20 (agent; waits for the user)).

## Decision

This entry records the completion of W8 of
[ADR-PDD3](PDD3-decisions-of-the-user-on-items-65-to-78-and-the-3a-review.md), as the user restated
it on 2026-11-20: the tests that started cameras through the phase 2 loop move to the shared loop,
and then the phase 2 loop is deleted. It completes item 12 of
[ADR-6EKB](6EKB-choices-of-the-3a-review-fixes.md) and item 14 of
[ADR-S6HT](S6HT-choices-of-the-3a-loop-code.md). An agent made the choices below. The user decides
them.

1. **Deleted code.** `skellycam/core/camera/opencv/opencv_camera_loop.py`,
   `opencv_camera_worker_method.py`, and the helpers that only they used in `opencv/opencv_helpers/`:
   `camera_loop_update_checks.py`, `check_for_new_config.py`, `opencv_get_frame.py` and
   `setup_opencv_camera_loop.py`. Also `await_extracted_configs` in `camera_group.py` and each
   `state is None` rule: `CameraStatus.in_gate`, `CameraStatus.ready`,
   `CameraOrchestrator.should_grab_by_id` and the record start. The helpers that the shared loop or
   the OpenCV source use stay: `create_cv2_video_capture.py`, `create_initial_frame_recarray.py`,
   `handle_recording_updates.py`, `handle_video_recording_loop.py`, `opencv_apply_config.py`,
   `opencv_extract_config.py` and `recommend_camera_exposure_setting.py`.
2. **Moved to the shared loop, with the same criteria.** T-RING-38 and T-RING-40 run the capture app
   with the fake source of section 16.1 of [`specs/windows-capture.md`](../../specs/windows-capture.md).
   T-RING-39 and T-RING-47 run `CameraGroup` with the OpenCV source and the fake capture of the ring
   tests. T-RING-38 reads its counters after the fake stops and the loop ends, because a close of the
   group closes the rings before the decode stage writes its last frame. The reference video tests
   (`test_concurrent_camera_replay.py`, `test_recording_finalization.py`,
   `test_recording_lifecycle.py`) run `CameraGroup` with the OpenCV source on a file-backed capture
   that reports 60 fps and gives one frame each 1/60 s: the shared loop refuses a mode under 30 fps,
   and the videos have 6 fps. Each ring frame and each saved frame is compared with the video frame
   at its `source_frame_number`, over the whole image (U2: no stamp; before, the top 80 rows were
   left out). `test_capture_reads.py` tests `OpenCVSource.read_frame` in place of `opencv_get_frame`.
   In `test_camera_startup_failure.py`, one test reads the failure with `take_setup_failure`, and one
   test checks that the apply response gives the original open error of the OpenCV source. The unit
   tests of `CameraStatus` and `CameraOrchestrator` (`test_camera_orchestrator.py`, and the fixture
   of `test_camera_shutdown.py`) set the states of 8.1 in place of the flags of the phase 2 rules.
   One criterion changes with 9.4 and 5.2: the old test "no grab while another camera is not
   connected" becomes "no grab while the cameras wait (`waiting`) to join the gate together",
   because a camera that is `starting` does not hold the gate.
3. **Retired, because a capture test proves the same rule on the shared loop.** The two tests of
   T-RING-23 in the camera loop (T-CAP-08). The dated note at the row of T-RING-23 in
   [`specs/frame-ring.md`](../../specs/frame-ring.md) records it. With no spec row:
   `test_failed_reads_never_publish_stale_frames` (T-CAP-103, T-CAP-36);
   `test_aborted_startup_reports_missing_camera_instead_of_type_error` (T-CAP-109);
   `test_successful_config_is_unchanged` (T-CAP-41).
4. **Retired, because the accepted capture spec changed the rule.** A failing camera no longer stops
   the group. It is `failed` or `dead`, and the other cameras continue (D10, D23, D38, U4). T-CAP-35,
   T-CAP-81, T-CAP-102 and T-CAP-103 check the new rule. These tests checked the old rule:
   `test_camera_failure_stops_sibling_and_preserves_error`, the case `one-camera-eof` of the
   concurrent replay, the case `camera-failure-recording` of the finalization test, the case
   `second-recording-fails` of the lifecycle test, and the case `eof-failure` of
   `test_camera_loop_shared_memory.py`. The stall watch of 9.5 replaces the limit of 30 failed reads
   of the phase 2 loop.
5. **Merged.** The case `requested-stop` of `test_camera_loop_shared_memory.py` (one video, pause,
   each frame, clean-up) is a part of the concurrent replay, which checks the same points for each of
   the three videos, and also the order of the capture stamps. The file is deleted, with the poe task
   `test-reference-loop`.
6. **Docs.** The English page `skellycam-docs/docs/technical/frame-synchronization.mdx` names the
   shared loop. The translated copies are not changed; the translation process updates them, as for
   item 61 of [`specs/frame-ring.md`](../../specs/frame-ring.md). The
   `README.md` of `skellycam/tests/reference_recordings/` is not changed, because it holds a
   private-data finding that the user decides first (see [open-work.md](../open-work.md)).

## Reason

- No camera process runs the phase 2 loop (W8). Its tests measured code that no user runs.
- Items 3 and 4: a test that the spec changed, or that a capture test already proves, adds run time
  and no proof.
- Item 2: a moved test keeps its criteria. Where the shared loop stamps no text, the comparison is
  stricter.

## Alternatives rejected

- Keep the failing-camera cases with the new rule: they would repeat T-CAP-35 and T-CAP-103 with
  video files.
- A virtual clock for the reference videos: the OpenCV source stamps arrivals with the real clock.

## Open work

See [open-work.md](../open-work.md).
