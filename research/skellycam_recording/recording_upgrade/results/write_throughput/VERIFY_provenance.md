# write_throughput: provenance check of the updated draft FINDINGS (2026-11-10)

Verifier: adversarial provenance pass on the post-bench draft (quiet run `20261109T230007`). I opened every cited JSON, result file, code line and log record and compared them with the draft. No timed or functional benchmarks were run. The previous report is kept as `VERIFY_provenance.prev.md`.

`RES` = `research/skellycam_recording/recording_upgrade/results/write_throughput`, `SCR` = `research/skellycam_recording/recording_upgrade/scripts/write_throughput`, `RU` = `research/skellycam_recording/recording_upgrade`.

**Method.** A throwaway script recomputed the median (min-max) of every `summary.*` field the draft cites. It covered all 77 cell JSONs in `RES/bench/{focus16_av19,models16_av19_shared_vs_thread,core_av19,long_av19}`, grouped by writer, model, cams, profile and duration. The script is at `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step2/wtv/st.py`. I also read `usability_18000.json`, `first_read_check_{5000,3000}.json`, `idle_baseline_av19.jsonl`, the WT lines of `RU/results/BENCH_RUN_2300_LOG.jsonl`, `RU/results/crash_resilience/bench/fsync_pyav19.json` and the daytime `RES/bench/focus16/*.json`. The FFmpeg n9.0.2 and RFC 9559 lines were re-checked against the copies fetched on 2026-11-09 (path in draft section 7). Every cited line still matches.

## 1. Verdict

The update holds up well on provenance:
- All 77 cells say `env.av` 19.0.2 and libavformat [63, 1, 102].
- Every cell has written = produced, dropped = 0 and late_ticks = 0.
- Almost every number in 2.8-2.13 and tables 3.2-3.4 matches the JSON to the stated precision.
- The idle baselines, item totals, load record and code citations all check out.

Five claims are refuted. One is a wrong per-cell count. Four are comparison words ("barely", "roughly doubles", "a third to a half", "more than the rep range") that the numbers do not support. There are also eight weak spots: a wrong line citation, a mislabelled inference, a cross-topic quiet-run result that goes unmentioned, a one-item range given as the general case, an over-broad "unbuffered" wording, the runner's leftover-process flag left out, a rounding error, and a grab-late range quoted wrong. The functional sections 2.1-2.7 are unchanged and my spot checks match (T1 table, T4 summaries, empty-packet kills 332/340/367).

## 2. Refuted

| # | Draft claim | Evidence | Correction |
|---|---|---|---|
| R1 | 3.2 footer: "All 12 cells: 86,400/86,400 written, 0 dropped." | Every focus16_av19 cell has `summary.written` = `produced` = 28,800 (16 cams x 60 fps x 30 s). 86,400 is the sum of 3 reps per writer, as in `RES/BENCH.md` lines 92-95. | "Each of the 12 cells: 28,800/28,800 written, 0 dropped (86,400 per writer over 3 reps)." |
| R2 | 2.10 (core_av19): "files p50 grows with camera count; the containers barely do (1080p30 below)" | Same table, 1 to 16 cams: files 1.324 to 3.368 (2.5x), append 0.195 to 0.679 (3.5x), mkv_flush 0.324 to 0.818 (2.5x), fmp4_frame_flush 0.311 to 0.958 (3.1x) (`write_ms_all.p50`, core_av19 1080p30 JSONs). In relative terms the containers grow as much as files or more. | "files p50 rises by 2.0 ms from 1 to 16 cams. The one-file layouts are nearly flat up to 8 cams, then rise 2.5-3.5x at 16 cams (+0.48 to +0.65 ms)." |
| R3 | 2.11 inferred: "process_shared uses a third to a half of the bench CPU and roughly doubles tick->written p99" | Bench CPU ratio, shared/thread (`our_cpu_s`/30, medians): files 0.34/0.69 = 0.49, append 0.29/0.70 = 0.42, mkv_flush 0.26/0.93 = 0.28. tick->written p99 ratio: files 7.49/5.98 = 1.25x, append 4.49/2.10 = 2.1x, mkv_flush 5.44/2.62 = 2.1x (`models16_av19_shared_vs_thread/*.json`). | "process_shared used 28-49 % of the thread model's bench CPU and raised tick->written p99 by 1.25x (files) to 2.1x (append, mkv_flush)." Implication 6 says "doubled tick->written p99" and needs the same fix. |
| R4 | 2.10: "the same config run in two different items differs by more than the within-item rep range" (files thread table: p99.9 and bench CPU) | The rep ranges overlap. files p99.9 is 20.3 (12.8-29.5) in focus16_av19 and 8.4 (7.0-19.3) in models16_av19. Bench CPU is 1.09 (0.75-1.13) vs 0.69 (0.67-0.78). files p50 is the same in both items (2.111 vs 2.098). Only append p50 has disjoint ranges: 0.553 (0.539-0.586) vs 0.365 (0.355-0.520). | "The medians of the same config differ between items: files p99.9 20.3 vs 8.4 ms and bench CPU 1.09 vs 0.69, with overlapping rep ranges. append p50 0.553 vs 0.365 ms, with disjoint ranges." Keep "cause not attributed". |
| R5 | Implication 6: process_shared "doubled tick->written p99" | Same as R3: files rose 1.25x. | "raised tick->written p99 1.25-2.1x". |

