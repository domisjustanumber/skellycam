# write_throughput bench run (G5), 2026-11-09 23:00 run, machine Gerald

- **Run id:** `20261109T230007` (timed overnight queue, 2026-11-09 23:00 to 2026-11-10 05:36). The write_throughput items ran 00:53-01:28 and 04:36-05:36 local time.
- **Machine:** Gerald, Intel i7-14700K, Windows 11 10.0.26300, power plan Balanced, disk C: only (WD_BLACK SN850X NVMe, the OS disk), 810.6 GB free at the start and 809.7 GB after the last item (runner start state and per-item `free_disk_gb_after` in `results/BENCH_RUN_2300_LOG.jsonl`).
- **P-cores only:** every item ran with its affinity set to logical CPUs 0-15 (8 P-cores, EfficiencyClass 1). **Results are for 16 logical CPUs (P-cores), not all 28.** Evidence: `"affinity": "pcores"` on every WT line and `pcores` / `pcores_note` in the start state of `results/BENCH_RUN_2300_LOG.jsonl`; code: `scripts/bench_runner/run_queue.py:21-22`.
- **Software:** Python 3.12.13, PyAV 19.0.2 (libavformat / libavcodec 63.1.102), numpy 2.2.6, OpenCV 4.12.0, psutil 7.2.2 (`env` block of every JSON below; all 77 write cells and both usability JSONs say `env.av = 19.0.2`).
- **Windows Defender real-time protection was ON** and was not changed. Its CPU cost is part of the result: it is what a default Windows install pays. It is reported per cell (`MsMpEng CPU s`) and per item (section 1).
- **Predecessor:** `BENCH_20261109_contaminated.md` (daytime run on 2026-11-09, PyAV 18.0.0, other agents running, 28 logical CPUs). Its numbers are lower bounds / indicative only and are **not** comparable row for row with this file (see section 7, anomaly A1).

Paths are relative to `research/skellycam_recording/recording_upgrade/results/write_throughput/` unless they start with `results/` (relative to `research/skellycam_recording/recording_upgrade/`) or are absolute. Scripts: `research/skellycam_recording/recording_upgrade/scripts/write_throughput/` (`SCR`). Labels: every number is **measured** (read from the cited file) unless marked **inferred**.

## How to read the columns (code references)

- One cell = one `bench_write.py` process: N simulated camera processes replay real corpus JPEGs on an absolute per-camera schedule; nothing is encoded (`SCR/bench_write.py:7-11`). 1080p60 sends the 1080p30 corpus frames at 60 fps because no 1080p60 capture exists (`SCR/wt_common.py:41-42`).
- **thread** model: the camera loop hands each frame to one writer thread per camera through a bounded queue of `ring_s` = 2.87 s of frames; a full queue drops the frame and counts it (`SCR/bench_write.py:19-20`, `:170`, `:233-237`, `:307`). **process_shared**: frames go through a shared-memory ring to ONE writer process serving all cameras round-robin (`SCR/bench_write.py:22`).
- **written/produced, dropped**: summed over cameras (`SCR/bench_write.py:401-402`). **late ticks**: ticks the camera loop picked up more than one frame period late (`SCR/bench_write.py:226-228`). **fps/cam** = written / duration / cams (computed here from the summary).
- **write ms**: duration of one `writer.write()` call (frame + 32-byte sidecar index), all cameras pooled (`SCR/bench_write.py:95-99`, `:407`). Percentiles from `numpy.percentile`, max = p100 (`SCR/wt_common.py:372-377`).
- **tick->written ms**: scheduled capture tick to write return, so it includes queue wait (`SCR/bench_write.py:89`). **grab late ms**: how late the camera loop picked up its tick (`SCR/bench_write.py:226`).
- **CPU %/cam** = bench process CPU / duration / cams, 100 = one logical CPU; for process_shared the writer process CPU is added (`SCR/bench_write.py:387-389`, `:410`). **bench CPU (logical CPUs)** = `our_cpu_s / duration_s` (computed here).
- **sys busy % (of 28)**: psutil system-wide busy share of all 28 logical CPUs, not of the 16 the bench could use (`SCR/bench_write.py:384-386`, `:411`; `logical_cpus` = 28 in every JSON).
- **MsMpEng CPU s**: Defender engine CPU seconds (user + system) between the start and the end of the timed run (`SCR/bench_write.py:269-278`, `:338`, `:350`, `:413`). It excludes cell start-up and the media delete.
- **MB/s** = bytes / scheduled duration (`SCR/bench_write.py:404`). **disk write GB**: PhysicalDrive write-byte delta during the run; the lazy writer can still hold data at the end of short cells (`SCR/summarize_bench.py:31-32`, `:52-53`). **delete s**: `shutil.rmtree` of the cell's media after the run (`SCR/bench_write.py:443-446`).
- Idle baseline: MsMpEng / SearchIndexer / SearchProtocolHost / SearchFilterHost CPU seconds over 30 s of idle (`scripts/bench_runner/idle_baseline.py:20-47`).
- First read: writes N corpus 720p JPEGs as files and as one append file (untimed), then reads each layout twice in order, timing each pass and MsMpEng CPU (`SCR/first_read_check.py:31-61`).
- Usability: builds an N-frame single-camera 720p30 recording per format, then times frame table, sequential read, 1000 random reads with a byte check, first decoded image, copy (shutil, robocopy /MT:8) and delete; all warm-cache (`SCR/bench_usability.py:9-21`, `:201`).
- Medians with min-max over repetitions are written `median (min-max)`. Cells with n = 1 show the single value.

## 1. Load record per item

