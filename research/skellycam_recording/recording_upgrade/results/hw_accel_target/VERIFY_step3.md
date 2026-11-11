# hw_accel_target: step 3 verification (provenance + method), 2026-11-10

Scope: only the claims that are new or changed in the step 3 draft, from gap-fills GF03 and GF04. GF06 and GF07 were only spot-checked (excerpts exist and match A8 / P5 / I5); they are not re-verified here. No timed test was run. Every number was re-read from the cited files.

Paths: `R` = `research/skellycam_recording/recording_upgrade/results/`, `S` = `.../scripts/`, `IB` = `R/intra_compare/bench/`.

Re-check script (parse only, no device opened): `C:/Users/Dom/AppData/Local/Temp/claude/ca7e9b09df19a3f5/a7ea874e-b7d7-409b-8fa2-7bc75f5d271b/scratchpad/step3/verify_hw/cap.py`. It recomputes every §3.3.1 cell directly from the 24 `IB/matched_concurrent_*.json` files, without going through `GF04_capacity.json`.

## 1. Refuted

| # | draft claim | checked against | correction |
|---|---|---|---|
| X1 | §3.3 JPEG capacity cell, §3.3.1 table row and bullet heading, §4.4: "nvJPEG fed decoded camera MJPEG **misses A**" | `IB/matched_stream_A_1080p_20261110T042204Z.json` `summary[]`. Source `mjpeg_cpu`: nvjpeg_420 and nvjpeg_422 give `ssim_y` 0.9954, `psnr_y` 45.211 (miss). Source `mjpeg_qsv`: nvjpeg_420 gives `ssim_y` 0.99788, `psnr_y` 56.462 against matched 49.995 (**hit**). `R/intra_compare/FINDINGS.md:276-283` limits the miss to "`mjpeg_cpu` → swscale `rgb24`" and records the 56.46 dB result after mjpeg_qsv decode | Narrow it to "nvJPEG fed **CPU-decoded** camera MJPEG through swscale `rgb24` misses A (SSIM-Y 0.9954, PSNR-Y 45.21 dB). After `mjpeg_qsv` decode it hits A (SSIM-Y 0.99788, PSNR-Y 56.46 dB). The QC uses the first 4 C930e frames only (intra_compare §5 flag 5)." |

## 2. Weak

| # | claim | problem | fix |
|---|---|---|---|
| W1 | §3.3.1, §3.3 HEVC cell, §4.5, inferred bullet: "hevc_qsv … 1 stream", "carries 1"; nvJPEG NV12 "8" | "Streams kept up" is the largest **tested** N (tested N = 1, 4, 8, 16), not a measured maximum. hevc_qsv N=2–3 and nvJPEG N=9–15 were not run. hevc_qsv's unpaced aggregate is 66.40 fps (about 2.2 × 30). nvJPEG reaches 98.2% of the needed rate at N=16 (intra_compare §3.5) | Write "1 of the tested N (1/4/8/16); N=4 fails; N=2–3 not tested". Same form for nvJPEG: "8 of the tested N; N=9–15 not tested" |
| W2 | N13 "The pinned nvJPEG wheels"; §4.2 "SASS in the pinned wheels" | The study pins only `nvidia-nvimgcodec-cu12[nvjpeg]==0.10.0.9`. The nvjpeg extra is unpinned and only resolved to 12.4.0.76 (GF03 §1, G04; `R/gpu_encode/NOTES.md:148`) | Write "the wheels used (nvimgcodec 0.10.0.9 pinned; nvjpeg 12.4.0.76 as resolved, unpinned)" |
| W3 | R5 "(… GF03 W03-W07, C02-C06, C13)" cited for the redistribution restrictions | C04 is a **permission** ("develop and test applications released under OSI approved … licenses"). C05 is the conflict rule for component licences. Neither supports a restriction | Cite C02, C03, C06, C11 and C13 for the restrictions. C04 is already cited separately in the sub-bullet |
| W4 | N13 "[source] GeForce RTX 20/30/40/50 = CC 7.5/8.6/8.9/12.0 (GF03 K01-K04)" | K01-K04 quote one SKU per generation (5090, 4090, 3070, 2080). The saved page text does list the other desktop RTX SKUs under the same headings (scratchpad `step3/GF03/work/txt/cuda_gpus.txt` lines 26-32, 57-63, 78-87, 106-109), but GF03 did not cite them. Laptop SKUs were not checked | Cite the page lines, or write "representative desktop SKUs" |
| W5 | N9: the R19 and R20 quotes are attributed to the "nvImageCodec 0.10 release notes" | That page is labelled "v0.10.0-beta.11". Whether it applies to wheel 0.10.0.9 is NOT VERIFIED (GF03 R17, R18) | Add "(notes labelled beta; applicability to 0.10.0.9 NOT VERIFIED, GF03 R17-R18)" |
| W6 | §3.3.1 bullet: "Paced = 450 frames per stream; unpaced = 300; one thread or process per stream (`bench_matched_concurrent.py:14-16, 127-131`)" | Lines 14-16 and 127-131 define keeps-up only. The frame counts are at `:245-246` (`--paced-frames` default 450, `--unpaced-frames` default 300). Workers are at `:10-12` | Cite `:10-16, 127-131, 245-246` |
| W7 | §3.3.1 "capacity at target A" | The scaling items have no quality check (intra_compare §5 flag 5). "At A" means the encoder setting chosen for A, not a quality checked in those runs | Add a scope bullet: "settings for A; no QC in the scaling items" |
| W8 | R6 sha256 and quotes | Both licence copies exist only in the temp scratchpad (`step3/GF04_src/`), not under `R/`. Re-checked: sha256 `ba6bceeb…4433579` and `dcb18a8a…7fe6d4` match, and both quotes are present | Copy the two files (or excerpts with sha256) into `R/hw_accel_target/gapfill/` so the citation outlives the scratchpad |