## 3. Weak (survives with the fix)

| # | Draft claim | Problem | Fix |
|---|---|---|---|
| W1 | 2.14: Electron 35/45 MJPEG errors, citing `RU/results/chromium_codecs/tables.md` lines 87-100 and 127-131 | Those lines hold vp9/vp8/h264/hevc AVI rows and ffv1 rows, not MJPEG. The MJPEG rows are lines 105-119 (`mjpeg_422__{mp4,fmp4,mkv,mov,avi}`) and 165-176 (`mjpeg_camera__{mkv,avi,mov,mp4}`). They also include C156. The claim itself holds. | Cite lines 105-119 and 165-176. |
| W2 | Header: "measured (other topic): those camera JPEGs are about target A, nearest IJG q94" | The measured part is the q94 quantisation tables (`RU/results/intra_compare/camera_jpeg_quality.md`). Target A is libjpeg-turbo q94 on raw YUY2. HANDOFF 1.1 labels "about as faithful as the camera's own JPEG" as **inferred**, and HANDOFF line 182 notes that the cameras' 1080p JPEGs are much smaller than turbo q94 on YUY2 (cause unanswered). | "measured: the camera JPEGs' tables are nearest IJG q94. inferred (HANDOFF 1.1): about target A." |
| W3 | Section 6: the `variants` (mkv defaults, cluster1, fmp4_1s, hybrid) and mkvseg10 write cells: "Their write cost under PyAV 19.0.2 on a quiet machine is NOT VERIFIED" | The quiet run's CR-FRAG-MJPEG-PYAV19 (item 19) measured the unpaced single-writer mux cost and overhead for mkv, mkv+fp, mkv_cl0+fp, fmp4 fragment variants, seg_mkv_1/10/60, rawidx and folder under PyAV 19.0.2, with 3000 frames x 3 reps (`RU/results/crash_resilience/bench/fragment_overhead_mjpeg_pyav19.json`). `RU/results/BENCH_QUEUE_2300.md` lines 238 and 240 dropped the WT variants for exactly that reason. | Cross-reference CR-FRAG-MJPEG. Narrow NOT VERIFIED to the multi-camera paced cells. |
| W4 | Implication 2: giving up a standard container "buys about 0.25-0.3 ms per write at p50 and about 0.3 logical CPUs (append vs mkv_flush)" | That range is from focus16_av19 only (0.808-0.553 = 0.255 ms; 0.90-0.63 = 0.27 CPUs). models16_av19 thread gives 0.846-0.365 = 0.48 ms and 0.93-0.70 = 0.23 CPUs. long_av19 gives 1.003-0.479 = 0.52 ms and (716.6-483.5)/600 = 0.39 CPUs. | "0.25-0.52 ms at p50 and 0.23-0.39 logical CPUs across the three quiet items". The conclusion is unchanged. |
| W5 | 2.2 inferred: the WriteFile premise "holds only because every writer here writes unbuffered (code: `SCR/wt_common.py:146,177,195`)" | Those lines are the `_Idx`, files and append opens. The container writers go through libavformat's AVIO buffer, which is why mkv defaults and fmp4_1s lose frames. "Every writer" over-reaches. | "because the files and append writers and the sidecar index write unbuffered". |
| W6 | Section 5 "Background load" and section 7 "nothing else running" | The runner flagged "leftover processes after item (listed, not killed)" on 9 of 10 WT items: Claude-session bash/uv/python watcher processes, one under the skellycam `.venv`. The pre-item top-10 also lists claude.exe and Code.exe (`RU/results/BENCH_RUN_2300_LOG.jsonl`, `flags`, `leftover_processes`, `load_before.top10_cpu_s_in_window`). `RES/BENCH.md` line 30 explains these as monitoring shells. | Add one bullet: the flag, what it listed, and that no bench process was left behind (BENCH.md line 30). |
| W7 | 2.9: item totals vs cell sums, "core 116.2 vs 87.5" | The JSON sum of the 32 WT-CORE-AV19 cells is 87.58 CPU-s, so 87.6 (BENCH.md line 51 truncates to 87.5). WT-CORE60-AV19 is left out: 37.7 for the item vs 30.78 for its cells. | "core 116.2 vs 87.6; core60 37.7 vs 30.8". |
| W8 | 2.8: "Grab-late max was 1.1-2.0 ms in focus16 (medians per writer)" | The medians per writer are files 1.286, append 1.660, mkv_flush 1.879 and fmp4_frame_flush 2.002. Per rep the range is 1.07-2.29 (`grab_lateness_ms_all.max`). | "1.3-2.0 ms (medians per writer; 1.1-2.3 over all reps)". |

