# python_integration: timed bench results (23:00 run, 2026-11-09/10)

- **Run:** `run_id 20261109T230007` (queue `results/bench_queue_2300.json`), items 24, 39 and 40. Items ran 2026-11-10 01:01-03:16 local time (UTC-5).
- **Machine:** Gerald. i7-14700K, RTX 3070 (driver 610.88), Intel UHD 770 present, Windows 11 (`Windows-11-10.0.26300-SP0` in every JSON `env.platform`), Defender real-time protection ON.
- **P-cores only.** The runner pinned every item to the 8 P-cores. **Results are for 16 logical CPUs (P-cores), not all 28.**
  - The JSONs still record `cpu_count: 28` (`os.cpu_count()`), which ignores affinity.
  - Source for the pinning: `results/BENCH_QUEUE_2300.md`, "What the runner does", affinity row.
- **Library versions, as recorded in the JSON `env` blocks:**
  - `recwriter_quiet1_pyav19.json`: python 3.12.13, av 19.0.2, opencv 4.12.0.
  - `jpeg_decode_quiet1_pyav19.json`: python 3.12.13, numpy 2.2.6, opencv 4.12.0 (`cv2_num_threads` 1), simplejpeg 1.9.0, PyTurboJPEG 2.6.1, av 19.0.2.
    - `turbojpeg_dll` = `<SP>/jpeg_passthrough/ljt321/bin/turbojpeg.dll`. This is **libjpeg-turbo 3.2.1**, not the 3.2.0 named in the script docstring (`BENCH_QUEUE_2300.md`, "Notes for reading tonight's results"). The JSON records the path only, not the version.
  - `nvjpeg_decode_quiet1_2300.json`: python 3.12.13, **nvImageCodec 0.9.0.20** (`env.nvimgcodec`). The intra_compare benches use 0.10.0.9.
    - nvidia-smi before: `NVIDIA GeForce RTX 3070, 610.88, 0, 0 %, 0 %, 479 MiB`.
    - nvidia-smi after: `NVIDIA GeForce RTX 3070, 610.88, 0, 41 %, 0 %, 967 MiB`. The fields are name, driver, encoder sessions, GPU utilisation, decoder utilisation and memory used (`bench_nvjpeg_decode.py:41-42`).
  - FFmpeg is not recorded in these JSONs. PyAV 19.0.2 bundles FFmpeg 9.0.2 (from `av.ffmpeg_version_info` in the uncompressed_intra JSONs of the same run).

Paths:
- `R/` = `research/skellycam_recording/recording_upgrade/results/python_integration/`
- `S/` = `research/skellycam_recording/recording_upgrade/scripts/python_integration/`
- `<SP>` = `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/93366190-c2b0-4501-a85e-83654db13698/scratchpad`

Every number below comes from a file named next to it. Anything I worked out is marked **inferred**, or **arithmetic** where it is plain arithmetic on file values.

## 1. Load record

Source: `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/items_load_2300.json`, which carries the runner's `results/BENCH_RUN_2300_LOG.jsonl` lines. Per-item stdout/stderr are in `results/bench_runner/logs/20261109T230007/`.

| # | id | start-end (local) | status / exit | duration vs est / timeout (min) | CPU before, mean / max % | top process before (CPU-s in 10 s) | MsMpEng CPU-s during item | Defender scan events | nvidia-smi before -> after | flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 24 | PI-RECWRITER-AV19 | 01:01-01:03 | ok / 0 | 2.24 vs 12 / 30 | 3.37 / 9.4 | AsusFanControlService 1.56 | 12.31 | none | `0, 0, 0 %, 0 %, 0 %, 713 MiB` -> `... 695 MiB` | none |
| 39 | PI-JPEG-DECODE-PYAV19 | 03:06-03:16 | ok / 0 | 9.21 vs 12 / 30 | 3.75 / 6.2 | Corsair.Service 1.67 | 16.62 | none | `... 373 MiB` -> `... 342 MiB` | none |
| 40 | PI-NVJPEG-DECODE | 03:16-03:16 | ok / 0 | 0.19 vs 5 / 15 | 3.21 / 4.8 | Corsair.Service 1.73 | 0.78 | none | `0, 0, 0 %, 0 %, 0 %, 342 MiB` -> `0, 0, 41 %, 0 %, 0 %, 342 MiB` | none |

