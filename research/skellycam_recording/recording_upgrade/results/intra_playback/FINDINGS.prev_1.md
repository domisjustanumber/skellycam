> **Draft, not yet verified** (returned by the workflow agent on 2026-11-09 as its summary; saved by the main session). Provenance/method verification runs after tonight's bench.

## intra_playback findings (FINDINGS text, not written to disk because of the write guard)

All 48 intra clips (H.264 and HEVC, from NVENC and QSV) play and scrub frame-exactly in Electron 35.7.5, Electron 45.2.3 and Chrome 156 on this machine, the same as the JPEG path. Clips were made with PyAV 19.0.2; full notes are in `results/intra_playback/NOTES.md`.

Sources for the claims below, all relative to `research/skellycam_recording/recording_upgrade/`:
- functional JSONs: `results/intra_playback/functional/<e35|e45|c156>/`
- generated tables: `results/intra_playback/functional_tables.md`
- clip data: `results/intra_playback/clips_summary.json`
- stream headers: `results/intra_playback/sps_vui_trace.txt`
- the per-browser totals were recomputed from the JSONs in this session.

### Clips (measured)
- **What was made:** 4 encoders (h264_nvenc, hevc_nvenc, h264_qsv, hevc_qsv) × 3 containers (mp4 +faststart, fragmented mp4, mkv) × 4 contents = 48 clips.
  - Contents: 720p30 and 1080p30, each in CFR and in VFR. The VFR timing is the real capture timing.
  - Source frames are real corpus content with the existing 16-bit frame-index pattern burned in.
- **Every clip is all-IDR with no B-frames.** Every frame has an IDR NAL unit, there are 0 non-IRAP frames, the container key flag is set on every frame, and ffprobe reports key_frame=1 / pict_type I on every frame with has_b_frames=0.
- **JPEG fixtures:** mjpeg_qsv 4:2:2 frames, stored both as a raw .mjpeg plus an index and as an MKV plus a byte-offset index. There is also an MKV of 300 unmodified camera JPEGs.
- **Quality was matched at about 55 dB Y-PSNR.** That is roughly what mjpeg_qsv gives at the cameras' own JPEG size (q85 at 720p, q90 at 1080p). Results:

| Encoder (quality setting) | 720p bytes/frame | 1080p bytes/frame |
|---|---|---|
| h264_nvenc (QP 17 / 14) | 33.8 KB | 182 KB |
| hevc_nvenc (QP 17 / 11) | 27.5 KB | 213 KB |
| h264_qsv (ICQ 11 / 8) | 41.3 KB | 224 KB |
| hevc_qsv (ICQ 20 / 17) | 31.7 KB | 185 KB |
| mjpeg_qsv | 51.1 KB | 207 KB |

All points land between 54.5 and 55.7 dB. The 1080p content is only 19 real frames looped.

### Seek, step and playback (measured; identical in E35, E45 and C156 unless stated)
- **`<video>` paused seeks:** 4800/4800 exact per browser when seeking to the midpoint between this frame's pts and the next, taken from the file. This holds for mp4, fmp4 and mkv, CFR and VFR.
- **The literal `currentTime=(k+0.5)/fps` rule only works on CFR files:** 2400/2400 on CFR, 228/2400 on VFR (misses are +1 to +3 frames). Real recordings are VFR, so the UI must use the file's own pts.
- **WebCodecs by index:** 4800/4800 per browser. Every seek decoded exactly one chunk, so any intra frame decodes alone.
- **Single steps:** 5856/5856 per browser for `<video>` (midpoint rule) and the same for WebCodecs.
- **JPEG path** (concatenated .mjpeg and JPEG-in-MKV; HTTP Range fetch, then createImageBitmap or ImageDecoder): exact everywhere. Seeks 800/800 and steps 976/976 per decode path per browser; playback 1200/1200 frames.
- **WebCodecs playback (one master clock) and JPEG playback:** 0 pattern mismatches.
- **`<video>` playback with requestVideoFrameCallback:** 0 mismatches on CFR. On VFR there were 25 (E35), 62 (E45) and 55 (C156) mismatches across about 3300–3550 frames per browser.
  - In every case the pixels read inside the callback showed frame k+1 while the callback's reported time was exactly frame k's pts.
  - This looks like a readback race (inferred). Which frame was actually on screen is not verified.

### Hardware vs software decode (measured)
- **`<video>` uses the hardware decoder (D3D11VideoDecoder, on the NVIDIA GPU) for H.264 and HEVC in all three browsers.** WebCodecs uses the same decoder when hardware is preferred or no preference is given.
- **H.264 with prefer-software** uses FFmpegVideoDecoder.
- **HEVC has no software decode at all:** prefer-software returns "config not supported" in E35, E45 and C156.
- **MediaCapabilities** reports the mp4 codec strings as supported, smooth and powerEfficient in all three browsers.

### NVENC H.264 needs a flush for WebCodecs seeks (measured)
- **h264_nvenc:** after a single decode() call, no frame came out until flush() was called (360/360 seeks per browser needed the fallback flush). The other three encoders and the software decoder never needed it (0/360).
- **Likely cause (inferred):** the h264_nvenc stream header has bitstream_restriction_flag=0, while h264_qsv writes max_num_reorder_frames=0, so the hardware decoder holds the frame back.
- **Workaround that worked every time:** call flush() right after each key chunk.

