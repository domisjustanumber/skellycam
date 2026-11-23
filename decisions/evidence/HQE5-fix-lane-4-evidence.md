# HQE5 — Evidence of fix lane 4

The evidence of [ADR-HQE5](../entries/HQE5-choices-of-fix-lane-4.md).

1. CI run 45214740615, Linux: 7 failed, each with `workers="process"`: "no answer from the camera process in
   30 s", then SIGTERM; 15 warnings "This process ... is multi-threaded, use of fork() may lead to deadlocks".
   Reproduced in a copy of commit 54d915c59 under WSL Ubuntu 24.04 (uv 0.13.9, Python 3.13.18, a stand-in
   `sounddevice` with no PortAudio): T-REC-44 alone passes; T-REC-31 then T-REC-44 fails in the same way. The two
   camera processes had one thread each, in a futex wait. `py-spy` 0.4.1 `dump --native` of each: after
   `os.fork()` in `popen_fork.py:73`, `VideoReformatter.__dealloc__` (PyAV) → `sws_freeContext` →
   `avpriv_slicethread_free` → `pthread_cond_destroy`. With `spawn`, T-REC-31 then the 7 tests: 8 of 10 passed;
   the 2 lost-heartbeat tests failed with `FileNotFoundError` in a restarted camera process. The agent's reading
   of it (not traced to the line): on POSIX a spawned process opens a semaphore by its name, and
   `reset_for_start` dropped the old arrays of one camera while the other restarted camera process still started
   with them. With `spawn` and `CameraStatus.retired`: T-REC-31, each test of `test_connection.py`, the new tests
   of this lane and `test_pace_marker.py`: 90 passed in the same copy.
   The test `test_a_camera_process_starts_after_a_video_decode_in_the_main_process` (PyAV in the main process,
   then two camera processes) fails on the old code in that copy with the same text, and passes on the new code.
2. The log of run 44676423645: `test_connection.py ssssssssss`.
3. The Windows runner, run 45214740615: `row=30 from=125 to=127` (delay 0.05 s) and `row=30 from=125 to=131`,
   `from=126 to=131` (0.2 s): each gap is on one row near the end; 1.0 s and 60 fps passed.
