# Bench run 2300: summary (2026-11-09 23:00 to 2026-11-10 06:13)

The timed queue from `BENCH_QUEUE_2300.md` (HANDOFF.md section 5), run to the end as Dom asked. Paths are relative to `research/skellycam_recording/recording_upgrade/results/`. Each topic's `BENCH.md` holds the full tables, per-item load record and caveats; this file is the overview.

## 1. What ran

| run | id | items | start | end | minutes |
|---|---|---|---|---|---|
| main queue | `20261109T230007` | all 68 of `bench_queue_2300.json` | 23:00:07 | 05:36:29 | 396.4 |
| OV-COST re-run | `20261110T053653` | OV-COST only | 05:36:53 | 06:13:14 | 36.4 |

- Command: `uv run --script research/skellycam_recording/recording_upgrade/scripts/bench_runner/run_queue.py --deadline 10:00`, started from the repo root.
- **Result: 67 of 68 items ok (exit 0); 1 timeout (OV-COST), which then completed in the re-run. No item skipped.**
- Log: one line per item in `BENCH_RUN_2300_LOG.jsonl`. Stdout and stderr are in `bench_runner/logs/20261109T230007/` and `bench_runner/logs/20261110T053653/`.
- The queue's estimate was 477.8 min; the actual time was 396.4 min, including the 01:55–02:30 Defender wait. Most items ran under their estimates. Exceptions, all complete:
  - the hevc_qsv scaling items 7, 34, 44 and 52 ran 1.6–2.1× their estimates, because hevc_qsv tops out at about 66 fps in total at 1080p;
  - OV-COST took 36 min against its 12-minute estimate.
- **The OV-COST re-run** used a one-item copy of the queue with the timeout raised from 30 to 60 min. The copy is in the session scratchpad (`queue_ovcost_rerun.json`). `bench_queue_2300.json` and `make_queue.py` were not changed.
  - **To do:** raise OV-COST's estimate and timeout in `make_queue.py` (about 36 and 60 min) before any future queue is built.

## 2. Machine state and load record

| item | value | source |
|---|---|---|
| Machine | GERALD, i7-14700K, 28 logical CPUs; items pinned to the P-cores (CPUs 0–15) | start record in `BENCH_RUN_2300_LOG.jsonl` |
| iGPU | Intel UHD 770 OK / Present True at the start; no QSV item was skipped | same |
| Power plan | Balanced; display kept on by the runner | same |
| GPU drivers | NVIDIA 610.88 (RTX 3070); Intel 32.0.101.7088 | `nvidia-smi` and `Win32_VideoController`, read 2026-11-10 06:29, after the run (the runner does not record them) |
| Python / uv | 3.12.13 / uv 0.11.8; benches use PyAV 19.0.2 via PEP 723 pins | start record; each bench's JSON `env` |
| Free disk C: | 810.6 GB at the start | start record |
| Pre-run check (22:59) | UHD 770 present; this Claude session the only one; Parsec, Electron and run_suite.py closed; total CPU 3.6% averaged over 10 s; Task Manager open | this session's pre-run check |

- **Background load before each item:** total CPU over 10 s averaged 2.98–6.81% (max sample 10.3%). **No item was flagged `load_over_15pct`.**
- **Defender scans:** no scan event during any item or in the run as a whole (`defender_scan_events_during_run: ""`). The runner waited out 01:55–02:30 before item 35, as planned.
- **Defender real-time scanning (MsMpEng CPU) was large during the write-heavy items.** Real-time protection was on and was not changed. It is part of the real cost on a default Windows install.
  - CPU-seconds per item: WT-LONG-AV19 649.9, WT-USABILITY-18K 193.4, WT-MODELS16-AV19 189.3, WT-CORE-AV19 116.2, WT-FOCUS16-AV19 114.3, OV-COST 125.1 (timed-out attempt) and 79.4 (re-run).
  - write_throughput/BENCH.md breaks this down per writer: folder-of-files is the one that triggers it.
- **The leftover-process flag on every item is harmless.** It listed only this Claude session's own monitoring shells, whose command lines contain the study path. No bench process was left behind. The final check after both runs found no leftover study processes, so nothing was killed.
- **Item 34's stderr** holds only nvImageCodec warnings that the optional nvJPEG2000 and nvTIFF plugins are missing. They are not used.

## 3. Flags, deviations and anomalies to carry into the post-bench verify

