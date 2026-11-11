# jpeg_passthrough: BENCH (timed results, run 20261109T230007)

- **Run:** runner `run_id` 20261109T230007, the timed overnight queue (2026-11-09 23:00 to 2026-11-10 05:36 local, UTC-5).
- **Machine:** "Gerald": i7-14700K, RTX 3070, Windows 11 (`platform` Windows-11-10.0.26300-SP0 in the rotate JSON). All output went to disk C:. Defender real-time protection was ON.
- **P-cores only.** The runner pinned every item to the 8 P-cores. **These results are for 16 logical CPUs (P-cores), not all 28.** The JSONs record `cpu_count` 28, because `os.cpu_count()` ignores affinity.
- **Versions as recorded:**
  - mux and open benches: PyAV 19.0.2 with bundled libavformat 63.1.102, libavcodec 63.1.102 and libavutil 61.1.102 (`meta.pyav`, `meta.pyav_ffmpeg_libs`).
  - open bench: OpenCV 4.12.0 (`meta.opencv`).
  - Tonight's JPEG JSONs record library versions, not the FFmpeg version string. FINDINGS.md gives "9.0.2" for this PyAV build (`pyav19_seek_ts_check.json` meta).
  - rotate bench: libjpeg-turbo 3.2.1 `turbojpeg.dll`, sha256 `3dd7a8a99dd744b4f53d8c8108cca703abe25c99cc526fc6bfc49ce681f975fd` (`meta.lib_sha256`). No PyAV is involved.
- **Paths** are relative to `research/skellycam_recording/recording_upgrade/` (RU) unless they start with `research/` or `C:`.
- **Labels:** "computed" = arithmetic on JSON fields. **inferred** = reasoning, not a measurement.

**Result files (tonight)**

| item | file |
|---|---|
| JP-MUX-PYAV19 | `results/jpeg_passthrough/bench/bench_mux_default_pyav19_20261110T055215Z.json` |
| JP-MUX-FSYNC-PYAV19 | `results/jpeg_passthrough/bench/bench_mux_fsync_pyav19_20261110T093308Z.json` |
| JP-ROTATE | `results/jpeg_passthrough/bench/bench_rotate_20261110T093546Z.json` |
| JP-OPEN-LONG-PYAV19 | `results/jpeg_passthrough/bench/open_long.json` |

Item stdout/stderr: `results/bench_runner/logs/20261109T230007/{17_JP-MUX-PYAV19,29_JP-OPEN-LONG-PYAV19,59_JP-MUX-FSYNC-PYAV19,60_JP-ROTATE}.{out,err}.txt`. All four `.err.txt` files are empty.

## 1. Load record

