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
