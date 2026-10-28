# Prototype benchmarks: candidate optimisations of the SkellyCam frame pipeline

Stage: **prototypes**. Measured on 2026-10-28, 01:44 to 03:20 local, on the same machine as the 20261027 idle baseline re-run,
against SkellyCam HEAD `23ccbf208e43879bfc74fc01049e5af2a623933d` (checkout unchanged; no SkellyCam source file modified).
Reference sizes: 1280x720 and 1920x1080 BGR uint8 (both used everywhere unless a row says otherwise). Target: 5 cameras x 60 fps.

Every script here is prototype code, not SkellyCam code. Where a row measures SkellyCam behaviour it imports the real class
from the SkellyCam venv (`CameraSharedMemoryRingBuffer`, `CameraGroupSharedMemory`, `create_frontend_payload`,
`VideoRecorder`, `PyavVideoWriter`); where a prototype replaces one SkellyCam method it does so on one instance inside the
benchmark process only, and the script says so. All multi-process benchmarks use `multiprocessing` spawn, as SkellyCam does on Windows.

The partial results of the stopped 2026-10-25 prototype agent (machine loaded, provisional) are kept unchanged in
`results_partial_20261025/`. **Everything in `results/` was re-run tonight.**

## Machine state: every measurement ran idle (except P10's last row, see below)

