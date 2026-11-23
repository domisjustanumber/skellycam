# MX8V — Decisions of the user on capture timings

**Status:** accepted, 2026-11-23 (user; Q565 to Q571, to which the user answered "agree to all"; Q576 and
Q577, agreed; Q578, the user refused "always on").

## Decision

The request of the user (2026-11-23): "I want to be able to see capture timings in the realtime pipeline UI
in FreeMoCap, that is - any codec work - anything else you think might take more than 1ms to complete". The
user decided these items on 2026-11-23. They are not built. The spec
[`specs/capture-timings.md`](../../specs/capture-timings.md) (draft 1) applies them, and its section 14 gives
each one.

1. **Q565.** The split of the work: skellycam measures and publishes; FreeMoCap displays. The spec covers the
   skellycam side and the interface that FreeMoCap reads.
2. **Q566.** A fixed list of named steps. Each step that is codec work (a JPEG encode or decode, also the
   hidden decode in OpenCV `retrieve()`), and each other step that can take more than 1 ms, is in the list.
   A step known to be far below 1 ms can be left out, with the reason and the measured number.
3. **Q567.** A step that is a wait (camera wait, gate wait, queue wait) is marked apart from a step that is
   work. Thus a display never adds waits into "time spent".
4. **Q568.** skellycam does not send one event for each frame. Each process keeps the numbers of each step
   and publishes a summary once per second: for each camera and each step, `n`, p50, p95 and max, in
   milliseconds.
5. **Q569.** One shared shape for each summary (capture process, recorder thread, main-process preview path,
   UI). Thus one display code path shows them all.
6. **Q570.** An end-to-end delay is also given: from `arrival_ns` to `published_ns` (the ring commit), from
   `published_ns` to the start of the websocket send, and in the UI to the draw where the clocks permit it.
   The spec states the clock of each part, and the parts that cannot be compared across processes or
   machines.
7. **Q571.** The spec now. The code only after the user accepts the spec and after branch `dom/fix-lane-3`
   merges.
8. **Q576.** In FreeMoCap the capture steps appear as one "capture" block in the per-stage table of the
   Pipeline metrics window, fed by the summaries of each second. No per-frame bars in the timeline for
   capture steps.
9. **Q577.** skellycam builds the measurement and the interface first. The FreeMoCap display is work of the
   freemocap session, and it comes only after FreeMoCap moves to the new skellycam. Until then the numbers
   are readable from the skellycam websocket and a Python call. No display in skellycam-ui.
10. **Q578.** The measurement is not always on. The words of the user: "this must be toggle-able like all
    other metrics in skellytracker". The measurement has an on and off switch, as close to the pattern of
    skellytracker and of FreeMoCap `log_pipeline_times` as the process model of skellycam permits, and the
    host app can set it through the API. The details of the switch are agent choices
    ([ADR-8Z0Q](8Z0Q-choices-of-the-capture-timings-spec.md) item 3).

## Reason

The user gave no reason other than the words above. The facts that the questions stated:

1. Q565, Q576: the Pipeline metrics window of FreeMoCap has a per-stage table, and its timeline shows
   per-frame events. FreeMoCap mounts `camera_router` of skellycam and holds a `CameraGroupManager`.
2. Q566: the request names codec work and each step over 1 ms.
3. Q567: a wait is not work of the thread that waits.
4. Q568: the camera processes already send one diagnostics message each second to the main process.
5. Q571: `dom/fix-lane-3` changes `camera_loop.py`, `camera_group.py` and `camera_group_manager.py`.
6. Q577: FreeMoCap imports the old skellycam (`skellycam-sfn26-pins`) today. That skellycam has no
   capture timings.
7. Q578: FreeMoCap has `log_pipeline_times: bool = False`. A skellytracker run has no timing span on by
   default.

## Open work

See [open-work.md](../open-work.md).
