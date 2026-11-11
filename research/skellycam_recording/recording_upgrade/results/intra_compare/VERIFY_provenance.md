# intra_compare: provenance verification of the 2026-11-10 draft FINDINGS

Verifier: provenance lens (adversarial). Date: 2026-11-10. No timed measurements were run. The only network access was a re-fetch of the cited FFmpeg n9.0.2 source files (raw.githubusercontent.com) and the NVIDIA support matrix.

`R` = `research/skellycam_recording/recording_upgrade/results/intra_compare/`, `B` = `R/bench/`, `S` = `research/skellycam_recording/recording_upgrade/scripts/intra_compare/`.

## 1. What was checked

| area | how | result |
|---|---|---|
| Single-stream numbers, §2.4, §2.7, §3.3, §3.4 (items 1–3) | Every `summary[]` row of the 3 `matched_stream_*` JSONs dumped (fps median/min/max, cpu_ms, cores, bytes, `quality_check`) and compared cell by cell | all fps, CPU and QC numbers match; one bytes claim is wrong (R1) |
| GPU engine figures, §2.4 | `runs[].gpu` of S-A1080 | NVENC VideoEncode about 97% and nvidia-smi encoder 100% match; h264_qsv VideoDecode 87 / 3D 44 match; hevc_qsv 3D 89–91 are the nv12/yuy2 medians (per-rep range 81.0–91.3) |
| Scaling numbers, §2.5, §2.6, §3.5 (24 files) | Every `runs[]` cell dumped (opened, aggregate fps, keeps-up, late, dropped, cores, p99, wall) plus `limit_probe` | all cited medians and min–max match; omissions in W4 |
| Sweep tables, §2.2, §2.3, §3.1, §3.2 | Compared with `R/matched_summary.md`; ratios recomputed | all table cells match; R2 and R4 are wrong side claims |
| Sweep size and verification, §2.1 | `R/raw/*.json` recounted (994 points, 73,556 frames); `R/verification.md`; `R/matched_settings.json` `pix_fmt_fed` | match |
| Targets, §2.2 | `R/camera_jpeg_quality.md`, `R/curves.md` (q50, q90, q94, q95 rows) | match |
| Pitfalls, §2.8 | `R/knob_check.json`, `R/dht_check.json`, `R/nvjpeg_rgb_diag.json`; FFmpeg n9.0.2 files re-fetched | match (see §3) |
| Code citations | `S/bench_matched_stream.py`, `S/benchpaths.py`, `S/bench_matched_concurrent.py`, `S/iclib.py` opened at the cited lines | match, except W5 and W6 |
| Run record, §5 | `results/BENCH_RUN_2300_LOG.jsonl` (27 intra_compare items), `results/BENCH_RUN_2300_SUMMARY.md` §2–§4, `R/BENCH.md` caveats 5 and 8 | match |
| Cross-topic citations | `results/gpu_encode/FINDINGS.md` §2.4, `results/gpu_encode/nvimgcodec_jpeg.md`, `results/chromium_codecs/FINDINGS.md` C17/C17a, `results/licensing/FINDINGS.md` §2.5, `results/hw_accel_target/FINDINGS.md` | they exist and mostly say what is claimed; W1 and W2 |

## 2. Refuted claims

**R1. §2.4: "bench bytes/frame at the chosen settings are within 0.1% of the sweep for JPEG".**
- measured, S-A1080 (`bytes_per_frame_median` against `quality_check.matched_bytes_per_frame`), JPEG rows:
  - nvjpeg_420 nv12 −0.46%; nvjpeg_420 yuy2 −0.32%; ff_mjpeg_420 yuy2 −0.32%; mjpeg_qsv_420 yuy2 −0.19%;
  - ff_mjpeg_420 mjpeg_cpu −1.21%; nvjpeg_420 mjpeg_cpu −1.51%; nvjpeg_422 mjpeg_cpu −1.84%; nvjpeg_420 mjpeg_qsv −2.69%.