### MJPEG and JPEG-in-MKV (measured)
- **MJPEG in MKV cannot be opened by `<video>`** in any browser (DEMUXER_ERROR_NO_SUPPORTED_STREAMS).
- **Fetching JPEG frames out of an MKV by byte offset works (G1 and G9 together).** The page fetched 300 frames in order plus 150 at random, per browser.
  - Every fetch returned HTTP 206 and was byte-identical to the original camera file, starting with SOI and ending with EOI.
  - Every frame decoded with both createImageBitmap and ImageDecoder.
  - In MKV, PyAV's packet.pos is always 4 bytes before the JPEG payload, so the index must store the payload offset.

### E35 vs E45 for HEVC (measured)
- **Playback works the same in both.** HEVC Main decodes in hardware in both, and seek and step results are identical.
- **Only the API probes for MKV differ:** E35 returns an empty string from canPlayType and "unsupported" from MediaCapabilities for any MKV type. E45 and C156 return "probably" and "supported". All three play the MKV files anyway.
- **Not played:** HEVC 4:2:2 (the earlier chromium_codecs probes show E35 unsupported, E45/C156 supported).

### Harness changes (code)
All changes keep the existing suites unchanged. The four existing bench suites produce identical configurations before and after the edits.
- **`scripts/chromium_sync_scrub/harness/harness.mjs`:**
  - new `video-rvfc` sync mode;
  - new `jpegmkv` test;
  - `wcflush` option (flush after each WebCodecs key chunk);
  - per-configuration decoder names from the DevTools Media log (`medialog`);
  - mismatch examples recorded during playback;
  - mkv MIME used in the API probe.
- **`harness/main.cjs`:** opt-in `--medialog=1` and `--noocclusion=1`; defaults unchanged.
- **`harness/run_chrome.cjs`:** new, runs the same pages in Chrome 156.
- **`run_suite.py`:**
  - `--electron chrome`;
  - new suites `intra_functional`, `bench_intra_seek`, `bench_intra_sync`, `bench_intra_scrub`;
  - `--skip` and `--parts` options;
  - a PEP 723 header so it runs with `uv run --script` instead of the skellycam venv.
- **`summarize.py`:** `bench intra` writes `results/intra_playback/bench/bench_tables.md`.
- **New scripts in `scripts/intra_playback/`:** `gen_intra_clips.py`, `summarize_intra.py`, `trace_headers.sh`.

### Limits
- One machine, NVIDIA decode only; no machine without HEVC hardware was tried.
- The 0.011 ms near-duplicate VFR frame pair was not targeted explicitly.
- Each playback check covers 5 s per clip.
- The functional runs were on a shared machine with all three browsers running in parallel; CPU samples were stripped from the functional JSONs.
- Media (3.9 GB) is only under `C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/intra_playback/`.
- Nothing was committed, and no leftover study processes are running.

## BENCH COMMANDS
Run from the repo root `C:/Users/Dom/GitHub/freemocap/skellycam`, one at a time, on a quiet machine with the display on and unlocked. All of these were smoke-tested on E35 and E45 with 0 errors; extra E45 smoke passes covered the hevc_qsv, jpeg_in_mkv and hevc_nvenc configurations. Smoke timing outputs were deleted and only `_index.json` was kept. Results go to `results/intra_playback/bench/<e35|e45>/<suite>/`.

1. IP-SYNC-E35 (prio 1, ~15 min; 34 configurations; N=4 and 8, 1080p, 15 s each): `<video>` free / rVFC-steered / leader (NVENC files only), and WebCodecs master clock, for H.264 and HEVC intra (NVENC and QSV files), against the JPEG master clock (bitmap and ImageDecoder on .mjpeg, bitmap on JPEG-in-MKV).
   `uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite bench_intra_sync`
2. IP-SYNC-E45 (prio 1, ~15 min):
   `uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite bench_intra_sync`
3. IP-SEEK-E35 (prio 1, ~4 min; 12 configurations; N=1, 1080p, 200 random seeks: `<video>` midpoint rule, WebCodecs with wcflush=1, JPEG Range fetch with bitmap / ImageDecoder on .mjpeg and MKV):
   `uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite bench_intra_seek`
4. IP-SEEK-E45 (prio 1, ~4 min):
   `uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite bench_intra_seek`
5. IP-SCRUB-E35 (prio 2, ~6 min; 24 configurations; N=4 and 8, 1080p, 8 s simulated drag: `<video>` gated, WebCodecs with wcflush=1, JPEG bitmap / ImageDecoder):
   `uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 35 --suite bench_intra_scrub`
6. IP-SCRUB-E45 (prio 2, ~6 min):
   `uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/run_suite.py --electron 45 --suite bench_intra_scrub`
7. IP-SUM (prio 1, ~1 min):
   `uv run --script research/skellycam_recording/recording_upgrade/scripts/chromium_sync_scrub/summarize.py bench intra`

Totals: priority 1 is about 39 min; everything is about 51 min. To trim, add `--skip _qsv_` to the sync and scrub runs; that drops the QSV-encoded files, about 40% of their configurations.
