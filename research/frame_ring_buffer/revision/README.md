# Revision stage (2026-10-28): benchmarks added to answer the critics

The three critiques (`../study_state/critic_evidence_result.json`, `critic_priorities_result.json`,
`critic_reproduce_result.json`) found weak inferences in `recommend_result.json`. This stage re-ran or added the
benchmarks below, all against SkellyCam `23ccbf208e43879bfc74fc01049e5af2a623933d` (unmodified; every change is a
benchmark-process monkeypatch or a prototype), and rewrote `../study_state/recommend_result.json`. The issue-by-issue
record is `../study_state/revision_result.json`.

Driver: `run_revision.py` (from `C:\Users\Dom\GitHub\freemocap\skellycam`, PowerShell, `$env:PYTHONIOENCODING='utf-8'`):

```
.venv\Scripts\python.exe research\frame_ring_buffer\revision\run_revision.py            # every step, 15 s apart
.venv\Scripts\python.exe research\frame_ring_buffer\revision\run_revision.py e2ev p8v    # steps whose name starts with these
```

Each step runs through its stage's `run_with_load.py` (load before / during / after, the same idle rule as
`../PROVISIONAL.md`), so every result has a `load_<step>.json` next to it. `run_revision_log.txt` has one line per step.
New result files use new names; no file cited by an earlier stage was overwritten. To re-run without touching these
either, set `FRAME_PIPELINE_RESULTS_DIR` (see `../fp_paths.py`).

Machine state: every measuring step met the idle rule (background CPU mean 1.9-4.6%, p95 3.0-8.0%, system CPU 3.3-5.9% (corrected 2026-10-28; was mean 2.4-4.6%, p95 4.1-8.0%, system 3.4-5.9%)
before and after; the per-step values are in the `load_*.json` files). One disclosure: a smoke-test process of
`bench_e2e_variants.py` started at 06:09 (PIDs 25624/35116) stayed alive, blocked on a full stdout pipe, until 06:21,
i.e. through the `e2ev_*` steps. The load records include it as background, and every step still met the idle rule.
It was killed at 06:21.

## What was added