Source: the per-item load record (`items_load_2300.json` in the monitoring session's scratchpad), cross-checked against `results/BENCH_RUN_2300_LOG.jsonl`.

| # | item | start–end (local) | duration / estimate (min) | status, exit | CPU before, mean / max % | top process before (as recorded) | MsMpEng CPU-s during item | Defender scan events | load flag |
|---|---|---|---|---|---|---|---|---|---|
| 17 | JP-MUX-PYAV19 | 00:51:28–00:52:15 | 0.79 / 10 | ok, 0 | 3.11 / 6.9 | Corsair.Service.exe 1.67 | **32.44** | none | none |
| 29 | JP-OPEN-LONG-PYAV19 | 01:18:31–01:18:57 | 0.43 / 10 | ok, 0 | 3.58 / 11.8 | Corsair.Service.exe 1.95 | 1.23 | none | none |
| 59 | JP-MUX-FSYNC-PYAV19 | 04:32:09–04:33:08 | 0.98 / 10 | ok, 0 | 3.68 / 7.0 | Corsair.Service.exe 1.77 | **34.78** | none | none |
| 60 | JP-ROTATE | 04:33:19–04:35:46 | 2.45 / 3 | ok, 0 | 6.03 / 7.9 | SearchIndexer.exe 9.36 | 4.75 | none | none |

- **No item was load-flagged.** `load_over_15pct` is false for all four, and no Defender scan event (ids 1000/1001) fell inside any item.
- The raw runner log gives every item the flag "leftover processes after item (listed, not killed)". The processes it lists are the monitoring session's own bash shells and its log-polling `python -c` reader, not bench processes (`leftover_note` in the load record). Harmless.
- **Defender real-time activity was high during both mux items.** MsMpEng used 32.44 CPU-s in a 47 s item and 34.78 CPU-s in a 59 s item. Each mux item writes 260 output sets of 166–577 MB, including 3000-file `jpg_folder` sets. inferred: this is real-time scanning of the bench's own output. It is part of the measured environment, not a load flag. MsMpEng was not pinned, so it may have run on E-cores (inferred). See caveats.
- `meta.cpu_percent_before_1s` in the mux JSONs: 3.0 (default) and 4.6 (fsync).

## 2. Completeness

| item | verdict | evidence |
|---|---|---|
| JP-MUX-PYAV19 | **complete** | 130 runs = 13 containers × 2 sizes × 5 reps; 0 runs with an `error` key; every run has `frames` 3000; every summary row has `reps` 5. stdout prints all 130 lines with 0 `ERROR`s and "wrote …json". |
| JP-MUX-FSYNC-PYAV19 | **complete** | Same checks: 130 runs, 0 errors, `frames` 3000, `reps` 5 per case, `args.fsync` true. |
| JP-ROTATE | **complete** | 6 cases (720p/1080p × rot90/180/270) × 5 reps = 30 runs, `args.frames` 1000. The script raises on any failed transform (`bench_rotate.py:53-55`), and the exit code was 0. |
| JP-OPEN-LONG-PYAV19 | **complete** | See below. |

**Why the run times were far under the estimates (inferred).**
- **JP-MUX (47 s and 59 s against an estimate of 10 min).** One run is a fresh process (`bench_mux.py:150`) that muxes 3000 frames in 16–60 µs/frame, about 0.05–0.18 s, then closes. 130 such runs plus interpreter and PyAV start-up fit in under a minute. The 10-minute estimate was conservative.
- **JP-OPEN-LONG (26 s against an estimate of 10 min).** It did **not** reuse a pre-built file:
  - The script writes each 54,000-frame file fresh from RAM (`bench_open_long.py:59-71`) and deletes it after its reps (`:99`).
  - The JSON records about 2.99 GB per file (`files.*.bytes`), `meta.frames` 54000, `meta.reps` 5 and `meta.dry` false.
  - 5 timings are recorded per reader per container (`cv2_open_ms`, `pyav_open_ms`).
  - A full demux counted 54,000 packets in every container (`pyav_demux_packets`).
  - The recorded read times add up to about 16 s: the fmp4_perframe opens alone take 5 × 1.11 s + 5 × 1.22 s, plus 2.2 s of demux. The other ~10 s fit four ~3 GB page-cache writes at the ~18 µs/frame (720p) mux wall cost measured in JP-MUX (inferred).

**What open_long times** (code, `bench_open_long.py`):
- `cv2_open_ms` = `cv2.VideoCapture(path, CAP_FFMPEG)` plus `CAP_PROP_FRAME_COUNT`, with `release()` excluded (`:74-77`).
- `pyav_open_ms` = `av.open` plus `streams.video[0].frames`, timed before the context closes (`:79-82`).
- `pyav_demux_count_ms` = one full demux pass with no decode (`:89-92`).
- `count_exact` = the cv2 count equals `--frames` (`:96`).
- Every rep reads the file from the page cache, straight after the write (docstring `:15`). No cold-open time was measured.

## 3. Results

### 3.1 Mux cost per container (JP-MUX-PYAV19 default vs JP-MUX-FSYNC-PYAV19)

Field meanings (code, `bench_mux.py`):
- `cpu_us_per_frame_mux` = `time.process_time()` across the mux loop / N.
- `wall_us_per_frame_mux` = `perf_counter` across the same loop / N.
- `cpu_ms_close` and `wall_ms_close` = `container.close()`, plus, with `--fsync`, a reopen `r+b` and `os.fsync` (FlushFileBuffers) of the output (`:98-115`).
- Setup: 1 camera per fresh worker process, 3000 frames held in RAM, VFR timestamps (`:47-51`, `:150`).
- 720p = c930e_720p_flash, 891 frames looped, payload 55,341 B/frame (computed from `payload_bytes`/3000). 1080p = c922_1080p, 19 frames looped, 192,382 B/frame (`:44`, `:9-10`).
- Baselines:
  - `pkt_only` = `av.Packet` creation only, no muxing.
  - `raw_sidecar` = Python write plus a 20-byte index record.
  - `jpg_folder` = open, write and close one file per frame (`:54-80`).
- `jpg_folder` gets no fsync even with `--fsync`: only `raw_sidecar` and the libav containers are fsynced (`:72-79`, `:110-112`).
- Stream time base: `fmp4_*_tb_us` set 1/1e6 explicitly, and `avi_tb_rate` uses 1/30. `mp4`, `mov` and `nut` keep the muxer's default stream time base, with packets at 1/1e6 (`bench_mux.py:92-97`; `jp_io.py:31-49`).
- Container bytes/frame (computed) = (`bytes_on_disk` − `payload_bytes`) / 3000.

Values are the median (min–max) over 5 reps.

#### 720p (payload 55,341 B/frame)

| container | wall µs/frame, default | CPU µs/frame, default | close wall ms, default | wall µs/frame, fsync | CPU µs/frame, fsync | close wall ms, fsync | close CPU ms, fsync | container bytes/frame (computed) |
|---|---|---|---|---|---|---|---|---|
| pkt_only | 0.7 (0.7–0.7) | 0.0 (0.0–0.0) | 0.00 (0.00–0.00) | 0.7 (0.7–0.7) | 0.0 (0.0–0.0) | 0.0 (0.0–0.0) | 0.0 (0.0–0.0) | n/a (no file) |
| mkv | 19.0 (18.6–19.3) | 15.6 (15.6–20.8) | 0.38 (0.36–0.38) | 19.1 (18.7–20.6) | 20.8 (20.8–20.8) | 45.4 (41.8–57.9) | 31.2 (0.0–31.2) | 45.7 |
| mp4 | 17.9 (17.4–18.3) | 15.6 (15.6–20.8) | 0.27 (0.25–0.49) | 17.9 (17.4–18.4) | 20.8 (15.6–20.8) | 45.0 (39.6–54.6) | 15.6 (0.0–31.2) | 11.8 |
| fmp4_1s | 20.7 (20.5–21.4) | 20.8 (15.6–20.8) | 0.53 (0.50–0.71) | 20.6 (20.1–21.2) | 20.8 (15.6–20.8) | 45.1 (40.7–54.6) | 15.6 (0.0–31.2) | 12.4 |
| fmp4_perframe | 20.1 (19.6–20.7) | 20.8 (20.8–20.8) | 0.30 (0.29–0.33) | 19.9 (19.5–20.4) | 20.8 (10.4–20.8) | 45.5 (42.6–49.0) | 15.6 (0.0–46.9) | 131.3 |
| fmp4_1s_tb_us | 20.8 (20.6–20.9) | 20.8 (20.8–20.8) | 0.64 (0.52–0.76) | 20.9 (20.4–21.8) | 20.8 (15.6–20.8) | 42.9 (41.0–46.6) | 15.6 (0.0–46.9) | 12.4 |
| fmp4_perframe_tb_us | 20.4 (20.0–20.6) | 20.8 (15.6–20.8) | 0.28 (0.28–0.31) | 19.9 (19.6–20.4) | 20.8 (20.8–20.8) | 44.4 (40.4–60.0) | 0.0 (0.0–31.2) | 131.3 |
| mov | 18.0 (17.8–18.4) | 15.6 (15.6–20.8) | 0.27 (0.26–0.28) | 18.0 (17.4–18.2) | 15.6 (15.6–15.6) | 48.6 (39.7–51.5) | 15.6 (0.0–31.2) | 11.8 |
| avi_tb_rate | 16.1 (16.0–16.9) | 15.6 (15.6–15.6) | 0.23 (0.22–0.23) | 16.0 (15.9–16.1) | 15.6 (15.6–15.6) | 60.5 (51.7–151.1) | 31.2 (0.0–31.2) | 26.4 |
| nut | 17.6 (17.2–17.7) | 15.6 (15.6–20.8) | 0.57 (0.55–0.61) | 17.3 (17.0–17.5) | 15.6 (15.6–15.6) | 52.4 (51.8–54.6) | 15.6 (15.6–31.2) | 28.9 |
| mjpeg_raw_mux | 16.5 (16.2–17.1) | 15.6 (15.6–20.8) | 0.15 (0.14–0.16) | 16.2 (16.0–16.7) | 15.6 (15.6–15.6) | 81.9 (53.2–255.3) | 15.6 (0.0–31.2) | 0.0 |
| raw_sidecar | 20.0 (19.4–20.6) | 20.8 (20.8–20.8) | 0.14 (0.13–0.14) | 16.3 (16.2–17.1) | 15.6 (15.6–15.6) | 66.3 (56.9–68.9) | 15.6 (0.0–31.2) | 20.0 |
| jpg_folder | 217.9 (190.7–298.4) | 192.7 (187.5–218.8) | 0.00 (0.00–0.00) | 190.4 (187.5–215.5) | 187.5 (187.5–197.9) | 0.0 (0.0–0.0), no fsync | 0.0 (0.0–0.0) | 0.0 |

#### 1080p (payload 192,382 B/frame)

| container | wall µs/frame, default | CPU µs/frame, default | close wall ms, default | wall µs/frame, fsync | CPU µs/frame, fsync | close wall ms, fsync | close CPU ms, fsync | container bytes/frame (computed) |
|---|---|---|---|---|---|---|---|---|
| pkt_only | 0.7 (0.7–0.7) | 0.0 (0.0–0.0) | 0.00 (0.00–0.00) | 0.7 (0.7–0.7) | 5.2 (0.0–5.2) | 0.0 (0.0–0.0) | 0.0 (0.0–0.0) | n/a (no file) |
| mkv | 55.2 (54.3–56.7) | 52.1 (52.1–57.3) | 0.40 (0.38–0.41) | 54.6 (53.5–54.6) | 52.1 (52.1–57.3) | 145.6 (141.4–147.5) | 31.2 (0.0–62.5) | 45.8 |
| mp4 | 51.2 (50.9–53.3) | 52.1 (41.7–57.3) | 0.28 (0.27–0.29) | 50.2 (49.6–50.9) | 46.9 (41.7–52.1) | 144.6 (137.2–146.6) | 15.6 (0.0–46.9) | 12.1 |
| fmp4_1s | 59.9 (59.4–60.6) | 57.3 (57.3–62.5) | 1.54 (1.41–1.71) | 58.8 (58.1–61.7) | 57.3 (52.1–62.5) | 141.9 (139.7–149.6) | 31.2 (15.6–46.9) | 12.4 |
| fmp4_perframe | 55.7 (55.4–57.5) | 57.3 (52.1–57.3) | 0.30 (0.28–0.32) | 55.8 (54.9–56.1) | 57.3 (52.1–57.3) | 145.9 (138.3–389.1) | 31.2 (15.6–78.1) | 131.3 |
| fmp4_1s_tb_us | 60.2 (59.0–62.3) | 62.5 (57.3–62.5) | 1.54 (1.41–1.67) | 59.2 (58.3–59.7) | 57.3 (52.1–62.5) | 140.5 (140.2–146.9) | 31.2 (15.6–62.5) | 12.4 |
| fmp4_perframe_tb_us | 56.3 (55.5–61.0) | 57.3 (52.1–62.5) | 0.29 (0.27–0.31) | 55.0 (54.8–56.2) | 57.3 (52.1–57.3) | 139.3 (137.9–146.6) | 46.9 (0.0–62.5) | 131.3 |
| mov | 51.3 (50.7–52.1) | 52.1 (46.9–52.1) | 0.28 (0.27–0.30) | 50.9 (49.7–51.2) | 52.1 (46.9–52.1) | 139.2 (138.5–336.0) | 62.5 (15.6–78.1) | 12.0 |
| avi_tb_rate | 46.4 (45.6–47.9) | 46.9 (41.7–46.9) | 0.24 (0.22–0.25) | 46.2 (44.8–47.5) | 46.9 (41.7–46.9) | 154.9 (139.6–165.4) | 31.2 (0.0–62.5) | 26.6 |
| nut | 47.9 (47.3–48.2) | 46.9 (46.9–46.9) | 0.66 (0.62–0.67) | 47.2 (46.8–47.6) | 46.9 (41.7–46.9) | 155.4 (152.9–521.1) | 62.5 (46.9–78.1) | 33.8 |
| mjpeg_raw_mux | 46.4 (46.0–49.1) | 46.9 (41.7–46.9) | 0.18 (0.16–0.19) | 45.6 (44.9–46.1) | 46.9 (41.7–46.9) | 156.9 (152.7–162.8) | 31.2 (15.6–78.1) | 0.0 |
| raw_sidecar | 43.0 (42.1–43.5) | 41.7 (36.5–41.7) | 0.13 (0.12–0.16) | 41.8 (41.7–42.3) | 41.7 (36.5–46.9) | 145.4 (143.2–507.8) | 31.2 (0.0–78.1) | 20.0 |
| jpg_folder | 232.5 (224.9–251.0) | 224.0 (218.8–234.4) | 0.00 (0.00–0.00) | 223.4 (219.0–244.5) | 224.0 (213.5–224.0) | 0.0 (0.0–0.0), no fsync | 0.0 (0.0–0.0) | 0.0 |

**Reading the mux tables.**
- **Use wall µs/frame, not CPU µs/frame, to compare containers.**
  - Every CPU value is a whole multiple of 15.625 ms over 3000 frames, which is a step of 5.21 µs/frame. Checked on all 260 runs (0 exceptions). `cpu_ms_close` takes only multiples of 15.625 ms.
  - inferred: this is the Windows `GetProcessTimes` tick behind `time.process_time()`. CPU differences under about 5 µs/frame, and every CPU close value, are below resolution.
- **The libav containers are close to each other and to the raw-file baseline.**
  - 720p: wall 16.1–20.8 µs/frame for every libav container, against 20.0 µs/frame for `raw_sidecar` (default run).
  - 1080p: 46.4–60.2 µs/frame against 43.0 µs/frame.
  - At 720p, fMP4 at 1/1e6 (`fmp4_1s_tb_us` 20.8, `fmp4_perframe_tb_us` 20.4) costs the same as fMP4 at the default time base (20.7, 20.1).
- **One file per frame (`jpg_folder`) costs 4–12× a container per frame.**
  - 720p: 217.9 against 19.0 µs/frame (mkv). 1080p: 232.5 against 55.2 µs/frame (computed ratios: 11.5× and 4.2×).
  - Its 720p range is wide (190.7–298.4).
- **Close without fsync costs under 1 ms for every container** except fMP4 1 s at 1080p, which takes 1.54 ms at either time base.
- **Close with fsync costs about 43–82 ms at 720p** (166 MB file) and **139–157 ms at 1080p** (577 MB file), as medians. Single reps reach 255 ms (720p `mjpeg_raw_mux`) and 521 ms (1080p `nut`).
  - inferred: that is about 3.7–4.0 GB/s of flush throughput (166 MB / 45 ms, 577 MB / 145 ms). It is a whole-file flush at close, not a per-frame cost. Per-frame durability policies are measured in crash_resilience CR-FSYNC.
- **Container bytes/frame (computed):**
  - mp4 / mov / fMP4 1 s: 11.8–12.4 B/frame.
  - mkv: 45.7. raw_sidecar index: 20.0.
  - avi: 26.4. nut: 28.9 at 720p and 33.8 at 1080p.
  - **fMP4 per-frame: 131.3 B/frame**, which is 0.24 % of a 720p frame (computed).

### 3.2 Lossless rotation cost (JP-ROTATE)

Method (code, `bench_rotate.py:45-61`):
- `tj3Transform` with options 0, through the ctypes wrapper `rotate_check.TJ.transform`, which copies the input into a ctypes buffer and copies the output back to `bytes` on each call (`rotate_check.py:74-92`).
- 1000 frames per (size, op), 5 reps, single thread.
- 720p = c930e_720p_flash, 891 distinct frames. 1080p = c922_1080p, 19 distinct frames, looped.
- `cpu_us_per_frame` = `process_time`/frames; `wall_us_per_frame` = `perf_counter`/frames.

Values are the median (min–max) over 5 reps.

| size | op | CPU µs/frame | wall µs/frame |
|---|---|---|---|
| 720p | rot90 | 2125 (2062–2344) | 2138 (2124–2345) |
| 720p | rot180 | 2000 (1969–2000) | 2019 (2008–2023) |
| 720p | rot270 | 2234 (2188–2250) | 2238 (2235–2299) |
| 1080p | rot90 | 7188 (7078–7203) | 7211 (7179–7262) |
| 1080p | rot180 | 6703 (6656–6750) | 6753 (6668–6829) |
| 1080p | rot270 | 8781 (8703–8953) | 8873 (8743–9052) |

- The Rust comment "~1-2ms per frame" (`jpeg_transform.rs:4`, FINDINGS §5) roughly matches 720p here (2.0–2.2 ms). **It does not match 1080p (6.8–8.9 ms).**
  - Tonight's harness is Python ctypes calling `tj3Transform`; Rust calls the legacy `tjTransform`. The two are not identical, so this does not test the Rust number directly.
- inferred: at 30 fps, rot270 at 1080p is about 266 ms of CPU per second, about 27 % of one logical CPU per camera. 720p rot270 is about 67 ms per second (computed: wall µs/frame × 30).

### 3.3 Open time and frame count on a 54,000-frame file (JP-OPEN-LONG-PYAV19)

- c930e_720p_flash, looped to 54,000 frames (30 min at 30 fps), with real VFR intervals looped.
- Writer: PyAV 19.0.2 `add_mux_stream` passthrough. Stream time base 1/1e6 for the three MP4 variants; MKV keeps its default (`bench_open_long.py:37-38`, `:63-64`).
- Page cache warm. Values are the median (min–max) over 5 reps.

| container | file bytes | cv2 open + CAP_PROP_FRAME_COUNT, ms | cv2 frame count | PyAV open + stream.frames, ms | PyAV `stream.frames` | PyAV demux packets | full demux count, ms (1 run) | `count_exact` (cv2) |
|---|---|---|---|---|---|---|---|---|
| fmp4_1s_tb_us | 2,989,397,148 | 42.57 (41.42–55.10) | 54,000 | 45.69 (45.05–47.81) | 0 | 54,000 | 547.41 | true |
| fmp4_perframe_tb_us | 2,995,815,628 | **1107.28 (1104.80–1111.88)** | 54,000 | **1224.24 (1217.30–1228.59)** | 0 | 54,000 | 2220.53 | true |
| mp4_tb_us (plain, finalized) | 2,989,414,232 | 2.38 (2.33–7.74) | 54,000 | 2.95 (2.83–3.56) | 54,000 | 54,000 | 486.34 | true |
| mkv | 2,991,273,780 | 0.19 (0.19–4.93) | **53,819** | 0.17 (0.15–0.32) | 0 | 54,000 | 580.72 | **false** |

- **fMP4 per-frame fragments cost about 1.1 s (cv2) and 1.2 s (PyAV) per open of a 30-minute file.** That is about 26× fMP4 1 s fragments (42.6 ms) and about 465× a finalized MP4 (2.4 ms), computed from the medians.
  - inferred: FreeMoCap opens every camera file with `cv2.VideoCapture` plus `CAP_PROP_FRAME_COUNT` (script docstring `:10`, citing `video_group_helper.py:151,159`), so this cost is paid once per camera file at each open.
- **The cv2 count is exact on all three MP4 variants and short by 181 frames on MKV** (53,819 / 54,000). PyAV's `stream.frames` is 0 for fMP4 and MKV and exact only for the finalized MP4.
- **Counting by full PyAV demux** (no decode) takes 0.49–0.58 s for MP4, fMP4 1 s and MKV, and 2.22 s for fMP4 per-frame.
- The first rep is the slowest for cv2 (fmp4_1s 55.10, mp4 7.74, mkv 4.93 ms), then it settles.

## 4. Headline numbers

- **Container mux cost is small and close to a raw file write.** 720p: 16.1–20.8 µs/frame wall for every libav container (default run) against 20.0 for raw + sidecar. 1080p: 46.4–60.2 against 43.0. fMP4 at 1/1e6 costs 20.8 (1 s) and 20.4 (per frame) µs/frame at 720p. File: `research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/bench_mux_default_pyav19_20261110T055215Z.json`.
- **A folder of JPEGs costs 217.9 µs/frame (720p) and 232.5 µs/frame (1080p)**, against 19.0 and 55.2 for MKV. Same file.
- **fsync at close costs 43–82 ms (720p, 166 MB) and 139–157 ms (1080p, 577 MB)** (medians), with outliers up to 521 ms. File: `research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/bench_mux_fsync_pyav19_20261110T093308Z.json`.
- **fMP4 per-frame fragments add 131.3 B/frame**; fMP4 1 s adds 12.4, MP4 11.8 and MKV 45.7 (computed from `bytes_on_disk`). Both mux files.
- **Opening a 30-minute (54,000-frame) fMP4 with per-frame fragments takes 1107 ms (cv2) and 1224 ms (PyAV).** fMP4 1 s takes 42.6 / 45.7 ms; a finalized MP4 2.4 / 3.0 ms; MKV 0.19 / 0.17 ms. File: `research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/open_long.json`.
- **The OpenCV frame count is exact on every MP4/fMP4 variant at 54,000 frames, and 53,819 on MKV.** Same file.
- **Lossless rotation (tj3Transform via ctypes) costs 2.0–2.2 ms/frame at 720p and 6.8–8.9 ms/frame at 1080p** (wall medians). File: `research/skellycam_recording/recording_upgrade/results/jpeg_passthrough/bench/bench_rotate_20261110T093546Z.json`.

## 5. Caveats

- **P-cores only:** 16 logical CPUs, not all 28. One camera per process. Workers ran one at a time, so these are single-stream costs. Multi-camera contention is the write_throughput topic's job.
- **CPU-time resolution is 15.625 ms** (measured: every CPU value is a multiple; the cause is inferred).
  - Mux CPU µs/frame moves in steps of 5.21 µs, and close CPU ms in steps of 15.6 ms.
  - Rotate CPU values are also stepped (15.625 ms / 1000 frames = 15.6 µs), which is small next to 2–9 ms.
- **Page cache throughout.**
  - Default mux runs never reach the disk inside the timed window.
  - The fsync runs time FlushFileBuffers once at close; nothing is durable per frame.
  - open_long reads every file warm, straight after writing it. Cold-open times are not measured.
- **Defender real-time ON:** MsMpEng used 32.44 and 34.78 CPU-s during the two mux items.
  - inferred: this may inflate wall times, mainly `jpg_folder` (3000 file creates per run) and the fsync close. That would explain part of the wide `jpg_folder` range at 720p (190.7–298.4 µs).
  - No scan events fell in any item. Not a load flag.
- **Payloads are looped:**
  - 1080p mux and rotate use 19 distinct c922 frames;
  - open_long loops 891 c930e frames to 54,000.
  - Mux and open cost should not depend on content (open_long docstring `:12-14`); rotate cost might (not tested).
- **`mp4`, `mov` and `nut` in the mux bench keep the muxer's default stream time base,** not 1/1e6 (`bench_mux.py:92-97`). Only the `*_tb_us` fMP4 rows and the open_long MP4 rows set 1/1e6. `mp4_tb_us`, `mov_tb_us` and `nut_tb_us` were not in tonight's mux list.
- **`jpg_folder` is never fsynced** (`bench_mux.py:72-79`), so its "fsync" row is a second default run.
- **Rotation is timed through Python ctypes,** including two buffer copies per call. It is not the Rust `tjTransform` call. libjpeg-turbo 3.2.1, not the version Rust links.
- **The JSONs do not record the FFmpeg version string;** "9.0.2" comes from FINDINGS.md. Tonight's JSONs record libavformat/libavcodec 63.1.102.
- **The estimates were far above the actual run times** (47 s / 59 s / 26 s against 10 min each). The explanation in section 2 is inferred from per-run times. The JSON and stdout checks are what show the items are complete.
