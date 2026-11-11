# intra_compare bench results: 23:00 run of 2026-11-09

- **Run:** `20261109T230007` (runner `scripts/bench_runner/run_queue.py`). The intra_compare items ran 2026-11-09 23:00 to 2026-11-10 04:19 local (UTC-5). Queue and item definitions: `results/BENCH_QUEUE_2300.md`.
- **Machine:** Gerald (i7-14700K, `cpu_count` 28). **Results are for 16 logical CPUs (P-cores), not all 28.** Every JSON records `system_before.process_cpu_affinity` = 0–15. **Exception:** the libx265 rows of items 1–3 used 23–27 cores; see caveat 1.
- **Software, as recorded in the JSON `system_before` blocks (identical in all 27 files):** PyAV 19.0.2, libavcodec 63.1.102 (the FFmpeg 9.0.2 that PyAV bundles, per the `benchpaths.py:3` docstring), simplejpeg 1.9.0, nvImageCodec `0.10.0` (pinned 0.10.0.9), Python 3.12.13.
- **GPUs:** display devices `NVIDIA GeForce RTX 3070`, `Intel(R) UHD Graphics 770` and `Parsec Virtual Display Adapter`, all `OK|True`. The DXGI adapter list has two RTX 3070 LUIDs, the UHD 770 and the Microsoft Basic Render Driver.
- **Driver versions are not in the JSONs.** The env-block nvidia-smi query is session count and utilisation only (`benchpaths.py:294`). The run context gives NVIDIA driver 610.88; these files do not confirm it. No Intel driver version is recorded.
- **Data:** the 27 JSON files in `results/intra_compare/bench/` (paths below are relative to `results/intra_compare/`). The folder holds no other files: no older or smoke JSONs remain there.
- **Terminology** (`FINDINGS.md`, `matched_settings.json`):
  - **Target A:** SSIM-Y 0.9961, camera-equivalent, about 52 dB PSNR-Y.
  - **Target B:** PSNR-Y 45 dB.
  - **jt422:** libjpeg-turbo 4:2:2.
  - **QC:** the in-pipeline quality check.

## 1. Load record

Source: the per-item load record of the run, built from `results/BENCH_RUN_2300_LOG.jsonl`.
- **CPU % before:** 10 s of typeperf total CPU before the item.
- **Top process:** CPU seconds in the same 10 s window.
- **nvidia-smi columns:** sessions, average fps, gpu, enc, dec, memory (`run_queue.py:121-122`).

| # | id | status (exit) | start → end (local) | duration / est (min) | ratio | CPU % before mean / max | top process before (CPU-s in 10 s) | MsMpEng CPU-s during | Defender scan events | flags | nvidia-smi before → after | JSON |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | IC-STREAM-1080p-A | ok (0) | 23:00 → 23:22 | 21.71 / 30 | 0.72 | 4.05 / 5.5 | AsusFanControlService.exe 1.47 | 50.89 | none | none | 0, 0, 4 %, 0 %, 0 %, 707 MiB → 0, 0, 0 %, 0 %, 0 %, 694 MiB | `bench/matched_stream_A_1080p_20261110T042204Z.json` |
| 2 | IC-STREAM-720p-A | ok (0) | 23:22 → 23:34 | 12.73 / 18 | 0.71 | 6.07 / 14.5 | MsMpEng.exe 4.81 | 34.98 | none | none | 0, 0, 3 %, 0 %, 0 %, 700 MiB → 0, 0, 0 %, 0 %, 0 %, 712 MiB | `bench/matched_stream_A_720p_20261110T043459Z.json` |
| 3 | IC-STREAM-1080p-B | ok (0) | 23:35 → 23:42 | 6.91 / 9 | 0.77 | 3.48 / 4.9 | Corsair.Service.exe 1.62 | 14.83 | none | none | 0, 0, 0 %, 0 %, 0 %, 712 MiB → 0, 0, 0 %, 0 %, 0 %, 705 MiB | `bench/matched_stream_B_1080p_20261110T044204Z.json` |
| 4 | IC-SCALE-h264_nvenc_420 | ok (0) | 23:42 → 23:46 | 4.53 / 6 | 0.76 | 3.76 / 7.4 | PreSonusHardwareAccessService.exe 1.44 | 9.16 | none | none | 0, 0, 0 %, 0 %, 0 %, 705 MiB → 0, 0, 0 %, 0 %, 0 %, 722 MiB | `bench/matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json` |
| 5 | IC-SCALE-hevc_nvenc_420 | ok (0) | 23:46 → 23:51 | 4.79 / 6 | 0.80 | 3.23 / 6.7 | Corsair.Service.exe 1.62 | 9.72 | none | none | 0, 0, 0 %, 0 %, 0 %, 722 MiB → 0, 0, 0 %, 0 %, 0 %, 714 MiB | `bench/matched_concurrent_hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json` |
| 6 | IC-SCALE-h264_qsv_420 | ok (0) | 23:51 → 23:57 | 5.67 / 6 | 0.94 | 3.71 / 7.7 | Corsair.Service.exe 1.5 | 26.66 | none | none | 0, 0, 0 %, 0 %, 0 %, 714 MiB → 0, 0, 0 %, 0 %, 0 %, 714 MiB | `bench/matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json` |
| 7 | IC-SCALE-hevc_qsv_420 | ok (0) | 23:57 → 00:16 | 18.68 / 9 | 2.08 | 4.02 / 7.9 | AsusFanControlService.exe 1.5 | 48.86 | none | none | 0, 0, 0 %, 0 %, 0 %, 718 MiB → 0, 0, 0 %, 0 %, 0 %, 708 MiB | `bench/matched_concurrent_hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json` |
| 8 | IC-SCALE-mjpeg_qsv_420 | ok (0) | 00:16 → 00:23 | 6.54 / 6 | 1.09 | 3.75 / 9.0 | AsusFanControlService.exe 1.61 | 28.03 | none | none | 0, 0, 0 %, 0 %, 0 %, 708 MiB → 0, 0, 0 %, 0 %, 0 %, 712 MiB | `bench/matched_concurrent_mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json` |
| 9 | IC-SCALE-nvjpeg_420 | ok (0) | 00:23 → 00:28 | 5.31 / 6 | 0.88 | 3.57 / 5.5 | Corsair.Service.exe 1.62 | 11.83 | none | none | 0, 0, 0 %, 0 %, 0 %, 712 MiB → 0, 0, 0 %, 0 %, 0 %, 718 MiB | `bench/matched_concurrent_nvjpeg_420_1080p_nv12_thread_20261110T052842Z.json` |
| 10 | IC-SCALE-jpeg_turbo_420-proc | ok (0) | 00:28 → 00:34 | 5.39 / 8 | 0.67 | 3.71 / 6.3 | Corsair.Service.exe 1.67 | 47.61 | none | none | 0, 0, 0 %, 0 %, 0 %, 719 MiB → 0, 0, 0 %, 0 %, 0 %, 728 MiB | `bench/matched_concurrent_jpeg_turbo_420_1080p_nv12_process_20261110T053417Z.json` |
| 11 | IC-SCALE-jpeg_turbo_420-thread | ok (0) | 00:34 → 00:34 | 0.31 / 2 | 0.15 | 3.71 / 7.9 | Corsair.Service.exe 1.48 | 1.55 | none | none | 0, 0, 0 %, 0 %, 0 %, 728 MiB → 0, 0, 0 %, 0 %, 0 %, 728 MiB | `bench/matched_concurrent_jpeg_turbo_420_1080p_nv12_thread_20261110T053447Z.json` |
| 31 | IC-SCALE-jpeg_turbo_422-proc-yuy2 | ok (0) | 01:28 → 01:32 | 3.77 / 6 | 0.63 | 3.11 / 4.7 | Corsair.Service.exe 1.72 | 34.19 | none | none | 0, 0, 0 %, 0 %, 0 %, 330 MiB → 0, 0, 0 %, 0 %, 0 %, 357 MiB | `bench/matched_concurrent_jpeg_turbo_422_1080p_yuy2_process_20261110T063244Z.json` |
| 32 | IC-SCALE-nvjpeg_422-yuy2 | ok (0) | 01:32 → 01:36 | 3.66 / 4.5 | 0.81 | 4.36 / 14.7 | PreSonusHardwareAccessService.exe 1.61 | 9.42 | none | none | 0, 0, 0 %, 0 %, 0 %, 357 MiB → 0, 0, 0 %, 0 %, 0 %, 354 MiB | `bench/matched_concurrent_nvjpeg_422_1080p_yuy2_thread_20261110T063635Z.json` |
| 33 | IC-SCALE-mjpeg_qsv_422-yuy2 | ok (0) | 01:36 → 01:41 | 4.68 / 4.5 | 1.04 | 3.82 / 6.9 | Corsair.Service.exe 1.84 | 19.56 | none | none | 0, 0, 0 %, 0 %, 0 %, 354 MiB → 0, 0, 0 %, 0 %, 0 %, 347 MiB | `bench/matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json` |
| 34 | IC-SCALE-hevc_qsv_422-yuy2 | ok (0) | 01:41 → 01:54 | 12.87 / 6.5 | 1.98 | 3.67 / 6.5 | Corsair.Service.exe 1.8 | 34.17 | none | none | 0, 0, 0 %, 0 %, 0 %, 347 MiB → 0, 0, 0 %, 0 %, 0 %, 337 MiB | `bench/matched_concurrent_hevc_qsv_422_1080p_yuy2_thread_20261110T065430Z.json` |
| 41 | IC-SCALE-h264_nvenc_420-mjpeg_cpu | ok (0) | 03:16 → 03:19 | 2.97 / 5.5 | 0.54 | 3.65 / 7.7 | PreSonusHardwareAccessService.exe 1.52 | 7.56 | none | none | 0, 0, 0 %, 0 %, 0 %, 342 MiB → 0, 0, 0 %, 0 %, 0 %, 373 MiB | `bench/matched_concurrent_h264_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z.json` |
| 42 | IC-SCALE-hevc_nvenc_420-mjpeg_cpu | ok (0) | 03:19 → 03:23 | 3.20 / 5.5 | 0.58 | 4.41 / 8.1 | Corsair.Service.exe 1.61 | 7.66 | none | none | 0, 0, 1 %, 0 %, 0 %, 379 MiB → 0, 0, 0 %, 0 %, 0 %, 386 MiB | `bench/matched_concurrent_hevc_nvenc_420_1080p_mjpeg_cpu_thread_20261110T082302Z.json` |
| 43 | IC-SCALE-h264_qsv_420-mjpeg_qsv | ok (0) | 03:23 → 03:27 | 3.83 / 5.5 | 0.70 | 3.28 / 7.4 | AsusFanControlService.exe 1.56 | 16.3 | none | none | 0, 0, 0 %, 0 %, 0 %, 386 MiB → 0, 0, 2 %, 0 %, 0 %, 356 MiB | `bench/matched_concurrent_h264_qsv_420_1080p_mjpeg_qsv_thread_20261110T082702Z.json` |
| 44 | IC-SCALE-hevc_qsv_420-mjpeg_qsv | ok (0) | 03:27 → 03:39 | 12.54 / 7 | 1.79 | 3.51 / 7.9 | AsusFanControlService.exe 1.52 | 37.81 | none | none | 0, 0, 0 %, 0 %, 0 %, 356 MiB → 0, 0, 8 %, 0 %, 0 %, 352 MiB | `bench/matched_concurrent_hevc_qsv_420_1080p_mjpeg_qsv_thread_20261110T083946Z.json` |
| 45 | IC-SCALE-h264_nvenc_420-yuy2 | ok (0) | 03:39 → 03:43 | 3.04 / 4.5 | 0.68 | 3.93 / 9.7 | AsusFanControlService.exe 1.47 | 7.06 | none | none | 0, 0, 0 %, 0 %, 0 %, 365 MiB → 0, 0, 0 %, 0 %, 0 %, 356 MiB | `bench/matched_concurrent_h264_nvenc_420_1080p_yuy2_thread_20261110T084300Z.json` |
| 49 | IC-SCALE720-h264_nvenc_420 | ok (0) | 03:52 → 03:54 | 2.76 / 3.5 | 0.79 | 2.98 / 5.4 | AsusFanControlService.exe 1.64 | 6.34 | none | none | 0, 0, 0 %, 0 %, 0 %, 379 MiB → 0, 0, 0 %, 0 %, 0 %, 364 MiB | `bench/matched_concurrent_h264_nvenc_420_720p_nv12_thread_20261110T085446Z.json` |
| 50 | IC-SCALE720-hevc_nvenc_420 | ok (0) | 03:54 → 03:57 | 2.83 / 3.5 | 0.81 | 3.41 / 6.9 | Corsair.Service.exe 1.56 | 7.22 | none | none | 0, 0, 0 %, 0 %, 0 %, 352 MiB → 0, 0, 0 %, 0 %, 0 %, 352 MiB | `bench/matched_concurrent_hevc_nvenc_420_720p_nv12_thread_20261110T085747Z.json` |
| 51 | IC-SCALE720-h264_qsv_420 | ok (0) | 03:57 → 04:01 | 3.39 / 3.5 | 0.97 | 3.43 / 6.9 | Corsair.Service.exe 1.56 | 15.34 | none | none | 0, 0, 0 %, 0 %, 0 %, 352 MiB → 0, 0, 0 %, 0 %, 0 %, 356 MiB | `bench/matched_concurrent_h264_qsv_420_720p_nv12_thread_20261110T090121Z.json` |
| 52 | IC-SCALE720-hevc_qsv_420 | ok (0) | 04:01 → 04:08 | 7.15 / 4.5 | 1.59 | 3.33 / 7.6 | Corsair.Service.exe 1.95 | 23.09 | none | none | 0, 0, 0 %, 0 %, 0 %, 356 MiB → 0, 0, 0 %, 0 %, 0 %, 347 MiB | `bench/matched_concurrent_hevc_qsv_420_720p_nv12_thread_20261110T090841Z.json` |
| 53 | IC-SCALE720-mjpeg_qsv_420 | ok (0) | 04:08 → 04:12 | 3.54 / 3.5 | 1.01 | 3.72 / 5.9 | Corsair.Service.exe 1.78 | 16.06 | none | none | 0, 0, 0 %, 0 %, 0 %, 347 MiB → 0, 0, 0 %, 0 %, 0 %, 360 MiB | `bench/matched_concurrent_mjpeg_qsv_420_720p_nv12_thread_20261110T091225Z.json` |
| 54 | IC-SCALE720-nvjpeg_420 | ok (0) | 04:12 → 04:15 | 2.86 / 3.5 | 0.82 | 3.62 / 7.4 | Corsair.Service.exe 1.69 | 6.67 | none | none | 0, 0, 0 %, 0 %, 0 %, 360 MiB → 0, 0, 0 %, 0 %, 0 %, 362 MiB | `bench/matched_concurrent_nvjpeg_420_720p_nv12_thread_20261110T091527Z.json` |
| 55 | IC-SCALE720-jpeg_turbo_420-proc | ok (0) | 04:15 → 04:19 | 3.42 / 5 | 0.68 | 3.75 / 9.7 | AsusFanControlService.exe 1.61 | 33.19 | none | none | 0, 0, 0 %, 0 %, 0 %, 362 MiB → 0, 0, 0 %, 0 %, 0 %, 367 MiB | `bench/matched_concurrent_jpeg_turbo_420_720p_nv12_process_20261110T091904Z.json` |

