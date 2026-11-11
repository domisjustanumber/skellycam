# uncompressed_intra (G4): timed bench results (23:00 run, 2026-11-09/10)

- **Run:** `run_id 20261109T230007`, items 35 (UI-GPU-AV19), 56 (UI-BAYER-AV19), 57 (UI-CORE-AV19) and 58 (UI-SUM). Items ran 2026-11-10 02:30-04:31 local time (UTC-5).
- **Machine:** Gerald (`machine` in every JSON). i7-14700K, RTX 3070 (driver 610.88), Intel UHD 770 present, Windows 11, Defender real-time protection ON.
- **P-cores only.** The runner pinned every item to the 8 P-cores. **Results are for 16 logical CPUs (P-cores), not all 28.**
  - The JSONs record `cpu_logical: 28` (`psutil.cpu_count()`), which ignores affinity.
  - Source for the pinning: `results/BENCH_QUEUE_2300.md`, "What the runner does", affinity row.
- **Library versions, as recorded in every tonight JSON:**
  - `av_version` 19.0.2, `ffmpeg_version` 9.0.2;
  - `library_versions`: libavcodec 63.1.102, libavformat 63.1.102, libavutil 61.1.102, libswscale 10.1.102;
  - numpy 2.2.6, python 3.12.13.
  - Each case ran in its own `uv run --script bench_intra.py` process (`bench_suite.py:106`, `--interp uv`).
- **Hardware target.** The target is a format that is hardware-encodable on RTX 3000+.
  - **In target:** the NVENC rows (group `gpu`, §4.1).
  - **Outside target:** the FFV1 and rawvideo rows (UI-BAYER-AV19, UI-CORE-AV19, §4.2). They are here for G4 only, as the **CPU fallback**, and are labelled so wherever quoted (`BENCH_QUEUE_2300.md`, "Notes for reading tonight's results").

Paths:
- `R/` = `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/`
- `S/` = `research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/`
- Tonight's result files are `R/bench/<config>__<source>_<res>__t<threads>__pyav19.0.2_q2300.json` (36 files).

`R/bench/BENCH.md` is the earlier report from 2026-11-09 11:30, made on a machine about 50% loaded. This file supersedes its numbers for the configs measured tonight. Every number below is from a file named next to it; anything else is marked **inferred** or **arithmetic**.

## 1. Load record

