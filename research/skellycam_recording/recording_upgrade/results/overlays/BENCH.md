# overlays (G3): timed bench results (23:00 run, 2026-11-09/10)

- **Runs:**
  - `run_id 20261109T230007`: items 36 (OV-COST, **timed out**), 37-38 (OV-DRAW-E35/E45) and 65-66 (OV-PLAY-E35/E45). Items ran 2026-11-10 02:35-05:01 local time (UTC-5).
  - `run_id 20261110T053653`: OV-COST re-run alone, 05:37-06:13, from a scratch copy of the queue with a 60-min timeout.
- **Machine:** Gerald (`host` in the OV-COST JSON). i7-14700K, RTX 3070 (driver 610.88), Intel UHD 770 present, Windows 11, Defender real-time protection ON.
- **P-cores only.** The runner pinned every item to the 8 P-cores. **Results are for 16 logical CPUs (P-cores), not all 28.**
  - The OV-COST JSON records `cpu_count: 28` (`os.cpu_count()`), which ignores affinity.
  - Source for the pinning: `results/BENCH_QUEUE_2300.md`, "What the runner does", affinity row.
- **Versions, as recorded in the JSONs:**
  - `bench/bench_overlay_cost_20261110T103707Z.json`: python 3.12.13, opencv 4.12.0, numpy 2.2.6, msgspec 0.21.1. **No PyAV**: the script imports none (`bench_overlay_cost.py:5-7`). nvidia-smi `0, 0 %` before and after.
  - Electron 35.7.5 (E35): Chrome 134.0.6998.205, node 22.16.0, scaleFactor 1 (`env` in `electron_drawbench_35.7.5.json` / `electron_play_quiet_35.7.5.json`).
  - Electron 45.2.3 (E45): Chrome 156.0.8078.80, node 24.22.2, scaleFactor 1.
  - Chromium's basic GPU info lists vendorId 4318 / deviceId 9348 (RTX 3070, driverVersion 32.0.16.1088), 32902 / 42880 (Intel) and 5140 (Microsoft Basic Render). This is `getGPUInfo('basic')` (`electron_harness/main.js:100`). Which adapter decoded or rasterised is not recorded.

Paths:
- `R/` = `research/skellycam_recording/recording_upgrade/results/overlays/`
- `S/` = `research/skellycam_recording/recording_upgrade/scripts/overlays/`
- `H` = `S/electron_harness/harness.js`

Every number is from a file named next to it. Anything else is marked **inferred**, or **arithmetic** for plain arithmetic on file values.

## 1. Load record