From the runner's per-item record (`results/BENCH_RUN_2300_LOG.jsonl`; per-item digest `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/items_load_2300.json`). "CPU before" is the system CPU load sampled just before the item. Every item exited 0. The only flag, "leftover processes after item", listed only the monitoring Claude session's shells (their command line holds the study path); no bench process was left behind. No item had `load_over_15pct`, and no Defender scan event was logged during any WT item.

| # | item | status | start-end (local) | duration / est min | CPU before mean / max % | top process before (%) | MsMpEng CPU s during item | Defender scan events | free disk after GB |
|---|---|---|---|---|---|---|---|---|---|
| 20 | WT-IDLE-BEFORE | ok, rc 0 | 00:53:10-00:53:40 | 0.5 / 0.6 | 6.81 / 13.9 | SearchIndexer.exe 8.48 | 1.7 | none | 810.6 |
| 21 | WT-FOCUS16-AV19 | ok, rc 0 | 00:53:51-01:00:15 | 6.4 / 10 | 4.06 / 7.2 | AsusFanControlService.exe 1.48 | **114.3** | none | 810.6 |
| 22 | WT-FIRST-READ | ok, rc 0 | 01:00:26-01:00:49 | 0.38 / 4 | 3.53 / 7.1 | Corsair.Service.exe 1.58 | **23.95** | none | 810.6 |
| 23 | WT-IDLE-AFTER | ok, rc 0 | 01:01:00-01:01:31 | 0.5 / 0.6 | 3.30 / 5.6 | AsusFanControlService.exe 1.50 | 1.56 | none | 810.6 |
| 30 | WT-MODELS16-AV19 | ok, rc 0 | 01:19:08-01:28:47 | 9.65 / 14 | 3.78 / 6.4 | Corsair.Service.exe 1.72 | **189.31** | none | 810.6 |
| 62 | WT-CORE-AV19 | ok, rc 0 | 04:36:16-04:47:39 | 11.38 / 18 | 3.42 / 8.8 | AsusFanControlService.exe 1.53 | **116.16** | none | 810.1 |
| 63 | WT-CORE60-AV19 | ok, rc 0 | 04:47:50-04:52:04 | 4.22 / 7 | 3.38 / 7.3 | AsusFanControlService.exe 1.52 | **37.7** | none | 810.1 |
| 64 | WT-IDLE-AFTER2 | ok, rc 0 | 04:52:15-04:52:45 | 0.5 / 0.6 | 4.27 / 7.1 | Corsair.Service.exe 1.70 | 1.3 | none | 810.1 |
| 67 | WT-USABILITY-18K | ok, rc 0 | 05:02:06-05:05:09 | 3.05 / 10 | 3.67 / 8.3 | AsusFanControlService.exe 1.58 | **193.36** | none | 810.1 |
| 68 | WT-LONG-AV19 | ok, rc 0 | 05:05:21-05:36:28 | 31.13 / 35 | 6.31 / 9.4 | SearchIndexer.exe 9.83 | **649.91** | none | 809.7 |

MsMpEng CPU summed over the cells' timed windows, by writer (from the cell JSONs; the rest of each item total falls in start-up, payload loading and deletes):

| item | sum over cells s | files | append | mkv_flush | fmp4_frame_flush |
|---|---|---|---|---|---|
| WT-FOCUS16-AV19 (12 cells x 30 s) | 93.9 | 82.0 | 3.8 | 4.4 | 3.7 |
| WT-MODELS16-AV19 (18 cells x 30 s) | 153.7 | 81.0 thread + 58.2 process_shared | 3.6 + 3.1 | 4.3 + 3.4 | - |
| WT-CORE-AV19 (32 cells x 20 s) | 87.5 | 66.2 | 7.6 | 6.5 | 7.1 |
| WT-CORE60-AV19 (12 cells x 20 s) | 30.8 | 23.3 | 2.7 | 2.9 | 1.9 |
| WT-LONG-AV19 (3 cells x 600 s) | 604.3 | 558.7 | 19.9 | 25.7 | - |

### Idle baselines (30 s each, `bench/idle_baseline_av19.jsonl`)

| tag | when | MsMpEng CPU s | SearchIndexer CPU s | SearchProtocolHost CPU s | SearchFilterHost CPU s |
|---|---|---|---|---|---|
| before_focus16_av19 | 2026-11-10T00:53:10 | 1.531 | 1.344 | 0.422 | (not running) |
| after_first_read_av19 | 2026-11-10T01:01:01 | 1.469 | 1.203 | 0.016 | (not running) |
| after_core_av19 | 2026-11-10T04:52:15 | 1.234 | 1.219 | 0.031 | 0.0 |

inferred (arithmetic): idle MsMpEng is 1.2-1.5 s per 30 s, about 0.04-0.05 of one logical CPU. The baseline did not drift across the night (1.53 before, 1.23 after the core cells).

## 2. Completeness

