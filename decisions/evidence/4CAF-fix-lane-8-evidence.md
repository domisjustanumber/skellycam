# 4CAF — Evidence of fix lane 8

The evidence of [ADR-4CAF](../entries/4CAF-choices-of-the-close-of-the-queues-of-a-group.md).

Set-up, as for fix lanes 6 and 7 ([R394 evidence](R394-fix-lane-7-evidence.md)): a copy of the worktree under WSL
Ubuntu 24.04 (uv 0.13.9, Python 3.13.18, pytest 9.2.0, a stand-in `sounddevice` with no PortAudio),
`taskset -c 0-1` (2 cores), one run at a time. A second copy, "before", has the three product files of 8b196f779
(`camera_group.py`, `pubsub_abcs.py`, `pubsub_manager.py`) and the new test. The diagnostic plugins of the lane
(the count of open files after each test, and an end of the process after the summary) are in a scratch folder
outside the repository. Windows: the development machine, Windows 11, Python 3.13.18. A Linux result is a fact about
Linux only; the result on macOS is [NV].

## Task 1: the queues of a closed group

1. **The users of the code** (a search of each `.py` file). `CAMERA_GROUP_PUB_SUB_MANAGERS` and
   `create_camera_group_pubsub_manager`: only `pubsub_manager.py` and `CameraGroupIPC.create`. The subscriptions
   of a group: `CameraGroupIPC` (extracted config, recording finished, diagnostics), `CameraManager` (settings, ring
   names, recording info, 3 for each camera), `CameraGroupManager` (frame rate; no product code publishes or reads it;
   `get_backend_framerate_updates` has no caller in the product). The readers in the main process: the watch thread
   of the group and the close (`_take_diagnostics`). The take level and the preview use no queue of the group. The
   camera processes get the queues pickled at their start. FreeMoCap (its checkout beside this repository): one
   test calls `create_camera_group_pubsub_manager` and `PubSubTopicManager.close`; its run time reads
   `ipc.global_kill_flag` of a group.
2. **T-CAP-114 before the change** (Windows): failed, "assert '8dec60' not in {'8dec60': PubSubTopicManager(...)}".
   After the change: passed. A temporary mutation (no close of the two pipe ends of a queue with no feeder thread):
   failed, "timed out: the read ends of the queues closed" (60 s). The file was put back.
3. **The count of open files**, the selection of the first macOS step (`pytest skellycam/tests/capture
   skellycam/tests/preview -m "not camera_hardware and not capture_local and not capture_timing and not pace"`), the
   count of `/proc/<pid>/fd` after each test and each 2 s:

   | Copy | Open-file limit | Result | Largest count | Count at the end |
   |---|---|---|---|---|
   | before | 65536 | 417 passed, 1 failed (T-CAP-114) | 4,050 | 4,017 (3,983 pipes, 208 groups in the registry, 842 threads) |
   | after | 65536 | 418 passed | 85 | 36 (3 pipes, 0 groups, 3 threads) |
   | after | 256 | 418 passed | 85 | 36 |

   At the end of each run, no thread that is not a daemon was alive.
4. **The capture and preview tests** with the change. Windows: `skellycam/tests/capture -m "not camera_hardware and
   not capture_local and not pace"` 416 passed, 3 skipped; `skellycam/tests/preview` with the same markers 62
   passed; `test_pubsub.py`, `test_camera_group_manager.py`, `test_camera_shutdown.py`,
   `test_camera_startup_failure.py` and `test_worker_lifecycle.py` 65 passed. WSL on 2 cores, the selection of the
   Linux CI job (`skellycam/tests/capture skellycam/tests/preview -m "not camera_hardware and not capture_local and
   not pace"`), 1 run: 452 passed, 29 skipped.
5. **The recorder tests** (the recorder writes the take while the group runs), Windows:
   `skellycam/tests/take_recorder -m "not recorder_bench and not pace"` 269 passed. They include
   `test_the_shutdown_endpoint_finishes_a_running_take` (THREAD and PROCESS workers) and
   `test_an_exit_during_a_take_leaves_finished_camera_files`, which close a group during a take and check the take
   files.
