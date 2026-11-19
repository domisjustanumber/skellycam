# BGR ring benchmarks M5, M6, M7 (2026-11-19)

Measurements M5, M6 and M7 of section 11.3 of `specs/frame-ring.md`, made on the product code of the implementation worktree (`skellycam.core.ipc.frame_ring`, branch dom/native-jpeg, not changed). No camera was used. All frames are synthetic. No image is saved.

A sub-agent (opus) made the measurements and wrote this text. The main session checked `results/m5.json` against the M5 table.

## Setup

- Intel Core i7-14700K (8 P-cores, 12 E-cores, 28 logical cores), Windows 11 (10.0.26300).
- Python 3.13.18, opencv-contrib-python 5.1.0, numpy 2.5.5, zlib 1.3.2, psutil 7.2.2. The environment of the implementation worktree. No dependency was added.
- `cv2.setNumThreads(1)` in each process.
- Machine load. Before each run, the machine used 8.5 to 11.9 % of all cores (about 2.5 to 3.3 cores) for its usual services and programs. Another session ran tests at times. It used about one core during the second M5 run, M6 run 2 and the second M7 run. The "other load" column of M6 shows this load. The cases of this study never ran in parallel with each other.
- Synthetic frames: `common.photo_like` makes a photo-like image (smooth colour regions, 40 hard-edged shapes, blurred texture, sensor-like noise). `cv2.imencode` q90 4:2:0 of 8 seeds gives 154 to 165 kB at 1280x720 and 326 to 348 kB at 1920x1080. The 720p size is in the range of real webcam frames. The 1080p frames are larger than the real q90 median (184 kB in `../encode_bench/FINDINGS.md`), so the 1080p decode is a little pessimistic.
- Scripts: `m5_crc.py`, `m6_decode_load.py`, `m7_jitter.py`, helpers in `common.py`. Run with `uv run --project <implementation worktree> python <script>`. `common.add_ring_path` puts the worktree on `sys.path` (env var `SKELLYCAM_IMPL` overrides it).
- Numbers: `results/m5.json`, `results/m6_run2.json`, `results/m6_run3.json`, `results/m7.json`.

## M5: CRC-32 of a BGR frame, and the full BGR write and read

Method. 2,400 timed calls per item after 100 warm-up calls. Frames: the decoded synthetic JPEGs, 8 different frames in turn (at 1080p, 8 x 6.2 MB is larger than the 33 MB L3 cache). Write = the real `FrameRingWriter.write` of a BGR ring (W1 to W7). Read = the real `FrameRingReader.read` of the same frame just after (R1 to R13, with the CRC check and the new `bytearray`). The loop is not paced. Copy = the W3 slice assignment alone into a bytearray. Three runs. The table gives the last run (`results/m5.json`); the p99 of the other two runs is in the notes.

Times in ms: median / p95 / p99 / max.

| Item | 1280x720x3 (2.76 MB) | 1920x1080x3 (6.22 MB) |
|---|---|---|
| `zlib.crc32` of one frame | 0.67 / 0.76 / 1.07 / 1.48 | 1.51 / 1.65 / 2.24 / 3.16 |
| W3 copy alone | 0.08 / 0.13 / 0.17 / 0.38 | 0.31 / 0.49 / 0.56 / 1.19 |
| BGR `write` (W1 to W7) | 0.79 / 0.90 / 1.24 / 1.66 | 1.83 / 1.99 / 2.46 / 3.22 |
| BGR `read` (R1 to R13) | 1.17 / 1.33 / 1.68 / 2.54 | 2.58 / 2.77 / 3.35 / 4.09 |
| CRC share of the write (median) | 85 % | 83 % |
| CRC share of the read (median) | 57 % | 59 % |