## 4. Checked and confirmed

| Claim group | Evidence opened | Result |
|---|---|---|
| Version rule: 77 cells + first_read_5000 + usability_18000 all PyAV 19.0.2 / libavformat 63.1.102 | `env` of every JSON | match |
| 2.8: 77/77 written = produced, 0 dropped, 0 late; 12 + 18 + 44 + 3 cells | recompute script | match |
| 2.8 long cells: 576,000 frames, 94,163,436,720 B, 156.94 MB/s, files_written 576,016, disk delta 106.19/95.64/91.90 GB, delete 53.0/4.4/4.4 s, grab-late max 1.28/1.99/2.60 | `long_av19/*.json` | match |
| 2.8 focus16 disk delta medians 2.03-2.62 GB vs payload 4.71 GB; tick->written max for files 26.3 (26.1-167.9); slots 172 | focus16_av19 | match |
| 2.8 build_s 3.77/0.33/0.83/0.41 s, 996.8 MB; MB/s arithmetic | `usability_18000.json` | match |
| 2.9 idle baselines 1.531/1.469/1.234 (MsMpEng), 1.344/1.203/1.219 (SearchIndexer) | `idle_baseline_av19.jsonl` | match |
| 2.9 focus16 MsMpEng 26.8/1.19/1.52/1.16 with ranges; long 558.7/19.9/25.7; core files table (12 values); one-file layouts 0.41-1.34 | cell JSONs | match |
| 2.9 per-file arithmetic 0.97/0.93/1.5-1.7 ms | from the JSON values | match |
| 2.9 item totals 114.3, 649.9, 116.16; no scan events; cell sums 93.91, 604.3 | LOG.jsonl, recompute | match (core sum, see W7) |
| 2.10 focus16 p50/p99.9/max, bench CPU, sys busy % (all four writers, all ranges) | focus16_av19 | match |
| 2.10 long table (p50, p99.9, max, tick p99.9) | long_av19 | match |
| 2.10 core 1080p30 p50 table (16 values) | core_av19 | match (wording, see R2) |
| 2.10 daytime p50 1.299/0.179/0.260/0.266, files CPU %/cam 3.84 vs 6.82; daytime env 18.0.0; ratios 1.6-3.2x | `RES/bench/focus16/*.json`, focus16_av19 | match |
| 2.11 models16 table (36 values) and 0 drops in 18 cells; process_shared CPU accounting (writer CPU split per cam, summed once) | models16_av19 JSONs; code `SCR/bench_write.py:146`, `:387-389` | match (ratio wording, see R3) |
| 2.12 first read 20.594/20.594/0.186/0.156/0.088/0.031/0.084/0.000; 276,716,591 B; 4.1 ms, 111x; 3000-file 11.35 s (av 18.0.0) | `first_read_check_{5000,3000}.json` | match |
| 2.12 usability table, shutil copies, open_meta 0.412/0.006, stream_frames 0, alloc 1.022 GB, 4.35/3.59 ms per file, item MsMpEng 193.36 | `usability_18000.json`, LOG.jsonl | match |
| 2.13 fsync policies: 16.3 us / 2484 MB/s; 409.3 / 669.0 / 8.74 ms / 127; 16.1 / 883.4 / 4.17 ms / 1066 | `crash_resilience/bench/fsync_pyav19.json` (medians) | match |
| Section 5: affinity "pcores" on all WT lines; CPU-before means 3.3-6.8 %; SearchIndexer 8.48 / 9.83 CPU-s; no load_over_15pct; MsMpEng 0.03125/0.15625 | LOG.jsonl, first_read_5000 | match |
| Code: bench_write.py:7-11, 19-20, 22, 170, 233-237, 269-278, 307, 338, 350, 384-389, 413; wt_common.py:41-42, 144-220, 295, 304-305; run_queue.py:21-22, 441-446 (affinity set per item); idle_baseline.py:20-47 | files opened | match |
| Queue citations: BENCH_QUEUE_2300.md line 238 (core reduced, fsync and mkvseg10 dropped), line 243 (usability_1h replaced) | file | match |
| Section 7 commands: item commands equal `results/bench_queue_2300.json`; `run_queue.py` has `--only` and `--deadline`; the scratchpad scripts exist | files | match |
| Source lines: matroskaenc.c 2613, 3231-3236, 3602-3603; mux.c 820-827, 1075-1092, 1180-1191, 1230-1235; RFC 9559 quote | fetched n9.0.2 copies and rfc9559.txt lines 1003-1005 | match, exact |
| Section 8 old entries (models16 0.262-0.279 vs 0.920-1.380; usability_27000 116.42 / 0.009 / 0.442 / 1.008; MsMpEng 31.7 vs 7.1) | `models16_files_rerun`, `models16`, `usability_27000.json` (av 18.0.0), daytime focus16 | match |
| 2.14 background files exist (p11 298/359 MKV rows; p3v, p3) | frame_ring_buffer results | present |
