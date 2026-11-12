# encoder_pairing FINDINGS: T-S6, sidecar records stay paired with their source frames through JPEG encoding

Date: 2026-11-12, Gerald (i7-14700K, UHD 770). Python 3.13.13, PyAV 19.0.2 / FFmpeg 9.0.2, numpy 2.5.4, simplejpeg 1.9.0.
Two other agents were running Electron tests at the same time: **timing numbers are indicative only**. Pairing and
crash results don't depend on timing.

*Written by a sub-agent; saved by the main session. Before saving, the main session checked these against the result files and the FFmpeg source copy: `qsv_pairing.json` summary (21/21 runs fully paired, 11,700 records); `crash_kill.json` (38/38 every record pairs, 38/38 recovered files fully paired, 0 CRC mismatches); `ASYNC_DEPTH_DEFAULT 4` (`qsv_internal.h:50`) and the release condition at `qsvenc.c:2655`.*

Labels: [M] measured (result file), [C] code read (path:line), [S] primary source, [I] inferred, [NV] not verified.
Paths: `R` = `research/skellycam_recording/recording_upgrade/results/`, `S` = `.../scripts/`,
`FF` = FFmpeg tag n9.0.2 (copies in the session scratchpad `encoder_pairing/ffsrc/`, sha256 in §7).

## 0. Answer

- Every sidecar record stayed paired with its own source frame and capture times on every path tested:
  - `mjpeg_qsv`: 11,700/11,700 records in 21 runs [M];
  - libjpeg-turbo workers: 5,694/5,694 [M];
  - after 38 hard kills: every record on disk, before and after recovery [M].
- Pairing was checked five ways per record:
  1. the JPEG CRC at the record's offset;
  2. a barcode decoded from the JPEG's pixels = `source_frame_number`;
  3. all three times = the truth for that frame;
  4. `write_index` = the record's position;
  5. the container packet with pts = `write_index` has the same CRC and offset.
- It holds because of the writer rule in §5: identity = a gap-free submit counter `seq` carried through the encoder,
  metadata held in a pending map, and records written only after their packet is on disk.
- **New:** the 3-call delay is FFmpeg's `async_depth` − 1 (default 4) [C]. With `async_depth=1` it is 0 [M], and the
  encoder holds nothing at a crash. The cost is about 17 ms of blocking per encode call [M].

## 1. Setup

- **Frames:** synthetic full-range YUYV, 720p and 1080p. A 48-bit barcode (32-bit id + 16-bit CRC) is drawn into Y in
  20×40 px blocks, over a gradient + noise background (`S/encoder_pairing/eplib.py`, `FrameSource`, `stamp_yuyv`).
  - The barcode survives JPEG at target A in every frame decoded (17,000+ frames, 0 read failures) [M].
  - JPEG sizes are 224 KB (720p) and 441 KB (1080p).
- **Fake capture times:** deterministic per `source_frame_number`, so a swap would show (`truth_times`). The
  "irregular" variant adds +120 ms on every 50th frame and −9 ms on every 7th.
- **Encoders:**
  - `mjpeg_qsv`: yuyv422 with `color_range` = JPEG (F2), `global_quality` 95 (720p) / 94 (1080p),
    i.e. `matched_settings.json` `mjpeg_qsv_422` yuy2 target A.
  - libjpeg-turbo: simplejpeg 1.9.0 `encode_jpeg_yuv_planes`, 4:2:2, quality 95/94, `fastdct=False`, in N spawned
    worker processes.
- **Binding:** the plan names no binding (`CAPTURE_AND_RECORDING_PLAN.md:50, 225`). The earlier studies used
  **simplejpeg 1.9.0** (libjpeg-turbo 3.1.2) [C: `S/intra_compare/benchpaths.py:3-4`;
  `R/hw_accel_target/FINDINGS.md` C2]. PyTurboJPEG was not used anywhere.
  - simplejpeg is not in the phase-1 venv. These tests used a scratch venv with `av==19.0.2`, `numpy==2.5.4`,
    `simplejpeg==1.9.0` (the same av/numpy as phase 1).