- **No intra_compare item was flagged `load_over_15pct`** (0 of 27). None of the run's 69 load records has the flag (0).
  - The highest pre-item max was 14.7 % (item 32). The highest mean was 6.07 % (item 2, with MsMpEng top at 4.81 CPU-s).
  - No Defender scan events were logged during any item.
- The runner's `leftover_note` lists only the monitoring session's own shells, and no bench process.
- **stderr (non-fatal):**
  - Every item: the nvImageCodec warnings about missing optional nvJPEG2000 and nvTIFF plugins.
  - Items 1–3 only: five `cuDevicePrimaryCtxRelease failed: 4` lines each.
  - All cells wrote results despite these lines.

## 2. Completeness

| # | id | cells expected → ran | reps per cell | runs with error | streams opened < requested | stream errors | frames short | QC errors / MISS / below-as-matched / PSNR-Y > 2 dB under matched | verdict |
|---|---|---|---|---|---|---|---|---|---|
| 1 | IC-STREAM-1080p-A | 56 → 56 (skipped 0) | 1 warm-up + 5 (all 5–5 ok) | 0 | n/a | n/a | n/a | 0 / 2 / 1 / 3 | complete |
| 2 | IC-STREAM-720p-A | 43 → 43 (skipped 0) | 1 warm-up + 4 (all 4–4 ok) | 0 | n/a | n/a | n/a | 0 / 0 / 1 / 3 | complete |
| 3 | IC-STREAM-1080p-B | 27 → 27 (skipped 0) | 1 warm-up + 3 (all 3–3 ok) | 0 | n/a | n/a | n/a | 0 / 2 / 5 / 0 | complete |
| 4 | IC-SCALE-h264_nvenc_420 | 24 → 24 | 3 | 0 | 6 (N=16 → 12, NVENC session limit) | 0 | 0 | n/a | complete; 16-stream cells ran 12 streams |
| 5 | IC-SCALE-hevc_nvenc_420 | 24 → 24 | 3 | 0 | 6 (N=16 → 12, NVENC session limit) | 0 | 0 | n/a | complete; 16-stream cells ran 12 streams |
| 6 | IC-SCALE-h264_qsv_420 | 24 → 24 | 3 | 0 | 0 | 0 | 0 | n/a | complete |
| 7 | IC-SCALE-hevc_qsv_420 | 24 → 24 | 3 | 0 | 0 | 0 | 0 | n/a | complete |
| 8 | IC-SCALE-mjpeg_qsv_420 | 24 → 24 | 3 | 0 | 0 | 0 | 0 | n/a | complete |
| 9 | IC-SCALE-nvjpeg_420 | 24 → 24 | 3 | 0 | 0 | 0 | 0 | n/a | complete |
| 10 | IC-SCALE-jpeg_turbo_420-proc | 24 → 24 | 3 | 0 | 0 | 0 | 0 | n/a | complete |
| 11 | IC-SCALE-jpeg_turbo_420-thread | 4 → 4 | 1 | 0 | 0 | 0 | 0 | n/a | complete |
| 31 | IC-SCALE-jpeg_turbo_422-proc-yuy2 | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 32 | IC-SCALE-nvjpeg_422-yuy2 | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 33 | IC-SCALE-mjpeg_qsv_422-yuy2 | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 34 | IC-SCALE-hevc_qsv_422-yuy2 | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 41 | IC-SCALE-h264_nvenc_420-mjpeg_cpu | 16 → 16 | 2 | 0 | 4 (N=16 → 12, NVENC session limit) | 0 | 0 | n/a | complete; 16-stream cells ran 12 streams |
| 42 | IC-SCALE-hevc_nvenc_420-mjpeg_cpu | 16 → 16 | 2 | 0 | 4 (N=16 → 12, NVENC session limit) | 0 | 0 | n/a | complete; 16-stream cells ran 12 streams |
| 43 | IC-SCALE-h264_qsv_420-mjpeg_qsv | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 44 | IC-SCALE-hevc_qsv_420-mjpeg_qsv | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 45 | IC-SCALE-h264_nvenc_420-yuy2 | 16 → 16 | 2 | 0 | 4 (N=16 → 12, NVENC session limit) | 0 | 0 | n/a | complete; 16-stream cells ran 12 streams |
| 49 | IC-SCALE720-h264_nvenc_420 | 16 → 16 | 2 | 0 | 4 (N=16 → 12, NVENC session limit) | 0 | 0 | n/a | complete; 16-stream cells ran 12 streams |
| 50 | IC-SCALE720-hevc_nvenc_420 | 16 → 16 | 2 | 0 | 4 (N=16 → 12, NVENC session limit) | 0 | 0 | n/a | complete; 16-stream cells ran 12 streams |
| 51 | IC-SCALE720-h264_qsv_420 | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 52 | IC-SCALE720-hevc_qsv_420 | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 53 | IC-SCALE720-mjpeg_qsv_420 | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 54 | IC-SCALE720-nvjpeg_420 | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |
| 55 | IC-SCALE720-jpeg_turbo_420-proc | 16 → 16 | 2 | 0 | 0 | 0 | 0 | n/a | complete |

- **Single-stream items (1–3):**
  - Every path × source cell compatible with the requested sources ran, matching the smoke counts in the queue (56 / 43 / 27). No cell was skipped, no timed rep failed and no QC errored.
  - "MISS" = QC below target by more than the sweep's own shortfall at that setting, plus a tolerance of 0.5 dB or 0.0005 SSIM.
  - "below-as-matched" = QC below target, and the sweep's own value at that integer knob step was also below it.
- **NVENC items (4, 5, 41, 42, 45, 49, 50):**
  - Complete, but every N=16 cell opened only 12 encoders, in both modes and every rep (`open_error` = `avcodec_open2` ExternalError).
  - Read the N=16 rows of these paths as 12-stream rows. The limit probes in §5.2 give the same ceiling.
- **Items over their estimate (7, 34, 44, 52):**
  - IC-SCALE-hevc_qsv_420 took 18.68 min (est 9), IC-SCALE-hevc_qsv_422-yuy2 12.87 (est 6.5), IC-SCALE-hevc_qsv_420-mjpeg_qsv 12.54 (est 7) and IC-SCALE720-hevc_qsv_420 7.15 (est 4.5). **All four are complete.**
    - Every run is present (24 / 16 / 16 / 16).
    - `total_frames` = opened × frames per stream in every run.
    - There are no stream errors.
  - The extra time is real encode time. At 1080p, hevc_qsv encodes about 64–67 frames/s in total whatever N is (123–135 fps at 720p), so a paced 16-stream 1080p run of 16 × 450 frames takes about 108 s instead of 15 s.
    - Measured `wall_s` of the N=16 paced runs: 107.8–107.9 s (item 7), 111.4–111.5 s (item 34), 108.4–108.7 s (item 44), 53.7–53.8 s (item 52).
    - Sum of run `wall_s` in item 7: 1,002.9 s (paced 611.4, unpaced 391.5), against 221.7 s for item 4 (h264_nvenc_420, same 24 runs: paced 179.9, unpaced 41.8).
- **IC-SCALE-jpeg_turbo_420-thread (item 11) ran 19 s (0.31 min) against a 2 min estimate. It is complete, not truncated.** Evidence:
  - The queue command asks for `--modes unpaced --reps 1`, i.e. 4 runs (N = 1, 4, 8, 16). The JSON has 4 runs.
  - Each run opened N of N streams with no stream errors.
  - `total_frames` = 300 × (1 + 4 + 8 + 16) = 8,700.
  - The sum of `wall_s` is 3.9 s, because the 16 threads together encode 3,511 fps. Snapshot before → after: 05:34:28 → 05:34:46 UTC.
  - stdout ends with `wrote …thread_20261110T053447Z.json` and stderr holds only the nvImageCodec plugin warnings.

## 3. Single-stream tables (items 1–3)

**Definitions** (`bench_matched_stream.py`):
- **Reps:** one thread, unpaced, at least 300 frames and at least 3 s per rep (`:58`); packets discarded, so no file I/O (`:12`).
- **fps:** frames / wall (`:70`).
- **CPU ms/frame:** process user + system CPU over all threads, driver threads included, divided by frames (`:69-71`).
- **CPU cores:** CPU s / wall.
- **bytes/frame:** from the timed reps (`:72`).
- **Values in cells:** median (min–max) over the timed reps (5 / 4 / 3; the warm-up rep is excluded, `:119-123`).

**Columns:**
- **× jt422:** bytes/frame ÷ the jt422 row of the same content: NV12 and RGB rows use the YUY2 jt422 row (all are made from the same YUY2 frames, `benchpaths.py:8-15`), and `mjpeg_qsv` rows use the `mjpeg_cpu` jt422 row. Item 3 has no YUY2 source, so its NV12 rows have no ratio.
- **NV enc % (smi):** GPU-wide nvidia-smi `utilization.encoder`, median over reps of each rep's mean.
- **GPU Engine %:** this process's `\GPU Engine` counters, summed over the instances of each engine type on adapters with the same name (`benchpaths.py:429-435`), so values can exceed 100. Engines with a median ≥ 1 % are listed. Intel engine names are as Windows reports them.
- **QC:** an untimed re-encode of the first 4 source frames with the same pipeline, decoded by PyAV and compared with the source Y (`benchpaths.py:266-288`).
- **target column:** "hit" = QC at or above target.

**Flags:**
- **MISS:** QC below target by more than the matched setting's own shortfall, plus a tolerance of 0.5 dB or 0.0005 SSIM.
- **below (… matched value also below):** a knob-step shortfall already present in `matched_settings.json`.
- **PSNR-Y … vs matched:** QC PSNR-Y more than 2 dB under the sweep value.

### 3.1 Target A, 1080p (item 1)

Source: `bench/matched_stream_A_1080p_20261110T042204Z.json`.