- CRC speed: 4.1 GB/s at both sizes. The same frame on each call (hot cache) gives the same median.
- The median is the same in the three runs (within 0.05 ms). The tail is not. p99 of the 1080p write: 3.17, 2.30 and 2.46 ms. p99 of the 1080p read: 4.05, 3.13 and 3.35 ms.
- The read costs about 1.1 ms more than its CRC at 1080p. Most of it is the new 6.2 MB `bytearray` of R11. It is a new block on each read, and the OS must give it fresh pages. The copy into a reused buffer is 0.3 ms.

## M6: decode thread CPU and BGR skip rate

Method. The main process creates a JPEG ring and a BGR ring per camera (as in 7.1) and starts one process per camera (spawn). Each camera process calls `cv2.setNumThreads(1)`, attaches the two writers, starts the real `DecodeStage`, and runs a feeder thread. The feeder is paced by sleep to an absolute deadline. Per tick it does the steps of 5.3: the JPEG ring write, then `DecodeInput(source="JPEG")` into the waiting place. 8 synthetic JPEGs are used in turn, with a different start per camera. 20 s per case; all cameras start together.

Offered = feeder puts. Committed and skipped are the BGR ring counters (table 3.3). Each case checks committed + skipped = offered. Decode thread CPU = user + system time of that thread (psutil) over the 20 s, as a percent of one core. Machine CPU = `psutil.cpu_percent` over the middle 18 s. Two runs (run 2 and run 3) after a fix of the method (see run 1 below). The table gives run 3, with run 2 in brackets.

| Case | Decode thread CPU, % of one core (median, max) | Offered | Committed | Skipped | Skip rate | Decode ms median, worst p99 | Machine CPU, cores (of 28) | Camera processes, cores | Other load, cores |
|---|---|---|---|---|---|---|---|---|---|
| 720p60 x 4 | 22.9, 23.4 (21.7, 22.2) | 4,804 | 4,804 | 0 | 0 | 2.66, 3.64 (2.71, 3.62) | 3.67 (4.31) | 0.94 (0.88) | 2.73 (3.43) |
| 720p60 x 8 | 23.4, 24.5 (24.9, 25.5) | 9,608 | 9,608 | 0 | 0 | 2.71, 4.19 (2.95, 3.86) | 5.80 (4.84) | 1.94 (2.04) | 3.86 (2.80) |
| 1080p60 x 4 | 48.0, 48.4 (48.1, 48.2) | 4,804 | 4,804 | 0 | 0 | 5.66, 6.90 (5.74, 7.26) | 4.73 (5.80) | 1.93 (1.97) | 2.80 (3.83) |
| 1080p60 x 8 | 54.1, 55.9 (55.9, 57.4) | 9,608 | 9,608 | 0 | 0 | 6.26, 9.61 (6.64, 10.26) | 8.65 (8.51) | 4.49 (4.60) | 4.16 (3.91) |
| 720p30 x 4 (reference) | 12.3, 13.0 (10.8, 11.8) | 2,404 | 2,404 | 0 | 0 | 2.84, 4.83 (2.65, 4.43) | 9.55 (3.53) | 0.52 (0.45) | 9.03 (3.08) |

- No frame was skipped and no decode failed in any case of runs 2 and 3.
- "Other load" = machine CPU minus the CPU of the camera processes. In run 3, the 720p30 case had about 9 cores of other load (another program started). Its own numbers did not change.
- Feeder thread: 1 to 5 % of one core. Feeder lateness (how late a tick starts after its deadline) had a p99 of 0.64 to 0.78 ms in all cases. The max was 1.0 to 1.7 ms, except at 1080p60 x 8: 6.7 ms (run 2) and 8.5 ms (run 3), one tick of one camera each time.
- At 1080p60 the decode thread uses about half a core. Per frame: the decode takes about 5.7 to 6.6 ms and the BGR write 1.8 ms, so about 8 to 9 ms of the 16.7 ms period. With 8 processes, each decode is 10 to 15 % slower than with 4 (shared cores, E-cores).
- Run 1 had a fault in the method, and no JSON of it is kept. The feeder took its CPU snapshot after it started its clock, so the first ticks of each camera were late. The feeder then put frames back to back to catch up. That run had 9, 32, 8, 42 and 1 skipped frames (skip rate 0.04 to 0.44 %), about 1 to 5 per camera. All of them came from that catch-up burst and from one frame that `stop()` dropped at the end. Its decode thread CPU was higher (24, 34, 58, 73 and 12 %). Its decodes were slower (720p60 x 8: 4.10 ms median; 1080p60 x 8: 8.66 ms median, 13.55 ms worst p99), with no other heavy process running. The cause of this slower run is not known; thread placement on E-cores by Windows is a guess. Even that run did not skip a frame in steady state.