| item | output | expected | present | errors | evidence |
|---|---|---|---|---|---|
| WT-IDLE-BEFORE | 1 JSONL line, tag before_focus16_av19 | 1 | 1 | none | `bench/idle_baseline_av19.jsonl` line 1; stdout `results/bench_runner/logs/20261109T230007/20_WT-IDLE-BEFORE.out.txt` |
| WT-FOCUS16-AV19 | `bench/focus16_av19/*.json` | 12 (4 writers x 3 reps) | 12 | none: rc=0 for 12/12, stderr empty | `bench/focus16_av19/run_log.txt`; `.../21_WT-FOCUS16-AV19.out.txt` |
| WT-FIRST-READ | `bench/usability/first_read_check_5000.json` | 4 passes (files, append x 1st, 2nd) | 4 | none, stderr empty | see below |
| WT-IDLE-AFTER | JSONL line, tag after_first_read_av19 | 1 | 1 | none | `bench/idle_baseline_av19.jsonl` line 2 |
| WT-MODELS16-AV19 | `bench/models16_av19_shared_vs_thread/*.json` | 18 (3 writers x 2 models x 3 reps) | 18 | none: rc=0 for 18/18 | `bench/models16_av19_shared_vs_thread/run_log.txt` |
| WT-CORE-AV19 | `bench/core_av19/*__720p30__*.json`, `*__1080p30__*.json` | 32 (4 writers x 4 cam counts x 2 profiles, 1 rep) | 32 | none: rc=0 for 32/32 | `bench/core_av19/run_log.txt` lines 1-32 |
| WT-CORE60-AV19 | `bench/core_av19/*__1080p60__*.json` | 12 (4 writers x 1/4/8 cams, 1 rep) | 12 | none: rc=0 for 12/12 | `bench/core_av19/run_log.txt` lines 33-44 |
| WT-IDLE-AFTER2 | JSONL line, tag after_core_av19 | 1 | 1 | none | `bench/idle_baseline_av19.jsonl` line 3 |
| WT-USABILITY-18K | `bench/usability/usability_18000.json` | 5 formats with all fields | 5 | none, stderr empty | see below |
| WT-LONG-AV19 | `bench/long_av19/*.json` | 3 (files, append, mkv_flush, 600 s) | 3 | none: rc=0 for 3/3 | `bench/long_av19/run_log.txt` (654 s, 606 s, 607 s) |

- In all 77 write cells, written = produced and dropped = 0; no `msmpeng_cpu_s` read failed (the field is a float in every cell); `logical_cpus` = 28 and `env.av` = 19.0.2 in every cell (checked by script over the four folders).
- **WT-FIRST-READ ran 23 s against a 4 min estimate, and it is complete.** The JSON has all 4 passes; each read 276,716,591 bytes; the 4 timed passes add to 20.95 s, and the untimed write of 5000 files plus one append file accounts for the rest (inferred). The estimate was simply generous. Same numbers in stdout `results/bench_runner/logs/20261109T230007/22_WT-FIRST-READ.out.txt`.
- **WT-USABILITY-18K ran 3.05 min against a 10 min estimate, and it is complete.** All 5 formats are present with every field; `frames_found` = 18000 and `random_wrong` = 0 for each; the copies were verified by file count (`copy_verified_files` and `robocopy_verified_files` = 18001 for the folder formats, 2 for the one-file formats). The timed fields add to 181.5 s (files 95.4, files_subdirs 79.4, append 1.2, mkv_flush 1.9, fmp4_frame_flush 3.5), which matches the 3.05 min item (computed from `bench/usability/usability_18000.json`). robocopy returned rc 1 for every format; by robocopy's exit-code convention 1 means files were copied without failure (source knowledge, not re-checked here), and the verified counts agree.
- `bench/bench_summary.md` was regenerated by every run_matrix item over **all** set folders. Its PyAV 18.0.0 sections (from the contaminated daytime run) are `core16_extra`, `core4_1080p30`, `focus16`, `models16`, `models16_files_rerun`, `warmup` and `usability_27000.json`. Its PyAV 19.0.2 sections (tonight) are `core_av19`, `focus16_av19`, `long_av19`, `models16_av19_shared_vs_thread` and `usability_18000.json` (env.av counted per folder by script). The table itself has no env.av column, so separate rows by section name.
- Not run tonight (outside these items): `variants`, `intra_ffv1`, `repeat`, the 4-camera `models` cells, the in-loop models, fsync writers, `files_subdirs` / `mkvseg10` write cells, and the 108k-frame `usability_1h`.

## 3. Write cells at 16 cameras x 1080p60

### 3.1 focus16_av19: 4 writers, thread model, 30 s, 3 interleaved reps (`bench/focus16_av19/`)

| writer | model | cams | profile | n | written/produced | dropped | late ticks | fps/cam | write ms p50 | write ms p99 | write ms p99.9 | write ms max | tick->written ms p99 | tick->written ms max | grab late ms max | CPU %/cam | bench CPU (logical CPUs) | sys busy % (of 28) | MsMpEng CPU s | MB/s | disk write GB | delete s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | thread | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 2.111 (1.978-2.206) | 5.26 (5.18-5.53) | 20.3 (12.8-29.5) | 25.6 (25.5-167.4) | 6.25 (6.02-7.14) | 26.3 (26.1-167.9) | 1.3 (1.1-1.7) | 6.8 (4.7-7.1) | 1.09 (0.75-1.13) | 14.6 (12.7-14.8) | 26.8 (25.9-29.3) | 156.9 (156.9-156.9) | 2.62 (2.60-2.62) | 2.3 (2.3-2.4) |
| append | thread | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 0.553 (0.539-0.586) | 1.39 (1.36-1.47) | 1.7 (1.6-1.8) | 15.7 (11.5-37.7) | 2.33 (2.33-2.42) | 15.9 (11.6-38.0) | 1.7 (1.6-2.0) | 4.0 (3.5-4.4) | 0.63 (0.56-0.71) | 7.6 (7.4-7.8) | 1.2 (1.2-1.5) | 156.9 (156.9-156.9) | 2.45 (2.28-2.58) | 0.3 (0.3-0.3) |
| mkv_flush | thread | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 0.808 (0.804-0.884) | 1.64 (1.63-1.68) | 2.9 (2.1-2.9) | 8.0 (6.2-9.2) | 2.61 (2.60-2.68) | 9.3 (7.1-10.9) | 1.9 (1.8-2.0) | 5.7 (5.4-5.8) | 0.90 (0.86-0.93) | 8.1 (8.0-8.5) | 1.5 (1.3-1.5) | 156.9 (156.9-156.9) | 2.47 (2.29-2.61) | 0.3 (0.3-0.3) |
| fmp4_frame_flush | thread | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 0.853 (0.767-0.879) | 1.66 (1.62-1.70) | 3.2 (2.3-5.4) | 7.2 (5.7-11.3) | 2.64 (2.58-2.69) | 7.9 (6.2-12.6) | 2.0 (1.6-2.3) | 5.5 (5.4-6.6) | 0.88 (0.86-1.06) | 8.1 (8.0-9.0) | 1.2 (1.1-1.4) | 156.9 (156.9-156.9) | 2.03 (1.94-2.10) | 0.3 (0.3-0.3) |

