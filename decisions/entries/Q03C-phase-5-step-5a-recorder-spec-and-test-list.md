# Q03C — Phase 5 step 5a spec and test list: the new video recorder

**Status:** proposed, 2026-11-19 (agent; commit to dom/recorder).

## Decision

[`specs/recorder.md`](../../specs/recorder.md) is the proposed spec of step 5a, with its test list
(T-REC-01 to T-REC-37, T-REC-38 to T-REC-45 for the connection, and T-REC-STALL, T-REC-KILL,
T-REC-FSYNC, T-REC-GIL). It follows R1 to R12 of
[ADR-VPF8](VPF8-phase-5-recorder-decisions.md), the skellyfileformat SPEC draft v2 rule by rule, the
plan, [`specs/frame-ring.md`](../../specs/frame-ring.md) and
[`specs/windows-capture.md`](../../specs/windows-capture.md). The user reviews it before any code
(R12).

It proposes six changes to skellyfileformat (section 13 of the spec): P-1 a `missing` flag and
`missing=` count for a row with no image; P-2 container times that count blocks; P-3 the completion
of one camera pair during a take; P-4 the manifest codes `camera_dead` and `take_error`; P-5 the
`key_origin` value `provisional`; P-6 the lock call on each OS. Section 14 lists the sentences of
`specs/windows-capture.md` that the connection commit changes.

An agent made these choices where the sources leave a gap. Section 16 of the spec states each one,
and the body marks each one [agent n]:

1. Package `skellycam/core/take_recorder/`.
2. A take level (main process) and a camera level (camera process).
3. `give` waits while the queue is full; the stall limit counts one wait.
4. Queue size ⌈3 s × rate⌉ frames.
5. A named non-daemon writer thread; `None` ends it.
6. The MKV through a Python file object.
7. A row is written after its block is in the file; offsets from `tell()`.
8. The CSV unbuffered, one write per line.
9. fsync once per second on the writer thread.
10. `camera_key` from `camera_id`; the label starts with `camera_id`.
11. The main process writes each footer and each missing row; the frame count is the largest row
    count.
12. The completion: cut to equal rows and blocks, missing rows, `# repair`, `# end`.
13. The last real frame is the last row with a block.
14. The stop response fields from the CSVs.
15. The lock calls, 10 s limit, and the timeout cases.
16. An empty take folder; HTTP 422 and 409.
17. `purpose` `motion_capture`.
18. `clock_hz` empty.
19. `group_position` by `camera_index`.
20. The nominal rate as a fraction.
21. The recorder gets the bytes before the DHT insertion.
22. The capture info values; `input_range` in the log.
23. The playback list leaves out new takes.
24. A stall or a write error ends the take for each camera.
25. The wait for each camera at the end, then a hard end.
26. Track size from the mode; `stored_px` from the first JPEG.
27. Test markers, benchmark variables and frame sizes.
28. The conformance adapter and its expected results.
29. `exposure_us` from the log2 value.
30. `DISCONTINUITY` and `DHT_INSERTED` not in the CSV.
31. The status member `recorder`.
32. The fields of `CameraTakeResult`; a hard end when the writer does not finish.
33. A frame with another rotation raises `ValueError`.

Questions for the user (section 17 of the spec, each with a recommended answer):

- Q1: between 5a and 5b, a record start with a microphone gets HTTP 422 (recommended), or records
  video only with a warning.
- Q2: the container time counts the blocks (recommended), or the rows.
- Q3: a CI change runs the 5a tests on Windows, Linux and macOS on each push to `dom/recorder`
  (recommended), or no CI change.

## Reason

- R12: a spec and a test list before any code. R6: the proposals go to the user.
- Each choice is the smallest one that makes the spec complete.

## Open work

See [open-work.md](../open-work.md).