| path | source | fps | CPU ms/frame | CPU cores | bytes/frame | × jt422 | NV enc % (smi) | GPU Engine % (process) | QC PSNR-Y | QC SSIM-Y | target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| jpeg_turbo_420 | nv12 | 360 (358–360) | 2.77 (2.76–2.79) | 0.99 | 255,423 | 0.89 | 0 | – | 52.82 | 0.997 | hit |
| ff_mjpeg_420 | nv12 | 415 (410–418) | 11.08 (9.77–11.94) | 4.59 | 227,158 | 0.79 | 0 | – | 53.152 | 0.99706 | hit |
| mjpeg_qsv_420 | nv12 | 602 (601–606) | 1.81 (1.78–1.86) | 1.09 | 276,187 | 0.96 | 0 | iGPU VideoDecode 49, iGPU 3D 16 | 52.967 | 0.99695 | hit |
| nvjpeg_420 | nv12 | 323 (283–341) | 7.57 (7.13–10.18) | 2.43 | 225,514 | 0.79 | 0 | – | 52.344 | 0.99707 | hit |
| h264_nvenc_420 | nv12 | 540 (540–540) | 1.40 (1.37–1.51) | 0.75 | 157,924 | 0.55 | 100 | NV VideoEncode 97 | 54.065 | 0.99716 | hit |
| hevc_nvenc_420 | nv12 | 390 (389–390) | 1.47 (1.43–1.51) | 0.57 | 135,292 | 0.47 | 100 | NV VideoEncode 97 | 54.236 | 0.9973 | hit |
| h264_qsv_420 | nv12 | 585 (585–585) | 2.04 (1.95–2.10) | 1.20 | 170,101 | 0.59 | 0 | iGPU VideoDecode 87, iGPU 3D 44 | 53.945 | 0.99705 | hit |
| hevc_qsv_420 | nv12 | 65 (65–66) | 2.81 (2.45–5.10) | 0.18 | 117,180 | 0.41 | 0 | iGPU 3D 91, iGPU VideoDecode 8 | 54.071 | 0.99723 | hit |
| libx264_ultrafast_420 | nv12 | 372 (371–375) | 14.70 (12.06–15.04) | 5.48 | 250,639 | 0.87 | 0 | – | 54.058 | 0.99706 | hit |
| libx264_veryfast_420 | nv12 | 229 (229–232) | 31.05 (30.82–32.53) | 7.12 | 163,303 | 0.57 | 0 | – | 53.952 | 0.99715 | hit |
| libx265_ultrafast_420 | nv12 | 106 (105–107) | 252.95 (250.49–254.08) | 26.93 | 147,170 | 0.51 | 0 | – | 54.116 | 0.99717 | hit |
| jpeg_turbo_422 | yuy2 | 225 (225–226) | 4.38 (4.33–4.43) | 0.98 | 286,974 | 1.00 | 0 | – | 52.82 | 0.997 | hit |
| jpeg_turbo_420 | yuy2 | 231 (231–232) | 8.30 (8.19–9.27) | 1.92 | 255,461 | 0.89 | 0 | – | 52.82 | 0.997 | hit |
| ff_mjpeg_422 | yuy2 | 419 (415–420) | 13.00 (11.24–15.51) | 5.44 | 265,207 | 0.92 | 0 | – | 53.152 | 0.99706 | hit |
| ff_mjpeg_420 | yuy2 | 480 (477–481) | 11.70 (9.79–12.70) | 5.60 | 226,435 | 0.79 | 0 | – | 53.152 | 0.99706 | hit |
| mjpeg_qsv_422 | yuy2 | 481 (481–482) | 1.58 (1.53–1.81) | 0.76 | 308,099 | 1.07 | 0 | iGPU VideoDecode 52, iGPU 3D 15 | 52.967 | 0.99695 | hit |
| mjpeg_qsv_420 | yuy2 | 553 (543–554) | 7.56 (7.06–8.34) | 4.10 | 275,656 | 0.96 | 0 | iGPU VideoDecode 47, iGPU 3D 17 | 52.967 | 0.99695 | hit |
| nvjpeg_422 | yuy2 | 343 (340–368) | 8.14 (7.90–9.26) | 2.95 | 253,793 | 0.88 | 0 | – | 52.365 | 0.99708 | hit |
| nvjpeg_420 | yuy2 | 361 (335–376) | 7.74 (6.62–9.70) | 2.62 | 225,816 | 0.79 | 0 | – | 52.365 | 0.99708 | hit |
| h264_nvenc_420 | yuy2 | 544 (542–545) | 6.67 (4.92–7.01) | 3.62 | 155,555 | 0.54 | 100 | NV VideoEncode 97, NV 3D 22 | 54.065 | 0.99716 | hit |
| hevc_nvenc_420 | yuy2 | 390 (389–390) | 6.38 (6.02–6.94) | 2.48 | 133,015 | 0.46 | 100 | NV VideoEncode 97 | 54.238 | 0.9973 | hit |
| h264_qsv_420 | yuy2 | 580 (574–582) | 8.44 (7.51–8.78) | 4.86 | 167,682 | 0.58 | 0 | iGPU VideoDecode 87, iGPU 3D 47 | 53.945 | 0.99705 | hit |
| hevc_qsv_420 | yuy2 | 66 (66–66) | 10.10 (7.71–10.99) | 0.67 | 115,273 | 0.40 | 0 | iGPU 3D 89, iGPU VideoDecode 8 | 54.071 | 0.99723 | hit |
| hevc_qsv_422 | yuy2 | 64 (64–64) | 3.18 (2.24–5.00) | 0.20 | 155,864 | 0.54 | 0 | iGPU 3D 90, iGPU VideoDecode 12 | 54.069 | 0.99723 | hit |
| libx264_ultrafast_420 | yuy2 | 434 (432–435) | 15.32 (14.48–15.53) | 6.66 | 250,670 | 0.87 | 0 | – | 54.058 | 0.99706 | hit |
| libx264_veryfast_420 | yuy2 | 256 (253–256) | 28.50 (27.65–32.02) | 7.21 | 163,298 | 0.57 | 0 | – | 53.952 | 0.99715 | hit |
| libx265_ultrafast_420 | yuy2 | 107 (105–107) | 250.73 (249.04–251.79) | 26.72 | 147,227 | 0.51 | 0 | – | 54.116 | 0.99717 | hit |
| jpeg_turbo_422 | mjpeg_cpu | 152 (152–153) | 6.43 (6.40–6.54) | 0.98 | 145,619 | 1.00 | 0 | – | 52.922 | 0.99711 | hit |
| jpeg_turbo_420 | mjpeg_cpu | 156 (154–156) | 8.96 (8.44–9.52) | 1.40 | 129,794 | 0.89 | 0 | – | 52.922 | 0.99711 | hit |
| ff_mjpeg_422 | mjpeg_cpu | 243 (241–245) | 9.05 (8.46–10.47) | 2.18 | 148,766 | 1.02 | 0 | – | 53.347 | 0.99688 | hit |
| ff_mjpeg_420 | mjpeg_cpu | 209 (208–210) | 14.44 (9.85–15.35) | 3.04 | 134,823 | 0.93 | 0 | – | 53.347 | 0.99688 | hit |
| mjpeg_qsv_422 | mjpeg_cpu | 206 (206–207) | 7.06 (6.97–8.22) | 1.46 | 145,848 | 1.00 | 0 | iGPU VideoDecode 22, iGPU 3D 6 | 53.14 | 0.99721 | hit |
| mjpeg_qsv_420 | mjpeg_cpu | 206 (204–207) | 9.23 (8.78–9.80) | 1.89 | 130,143 | 0.89 | 0 | iGPU VideoDecode 17, iGPU 3D 6 | 53.14 | 0.99721 | hit |
| nvjpeg_422 | mjpeg_cpu | 140 (135–141) | 9.26 (9.10–9.59) | 1.28 | 176,016 | 1.21 | 0 | NV 3D 26 | 45.211 | 0.9954 | **MISS** (0.9954 < 0.9961; matched 0.99617); **PSNR-Y -4.8 dB vs matched** |
| nvjpeg_420 | mjpeg_cpu | 145 (136–145) | 8.94 (8.16–10.12) | 1.29 | 162,192 | 1.11 | 0 | NV 3D 24 | 45.211 | 0.9954 | **MISS** (0.9954 < 0.9961; matched 0.99617); **PSNR-Y -4.8 dB vs matched** |
| h264_nvenc_420 | mjpeg_cpu | 228 (227–229) | 9.84 (7.67–12.25) | 2.25 | 115,527 | 0.79 | 42 | NV VideoEncode 42 | 52.691 | 0.99668 | hit |
| hevc_nvenc_420 | mjpeg_cpu | 230 (228–231) | 8.84 (7.40–9.91) | 2.04 | 139,317 | 0.96 | 67 | NV VideoEncode 66 | 53.33 | 0.99694 | hit |
| h264_qsv_420 | mjpeg_cpu | 236 (235–236) | 10.26 (7.22–11.45) | 2.42 | 147,765 | 1.01 | 0 | iGPU VideoDecode 36, iGPU 3D 20 | 53.122 | 0.99694 | hit |
| hevc_qsv_420 | mjpeg_cpu | 68 (68–68) | 9.22 (8.44–10.94) | 0.63 | 100,277 | 0.69 | 0 | iGPU 3D 91, iGPU VideoDecode 8 | 52.533 | 0.99645 | hit |
| hevc_qsv_422 | mjpeg_cpu | 66 (66–66) | 8.75 (6.98–10.26) | 0.58 | 127,274 | 0.87 | 0 | iGPU 3D 88, iGPU VideoDecode 13 | 49.972 | 0.99608 | below (0.99608 < 0.9961; matched value 0.99575 also below); **PSNR-Y -2.1 dB vs matched** |
| libx264_ultrafast_420 | mjpeg_cpu | 198 (198–200) | 17.81 (14.68–19.10) | 3.56 | 244,173 | 1.68 | 0 | – | 53.241 | 0.99685 | hit |
| libx264_veryfast_420 | mjpeg_cpu | 156 (156–157) | 31.95 (30.42–34.20) | 4.98 | 149,046 | 1.02 | 0 | – | 53.118 | 0.99698 | hit |
| libx265_ultrafast_420 | mjpeg_cpu | 108 (106–108) | 250.73 (250.43–252.29) | 27.11 | 150,005 | 1.03 | 0 | – | 53.352 | 0.99692 | hit |
| jpeg_turbo_420 | mjpeg_qsv | 291 (291–292) | 7.02 (6.85–7.79) | 2.04 | 130,061 | 0.89 | 0 | iGPU VideoDecode 29, iGPU 3D 8 | 52.883 | 0.99707 | hit |
| ff_mjpeg_420 | mjpeg_qsv | 591 (590–612) | 10.46 (10.02–11.52) | 6.17 | 136,398 | 0.94 | 0 | iGPU VideoDecode 62, iGPU 3D 16 | 53.326 | 0.99687 | hit |
| mjpeg_qsv_420 | mjpeg_qsv | 609 (432–611) | 1.17 (1.05–1.38) | 0.71 | 130,561 | 0.90 | 0 | iGPU VideoDecode 56, iGPU 3D 19 | 53.112 | 0.99719 | hit |
| nvjpeg_420 | mjpeg_qsv | 446 (430–459) | 8.72 (7.58–9.41) | 3.89 | 160,252 | 1.10 | 0 | NV 3D 88, iGPU VideoDecode 46, iGPU 3D 13 | 56.462 | 0.99788 | hit |
| h264_nvenc_420 | mjpeg_qsv | 594 (591–596) | 7.62 (7.46–8.34) | 4.53 | 117,119 | 0.80 | 83 | NV VideoEncode 84, iGPU VideoDecode 60, NV 3D 26, iGPU 3D 16 | 52.679 | 0.99667 | hit |
| hevc_nvenc_420 | mjpeg_qsv | 380 (377–380) | 6.84 (6.12–7.46) | 2.60 | 141,694 | 0.97 | 84 | NV VideoEncode 85, iGPU VideoDecode 36, iGPU 3D 9 | 53.298 | 0.99692 | hit |
| h264_qsv_420 | mjpeg_qsv | 554 (361–554) | 8.44 (8.24–8.58) | 4.63 | 148,400 | 1.02 | 0 | iGPU VideoDecode 65, iGPU 3D 46 | 53.089 | 0.99692 | hit |
| hevc_qsv_420 | mjpeg_qsv | 66 (66–66) | 15.88 (12.81–17.08) | 1.05 | 101,890 | 0.70 | 0 | iGPU 3D 78, iGPU VideoDecode 13 | 52.51 | 0.99643 | hit |
| libx264_ultrafast_420 | mjpeg_qsv | 505 (488–508) | 15.08 (13.03–17.19) | 7.45 | 243,538 | 1.67 | 0 | iGPU VideoDecode 52, iGPU 3D 14 | 53.189 | 0.99682 | hit |
| libx264_veryfast_420 | mjpeg_qsv | 286 (285–290) | 31.34 (30.18–34.87) | 9.00 | 150,297 | 1.03 | 0 | iGPU VideoDecode 29, iGPU 3D 8 | 53.086 | 0.99695 | hit |
| libx265_ultrafast_420 | mjpeg_qsv | 108 (105–108) | 248.34 (246.58–249.62) | 26.75 | 152,036 | 1.04 | 0 | iGPU VideoDecode 12, iGPU 3D 3 | 53.313 | 0.9969 | hit |
| nvjpeg_422 | rgb | 1,085 (1,066–1,089) | 0.90 (0.87–0.92) | 0.97 | 254,274 | 0.89 | 0 | – | 51.361 | 0.9971 | hit |
| nvjpeg_420 | rgb | 1,126 (1,117–1,132) | 0.87 (0.86–0.89) | 0.98 | 226,566 | 0.79 | 0 | – | 51.361 | 0.9971 | hit |

### 3.2 Target A, 720p (item 2)

Source: `bench/matched_stream_A_720p_20261110T043459Z.json`.