16 x 1080p60 = 156.9 MB/s scheduled for every writer. Every cell kept 60.00 fps per camera with 0 dropped and 0 late ticks.

### 3.2 models16_av19_shared_vs_thread: thread vs process_shared, 3 writers, 30 s, 3 interleaved reps (`bench/models16_av19_shared_vs_thread/`)

| writer | model | cams | profile | n | written/produced | dropped | late ticks | fps/cam | write ms p50 | write ms p99 | write ms p99.9 | write ms max | tick->written ms p99 | tick->written ms max | grab late ms max | CPU %/cam | bench CPU (logical CPUs) | sys busy % (of 28) | MsMpEng CPU s | MB/s | disk write GB | delete s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | process_shared | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 0.270 (0.270-0.275) | 0.59 (0.57-0.60) | 0.8 (0.8-0.8) | 21.7 (19.3-37.5) | 7.49 (7.20-7.49) | 26.5 (24.9-41.9) | 1.5 (1.1-1.8) | 2.1 (1.9-3.1) | 0.34 (0.31-0.50) | 9.5 (9.4-10.1) | 19.5 (18.6-20.2) | 156.9 (156.9-156.9) | 2.56 (2.48-2.77) | 2.2 (2.2-2.3) |
| append | process_shared | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 0.118 (0.117-0.119) | 0.35 (0.35-0.37) | 0.7 (0.6-0.8) | 6.0 (1.6-9.1) | 4.49 (4.40-4.55) | 10.4 (10.1-22.1) | 1.9 (1.7-2.0) | 1.8 (1.4-2.1) | 0.29 (0.23-0.33) | 4.9 (4.8-4.9) | 1.1 (1.0-1.1) | 156.9 (156.9-156.9) | 2.40 (2.35-2.42) | 0.3 (0.3-0.3) |
| mkv_flush | process_shared | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 0.170 (0.167-0.176) | 0.48 (0.46-0.48) | 0.8 (0.8-0.8) | 15.0 (7.6-20.7) | 5.44 (5.44-5.57) | 19.3 (9.7-55.1) | 1.7 (1.6-1.9) | 1.6 (1.6-2.3) | 0.26 (0.25-0.36) | 4.9 (4.9-5.0) | 1.2 (1.1-1.2) | 156.9 (156.9-156.9) | 2.25 (2.15-2.25) | 0.3 (0.3-0.3) |
| files | thread | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 2.098 (2.027-2.323) | 5.27 (5.25-5.42) | 8.4 (7.0-19.3) | 34.0 (21.8-38.2) | 5.98 (5.96-6.20) | 34.6 (22.2-38.4) | 1.1 (1.0-1.2) | 4.3 (4.2-4.9) | 0.69 (0.67-0.78) | 12.5 (12.3-13.1) | 26.6 (26.0-28.4) | 156.9 (156.9-156.9) | 2.44 (2.33-2.44) | 2.3 (2.3-2.3) |
| append | thread | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 0.365 (0.355-0.520) | 1.12 (1.09-1.56) | 1.4 (1.4-1.8) | 4.1 (3.4-10.1) | 2.10 (2.03-2.51) | 4.9 (4.3-10.8) | 1.7 (1.6-1.7) | 4.4 (4.2-4.6) | 0.70 (0.67-0.73) | 8.3 (8.3-8.6) | 1.1 (1.1-1.4) | 156.9 (156.9-156.9) | 2.43 (2.31-2.48) | 0.4 (0.4-0.4) |
| mkv_flush | thread | 16 | 1080p60 | 3 | 86400/86400 | 0 | 0 | 60.00 (60.00-60.00) | 0.846 (0.648-1.011) | 1.64 (1.35-1.81) | 3.3 (2.1-3.6) | 5.9 (3.2-7.3) | 2.62 (2.34-2.81) | 6.7 (4.3-9.0) | 1.7 (1.4-1.9) | 5.8 (5.0-6.2) | 0.93 (0.80-0.99) | 7.9 (7.6-8.2) | 1.5 (1.4-1.5) | 156.9 (156.9-156.9) | 2.01 (1.97-2.17) | 0.3 (0.3-0.4) |

Read the process_shared rows by tick->written, not by write ms: one writer process serves 16 cameras round-robin, so each call is cheaper (less concurrency) but each frame waits longer for its turn (`SCR/bench_write.py:22`).

### 3.3 long_av19: sustained 10-minute cells, 16 x 1080p60, thread model, 1 rep each (`bench/long_av19/`)

