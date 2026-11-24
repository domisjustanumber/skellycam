# B7YV — Choices of fix lane 6: one run for the two halves, nominal values, loose checks, the loop threads on the test clock

**Status:** proposed, 2026-11-24 (agent; builds the decisions of the user in
[ADR-F4N7](F4N7-decisions-of-the-user-on-the-pace-tests-of-fix-lane-6.md)).

## Decision

1. **One run.** `one_run(key, run)` of `skellycam/tests/pace.py`: the blocking test and the `pace` test of a split
   test check the data of one run in a session. A CI step with `-m "not pace"` or `-m pace` makes its own run.
   `bound(nominal, strict)`: the nominal value plus the strict tolerance times the margin.
2. **Nominal values** ([`windows-capture.md`](../../specs/windows-capture.md) 16.1). A gap between two frames of
   one camera: 1/30 s, so the limit of 100 ms is 233 ms on CI. The arrivals of one row of two cameras: 0 (300 ms
   on CI). The exit of T-CAP-40: the limit of 5 s, tolerance 2 s. T-CAP-04: 2.0 s, tolerance 0.1 s. The pause of
   the loop passes under load: 1/30 s (1 s is 2.93 s on CI). n camera messages in a window
   ([`preview.md`](../../specs/preview.md) 9.1): the time to the n-th message, nominal n / 30 s (T-PRV-15: 0.97 s
   on CI; T-PRV-16: 4 s).
3. **Loose checks of the blocking halves.** A gap of 100 ms: at most 1 s (a hung call that holds the gate stops
   the other camera for the 5 s of the limit). The exit of T-CAP-40: at most 10 times the limit. T-CAP-04: `None`,
   not before 1.9 s, at most 20 s, and the share of the core under 2 % (an early return or a spin is no pace
   effect). A count of messages: a wait for the n-th message, limit 10 times the window. In place of a share of
   frames: more camera messages than the safety net can give (more than the seconds of the run plus 2).
4. **T-CAP-110** (Q671). The row at the arm is `frame_count` minus `first_recording_frame_number`, read just before
   `arm_hang()`. The loop sets `frame_count` after it gives the frame to the writer. T-CAP-110 has no `pace` test.
5. **The gate test** (Q671). A ring watcher of A; a wait for source frame 330 of A (frame 300 comes after the gap,
   and 30 more give rows after it), limit 100 s. The take holds the gap: one pair of rows of A, source frame 299 or
   earlier then 300 or later, at least 0.49 s apart. In place of the bound of 100 ms: the median difference of the
   arrivals of the rows after the gap row is under 250 ms (half the gap), with at least 5 rows. A camera B that does
   not wait for A is ahead by about the gap in each of those rows.
6. **The stall test** (Q672). Only the THREAD case moves its gap bound to a `pace` test.
7. **T-PRV-54** (Q670). Four rings, 5 s. `WsClient(rings=...)` notes `FakeRing.last` at each answer. The sender
   reads the ring after the answer, so the rule holds at each pace. The count check of item 3 stops a sender that
   sends only by the safety net.
8. **The loop threads on the clock** (Q673). `VirtualClock.expect(thread)`: a thread that is not started is a
   participant until it waits on the clock, ends or calls `leave`; until then only forced steps move the time.
   `capture_session.install_loop_clock` calls it in `CameraWorker.start` for a THREAD worker; `forget` drops a
   thread whose start raised. The gate probe takes an expected thread. The close of the fake still leaves the clock.
9. **T-CAP-86 diagnostics** (Q673), in a `finally`: `VirtualClock.describe()`, the state, gate count and taken
   frames of each camera, the last relay messages, the events of the reopened camera, the clock at three points,
   and the pass, time and gate counts at each new relay message. T-CAP-13 gives the times of the opens.
10. **CI.** No change of `capture.yml`: its pace step (`-m "pace and ..."`, margin 3) and its blocking steps
    (`not pace`) take the new tests. `test_pace_marker.py` lists each new test.
11. **T-PRV-54 answers late** (it replaces the answer at once of item 7). After each camera message, the writer
    of the ring writes 5 more frames and pauses (`PacedWriter.stop_after`, as in T-PRV-07). Then the client
    answers. Thus the newest frame at the send is the pause frame, and the check is exact at each pace. With the
    answer at once, the test passed for a sender of the next frame in sequence and for a sender of the newest frame
    minus 2. With the late answer, the test fails for each of these two changes of `preview_relay.py`.
12. **Not changed.** The safety-net counts (4 to 7) of T-PRV-09 and T-PRV-13 and the answer windows of T-PRV-15 stay
    blocking: they did not fail on CI.
13. **The share level** (Q690 of [ADR-B1DE](B1DE-decisions-of-the-user-on-the-share-level-and-the-test-clock.md)).
    `share_level()` of `skellycam/tests/preview/test_ws_flow.py`: `SHARE` (0.8) when `margin()` is 1, `CI_SHARE`
    (0.4) when it is above 1. Two small tests check 0.8 with no setting, and 0.4 at margin 3 and at margin 10.

## Reason

1. One run keeps the time of a local run, and the two halves see the same facts.
2. 16.1: the margin multiplies only the part of a bound past its nominal value.
3. Each loose check still fails for the fault of its test.
4. The count at the arm is a fact of the run, not a rate of the machine.
5. A wait for a frame replaces a sleep that a slow runner makes too short. A median does not move for a few rows
   that a busy machine moves.
6. Q672 names only THREAD workers; with PROCESS workers the load does not run in the camera processes.
7. The control thread got the same rule in [ADR-DC43](DC43-choices-of-fix-lane-5.md) item 1.

## Evidence

[evidence/B7YV-fix-lane-6-evidence.md](../evidence/B7YV-fix-lane-6-evidence.md).

## Alternatives rejected

1. Two runs, one for each half: twice the time, for the same facts.
2. A share of frames at a low level in the blocking half: still a rate of the machine.
3. A patch of `ManagedThread.start`: the other workers of the registry are no camera loops.
4. A fix of T-CAP-86 now: Q673 asks for the diagnostics first. They show a fault of the test clock (evidence item 3).
