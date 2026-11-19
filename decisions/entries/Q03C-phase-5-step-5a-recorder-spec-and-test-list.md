# Q03C — Phase 5 step 5a spec and test list: the new video recorder

**Status:** proposed, 2026-11-19 (agent; commit to dom/recorder; revised on 2026-11-19 and 2026-11-20).

## Decision

[`specs/recorder.md`](../../specs/recorder.md) is the proposed spec of step 5a, with its test list
(T-REC-01 to T-REC-37, the connection tests T-REC-40 to T-REC-49, and T-REC-STALL, T-REC-KILL,
T-REC-FSYNC, T-REC-GIL). It follows R1 to R12 of
[ADR-VPF8](VPF8-phase-5-recorder-decisions.md), M1 to M10 and C1 to C7 of
[ADR-J3QP](J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md), the skellyfileformat
SPEC draft v2 rule by rule, the plan, [`specs/frame-ring.md`](../../specs/frame-ring.md) and
[`specs/windows-capture.md`](../../specs/windows-capture.md). The revision of 2026-11-19 applies
M1 to M10, C1 to C7 and the faults of an independent review (section 15.5 of the spec). The user
reviews it before any code (R12).

Section 13 of the spec is the one list of proposed format changes for the recorder and the player:
F-1 the `missing` flag, the `missing=` count and the placeholder; F-2 the short file; F-3 two
exceptions to unchanged bytes; F-4 the completion of a take by its own writer; F-5 the codes
`camera_dead`, `camera_file_short`, `take_error`; F-6 `key_origin` `provisional`; F-7 the lock on
each OS; F-8 equal player times; F-9 when a player checks the block count; F-10 a `missing` row in a
player. Section 14 lists the edits of `specs/windows-capture.md` that the connection commit makes.

Agent choices (section 16 of the spec, marked [agent n] in the body):

1. Package `skellycam/core/take_recorder/`.
2. A take level and a camera level.
3. `give` waits while the queue is full; the stall limit counts one wait.
4. Queue size ⌈3 s × rate⌉ items.
5. A named non-daemon writer thread.
6. The MKV through a Python file object.
7. A row is written after its block is in the file; offsets from `tell()`.
8. The CSV unbuffered, one write per line.
9. fsync once per second on the writer thread.
10. (now C3)
11. The camera writer pads with placeholders and writes its `# end` line; frame count from the
    orchestrator.
12. The completion of a short file after the join.
13. `last_frame` is the last row that is not `missing`.
14. The stop response fields from the CSVs.
15. The lock calls and the timeout at the end.
16. An empty take folder; HTTP 422 and 409.
17. `purpose` `motion_capture`.
18. `clock_hz` empty.
19. `group_position` by `camera_index`.
20. The nominal rate as a fraction.
21. The hand-built placeholder (minimal tables) and its SOF compare by size, components and H/V.
22. The layout from the camera's last good frame before the take; a bounded wait only without it.
23. The capture info values; `input_range` in the log.
24. `give_missing` and the padding of `end`.
25. The end wait margin of 5 s; stage `recording`.
26. Track size from the mode; `stored_px` from the first camera block.
27. Test markers, benchmark variables and frame sizes.
28. The conformance adapter.
29. `exposure_us` from the log2 value.
30. `DISCONTINUITY` and `DHT_INSERTED` not in the CSV.
31. (now M5, second case)
32. The stall watch of a pull source counts from the end of the last wait (in `give` or at the gate).
33. `needs_new_player` and HTTP 409 for new takes in the playback API.
34. The workflow `recorder.yml`.

No question is open. The questions of the first draft are answered by C1, M1 and C4; Q1 of the
second draft (a write error is a second short-file case) by the user on 2026-11-20 (M5 of
[ADR-J3QP](J3QP-missing-frames-as-black-placeholders-and-the-end-of-a-take.md)). A third revision
on 2026-11-20 applies the fixes of a cross-check against the player spec.

## Reason

- R12: a spec and a test list before any code. R6: the format proposals go to the user.
- Each choice is the smallest one that makes the spec complete.

## Open work

See [open-work.md](../open-work.md).