- **Writer:** `PairingWriter` (`eplib.py:419-504`).
  - MKV with `flush_packets=1`; pts = `write_index` at a fixed `Fraction(1, 30)` packet time base.
  - S1 64-byte record (SE §8.1).
  - Record k written after `mux(k+1)` with `offset = st_size − size` (`:480`). The last record after `close()`, found by
    searching the tail (`:497`).
- **Verify** (`eplib.py`, `verify`): for each record, read the JPEG at its offset, check the CRC, decode it, read the
  barcode, compare the times, and join to the demuxed packet by pts.

## 2. mjpeg_qsv (`S/encoder_pairing/pairing_qsv.py` → `R/encoder_pairing/qsv_pairing.json`)

### 2.1 How the delay works

- **[C] The delay is a FIFO depth, not a fixed property:**
  - `FF/libavcodec/qsvenc.c:2655`: a packet is returned only when `av_fifo_can_read(async_fifo) >= async_depth`, or on
    flush.
  - `FF/libavcodec/qsv_internal.h:50`: `#define ASYNC_DEPTH_DEFAULT 4`.
  - `FF/libavcodec/qsvenc_jpeg.c:65`: `mjpeg_qsv` exposes `async_depth` (range 1–INT_MAX).
- **[M] Packets per call:**

  | `async_depth` | Packets per call (first 20 calls) | Calls late | Returned by `encode(None)` |
  |---|---|---|---|
  | 1 | 1 from call 0 | 0 | 0 |
  | 2 | 0, then 1 each | 1 | 1 |
  | 4 (default) | 0, 0, 0, then 1 each | 3 | 3 |
  | 8 | 7 × 0, then 1 each | 7 | 7 |

  - The same at 720p and 1080p.
  - In every pairing run, every packet was exactly 3 calls late (depth 4) or 0 (depth 1).
- **[M] `packet.pts` carries the input pts back exactly** with time base 1/30, including gapped pts (0, 1, 5, 6, 7, 20,
  21, 1000).
  - `dts` = `pts`, `duration` = 0, `is_keyframe` = True, `opaque` = None.
  - [C] The route is pts → 90 kHz `TimeStamp` → back (`qsvenc.c:2117`, `:2668-2669`).
  - [I] With time base 1/fps and fps ≤ 90,000, both roundings are under half a unit, so the integer comes back exactly.
- **[M] A nanosecond time base breaks exact matching.** With pts = `arrival_ns` and time base 1/10⁹, 1 of 12 came back
  exact; max error 5,375 ns. Don't use capture time as the identity.
- **[M+C] `copy_opaque` can't be used.** `avcodec_open2("mjpeg_qsv")` returns EINVAL.
  - `FF/libavcodec/encode.c:816-817` rejects `COPY_OPAQUE` without `AV_CODEC_CAP_ENCODER_REORDERED_OPAQUE`.
  - `mjpeg_qsv` declares only `DELAY | HYBRID` (`qsvenc_jpeg.c:90`).
- **[M] `encode(None)` is terminal.** It returns the held packets in order. A second `encode(None)`, and any frame sent
  after it, raise `EOFError` (`avcodec_send_frame`). So: one encoder per recording.
- **[M] No frame was dropped or reordered:** 0 FIFO violations and 0 unknown pts in all pairing packets, plus 14,400
  more in the throughput runs.

### 2.2 Pairing runs

21 runs: 720p and 1080p × gap patterns × timing × depth 4/1, plus one `pts=sfn` run.
- Gap patterns: none; periodic (every 7th dropped); bursty (3 % chance of a 1–10 frame burst); switch (none → bursty →
  every 3rd dropped → a +1000 jump, changing mid-stream).
- Timing: unpaced; paced 30 fps; irregular (0.3–1.7× frame period, plus a 300 ms stall every 100 frames).

