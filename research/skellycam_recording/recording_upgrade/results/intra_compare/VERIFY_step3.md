# intra_compare: verification of step 3 changes (GF04, GF05)

Date 2026-11-10. Adversarial check of provenance and method, limited to the new or changed claims in the step 3 FINDINGS draft. No test and no timing were run. Inspection only (Python JSON reads, grep, sed).

Paths: `RU` = `research/skellycam_recording/recording_upgrade/`, `R` = `RU/results/intra_compare/`.

## Verdict

**Pass, with two minor wording fixes.** No refuted claim. Every changed number matches its file. No timing claim from a concurrent run was added.

## Claims checked

| # | draft location | claim | check (2026-11-10) | result |
|---|---|---|---|---|
| 1 | §6, §4, §8 GF05 row 1 | E35 fails on `hevc_intra_420.mp4` with `DEMUXER_ERROR_NO_SUPPORTED_STREAMS`, error code 4 | `RU/results/uncompressed_intra/chromium_check_electron35.json` `results[16]`: name `hevc_intra_420.mp4`, `end` "error", `error.code` 4, message "DEMUXER_ERROR_NO_SUPPORTED_STREAMS: FFmpegDemuxer: no supported streams"; `electron` 35.7.5 | confirmed |
| 2 | same | E45 loads, draws and seeks it | `…electron45.json` `results[16]`: `loadeddata` true, `firstFrameSum` 2011927, `seeked` true, `framesDiffer` true, 1920×1080, `error` null; `electron` 45.2.3 | confirmed |
| 3 | §6, §8 | Sample is 8 frames, 1080p, Rext, `hvc1`, yuv420p, all I | `RU/results/chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt`: `profile=Rext`, `codec_tag_string=hvc1`, 1920×1080, yuv420p, `nb_frames=8`; `8 frame,I` | confirmed |
| 4 | §6, §8 | The ffprobed file is the file Electron tested | media mtime 2026-11-09 11:08:36; Electron JSONs written 2026-11-09 11:11; ffprobe ran 2026-11-10 on the same path | confirmed (no regeneration in between) |
| 5 | §6, §8 | Made by the ffmpeg CLI, libx265 crf 20, `keyint=1`, generator line 46 | `RU/scripts/uncompressed_intra/make_chromium_samples.py:46` (`-c:v libx265 -x265-params keyint=1:log-level=error -crf 20 -pix_fmt yuv420p -tag:v hvc1`); `subprocess.run(["ffmpeg", …])` in `main()` | confirmed |
| 6 | §8 GF05 row 1 | Same result as intra_playback F16 | `RU/results/intra_playback/FINDINGS.md:80` (F16: fails in E35, plays in E45) | confirmed |
| 7 | "Changes" list, §8 GF05 row 2 | `R/NOTES.md` lines 54 (§1), 179, 181, 185, 186, 208 (§6) carry "(corrected 2026-11-10, GF05 …)" marks | `sed -n` of each line; §1 = lines 11–60, §6 = lines 164–212 | confirmed |
| 8 | §8 GF05 row 2 | Corrected values equal `R/matched_summary.md` (83,913; 53,975 / 141,655; 94,459 / 249,785; 67,662 / 161,155) | `R/matched_summary.md` lines 36, 56, 80, 68, 89, 67, 87 | confirmed |
| 9 | "Changes" list | Lines 185, 186 were missing from the earlier list | current `R/FINDINGS.md:40-43` lists other lines; `R/gapfill/GF05_NOTES.md` table | confirmed |
| 10 | §8 GF05 row 3 | `R/BENCH.md` caveat 3 corrected in place | `R/BENCH.md:606` carries "(corrected 2026-11-10, GF05 …)" | confirmed |
| 11 | §8 GF05 row 3 | nvJPEG QC: NV12 / YUY2 52.344 / 52.365 dB, SSIM-Y 0.99707 / 0.99708 (1080p); 51.474 / 51.485 dB (720p); `mjpeg_cpu` 45.211 dB | `R/bench/matched_stream_A_1080p_20261110T042204Z.json` and `…A_720p_20261110T043459Z.json` `summary[].quality_check` | confirmed; 720p SSIM-Y 0.99655 / 0.99656 also hit A |
| 12 | §8 GF04 row | nvJPEG NV12 unpaced median 455.51 fps at N=8, 475.37 at N=16 | `…nvjpeg_420_1080p_nv12_thread_20261110T052842Z.json` `runs[]` unpaced: N=8 459.10, 454.95, 455.51; N=16 475.37, 471.93, 476.93 | confirmed |
| 13 | §8 GF04 row | hevc_qsv after mjpeg_qsv: 63.58 at N=1, 66.43 at N=16 | `…hevc_qsv_420_1080p_mjpeg_qsv_thread_20261110T083946Z.json` unpaced: N=1 63.50, 63.65 (median 63.575); N=16 66.32, 66.53 (median 66.425) | confirmed (2-rep medians, rounded half up) |
| 14 | §8 GF04 row | hw_accel_target §3.3.1 unpaced column is at the largest N that keeps up | `RU/results/hw_accel_target/gapfill/GF04_doc_fixes.md:53` ("Unpaced = … same N"); rows at lines 66, 70 | confirmed |
| 15 | §4 | E35 is "the skellycam-ui pin" | `skellycam-ui/package.json:52` `"electron": "^35.0.3"`; installed `node_modules/electron/package.json` version 35.7.5 | weak: a caret range, not an exact pin |
| 16 | §4, §6 | Rext 4:2:0 sample fails in E35 | the result is measured; the cause (Rext profile vs something else in this file) is not isolated. The `<video>` mime declares `hvc1.1.6` (Main-style string) for a Rext stream (noted in intra_playback FINDINGS line 321) | weak: keep cause unstated or label it inferred |

## Method checks

- Timing: the step 3 changes add no fps, CPU or latency claims. The GF04 fps values come from the quiet run files (`20261109T230007`), not from step 3. Pass.
- Over-generalisation: §4 and §6 say "one ffmpeg-CLI sample" and keep PyAV-made streams and frame-exact seek as NOT VERIFIED. Pass.
- Labels: the result is labelled measured with files; the generator is code with file:line; the ffprobe is a CLI inspection. Pass.
- The sample is a single 8-frame clip of C930e frames converted to NV12, at crf 20, not a target A or B setting. The draft does not claim otherwise.

## Fixes

1. §4: replace "E35 (the skellycam-ui pin)" with "E35 (35.7.5, as installed in skellycam-ui; `package.json:52` `^35.0.3`)".
2. §4 "Avoid libx265 output for the UI": if the bullet is read as "Rext causes the E35 failure", add "inferred:" to that link, or say only "the one libx265 sample tested fails in E35".
3. Nit: 66.43 is the half-up rounding of the 2-rep median 66.425; fine as is.