1. **OV-COST timed out at 1800 s** after 7 of its 8 size × case blocks, writing no JSON. The re-run (section 1) completed 246/246 records: `overlays/bench/bench_overlay_cost_20261110T103707Z.json`.
2. **Items 1–3 are not all P-core-only.** In every single-stream JSON, `process_cpu_affinity` is CPUs 0–15 in `system_before` and 0–27 in `system_after`.
   - The libx265 rows show 23–27 CPU cores in use.
   - Which cells after the affinity change also ran on all 28 CPUs can't be told from the files.
   - That libx265 widened the affinity is inferred, not tested.
   - The scaling items kept 0–15 throughout.
   - Source: `intra_compare/bench/matched_stream_{A_1080p,A_720p,B_1080p}_*.json`.
3. **NVENC opens at most 12 sessions.** Every N=16 NVENC cell opened 12 encoders; the 13th `avcodec_open2` fails with ExternalError, and the limit probes stop at 12/32. Read the N=16 NVENC rows as 12 streams. QSV h264 opened 32/32. (intra_compare/BENCH.md)
4. **nvJPEG fed decoded camera MJPEG misses the matched quality target** in items 1 and 3 (SSIM-Y 0.9954; PSNR-Y 43.14 dB at B). In item 2 it hits SSIM-Y but is 3.8 dB under its matched PSNR-Y. This is consistent with the swscale-RGB loss noted in the queue. (intra_compare/BENCH.md)
5. **WebCodecs scrub (intra_playback) is not reliable as a capacity number.**
   - 914 per-stream errors in 5 E35 configs do not appear in `_index.json` or `bench_tables.md` (`run_suite.py:358`, `summarize.py:181-186`).
   - The GPU process's private memory grew to 9–38 GB in all 16 WebCodecs scrub configs, and the GPU process was replaced in 3 E35 N=8 configs.