| Result | Value |
|---|---|
| Runs with every record paired | **21/21** [M] |
| Records = frames in | 11,700/11,700 [M] |
| Container pts in order, 0..N−1, offset = demux `pos + 4` | all runs [M] |
| `FLAG_GAP` count = `source_frame_number` gaps | all runs (e.g. switch: 85 = 85) [M] |
| Frame in → packet out, paced, depth 4 | p50 100 ms (= 3 frame periods) [M] |
| Same, irregular with a 300 ms stall | max 432 ms: packets wait in the encoder until 3 more frames arrive [M] |
| Same, depth 1 | p50 12–15 ms [M] |

- [I] Under depth 4, a camera stall delays the last 3 frames' packets by the stall. A writer must not assume packet
  time ≈ capture time.

### 2.3 Throughput sanity check (`throughput_qsv.py` → `qsv_throughput.json`; 1080p30, one thread + encoder per camera, 300 frames)

| Cameras | Depth | Calls late | Keep up (≥ 29.4 fps) | Encode call p50/p99 ms | Frame in → packet out p50/p99 ms | Paced-late frames |
|---|---|---|---|---|---|---|
| 1 | 4 | 3 in every packet | 1/1 | 2.1 / 3.0 | 100.6 / 101.3 | 0 |
| 4 | 4 | 3 in every packet | 4/4 | 5.7 / 7.9 | 101.9 / 106.4 | 4 |
| 8 | 4 | 3 in every packet | 8/8 | 10.5 / 15.1 | 105.1 / 113.2 | 15 |
| 16 | 4 | 3 in every packet | 15/16 (min 29.35) | 19.9 / 48.1 | 111.9 / 184.4 | 340 |
| 1 | 1 | 0 | 1/1 | 13.6 / 20.4 | 12.1 / 18.6 | 0 |
| 4 | 1 | 0 | 4/4 | 15.4 / 22.7 | 12.7 / 19.5 | 13 |
| 8 | 1 | 0 | 8/8 | 16.0 / 25.8 | 12.4 / 21.5 | 49 |
| 16 | 1 | 0 | 16/16 (min 29.58) | 23.8 / 50.3 | 18.3 / 40.4 | 1,353 (28 %) |

- **[M] The delay in calls doesn't grow with load.** Only the time per call grows.
- [I] 16 threads × 17 ms blocking calls still reach about 30 fps each, so the waits overlap. PyAV doesn't hold the GIL
  through the QSV sync.
- CPU per process was not captured: the `GetProcessTimes` call returned 0. TP3 measures it properly.
- **[M] Depth 1 costs about 17 ms per call, single stream, unpaced, at both resolutions** (720p 16.8 ms, 1080p 17.4 ms;
  about 58–61 fps per stream). Depth 4 runs at 1.5 / 2.2 ms per call (630 / 434 fps).
  - `timeBeginPeriod(1)` changed nothing, so it isn't Windows timer granularity (`qsv_ad1_timer_probe.json`).
  - The cause (the `MFXVideoCORE_SyncOperation` wait at `qsvenc.c:2665`, or the runtime) is [NV].

## 3. libjpeg-turbo worker pool (`pairing_turbo.py` → `turbo_pairing.json`)

- **Design** (`eplib.py`, `TurboPool`):
  - spawned workers; one task queue and one result queue;
  - results go into a reorder dict keyed by `seq` and are released while the oldest pending `seq` is present;
  - a worker-reported failure, or a `seq` missing past 2 s, is released as a skip;
  - in-flight cap 2 × workers, with backpressure.
- **[M] 11/11 runs fully paired:** 2/3/4 workers × jitter 0/15 ms unpaced at 1080p, paced 1080p30, the 720p switch
  pattern, and failure injection (every 97th frame).
  - 5,694 records = 5,700 frames − 6 injected failures.
  - Container pts in order in every run.
  - Without jitter, natural reordering was 0 at these loads. With 15 ms jitter: 77–177 out-of-order arrivals per run,
    730 in total.

| 1080p, unpaced, jitter 15 ms | 2 workers | 3 workers | 4 workers |
|---|---|---|---|
| Out-of-order arrivals | 77 | 161 | 175 |
| Reorder buffer max frames / bytes | 2 / 0.90 MB | 3 / 1.35 MB | 4 / 1.80 MB |
| Extra hold in the buffer p50 / p99 / max (ms) | 0.006 / 7.8 / 11.2 | 0.008 / 8.6 / 11.7 | 0.05 / 8.8 / 11.0 |
| Raw frames in flight (cap) | 4 (16.6 MB) | 6 (24.9 MB) | 8 (33.2 MB) |

