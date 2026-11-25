# B7YV — Evidence of fix lane 6

The evidence of [ADR-B7YV](../entries/B7YV-choices-of-fix-lane-6.md) and of the clock item (Q673) of
[ADR-F4N7](../entries/F4N7-decisions-of-the-user-on-the-pace-tests-of-fix-lane-6.md).

Set-up: a copy of the worktree of this lane under WSL Ubuntu 24.04 (uv 0.13.9, Python 3.13.18, a stand-in
`sounddevice` with no PortAudio, open-file limit 65536), `taskset -c 0-1` (2 cores), one run at a time. Each run is
one pytest process with T-CAP-13 (two cases) and T-CAP-86. Other work ran on the same host at the same time, so the
load changed during the runs.

1. **Before the clock change** (the T-CAP-86 diagnostics only), 20 runs: T-CAP-13 "as it comes" failed 2 times,
   T-CAP-86 6 times. 15 more runs, each just before a run of the new harness: T-CAP-13 failed 1 time, T-CAP-86 9
   times. Each T-CAP-13 failure: "the first camera was not `waiting` while the second started (s from the clock
   start: waiting [6.0], second passed 6.0, opens {'e605': [3.0], '17ae': [0.0]})". The first camera has no
   open delay, and the second camera has 3 s: the first camera opened 3 s of virtual time after the second.
2. **After the clock change** (`VirtualClock.expect` for each camera loop thread), 20 runs: T-CAP-13 failed 0
   times, T-CAP-86 11 times. The new self-test
   `test_virtual_clock_holds_the_time_for_an_expected_thread_until_it_waits` passes; with no `expect`, the same
   steps move the time 3.0 s before the late thread waits.
3. **T-CAP-86, before and after.** Each failure but one: "timed out: camera 4a36 in ('ready',)", and the
   reopened camera is `failed` with "not ready in 15 s". One failure after the change: "17 relay messages, not
   20" (the failure of the macOS CI job). The diagnostics of each failure have the same form. A run before the
   change: the hold starts at 6.233 s of virtual time and ends at 22.133 s; the relay messages and the gate counts
   of the two other cameras (pass of the collection, virtual s, message count, gate counts):
   (0, 6.233, 1, [5, 5, 5]) ... (71, 8.6, 6, ...) ... (158, 11.5, 8, ...) ... (475, 22.067, 18, ...),
   (477, 22.133, 20, ...). A run after the change: the hold from 3.2 s to 21.1 s; (0, 3.2, 1, [4, 4, 4]),
   (2, 3.267, 2, [5, 6, 4]), (107, 6.767, 3, [6, 6, 4]) ... (537, 21.1, 20, [19, 18, 4]). In a passing run the
   collection took 345 passes and 11.5 s. At each snapshot the clock had no expected thread, the two other
   loops were in `gate` or `wait`, the test thread in `run`, and the held camera in `hold`.
   The reading of the agent: each pass of the collection moves the virtual time by one frame period. The two
   other camera loops make one gate round only every 1 to 300 passes, so their frames do not keep up with the
   virtual time. A loop in the state `gate` lets the clock move while it sleeps 1 ms of real time at the gate and
   while it does the work of its next pass, up to its next gate probe. When the host is busy, the collection needs
   more than the 15 s of the ready limit of the held camera. This is a fault of the test clock, not of the product;
   the clock change of Q673 does not touch it. No fix is made here (Q673).
4. **The blocking halves on 2 cores**, 5 runs each: T-CAP-04, T-CAP-40, T-CAP-82, T-CAP-110 and the gate test
   (5 of 5 passed); the stall test with THREAD and PROCESS workers (5 of 5); T-PRV-05, T-PRV-09, T-PRV-10,
   T-PRV-13, T-PRV-15 (two cases), T-PRV-16 and T-PRV-54 (5 of 5).
5. **Windows** (the development machine, Windows 11, Python 3.13.18): each changed test file passed one time, with
   its `pace` tests (margin 1); the 12 new `pace` tests alone with `SKELLYCAM_PACE_MARGIN=3` passed; the other test
   files that use the capture harness passed with `-m "not pace"`.
6. **The gate on the test clock** (item 1 of [ADR-7GC1](../entries/7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md)),
   the set-up above, each run T-CAP-13 (two cases) and T-CAP-86. Before the change, 30 runs: T-CAP-86 failed 25 times (each failure took about 61 s), T-CAP-13 0
   times. After the change, 30 runs: 0 failures (each run about 2 s). The diagnosis of this lane read the trace of
   the failed runs: the time moved more than 99 % of the virtual time of the collection while a loop in "gate"
   could pass. This step did not measure that share again. The two new self-tests of the clock pass on Windows and
   in WSL. With the change, T-CAP-05 failed at each run: "ring frame counts differ: {'e605': 1109, '17ae': 1109,
   '4a36': 1110}". The decision Q696 of the user then changed the end check of T-CAP-05.