- **No item was load-flagged.**
  - `load_over_15pct` is false for all three. CPU before stayed at 3.2-3.8% mean and 9.4% max.
  - `defender_scan_events_during_item` is empty for all three.
  - The flag lists are empty.
- The raw runner log had a "leftover processes" note on some items. The load record says these lists held only the monitoring Claude session's shells, with no bench process, so they are harmless.
- MsMpEng used 12.31 CPU-s during PI-RECWRITER's 2.24 min, about 0.09 of a core on average (**arithmetic**). That item writes a folder-of-JPEGs baseline of 3000 files per case. **Inferred:** Defender scanning those new files is the likely cause. This is not established.

## 2. Completeness

| item | expected | present | errors / skips |
|---|---|---|---|
| PI-RECWRITER-AV19 | Phase A: 2 sizes × 4 writers × 2 fsync = 16 cases of 3000 calls. Phase B: 5 cam × 30 and 60 fps, 60 s each. Phase C: mkv + mp4f, 18,000 frames, 3 reps (`bench_recwriter.py:85-191`) | 16/16 A cases (`n` 3000 each). B: 1801 and 3601 multiframes. C: 2/2 containers × 3 reps. `quick: false` | none; stderr empty |
| PI-JPEG-DECODE-PYAV19 | 5 corpus sets × 10 methods (`bench_jpeg_decode.py:48,51-99`), 5 passes, threads 1 and 5 for 5 s each | 50/50 method rows. `n` = 1500 / 1500 / 95 / 95 / 55 calls (300/300/19/19/11 frames × 5 passes). Every row has `threaded` for 1 and 5 | no `error` field in any row. stderr (20,043 lines): 20,021 bare libjpeg `Corrupt JPEG data: N extraneous bytes before marker 0xd9` lines plus 11 PyTurboJPEG `UserWarning: Corrupt JPEG data: ...` lines, each followed by its `warnings.warn(error_message)` source line (Python prints each distinct warning once). Per FINDINGS F14 the 20,021 bare lines come from `cv2.imdecode` on generic_1080p (one per call, *inferred* from an exact count match), so cv2's generic_1080p timings include a stderr write per call; the same warnings are documented in FINDINGS F9. Not an error (corrected 2026-11-10, GF05: was "about 18,000 libjpeg-turbo `UserWarning` lines (PyTurboJPEG on generic_1080p)"; recounted from `results/bench_runner/logs/20261109T230007/39_PI-JPEG-DECODE-PYAV19.err.txt`) |
| PI-NVJPEG-DECODE | 5 sets × (gpu_single, gpu_to_host, gpu_batch5) (`bench_nvjpeg_decode.py:67-99`) | 15/15 stat blocks. n = 1500 / 1500 / 95 / 95 / 55 per single mode, 100 batch calls per set. `quick: false` | none. stderr: 5 × `cuDevicePrimaryCtxRelease failed: 4`, printed after `wrote ...json` at interpreter exit |

**PI-NVJPEG-DECODE ran 11 s against a 5-min estimate, and it is complete.**
- `env.finished_unix - env.started_unix` = 10.28 s (**arithmetic**).
- The calls fit that time. Sum of n × median over gpu_single + gpu_to_host + batch is about 9 s, plus 20 warm-up decodes per set (**arithmetic**). The 5-min estimate was simply high.
- The shutdown `cuDevicePrimaryCtxRelease` messages come after the JSON was written.

## 3. RecordingWriter / RecorderThread (`R/bench/recwriter_quiet1_pyav19.json`)

Method:
- Field meanings: `bench_recwriter.py:51-55` (`stats`) and `:85-117` (phase A).
- Frames are real camera JPEGs, looped: `c922_720p_flash` at 720p and `c922_1080p` (19 frames) at 1080p (`:88`).
- One unthreaded writer with a flush per frame. fsync is either off or every 30 frames.
- **There are no repeats in phases A and B.** Each A row is one pass of 3000 `write()` calls, so the spread shown is across calls (p99, p99.9, max), not across reps.

### 3.1 Phase A: `write()` per call, ms

