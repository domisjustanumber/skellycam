# 8Z0Q — Choices of the capture timings spec

**Status:** proposed, 2026-11-23 (agent; draft 1 of [`specs/capture-timings.md`](../../specs/capture-timings.md)).

## Decision

The agent made these choices for [`specs/capture-timings.md`](../../specs/capture-timings.md). The
decisions of the user are in [ADR-MX8V](MX8V-decisions-of-the-user-on-capture-timings.md). Each item
gives its spec section, and the line "not" gives the rejected alternative.

1. **Transport** (6.2 to 6.4): a new field `timings` of `DiagnosticsMessage`, once per second; the
   call `CameraGroupManager.capture_timings()`; one websocket JSON message `capture_timings` once per
   second from the loop of `_app_state_sender`. Not: a new pubsub topic (a second queue and pipe for
   the same rate).
2. **`performance_data` goes** (6.4): its module, `get_latest_performance_data`, its message type,
   its tests. No code sends it. Not: reuse its name for the new shape (an old client would parse the
   new shape wrongly).
3. **Switch** (section 2): `log_capture_times: bool`, default `False`, held by `CameraGroupManager`
   for the whole app; one shared scalar with no lock in each `CameraStatus`; the loop reads it once
   per window, so a change applies within about 1 s with no new open; set by
   `set_log_capture_times(on)` or `POST /camera/timings`. Not: a field of `CameraConfig` (apply rules
   and reopen test of each camera), or an environment variable (no change while the app runs).
4. **Off** (2 item 5): the message still comes each second, with `"summaries": []`. Not: no message
   (a display cannot show "timing off").
5. **Steps** (1.4, 3.1, 5.4): the ids, `where` and `kind` of table 3.1. A wait is a wait for another
   part (camera, other cameras, recorder queue, network). Disk work is work. `preview_send` is a
   wait (an `await`). Not: a third kind `io` (the user decided two kinds).
6. **OpenCV split** (3.1): `camera_wait` is `read_frame` minus `retrieve()`; `opencv_retrieve` is
   work. Not: one step for `read_frame` (it hides the decode).
7. **Gate wait** (3.1): one sample for each frame, 0 with no refused pass. Not: one sample for each
   refused pass (`n` would count sleeps).
8. **Buffers** (5.1): for each step a fixed `array("q")` of 512 durations and a total; one writer
   thread for each buffer; the reader takes the samples between two totals; the `CameraLoop` owns the
   buffers. Not: a lock for each sample, or a reset by the reader (a race).
9. **Statistics** (5.2): nearest rank over the window between two publishes; `null` when `n` is 0;
   over 512 samples, the full `n` and the newest 512. Not: an interpolated percentile (other values in
   TypeScript, and a value that no sample had).
10. **Budget** (5.3): off, one branch for each step; on, at most 10 clock reads for each frame in the
    loop thread and 2 for each step elsewhere, no growing container, at most 4 KiB for each summary.
    Not: an event for each frame (refused by Q568).
11. **Delays** (section 4): `arrival_to_published` ends at the end of `ring_write` (no change of the
    ring API); `published_to_send`; `receive_to_draw` with `performance.timeOrigin +
    performance.now()`. Not: a server time in each frame message (two clocks with an unknown offset).
12. **UI** (section 7): the two workers measure and post one summary each second to a store; the
    flag comes from `capture_timings`; nothing goes to the server. Not: a post for each duration (one
    more message for each frame).
13. **Preview** (6.5): the wired sender measures; one summary for each connection, only in its
    message. Not: in `CameraGroupManager` (a second connection overwrites it).
14. **Left out** (3.2): status update, frame decision, decode hand-over, rate checks, callback
    waiting place, SOF parse, control thread, preview tick. `arrival_to_published` holds the loop
    parts. Not: a step for each part (more clock reads for parts far below 1 ms).
15. **Age** (6.3): the call leaves out a summary older than 3 s and a closed group. Not: keep it for
    ever (a dead camera shows old numbers).
16. **Units** (5.2): milliseconds, 3 decimals. Not: integer microseconds (FreeMoCap shows ms).
17. **Version** (6.7): 1; a new step id or field keeps it; a change of a name, unit, type or meaning
    increases it. Not: a new version for each step (each display breaks).
18. **FreeMoCap** (8.1): the note recommends `log_capture_times` from `log_pipeline_times`.
19. **Certify** (section 9): no reuse now.

## Reason

1. The diagnostics message already goes each second, under its 32 KiB limit with about 14 kB used
   ([`unix-capture.md`](../../specs/unix-capture.md) 4.2). FreeMoCap imports skellycam as a library
   and mounts only `camera_router`, so it needs a Python call.
3. FreeMoCap has `log_pipeline_times: bool = False`, and skellytracker has no span on by default
   (Q578). A scalar that the loop reads once per second costs nothing on the frame path.
8. A lock or a reset on the frame path adds a wait or a race.
10. At 60 fps a frame has about 16 ms; 10 clock reads are far below it [NV; M-TIM-1 measures it].
11. The clocks of Python and of the browser have different origins.
18. The user then has one switch.
19. Certify measures the camera and the clock for a report; these timings measure the cost of each
    step, live.

The other items: the reason is in the "Not" line of the item.

## Open work

See [open-work.md](../open-work.md).
