# 82AA — The last frame of a take with no stop pause, the files of a surviving process, the stuck-writer limit

**Status:** accepted, 2026-11-20 (user, review sheets Q465, Q466 and Q472; the correction of item 1 by
the fourth review).

## Decision

1. **The last frame of a take** (Q472: items 5 and 10 of
   [ADR-F8C0](F8C0-third-review-choices.md)). The stop does not pause the cameras. It sets the last
   frame of the take to the largest gate count plus 2, and at least the first frame. With no take
   level (the group stops, or the main process is gone), the first camera that ends sets the last
   frame to the latest group frame plus 2, at least the first frame, and each camera ends its writer
   with that frame count. Correction of the fourth review: the stop reads the gate count and writes
   the last frame under the lock of `last_recording_frame_number`, and it writes only when the value
   is still −1. A last frame that a camera set first stays.
2. **The files of a surviving process** (Q465). A camera process that survives `terminate` and `kill`
   leaves its files unfinished, and the manifest stays `recording` for the repair step.
3. **The stuck-writer limit** (Q466). A stop or an exit gives up on a stuck writer after 15 s with no
   progress.

## Reason

- Item 1: a paused push source loses the frames of the pause (a `gap` at row N − 2 on real cameras);
  the gate lets a camera hold one frame more than the largest count; a stall of the main process
  between the read and the write gave more rows than the frame count.
- Items 2 and 3: the take level never touches the files of a live writer, and an exit cannot hang on a
  disk that takes nothing.

## Evidence

The tests `test_the_stop_costs_no_source_frame_before_the_last_rows`,
`test_a_slow_stop_ends_each_camera_at_the_last_frame`, `test_the_stop_keeps_a_last_frame_that_a_camera_set`,
`test_the_cameras_end_their_take_10_s_after_the_server_died`,
`test_finish_does_not_touch_the_files_of_a_camera_whose_process_runs` and
`test_the_wait_for_a_recording_save_has_a_time_limit`.
