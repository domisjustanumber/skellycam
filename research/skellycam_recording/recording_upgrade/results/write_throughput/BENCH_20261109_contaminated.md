# write_throughput bench run (G5), 2026-11-09, machine Gerald

Bench runner results for the wrapper / file-layout / writer-threading benches designed in `NOTES.md` sections 7-8.
Paths are relative to `research/skellycam_recording/recording_upgrade/results/write_throughput/` unless absolute.
Scripts: `research/skellycam_recording/recording_upgrade/scripts/write_throughput/` (`SCR`). Labels: **measured**
(result file), **inferred** (reasoning, marked). Camera payloads are real corpus JPEG bytes, looped (1080p cells loop
the 19-frame `c922_1080p` / `c930e_1080p` sets; 1080p60 sends those 1080p frames at 60 fps because no 1080p60 capture
exists; the usability bench loops the 891-frame `c930e_720p_flash` set). Nothing is encoded; only wrapper and
file-system cost is measured.

## 1. Environment and machine state

- measured: Python 3.12.13, PyAV 18.0.0 (libavformat 62.12.102, libavcodec 62.28.102), numpy 2.2.6, OpenCV 4.12.0, psutil 7.2.2, Windows 11 10.0.26300 (`env` block in every JSON).
- measured: disk WD_BLACK SN850X 4000GB, NVMe SSD; C: NTFS, 4096-byte clusters; 826 GB free before, 825 GB after (`bench/sysinfo/sysinfo_20261109T120423.json`, `bench/sysinfo/sysinfo_20261109T123537.json`).
- measured: Defender real-time and on-access protection enabled, AMRunningMode Normal; exclusion list unreadable without admin ("N/A: Must be an administrator to view exclusions"); WSearch service running; power plan Balanced (same files).
- measured: nvidia-smi encoder sessions 0 at every set boundary, GPU utilization 4-30 % (`bench/runner_log.txt`, "nvidia:" lines). No GPU work in this bench.
- measured: quiet check (typeperf `\Processor(_Total)\% Processor Time`, 10 x 1 s): 20.4 %, 21.4 %, 17.4 %, then 11.6 % at 12:05:57, after which the bench started (`bench/sysinfo/quiet_20261109T120453_before2.json`, `quiet_*_recheck1..3.json`); 9.4 % after (`bench/sysinfo/quiet_20261109T123530_after.json`). The first reading (28.9 %, `quiet_20261109T120429_before.json`) overlapped sysinfo.py and is not used.
- **FLAG**: the machine was not fully idle. Other agents' processes ran during the session: `research/usb_cameras/suite/windows/run_suite.py --quick ...` (camera suite) and `scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite bench_sync --smoke` (process list read at 12:05, Win32_Process). Top consumers before the start: cpptools.exe, MsMpEng.exe, python.exe. System busy during cells was 11-44 % (tables). Treat single-run tail values (p99.9, max, grab lateness) as noisy; see section 4.
- Benchmark runtime: 12:06:06 (warm-up) to 12:36:17 = 30 min, inside the 35-minute cap.

## 2. What ran, and what was dropped to fit the cap

| manifest id | status | what ran instead / why |
|---|---|---|
| sysinfo_before / sysinfo_after | ran | plus `SCR/quiet_check.py` (new) for the bench-protocol quiet check |
| warm-up | ran, discarded | files x 16 cams x 1080p60 x thread, 10 s (`bench/warmup/`) |
| repeat | replaced by `focus16` | {files, append, mkv_flush, fmp4_frame_flush} x 16 cams x 1080p60 x thread, 30 s, **3 interleaved repetitions** |
| models | reduced to `models16` | 16 cams only (4 cams dropped), 30 s instead of 60 s, 1 repetition; files re-run twice more for thread / process / process_shared (`models16_files_rerun`) after spikes in the first run |
| core | reduced to `core4_1080p30` + `core16_extra` | all 8 writers at 4 cams x 1080p30, 20 s, 1 rep; the 4 writers not in focus16 at 16 cams x 1080p60, 30 s, 1 rep. Dropped: 720p30, 1 and 8 cams, 1080p60 at 4 cams |
| usability_1h | reduced | 27000 frames (15-minute equivalent, 1.5 GB per format) instead of 108000; 1 run. Scaling to 108000 NOT VERIFIED |
| (new) first_read_check | ran | 3000-file follow-up to the usability first-read result (`SCR/first_read_check.py`) |
| variants, intra_ffv1, long | dropped | wall-time cap |
| functional_rerun_quiet | dropped | priority 3, 45 min; T4 stability on a quiet machine still NOT VERIFIED |