| writer | model | cams | profile | n | written/produced | dropped | late ticks | fps/cam | write ms p50 | write ms p99 | write ms p99.9 | write ms max | tick->written ms p99 | tick->written ms max | grab late ms max | CPU %/cam | bench CPU (logical CPUs) | sys busy % (of 28) | MsMpEng CPU s | MB/s | disk write GB | delete s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | thread | 16 | 1080p60 | 1 | 576000/576000 | 0 | 0 | 60.00 | 1.977 | 5.50 | 37.7 | 328.8 | 7.43 | 329.1 | 1.3 | 4.4 | 0.70 | 12.9 | 558.7 | 156.9 | 106.19 | 53.0 |
| append | thread | 16 | 1080p60 | 1 | 576000/576000 | 0 | 0 | 60.00 | 0.479 | 1.29 | 1.7 | 26.6 | 2.19 | 27.4 | 2.0 | 5.0 | 0.81 | 8.3 | 19.9 | 156.9 | 95.64 | 4.4 |
| mkv_flush | thread | 16 | 1080p60 | 1 | 576000/576000 | 0 | 0 | 60.00 | 1.003 | 2.26 | 6.7 | 31.8 | 3.21 | 32.9 | 2.6 | 7.5 | 1.19 | 8.8 | 25.7 | 156.9 | 91.90 | 4.4 |

- Each cell wrote 576,000 frames, 94.16 GB of payload (files: 576,016 files = 576,000 frames + 16 sidecar indexes) (`bytes`, `files_written`).
- PhysicalDrive writes during the run: files 106.19 GB, append 95.64 GB, mkv_flush 91.90 GB (`physical_disk_delta`). inferred: the files layout writes about 12 GB (13 %) more than its payload (file-system metadata for 576k files); mkv_flush ending below the payload means part of it was still in the cache at the end of the timed window.
- Deleting the media after the timed run: files 53.0 s (576,016 files) vs 4.4 s for append and mkv_flush (`delete_s`).

## 4. Core matrix: writers x cameras x profiles, thread model, 20 s, 1 rep (`bench/core_av19/`)

Every cell: 0 dropped, 0 late ticks, fps/cam exactly 30.00 or 60.00. Single runs, so tail values (p99.9, max) are one sample each.

#### core_av19, 720p30, thread model, 20 s, 1 rep

| writer | cams | written/produced | dropped | late ticks | write ms p50 | p99 | p99.9 | max | tick->written ms max | grab late ms max | CPU %/cam | sys busy % (of 28) | MsMpEng CPU s | MB/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | 1 | 600/600 | 0 | 0 | 1.260 | 2.35 | 2.8 | 2.8 | 3.4 | 1.1 | 3.4 | 4.0 | 2.1 | 1.7 |
| append | 1 | 600/600 | 0 | 0 | 0.105 | 0.46 | 1.1 | 2.0 | 2.5 | 1.1 | 0.1 | 3.5 | 0.8 | 1.7 |
| mkv_flush | 1 | 600/600 | 0 | 0 | 0.180 | 0.50 | 1.1 | 1.5 | 1.9 | 0.8 | 1.7 | 4.1 | 1.0 | 1.7 |
| fmp4_frame_flush | 1 | 600/600 | 0 | 0 | 0.184 | 0.53 | 3.1 | 5.1 | 5.6 | 0.8 | 1.7 | 3.6 | 0.5 | 1.7 |
| files | 4 | 2400/2400 | 0 | 0 | 1.540 | 2.76 | 3.9 | 4.1 | 4.4 | 0.9 | 3.4 | 5.5 | 6.0 | 8.0 |
| append | 4 | 2400/2400 | 0 | 0 | 0.119 | 0.46 | 1.9 | 2.1 | 2.9 | 0.9 | 0.4 | 3.8 | 0.9 | 8.0 |
| mkv_flush | 4 | 2400/2400 | 0 | 0 | 0.211 | 0.64 | 4.9 | 5.8 | 6.3 | 0.9 | 0.5 | 3.5 | 0.9 | 8.0 |
| fmp4_frame_flush | 4 | 2400/2400 | 0 | 0 | 0.209 | 0.68 | 6.2 | 7.0 | 7.7 | 1.2 | 0.8 | 3.8 | 0.8 | 8.0 |
| files | 8 | 4800/4800 | 0 | 0 | 2.340 | 4.52 | 5.7 | 6.3 | 6.8 | 0.9 | 4.8 | 8.2 | 9.6 | 16.0 |
| append | 8 | 4800/4800 | 0 | 0 | 0.137 | 0.77 | 3.8 | 25.3 | 25.7 | 1.1 | 0.8 | 4.0 | 1.1 | 16.0 |
| mkv_flush | 8 | 4800/4800 | 0 | 0 | 0.235 | 0.76 | 5.1 | 5.6 | 6.5 | 1.1 | 1.7 | 3.9 | 0.7 | 16.0 |
| fmp4_frame_flush | 8 | 4800/4800 | 0 | 0 | 0.234 | 0.88 | 6.0 | 6.9 | 8.1 | 1.1 | 0.4 | 3.6 | 0.6 | 16.0 |
| files | 16 | 9600/9600 | 0 | 0 | 3.255 | 8.10 | 9.7 | 10.3 | 11.2 | 1.2 | 3.4 | 10.8 | 16.6 | 31.9 |
| append | 16 | 9600/9600 | 0 | 0 | 0.170 | 0.78 | 1.8 | 2.0 | 3.0 | 1.6 | 1.6 | 4.9 | 1.1 | 31.9 |
| mkv_flush | 16 | 9600/9600 | 0 | 0 | 0.266 | 1.53 | 7.6 | 8.1 | 9.9 | 1.8 | 1.3 | 4.8 | 0.7 | 31.9 |
| fmp4_frame_flush | 16 | 9600/9600 | 0 | 0 | 0.258 | 1.02 | 7.2 | 7.6 | 8.7 | 1.4 | 1.8 | 5.2 | 1.2 | 31.9 |

#### core_av19, 1080p30, thread model, 20 s, 1 rep