6. **N=8 `<video>` sync:** in 19 of 20 configs one or two tiles stall (under 65% of the median stream's rVFC callbacks), pushing max spread to 100–245 frames. Master-clock sync had spread 0 in all 28 configs. (intra_playback/BENCH.md)
7. **Write latencies tonight are higher than in the contaminated daytime run** for folder-of-files and append at 16 × 1080p60 (2.11 vs 1.30 ms and 0.55 vs 0.18 ms). The old BENCH.md is therefore not a lower bound in every column. P-core pinning is a possible cause (inferred). The old file was kept as `write_throughput/BENCH_20261109_contaminated.md`.
8. **Fast items checked and found complete** (the estimates were just generous):
   - JP-MUX, CR-FSYNC, CR-FRAG-MJPEG, JP-OPEN-LONG, WT-FIRST-READ, WT-USABILITY-18K, PI-NVJPEG-DECODE, IP-SEEK (200/200 seeks per config), and IC-SCALE-jpeg_turbo_420-thread.
   - **CR-FRAG-INTRA** is complete as the script defines it: it encodes 300 frames once, untimed, and loops the packets to 3000 for the timed remux (`bench_fragment_overhead.py:63,85-88`). Its JSON records no keyframe flags; that the payloads are all-intra rests on the smoke check.
9. **No lossless check inside the timed uncompressed_intra bench.** Exactness is cited from the functional files. FFV1 s24 on NV12 and Bayer8, and the 720p NVENC rows, have no PyAV 19 exactness file. Encoder open is inside the timed window: it is 3.6–22.7% of NVENC wall time. (uncompressed_intra/BENCH.md)
10. **Overlays:** canvas-over-video captures now show the overlay 1–3 frames behind; the earlier run found 1. The E45 drop counter reports 19–20/300 frames dropped on CFR files, while presentedFrames shows 0 gaps. (overlays/BENCH.md)
11. **Coarse CPU timers:** mux and fragment CPU figures are multiples of 15.625 ms, so differences under about 5 µs/frame are not resolved; those documents compare on wall time. Process-worker CPU in items 10 and 55 is a lower bound (3 negative readings).
12. **Single runs:** the core write matrix, the long cells, each intra_playback config, the recwriter A/B phases and the decode benches ran once. Their medians and min–max are within a run, not across repeats.

## 4. Headline numbers

These are pointers; the labelled tables and caveats are in each topic's BENCH.md. All results are measured, P-core only (except flag 2), on this run.

**Matched-quality intra encode (intra_compare)**

| number | file |
|---|---|
| Target A, 1080p from NV12, size against libjpeg-turbo 4:2:2: hevc_qsv 0.41, hevc_nvenc 0.47, h264_nvenc 0.55, h264_qsv 0.59; single-stream speed 65 / 390 / 540 / 585 fps | `intra_compare/bench/matched_stream_A_1080p_20261110T042204Z.json` |
| h264_nvenc 1080p30, 12 streams paced: all keep up at 0.61 cores; 542 fps total unpaced | `intra_compare/bench/matched_concurrent_h264_nvenc_420_1080p_nv12_thread_20261110T044648Z.json` |
| h264_qsv 1080p30, 16 streams paced: all keep up at 1.25 cores; 679 fps total unpaced; 32/32 sessions open | `intra_compare/bench/matched_concurrent_h264_qsv_420_1080p_nv12_thread_20261110T045738Z.json` |
| hevc_qsv 1080p: 66–67 fps total at every N, so only 1 stream keeps up at 30 fps | `intra_compare/bench/matched_concurrent_hevc_qsv_420_1080p_nv12_thread_20261110T051629Z.json` |
| libjpeg-turbo 4:2:0 1080p, 16 streams: 3,511 fps as threads, 3,572 fps as processes | `intra_compare/bench/matched_concurrent_jpeg_turbo_420_1080p_nv12_{thread_20261110T053447Z,process_20261110T053417Z}.json` |
| nvJPEG 1080p from NV12: 8 streams keep up, 16 do not (475 fps total) | `intra_compare/bench/matched_concurrent_nvjpeg_420_1080p_nv12_thread_20261110T052842Z.json` |
| mjpeg_qsv 4:2:2 from YUY2, 16 streams: all keep up at 0.92 cores | `intra_compare/bench/matched_concurrent_mjpeg_qsv_422_1080p_yuy2_thread_20261110T064127Z.json` |
| Camera MJPEG CPU decode → h264_nvenc, 12 streams: all keep up, but at 4.06 cores | `intra_compare/bench/matched_concurrent_h264_nvenc_420_1080p_mjpeg_cpu_thread_20261110T081938Z.json` |

**Playback in Electron (intra_playback; clips at 54.5–55.0 dB Y-PSNR, not target A or B)**

| number | file |
|---|---|
| Every seek frame-exact: 200/200 in all 24 configs (E35 and E45, H.264/HEVC NVENC+QSV, JPEG paths) | `intra_playback/bench/*/bench_intra_seek/*.json` |
| Seek p50: WebCodecs 2.7–2.9 ms (E45) and 3.1–3.4 ms (E35); JPEG ImageDecoder 4.6 ms, createImageBitmap 6.0 ms (E45); `<video>` to rVFC 8.5–14.1 ms | same folder |
| Master-clock sync at N=8, E45: WebCodecs 0.55 cores / 872 MB; JPEG createImageBitmap 2.14 cores / 1396 MB; JPEG ImageDecoder 1.44 cores / 987 MB; spread 0 | `intra_playback/bench/e45/bench_intra_sync/*__n8.json` |

**Passthrough, durability and writing (jpeg_passthrough, crash_resilience, write_throughput, python_integration)**

| number | file |
|---|---|
| Mux cost at 720p: containers 16.1–20.8 µs/frame wall; raw + sidecar 20.0; folder of JPEGs 217.9 | `jpeg_passthrough/bench/bench_mux_default_pyav19_20261110T055215Z.json` |
| Opening a 54,000-frame (30 min) file: per-frame-fragment fMP4 1107 ms (cv2) / 1224 ms (PyAV); 1 s-fragment fMP4 42.6 ms; finalized MP4 2.4 ms; cv2 counts MKV as 53,819 of 54,000 | `jpeg_passthrough/bench/open_long.json` |
| Lossless JPEG rotation: 2.0–2.2 ms/frame at 720p, 6.8–8.9 ms at 1080p | `jpeg_passthrough/bench/bench_rotate_20261110T093546Z.json` |
| Flush per frame p50 16.3 µs; fsync per frame p50 409 µs, p99 669 µs, max 8.7 ms, 127 MB/s | `crash_resilience/bench/fsync_pyav19.json` |
| MKV `flush_packets=1` adds 4.9 µs/frame (MJPEG), 2.7 (H.264 intra), 3.0 (HEVC intra); overhead MKV 45.8 B/frame, per-frame fMP4 131.3, 1 s fMP4 12.5 | `crash_resilience/bench/fragment_overhead_{mjpeg,intra}_pyav19.json` |
| Repair of a killed 1 GB MKV+fp: 0.907 s/GB (PyAV remux) or 0.965 s/GB (resumable repair), 17,617 of 17,618 frames recovered; plain MP4 recovers 0 | `crash_resilience/bench/repair_pyav19.json` |
| 0 frames dropped in all 77 write cells, including three 10-min 16 × 1080p60 cells of 576,000 frames each | `write_throughput/bench/long_av19/*.json` |
| 16 × 1080p60 write median: files 2.111 ms, append 0.553, mkv_flush 0.808, fmp4_frame_flush 0.853; p99.9 files 20.3 ms vs 1.7 / 2.9 / 3.2 | `write_throughput/bench/focus16_av19/` |
| Defender CPU per 30 s cell: files 26.8 s vs 1.2–1.5 s (idle level) for the other writers; first read of 5000 new .jpg files 20.59 s, all of it Defender CPU | `write_throughput/bench/focus16_av19/`, `write_throughput/bench/usability/first_read_check_5000.json` |
| RecordingWriter MKV `write()` median 0.033 ms (720p) / 0.112 ms (1080p) vs 0.223 / 0.274 ms for a folder; 10-min fMP4 opens in 372 ms (cv2) vs 3.7 ms for MKV | `python_integration/bench/recwriter_quiet1_pyav19.json` |
| Live-view decode of a C922 1080p JPEG: cv2 5.29 ms, simplejpeg 3.34 ms; nvJPEG 1.92–2.27 ms on the GPU, 3.37–3.64 ms including the copy to host | `python_integration/bench/{jpeg_decode_quiet1_pyav19,nvjpeg_decode_quiet1_2300}.json` |

**G4 and G3 (uncompressed_intra, overlays)**

| number | file |
|---|---|
| h264_nvenc lossless NV12 1080p: 516 fps, 0.045 cores, 593.6 KB/frame; hevc_nvenc lossless 302 fps, but software decode only 29 fps | `uncompressed_intra/bench/{h264,hevc}_nvenc_intra_lossless.mkv__nv12_1080p__t1__pyav19.0.2_q2300.json` |
| Outside the hardware target (G4 CPU fallback): FFV1 Bayer12 single-thread 11–12 fps at 2.6 cores per stream | `uncompressed_intra/bench/ffv1_l3_s{4,24}_crc_g1.mkv__bayer12_1080p__t1__pyav19.0.2_q2300.json` |
| Binary overlay sidecar for the full overlay: 29.3 µs/frame, 354.55 MB/h; cv2 burn-in of ChArUco 16.5 ms/frame | `overlays/bench/bench_overlay_cost_20261110T103707Z.json` |
| Electron canvas draw with placed labels: 1.1 ms (E35), 0.9 ms (E45); SVG DOM 18 ms | `overlays/bench/electron_drawbench_{35.7.5,45.2.3}.json` |

## 5. Files written after the run

- `intra_compare/BENCH.md`, `intra_playback/BENCH.md`, `jpeg_passthrough/BENCH.md`, `crash_resilience/BENCH.md`, `python_integration/BENCH.md`, `uncompressed_intra/BENCH.md`, `overlays/BENCH.md` (all new).
- `write_throughput/BENCH.md` (new); the contaminated predecessor was moved to `write_throughput/BENCH_20261109_contaminated.md`.
- Regenerated by the benches themselves: `intra_playback/bench/bench_tables.md`, `write_throughput/bench/bench_summary.md`, `uncompressed_intra/bench/bench_summary.md`. The two summary files mix PyAV 18 and older PyAV 19 rows with tonight's; the BENCH.md files say which rows are tonight's.
- Nothing was committed.

## 6. Next (HANDOFF.md section 6, from step 2)

- Update each topic's FINDINGS with these numbers, then verify (provenance and method) and revise. Include the intra_compare and intra_playback drafts and the section 3 flags above.
- **Quality target decided** (Dom, 2026-11-10): target A is the primary operating point. The reasoning is in HANDOFF section 1.1. The machine-vision (YOLO/RTMW) test is not to be run; Dom judged the existing evidence sufficient.