| path | source | fps | CPU ms/frame | CPU cores | bytes/frame | × jt422 | NV enc % (smi) | GPU Engine % (process) | QC PSNR-Y | QC SSIM-Y | target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| jpeg_turbo_420 | nv12 | 744 (728–764) | 1.34 (1.30–1.37) | 1.00 | 150,618 | 0.90 | 0 | – | 51.995 | 0.99654 | hit |
| ff_mjpeg_420 | nv12 | 912 (912–915) | 5.55 (5.17–5.62) | 5.06 | 119,970 | 0.72 | 0 | – | 52.694 | 0.99681 | hit |
| mjpeg_qsv_420 | nv12 | 1,155 (1,140–1,161) | 0.75 (0.74–0.77) | 0.86 | 163,558 | 0.98 | 0 | iGPU VideoDecode 46, iGPU 3D 13 | 52.577 | 0.99676 | hit |
| nvjpeg_420 | nv12 | 617 (579–646) | 4.59 (3.55–4.96) | 2.78 | 117,252 | 0.70 | 0 | – | 51.474 | 0.99655 | hit |
| h264_nvenc_420 | nv12 | 1,115 (1,115–1,115) | 0.56 (0.55–0.59) | 0.63 | 83,596 | 0.50 | 99 | NV VideoEncode 97, NV 3D 21 | 53.418 | 0.99686 | hit |
| hevc_nvenc_420 | nv12 | 842 (842–842) | 0.60 (0.56–0.60) | 0.51 | 64,007 | 0.38 | 100 | NV VideoEncode 97 | 53.285 | 0.99687 | hit |
| h264_qsv_420 | nv12 | 1,151 (1,149–1,152) | 0.97 (0.91–1.05) | 1.11 | 89,279 | 0.53 | 0 | iGPU VideoDecode 84, iGPU 3D 53 | 53.299 | 0.99673 | hit |
| hevc_qsv_420 | nv12 | 128 (127–129) | 1.57 (1.20–2.30) | 0.20 | 61,274 | 0.37 | 0 | iGPU 3D 82, iGPU VideoDecode 8 | 53.505 | 0.99699 | hit |
| libx264_ultrafast_420 | nv12 | 791 (788–792) | 6.36 (5.78–6.56) | 5.03 | 133,638 | 0.80 | 0 | – | 53.45 | 0.99675 | hit |
| libx264_veryfast_420 | nv12 | 433 (429–434) | 14.14 (13.00–15.17) | 6.09 | 86,591 | 0.52 | 0 | – | 53.3 | 0.99684 | hit |
| libx265_ultrafast_420 | nv12 | 232 (229–234) | 113.82 (113.48–114.30) | 26.32 | 80,414 | 0.48 | 0 | – | 53.472 | 0.99686 | hit |
| jpeg_turbo_422 | yuy2 | 512 (511–512) | 1.92 (1.90–1.93) | 0.98 | 167,565 | 1.00 | 0 | – | 51.995 | 0.99654 | hit |
| jpeg_turbo_420 | yuy2 | 510 (509–512) | 3.75 (3.60–4.24) | 1.92 | 150,564 | 0.90 | 0 | – | 51.995 | 0.99654 | hit |
| ff_mjpeg_422 | yuy2 | 872 (868–875) | 7.14 (6.17–7.62) | 6.24 | 137,914 | 0.82 | 0 | – | 52.694 | 0.99681 | hit |
| ff_mjpeg_420 | yuy2 | 1,040 (1,040–1,046) | 4.94 (4.20–5.43) | 5.15 | 119,663 | 0.71 | 0 | – | 52.694 | 0.99681 | hit |
| mjpeg_qsv_422 | yuy2 | 894 (891–896) | 0.66 (0.49–0.74) | 0.59 | 182,530 | 1.09 | 0 | iGPU VideoDecode 46, iGPU 3D 11 | 52.577 | 0.99676 | hit |
| mjpeg_qsv_420 | yuy2 | 963 (958–973) | 4.18 (3.94–4.38) | 4.03 | 163,254 | 0.97 | 0 | iGPU VideoDecode 44, iGPU 3D 14 | 52.577 | 0.99676 | hit |
| nvjpeg_422 | yuy2 | 626 (592–643) | 5.54 (4.22–5.59) | 3.49 | 131,542 | 0.79 | 0 | NV 3D 50 | 51.485 | 0.99656 | hit |
| nvjpeg_420 | yuy2 | 613 (562–639) | 5.13 (4.77–5.37) | 3.09 | 117,520 | 0.70 | 0 | – | 51.485 | 0.99656 | hit |
| h264_nvenc_420 | yuy2 | 1,117 (1,117–1,118) | 3.44 (3.17–3.70) | 3.85 | 82,451 | 0.49 | 97 | NV VideoEncode 97, NV 3D 27 | 53.418 | 0.99686 | hit |
| hevc_nvenc_420 | yuy2 | 842 (842–842) | 3.72 (3.55–4.03) | 3.14 | 63,101 | 0.38 | 100 | NV VideoEncode 97 | 53.281 | 0.99686 | hit |
| h264_qsv_420 | yuy2 | 1,052 (1,046–1,056) | 4.44 (4.16–4.62) | 4.66 | 88,133 | 0.53 | 0 | iGPU VideoDecode 77, iGPU 3D 57 | 53.299 | 0.99673 | hit |
| hevc_qsv_420 | yuy2 | 131 (130–131) | 4.14 (2.21–5.42) | 0.54 | 60,330 | 0.36 | 0 | iGPU 3D 83, iGPU VideoDecode 8 | 53.505 | 0.99699 | hit |
| hevc_qsv_422 | yuy2 | 124 (124–125) | 2.09 (1.65–2.33) | 0.26 | 79,714 | 0.48 | 0 | iGPU 3D 82, iGPU VideoDecode 11 | 53.504 | 0.99699 | hit |
| libx264_ultrafast_420 | yuy2 | 860 (851–863) | 6.55 (5.81–6.57) | 5.61 | 133,639 | 0.80 | 0 | – | 53.45 | 0.99675 | hit |
| libx264_veryfast_420 | yuy2 | 482 (479–483) | 13.42 (13.29–13.57) | 6.46 | 86,592 | 0.52 | 0 | – | 53.3 | 0.99684 | hit |
| libx265_ultrafast_420 | yuy2 | 234 (231–235) | 113.73 (113.05–114.47) | 26.58 | 80,417 | 0.48 | 0 | – | 53.472 | 0.99686 | hit |
| jpeg_turbo_422 | mjpeg_cpu | 392 (391–393) | 2.50 (2.49–2.52) | 0.98 | 60,750 | 1.00 | 0 | – | 52.498 | 0.99706 | hit |
| jpeg_turbo_420 | mjpeg_cpu | 356 (354–356) | 5.25 (4.96–5.83) | 1.87 | 55,285 | 0.91 | 0 | – | 52.498 | 0.99706 | hit |
| ff_mjpeg_422 | mjpeg_cpu | 559 (557–561) | 3.72 (3.09–4.28) | 2.08 | 58,674 | 0.97 | 0 | – | 52.73 | 0.99655 | hit |
| ff_mjpeg_420 | mjpeg_cpu | 472 (470–474) | 7.85 (6.59–8.43) | 3.69 | 54,327 | 0.89 | 0 | – | 52.73 | 0.99655 | hit |
| mjpeg_qsv_422 | mjpeg_cpu | 316 (313–324) | 4.20 (3.78–4.99) | 1.35 | 59,696 | 0.98 | 0 | iGPU VideoDecode 16, iGPU 3D 6 | 52.124 | 0.99685 | hit |
| mjpeg_qsv_420 | mjpeg_cpu | 256 (254–257) | 3.75 (3.14–4.54) | 0.96 | 54,126 | 0.89 | 0 | iGPU VideoDecode 10, iGPU 3D 5 | 52.124 | 0.99685 | hit |
| nvjpeg_422 | mjpeg_cpu | 244 (236–245) | 6.84 (5.86–7.05) | 1.67 | 66,882 | 1.10 | 0 | NV 3D 28 | 45.512 | 0.99737 | hit; **PSNR-Y -3.8 dB vs matched** |
| nvjpeg_420 | mjpeg_cpu | 247 (232–251) | 6.18 (5.67–7.05) | 1.53 | 61,994 | 1.02 | 0 | NV 3D 26 | 45.512 | 0.99737 | hit; **PSNR-Y -3.8 dB vs matched** |
| h264_nvenc_420 | mjpeg_cpu | 509 (503–510) | 4.53 (4.45–4.81) | 2.29 | 45,009 | 0.74 | 40 | NV VideoEncode 41, NV 3D 37 | 52.208 | 0.99652 | hit |
| hevc_nvenc_420 | mjpeg_cpu | 499 (498–501) | 4.51 (4.31–5.18) | 2.25 | 54,075 | 0.89 | 66 | NV VideoEncode 67, NV 3D 11 | 52.913 | 0.99681 | hit |
| h264_qsv_420 | mjpeg_cpu | 519 (516–527) | 5.77 (5.32–6.58) | 3.01 | 53,666 | 0.88 | 0 | iGPU VideoDecode 38, iGPU 3D 28 | 52.485 | 0.99666 | hit |
| hevc_qsv_420 | mjpeg_cpu | 137 (136–137) | 5.07 (3.98–5.70) | 0.69 | 38,422 | 0.63 | 0 | iGPU 3D 83, iGPU VideoDecode 8 | 51.998 | 0.9962 | hit |
| hevc_qsv_422 | mjpeg_cpu | 132 (131–132) | 4.99 (4.06–7.89) | 0.66 | 43,593 | 0.72 | 0 | iGPU 3D 83, iGPU VideoDecode 12 | 49.53 | 0.996 | below (0.996 < 0.9961; matched value 0.99582 also below); **PSNR-Y -2.7 dB vs matched** |
| libx264_ultrafast_420 | mjpeg_cpu | 438 (437–439) | 8.29 (7.61–8.76) | 3.63 | 90,669 | 1.49 | 0 | – | 52.823 | 0.99668 | hit |
| libx264_veryfast_420 | mjpeg_cpu | 334 (334–335) | 13.47 (12.29–14.10) | 4.50 | 55,640 | 0.92 | 0 | – | 52.473 | 0.99669 | hit |
| libx265_ultrafast_420 | mjpeg_cpu | 248 (243–250) | 107.41 (106.22–108.31) | 26.56 | 68,146 | 1.12 | 0 | – | 53.178 | 0.99697 | hit |

### 3.3 Target B, 1080p (item 3)

Source: `bench/matched_stream_B_1080p_20261110T044204Z.json`.

| path | source | fps | CPU ms/frame | CPU cores | bytes/frame | × jt422 | NV enc % (smi) | GPU Engine % (process) | QC PSNR-Y | QC SSIM-Y | target |
|---|---|---|---|---|---|---|---|---|---|---|---|
| jpeg_turbo_420 | nv12 | 507 (507–509) | 1.96 (1.94–1.96) | 0.99 | 69,092 | – | 0 | – | 45.146 | 0.98772 | hit |
| ff_mjpeg_420 | nv12 | 473 (464–474) | 8.44 (7.89–8.62) | 4.00 | 65,533 | – | 0 | – | 44.661 | 0.98584 | below (44.661 < 45.0; matched value 44.769 also below) |
| mjpeg_qsv_420 | nv12 | 618 (616–621) | 1.76 (1.66–1.78) | 1.09 | 68,768 | – | 0 | iGPU VideoDecode 50, iGPU 3D 16 | 45.171 | 0.98776 | hit |
| nvjpeg_420 | nv12 | 330 (281–354) | 8.05 (7.79–8.43) | 2.76 | 71,782 | – | 0 | NV 3D 62 | 45.416 | 0.98859 | hit |
| h264_nvenc_420 | nv12 | 635 (635–635) | 1.39 (1.36–1.40) | 0.88 | 21,825 | – | 100 | NV VideoEncode 97 | 44.614 | 0.98835 | below (44.614 < 45.0; matched value 44.848 also below) |
| hevc_nvenc_420 | nv12 | 425 (425–425) | 1.43 (1.41–1.44) | 0.61 | 14,506 | – | 100 | NV VideoEncode 97, NV 3D 63 | 45.127 | 0.98961 | hit |
| h264_qsv_420 | nv12 | 691 (689–692) | 1.93 (1.84–2.03) | 1.33 | 27,081 | – | 0 | iGPU VideoDecode 87, iGPU 3D 50 | 44.74 | 0.98881 | below (44.74 < 45.0; matched value 44.898 also below) |
| hevc_qsv_420 | nv12 | 87 (86–87) | 2.81 (2.34–2.97) | 0.24 | 14,449 | – | 0 | iGPU 3D 83, iGPU VideoDecode 8 | 45.12 | 0.98967 | hit |
| libx264_ultrafast_420 | nv12 | 431 (430–432) | 10.74 (10.29–10.76) | 4.63 | 54,452 | – | 0 | – | 44.628 | 0.98463 | below (44.628 < 45.0; matched value 44.904 also below) |
| libx264_veryfast_420 | nv12 | 310 (310–311) | 17.98 (16.53–20.37) | 5.57 | 28,041 | – | 0 | – | 45.003 | 0.98941 | hit |
| libx265_ultrafast_420 | nv12 | 152 (151–152) | 177.78 (177.51–178.03) | 26.98 | 19,925 | – | 0 | – | 45.263 | 0.98899 | hit |
| jpeg_turbo_422 | mjpeg_cpu | 164 (164–164) | 6.12 (6.11–6.13) | 1.00 | 69,332 | 1.00 | 0 | – | 45.695 | 0.98792 | hit |
| jpeg_turbo_420 | mjpeg_cpu | 169 (169–169) | 9.10 (8.35–9.18) | 1.54 | 61,075 | 0.88 | 0 | – | 45.695 | 0.98792 | hit |
| ff_mjpeg_422 | mjpeg_cpu | 255 (255–256) | 6.99 (6.61–7.97) | 1.78 | 69,908 | 1.01 | 0 | – | 45.798 | 0.98853 | hit |
| ff_mjpeg_420 | mjpeg_cpu | 219 (219–219) | 12.77 (12.47–13.91) | 2.79 | 59,585 | 0.86 | 0 | – | 45.798 | 0.98853 | hit |
| mjpeg_qsv_422 | mjpeg_cpu | 207 (206–207) | 5.66 (5.53–6.86) | 1.17 | 68,702 | 0.99 | 0 | iGPU VideoDecode 23, iGPU 3D 6 | 45.71 | 0.98796 | hit |
| mjpeg_qsv_420 | mjpeg_cpu | 206 (205–208) | 9.92 (7.26–10.69) | 2.03 | 60,803 | 0.88 | 0 | iGPU VideoDecode 17, iGPU 3D 6 | 45.71 | 0.98796 | hit |
| nvjpeg_422 | mjpeg_cpu | 143 (139–143) | 9.70 (8.36–9.78) | 1.39 | 74,448 | 1.07 | 0 | NV 3D 26 | 43.144 | 0.98717 | **MISS** (43.144 < 45.0; matched 44.997) |
| nvjpeg_420 | mjpeg_cpu | 145 (142–147) | 9.04 (8.77–10.67) | 1.31 | 65,835 | 0.95 | 0 | NV 3D 24 | 43.144 | 0.98717 | **MISS** (43.144 < 45.0; matched 44.997) |
| h264_nvenc_420 | mjpeg_cpu | 231 (230–232) | 8.32 (8.30–9.98) | 1.93 | 18,404 | 0.27 | 40 | NV VideoEncode 39, NV 3D 24 | 45.712 | 0.99082 | hit |
| hevc_nvenc_420 | mjpeg_cpu | 230 (228–231) | 9.80 (8.98–10.70) | 2.23 | 12,789 | 0.18 | 57 | NV VideoEncode 58 | 45.843 | 0.99006 | hit |
| h264_qsv_420 | mjpeg_cpu | 238 (238–238) | 11.07 (7.93–11.27) | 2.63 | 22,996 | 0.33 | 0 | iGPU VideoDecode 32, iGPU 3D 20 | 45.751 | 0.9906 | hit |
| hevc_qsv_420 | mjpeg_cpu | 90 (90–90) | 10.57 (9.27–10.83) | 0.95 | 11,321 | 0.16 | 0 | iGPU 3D 87, iGPU VideoDecode 8 | 45.46 | 0.98969 | hit |
| hevc_qsv_422 | mjpeg_cpu | 87 (87–88) | 9.53 (9.17–10.62) | 0.83 | 14,642 | 0.21 | 0 | iGPU 3D 83, iGPU VideoDecode 11 | 44.849 | 0.98935 | below (44.849 < 45.0; matched value 44.782 also below) |
| libx264_ultrafast_420 | mjpeg_cpu | 214 (214–215) | 13.85 (12.86–16.43) | 2.97 | 46,456 | 0.67 | 0 | – | 45.271 | 0.98629 | hit |
| libx264_veryfast_420 | mjpeg_cpu | 185 (185–186) | 17.39 (16.64–21.00) | 3.22 | 22,368 | 0.32 | 0 | – | 45.209 | 0.99012 | hit |
| libx265_ultrafast_420 | mjpeg_cpu | 131 (131–131) | 178.22 (177.28–178.92) | 23.29 | 15,826 | 0.23 | 0 | – | 45.739 | 0.98971 | hit |

