# DC43 — Choices of fix lane 5: the control thread on the test clock, two test waits, the Windows Server OS key

**Status:** proposed, 2026-11-23 (agent; the supervisor gave the 8 failures of CI run 45278395951).

## Decision

1. **Search time-outs on Linux CI (5 tests).** The fault is in the test clock, not in the product. The limit of
   20 s from the first set ([`camera-requests.md`](../../specs/camera-requests.md) 1.3 item 6) stays. The
   control thread of a camera loop does not wait on the `VirtualClock`. Thus the virtual time ran on while a
   set waited for that thread. The fix: in `capture_session.py`, `ClockQueue` replaces the class of the request
   queue of each `_ControlThread` on a virtual clock. A request stops the time (`VirtualClock.give_work`) until
   the control thread waits for its next request (`VirtualClock.idle_if`, state `idle`). `give_work` changes
   only no state or `idle` to `run`: a control thread that waits on the clock (the fake hang of a set) keeps
   its wait. The clock and the consumer go on the queue before its class changes, so a `get` of the started
   thread never finds a `ClockQueue` with no clock. A read of the controls after the timeout of the queue
   does not stop the time, as before. A new test sets a real delay of 20 ms before each set; the search must
   end `done` at -9 with 8 trials. A test of the clock checks the kept wait.
   T-CAP-31 then failed by one frame: with no virtual time in the set, a frame can arrive while the loop
   waits in its read, before it takes the check signal. The check does not count that frame. Spec 10.2 of
   [`windows-capture.md`](../../specs/windows-capture.md) names no first frame of the skip. Thus the test
   accepts a window that starts at the 16th or the 17th frame after the change. The product stays.
   The skip of the product is 15 + k frames, where k is the count of frames that the loop took after the
   change and before it read the check signal. The spec names no first frame. The user decides this point.
2. **T-UNX-95, `device-removed` (1 test).** A fault of the test. The test thread polls each 5 ms of real time.
   On the virtual clock the 2 s in `ready` before the removal can pass in less time. `one_camera` gets
   `until`. The two cases with `removed_after_frame` also accept `dead`.
3. **F1 (1 test).** A fault of the test. On POSIX the SIGTERM handler of a camera process only sets the stop
   flag. The kill after 1 s ends the process, and SIGKILL does not wait for the end. The test joins for at most
   1 s after `_end_process` and measures to the end. The bound of 2 s stays. The product stays as
   [`unix-capture.md`](../../specs/unix-capture.md) 4.10 states it: `terminate`, then `kill` after 1 s.
4. **T-UNX-74 on Windows Server (1 test).** The product is correct. The test was wrong.
   [`certify.md`](../../specs/certify.md) 11.2 makes the Windows key from the release and the feature version.
   The release is `platform.release()` (`os.release` of the report). On Windows Server 2025 the key is
   `2025Server 24H2`. The test on the system now has a fixed pattern for a client and a server release
   (`^\d+(Server)? \w+$`). A new test with fakes gives the client key `11 24H2` and the server key
   `2025Server 24H2` for the same feature version.

## Reason

1. On a real clock the hand-over takes a few ms of a limit of 20 s. On the virtual clock the loop thread ran
   at about 180 times real time, so a GIL delay of about 5 ms was about 1 s of virtual time for each set. A
   result on the virtual clock must not depend on the pace of the machine. Thus a `pace` marker is wrong
   here.
2. A test must not wait for a state that can be shorter than its poll.
3. The CI step and WSL show the process alive just after the kill. The spec asks for no wait for the end.
4. A server key that differs from the client key `11 24H2` keeps each model unchecked on Windows Server. That
   is the rule "a new OS version is a new OS key" (unix-capture.md 4.9).

## Evidence

WSL Ubuntu 24.04, a copy of commit 0d0dfa054, uv 0.13.9, Python 3.13.18, the stand-in `sounddevice` of
[ADR-HQE5](HQE5-choices-of-fix-lane-4.md), open-file limit 65536:

- `taskset -c 0-1` (2 cores), the first four capture test files: 10 failed, 79 passed, each a search
  `timed-out` (the CI failures among them). The same files pass on 28 cores. Trace lines in a copy only: the
  virtual time from the put of a set to its start was 0.03 s to 2.2 s, for 3 ms of real time.
- The new test with the old harness fails on 1, 2 and 28 cores (`timed-out`). With `ClockQueue`: those four
  files and `test_restore.py` on 2 cores, 115 passed; the 18 test files that use the harness (no hardware) on
  4 cores, 335 passed, 9 skipped.
- T-CAP-31 with `ClockQueue`: the check started at frame 181 (first 166), one frame after the frame of the
  test; `too_slow` came at its own t_a + 2.0275 s. With the new test rule it passes on 1, 2 and 28 cores.
- A poll of the state each 5 ms of `removed_after_frame=150` on 2 cores: `waiting` then `dead`, 5 ms of real
  time apart; `ready` was not seen.
- F1 fails on 2 and on 28 cores; with the join it passes.
- Review round 1: the test of the kept wait fails with the old `give_work` and passes with the new one. 2 cores:
  the four files and `test_restore.py`, 114 passed. Windows, the five test files of the review: 163 passed.

## Alternatives rejected

1. A larger limit of the search, or a `pace` marker: the product limit is correct, and the fault is in the
   test clock. A control thread that waits on the clock in the product: the product must not know the test
   clock.
2. A tracker of each state for each test: larger than the fault.
3. A join after the kill in `_end_process`: the end runs on its own thread, and no caller needs the end at
   the return. The user can choose it.
4. A key `Server 2025 24H2`: the spec gives no such form, and the key is distinct already.

## Not repeated

- On 28 cores the search tests passed; the fault needs 2 cores (`taskset -c 0-1`). On 1 core they passed too.

## Open work

[open-work.md](../open-work.md)
