# intra_playback: method verification of the 2026-11-10 draft FINDINGS

Verifier: adversarial, methodology lens. Date 2026-11-10. Draft checked: the updated intra_playback FINDINGS text (not on disk), against run `20261109T230007`.
Paths are relative to `research/skellycam_recording/recording_upgrade/` (RU). `R` = `results/intra_playback/`, `B` = `R/bench/<e35|e45>/`.

No timed measurement was run. Checks made:
- every bench number in the draft re-read from `B/**.json` with a script (scratchpad `step2/ip_method/dump.py`);
- functional totals re-summed from `R/functional/<e35|e45|c156>/*.json` (`func.py`, `func2.py`);
- one ffprobe 9.0.2 inspection of an existing file (allowed: the CLI may inspect files).

## Verdict

**Sound with corrections.** Every number checked matches the JSON. The functional conclusions (F1–F15) stand. The quality note is handled correctly: the clips are at about 55 dB, kept apart from targets A and B. Single-run, P-core and flag caveats are present.

Corrections needed:
- 2 refuted statements: the 60 Hz vsync arithmetic, and "profile not probed" for the libx265 sample, which is now measured as Rext.
- Several method weaknesses:
  - the scrub "58 shown/s" is the harness's input-rate ceiling, not a capacity figure;
  - rAF ran at about half rate in every `<video>` sync config;
  - presented frames are equal in E35 and E45 even though E45 gets fewer rVFC callbacks;
  - timer quantisation is 0.1 ms;
  - the JPEG timing used a proxy for the camera JPEGs, not the camera bytes;
  - the CPU comparison leaves out GPU decode;
  - warm page cache and Defender attribution are not stated.

## Refuted

| # | Draft claim | Evidence | Correction |
|---|---|---|---|
| X1 | F18 / BENCH.md: "about 14 ms is one 60 Hz vsync" | arithmetic: one 60 Hz period is 16.7 ms. measured: in the master-clock sync configs, rAF ticked 55.7–56.1 /s (`result.ticks / result.dur_s`, `B/bench_intra_sync/*__{wc-master,jpeg-master-*}__n*.json`); the display rate was not recorded | Remove the claim, or write: "p50 11.8–14.1 ms, less than one 60 Hz period (16.7 ms). Cause not determined. Display rate not recorded; rAF ran at about 56/s in master-clock configs (measured)." |
| X2 | F16 / §6: "This sample's profile was not probed", and the "Main" vs Rext records "conflict" | measured (ffprobe 9.0.2, inspect only, 2026-11-10) on `C:/Users/Dom/Documents/skellycam-raw/.../uncompressed_intra/chromium_samples/hevc_intra_420.mp4`: `codec_name=hevc, profile=Rext, codec_tag=hvc1, 1920x1080, yuv420p, nb_frames=8`; the first 5 frames are all `pict_type=I`. code: the generator declares the codec string `hvc1.1.6.L120.90` (Main) for this file (`scripts/uncompressed_intra/make_chromium_samples.py:46`), which does not match the stream | F16: "measured (ffprobe inspection): the CLI sample is HEVC **Rext**, 8 frames, all-intra. So libx265 all-intra is Rext from both the CLI and PyAV. uncompressed_intra VERIFY_method R1's 'Main' (from code) is wrong, and the declared codec string `hvc1.1.6` mislabels the stream." Keep §6 NOT VERIFIED for frame-exact seek (no seek test, 8-frame sample). Optional, inferred: the NVENC/QSV HEVC clips are Main (`general_profile_idc = 1`, `R/sps_vui_trace.txt`) and play in E35, while the Rext sample fails there. |

## Weak

