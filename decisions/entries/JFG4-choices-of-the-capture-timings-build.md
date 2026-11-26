# JFG4 — Choices of the capture timings build: the capture side of `specs/capture-timings.md`

**Status:** proposed, 2026-11-25 (agent; the items that the user decided are in
[ADR-GZS7](GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md); builds steps 1 to 6 of section 11 of
[`capture-timings.md`](../../specs/capture-timings.md), accepted in
[ADR-8B85](8B85-acceptance-of-the-capture-timings-spec.md)).

## Decision

What is built: steps 1 to 6 of section 11 (the module `skellycam/core/capture_timings.py`, the switch and its route,
the brackets of table 3.1, the field `DiagnosticsMessage.timings`, `capture_timings()`, the websocket message, the
removal of `performance_data`), with the tests in `skellycam/tests/capture_timings/`.

The choices that the spec left open:

1. Accepted by the user (Q837): moved to [ADR-GZS7](GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md).
2. **A loop made with the switch on** (a group made after a change to on, a restart) measures from its creation.
   Its publish at the end of the open sends the first summary, with the callback samples of the warm-up.
3. Accepted by the user (Q838): moved to [ADR-GZS7](GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md).
4. **Source steps.** A source names its steps in the class attribute `timing_steps`. `CameraLoop._new_source` gives
   each new source its own `StepSet` (`timing_set`). The loop keeps the sets of the other writer instances by role
   (`source`, `decode`, `writer`) and retires a set when the source closes, the decode stage stops, or
   `end` or `abandon` returns. A source that no loop measures uses `OFF_SET`, which is never on.
5. **Sets.** A set that another thread reads gets each step id at its creation, so its dict never changes size
   during a read. The set of a connection grows by key (group, camera or None, step) on its event loop thread.
   `StepSet.pending` carries the `published_ns` of each camera of a group message from `get_latest_ring_payload`
   to the start of its send (interim relay).
6. Accepted by the user (Q840): moved to [ADR-GZS7](GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md).
7. **The main process.** The receipt time and the 3 s age rule use `capture_timings.main_clock_ns` (a test can
   replace it). A group with `_closing` set is a closed group. `set_log_capture_times` drops the kept summaries at
   each change, on and off.
8. Accepted by the user (Q839): moved to [ADR-GZS7](GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md).
9. **The message loop.** `_app_state_sender` sleeps `CAPTURE_TIMINGS_INTERVAL_S` (1.0, as before) and sends the
   message after the app state check. A test that patches the interval also runs the state check faster.
10. **The route** uses `StrictBool`: `"yes"`, `null`, `1` and a missing field get 422. It answers the value of the
    manager after the set.
11. **Test seams.** The loop tests drive a real `CameraLoop` on the test thread with a virtual clock and fakes that
    move it (`loop_harness.py`). The fixture of T-TIM-24 is `skellycam/tests/capture_timings/summary_fixture.json`;
    the TypeScript test of step 8 reads the same file. The real Media Foundation bracket runs on the stand-ins of
    `mf_standins.py` (case `timings`, Windows only).
12. **Faults.** A fault while the loop builds its timings sends `timings = None` with the diagnostics dict (one log
    line). A fault while the server builds or encodes the `capture_timings` message sends no message that second
    (one log line); it never sets the kill flag. `PreviewTimings` drops the keys and the `seq` of a group that is
    no longer open.
13. Accepted by the user (Q838): moved to [ADR-GZS7](GZS7-decisions-of-the-user-on-the-capture-timings-build-and-the-merge-order.md).

## Reason

1. Item 2: spec 5.2 says that the publish at the end of an open holds the callback samples of the warm-up.
2. Items 4 and 5: no container grows for each frame, and no reader sees a dict change size; the retire rule of 5.1
   needs to know each set of each instance.
3. Item 12: a fault of the measurement must not stop the diagnostics or the app.

## Alternatives rejected

1. The sets of the sources in a list that grows at each reopen: it grows for each reopen.

## Open work

[open-work.md](../open-work.md).