**Single-stream flags in one place:**
- **nvJPEG fed decoded camera MJPEG (swscale `rgb24`) misses.**
  - At A 1080p: SSIM-Y 0.9954 < 0.9961 and PSNR-Y 45.21 against 49.995 matched.
  - At A 720p: PSNR-Y 45.51 against 49.30 matched; SSIM-Y passes.
  - At B 1080p: PSNR-Y 43.14 < 45.
  - The same encoder hits at A from NV12 / YUY2 (52.3–52.4 dB) and from exact RGB (51.36 dB). From `mjpeg_qsv` decode it reaches 56.46 dB.
- **hevc_qsv_422 from MJPEG CPU decode** is 2.1 dB (1080p) and 2.7 dB (720p) under its matched PSNR-Y. Its SSIM-Y is at or just under target, as in the sweep.
- **Item 3 knob-step shortfalls** (QC 44.61–44.85 dB, each with its matched value also under 45): ff_mjpeg_420, h264_nvenc_420, h264_qsv_420 and libx264_ultrafast_420 from NV12, and hevc_qsv_422 from MJPEG.

## 4. Scaling tables (items 4–11, 31–34, 41–45, 49–55)

**Definitions** (`bench_matched_concurrent.py`):
- **Streams:** one thread or one spawned process per stream, each with its own encoder and per-frame input work.
- **paced:** 450 frames per stream at 30 fps.
- **unpaced:** 300 frames per stream.
- **late:** the encode finished after frame i+1 was due (`:69-72`).
- **late %:** `late_frames` / `total_frames`, computed here.
- **dropped-equiv:** Σ round(lag at end × 30) over streams: the frames a 1-deep camera buffer would have lost (`:129`).
- **keeps up:** per-stream fps ≥ 0.98 × 30 and end lag < 1/30 s (`:130-131`). "yes" = every stream in every rep; otherwise the per-rep counts are shown. A stream can keep up and still be late on some frames (latency above 33 ms without accumulating lag).
- **CPU:** process CPU for thread workers. For process workers it is the children's CPU, a lower bound (`:193-210`); see caveat 4.
- **encode ms:** latency of the encode call alone (`:60-63`).
- **opened:** "(limit)" = fewer encoders opened than requested.
- **Values in cells:** median (min–max) over reps. Paced per-stream fps min is the minimum over reps.

### 4.1 1080p from NV12, the decisive set (items 4–11; 3 reps, item 11 1 rep)

#### 4. IC-SCALE-h264_nvenc_420: h264_nvenc_420 · 1080p · nv12 · thread — `bench/matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json` (3 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.12 (0.12–0.12) | 3.82 (3.82–3.89) | 512 (508–516) | 512 (508–516) | 0.75 (0.67–0.85) | 1.46 (1.30–1.67) | 1.9 / 2.5 | 11 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.26 (0.26–0.27) | 2.17 (2.13–2.26) | 534 (532–540) | 134 (134–136) | 0.80 (0.77–0.84) | 1.50 (1.42–1.58) | 2.0 / 36.0 | 57 | NV 3D 104, NV VideoEncode 65 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 0.44 (0.41–0.47) | 1.83 (1.71–1.94) | 539 (537–540) | 68 (67–68) | 0.82 (0.81–0.82) | 1.52 (1.50–1.53) | 2.0 / 76.2 | 74 | NV 3D 102, NV VideoEncode 79 |
| 16 | 12 **(limit)** | yes | 0.0 | 0 | 30.0 | 0.61 (0.60–0.64) | 1.70 (1.67–1.76) | 542 (537–542) | 45 (45–45) | 0.79 (0.76–0.80) | 1.45 (1.42–1.48) | 1.9 / 121.0 | 80 | NV 3D 101, NV VideoEncode 85 |

#### 5. IC-SCALE-hevc_nvenc_420: hevc_nvenc_420 · 1080p · nv12 · thread — `bench/matched_concurrent_hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json` (3 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.13 (0.12–0.14) | 4.31 (4.10–4.69) | 389 (380–390) | 389 (380–390) | 0.55 (0.52–0.63) | 1.41 (1.35–1.61) | 2.6 / 2.7 | 16 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.30 (0.28–0.31) | 2.47 (2.31–2.59) | 391 (388–391) | 98 (97–98) | 0.58 (0.58–0.60) | 1.50 (1.50–1.54) | 2.6 / 28.1 | 67 | NV 3D 103, NV VideoEncode 74 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 0.42 (0.35–0.44) | 1.73 (1.46–1.83) | 390 (389–392) | 49 (49–49) | 0.59 (0.59–0.61) | 1.52 (1.52–1.56) | 2.6 / 58.1 | 80 | NV 3D 101, NV VideoEncode 85 |
| 16 | 12 **(limit)** | yes | 0.0 | 0 | 30.0 | 0.65 (0.59–0.66) | 1.81 (1.63–1.82) | 390 (390–392) | 33 (33–33) | 0.58 (0.58–0.60) | 1.49 (1.48–1.54) | 2.6 / 87.5 | 86 | NV 3D 100, NV VideoEncode 90 |

#### 6. IC-SCALE-h264_qsv_420: h264_qsv_420 · 1080p · nv12 · thread — `bench/matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json` (3 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.17 (0.17–0.17) | 5.56 (5.49–5.59) | 542 (541–543) | 542 (541–543) | 1.15 (1.07–1.27) | 2.13 (1.98–2.34) | 1.7 / 4.3 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.36 (0.36–0.37) | 3.03 (2.99–3.10) | 678 (670–679) | 171 (169–171) | 1.65 (1.61–1.70) | 2.44 (2.37–2.54) | 5.8 / 11.9 | 0 | iGPU VideoDecode 45, iGPU 3D 30 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 0.62 (0.61–0.64) | 2.58 (2.53–2.66) | 684 (683–685) | 86 (86–86) | 1.74 (1.69–1.81) | 2.54 (2.47–2.64) | 11.4 / 21.9 | 0 | iGPU VideoDecode 68, iGPU 3D 49 |
| 16 | 16 | yes | 0.0 | 0 | 30.0 | 1.25 (1.23–1.28) | 2.60 (2.57–2.66) | 679 (678–682) | 43 (43–43) | 1.81 (1.78–1.94) | 2.66 (2.63–2.85) | 22.4 / 45.3 | 0 | iGPU VideoDecode 78, iGPU 3D 58 |

#### 7. IC-SCALE-hevc_qsv_420: hevc_qsv_420 · 1080p · nv12 · thread — `bench/matched_concurrent_hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json` (3 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.15 (0.15–0.18) | 5.17 (5.14–6.11) | 66 (66–66) | 66 (66–66) | 0.28 (0.24–0.29) | 4.17 (3.65–4.32) | 14.9 / 17.9 | 0 | iGPU 3D 79, iGPU VideoDecode 7 |
| 4 | 4 | no (0/4, 0/4, 0/4) | 98.4 (98.4–98.6) | 1,397 (1,394–1,397) | 16.8 | 0.25 (0.24–0.27) | 3.69 (3.52–4.00) | 67 (67–67) | 17 (17–17) | 0.24 (0.24–0.26) | 3.57 (3.53–3.80) | 59.0 / 87.7 | 0 | iGPU 3D 95, iGPU VideoDecode 8 |
| 8 | 8 | no (0/8, 0/8, 0/8) | 99.3 | 9,266 (9,257–9,277) | 8.3 | 0.25 (0.24–0.25) | 3.71 (3.67–3.72) | 66 (66–66) | 8 (8–8) | 0.23 (0.22–0.25) | 3.48 (3.38–3.77) | 118.6 / 186.5 | 0 | iGPU 3D 97, iGPU VideoDecode 9 |
| 16 | 16 | no (0/16, 0/16, 0/16) | 99.1 (99.1–99.2) | 44,139 (44,062–44,184) | 4.2 | 0.25 (0.23–0.26) | 3.70 (3.50–3.84) | 67 (67–67) | 4 (4–4) | 0.24 (0.24–0.26) | 3.66 (3.65–3.85) | 238.1 / 356.5 | 0 | iGPU 3D 100, iGPU VideoDecode 9 |

#### 8. IC-SCALE-mjpeg_qsv_420: mjpeg_qsv_420 · 1080p · nv12 · thread — `bench/matched_concurrent_mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json` (3 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 2.9 (2.9–5.8) | 0 | 30.0 | 0.13 (0.12–0.13) | 4.24 (3.96–4.31) | 406 (405–407) | 406 (405–407) | 0.80 (0.78–0.85) | 1.98 (1.93–2.08) | 2.3 / 3.2 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.30 (0.27–0.31) | 2.54 (2.28–2.60) | 687 (685–696) | 173 (173–176) | 1.47 (1.46–1.69) | 2.12 (2.11–2.46) | 5.6 / 10.8 | 0 | iGPU VideoDecode 30, iGPU 3D 11 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 0.51 (0.49–0.52) | 2.14 (2.05–2.15) | 701 (696–705) | 88 (88–89) | 1.62 (1.58–1.62) | 2.30 (2.26–2.32) | 11.0 / 20.9 | 0 | iGPU VideoDecode 48, iGPU 3D 17 |
| 16 | 16 | yes | 0.0 | 0 | 30.0 | 1.05 (1.03–1.05) | 2.19 (2.14–2.20) | 700 (695–705) | 44 (44–44) | 1.63 (1.56–1.71) | 2.31 (2.24–2.44) | 21.8 / 43.8 | 0 | iGPU VideoDecode 50, iGPU 3D 20 |

