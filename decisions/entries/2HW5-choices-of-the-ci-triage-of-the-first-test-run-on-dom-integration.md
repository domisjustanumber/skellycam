# 2HW5 — Choices of the CI triage of the first test run on dom/integration

**Status:** proposed, 2026-11-26 (agent; the CI triage lane of the run of `test.yml` on 32eb69e20, CI run
45872128301; waits for the user).

## Decision

These are the choices of the agent for the failures of that run. Each change is in the tests. No product file
changes.

1. **The certify ring watch holds the virtual clock while it is behind.** On a virtual clock, the thread of
   `session.RingWatch` (certify) is a participant from its start (`VirtualClock.expect`). After each read, the
   time does not move while the head of its ring is 8 frames or more past the frame that it asked for. It
   leaves the clock at its end. In the open step of certify, the thread that opens the rings also holds the
   time from the open of each JPEG ring until a watch reads it: the session looks for new rings only each 5 ms
   of real time. A ring that closes before a watch reads it holds nothing. `capture_session.install_watch_clock`
   does this for each `CaptureApp` on a virtual clock, with the helper `hold_clock_while_behind` (a gate whose
   `shut` reads the ring head). A second app in one test wraps the product functions, as `install_gate_probe`
   does; the watch then follows the clock of the newest app. No certify test has two apps.
   The hold from the ring open hides the product race of item 5 in each THREAD certify test. It is acceptable
   only with T-CERT-151, which covers that race with PROCESS workers.
2. **The reader of T-RING-40 holds the clock in the same way**, while it is 500 frames behind the JPEG ring
   (the ring has 1,000 slots). Each check of T-RING-40 stays.
3. **T-REC-41 waits for 60 decoded frames.** With a BGR ring, the test records 60 frames, then also waits until
   the decode stage wrote 60 BGR frames with an image, and then stops. The check "60 or more decodes, one decode
   per BGR write" stays. Section 8.3 of [`frame-ring.md`](../../specs/frame-ring.md) lets the decode stage fall
   behind the recorder.
4. **T-RING-38 accepts `ready` or `dead` at its start.** The fake stops after frame 200, so the camera ends
   (`dead`) soon after `ready`. The start of the test waits for `ready` or `dead`, as
   `capture_session.one_camera` does for such a camera. The test opens its views of the rings just after the
   apply, before that wait: the group watch can close the rings of a camera whose loop ended. Each check of
   T-RING-38 stays.
5. **The failure of `test_t_cert_92_a_hang_at_the_open` on windows-2025 is a product race. The fix waits for
   the user.** T-CERT-151 (`test_t_cert_151_a_ready_camera_with_no_ring_watch_at_the_judge`) is its regression
   test: a strict `xfail` until the fix lands, with the marker `capture_timing` (PROCESS workers, real time).
   The check "no `not-reached` row for a camera that can go on" of `assert_not_reached` also gives the rows of
   that camera in its message. The race: `CameraGroup.start` opens the rings only after the hung camera fails
   (5 s); the good camera waited in `waiting` and is `ready` about 1 ms after its ring opens; the session judges
   the open before its next look for new rings (each 5 ms), so the camera has no `RingWatch`; `judge_open` then
   leaves it out of `live` with no reason, and its later checks become one `not-reached` row. The file and line
   of each step are in [the evidence file](../evidence/2HW5-ci-triage-evidence.md).
6. **The pace failure on windows-2025 is a pace result.** `test_a_slow_stop_has_a_gap_only_on_the_last_row[0.2-60]`
   (marker `pace`, a non-blocking step) found one `camera_gap` of one frame on row 17 of 30. This is the busy-machine
   case of Q619 that its marker names. No change.

## Reason

1. The fake cameras of a THREAD session run on the virtual clock. The time moves when each camera loop waits,
   so a loop can run seconds of virtual time in a few milliseconds of real time. A thread that reads a ring in
   real time and is no participant can then wait for the CPU while the ring laps it. A JPEG ring holds 1 s of
   frames ([`frame-ring.md`](../../specs/frame-ring.md) 3.7). The real cameras of the product give 30 frames
   each second, so this lap is a fault of the test clock, not of the product.
2. In the certify tests, the watch then missed the 30 hashed frames of D-11. The product then writes
   `native-jpeg:source-equals-ring` `not-run` `ring-lapped`, as section 4.4 of
   [`certify.md`](../../specs/certify.md) states, and rule 4 of the summary item (section 3.4) makes the item
   `partial`. The product was correct. The tests expect `pass`, which is correct for a watch that keeps up.
3. Items 1 and 2 keep the time of the fake cameras within a known number of frames of the reader, whatever the
   pace of the machine. A cap on the speed of the virtual clock would slow each test and still depend on the
   pace.
4. Items 3 and 4 are waits that the pace of the machine no longer decides. No check is removed or loosened.
5. Item 5: no spec rule says what certify does with a camera that is `ready` but has no ring watch. The fix is
   a choice for the user (spec and tests before code). The regression test fails today and passes after a fix
   that does not depend on the time of a look of `watch_rings`.

## Evidence

The logs of CI run 45872128301, runs of copies of 32eb69e20 in WSL Ubuntu 24.04 on 1 or 2 cores, and runs on
Windows. An independent review found the race of item 5 and its probe (the look of `watch_rings` each 0.25 s).
See [the evidence file](../evidence/2HW5-ci-triage-evidence.md).

## Alternatives rejected

1. A `pace` marker for the failing tests: their checks are logic checks, not bounds of time (section 16.1 of
   [`windows-capture.md`](../../specs/windows-capture.md)).
2. A larger ring for certify, or a start of the watch at the oldest slot: a product change for a fault of the
   test clock.
3. The decode stage as a participant of the clock: T-RING-38 needs a decode stage that falls behind.

## Open work

[open-work.md](../open-work.md)