| size | writer | fsync every | median | p99 | p99.9 | max | mean | close() |
|---|---|---|---|---|---|---|---|---|
| 720p | mkv | off | 0.033 | 0.1364 | 0.2601 | 0.6333 | 0.0515 | 1.255 |
| 720p | mkv | 30 | 0.0329 | 0.285 | 0.353 | 0.607 | 0.057 | 1.053 |
| 720p | mp4f | off | 0.0319 | 0.1151 | 0.1816 | 0.5776 | 0.0498 | 0.979 |
| 720p | mp4f | 30 | 0.0323 | 0.2796 | 0.3578 | 0.5772 | 0.0591 | 0.923 |
| 720p | avi | off | 0.0288 | 0.1115 | 0.1916 | 0.5967 | 0.0456 | 0.92 |
| 720p | avi | 30 | 0.0291 | 0.2913 | 0.53 | 2.8203 | 0.0558 | 0.872 |
| 720p | folder of JPEGs | off | 0.2233 | 0.3265 | 0.4164 | 0.5615 | 0.23 | 0.037 |
| 720p | folder of JPEGs | 30 | 0.2233 | 0.5461 | 0.6194 | 0.6687 | 0.2389 | 0.047 |
| 1080p | mkv | off | 0.1117 | 0.1813 | 0.3015 | 0.5746 | 0.1061 | 1.043 |
| 1080p | mkv | 30 | 0.1103 | 0.3607 | 0.4137 | 0.6646 | 0.113 | 1.065 |
| 1080p | mp4f | off | 0.1112 | 0.1833 | 0.2504 | 0.6799 | 0.1053 | 0.909 |
| 1080p | mp4f | 30 | 0.1139 | 0.3374 | 0.4164 | 0.6441 | 0.115 | 1.018 |
| 1080p | avi | off | 0.1019 | 0.1964 | 0.3753 | 7.1538 | 0.1 | 0.904 |
| 1080p | avi | 30 | 0.1048 | 0.3644 | 0.4908 | 1.9316 | 0.1081 | 0.799 |
| 1080p | folder of JPEGs | off | 0.2737 | 0.4049 | 0.5416 | 2.2599 | 0.2808 | 0.033 |
| 1080p | folder of JPEGs | 30 | 0.2794 | 0.5996 | 0.6918 | 10.4082 | 0.299 | 0.039 |

### 3.2 Phase B: `RecorderThread.submit()`, 5 cameras in lockstep, 60 s, MKV, `maxsize=256`, policy `drop` (`:120-160`)

| case | multiframes | submit() calls | submit median ms | p99 | p99.9 | max | producer lateness median / max ms | dropped per cam | max queue depth per cam | frames written per cam | all bytes exact | thread errors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5 cam × 30 fps | 1801 | 9005 | 0.0142 | 0.0586 | 0.1154 | 0.54 | 0.5289 / 1.4394 | 0,0,0,0,0 | 1,1,1,1,1 | 1801 × 5 | True | None × 5 |
| 5 cam × 60 fps | 3601 | 18005 | 0.0143 | 0.0642 | 0.2 | 0.4122 | 0.5421 / 1.4917 | 0,0,0,0,0 | 1,1,1,1,1 | 3601 × 5 | True | None × 5 |

`producer_lateness` is how late the paced loop woke against its target (`:136-140`). It measures the sleep loop, not the recorder.

### 3.3 Phase C: open / count / mid-seek on a 10-min 720p file (18,000 frames), 3 reps, ms: median (min-max) [rep 1, 2, 3]

| container | file bytes | cv2 open + CAP_PROP_FRAME_COUNT + first read | cv2 seek to frame 9000 + read | PyAV open + first packet | cv2 frame count |
|---|---|---|---|---|---|
| mkv | 1,398,584,150 | 3.68 (3.66-77.83) [77.83, 3.66, 3.68] | 29.29 (29.02-29.42) | 0.39 (0.34-0.40) | 18000.0 |
| mp4f (fragmented MP4) | 1,400,100,613 | 371.96 (370.83-378.58) [378.58, 371.96, 370.83] | 25.67 (25.57-25.71) | 407.89 (407.89-409.05) | 18000.0 |

- Timed regions are at `:177-191`.
- The MKV first-rep 77.83 ms is the first open after writing. **Inferred:** a cold-open cost (index/Cues read or cache), because reps 2-3 drop to 3.7 ms. The fMP4 open stays at about 371-409 ms in every rep.
- `cv2_frame_count_prop` is taken from the last rep only (`:192`).