- Paced 1080p30, no jitter: buffer max 1 frame, hold ≤ 0.16 ms [M].
  - Submit → release was about 36 ms, because this harness drains results only when the next frame is submitted. [I] A
    production collector that blocks on the result queue removes that period.
- **[M] An injected encode failure becomes a clean skip:** no packet, no record, later frames unaffected.
  - It shows up only as `FLAG_GAP` on the next record (gap flags 24 = 18 camera gaps + 6 skips).
  - [I] Add a distinct "encode skip" flag so a camera drop and an encoder drop can be told apart.

## 4. Hard kills (`crash_kill.py` → `crash_kill.json`; 720p30 paced, bursty gaps)

- **Kills:** a child process runs capture → encode → mux → sidecar and is killed by `os._exit(1)` at writer points:
  - `before_mux` (packet returned, not yet muxed);
  - `after_mux`;
  - `mid_record` (37 of 64 bytes written, then exit);
  - `after_record`;
  - `flush` k (during stop);
  - `after_container_close`.
  - Plus 3 × TerminateProcess (`Popen.kill`) at a random 1.5–4.0 s per mode.
- **Loss accounting:** from the child's flushed event log (S = submitted, M = muxed, R = recorded) and a demux of the
  killed file.

| Mode | `before_mux` | `after_mux` | `mid_record` | `after_record` | `flush` 0/1 | `after_container_close` | TerminateProcess ×3 |
|---|---|---|---|---|---|---|---|
| Passthrough | 2 (1 in hand + 1 held by muxer) | 2 (1 muxer + 1 on disk, no record) | 2, torn 37 B caught | 1 (muxer) | — | 1 (on disk, no record) | 1, 1, 1 |
| `mjpeg_qsv` depth 4 | 5 (4 + 1) | 5 (3 encoder + 1 + 1) | 5, torn caught | 4 (3 + 1) | 4 / 3 | 1 | 4, 4, 4 |
| `mjpeg_qsv` depth 1 | 2 | 2 | 2, torn caught | 1 | 0 / 0 (nothing to flush; ran to close) | 1 | 1, 1, 1 |
| turbo, 3 workers | 3 (2 + 1) | 3 | 3, torn caught | 2 (1 in pool + 1) | 2 / 0 | 1 | 2, 2, 2 |

- **[M] Every record on disk paired after every kill: 38/38 runs.**
  - 0 bad-CRC whole records.
  - Torn tails (37 B) were detected by length and CRC in 4/4 `mid_record` runs.
  - The record set was always a subset of the muxed set, and no record pointed at a lost frame.
- **[M] Loss = frames in the encoder or pool + 1 held back by the muxer, + 0–1 "on disk without record".**
  - The last case is a complete frame whose record (written one step later) hadn't been written. It is the price of
    rule 4 and is never a wrong pairing.
  - So the plan's "up to 3 frames in the encoder" means **3–5 lost per kill with `mjpeg_qsv` at depth 4** (4 in every
    TerminateProcess run), against 1–2 for passthrough and depth 1.
  - The 0–3 counts in some depth-1 and turbo flush runs are hook artefacts: there were too few packets for the flush
    hook to fire, so the run closed normally (N/A, not better crash behaviour).
- **[M] Recovery made a fully paired file in 38/38 runs** (`recover()`): truncate to valid records → remux → join by
  pts = `write_index` with a CRC check → drop packets with no record (0–1 per run) → rebuild offsets by scan.
  0 CRC mismatches.
- **[M] Turbo worker lifetime:**
  - The first matrix hung. A worker exiting after its parent died blocked joining its result-queue feeder thread (a full
    pipe that nobody drains), and the parent's `communicate()` waited on the stdout handle the worker had inherited.
  - Fix used: `cancel_join_thread()` on parent death (`eplib.py:273-274`), and child output to a file.
  - Even so, 2 of 9 `os._exit` runs still had a worker alive 2 s later; the harness killed them.
  - [I] Production needs a Job object with `KILL_ON_JOB_CLOSE`, or worker threads instead of processes.