#### 9. IC-SCALE-nvjpeg_420: nvjpeg_420 · 1080p · nv12 · thread — `bench/matched_concurrent_nvjpeg_420_1080p_nv12_thread_20261110T052842Z.json` (3 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.51 (0.43–0.51) | 16.81 (14.34–17.08) | 192 (192–192) | 192 (192–192) | 2.06 (1.95–2.54) | 10.73 (10.16–13.23) | 5.1 / 6.5 | 0 | NV 3D 16 |
| 4 | 4 | yes | 0.2 (0.0–0.2) | 0 | 30.0 | 1.64 (1.51–1.67) | 13.65 (12.55–13.93) | 423 (418–426) | 107 (105–108) | 4.24 (4.09–4.67) | 10.01 (9.79–10.96) | 8.6 / 19.3 | 0 | NV 3D 12 |
| 8 | 8 | yes | 1.8 (0.0–2.0) | 0 | 30.0 | 2.56 (2.47–2.57) | 10.65 (10.27–10.69) | 456 (455–459) | 58 (57–58) | 4.35 (4.34–4.41) | 9.57 (9.52–9.60) | 16.6 / 35.6 | 0 | NV 3D 40 |
| 16 | 16 | no (1/16, 2/16, 3/16) | 83.6 (72.8–87.2) | 70 (56–79) | 29.4 | 4.73 (4.45–4.79) | 10.04 (9.39–10.16) | 475 (472–477) | 30 (30–30) | 4.87 (4.67–4.94) | 10.23 (9.90–10.35) | 32.0 / 66.3 | 0 | NV 3D 65 |

#### 10. IC-SCALE-jpeg_turbo_420-proc: jpeg_turbo_420 · 1080p · nv12 · process — `bench/matched_concurrent_jpeg_turbo_420_1080p_nv12_process_20261110T053417Z.json` (3 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.1 | 0.21 (0.20–0.21) | 7.05 (6.63–7.12) | 355 (352–357) | 358 (355–359) | 1.00 (0.99–1.00) | 2.81 | 2.8 / 3.3 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.1 | 0.72 (0.64–0.75) | 6.00 (5.29–6.27) | 1,397 (1,394–1,405) | 357 (355–359) | 3.97 (3.96–4.02) | 2.85 (2.84–2.87) | 2.8 / 3.4 | 0 | – |
| 8 | 8 | yes | 0.0 | 0 | 30.1 | 1.17 (1.16–1.40) | 4.87 (4.82–5.82) | 2,466 (2,405–2,591) | 332 (318–340) | -2.22 (-2.44–7.79) | -0.92 (-0.99–3.01) | 2.9 / 4.4 | 0 | – |
| 16 | 16 | yes | 0.0 | 0 | 30.1 | 1.69 (1.59–1.78) | 3.51 (3.32–3.70) | 3,572 (3,512–3,579) | 228 (228–230) | 15.32 (13.10–15.41) | 4.29 (3.73–4.31) | 4.4 / 5.6 | 0 | – |

#### 11. IC-SCALE-jpeg_turbo_420-thread: jpeg_turbo_420 · 1080p · nv12 · thread — `bench/matched_concurrent_jpeg_turbo_420_1080p_nv12_thread_20261110T053447Z.json` (1 rep)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | not run (unpaced only) | – | – | – | – | – | 355 | 355 | 0.96 | 2.71 | 2.8 / 3.4 | 0 | – |
| 4 | 4 | not run (unpaced only) | – | – | – | – | – | 1,440 | 360 | 4.03 | 2.80 | 2.8 / 3.1 | 0 | – |
| 8 | 8 | not run (unpaced only) | – | – | – | – | – | 2,707 | 344 | 7.81 | 2.88 | 2.9 / 4.3 | 0 | – |
| 16 | 16 | not run (unpaced only) | – | – | – | – | – | 3,511 | 225 | 14.55 | 4.14 | 4.3 / 7.3 | 0 | – |

### 4.2 4:2:2 from YUY2, 1080p (items 31–34; 2 reps)

#### 31. IC-SCALE-jpeg_turbo_422-proc-yuy2: jpeg_turbo_422 · 1080p · yuy2 · process — `bench/matched_concurrent_jpeg_turbo_422_1080p_yuy2_process_20261110T063244Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.1 | 0.24 (0.23–0.24) | 7.88 (7.64–8.12) | 225 (224–226) | 226 (225–227) | 1.00 (0.99–1.00) | 4.43 | 4.4 / 5.1 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.1 | 0.72 (0.72–0.73) | 6.02 (5.96–6.08) | 848 (846–849) | 215 (214–215) | 3.16 (2.35–3.98) | 3.73 (2.77–4.69) | 4.6 / 5.6 | 0 | – |
| 8 | 8 | yes | 0.0 | 0 | 30.1 | 1.69 (1.50–1.89) | 7.05 (6.25–7.85) | 1,461 (1,445–1,476) | 188 (186–190) | 2.58 (0.75–4.41) | 1.78 (0.51–3.05) | 5.0 / 7.8 | 0 | – |
| 16 | 16 | yes | 0.0 | 0 | 30.1 | 2.81 (2.48–3.14) | 5.85 (5.17–6.53) | 1,742 (1,719–1,766) | 111 (111–112) | 14.67 (13.77–15.56) | 8.41 (8.01–8.81) | 8.3 / 13.1 | 0 | – |

#### 32. IC-SCALE-nvjpeg_422-yuy2: nvjpeg_422 · 1080p · yuy2 · thread — `bench/matched_concurrent_nvjpeg_422_1080p_yuy2_thread_20261110T063635Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.1 | 0.60 (0.58–0.63) | 20.05 (19.27–20.83) | 230 (229–232) | 230 (229–232) | 1.88 (1.88–1.88) | 8.18 (8.12–8.23) | 4.8 / 6.7 | 0 | NV 3D 18 |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 1.65 (1.61–1.68) | 13.70 (13.42–13.98) | 482 (463–502) | 121 (116–126) | 4.74 (4.70–4.78) | 9.86 (9.38–10.34) | 7.7 / 26.0 | 0 | NV 3D 6 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 2.47 (2.47–2.47) | 10.29 (10.28–10.30) | 513 (511–515) | 65 (64–65) | 5.26 (5.04–5.48) | 10.26 (9.79–10.74) | 15.1 / 32.0 | 0 | NV 3D 68 |
| 16 | 16 | yes | 9.3 (5.3–13.3) | 0 | 30.0 | 4.68 (4.63–4.74) | 9.76 (9.65–9.88) | 567 (567–568) | 36 (36–36) | 5.85 (5.36–6.34) | 10.31 (9.45–11.16) | 26.8 / 53.2 | 0 | NV 3D 83 |

#### 33. IC-SCALE-mjpeg_qsv_422-yuy2: mjpeg_qsv_422 · 1080p · yuy2 · thread — `bench/matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.13 (0.13–0.14) | 4.43 (4.31–4.55) | 320 (317–324) | 320 (317–324) | 0.50 (0.48–0.52) | 1.56 (1.51–1.61) | 3.0 / 3.8 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.34 (0.34–0.34) | 2.82 (2.80–2.83) | 925 (922–928) | 237 (237–238) | 1.93 (1.92–1.95) | 2.09 (2.08–2.10) | 4.0 / 10.9 | 0 | iGPU VideoDecode 46, iGPU 3D 16 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 0.50 (0.49–0.51) | 2.07 (2.03–2.10) | 923 (922–923) | 117 (116–117) | 1.98 (1.95–2.01) | 2.15 (2.11–2.18) | 8.0 / 23.8 | 0 | iGPU VideoDecode 59, iGPU 3D 23 |
| 16 | 16 | yes | 0.0 | 0 | 30.0 | 0.92 (0.86–0.97) | 1.91 (1.79–2.03) | 934 (932–936) | 59 (59–59) | 2.12 (2.03–2.21) | 2.27 (2.17–2.37) | 16.1 / 37.0 | 0 | iGPU VideoDecode 74, iGPU 3D 31 |

#### 34. IC-SCALE-hevc_qsv_422-yuy2: hevc_qsv_422 · 1080p · yuy2 · thread — `bench/matched_concurrent_hevc_qsv_422_1080p_yuy2_thread_20261110T065430Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.15 (0.15–0.16) | 5.10 (4.86–5.35) | 64 (64–64) | 64 (64–64) | 0.20 (0.19–0.20) | 3.10 (3.02–3.18) | 15.4 / 18.6 | 0 | iGPU 3D 78, iGPU VideoDecode 11 |
| 4 | 4 | no (0/4, 0/4) | 98.5 | 1,500 (1,499–1,500) | 16.2 | 0.26 (0.26–0.26) | 3.99 (3.94–4.04) | 65 (65–65) | 16 (16–16) | 0.25 (0.25–0.25) | 3.83 (3.81–3.85) | 61.6 / 96.6 | 0 | iGPU 3D 95, iGPU VideoDecode 13 |
| 8 | 8 | no (0/8, 0/8) | 99.3 | 9,768 (9,755–9,782) | 8.0 | 0.25 (0.24–0.26) | 3.89 (3.80–3.99) | 64 (64–64) | 8 (8–8) | 0.25 (0.25–0.25) | 3.96 (3.94–3.97) | 122.2 / 203.2 | 0 | iGPU 3D 97, iGPU VideoDecode 13 |
| 16 | 16 | no (0/16, 0/16) | 99.2 | 45,802 (45,785–45,820) | 4.0 | 0.25 | 3.90 (3.90–3.90) | 65 (65–65) | 4 (4–4) | 0.25 (0.25–0.25) | 3.86 (3.83–3.89) | 243.1 / 398.8 | 0 | iGPU 3D 100, iGPU VideoDecode 13 |

### 4.3 Recorder pipelines from camera MJPEG / YUY2, 1080p (items 41–45; 2 reps)

#### 41. IC-SCALE-h264_nvenc_420-mjpeg_cpu: h264_nvenc_420 · 1080p · mjpeg_cpu · thread — `bench/matched_concurrent_h264_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.33 (0.33–0.34) | 11.02 (10.90–11.15) | 240 (240–241) | 241 (240–241) | 2.21 (2.12–2.30) | 9.19 (8.80–9.58) | 4.3 / 4.9 | 19 | NV 3D 33, NV VideoEncode 22 |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 1.35 (1.32–1.37) | 11.22 (11.00–11.45) | 590 (586–594) | 148 (148–149) | 5.32 (4.66–5.98) | 9.01 (7.96–10.06) | 4.9 / 17.7 | 53 | NV 3D 101, NV VideoEncode 65 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 2.55 (2.12–2.98) | 10.64 (8.85–12.43) | 593 (590–595) | 75 (75–75) | 4.98 (4.91–5.04) | 8.39 (8.32–8.47) | 5.0 / 58.7 | 69 | NV 3D 98, NV VideoEncode 79 |
| 16 | 12 **(limit)** | yes | 0.0 | 0 | 30.0 | 4.06 (4.01–4.10) | 11.27 (11.15–11.39) | 596 (595–597) | 50 (50–50) | 5.12 (5.03–5.21) | 8.59 (8.46–8.72) | 5.0 / 95.6 | 78 | NV 3D 97, NV VideoEncode 85 |

#### 42. IC-SCALE-hevc_nvenc_420-mjpeg_cpu: hevc_nvenc_420 · 1080p · mjpeg_cpu · thread — `bench/matched_concurrent_hevc_nvenc_420_1080p_mjpeg_cpu_thread_20261110T082302Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.33 (0.32–0.34) | 10.94 (10.56–11.32) | 238 (238–239) | 239 (239–239) | 2.17 (1.99–2.36) | 9.11 (8.33–9.90) | 4.3 / 4.9 | 27 | NV VideoEncode 33 |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 1.29 (1.25–1.32) | 10.73 (10.46–11.01) | 375 (374–376) | 94 (94–95) | 3.14 (3.08–3.20) | 8.37 (8.22–8.52) | 4.7 / 30.3 | 66 | NV 3D 87, NV VideoEncode 74 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 2.87 (2.85–2.89) | 11.96 (11.89–12.04) | 378 (377–379) | 48 (47–48) | 3.08 (3.07–3.08) | 8.13 (8.09–8.18) | 4.8 / 67.3 | 81 | NV 3D 99, NV VideoEncode 85 |
| 16 | 12 **(limit)** | yes | 0.0 | 0 | 30.0 | 3.90 (3.77–4.03) | 10.84 (10.48–11.21) | 378 (376–379) | 32 (32–32) | 3.12 (3.10–3.15) | 8.26 (8.16–8.36) | 4.8 / 103.3 | 84 | NV 3D 96, NV VideoEncode 90 |

#### 43. IC-SCALE-h264_qsv_420-mjpeg_qsv: h264_qsv_420 · 1080p · mjpeg_qsv · thread — `bench/matched_concurrent_h264_qsv_420_1080p_mjpeg_qsv_thread_20261110T082702Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 1.1 | 0 | 30.1 | 0.44 (0.44–0.44) | 14.71 (14.69–14.72) | 347 (289–405) | 348 (289–406) | 2.78 (2.13–3.42) | 7.92 (7.40–8.44) | 2.3 / 3.8 | 0 | iGPU VideoDecode 20, iGPU 3D 9 |
| 4 | 4 | yes | 2.4 (2.4–2.5) | 0 | 30.0 | 1.91 (1.84–1.98) | 15.88 (15.30–16.46) | 428 (416–441) | 109 (106–112) | 3.63 (3.11–4.16) | 8.53 (7.04–10.01) | 3.9 / 37.6 | 0 | iGPU VideoDecode 58, iGPU 3D 36 |
| 8 | 8 | yes | 3.7 (3.1–4.2) | 0 | 30.0 | 2.85 (2.79–2.90) | 11.85 (11.63–12.07) | 457 (449–465) | 58 (57–59) | 3.25 (2.98–3.52) | 7.12 (6.41–7.83) | 4.0 / 93.3 | 0 | iGPU VideoDecode 81, iGPU 3D 50 |
| 16 | 16 | yes | 0.0 | 0 | 30.0 | 4.33 (4.30–4.35) | 9.01 (8.96–9.06) | 486 (476–495) | 31 (30–31) | 3.82 (3.73–3.91) | 7.87 (7.83–7.90) | 3.9 / 195.5 | 0 | iGPU VideoDecode 92, iGPU 3D 59 |

