# ETJ1 — Measurements M5 to M7 of the BGR ring

**Status:** evidence, 2026-11-19 (commit to dom/native-jpeg).

## Evidence

Measurements M5, M6 and M7 of section 11.3 of [`specs/frame-ring.md`](../../specs/frame-ring.md)
were made on 2026-11-19 on the code of step 2b (commit 2e5a5895e). The machine was an Intel Core
i7-14700K with Windows 11, Python 3.13.18 and OpenCV 5.1.0. All frames were synthetic. The
scripts, the numbers and the method are in `research/frame_ring_buffer/bgr_bench/` of branch
`dom/research` (commit 6a508ec8a): read `FINDINGS.md` there.

Times are median / p99 in ms.

| Item | 1280x720 | 1920x1080 |
|---|---|---|
| M5: `zlib.crc32` of one BGR frame | 0.67 / 1.07 | 1.51 / 2.24 |
| M5: BGR ring write (W1 to W7) | 0.79 / 1.24 | 1.83 / 2.46 |
| M5: BGR ring read (R1 to R13) | 1.17 / 1.68 | 2.58 / 3.35 |
| M6: decode thread at 60 frames/s, 4 camera processes | 23 % of one core | 48 % of one core |
| M6: decode thread at 60 frames/s, 8 camera processes | 23 % of one core | 54 % of one core |
| M6: BGR frames skipped, 4 and 8 camera processes, 20 s | 0 | 0 |

- M7: with the decode stage in the same process, the lateness of a capture thread paced at
  60 frames/s did not change: 0.36 / 0.67 ms with the stage off, 0.36 / 0.67 ms (720p) and
  0.33 / 0.66 ms (1080p) with it on.
- M7: `zlib.crc32` and `cv2.imdecode` release the GIL on Python 3.13.18 (two threads take 1.0 to
  1.2 times the wall time of one). The W3 copy and the R11 copy hold the GIL, for 0.2 to 0.9 ms
  for a 1080p frame.
- Target "BGR read: p99 at most 3 ms at 1080p" (11.3): not met. Three runs gave 3.13, 3.35 and
  4.05 ms. About 1 ms of each read is the new 6.2 MB `bytearray` of R11. A copy into a buffer
  that is used again takes 0.3 ms.
- Target "BGR write: p99 at most 3 ms at 1080p" (11.3): met in two runs (2.30 and 2.46 ms), not
  met in one (3.17 ms). The loop was not paced.
- The estimates of 11.2 are near the measurements: CRC 0.9 / 2 ms (measured 0.67 / 1.51 ms),
  decode thread 7.7 ms for a 1080p frame (measured 7.5 to 8.4 ms), reader 2.3 ms (measured
  2.58 ms).

Limits: one machine, Windows only. The machine had 2.5 to 4 cores of other load. The 1080p JPEGs
were larger than usual camera frames. One earlier run of M6 was 10 to 40 % slower, and its cause
is not known.

The user decided on 2026-11-19: the reader does not change in phase 2. A read call that copies
into a buffer of the reader is open work, for the first consumer that reads the BGR ring.

## Open work

See [open-work.md](../open-work.md).
