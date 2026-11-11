# intra_playback bench results, run 20261109T230007

Timed Electron benches of H.264 / HEVC intra-only files (NVENC- and QSV-encoded) against the JPEG path (Range fetch + createImageBitmap / ImageDecoder), 1080p30, N = 1 / 4 / 8 streams. Generated from the per-configuration JSON files listed below; every number is copied from a file unless marked *inferred*.

| item | value |
|---|---|
| run id | `20261109T230007` (runner `scripts/bench_runner/run_queue.py`, queue `results/BENCH_QUEUE_2300.md`) |
| run window | 2026-11-09 23:00 to 2026-11-10 05:36 local (UTC-5). intra_playback items ran 00:34-01:13 and 03:43-03:51 local |
| machine | GERALD: i7-14700K, RTX 3070, Intel UHD 770 present (`state.display_devices` in `results/BENCH_RUN_2300_LOG.jsonl` line 1 also lists a Parsec Virtual Display Adapter) |
| CPU set | **results are for 16 logical CPUs (P-cores), not all 28.** Runner start state: `pcores` = [0..15], `logical_cpus` = 28 (`BENCH_RUN_2300_LOG.jsonl` line 1) |
| GPU used by Chromium | active `gpuDevice` vendor 0x10DE device 0x2484 (NVIDIA), driver `32.0.16.1088` (= 610.88 per the run brief; mapping *inferred* from the Windows driver string). Intel UHD 770 listed but inactive (`gpu_info.gpuDevice` in every JSON) |
| Electron 35 (skellycam-ui pin) | Electron 35.7.5, Chromium 134.0.6998.205, Node 22.16.0, V8 13.4.114.21-electron.0 (`versions` in every JSON) |
| Electron 45 (newest stable) | Electron 45.2.3, Chromium 156.0.8078.80, Node 24.22.2, V8 15.6.75.27-electron.0 (`versions` in every JSON) |
| page | 1600 x 900 window, `--noocclusion=1`, media served from `CSS_MEDIA_ROOT` = `C:/Users/Dom/Documents/skellycam-raw/.../recording_upgrade_20261109/intra_playback` over the harness's local HTTP server (`window`, `switches` in every JSON; `switches` in `_index.json`; `run_suite.py:53-56`) |
| JSON read | 148 files under `bench/e35|e45/bench_intra_{seek,sync,scrub}/` modified after 2026-11-09 23:00; 0 older files in those folders (none). Smoke folders (`*_smoke`) not used |
| repeats | **one run per configuration per Electron.** Medians, p95 and min-max below are within-run distributions (over seeks, rAF ticks or input events), not across repeats |

Paths in this document are relative to `research/skellycam_recording/recording_upgrade/results/intra_playback/` unless they start with `scripts/` or `results/` (then relative to `research/skellycam_recording/recording_upgrade/`).

## Field meanings (from the harness code)