## 3. Confirmed (checked, no change needed)

GF04 / §3.3.1 / §5 / §6 / header:
- measured: every §3.3.1 cell matches the raw JSONs: streams, opened, cores median (min–max), reps, late frames, unpaced aggregate fps (median over reps), the 720p column, and the limit probes (NVENC 12/32; h264_qsv, mjpeg_qsv 4:2:0 and 4:2:2 32/32).
- measured: every N=16 NVENC cell, at 1080p, at 720p and in the pipelines, has `opened` = 12.
- measured: all 24 scaling files have `process_cpu_affinity` 0–15 before and after.
- measured: hevc_qsv N=4 has `streams_keeping_up` 0 in all 3 reps.
- measured: nvJPEG N=16 keeps up 1, 2 and 3 of 16.
- measured: nvJPEG 4:2:2 has 383 and 955 late frames of 7,200.
- measured: single-stream libx264 ultrafast 372.47 fps / 5.476 cores, veryfast 229.19 / 7.116, libx265 106.22 / 26.935.
- measured: `system_after` affinity is 0–27. The libx265 widening is measured (intra_compare §5 flag 1, F1).
- measured: negative process CPU is −2.224 and −2.44 (item 10) and −1.149 (item 55).
- measured: `verify_method_lowpower.json` has 4 hevc_qsv cases, each 8/8 keyframes (default, low_power, veryfast, both).
- measured: `BENCH_RUN_2300_SUMMARY.md` §1-§2: 23:00:07–05:36:29, 67/68 ok, OV-COST the only timeout, no `load_over_15pct`, NVIDIA 610.88 / Intel 32.0.101.7088.
- measured: `bench_queue_2300.json` has 68 `id` fields, 0 `B-` ids and 0 `scripts/hw_accel_target` matches. `BENCH_RUN_2300_LOG.jsonl` has 0 matches for `"B-`. `R/hw_accel_target/bench/` is empty.
- §5 mapping:
  - `BENCH_QUEUE_2300.md:216-222` say what the draft says;
  - the queue order matches every item number used (4–10, 31–34, 41–45, 49–55, 56 UI-BAYER, 57 UI-CORE, 12–15/25–26/46–47 IP-*);
  - the `NOTES_functional.md:195-210` line numbers match the B-* ids;
  - `[9]` and `[10]` map to HANDOFF §1 requirements 3 and 8.
- code: `bench_encode_stream.py:49-66` (ENC table, empty QSV options), `:54` (mjpeg_qsv nv12), `:112` (no range argument), `:119-124` (`dst_color_range=1` for non-yuvj).
- code: `benchpaths.py:16-19` (range rule).
- code: `bench_matched_concurrent.py:60-62, 73-75` (packets counted, not written).
- Not timed: no `matched_concurrent_libx26*` file and no nvjpeg process file in IB (absence confirmed).
- Timing rule: every timing number is from the quiet run. None comes from a concurrent run.

GF03 / N6, N7, N9, N13, R5, §3.1, §3.3, §4, §6:
- source: `GF03_quote_verification.json` has 72/72 `found_verbatim`.
- source: R01, R04, R05, R06 (including "Jetson Thor (Blackwell), running Linux ARM64"), R07, R09, R10, R14 ("… X.z where z≥y"), R19, R20, W01, W10, G01, H01, C04, E04 and C13 match the draft wording.
- code: `GF03_sources/nvjpeg_h_12.4.0.76_lines.txt` lines 70-73 (12.4.0.76), 154 (`NVJPEG_INPUT_YUV`), 159 (`NVJPEG_INPUT_NV12`), 183-185 (`ENC_BACKEND_GPU` / `HARDWARE`), 540 (`nvjpegEncodeYUV`) and 560 (`nvjpegEncode`).
- measured (static parse): `GF03_wheel_arch_facts.json` `fatbin`. nvjpeg64_12.dll has SASS 50, 52, 60, 61, 70, 75, 80, 86, 89, 90, 100, 101, 103, 120, 121 plus PTX 121 (PTX in 10 of 11 fatbins). The three nvImageCodec binaries have SASS 50, 60, 70, 80, 90, 100, 120 plus PTX 120. The "not cross-checked with cuobjdump" label is present.
- measured: `R/gpu_encode/NOTES.md:148` gives nvidia-nvjpeg-cu12==12.4.0.76.
- Labels: the [inferred] "code present, not run" is correctly marked, and functional encode on 7.5/8.9/12.0 is kept NOT VERIFIED.
- Spot checks (GF06/GF07): the AMF IDR_PERIOD (`amfenc_h264.c:575`), AMF doc 1953, Apple "A key frame interval of 1" and Intel "Requires discrete graphics" / "do not have media support" excerpts exist in `GF06_sources/` and `GF07_sources/`.
- Spot check (GF05): `R/intra_compare/NOTES.md:179, 181, 185, 186, 208` carry "corrected 2026-11-10, GF05".

## 4. Verdict

Provenance is sound: every GF03/GF04 number and quote checked matches its file. One over-generalisation must be fixed (X1: the nvJPEG miss applies to CPU-decoded MJPEG only). Eight weak points need wording or citation fixes; the most important is W1 (capacity = largest tested N, not a maximum).
