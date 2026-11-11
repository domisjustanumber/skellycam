# crash_resilience: BENCH (timed results, run 20261109T230007)

- **Run:** runner `run_id` 20261109T230007, the timed overnight queue (2026-11-09 23:00 to 2026-11-10 05:36 local, UTC-5).
- **Machine:** "Gerald": i7-14700K, RTX 3070, Windows 11. Disk C: only (`drive` "C:" in the fsync JSON). Defender real-time protection was ON.
- **P-cores only.** The runner pinned every item to the 8 P-cores. **These results are for 16 logical CPUs (P-cores), not all 28.**
- **Versions as recorded** (`env` in every JSON):
  - Python 3.12.13; PyAV 19.0.2 with libavformat 63.1.102, libavcodec 63.1.102 and libavutil 61.1.102; OpenCV 4.12.0.
  - `ffmpeg_cli` "ffmpeg version 9.0.2-full_build-www.gyan.dev". That is the CLI on PATH. Tonight it was used only through ffprobe, to count frames in CR-REPAIR (inspection).
  - The repair writer child ran under the uv PyAV 19 interpreter (`writer_child_interpreter` = `C:\Users\Dom\AppData\Local\uv\cache\environments-v2\bench-repair-3b3a0ca94771b06c\Scripts\python.exe`), not the PyAV 18 venv.
- **Paths** are relative to `research/skellycam_recording/recording_upgrade/` (RU) unless they start with `research/` or `C:`.
- **Labels:** "computed" = arithmetic on JSON fields. **inferred** = reasoning, not a measurement.

**Result files (tonight)**

| item | file |
|---|---|
| CR-FSYNC-PYAV19 | `results/crash_resilience/bench/fsync_pyav19.json` |
| CR-FRAG-MJPEG-PYAV19 | `results/crash_resilience/bench/fragment_overhead_mjpeg_pyav19.json` |
| CR-REPAIR-PYAV19 | `results/crash_resilience/bench/repair_pyav19.json` |
| CR-FRAG-INTRA-PYAV19 | `results/crash_resilience/bench/fragment_overhead_intra_pyav19.json` |

- Item stdout/stderr: `results/bench_runner/logs/20261109T230007/{18_CR-FSYNC-PYAV19,19_CR-FRAG-MJPEG-PYAV19,28_CR-REPAIR-PYAV19,61_CR-FRAG-INTRA-PYAV19}.{out,err}.txt`. All four `.err.txt` files are empty.
- The `*_smoke*.json` files in the same folder are PyAV 18 smoke runs from a loaded machine (FINDINGS §5). Do not quote them.

## 1. Load record

