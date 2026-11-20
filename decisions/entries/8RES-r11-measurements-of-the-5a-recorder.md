# 8RES — R11 measurements of the 5a recorder

**Status:** evidence, 2026-11-20 (agent; commit to dom/recorder).

## Evidence

The measurements of R11 (section 11 of [`specs/recorder.md`](../../specs/recorder.md)) were made
on 2026-11-20 on the code of step 5a (commit a1541389c), with the queue of 3 s and the stall limit
of 10 s. The machine was an Intel Core i7-14700K (28 logical processors) with 64 GB of memory, one
WD_BLACK SN850X NVMe drive and Windows 11. Python 3.13.18, PyAV 19.0.2, OpenCV 5.1.0. All frames
were synthetic JPEGs at quality 90: 1280x720 of about 75 kB, 1920x1080 of about 129 kB. Other
agents can have used the machine at the same time.

Tools: the benchmarks of `skellycam/tests/take_recorder/test_benchmarks.py` with
`SKELLYCAM_BENCH=1`, and [`recorder_bench.py`](../scripts/recorder_bench.py) for the fsync cost
with 1, 4, 8 and 16 writers and for the tables. The full tables are in
[`8RES-r11-recorder-measurements.md`](../evidence/8RES-r11-recorder-measurements.md).

| Measurement | Result |
|---|---|
| T-REC-STALL, 1 and 4 processes, 720p30 and 1080p60, stall at frame 300 | 0.5 s and 2 s: no `give` wait, queue high-water 0.5 s and 2.0 s, no lost frame. 10 s: the queue fills (3.0 s), the longest `give` wait is 6.97 to 6.99 s, 208 (30 fps) or 418 (60 fps) frames are replaced in the source, no lost frame, equal rows. 15 s: `RecorderStalled` after 10.00 s, `take_error` "disk stall", each file finished, equal rows. All 16 cases pass. |
| T-REC-STALL, the other camera processes | Lateness p99 0.60 to 0.68 ms, max 0.73 to 3.96 ms, for each stall length. |
| T-REC-KILL, 20 kills in each case | Normal writing: 0 or 1 frame lost (720p30 and 640x480 with placeholders). Full queue: up to 92 frames lost (the 90 queued items, the block that the muxer held and the item in the blocked write). Blocks minus rows: 0 in all 80 kills. No torn CSV bytes. Each row has a correct CRC and its block. |
| T-REC-FSYNC, 16 processes at 1080p60, 3 x 60 s and 10 min | fsync call p50 2.0 to 2.1 ms, max 36 to 167 ms. Queue high-water 2 to 11 items (at most 0.18 s). MKV write p99.9 0.21 to 0.26 ms. Capture lateness p99 0.64 to 0.97 ms (one max of 16.2 ms). fsync off: high-water 1 to 2 items, one MKV write of 46 ms. |
| T-REC-FSYNC, 1, 4, 8, 16 writers at 1080p30 and 1080p60, 60 s | fsync max 3.6 ms (1 writer), 20 to 105 ms (4 writers), 50 to 77 ms (8 writers), 70 to 105 ms (16 writers). Queue high-water at most 6 items (0.1 s). Capture lateness p99 at most 0.66 ms with fsync on. |
| T-REC-GIL, 4 x 720p30 and 1 x 720p60, 10 min, writer on and off | Lateness p99 0.61 ms in both cases; max 9.2 ms (off) and 9.6 to 10.6 ms (on). Interval jitter p99 0.45 to 0.49 ms in both cases. Loop step p99 0.05 ms (on) against 0.00 ms (off). |

What the results show for the two limits that the user must fix (R11):

- The queue absorbs a disk stall up to its own length with no `give` wait (0.5 s and 2 s of stall
  gave 0.5 s and 2.0 s of high-water). The largest natural delay measured, the once-per-second
  fsync with 16 writers at 1080p60, used at most 0.18 s of queue. A queue of 3 s is about 16 times
  that.
- A larger queue costs frames only when a camera process is killed while its disk is stalled: up to
  the queue plus 2 frames. During normal writing a kill loses 0 or 1 frame, because the queue is
  almost empty.
- The stall limit is the time that the whole group stays frozen before the take ends (a stall up to
  the queue plus the limit, 13 s, ends with no lost frame and with gap rows). No measured delay came
  near it.
- The once-per-second fsync of SFF-788 did not delay capture (lateness p99 below 1 ms in all runs).
- The writer thread did not delay a capture loop in the same process (T-REC-GIL).

Limits of the method (some found by an independent review on 2026-11-20):

- The injected stall sleeps inside the MKV writes of one camera only. A real slow disk stalls all
  cameras at the same time, and mostly in the fsync calls. This case was not measured.
- No gate joins the camera processes, so the freeze of the whole group (5.2) was not measured.
- The frames were 75 kB (720p) and 129 kB (1080p). The spec plans for 600 kB frames at 1080p. 16
  cameras at 1080p60 write 124 MB/s with 129 kB frames and 576 MB/s with 600 kB frames. At 600 kB,
  16 full queues of 180 items hold about 1.7 GB of memory.
- One machine, one NVMe drive, Windows only. Not measured: a spinning disk, a USB disk (the optional
  run of T-REC-STALL, section 11 of the spec), antivirus software, a nearly full disk, Linux and
  macOS.
- One run of each fsync matrix case.

The code of these runs is commit a1541389c. The later fixes of the review
([ADR-T24F](T24F-choices-of-the-5a-recorder-code.md)) change mostly the take level and the error
paths. They also add three small steps to the live path that these runs did not measure: a
`frame_number` check in `give`, an SOF parse of each good frame and a write wrapper on the writer
thread.

## Open work

See [open-work.md](../open-work.md).
