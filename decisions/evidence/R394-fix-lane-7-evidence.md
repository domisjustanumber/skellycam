# R394 — Evidence of fix lane 7

The evidence of [ADR-R394](../entries/R394-choices-of-fix-lane-7.md), for the three items of
[ADR-N14T](../entries/N14T-decisions-of-the-user-on-the-ci-review-of-2026-11-25.md).

Set-up, as for fix lane 6 ([B7YV evidence](B7YV-fix-lane-6-evidence.md)): a copy of the worktree of this lane under
WSL Ubuntu 24.04 (uv 0.13.9, Python 3.13.18, pytest 9.2.0, a stand-in `sounddevice` with no PortAudio),
`taskset -c 0-1` (2 cores), one run at a time. The diagnostic plugins and probes of this lane were in a scratch
folder outside the repository and in a second copy of the worktree; the worktree has none of them. A Linux result is
a fact about Linux only.

## Item 2: "Too many open files"

1. **The macOS CI job** (run 45523455772, job 138900837438, `macos-15`): the first pytest step ran 433 tests in
   4 min 55 s (11 failed, 4 errors). The first failure is
   `test_t_unx_98_two_cameras_of_one_model_keep_their_own_entries[other usb ids]` (69 %): "WorkerRegistry: 1
   worker(s) could not be killed: ['Camera1-17ae-Worker(PID:1402)']". The first "Too many open files" is in
   T-CAP-113 (84 %); after it, each test in `test_status_locks.py` and `test_camera_message.py` fails with it. After
   the summary line, the process did not end. The runner killed it at the limit of 40 min ("Terminate orphan
   process: pid (1402) (python3.13)").
2. **The count of open files grows without a bound.** The selection of the first macOS step
   (`pytest skellycam/tests/capture skellycam/tests/preview -m "not camera_hardware and not capture_local and not
   capture_timing and not pace"`), open-file limit 65536, the count of `/proc/<pid>/fd` after each test (a pytest
   plugin) and each 2 s (`ls /proc/<pid>/fd | wc -l`): 12 after the first test, 3,962 after the last of 437 tests
   (sampled maximum 3,991); 3,925 of them are pipes, 24 are files in `/dev/shm`, no socket. A test file that makes
   no camera group adds no pipe (for example `test_helpers.py`, `test_exposure_search.py`, the preview unit tests).
   A test that makes a camera group adds 2 to 58 pipes, for example `test_camera_requests.py` 996 pipes in 74 tests,
   `test_states.py` 672 in 37 tests.
3. **The pipes are the queues of the pubsub managers of the old camera groups.** A second run (same set-up) also
   counted the live `multiprocessing.Queue` objects (`gc.get_objects`) and the global registry
   `CAMERA_GROUP_PUB_SUB_MANAGERS` of `skellycam/core/ipc/pubsub/pubsub_manager.py` after each test. At the end:
   3,941 pipes, 1,958 live queues (each queue holds a pipe of 2 ends), 206 groups in the registry with 1,754 of
   these queues as subscriptions, and 834 threads (831 `QueueFeederThread`). The pipes are twice the queues at each
   point of the run. Code facts: `create_camera_group_pubsub_manager` puts each new manager into the registry and
   removes an entry only when the same group ID comes again; `CameraGroup.close` (`camera_group.py`) does not close
   the manager or remove it; no product code calls `PubSubTopicManager.close`. `multiprocessing.Queue.close` does
   not close the pipe of a queue that never had a `put` (no feeder thread); the pipe closes when the queue object
   goes.
4. **The experiment.** A third run with a plugin that, after each test, closes each manager of the registry
   (`cancel_join_thread` and `close` of each subscription) and clears the registry: 414 passed, 23 skipped; the
   sampled maximum was 121 open files, 54 at the end. The same plugin with the open-file limit 256: 414 passed.
   Without it, at the limit 256: 268 failed, 24 errors, 122 passed, in 15 s; the first "Too many open files" is in
   `test_camera_requests.py` (about 9 % of the run).
5. **The hang at the end of the run.** In the run of item 2, pytest printed its summary (1 failed: T-UNX-98
   [other usb ids], with "could not be killed", as on macOS) and then did not end (killed after 11 min). A stack
   dump (py-spy 0.4.1): the main thread in `threading._shutdown`, and the non-daemon thread `Camera0-e605-Worker`
   (`camera_worker.py` makes it with `daemon=False`) in `VirtualClock.wait_until` of
   `skellycam/tests/capture/fake_source.py`, called from `read_frame` of the fake in `CameraLoop._read`. The run of
   item 3 had no failure of T-UNX-98 and no hang, so that failure is intermittent on Linux.
6. **Not verified.** The open-file limit of the hosted `macos-15` runner and the count of open files on macOS
   [NV]. On Linux the limit 256 fails at about 9 % of the run, and the macOS job failed only at 84 %, so the limit
   of that runner is likely higher than 256 [NV]. That the macOS errors come from the same registry [NV]. Why
   T-UNX-98 [other usb ids] leaves a camera loop thread that does not end was not examined.

## Item 3: T-CAP-91 on Linux CI

7. **The CI failure and the count without a fault.** CI run 45523455772, job `capture-linux` (`ubuntu-24.04`, commit
   dfc6c6e2a): "AssertionError: 1 frames replaced in 100 s"; the step ran 7 min 10 s (1 failed, 447 passed). A
   temporary probe in a second copy of the worktree printed the replaced frames of each fake, the gap between the
   arrivals of the gate frames of the two cameras with one ring frame number, the open times of the fakes and each
   forced step of `VirtualClock`. Before the change of item 3 of ADR-R394, T-CAP-91 alone, 30 runs: 30 passed, each
   with the count 2 (replaced frames at 63.667 s and 97.033 s of the window), no replaced frame of the 29.97 fps
   fake, both opens at one virtual time, no forced step. The gap starts at 3.1 ms and grows by about 1 ms each
   second; a frame is replaced only when it reaches two frame periods (66.7 ms), and the gap then goes back to
   33.4 ms. Thus the count is 1 when the gap starts 3.1 ms or more lower. With two busy loops on the same 2 cores,
   20 runs: 20 passed with 2 (one forced step of 3 ms, at the end of the warm-up). In the whole Linux CI selection
   (`skellycam/tests/capture skellycam/tests/preview -m "not camera_hardware and not capture_local and not pace"`),
   3 runs of about 7 min: T-CAP-91 passed with 2 in each; one run had one other failure,
   `test_status_locks.py::test_a_live_but_slow_holder_and_torn_json_never_raise[writes with no lock]` (not examined).
   The failure of CI did not occur without an injected delay.
8. **The cause, with an injected delay.** A temporary real sleep of the main thread after each `CameraWorker.start`
   (in the wrapper of `install_loop_clock`), T-CAP-91 alone, before the change:

   | Sleep | Runs | Failed with "1 frames replaced in 100 s" | Second open after the first (virtual) |
   |---|---|---|---|
   | 0.5 ms | 5 | 0 | 0 |
   | 2 ms | 5 | 1 | 3.003 s in the failed run, else 0 |
   | 5 ms | 5 | 0 | 0 |
   | 20 ms | 5 | 5 | 3.003 s |
   | 0.2 s | 10 | 10 | 3.003 s |

   In each failed run the gap of item 7 starts at -30.3 ms (the frame of the 30 fps camera arrives 30.3 ms after
   the frame of the 29.97 fps camera with the same number), and the only replaced frame is at about 97 s. The
   virtual time moved 3 s before the second open with no forced step: the first loop was the only participant
   (the second thread was not expected yet). The four forced steps of these runs come after the second open.
9. **After the first rule only** (the start of the group expects each loop thread), a sleep of 0.2 s, 20 runs: 20
   failed with 1. The second camera opened 30 ms later: three forced steps of 10 ms while the second thread was
   expected and not started (the probe listed it in `expected`).
10. **After both rules** (item 3 of ADR-R394), 2 cores in WSL:
    - with a sleep of 20 ms, and of 0.2 s, T-CAP-91 alone, 20 runs each: 40 passed, the count 2, both opens at one
      virtual time;
    - with no injection or probe (a clean copy of the worktree), T-CAP-91 alone, 30 runs: 30 passed;
    - T-CAP-86, T-CAP-13 (two cases), T-CAP-05 and T-CAP-91 in one process, 20 runs: 100 of 100 passed.

    The new self-tests: on Windows (the development machine, Windows 11, Python 3.13.18) `test_helpers.py` passed
    (38 tests). With the change undone (`git stash` of `fake_source.py` and `capture_session.py`), the two self-tests
    of that time failed: the second camera opened 2.99999997 s after the first, and a thread that was expected two
    times held the clock. With only the forced-step condition removed, the self-test of the forced steps failed, and
    the group self-test failed with the second open 0.03 s after the first.
11. **The whole capture blocking selection** (`uv run pytest skellycam/tests/capture -m "not camera_hardware and not
    capture_local and not pace"`) with both rules: Windows (the machine of item 10), 1 run: 415 passed, 3 skipped;
    WSL on 2 cores (the clean copy), 2 runs: 389 passed, 29 skipped in each. The preview tests
    (`skellycam/tests/preview`, same markers) on Windows: 62 passed.