## 4. CPU JPEG decode (`R/bench/jpeg_decode_quiet1_pyav19.json`)

Method:
- Field meanings: `bench_jpeg_decode.py:102-140`. `single_call` is per-call time over 5 passes after 20 warm-up calls.
- Min-max is across all calls, not across repeats. The script stores no per-pass statistics.
- `threaded` = aggregate decodes/s for 1 and 5 Python threads over 5 s. There is one run of each.
- `max_abs_diff_vs_cv2` is measured on frame 0 only (`:176-181`). "—" means the output shape differs from cv2's full decode (reduced outputs and native planes).
- cv2 runs with `setNumThreads(1)` (`:155`).
- "full" = full-size BGR. "reduced" = cv2 `IMREAD_REDUCED_COLOR_2`, simplejpeg `min_height=360`, PyTurboJPEG scale 1/2.
- `pyav_mjpeg_native_yuv` decodes only, with no colour conversion.

### c930e_720p_flash (300 frames, median JPEG 56,715 B, 720×1280)
| method | output | max abs diff vs cv2 | n | median ms | p90 | p99 | min-max ms | 1 thread dec/s | 5 threads dec/s | 5/1 (arithmetic) |
|---|---|---|---|---|---|---|---|---|---|---|
| cv2_imdecode_bgr | 720×1280×3 | 0 | 1500 | 2.0959 | 2.1724 | 2.4081 | 1.9419-2.9562 | 468.6 | 1960.9 | 4.18 |
| cv2_imdecode_reduced2_bgr | 360×640×3 | — | 1500 | 0.8068 | 0.8444 | 0.9377 | 0.7614-1.216 | 1229.9 | 6032.4 | 4.90 |
| simplejpeg_bgr | 720×1280×3 | 0 | 1500 | 1.4754 | 1.5226 | 1.6441 | 1.3683-1.8363 | 670.0 | 3041.3 | 4.54 |
| simplejpeg_bgr_fast | 720×1280×3 | 8 | 1500 | 1.2824 | 1.3249 | 1.468 | 1.1889-1.7116 | 771.0 | 3418.0 | 4.43 |
| simplejpeg_bgr_min_h360 | 360×640×3 | — | 1500 | 0.7616 | 0.7908 | 0.9572 | 0.7197-1.3824 | 1302.1 | 6479.6 | 4.98 |
| simplejpeg_bgr_into_buffer | 720×1280×3 | 0 | 1500 | 1.1577 | 1.1964 | 1.3656 | 1.1015-1.9056 | 858.0 | 4243.4 | 4.95 |
| turbojpeg_bgr (ljt 3.2.1) | 720×1280×3 | 0 | 1500 | 1.4439 | 1.504 | 1.724 | 1.3624-2.3507 | 669.2 | 3069.5 | 4.59 |
| turbojpeg_bgr_scale_1_2 | 360×640×3 | — | 1500 | 0.7725 | 0.7949 | 0.8673 | 0.7294-1.1244 | 1293.7 | 6379.8 | 4.93 |
| pyav_mjpeg_bgr24 | 720×1280×3 | 6 | 1500 | 1.6528 | 1.6973 | 1.7752 | 1.5515-2.4044 | 597.2 | 2387.2 | 4.00 |
| pyav_mjpeg_native_yuv | planes | — | 1500 | 1.1747 | 1.2287 | 1.3858 | 1.1134-2.0562 | 837.4 | 4209.8 | 5.03 |