| step / script | answers | outputs |
|---|---|---|
| `baseline/bench_e2e_variants.py` (+ `analyze_gap_detector.py`) | the REAL SkellyCam stack (same harness as `bench_e_e2e.py`) with ONE change at a time: `nocopycopy` (rank "remove copy.copy" alone), `cvthreads1` (`cv2.setNumThreads(1)` in camera processes alone), both, `extracpu3` (retrieve CPU raised by 3 ms toward P9's real-camera 11-15 ms), `dshowlike` (grab returns at once, retrieve waits), a HEAD control and a no-UI repeat. Dumps per-frame timestamps and sensor ticks for the drop-detector validation, the stop-pause gap and the capture-time spread | `baseline/results/e2ev_*.json`, `e2ev_*_perframe.npz`, `e2ev_summary.md` (`summarize_e2e.py "e2ev_*_1080p_*.json" e2ev_summary.md`), `e2ev_gap_detector.{md,json}` |
| `prototypes/p8_e2e_proto.py` new options `P8_LOCKSTEP`, `P8_META`, `P8_RECTHREAD`, `P8_EXTRA_CPU_MS`, cross-camera spread | the recommended design (decoupled recorder + seqlock ring) WITH SkellyCam's lockstep gate and per-frame metadata writes, the recorder as a thread, and a CPU-sensitivity stand-in | `prototypes/results/p8v_e2e_*.json`, `p8v_e2e_summary.md` |
| `prototypes/p10_msmf_threads.py` `P10_PLAN=revision` | unthrottled encode rate at `setNumThreads(1)`, and paced rows under a concurrent 5x1080p60 decode load | `prototypes/results/p10v_msmf_threads.{json,md}` |
| `prototypes/p11_crash_container.py` | is a recording readable after its writer is killed (MSMF MP4, MJPEG MKV, NVENC fragmented MP4, NVENC MKV; killed idle and mid-write) | `prototypes/results/p11_crash_container.{json,md}` |
| `prototypes/p3_lossless_record.py ASYM` | one of 5 recorders stalls: block vs drop vs block + lockstep; recorded frame-number sets and capture-time spread | `prototypes/results/p3v_asymmetric_stall.{json,md}` |
| `prototypes/p12_disk_sustained.py` | the physical disk: 64 GiB unbuffered write-through (SLC-cache exhaustion), 5 paced write-through streams at 162 MB/s for 300 s and 69 MB/s for 600 s, buffered writes + FlushFileBuffers at stop | `prototypes/results/p12_disk_sustained.{json,md}` |
| `baseline/bench_h_deflate.py` | permessage-deflate cost on a real `create_frontend_payload` payload with the websockets library's own compressor | `baseline/results/h_deflate.{json,md}` |
| `prototypes/p6_ui_path.py` with `P6_OUT` | two more repeats of every P6 row (3 runs with the original) | `prototypes/results/p6_ui_skellycamvenv_rev_rep{2,3}.json` |
| `fp_paths.py` + edits to every stage's result path | `FRAME_PIPELINE_RESULTS_DIR` output-directory option | (docs in each stage README) |

## Key results (numbers from the files above)

### Real stack, one change at a time (5 x 1080p mjpeg + UI, 30 s; `baseline/results/e2ev_summary.md`, `e2ev_gap_detector.md`)

| run | min-camera fps | sensor frames never grabbed (5 cams) | retrieve / put_frame / record_frame median ms | finalizer processing / camera idle (gate) median ms | children CPU % |
|---|---|---|---|---|---|
| HEAD control (`e2ev_head_1080p_mjpeg_ui`) | 54.14 | 878 | 10.16 / 3.61 / 1.14 | 15.42 / 2.48 | 1338 |
| copy.copy removed (`e2ev_nocopycopy_*`, 2 runs) | 58.84 / 58.98 | 170 / 150 | 9.72-9.99 / 1.29-1.38 / 1.02-1.06 | 13.51-14.12 / 2.50-3.19 | 1392 / 1351 |
| setNumThreads(1) in camera processes (`e2ev_cvthreads1_*`) | 54.74 | 788 | 8.88 / 2.97 / 2.75 (corrected 2026-10-28; was 2.73, camera 0's median) | 14.94 / 1.81 | 713 |
| both (`e2ev_nocopycopy+cvthreads1_*`) | 58.29 | 254 | 8.58 / 1.13 / 2.72 | 13.76 / 2.82 | 686 |
| retrieve + 3 ms CPU (`e2ev_extracpu3_*`) | 48.46 | 1732 | 12.88 / 3.35 / 1.08 | 17.67 / 2.22 | 1230 |
| HEAD no UI repeat (`e2ev_head_1080p_mjpeg_noui_rep2`) | 55.62 | 655 | 10.00 / 3.41 / 1.10 | 14.89 / 2.40 | 1399 |

Original HEAD runs for comparison: 53.56 / 53.57 fps, 964 / 964 (`baseline/results/e_e2e_summary.md`), reproduced at
53.92 / 53.97 fps, 911 / 902 (`../reproducibility/comparison.md`); original no-UI run 55.94 fps, 605.

Drop detector (rank 4) against the true count (sum of 5 cameras): the proposed per-interval `round(dt/T) - 1` finds 16 of
878 at HEAD (10 of 170, 15 of 150, 56 of 788 ...); the accumulated clock `round((t_last - t_first)/T) + 1 - n` finds
880 of 878, 175 of 170, 154 of 150, 790 of 788, 1730 of 1732, 655 of 655, 255 of 254.

Stop / start pause gap: at most 1 skipped sensor tick between consecutive recorded frames among the last 10 recorded
frames of every camera in every run (sum over 5 cameras 0-14 ticks over 50 camera-frames, i.e. 0-0.28 per camera-frame, against 0.02-0.24 per camera-frame
elsewhere in the same runs). The pause exists in code (`camera_group.py` L215-232) but costs at most about one frame per camera here.

Capture-time spread: the finalizer reports "Mean Inter-Camera Sync" 0.47-1.28 ms (grab-call stamps) while the sensor tick
times of the same frame number differ by 7.0-13.3 ms median and up to 20.2 ms across the 5 free-running synthetic cameras
(random phase). Lockstep aligns frame NUMBERS and grab CALLS, not exposure instants; with unsynchronised cameras the
capture-time spread of a multiframe was 7.0-13.3 ms median and up to 20.2 ms in these runs.

### Recommended design with lockstep kept (`prototypes/results/p8v_e2e_summary.md`, 5 x 1080p imdecode, MSMF, UI on, 30 s)

| run | min-camera fps | never grabbed | lockstep gate wait median (cam 0) | tick -> written p99 ms (worst cam) | CPU % cams / recorders / main |
|---|---|---|---|---|---|
| no gate (original P8 shape) re-run, now with spread | 59.95 | 0 | - | 17.3 | 305 / 992 / 84 |
| lockstep + metadata writes, run 1 / run 2 | 59.82 / 59.95 | 20 / 0 | 0.027 / 0.175 ms | 30.5 / 27.3 | 330 / 1017 / 98 and 338 / 979 / 107 |
| lockstep + metadata + recorder as a thread in the camera process | 59.93 | 1 | 6.62 ms | 29.7 | 1323 (all in camera processes) |
| lockstep + metadata + 3 ms extra CPU per frame (decode 14.5 ms) | 58.08 | 276 | 1.69 ms | 34.8 | 408 / 985 / 118 |

Not modelled even here: `camera_loop_update_checks` / pubsub polling, the deepcopy in `should_grab_by_id`, the
start/stop handshake and the finalizer.

### One recorder stalls (`prototypes/results/p3v_asymmetric_stall.md`, 1080p, L=172 = 2.87 s, stall at t=3 s on camera 0 only)

1000 ms stall: lossless and in sync under every policy. 3500 ms stall: block without lockstep -> camera 0 records 445
frames vs 481, the frame numbers still match over the common range, but camera 0's frame k was captured up to 606 ms later
than the others' (92 frames out of sync by >= 1 period, invisible to every count check); drop -> 443 vs 481, 639 ms;
block + lockstep -> all 5 cameras record 445 frames, all skip the same 36 sensor ticks, spread stays 6.3 ms.

### Crash safety of the recording file (`prototypes/results/p11_crash_container.md`, 300 frames written, then TerminateProcess)

| writer / container | killed idle (720p / 1080p) | killed mid-write |
|---|---|---|
| cv2 'X264' -> MSMF .mp4 (SkellyCam default) | 0 / 0 frames readable (PyAV: invalid data; no moov) | 0 / 0 |
| PyAV MJPEG passthrough .mkv | 298 / 298 (the last 2 packets lost) | 359 / 359 (all but the in-flight tail) |
| PyAV h264_nvenc fragmented .mp4 | 233 / 237 (cv2); PyAV errors at the truncated tail | 291 / 297 (cv2) |
| PyAV h264_nvenc .mkv | 233 / 237 (encoder pipeline frames lost, file valid) | 291 / 297 |

Clean release gives 300 in every case.

### OpenCV threads in the real recorder (`prototypes/results/p10v_msmf_threads.md`, 5 x 1080p)

Unthrottled encode rate (slowest camera): default 115.8 fps at 1826% CPU, threads=1 116.1 fps at 896%, threads=2 115.0 fps
at 1045%. Paced 60 fps while 5 extra processes decode 1080p JPEGs at 60 fps: default 1185%, threads=1 481%, threads=2
501%, all 60.0 fps with 0 late writes; record_frame median 1.88 / 2.67 / 2.53 ms.

### Physical disk (`prototypes/results/p12_disk_sustained.md`; C:, 4 TB SN850X, 224.9 GB free = 94.4% used)

A, 64 GiB unbuffered write-through: 4.2-5.3 GB/s per GiB (median 5.2) for the first 48 GiB (corrected 2026-10-28; was "about 5.0-5.3 GB/s"; 16 of those 48 GiB were below 5.0), then 481-1508 MB/s (SLC cache exhausted);
write() max 97 ms. B1, 5 paced write-through streams at 162 MB/s for 300 s, started right after A: 162.2 MB/s achieved,
write() median 0.42 ms, p99.9 15.8 ms, max 134.8 ms; worst stream fell 135 ms behind its 60 Hz schedule (the 1080p ring
holds 2.87 s). Time to fill the 224.9 GB free: 54 min at 69 MB/s (HEAD MSMF), 23 min at 162 MB/s (MJPEG passthrough).
B2, 69 MB/s write-through for 600 s: 70.0 MB/s, write() max 137.8 ms, worst lag 138 ms. C, buffered writes at
162 MB/s for 60 s, then FlushFileBuffers: worst lag 3.4 ms, flush at stop up to 0.48 s. So, with Defender in its default
state, the disk kept up at both recording rates even with the SLC cache exhausted, and the worst raw storage stall
(138 ms) is about 5% of the 1080p ring. Not covered: stalls through the real encoders, antivirus scans of the growing
files, and runs longer than 10 minutes.

### Deflate (`baseline/results/h_deflate.md`)

websockets 16.1.1 `PerMessageDeflate` with uvicorn's defaults on a payload from SkellyCam's real `create_frontend_payload`:
1080p 314 KB -> 95 KB in 6.22 ms median (6.93 p99); 720p 142 KB -> 44 KB in 2.81 ms. The synthetic content deflates far
more than real camera JPEGs would, so only the time is representative.

### P6 repeats (`prototypes/results/p6_ui_skellycamvenv_rev_rep{2,3}.json`)

Over 4 runs (original, reproducibility re-run, 2 revision repeats): 1080p `view_proto_threads_poll2ms` 60.0-60.1/s,
`view_proto_threads` 46.4-47.5/s, `cur_copy_real` 51.6-51.8/s; 720p `view_proto` 43.5-60.0/s (bimodal). The rate gain
comes from the poll interval; the thread pool removes event-loop blocking.

### DSHOW-like timing stand-in (`baseline/results/e2ev_dshowlike_1080p_mjpeg_ui_v2.json`)

grab() returns at once, retrieve() waits for the next sensor tick and then decodes: 54.17 fps, 874 never grabbed (HEAD
control 54.14, 878), i.e. the same throughput. The grab stamps spread 2.82 ms p99 across cameras while the capture times
of the same frame number spread 12.9 ms median, 20.2 ms max. The first dshowlike run logged `read()` calls made during
setup into its tick log (index shift; its tick-based numbers were wrong); it is kept in
`baseline/results/superseded_revision/` and was re-run as `_v2` after the fix in `bench_e2e_variants.py`.