7. **The end check of T-CAP-05** (item 2 of [ADR-7GC1](../entries/7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md),
   Q696 of [ADR-8ACV](../entries/8ACV-decision-of-the-user-on-the-end-check-of-t-cap-05.md)), with the clock change
   of item 6. On Windows (the machine of item 5):
   - 5 runs: 5 passed. Ring frame counts 1109, 1109 and 1110 (the fast camera). The last ring frames arrive at
     39.9999996 s, 39.9999996 s and 39.9999999 s of the clock. From ring frame 811 to the end (frame 811 of the
     two others arrives at 30.1 s, of the fast camera at 30.0667 s), ring frame n of the fast camera arrives one
     frame period (33 ms) before ring frame n of the two others: it is one frame ahead after the drop at the end
     of its 60 fps window. At ring frame 810 the difference is 66.7 ms, and at ring frames 780 to 809 it is 50 ms (a trace of one run).
   - The fast window at 60.0000018 frames per second (frames a few ns early), a temporary change: 3 runs, 3
     passed. Ring frame counts 1109, 1109 and 1109; the last ring frames at 39.9999996 s, 39.9999996 s and
     39.9999993 s.
   - The clock before the change, a temporary reverse of the clock files: 3 runs at 60 frames per second and 1
     run at 60.0000018 frames per second, each passed.
   - A temporary mutation of the gate in `should_grab_by_id` (`own <= status.frame_count.value + 1`, so a camera
     can be two frames ahead): T-CAP-05 failed, "ring frame counts differ by more than one: {'e605': 1109,
     '17ae': 1109, '4a36': 1111}". After the undo, the diff of `skellycam/core` and `skellycam/api` was empty.
   - `-m "not pace"`, each test file of `skellycam/tests/capture/` in 7 slices, and `test_pace_marker.py`: each
     passed (464 passed, 49 skipped; the `pace` tests and T-CAP-46 deselected).

   In WSL (the set-up above, a new copy of the worktree): 20 runs, each one pytest process with T-CAP-86,
   T-CAP-13 (two cases) and T-CAP-05: 0 failures (80 of 80 tests passed, about 3 s for each run).
   `test_helpers.py`: 34 passed.
8. **The slow period of T-REQ-17** (item 4 of [ADR-7GC1](../entries/7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md)).
   The CI failure (run 45503344875): `('done', None) == ('failed', 'timed-out')`. The diagnosis of this lane: 23 of
   60 runs failed on 2 cores (13 of 60 before the clock changes of this lane). On Windows (the machine of item 5),
   with a temporary real sleep of 0.05 s between `slow_period` and the request:
   - the test before the change: 3 runs, 3 failed with that same assertion;
   - the test with `at_next_set=True`: 3 runs, 3 passed.

   After the sleep was removed: `test_camera_requests.py` and `test_helpers.py` with `-m "not pace"`, 110 passed;
   `test_states.py` with `-m "not pace"`, 38 passed. In WSL (the set-up above, a new copy of the worktree): 30
   runs of T-REQ-17, 0 failures. In one run, after the test passed, the watch thread of the group logged "the
   watch could not read the camera queues: handle is closed" at the end of the process.

   T-CAP-113 (`test_t_cap_113_a_frame_that_waits_at_the_gate_is_not_too_slow`) has the same race. A temporary
   probe asserted that the slow period of 12 s had not ended at the end of the check. With no sleep, the probe
   passed. With a real sleep of 0.05 s or 0.5 s before `app.apply`, the probe failed: the slow period had ended
   before the check, so the test then passes but does not test its case. The armed slow period does not fit:
   the live set goes to the other camera. No change was made there.
9. **The slow period of T-CAP-113** (item 5 of [ADR-7GC1](../entries/7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md)).
   Before the change, a temporary probe of the test: the case is exercised when a check starts after the apply,
   ends `ready` after that, and the slow period does not end before that end.
   - Windows (the machine of item 5), 30 runs: 30 passed; 29 exercised the case, 1 did not. In that run, the check
     after the apply started at 5.9 s of the clock and had no end yet: the test read the `ready` state from
     before the check, because its wait took the `checking` of the start-up.
   - WSL (the set-up above, a new copy of the worktree), 30 runs: 30 passed and 30 exercised the case.
   - With a real sleep of 0.05 s before the apply (evidence item 8), the slow period ended before the check.

   After the change (the slow period starts at the set of the first camera):
   - A trace of one run: the set at 3.333 s, the check from 3.333 s to 7.117 s, and the slow period did not end
     before the end of the test.
   - A temporary slow period of 1 s: the test failed, "the slow period ended before the end of the check".
   - A temporary mutation of `_pass` of `camera_loop.py`: at the gate, the check ends `too_slow` when the clock
     is at or after the early deadline. The test failed: the state was not `ready`. Two other temporary
     mutations did not make the test fail: the early deadline compared with the time of the take, not the
     arrival, in `_feed_check`; and the measured rate from the time of the take. In this run the loop takes the
     newest frame after each wait, so these times are near the arrival. Each mutation was undone; the diff of
     `skellycam/core` and `skellycam/api` was empty.
   - Windows, 30 runs: 0 failures. WSL on 2 cores, 30 runs: 0 failures. `test_states.py` with `-m "not pace"`:
     38 passed.