| field | meaning | code |
|---|---|---|
| `result.summary.exact` / `n` | seeks whose burned-in 16-bit frame index read back from the decoded frame equals the requested frame k / number of seeks | `scripts/chromium_sync_scrub/harness/harness.mjs:292-294` |
| `lat_rvfc_ms` (`<video>`) | time from setting `currentTime` to the `requestVideoFrameCallback` callback (frame handed to the compositor) | `harness.mjs:87-95`, `:267` |
| `lat_seeked_ms` (`<video>`) | time from setting `currentTime` to the `seeked` event | `harness.mjs:87-95`, `:267` |
| `lat_ms` (WebCodecs, JPEG) | time around `frameAt(k)`: fetch (HTTP Range) + decode until a frame object exists; excludes drawing | `harness.mjs:277-284` |
| p50 / p95 | nearest-rank percentile; `min` below is computed from `result.rows` (the summary has no min) | `harness.mjs:25-26` |
| `flushes` / `resets` (WebCodecs) | `wcflush=1`: `flush()` after every key chunk; the decoder is `reset()`+`configure()`d before each non-sequential target | `harness.mjs:137-152` |
| sync `spread` | per rAF tick, max - min of the stream frame indices: rVFC `mediaTime` -> nearest pts for `<video>`, drawn index for master-clock paths | `harness.mjs:396`, `:440`, `:453` |
| sync `rvfc_or_draws_per_s` | per stream, rVFC callbacks (or canvas draws) / 15 s | `harness.mjs:456` |
| sync `dropped` | `getVideoPlaybackQuality()` dropped / total per `<video>` | `harness.mjs:412` |
| `video-leader` corrections | follower `currentTime` set to the leader's every 15 ticks when > 2 frames off (SyncedVideoPlayer logic); NVENC files only | `harness.mjs:397-400`, `run_suite.py:259` |
| `video-rvfc` | followers steered by rVFC index: playbackRate +-5 %/frame capped at +-20 %, hard seek if > 6 frames off | `harness.mjs:376-380` |
| scrub `frames_shown_per_s` / `distinct_per_s` | per stream, presents (rVFC callbacks or canvas draws) / 8 s and distinct frame indices / 8 s; slider moves 90 frames/s as a triangle wave, input event every ~16 ms | `harness.mjs:461-513` |
| scrub `lag_frames` | per input event, max over streams of abs(target - shown index) | `harness.mjs:484`, `:507` |
| scrub per-stream `errors` | `frameAt()` threw (message not recorded) | `harness.mjs:501-502` |
| CPU cores | sum over Electron processes of `cumulativeCPUUsage` delta / sampling window (~14.5 s sync, ~7.5 s scrub); 1.0 = one logical CPU | `scripts/chromium_sync_scrub/harness/main.cjs:93-101` |
| WS total MB | sum of working sets of all Electron processes at the last 500 ms sample | `main.cjs:103-105` |
| GPU proc private peak | max `memory.privateBytes` (stored as `private_kb`) of the `GPU` process over `metrics_samples` (computed here); shown raw in section 5 (corrected 2026-11-10, GF05: section 5 showed it / 1,048,576 labelled GB; Electron's "Kilobytes" unit is NOT VERIFIED, FINDINGS F22) | `main.cjs:66-68` |
| `_index*.json` `error` | only `result.error` (whole-config failure); per-stream scrub errors are not counted there | `scripts/chromium_sync_scrub/run_suite.py:356-361` |

Seek configs record no CPU/memory: `testSeek` never calls `metrics('start')`, so `metrics_summary` is `null` (`harness.mjs:238-313`).

## 1. Load record per item

From the runner's per-item record (`results/BENCH_RUN_2300_LOG.jsonl`, condensed in the session scratchpad `items_load_2300.json`). CPU % before = 10 s typeperf total CPU just before the item, system-wide (not limited to the P-cores).

| # | id | status (exit) | start-end local | duration / est / timeout (min) | CPU % before mean / max | top process before (CPU-s) | MsMpEng CPU-s during | Defender scan events | flags | load_over_15pct |
|---|---|---|---|---|---|---|---|---|---|---|
| 12 | IP-SEEK-E35 | ok (0) | 00:34:58-00:35:31 | 0.56 / 4 / 15 | 3.37 / 6.3 | AsusFanControlService.exe (1.59) | 9.55 | none | none | False |
| 13 | IP-SEEK-E45 | ok (0) | 00:35:43-00:36:15 | 0.54 / 4 / 15 | 3.63 / 7.3 | AsusFanControlService.exe (1.53) | 8.91 | none | none | False |
| 14 | IP-SYNC-E35 | ok (0) | 00:36:26-00:43:41 | 7.25 / 9 / 25 | 3.56 / 6.8 | Corsair.Service.exe (1.66) | 27.75 | none | none | False |
| 15 | IP-SYNC-E45 | ok (0) | 00:43:52-00:51:05 | 7.21 / 9 / 25 | 3.53 / 6.2 | Corsair.Service.exe (1.77) | 29.19 | none | none | False |
| 16 | IP-SUM | ok (0) | 00:51:16-00:51:17 | 0.01 / 1 / 5 | 3.85 / 7.0 | Corsair.Service.exe (1.8) | 0.55 | none | none | False |
| 25 | IP-SCRUB-E35 | ok (0) | 01:04:07-01:08:38 | 4.5 / 6 / 20 | 3.34 / 8.9 | AsusFanControlService.exe (1.59) | 24.36 | none | none | False |
| 26 | IP-SCRUB-E45 | ok (0) | 01:08:49-01:13:24 | 4.59 / 6 / 20 | 4.08 / 9.3 | Corsair.Service.exe (1.77) | 25.81 | none | none | False |
| 27 | IP-SUM-2 | ok (0) | 01:13:35-01:13:36 | 0.01 / 1 / 5 | 3.94 / 10.3 | PreSonusHardwareAccessService.exe (1.64) | 0.31 | none | none | False |
| 46 | IP-SYNC-QSV-E35 | ok (0) | 03:43:11-03:47:19 | 4.14 / 6 / 20 | 4.11 / 9.4 | Corsair.Service.exe (1.56) | 15.58 | none | none | False |
| 47 | IP-SYNC-QSV-E45 | ok (0) | 03:47:30-03:51:38 | 4.13 / 6 / 20 | 3.21 / 4.5 | Corsair.Service.exe (1.72) | 16.89 | none | none | False |
| 48 | IP-SUM-3 | ok (0) | 03:51:49-03:51:50 | 0.0 / 1 / 5 | 3.85 / 8.8 | AsusFanControlService.exe (1.62) | 0.19 | none | none | False |

- **load_over_15pct:** 0 of 11 intra_playback items flagged (field `load_over_15pct` is `false` for all; highest CPU before = 10.3 % max, 4.11 % mean).
- No Defender scan event (Operational ids 1000/1001) fell inside any item. MsMpEng used 0.19-29.19 CPU-s per item; the larger values are on the 4-7 min Electron items.
- All 11 items exited 0 with empty stderr (`results/bench_runner/logs/20261109T230007/<n>_<id>.err.txt`, 0 bytes each). The runner's leftover-process note listed only the monitoring session's shells; no bench process was left.
- nvidia-smi before/after per item is in the load record; per-configuration nvidia-smi snapshots (`nvidia_smi.before/after`, query `encoder.stats.sessionCount,utilization.gpu,utilization.decoder,memory.used`) are point samples, not averages (`run_suite.py:68-73`, `:95-103`).

## 2. Completeness

Expected configurations come from `intra_bench_configs()` (`run_suite.py:246-275`): seek 4 video files x 2 methods + 2 JPEG files x 2 decoders = 12; sync per N: 4 video files x 3 methods + `video-leader` on the 2 NVENC files + 3 JPEG configs = 17, x 2 N = 34 (22 non-QSV via `--skip _qsv_`, 12 QSV via `--only _qsv_`); scrub per N: 4 x 2 + 2 x 2 = 12, x 2 N = 24.

| item | expected configs | JSON present | index file (runs / errors) | per-config result errors | notes |
|---|---|---|---|---|---|
| IP-SEEK-E35 | 12 | 12 | `e35/bench_intra_seek/_index.json`: 12 / 0 | 0 | every config: `result.rows` length 200 and `summary.n` = 200: True; WebCodecs/JPEG `errors` sum 0; `unreadable` sum 0 |
| IP-SEEK-E45 | 12 | 12 | `e45/bench_intra_seek/_index.json`: 12 / 0 | 0 | every config: `result.rows` length 200 and `summary.n` = 200: True; WebCodecs/JPEG `errors` sum 0; `unreadable` sum 0 |
| IP-SYNC-E35 | 22 | 22 (non-QSV) | `e35/bench_intra_sync/_index.json`: 22 / 0 | 0 | - |
| IP-SYNC-E45 | 22 | 22 (non-QSV) | `e45/bench_intra_sync/_index.json`: 22 / 0 | 0 | - |
| IP-SYNC-QSV-E35 | 12 | 12 (QSV) | `e35/bench_intra_sync/_index_only__qsv_.json`: 12 / 0 | 0 | own index file, so the non-QSV `_index.json` was not overwritten (`run_suite.py:363-367`) |
| IP-SYNC-QSV-E45 | 12 | 12 (QSV) | `e45/bench_intra_sync/_index_only__qsv_.json`: 12 / 0 | 0 | own index file, so the non-QSV `_index.json` was not overwritten (`run_suite.py:363-367`) |
| IP-SCRUB-E35 | 24 | 24 | `e35/bench_intra_scrub/_index.json`: 24 / 0 | 0 | **per-stream `errors` > 0 in 5 configs** (all WebCodecs; see section 5). The queue's smoke note "8 configs" is the smoke subset (one config per path per N, `run_suite.py:342-349`) |
| IP-SCRUB-E45 | 24 | 24 | `e45/bench_intra_scrub/_index.json`: 24 / 0 | 0 | per-stream `errors` 0 in all configs. The queue's smoke note "8 configs" is the smoke subset (one config per path per N, `run_suite.py:342-349`) |
| IP-SUM / IP-SUM-2 / IP-SUM-3 | 1 file | `bench/bench_tables.md` (mtime 2026-11-10 03:51:50 = IP-SUM-3 end) | - | - | IP-SUM (00:51) predates the scrub items; IP-SUM-3's output holds all 6 suite sections, 140 config rows (= 2 x (12 + 34 + 24)). It does not show scrub per-stream errors or memory (`summarize.py:181-186`) |

**IP-SEEK finished in about 33 s against a 4 min estimate, and it is complete.** Evidence: every one of the 24 seek JSONs has 200 entries in `result.rows` and `result.summary.n` = 200, with `exact` = 200, `unreadable` = 0, WebCodecs/JPEG `errors` = 0 and `decoded_hist` = {1: 200}; `<video>` configs have `rvfc_fired` = 200. The sum of `result.summary.wall_s` over the 12 configs is 28.2 s (E35) and 28.8 s (E45), against item durations of 34 s and 32 s; stdout shows 2-4 s per config (`results/bench_runner/logs/20261109T230007/12_IP-SEEK-E35.out.txt`, `13_IP-SEEK-E45.out.txt`). At p50 latencies of 3-14 ms, 200 seeks take 1.4-3.8 s per config, so the 4 min estimate was simply conservative (*inferred*).

## 3. Random seek (N = 1, 1080p30 CFR, 600 frames, 200 random targets, seed 11)

`<video>` seeks to the midpoint between frame k's pts and the next (`mode=mid`). WebCodecs uses `wcflush=1`. JPEG = HTTP Range fetch of one frame, then createImageBitmap or ImageDecoder. Latency for `<video>` = to the rVFC callback; the `seeked` event column is shown separately. In 7 of 8 WebCodecs configs the max is the first seek (29-36 ms; decoder warm-up, *inferred*); the exception is E45 H.264 QSV, whose 31.5 ms max is seek 33 (`result.rows[32]`). The column `max excl. 1st` drops row 0.

### E35: Electron 35.7.5 / Chromium 134.0.6998.205

| file | method | exact / n | latency p50 / p95 ms | min-max ms | max excl. 1st | mean | `seeked` event p50 / p95 / min-max ms | flushes / resets | wall s |
|---|---|---|---|---|---|---|---|---|---|
| H.264 NVENC intra (mp4) | `<video>` mid -> rVFC | 200 / 200 | 11.8 / 14.1 | 1.5-19.6 | 19.6 | 10.94 | 1.6 / 2.5 / 1-5.5 | - | 3.77 |
| H.264 NVENC intra (mp4) | WebCodecs (wcflush) | 200 / 200 | 3.1 / 4.3 | 2.7-33.4 | 7.5 | 3.39 | - | 200 / 199 | 1.78 |
| HEVC NVENC intra (mp4) | `<video>` mid -> rVFC | 200 / 200 | 14 / 14.5 | 4.4-17.2 | 15.1 | 13.90 | 1.5 / 3.8 / 1.2-16.1 | - | 3.66 |
| HEVC NVENC intra (mp4) | WebCodecs (wcflush) | 200 / 200 | 3.4 / 4.5 | 2.9-33.6 | 10.4 | 3.68 | - | 200 / 199 | 1.82 |
| H.264 QSV intra (mp4) | `<video>` mid -> rVFC | 200 / 200 | 12.6 / 14.5 | 0.6-22.1 | 22.1 | 10.91 | 1.5 / 3.9 / 0.9-6.4 | - | 3.81 |
| H.264 QSV intra (mp4) | WebCodecs (wcflush) | 200 / 200 | 3.3 / 4.7 | 2.8-36.4 | 10.9 | 3.65 | - | 200 / 199 | 1.90 |
| HEVC QSV intra (mp4) | `<video>` mid -> rVFC | 200 / 200 | 14.1 / 14.5 | 5.8-17.5 | 14.7 | 14.07 | 1.5 / 3.1 / 1.1-5.3 | - | 3.68 |
| HEVC QSV intra (mp4) | WebCodecs (wcflush) | 200 / 200 | 3.4 / 4.6 | 2.9-34.2 | 9 | 3.67 | - | 200 / 199 | 1.84 |
| JPEG concatenated (.mjpeg) | Range + createImageBitmap | 200 / 200 | 7 / 7.7 | 6.6-11 | 11 | 7.12 | - | - | 1.52 |
| JPEG concatenated (.mjpeg) | Range + ImageDecoder | 200 / 200 | 4.4 / 4.8 | 4.1-5.9 | 5.9 | 4.47 | - | - | 1.42 |
| JPEG-in-MKV | Range + createImageBitmap | 200 / 200 | 7.1 / 7.8 | 6.6-14.3 | 9.9 | 7.19 | - | - | 1.53 |
| JPEG-in-MKV | Range + ImageDecoder | 200 / 200 | 4.4 / 4.9 | 4.2-5.8 | 5.8 | 4.48 | - | - | 1.42 |

### E45: Electron 45.2.3 / Chromium 156.0.8078.80

| file | method | exact / n | latency p50 / p95 ms | min-max ms | max excl. 1st | mean | `seeked` event p50 / p95 / min-max ms | flushes / resets | wall s |
|---|---|---|---|---|---|---|---|---|---|
| H.264 NVENC intra (mp4) | `<video>` mid -> rVFC | 200 / 200 | 12 / 14.4 | 1.7-19.5 | 19.5 | 11.15 | 1.5 / 2.3 / 0.9-5.1 | - | 3.71 |
| H.264 NVENC intra (mp4) | WebCodecs (wcflush) | 200 / 200 | 2.7 / 4 | 2.1-29.4 | 7.3 | 3.01 | - | 200 / 199 | 1.74 |
| HEVC NVENC intra (mp4) | `<video>` mid -> rVFC | 200 / 200 | 14.1 / 14.5 | 8.1-17.5 | 14.7 | 13.97 | 1.5 / 2.4 / 1-4.9 | - | 3.70 |
| HEVC NVENC intra (mp4) | WebCodecs (wcflush) | 200 / 200 | 2.9 / 4.3 | 2.4-29.4 | 6.6 | 3.18 | - | 200 / 199 | 1.75 |
| H.264 QSV intra (mp4) | `<video>` mid -> rVFC | 200 / 200 | 8.5 / 14.6 | 0.6-18.4 | 18.4 | 8.41 | 1.3 / 3.2 / 0.8-6.9 | - | 3.82 |
| H.264 QSV intra (mp4) | WebCodecs (wcflush) | 200 / 200 | 2.8 / 4.6 | 2.3-31.5 | 31.5 | 3.25 | - | 200 / 199 | 1.90 |
| HEVC QSV intra (mp4) | `<video>` mid -> rVFC | 200 / 200 | 14 / 14.5 | 8.6-17.4 | 14.7 | 13.97 | 1.5 / 2.3 / 0.9-4.4 | - | 3.69 |
| HEVC QSV intra (mp4) | WebCodecs (wcflush) | 200 / 200 | 2.8 / 3.7 | 2.4-29.5 | 6.9 | 3.08 | - | 200 / 199 | 1.72 |
| JPEG concatenated (.mjpeg) | Range + createImageBitmap | 200 / 200 | 6 / 6.5 | 5.7-9.3 | 9.3 | 6.08 | - | - | 1.39 |
| JPEG concatenated (.mjpeg) | Range + ImageDecoder | 200 / 200 | 4.6 / 5 | 4.3-5.4 | 5.4 | 4.63 | - | - | 1.99 |
| JPEG-in-MKV | Range + createImageBitmap | 200 / 200 | 6.1 / 6.6 | 5.7-9 | 8.6 | 6.16 | - | - | 1.41 |
| JPEG-in-MKV | Range + ImageDecoder | 200 / 200 | 4.6 / 5 | 4.4-5.3 | 5.3 | 4.65 | - | - | 1.98 |

Source: `bench/<e35|e45>/bench_intra_seek/c1080p30_<file>__<method>.json`, fields `result.summary.*` and `result.rows[*]`.

## 4. Multi-stream sync playback (N = 4 / 8, 1080p30, 15 s at 1x)

Each of N tiles plays the same file (`?cam=i`). `<video>` methods: `video-free` (N independent `play()`), `video-leader` (SyncedVideoPlayer-style correction, NVENC files only), `video-rvfc` (rVFC-steered followers). Master-clock methods (`wc-master`, `jpeg-master-*`) draw the newest decoded frame <= the clock target to a canvas on each rAF. Pattern readback was off in the bench (`readpattern` not passed, `run_suite.py:261`), so these runs do not check which frame was shown, only indices. Rows marked **QSV** come from IP-SYNC-QSV-E35/E45 (03:43-03:51, `_index_only__qsv_.json`); all others from IP-SYNC-E35/E45 (00:36-00:51).

### E35: Electron 35.7.5 / Chromium 134.0.6998.205

| file | method | N | spread p50 / p95 / max (frames) | spread = 0 % of ticks | rVFC or draws /s per stream, min-median-max | dropped / total frames (`<video>`) | corrections; rVFC hard seeks / rate changes | CPU cores total (GPU proc / Tab) | WS total MB |
|---|---|---|---|---|---|---|---|---|---|
| H.264 NVENC intra (mp4) | `<video>` free | 4 | 0 / 1 / 3 | 80.2 | 23.9-25.2-26.6 | 124 / 1828 | - | 0.30 (0.16 / 0.11) | 864 |
| H.264 NVENC intra (mp4) | `<video>` leader | 4 | 0 / 1 / 3 | 90.3 | 25.6-26.0-26.9 | 120 / 1824 | 0 | 0.33 (0.18 / 0.11) | 879 |
| H.264 NVENC intra (mp4) | `<video>` rVFC-steered | 4 | 1 / 2 / 3 | 31.5 | 23.2-24.3-26.5 | 139 / 1819 | 0 / 244 | 0.33 (0.18 / 0.12) | 870 |
| H.264 NVENC intra (mp4) | WebCodecs master clock | 4 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.41 (0.19 / 0.16) | 618 |
| H.264 NVENC intra (mp4) | `<video>` free | 8 | 193 / 195 / 195 | 0.2 | 12.6-22.3-24.9 | 219 / 3280 | - | 0.45 (0.20 / 0.16) | 1289 |
| H.264 NVENC intra (mp4) | `<video>` leader | 8 | 4 / 172 / 195 | 0.2 | 12.3-21.9-23.2 | 228 / 3447 | 15 | 0.48 (0.23 / 0.16) | 1276 |
| H.264 NVENC intra (mp4) | `<video>` rVFC-steered | 8 | 2 / 172 / 193 | 14.3 | 12.3-22.4-24.4 | 296 / 3294 | 2 / 616 | 0.48 (0.22 / 0.17) | 1290 |
| H.264 NVENC intra (mp4) | WebCodecs master clock | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.58 (0.25 / 0.22) | 691 |
| HEVC NVENC intra (mp4) | `<video>` free | 4 | 0 / 1 / 3 | 71.6 | 24.4-24.7-26.7 | 114 / 1826 | - | 0.32 (0.15 / 0.12) | 878 |
| HEVC NVENC intra (mp4) | `<video>` leader | 4 | 0 / 1 / 3 | 83.5 | 24.6-24.7-26.7 | 116 / 1820 | 0 | 0.32 (0.16 / 0.13) | 875 |
| HEVC NVENC intra (mp4) | `<video>` rVFC-steered | 4 | 0 / 1 / 3 | 53.9 | 25.1-25.6-26.5 | 132 / 1824 | 0 / 138 | 0.33 (0.16 / 0.13) | 996 |
| HEVC NVENC intra (mp4) | WebCodecs master clock | 4 | 0 / 0 / 0 | 100 | 30.1-30.1-30.1 | - | - | 0.40 (0.18 / 0.16) | 613 |
| HEVC NVENC intra (mp4) | `<video>` free | 8 | 225 / 230 / 231 | 0 | 10.5-22.5-25.1 | 218 / 3211 | - | 0.52 (0.21 / 0.20) | 1363 |
| HEVC NVENC intra (mp4) | `<video>` leader | 8 | 8 / 206 / 228 | 0.2 | 10.1-21.7-25.3 | 228 / 3327 | 24 | 0.49 (0.21 / 0.19) | 1448 |
| HEVC NVENC intra (mp4) | `<video>` rVFC-steered | 8 | 3 / 208 / 235 | 10.8 | 11.1-23.2-25.9 | 204 / 3192 | 2 / 534 | 0.50 (0.21 / 0.19) | 1339 |
| HEVC NVENC intra (mp4) | WebCodecs master clock | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.59 (0.24 / 0.23) | 684 |
| H.264 QSV intra (mp4) **QSV** | `<video>` free | 4 | 0 / 1 / 3 | 88.9 | 25.3-25.7-26.8 | 112 / 1820 | - | 0.37 (0.18 / 0.13) | 922 |
| H.264 QSV intra (mp4) **QSV** | `<video>` rVFC-steered | 4 | 1 / 2 / 4 | 23.3 | 22.9-23.4-26.5 | 119 / 1815 | 0 / 273 | 0.40 (0.18 / 0.14) | 915 |
| H.264 QSV intra (mp4) **QSV** | WebCodecs master clock | 4 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.42 (0.19 / 0.17) | 673 |
| H.264 QSV intra (mp4) **QSV** | `<video>` free | 8 | 226 / 244 / 245 | 0.5 | 9.9-23.4-24.5 | 221 / 3188 | - | 0.53 (0.21 / 0.19) | 1433 |
| H.264 QSV intra (mp4) **QSV** | `<video>` rVFC-steered | 8 | 4 / 217 / 242 | 8.2 | 10.7-23.1-25.1 | 257 / 3198 | 2 / 584 | 0.56 (0.24 / 0.20) | 1363 |
| H.264 QSV intra (mp4) **QSV** | WebCodecs master clock | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.63 (0.26 / 0.24) | 745 |
| HEVC QSV intra (mp4) **QSV** | `<video>` free | 4 | 0 / 1 / 3 | 78.1 | 23.4-23.4-26.7 | 120 / 1828 | - | 0.31 (0.16 / 0.12) | 853 |
| HEVC QSV intra (mp4) **QSV** | `<video>` rVFC-steered | 4 | 1 / 2 / 3 | 27.8 | 24.3-24.8-26.9 | 131 / 1816 | 0 / 236 | 0.35 (0.18 / 0.13) | 848 |
| HEVC QSV intra (mp4) **QSV** | WebCodecs master clock | 4 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.40 (0.18 / 0.16) | 600 |
| HEVC QSV intra (mp4) **QSV** | `<video>` free | 8 | 194 / 196 / 196 | 0 | 11.8-21.4-24.1 | 225 / 3281 | - | 0.52 (0.23 / 0.19) | 1304 |
| HEVC QSV intra (mp4) **QSV** | `<video>` rVFC-steered | 8 | 1 / 86 / 100 | 12.5 | 17.8-22.8-24.6 | 225 / 3563 | 1 / 743 | 0.54 (0.25 / 0.21) | 1321 |
| HEVC QSV intra (mp4) **QSV** | WebCodecs master clock | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.59 (0.25 / 0.23) | 698 |
| JPEG concatenated (.mjpeg) | JPEG master clock, bitmap | 4 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 1.17 (0.11 / 0.94) | 827 |
| JPEG concatenated (.mjpeg) | JPEG master clock, ImageDecoder | 4 | 0 / 0 / 0 | 100 | 29.9-29.9-29.9 | - | - | 0.76 (0.09 / 0.61) | 596 |
| JPEG concatenated (.mjpeg) | JPEG master clock, bitmap | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 2.56 (0.19 / 2.16) | 1256 |
| JPEG concatenated (.mjpeg) | JPEG master clock, ImageDecoder | 8 | 0 / 0 / 0 | 100 | 29.9-29.9-29.9 | - | - | 1.45 (0.16 / 1.19) | 795 |
| JPEG-in-MKV | JPEG master clock, bitmap | 4 | 0 / 0 / 0 | 100 | 30.1-30.1-30.1 | - | - | 1.17 (0.11 / 0.94) | 818 |
| JPEG-in-MKV | JPEG master clock, bitmap | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 2.55 (0.19 / 2.15) | 1253 |

### E45: Electron 45.2.3 / Chromium 156.0.8078.80

| file | method | N | spread p50 / p95 / max (frames) | spread = 0 % of ticks | rVFC or draws /s per stream, min-median-max | dropped / total frames (`<video>`) | corrections; rVFC hard seeks / rate changes | CPU cores total (GPU proc / Tab) | WS total MB |
|---|---|---|---|---|---|---|---|---|---|
| H.264 NVENC intra (mp4) | `<video>` free | 4 | 1 / 2 / 3 | 21.0 | 21.5-24.1-26.7 | 117 / 1821 | - | 0.28 (0.16 / 0.10) | 872 |
| H.264 NVENC intra (mp4) | `<video>` leader | 4 | 0 / 1 / 3 | 60 | 19.5-19.7-20.6 | 116 / 1824 | 0 | 0.29 (0.16 / 0.10) | 1035 |
| H.264 NVENC intra (mp4) | `<video>` rVFC-steered | 4 | 1 / 2 / 3 | 34.3 | 19.2-19.7-21.7 | 135 / 1820 | 0 / 414 | 0.30 (0.16 / 0.10) | 965 |
| H.264 NVENC intra (mp4) | WebCodecs master clock | 4 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.38 (0.19 / 0.13) | 740 |
| H.264 NVENC intra (mp4) | `<video>` free | 8 | 196 / 198 / 198 | 0.2 | 12.3-21.5-27.4 | 227 / 3273 | - | 0.46 (0.22 / 0.15) | 1428 |
| H.264 NVENC intra (mp4) | `<video>` leader | 8 | 3 / 174 / 197 | 0.5 | 12.2-21.4-27.5 | 228 / 3439 | 15 | 0.44 (0.22 / 0.14) | 1372 |
| H.264 NVENC intra (mp4) | `<video>` rVFC-steered | 8 | 2 / 170 / 195 | 3.7 | 11.5-21.8-27.4 | 256 / 3280 | 2 / 764 | 0.46 (0.23 / 0.15) | 1372 |
| H.264 NVENC intra (mp4) | WebCodecs master clock | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.55 (0.26 / 0.19) | 872 |
| HEVC NVENC intra (mp4) | `<video>` free | 4 | 1 / 2 / 3 | 26.9 | 19.9-20.1-21.2 | 115 / 1823 | - | 0.28 (0.14 / 0.10) | 993 |
| HEVC NVENC intra (mp4) | `<video>` leader | 4 | 1 / 2 / 3 | 48.9 | 20.5-20.7-21.5 | 117 / 1821 | 0 | 0.29 (0.15 / 0.10) | 1047 |
| HEVC NVENC intra (mp4) | `<video>` rVFC-steered | 4 | 1 / 2 / 2 | 45.6 | 19.5-19.8-21.8 | 140 / 1820 | 0 / 435 | 0.29 (0.15 / 0.10) | 1054 |
| HEVC NVENC intra (mp4) | WebCodecs master clock | 4 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.36 (0.17 / 0.13) | 835 |
| HEVC NVENC intra (mp4) | `<video>` free | 8 | 223 / 233 / 233 | 0.5 | 10.6-21.6-27.2 | 218 / 3202 | - | 0.47 (0.20 / 0.15) | 1550 |
| HEVC NVENC intra (mp4) | `<video>` leader | 8 | 3 / 124 / 147 | 0.2 | 13.2-22.1-27.6 | 238 / 3466 | 13 | 0.45 (0.21 / 0.15) | 1513 |
| HEVC NVENC intra (mp4) | `<video>` rVFC-steered | 8 | 9 / 198 / 227 | 10 | 10.5-21.7-25.1 | 216 / 3408 | 2 / 850 | 0.50 (0.24 / 0.17) | 1523 |
| HEVC NVENC intra (mp4) | WebCodecs master clock | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.51 (0.23 / 0.18) | 1022 |
| H.264 QSV intra (mp4) **QSV** | `<video>` free | 4 | 0 / 1 / 3 | 56.0 | 19.9-20.4-22.1 | 120 / 1824 | - | 0.34 (0.18 / 0.11) | 951 |
| H.264 QSV intra (mp4) **QSV** | `<video>` rVFC-steered | 4 | 1 / 2 / 3 | 38.3 | 19.4-20.2-22.7 | 135 / 1819 | 0 / 386 | 0.36 (0.18 / 0.12) | 997 |
| H.264 QSV intra (mp4) **QSV** | WebCodecs master clock | 4 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.38 (0.19 / 0.13) | 965 |
| H.264 QSV intra (mp4) **QSV** | `<video>` free | 8 | 224 / 244 / 245 | 0.5 | 10.3-21.7-25.6 | 235 / 3183 | - | 0.54 (0.23 / 0.17) | 1510 |
| H.264 QSV intra (mp4) **QSV** | `<video>` rVFC-steered | 8 | 10 / 213 / 245 | 4.9 | 10.2-22.9-25.7 | 236 / 3190 | 2 / 805 | 0.55 (0.25 / 0.19) | 1468 |
| H.264 QSV intra (mp4) **QSV** | WebCodecs master clock | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.57 (0.27 / 0.20) | 1104 |
| HEVC QSV intra (mp4) **QSV** | `<video>` free | 4 | 0 / 1 / 3 | 59.2 | 19.9-20.1-22.1 | 120 / 1824 | - | 0.29 (0.15 / 0.10) | 977 |
| HEVC QSV intra (mp4) **QSV** | `<video>` rVFC-steered | 4 | 1 / 2 / 3 | 46.3 | 19.3-19.7-22.4 | 136 / 1817 | 0 / 372 | 0.30 (0.16 / 0.10) | 966 |
| HEVC QSV intra (mp4) **QSV** | WebCodecs master clock | 4 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.37 (0.19 / 0.13) | 759 |
| HEVC QSV intra (mp4) **QSV** | `<video>` free | 8 | 192 / 195 / 195 | 0.2 | 12.9-21.9-27.7 | 231 / 3282 | - | 0.46 (0.22 / 0.15) | 1428 |
| HEVC QSV intra (mp4) **QSV** | `<video>` rVFC-steered | 8 | 2 / 169 / 196 | 12.2 | 11.9-20.7-25 | 213 / 3264 | 2 / 729 | 0.47 (0.22 / 0.16) | 1418 |
| HEVC QSV intra (mp4) **QSV** | WebCodecs master clock | 8 | 0 / 0 / 0 | 100 | 30-30.0-30 | - | - | 0.52 (0.24 / 0.18) | 924 |
| JPEG concatenated (.mjpeg) | JPEG master clock, bitmap | 4 | 0 / 0 / 0 | 100 | 29.9-29.9-29.9 | - | - | 1.04 (0.11 / 0.84) | 939 |
| JPEG concatenated (.mjpeg) | JPEG master clock, ImageDecoder | 4 | 0 / 0 / 0 | 100 | 29.9-29.9-29.9 | - | - | 0.77 (0.09 / 0.62) | 714 |
| JPEG concatenated (.mjpeg) | JPEG master clock, bitmap | 8 | 0 / 0 / 0 | 100 | 29.9-29.9-29.9 | - | - | 2.14 (0.20 / 1.77) | 1396 |
| JPEG concatenated (.mjpeg) | JPEG master clock, ImageDecoder | 8 | 0 / 0 / 0 | 100 | 29.9-29.9-29.9 | - | - | 1.44 (0.15 / 1.19) | 987 |
| JPEG-in-MKV | JPEG master clock, bitmap | 4 | 0 / 0 / 0 | 100 | 29.9-29.9-29.9 | - | - | 1.05 (0.11 / 0.84) | 967 |
| JPEG-in-MKV | JPEG master clock, bitmap | 8 | 0 / 0 / 0 | 100 | 29.9-29.9-29.9 | - | - | 2.14 (0.20 / 1.77) | 1390 |

Source: `bench/<e35|e45>/bench_intra_sync/c1080p30_<file>__<method>__n<N>.json`, fields `result.spread`, `result.spread_exact0_pct`, `result.rvfc_or_draws_per_s`, `result.dropped`, `result.follower_corrections`, `result.rvfc_hard_seeks`, `result.rvfc_rate_changes`, `metrics_summary.cpu_cores_total_from_cumulative`, `metrics_summary.GPU|Tab.cpu_cores_from_cumulative`, `metrics_summary.total_ws_mb_last`. Master-clock rows also record `result.lag_max` (target minus slowest stream): 0 / 0 / 0 in every master-clock config.

**N = 8 `<video>`: one or two tiles stall.** In 19 of 20 N = 8 `<video>` configs (both Electrons, all files) the slowest stream delivered under 65 % of the median stream's rVFC callbacks (slowest stream 42-78 % of the median across the 20 configs). This drives the N = 8 max spread to 100-245 frames:

| Electron | config | rVFC callbacks per stream (stream 0..7) | `getVideoPlaybackQuality` total frames per stream |
|---|---|---|---|
| E35 | `h264_nvenc_intra.mp4__video-free__n8` | 373, 374, 336, 352, 192, 189, 333, 325 | 458, 459, 456, 458, 267, 267, 460, 455 |
| E35 | `h264_nvenc_intra.mp4__video-leader__n8` | 342, 348, 344, 337, 184, 304, 318, 319 | 458, 459, 457, 457, 268, 434, 459, 455 |
| E35 | `h264_nvenc_intra.mp4__video-rvfc__n8` | 366, 351, 347, 343, 186, 185, 329, 310 | 460, 459, 459, 459, 272, 271, 459, 455 |
| E35 | `hevc_qsv_intra.mp4__video-free__n8` | 350, 362, 338, 331, 177, 177, 306, 310 | 458, 459, 459, 458, 266, 266, 459, 456 |
| E35 | `hevc_qsv_intra.mp4__video-rvfc__n8` | 369, 349, 343, 342, 267, 339, 343, 333 | 458, 459, 457, 457, 365, 457, 457, 453 |
| E45 | `h264_nvenc_intra.mp4__video-free__n8` | 322, 324, 313, 333, 185, 189, 346, 411 | 459, 458, 457, 456, 264, 263, 460, 456 |
| E45 | `h264_nvenc_intra.mp4__video-leader__n8` | 312, 313, 326, 322, 183, 319, 390, 413 | 459, 457, 457, 457, 266, 429, 459, 455 |
| E45 | `h264_nvenc_intra.mp4__video-rvfc__n8` | 356, 330, 324, 311, 182, 173, 411, 336 | 459, 459, 458, 458, 267, 268, 457, 454 |
| E45 | `hevc_qsv_intra.mp4__video-free__n8` | 330, 318, 326, 370, 193, 196, 375, 415 | 460, 459, 458, 457, 267, 267, 459, 455 |
| E45 | `hevc_qsv_intra.mp4__video-rvfc__n8` | 366, 335, 310, 375, 178, 180, 312, 306 | 458, 456, 456, 456, 266, 264, 456, 452 |

(Subset shown: H.264 NVENC and HEVC QSV files; the other N = 8 `<video>` configs show the same pattern in `result.per_stream[*].rvfc_callbacks`.) Streams 4 and 5 are the slow ones in most configs. With the 3 x 3 grid (`harness.mjs:97`) these are the centre and middle-right tiles; whether the cause is tile position, open order or decoder/compositor scheduling is not determined (*inferred*: not a codec effect, since all four files and both Electrons show it). The N = 8 `<video>` items also took ~31 s of wall time per config against ~16 s for N = 4 and for all master-clock configs (stdout logs), with the same ~14.5 s measurement window (`metrics_summary.window_s`).

## 5. Drag scrub (N = 4 / 8, 1080p30, 8 s simulated drag, 90 frames/s slider speed)

`<video>` gated = set `currentTime` only when the previous seek finished (pending target applied on `seeked`). WebCodecs = `frameAt(target)` loop per stream with `wcflush=1` (reset + configure + decode + flush for each new target). JPEG = Range fetch + decode per target. Input events arrive every ~16 ms, so ~60 presents/s per stream is the ceiling (*inferred* from `sleep(16)` in `harness.mjs:485`, `:507`).

### E35: Electron 35.7.5 / Chromium 134.0.6998.205

| file | method | N | input events | frames shown /s per stream min-max | distinct /s min-max | lag p50 / p95 / max (frames) | per-stream errors (sum; streams > 0) | CPU cores total (GPU proc) | WS total MB (last) | GPU proc peak `private_kb` (raw; unit NOT VERIFIED, FINDINGS F22); GPU pids (corrected 2026-11-10, GF05: was private_kb / 1,048,576 labelled GB) |
|---|---|---|---|---|---|---|---|---|---|---|
| H.264 NVENC intra (mp4) | `<video>` gated | 4 | 477 | 37.38-40 | 34.12-36.25 | 4 / 7 / 11 | n/a | 1.21 (0.33) | 1062 | 528,776; 1 |
| H.264 NVENC intra (mp4) | WebCodecs (wcflush) | 4 | 472 | 52.88-53.25 | 48.75-49.25 | 3 / 6 / 11 | 0; 0 | 1.60 (0.85) | 734 | 13,610,276; 1 |
| H.264 NVENC intra (mp4) | `<video>` gated | 8 | 460 | 33-39.62 | 30.50-35.75 | 6 / 22 / 42 | n/a | 2.46 (0.40) | 1464 | 897,088; 1 |
| H.264 NVENC intra (mp4) | WebCodecs (wcflush) | 8 | 421 | 19.50-20.38 | 19.50-20.25 | 9 / 68 / 85 | **300; 5** | 1.27 (0.67) | 373 | 32,454,048; 2 **(GPU process replaced)** |
| HEVC NVENC intra (mp4) | `<video>` gated | 4 | 479 | 40.75-43.50 | 37.62-40.25 | 3 / 6 / 9 | n/a | 1.63 (0.38) | 1115 | 611,112; 1 |
| HEVC NVENC intra (mp4) | WebCodecs (wcflush) | 4 | 436 | 22.12-22.38 | 21.75-22.12 | 9 / 23 / 56 | **4; 4** | 0.93 (0.61) | 243 | 33,430,108; 1 |
| HEVC NVENC intra (mp4) | `<video>` gated | 8 | 457 | 36.75-41.50 | 33.38-36.62 | 5 / 23 / 40 | n/a | 2.51 (0.44) | 1459 | 878,008; 1 |
| HEVC NVENC intra (mp4) | WebCodecs (wcflush) | 8 | 423 | 11-11.12 | 11-11.12 | 13 / 71 / 88 | **80; 8** | 1.04 (0.68) | 246 | 32,392,112; 1 |
| H.264 QSV intra (mp4) | `<video>` gated | 4 | 473 | 28.75-30.88 | 27.88-29.88 | 5 / 9 / 12 | n/a | 1.20 (0.33) | 1202 | 531,792; 1 |
| H.264 QSV intra (mp4) | WebCodecs (wcflush) | 4 | 466 | 51.12-51.38 | 48-48.62 | 3 / 6 / 9 | 0; 0 | 1.50 (0.72) | 19868 | 27,504,736; 1 |
| H.264 QSV intra (mp4) | `<video>` gated | 8 | 444 | 18.25-20.62 | 17.88-19.75 | 11 / 25 / 36 | n/a | 2.11 (0.35) | 1591 | 901,812; 1 |
| H.264 QSV intra (mp4) | WebCodecs (wcflush) | 8 | 423 | 20-21.88 | 20-21.75 | 8 / 104 / 121 | **523; 5** | 1.37 (0.66) | 467 | 32,820,036; 2 **(GPU process replaced)** |
| HEVC QSV intra (mp4) | `<video>` gated | 4 | 478 | 40.50-42.38 | 38-39.50 | 3 / 6 / 10 | n/a | 1.56 (0.37) | 1149 | 608,940; 1 |
| HEVC QSV intra (mp4) | WebCodecs (wcflush) | 4 | 465 | 46.50-46.75 | 45.25-45.62 | 3 / 8 / 13 | 0; 0 | 1.55 (0.89) | 12033 | 22,446,108; 1 |
| HEVC QSV intra (mp4) | `<video>` gated | 8 | 467 | 36.25-45.50 | 34-40.25 | 5 / 20 / 33 | n/a | 2.31 (0.44) | 1499 | 874,384; 1 |
| HEVC QSV intra (mp4) | WebCodecs (wcflush) | 8 | 417 | 11.12-11.25 | 11.12-11.25 | 13 / 55 / 69 | **7; 7** | 1.03 (0.70) | 362 | 33,426,832; 2 **(GPU process replaced)** |
| JPEG concatenated (.mjpeg) | Range + createImageBitmap | 4 | 465 | 58-58 | 51-51 | 2 / 2 / 8 | 0; 0 | 2.57 (0.26) | 780 | 584,252; 1 |
| JPEG concatenated (.mjpeg) | Range + ImageDecoder | 4 | 468 | 58.50-58.50 | 52.50-52.50 | 2 / 2 / 7 | 0; 0 | 1.67 (0.20) | 488 | 552,380; 1 |
| JPEG concatenated (.mjpeg) | Range + createImageBitmap | 8 | 365 | 41.75-41.88 | 36.75-36.88 | 4 / 6 / 10 | 0; 0 | 4.32 (0.36) | 806 | 738,816; 1 |
| JPEG concatenated (.mjpeg) | Range + ImageDecoder | 8 | 469 | 58.62-58.62 | 51.12-51.12 | 2 / 2 / 9 | 0; 0 | 3.20 (0.37) | 723 | 750,968; 1 |
| JPEG-in-MKV | Range + createImageBitmap | 4 | 466 | 58.25-58.25 | 52-52 | 2 / 2 / 7 | 0; 0 | 2.58 (0.27) | 665 | 588,004; 1 |
| JPEG-in-MKV | Range + ImageDecoder | 4 | 469 | 58.62-58.62 | 52.38-52.38 | 2 / 2 / 8 | 0; 0 | 1.67 (0.20) | 584 | 543,176; 1 |
| JPEG-in-MKV | Range + createImageBitmap | 8 | 367 | 42.38-42.50 | 38.12-38.38 | 4 / 6 / 9 | 0; 0 | 4.32 (0.35) | 796 | 731,400; 1 |
| JPEG-in-MKV | Range + ImageDecoder | 8 | 469 | 58.50-58.50 | 51.50-51.50 | 2 / 2 / 9 | 0; 0 | 3.17 (0.36) | 723 | 763,952; 1 |

### E45: Electron 45.2.3 / Chromium 156.0.8078.80

| file | method | N | input events | frames shown /s per stream min-max | distinct /s min-max | lag p50 / p95 / max (frames) | per-stream errors (sum; streams > 0) | CPU cores total (GPU proc) | WS total MB (last) | GPU proc peak `private_kb` (raw; unit NOT VERIFIED, FINDINGS F22); GPU pids (corrected 2026-11-10, GF05: was private_kb / 1,048,576 labelled GB) |
|---|---|---|---|---|---|---|---|---|---|---|
| H.264 NVENC intra (mp4) | `<video>` gated | 4 | 473 | 35.62-36.75 | 33-34.12 | 5 / 8 / 10 | n/a | 1.14 (0.32) | 1076 | 528,544; 1 |
| H.264 NVENC intra (mp4) | WebCodecs (wcflush) | 4 | 471 | 53-53.25 | 49-49.50 | 3 / 6 / 14 | 0; 0 | 1.26 (0.70) | 2208 | 12,566,368; 1 |
| H.264 NVENC intra (mp4) | `<video>` gated | 8 | 459 | 34.88-41.75 | 31.75-36.75 | 6 / 28 / 42 | n/a | 2.39 (0.40) | 1517 | 888,792; 1 |
| H.264 NVENC intra (mp4) | WebCodecs (wcflush) | 8 | 405 | 25-25.25 | 24.12-24.88 | 8 / 13 / 15 | 0; 0 | 1.15 (0.61) | 31904 | 39,695,312; 1 |
| HEVC NVENC intra (mp4) | `<video>` gated | 4 | 475 | 39.88-42 | 37.50-39.38 | 3 / 6 / 9 | n/a | 1.42 (0.36) | 1262 | 609,488; 1 |
| HEVC NVENC intra (mp4) | WebCodecs (wcflush) | 4 | 442 | 42.88-43.12 | 41.25-41.88 | 3 / 10 / 16 | 0; 0 | 1.25 (0.76) | 11023 | 18,429,068; 1 |
| HEVC NVENC intra (mp4) | `<video>` gated | 8 | 466 | 36.50-45.38 | 34.25-41.25 | 5 / 13 / 29 | n/a | 2.52 (0.47) | 1630 | 870,064; 1 |
| HEVC NVENC intra (mp4) | WebCodecs (wcflush) | 8 | 387 | 12.75-12.88 | 12.62-12.88 | 14 / 27 / 42 | 0; 0 | 0.93 (0.62) | 20253 | 31,540,568; 1 |
| H.264 QSV intra (mp4) | `<video>` gated | 4 | 471 | 28-30.25 | 26.50-29.25 | 6 / 10 / 12 | n/a | 1.13 (0.33) | 1303 | 534,308; 1 |
| H.264 QSV intra (mp4) | WebCodecs (wcflush) | 4 | 471 | 56-56.50 | 50.62-51.50 | 3 / 5 / 7 | 0; 0 | 1.29 (0.68) | 1778 | 9,586,248; 1 |
| H.264 QSV intra (mp4) | `<video>` gated | 8 | 438 | 17.25-21.62 | 16.38-20.38 | 10 / 23 / 38 | n/a | 2.12 (0.32) | 1693 | 894,636; 1 |
| H.264 QSV intra (mp4) | WebCodecs (wcflush) | 8 | 408 | 26.12-26.25 | 25.12-25.88 | 7 / 11 / 14 | 0; 0 | 1.24 (0.66) | 27038 | 34,609,500; 1 |
| HEVC QSV intra (mp4) | `<video>` gated | 4 | 477 | 38.50-40.62 | 35.50-38 | 4 / 6 / 9 | n/a | 1.32 (0.35) | 1178 | 610,812; 1 |
| HEVC QSV intra (mp4) | WebCodecs (wcflush) | 4 | 419 | 29.25-29.25 | 28.50-28.88 | 7 / 13 / 18 | 0; 0 | 0.97 (0.63) | 19021 | 28,510,552; 1 |
| HEVC QSV intra (mp4) | `<video>` gated | 8 | 466 | 35.50-42 | 32.75-38.25 | 6 / 24 / 34 | n/a | 2.43 (0.44) | 1514 | 883,272; 1 |
| HEVC QSV intra (mp4) | WebCodecs (wcflush) | 8 | 390 | 12.62-12.75 | 12.50-12.62 | 15 / 24 / 30 | 0; 0 | 0.87 (0.59) | 22160 | 33,952,724; 1 |
| JPEG concatenated (.mjpeg) | Range + createImageBitmap | 4 | 466 | 58.25-58.25 | 51.12-51.12 | 2 / 2 / 9 | 0; 0 | 2.24 (0.26) | 763 | 577,484; 1 |
| JPEG concatenated (.mjpeg) | Range + ImageDecoder | 4 | 470 | 58.75-58.75 | 53-53 | 2 / 2 / 9 | 0; 0 | 1.56 (0.20) | 675 | 558,604; 1 |
| JPEG concatenated (.mjpeg) | Range + createImageBitmap | 8 | 394 | 49-49.12 | 44-44.12 | 3 / 4 / 10 | 0; 0 | 4.19 (0.45) | 963 | 716,460; 1 |
| JPEG concatenated (.mjpeg) | Range + ImageDecoder | 8 | 465 | 58-58 | 50.50-50.50 | 2 / 2 / 10 | 0; 0 | 3.05 (0.36) | 800 | 786,164; 1 |
| JPEG-in-MKV | Range + createImageBitmap | 4 | 467 | 58.25-58.25 | 50.75-50.75 | 2 / 2 / 10 | 0; 0 | 2.21 (0.26) | 755 | 574,036; 1 |
| JPEG-in-MKV | Range + ImageDecoder | 4 | 468 | 58.50-58.50 | 50.12-50.12 | 2 / 2 / 9 | 0; 0 | 1.55 (0.20) | 613 | 553,676; 1 |
| JPEG-in-MKV | Range + createImageBitmap | 8 | 407 | 50.62-50.75 | 46.12-46.25 | 3 / 4 / 12 | 0; 0 | 4.34 (0.47) | 964 | 706,616; 1 |
| JPEG-in-MKV | Range + ImageDecoder | 8 | 468 | 58.50-58.50 | 50.75-50.75 | 2 / 2 / 9 | 0; 0 | 3.12 (0.38) | 799 | 783,976; 1 |

JPEG createImageBitmap at N = 8 is the only JPEG case below ~58 shown/s (41.8-42.5 /s E35, 49.0-50.8 /s E45), and those runs also logged fewer input events (365-407 vs 465-470 for the other JPEG configs), i.e. the page's event loop was busy (*inferred*); ImageDecoder at N = 8 stayed at 58.0-58.6 /s with ~3.1 CPU cores against ~4.2-4.3 for bitmap.

Source: `bench/<e35|e45>/bench_intra_scrub/c1080p30_<file>__<method>__n<N>.json`, fields `result.input_events`, `result.frames_shown_per_s`, `result.distinct_per_s`, `result.lag_frames`, `result.per_stream[*].errors`, `metrics_summary.*`, and `metrics_samples[*]` (type `GPU`: `private_kb`, `pid`).

**WebCodecs scrub grows the GPU process's private bytes fast.** In all 16 WebCodecs scrub configs the GPU process's `private_kb` climbs during the 8 s drag (peaks 9,586,248-39,695,312 `private_kb`, table above), while no `<video>` or JPEG scrub config exceeds 901,812 `private_kb`. In E35, three N = 8 configs show a second GPU-process pid in `metrics_samples` (the GPU process was replaced mid-run); the new process's first sample is 82,404-99,088 `private_kb`, together with the per-stream errors; E35 HEVC NVENC N = 4 and N = 8 show the drop and errors with one pid. E45 shows the same growth without a replacement or errors within the 8 s window. Example series, GPU process `private_kb` / 1,048,576 at 1 s steps (`metrics_samples`, every other 500 ms sample). (corrected 2026-11-10, GF05: these values were labelled "GB"; they are `private_kb` / 1,048,576, which is GiB only if Electron's "Kilobytes" are 1024 bytes; unit NOT VERIFIED, FINDINGS F22. Raw peaks per config: `gapfill/GF05_private_kb_cells.json`.)

