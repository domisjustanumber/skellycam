# T-S2: cost of learning each JPEG's offset live (file size after every mux)

2026-11-12, Gerald (i7-14700K, WD_BLACK SN850X). PyAV 19.0.2 (FFmpeg 9.0.2), `skellycam-phase1` venv. Script: `scripts/stat_cost/stat_cost.py`. Result: `stat_cost.json`.

**Labels:** [M] measured, [I] inferred, [NV] not verified.

## Answer
**Keep live offsets: they're cheap.** At 16 cameras × 1080p60 (one writer thread per camera, `flush_packets=1`, 256 KB frames, about 245 MB/s to disk), asking for the file size after each mux cost [M]:

| | p50 | p99 | p99.9 | max |
|---|---|---|---|---|
| `os.stat(path).st_size` | 23.7–24.9 µs | 245–277 µs | 382–566 µs | 0.93 ms |
| `os.fstat(fd).st_size` (read-only handle opened after the header) | 20.5–23.6 µs | 249–378 µs | 416–720 µs | 1.14 ms |
| for comparison, `mux()` itself | 168–208 µs | 557–861 µs | 0.85–8.4 ms | — |

- **Small against the budget:** the frame budget is 16.7 ms. The size query is about 12 % of a mux at the median and comparable to the mux's own tail.
- **Total CPU:** 16 × 60 × ~25 µs ≈ 24 ms of thread time per second, about 2.4 % of one core across all writer threads [I, arithmetic; CPU not measured directly].
- **Correctness:** in every sampled check (60 per camera per run, 6 runs with a size query), the offset derived as size after `mux(i)` − len(frame i−1) pointed at an SOI marker [M].
- **`os.stat` vs `os.fstat`:** no meaningful difference. `os.stat(path)` needs no extra handle, so prefer it.

## Method
- 16 threads, each pacing 60 fps and muxing real JPEG packets (720p testsrc2 JPEGs padded to 256 KB after EOI) into its own MKV, as the row-1.5 writer does.
- Three modes: `none`, `stat`, `fstat`. 3 reps of 20 s each, with the order reversed on alternate reps. Files were deleted after each run.
- **Late frames** (a frame starting more than one period after its due time) appeared in a `none` run (1,049) as well as a `stat` run (179), so they come from background load, not the size query [M]. Background load: one of Dom's other jobs (an OpenMMLab model export) was running; machine CPU was about 10 % before the run.

## Consequence for the design
- Row 1.5's live offsets stay: a video-only MKV writes record i−1 after `mux(i)` with the live offset (T-S6 writer rule).
- Finalisation still rebuilds every offset by scan (SE §7). Live offsets serve unfinalised and crashed files.
- Not tested: an HDD or a network drive, and Linux/macOS file systems [NV].