### c922_720p_flash (300 frames, median JPEG 77,265 B, 720×1280)
| method | output | max abs diff vs cv2 | n | median ms | p90 | p99 | min-max ms | 1 thread dec/s | 5 threads dec/s | 5/1 |
|---|---|---|---|---|---|---|---|---|---|---|
| cv2_imdecode_bgr | 720×1280×3 | 0 | 1500 | 2.3106 | 2.3974 | 2.6352 | 2.1765-3.075 | 421.4 | 1822.7 | 4.33 |
| cv2_imdecode_reduced2_bgr | 360×640×3 | — | 1500 | 1.0335 | 1.0936 | 1.2857 | 0.9537-1.6802 | 957.7 | 4693.3 | 4.90 |
| simplejpeg_bgr | 720×1280×3 | 0 | 1500 | 1.7454 | 1.8284 | 2.0035 | 1.607-2.5841 | 572.7 | 2662.5 | 4.65 |
| simplejpeg_bgr_fast | 720×1280×3 | 26 | 1500 | 1.5305 | 1.6004 | 1.7529 | 1.4414-2.2996 | 650.4 | 2946.6 | 4.53 |
| simplejpeg_bgr_min_h360 | 360×640×3 | — | 1500 | 0.9845 | 1.029 | 1.1704 | 0.913-1.5091 | 1011.8 | 4962.8 | 4.90 |
| simplejpeg_bgr_into_buffer | 720×1280×3 | 0 | 1500 | 1.4027 | 1.4657 | 1.5946 | 1.3126-1.9991 | 713.3 | 3516.7 | 4.93 |
| turbojpeg_bgr (ljt 3.2.1) | 720×1280×3 | 0 | 1500 | 1.6887 | 1.7541 | 1.9981 | 1.5808-3.2407 | 576.9 | 2668.9 | 4.63 |
| turbojpeg_bgr_scale_1_2 | 360×640×3 | — | 1500 | 0.9998 | 1.0479 | 1.1515 | 0.9314-1.4677 | 991.9 | 4912.3 | 4.95 |
| pyav_mjpeg_bgr24 | 720×1280×3 | 24 | 1500 | 1.9152 | 1.9712 | 2.0326 | 1.7864-2.4654 | 521.7 | 2129.8 | 4.08 |
| pyav_mjpeg_native_yuv | planes | — | 1500 | 1.3823 | 1.4308 | 1.552 | 1.3118-2.05 | 720.7 | 3585.1 | 4.97 |

### c930e_1080p (19 frames, median JPEG 133,365 B, 1080×1920)
| method | output | max abs diff vs cv2 | n | median ms | p90 | p99 | min-max ms | 1 thread dec/s | 5 threads dec/s | 5/1 |
|---|---|---|---|---|---|---|---|---|---|---|
| cv2_imdecode_bgr | 1080×1920×3 | 0 | 95 | 4.6498 | 4.7102 | 4.8251 | 4.5796-4.8587 | 211.9 | 879.3 | 4.15 |
| cv2_imdecode_reduced2_bgr | 540×960×3 | — | 95 | 2.3699 | 2.4619 | 2.5921 | 2.3108-2.774 | 414.4 | 1927.0 | 4.65 |
| simplejpeg_bgr | 1080×1920×3 | 0 | 95 | 3.3879 | 3.5012 | 3.923 | 3.3026-4.1349 | 290.6 | 1332.5 | 4.59 |
| simplejpeg_bgr_fast | 1080×1920×3 | 11 | 95 | 2.9195 | 2.9842 | 3.0644 | 2.8274-3.1409 | 332.0 | 1524.6 | 4.59 |
| simplejpeg_bgr_min_h360 | 405×720×3 | — | 95 | 1.692 | 1.7553 | 1.8334 | 1.6616-1.9099 | 584.9 | 2919.2 | 4.99 |
| simplejpeg_bgr_into_buffer | 1080×1920×3 | 0 | 95 | 2.7215 | 2.8073 | 2.8956 | 2.6743-2.9865 | 366.0 | 1828.4 | 5.00 |
| turbojpeg_bgr (ljt 3.2.1) | 1080×1920×3 | 0 | 95 | 3.3295 | 3.4229 | 3.7535 | 3.244-3.7639 | 291.0 | 1352.7 | 4.65 |
| turbojpeg_bgr_scale_1_2 | 540×960×3 | — | 95 | 1.9974 | 2.0413 | 2.0758 | 1.9529-2.1114 | 490.1 | 2390.8 | 4.88 |
| pyav_mjpeg_bgr24 | 1080×1920×3 | 8 | 95 | 3.4025 | 3.5279 | 3.8466 | 3.2825-3.8673 | 293.7 | 1202.0 | 4.09 |
| pyav_mjpeg_native_yuv | planes | — | 95 | 2.7347 | 2.8242 | 3.0148 | 2.6794-3.0341 | 364.2 | 1802.4 | 4.95 |