| config | series (s: `private_kb` / 1,048,576; unit NOT VERIFIED, FINDINGS F22) |
|---|---|
| E35 `h264_nvenc_intra.mp4__webcodecs__n8` | 0: 5.1, 1: 12.9, 2: 18.1, 3: 24.2, 4: 27.8, 5: 31.0, 6: 21.1, 7: 2.2, 8: 0.1 |
| E45 `h264_nvenc_intra.mp4__webcodecs__n8` | 0: 4.4, 1: 11.0, 2: 14.8, 3: 19.9, 4: 26.0, 5: 26.5, 6: 32.3, 7: 35.7, 8: 37.9 |
| E35 `hevc_nvenc_intra.mp4__webcodecs__n4` | 0: 4.3, 1: 11.1, 2: 16.1, 3: 19.6, 4: 23.1, 5: 26.3, 6: 29.5, 7: 31.9, 8: 18.8, 9: 5.2 |

*Inferred:* the per-target `reset()` + `configure()` + `flush()` cycle in `WcSource.frameAt` (`harness.mjs:137-152`) is the likely trigger, since the frames themselves are closed after drawing (`harness.mjs:501`). This makes the WebCodecs scrub rates a measurement of this harness pattern, not of WebCodecs decode capacity. The WebCodecs seek bench uses the same pattern (199 resets per 200 seeks) but records no memory, so whether it also grows is unknown.