All steps ran through `run_with_load.py` (a copy of `baseline/run_with_load.py` that writes into `prototypes/results/`).
Idle rule (same as the baseline): background CPU (all processes outside the benchmark's tree, % of the 28-thread machine) mean < 10%
and p95 < 10% during the run, and system CPU < 10% in 3 s windows before and after it. Table: `results/load_summary.md`
(built by `summarize_load.py` from `results/load_*.json`).

| | range |
|---|---|
| system CPU before / after each run | 3.3-6.8% / 2.9-5.8% (P10 after: 18.2%) |
| memory in use | 35.2-36.3% |
| background CPU during, mean / p95 / max | 1.6-3.9% / 2.5-6.1% / 3.5-11.2% (P10: 22.7% max at its end) |
| top background processes | PreSonusHardwareAccessService, Corsair.Service.CpuIdRemote64, MsMpEng, WmiPrvSE, System (each < 2% outside P10's end) |
| verdict | **idle** for every measuring run, except **P10, labelled provisional by the rule**: Windows Defender (MsMpEng.exe, 5.6-16%) scanned the last row's new video files at t >= 282 s and in the after-window. All samples up to t = 156 s were below 6.1% background, so the paced rows (the ones used below) ran on an idle machine. The 3 `*_summarize` steps run < 1 s (no sample) and only re-format JSON. |

No benchmark left a child process behind (`killed_leftover_pids` empty in every `load_*.json`).
Environment: `results/environment_system.json`, `results/environment_python_{skellycamvenv,benchvenv}.json` (from `env_snapshot.py`):
i7-14700K (20C/28T), 64 GB DDR5-4000, WD_BLACK SN850X NVMe, Windows 11 Home 26300, power plan Balanced, RTX 3070 driver 610.88;
Python 3.12.13; numpy 2.2.6; opencv-contrib-python 4.12.0.88 (parallel framework "Concurrency", default 28 threads); av 18.0.0;
psutil 7.2.2; bench venv adds simplejpeg 1.9.0 (PyTurboJPEG module present but its DLL is not, so simplejpeg stands in for libjpeg-turbo).

Temporary videos went to `C:\Users\Dom\AppData\Local\Temp\skellycam_frame_pipeline_tmp\bench_tmp\`. Each script records every
file's size in its JSON (`files[].bytes`, `file_bytes_before_delete`, `file_bytes`, `avi_bytes`, `temp_file_bytes_written_then_deleted`)
and then deletes it; about 63.7 GB in total was written and deleted. The folder was empty at the end.

## How to run

From `C:\Users\Dom\GitHub\freemocap\skellycam` (PowerShell: `$env:PYTHONIOENCODING='utf-8'` first):

```
.venv\Scripts\python.exe research\frame_ring_buffer\prototypes\run_all.py            # everything, in order, 15 s apart, with load records (about 70 min + 20 min for p10/p9)
.venv\Scripts\python.exe research\frame_ring_buffer\prototypes\run_all.py p8 p10     # only steps whose name starts with these
```

`run_all.py` lists the exact command, venv and environment variables of every step; `results/run_all_log.txt` has one line per step as run tonight.
Bench-venv steps use `research\frame_ring_buffer\.venv-bench\Scripts\python.exe` (simplejpeg).

| script | prototype | outputs |
|---|---|---|
| `proto_common.py` | `SeqRing`: one shared-memory block per camera = header (head index, drop/block counters, gated-reader cursors) + per-slot int64 metadata with a **sequence number** (odd = being written, even = 2k+2 for frame k) + 4 KiB-aligned payload slots, prefaulted. `FakeSensor` = the baseline's free-running 60 fps latest-frame-wins camera model. | (helpers) |
| `p1_write_variants.py` | Camera write path, 5 unthrottled spawned writers: current `put_frame` vs `put_data` without `copy.copy` vs decode/retrieve straight into the slot | `p1_write_{skellycamvenv,benchvenv}.json`, `p1_write.md` |
| `p2_seqlock_read.py` | Zero-copy reads (views + seqlock validation): adversarial torn-read test and cold read cost with 5 x 60 fps writers | `p2_seqlock_read.{json,md}` |
| `p3_lossless_record.py` | Decoupled per-camera recorder process with a gated cursor; full-ring policies overwrite (today) / block / drop; stall-tolerance sweep and real MSMF encoder | `p3_lossless_record.{json,md}` |
| `p4_mjpeg_passthrough.py` | MJPEG passthrough recording (camera JPEG bytes muxed into .mkv) vs decode + MSMF H.264 | `p4_mjpeg_passthrough.{json,md}` |
| `p5_nvenc.py` | NVENC h264/hevc via PyAV vs MSMF vs SkellyCam's own `PyavVideoWriter` (libx264) as the decoupled recorder; NVENC session limit | `p5_nvenc.{json,md}` |
| `p6_ui_path.py` | UI payload build: current copy + real `create_frontend_payload` vs views, preallocated resize, thread pool, latest-wins, 640x360, simplejpeg, JPEG forward | `p6_ui_{skellycamvenv,benchvenv}.json`, `p6_ui_path.md` |
| `p7_topology.py` | 5 workers as threads in one process vs 5 processes, per workload (GIL impact), 5 repetitions | `p7_topology_{skellycamvenv,benchvenv}.json`, `p7_topology.md` |
| `p8_e2e_proto.py` | End-to-end prototype pipeline, directly comparable with `baseline/bench_e_e2e.py`: 5 cameras, 60 fps, 30 s, UI on | `p8_e2e_*.json`, `p8_e2e_summary.md` |
| `p10_msmf_threads.py` | `cv2.setNumThreads(N)` vs CPU of the REAL `VideoRecorder` (MSMF), 5 processes | `p10_msmf_threads.{json,md}` |
| `p9_real_camera.py`, `p9b_pyav_dshow_probe.py` | Bonus: the 4 attached real UVC cameras, one at a time: `retrieve(image=slot view)` into shared memory; raw JPEG byte access | `p9_real_camera.{json,md}`, `p9b_pyav_dshow_probe.{json,md}`; first P9 attempt (wrong property order) kept as `run1_fourcc_first_p9_real_camera.*` |
| `run_with_load.py`, `summarize_load.py`, `env_snapshot.py`, `run_all.py` | load recording, environment, driver | `load_*.json`, `load_summary.md`, `environment_*.json`, `run_all_log.txt`, `*_stdout.log` |

Changes made to the stopped agent's scripts before this run: temp files moved to the fixed scratch folder (`proto_common.SCRATCH_TMP`);
P1 gained 3 rows that use the real SkellyCam ring (`cur_memcpy_putdata_nocopycopy`, `cur_memcpy_putdata_u8copyto`, `cur_vcap_into_sk_slot`)
and content verification; P5 gained SkellyCam's `PyavVideoWriter`; P7 now repeats each cell 5 times and records temp sizes;
P8 gained `imdecode_off` (decode off the capture loop); the md summaries now quote the idle 20261027 baseline instead of the
provisional one; the P6 summary header now correctly says the event-loop column is median / p99 / max (the stopped agent's header said
median / p99 over p99 / max values). P9, P9b and P10 are new.

**Keeping the cited results (added 2026-10-28, REVISION stage).** Re-running a command above writes fixed file names into
`results/` and overwrites the files the reports cite. To re-run without touching them, first set
`$env:FRAME_PIPELINE_RESULTS_DIR = '<some folder>'`: every stage script (via `research/frame_ring_buffer/fp_paths.py`) then
writes to `<some folder>\<stage>\results\` instead. `reproducibility/protect_originals.py snapshot|collect|restore` is the
fallback for older copies of the scripts.

**Summaries merge repeats.** `p8_e2e_proto.py --summarize` tabulates every `results/p8_e2e_*.json` (set `P8_SUMMARY_GLOB` / `P8_SUMMARY_OUT` to choose); the 2026-10-28 revision runs use the prefix `p8v_e2e_` (`P8_PREFIX`) and their own summary `p8v_e2e_summary.md`. P6 writes `p6_ui_<venv>.json` unless `P6_OUT` names another file. New options and scripts added by the revision stage (P8 `P8_LOCKSTEP`/`P8_META`/`P8_RECTHREAD`/`P8_EXTRA_CPU_MS`, P3 `ASYM`, P10 `P10_PLAN=revision`, P11 crash containers, P12 sustained disk) are documented in `../revision/README.md`.

## Results (all values from `results/`; "baseline" = `baseline/results/`, idle 20261027 re-run)

### P1 - write path (`results/p1_write.md`; 5 spawned unthrottled writers, 10 s after 1 ring lap + 2 s warm-up, cv2.setNumThreads(1))

| 1080p row | per-camera fps (slowest) | total median / worst p99 ms | publish median / p99 ms | CPU ms/frame | full-frame copies after the pixels exist |
|---|---|---|---|---|---|
| `cur_memcpy_putframe` (real `put_frame`) | 238 | 4.109 / 5.395 | **3.085 / 4.046** | 4.155 | 3 (stand-in memcpy, `copy.copy`, slot) |
| `cur_memcpy_putdata_nocopycopy` (real ring, `copy(data)` removed) | **431** | 2.284 / 3.216 | **1.166 / 1.854** | 2.301 | 2 |
| `cur_memcpy_putdata_u8copyto` (flat uint8 copyto) | 428 | 2.280 / 3.248 | 1.167 / 1.846 | 2.317 | 2 |
| `cur_vcap_putframe` (retrieve into private + real `put_frame`) | 85 | 11.670 / 14.165 | 2.618 / 3.891 | 11.605 | 2 |
| `cur_vcap_into_sk_slot` (retrieve straight into the real ring's slot) | **115** | 8.574 / 10.304 | **0.060 / 0.143** | 8.573 | **0** |
| `cur_imdecode_putframe` (baseline e2e stand-in + `put_frame`) | 97 | 10.202 / 12.558 | 2.217 / 3.537 | 10.245 | 3 |
| `p_imdecode_copyslot` (imdecode, 1 copy into SeqRing slot) | 132 | 7.515 / 9.065 | 0.006 / 0.014 | 7.553 | 1 |
| `p_vcap_into_slot` | 118 | 8.387 / 10.259 | 0.009 / 0.022 | 8.416 | 0 |
| `p_simplejpeg_into_slot` (bench venv, libjpeg-turbo decodes into the slot) | **212** | 4.680 / 6.011 | 0.003 / 0.009 | 4.668 | 0 |

720p shows the same pattern: publish 1.400 -> 0.526 ms without `copy.copy`, 1.033 -> 0.042 ms when retrieving into the slot, simplejpeg 473 fps vs imdecode 282.
`cv2.imdecode` has no `dst` argument in OpenCV 4.12's Python binding (it raises "imdecode() takes at most 2 arguments"), so decode-into-slot needs
`VideoCapture.retrieve(image=)`, `simplejpeg(buffer=)` or native code. The `vcap` rows read an MJPEG AVI through CAP_FFMPEG (no camera); P9 repeats the idea on real cameras.

### P2 - zero-copy seqlock reads (`results/p2_seqlock_read.md`)

Adversarial test (720p, unthrottled writer at about 4,200-5,700 fps, 10 s per row). Every frame is a single byte value, so a mixed frame is detectable.
- The current pattern (copy, then check `frame_number`, as in `get_data_by_index`, [`ring_buffer_shared_memory.py` L175-202](https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/ipc/shared_memory/ring_buffer_shared_memory.py#L175-L202)) **accepted torn frames**. With L=2 latest it accepted 15 silent tears out of 44,276 reads. Reading the slot the writer overwrites next, it accepted 39,854-41,834 silent tears and 1,068-1,846 wrong frames, at every ring length (2, 8, 388).
- The seqlock readers (copy or view + resize) accepted **0 torn and 0 wrong frames in all 12 seqlock rows**. They rejected every racing read instead.

Cold read cost with 5 x 60 fps writers (600 reads per style): reading 1080p through a validated **view** costs 0.0204 ms (p99 0.039), against 0.3784 ms for a validated copy.
For 5 cameras, views cost 0.0333 ms against 1.8365 ms for copies. The baseline's real `get_latest_multiframe` takes 2.3533 ms (p99 7.29).
Resizing straight from the view (the UI's first step) costs 2.50 ms for 5 cameras, with 0 copies out of shm. Validation failures: 0 in all rows.

### P3 - lossless record path (`results/p3_lossless_record.md`)

Part A: 5 x 1080p cameras at 60 fps, 5 recorders, then one simultaneous recorder stall of S ms at t = 3 s (8 s runs).

| ring slots L (s at 60 fps) | largest stall with 0 loss | first stall that loses frames: overwrite (today) / block / drop |
|---|---|---|
| 16 (0.27 s) | 200 ms | 1000 ms: recorder silently lost 225 / sensor skipped 210 (counted) / ring-full drops 220 (counted) |
| 64 (1.07 s) | 1000 ms | 2500 ms: 435 lost silently / 420 / 430 |
| 172 (2.87 s, SkellyCam's 1 GiB default at 1080p) | **2500 ms** | 3500 ms: 195 lost silently / 180 / 190 |

The losses scale as predicted: (S x 60 - L) frames per camera. Under `overwrite` the recorder gets non-consecutive frames, and nothing outside the recorder counts the loss.
Under `block` and `drop` every recorded stream stays consecutive and every lost frame is counted at the camera (`sensor_skipped` or `ring_full_drops`).
The ring can only absorb a stall up to its own length. No policy creates capacity; the policies differ only in where the loss shows up and whether it is counted.

Part B uses the real MSMF writer (`cv2.VideoWriter('X264')`, as `VideoRecorder` resolves on this machine), block policy, 20 s, and one 1500 ms stall at t = 8 s.
At both 1080p (L=172) and 720p (L=388): 6005 frames were produced and 6005 recorded, with 0 lost and 0 sensor frames skipped. The maximum lag was 90 slots.
Every file decoded to exactly the frames produced, and 0 of 605 sampled frames had the wrong content (so a slot was never reused while the encoder held it).
Recorder `write()` at 1080p: median 0.67 ms, p99 3.98 ms.

### P4 - MJPEG passthrough (`results/p4_mjpeg_passthrough.md`; 5 cameras, 20 s, synthetic q90 JPEGs)

| 1080p | fps (min) | never grabbed | files == produced | disk MB/s (5 cams) | CPU % cameras / recorders | tick -> written median / p99 ms |
|---|---|---|---|---|---|---|
| passthrough (JPEG bytes -> .mkv) | 60.01 | 0 | yes | 162.1 | **35 / 28** | 0.8 / 1.8 |
| decode + MSMF H.264 (default threads) | 59.98 | 0 | yes | 77.9 | 302 / 939 | 10.8 / 15.0 |

720p: passthrough 45 / 16% CPU vs 149 / 292% for decode + MSMF. With no pacing, the passthrough recorders muxed 9,740 (1080p) and 28,008 (720p) frames/s in total.
Those disk MB/s figures (5,166 and 6,603) reflect the OS write cache, not sustained NVMe writes.
The synthetic q90 JPEGs (540 KB at 1080p) are much larger than real camera frames: 57-116 KB at 1080p30 in `p9b_pyav_dshow_probe.md`. Real passthrough files would therefore be about 5-9x smaller than here (extrapolation).

### P5 - hardware encode (`results/p5_nvenc.md`; recorder processes call cv2.setNumThreads(2))

- **NVENC session limit on driver 610.88: 12 concurrent sessions** for both h264_nvenc and hevc_nvenc; the 13th open failed (nvidia-smi sessionCount = 12). Five cameras fit.
- 5 x 1080p paced 60 fps, 20 s. All encoders wrote every frame (files == produced). Recorder CPU and recorder throughput (unthrottled, slowest camera / sum):

| encoder | recorder CPU % (5) | Mbit/s per cam | tick -> written median / p99 ms | unthrottled: slowest / sum fps |
|---|---|---|---|---|
| MSMF ('X264') | 283 | 124.9 | 2.6 / 5.6 | 115 / 578 |
| h264_nvenc (p4, ll, cq 23) | **105** | 29.7 | 3.8 / 189.0 | 89 / 447 |
| hevc_nvenc (cq 25) | 80 | 16.2 | 693.2 / 1116.6 (backlog grows) | **56 / 283: does not keep up** |
| SkellyCam `PyavVideoWriter` (libx264 crf 18 fast) | 2442 | 8.4 | 2202 / 3709 (backlog) | **46 / 230; 319 sensor frames lost in 20 s** |

At 720p, all four keep up when paced (libx264 at 1273% CPU). NVENC's tick -> written p99 (103-218 ms) comes from occasional blocking `encode()` calls (p99 17 ms at 1080p).
The aggregate NVENC throughput for 1080p is about 410-450 fps (`p7_topology.md` h264_nvenc, `p5_nvenc.md`), so 5 x 60 = 300 fps leaves about 1.4-1.5x headroom.

### P10 - OpenCV thread count vs recorder CPU (`results/p10_msmf_threads.md`; REAL `VideoRecorder`, 5 processes, paced 60 fps, 20 s)

| size | cv2 threads | CPU % (5 recorders) | record_frame median / p99 ms | late > 16.7 ms | encode fps slowest (unthrottled) |
|---|---|---|---|---|---|
| 1080p | default (28) | **1187** | 2.16 / 4.86 | 0 | 114.7 |
| 1080p | 1 | **359** | 2.42 / 4.26 | 0 | - |
| 1080p | 2 / 4 / 8 | 563 / 619 / 750 | 2.28-2.07 / 3.61-2.87 | 0 | 115.4 (2 threads) |
| 720p | default / 1 / 2 | 506 / 227 / 224 | 0.97-1.17 / 1.41-1.94 | 0 | - |

Output does not change with the thread count: 124.9 Mbit/s per camera in every paced 1080p row (124.8 in the unthrottled rows, 55.5 at 720p), and all files decode to the frames written. (corrected 2026-10-28; was "124.9 Mbit/s per camera in every row") SkellyCam never calls `cv2.setNumThreads` (grep of `skellycam/`: no match).
The cause is likely OpenCV's "Concurrency" thread pool busy-waiting around per-frame conversions. That is an inference; it was not profiled.
The same effect shows in P8: NVENC recorders with default threads used 584% CPU, against 105% in P5 with 2 threads.

### P6 - UI path (`results/p6_ui_path.md`; relay shape: await 10 ms, then build; no browser)

| 1080p variant | payloads/s | build median / p99 ms | event-loop blocked median / p99 ms | main CPU % |
|---|---|---|---|---|
| `cur_copy_real` (copy out of shm + real `create_frontend_payload`) | 51.8 | 8.28 / 10.11 | 8.28 / 10.11 | 89 |
| `view_real` (views + real `create_frontend_payload`) | 57.8 | 6.31 / 7.38 | 6.31 / 7.38 | 76 |
| `view_proto` (views, resize into preallocated dst, 1 assemble copy, latest-wins) | 53.0 | 4.84 / 7.20 | 4.84 / 7.20 | 59 |
| `view_proto_threads` (5 resize+encode jobs in a ThreadPoolExecutor) | 46.4 | 2.20 / 3.94 | **0.05 / 0.08** | 50 |
| `view_proto_threads_poll2ms` | **60.1** | 1.96 / 3.03 | **0.04 / 0.07** | 58 |
| `jpeg_forward` (camera JPEG bytes forwarded, no decode/encode) | 51.0 | 0.25 / 0.56 | 0.25 / 0.56 | 2 |
| `jpeg_reduced_reencode_threads` (decode at 1/2 scale + q60, threads) | 58.4 | 5.91 / 7.23 | 0.04 / 0.08 | 159 |

The baseline's real path reached 46.0 payloads/s at 9.39 ms (`d_ui.md`). With 10 ms polling, latest-wins rates of 43-58/s depend on the timer phase.
The same `view_proto` row gave 53.0/s and 57.8/s (1080p), and 60.0/s and 42.6/s (720p), in the two venvs. Polling every 2 ms gives a stable 60/s. The reproducibility re-run (2026-10-28) confirmed the bimodality: the five skellycamvenv 720p rows near 60/s that poll every 10 ms (`view_proto`, `view_proto_640x360`, `view_proto_threads`, `jpeg_forward`, `jpeg_reduced_reencode_threads`) fell from 59.4-60.1 to 43.9-45.6/s. The other 10 ms rows at 720p changed by -0.7% to +3.1% (skellycamvenv `cur_copy_real` 65.0, `view_real` 68.1, `jpeg_reduced_reencode` 43.5/s; benchvenv `view_proto` 42.6 and `view_simplejpeg` 44.5/s), and `view_proto_threads_poll2ms` stayed at 60.1/s at both sizes (`../reproducibility/comparison.md`). (corrected 2026-10-28; was "every 720p row that polls every 10 ms fell") Quote the 10 ms-poll 720p rows as a range (about 43-60/s), not a point value; the revision stage's two extra repeats are in `results/p6_ui_skellycamvenv_rev_rep{2,3}.json`.
simplejpeg at its default settings produced larger payloads (492 KB vs 306 KB) and a slower build (6.80 vs 4.99 ms), so here it was no better than `cv2.imencode` (not tuned).
The `jpeg_forward` payload (2.7 MB) is full-resolution synthetic q90. With real camera JPEGs (57-116 KB at 1080p, P9b) it would be about 0.3-0.6 MB (extrapolation).

### P7 - topology / GIL (`results/p7_topology.md`; 1080p, median of 5 repetitions)

5 threads in one process scale the same as 5 processes for work that releases the GIL: imdecode x4.60 vs x4.90, simplejpeg x5.00 vs x5.05,
MJPEG mux x2.05 vs x1.89, MSMF write x1.64 vs x1.53 (both limited by the encoder, not the GIL). NVENC is x1.08 / x1.13: the GPU is the limit, at about 407-426 fps total.
Pure-Python per-frame control work does not scale in threads (x1.03, 15,522 vs 74,947 iterations/s for 5 processes, x4.97).
Pixel work can therefore live on threads, but per-camera Python control loops need their own processes.

### P8 - end-to-end prototype (`results/p8_e2e_summary.md`; 5 cameras x 60 fps, 30 s, UI on; same sensor model, content, overlay and MSMF writer as `baseline/bench_e_e2e.py`)

| config | fps (min cam) | sensor frames never grabbed | files == produced, consecutive | tick -> written median / p99 / max ms | UI payloads/s | CPU % cams / recorders / main |
|---|---|---|---|---|---|---|
| **baseline** 1080p mjpeg + UI (2 runs) | 53.56 / 53.57 | **964 / 964** | yes | 23.9 / 34.4 / 37.4 | 36.9 / 36.6 | children 1345 / 1361, main 131 / 134 |
| P8 1080p imdecode + MSMF (2 runs) | **59.95 / 59.95** | **0 / 0** | yes / yes | 10.4 / 16.4 / 18.7; 10.1 / 15.2 / 17.1 | 47.3 / 46.9 | 312 / 954 / 85; 306 / 924 / 89 |
| P8 1080p simplejpeg + MSMF | 59.96 | 0 | yes | 7.3 / 11.3 / 12.6 | 43.6 | 202 / 886 / 76 |
| P8 1080p imdecode + h264_nvenc | 59.95 | 0 | yes | 12.6 / 218.2 / 297.3 | 45.1 | 296 / 584 / 76 |
| P8 1080p simplejpeg + h264_nvenc | 59.96 | 0 | yes | 8.8 / 151.2 / 253.2 | 45.2 | 194 / 535 / 63 |
| P8 1080p imdecode + passthrough | 59.96 | 0 | yes | 8.3 / 11.9 / 13.2 | 46.2 | 280 / 18 / 63 |
| P8 1080p **imdecode_off** + passthrough (2 runs; 2 decoder threads per camera) | 59.97 / 59.97 | 0 / 0 | yes / yes | **0.8 / 1.5 / 2.9**; 0.8 / 1.5 / 2.3 | 49.6 / 49.9 | 296 / 19 / 66; 273 / 20 / 70 |
| P8 1080p memcpy + MSMF | 59.97 | 0 | yes | 2.7 / 5.2 / 7.1 | 43.3 | 57 / 1010 / 72 |
| baseline 720p mjpeg + UI | 60.00 | 0 | yes | 5.5 / 7.7 / 10.9 | 57.0 | 478 / 55 |
| P8 720p imdecode + MSMF / + nvenc / imdecode_off + passthrough | 59.96 / 59.96 / 59.97 | 0 / 0 / 0 | yes | 4.5 / 6.2 / 8.2; 5.4 / 108.2 / 313.4; 0.5 / 1.1 / 2.5 | 51.8 / 51.8 / 53.8 | 145/299/39; 141/489/36; 149/20/32 |

In every P8 run the recorder never blocked a camera (`block_events` 0) and the UI accepted 0 invalid frames.
In the `imdecode_off` runs, decoding ran at 60.00 fps per camera with 0 decode-skipped frames, tick -> decoded median 8.4 ms and p99 10.4-10.7 ms (1080p).
The per-camera loop with in-loop decode still runs at 9 ms median and 13-15 ms p99 at 1080p. That leaves less than 2 ms of p99 headroom in the 16.7 ms budget,
which is why `imdecode_off` (or a faster decoder) is the more robust 1080p option.

### P9 / P9b - real cameras (bonus; `results/p9_real_camera.md`, `results/p9b_pyav_dshow_probe.md`)

Four UVC cameras were attached: c922, C930e, Razer Kiyo Pro and "USB Camera". They were tested one at a time through DSHOW, MJPG and BUFFERSIZE=1, with SkellyCam's property order. (Note added 2026-10-28: the Kiyo Pro was supposed to be excluded from the overnight runs, but the exclusion was never passed to this workflow. The kept P9 run, 03:10:30-03:17:09, opened DSHOW indices 0-3, and the first attempt, 02:55:33-03:09:39, opened indices 0-5. Neither recorded which camera each index was, so one index (probably 3) was likely the Kiyo; this is inferred. Every by-name PyAV attempt on "Razer Kiyo Pro" failed with OSError 5: 2 in P9 and 5 in P9b. See `../../overnight_run_20261027/REPORT.md` finding 6.)
- `retrieve(image=<shared-memory slot view>)` wrote into shared memory **in place on every camera at 720p and 1080p** (pointer check and non-zero pixels).
  It used 0.3-1.4 ms less process CPU per frame than retrieve into a new array plus a copy, for example 11.42 vs 12.66 ms at 1080p on index 0.
- **No camera delivered 60 fps tonight**: 25.7-30.1 fps at both sizes, although 60 was requested and DSHOW reported 60. Camera mode limits explain most of it, but not all (not established). The C930e lists MJPG only up to 1080p30, the c922 only up to 30 fps at 1080p, and the generic camera runs at about 25.7 fps even when 30 is requested. In P9b every 60 fps request failed with an I/O error except the c922 at 720p. The c922 does list a 720p60 MJPG mode, and in P9b it negotiated 60 there but delivered 30.1 fps. The Kiyo lists 60 fps modes at both sizes (`../../usb_cameras/mjpeg/HANDBACK_earlier_instance.md`). Why the c922 at 720p (and the Kiyo, if it was one of the P9 indices) stayed at about 30 fps is not known. Exposure is an unlikely cause for the c922, C930e and generic camera: the overnight camera run had left them at manual exposure -7 (the C930e reads back -5) with AE priority 0, although P9 did not record its exposure settings (`../../usb_cameras/results/windows/Gerald/RERUN_20261027.md`, Conditions). The Kiyo was excluded from that run, so its exposure state is not known. (corrected 2026-10-28; was "Likely causes are exposure in a dark room and camera mode limits (not established).")
  **5 x 60 fps could therefore not be checked with real cameras.**
- **In OpenCV's DSHOW backend, `grab()` returns in about 0.00-0.01 ms, and the wait for the next frame (about 32 ms at 30 fps) happens inside `retrieve()`.**
  SkellyCam stamps `pre/post_frame_grab_ns` around `grab()` ([`opencv_get_frame.py` L53-55](https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera/opencv/opencv_helpers/opencv_get_frame.py#L53-L55)) and calls it the best proxy for capture time.
  On DSHOW those stamps therefore mark when grab was called, not when the frame arrived. This was measured in a standalone loop, not in SkellyCam's own loop (open question for the sync analysis).
  Because the wait and the decode both sit inside `retrieve()`, this split cannot say on which thread DSHOW decodes MJPEG. Process CPU was 7.2-14.7 ms per decoded frame.
- **OpenCV 4.12 does not hand over the camera's JPEG bytes**: DSHOW with `CAP_PROP_CONVERT_RGB=0` still returned decoded BGR, and MSMF refused `CAP_PROP_FORMAT=-1`.
  **PyAV's FFmpeg dshow input does**: with `vcodec=mjpeg` and a framerate the camera offers, 3 cameras delivered 100% FF D8 (JPEG) packets at 26-30 fps, 1080p and 720p.
  Packets were 57-116 KB per frame at 1080p and 25-63 KB at 720p, at under 0.6 ms CPU per packet. Asking for 60 fps where a camera has no 60 fps mode gives an I/O error.
  The Razer Kiyo Pro would not open through FFmpeg dshow in any mode (cause not established).

## What could not be measured / open questions

* Real 5 x 60 fps capture: only 4 cameras are attached and none delivered more than 30.1 fps (P9). All 5 x 60 results use the synthetic `FakeSensor`.
* Whether DSHOW decodes MJPEG on the calling thread or on a graph thread (P9 cannot separate the wait from the decode).
* P8 removes SkellyCam's lockstep grab gate (`orchestrator.should_grab_by_id`, [`opencv_camera_loop.py` L67-69](https://github.com/freemocap/skellycam/blob/23ccbf208e43879bfc74fc01049e5af2a623933d/skellycam/core/camera/opencv/opencv_camera_loop.py#L67-L69)) as well as the in-loop encode and `copy.copy`.
  Its gain is the combined effect; the cross-camera timing spread of free-running cameras was not measured. (Update 2026-10-28: the revision stage re-ran P8 with SkellyCam's lockstep gate and per-frame metadata writes kept, which gave 59.82 / 59.95 fps on the slowest camera (`results/p8v_e2e_summary.md`). It also re-ran the no-gate shape with the spread recorded: the cross-camera sensor-tick spread was 6.3 ms in every frame (`results/p8v_e2e_1080p_imdecode_msmf_spread.json`). That value is the fixed random phase of the synthetic FakeSensor cameras, so real free-running cameras are still unmeasured. See `../revision/README.md`.) Grouping frames by timestamp is the alternative, and its quality is an open question.
* P8 recorders hold the shm slot until `write()`/`encode()` returns (cursor advanced after). That is safe for MSMF and PyAV here (P3 content check: 0 of 605 mismatches),
  but it relies on each encoder copying the input frame before returning.
* The x86 seqlock in `SeqRing` relies on x86-64 store ordering (TSO) and single-instruction int64 stores (see the `proto_common.py` docstring). It is not portable to ARM without fences.
* No browser was attached in P6, so websocket send and browser decode are not included. No disk-full or slow-disk (pSLC exhausted) test was run. (Update 2026-10-28: the revision stage's P12, `results/p12_disk_sustained.md`, later ran a slow-disk test on C:. It wrote 68.7 GB unbuffered write-through: about 5 GB/s per GiB for the first 48 GiB, then 481-1508 MB/s. Paced 162 and 69 MB/s streams held their rate, with a worst `write()` of 134.8 and 137.8 ms. P12 wrote raw data with no encoder, and there is still no disk-full test.) P3 models a stall as a sleep.
* simplejpeg was not tuned for encode (subsampling/quality defaults differ from `cv2.imencode`), and PyTurboJPEG could not be tested because its DLL is not installed.
* Spill-to-disk as a full-ring policy was not prototyped; only block and drop were.