| writer | cams | written/produced | dropped | late ticks | write ms p50 | p99 | p99.9 | max | tick->written ms max | grab late ms max | CPU %/cam | sys busy % (of 28) | MsMpEng CPU s | MB/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | 1 | 600/600 | 0 | 0 | 1.324 | 2.74 | 3.7 | 3.8 | 4.5 | 0.8 | 2.9 | 4.2 | 2.3 | 5.8 |
| append | 1 | 600/600 | 0 | 0 | 0.195 | 0.63 | 1.2 | 1.6 | 2.7 | 0.8 | 1.3 | 3.6 | 1.0 | 5.8 |
| mkv_flush | 1 | 600/600 | 0 | 0 | 0.324 | 0.80 | 2.5 | 2.8 | 3.3 | 1.0 | 0.9 | 3.4 | 0.4 | 5.8 |
| fmp4_frame_flush | 1 | 600/600 | 0 | 0 | 0.311 | 0.68 | 2.0 | 2.0 | 2.3 | 1.5 | 1.5 | 3.7 | 1.0 | 5.8 |
| files | 4 | 2400/2400 | 0 | 0 | 1.623 | 2.69 | 4.2 | 4.3 | 5.1 | 1.0 | 3.6 | 5.8 | 5.9 | 19.6 |
| append | 4 | 2400/2400 | 0 | 0 | 0.211 | 0.57 | 2.0 | 2.2 | 2.4 | 1.1 | 1.5 | 4.0 | 0.7 | 19.6 |
| mkv_flush | 4 | 2400/2400 | 0 | 0 | 0.331 | 0.70 | 2.7 | 2.9 | 3.3 | 1.0 | 2.3 | 4.0 | 0.8 | 19.6 |
| fmp4_frame_flush | 4 | 2400/2400 | 0 | 0 | 0.324 | 0.79 | 3.8 | 4.2 | 4.6 | 1.4 | 2.1 | 4.1 | 1.0 | 19.6 |
| files | 8 | 4800/4800 | 0 | 0 | 2.411 | 5.59 | 7.0 | 7.5 | 8.1 | 0.9 | 4.5 | 8.0 | 9.3 | 39.2 |
| append | 8 | 4800/4800 | 0 | 0 | 0.272 | 0.69 | 1.0 | 1.0 | 1.9 | 1.1 | 1.0 | 4.1 | 0.9 | 39.2 |
| mkv_flush | 8 | 4800/4800 | 0 | 0 | 0.408 | 0.99 | 1.7 | 1.8 | 2.4 | 1.2 | 2.1 | 4.4 | 1.0 | 39.2 |
| fmp4_frame_flush | 8 | 4800/4800 | 0 | 0 | 0.413 | 0.95 | 2.7 | 2.9 | 3.3 | 1.2 | 1.6 | 4.2 | 1.1 | 39.2 |
| files | 16 | 9600/9600 | 0 | 0 | 3.368 | 7.90 | 12.3 | 12.7 | 13.7 | 1.4 | 4.4 | 10.7 | 14.3 | 78.5 |
| append | 16 | 9600/9600 | 0 | 0 | 0.679 | 1.58 | 1.9 | 4.3 | 5.0 | 1.9 | 2.1 | 5.7 | 1.1 | 78.5 |
| mkv_flush | 16 | 9600/9600 | 0 | 0 | 0.818 | 1.80 | 2.5 | 2.9 | 3.6 | 1.5 | 3.8 | 7.1 | 1.1 | 78.5 |
| fmp4_frame_flush | 16 | 9600/9600 | 0 | 0 | 0.958 | 1.76 | 8.1 | 8.5 | 9.7 | 1.8 | 3.0 | 6.3 | 0.8 | 78.5 |

#### core_av19, 1080p60, thread model, 20 s, 1 rep

| writer | cams | written/produced | dropped | late ticks | write ms p50 | p99 | p99.9 | max | tick->written ms max | grab late ms max | CPU %/cam | sys busy % (of 28) | MsMpEng CPU s | MB/s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | 1 | 1200/1200 | 0 | 0 | 1.238 | 2.01 | 3.6 | 5.4 | 5.7 | 0.8 | 7.7 | 4.9 | 3.4 | 11.5 |
| append | 1 | 1200/1200 | 0 | 0 | 0.182 | 0.43 | 0.6 | 1.7 | 2.0 | 0.8 | 3.0 | 3.6 | 1.0 | 11.5 |
| mkv_flush | 1 | 1200/1200 | 0 | 0 | 0.303 | 0.57 | 2.1 | 2.9 | 3.5 | 1.0 | 2.7 | 3.9 | 0.9 | 11.5 |
| fmp4_frame_flush | 1 | 1200/1200 | 0 | 0 | 0.300 | 0.58 | 0.8 | 4.3 | 5.1 | 1.0 | 0.9 | 3.7 | 0.8 | 11.5 |
| files | 4 | 4800/4800 | 0 | 0 | 1.444 | 2.43 | 3.3 | 3.8 | 4.6 | 1.1 | 7.3 | 7.3 | 8.9 | 39.2 |
| append | 4 | 4800/4800 | 0 | 0 | 0.195 | 0.52 | 0.9 | 13.9 | 14.2 | 1.5 | 2.8 | 4.1 | 0.9 | 39.2 |
| mkv_flush | 4 | 4800/4800 | 0 | 0 | 0.294 | 0.69 | 2.2 | 5.9 | 6.5 | 0.9 | 2.7 | 4.5 | 1.3 | 39.2 |
| fmp4_frame_flush | 4 | 4800/4800 | 0 | 0 | 0.310 | 0.75 | 1.3 | 5.2 | 5.7 | 0.8 | 3.6 | 4.2 | 0.6 | 39.2 |
| files | 8 | 9600/9600 | 0 | 0 | 1.898 | 3.88 | 5.1 | 6.6 | 7.3 | 0.8 | 7.9 | 9.9 | 11.1 | 78.5 |
| append | 8 | 9600/9600 | 0 | 0 | 0.259 | 0.62 | 1.0 | 2.2 | 2.6 | 1.0 | 4.6 | 5.3 | 0.8 | 78.5 |
| mkv_flush | 8 | 9600/9600 | 0 | 0 | 0.404 | 0.81 | 2.4 | 6.3 | 7.3 | 1.2 | 3.7 | 4.8 | 0.6 | 78.5 |
| fmp4_frame_flush | 8 | 9600/9600 | 0 | 0 | 0.408 | 0.83 | 2.5 | 7.9 | 9.0 | 1.3 | 2.3 | 4.2 | 0.5 | 78.5 |

