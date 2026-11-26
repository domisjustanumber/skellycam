# 3TYP — Timings of the small parts of the frame path

**Status:** evidence, 2026-11-23 (agent; one run of
[`measure_capture_timing_parts.py`](../scripts/measure_capture_timing_parts.py) for
[`specs/capture-timings.md`](../../specs/capture-timings.md) 3.2 and 5.3).

## Decision

No decision. These numbers give the cost of the parts of the frame path that
[`specs/capture-timings.md`](../../specs/capture-timings.md) leaves out of its step list, and the cost of the
measurement itself.

## Evidence

Tool: [`measure_capture_timing_parts.py`](../scripts/measure_capture_timing_parts.py), one run, Python
3.13.18, numpy 2.5.5, OpenCV 5.1.0, Windows 11, Intel64 Family 6 Model 183, other work on the machine. Each
part runs in a loop of 300 to 50,000 calls on one thread. Each value is the time of one call, with the cost of
two `perf_counter_ns` reads in it. The JPEGs are synthetic: q90 from a generated gradient with noise, 323,537
bytes at 720p and 724,907 bytes at 1080p. They are larger than camera JPEGs, so the decode, the CRC and the
hash are slower than with a camera. No camera and no camera frame was used.

| Part (code) | p50 / p99 / max |
|---|---|
| `np.mean` of the BGR image (`_brightness`), 720p / 1080p | 1.36 / 1.80 / 2.33 ms; 3.07 / 3.52 / 4.11 ms |
| `decode_jpeg`, 720p / 1080p | 3.48 / 3.91 / 4.19 ms; 7.82 / 8.51 / 8.87 ms |
| `decode_jpeg` and `np.mean` (all of `_brightness`), 720p / 1080p | 4.89 / 5.33 / 5.38 ms; 11.00 / 11.63 / 12.03 ms |
| `check_jpeg`, a JPEG with a DHT, 720p and 1080p | 2.8 / 3.1 / 17.1 µs |
| `check_jpeg` with a DHT insertion, 720p / 1080p | 7.4 / 8.7 / 10.7 µs; 12.6 / 14.9 / 23.3 µs |
| Two SHA-256 and `dqt_segments` (`_hash`), 720p / 1080p | 124 / 181 / 254 µs; 274 / 301 / 446 µs |
| `parse_sof` | 2.8 / 3.3 / 137 µs |
| `CaptureWaitingPlace.put` | 0.5 / 0.6 / 11.7 µs |
| `WaitingPlace.put` of the decode stage | 0.5 / 0.6 / 4.3 µs |
| `sidecar.row_line` | 1.1 / 1.9 / 64.6 µs |
| Two stores of a shared scalar with no lock (the status update) | 0.1 / 0.2 / 5.1 µs |
| The frame decision in a take: a read, the lock of a shared value with no other holder, a read, the release | 0.5 / 0.5 / 19.3 µs |
| `_feed_check` and `_feed_block` of one frame, in a take, no check | 0.4 / 1.1 / 13.8 µs |
| `pickle.dumps` of a diagnostics message (64 `frame_log` rows, 60 hash keys) with a summary of 20 steps | 24.5 / 40.2 / 89.8 µs |
| The build of a summary: 20 steps, 60 samples each, sort and nearest rank | 56.9 / 69.0 / 135 µs |
| One `perf_counter_ns` call | under 0.05 / 0.1 / 2.9 µs |
| One sample store into an `array("q")` and the increase of a total | 0.1 / 0.2 / 9.1 µs |
| One branch on a plain attribute that is false | under 0.05 / 0.1 / 12.2 µs |

Sizes: the summary of 20 steps and 1 delay is 1,577 bytes pickled. The synthetic diagnostics message is 6,702
bytes, and 8,850 bytes with the summary.

## Not repeated

- The decode and the hash of a synthetic noisy JPEG are slower than with a camera JPEG of the same size class.
  Use [`frame-ring.md`](../../specs/frame-ring.md) 11.1 for the decode of camera JPEGs.