6. **Not verified.** macOS (the jobs run only by hand) [NV]. The recorder tests in WSL were not run.

## Task 2: the camera loop thread of T-UNX-98 that does not end

The evidence of [ADR-JC4X](../entries/JC4X-choices-of-the-gate-probe-of-a-second-app-on-the-test-clock.md). The
runs use a scratch plugin: at the end of pytest, when a non-daemon thread is still alive after 3 s, it prints each
thread stack and the state of each `VirtualClock`, and then ends the process with the status of pytest.

7. **The rate.** `test_t_unx_98_two_cameras_of_one_model_keep_their_own_entries[other usb ids]` alone, 30 runs on
   the copy of 8b196f779: 0 stuck. The whole file `test_restore_store.py`, 20 runs on that copy: 1 failed, with
   `[same model]`, "WorkerRegistry: 1 worker(s) could not be killed: ['Camera1-17ae-Worker(PID:...)']", and the
   thread `Camera1-17ae-Worker` stuck. The same file, 40 runs on the copy with the fix of Task 1: 2 stuck. Thus
   neither the clock rules of fix lane 7 nor the fix of Task 1 removes it. Fix lane 7 saw it before its clock
   rules too (R394 evidence item 5, on cf40e5657).
8. **The state of the clock in a stuck run.** The clock at 8.2 s of virtual time, with one state: the stuck loop
   in "run", no expected thread, no change for 23 s; the thread stack: `VirtualClock.wait_until` from
   `FakeSource.read_frame` in `CameraLoop._read`. A loop in `wait_until` must be in a "wait" state.
9. **A log of each state change of the clock** (a temporary probe in a third copy): the same file, 40 runs: 7
   stuck (a higher rate with the probe).
10. **The last changes of the stuck loop** (one run): the loop sets `('wait', 8.2333 s)` in `wait_until`, called
    from `read_frame`; then `gate`, called from `should_grab_by_id`, sets "run" for the same thread; then the other
    camera thread leaves the clock at its close. No later change. The code fact: each server of the test calls
    `install_gate_probe`, so the second wrapper wraps the first; its `shut` calls the first wrapper, and the first
    wrapper calls `VirtualClock.gate` for the thread that runs `_advance`.
11. **The self-test** `test_two_gate_probes_of_one_test_leave_the_wait_of_another_thread` (Windows): with the fix,
    3 runs, 3 passed; without it (`git stash` of `capture_session.py`), 3 runs, 3 failed: the waiting thread has
    the state "gate" and the time stays at 0.
12. **After the fix** (WSL on 2 cores):
    - the file `test_restore_store.py`, the probe copy, 40 runs: 0 stuck (7 of 40 before);
    - the file, the clean copy with both fixes, 40 runs: 0 stuck (2 of 40 before);
    - T-CAP-86, T-CAP-13 (two cases), T-CAP-05 and T-CAP-91 in one process, 20 runs: 100 of 100 passed.
    - the selection of the Linux CI job (capture and preview, blocking), 1 run: 453 passed, 29 skipped.

    Windows: `test_helpers.py` 39 passed; `skellycam/tests/capture -m "not camera_hardware and not capture_local and
    not pace"` 417 passed, 3 skipped.
13. **The other test, `test_status_locks.py::test_a_live_but_slow_holder_and_torn_json_never_raise[writes with no
    lock]`** (marker `capture_timing`), WSL on 2 cores, 20 runs: 1 failed, "assert (not False and 'info' in
    set())" (line 57), the same failure as fix lane 7. The reading of the agent, not proved: the child holds the
    lock for 1.5 s of real time from its `go`. The test then needs its second read in that time. When the main
    process gets the CPU late, the child has let the lock go, the second read takes the lock, and `info` leaves
    `no_lock`. No change.