### c922_1080p (19 frames, median JPEG 192,435 B, 1080×1920)
| method | output | max abs diff vs cv2 | n | median ms | p90 | p99 | min-max ms | 1 thread dec/s | 5 threads dec/s | 5/1 |
|---|---|---|---|---|---|---|---|---|---|---|
| cv2_imdecode_bgr | 1080×1920×3 | 0 | 95 | 5.2931 | 5.3857 | 5.6818 | 5.2227-6.1716 | 186.9 | 807.5 | 4.32 |
| cv2_imdecode_reduced2_bgr | 540×960×3 | — | 95 | 2.9316 | 3.0253 | 3.1958 | 2.8721-3.6761 | 332.9 | 1587.7 | 4.77 |
| simplejpeg_bgr | 1080×1920×3 | 0 | 95 | 4.0701 | 4.1413 | 4.379 | 4.0212-4.6263 | 242.6 | 1150.0 | 4.74 |
| simplejpeg_bgr_fast | 1080×1920×3 | 13 | 95 | 3.4824 | 3.524 | 3.6307 | 3.4438-3.6613 | 275.2 | 1288.1 | 4.68 |
| simplejpeg_bgr_min_h360 | 405×720×3 | — | 95 | 2.1802 | 2.2094 | 2.2785 | 2.1458-2.403 | 453.9 | 2262.1 | 4.98 |
| simplejpeg_bgr_into_buffer | 1080×1920×3 | 0 | 95 | 3.3434 | 3.4112 | 3.7375 | 3.3042-4.0412 | 297.3 | 1486.1 | 5.00 |
| turbojpeg_bgr (ljt 3.2.1) | 1080×1920×3 | 0 | 95 | 3.984 | 4.1082 | 4.2892 | 3.9164-4.3225 | 244.4 | 1161.2 | 4.75 |
| turbojpeg_bgr_scale_1_2 | 540×960×3 | — | 95 | 2.6075 | 2.6733 | 2.7154 | 2.5628-2.7423 | 376.2 | 1845.9 | 4.91 |
| pyav_mjpeg_bgr24 | 1080×1920×3 | 11 | 95 | 4.048 | 4.1434 | 4.3159 | 3.903-4.9904 | 249.4 | 1056.8 | 4.24 |
| pyav_mjpeg_native_yuv | planes | — | 95 | 3.3099 | 3.3874 | 3.7524 | 3.2278-4.0885 | 302.0 | 1504.2 | 4.98 |

### generic_1080p (11 frames, median JPEG 65,502 B, 1080×1920; simplejpeg runs with `strict=False`, `:58-63`)
| method | output | max abs diff vs cv2 | n | median ms | p90 | p99 | min-max ms | 1 thread dec/s | 5 threads dec/s | 5/1 |
|---|---|---|---|---|---|---|---|---|---|---|
| cv2_imdecode_bgr | 1080×1920×3 | 0 | 55 | 4.1413 | 4.4954 | 4.6463 | 3.7352-4.7025 | 238.7 | 946.7 | 3.97 |
| cv2_imdecode_reduced2_bgr | 540×960×3 | — | 55 | 1.837 | 2.3263 | 2.5476 | 1.5659-2.5634 | 497.3 | 2292.5 | 4.61 |
| simplejpeg_bgr | 1080×1920×3 | 0 | 55 | 2.8843 | 3.3123 | 3.6689 | 2.5892-3.7954 | 333.9 | 1547.5 | 4.63 |
| simplejpeg_bgr_fast | 1080×1920×3 | 12 | 55 | 2.3343 | 2.7715 | 3.2785 | 2.0652-3.5312 | 393.2 | 1758.4 | 4.47 |
| simplejpeg_bgr_min_h360 | 405×720×3 | — | 55 | 1.2793 | 1.5686 | 1.6774 | 1.0729-1.7327 | 740.5 | 3677.2 | 4.97 |
| simplejpeg_bgr_into_buffer | 1080×1920×3 | 0 | 55 | 2.138 | 2.5901 | 2.7285 | 1.887-2.8093 | 441.6 | 2197.8 | 4.98 |
| turbojpeg_bgr (ljt 3.2.1) | 1080×1920×3 | 0 | 55 | 2.7631 | 3.2473 | 3.8043 | 2.4568-4.0054 | 337.5 | 1541.6 | 4.57 |
| turbojpeg_bgr_scale_1_2 | 540×960×3 | — | 55 | 1.4864 | 1.9227 | 1.9958 | 1.2202-2.0004 | 629.7 | 2949.3 | 4.68 |
| pyav_mjpeg_bgr24 | 1080×1920×3 | 11 | 55 | 2.8773 | 3.2174 | 3.2913 | 2.627-3.344 | 340.8 | 1336.2 | 3.92 |
| pyav_mjpeg_native_yuv | planes | — | 55 | 2.1808 | 2.5284 | 2.5819 | 1.9613-2.6104 | 442.8 | 2191.1 | 4.95 |

