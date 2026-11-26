# F4N7 — Decisions of the user on the pace tests of fix lane 6 and the search check with no answer (Q669 to Q673, Q675)

**Status:** absorbed into
[`specs/windows-capture.md#102-after-a-live-control-change-d32`](../../specs/windows-capture.md#102-after-a-live-control-change-d32),
[`specs/windows-capture.md#161-kinds`](../../specs/windows-capture.md#161-kinds),
[`specs/windows-capture.md#162-test-list`](../../specs/windows-capture.md#162-test-list),
[`specs/preview.md#91-kinds-and-helpers`](../../specs/preview.md#91-kinds-and-helpers),
[`specs/preview.md#92-test-list`](../../specs/preview.md#92-test-list),
[`skellycam/tests/capture/test_states.py`](../../skellycam/tests/capture/test_states.py),
2026-11-25 (commit to dom/log-cleanup; was accepted, 2026-11-24 (user; the coordinator asked the questions and relayed the answers)).

## Decision

The user decided these items on 2026-11-24. The words of the user: "Q669-Q677 yes". This entry records Q669 to
Q673 and Q675.

1. **Q669.** Apply the pace rule of [ADR-81RE](81RE-decisions-of-the-user-on-the-restore-file-the-take-rate-and-pace-tests.md)
   (Q619) to the real-time tests that failed on CI: split each one in two. A blocking test keeps the checks of the
   logic, with loose waits. A `pace` test keeps the bound of time: strict on a real machine, with the margin on CI.
   This includes T-CAP-82. Its limit of 100 ms on a gap is the ruling U16 of the user
   ([ADR-HB4Z](HB4Z-answers-u16-to-u23-of-the-user-to-the-review-of-the-3a-tests.md) item 1): on CI it warns, it
   does not block. [`windows-capture.md`](../../specs/windows-capture.md) 16.1 and 16.2 state it.
2. **Q670.** A preview test of a share of frames (the spec says 80 %): 40 % is the warning level on CI, and 80 %
   stays on a real machine. A blocking test checks the real rule of 4.3 of the preview spec: after each answer,
   the next camera message holds the newest frame at the send or one older. That rule does not depend on the
   speed. [`preview.md`](../../specs/preview.md) 9.1 and 9.2 (T-PRV-54) state it.
3. **Q671.** T-CAP-110 and the gate test (`test_a_camera_selected_again_shares_the_gate_with_a_restarted_camera`):
   conditions replace the fixed numbers of the author. T-CAP-110: the rows up to the frame count that the test
   reads when it arms the hang. The gate test: wait for frame 300 of camera A with a loose time limit, not 12 s,
   and the take must hold the gap of A. Nothing is weakened. [`windows-capture.md`](../../specs/windows-capture.md)
   16.1 and 16.2 state it.
4. **Q672.** The stall test with THREAD workers (`test_the_watch_ends_no_healthy_camera_under_load[thread]`): its
   bound on the gap moves to a `pace` test. [`windows-capture.md`](../../specs/windows-capture.md) 16.1 states it.
5. **Q673.** On the virtual test clock, each camera loop thread is a participant from its start, as
   [ADR-DC43](DC43-choices-of-fix-lane-5.md) did for the control thread with `ClockQueue`. T-CAP-86 gets failure
   diagnostics in a `finally` (the virtual time, the clock states, the state and the frame count of each camera,
   the events of the reopened camera) before its fix is decided. Runs on 2 cores in WSL give the proof.
   [`windows-capture.md`](../../specs/windows-capture.md) 16.1 states the clock rule.
6. **Q675.** This item belongs to the lane before this one, the lane of ADR-0R76. When the last set of an exposure search gives no answer in 6 s,
   the check counts only frames from the time-out on. The exact rule of Q666
   ([ADR-JWZ1](JWZ1-decision-of-the-user-on-the-exact-skip-after-a-search.md)) applies only when the last set
   answers. [`windows-capture.md`](../../specs/windows-capture.md) 10.2 states it: its third bullet of the search
   cites [ADR-0R76](0R76-choices-of-the-exact-skip-after-a-live-change.md) item 4 and this entry.

The choices of the agent that build these items are in [ADR-B7YV](B7YV-choices-of-fix-lane-6.md) (proposed).

## Reason

1. CI run 45401541234 of the Capture workflow failed on 13 tests on macOS and on one test on Linux and Windows.
   The product code did not change between that run and the run before it: only tests changed. The macOS runner
   was starved: the fake replaced 104 to 327 waiting frames in one camera, the product warned "24.32 fps" for a
   fake at 30 fps, and a plain wait of 2 s returned 141 ms late.
2. "A red workflow should mean a real fault" (Q619).
3. T-CAP-13 on macOS: the first camera started its open about 6 s of virtual time after the second camera. The
   virtual clock took a thread only at its first wait, so a camera loop that did not wait yet did not hold the
   time.
4. Q675: with no answer, the frames before the time-out are frames of the exposure of the last trial.
