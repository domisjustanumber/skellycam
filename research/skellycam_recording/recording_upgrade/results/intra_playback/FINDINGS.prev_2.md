# intra_playback: intra-only H.264 / HEVC vs the JPEG path in Electron / Chrome (G8, G9)

Machine Gerald (i7-14700K, RTX 3070, Intel UHD 770 present but not used by Chromium). Updated 2026-11-10 with the quiet bench run `20261109T230007`, then revised after two verifiers (§8). This replaces the unverified draft of 2026-11-09.

Labels: **measured** (result file), **source** (primary source), **code** (file:line), **inferred** (minimal, marked). Unverifiable means NOT VERIFIED.
Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU). Abbreviations:
- `R` = `results/intra_playback/`
- `F` = `R/functional/<e35|e45|c156>/`: functional runs, 2026-11-09. These are untimed, and the three browsers ran in parallel on a shared machine.
- `B` = `R/bench/<e35|e45>/`: timed runs, 2026-11-10 00:34–01:13 and 03:43–03:51, quiet machine. The runner launched them with P-core affinity (16 logical CPUs), inherited by child processes (code: `scripts/bench_runner/run_queue.py:21-22,441-446`). The Electron processes' actual affinity was not recorded (NOT VERIFIED).
- Browsers: E35 = Electron 35.7.5 / Chromium 134.0.6998.205 (the skellycam-ui pin); E45 = Electron 45.2.3 / Chromium 156.0.8078.80; C156 = Chrome 156 (functional runs only). Versions are in `versions` in every JSON.

All numbers below were re-read from the raw JSON (functional totals re-summed, and every bench value checked against `B/**.json`). `R/BENCH.md` and `R/bench/bench_tables.md` agree with the JSON, except for two points: the GPU memory unit (see F22) and BENCH.md's "about one 60 Hz vsync" remark, which is wrong (see F18).

## 1. Questions answered

1. Can intra-only H.264 and HEVC from `h264_nvenc`, `hevc_nvenc`, `h264_qsv` and `hevc_qsv` (PyAV 19.0.2) be played, seeked, stepped and scrubbed frame-exactly in E35, E45 and C156, the same way the JPEG path can (Range fetch, then `createImageBitmap` or `ImageDecoder`)? (G8, G9)
2. What does each path cost per frame on a quiet machine: seek latency, multi-stream sync spread, scrub rate, CPU and memory? (G9)
3. What do E35 and E45 do differently? Which decoder runs (hardware or software)? Which seek rules work on real VFR timing?

**Quality note: these clips are NOT at target A or target B.**
- The clips were matched to about 55 dB Y-PSNR: 54.49–55.01 dB for the 1080p bench clips, and 54.49–55.72 dB across all functional clips (measured, `R/clips_summary.json`).
- That is higher than target A (SSIM-Y 0.9961, about 52 dB PSNR-Y) and target B (45 dB). Both targets come from intra_compare.
- The SSIM values here are an 8x8 box-window SSIM (`R/NOTES.md` §2), so they cannot be compared with A's SSIM-Y either.
- Do not mix the sizes or costs in this topic with intra_compare's numbers at A or B.

## 2. Findings

### 2.1 Frame-exact access (functional, all three browsers)

- **F1** measured: **all 48 intra clips open, play and seek in E35, E45 and C156.** The clips are 4 encoders × 3 containers (mp4 +faststart, fMP4, mkv) × 4 contents (720p30 and 1080p30, each CFR and real-capture VFR).
  - Paused `<video>` seek to the midpoint between this frame's real pts and the next (`mid`): 1200/1200 per encoder family, which is 4800/4800 per browser (`F/seek_*.json`).
  - code: the `mid` target is `(pts[k] + pts[k+1]) / 2` (`scripts/chromium_sync_scrub/harness/harness.mjs:74`).
- **F2** measured: **WebCodecs by index, with `flush()` after each chunk (`wcflush=1`), was 4800/4800 per browser.** Every seek decoded exactly one chunk (`decoded_hist {"1": n}`), so every intra frame decodes on its own (`F/seek_*.json`).
- **F3** measured: **single steps were exact.** `<video>` `mid` was 1464/1464 per encoder family (5856 per browser), forward and backward. WebCodecs with `wcflush=1` gave the same (`F/step_*.json`).
- **F4** measured: **the JPEG path was exact in every run.** This covers the concatenated `.mjpeg` file + index and JPEG-in-MKV + byte-offset index, each read by Range fetch.
  - Seeks: 800/800 per decode path (`createImageBitmap`, `ImageDecoder`) per browser (`F/seek_*.json`).
  - Steps: 976/976 per decode path per browser (`F/step_*.json`).
  - Playback pattern check, **`createImageBitmap` path only**: 600 draws / 0 mismatches on CFR and on VFR per browser (`F/play_*.json`). code: only `jpeg-master-range-bitmap` was in the play check (`scripts/chromium_sync_scrub/run_suite.py:224`).
- **F5** measured: **the CFR midpoint `(k + 0.5) / fps` (`cfrmid`) is exact only on CFR files.**
  - CFR: 600/600 per encoder family, which is 2400/2400 per browser.
  - VFR (real capture timing): 57/600 per encoder family, which is 228/2400 per browser.
  - VFR misses are +1 to +3 frames; e.g. every vfr720p clip has `off_by_hist {1: 39, 2: 33, 3: 21}` (`F/seek_vfr*.json`).
  - code: `harness.mjs:71`.