Script changes made by the bench runner:
- `SCR/run_matrix.py`: added `--writers --cams --profiles --models --duration --reps --outdir-name` (subset + interleaved repetitions); the named sets are unchanged.
- `SCR/summarize_bench.py`: the usability section now globs `usability_*.json` only (it would crash on the new first_read JSON).
- New: `SCR/quiet_check.py`, `SCR/aggregate_bench.py` (median / min-max across repetitions; produced the tables below), `SCR/first_read_check.py`.
- Media went to `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/write_throughput/` and was deleted after each cell (`bench_runs/` is empty; `payload_cache/`, 23 MB, kept for later runs).

## 3. Results tables (measured)

Columns: write ms = duration of one `writer.write()` call (frame + 32-byte sidecar index), all cameras pooled;
grab late = how late the simulated camera loop picked up its tick; tick->written = tick to write return;
CPU %/cam = bench process CPU / duration / cameras (100 = one logical CPU); sys busy % = share of all 28 logical CPUs;
MsMpEng CPU s = Defender engine CPU seconds during the cell. 16 x 1080p60 = 157 MB/s, 4 x 1080p30 = 20 MB/s.
Raw JSON: `bench/<set>/*.json`; per-cell table generated by summarize_bench.py: `bench/bench_summary.md`.

### focus16 (n = repetitions; values = median (min-max) when n > 1)

| writer | model | cams | profile | payload | n | written/produced | dropped | write ms p50 | write ms p99 | write ms p99.9 | write ms max | grab late ms p99 | grab late ms max | tick->written ms max | CPU %/cam | sys busy % | MsMpEng CPU s | MB/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| append | thread | 16 | 1080p60 | mjpeg | 3 | 86400/86400 | 0 | 0.179 (0.169-0.201) | 0.59 (0.40-0.71) | 1.1 (0.9-1.2) | 17.8 (9.8-59.6) | 0.69 (0.69-0.69) | 1.1 (0.9-4.7) | 18.0 (10.6-60.1) | 2.2 (0.2-3.9) | 15.5 (14.8-19.1) | 7.1 (3.3-15.2) | 157 (157-157) |
| files | thread | 16 | 1080p60 | mjpeg | 3 | 86400/86400 | 0 | 1.299 (1.256-1.358) | 2.40 (2.15-2.42) | 9.8 (7.4-39.0) | 24.1 (13.3-183.3) | 0.66 (0.65-0.68) | 1.0 (0.8-1.1) | 24.5 (13.9-183.6) | 3.8 (2.5-4.7) | 25.0 (18.7-25.8) | 31.7 (26.6-33.7) | 157 (157-157) |
| fmp4_frame_flush | thread | 16 | 1080p60 | mjpeg | 3 | 86400/86400 | 0 | 0.266 (0.266-0.275) | 0.80 (0.76-1.14) | 1.5 (1.4-1.8) | 3.1 (2.8-4.7) | 0.71 (0.70-0.74) | 1.0 (0.9-1.1) | 3.6 (3.2-5.5) | 3.1 (0.5-3.7) | 13.1 (11.0-13.3) | 5.4 (4.0-10.8) | 157 (157-157) |
| mkv_flush | thread | 16 | 1080p60 | mjpeg | 3 | 86400/86400 | 0 | 0.260 (0.254-0.261) | 0.99 (0.85-1.01) | 2.4 (2.1-2.5) | 9.9 (9.0-13.1) | 0.71 (0.70-0.72) | 1.0 (1.0-1.3) | 10.8 (9.4-13.7) | 4.2 (3.0-4.6) | 13.6 (12.2-17.4) | 6.1 (5.5-13.1) | 157 (157-157) |