## M7: capture timing while the decode thread runs, and the GIL

### Does `zlib.crc32` release the GIL?

Yes. Method: the wall time of 2 threads that each do the operation 200 times, against 1 thread that does it 200 times. A ratio near 1 means the operation releases the GIL; near 2 means it holds the GIL. Three runs. The first run had a fault in the copy tests, which are not counted from it. Values in brackets are from that first run.

| Operation | Ratio, 2 threads / 1 thread | Per call, 1 thread | GIL |
|---|---|---|---|
| `zlib.crc32`, 6 MB `bytes` | 1.01, 1.02 (1.03) | 1.45 ms | released |
| `zlib.crc32`, 1080p BGR `ndarray` | 1.17, 0.98 (1.03) | 1.5 ms | released |
| `cv2.imdecode`, 1080p JPEG | 1.08, 1.07 (1.18) | 5.7 ms | released |
| Writer W3: memoryview slice assignment, 6.2 MB | 1.67, 2.08 | 0.17 to 0.22 ms | held |
| Reader R11: new `bytearray` of a memoryview, 6.2 MB | 2.11, 1.95 | 0.85 to 0.93 ms | held |
| `np.copyto`, 1080p BGR (not used by the ring) | 1.68, 1.55 | 0.17 ms | not clear (memory bandwidth) |
| Pure Python loop (control) | 2.01, 1.95 | 0.93 ms | held |

What holds the GIL in the decode thread, per frame:

- `cv2.imdecode` releases it. This confirms 8.4.
- `zlib.crc32` releases it. The CPython source says the zlib module releases the GIL for inputs larger than 5 KiB; small inputs were not tested here. The 6 MB test confirms it.
- The W3 copy into shared memory holds it: about 0.2 to 0.3 ms at 1080p, 0.08 ms at 720p.
- The Python code of the decode loop and of `write` (header pack, counters, waiting place) holds it in short steps of a few µs each.
- A BGR reader in the same process would hold the GIL for about 0.9 ms per 1080p frame during R11.

### Jitter of a capture-like thread

Method. One process. A capture-like thread is paced at 60 fps by sleep to an absolute deadline. Per tick it does a JPEG ring write of a 150,000-byte payload (5.4), and it records how late the tick starts and how long the write takes. Cases: decode stage off; decode stage on, fed a 720p or a 1080p synthetic JPEG per tick through the waiting place (the `put` is timed apart). 2,400 ticks (40 s) per case. The table gives the last run (`results/m7.json`). Times in ms: median / p95 / p99 / max.

| Case | Tick lateness | JPEG write (job) | `put` | Ticks > 1 ms late | BGR committed / skipped |
|---|---|---|---|---|---|
| Decode off | 0.36 / 0.61 / 0.67 / 4.20 | 0.09 / 0.15 / 0.19 / 0.53 | - | 1 | - |
| Decode on, 720p | 0.36 / 0.61 / 0.67 / 0.89 | 0.08 / 0.13 / 0.17 / 0.52 | 0.018 / 0.027 / 0.035 / 0.095 | 0 | 2,400 / 0 |
| Decode on, 1080p | 0.33 / 0.57 / 0.66 / 0.79 | 0.08 / 0.12 / 0.16 / 0.22 | 0.016 / 0.025 / 0.031 / 0.057 | 0 | 2,400 / 0 |

