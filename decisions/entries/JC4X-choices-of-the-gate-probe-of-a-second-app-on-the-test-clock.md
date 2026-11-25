# JC4X — Choices of fix lane 8: the gate probe of a second app on the test clock (T-UNX-98)

**Status:** proposed, 2026-11-25 (agent; builds item 3 of
[ADR-2SX2](2SX2-acceptance-of-the-choices-of-fix-lane-7-and-its-follow-ups.md)).

## Decision

1. **The cause is in the test helpers**, not in the product and not in the lane 7 clock rules. The tests of
   `test_restore_store.py` (T-UNX-96 to T-UNX-101) make two servers (`CaptureApp`) in one test, with one
   `monkeypatch`. Each server calls `capture_session.install_gate_probe`, so the second wrapper of
   `CameraOrchestrator.should_grab_by_id` wraps the first wrapper. The `shut` of the second wrapper then calls the
   first wrapper, and that calls `VirtualClock.gate`. `shut` runs under the lock of the clock (a re-entrant lock),
   in the thread that moves the time, so the waiting camera loop got the state of the gate ("run" or "gate") in
   place of its wait. With no wait left, `_advance` moves the time no more, also by forced steps, and the loop
   waits in `wait_until` for good. The camera worker thread is not a daemon (`camera_worker.py`), so the pytest
   process cannot end. The docstring of `VirtualClock.gate` already says that `shut` must not call the clock
   ([ADR-7GC1](7GC1-choices-of-the-gate-on-the-test-clock-and-the-end-of-t-cap-05.md) item 1).
2. **The fix.** `install_gate_probe` keeps the product probe on its wrapper (`product_probe`), and a second install
   wraps that product probe, not the wrapper of the first app. So `shut` never calls the clock. One self-test in
   `test_helpers.py`: two installs, a loop at a shut gate, a thread that runs and then leaves, and a thread that
   waits on the clock; the wait must end. No product code changes. The camera thread stays non-daemon, and no
   pytest exit time-out is added.
3. **The other test** (`test_status_locks.py::test_a_live_but_slow_holder_and_torn_json_never_raise[writes with no
   lock]`, marker `capture_timing`): evidence item 13. No change.

## Reason

1. Item 1: the log of each state change of the clock in a failed run shows the last change of the stuck loop: the
   loop set its wait in `wait_until`, and then `gate`, called from `should_grab_by_id` in the same thread, set
   "run" (evidence item 10).
2. Item 2: a fix of the wrapper is the root. A check in `VirtualClock.gate` for a nested call would hide another
   wrong `shut`.

## Evidence

Items 7 and later of [evidence/4CAF-fix-lane-8-evidence.md](../evidence/4CAF-fix-lane-8-evidence.md).

## Alternatives rejected

1. A daemon camera thread, or a time-out at the end of pytest: they hide the fault, and they need the user.
2. One install of the probe for each process (a module flag): the second app could have another clock.

## Open work

[open-work.md](../open-work.md)
