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