- The two earlier runs gave the same median, p95 and p99 (within 0.05 ms). Their max values: decode off 0.92 and 0.83 ms; 720p 0.99 and 1.27 ms; 1080p 0.77 and 1.30 ms.
- The lateness of about 0.35 ms median is the wake-up delay of `time.sleep` on Windows. It is there with the decode stage off too.
- The decode thread does not change the median, p95 or p99 of the capture thread. The max varies from run to run by more than the decode stage changes it; the 4.2 ms max was with decode off. In 2 of 6 decode-on cases the max was 1.27 to 1.30 ms. In the decode-off runs without an outlier it was 0.83 to 0.92 ms.

## What this means for the spec

- BGR ring skip rate: 0 % at 720p60 and 1080p60, with 4 and with 8 camera processes, in steady state on this machine. Skips come from bursts. When frames reach the waiting place back to back (run 1), the waiting place replaces frames, as 8.3 intends.
- Copy-then-CRC for BGR at 1080p60 is affordable on this machine. The writer side costs 1.8 ms per frame, and 83 % of that is the CRC. That is about 11 % of one core per camera at 60 fps. The whole decode thread uses 48 to 56 % of one core per camera at 1080p60. 8 cameras at 1080p60 used about 4.5 cores of 28.
- Each BGR reader pays 2.6 ms per 1080p frame, about 16 % of one core per camera at 60 fps. It holds the GIL for about 0.9 ms per frame during its copy.
- The decode thread does not disturb capture timing in the same process. The p99 lateness and the JPEG write time do not change.
- `zlib.crc32` releases the GIL on Python 3.13.18. The [NV] of M7 and of section 10 ("CRC speed on Python 3.13") can be closed for Windows.

Numbers that contradict or change the spec:

- 11.2 estimated the CRC of a BGR frame at about 0.9 / 2 ms (720p / 1080p). Measured: 0.67 / 1.51 ms median, 1.07 / 2.24 ms p99.
- 11.2 estimated the BGR decode thread at about 7.7 ms per 1080p frame. Measured: decode 5.7 to 6.6 ms plus write 1.8 ms, so 7.5 to 8.4 ms, close to the estimate.
- 11.2 estimated the BGR reader at about 2.3 ms per 1080p frame. Measured: 2.58 ms median.
- 11.3 target "BGR read: p99 at most 3 ms at 1080p": not met. The p99 was 3.13 to 4.05 ms in three runs. The new `bytearray` per read (fresh pages each time) adds about 1 ms over a copy into a reused buffer.
- 11.3 target "BGR write, decode not included: p99 at most 3 ms at 1080p": met in two runs of three (2.30 and 2.46 ms) and missed in one (3.17 ms). This was an unpaced loop. The write inside the paced decode thread was not timed apart.
- 8.4 decode cost (2.60 / 5.42 ms, one thread, real frames): the synthetic frames gave 2.66 to 2.84 / 5.66 to 5.74 ms with 4 processes, in line with it.

## Limits

- One machine, Windows only. No Apple Silicon or Linux (M8 is a separate measurement).
- Synthetic frames. The 1080p JPEGs (about 335 kB) are larger than typical real 1080p q90 frames, so the 1080p decode times are on the high side.
- The machine was not idle: about 2.5 to 4 cores of other load in each case (services; at times another session's tests; 9 cores in one case). This is 10 to 15 % of the machine.
- Decode thread CPU comes from Windows thread times. Their resolution is one clock tick (15.6 ms), so over 20 s the error is about 0.1 % of one core.
- The decode times varied between runs on the same code: run 1 was 10 to 40 % slower, perhaps because of thread placement on P-cores and E-cores. More runs would give a better spread.
- M6 did not time the BGR write inside the decode thread apart from the decode, and it did not run a BGR reader.
- M7 ran one camera in one process. Capture timing under 8 busy camera processes was seen only through the feeder lateness of M6 (p99 0.7 ms; max 8.5 ms at 1080p60 x 8).
- The decode thread was not tested with a near-spin loop in the same process (8.10).