Source: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/items_load_2300.json`, cross-checked against `results/BENCH_RUN_2300_LOG.jsonl` (lines 38 and 72-73 for OV-COST). Logs are in `results/bench_runner/logs/20261109T230007/{36,37,38,65,66}_*` and `results/bench_runner/logs/20261110T053653/36_OV-COST.*`.

| run | # | id | start-end (local) | status / exit | duration vs est / timeout (min) | CPU before, mean / max % | top process before (CPU-s in 10 s) | MsMpEng CPU-s during item | Defender scan events | nvidia-smi before -> after | flags |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 20261109T230007 | 36 | OV-COST (attempt 1) | 02:35-03:05 | **timeout** / 15 | 30.0 vs 12 / 30 | 3.69 / 6.8 | AsusFanControlService 1.58 | 125.08 | none | `0, 0, 0 %, 0 %, 0 %, 363 MiB` -> `... 370 MiB` | `hard timeout 1800 s: process tree killed` |
| 20261109T230007 | 37 | OV-DRAW-E35 | 03:05-03:06 | ok / 0 | 0.53 vs 3 / 10 | 3.30 / 6.5 | AsusFanControlService 1.55 | 2.03 | none | `... 370 MiB` -> `0, 0, 5 %, 0 %, 0 %, 368 MiB` | none |
| 20261109T230007 | 38 | OV-DRAW-E45 | 03:06-03:06 | ok / 0 | 0.51 vs 3 / 10 | 3.58 / 5.7 | Corsair.Service 1.72 | 1.56 | none | `... 373 MiB` -> `... 373 MiB` | none |
| 20261109T230007 | 65 | OV-PLAY-E35 | 04:52-04:57 | ok / 0 | 4.40 vs 6 / 15 | 3.53 / 7.2 | Corsair.Service 1.73 | 8.48 | none | `... 370 MiB` -> `0, 0, 5 %, 0 %, 0 %, 352 MiB` | none |
| 20261109T230007 | 66 | OV-PLAY-E45 | 04:57-05:01 | ok / 0 | 4.39 vs 6 / 15 | 2.99 / 4.7 | AsusFanControlService 1.52 | 9.06 | none | `... 352 MiB` -> `... 352 MiB` | none |
| 20261110T053653 | 36 | OV-COST (attempt 2) | 05:37-06:13 | ok / 0 | 36.12 vs 35 / 60 | 3.76 / 7.5 | Corsair.Service 1.86 | 79.36 | none | `0, 0, 0 %, 0 %, 0 %, 369 MiB` -> `... 342 MiB` | none |

**No item was load-flagged.** `load_over_15pct` is false for all six rows, and no Defender scan event was logged. The raw log's "leftover processes" notes (for example on attempt 1) listed only the monitoring session's shells. The load record calls them harmless; no bench process was left behind.

**The OV-COST timeout:**
- The queue gave OV-COST a 12-min estimate and a 30-min timeout (`BENCH_QUEUE_2300.md`, row 36). Both were too low.
- Attempt 1 printed "done" for 7 of the 8 size × case blocks. All of 1280x720 text/skeleton/charuco/all and 1920x1080 text/skeleton/charuco finished; 1920x1080 `all` did not (`logs/20261109T230007/36_OV-COST.out.txt`).
- The process tree was then killed at 1800 s. **No JSON was written**, because the script writes its JSON only at the end (`bench_overlay_cost.py:203-205`).
- The re-run used `queue_ovcost_rerun.json` in the scratchpad (est 35 / timeout 60, `BENCH_RUN_2300_LOG.jsonl` line 72-73). It finished all 8 blocks in 36.12 min and wrote the one OV-COST result file. That file's `utc` stamp 20261110T103707Z = 05:37 local.
- **Inferred:** the time goes to `alpha_render` (35-113 ms/frame) and to cv2 burn-in for charuco/all (about 16.5 ms/frame). Over 900 frames × 3 reps × 8 blocks this dominates the run.
- MsMpEng used 125.08 CPU-s in attempt 1 (30 min) and 79.36 CPU-s in attempt 2 (36 min), i.e. 0.07 and 0.04 cores on average (**arithmetic**). The script writes scratch sidecar files, and the SVG-per-frame method writes 900 files per rep.

## 2. Completeness

| item | expected | present | errors / skips |
|---|---|---|---|
| OV-COST (attempt 2) | 11 methods (`--only` list) × 2 sizes × 4 cases × 3 reps, but `jpeg_roundtrip_only` is per size only: 10 × 2 × 4 × 3 + 1 × 2 × 3 = **246** records (`bench_overlay_cost.py:101-202`) | **246/246**: 24 per method, 6 for `jpeg_roundtrip_only`. Every record has n = 900 frames | none. `alpha_vp9_pipeline` (ffmpeg CLI) was excluded by the queue's `--only`, by design |
| OV-COST (attempt 1) | same | 0 (no JSON); 7/8 blocks printed done | hard timeout |
| OV-DRAW-E35 / E45 | `drawbench`: 3 canvas modes + SVG DOM, reps=5 (`H:484-514`) | 4/4 modes in each file, n = 1500 each (300 overlay frames × 5 reps) | none |
| OV-PLAY-E35 / E45 | `play` (5 files at 1x + 2x VP9 + 2 canvas-composite), `seek` (5 files × exact/mid), `vtt` (3), `alpha` (`H:519-531`) | all present in both files: 8 play runs, 5 seek files with 2 modes each, 3 VTT runs, alpha load + dual-video sync + dual-video seek | no `error` field. The AV1 test file has unreadable barcodes at frames 14 and 254 (`decodeFailAt`), a known test-media defect (FINDINGS §2.3) |

## 3. Method notes (field meanings)

**OV-COST** (`bench_overlay_cost.py`):
- Each method is timed per frame with `perf_counter_ns`, single-threaded, over 900 frames per rep, 3 reps (`:109-202`).
- `median_us` / `p95_us` / `max_us` are per-call statistics within a rep (`:59-62`).
- **Tables give the median of the 3 per-rep medians (min-max of those medians).**
- `bytes_per_frame` = file size / 900, and `MB_per_hour_30fps` = that × 108,000 / 1e6 (`:126-127`).
- `close()` is timed separately.
- `burnin_cv2` draws on a copy of a decoded corpus frame; the copy is outside the timer (`:151`).
- `burnin_cv2_jpeg_roundtrip` times imdecode + burn-in + imencode q90 (`:160-163`). `jpeg_roundtrip_only` is the same without drawing (`:193-202`).
- `alpha_render` rasterises the overlay to BGRA (`:173`).
- `cv2.setNumThreads` is not set in this script, so OpenCV's internal thread count is its default under the 16-CPU affinity. It is not recorded.

**OV-DRAW** (`H:484-514`):
- Overlay at 1280×720 (`H:7`), 300 frames from `overlay.jsonl`, 5 reps pooled into one sorted list. So **there is no per-rep min-max**: the files give median, p95 and max over 1500 calls.
- Canvas times include `getImageData(0,0,1,1)`, which forces the draw to complete.
- `svg_dom_innerHTML_plus_raf` includes waiting for the next `requestAnimationFrame` (the file's own note: "~16.7 ms at 60 Hz floor").
- `performance.now()` values are quantised to 0.1 ms in these files (e.g. 1.1000000014901161). Sub-0.1 ms differences are not resolvable.

**OV-PLAY** (`H:178-241` play, `:243-307` seek, `:310-371` vtt, `:373-430` alpha):
- The reference frame is the barcode read by `drawImage(video)` + `getImageData` inside each callback.
- "Captures" are `webContents.capturePage` composites, taken on every 10th rVFC callback (`H:208`). They show compositor output, not scan-out.
- Every run is a single play-through of a 300-frame, 10-s clip. These are **counts from one run each, not rates with repeats**.
- The verifier's 3-repeat `play` runs were not in the queue.

## 4. Results

### 4.1 OV-COST: per-frame cost, µs (`R/bench/bench_overlay_cost_20261110T103707Z.json`)

#### 1280x720 (corpus `c930e_720p_flash`)
| method | text | skeleton | charuco | all |
|---|---|---|---|---|
| sidecar_bin (`.skov`) | 0.8 (0.8-1.4) | 1.6 (1.6-1.7) | 28.2 (28.2-28.2) | 29.3 (29.1-29.5) |
| sidecar_msgpack | 0.4 (0.4-0.6) | 1.8 (1.8-1.8) | 22.6 (22.5-22.9) | 23.7 (23.2-24.4) |
| sidecar_jsonl | 1.6 (1.6-1.7) | 15.3 (15.1-15.3) | 113.1 (112.2-113.3) | 125.4 (125.3-125.7) |
| sidecar_vtt | 3.3 (3.3-3.5) | 17.0 (16.8-17.0) | 114.3 (114.2-115.2) | 128.3 (128.2-128.4) |
| svg_single | 2.0 (2.0-2.0) | 127.4 (127.0-128.1) | 530.5 (529.4-531.2) | 653.4 (651.4-655.8) |
| svg_per_frame | 165.0 (163.9-168.6) | 328.9 (317.7-331.0) | 755.3 (749.9-756.1) | 934.9 (916.3-939.5) |
| ass | 2.7 (2.6-2.7) | 75.3 (74.7-75.7) | 252.1 (250.8-252.3) | 326.8 (325.5-331.8) |
| burnin_cv2 | 89.1 (88.5-89.6) | 197.4 (196.8-197.9) | 16,514.5 (16,500.1-16,603.9) | 16,646.6 (16,643.6-16,677.8) |
| burnin_cv2_jpeg_roundtrip | 3,426.9 (3,422.6-3,437.6) | 3,580.4 (3,572.3-3,583.8) | 20,294.9 (20,204.6-20,304.8) | 20,370.0 (20,360.5-20,475.5) |
| alpha_render | 34,674.8 (34,638.9-34,866.6) | 35,229.7 (35,143.3-35,238.7) | 68,145.7 (68,076.8-68,480.8) | 68,229.8 (68,171.3-68,274.7) |
| jpeg_roundtrip_only (no overlay) | 3,315.3 (3,315.0-3,330.7) | | | |

#### 1920x1080 (corpus `c930e_1080p`, 19 frames looped)
| method | text | skeleton | charuco | all |
|---|---|---|---|---|
| sidecar_bin (`.skov`) | 0.8 (0.8-0.8) | 1.6 (1.6-1.6) | 27.8 (27.6-27.8) | 29.1 (29.1-29.5) |
| sidecar_msgpack | 0.4 (0.4-0.4) | 1.8 (1.7-1.9) | 22.6 (22.4-22.6) | 24.0 (23.9-24.6) |
| sidecar_jsonl | 1.6 (1.6-1.7) | 15.3 (15.2-15.4) | 116.4 (114.9-117.9) | 129.3 (128.7-132.1) |
| sidecar_vtt | 3.3 (3.2-3.3) | 17.1 (16.9-17.1) | 117.7 (117.1-118.1) | 131.6 (130.4-131.8) |
| svg_single | 2.0 (2.0-2.0) | 124.8 (124.7-125.6) | 529.1 (527.1-529.5) | 657.4 (653.6-659.6) |
| svg_per_frame | 163.8 (163.8-165.7) | 323.0 (321.7-323.1) | 760.3 (755.6-761.1) | 950.6 (949.3-967.8) |
| ass | 2.6 (2.6-2.6) | 75.5 (75.4-75.8) | 250.8 (250.1-251.9) | 326.7 (325.7-328.7) |
| burnin_cv2 | 90.1 (90.0-91.2) | 218.1 (216.2-218.4) | 16,539.2 (16,516.0-16,632.1) | 16,724.6 (16,706.1-16,770.8) |
| burnin_cv2_jpeg_roundtrip | 7,683.8 (7,654.7-7,685.6) | 7,884.5 (7,859.2-7,891.8) | 24,686.8 (24,440.4-24,706.4) | 24,932.4 (24,836.2-24,956.8) |
| alpha_render | 79,194.2 (79,128.4-79,343.2) | 80,109.0 (79,980.4-80,363.6) | 113,016.3 (112,547.2-113,359.8) | 113,110.0 (112,720.1-113,366.4) |
| jpeg_roundtrip_only (no overlay) | 7,527.4 (7,492.1-7,545.8) | | | |

**Per-call tails:**
- 11 rep records of methods with a median below 200 µs had a single call above 1 ms. The largest: JSONL charuco 1080p 1,877.4 µs, VTT all 720p 1,840.1 µs, JSONL skeleton 720p 1,623.8 µs.
- `svg_single` had single calls of 16,963.5 µs (all, 720p, rep 0) and 36,073.8 µs (all, 1080p, rep 2).
- The VTT `close()` of all 720p rep 2 took 2,612.8 µs, against 68.9-71.0 µs in the other reps.
- **Inferred:** these are occasional file-system stalls (buffered writes flushing, or Defender). They are not recorded as such.

### 4.2 OV-COST: bytes per frame / MB per hour at 30 fps (identical in all 3 reps)

| method | res | text | skeleton | charuco | all |
|---|---|---|---|---|---|
| sidecar_bin (`.skov`) | 720p and 1080p | 40.1 B / 4.33 MB | 443.1 B / 47.86 MB | 2,882.9 B / 311.35 MB | 3,282.9 B / 354.55 MB |
| sidecar_msgpack | 720p and 1080p | 31.8 B / 3.44 MB | 928.8 B / 100.31 MB | 5,999.9 B / 647.99 MB | 6,890.3 B / 744.15 MB |
| sidecar_jsonl | 720p | 44.6 B / 4.82 MB | 665.4 B / 71.87 MB | 5,082.0 B / 548.86 MB | 5,697.7 B / 615.35 MB |
| sidecar_jsonl | 1080p | 44.6 B / 4.82 MB | 680.6 B / 73.50 MB | 5,215.2 B / 563.24 MB | 5,845.8 B / 631.34 MB |
| sidecar_vtt | 720p | 78.4 B / 8.47 MB | 699.2 B / 75.52 MB | 5,115.8 B / 552.51 MB | 5,731.5 B / 619.00 MB |
| sidecar_vtt | 1080p | 78.4 B / 8.47 MB | 714.3 B / 77.15 MB | 5,248.9 B / 566.88 MB | 5,879.5 B / 634.99 MB |
| svg_single | 720p | 168.6 B / 18.21 MB | 5,040.1 B / 544.33 MB | 30,296.4 B / 3,272.01 MB | 35,156.6 B / 3,796.92 MB |
| svg_single | 1080p | 168.6 B / 18.21 MB | 5,087.0 B / 549.40 MB | 30,591.9 B / 3,303.93 MB | 35,498.8 B / 3,833.87 MB |
| svg_per_frame | 720p | 291.6 B / 31.50 MB | 5,163.1 B / 557.62 MB | 30,419.4 B / 3,285.30 MB | 35,279.7 B / 3,810.21 MB |
| svg_per_frame | 1080p | 293.6 B / 31.71 MB | 5,212.1 B / 562.91 MB | 30,717.0 B / 3,317.43 MB | 35,623.8 B / 3,847.37 MB |
| ass | 720p | 94.5 B / 10.20 MB | 2,627.0 B / 283.72 MB | 14,615.5 B / 1,578.48 MB | 17,053.1 B / 1,841.73 MB |
| ass | 1080p | 94.5 B / 10.20 MB | 2,757.1 B / 297.77 MB | 14,911.6 B / 1,610.45 MB | 17,478.8 B / 1,887.71 MB |

Burn-in + JPEG q90 round trip: output JPEG bytes/frame vs the camera's own JPEG (`out_jpeg_bytes_per_frame`, `camera_jpeg_bytes_per_frame`):

| res | text | skeleton | charuco | all | camera JPEG |
|---|---|---|---|---|---|
| 1280x720 | 61,192 | 70,121 | 162,159 | 167,033 | 55,379 |
| 1920x1080 | 138,934 | 151,936 | 290,536 | 299,194 | 134,592 |

The 720p `.skov` "all" size (3,282.9 B/frame) is within 5 B of the functional measurement in FINDINGS §3.1 (3,287.6 B).

### 4.3 OV-DRAW: UI draw cost per frame in Electron, ms (1280×720 overlay, 1500 calls)

| mode | E35 median | E35 p95 | E35 max | E45 median | E45 p95 | E45 max |
|---|---|---|---|---|---|---|
| canvas_full_layout (placed labels) | 1.1 | 1.3 | 84.5 | 0.9 | 1.1 | 112.9 |
| canvas_full_naive_labels | 1.0 | 1.2 | 1.9 | 0.8 | 0.9 | 1.4 |
| canvas_no_labels | 0.9 | 1.0 | 1.3 | 0.6 | 0.7 | 1.0 |
| svg_dom_innerHTML_plus_raf (includes the wait for the next rAF) | 18.0 | 18.2 | not recorded | 18.0 | 18.1 | not recorded |

- Sources: `R/bench/electron_drawbench_35.7.5.json`, `R/bench/electron_drawbench_45.2.3.json` → `results.drawbench`. Values are rounded from the float fields (e.g. 1.1000000014901161).
- **Inferred:** the single 84.5 / 112.9 ms `canvas_full_layout` max is a one-off first-call cost. The label layout keeps a measure cache (`H`, `measureCache`), and the other canvas modes have no such outlier.

### 4.4 OV-PLAY: playback alignment (`R/bench/electron_play_quiet_{35.7.5,45.2.3}.json` → `results.play`)

How to read the columns:
- Each fraction is matches / readable callbacks.
- "rVFC lookup" = nearest pts-table entry to `metadata.mediaTime`, against the frame `drawImage` read in the same callback (`H:195-201`).
- "today's rule" = `floor(currentTime*30)` in rAF (`H:221`).
- Capture mismatch is written as video − overlay.

| file / mode | Electron | rVFC callbacks | rVFC lookup == drawImage frame | round(mediaTime×30) == frame | today's rule == frame | rAF offsets (rule − frame: count) | captures overlay == video | capture mismatch (video − overlay: count) | presentedFrames gaps | dropped / total |
|---|---|---|---|---|---|---|---|---|---|---|
| base_cfr_h264.mp4 | 35 | 283 | 275/283 | 275/283 | 501/558 | -1: 5, +1: 52 | 12/28 | +1: 13, +2: 3 | 16 | 0/300 |
| base_cfr_h264.mp4 | 45 | 280 | 280/280 | 280/280 | 293/559 | -1: 156, +1: 110 | 14/28 | +1: 14 | 0 | 19/300 |
| base_cfr_vp9.webm | 35 | 279 | 270/279 | 270/279 | 481/560 | -1: 20, +1: 59 | 3/28 | +1: 22, +2: 3 | 20 | 0/300 |
| base_cfr_vp9.webm | 45 | 279 | 279/279 | 279/279 | 280/559 | -1: 154, +1: 123, +2: 2 | 0/28 | +1: 26, +2: 1, +3: 1 | 0 | 20/300 |
| base_cfr_av1.webm | 35 | 271 (2 unreadable) | 255/269 | 255/269 | 491/556 | -1: 12, +1: 53 | 2/27 | +1: 21, +2: 4 | 28 | 0/300 |
| base_cfr_av1.webm | 45 | 280 (2 unreadable) | 278/278 | 278/278 | 296/555 | -1: 148, +1: 110, +2: 1 | 2/28 | +1: 24, +2: 1, +3: 1 | 0 | 19/300 |
| base_vfr_vp9.webm | 35 | 282 | 277/282 | 139/282 | 139/562 | -1: 135, +1: 153, +2: 131, +3: 4 | 4/28 | +1: 22, +2: 2 | 17 | 0/300 |
| base_vfr_vp9.webm | 45 | 256 | 253/256 | 125/256 | 130/563 | -1: 146, +1: 151, +2: 132, +3: 4 | 6/26 | +1: 13, +2: 6, +3: 1 | 43 | 0/300 |
| base_vfr_h264.mp4 | 35 | 282 | 274/282 | 135/282 | 132/561 | -1: 145, +1: 150, +2: 130, +3: 4 | 4/28 | +1: 23, +2: 1 | 17 | 0/300 |
| base_vfr_h264.mp4 | 45 | 261 | 258/261 | 132/261 | 138/563 | -1: 139, +1: 164, +2: 119, +3: 3 | 4/26 | +1: 14, +2: 7, +3: 1 | 38 | 0/300 |
| base_cfr_vp9.webm @2x | 35 | 241 | 224/241 | 224/241 | 139/279 | -2: 2, -1: 65, +1: 73 | 0/24 | +1: 21, +2: 2, +3: 1 | 38 | 19/300 |
| base_cfr_vp9.webm @2x | 45 | 247 | 245/247 | 245/247 | 137/280 | -1: 56, +1: 86, +2: 1 | 0/25 | +1: 20, +2: 4, +3: 1 | 32 | 21/300 |
| base_cfr_vp9.webm @canvasComposite | 35 | 286 | 285/286 | 285/286 | 490/560 | -1: 9, +1: 61 | **29/29** | none | 13 | 0/300 |
| base_cfr_vp9.webm @canvasComposite | 45 | 269 | 267/269 | 267/269 | 393/560 | -1: 12, +1: 155 | **27/27** | none | 30 | 2/300 |
| base_vfr_h264.mp4 @canvasComposite | 35 | 286 | 286/286 | 145/286 | 155/562 | -1: 123, +1: 145, +2: 136, +3: 3 | **29/29** | none | 12 | 1/300 |
| base_vfr_h264.mp4 @canvasComposite | 45 | 269 | 261/269 | 134/269 | 151/564 | -1: 122, +1: 165, +2: 118, +3: 8 | **26/27** | +1: 1 | 28 | 4/300 |

- Every rVFC-lookup mismatch, in both versions and all runs, had `drawImage` one frame **ahead** of the lookup (code − fi = +1). The harness recorded all of them, since each run had at most 17, under the 20 it keeps (`H:201`).
- `presentedFrames` gaps never exceeded 1 (`maxPresentedGap` 1).

### 4.5 OV-PLAY: paused seeks (`results.seek`; 80 targets per file, 79 readable for AV1)

| file | mode | requested frame shown, E35 | E45 | frame == rVFC lookup, E35 | E45 | capture right after seek / +100 ms, E35 | E45 |
|---|---|---|---|---|---|---|---|
| base_cfr_h264.mp4 | exact pts | 80/80 | 80/80 | 80/80 | 80/80 | 65/80 / 80/80 | 65/80 / 80/80 |
| base_cfr_h264.mp4 | midpoint | 80/80 | 80/80 | 80/80 | 80/80 | 63/80 / 80/80 | 64/80 / 80/80 |
| base_cfr_vp9.webm | exact | 79/80 | 79/80 | 80/80 | 80/80 | 76/80 / 80/80 | 79/80 / 80/80 |
| base_cfr_vp9.webm | midpoint | 80/80 | 80/80 | 80/80 | 80/80 | 80/80 / 80/80 | 78/80 / 80/80 |
| base_cfr_av1.webm | exact | 78/79 | 78/79 | 79/79 | 79/79 | 79/79 / 79/79 | 78/79 / 79/79 |
| base_cfr_av1.webm | midpoint | 79/79 | 79/79 | 79/79 | 79/79 | 79/79 / 79/79 | 77/79 / 79/79 |
| base_vfr_vp9.webm | exact | 43/80 | 56/80 | 80/80 | 80/80 | 80/80 / 80/80 | 80/80 / 80/80 |
| base_vfr_vp9.webm | midpoint | 80/80 | 80/80 | 80/80 | 80/80 | 76/80 / 80/80 | 78/80 / 80/80 |
| base_vfr_h264.mp4 | exact | 42/80 | **80/80** | 80/80 | 80/80 | 66/80 / 80/80 | 65/80 / 80/80 |
| base_vfr_h264.mp4 | midpoint | 76/80 | 79/80 | 80/80 | 80/80 | 58/80 / 80/80 | 64/80 / 80/80 |

- Every "requested frame shown" count is **identical to the earlier loaded-machine run** in FINDINGS §2.3 (paused-seek tables, both modes, both versions).
- The VTT seek counts below also match.
- **Inferred:** paused-seek behaviour is deterministic and load-independent, so the earlier tables stand.

### 4.6 OV-PLAY: WebVTT metadata cues (`results.vtt`; `activeCues` read in rVFC vs the `drawImage` frame)

| case | Electron | cues | play: cue == frame | empty | multiple active | offsets (cue − frame: count) | cuechange events | paused seeks: cue == frame |
|---|---|---|---|---|---|---|---|---|
| CFR (`base_cfr_vp9.webm`, `overlay.vtt`) | 35 | 300 | 257/281 | 0 | 0 | -1: 13, +1: 11 | 340 | 40/40 |
| CFR | 45 | 300 | 143/278 | 0 | 0 | -2: 3, -1: 116, +1: 16 | 340 | 40/40 |
| CFR, cues shifted half a frame (`overlay_half.vtt`) | 35 | 300 | 197/289 | 1 | 0 | -1: 3, +1: 88 | 341 | 39/40 |
| CFR, half shift | 45 | 300 | 143/279 | 1 | 0 | -1: 57, +1: 78 | 341 | 39/40 |
| VFR (`base_vfr_vp9.webm`, `overlay_vfr.vtt`) | 35 | 300 | 70/285 | 0 | 0 | -1: 215 | 340 | 30/40 |
| VFR | 45 | 300 | 97/287 | 0 | 1 | -1: 188, +1: 2 | 340 | 32/40 |

The CFR play counts differ a lot from the loaded run (FINDINGS §2.4: 148/299 E35, 8/299 E45). **Inferred:** `activeCues` timing during playback is load-sensitive. The paused-seek counts (40/40, 39/40, 30/40, 32/40) are unchanged.

### 4.7 OV-PLAY: alpha layer (`results.alpha`)

| check | E35 | E45 |
|---|---|---|
| VP9-alpha WebM loads | ok | ok |
| frame 0 alpha < 8 / > 247 fraction | 0.8746 / 0.1135 | 0.8746 / 0.1135 |
| dual `<video>` play: capturePage composites, base == layer | **26/26** | **27/27** |
| dual play: `drawImage` reads, base == layer, in base's rVFC | 62/256 (layer +1: 186, +3: 8) | 22/273 (layer +1: 240, +2: 2, +3: 9) |
| dual paused seeks, both on the requested frame | 30/30 | 30/30 |

## 5. Headline numbers

1. **Vector sidecars cost microseconds per frame.** For the full "all" overlay at 720p:
   - `.skov` binary: 29.3 µs/frame, 3,282.9 B/frame = 354.55 MB/hour;
   - MessagePack: 23.7 µs, 744.15 MB/h;
   - JSONL: 125.4 µs, 615.35 MB/h;
   - WebVTT: 128.3 µs, 619.00 MB/h.
   - Text-only (today's stamp) is at most 3.3 µs/frame and at most 8.47 MB/h for every sidecar.
   - Source: `research/skellycam_recording/recording_upgrade/results/overlays/bench/bench_overlay_cost_20261110T103707Z.json`.
2. **cv2 burn-in is cheap for text and skeleton but not for ChArUco.** Text 89.1 µs, skeleton 197.4 µs, but charuco 16,514.5 µs and all 16,646.6 µs per 720p frame (1080p: 16,539.2 / 16,724.6 µs). That is about half of a 33.3 ms (30 fps) frame budget (**arithmetic**). Source: same file.
3. **Burning into passthrough JPEGs costs 20.37 ms/frame at 720p ("all") and 24.93 ms at 1080p,** against 3.32 / 7.53 ms for a plain decode + re-encode.
   - The re-encoded q90 JPEG grows to 167,033 B against the camera's 55,379 B at 720p: 3.0× (**arithmetic**).
   - At 1080p: 299,194 vs 134,592 B (2.2×).
   - Source: same file.
4. **Rasterising an alpha overlay layer takes 34.7-68.2 ms/frame at 720p and 79.2-113.1 ms at 1080p.** That is over the 33.3 ms budget in every case (**arithmetic**), before any VP9 encode. Source: same file, `alpha_render`.
5. **Electron UI draw of the full overlay on canvas with placed labels:** median 1.1 ms (E35) and 0.9 ms (E45); without labels, 0.9 / 0.6 ms. SVG DOM replacement plus rAF: 18.0 ms in both. Sources: `research/skellycam_recording/recording_upgrade/results/overlays/bench/electron_drawbench_35.7.5.json`, `.../electron_drawbench_45.2.3.json`.
6. **Video drawn into the overlay canvas keeps the composite paired:** captures 29/29 and 29/29 (E35), 27/27 and 26/27 (E45). A separate canvas over `<video>` matched only 0-14 of 24-28 captures, with the overlay 1-3 frames behind. Sources: `research/skellycam_recording/recording_upgrade/results/overlays/bench/electron_play_quiet_35.7.5.json`, `.../electron_play_quiet_45.2.3.json` → `results.play`.
7. **The rVFC `mediaTime` lookup beats today's `floor(currentTime*30)` rule.**
   - rVFC lookup: 253/256-280/280 in E45 and 255/269-277/282 in E35 at 1x.
   - Today's rule on CFR H.264: 501/558 (E35) but 293/559 (E45). On VFR: 130/563-139/562.
   - Source: same files.
8. **Paused seeks repeat the loaded-run results exactly.** VFR H.264 at the exact pts: 42/80 (E35) vs 80/80 (E45). VFR VP9: 43/80 vs 56/80. Midpoint seeks: 76-80/80. Every capture taken 100 ms after a seek matched (80/80 or 79/79). Source: same files → `results.seek`.

## 6. Caveats

- **P-cores only** (16 logical CPUs). OV-COST is single-threaded Python, but OpenCV's internal threading inside `imdecode`/`imencode`/drawing is not pinned or recorded.
- **The OV-COST timeout is part of the record.**
  - The queue's 12-min estimate and 30-min timeout were too low; the run needs about 36 min.
  - The only result is from the 05:37 re-run, made after the main run's 05:00 deadline. The load check (3.76% CPU mean) and the absence of Defender scan events cover it like the others.
- **OV-COST spread is narrow, but its tails are not stable.** Of the 70 cells with a median above 2 µs, 60 have rep medians within 2% of each other and all are within 6.1% (**arithmetic**). The widest: VTT text 720p 3.3-3.5 µs, MessagePack all 720p 23.2-24.4 µs, svg_per_frame skeleton 720p 317.7-331.0 µs. Cells below 2 µs move in 0.1-µs steps (e.g. sidecar_bin text 720p 0.8-1.4 µs). Meanwhile single calls of over 1 ms appear in 11 rep records of fast methods, plus two `svg_single` spikes of 17 and 36 ms. **Inferred:** these are file-system stalls with Defender on.
- **The overlay content is synthetic and deterministic** (`overlay_model.make_frames`), so sizes are for this content. Burn-in cost grows with the label count (charuco has 100 labelled corners).
- **The 1080p corpus loops 19 frames.** Burn-in and JPEG round-trip cost depends on JPEG content.
- **Electron draw:**
  - The 5 reps are pooled, so there is no per-rep spread.
  - The timer resolution is 0.1 ms.
  - The SVG figure includes the rAF wait, so it is not draw cost alone.
  - The display refresh rate is not recorded. **Inferred:** about 60 Hz from about 560 rAF ticks per 10-s clip.
- **Every Electron play/VTT/alpha count is from one run.**
  - The play-time rates move between runs: today's rule and VTT play differ widely from the loaded run.
  - So only the patterns are robust: the lookup error is +1 when present, the composite stays paired, and paused seeks are stable.
  - The verifier's 3-repeat play runs were not queued.
- **The readback instrumentation is still in the harness.** rVFC and rAF callbacks do synchronous `getImageData`. The canvas-over-`<video>` capture mismatch rates may be inflated by it (FINDINGS §2.3). A run without the rAF loop is still not possible from the command line.
- **Tonight's canvas-over-`<video>` captures show the overlay up to 3 frames behind** (+2 and +3 counts). The earlier run found only N-1 (FINDINGS §2.3, "0 exceptions across all 10 1x runs"). The direction holds; "always exactly one behind" does not.
- **E45 reported `droppedVideoFrames` 19-20/300 on the three CFR 1x files** while showing 0 presentedFrames gaps. E35 showed 0 dropped with 16-28 gaps. These are two counters that disagree. **Inferred:** a difference in how the two Chromium versions count. Not investigated.
- **The alpha-layer results use the CLI-encoded VP9-alpha test file** (FINDINGS §2.5), not a PyAV-19-encoded one.