### models16 (n = repetitions; values = median (min-max) when n > 1)

| writer | model | cams | profile | payload | n | written/produced | dropped | write ms p50 | write ms p99 | write ms p99.9 | write ms max | grab late ms p99 | grab late ms max | tick->written ms max | CPU %/cam | sys busy % | MsMpEng CPU s | MB/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| append | inloop | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.176 | 0.50 | 0.7 | 0.9 | 0.70 | 1.0 | 1.5 | 1.9 | 17.1 | 9.4 | 157 |
| files | inloop | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 1.375 | 2.15 | 12.2 | 17.6 | 0.66 | 1.3 | 18.0 | 2.7 | 28.2 | 38.7 | 157 |
| mkv_flush | inloop | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.241 | 0.66 | 2.4 | 9.2 | 0.87 | 6.1 | 9.6 | 1.4 | 17.5 | 7.3 | 157 |
| append | inloop_lockstep | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.182 | 0.48 | 0.7 | 0.8 | 0.68 | 1.0 | 1.4 | 2.4 | 15.6 | 7.9 | 157 |
| files | inloop_lockstep | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 1.325 | 2.07 | 10.1 | 23.6 | 0.67 | 8.0 | 24.1 | 3.0 | 22.0 | 34.9 | 157 |
| mkv_flush | inloop_lockstep | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.262 | 0.76 | 3.2 | 11.5 | 0.72 | 1.1 | 11.8 | 3.9 | 17.1 | 8.6 | 157 |
| append | process | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.124 | 0.34 | 0.6 | 25.5 | 0.58 | 1.7 | 26.4 | 3.2 | 18.3 | 5.3 | 157 |
| files | process | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 1.033 | 1.96 | 10.0 | 88.2 | 54.37 | 101.7 | 157.6 | 5.9 | 43.8 | 40.8 | 157 |
| mkv_flush | process | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.187 | 0.53 | 1.6 | 2.9 | 0.62 | 2.6 | 4.4 | 2.3 | 16.7 | 6.6 | 157 |
| append | process_shared | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.053 | 0.21 | 0.4 | 3.0 | 0.71 | 1.0 | 5.2 | 2.0 | 19.6 | 6.9 | 157 |
| files | process_shared | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.279 | 0.63 | 8.8 | 98.7 | 27.40 | 43.9 | 269.9 | 3.2 | 32.7 | 32.4 | 157 |
| mkv_flush | process_shared | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.092 | 0.30 | 0.5 | 5.2 | 0.71 | 1.1 | 8.1 | 1.7 | 14.0 | 8.2 | 157 |
| append | thread | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.198 | 0.38 | 0.5 | 1.2 | 0.69 | 1.1 | 1.6 | 0.4 | 22.2 | 14.3 | 157 |
| files | thread | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 1.380 | 2.20 | 28.0 | 241.0 | 33.32 | 69.2 | 274.6 | 6.3 | 36.2 | 39.5 | 157 |
| mkv_flush | thread | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.263 | 0.95 | 1.7 | 3.2 | 0.70 | 1.6 | 3.7 | 4.6 | 15.2 | 6.3 | 157 |

### models16_files_rerun (n = repetitions; values = median (min-max) when n > 1)

