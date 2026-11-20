# 953T — R11 measurements after the review fixes

**Status:** evidence, 2026-11-20 (agent; commit to dom/recorder).

## Evidence

The R11 benchmarks of [ADR-8RES](8RES-r11-measurements-of-the-5a-recorder.md) ran again on commit
fb39e2f2f, after the review fixes ([ADR-T24F](T24F-choices-of-the-5a-recorder-code.md)) and D1 of
[ADR-C6DE](C6DE-stall-as-no-progress-limits-and-no-fat-disk.md), on the same machine, with a steady
CPU load of about 20 % from other idle sessions. The fsync test and the fsync matrix ran two times.
The tables and the analysis are in the section "Update of 2026-11-20" of
[`8RES-r11-recorder-measurements.md`](../evidence/8RES-r11-recorder-measurements.md).

- Capture lateness, the stall cases and T-REC-GIL did not become worse. All 16 stall cases pass.
- fsync with 16 writers at 1080p60: p50 2.0 to 2.1 ms, max 29 to 182 ms; queue high-water at most
  11 items.
- T-REC-KILL, normal writing: 0 to 2 frames lost; blocks − rows 0 or 1. A kill between the return of
  the write of block k − 1 and the write of row k − 1 gives the second lost frame. That window was
  about 31 µs (p50) before and after the review fixes; the first runs did not hit it in 40 kills.
  No outcome leaves a row whose block was not handed to the OS. This is the guarantee of spec 6.3
  and 5.6, seen with more kill points, and the pass rule of T-REC-KILL (blocks − rows 0 or 1).
- T-REC-KILL, full queue: 92 frames lost in each of 40 kills (the queue of 90, the held block and
  the block in the blocked write). The value 39 of the first runs came from the test, which stopped
  its wait early.

## Open work

See [open-work.md](../open-work.md).