The 5-thread aggregate is 3.92-5.03× the 1-thread rate for every method and set (**arithmetic**). **Inferred:** all four libraries release the GIL during decode. This was run on 16 logical CPUs; with 5 threads the CPU was not oversubscribed.

## 5. nvJPEG decode via nvImageCodec 0.9.0.20 (`R/bench/nvjpeg_decode_quiet1_2300.json`)

Method:
- Field meanings: `bench_nvjpeg_decode.py:77-96`.
- `gpu_single` = `Decoder.decode(bytes)` plus `__cuda_array_interface__` access, which forces completion.
- `gpu_to_host` = a **second, separate** decode of the same bytes plus `.cpu()` to numpy, so it includes a full decode (`:84-86`).
- `gpu_batch5` = one `decode([5 frames])` call. The 5 frames are the set's first 5, repeated 100 times (`:89-95`).
- The stats are median / mean / p90 / p99 only. The script records no min or max (`:48-51`), so no min-max can be given.
- Output is `ImageBufferKind.STRIDED_DEVICE` with shape H×W×3 in every set.

| set | frames | output | gpu_single n | median ms | p90 | p99 | gpu_to_host median ms | p90 | p99 | batch5 calls | batch5 median ms | p90 | p99 | batch5 median / 5 (arithmetic) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c930e_720p_flash | 300 | 720×1280×3 | 1500 | 0.7233 | 0.7645 | 0.834 | 1.44 | 1.505 | 1.6293 | 100 | 1.2017 | 2.4848 | 4.0703 | 0.240 |
| c922_720p_flash | 300 | 720×1280×3 | 1500 | 0.9343 | 0.9929 | 1.0601 | 1.6835 | 1.8112 | 2.5246 | 100 | 1.232 | 1.442 | 1.7647 | 0.246 |
| c930e_1080p | 19 | 1080×1920×3 | 95 | 2.0797 | 2.3037 | 2.3719 | 3.4495 | 3.6336 | 3.7825 | 100 | 3.115 | 4.0814 | 6.3432 | 0.623 |
| c922_1080p | 19 | 1080×1920×3 | 95 | 2.2676 | 2.4442 | 2.5306 | 3.644 | 3.8155 | 4.0335 | 100 | 3.197 | 4.1534 | 5.6243 | 0.639 |
| generic_1080p | 11 | 1080×1920×3 | 55 | 1.9188 | 2.1418 | 2.5173 | 3.367 | 3.5392 | 3.7484 | 100 | 2.6539 | 3.1176 | 3.4394 | 0.531 |

These times are host wall time per call. The JSON does not record the host CPU time spent in the calls.

## 6. Headline numbers

1. **Container `write()` is about 0.03 ms per 720p frame and 0.10-0.11 ms per 1080p frame.** A folder of JPEGs costs 0.223 ms (720p) and 0.274-0.279 ms (1080p) at the median. That is 6.8× the MKV median at 720p and 2.5× at 1080p (**arithmetic**). fsync every 30 roughly doubles p99 (MKV 720p 0.136 -> 0.285 ms) but leaves the median unchanged. Source: `research/skellycam_recording/recording_upgrade/results/python_integration/bench/recwriter_quiet1_pyav19.json` → `a_write_cost`.
2. **The worst single `write()` call was 10.41 ms (folder, 1080p, fsync 30) and 7.15 ms (AVI, 1080p, fsync off).** Every MKV and fMP4 case stayed at or below 0.68 ms max. Source: same file, `max_ms`.
3. **`RecorderThread.submit()` costs 0.014 ms at the median** (p99.9 0.115 / 0.200 ms, max 0.54 / 0.41 ms) for 5 cameras at 30 / 60 fps over 60 s. 0 drops, max queue depth 1, all files byte-exact, no thread errors. Source: same file, `b_threaded`.
4. **On a 10-min 720p file, fMP4 takes about 100× longer to open than MKV (warm).**
   - cv2 open + count + first read: fMP4 371.96 ms (370.83-378.58) vs MKV 3.68 ms (3.66-77.83; the 77.83 is the first rep).
   - PyAV open + first packet: fMP4 407.89 ms vs MKV 0.39 ms.
   - Mid-file seek is similar: MKV 29.29 ms, fMP4 25.67 ms. Both report 18,000 frames.
   - Source: same file, `c_open_cost`.