- Only the CPU/QSV JPEG rows from NV12 or native YUY2, plus the exact-RGB nvJPEG rows, are within 0.1%.
- The companion claim "1.8–3.5% smaller for H.264/HEVC fed decoded MJPEG" holds only for the NVENC/QSV 4:2:0 `mjpeg_cpu` rows (1.78–3.53%):
  - hevc_qsv_422 mjpeg_cpu is −0.47%, libx264 ultrafast mjpeg_cpu is −1.10%, and the `mjpeg_qsv` source rows are −1.36 to −1.97%.
  - The 4:2:0 H.264/HEVC rows fed YUY2 through swscale are also 1.42–1.63% smaller. This supports the swscale inference but is not mentioned.
- Correction: "JPEG rows from NV12, native YUY2 or exact RGB are within 0.06% of the sweep, except nvJPEG through swscale (−0.3 to −0.5%). Every row whose input passes through swscale or a decoder is smaller: JPEG by up to 2.7% (nvJPEG after mjpeg_qsv), and NVENC/QSV H.264/HEVC by 1.4–1.6% from YUY2 and 1.8–3.5% from `mjpeg_cpu`."

**R2. §2.3: "4:2:2 against 4:2:0 at the same knob … PSNR-Y is identical in every pair".**
- measured, `R/matched_summary.md`: true for every pair at target A.
- At target B, hevc_qsv_422 against hevc_qsv_420 differs: yuy2_1080p 45.07 vs 45.08, yuy2_720p 45.22 vs 45.23, mjpeg_720p 45.04 vs 45.05, mjpeg_1080p 44.78 vs 44.80.
- The byte ranges given (1.07–1.17, 1.13–1.33) are at target A. Recomputed, the target B ratios fall inside them.
- Correction: "PSNR-Y is identical in every pair at target A; at target B hevc_qsv_422 differs by 0.01–0.02 dB."

**R3. §2.1: "The same versions are in every bench JSON's `system_before`".**
- measured: all 27 bench JSONs record `nvimgcodec` "0.10.0" (not 0.10.0.9) and no libjpeg-turbo version.
- The full versions (nvidia-nvimgcodec-cu12 0.10.0.9; libjpeg-turbo 3.1.2) come from the sweep's `R/raw/*.json` `runs[].versions`.
- Correction: "Bench JSONs record PyAV 19.0.2, libavcodec 63.1.102, simplejpeg 1.9.0, nvimgcodec 0.10.0 and Python 3.12.13. The libjpeg-turbo build and the nvimgcodec wheel version are from `R/raw/*.json`."

**R4. §2.2: "H.264/HEVC: 53.12–53.33 dB" at A on yuy2_1080p.**
- measured: libx264_ultrafast_420 is 53.36 dB (`R/matched_summary.md`). The range over all H.264/HEVC paths is 53.12–53.36.
- Correction: give 53.12–53.36, or name the excluded path.

## 3. Verified (selected)

- measured: every single-stream fps/CPU cell in §2.4, §3.3 and §3.4 matches the JSON `summary[]` to the rounding shown.
  - One exception: §3.3 labels libx265 "23–27 cores", but at A 1080p its per-rep range is 26.0–27.3. The 23.25 is from S-B1080 (W8).
- measured: QC values in §2.7 (0.9954 / 45.21; 45.51 vs 49.30; 43.14; 52.34–52.37; 51.36; 56.46; hevc_qsv_422 0.99608 / 0.9960 with −2.13 / −2.66 dB) and the five B rows under 45 dB (44.61–44.85, sweep also under 45) all match.
- measured: every scaling median and min–max in §2.5 and §3.5 matches `runs[]`.
  - The "512–542" (h264_nvenc) and "389–391" (hevc_nvenc) unpaced ranges are ranges of per-N medians. Individual reps reach 507.5 and 380.0–392.2 (W4).