Source: the per-item load record (`items_load_2300.json` in the monitoring session's scratchpad), cross-checked against `results/BENCH_RUN_2300_LOG.jsonl`.

| # | item | start–end (local) | duration / estimate (min) | status, exit | CPU before, mean / max % | top process before (as recorded) | MsMpEng CPU-s during item | Defender scan events | load flag |
|---|---|---|---|---|---|---|---|---|---|
| 18 | CR-FSYNC-PYAV19 | 00:52:26–00:52:40 | 0.23 / 5 | ok, 0 | 5.40 / 8.1 | SearchIndexer.exe 9.05 | 1.05 | none | none |
| 19 | CR-FRAG-MJPEG-PYAV19 | 00:52:51–00:52:59 | 0.12 / 6 | ok, 0 | 3.59 / 6.6 | AsusFanControlService.exe 1.58 | 5.38 | none | none |
| 28 | CR-REPAIR-PYAV19 | 01:13:47–01:18:20 | 4.55 / 8 | ok, 0 | 3.59 / 6.2 | AsusFanControlService.exe 1.58 | 10.25 | none | none |
| 61 | CR-FRAG-INTRA-PYAV19 | 04:35:57–04:36:05 | 0.14 / 9 | ok, 0 | 3.89 / 10.3 | AsusFanControlService.exe 1.52 | 1.36 | none | none |

- **No item was load-flagged.** `load_over_15pct` is false for all four, and no Defender scan event fell inside any item.
- The raw runner log gives every item the flag "leftover processes after item (listed, not killed)". The processes it lists are the monitoring session's own shells and its log-polling `python -c` reader, not bench processes (`leftover_note`). Harmless.
- nvidia-smi before and after each item showed 0 encoder sessions and 0 % utilisation. CR-FRAG-INTRA's own JSON records `nvidia_smi_before` and `nvidia_smi_after` as "0, 0 %". These are snapshots taken outside the short NVENC encode.

## 2. Completeness

| item | verdict | evidence |
|---|---|---|
| CR-FSYNC-PYAV19 | **complete** | `frames` 3000, `repeats` 3; all 9 policies have 3 repeats each. Every repeat wrote the same data size (166,023,810 B for the raw policies, 166,161,060 B for MKV). `started` 00:52:27, `finished` 00:52:40. stdout prints all 9 policies. |
| CR-FRAG-MJPEG-PYAV19 | **complete** | 19 variants, each with 3 repeats and `error` null. `frames` 3000. Payload 166,023,810 B in every repeat (3000 × 55,341 B, computed), so every repeat muxed 3000 packets. |
| CR-FRAG-INTRA-PYAV19 | **complete, as the script defines it** | See below. |
| CR-REPAIR-PYAV19 | **complete for the requested methods** | 4 recordings of about 0.975 GB, 17,618 frames requested each. `pyav_copy_mkv` ran ×3 on all 4. `resumable_repair` ran ×3 on mkv+fp, the only container the script gives it (`bench_repair.py:86`). The plain-MP4 rows are the expected "unrepairable" result (`InvalidDataError`, 0 packets), not a failure of the item. The ffmpeg CLI rows were excluded by `--methods`, as queued. |

**CR-FRAG-INTRA-PYAV19 (8 s against a 9 min estimate).**
- **What the script does** (code, `bench_fragment_overhead.py`):
  - It NVENC-encodes only `base = min(n, 300)` frames per payload into one template MKV (`:63-77`). This encode is untimed.
  - It demuxes those packets and loops them to `n` = 3000 packets with rising pts (`:78-88`).
  - Each timed repeat re-muxes those 3000 in-memory packets (`:117-164`).
  - The estimate assumed 3000 frames × 3 repeats of NVENC encoding. The script never does that, which explains the short run (inferred).
- **What the JSON shows:**
  - 32 rows = 16 variants × 2 payloads (`h264nv_intra`, `hevcnv_intra`), each with 3 repeats and `error` null.
  - `avi+fp`, `rawidx` and `folder` are skipped for these payloads by design (`:184-187`).
  - `payload_bytes` is constant across repeats: 114,716,900 B for H.264 (38,239 B/frame) and 134,859,760 B for HEVC (44,953 B/frame). These differ from MJPEG's 55,341 B/frame, so encoded packets, not JPEGs, were muxed (computed).
- **Did NVENC run?** `prepare_packets` is not wrapped in a try block (`:182`), so a failed NVENC open would have ended the script with a non-zero exit. The exit code was 0 (inferred: NVENC ran).
- **All-intra check.**
  - Tonight's JSON does not record keyframe flags. The queue's smoke check verified "templates all keyframes" with ffprobe (`BENCH_QUEUE_2300.md`, item 61).
  - Indirect evidence (inferred): `fmp4_kf` (one fragment per keyframe) and `fmp4_every` give identical container bytes, 131.3 B/frame, for both payloads. That holds only if every packet is a keyframe.

**CR-FSYNC and CR-FRAG-MJPEG (14 s and 8 s against 5 and 6 min).**
- One repeat takes 0.06–1.4 s (fsync: `wall_s`) or 0.04–0.6 s (fragments: `wall_s`).
- 27 and 57 repeats plus start-up fit in the observed times. The estimates were conservative (inferred).

## 3. Results

### 3.1 Durability policies (CR-FSYNC-PYAV19)

Method (code, `bench_fsync.py`):
- Each frame appends one camera JPEG (c930e_720p_flash, looped to 3000) to a data file, plus a 72-byte record to a sidecar (`:41`, `:86-102`).
- Policies (`:12-17`, `:94-101`):
  - `none` = Python buffered writes;
  - `flush` = `flush()` of both files every frame;
  - `fsync_every_K` = flush every frame plus `os.fsync` of both files every K frames;
  - `sidecar_fsync_1` = flush data, fsync only the sidecar, every frame.
- Latency = `perf_counter_ns` around the write and durability step of one frame (`:67/80`, `:90/102`). p50/p99 come from one sorted list per repeat (`:44-46`).
- MB/s = data-file bytes / wall time (`:105`, `:110`). Sidecar bytes are not counted.
- CPU µs/frame (computed) = `cpu_s` × 1e6 / 3000.
- Values are the median (min–max) over 3 repeats.

| policy | MB/s | wall s (3000 frames) | CPU µs/frame (computed) | latency p50 µs | latency p99 µs | latency max µs | data file bytes |
|---|---|---|---|---|---|---|---|
| none | 2612 (2587–2680) | 0.064 (0.062–0.064) | 20.8 (20.8–20.8) | 14.4 (14.0–14.9) | 80.3 (77.7–81.5) | 284 (221–324) | 166,023,810 |
| flush | 2484 (2359–2485) | 0.067 (0.067–0.070) | 26.0 (20.8–26.0) | 16.3 (16.2–17.1) | 81.7 (78.6–85.4) | 251 (241–291) | 166,023,810 |
| fsync_every_1 | 127 (125–128) | 1.304 (1.292–1.323) | 72.9 (62.5–78.1) | 409.3 (406.8–411.0) | 669.0 (649.7–699.4) | 8736 (8658–8772) | 166,023,810 |
| fsync_every_10 | 687 (664–694) | 0.242 (0.239–0.250) | 36.5 (15.6–36.5) | 17.5 (17.2–17.9) | 720.6 (698.1–739.9) | 3054 (2098–9318) | 166,023,810 |
| fsync_every_30 | 1066 (1040–1076) | 0.156 (0.154–0.160) | 26.0 (15.6–41.7) | 16.1 (16.0–16.2) | 883.4 (863.7–890.7) | 4173 (3596–9065) | 166,023,810 |
| fsync_every_300 | 1454 (1435–1505) | 0.114 (0.110–0.116) | 31.2 (26.0–36.5) | 15.7 (15.6–15.8) | 75.5 (75.4–79.7) | 12361 (6706–12566) | 166,023,810 |
| sidecar_fsync_1 | 238 (197–243) | 0.697 (0.683–0.842) | 46.9 (41.7–62.5) | 214.5 (208.1–222.4) | 374.4 (365.9–2672.9) | 2916 (604–58903) | 166,023,810 |
| mkv_fp_fsync_1 (confounded) | 121 (118–121) | 1.374 (1.374–1.412) | 119.8 (109.4–130.2) | 439.4 (433.6–446.8) | 699.5 (673.5–706.5) | 8680 (8648–8692) | 166,161,060 |
| mkv_fp_fsync_30 (confounded) | 857 (811–879) | 0.194 (0.189–0.205) | 52.1 (36.5–62.5) | 25.8 (25.7–26.4) | 942.2 (874.2–960.0) | 1306 (1230–9372) | 166,161,060 |

**Confounder in `mkv_fp_fsync_K`** (FINDINGS §5; `BENCH_QUEUE_2300.md`, "Notes for reading tonight's results").
- This policy writes Matroska through a **Python file object**: `av.open(f, "w", format="matroska", options={"flush_packets": "1"})` with `f.flush()` + `os.fsync` every K frames (`bench_fsync.py:60-79`).
- It also uses `add_stream("mjpeg")` with a 1/1000 packet time base (`:63-71`). The recorder and every kill test instead use the path-based `av.open(path, …, flush_packets=1)` with `add_mux_stream`.
- **So its numbers do not transfer to the recorder's writer.** A by-path policy was not benched, and how to fsync a path-opened file on Windows is NOT VERIFIED (FINDINGS §5).
- The other 7 policies are Python raw-file writes, not libavformat. They measure durability syscalls, not a container.

**Reading the table.**
- **`flush` per frame (which survives a process kill) costs almost nothing over `none`.** p50 16.3 against 14.4 µs; throughput 2484 against 2612 MB/s.
- **fsync on every frame costs about 400 µs per frame.** p50 409.3 µs, p99 669.0 µs, max 8.7 ms; throughput drops to 127 MB/s.
- **fsync every 30 frames keeps p50 at 16.1 µs,** but the fsync frame lands in the p99 (883.4 µs). Worst frame 4.2 ms (median); one repeat hit 9.1 ms.
- **fsync every 300 frames gives the largest single stall:** 12.4 ms median max, because each fsync flushes about 16.6 MB (computed: 300 × 55,341 B).
- **fsync of the sidecar only, every frame,** costs p50 214.5 µs. One repeat had a 58.9 ms worst frame and a 2.67 ms p99.
- inferred: one 720p MJPEG camera at 30 fps writes about 1.66 MB/s (55,341 B × 30). Even `fsync_every_1` (127 MB/s; p99 0.67 ms against a 33 ms frame interval) has headroom for one camera, but the stalls up to 8.7 ms (or 58.9 ms on the sidecar) must not block capture. Multi-camera fsync was not measured.

### 3.2 Container-setting overhead (CR-FRAG-MJPEG-PYAV19 and CR-FRAG-INTRA-PYAV19)

Method (code, `bench_fragment_overhead.py`):
- Packets are prepared in memory. Only muxing and file writing are timed (`:9-10`, `:117-164`).
- MJPEG = the camera's own JPEGs (c930e_720p_flash) with CFR pts at 1/1000 (`:56-57`). Intra = NVENC H.264 QP 14 / HEVC QP 11, `gop` 0, matched settings A (`:45-48`), re-muxed from a template with `add_stream_from_template(…, opaque=True)` (`:147-148`).
- `+fp` = `flush_packets=1`. `mkv_cl0` = `cluster_size_limit=0` + `cluster_time_limit=0`.
- fMP4 variants:
  - `fmp4_kf` = `frag_keyframe`;
  - `fmp4_every` = `frag_every_frame`;
  - `fmp4_frag_<ms>` = `frag_duration`;
  - `seg_mkv_<s>` = segment muxer.
  - Sources: `common_cr.py:64-82`; `bench_fragment_overhead.py:100-114`.
- `cpu_us_per_frame_median` = median `cpu_s` / frames (`:200`). `overhead_bytes_per_frame` = (file bytes − payload bytes) / frames (`:160-164`).
- Wall µs/frame (computed) = `wall_s` × 1e6 / 3000.
- 3000 packets, 3 repeats. Values are the median (min–max) over 3 repeats. Payload: MJPEG 55,341, H.264 intra 38,239, HEVC intra 44,953 B/frame (computed).

| variant | MJPEG CPU µs/frame | MJPEG wall µs/frame | MJPEG overhead B/frame | H.264 intra CPU µs/frame | H.264 intra wall µs/frame | H.264 overhead B/frame | HEVC intra CPU µs/frame | HEVC intra wall µs/frame | HEVC overhead B/frame |
|---|---|---|---|---|---|---|---|---|---|
| mkv | 20.8 (15.6–26.0) | 20.0 (19.5–20.5) | 45.8 | 20.8 (15.6–20.8) | 19.7 (19.2–19.9) | 45.7 | 15.6 (15.6–15.6) | 14.9 (14.8–15.1) | 45.8 |
| mkv+fp | 26.0 (26.0–26.0) | 24.9 (24.8–25.0) | 45.8 | 26.0 (20.8–26.0) | 22.4 (22.3–22.9) | 45.7 | 15.6 (15.6–15.6) | 17.9 (17.8–17.9) | 45.8 |
| mkv_cl0+fp | 26.0 (26.0–26.0) | 25.3 (24.9–25.5) | 45.8 | 20.8 (20.8–26.0) | 22.3 (22.0–22.6) | 45.7 | 15.6 (10.4–15.6) | 18.4 (17.9–18.6) | 45.8 |
| fmp4_kf | 20.8 (15.6–20.8) | 20.0 (19.7–20.1) | 131.3 | 20.8 (20.8–20.8) | 19.6 (19.5–20.7) | 131.3 | 15.6 (15.6–15.6) | 15.8 (15.5–15.8) | 131.3 |
| fmp4_kf+fp | 20.8 (20.8–26.0) | 25.1 (24.8–25.3) | 131.3 | 20.8 (20.8–20.8) | 21.3 (21.3–21.6) | 131.3 | 20.8 (20.8–20.8) | 17.6 (17.1–18.5) | 131.3 |
| fmp4_every | 20.8 (20.8–20.8) | 20.4 (19.7–20.5) | 131.3 | 20.8 (15.6–20.8) | 19.7 (19.6–20.0) | 131.3 | 15.6 (10.4–15.6) | 15.8 (15.5–16.1) | 131.3 |
| fmp4_every+fp | 20.8 (20.8–26.0) | 23.5 (23.4–23.7) | 131.3 | 20.8 (20.8–20.8) | 21.5 (21.2–21.8) | 131.3 | 15.6 (10.4–15.6) | 17.0 (17.0–18.5) | 131.3 |
| mp4 (plain) | 15.6 (15.6–15.6) | 17.6 (17.3–17.9) | 10.2 | 15.6 (15.6–15.6) | 18.1 (18.0–19.0) | 9.8 | 10.4 (10.4–15.6) | 14.0 (13.9–14.2) | 9.9 |
| nut+fp | 20.8 (20.8–20.8) | 22.0 (22.0–22.3) | 28.7 | 20.8 (15.6–20.8) | 20.5 (20.2–21.2) | 28.8 | 15.6 (15.6–20.8) | 16.7 (16.0–16.8) | 28.8 |
| avi+fp | 20.8 (20.8–20.8) | 20.4 (20.2–20.6) | 26.4 | skipped (by design) | – | – | skipped (by design) | – | – |
| fmp4_frag_100+fp | 15.6 (15.6–20.8) | 19.2 (19.0–19.4) | 50.6 | 20.8 (20.8–20.8) | 19.6 (19.3–19.7) | 50.6 | 15.6 (15.6–15.6) | 14.9 (14.6–15.2) | 50.6 |
| fmp4_frag_500+fp | 20.8 (20.8–20.8) | 19.8 (19.3–20.5) | 16.7 | 20.8 (15.6–20.8) | 19.8 (19.5–20.1) | 16.7 | 15.6 (10.4–15.6) | 15.4 (15.0–15.6) | 16.8 |
| fmp4_frag_1000+fp | 20.8 (20.8–20.8) | 19.7 (19.7–20.2) | 12.5 | 20.8 (20.8–20.8) | 20.4 (20.2–20.6) | 12.5 | 15.6 (15.6–15.6) | 15.8 (15.3–15.9) | 12.5 |
| fmp4_frag_2000+fp | 20.8 (20.8–20.8) | 19.9 (19.7–19.9) | 10.4 | 20.8 (20.8–20.8) | 20.3 (20.3–21.3) | 10.4 | 15.6 (10.4–15.6) | 15.9 (15.6–16.5) | 10.4 |
| seg_mkv_1+fp | 31.2 (31.2–31.2) | 32.0 (31.7–33.5) | 61.4 | 31.2 (31.2–31.2) | 30.6 (30.5–30.9) | 63.8 | 26.0 (26.0–26.0) | 26.8 (26.1–26.8) | 66.4 |
| seg_mkv_10+fp | 20.8 (20.8–20.8) | 21.6 (21.6–22.0) | 46.4 | 20.8 (20.8–20.8) | 22.1 (21.9–22.5) | 46.6 | 15.6 (15.6–20.8) | 17.2 (17.2–17.7) | 46.9 |
| seg_mkv_60+fp | 15.6 (15.6–20.8) | 23.1 (20.5–23.3) | 45.8 | 20.8 (20.8–20.8) | 21.1 (20.9–21.5) | 45.8 | 15.6 (15.6–20.8) | 16.8 (16.7–17.4) | 45.9 |
| rawidx | 36.5 (31.2–36.5) | 34.9 (34.8–38.3) | 32.0 | skipped (by design) | – | – | skipped (by design) | – | – |
| folder | 208.3 (187.5–208.3) | 207.3 (206.6–219.9) | 0.0 | skipped (by design) | – | – | skipped (by design) | – | – |

**Reading the table.**
- **The CPU columns are quantized.** Every value is a multiple of 15.625 ms / 3000 = 5.21 µs/frame (inferred cause: the Windows process-time tick). Compare variants by wall time.
- **`flush_packets=1` costs about 1–5 µs/frame of wall time** (computed from the medians):
  - MKV: MJPEG 20.0 → 24.9, H.264 19.7 → 22.4, HEVC 14.9 → 17.9 µs/frame.
  - fMP4 per-frame: MJPEG 20.4 → 23.5, H.264 19.7 → 21.5, HEVC 15.8 → 17.0.
  - **`cluster_size_limit=0` + `cluster_time_limit=0` adds nothing measurable on top of +fp** (25.3 / 22.3 / 18.4) and gives byte-identical files (45.8 / 45.7 / 45.8 B/frame).
- **Container bytes do not depend on the payload codec:**
  - MKV about 45.8 B/frame;
  - fMP4 per-frame (`kf` or `every`, the same for all-key payloads) 131.3;
  - fMP4 1 s fragments 12.5; 2 s 10.4; 100 ms 50.6;
  - NUT 28.7–28.8; plain MP4 9.8–10.2.
  - fMP4 per-frame is 0.24 % (MJPEG) to 0.34 % (H.264) of payload (computed).
- **The 1 s segment muxer costs the most of the container options:** 26.8–32.0 µs/frame wall and 61.4–66.4 B/frame. 10 s and 60 s segments cost about the same as plain MKV+fp.
- **Raw + CRC index with a flush per frame** (`rawidx`, two Python flushes per frame) costs 34.9 µs/frame. **One file per frame** costs 207.3 µs/frame. These are MJPEG only.
- The differences between payloads in absolute wall µs/frame (HEVC lowest) follow payload size (44,953 B for HEVC, 38,239 B for H.264, 55,341 B for MJPEG) only loosely. H.264 is smaller than HEVC but slower, so it is not settled which factor dominates (inferred; not investigated).

### 3.3 Repair (CR-REPAIR-PYAV19)

Method (code, `bench_repair.py`):
- Each recording is about 1 GB: MJPEG passthrough, 17,618 frames (`frames`), written by `writer_child.py` in `drained:N` mode under PyAV 19 and killed before close (`:43-53`, `:74`, `:81`). Making the recordings is untimed.
- `pyav_copy_mkv` = `common_cr.remux_pyav` to `.mkv` with `add_stream_from_template(opaque=True)` (`common_cr.py:293-316`).
- `resumable_repair` = `ResumableRecorder._repair_segment` (`resumable_recorder.py:198-228`) on a copy of the file. The copy is made before the timer starts (`bench_repair.py:93-103`).
- `seconds` = `perf_counter` around the repair call.
- `output_frames` = ffprobe count after the timed call (`:104`, `:114`).
- `input_frames_written` = the requested N (`:118`).
- No cache drop. `free_ram_mb_start` was 49,399 MB, so the about 1 GB inputs fit in the page cache (inferred: all repeats read from cache).
- Values are the median (min–max) over 3 repeats.

| recording (killed, unfinalized) | input GB | method | seconds | s/GB | frames out / frames written |
|---|---|---|---|---|---|
| mkv+fp | 0.9755 | pyav_copy_mkv | 0.884 (0.859–0.893) | **0.907 (0.881–0.916)** | 17,617 / 17,618 (all 3 reps) |
| mkv+fp | 0.9755 | resumable_repair | 0.941 (0.934–0.942) | **0.965 (0.957–0.965)** | 17,617 / 17,618 (all 3 reps; `repair_returned_frames` 17,617) |
| fmp4_every+fp | 0.9770 | pyav_copy_mkv | 1.314 (1.306–1.330) | **1.345 (1.337–1.361)** | 17,617 / 17,618 (all 3 reps) |
| mp4 (plain) | 0.9749 | pyav_copy_mkv | 0.000 (0.000–0.004), a failed open, not a repair | n/a | **0 / 17,618**: `InvalidDataError`, 0 packets |
| rawidx (.mjpeg, read with `-f mjpeg`) | 0.9751 | pyav_copy_mkv | 1.405 (1.395–1.412) | **1.441 (1.431–1.448)** | 17,618 / 17,618 (all 3 reps) |

- **A PyAV remux of a killed MKV+fp recording runs at 0.907 s/GB.** The resumable recorder's segment repair, which also checks SOI/EOI per JPEG, runs at 0.965 s/GB. fMP4 per-frame takes 1.345 s/GB and raw .mjpeg 1.441 s/GB.
- **Frames recovered:**
  - MKV+fp and fMP4 per-frame + fp: 17,617 of 17,618 (1 frame short).
  - raw .mjpeg: all 17,618.
  - plain MP4: none.
  - inferred: the 1-frame shortfall matches the 1-frame kill loss for MKV+fp and fMP4 every+fp in FINDINGS §2.1. The repair itself loses nothing that was readable.
- inferred: at about 1.66 MB/s per 720p camera (§3.1), 1 GB is about 10 minutes of one camera. Repairing that segment from cache takes about 0.9–1.0 s with the MKV methods. Cold-cache repair was not measured.

## 4. Headline numbers

- **A flush per frame is almost free; an fsync per frame is not.** `flush`: p50 16.3 µs, 2484 MB/s. `fsync_every_1`: p50 409.3 µs, p99 669.0 µs, max 8.7 ms, 127 MB/s. `fsync_every_30`: p50 16.1 µs, p99 883.4 µs, 1066 MB/s. File: `research/skellycam_recording/recording_upgrade/results/crash_resilience/bench/fsync_pyav19.json`. The `mkv_fp_fsync_*` rows are confounded and do not transfer to the recorder's writer.
- **`flush_packets=1` on MKV costs +4.9 µs/frame (MJPEG), +2.7 (H.264 intra) and +3.0 (HEVC intra) of wall time** (computed from medians). `cl0` adds nothing measurable and no bytes. Files: `research/skellycam_recording/recording_upgrade/results/crash_resilience/bench/fragment_overhead_mjpeg_pyav19.json` and `research/skellycam_recording/recording_upgrade/results/crash_resilience/bench/fragment_overhead_intra_pyav19.json`.
- **Container bytes are about 45.8 B/frame for MKV, 131.3 for fMP4 per-frame, 12.5 for fMP4 1 s and 28.7–28.8 for NUT,** the same for MJPEG and NVENC intra payloads. Same two files.
- **1 s segments are the most expensive container option** (26.8–32.0 µs/frame, 61.4–66.4 B/frame). One file per frame costs 207.3 µs/frame. Same two files.
- **Repair of a killed 1 GB MKV+fp: 0.907 s/GB (PyAV remux) and 0.965 s/GB (resumable segment repair), 17,617 of 17,618 frames recovered.** fMP4 every+fp takes 1.345 s/GB; raw .mjpeg 1.441 s/GB with 17,618 / 17,618; plain MP4 recovers 0 frames. File: `research/skellycam_recording/recording_upgrade/results/crash_resilience/bench/repair_pyav19.json`.
- **Sidecar-only fsync per frame:** p50 214.5 µs, 238 MB/s, with one 58.9 ms worst frame across 3 repeats. File: `research/skellycam_recording/recording_upgrade/results/crash_resilience/bench/fsync_pyav19.json`.

## 5. Caveats

- **P-cores only:** 16 logical CPUs, not all 28. One writer at a time; no multi-camera contention.
- **The CR-FSYNC confounder:**
  - `mkv_fp_fsync_K` writes through a Python file object with `add_stream`, not the path-based `flush_packets=1` + `add_mux_stream` writer used by the recorder and the kill tests (`bench_fsync.py:60-79`; FINDINGS §5).
  - A by-path fsync policy was not benched.
  - The other fsync policies measure Python raw-file writes, not a libavformat container.
- **CPU-time resolution is 15.625 ms** (measured: every value is a multiple of it; the cause is inferred). CPU µs/frame moves in steps of 5.21 µs at 3000 frames, so read wall time.
- **Page cache:**
  - Fragment and fsync runs write about 166 MB per repeat. Only the fsync policies reach the disk inside the timed window.
  - Repair inputs were read from cache (inferred from 49 GB free RAM; the first repeat is not slower).
  - No cold-cache number exists for any item.
- **Defender real-time ON.** MsMpEng used 1.05–10.25 CPU-s per item, with no scan events. Not a load flag; possible small influence on wall time (inferred).
- **Intra payloads are 300 NVENC packets looped to 3000** (`bench_fragment_overhead.py:63`, `:85-88`). The encode is untimed, and the template time base comes from the MKV template.
  - Tonight's JSON does not record keyframe flags. All-intra rests on the queue's smoke check plus the `fmp4_kf` = `fmp4_every` byte equality (inferred).
  - `avi+fp`, `rawidx` and `folder` are not run for intra payloads (`:184-187`).
- **MJPEG fragment runs use CFR pts at 1/1000** (`:57`), not real VFR capture times. The overhead bytes for a 1/1e6 VFR stream may differ (not tested).
- **Repair:**
  - Frames are counted by ffprobe 9.0.2 CLI after the timed call (inspection only).
  - The ffmpeg `-c copy` repair rows were not run (not the implementation under test).
  - `input_frames_written` is the requested count, not a measured one (`bench_repair.py:118`).
  - The plain-MP4 "seconds" is a failed open (`InvalidDataError`), not a repair time.
- **The estimates were far above the actual run times** (14 s / 8 s / 8 s against 5 / 6 / 9 min). The explanations in section 2 are inferred from the code and per-repeat times. The JSON and stdout checks are what show completeness.