## 6. E35 vs E45

| measure | E35 (Electron 35.7.5 / Chromium 134) | E45 (Electron 45.2.3 / Chromium 156) | source fields |
|---|---|---|---|
| seek p50, WebCodecs (4 video files), ms | 3.1-3.4 | 2.7-2.9 | `bench_intra_seek/*__webcodecs.json` `result.summary.lat_ms.p50` |
| seek p50, `<video>` to rVFC (4 video files), ms | 11.8-14.1 | 8.5-14.1 | `bench_intra_seek/*__video__mid.json` `result.summary.lat_rvfc_ms.p50` |
| seek p50, Range + createImageBitmap (2 JPEG files), ms | 7.0-7.1 | 6.0-6.1 | `bench_intra_seek/*__jpeg-range-bitmap.json` `result.summary.lat_ms.p50` |
| seek p50, Range + ImageDecoder (2 JPEG files), ms | 4.4-4.4 | 4.6-4.6 | `bench_intra_seek/*__jpeg-range-imagedecoder.json` `result.summary.lat_ms.p50` |
| N = 4 `<video>` configs: median rVFC callbacks/s per stream (10 configs) | 23.4-26.0 | 19.7-24.1 | `result.rvfc_or_draws_per_s` |
| N = 4 `<video>` configs: spread = 0 % of ticks | 23.3-90.3 | 21.0-60.0 | `result.spread_exact0_pct` |
| N = 4 `<video>` configs: spread max, frames | 3-4 | 2-3 | `result.spread.max` |
| N = 8 JPEG master clock bitmap: CPU cores total (2 files) | 2.55-2.56 | 2.14-2.14 | `metrics_summary.cpu_cores_total_from_cumulative` |
| N = 8 WebCodecs master clock: WS total MB (4 files) | 684-745 | 872-1104 | `metrics_summary.total_ws_mb_last` |
| WebCodecs scrub: per-stream errors summed over 8 configs | 914 | 0 | `result.per_stream[*].errors` |
| WebCodecs scrub N = 8: min-stream frames shown/s (4 files) | 11.00-20.00 | 12.62-26.12 | `result.frames_shown_per_s` |
| JPEG bitmap scrub N = 8: min-stream frames shown/s (2 files) | 41.75-42.38 | 49.00-50.62 | `result.frames_shown_per_s` |