#### 44. IC-SCALE-hevc_qsv_420-mjpeg_qsv: hevc_qsv_420 · 1080p · mjpeg_qsv · thread — `bench/matched_concurrent_hevc_qsv_420_1080p_mjpeg_qsv_thread_20261110T083946Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 1.4 (1.3–1.6) | 0 | 30.0 | 0.43 (0.41–0.46) | 14.36 (13.58–15.14) | 64 (64–64) | 64 (64–64) | 0.74 (0.62–0.86) | 11.64 (9.79–13.49) | 14.9 / 17.3 | 0 | iGPU 3D 77, iGPU VideoDecode 13 |
| 4 | 4 | no (0/4, 0/4) | 99.0 (98.2–99.8) | 1,424 (1,396–1,453) | 16.4 | 0.92 (0.89–0.94) | 13.84 (13.34–14.33) | 66 (66–67) | 17 (16–17) | 0.90 (0.87–0.93) | 13.62 (13.28–13.96) | 59.1 / 103.8 | 0 | iGPU 3D 95, iGPU VideoDecode 15 |
| 8 | 8 | no (0/8, 0/8) | 99.0 | 9,232 (9,225–9,239) | 8.3 | 1.06 (1.03–1.08) | 15.87 (15.54–16.20) | 66 (66–67) | 8 | 0.97 (0.96–0.99) | 14.62 (14.41–14.83) | 117.9 / 205.7 | 0 | iGPU 3D 99, iGPU VideoDecode 16 |
| 16 | 16 | no (0/16, 0/16) | 99.5 (99.3–99.6) | 44,404 (44,356–44,453) | 4.1 | 0.96 (0.93–0.99) | 14.48 (14.07–14.89) | 66 (66–67) | 4 (4–4) | 0.96 (0.95–0.97) | 14.46 (14.33–14.60) | 235.8 / 397.1 | 0 | iGPU 3D 99, iGPU VideoDecode 16 |

#### 45. IC-SCALE-h264_nvenc_420-yuy2: h264_nvenc_420 · 1080p · yuy2 · thread — `bench/matched_concurrent_h264_nvenc_420_1080p_yuy2_thread_20261110T084300Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.46 (0.44–0.49) | 15.38 (14.55–16.21) | 512 (511–512) | 513 (513–514) | 2.65 (1.94–3.36) | 5.18 (3.80–6.56) | 1.9 / 2.2 | 12 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 1.58 (1.49–1.66) | 13.15 (12.45–13.85) | 537 (537–537) | 135 (135–135) | 2.61 (2.42–2.80) | 4.86 (4.50–5.22) | 1.9 / 28.9 | 58 | NV 3D 104, NV VideoEncode 66 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 2.25 (2.03–2.46) | 9.35 (8.47–10.23) | 539 (537–540) | 68 (68–68) | 3.03 (2.84–3.22) | 5.62 (5.29–5.95) | 1.9 / 63.2 | 71 | NV 3D 101, NV VideoEncode 79 |
| 16 | 12 **(limit)** | yes | 0.0 | 0 | 30.0 | 2.53 (2.41–2.64) | 7.02 (6.69–7.34) | 540 (540–541) | 45 (45–45) | 2.89 (2.88–2.90) | 5.35 (5.32–5.38) | 1.9 / 100.7 | 80 | NV 3D 100, NV VideoEncode 85 |

### 4.4 720p from NV12 (items 49–55; 2 reps)

#### 49. IC-SCALE720-h264_nvenc_420: h264_nvenc_420 · 720p · nv12 · thread — `bench/matched_concurrent_h264_nvenc_420_720p_nv12_thread_20261110T085446Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.1 | 0.07 (0.06–0.07) | 2.17 (1.91–2.43) | 1,017 (991–1,042) | 1,017 (991–1,042) | 0.61 (0.52–0.70) | 0.60 (0.52–0.68) | 1.0 / 1.9 | 2 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.23 (0.22–0.24) | 1.91 (1.84–1.97) | 1,120 (1,118–1,123) | 283 (282–283) | 0.66 (0.63–0.69) | 0.59 (0.56–0.61) | 0.9 / 26.0 | 40 | NV 3D 107, NV VideoEncode 49 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 0.35 (0.33–0.37) | 1.46 (1.37–1.54) | 1,108 (1,107–1,109) | 141 (140–141) | 0.70 (0.69–0.72) | 0.63 (0.62–0.65) | 0.9 / 63.4 | 57 | NV 3D 92, NV VideoEncode 66 |
| 16 | 12 **(limit)** | yes | 0.0 | 0 | 30.0 | 0.39 (0.39–0.40) | 1.09 (1.07–1.11) | 1,115 (1,115–1,115) | 94 (94–95) | 0.64 (0.61–0.66) | 0.57 (0.55–0.59) | 0.9 / 98.4 | 67 | NV 3D 102, NV VideoEncode 74 |

#### 50. IC-SCALE720-hevc_nvenc_420: hevc_nvenc_420 · 720p · nv12 · thread — `bench/matched_concurrent_hevc_nvenc_420_720p_nv12_thread_20261110T085747Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.1 | 0.06 (0.05–0.07) | 1.96 (1.70–2.22) | 795 (787–804) | 796 (787–804) | 0.48 (0.42–0.53) | 0.60 (0.52–0.68) | 1.2 / 1.7 | 16 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.23 (0.22–0.24) | 1.92 (1.81–2.04) | 840 (834–847) | 211 (209–213) | 0.53 (0.49–0.57) | 0.63 (0.59–0.68) | 1.2 / 22.6 | 52 | NV 3D 106, NV VideoEncode 48 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 0.35 (0.34–0.35) | 1.44 (1.41–1.48) | 841 (839–843) | 106 (105–106) | 0.51 (0.48–0.54) | 0.60 (0.57–0.64) | 1.2 / 51.0 | 67 | NV 3D 104, NV VideoEncode 65 |
| 16 | 12 **(limit)** | yes | 0.0 | 0 | 30.0 | 0.42 (0.41–0.43) | 1.16 (1.14–1.19) | 842 (840–844) | 70 (70–71) | 0.53 (0.53–0.54) | 0.63 (0.62–0.64) | 1.2 / 79.4 | 72 | NV 3D 101, NV VideoEncode 80 |

#### 51. IC-SCALE720-h264_qsv_420: h264_qsv_420 · 720p · nv12 · thread — `bench/matched_concurrent_h264_qsv_420_720p_nv12_thread_20261110T090121Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.1 | 0.12 (0.12–0.12) | 3.89 (3.82–3.96) | 998 (996–1,001) | 998 (996–1,001) | 0.83 (0.62–1.04) | 0.83 (0.62–1.04) | 0.9 / 2.2 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.38 (0.34–0.41) | 3.12 (2.81–3.43) | 1,480 (1,459–1,500) | 383 (377–389) | 1.79 (1.75–1.84) | 1.21 (1.20–1.22) | 1.9 / 12.8 | 0 | – |
| 8 | 8 | yes | 0.0 | 0 | 30.1 | 0.53 (0.53–0.53) | 2.20 (2.19–2.21) | 1,567 (1,563–1,571) | 199 (199–200) | 2.02 (1.96–2.08) | 1.29 (1.25–1.33) | 2.0 / 35.9 | 0 | iGPU 3D 47, iGPU VideoDecode 46 |
| 16 | 16 | yes | 0.0 | 0 | 30.0 | 0.79 (0.75–0.82) | 1.64 (1.57–1.71) | 1,575 (1,572–1,578) | 100 (99–100) | 2.00 (1.99–2.02) | 1.27 (1.26–1.28) | 2.0 / 85.7 | 0 | iGPU 3D 74, iGPU VideoDecode 72 |

#### 52. IC-SCALE720-hevc_qsv_420: hevc_qsv_420 · 720p · nv12 · thread — `bench/matched_concurrent_hevc_qsv_420_720p_nv12_thread_20261110T090841Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.0 | 0.11 (0.10–0.11) | 3.65 (3.51–3.79) | 123 (122–124) | 123 (122–124) | 0.31 (0.31–0.31) | 2.50 | 8.0 / 10.8 | 0 | iGPU 3D 61, iGPU VideoDecode 6 |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.33 (0.31–0.36) | 2.78 (2.55–3.00) | 135 | 34 (34–34) | 0.34 (0.31–0.37) | 2.54 (2.33–2.75) | 29.5 / 31.8 | 0 | iGPU 3D 89, iGPU VideoDecode 9 |
| 8 | 8 | no (0/8, 0/8) | 98.5 (98.5–98.6) | 2,760 (2,760–2,761) | 16.8 | 0.37 (0.36–0.38) | 2.74 (2.67–2.81) | 134 (134–134) | 17 (17–17) | 0.33 (0.33–0.34) | 2.48 (2.44–2.52) | 59.1 / 62.8 | 0 | iGPU 3D 94, iGPU VideoDecode 9 |
| 16 | 16 | no (0/16, 0/16) | 99.3 | 18,362 (18,335–18,390) | 8.4 | 0.37 (0.36–0.37) | 2.74 (2.69–2.79) | 134 (134–134) | 8 | 0.35 (0.33–0.37) | 2.60 (2.45–2.76) | 118.4 / 124.2 | 0 | iGPU 3D 97, iGPU VideoDecode 9 |

#### 53. IC-SCALE720-mjpeg_qsv_420: mjpeg_qsv_420 · 720p · nv12 · thread — `bench/matched_concurrent_mjpeg_qsv_420_720p_nv12_thread_20261110T091225Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 2.8 (0.0–5.6) | 0 | 30.1 | 0.07 (0.06–0.07) | 2.24 (2.01–2.46) | 759 (756–762) | 759 (756–762) | 0.61 (0.48–0.75) | 0.81 (0.62–0.99) | 1.2 / 2.4 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 0.26 (0.25–0.28) | 2.19 (2.07–2.32) | 1,226 (1,213–1,240) | 308 (305–311) | 1.23 (1.03–1.42) | 1.00 (0.83–1.17) | 2.1 / 13.6 | 0 | iGPU VideoDecode 11, iGPU 3D 5 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 0.39 (0.38–0.41) | 1.63 (1.58–1.69) | 1,793 (1,787–1,798) | 226 (224–228) | 1.87 (1.80–1.94) | 1.04 (1.00–1.09) | 3.7 / 13.8 | 0 | iGPU VideoDecode 31, iGPU 3D 16 |
| 16 | 16 | yes | 0.0 | 0 | 30.0 | 0.57 (0.57–0.57) | 1.19 (1.18–1.19) | 1,794 (1,779–1,809) | 113 (112–114) | 2.03 (1.96–2.10) | 1.13 (1.10–1.16) | 8.5 / 17.2 | 0 | iGPU VideoDecode 45, iGPU 3D 22 |

#### 54. IC-SCALE720-nvjpeg_420: nvjpeg_420 · 720p · nv12 · thread — `bench/matched_concurrent_nvjpeg_420_720p_nv12_thread_20261110T091527Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.1 | 0.42 (0.39–0.44) | 13.85 (13.02–14.69) | 418 (361–475) | 419 (362–476) | 1.84 (1.48–2.20) | 4.61 (3.12–6.09) | 2.3 / 4.1 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.0 | 1.49 (1.47–1.51) | 12.38 (12.20–12.56) | 771 (724–818) | 194 (182–205) | 4.39 (4.38–4.40) | 5.72 (5.38–6.05) | 4.7 / 9.6 | 0 | NV 3D 22 |
| 8 | 8 | yes | 0.0 | 0 | 30.0 | 2.23 (2.07–2.40) | 9.31 (8.63–9.98) | 932 (924–940) | 118 (116–119) | 5.26 (5.14–5.38) | 5.64 (5.47–5.82) | 7.9 / 17.8 | 0 | NV 3D 75 |
| 16 | 16 | yes | 0.9 (0.0–1.9) | 0 | 30.0 | 3.07 (3.02–3.12) | 6.39 (6.29–6.49) | 969 (957–981) | 61 (61–62) | 5.49 (5.19–5.80) | 5.67 (5.42–5.92) | 15.5 / 33.5 | 0 | NV 3D 66 |

#### 55. IC-SCALE720-jpeg_turbo_420-proc: jpeg_turbo_420 · 720p · nv12 · process — `bench/matched_concurrent_jpeg_turbo_420_720p_nv12_process_20261110T091904Z.json` (2 reps)