- measured: limit probes. h264_nvenc and hevc_nvenc opened 12/32, the first error text matches, and nvidia-smi showed 12 at the peak. h264_qsv, mjpeg_qsv_420 and mjpeg_qsv_422 opened 32/32. hevc_qsv, simplejpeg and nvJPEG have `args.limit_probe` 0, so no probe ran.
- measured: flag 1. Affinity is 0–15 before and 0–27 after in all three stream files. libx265 cores were 23.25–27.31. Non-x265 maxima after the first x265 cell were 9.966 / 6.613 / 3.902. All 24 scaling files keep 0–15.
- measured: flag 6. The negative process CPU readings (−2.224, −2.44 in item 10; −1.149 in item 55) are confirmed.
- measured: flag 11. No intra_compare item has `load_over_15pct`. The highest pre-item max was 14.73% (item 32; item 2 had 14.49%). `msmpeng_cpu_s_during_item` is 1.55–50.89. `defender_scan_events_during_item` is empty in every intra_compare item.
- measured: item numbers 1–11, 31–34, 41–45 and 49–55 map to the cited files (queue order in the log's `start` event).
- code: FFmpeg n9.0.2 `libavcodec/options_table.h:151` (`i_qfactor` default −0.8), `nvenc.c:835-836`, `qsvenc.c:762`, `qsvenc.c:922-929` and `mjpegenc.c:650` were re-fetched 2026-11-10 from https://raw.githubusercontent.com/FFmpeg/FFmpeg/n9.0.2/. They match the excerpts file line for line.
- measured: `R/knob_check.json`. Stats QP 19 (NVENC reports frameAvgQP−1, so 20) and 20 for h264_qsv; 22 for libx264/libx265. Packet sizes are 50,990→33,081; 36,511→22,404; 56,202→37,634; 37,257→22,783. `flags=+qscale` with `global_quality` 236 or 1416 gives identical 125,998 B for FFmpeg mjpeg; `qmin=qmax=12` gives 67,031.
- source: re-fetched 2026-11-10, https://developer.nvidia.com/video-encode-and-decode-gpu-support-matrix-new. The column header is "Max # of concurrent sessions", and the GeForce RTX 3070 row shows 12 (all RTX 30 rows show 12).
- measured: `R/NOTES.md` stale cells exist. §6 lines 181 and 208 say 55,112 / 144,376 where `R/matched_summary.md` has 53,975 / 141,655. §1 says "1.41-1.52x passthrough" where the summary has 1.42 / 1.53.

## 4. Weak claims (fix wording or evidence)

| # | claim | why weak | fix |
|---|---|---|---|
| W1 | §2.6 "source (cited, not re-checked here): NVIDIA's support matrix lists … 12" | A second-hand citation with no URL, quote or access date, which breaks the evidence rule | Add the URL, the exact header "Max # of concurrent sessions", RTX 3070 = 12, accessed 2026-11-10 (re-fetched here) |
| W2 | §4 "libx264/libx265 are also GPL in the wheel (`licensing/FINDINGS.md` §2.5)" | licensing §2.5 says the wheel's FFmpeg reports "LGPL version 3 or later" with `has_enable_gpl: false`; pyav-ffmpeg patches x264/x265 into the version3 list; x264/x265 themselves are GPL v2+ (source), and the GPL DLLs cannot be removed | Say: "the wheel bundles libx264/libx265, which are GPL-licensed and cannot be stripped; the FFmpeg build reports LGPLv3 (licensing §2.5)" |
| W3 | §4 storage line compares h264_nvenc and hevc_qsv **YUY2** bytes with camera **passthrough** (MJPEG) bytes in one list | Mixed input classes, unlabelled. For an MJPEG camera, h264_nvenc at A is 123,426 B/frame (3.7 MB/s), not 157,840 | Label each value's input class, or add the MJPEG-class values |
| W4 | §2.5 nvJPEG 1080p NV12 "8 keep up"; §2.5 unpaced ranges "512–542", "389–391" | At N=8 the reps had 0, 73 and 66 late frames (N=4: 3, 0, 4), not stated. The unpaced ranges are of per-N medians, and individual reps reach 507.5 and 380.0. Paced N=1 also shows late frames for mjpeg_qsv_420 (13, 13, 26) and mjpeg_qsv→h264_qsv (5, 5) | State the late counts; say "medians per N" |
| W5 | §5 flag 10, set sizes "YUY2 16 frames, MJPEG 1080p 38, 720p 240" cited to `S/benchpaths.py:190, 206, 218` | Those lines show the modulo cycling only. The sizes are in `S/iclib.py:44-48` (`INPUTS`) | Add `S/iclib.py:44-48` |
| W6 | §2.6 "code: the probe skips simplejpeg and nvJPEG (`:268`)" | True, but no probe was requested for those files (`args.limit_probe` = 0), nor for any hevc_qsv file | Say "not probed (`limit_probe` 0)" |
| W7 | §2.4 "decoding camera MJPEG on the CPU first limits one stream to 152–243 fps for most paths … (libx264/x265 excepted)" | nvJPEG (140–145 fps) and hevc_qsv / hevc_qsv_422 (66–68 fps) are also outside the range and not named | Name all the exceptions |
| W8 | §3.3 libx265 row "(23–27 cores)" | At A 1080p the range is 26.0–27.3 cores. 23.25 is the B 1080p mjpeg_cpu row | Use 26–27 here, and 23–27 in flag 1 only |
| W9 | §2.3 "libx265 at 1080p (0.99x) and nvJPEG 4:2:2 at 720p (0.98x) are just under" | nvjpeg_420 mjpeg_1080p is also 0.99x passthrough (`R/matched_summary.md`) | Add it |
| W10 | §5 flag 12, inferred timer error "under about 0.5% for reps of 3 s" | The bound is relative to wall time, but the error is relative to CPU seconds. Low-CPU cells are worse: hevc_qsv reps have 0.73–1.53 CPU-s, so 1–2% per 15.625 ms step; paced N=1 cells have about 1.7 CPU-s. Granularity is directly measurable here: `cpu_s` values are multiples of 0.015625 (for example 2.21875, 1.6875) | Label it measured from these files, and state the bound against CPU seconds |
| W11 | §4 G7 factor "2.9–3.4x" at B | 1/0.29 = 3.45, so 2.9–3.4 rounds the top end down | Write 2.9–3.4 as "about 2.9–3.5" |
| W12 | §2.8 "every JPEG encoder and the cameras use the standard Annex K Huffman tables" | `R/dht_check.json` checks one sample per encoder per class. mjpeg_qsv_420/422 and nvjpeg_420 have no mjpeg_1080p sample | Say "every sampled file (29 encoder samples, 4 camera sets)" |
| W13 | Changes list: "`R/NOTES.md` §1 and §6 hold a few stale cells" | Confirmed, but the cells could be named | Cite §6 lines 181, 208 and the §1 "1.41-1.52x" line |

## 5. Labels, targets and rules

- Every quality-dependent number carries target A or B, except R2. The §2.5 scaling block is labelled "all at target A". The intra_playback clips are kept separate (54.5–55.0 dB, `BENCH_RUN_2300_SUMMARY.md` §4 line 82).
- No PyAV 18 results and no contaminated daytime numbers are presented as current.
- The inferred claims are marked: hevc_nvenc 13-stream cap, GIL scaling, swscale cause, x265 affinity, storage arithmetic.
- An unexplained conflict is noted correctly as NOT VERIFIED:
  - `R/nvjpeg_rgb_diag.json` shows swscale-RGB loss on yuy2_1080p (46.7 dB for the RGB step);
  - but the timed bench's swscale-RGB QC from NV12/YUY2 hits A (52.34–52.37 dB).
  - `R/BENCH.md` caveat 3 ("its QC carries the swscale RGB bias") does not match the bench QC for those feeds. That is a BENCH.md issue, not a FINDINGS one.

## 6. Verdict

Mostly sound, but needs edits before saving:
- Four claims are refuted, all minor in effect: R1 bytes-match claim, R2 PSNR-identical-at-B, R3 versions in JSON, R4 PSNR range.
- 13 weak claims need wording or citation fixes. W1 (second-hand source with no URL or quote) and W3 (storage list that mixes input classes) matter most.
- The headline numbers are confirmed against the JSON: sizes at A/B, single-stream fps/CPU, scaling limits, the 12-session NVENC limit, the nvJPEG QC miss and the i_qfactor pitfall.