- Seek exactness, sync behaviour of the master-clock paths (spread 0 everywhere) and the N = 8 `<video>` stall are the same in both.
- E45 delivers fewer rVFC callbacks per stream at N = 4 than E35, and its N = 4 `<video>` streams are less often index-aligned (lower spread = 0 %), though max spread stays at 2-4 frames in both. This matches the functional finding that E45 delivered fewer rVFC callbacks (`NOTES.md` 4.3).
- WebCodecs and createImageBitmap seeks are faster in E45; ImageDecoder seeks are slightly slower.
- E35's GPU process was replaced during 3 WebCodecs scrub configs and logged per-stream errors in 5; E45 logged none, but its GPU-process private bytes grew just as fast (section 5).

## 7. Headline numbers

1. **Every seek landed on the requested frame:** `exact` = 200 of 200 in all 24 seek configs (12 per Electron; H.264/HEVC NVENC/QSV via `<video>` and WebCodecs, JPEG via bitmap and ImageDecoder). Path: `bench/<e35|e45>/bench_intra_seek/*.json` -> `result.summary.exact`, `result.summary.n`.
2. **WebCodecs intra seek (fetch + decode) is the fastest single-frame path:** p50 2.7-2.9 ms in E45 and 3.1-3.4 ms in E35 across the four intra files, e.g. H.264 NVENC E45 p50 2.7 ms / p95 4.0 ms. Path: `bench/e45/bench_intra_seek/c1080p30_h264_nvenc_intra.mp4__webcodecs.json` -> `result.summary.lat_ms.p50` / `.p95`.
3. **JPEG seek costs more per frame:** Range + ImageDecoder p50 4.6 ms (E45) / 4.4 ms (E35); Range + createImageBitmap p50 6.0 ms (E45) / 7.0 ms (E35), on `.mjpeg`; JPEG-in-MKV is within 0.1 ms of it. Path: `bench/e45/bench_intra_seek/c1080p30_jpeg_seq__jpeg-range-imagedecoder.json` and `...__jpeg-range-bitmap.json` -> `result.summary.lat_ms.p50`.
4. **`<video>` seeks reach the rVFC callback in p50 8.5-14.1 ms** (the `seeked` event fires at p50 1.3-1.6 ms). E.g. HEVC NVENC E45 rVFC p50 14.1 ms, `seeked` p50 1.5 ms. Path: `bench/e45/bench_intra_seek/c1080p30_hevc_nvenc_intra.mp4__video__mid.json` -> `result.summary.lat_rvfc_ms.p50`, `result.summary.lat_seeked_ms.p50`.
5. **Master-clock sync is frame-exact at N = 8 for both WebCodecs and JPEG, and WebCodecs costs about a quarter of the CPU of the JPEG bitmap path:** spread 0 / 0 / 0 frames (100 % of ticks) in all 28 master-clock configs; at N = 8 in E45, H.264 NVENC `wc-master` uses 0.55 CPU cores and 872 MB, against 2.14 cores / 1396 MB for JPEG bitmap and 1.44 cores / 987 MB for JPEG ImageDecoder. Paths: `bench/e45/bench_intra_sync/c1080p30_h264_nvenc_intra.mp4__wc-master__n8.json`, `bench/e45/bench_intra_sync/c1080p30_jpeg_seq__jpeg-master-range-bitmap__n8.json`, `...__jpeg-master-range-imagedecoder__n8.json` -> `result.spread`, `metrics_summary.cpu_cores_total_from_cumulative`, `metrics_summary.total_ws_mb_last`.
6. **`<video>` sync holds at N = 4 but breaks at N = 8:** H.264 NVENC `video-free` E45 spread max 3 frames at N = 4, but p50 196 / max 198 frames at N = 8, because two of eight tiles get under 60 % of the median stream's rVFC callbacks (185 and 189 vs 313-411; section 4); leader correction and rVFC steering do not fix it (N = 8 spread p95 86-217 frames). Path: `bench/e45/bench_intra_sync/c1080p30_h264_nvenc_intra.mp4__video-free__n8.json` -> `result.spread`, `result.per_stream[*].rvfc_callbacks`.
7. **Scrubbing at N = 8: JPEG + ImageDecoder keeps up, `<video>` gated lags:** JPEG `.mjpeg` ImageDecoder E45 58.0-58.0 frames shown/s per stream, lag p50 / p95 2 / 2 frames; HEVC NVENC `<video>` gated E45 36.5-45.4 /s, lag p50 / p95 5 / 13. Paths: `bench/e45/bench_intra_scrub/c1080p30_jpeg_seq__jpeg-range-imagedecoder__n8.json`, `bench/e45/bench_intra_scrub/c1080p30_hevc_nvenc_intra.mp4__video-gated__n8.json` -> `result.frames_shown_per_s`, `result.lag_frames`.
8. **The WebCodecs scrub numbers are not usable as capacity figures:** GPU-process peak `private_kb` reaches 9,586,248-39,695,312 within 8 s (corrected 2026-11-10, GF05: was "9-38 GB"; Electron's kilobyte unit is NOT VERIFIED, FINDINGS F22), E35 replaced its GPU process in 3 configs, e.g. E35 H.264 QSV N = 8: 523 per-stream errors, 20.0 frames shown/s, 2 GPU pids. Path: `bench/e35/bench_intra_scrub/c1080p30_h264_qsv_intra.mp4__webcodecs__n8.json` -> `result.per_stream[*].errors`, `metrics_samples[type=GPU].private_kb|pid`.

## 8. Caveats

- **Clip quality.** Generator target `target_y_psnr_db` = 55.0 (`clips_summary.json` `generator`). Measured on the bench clips (`clips_summary.json` `clips.<clip>.decode_check_mp4` / `decode_check`, 60 frames):

  | clip | encoder setting (`quality_param`) | bytes (600 frames) | Y-PSNR mean dB | Y-SSIM mean |
  |---|---|---|---|---|
  | h264_nvenc_intra.mp4 | h264_nvenc 14 | 109,174,200 | 54.49 | 0.9969 |
  | hevc_nvenc_intra.mp4 | hevc_nvenc 11 | 127,807,632 | 54.92 | 0.9971 |
  | h264_qsv_intra.mp4 | h264_qsv 8 | 134,142,671 | 54.93 | 0.9972 |
  | hevc_qsv_intra.mp4 | hevc_qsv 17 | 110,776,615 | 55.01 | 0.9972 |
  | jpeg_seq | mjpeg_qsv 4:2:2 (yuyv422 full range in) 90 | 124,162,572 | 54.55 | 0.9975 |
  | jpeg_in_mkv | mjpeg_qsv 4:2:2 (yuyv422 full range in) 90 | 124,189,970 | 54.55 | 0.9975 |

  This is about 55 dB, not intra_compare's target A (SSIM-Y 0.9961, ~52 dB) or target B (45 dB) (`HANDOFF.md` loose ends). Do not mix these numbers with intra_compare results at A or B.
- **Content.** 1080p30 CFR, 600 frames, only 19 distinct source frames looped (`clips_summary.json` `distinct_source_frames`), with the frame-index pattern burned in. MP4 (+faststart) only for H.264/HEVC; fragmented MP4, MKV and VFR files were not benched (functional results cover them).
- **QSV files are decoded on the NVIDIA GPU** in Chromium (the active `gpuDevice`; `FINDINGS.md`, a draft not yet verified, reports that `<video>` uses D3D11VideoDecoder on the NVIDIA GPU). "QSV" rows test QSV-encoded bitstreams, not Intel decode.
- **One run per config, no repeats**; between-run variance is unknown. IP-SYNC-QSV ran ~3 h after IP-SYNC (03:43 vs 00:36), so QSV vs NVENC sync rows were not measured back to back.
- **P-cores only:** 16 logical CPUs. CPU cores are Electron-process CPU time / window (`main.cjs:93-101`), not system CPU; the GPU's own decode load is only in the nvidia-smi point samples.
- **Localhost HTTP.** JPEG and WebCodecs latencies include a Range fetch from the harness's local server with `cache: 'no-store'` (`harness.mjs:129`, `:181`); file-system or network sources will differ.
- **Display timing.** rVFC rates and `lat_rvfc_ms` depend on the compositor/vsync; the display refresh rate was not recorded, and a Parsec virtual display adapter was present (runner start state). The `<video>` seek-to-rVFC p50s (8.5-14.1 ms, section 3) are under one 60 Hz frame period (16.7 ms); the cause of the rVFC delay is not determined (corrected 2026-11-10, GF05: the earlier "~14 ms rVFC p50 is consistent with one 60 Hz frame" was wrong, since one 60 Hz frame is 16.7 ms; aligned with FINDINGS F18).
- **Sync bench does not read the pattern** (`readpattern` not set), so spread is index-based (rVFC `mediaTime` or drawn index), not verified pixels. The functional run did check pixels (`NOTES.md` 4.3).
- **WebCodecs paths use `wcflush=1`** (reset + flush per target). A sequential WebCodecs scrub without per-target reset was not measured; see the memory growth in section 5.
- **`_index*.json` and `bench_tables.md` hide per-stream scrub errors**: the index records only whole-config failures (`run_suite.py:358`), and the summarizer prints no error or memory columns for scrub (`summarize.py:181-186`). Use this document or the JSON.
- **Seek configs have no CPU/memory data** (`metrics_summary` null).

Generated tables for the same JSON: `bench/bench_tables.md` (IP-SUM-3, 2026-11-10 03:51).
