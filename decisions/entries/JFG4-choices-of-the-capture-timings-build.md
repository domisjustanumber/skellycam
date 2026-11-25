# JFG4 — Choices of the capture timings build: the capture side of `specs/capture-timings.md`

**Status:** proposed, 2026-11-25 (agent; builds steps 1 to 6 of section 11 of
[`capture-timings.md`](../../specs/capture-timings.md), accepted in
[ADR-8B85](8B85-acceptance-of-the-capture-timings-spec.md)).

## Decision

What is built: steps 1 to 6 of section 11 (the module `skellycam/core/capture_timings.py`, the switch and its route,
the brackets of table 3.1, the field `DiagnosticsMessage.timings`, `capture_timings()`, the websocket message, the
removal of `performance_data`), with the tests in `skellycam/tests/capture_timings/`.

The choices that the spec left open:

1. **The publish of a change.** The publish that reads a change to on starts the first window and sends
   `timings = None`; the next publish sends the first summary. The publish that reads a change to off sends None.
   A summary covers only a window with the switch on at its start and its end. Thus the first summary
   comes up to about 2 s after the change (the next publish, then one window), where spec 8.2 says
   "normally within 1 s". The other choice: a summary with n 0 at
   the first publish (within 1 s, but of an empty window).
2. **A loop made with the switch on** (a group made after a change to on, a restart) measures from its creation.
   Its publish at the end of the open sends the first summary, with the callback samples of the warm-up.
3. **The read budget (5.3).** At most 10 reads for each frame for the steps of cadence `frame`, plus one for each
   refused pass, plus 3 for each granted pass that gives no frame (the two gate reads and the end of the
   wait). A step of cadence `event` (`take_start`, `take_end`, `exposure_search_brightness`) adds its own
   2 reads on its frame. To stay in 10 on the OpenCV source with a take and a hash: brackets that follow one
   another share one read, so a few short lines (the flag counts, the dict of the ring fields) fall into the next
   bracket; and the OpenCV `camera_wait` ends at the read before the retrieve (`pre_ns`), with no read of its own.
   `should_record_frame_number` stays outside each bracket.
4. **Source steps.** A source names its steps in the class attribute `timing_steps`. `CameraLoop._new_source` gives
   each new source its own `StepSet` (`timing_set`). The loop keeps the sets of the other writer instances by role
   (`source`, `decode`, `writer`) and retires a set when the source closes, the decode stage stops, or
   `end` or `abandon` returns. A source that no loop measures uses `OFF_SET`, which is never on.
5. **Sets.** A set that another thread reads gets each step id at its creation, so its dict never changes size
   during a read. The set of a connection grows by key (group, camera or None, step) on its event loop thread.
   `StepSet.pending` carries the `published_ns` of each camera of a group message from `get_latest_ring_payload`
   to the start of its send (interim relay).
6. **Rounding.** Half up in integers: `ms = ((ns + 500) // 1000) / 1000`, and `window_s` the same way to 0.001 s. Thus
   the tile can give the same JSON (T-TIM-24); Python `round` rounds half to even.
7. **The main process.** The receipt time and the 3 s age rule use `capture_timings.main_clock_ns` (a test can
   replace it). A group with `_closing` set is a closed group. `set_log_capture_times` drops the kept summaries at
   each change, on and off.
8. **Preview summaries.** One `"preview"` summary for each (group, camera or None) that the connection measured,
   for each group that is still open; `seq` for each of them; the first window after a change to on gives none.
   `PreviewRelay` brackets: `preview_ring_read` is the whole `_newest_unsent` call that gives a frame;
   `preview_send` is the call of the send function that the relay gets.
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
13. **Proposed corrections of the spec** (marked in the spec text): 2 item 3, the path is
    `/skellycam/camera/timings` also in skellycam alone (`skellycam/app.py` mounts each router with the prefix
    `/skellycam`); 5.3, a granted pass with no frame reads the clock 3 times.

## Reason

1. Items 1 and 2: a summary of a window that was off for a part would hide the change; the spec's "takes effect at
   the next publish" holds in each case.
2. Item 3: the spec counts the reads of the loop thread for each frame; the event steps run on few frames (one
   trial of a search, a take start or end), and the take and the search never share a frame.
3. Items 4 and 5: no container grows for each frame, and no reader sees a dict change size; the retire rule of 5.1
   needs to know each set of each instance.
4. Item 6: one shape for Python and TypeScript (Q569).

## Alternatives rejected

1. The sets of the sources in a list that grows at each reopen: it grows for each reopen.
2. One read for the end of each bracket and one for the start of the next: 11 to 13 reads on the OpenCV source with
   a take and a hash, over the budget.

## Open work

[open-work.md](../open-work.md).
