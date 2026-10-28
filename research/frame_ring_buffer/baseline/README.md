# Baseline benchmarks: the current SkellyCam frame pipeline (HEAD 23ccbf20)

These benchmarks measure the SkellyCam pipeline as it is at `23ccbf208e43879bfc74fc01049e5af2a623933d`, using the real
SkellyCam classes from the SkellyCam venv (`C:\Users\Dom\GitHub\freemocap\skellycam\.venv`). No SkellyCam source file is
modified. Where a benchmark wraps or substitutes something, it does so inside the benchmark process only, and the script
docstring says what it changes. Every multi-process benchmark uses `multiprocessing` spawn, which is what SkellyCam uses
on Windows.

Reference sizes: 1280x720 and 1920x1080, BGR uint8 x3. That is SkellyCam's native layout: a `frame_metadata` record of
632 B followed by an HxWx3 image, giving 2,765,432 B per record at 720p and 6,221,432 B at 1080p
(`results/f_copies.md`). Ring lengths are 388 slots at 720p and 172 at 1080p (`results/a_write.json`, `ring_len`).

## How to run

Run everything from `C:\Users\Dom\GitHub\freemocap\skellycam` with `PYTHONIOENCODING=utf-8` set (SkellyCam logs at TRACE
level to the console, and that output contains non-cp1252 characters). In cmd.exe: `set PYTHONIOENCODING=utf-8`; in PowerShell
(the default shell on this machine): `$env:PYTHONIOENCODING='utf-8'`; in Git Bash: `export PYTHONIOENCODING=utf-8`.
To record machine load around a run (as the 20261027 re-run did), prefix any command below with
`.venv\Scripts\python.exe research\frame_ring_buffer\baseline\run_with_load.py <name> <log file> <timeout_s> --` (see the
"20261027 idle re-run" section).

| script | what it measures | command | outputs |
|---|---|---|---|
| `bench_a_write.py` | (a) `put_frame` latency and the maximum sustained rate, for 1 to 5 spawned writer processes at both sizes, plus a single-copy reference | `.venv\Scripts\python.exe research\frame_ring_buffer\baseline\bench_a_write.py` | `results/a_write.{json,md}` |
| `bench_b_read.py` | (b) every reader style in the code (latest, by index, next, multiframe, by number) against views; cold and warm reads; 5 interleaved rounds | `... bench_b_read.py` | `results/b_read.{json,md}` (the 2026-10-25 `b_read_run1_sequential.*`, from an earlier version of the script, is only in `results_provisional_20261025/`) |
| `bench_c_record.py` | (c) real `VideoRecorder.create` and `record_frame`, 5 processes, paced at 60 fps for 20 s and unthrottled for 10 s, with CPU% and frames counted in the output files | `... bench_c_record.py` | `results/c_record.{json,md}` |
| `bench_d_ui.py` | (d) real UI path: `get_latest_multiframe` / `get_images_by_frame_number` followed by `create_frontend_payload`, 5 cameras, relay-style 10 ms loop | `... bench_d_ui.py` | `results/d_ui.{json,md}` |
| `bench_e_e2e.py` | (e) the REAL `WorkerRegistry` / `CameraGroupManager` / camera-process stack, 5 synthetic 60 fps cameras, recording for 30 s, plus a UI consumer | `... bench_e_e2e.py <720p\|1080p> <mjpeg\|memcpy> <ui\|noui> 30` (set `BENCH_E2E_REP=_rep2` for repeats). The summary has 8 runs: `720p memcpy ui` (+ `_rep2`), `720p mjpeg ui`, `1080p memcpy ui` (+ `_rep2`), `1080p mjpeg ui` (+ `_rep2`), `1080p mjpeg noui` | `results/e_e2e_*.json`, `results/e_e2e_summary.md` (built by `summarize_e2e.py`) |
| `bench_f_copies.py` | (f) bytes copied per frame on the record and UI paths, by instrumenting real calls | `... bench_f_copies.py` | `results/f_copies.{json,md}` |
| `bench_g_decode_ref.py` | (g) the cost of the e2e camera stand-in (`cv2.imdecode` vs `memcpy`). Not SkellyCam code. | `... bench_g_decode_ref.py` | `results/g_decode_ref.{json,md}` |
| `repro_type_overloads_spawn.py` | spawn-child crash caused by `type_overloads.py` L23 | `... repro_type_overloads_spawn.py` | `results/repro_type_overloads_spawn.txt` |
| existing diagnostics | `check_shm_speed.py`; `pytest test_shared_memory.py`; the same plus `test_camera_orchestrator.py` and `test_frontend_payload_and_recording.py` | the `CMD:` first line of each output file (the last line is the exit code) | `results/diag_check_shm_speed.txt`, `results/diag_pytest_shared_memory.txt`, `results/diag_pytest_three_files.txt` |
| `run_with_load.py` | (added 20261027) runs one command and records system CPU %, memory % and top processes in a 3 s window before and after it, and background CPU about once a second while it runs; kills any leftover child | `... run_with_load.py <name> <log> <timeout_s> -- <command>` | `results/load_<name>.json`, `results/<log>` |
| `summarize_load.py` | (added 20261027) tabulates every `load_*.json` | `... summarize_load.py` | `results/load_summary.md` |
| `env_snapshot.py` | (added 20261027) hardware, OS, power plan and package versions | `... env_snapshot.py` | `results/environment_system.json`, `results/environment_python.json` |