| writer | model | cams | profile | payload | n | written/produced | dropped | write ms p50 | write ms p99 | write ms p99.9 | write ms max | grab late ms p99 | grab late ms max | tick->written ms max | CPU %/cam | sys busy % | MsMpEng CPU s | MB/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | process | 16 | 1080p60 | mjpeg | 2 | 57600/57600 | 0 | 0.945 (0.920-0.970) | 1.88 (1.79-1.97) | 25.5 (23.2-27.9) | 49.4 (35.8-63.1) | 29.39 (0.59-58.18) | 50.7 (0.8-100.5) | 80.3 (36.9-123.7) | 5.0 (4.1-5.9) | 25.0 (18.1-32.0) | 35.9 (28.6-43.1) | 157 (157-157) |
| files | process_shared | 16 | 1080p60 | mjpeg | 2 | 57600/57600 | 0 | 0.263 (0.262-0.263) | 0.52 (0.51-0.52) | 0.8 (0.8-0.9) | 16.3 (13.4-19.1) | 0.72 (0.70-0.73) | 12.5 (1.3-23.7) | 26.1 (18.8-33.4) | 2.5 (2.3-2.7) | 16.2 (16.1-16.2) | 21.6 (20.5-22.6) | 157 (157-157) |
| files | thread | 16 | 1080p60 | mjpeg | 2 | 57600/57600 | 0 | 1.265 (1.236-1.295) | 2.13 (2.07-2.19) | 14.4 (9.1-19.7) | 74.8 (31.9-117.7) | 0.65 (0.64-0.66) | 0.9 (0.9-1.0) | 75.3 (32.6-118.0) | 2.1 (2.0-2.2) | 19.9 (16.8-23.1) | 37.1 (30.7-43.6) | 157 (157-157) |

### core4_1080p30 (n = repetitions; values = median (min-max) when n > 1)

| writer | model | cams | profile | payload | n | written/produced | dropped | write ms p50 | write ms p99 | write ms p99.9 | write ms max | grab late ms p99 | grab late ms max | tick->written ms max | CPU %/cam | sys busy % | MsMpEng CPU s | MB/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| append | thread | 4 | 1080p30 | mjpeg | 1 | 2400/2400 | 0 | 0.077 | 0.25 | 0.4 | 0.6 | 0.60 | 0.9 | 1.1 | 0.0 | 20.9 | 8.4 | 20 |
| append_fsync1s | thread | 4 | 1080p30 | mjpeg | 1 | 2400/2400 | 0 | 0.077 | 4.18 | 35.9 | 47.3 | 0.61 | 0.9 | 47.8 | 1.6 | 16.2 | 7.1 | 20 |
| files | thread | 4 | 1080p30 | mjpeg | 1 | 2400/2400 | 0 | 0.543 | 1.82 | 3.7 | 3.9 | 0.62 | 0.7 | 4.4 | 0.6 | 17.2 | 8.5 | 20 |
| files_fsync | thread | 4 | 1080p30 | mjpeg | 1 | 2400/2400 | 0 | 1.053 | 2.80 | 9.2 | 9.3 | 0.61 | 0.8 | 9.6 | 1.5 | 20.4 | 9.6 | 20 |
| files_subdirs | thread | 4 | 1080p30 | mjpeg | 1 | 2400/2400 | 0 | 0.535 | 1.14 | 2.5 | 2.6 | 0.61 | 4.7 | 5.7 | 2.9 | 18.1 | 8.5 | 20 |
| fmp4_frame_flush | thread | 4 | 1080p30 | mjpeg | 1 | 2400/2400 | 0 | 0.146 | 0.45 | 1.6 | 1.8 | 0.65 | 0.9 | 2.3 | 0.2 | 13.0 | 6.1 | 20 |
| mkv_flush | thread | 4 | 1080p30 | mjpeg | 1 | 2400/2400 | 0 | 0.145 | 0.38 | 1.5 | 33.4 | 0.63 | 0.7 | 33.8 | 1.7 | 16.7 | 10.1 | 20 |
| mkvseg10 | thread | 4 | 1080p30 | mjpeg | 1 | 2400/2400 | 0 | 0.160 | 0.53 | 1.2 | 1.3 | 0.64 | 0.8 | 1.8 | 1.4 | 11.7 | 5.5 | 20 |

### core16_extra (n = repetitions; values = median (min-max) when n > 1)