- **F6** code: **today's UI uses neither rule. It seeks to `frame / fps`, the start of the frame interval** (`skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:334`, read 2026-11-10).
  - Correction: the HANDOFF headline (`HANDOFF.md:170`) calls `(k+0.5)/fps` "the UI's current seek rule". That is wrong. `(k+0.5)/fps` is a CFR-only candidate fix, and it also fails on VFR (F5).
  - measured, background (chromium_sync_scrub F14, AV1 intra, not these files): the UI rule `k/fps` was 0/122 on vfr720p steps.
  - This topic did not run the `ui` mode on its own clips.
- **F7** measured: **`<video>` playback with rVFC readback showed 0 mismatches on CFR.**
  - On VFR there were 25 (E35), 62 (E45) and 55 (C156) mismatches over 3549, 3426 and 3294 rVFC callbacks (`F/play_vfr*.json`).
  - In every recorded example, the pattern read inside the callback was frame k+1 while `mediaTime` equalled pts[k] (`mismatch_examples`).
  - inferred: this is a readback race; rVFC is best-effort per chromium_sync_scrub F7. Which frame was actually on screen is NOT VERIFIED.
- **F8** measured: **master-clock playback (WebCodecs `wc-master` and JPEG bitmap) had 0 pattern mismatches** on CFR and VFR in all three browsers (`F/play_*.json`).

### 2.2 Decoders and codec support

- **F9** measured: **`<video>` and WebCodecs (no preference or `prefer-hardware`) use `D3D11VideoDecoder` for H.264 and HEVC in E35, E45 and C156** (DevTools Media log in `F/seek_*.json`).
  - measured: the active Chromium GPU is NVIDIA 0x10DE:0x2484 (RTX 3070), driver 32.0.16.1088. The Intel GPU is listed but inactive (`gpu_info.gpuDevice` in `F/seek_c1080p30.json` and every `B/**.json`).
  - So the QSV-encoded files were decoded on the NVIDIA GPU. Intel decode was not tested.
- **F10** measured: **HEVC has no software decode in E35, E45 or C156 on this Windows machine.** WebCodecs `prefer-software` for HEVC fails with `config not supported` for every HEVC clip (e.g. `hev1.1.6.L120.90`, `F/seek_*.json`).
  - H.264 with `prefer-software` decodes with `FFmpegVideoDecoder`: 360/360 exact per browser.
  - macOS, Linux and other Chromium builds: NOT VERIFIED.
- **F11** measured: **`h264_nvenc` needs `flush()` per frame in WebCodecs.**
  - No frame came out within 200 ms of `decode()`, so the harness's fallback flush fired on 360/360 seeks per browser, under no preference and under `prefer-hardware` (code: wait `flushAfterMs || 200`, then flush, `harness.mjs:153-158`).
  - `h264_qsv`, `hevc_nvenc` and `hevc_qsv` needed 0/360, and so did the software H.264 decoder (`F/seek_*.json`).
- **F12** measured: **the SPS fields differ.**
  - `h264_nvenc`: `bitstream_restriction_flag = 0`.
  - `h264_qsv`: `max_num_reorder_frames = 0`, `max_dec_frame_buffering = 2`.
  - Both HEVC encoders: `sps_max_num_reorder_pics = 0`; profile Main (`general_profile_idc = 1`) (`R/sps_vui_trace.txt`).
  - inferred: with no reorder bound, the H.264 hardware decoder keeps the frame back until it gets more data or a flush. Chromium's code was not traced (NOT VERIFIED).
  - Remedy, measured: `flush()` right after each key chunk was exact in every run (F2).