| # | Claim | Problem (evidence) | Fix |
|---|---|---|---|
| W1 | F23 table, P3: JPEG `ImageDecoder` scrubs at "58.0–58.6 shown/s"; at N=4 the bitmap path matches it | measured: the harness's input loop is `sleep(16)` (code `scripts/chromium_sync_scrub/harness/harness.mjs:507`, `:485`). `input_events` was 465–479 per 8 s in unloaded configs, i.e. ≤ about 60 per s. `ImageDecoder` shown × 8 s = 464–470, the same as its `input_events`. So these paths **hit the harness ceiling**; their capacity is not measured. Bitmap N=8 also lowered the input rate itself (`input_events` 365–407), so its shortfall mixes decode cost with main-thread starvation | State that about 58–60 shown/s is the input-rate ceiling: `ImageDecoder` (N = 4, 8) and bitmap (N = 4) saturate it, and capacity above that is not measured. In P3, write "reached the harness ceiling" in place of "scrubbed at 58 /s". |
| W2 | §5 / F19 / F21: spread compared across paths ("100% of ticks" vs "21–90% of ticks") | measured: rAF ticks/s was **28.0–39.3 in every `<video>` sync config** (N = 4 and 8, both Electrons) vs **55.7–56.1 in every master-clock config** (`result.ticks / dur_s`). Spread was sampled at about half the rate for `<video>`, and the page's own rendering cadence halved while `<video>` elements played | Add a measured bullet: "During `<video>` sync, rAF ran at 28–39 /s against 56 /s for master-clock paths. Cause not determined." Note that tick-percentage comparisons use different sampling rates. In P1, this also counts against `<video>` (inferred: overlays drawn on rAF would update at about 28 Hz). |
| W3 | F24, table 3.2: "E45 delivers fewer rVFC callbacks per stream at N = 4 … matches the functional VFR rVFC counts (F7)" | measured: `presented_frames_delta`/15 s is 27.3–28.1 /s per stream in **both** E35 and E45 at N = 4, and `droppedVideoFrames` is 5.9–8.4% in both (`result.per_stream`, `result.dropped`). The difference is in rVFC delivery, not in frames presented. The F7 corroboration uses the functional runs, which the draft says carry no timing claims (three browsers in parallel) | Write: "E45 fires fewer rVFC callbacks (median 19.7–24.1 vs 23.4–26.0 /s), but frames presented per stream are equal (27.3–28.1 /s in both)." Drop the F7 corroboration. |
| W4 | P1: "`<video>` sync holds at N = 4" | measured: at N = 4 every tile drops 5.9–8.4% of frames (`getVideoPlaybackQuality`) and presents 27.3–28.1 of 30 fps; spread max is 2–4 frames | Qualify: "spread holds (max 2–4 frames), but each tile presents about 28 of 30 fps and reports 6–8% dropped". |
| W5 | F18, F24, table 3.2: E35 vs E45 seek differences (e.g. `ImageDecoder` "slightly slower", 4.6 vs 4.4 ms); "JPEG-in-MKV within 0.1 ms" | measured: every `lat_ms` in `B/bench_intra_seek/*.json` `result.rows` is a multiple of 0.1 ms (`performance.now()` quantisation). 4.4 vs 4.6 is 2 ticks, from a single run per config | Add "page timer resolution is 0.1 ms". Do not claim differences ≤ 0.2 ms, such as `ImageDecoder` E35 vs E45. "Within 0.1 ms" means "within one timer tick". |
| W6 | P3: "the JPEG passthrough path (G1, G7) meets G9 on this machine" | measured: the timed JPEG clips are `mjpeg_qsv` 4:2:2 q90 re-encodes (206,938 B/frame), not camera bytes (`R/NOTES.md` §2, `R/clips_summary.json`). The camera-bytes MKV test (F14) is functional only. measured: the mean C922 1080p camera JPEG is 192,382 B (`results/intra_compare/camera_jpeg_quality.md` row `c922_1080p`), so the proxy is about 8% larger | Say the timing was measured on a 1080p JPEG proxy of similar size (inferred: a fair proxy). Camera-bytes timing is NOT VERIFIED. Limit to N ≤ 8, 1080p30, one machine. |
| W7 | P3 / F20: "Its cost is CPU: 1.44 cores … vs 0.51–0.57 for WebCodecs" | code: CPU is the sum of Electron process CPU (`harness/main.cjs:93-101`). WebCodecs decode runs on NVDEC (F9), which this figure does not count. nvidia-smi has only before/after point samples | State that the WebCodecs figure leaves out GPU decode work. inferred: on a machine without hardware decode, the H.264 comparison changes (software FFmpeg decode) and HEVC has no path at all (F10). |
| W8 | F21: N=8 spread "p95 was 86–217 frames" | measured: 86–217 is right for the leader/rVFC-steered configs only. Across all 20 N = 8 `<video>` configs, p95 is 86–244 (h264_qsv `video-free` 244 in both Electrons) | Write "p95 86–217 with correction/steering; 86–244 across all N = 8 `<video>` configs". |
| W9 | F21 evidence | Draft cites only rVFC callbacks. measured: `presented_frames_delta` agrees, e.g. E35 h264_nvenc `video-free` N = 8: slowest 16.0 vs median 27.9 presented /s. So the stall is real presentation, not just missed callbacks | Add the `presented_frames_delta` evidence. The "not a codec effect" inference is fine. Also note that wc-master at N = 8 uses the same D3D11 decoder without stalling, so a decoder-capacity cause is unlikely (inferred). |
| W10 | F22 inference: "the per-target reset/configure/flush cycle triggers it" | Supporting evidence the draft does not use. measured: wc-master N = 8 (sequential decode, no reset; code `harness.mjs:330-335`) peaked at 0.91–1.19 GiB GPU private in all 8 configs (`metrics_samples[type=GPU]`) | Add it. It narrows the cause to the scrub/seek reset pattern (still inferred). |
| W11 | §5 "Localhost HTTP … disk or network sources will differ" | code: the server opens the file per Range request (`harness/server.cjs:57`, `createReadStream`). The same 1080p files were re-read across configs, so reads came from a **warm OS page cache** (inferred). The server runs in the Electron main process, so its CPU is in the totals (`main.cjs:12`) | Say "warm page cache; cold-disk latency not measured". |
| W12 | §5 Defender: "MsMpEng used 0.19–29.19 CPU-s per item" | measured: 0.19–0.55 are the `IP-SUM*` summariser items. The 7 bench items used 8.91–29.19 CPU-s, e.g. IP-SEEK-E35 9.55 CPU-s in a 33 s item, about 0.29 cores (`results/BENCH_RUN_2300_LOG.jsonl` lines 13–16, 26–27, 48–49). This is not in the Electron CPU figures. Whether file-open scanning affected Range latency is not determined | Give the bench-item range (8.9–29.2 CPU-s). State that MsMpEng is outside the Electron CPU figure and that its effect on latency is NOT VERIFIED. |
| W13 | Table 3.1, row "JPEG Range + `ImageDecoder` (`.mjpeg` or JPEG-in-MKV)": N = 8 sync 1.44 cores, spread 0 | code: sync ran `ImageDecoder` on `jpeg_seq` only; there is no JPEG-in-MKV `ImageDecoder` sync config (`scripts/chromium_sync_scrub/run_suite.py:260-261`) | Footnote: "sync figures from `.mjpeg` only". |
| W14 | Table 3.1 `<video>` rows "`mid` from pts" carry the scrub numbers | code: `<video>` scrub sets `currentTime = frame / fps` (the UI rule; `harness.mjs:482`), not `mid`. On these CFR clips this is harmless | Footnote: "scrub uses `frame / fps` (CFR clip)". |
| W15 | F10 / P5: "HEVC has no software decode in Chromium" | measured on three Windows builds only. Other platforms' Chromium decoders were not tested (draft §6) | Scope it: "in E35, E45 and C156 on Windows". macOS/Linux is NOT VERIFIED. |
| W16 | P8: "moving the UI from E35 to E45 is not needed for NVENC/QSV H.264 or HEVC Main intra" | Functional pass on one machine with NVIDIA D3D11 hardware decode. E35 and E45 behaviour on machines without HEVC decode hardware, or on Intel/AMD decode, was not tested | Add "on this machine (NVIDIA D3D11 decode)". The E45 "no scrub errors" point comes from a single 8 s run and grew the same 30+ GiB, so do not weigh it as stability evidence. |
| W17 | §5 "P-cores only" | code: affinity is inherited from the runner (`scripts/bench_runner/run_queue.py:21-22, 441-443`). The Electron and GPU processes' affinity is not recorded in the bench JSON | Write "inherited (code); not recorded per Electron process". |
| W18 | F23: "CPU at N = 8 about 3.1–3.2 cores for `ImageDecoder`" | measured: 3.05–3.20 (`metrics_summary.cpu_cores_total_from_cumulative`) | Write 3.05–3.20. |