Source: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/items_load_2300.json` (runner lines of `results/BENCH_RUN_2300_LOG.jsonl`). Logs are in `results/bench_runner/logs/20261109T230007/{35,56,57,58}_*.{out,err}.txt`.

| # | id | start-end (local) | status / exit | duration vs est / timeout (min) | CPU before, mean / max % | top process before (CPU-s in 10 s) | MsMpEng CPU-s during item | Defender scan events | nvidia-smi before -> after | flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 35 | UI-GPU-AV19 | 02:30-02:35 | ok / 0 | 4.75 vs 6 / 15 | 3.87 / 8.2 | AsusFanControlService 1.59 | 13.14 | none | `0, 0, 0 %, 0 %, 0 %, 337 MiB` -> `... 363 MiB` | waited for the Defender avoid window until 02:30 (daily quick scan configured at 02:00) |
| 56 | UI-BAYER-AV19 | 04:19-04:28 | ok / 0 | 8.88 vs 8 / 20 | 4.27 / 9.4 | AsusFanControlService 1.56 | 17.92 | none | `... 367 MiB` -> `... 342 MiB` | none |
| 57 | UI-CORE-AV19 | 04:28-04:31 | ok / 0 | 3.45 vs 8 / 20 | 5.33 / 11.2 | Corsair.Service 1.67 | 9.22 | none | `... 342 MiB` -> `... 352 MiB` | none |
| 58 | UI-SUM | 04:31-04:31 | ok / 0 | 0.0 vs 0.5 / 3 | 3.89 / 7.3 | AsusFanControlService 1.53 | 0.2 | none | unchanged | none |

- **No item was load-flagged.** `load_over_15pct` is false for all four, and no Defender scan event was logged.
  - The only flag is UI-GPU's scheduled wait for the 01:55-02:30 Defender gap. It is a scheduling note, not a load flag.
  - The raw log's "leftover processes" notes were the monitoring session's shells, which the load record calls harmless.
- **Per-case machine CPU** (`system_cpu_percent_before` / `system_cpu_percent_during_encode`, whole machine over 28 logical CPUs, `bench_intra.py:132,172`):
  - before each case: 1.2-6.4%;
  - during single-thread and NVENC reps: 3.1-11.9%;
  - during the FFV1 all-threads reps: up to 37.3%. That is the bench's own threads.
- **NVENC was free.** nvidia-smi in every GPU JSON reads `0, 0 %` before and after (the `nvidia_smi_before/after` fields), so no other NVENC session ran.

## 2. Completeness

| item | expected (`bench_suite.py` cases + queue filters) | present | errors / skips |
|---|---|---|---|
| UI-GPU-AV19 | group `gpu` (`bench_suite.py:57-62`): 6 config/source pairs × 1080p + 720p, threads 1 = 12 | 12/12, each 3 reps × 300 frames, 20 warm-up frames discarded | stdout `[1/12]`-`[12/12]`, no `FAILED` and no `skip (exists)`; stderr empty |
| UI-BAYER-AV19 | group `bayer` filtered to sources bayer12, bayer8 and configs rawvideo.nut, ffv1_l3_s4_crc_g1.mkv, ffv1_l3_s24_crc_g1.mkv; threads 1 and 0 = 12 | 12/12, 3 × 300 | same; stderr empty |
| UI-CORE-AV19 | group `core_1080p` filtered to sources yuyv422, nv12 and the same 3 configs; threads 1 and 0 = 12 | 12/12, 3 × 300 | same; stderr empty |
| UI-SUM | regenerate `R/bench/bench_summary.md` | regenerated 04:31 | none |

- Every tonight case has `packets` = 300 and `decode_frames` = 300 in all 3 reps (`rep_results`).
- **`R/bench/bench_summary.md` mixes old and new rows.** It lists 183 timing rows:
  - 133 PyAV 18.0.0 rows (2026-11-09, loaded machine);
  - 14 older PyAV 19.0.2 rows (untagged files, `reps x frames` = 3x90, loaded machine);
  - **36 rows from tonight.**
- **How to tell tonight's rows apart:** they are the PyAV 19.0.2 rows with `reps x frames` = **3x300**. `bench_summary.py` has no tag column (`bench_summary.py:40-47`), so tonight's tagged files and the older untagged PyAV 19 files with the same names (rawvideo / FFV1 s4 / FFV1 s24 on YUY2 1080p) appear as adjacent rows told apart only by 3x300 vs 3x90.
- The summary header text "other agents were running" is hard-coded (`bench_summary.py:38-39`). It does not apply to tonight's rows.

## 3. Method (field meanings)

- **Input:** 8 real C930e 1080p YUY2 frames, or 8 C930e 720p JPEGs decoded to YUY2, **looped** to 300 frames (`looped: true`, `unique_frames: 8`).
- **Derived sources:** NV12, gray, P010 and Bayer are derived from those frames (`source_note`; `S/uintra_frames.py`). The >8-bit sources carry seeded noise in the low bits (FINDINGS §2.1).
- **Timing:** one discarded warm-up run, then 3 timed reps. Each rep encodes and muxes to a file on C:, then decodes that file (`bench_intra.py:139-189`). Values are **median (min-max) over the 3 reps** (`stats`, `:195-200`).
- **enc fps** = frames / encode wall time. **The encoder open is inside the timed region**, because PyAV opens on the first `encode()` (FINDINGS §2.7). `latency_max` therefore carries the open cost for NVENC: per-case medians 60.6-83.7 ms, single reps 59.5-87.1 ms, which is 3.6-22.7% of rep wall time (§6).
- **cores/stream** = process CPU seconds / (frames / 30) (`:168`). 1.0 = one core busy for a 30 fps stream. At t1 a value above 1 means the encoder cannot sustain 30 fps on one thread.
- **KB/frame** = encoded packet bytes / packets, in units of 1000 B, excluding container overhead (`:171`). **MB/s @30** = KB/frame × 30 / 1000 (**arithmetic**).
- **dec fps** = decode of the written file with libav's default decoder for the codec. That is **software** decode for h264/hevc, not NVDEC (`decoder` field). It uses the same thread setting as the encode.
- **prep ms** = untimed numpy/swscale re-layout to the encoder's pix_fmt (`:111-121`).
- **Threads:** t1 = `thread_count=1`. t0 = libav auto with `thread_type=AUTO` (`:146-148`). The thread count libav chose under the 16-CPU affinity is not recorded.
- **Lossless check:** the timed bench does **not** check exactness. The "exact?" column below cites the PyAV 19.0.2 functional files for the same config + source + path at 1080p:
  - `R/functional_matrix_pyav19.0.2.json`: 4 frames, fields `bit_exact_vs_source` / `psnr_plane0_min`;
  - `R/ffv1_recheck_pyav19.0.2.json`.
  - "not checked" means no PyAV 19 file covers that exact combination.

## 4. Results

### 4.1 In target: NVENC intra (group `gpu`, threads 1)

| config | source (src -> encoder pix_fmt, path) | res | enc fps | cores/stream | p99 latency ms | max latency ms | KB/frame | MB/s @30 | dec fps (SW) | prep ms | exact? (PyAV 19 functional) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| h264_nvenc_intra_lossless.mkv | nv12 (nv12 -> nv12, native) | 1080p | 516 (515-521) | 0.045 (0.045-0.055) | 1.98 (1.96-2.01) | 66.5 (62.1-68.8) | 593.6 | 17.8 | 103 (103-103) | 0.553 | yes (matrix) |
| h264_nvenc_intra_lossless.mkv | gray (gray -> yuv420p, Y + neutral chroma) | 1080p | 549 (542-551) | 0.050 (0.042-0.050) | 1.88 (1.85-1.90) | 66.7 (64.5-72.3) | 446.9 | 13.4 | 146 (146-147) | 0.226 | yes (matrix) |
| hevc_nvenc_intra_lossless.mkv | nv12 (nv12 -> nv12, native) | 1080p | 302 (298-303) | 0.048 (0.045-0.048) | 3.48 (3.47-3.71) | 77.0 (62.2-78.7) | 517.7 | 15.5 | 29 (29-29) | 0.556 | yes (matrix) |
| hevc_nvenc_intra_lossless.mkv | p010le (p010le -> p010le, native) | 1080p | 158 (158-159) | 0.084 (0.081-0.094) | 7.06 (6.97-7.16) | 76.1 (67.7-76.7) | 1,423.4 | 42.7 | 14 (14-14) | 0.991 | yes (matrix) |
| hevc_nvenc_intra_lossless.mkv | bayer8 (bayer_rggb8 -> yuv420p, mosaic as Y + neutral chroma) | 1080p | 186 (185-187) | 0.070 (0.066-0.072) | 5.95 (5.80-6.12) | 83.7 (65.2-87.1) | 1,369.7 | 41.1 | 19 (19-19) | 0.227 | yes (matrix, source `bayer_rggb8`) |
| hevc_nvenc_intra_cq.mp4 (lossy) | nv12 (nv12 -> nv12, native) | 1080p | 459 (459-463) | 0.034 (0.025-0.044) | 2.26 (2.25-2.29) | 62.7 (62.2-63.8) | 59.2 | 1.8 | 111 (110-112) | 0.534 | lossy: PSNR plane 0 min 51.02 dB (matrix) |
| h264_nvenc_intra_lossless.mkv | nv12 | 720p | 985 (983-1,061) | 0.023 (0.020-0.023) | 0.99 (0.94-1.03) | 63.9 (60.5-69.3) | 202.5 | 6.1 | 296 (295-297) | 0.29 | 1080p only checked |
| h264_nvenc_intra_lossless.mkv | gray | 720p | 1,027 (1,019-1,030) | 0.027 (0.023-0.027) | 0.96 (0.94-1.12) | 61.3 (59.5-61.8) | 173.4 | 5.2 | 353 (351-354) | 0.104 | 1080p only checked |
| hevc_nvenc_intra_lossless.mkv | nv12 | 720p | 660 (654-663) | 0.028 (0.023-0.030) | 1.62 (1.60-1.68) | 60.6 (60.6-60.6) | 213.1 | 6.4 | 73 (73-74) | 0.296 | 1080p only checked |
| hevc_nvenc_intra_lossless.mkv | p010le | 720p | 332 (332-334) | 0.047 (0.042-0.050) | 3.24 (3.22-3.33) | 73.9 (61.9-78.7) | 622.3 | 18.7 | 33 (33-33) | 0.466 | 1080p only checked |
| hevc_nvenc_intra_lossless.mkv | bayer8 | 720p | 381 (381-383) | 0.036 (0.033-0.037) | 3.21 (3.10-3.21) | 66.1 (62.6-69.3) | 559.5 | 16.8 | 53 (53-53) | 0.103 | 1080p only checked |
| hevc_nvenc_intra_cq.mp4 (lossy) | nv12 | 720p | 878 (861-935) | 0.017 (0.009-0.022) | 1.13 (1.09-1.14) | 62.5 (59.8-62.7) | 20.9 | 0.6 | 281 (279-282) | 0.292 | lossy |

KB/frame was identical in all 3 reps for every NVENC case (`stats.bytes_per_frame` min = max).

### 4.2 Outside target (G4 CPU fallback only): FFV1 v3 and rawvideo, 1080p

| config | source (src -> encoder pix_fmt, path) | threads | enc fps | cores/stream | p99 latency ms | max latency ms | KB/frame | MB/s @30 | dec fps | prep ms | exact? (PyAV 19 functional) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| rawvideo.nut | yuyv422 (native) | 1 | 385 (382-388) | 0.077 (0.077-0.077) | 3.09 (3.04-3.26) | 4.1 (3.5-4.3) | 4,147.2 | 124.4 | 806 (790-814) | 0.651 | yes (matrix) |
| rawvideo.nut | yuyv422 | 0 | 500 (500-503) | 0.084 (0.078-0.092) | 2.44 (2.38-2.54) | 3.7 (2.8-4.2) | 4,147.2 | 124.4 | 825 (795-825) | 0.643 | yes |
| ffv1_l3_s4_crc_g1.mkv | yuyv422 (-> yuv422p, numpy deinterleave) | 1 | 45 (45-45) | 0.664 (0.664-0.667) | 24.05 (23.95-25.16) | 37.0 (36.5-37.1) | 468.8 | 14.1 | 41 (41-41) | 1.49 | yes (matrix) |
| ffv1_l3_s4_crc_g1.mkv | yuyv422 | 0 | 150 (149-151) | 0.672 (0.658-0.686) | 7.59 (7.49-7.59) | 22.9 (22.3-23.6) | 468.8 | 14.1 | 475 (474-477) | 1.489 | yes |
| ffv1_l3_s24_crc_g1.mkv | yuyv422 (-> yuv422p) | 1 | 44 (44-44) | 0.673 (0.673-0.678) | 23.77 (23.70-23.95) | 37.5 (37.5-37.7) | 470.3 | 14.1 | 41 (41-41) | 1.432 | yes (`ffv1_recheck` `camera_size`, 8 frames) |
| ffv1_l3_s24_crc_g1.mkv | yuyv422 | 0 | 241 (234-244) | 0.880 (0.850-0.912) | 4.68 (4.62-4.70) | 20.8 (20.8-21.4) | 470.3 | 14.1 | 467 (466-468) | 1.415 | yes |
| rawvideo.nut | nv12 (native) | 1 | 510 (506-514) | 0.059 (0.058-0.059) | 2.44 (2.31-2.56) | 3.6 (2.8-3.8) | 3,110.4 | 93.3 | 1,069 (1,068-1,134) | 0.562 | yes (matrix) |
| rawvideo.nut | nv12 | 0 | 642 (640-653) | 0.058 (0.058-0.067) | 1.93 (1.86-1.94) | 3.2 (1.9-3.5) | 3,110.4 | 93.3 | 1,068 (1,067-1,072) | 0.556 | yes |
| ffv1_l3_s4_crc_g1.mkv | nv12 (-> yuv420p) | 1 | 59 (58-59) | 0.506 (0.506-0.512) | 18.15 (18.05-18.48) | 27.9 (27.7-27.9) | 381.3 | 11.4 | 52 (52-52) | 0.338 | yes (matrix) |
| ffv1_l3_s4_crc_g1.mkv | nv12 | 0 | 195 (194-196) | 0.519 (0.508-0.519) | 5.84 (5.80-5.99) | 17.6 (17.0-17.6) | 381.3 | 11.4 | 593 (583-599) | 0.358 | yes |
| ffv1_l3_s24_crc_g1.mkv | nv12 (-> yuv420p) | 1 | 57 (56-57) | 0.523 (0.520-0.523) | 19.00 (18.84-19.63) | 30.0 (29.6-30.3) | 382.8 | 11.5 | 52 (51-52) | 0.347 | not checked |
| ffv1_l3_s24_crc_g1.mkv | nv12 | 0 | 323 (304-326) | 0.709 (0.597-0.723) | 3.53 (3.52-3.69) | 15.9 (15.8-17.1) | 382.8 | 11.5 | 582 (574-587) | 0.339 | not checked |
| rawvideo.nut | bayer8 (bayer_rggb8, native) | 1 | 779 (767-784) | 0.037 (0.036-0.039) | 1.67 (1.66-1.75) | 2.2 (1.9-3.0) | 2,073.6 | 62.2 | 1,578 (1,571-1,595) | 0.302 | yes (matrix) |
| rawvideo.nut | bayer8 | 0 | 974 (964-985) | 0.042 (0.042-0.044) | 1.31 (1.28-1.35) | 2.1 (1.4-3.4) | 2,073.6 | 62.2 | 1,572 (1,432-1,572) | 0.296 | yes |
| ffv1_l3_s4_crc_g1.mkv | bayer8 (re-tag as gray) | 1 | 55 (55-55) | 0.539 (0.534-0.541) | 19.54 (19.34-19.97) | 26.1 (25.7-26.1) | 1,087.3 | 32.6 | 42 (42-43) | 0.316 | yes (matrix) |
| ffv1_l3_s4_crc_g1.mkv | bayer8 | 0 | 176 (176-177) | 0.539 (0.522-0.541) | 6.52 (6.10-7.35) | 14.8 (14.6-16.1) | 1,087.3 | 32.6 | 491 (488-503) | 0.313 | yes |
| ffv1_l3_s24_crc_g1.mkv | bayer8 (re-tag as gray) | 1 | 56 (56-56) | 0.533 (0.533-0.536) | 19.08 (18.97-19.50) | 25.8 (25.6-27.1) | 990.4 | 29.7 | 42 (42-43) | 0.318 | not checked |
| ffv1_l3_s24_crc_g1.mkv | bayer8 | 0 | 308 (301-310) | 0.719 (0.692-0.727) | 3.77 (3.76-3.90) | 12.9 (12.7-13.6) | 990.4 | 29.7 | 489 (484-491) | 0.311 | not checked |
| rawvideo.nut | bayer12 (bayer_rggb16le, native) | 1 | 391 (387-391) | 0.075 (0.075-0.075) | 3.03 (2.97-3.12) | 4.3 (3.8-4.5) | 4,147.2 | 124.4 | 819 (792-826) | 0.647 | yes (matrix) |
| rawvideo.nut | bayer12 | 0 | 492 (482-498) | 0.086 (0.073-0.089) | 2.78 (2.43-3.08) | 3.2 (3.0-3.6) | 4,147.2 | 124.4 | 788 (787-797) | 0.676 | yes |
| ffv1_l3_s4_crc_g1.mkv | bayer12 (re-tag as gray16le; range coder forced) | 1 | 11 (11-11) | 2.633 (2.631-2.638) | 90.70 (90.48-91.13) | 101.8 (101.7-102.2) | 2,413.3 | 72.4 | 9 (9-9) | 0.642 | yes (matrix, source `bayer_rggb16le`) |
| ffv1_l3_s4_crc_g1.mkv | bayer12 | 0 | 41 (41-41) | 2.638 (2.636-2.642) | 25.59 (25.55-27.68) | 39.1 (38.5-41.3) | 2,413.3 | 72.4 | 106 (106-106) | 0.665 | yes |
| ffv1_l3_s24_crc_g1.mkv | bayer12 (re-tag as gray16le; range coder forced) | 1 | 12 (11-12) | 2.587 (2.584-2.602) | 88.32 (88.10-89.47) | 100.7 (100.0-101.2) | 2,349.0 | 70.5 | 9 (9-9) | 0.649 | yes (`ffv1_recheck` `coder_and_noise`, level 3 gray16le, 1 frame) |
| ffv1_l3_s24_crc_g1.mkv | bayer12 | 0 | 83 (83-83) | 3.358 (3.270-3.383) | 13.24 (13.23-14.31) | 26.5 (26.2-26.7) | 2,349.0 | 70.5 | 106 (105-106) | 0.646 | yes |

- The "range coder forced" note comes from FINDINGS §2.6 (`ffv1_recheck_pyav19.0.2.json`): FFV1 v3 above 8 bits gives identical bytes for rice and range.
- Bayer8 and Bayer12 here are the mosaic layout. The quad split was not in tonight's queue.

### 4.3 Tonight vs the earlier loaded run (same configs, 1080p)

Sizes match the earlier files to the KB. Examples: h264 NV12 594, hevc NV12 518, P010 1423, Bayer8 1370, FFV1 s24 Bayer12 2349 (`R/bench/bench_summary.md`, PyAV 18.0.0 rows). This is a consistency check on the inputs.

Encode fps, earlier PyAV 18.0.0 loaded row -> tonight (`bench_summary.md`):
- h264_nvenc NV12: 428 -> 516;
- h264_nvenc gray: 472 -> 549;
- hevc_nvenc NV12: 292 -> 302;
- hevc_nvenc P010: 155 -> 158;
- hevc CQ: 431 -> 459;
- hevc Bayer8: 183 -> 186;
- FFV1 s24 YUY2 t1: 42 -> 44;
- FFV1 s24 Bayer12 t1: 10 -> 12.

**Inferred:** the speed-ups mix load removal with the PyAV 18 -> 19 change. Tonight's rows are the clean numbers. This comparison does not isolate a version effect.

## 5. Headline numbers

1. **In target. h264_nvenc lossless NV12 1080p:** 516 fps (515-521) at 0.045 cores per 30 fps stream, 593.6 KB/frame = 17.8 MB/s at 30 fps (**arithmetic**). Software decode reaches 103 fps. At 720p: 985 fps, 202.5 KB/frame. Source: `research/skellycam_recording/recording_upgrade/results/uncompressed_intra/bench/h264_nvenc_intra_lossless.mkv__nv12_1080p__t1__pyav19.0.2_q2300.json` (and `..._720p_...`).
2. **In target. hevc_nvenc lossless NV12 1080p:** 302 fps, 517.7 KB/frame. **Software decode only 29 fps.** P010 1080p: 158 fps, 1,423.4 KB/frame (42.7 MB/s), software decode 14 fps. Sources: `.../hevc_nvenc_intra_lossless.mkv__nv12_1080p__t1__pyav19.0.2_q2300.json`, `.../hevc_nvenc_intra_lossless.mkv__p010le_1080p__t1__pyav19.0.2_q2300.json`.
3. **In target. 8-bit Bayer through hevc_nvenc lossless** (mosaic as Y, exact in the PyAV 19 matrix), 1080p: 186 fps, 1,369.7 KB/frame, software decode 19 fps. For comparison, outside target: rawvideo 2,073.6 KB and FFV1 v3 s24 990.4 KB. Source: `.../hevc_nvenc_intra_lossless.mkv__bayer8_1080p__t1__pyav19.0.2_q2300.json`.
4. **In target. Host CPU across all 12 NVENC cases:** 0.017-0.084 cores per 30 fps stream. The slowest call per case, inferred to be the encoder open and inside the timed region, has `latency_max` medians of 60.6-83.7 ms. Source: the 12 `*nvenc*__pyav19.0.2_q2300.json` files.
5. **Outside target (CPU fallback).** FFV1 v3 on camera YUY2 1080p:
   - t1: 44-45 fps at 0.66-0.67 cores/stream;
   - t0: 150 fps (s4) and 241 fps (s24);
   - 468.8-470.3 KB/frame (14.1 MB/s).
   - Sources: `.../ffv1_l3_s4_crc_g1.mkv__yuyv422_1080p__t{1,0}__pyav19.0.2_q2300.json`, `.../ffv1_l3_s24_crc_g1.mkv__yuyv422_1080p__t{1,0}__pyav19.0.2_q2300.json`.
6. **Outside target. 12-bit Bayer in FFV1 v3 cannot hold 30 fps on one thread:**
   - t1: 11-12 fps at 2.59-2.63 cores/stream;
   - all threads: s24 reaches 83 fps at 3.36 cores/stream, s4 only 41 fps;
   - decode at t1: 9 fps.
   - Sources: `.../ffv1_l3_s24_crc_g1.mkv__bayer12_1080p__t{1,0}__pyav19.0.2_q2300.json`, `.../ffv1_l3_s4_crc_g1.mkv__bayer12_1080p__t{1,0}__pyav19.0.2_q2300.json`.
7. **Outside target. rawvideo 1080p** writes 385-974 fps at 0.037-0.086 cores/stream. It costs 62.2 MB/s (Bayer8), 93.3 MB/s (NV12) or 124.4 MB/s (YUY2, Bayer12) at 30 fps (**arithmetic**). Sources: `.../rawvideo.nut__*__pyav19.0.2_q2300.json`.

## 6. Caveats

- **P-cores only** (16 logical CPUs). The t0 rows depend on how many threads libav auto-selected, which is not recorded. `cpu_logical` 28 in the JSON is the machine total, not the affinity.
- **The lossless check is not part of this bench.** Exactness comes from separate PyAV 19.0.2 functional files with 4 or 8 frames at 1080p (1 frame for the FFV1 s24 gray16le check).
  - FFV1 s24 on NV12 and Bayer8 has no PyAV 19 exactness file.
  - **Inferred:** it is the same lossless FFV1 v3 encoder with a different slice count, so it is very likely exact. This is NOT VERIFIED.
  - The 720p NVENC rows were not checked.
- **"dec fps" is libav software decode** (h264, hevc). It is not NVDEC and not Chromium playback. The hevc lossless decode of 14-29 fps at 1080p is a CPU decoder figure.
- **The encoder open is in the timed region.** The slowest call per rep (`latency_max`, **inferred** to be the first call, which opens the encoder) takes 3.6-22.7% of the rep's `encode_wall_s` (**arithmetic** over `rep_results`).
  - The share is largest at 720p (13-23% for h264 and hevc NV12) and smallest for hevc P010 1080p (3.6-4.0%).
  - So the 720p NVENC fps understate steady-state throughput the most. A longer run, or timing after the first packet, would give the steady-state rate.
- **Inputs are 8 frames looped, from one camera (C930e).** Every other source is derived, and 720p is JPEG-derived. Sizes are content-dependent: FINDINGS §2.1 shows +58% for C922 YUY2 on FFV1. 12-bit sizes are inflated by synthetic noise.
- **Warm caches:** 8 unique frames, and decode reads the file just written. **Inferred:** rawvideo encode and all decode figures measure memory and page cache, not disk throughput.
- **`system_cpu_percent_*` is whole-machine CPU over 28 logical CPUs** (psutil). It includes the bench itself.
- **UI-BAYER-AV19 and UI-CORE-AV19 are outside the hardware target.** Quote them only as the G4 CPU fallback.
- **`bench_summary.md` cannot tell tonight's rows from older rows except by `reps x frames` = 3x300 with PyAV 19.0.2.** Do not quote the 3x90 PyAV 19.0.2 rows or the PyAV 18.0.0 rows as quiet-machine numbers.