Environment: `results/environment_system.json` (CPU, RAM, disk, OS, power plan) and `results/environment_python.json`
(package versions). Each result JSON also has an `env` block with the system CPU load measured just before that run and a
list of the other Python processes running at the time.
Summary: i7-14700K (20 cores / 28 threads), 64 GB DDR5 running at 4000 MT/s, WD_BLACK SN850X 4 TB NVMe, Windows 11 Home
build 26300, power plan Balanced, Python 3.12.13 (MSC v.1944), numpy 2.2.6, opencv-contrib-python 4.12.0.88,
av 18.0.0, psutil 7.2.2, polars 1.43.0 (now present in the SkellyCam venv), uvicorn 0.51.0. No C/C++ code was compiled
for these benchmarks.

**Keeping the cited results (added 2026-10-28, REVISION stage).** Re-running a command above writes fixed file names into
`results/` and overwrites the files the reports cite. To re-run without touching them, first set
`$env:FRAME_PIPELINE_RESULTS_DIR = '<some folder>'`: every stage script (via `research/frame_ring_buffer/fp_paths.py`) then
writes to `<some folder>\<stage>\results\` instead. `reproducibility/protect_originals.py snapshot|collect|restore` is the
fallback for older copies of the scripts.

**Summaries merge repeats.** `summarize_e2e.py` with no arguments tabulates every `results/e_e2e_*.json`, so a repeat run (`BENCH_E2E_REP`) adds a row to `e_e2e_summary.md`. To summarize a chosen set, pass a glob and an output name: `... summarize_e2e.py "e_e2e_*_repro*.json" e_e2e_repro_summary.md`. The 2026-10-28 revision stage's single-change variants (`bench_e2e_variants.py`, `analyze_gap_detector.py`, `bench_h_deflate.py`) are documented in `../revision/README.md`.

## 20261027 idle re-run

Run on the night of 2026-10-27/28 (00:59 to 01:27 local) on the same machine, at the same commit (HEAD
`23ccbf208e43879bfc74fc01049e5af2a623933d`, no source changes), with the same scripts and configs (5 cameras, 1280x720 and
1920x1080 BGR, 60 fps target). Nobody was using the machine and no other Python process was running when it started.
`results/` now holds tonight's outputs. The 2026-10-25 outputs are preserved unchanged in `results_provisional_20261025/`
and the old structured result in `../study_state/baseline_result_provisional_20261025.json`.

Every step was launched through `run_with_load.py`, in this order: a, b, c, d, f, g, the 8 e2e runs, `summarize_e2e.py`,
`repro_type_overloads_spawn.py`, the 3 diagnostics, each separated by a 15 s pause. Exact command list:
`results/load_*.json` field `command`.

### Machine load: every run was idle (`results/load_summary.md`, built by `summarize_load.py` from `results/load_*.json`)

Idle rule: background CPU (all processes outside the benchmark's process tree, % of the whole 28-thread machine) mean < 10% and
p95 < 10% while the run was going, and system CPU < 10% in the 3 s windows before and after.

| | range across all 19 runs |
|---|---|
| system CPU before / after the run | 2.9-5.1% / 3.3-5.1% |
| memory in use before / after | 35.6-37.9% / 35.6-37.8% |
| background CPU during, mean / p95 / max | 2.0-4.1% (corrected 2026-10-28; was 2.0-4.0%) / 2.9-7.2% / 2.9-11.2% |
| top background processes | before/after: PreSonusHardwareAccessService, Corsair.Service.CpuIdRemote64, MsMpEng, System, WmiPrvSE (each under 1%). During runs (1 s samples, `samples[].top_background`), the largest single values were: `System` 7.7% (c_record, t=41 s, when MSMF was writing files), MsMpEng 2.7%, VS Code 2.5%, firefox 1.5%. Only 2 of all samples had background above 8%: a_write t=116 s at 11.2% (three VS Code processes) and c_record t=41 s at 10.2% (`System`). |
| verdict | **idle** for every run. `summarize_e2e` and `diag_check_shm_speed` ended in under 1 s (no sample during the run), but were idle before and after; neither produces a timing. |

The 2026-10-25 run had system CPU of 11-64% just before each run (`results_provisional_20261025/*.json`, `env.system_cpu_pct_1s_before_run`).
Second measure: system CPU minus the benchmark tree reached a mean of 9.1-10.3% in the heaviest runs (c_record and the 1080p mjpeg
e2e runs), against 3.6-4.0% from the per-process sum. That gap grows with the benchmark's own load (5.5-6.2% at 1080p memcpy (corrected 2026-10-28; was 5.5%), 9-10% at
1080p mjpeg), so it most likely comes from kernel work the benchmark causes (disk writes of 2 GB per e2e run, page faults) and
from sampling-window misalignment, not from other workloads. This is an inference, not a measurement.

### README steps fixed in this re-run

1. `set PYTHONIOENCODING=utf-8` is cmd.exe syntax. The default shell here is PowerShell, so the PowerShell and Git Bash
   forms are now given too. The benchmark commands themselves worked as written.
2. The e2e row gave only the argument pattern. It now lists the 8 configurations that make up `e_e2e_summary.md`.
3. In the 2026-10-25 output, `diag_pytest_shared_memory.txt` began with a `CMD:` line for `test_shared_memory.py` alone, but its
   body held the three-file run (58 passed, 1 failed). The two runs now go to two files, `diag_pytest_shared_memory.txt` and `diag_pytest_three_files.txt`.
4. `environment_*.json` had no documented command, so `env_snapshot.py` was added.
5. `b_read_run1_sequential.*` came from an earlier version of `bench_b_read.py` and the documented command cannot reproduce it. It was removed from
   `results/` and stays in `results_provisional_20261025/`.
6. No step recorded machine load, so `run_with_load.py` and `summarize_load.py` were added. They also capture each command's output
   as `results/*_stdout.log`, which the old README did not document.
7. `bench_common.SCRATCH_TMP` was hard-coded to the 2026-10-25 session's scratch folder when these runs were made. On 2026-10-28,
   when that folder was deleted, it was changed to `%TEMP%\skellycam_frame_pipeline_tmp\bench_tmp`, the same root that `prototypes/` and `cpp/` use
   (`bench_common.py` L25). The 20.8 MB that bench_f left
   there tonight was deleted after its sizes were logged in `results/bench_tmp_leftover_sizes_before_delete.txt`. Empty `c_rec_*` folders remain.

No script hung at exit this time. Every run finished with its expected exit code: 0, except exit 1 for `check_shm_speed.py`
(ImportError) and for the three-file pytest run (the known failure). No child process was left behind
(`killed_leftover_pids` is empty in every `load_*.json`).

### Comparison: 2026-10-25 (loaded, provisional) vs 20261027 (idle)

Old values come from `results_provisional_20261025/<file>` and new values from `results/<file>`, using the same file names.
Change is (new - old) / old, or a plain difference where marked.

| metric | file | 2026-10-25 | 20261027 | change |
|---|---|---|---|---|
| put_frame 720p N=1 median / p99 ms | a_write.md | 0.629 / 0.827 | 0.562 / 0.719 | -11% / -13% |
| put_frame 720p N=1 max fps | a_write.md | 1539 | 1718 | +12% |
| put_frame 720p N=5 median / worst p99 ms | a_write.md | 1.167 / 1.891 | 1.145 / 1.916 | -2% / +1% |
| put_frame 720p N=5 slowest-camera fps | a_write.md | 819 | 839 | +2% |
| put_frame 1080p N=1 median / p99 ms | a_write.md | 1.352 / 1.825 | 1.326 / 1.775 | -2% / -3% |
| put_frame 1080p N=1 max fps | a_write.md | 717 | 740 | +3% |
| put_frame 1080p N=5 median / worst p99 ms | a_write.md | 2.936 / 4.412 | 2.747 / 4.040 | -6% / -8% |
| put_frame 1080p N=5 slowest-camera fps (aggregate GB/s) | a_write.md | 337 (10.57) | 353 (11.11) | +5% |
| put_frame 1080p first-lap median ms, N=1..5 | a_write.md | 2.90-3.22 | 2.70-3.93 | similar |
| single-copy reference median ms: 720p N=1 / N=5, 1080p N=1 / N=5 | a_write.md | 0.089 / 0.263, 0.174 / 0.644 | 0.089 / 0.244, 0.172 / 0.640 | 0 / -7%, -1% / -1% |
| single-copy aggregate GB/s, N=2..5 | a_write.md | 38.3-49.5 | 45.1-52.6 | higher |
| production vs single-copy bandwidth (x less) | a_write.md | 4-7x | 4.1-7.2x | same |
| read 1080p cold median ms: by_index / latest_reused / latest_alloc / next | b_read.md | 0.498 / 0.534 / 1.211 / 0.559 | 0.423 / 0.421 / 1.179 / 0.483 | -15% / -21% / -3% / -14% |
| read 1080p multiframe_latest median / p99 ms | b_read.md | 2.415 / 11.34 | 2.353 / 7.29 | -3% / -36% |
| read 1080p multiframe_by_number median / p99 ms | b_read.md | 6.147 / 15.36 | 6.628 / 13.54 | +8% / -12% |
| read 720p cold median ms: by_index / latest_reused / multiframe_latest / by_number | b_read.md | 0.422 / 0.297 / 1.513 / 4.065 | 0.215 / 0.208 / 1.063 / 3.153 | -49% / -30% / -30% / -22% |
| read frame_number mismatches | b_read.md | 0 | 0 | same |
| record 5x720p paced: fps; record_frame median / p99 / max ms | c_record.md | 60.0; 0.97 / 2.36 / 4.22 | 60.0; 0.99 / 1.38 / 2.93 | same; +2% / -42% / -31% |
| record 5x720p paced: summed CPU % (per camera) | c_record.md | 380 (70-84) | 476 (92-101) | +25% |
| record 5x1080p paced: fps; record_frame median / p99 / max ms | c_record.md | 60.0; 2.18 / 5.22 / 9.28 | 60.0; 2.17 / 4.05 / 6.47 | same; 0% / -22% / -30% |
| record 5x1080p paced: summed CPU % (per camera); writes over 16.7 ms | c_record.md | 1169 (225-244); 0 | 1207 (232-246); 0 | +3%; same |
| record unthrottled write() return rate, fps per camera: 5x720p / 5x1080p / 1x720p / 1x1080p | c_record.md | 292 / 140 / 1013 / 522 | 359 / 176 / 1260 / 676 | +23% / +25% / +24% / +29% |
| record unthrottled release() s: 5 cams / 1 cam | c_record.json `release_s` | 1.8-2.2 / 5.3-6.5 | 5.05-5.35 / 6.33-7.12 | longer |
| DERIVED encode fps per camera (frames / (elapsed + release)): 5x720p / 5x1080p / 1x720p / 1x1080p | c_record.json | 246 / 116 / 613 / 342 | 237 / 117 / 772 / 395 | -4% / +1% / +26% / +15% |
| record: file frames == written | c_record.md | yes (all) | yes (all) | same |
| UI 720p SkellyCam path: payloads/s; total median / p99 ms | d_ui.md | 59.9; 6.28 / 11.20 | 60.5; 4.70 / 7.90 | +1%; -25% / -29% |
| UI 1080p SkellyCam path: payloads/s; shm copy / build / total median ms; p99 | d_ui.md | 43.7; 3.39 / 7.24 / 10.90; 23.76 | 46.0; 2.74 / 6.59 / 9.39; 17.43 | +5%; -19% / -9% / -14%; -27% |
| UI 1080p FreeMoCap path: payloads/s; total median / p99 ms | d_ui.md | 37.9; 15.43 / 27.82 | 41.7; 12.87 / 15.58 | +10%; -17% / -44% |
| UI 1080p no sleep: payloads/s (distinct); total median ms | d_ui.md | 70.7 (58.2); 13.81 | 110.3 (60.0); 8.84 | +56%; -36% |
| e2e 5x1080p mjpeg + UI: fps per camera (2 runs) | e_e2e_summary.md | 44.01 / 46.78 | **53.56 / 53.57** | +22% / +15% |
| e2e 5x1080p mjpeg + UI: sensor frames never grabbed, sum of 5 cameras | e_e2e_summary.md | 2398 / 1984 (about 25%) | **964 / 964 (10.7% of 9009 / 9014)** | -60% / -51% |
| e2e 5x1080p mjpeg no UI: fps; never grabbed | e_e2e_summary.md | 46.11; 2084 | **55.94; 605 (6.7%)** | +21%; -71% |
| e2e 5x1080p mjpeg + UI: grab interval median ms; retrieve / put_frame / record_frame median ms | e_e2e_summary.md | 22.24 / 21.15; 12.27-11.22 / 4.23-4.07 / 1.34-1.30 | 18.69 / 18.69; 10.12-10.31 / 3.64-3.73 / 1.12-1.19 | -16% / -12%; -8% to -18% each |
| e2e 5x1080p mjpeg + UI: sensor tick -> written median / p99 / max ms | e_e2e_summary.md | 27.3 / 39.5 / 46.7 | 23.9 / 34.4 / 37.4 | -12% / -13% / -20% |
| e2e 5x1080p mjpeg + UI: finalizer "Mean Framerate" | e_e2e_1080p_mjpeg_ui.json `finalizer_stats` | 44.52 Hz | 53.93 Hz | +21% |
| e2e 5x1080p memcpy + UI: fps; never grabbed (2 runs) | e_e2e_summary.md | 59.99 / 59.95; 0 / 5 | 59.99 / 59.99; 0 / 0 | same |
| e2e 5x1080p memcpy: put_frame median ms; tick -> written median / p99 ms | e_e2e_summary.md | 2.76 / 2.33; 5.0 / 10.4-14.5 | 2.14 / 1.96; 4.0-4.1 / 7.6-11.7 | -22% / -16%; lower |
| e2e 5x720p mjpeg + UI: fps; never grabbed; tick -> written median / p99 / max ms | e_e2e_summary.md | 59.99; 0; 6.7 / 12.9 / 20.0 | 60.00; 0; 5.5 / 7.7 / 10.9 | same; same; lower |
| e2e 5x720p memcpy + UI: fps; never grabbed (2 runs) | e_e2e_summary.md | 58.76 / 60.00; 186 / 0 | 60.00 / 60.00; 0 / 0 | the 186 did not recur |
| e2e UI payloads/s at 1080p (mjpeg; memcpy) and at 720p | e_e2e_summary.md | 35.7, 34.8; 41.0, 38.3; 55.0-60.4 | 36.9, 36.6; 39.9, 40.8; 57.0-58.9 | similar |
| e2e summed child CPU %, 1080p mjpeg + UI | e_e2e_summary.md | 1184 / 1193 | 1345 / 1361 | +14% (more frames processed) |
| e2e: recorded frames consecutive; files == recorded; stop_error; kill flag | e_e2e_*.json | yes; yes; null; false (all runs) | yes; yes; null; false (all 8 runs) | same |
| bytes copied per frame or multiframe (all rows) | f_copies.md | see (f) below | identical byte counts; tracemalloc peaks differ by under 200 B | same |
| stand-in decode 1080p imdecode median ms, 1 / 5 procs | g_decode_ref.md | 6.98 / 7.69 | 7.30 / 7.73 | +5% / +1% |
| stand-in memcpy 1080p median ms, 1 / 5 procs | g_decode_ref.md | 0.35 / 1.18 | 0.35 / 1.15 | same |
| stand-in 720p imdecode / memcpy median ms (1 proc) | g_decode_ref.md | 3.05 / 0.15 | 3.21 / 0.15 | +5% / same |
| check_shm_speed.py | diag_check_shm_speed.txt | ImportError L8, exit 1 | ImportError L8, exit 1 | same |
| pytest test_shared_memory.py; three files | diag_pytest_*.txt | 21 passed; 58 passed 1 failed | 21 passed; 58 passed 1 failed (test_video_file_path_from_config) | same |
| type_overloads spawn repro | repro_type_overloads_spawn.txt | child exitcode=1 | child exitcode=1 | same |

### What changed in the conclusions

* **5x1080p60 with in-loop MJPEG decode still misses 60 fps on an idle machine, but by less.** It reaches 53.6 fps with the UI
  (2 runs, 964 sensor frames never grabbed each, 10.7%) and 55.9 fps without it (1 run, 6.7%), against 44-47 fps (about 25%
  lost) under load. The serial per-iteration work is still above the 16.7 ms budget: retrieve about 10.1-10.3 ms, plus
  put_frame about 3.6-3.7 ms, plus record_frame about 1.1-1.2 ms, giving a group interval median of 18.69 ms
  (`e_e2e_1080p_mjpeg_ui*.json`, `per_camera.*`; loop: [`opencv_camera_loop.py` L67-117](https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera/opencv/opencv_camera_loop.py#L67-L117)).
  The memcpy bracket (no decode cost) holds 59.97-60.00 fps with 0-3 of about 9,000 sensor frames never grabbed (3 idle 1080p runs: 0 / 0 here, 3 in the 2026-10-28 reproducibility re-run, `../reproducibility/rerun/baseline/results/e_e2e_summary.md`), and 720p mjpeg holds 60.00.
  (2026-10-28 revision: the loop-body arithmetic in this bullet's original reading was incomplete; the 1080p mjpeg loop body is about 15.8 ms (finalizer 'TOTAL FRAME PROCESSING TIME') plus about 2.5 ms of lockstep gate idle per frame, and removing `copy.copy` alone raises the rate to 58.8-59.0 fps; see `../revision/README.md`.)
* **The UI now has a measurable cost on capture.** Without the UI consumer, 1080p mjpeg ran at 55.94 fps, against 53.56/53.57 fps with it.
  This is only 1 no-UI run in this re-run, so treat it as an indication (2026-10-28: a revision-stage repeat, `e2ev_head_1080p_mjpeg_noui_rep2`, gave 55.62 fps with 655 never grabbed, against 54.14 fps for HEAD with the UI in the same session; `results/e2ev_summary.md`). The 2026-10-25 run, under load, saw no difference (46.1 vs 44.0/46.8).
  The UI is still not the main limit: the decode-in-loop is.
* **The 1080p UI work (shm copy plus build) is about 9 ms per payload, not 11-14 ms.** (corrected 2026-10-28; was "The 1080p UI build is about 9 ms": 9.39 ms is the `total median`, shm copy 2.74 ms plus resize+JPEG+pack 6.59 ms, in `results/d_ui.md`.) That alone would allow about 110 payloads/s (no-sleep row). The SkellyCam
  relay runs `await_10ms()` and then the build in series in one loop ([`websocket_server.py` L189-212](https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/api/websocket/websocket_server.py#L189-L212)).
  Sleep plus build per payload caps the rate at 46.0 payloads/s in `d_ui` and 36.6-40.8 in the e2e runs. The old statement "the build cost
  alone keeps the UI below 60 fps" does not hold on an idle machine.
* **Disk writes still never lost a grabbed frame** (all 8 e2e runs and all 6 bench_c rows: consecutive frame numbers, files decode to the
  recorded count, `stop_error` null). Losses remain frames never grabbed, which SkellyCam's own statistics do not show (finalizer
  "Mean Framerate" 53.93 Hz with no gap reported).
* **Encoder throughput at 5 cameras did not change** (derived 117 fps per camera at 1080p, 237 at 720p). `write()` returns faster on
  the idle machine, so after the unthrottled runs the queued frames take longer to drain: `release()` took 5.0-5.4 s, against 1.8-2.2 s on 10-25.
  Paced 60 fps recording is unaffected (release 0.06-0.07 s, 0 writes over 16.7 ms). On the idle machine the paced runs used more
  encoder CPU than on 10-25: 476% vs 380% at 720p, and 1207% vs 1169% at 1080p. The cause was not investigated.
* **put_frame overhead is unchanged.** It still makes 2 full copies per frame
  ([`ring_buffer_shared_memory.py` L118-133](https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/ipc/shared_memory/ring_buffer_shared_memory.py#L118-L133), `f_copies.md`).
  Isolated it costs 1.326 ms at 1080p, against 0.172 ms for one copy (7.7x). Under e2e load it costs 1.96-2.14 ms (memcpy) and 3.49-3.73 ms (mjpeg).
* **Read-style round variance does not come from load.** In both runs the spread of round medians (for example 720p `latest_reused` 0.191-0.788 ms tonight)
  comes mostly from the first one or two of the 5 rounds. Rounds 3-5 agree within about 20% (`b_read.json` `cold_round_medians_ms`). The cause was not established.

The sections below ("Results" through "Limitations") describe the **2026-10-25 provisional run**. Its files are now in
`results_provisional_20261025/`; where those sections say `results/...`, read `results_provisional_20261025/...`. Use the
table above for current numbers.

## Results of the 2026-10-25 provisional run (headline numbers; files now in `results_provisional_20261025/`)

### (a) Write: `put_frame` (`results/a_write.md`)
Each spawned writer process writes as fast as it can for 10 s, after one full first lap of the ring.

| size | N | production put_frame median / worst p99 (ms) | per-camera max fps (slowest camera) | single-copy reference median (ms) |
|---|---|---|---|---|
| 720p | 1 | 0.629 / 0.827 | 1539 | 0.089 |
| 720p | 5 | 1.167 / 1.891 | 819 | 0.263 |
| 1080p | 1 | 1.352 / 1.825 | 717 | 0.174 |
| 1080p | 5 | 2.936 / 4.412 | 337 | 0.644 |

The first lap through fresh pages has a median of 2.9 to 3.2 ms at 1080p. The writer never caps throughput at 60 fps: even 5x1080p
unthrottled reaches 337 fps per camera. Throughput saturates at about 10.6 to 11.5 GB/s aggregate for production and
about 38 to 50 GB/s for a single copy, which means production achieves about 4 to 7x less useful bandwidth than one copy
would. When the machine is loaded the way the e2e run loads it (5 x encode + decode + UI, 60 fps), `put_frame` is slower than when run
alone: 1080p median 2.3 to 2.9 ms (memcpy mode) and 4.1 to 4.2 ms (mjpeg mode), against 1.35 ms isolated
(`results/e_e2e_summary.md`, column put_frame).

### (b) Read styles (`results/b_read.md`, 5 x 60 fps writers; "cold" means the first read after a new frame is published)
1080p cold medians: `get_data_by_index` (reused buffer) 0.50 ms, `get_latest_data` (reused) 0.53 ms, `get_latest_data`
(allocating) 1.21 ms, `get_next_data` 0.56 ms, view only 0.03 ms. Multi-frame reads (5 cameras): `get_latest_multiframe` 2.42 ms,
`get_images_by_frame_number` 6.15 ms (it allocates five records on every call because `_frame_recarray_cache` is never filled),
5 views 0.06 ms. The 720p values are noisy: round medians vary up to about 5x, as shown in the range column (corrected 2026-10-28; was "2 to 4x": `by_index_reused` ranged 0.228-1.064 ms, 4.7x). There were no frame_number
mismatches in any style.

### (c) Record (`results/c_record.md`)
The default `writer_fourcc` X264 resolves to the **MSMF** backend in every process. All files contained exactly the number of frames
written (each file was decoded and counted).

| size | 5 cameras, paced at 60 fps for 20 s | record_frame median / p99 / max (ms) | summed process CPU (100 = 1 logical CPU) | release() |
|---|---|---|---|---|
| 720p | 60.0 fps per camera, 0 writes over 16.7 ms | 0.97 / 2.36 / 4.22 | 380% (~70-84% per camera; corrected 2026-10-28, was ~74-84%) | 0.08 s |
| 1080p | 60.0 fps per camera, 0 writes over 16.7 ms | 2.18 / 5.22 / 9.28 | **1169%** (~225-244% per camera) | 0.09-0.10 s |

When unthrottled, `write()` returns faster than the encoder finishes: `release()` then takes 1.8 to 2.2 s with 5 cameras and
5.3 to 6.5 s with 1 camera (`c_record.json` `release_s`). The "unthrottled fps" column therefore measures how fast `write()`
returns, not how fast frames are encoded. Derived from the same JSON (frames / (loop time + release time)), the encode
throughput is about 245 fps per camera at 5x720p, about 116 fps per camera at 5x1080p, about 613 fps for 1x720p and about
342 fps for 1x1080p. These are derived numbers, not separate measurements.

### (d) UI path (`results/d_ui.md`)
Relay-style loop: `await_10ms`, then build. The ack is instant because no browser is attached, so these are upper bounds on the
server-side UI work.

| size | path | payloads/s | shm copy median (ms) | resize+JPEG+pack median (ms) | total median / p99 (ms) | payload KB |
|---|---|---|---|---|---|---|
| 720p | SkellyCam UI (`get_latest_multiframe`) | 59.9 | 2.21 | 3.59 | 6.28 / 11.20 | 153 |
| 1080p | SkellyCam UI | 43.7 | 3.39 | 7.24 | 10.90 / 23.76 | 337 |
| 1080p | FreeMoCap UI (`get_images_by_frame_number`) | 37.9 | 7.29 | 8.07 | 15.43 / 27.82 | 337 |
| 1080p | SkellyCam UI, no sleep (maximum rate) | 70.7 (58.2 distinct) | 3.96 | 9.67 | 13.81 / 21.88 | 337 |

At 1080p the build cost alone (about 11 to 14 ms of the main event loop per payload) keeps the UI below 60 fps. (Corrected 2026-10-28: 10.90-13.81 ms is the total of shm copy plus build; the build alone was 7.24-9.67 ms.) In the full
e2e run the UI reached 34.8 to 41.0 payloads/s at 1080p and 55 to 60 at 720p (`e_e2e_summary.md`).

### (e) End-to-end, real stack (`results/e_e2e_summary.md`)
5 cameras, 60 fps sensors, 30 s recording, UI consumer on unless stated otherwise.

| config | achieved fps per camera | sensor frames never grabbed (sum of 5 cameras) | frames in files == frames recorded | sensor tick -> frame written median / p99 / max (ms) |
|---|---|---|---|---|
| 720p, memcpy stand-in (2 runs) | 58.76 / 60.00 | 186 / 0 | yes / yes | 2.5/17.3/63.7 ; 2.1/3.6/9.1 |
| 720p, mjpeg stand-in | 59.99 | 0 | yes | 6.7 / 12.9 / 20.0 |
| 1080p, memcpy stand-in (2 runs) | 59.99 / 59.95 | 0 / 5 | yes / yes | ~5 / 9-15 / 23-30 |
| 1080p, mjpeg stand-in (2 runs) | **44.01 / 46.78** | **2398 / 1984** (about 25%) | yes / yes | 27 / 39 / 47 |
| 1080p, mjpeg stand-in, no UI | **46.11** | **2084** | yes | 27.0 / 39.8 / 45.3 |

Disk writes never lost a frame the loop had grabbed: every recorded frame number is consecutive, every file decodes to the
recorded count, and the real `RecordingFinalizer.validate_recording` passed in all runs (`stop_error: null`). Frames are lost
**before** the recorder sees them. When one lockstep iteration (retrieve, then putText, then `put_frame`, then `record_frame`) takes longer
than 16.7 ms on the slowest camera, the sensor's newer frame replaces the one that was never grabbed. At 1080p with an in-loop
MJPEG decode (retrieve median 11.2 to 12.3 ms under load, against 6.98 ms isolated in `g_decode_ref.md`), plus `put_frame` at
about 4.1 ms and `record_frame` at about 1.3 ms, the group interval rises to a median of about 21 to 22 ms. The SkellyCam frame numbers and
the finalizer's own statistics ("Mean Framerate: 44.52 Hz"; `finalizer_stats` in `e_e2e_1080p_mjpeg_ui.json`) still look
gap-free. Nothing in the ring itself was overwritten or dropped: the UI and recorder never lag the ring, and the recorder does not read the ring at all.
The 186 missed frames in the first 720p memcpy run come from group-wide stalls (grab interval max 89 to 130 ms on every
camera at once) during a period when other workloads were running on the machine (see Limitations). A repeat run had 0.

### (f) Bytes copied per frame (`results/f_copies.md`), cross-checked against the verified frame_copies list

| path, per frame | measured by instrumentation | verified-list entry | agrees? |
|---|---|---|---|
| put_frame: `copy.copy(data)` | 1 call, 6,221,432 B at 1080p (= 1.00 record, includes 632 B metadata) | W15 / "copy(data) heap copy" | yes. tracemalloc peak 6,223,816 B allocated per `put_frame` |
| put_frame: slot assignment | 1 call, 6,221,432 B | "slot assignment into shm" | yes |
| put_frame: index and flag traffic | 1 x 8 B `np.copyto` (index store) + 4 x 1 B `np.copy` (valid/first_written flag reads) | W17 | yes (tiny but 5 extra numpy calls) |
| record_frame: image to encoder | view of the private recarray (`np.shares_memory` True), 0 Python copies | R12 / CP11 | yes |
| record_frame: `cv2.rotate` | 0 B without rotation; 1 x 6,220,800 B with CLOCKWISE_90 | "rotate copy only when rotation is set" | yes |
| record_frame: `copy(frame_metadata)` | 1 x 632 B | "632 B metadata copy" | yes |
| **Record path total (no rotation)** | **2 full-record copies = 12.44 MB/frame/camera at 1080p, i.e. 3.73 GB/s at 5x1080p60, of which 1.87 GB/s (the copy.copy) is avoidable** | | |
| SkellyCam UI: shm to private (`get_latest_multiframe`) | 5 x `np.copyto` = 31,107,160 B per multiframe at 1080p | R28 / UI8 | yes |
| SkellyCam UI: `cv2.resize` 0.5 | 5 outputs = 7,776,000 B (1.25 images) | UI10 | yes |
| SkellyCam UI: `cv2.rotate` | 0 B without rotation; 5 x 6,220,800 B with rotation, done before the resize | UI9 | yes |
| SkellyCam UI: JPEG bytes and their copies | imencode output, then `tobytes()` copy, then slice-assign, then final slice copy (each about the payload size; 0.05 images per copy at 720p). The last three are counted analytically | UI12 / UI14 | yes (analytic) |
| FreeMoCap UI (`get_images_by_frame_number`) | same copies, plus a heap allocation of 31,111,210 B (5.00 images) per call, against 3,239,239 B (0.52 images) for `get_latest_multiframe` | R29 / H18 | yes |
| SkellyCam UI flag reads | 60 x `np.copy` of 1 B per multiframe (75 for the by-number path) | not listed | new: per-call overhead only |

Not countable from Python: copies inside the DSHOW/MSMF capture backend, inside the MSMF H.264 encoder, and inside the
websocket stack. These stay open questions, as they are in the verified list.

### Existing diagnostics
* `check_shm_speed.py`: ImportError at line 8 (`results/diag_check_shm_speed.txt`). This matches W29: the script is stale and cannot serve as a baseline.
* `pytest skellycam/tests/test_shared_memory.py`: **21 passed** with the normal conftest (`results/diag_pytest_shared_memory.txt`).
  W28 reported that collection failed on a missing polars. polars 1.43.0 is now installed in the venv, so that no longer happens.
  Running it together with `test_camera_orchestrator.py` and `test_frontend_payload_and_recording.py` gives 58 passed and 1 failed
  (`test_video_file_path_from_config`). That is the same `idx0` vs `idx-0` failure reported in R33.

### Incidental reproduction
`type_overloads.py` L23 evaluates `multiprocessing.queues.Queue` at import time while importing only `multiprocessing.sharedctypes`. A
spawned child whose first pickled argument is a SkellyCam ring DTO crashes during unpickling with `AttributeError` and
exit code 1 (`results/repro_type_overloads_spawn.txt`). This extends W30: the crash depends on argument order, not only on
whether the child receives a Queue at all. All benchmark scripts work around it with a top-level `import multiprocessing.queues`.

## Limitations (read before citing)
* **The machine was not idle.** Other sessions' research jobs (USB-camera, MJPEG, GigE and UDP benchmarks under
  `research/usb_cameras/...` and the GigE diagnostics, then at `skellycam/system/diagnostics/gige/...`, moved on 2026-10-28 to
  `research/gige_vision/hardware_tests/...`) were running throughout. The system CPU load measured just before
  each run ranged from 11% to 64% (`env.system_cpu_pct_1s_before_run`, `env.other_python_processes_at_start`). Absolute latencies,
  especially p99 and maximum values and the 720p read rows, are noisier than they would be on an idle machine. The 1080p mjpeg e2e result
  (44 to 47 fps) was reproduced in 3 runs, including one at 34% background load.
* **No real cameras were used.** Two DSHOW devices (indices 0 and 1) were detected, but other jobs were using them under a
  camera lock, so no real-camera run was attempted. The e2e camera is `FakeCapture`, which models a free-running
  sensor with buffer-size-1 ("latest frame wins") semantics. Whether DSHOW with `CAP_PROP_BUFFERSIZE=1` really discards frames in
  this way is an assumption. Whether DSHOW decodes MJPEG inside `retrieve()` (the mjpeg mode) or on a separate graph thread
  (closer to the memcpy mode) is an **open question**. The mjpeg and memcpy modes bracket that range. The mjpeg stand-in also adds one
  memcpy (`imdecode` output into the buffer) that an in-place backend decode would not have. Its synthetic JPEGs (q90, 241 KB at 720p and 540 KB at 1080p)
  may not match a real camera's MJPEG.
* Synthetic content (moving gradient + box + ±8 noise) determines the encode cost and file sizes. 1080p MSMF produced about 15.6 MB/s per camera.
  Real scenes will differ.
* Whether the MSMF H.264 encoder runs on the GPU or on the CPU was not established. The measured CPU (about 2.3 logical CPUs per 1080p60 camera)
  suggests a software encoder, but that is an inference.
* `bench_f_copies.py` runs single-process with counting wrappers (bytes per call do not depend on the process topology). The JPEG
  `tobytes`, slice-assign and slice-copy byte counts are analytic. The wrappers add overhead, so no timing from that script is used.
* Unthrottled record rows: `write()` is asynchronous, so the derived encode rates in (c) are estimates.
* Large temporary files were written under the scratch `bench_tmp` folder and deleted after their sizes were recorded. The e2e recordings were
  1.0 to 2.3 GB per run (`recording_total_bytes`), and the bench_c sizes are in `c_record.json`. `bench_tmp_leftover_sizes_before_delete.txt` lists the last leftovers (about 20.8 MB from bench_f).
  SkellyCam's own log file (`configure_logging` at import) was also written to its default log path.
* `bench_f_copies.py` (first run) and `bench_e_e2e.py` (first run) hung at interpreter exit after all results had been written,
  and were stopped by `timeout` (exit 124). Both scripts now end with `os._exit(0)`, as SkellyCam's own `entry_point` does.