## Confirmed (spot list)

- F1–F5: 4800/4800 `mid` and `wcflush` seeks per browser; 5856 steps; JPEG 800/976; `cfrmid` VFR 228/2400. Harness rules at `harness.mjs:71` and `:74`. F6: UI rule at `skellycam-ui/src/components/playback/SyncedVideoPlayer.tsx:334`.
- F7: 25/62/55 VFR mismatches. F10: H.264 software 360/360. F11: 360 fallback flushes for h264_nvenc only.
- F17: 200/200 exact in all 24 seek configs.
- F18: all p50s and maxima. 7 of 8 maxima are at row 0; the exception is E45 h264_qsv, at row 32.
- F19: 28 master configs with spread 0/0/0.
- F20: all CPU and working-set figures.
- F21: slowest/median 0.42–0.60 in 19 of 20 configs and 0.78 in one; max spread 100–245; N = 4 max 2–4 and 21.0–90.3% of ticks at spread 0.
- F22: 914 errors (300 + 4 + 80 + 523 + 7); GPU peak 9.14–37.86 GiB; 3 configs with 2 pids; non-WebCodecs ≤ 0.86 GiB.
- F23: table values match.
- Load: 11 items; no load flag; mean ≤ 4.11%, max 10.25%.
- Flags not applicable (libx265 affinity, NVENC 12-session limit, nvJPEG, write latency) are correctly scoped out.
- Quality note: clips are 54.49–55.01 dB at 1080p, NOT target A or B, with box-SSIM. Correctly kept apart from A and B.