| writer | model | cams | profile | payload | n | written/produced | dropped | write ms p50 | write ms p99 | write ms p99.9 | write ms max | grab late ms p99 | grab late ms max | tick->written ms max | CPU %/cam | sys busy % | MsMpEng CPU s | MB/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| append_fsync1s | thread | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.189 | 7.04 | 19.2 | 235.0 | 53.94 | 87.0 | 292.4 | 1.6 | 33.9 | 19.9 | 157 |
| files_fsync | thread | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 1.777 | 9.44 | 113.0 | 1278.5 | 41.67 | 123.7 | 1278.6 | 2.7 | 40.6 | 28.0 | 157 |
| files_subdirs | thread | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 1.334 | 2.29 | 10.2 | 16.9 | 0.66 | 3.0 | 17.4 | 2.9 | 24.2 | 37.1 | 157 |
| mkvseg10 | thread | 16 | 1080p60 | mjpeg | 1 | 28800/28800 | 0 | 0.242 | 0.70 | 3.1 | 4.0 | 56.02 | 91.9 | 92.3 | 3.4 | 24.0 | 15.2 | 157 |

### usability: 27000 frames, single camera 720p30, warm cache, 1 run (`bench/usability/usability_27000.json`)

| format | files | GB | build s | frame table s | first seq read s | 1000 random reads s (wrong) | first image s | copy shutil s | copy robocopy /MT:8 s | delete s |
|---|---|---|---|---|---|---|---|---|---|---|
| files | 27001 | 1.495 | 7.02 | 0.060 | 116.42 | 0.053 (0) | 0.0024 | 9.96 | 6.73 | 2.26 |
| files_subdirs | 27001 | 1.495 | 5.70 | 0.061 | 129.79 | 0.071 (0) | 0.0024 | 9.83 | 4.79 | 2.12 |
| append | 2 | 1.495 | 0.57 | 0.009 | 0.29 | 0.018 (0) | 0.0024 | 0.34 | 0.43 | 0.12 |
| mkv_flush | 2 | 1.496 | 1.83 | 0.442 | 0.33 | 0.034 (0) | 0.0049 | 0.34 | 0.43 | 0.12 |
| fmp4_frame_flush | 2 | 1.499 | 0.74 | 1.008 | 1.00 | 0.651 (0) | 1.6402 | 0.41 | 0.46 | 0.12 |

files = 27000 frames + 1 sidecar index; copies verified by file count; robocopy returned exit code 1 for every format.

### first_read_check: 3000 freshly written 720p JPEG files vs one append file (`bench/usability/first_read_check_3000.json`)

| layout | pass | wall s | MsMpEng CPU s |
|---|---|---|---|
| files (.jpg) | 1st read | 11.35 | 12.02 |
| files (.jpg) | 2nd read | 0.117 | 0.14 |
| append (.mjpeg) | 1st read | 0.053 | 0.0 |
| append (.mjpeg) | 2nd read | 0.049 | 0.0 |

## 4. Findings (one claim per bullet)