| N | opened | paced: keeps up | paced: late % | paced: dropped-equiv | paced: per-stream fps min | paced: CPU cores | paced: CPU ms/frame | unpaced: aggregate fps | unpaced: per-stream fps median | unpaced: CPU cores | unpaced: CPU ms/frame | unpaced: encode ms p50 / p99 | unpaced: NV enc % (smi) | unpaced: GPU Engine % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1 | yes | 0.0 | 0 | 30.1 | 0.15 (0.15–0.15) | 4.93 (4.86–5.00) | 731 (726–735) | 736 (731–741) | 0.99 (0.96–1.02) | 1.35 (1.30–1.41) | 1.3 / 2.4 | 0 | – |
| 4 | 4 | yes | 0.0 | 0 | 30.1 | 0.47 (0.44–0.50) | 3.90 (3.68–4.12) | 2,863 (2,860–2,865) | 731 (727–735) | 3.99 (3.98–3.99) | 1.39 | 1.4 / 1.6 | 0 | – |
| 8 | 8 | yes | 0.0 | 0 | 30.1 | 0.81 (0.70–0.91) | 3.37 (2.93–3.80) | 4,864 (4,646–5,082) | 672 (652–693) | -0.21 (-1.15–0.73) | -0.05 (-0.25–0.14) | 1.4 / 2.1 | 0 | – |
| 16 | 16 | yes | 0.0 | 0 | 30.1 | 2.05 (1.29–2.80) | 4.26 (2.69–5.82) | 7,271 (7,143–7,400) | 480 (479–481) | 14.25 (12.86–15.63) | 1.96 (1.80–2.11) | 2.0 / 3.0 | 0 | – |

## 5. Scaling summary and limit probes

### 5.1 Largest N at which every stream kept up at 30 fps (paced; read from the tables above)

| path · source | 1080p | 720p |
|---|---|---|
| h264_nvenc_420 · NV12 | 12 (all that opened; N=16 → 12, session limit) | 12 (all that opened) |
| hevc_nvenc_420 · NV12 | 12 (all that opened) | 12 (all that opened) |
| h264_qsv_420 · NV12 | 16 | 16 |
| hevc_qsv_420 · NV12 | 1 (N=4: 0/4 in every rep) | 4 (N=8: 0/8) |
| mjpeg_qsv_420 · NV12 | 16 | 16 |
| nvjpeg_420 · NV12 | 8 (N=16: 1–3 of 16) | 16 |
| jpeg_turbo_420 · NV12 · process | 16 | 16 |
| jpeg_turbo_422 · YUY2 · process | 16 | – |
| nvjpeg_422 · YUY2 | 16 (9.3 % late at N=16) | – |
| mjpeg_qsv_422 · YUY2 | 16 | – |
| hevc_qsv_422 · YUY2 | 1 (N=4: 0/4) | – |
| h264_nvenc_420 · MJPEG CPU decode / YUY2 | 12 (all that opened) / 12 (all that opened) | – |
| hevc_nvenc_420 · MJPEG CPU decode | 12 (all that opened) | – |
| h264_qsv_420 · MJPEG QSV decode | 16 | – |
| hevc_qsv_420 · MJPEG QSV decode | 1 (N=4: 0/4) | – |

### 5.2 Limit probes

`--limit-probe 32`: open up to 32 encoders one by one, 2 frames each, all kept open; record how many opened and the first error (`bench_matched_concurrent.py:217-234`). The queue gave a probe to items 4, 5, 6, 8 and 33. The code skips simplejpeg and nvJPEG (`:268`).

| path · size · source | file | tried | opened | first error | nvidia-smi at peak (sessions, gpu, enc, dec) |
|---|---|---|---|---|---|
| h264_nvenc_420 · 1080p · nv12 · thread | `bench/matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json` | 32 | 12 | `ExternalError: [Errno 542398533] Generic error in an external library: 'avcodec_open2("h264_nve…` | 12, 5 %, 0 %, 0 % |
| h264_qsv_420 · 1080p · nv12 · thread | `bench/matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json` | 32 | 32 | `none (all opened)` | 0, 0 %, 0 %, 0 % |
| hevc_nvenc_420 · 1080p · nv12 · thread | `bench/matched_concurrent_hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json` | 32 | 12 | `ExternalError: [Errno 542398533] Generic error in an external library: 'avcodec_open2("hevc_nve…` | 12, 8 %, 6 %, 0 % |
| mjpeg_qsv_420 · 1080p · nv12 · thread | `bench/matched_concurrent_mjpeg_qsv_420_1080p_nv12_thread_20261110T052313Z.json` | 32 | 32 | `none (all opened)` | 0, 0 %, 0 %, 0 % |
| mjpeg_qsv_422 · 1080p · yuy2 · thread | `bench/matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json` | 32 | 32 | `none (all opened)` | 0, 0 %, 0 %, 0 % |

- **NVENC (H.264 and HEVC): 12 concurrent sessions in one process.** The 13th `avcodec_open2` fails with `ExternalError [Errno 542398533] Generic error in an external library`, and nvidia-smi reports `encoder.stats.sessionCount` = 12 at the peak. The 16-stream runs hit the same limit.
- **QSV (h264_qsv, mjpeg_qsv 4:2:0 and 4:2:2): 32 of 32 opened, no error.** No limit was reached up to 32.

## 6. Headline numbers

Paths are relative to `results/intra_compare/`.

1. **NVENC allows 12 concurrent encode sessions** (H.264 and HEVC). The probe opened 12 of 32; the 13th `avcodec_open2` fails and nvidia-smi shows 12 sessions at the peak. Sources: `bench/matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json` and `bench/matched_concurrent_hevc_nvenc_420_1080p_nv12_thread_20261110T045146Z.json`.
2. **h264_nvenc 1080p30 from NV12 at target A, 12 streams paced:** all keep up, 0 late frames, 0.61 (0.60–0.64) CPU cores and 1.70 ms CPU per frame. Unpaced, the 12 streams together reach 542 (537–542) fps at 80 % NVENC utilisation (nvidia-smi). Source: `bench/matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json`.
3. **h264_qsv 1080p30 from NV12, 16 streams paced:** all keep up at 1.25 (1.23–1.28) cores. Unpaced aggregate: 679 (678–682) fps. The probe opened 32 of 32 with no error. Source: `bench/matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json`.
4. **hevc_qsv 4:2:0 1080p tops out at 66–67 fps aggregate at every N**, so only 1 × 1080p30 stream keeps up. With 4 streams paced, 0 of 4 keep up in every rep: 98.4 % late, 1,397 dropped-equivalent. hevc_qsv 4:2:2 from YUY2 is the same (64–65 fps). Sources: `bench/matched_concurrent_hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json` and `bench/matched_concurrent_hevc_qsv_422_1080p_yuy2_thread_20261110T065430Z.json`.
5. **libjpeg-turbo 4:2:0 1080p, 16 streams:** 3,511 fps with threads (14.55 cores) against 3,572 (3,512–3,579) fps with processes. Threads scale like processes, so simplejpeg does not serialise on the GIL (inferred from the scaling). 16 × 1080p30 paced keeps up at 1.69 (1.59–1.78) cores, a lower bound (process mode). Sources: `bench/matched_concurrent_jpeg_turbo_420_1080p_nv12_thread_20261110T053447Z.json` and `bench/matched_concurrent_jpeg_turbo_420_1080p_nv12_process_20261110T053417Z.json`.
6. **nvJPEG 4:2:0 1080p from host NV12 (via swscale RGB):** 8 streams keep up, 16 do not (1, 2 and 3 of 16 per rep; 83.6 % late). The unpaced aggregate is 475 (472–477) fps. Source: `bench/matched_concurrent_nvjpeg_420_1080p_nv12_thread_20261110T052842Z.json`.
7. **Camera MJPEG CPU decode → h264_nvenc 1080p, 12 streams paced:** all keep up at 4.06 (4.01–4.10) cores (11.27 ms/frame), against 0.61 cores from NV12. Unpaced aggregate: 596 (595–597) fps. Source: `bench/matched_concurrent_h264_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z.json`.
8. **Single stream, target A, 1080p from NV12:**

   | path | size vs jt422 | fps | CPU ms/frame |
   |---|---|---|---|
   | hevc_qsv | 0.41 | 65 | 2.81 |
   | hevc_nvenc | 0.47 | 390 | 1.47 |
   | h264_nvenc | 0.55 | 540 | 1.40 |
   | h264_qsv | 0.59 | 585 | 2.04 |
   | libjpeg-turbo 4:2:0 | 0.89 | 360 | 2.77 |

   All QC rows hit target (SSIM-Y 0.9970–0.9973). Source: `bench/matched_stream_A_1080p_20261110T042204Z.json`.
9. **nvJPEG encode alone** (exact RGB source): 1,126 (1,117–1,132) fps at 0.87 ms CPU/frame. From host NV12 it drops to 323 (283–341) fps at 7.57 ms/frame. Fed decoded camera MJPEG it misses quality: SSIM-Y 0.9954 at target A, PSNR-Y 43.14 dB at target B. Sources: `bench/matched_stream_A_1080p_20261110T042204Z.json` and `bench/matched_stream_B_1080p_20261110T044204Z.json`.
10. **mjpeg_qsv 4:2:2 from native YUY2, 16 × 1080p30 paced:** all keep up at 0.92 (0.86–0.97) cores. Unpaced aggregate: 934 (932–936) fps. The probe opened 32 of 32. Source: `bench/matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json`.

## 7. Caveats

1. **libx265 rows are not P-core-only.**
   - Measured: every libx265 cell in items 1–3 shows `cpu_cores` 23.25–27.31 (all reps, warm-up included). A process on 16 logical CPUs cannot exceed 16, so those rows ran on more of the 28 CPUs. This already shows in the warm-up rep of the first libx265 cell (26.7).
   - Measured: `system_after.process_cpu_affinity` is 0–27 in all three `matched_stream_*` files, against 0–15 before.
   - Measured: the 24 scaling files keep 0–15 before and after.
   - Whether the non-x265 cells that ran after the first libx265 cell also had the wider mask cannot be told from the files. None of them exceeds 10 cores (max 9.97, libx264_veryfast from `mjpeg_qsv`).
   - Inferred: the x265 thread pool set its own affinity. Not verified.
2. **The input work is in the timed loop** (`benchpaths.py:7-19`, queue notes).
   - MJPEG-source rows include the MJPEG decode and the swscale range change.
   - YUY2 rows of 4:2:0 paths include the swscale yuyv422 → target format step.
   - NV12 / YUY2 range mapping is done untimed.
3. **nvJPEG from host NV12 / YUY2 / MJPEG goes through swscale `rgb24`** (`benchpaths.py:214-215, 227-228, 239-240`). Its fps and CPU therefore include that conversion. Its QC from NV12 / YUY2 hits target A (1080p PSNR-Y 52.344 / 52.365 dB, SSIM-Y 0.99707 / 0.99708; 720p 51.474 / 51.485 dB), above the sweep's exact-RGB matched value (50.797 dB at 1080p); only the decoded-MJPEG (`mjpeg_cpu`) feed misses (45.211 dB at A 1080p) (`bench/matched_stream_A_{1080p,720p}_*.json`, `summary[*].quality_check`). The swscale-RGB loss measured separately in `nvjpeg_rgb_diag.json` (46.73 dB for the RGB step on yuy2_1080p, `NOTES.md` §9.3) does not show in the bench QC from those feeds; why is NOT VERIFIED (corrected 2026-11-10, GF05: was "its QC carries the swscale RGB bias", which does not match the bench QC from NV12/YUY2, per `VERIFY_provenance.md` §5). The `rgb` source (exact BT.601 RGB prepared untimed) times the encode call alone.
4. **Process-worker CPU is a lower bound.** The code sums the children's CPU and skips a child that has already exited at the second read (`bench_matched_concurrent.py:202-210`, comment at `:210`).
   - Three unpaced N=8 runs recorded negative CPU: item 10 reps 1 and 3 (−2.22, −2.44 cores), item 55 rep 1 (−1.15). Their medians are not usable.
   - Treat every process-mode CPU number as a floor. Item 11 (threads) gives an in-process CPU figure for the same encoder.
5. **The QC covers the first 4 frames** (`--qcheck-frames 4`, `bench_matched_stream.py:87`), from a separate untimed encoder.
   - It is not computed on the timed frames.
   - The scaling items have no QC; they use the same `matched_settings.json` entries (`entry` block in each JSON).
6. **Short source sets, cycled** (`benchpaths.py:190, 206, 218`; sets in `iclib.py:43-48`):
   - YUY2: 16 frames (8 per camera);
   - MJPEG 1080p: 38 camera JPEGs;
   - MJPEG 720p: 240.
7. **Reps:**
   - single-stream: 1 warm-up + 5 (A 1080p), 4 (A 720p), 3 (B 1080p);
   - scaling: 3 reps for items 4–10, 1 rep for item 11 (unpaced only), 2 reps for items 31–55.
   - Min–max over 2 reps is only the two values.
8. **GPU utilisation from unpaced N=1 runs is unreliable.** These runs last 0.29–1.6 s for every path except hevc_qsv (2.4–4.7 s); h264_nvenc 1080p NV12 runs 0.58–0.59 s. That is at or below the 1 s typeperf period. The GPU Engine column is empty for the N=1 unpaced runs in 11 of the 20 GPU-path files, whose runs last 0.29–0.95 s. The nvidia-smi encoder % there is low (11 % for h264_nvenc 1080p NV12, against 100 % in item 1). Use the single-stream items for 1-stream GPU load.
9. **GPU metric scope:**
   - nvidia-smi columns are GPU-wide.
   - GPU Engine columns are per process (per child pid for process workers), and the iGPU's QSV work appears under the engine names Windows gives (`VideoDecode`, `3D`, occasionally `VideoProcessing`).