- **F13** measured: **MJPEG in MKV cannot be opened by `<video>`** in any of the three browsers (`DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, `mjpeg_qsv422.mkv`, 4 contents × 3 browsers, `F/seek_*.json`).
- **F14** measured: **the cameras' own JPEGs can be fetched out of an MKV by byte range (G1 + G9)**, tested on one 720p clip (`c720p30/camera_bytes_mkv`, 300 frames). Per browser: 300 sequential and 150 random fetches.
  - All 450 were byte-identical to the corpus files, started with SOI and ended with EOI, and decoded with both `createImageBitmap` and `ImageDecoder` (`F/jpegmkv_seq.json`, `F/jpegmkv_random.json`).
  - measured: in MKV, PyAV's `packet.pos` is 4 bytes before the JPEG payload for every packet (`pos_delta_hist {"4": n}`, `R/clips_summary.json`). The index must store the payload offset.
  - Untimed. No camera-byte file was in the timed bench (see P3).
- **F15** measured: **in E35 the MKV API probes report no support, yet the MKV files play.**
  - E35: `canPlayType('video/x-matroska; codecs=…') = ""` and MediaCapabilities `unsupported/not-smooth/not-powerEfficient`.
  - E45 and C156: `probably` / supported.
  - All three play the MKV files (`F/caps.json`, F1).
- **F16** measured, indirect (uncompressed_intra sample, not this topic's clips): **a libx265 all-intra 4:2:0 1080p MP4 (HEVC Rext) fails in E35 and plays in E45.**
  - The sample was made with `keyint=1`, CRF 20, `-tag:v hvc1`, by the ffmpeg 9.0.2 CLI (code: `scripts/uncompressed_intra/make_chromium_samples.py:46`).
  - measured (ffprobe inspection, 2026-11-10, `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/chromium_samples/hevc_intra_420.mp4`): `codec_name=hevc`, `profile=Rext`, `codec_tag=hvc1`, 1920x1080, yuv420p, `nb_frames=8`; method verifier saw `pict_type=I` on the frames it read.
  - E35: `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`. E45: loaded, drew a frame and seeked (`results/uncompressed_intra/chromium_check_electron{35,45}.json`).
  - measured: PyAV-made libx265 all-intra 4:2:0 streams are also Rext (`results/intra_compare/verification.md` rows `libx265_ultrafast_420`).
  - code: the generator declares the codec string `hvc1.1.6.L120.90` (Main) for this file (`make_chromium_samples.py:46`). That string does not match the stream. uncompressed_intra `VERIFY_method.md:28` calls the sample "Main" from that code; that is wrong.
  - inferred: the profile is the likely difference, since this topic's NVENC/QSV HEVC clips are Main (F12) and play in E35. Not isolated (NOT VERIFIED).
  - Frame-exact seek of a libx265 all-intra stream in Electron is NOT VERIFIED (see §6).

### 2.3 Timed bench (run 20261109T230007; N = 1/4/8; 1080p30 CFR mp4, 600 frames)

Each configuration ran once per Electron. Medians and min–max are within-run distributions, not repeats. Page latencies are `performance.now()` values quantised to 0.1 ms (measured: every `lat_ms` row in `B/bench_intra_seek/*.json` is a multiple of 0.1 ms), so differences of 0.2 ms or less are not claimed.

- **F17** measured: **every timed seek landed on the requested frame**: `exact` = 200/200 in all 24 seek configs, with 0 unreadable and 0 WebCodecs/JPEG errors (`B/bench_intra_seek/*.json`, `result.summary`).
- **F18** measured: **seek latency p50, from the request to a decoded frame or the rVFC callback** (`result.summary.lat_ms`, `lat_rvfc_ms`, `lat_seeked_ms`):
  - WebCodecs, 4 intra files: 2.7–2.9 ms (E45) and 3.1–3.4 ms (E35).
    - The max is 29.4–36.4 ms. In 7 of 8 configs it is the first seek (inferred: warm-up); the exception is E45 `h264_qsv` (row 32).
  - JPEG Range + `ImageDecoder`: 4.6 ms (E45) and 4.4 ms (E35).
  - JPEG Range + `createImageBitmap`: 6.0–6.1 ms (E45) and 7.0–7.1 ms (E35).
  - JPEG-in-MKV and `.mjpeg` differ by at most one timer tick (0.1 ms) in every case.
  - `<video>` `mid` until the rVFC callback: 8.5–14.1 ms (E45) and 11.8–14.1 ms (E35). The `seeked` event comes at p50 1.3–1.6 ms.
    - These p50s are under one 60 Hz frame period (16.7 ms). The cause of the rVFC delay is not determined. The display refresh rate was not recorded; rAF ticked 55.7–56.1/s in the master-clock sync configs (measured, F25).
- **F19** measured: **master-clock sync was frame-exact at N = 4 and N = 8**: spread 0/0/0 frames on 100% of ticks in all 28 master-clock configs (WebCodecs and JPEG, both Electrons) (`B/bench_intra_sync/*__{wc-master,jpeg-master-*}__n*.json`, `result.spread`). Spread is index-based (§5).
- **F20** measured: **Electron-process CPU of master-clock sync at N = 8**, total cores (`metrics_summary.cpu_cores_total_from_cumulative`):
  - E45: WebCodecs 0.51–0.57 (4 files), JPEG `ImageDecoder` 1.44, JPEG `createImageBitmap` 2.14.
  - E35: 0.58–0.63, 1.45 and 2.55–2.56.
  - Working set, E45: WebCodecs 872–1104 MB, `ImageDecoder` 987 MB, bitmap 1390–1396 MB (`total_ws_mb_last`).
  - code: the CPU figure sums Electron process CPU only (`scripts/chromium_sync_scrub/harness/main.cjs:93-101`). WebCodecs decode runs on the NVIDIA decoder (F9), which is not counted; nvidia-smi has only before/after point samples.
- **F21** measured: **N = 8 `<video>` sync has stalled tiles.**
  - In 19 of 20 N = 8 `<video>` configs (both Electrons, all files, free / leader / rVFC-steered), the slowest stream got 42–60% of the median stream's rVFC callbacks. The exception (E35 `hevc_qsv` `video-rvfc`) got 78%.
  - `presented_frames_delta` agrees, so the tile really presents fewer frames: e.g. E35 `h264_nvenc` `video-free` N = 8, slowest 16.0 vs about 28 presented/s (`result.per_stream[*].presented_frames_delta` / `dur_s`).
  - Max spread was 100–245 frames. Spread p95: 86–217 frames in the leader and rVFC-steered configs (12 configs), 195–244 in the free configs (8 configs). Neither correction method fixed the stall.
  - At N = 4, `<video>` spread max was 2–4 frames, with 21–90% of ticks at spread 0. But every tile presented only 27.3–28.1 of 30 frames/s, and `getVideoPlaybackQuality` reported 5.9–8.4% dropped, in both Electrons (`result.per_stream`, `result.dropped`).
  - Sources: `B/bench_intra_sync/*__video-*__n{4,8}.json`, `result.per_stream[*].rvfc_callbacks`, `result.spread`.
  - inferred: this is not a codec effect, because all four files and both Electrons show it. `wc-master` at N = 8 uses the same D3D11 decoder without stalling (F19), so decoder capacity is unlikely to be the cause (inferred). The cause (tile position, open order, compositor) is not determined.
- **F22** measured: **WebCodecs scrub has hidden errors, and GPU-process memory grows.**
  - E35 logged 914 per-stream `frameAt()` errors in 5 of 8 WebCodecs scrub configs:
    - H.264 NVENC N = 8: 300;
    - HEVC NVENC N = 4: 4;
    - HEVC NVENC N = 8: 80;
    - H.264 QSV N = 8: 523;
    - HEVC QSV N = 8: 7.
  - E45 logged 0 (`B/bench_intra_scrub/*__webcodecs__n*.json`, `result.per_stream[*].errors`).
  - The errors are invisible in `_index.json` and `bench_tables.md`. The index records only `result.error` (code: `scripts/chromium_sync_scrub/run_suite.py:358`), and the scrub summary prints no error or memory column (code: `summarize.py:181-186`).
  - In all 16 WebCodecs scrub configs, the GPU process's peak `private_kb` was 9,586,248–39,695,312 within the 8 s drag (`metrics_samples[type=GPU]`). That is 9.14–37.86 GiB if the unit is KiB. NOT VERIFIED whether Electron's "Kilobytes" are 1024 bytes; source: "Note that all statistics are reported in Kilobytes." (https://www.electronjs.org/docs/latest/api/structures/memory-info, accessed 2026-11-10). BENCH.md labels the same values "GB".
    - No `<video>` or JPEG scrub config exceeded 901,812 `private_kb` (0.86 GiB if KiB).
    - `wc-master` sync at N = 8 (sequential decode, no reset) peaked at 955,384–1,249,000 `private_kb` (0.91–1.19 GiB if KiB) in all 8 configs.
    - In 3 E35 N = 8 configs the GPU process was replaced: a second GPU pid appears in `metrics_samples` and private bytes fall to about 0.1 GB. inferred: a GPU-process crash or restart; no crash was logged.
  - inferred: the harness's per-target `reset()` + `configure()` + `flush()` cycle triggers the growth (code: `harness.mjs:137-152`), because the no-reset `wc-master` path stays near 1 GiB. Frames are closed after drawing (code: `harness.mjs:501`). So these scrub rates measure this harness pattern, not WebCodecs decode capacity.
- **F23** measured: **scrub rate, 8 s drag at 90 frames/s** (frames shown per second per stream, min–max over streams and both Electrons; lag p50/p95 in frames):

  | path | N = 4 | N = 8 |
  |---|---|---|
  | JPEG Range + `ImageDecoder` | 58.5–58.75 (ceiling), lag 2/2 | 58.0–58.62 (ceiling), lag 2/2 |
  | JPEG Range + `createImageBitmap` | 58.0–58.25 (ceiling), lag 2/2 | 41.75–50.75, lag 3–4/4–6 |
  | `<video>` gated (H.264 NVENC, HEVC NVENC, HEVC QSV) | 35.6–43.5, lag 3–5/6–8 | 33.0–45.5, lag 5–6/13–28 |
  | `<video>` gated (H.264 QSV) | 28.0–30.9, lag 5–6/9–10 | 17.25–21.6, lag 10–11/23–25 |

  - Sources: `B/bench_intra_scrub/*.json`, `result.frames_shown_per_s`, `result.lag_frames`.
  - code: the input loop calls `sleep(16)` per tick (`harness.mjs:485` for `<video>`, `:507` for JPEG/WebCodecs). measured: `input_events` was 365–479 per 8 s across scrub configs, a mean interval of 16.7–21.9 ms.
  - measured: **about 58–60 shown/s is the harness input-rate ceiling, not decode capacity.** `ImageDecoder` shown × 8 s (464–470) equals its `input_events` (465–470) at N = 4 and N = 8. `ImageDecoder` (N = 4, 8) and bitmap (N = 4) reach that ceiling; capacity above it is not measured.
  - measured: bitmap at N = 8 also cut `input_events` to 365–407, so its lower rate mixes decode cost with main-thread starvation.
  - code: the `<video>` scrub sets `currentTime = frame / fps` (the UI rule, `harness.mjs:482`), not `mid`. These clips are CFR.
  - Electron CPU at N = 8 was 3.05–3.20 cores for `ImageDecoder` and 4.2–4.3 for bitmap (`metrics_summary`).
  - WebCodecs scrub rates are left out of this table on purpose (F22).
- **F24** measured: **E35 vs E45 on the same files** (sources as above):
  - Seek exactness, master-clock spread 0 and the N = 8 `<video>` stall are the same in both.
  - E45 is faster for WebCodecs seeks in every file (p50 2.7–2.9 vs 3.1–3.4 ms; per-file gap 0.4–0.6 ms) and for `createImageBitmap` seeks (6.0–6.1 vs 7.0–7.1 ms). The `ImageDecoder` gap (4.6 vs 4.4 ms) is 2 timer ticks in one run, so no difference is claimed.
  - E45 fires fewer rVFC callbacks per stream at N = 4 (median 19.7–24.1/s vs 23.4–26.0/s, `rvfc_or_draws_per_s`), but frames presented per stream are the same in both (27.3–28.1/s, `presented_frames_delta`). The difference is in rVFC delivery only.
  - E35 logged the 914 WebCodecs scrub errors and the 3 GPU-process replacements; E45 logged none in a single 8 s run per config, with the same memory growth (F22). This is not stability evidence for E45.
  - JPEG bitmap scrub at N = 8: E45 49.0–50.75/s vs E35 41.75–42.5/s.
  - Functional: decoder choice, seek and step results are identical across E35, E45 and C156 (F1–F3, F9). E35 and E45 differ only in the MKV API probe (F15) and the libx265 Rext sample (F16).
- **F25** measured: **rAF runs at about half rate while `<video>` elements play.** rAF ticked 28.0–39.3/s in every `<video>` sync config (N = 4 and 8, both Electrons) vs 55.7–56.1/s in every master-clock config (`result.ticks / result.dur_s`, `B/bench_intra_sync/*.json`).
  - So `<video>` spread is sampled at about half the rate of master-clock spread; tick percentages are not directly comparable across paths.
  - Cause not determined.

## 3. Comparison tables

### 3.1 Path summary (1080p30; timed numbers from E45 unless stated; clips at about 55 dB, not A or B)

| path | frame-exact seek / step | seek p50 ms | N = 8 sync spread | N = 8 sync Electron CPU cores (a) | N = 8 scrub shown/s | software fallback | notes |
|---|---|---|---|---|---|---|---|
| `<video>` H.264 intra, `mid` from pts | yes (F1, F3, F17) | 8.5–12.0 to rVFC | p50 2–224, max 195–245 (stall, F21) | 0.44–0.55 | 17.25–41.75 (b) | yes, FFmpegVideoDecoder (F10) | `cfrmid` / `k/fps` fail on VFR (F5, F6); rAF ~28–39/s (F25) |
| `<video>` HEVC intra, `mid` from pts | yes | 14.0–14.1 to rVFC | p50 2–223, max 147–233 (stall) | 0.45–0.50 | 35.5–45.4 (b) | **none** on this machine (F10) | |
| WebCodecs H.264/HEVC intra, master clock | yes; `h264_nvenc` needs `flush()` (F11) | 2.7–2.9 | 0 (F19) | 0.51–0.57 (GPU decode not counted) | not usable (F22) | H.264 only | GPU-process memory growth in the scrub pattern |
| JPEG Range + `ImageDecoder` (`.mjpeg` or JPEG-in-MKV) | yes (F4, F17) | 4.6 | 0 (c) | 1.44 (c) | 58.0–58.5, harness ceiling (F23) | n/a (JPEG) | camera bytes byte-exact from MKV, 720p functional (F14) |
| JPEG Range + `createImageBitmap` | yes | 6.0–6.1 | 0 | 2.14 | 49.0–50.75 | n/a | slower than ImageDecoder at N = 8 |
| MJPEG in MKV via `<video>` | **cannot open** (F13) | – | – | – | – | – | |

- (a) code: Electron process CPU only (`main.cjs:93-101`); hardware decode work on the GPU is not included.
- (b) code: the `<video>` scrub seeks to `frame / fps`, not `mid` (`harness.mjs:482`); harmless on these CFR clips.
- (c) code: `ImageDecoder` sync ran on `jpeg_seq` (`.mjpeg`) only (`run_suite.py:260-261`).

### 3.2 E35 vs E45 (timed)

| measure | E35 | E45 | source |
|---|---|---|---|
| WebCodecs seek p50 (4 files), ms | 3.1–3.4 | 2.7–2.9 | `B/bench_intra_seek/*__webcodecs.json` |
| `<video>` seek to rVFC p50, ms | 11.8–14.1 | 8.5–14.1 | `*__video__mid.json` |
| JPEG ImageDecoder / bitmap seek p50, ms | 4.4 / 7.0–7.1 | 4.6 / 6.0–6.1 | `*__jpeg-range-*.json` (ImageDecoder gap = 2 timer ticks, not claimed) |
| N = 4 `<video>` median rVFC/s per stream | 23.4–26.0 | 19.7–24.1 | `bench_intra_sync`, `rvfc_or_draws_per_s` |
| N = 4 `<video>` presented frames/s per stream | 27.3–28.1 (both) | 27.3–28.1 (both) | `presented_frames_delta` / `dur_s` |
| N = 8 JPEG bitmap sync CPU cores | 2.55–2.56 | 2.14 | `metrics_summary` |
| N = 8 WebCodecs sync working set, MB | 684–745 | 872–1104 | `total_ws_mb_last` |
| WebCodecs scrub per-stream errors (8 configs) | 914 | 0 | `result.per_stream[*].errors` |
| GPU process replaced during WebCodecs scrub | 3 configs | 0 | `metrics_samples` GPU pids |
| MKV `canPlayType` / MediaCapabilities | "" / unsupported (plays anyway) | probably / supported | `F/caps.json` |
| libx265 all-intra 4:2:0 sample (CLI, Rext) | fails | plays | `results/uncompressed_intra/chromium_check_electron*.json` |

### 3.3 Bench clips (1080p30, 600 frames, 19 distinct source frames; about 55 dB, NOT target A or B)

| clip | setting | bytes/frame | Y-PSNR mean dB | box-SSIM Y |
|---|---|---|---|---|
| h264_nvenc intra | constqp 14 | 181,957 | 54.49 | 0.9969 |
| hevc_nvenc intra | constqp 11 | 213,013 | 54.92 | 0.9971 |
| h264_qsv intra | ICQ 8 | 223,571 | 54.93 | 0.9972 |
| hevc_qsv intra | ICQ 17 | 184,628 | 55.01 | 0.9972 |
| mjpeg_qsv 4:2:2 (`jpeg_seq`, `jpeg_in_mkv`) | q90 | 206,938 | 54.55 | 0.9975 |

- Source (measured): `R/clips_summary.json`, `clips.c1080p30/*`, `decode_check(_mp4)`, 60 quality frames.
- Y-PSNR is in limited-range units. The SSIM is an 8x8 box window, not ffmpeg's `ssim` filter (`R/NOTES.md` §2).
- These sizes come from a 3-QP sweep step on 19 looped pictures. They are not a matched-quality size comparison; use intra_compare at A or B for that.
- The JPEG clips are `mjpeg_qsv` re-encodes, not camera bytes. For scale, measured: the mean C922 1080p camera JPEG is 192,382 B (`results/intra_compare/camera_jpeg_quality.md`, row `c922_1080p`), so the proxy is about 8% larger.

## 4. Implications for the plan

- **P1 (F19, F21, F25) inferred: the multi-camera player should run on one master clock and draw to canvas, through WebCodecs or JPEG `ImageDecoder`, not N `<video>` elements.**
  - At N = 4, `<video>` spread holds (max 2–4 frames), but each tile presents about 28 of 30 frames/s with 6–8% dropped. At N = 8, tiles stall. Master-clock paths had spread 0 at N = 8.
  - inferred: overlays drawn on rAF would update at about 28–39 Hz while `<video>` plays (F25).
- **P2 (F1, F5, F6) inferred from those findings: seek by the file's own timing.** Use the pts midpoint for `<video>`, or a frame index for WebCodecs/JPEG.
  - Today's `frame / fps` (code) and the CFR midpoint `(k + 0.5) / fps` (measured) both miss on real VFR recordings.
- **P3 (F4, F14, F17, F18, F23) inferred: the JPEG passthrough path (G1, G7) is a good fit for G9 on this machine, at N ≤ 8, 1080p30.**
  - measured: frame-exact, 4.4–4.6 ms seek p50, and at N = 8 `ImageDecoder` scrub reached the harness input ceiling (about 58 shown/s).
  - The timed numbers are for `mjpeg_qsv` re-encoded JPEGs of similar size (206,938 B vs a 192,382 B camera mean), not the cameras' own files (inferred: a fair proxy). Timing on camera bytes is NOT VERIFIED; camera-byte MKV access was only tested functionally at 720p (F14).
  - Its cost is CPU: 1.44 Electron cores for N = 8 sync with `ImageDecoder` vs 0.51–0.57 for WebCodecs H.264/HEVC (E45). The WebCodecs figure leaves out the hardware decode work on the GPU (code: `main.cjs:93-101`). inferred: without hardware decode, H.264 falls back to software decode (CPU cost not measured) and HEVC has no path (F10).
  - inferred: prefer `ImageDecoder` over `createImageBitmap`, which costs 2.14 cores and drops to 49–51 shown/s at N = 8.
- **P4 (F13, F14) measured basis, inferred recommendation: store camera JPEGs in MKV (or a raw file) with a sidecar index of payload offsets (`packet.pos` + 4, measured).** Do not rely on `<video>` for MJPEG.
- **P5 (F10, F9) inferred: an HEVC-only recording may not be playable in Chromium on a machine without HEVC decode hardware**, because no software fallback was found in these Windows builds. H.264 intra falls back to FFmpeg.
  - Machines without HEVC hardware, and macOS/Linux, are NOT VERIFIED. hw_accel_target owns the hardware-coverage question.
- **P6 (F11, F12) measured basis, inferred recommendation: if the UI decodes H.264 intra with WebCodecs, call `flush()` after each key chunk.** Otherwise `h264_nvenc` output does not appear within 200 ms.
  - Alternative, not tested: an encoder option that writes `bitstream_restriction` (NOT VERIFIED).
- **P7 (F22) inferred: a WebCodecs scrub design must be benchmarked before it is chosen.** The tested per-target `reset/configure/flush` pattern grew GPU-process `private_kb` to 9,586,248–39,695,312 (9.14–37.86 GiB if KiB) in 8 s, and in 3 E35 configs the GPU process was replaced (new pid).
  - So no WebCodecs scrub capacity figure is available yet. The seek and sync numbers (F18–F20) stand.
- **P8 (F15, F16, F24) inferred: on this machine (NVIDIA D3D11 decode), moving the UI from E35 to E45 is not needed for NVENC/QSV H.264 or HEVC Main intra.**
  - Seek and step results are identical in both, and E35 plays MKV despite its probe.
  - E45 is needed for the tested libx265 all-intra (Rext) sample.
  - E35 and E45 on machines without HEVC hardware, or with Intel/AMD decode: NOT VERIFIED.
- **P9 (§1 quality note) inferred: these playback costs were measured at about 55 dB, above target A.**
  - At A the intra frames are smaller (intra_compare), so fetch and decode per frame should be no worse. This is NOT VERIFIED, because no clip at A or B was played.

## 5. Run flags and caveats that apply to this topic

- **Single run per config** (BENCH_RUN_2300_SUMMARY §3 flag 12). Min–max are within-run distributions; between-run variance is unknown.
  - IP-SYNC-QSV ran about 3 h after IP-SYNC (03:43 vs 00:36), so the QSV and NVENC sync rows were not measured back to back (`results/BENCH_RUN_2300_LOG.jsonl`).
- **CPU affinity:** items were launched with P-core affinity (log `affinity: "pcores"`, 16 logical CPUs of 28), which child processes inherit (code: `scripts/bench_runner/run_queue.py:21-22,441-446`). The Electron, GPU and renderer processes' actual affinity is not recorded (NOT VERIFIED); flag 2 shows a child can widen it.
  - CPU cores here are Electron-process CPU time over the window (code: `scripts/chromium_sync_scrub/harness/main.cjs:93-101`), not system CPU. GPU decode load appears only in nvidia-smi point samples.
- **Load record:** 0 of 11 intra_playback items flagged `load_over_15pct`. CPU before each item averaged ≤ 4.11%, max 10.25%. No Defender scan event fell inside an item (`BENCH_RUN_2300_LOG.jsonl`).
- **Defender:** stayed on and was not changed. MsMpEng used 8.91–29.19 CPU-s in the 7 bench items (0.19–0.55 in the 3 IP-SUM summariser items), e.g. IP-SEEK-E35 9.55 CPU-s in a 33 s item (measured, `BENCH_RUN_2300_LOG.jsonl` lines 13–16, 26–27, 48–49).
  - This CPU is not in the Electron CPU figures. Whether file-open scanning affected Range latency is NOT VERIFIED.
- **Timer resolution:** page latencies are quantised to 0.1 ms (measured, F18 preamble). The 15.625 ms CPU-timer flag: the granularity of Electron `cumulativeCPUUsage` on Windows was not checked (NOT VERIFIED); its effect is negligible (inferred: at most about 0.002 cores per process over an 8–15 s window).
- **WebCodecs scrub hidden errors and GPU memory** (flag 5): see F22. `_index*.json` and `bench_tables.md` must not be used as error or memory evidence for the scrub.
- **N = 8 `<video>` stalled tiles** (flag 6): see F21.
- **Seek configs record no CPU or memory**, because `metrics_summary` is null (code: `harness.mjs:238-313`). Whether the WebCodecs seek pattern (199 resets per 200 seeks) also grows GPU memory is unknown.
- **The sync bench does not read pixels** (`readpattern` not set; code: `run_suite.py:246-275`). Spread is index-based, and it is sampled on rAF, which runs at different rates per path (F25). Pixel checks are from the functional runs (F7, F8).
- **Localhost HTTP, warm page cache:** JPEG and WebCodecs latencies include a Range fetch with `cache: 'no-store'` from the harness's local server (code: `harness.mjs:129`). The server opens the file per Range request (code: `harness/server.cjs:57`) and runs in the Electron main process, so its CPU is in the totals (code: `main.cjs:12`). The same files were re-read across configs (inferred: warm OS page cache). Cold-disk and network latency were not measured.
- **The functional runs were not quiet:** E35, E45 and C156 ran in parallel on a shared machine. They carry no timing or rate claims.
- **Flags that do not apply here:**
  - libx265 affinity widening (intra_compare items 1–3);
  - the NVENC 12-session limit (encode only);
  - nvJPEG missing target A;
  - write-latency and lossless-check flags.

## 6. Not tested / limits / NOT VERIFIED

- **NOT VERIFIED: whether libx265 all-intra (Rext profile) plays frame-exactly in Electron.** The only evidence is F16:
  - one CLI-made 8-frame `keyint=1` sample (measured Rext) fails in E35 and plays in E45;
  - no PyAV-made libx265 intra stream was loaded;
  - no seek or step test was run.
- NOT VERIFIED: HEVC 4:2:2 (`hevc_qsv` from YUY2, Rext) playback.
  - chromium_codecs NOTES §3 probes show E35 unsupported and E45/C156 supported.
  - hw_accel_target NOTES_functional §4 shows NVIDIA cannot decode it. No clip was played.
- NOT VERIFIED: playback timing on the cameras' own JPEG bytes. The timed bench used `mjpeg_qsv` re-encodes (P3); camera-byte MKV access was tested functionally on one 720p clip (F14).
- One machine, NVIDIA decode only. Not tested:
  - Intel, AMD or Apple GPU decode;
  - a machine without HEVC decode hardware;
  - Linux or macOS.
- **Bench coverage:**
  - 1080p30 CFR MP4 only, 600 frames with 19 distinct pictures looped. fMP4, MKV (video), VFR, 720p and long files were not benched; the functional runs cover them without timing.
  - N = 16 was not run.
  - Scrub capacity above the harness's ~60 inputs/s is not measured (F23).
  - The display refresh rate was not recorded, and a Parsec virtual display adapter was present.
- No clip at target A or B was played. Playback cost at A or B is inferred only (P9).
- Not measured:
  - a sequential WebCodecs scrub without a per-target reset;
  - a WebCodecs scrub that bounds GPU memory;
  - CPU cost of software H.264 decode in the sync or scrub pattern.
- NOT VERIFIED: whether Electron's `MemoryInfo` "Kilobytes" are 1000 or 1024 bytes (F22).
- NOT VERIFIED: the actual CPU affinity of the Electron processes in the timed run (§5).
- NOT VERIFIED: which frame was on screen during the VFR `<video>` readback mismatches (F7).
- NOT VERIFIED: the cause of the `h264_nvenc` flush need beyond the SPS field (F12). No NVENC option for `bitstream_restriction` was checked.
- Each functional "plays" check covers 5 s per clip. The 0.011 ms VFR frame pair (frames 81/82) was not targeted (chromium_sync_scrub F16a covers it for older clips).
- Not tested: the cause of the N = 8 `<video>` stall (F21), the cause of the halved rAF rate during `<video>` playback (F25), the cause of the `<video>` rVFC seek delay (F18), and why H.264 QSV `<video>` gated scrub is slower than the other files (F23).

## 7. How to reproduce

From the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`. Media (3.9 GB) is only under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_playback/`.

```
# clips (PyAV 19.0.2, PEP 723 pins av==19.0.2, numpy==2.2.6)
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_playback/gen_intra_clips.py > research/skellycam_recording/recording_upgrade/results/intra_playback/gen_intra_clips.log 2>&1
bash research/skellycam_recording/recording_upgrade/scripts/intra_playback/trace_headers.sh > research/skellycam_recording/recording_upgrade/results/intra_playback/sps_vui_trace.txt
# functional (writes results/intra_playback/functional/<e35|e45|c156>/)
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite intra_functional
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite intra_functional
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron chrome --suite intra_functional
uv run --script research/skellycam_recording/recording_upgrade/scripts/intra_playback/summarize_intra.py
# timed bench: quiet machine, one at a time, display on; queue ids IP-* in results/bench_queue_2300.json
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron <35|45> --suite bench_intra_seek
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron <35|45> --suite bench_intra_sync --skip _qsv_
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron <35|45> --suite bench_intra_sync --only _qsv_
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron <35|45> --suite bench_intra_scrub
uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/summarize.py bench intra
# libx265 sample profile (inspection only)
ffprobe -v error -show_entries stream=codec_name,profile,codec_tag_string,width,height,pix_fmt,nb_frames -of compact C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/chromium_samples/hevc_intra_420.mp4
```

- The runner for the queued run was `scripts/bench_runner/run_queue.py`; use `--only IP-SEEK-E35,...` for a subset.
- Read scrub errors and GPU memory from the per-config JSON (`result.per_stream[*].errors`, `metrics_samples[type=GPU].private_kb`), not from `_index.json` or `bench_tables.md`.
- rAF rate: `result.ticks / result.dur_s`; presented frames: `result.per_stream[*].presented_frames_delta`; scrub input rate: `result.input_events`.
- Full per-config tables: `R/BENCH.md`. Functional tables: `R/functional_tables.md`. Clip generation details and harness changes: `R/NOTES.md` §2–3.

## 8. Verification (2026-11-10)

**Verifiers.** Two independent checks of the 2026-11-10 draft: provenance (`R/VERIFY_provenance.md`) and method (`R/VERIFY_method.md`). Neither ran a timed measurement.
- Provenance re-summed every functional total, re-computed every bench number from `B/**.json` (seek, sync, scrub, CPU, working set, rVFC, spread, the 914 hidden errors, GPU pids), clip sizes and PSNR, the load record, and re-opened every code reference. All matched except the items below. It also fetched the Electron MemoryInfo doc.
- Method re-read the bench JSON by script, re-summed functional totals, and ran one ffprobe inspection of the libx265 sample.
- Reviser re-checked each refutation and most weak points against the raw files before applying them: GPU `private_kb` peaks, rAF ticks/s, N = 4 presented frames, N = 8 p95 by path, scrub `input_events`, `wc-master` GPU peaks, per-file seek p50s, Defender CPU per IP item, the ffprobe profile of the sample, `sps_vui_trace.txt` HEVC profile, and `harness.mjs:153-158,480-486,505-507`, `run_suite.py:224,258-262`.

**Refuted and corrected.**
- F22 GPU memory: the draft's "9.6–39.7 GB decimal" assumed 1000-byte kB while its GiB figure assumed 1024. Now the raw `private_kb` range is quoted with one conversion and its assumption (P7 too).
- F18: "about 14 ms is one 60 Hz vsync" was wrong (one 60 Hz period is 16.7 ms). Removed; replaced with "under one 60 Hz period; cause not determined". BENCH.md carries the same wrong remark.
- F16: "profile not probed" was replaced by the measured ffprobe result (Rext). uncompressed_intra's "Main" label and the declared `hvc1.1.6` codec string are noted as wrong.

**Weak points fixed.**
- F4: the play check is the bitmap path only.
- F11: "within 200 ms of `decode()`".
- F14: scoped to 720p, 300 frames, untimed.
- F10, P5, P8: scoped to these Windows builds on this NVIDIA machine.
- F18, F24, §3.2: 0.1 ms timer resolution stated; the ImageDecoder E35/E45 gap is no longer claimed.
- F21: p95 split (leader/rVFC 86–217; free 195–244); `presented_frames_delta` evidence added; N = 4 dropped frames added.
- F22: "replaced (new pid)", with crash labelled inferred; `wc-master` 0.91–1.19 GiB added as support for the reset-pattern cause.
- F23: input cadence cited from code and `input_events`; ~58–60 shown/s identified as the harness ceiling; CPU 3.05–3.20.
- F24: the F7 corroboration was removed; rVFC fewer but presented frames equal; E45 scrub not used as stability evidence.
- New F25: rAF rate 28.0–39.3/s during `<video>` sync vs 55.7–56.1/s for master-clock paths.
- §3.1: E45 ImageDecoder scrub corrected to 58.0–58.5; footnotes for CPU scope, the `<video>` scrub seek rule, and `.mjpeg`-only ImageDecoder sync.
- P1 qualified at N = 4; P3 relabelled inferred (proxy JPEGs, harness ceiling, GPU decode excluded, scope); P2, P4, P6 labelled.
- §5: affinity is inherited, not recorded; Defender bench-item range 8.91–29.19 CPU-s, latency effect NOT VERIFIED; warm page cache stated; 15.625 ms flag is "negligible (inferred)", not "does not apply".

**Still NOT VERIFIED.**
- Frame-exact libx265 (Rext) intra playback in Electron, and HEVC 4:2:2 playback.
- Playback timing on camera JPEG bytes.
- Electron's kilobyte unit for `private_kb`.
- The Electron processes' actual CPU affinity.
- The display refresh rate.
- Defender's effect on Range latency.
- Non-NVIDIA, non-Windows and no-HEVC-hardware machines.
- Playback at target A or B.
- Causes of the N = 8 stall, the halved rAF rate and the `h264_nvenc` flush need.