## 5. The writer rule

1. **Identity.** `seq` = per-recording submit counter, 0..N−1 with no gaps. The pending map (insertion-ordered) holds
   `seq → (source_frame_number, arrival_ns, sample_time_ns, legacy_ns)`. Only `seq` goes into the encoder:
   - `mjpeg_qsv`: `frame.pts = seq`, codec time base `1/fps`;
   - turbo: in the task;
   - passthrough: used directly.
   - Never use a nanosecond pts (§2.1) or `copy_opaque` (refused). `source_frame_number` also works [M], but `seq` stays
     unique if the camera counter resets or wraps.
2. **In-order release.**
   - `mjpeg_qsv`: `meta = pending.pop(packet.pts)`; require it to be the oldest pending; on a mismatch or unknown pts,
     stop the recording with an error.
   - Turbo: reorder buffer by `seq`. A worker failure or timeout releases a skip (no packet, no record, an "encode skip"
     flag on the next record). In-flight cap 2 × workers; beyond it, the bounded writer queue drops and counts (row 1.5).
   - Passthrough: immediate.
3. **Mux.** `write_index` = packets muxed so far. Container pts = `write_index`, packet time base `Fraction(1, fps)`.
   `FLAG_GAP` when `source_frame_number` ≠ previous + 1.
4. **Record k** is written after `mux(k+1)` returns, `offset = st_size − size_k` (provisional flag). The last record
   after `close()` (tail search) or at finalisation (scan).
5. **Stop.** `encode(None)` once → mux its packets (3 at depth 4) → `close()` → last record. A new encoder per recording.
6. **Recovery** as in §4.
7. **Encoder depth.** Choose `async_depth` explicitly and write it in the sidecar header with the encoder name:
   - 1 → 0 frames held, about 17 ms blocking per frame;
   - 4 (default) → 3 held, about 100 ms latency at 30 fps.
   - TP3 decides between them (and 2).

## 6. Open

- `async_depth` 1 vs 2 vs 4 under TP3 load, with CPU measured. The cause of the 17 ms at depth 1 [NV].
- Real Kiyo Pro raw frames with the limited→full expansion: not tested (synthetic full-range input only).
- A `mjpeg_qsv` error mid-stream (no fault injection is possible); kills with several cameras at once; the cost of one
  `os.stat` per frame (T-S2).
- Add to T-S8 (pinned-version CI): `mjpeg_qsv` returns `pts` unchanged at time base 1/fps; the packet delay =
  `async_depth` − 1; `encode(None)` is terminal.
- Worker-process lifetime on Windows (Job object) if libjpeg-turbo stays in processes.

## 7. Files

- Scripts in `S/encoder_pairing/`: `eplib.py`, `pairing_qsv.py`, `pairing_turbo.py`, `crash_kill.py`,
  `throughput_qsv.py`, `qsv_ad1_timer_probe.py`.
- Results in `R/encoder_pairing/`: `qsv_pairing.json`, `turbo_pairing.json`, `crash_kill.json`, `qsv_throughput.json`,
  `qsv_ad1_timer_probe.json`.
- Venvs:
  - `skellycam-phase1/.venv` (read-only, `python -I`) for `pairing_qsv`, `throughput_qsv` and the timer probe;
  - a scratch venv (`av==19.0.2`, `numpy==2.5.4`, `simplejpeg==1.9.0`, Python 3.13.13) for `pairing_turbo` and
    `crash_kill`.
- FFmpeg n9.0.2 sources (raw.githubusercontent.com, tag n9.0.2), sha256:
  - `qsvenc.c` 4feac182…b7;
  - `qsvenc_jpeg.c` 292de0dd…8c;
  - `qsv_internal.h` c75d4fbb…5e;
  - `encode.c` 90db8ca6…fa;
  - `qsvenc.h` 389638fe…4b.