5. **CPU decode of a real c922 1080p JPEG (192 KB):**
   - cv2 5.29 ms;
   - simplejpeg 4.07 ms, or 3.34 ms decoding into a preallocated buffer;
   - PyTurboJPEG with libjpeg-turbo 3.2.1: 3.98 ms;
   - PyAV bgr24 4.05 ms; PyAV native YUV 3.31 ms;
   - reduced previews: simplejpeg `min_height=360` 2.18 ms, PyTurboJPEG 1/2 2.61 ms.
   - Source: `research/skellycam_recording/recording_upgrade/results/python_integration/bench/jpeg_decode_quiet1_pyav19.json` → `sets.c922_1080p`.
6. **At 720p (c930e, 57 KB), simplejpeg into-buffer takes 1.16 ms against cv2's 2.10 ms.** Five threads give 3.9-5.0× the single-thread rate for every library (simplejpeg into-buffer: 858 -> 4243 decodes/s). Source: same file → `sets.c930e_720p_flash`.
7. **nvJPEG (nvImageCodec 0.9.0.20, RTX 3070):**
   - decode left on the GPU: 0.72-0.93 ms at 720p and 1.92-2.27 ms at 1080p;
   - decode + copy to host: 1.44-1.68 ms at 720p and 3.37-3.64 ms at 1080p;
   - a batch of 5: 1.20-1.23 ms at 720p (0.24 ms/frame, **arithmetic**) and 2.65-3.20 ms at 1080p.
   - Source: `research/skellycam_recording/recording_upgrade/results/python_integration/bench/nvjpeg_decode_quiet1_2300.json`.

## 7. Caveats

- **P-cores only** (16 logical CPUs). Thread-scaling numbers would differ on all 28 logical CPUs or with E-cores in play.
- **There are no run-level repeats** for recwriter phases A and B, for JPEG decode, or for nvJPEG. Spreads are per-call percentiles from one run. Only recwriter phase C has 3 reps. The threaded JPEG rates are single 5-s runs.
- **Defender real-time was on.** The writes went to `C:\Users\Dom\Documents\skellycam-raw\...` (`env.target_disk`). The folder-of-JPEGs baseline writes one file per frame, and MsMpEng used 12.31 CPU-s during the item. **Inferred:** the folder numbers include some Defender cost, as in real use with Defender on.
- **The phase A input is small and looped.** 1080p loops 19 frames, so file content is repetitive. **Inferred:** this has little effect on a container write, which copies bytes without encoding.
- **Phase C measures 720p only, and the file was opened right after it was written** (page cache warm, apart from what the first rep shows).
- **JPEG decode inputs are short at 1080p** (19, 19 and 11 frames looped five times), and `max_abs_diff_vs_cv2` is measured on frame 0 only.
- **The libjpeg-turbo version is not in the JSON.** "3.2.1" rests on `BENCH_QUEUE_2300.md` and the DLL's path and sha256 recorded there, not on this result file.
- **nvJPEG:**
  - `gpu_batch5` repeats the same 5 frames 100 times.
  - `gpu_to_host` includes a second decode.
  - The JSON has no CPU-time fields, so host CPU cost per GPU decode is not measured.
  - nvImageCodec 0.9.0.20 differs from the 0.10.0.9 used in intra_compare.
- **The CPU-before load check is a 10-s sample before each item** (all under 15%). Background activity during the item is known only through MsMpEng CPU-s and Defender scan events (none).
