# 8Z0Q — Choices of the capture timings spec

**Status:** proposed, 2026-11-23 (agent; draft 2 of [`specs/capture-timings.md`](../../specs/capture-timings.md)).

## Decision

The agent made these choices for [`specs/capture-timings.md`](../../specs/capture-timings.md). The
decisions of the user are in [ADR-MX8V](MX8V-decisions-of-the-user-on-capture-timings.md). Each item
gives its spec section, and "Not" gives the rejected alternative and its reason.

1. **Transport** (6.2 to 6.4): the field `timings` of `DiagnosticsMessage`; `capture_timings()`; one
   websocket message each second from the `_app_state_sender` loop. Not: a new topic (a second
   queue and pipe for the same rate).
2. **Switch details** (2): `log_capture_times`, default off; a shared scalar that `reset_for_start`
   keeps; route body, answer and 422; the effect at the next publish of the loop (later in a
   start-up or a `take_end`); live change and one boolean as deliberate differences. Not: fixed at
   open (each change needs a reopen of up to 15 s), or a list of steps (one branch each saves
   nothing).
3. **Off** (2 item 5): the message still comes; `summaries` [] at once. Not: no message (no "off"
   for a display).
4. **Kinds and cadence** (1.4): the kind comes from the job of the step; disk calls and awaited
   calls are work; `cadence` is `frame`, `second` or `event`. Not: a third kind `io`.
5. **Steps** (3.1, 5.4): the 24 ids and the values of `where`; a later native source uses the
   Media Foundation ids.
6. **Brackets** (1.4, 3.1): no time is in two samples; `camera_wait` and `gate_wait` are sums over
   the passes of a frame; `opencv_retrieve` comes out of `camera_wait`; `mkv_close` is `_finish`
   minus its enclosed steps. Not: one step for `read_frame` (it hides the decode).
7. **Threads** (5.1, 6.2): one `TimingControl` with a forwarding `clock()`; one `StepSet` for each
   writer instance; retire and merge by step id; one reader; a publish from another thread repeats
   the last summary, or sends `None` when there is none; a snapshot swap in
   the main process; a `step_set` argument for the shared preview methods. Not: one shared set for
   all instances (two writers after a stall), or a lock for each sample.
8. **Statistics** (5.2): nearest rank over the window between two summaries; `null` for `n` 0; over
   512 samples, the full `n` and the newest 512. Not: an interpolated percentile (other values in
   TypeScript).
9. **Budget** (5.3): one branch for each step when off; at most 10 clock reads for each frame plus
   one for each refused gate pass; summary at most 4 KiB.
10. **Delays** (4): `arrival_to_published` ends at the end of `ring_write` (no ring API change);
    `receive_to_draw` on one page clock. Not: a server time in each frame message (two clocks).
11. **Preview** (6.5): the wired sender measures; summaries for each connection; a group summary
    for the interim relay. Not: in `CameraGroupManager` (a second connection overwrites it).
12. **Age** (6.3): a summary older than 3 s, or of a closed group, is left out. Not: keep it for ever
    (a dead camera shows old numbers).
13. **Units** (5.2): ms with 3 decimals.
14. **Left out** (3.2): seven parts, each with a number from
    [ADR-3TYP](3TYP-timings-of-the-small-parts-of-the-frame-path.md).
15. **`seq`, `window_end_ns`, version** (6.1, 6.7). Not: a new version for each new step.
16. **Tile details** (7): `TileTimings`, a handle in the third constructor argument of `Tile`,
    `receivedAtMs` on `TileUpdate`, a pull by `takeSummaries()`, `ui_draw` only after a new image.
    Not: a push to the server (no reader there).
17. **Certify** (9): no reuse now.
18. **Test seams** (10.1): one injected clock, no real sleep or queue timeout, `node --test` and
    playwright. Not: vitest (a new dependency).

## Reason

1. The diagnostics message already goes each second, under its 32 KiB limit with about 14 kB used
   ([`unix-capture.md`](../../specs/unix-capture.md) 4.2). FreeMoCap imports skellycam as a library
   and mounts only `camera_router`.
2. A reopen takes up to 15 s plus an exposure search; one scalar read each second costs nothing.
7. After a stall, `end()` returns while the old writer thread lives (`camera_writer.py`); the control
   thread can call `_publish_diagnostics` through `_fail`.
9. The measured costs are in ADR-3TYP: under 0.05 µs for a clock read, 0.1 µs for a store.
16. The tile runs on the main thread of the page, so the receipt and the draw share one clock.
    FreeMoCap gets the tile with the folder `skellycam-ui/src/player/`.

For the other items, the reason is in the "Not" part of the item.

## Open work

See [open-work.md](../open-work.md).