- measured: no cell dropped a frame: written == produced in all 45 timed cells, including in-loop and lockstep models at 16 x 1080p60 (`written/produced` and `dropped` columns).
- measured: at 16 x 1080p60 (thread model, 3 reps) the median write call is 1.30 ms for files vs 0.18 ms append, 0.26 ms mkv_flush, 0.27 ms fmp4_frame_flush (`bench/focus16/`).
- measured: same cells, p99.9: files 9.8 ms (7.4-39.0), append 1.1, mkv_flush 2.4, fmp4_frame_flush 1.5; max: files 24.1 ms (13.3-183.3), append 17.8 (9.8-59.6), mkv_flush 9.9, fmp4_frame_flush 3.1 (`bench/focus16/`).
- measured: Defender engine CPU during a 30 s 16 x 1080p60 cell: files 31.7 s (26.6-33.7) vs append 7.1, mkv_flush 6.1, fmp4_frame_flush 5.4; system busy 25.0 % vs 13-16 % (`bench/focus16/`). inferred (arithmetic): 31.7 s / 30 s is about one logical CPU of Defender work for a folder of JPEGs at this load.
- measured: files_subdirs (1000 files per folder) does not lower the write cost at 16 x 1080p60: p50 1.33 ms, MsMpEng 37.1 s, 1 rep (`bench/core16_extra/`).
- measured: fsync: files_fsync at 16 x 1080p60 p99.9 113 ms, max 1279 ms; at 4 x 1080p30 p50 1.05 ms vs 0.54 ms without fsync; append_fsync1s max 235 ms (16 x 1080p60) and 47 ms (4 x 1080p30); 1 rep each (`bench/core16_extra/`, `bench/core4_1080p30/`).
- measured: at 4 x 1080p30 (20 MB/s) every writer without fsync stayed below 4 ms at p99.9; mkv_flush had one 33.4 ms max (1 rep) (`bench/core4_1080p30/`).
- measured: writing inside the camera loop (inloop, inloop_lockstep) at 16 x 1080p60 dropped no frames for any wrapper; worst write max 23.6 ms and worst grab-lateness max 8.0 ms (both files, lockstep) (`bench/models16/`). Caveat: the inloop drop rule is a model (NOTES section 7), not a driver measurement; 1 rep.
- measured: one writer process serving all 16 cameras (process_shared) kept up with every wrapper; files p50 0.26-0.28 ms there vs 0.95-1.38 ms with 16 concurrent writers (thread / process) (`bench/models16/`, `bench/models16_files_rerun/`). inferred: per-file create cost rises with 16 concurrent creators; not isolated further.
- measured: grab-lateness p99 of 27-58 ms appeared in some single runs (files process / thread / process_shared, files_fsync, append_fsync1s, mkvseg10, all 16 cams) and did not repeat: files thread p99 0.64-0.68 ms in 5 of 6 runs; files process 0.59 ms in rep1 vs 58.2 ms in rep2 (`bench/models16*/`, `bench/focus16/`). inferred: in thread / process models the camera loop does not wait for the writer, so these are system-wide stalls (other agents were running, section 1), not wrapper cost. NOT attributed.
- measured: after recording, the first sequential read of 27000 fresh frame files took 116 s (files) / 130 s (files_subdirs) vs 0.29-1.0 s for the one-file formats; 1000 random reads afterwards took 0.05-0.07 s (`bench/usability/usability_27000.json`).
- measured: the slow first read is per new file and comes with Defender CPU: 3000 fresh .jpg files took 11.35 s and 12.0 s of MsMpEng CPU on the first pass, 0.117 s and 0.14 s on the second; one append file 0.053 s and 0.0 s (`bench/usability/first_read_check_3000.json`). inferred: on-access scanning of each newly created file at its first open. Whether a Defender folder exclusion or a different file extension removes it is NOT VERIFIED (no admin, no setting changes allowed).
- measured: same-volume copy: 27000 files 9.96 s (shutil) / 6.73 s (robocopy /MT:8) / 4.79 s (subdirs, robocopy) vs 0.34-0.46 s for the one-file formats; delete 2.1-2.3 s vs 0.12 s (`bench/usability/usability_27000.json`).
- measured: frame-accurate random access returned the exact camera bytes for 1000/1000 frames in every format (`random_wrong` = 0); fmp4_frame_flush was the slowest container with PyAV 18.0.0: 0.65 s per 1000 random reads, 1.0 s frame table, 1.64 s to the first decoded image, vs 0.034 s / 0.44 s / 0.005 s for mkv_flush (`bench/usability/usability_27000.json`).
- measured: mkv_flush and fmp4_frame_flush report `stream.frames` = 0 from metadata with a correct 900 s duration; a frame table needs a demux pass (0.44 s / 1.0 s for 27000 frames) or the sidecar index (0.009 s) (`bench/usability/usability_27000.json`, `meta` field).

## 5. Not measured / limits

- 4-camera models, 720p30 and 1/8-camera core cells, container variants, FFV1 intra payload, 10-minute sustained runs: dropped (section 2). Sustained behaviour past the SSD cache and Defender steady state is NOT VERIFIED here.
- Repetitions: only `focus16` (4 writers x 3 reps) and files thread / process / process_shared (3 runs each, counting models16) meet the >= 3 rule; every other cell is 1 run.
- Warm cache only (no admin to flush the standby list). Simulated cameras (no USB / driver timing).
- Version bumps (PyAV 19.0.2, OpenCV 5.0.0.93) not benchmarked here: these writes are plain file I/O or libavformat muxing of passthrough packets. PyAV 19.0.2 functional results: `functional/functional_results_av19.0.2.md`.