## 5. First read after writing (`bench/usability/first_read_check_5000.json`)

5000 freshly written 720p corpus JPEGs (one file each) vs the same bytes in one append file; 276,716,591 bytes per pass.

| layout | pass | wall s | MsMpEng CPU s during the pass |
|---|---|---|---|
| files (.jpg) | 1st read | 20.594 | 20.594 |
| files (.jpg) | 2nd read | 0.186 | 0.156 |
| append (.mjpeg) | 1st read | 0.088 | 0.031 |
| append (.mjpeg) | 2nd read | 0.084 | 0.000 |

inferred (arithmetic): 4.1 ms of wall time and 4.1 ms of Defender CPU per new file on the first open, 111x the second pass. The daytime 3000-file run gave 11.35 s / 12.0 s (`bench/usability/first_read_check_3000.json`, PyAV 18 env, contaminated), the same per-file cost (3.8 ms). This check does not prove that Defender causes the delay, only that Defender CPU equals the wall time of the slow pass; a Defender exclusion test was not allowed (no setting changes).

## 6. After-recording usability: 18,000 frames, 1 camera 720p30, warm cache, 1 run (`bench/usability/usability_18000.json`)

18,000 frames = a 10-minute single-camera recording of the looped 891-frame `c930e_720p_flash` set, about 1.0 GB per format. Random reads: 1000 random frames by index with a byte check. Copy and delete on the same volume (C:).

| format | files | GB | alloc GB (4 KiB clusters) | build s | open+meta s | frame table s | sequential read s | 1000 random reads s (wrong) | first image s | copy shutil s | copy robocopy /MT:8 s | delete copy s | delete s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| files | 18001 | 0.997 | 1.022 | 3.77 | 0.000 | 0.038 | 78.36 | 0.048 (0) | 0.0023 | 5.99 | 3.48 | 1.24 | 1.21 |
| files_subdirs | 18001 | 0.997 | 1.022 | 3.52 | 0.000 | 0.039 | 64.63 | 0.047 (0) | 0.0022 | 5.23 | 2.31 | 1.20 | 1.15 |
| append | 2 | 0.997 | 0.997 | 0.33 | 0.000 | 0.016 | 0.18 | 0.017 (0) | 0.0024 | 0.20 | 0.22 | 0.06 | 0.06 |
| mkv_flush | 2 | 0.998 | 0.998 | 0.83 | 0.006 | 0.233 | 0.20 | 0.027 (0) | 0.0037 | 0.21 | 0.22 | 0.06 | 0.06 |
| fmp4_frame_flush | 2 | 0.999 | 0.999 | 0.41 | 0.412 | 0.638 | 0.64 | 0.425 (0) | 0.3999 | 0.20 | 0.22 | 0.06 | 0.06 |

- `files` = 18,000 frames + 1 sidecar index; files_subdirs puts 1000 files per folder (`SCR/wt_common.py:48`).
- mkv_flush and fmp4_frame_flush report `stream_frames` = 0 in metadata with a correct duration (600.0 s and 599.999989 s) (`meta` field), so a frame table needs a demux pass (0.233 s / 0.638 s) or the sidecar index (append: 0.016 s).
- This bench does not record MsMpEng per format. The whole item used 193.36 s of MsMpEng CPU (section 1). inferred: most of it falls in the two folder formats' first sequential reads (78 s and 65 s), given the first-read result in section 5; not measured per format.
- PyAV 19 vs the daytime PyAV 18 run (`bench/usability/usability_27000.json`, 27,000 frames, contaminated): fmp4_frame_flush first image 0.400 s tonight vs 1.640 s then, and random reads 0.425 s vs 0.651 s. The frame counts and machine state differ, so this is not a version comparison (inferred caution).

## 7. Headline numbers

1. **No frame was lost in any write cell.** 77 of 77 cells tonight had written = produced, 0 dropped, 0 late ticks, including three 10-minute 16 x 1080p60 cells of 576,000 frames each at 156.9 MB/s. Files: `bench/focus16_av19/`, `bench/models16_av19_shared_vs_thread/`, `bench/core_av19/`, `bench/long_av19/` (`summary.written`, `produced`, `dropped`, `late_ticks`).
2. **Write call at 16 x 1080p60 (thread, 3 reps):** p50 files 2.111 ms (1.978-2.206) vs append 0.553, mkv_flush 0.808, fmp4_frame_flush 0.853; p99.9 files 20.3 ms (12.8-29.5) vs 1.7 / 2.9 / 3.2. File: `bench/focus16_av19/*.json`.
3. **Defender cost of a folder of JPEGs:** at 16 x 1080p60, MsMpEng used 26.8 s (25.9-29.3) per 30 s cell for files vs medians of 1.2-1.5 s for append, mkv_flush and fmp4_frame_flush, which is the idle level (idle baseline 1.23-1.53 s per 30 s). Files: `bench/focus16_av19/*.json` (`msmpeng_cpu_s`), `bench/idle_baseline_av19.jsonl`. inferred: about 0.9 of a logical CPU of Defender work for files.
4. **Sustained 10 minutes, 16 x 1080p60:** files write max 328.8 ms, p99.9 37.7 ms, MsMpEng 558.7 s in 600 s; append max 26.6 ms, p99.9 1.7 ms, MsMpEng 19.9 s; mkv_flush max 31.8 ms, p99.9 6.7 ms, MsMpEng 25.7 s. The 2.87 s queue absorbed the files stalls (tick->written max 329.1 ms, 0 dropped). Deleting the files recording took 53.0 s vs 4.4 s. Files: `bench/long_av19/files__16cam__1080p60__mjpeg__thread__600s.json`, `append__...600s.json`, `mkv_flush__...600s.json`.
5. **One shared writer process vs a thread per camera (16 x 1080p60, 3 reps):** files write p50 0.270 ms (process_shared) vs 2.098 ms (thread), but tick->written p99 7.49 ms vs 5.98 ms; append 4.49 vs 2.10 ms and mkv_flush 5.44 vs 2.62 ms tick->written p99. MsMpEng for files 19.5 s vs 26.6 s. File: `bench/models16_av19_shared_vs_thread/*.json`.
6. **Files cost scales with camera count, containers barely do:** files write p50 at 1 / 4 / 8 / 16 cameras x 1080p30 = 1.324 / 1.623 / 2.411 / 3.368 ms; mkv_flush 0.324 / 0.331 / 0.408 / 0.818 ms. MsMpEng at 16 x 1080p30 in 20 s: files 14.3 s vs 0.8-1.1 s for the others. File: `bench/core_av19/*__1080p30__*.json`.
7. **First read of fresh frame files:** 5000 new .jpg files took 20.59 s and 20.59 s of MsMpEng CPU on the first pass, 0.186 s on the second; one append file 0.088 s. File: `bench/usability/first_read_check_5000.json`.
8. **After a 10-minute single-camera recording (18,000 frames):** sequential read files 78.4 s / files_subdirs 64.6 s vs append 0.18 s, mkv_flush 0.20 s, fmp4_frame_flush 0.64 s; robocopy files 3.48 s vs 0.22 s; 1000 random reads mkv_flush 0.027 s vs fmp4_frame_flush 0.425 s, first image 0.0037 s vs 0.400 s; 0 wrong reads in every format. File: `bench/usability/usability_18000.json`.

## 8. Anomalies

- **A1. Per-call write latency is higher tonight than in the contaminated daytime run.** focus16 p50 tonight vs daytime (`BENCH_20261109_contaminated.md`, `bench/focus16/`): files 2.111 vs 1.299 ms, append 0.553 vs 0.179, mkv_flush 0.808 vs 0.260, fmp4_frame_flush 0.853 vs 0.266; CPU %/cam is also higher (files 6.8 vs 3.8). Tail values are mixed (files p99.9 20.3 vs 9.8; mkv_flush max 8.0 vs 9.9). inferred, not tested: the main change is the P-core affinity (16 camera processes, 16 writer threads and the parent on 16 logical CPUs = 8 physical cores with Hyper-Threading, instead of 28 logical CPUs). PyAV is unlikely to be the cause because append does not use PyAV and rose by the same factor. So the daytime numbers are not "lower bounds" for every column; treat the two runs as different configurations.
- **A2. Single large stalls.** focus16 files rep max 167.4 ms in one of 3 reps (others 25.5-25.6 ms); append max 37.7 ms in one rep; long files max 328.8 ms. They came with no drop and with grab late max at most 2.3 ms in focus16 (2.6 ms in the long cells), so the camera loop itself never stalled (thread model). Not attributed.
- **A3. 30 s cells do not reach the disk.** disk write GB during a 30 s 16 x 1080p60 cell is 1.9-2.6 GB against 4.7 GB of payload (inferred arithmetic: 156.9 MB/s x 30 s), so short cells measure the cache path; only the 600 s cells show the steady state.
- **A4. Defender work continues after the timed window.** Item totals exceed the cell sums (focus16 114.3 vs 93.9 s; long 649.9 vs 604.3 s; core 116.2 vs 87.5 s), so part of the cost lands outside the measured window (delete, start-up).

## 9. Caveats

- **1 rep** for every core_av19 cell and every long cell; only focus16_av19 and models16_av19 have 3 reps. Tail values (p99.9, max) of 1-rep cells are single samples.
- **Defender cost is included** in every timing (real-time protection on, default settings, no exclusions known; the exclusion list was not readable without admin in the earlier stage). This is the cost on a default Windows install, not the cost of the writer alone.
- **P-core only:** results are for 16 logical CPUs (8 P-cores with HT), not all 28. `sys busy %` is still a share of all 28 logical CPUs (`SCR/bench_write.py:384-386`).
- **Disk C: is shared with the OS** (the only disk); the background load before each item was 3.3-6.8 % mean (section 1), with SearchIndexer the top process before WT-IDLE-BEFORE and WT-LONG-AV19.
- Simulated cameras replaying looped corpus JPEGs (19-frame 1080p sets, 891-frame 720p set); Defender's handling of repeated content is NOT VERIFIED. Warm cache only. 1080p60 reuses 1080p30 frames.
- The core matrix covers 4 writers only (files, append, mkv_flush, fmp4_frame_flush); fsync variants, files_subdirs and mkvseg10 were not in tonight's write cells.
- Usability is 18,000 frames (10 min of one camera), not the planned 108,000 (1 h); scaling to 1 h is NOT VERIFIED.
