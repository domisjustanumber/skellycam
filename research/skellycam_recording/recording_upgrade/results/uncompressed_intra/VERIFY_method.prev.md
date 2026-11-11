# uncompressed_intra - adversarial verification (methodology lens)

Target: `FINDINGS.md` (12:11 version), plus `NOTES.md`, `bench/BENCH.md`, `bench/*.json` and the scripts. Verifier run on 2026-11-09 on Gerald. The verifier ran functional checks only (sizes, logs, bit-exactness, Chromium load and draw, readability after a kill), with no timing. Two timed repros are requested at the end.

Labels: **measured** (verifier result file, path below), **source** (primary source or library code at a pinned version), **code** (repo file:line), **inferred** (reasoning).

Verifier files:
- scripts: `scripts/uncompressed_intra/verify_method/` (`mkframes.py`, `cli_checks.sh`, `colsum.py`, `colsum2.py`, `compress.py`, `make_chromium_benched_samples.sh`);
- results: `results/uncompressed_intra/verify_method/` (`cli_checks.txt`, `canvas_sum_hypotheses.txt`, `ffv1_size_by_camera.txt`, `chromium_benched_configs_{electron35,electron45,manifest}.json`, `chromium_benched_configs_probe.txt`, `cpu_topology.txt`, `ffv1_encoder_help_ffmpeg9.0.2.txt`).
- Media went to `C:/Users/Dom/Documents/skellycam-raw/.../uncompressed_intra/verify_method/` and was deleted afterwards. The exceptions are two single-frame 12-bit inputs (`bayer_rggb16le_noiseTrue.raw`, `bayer16_quad_noiseTrue.raw`), kept for repro request 2.

## Verdict

Most functional claims hold up: bit-exactness, the PyAV Matroska gate, container pix_fmt behaviour, NVENC capability errors and the FFV1 v4 cross-version failure. Problems found:
- Refuted: one Chromium cell (x265 lossless), the claim that the PyAV 19 and 18 timings fall within the run spread, and one claim that is too general (packed 4:2:2).
- Bench method: several confounders change numbers and one recommendation:
  - encoder start-up time is inside the timed region;
  - only one camera's content was used;
  - the 12-bit sizes are dominated by synthetic noise;
  - the coder setting differs between the FFV1 v4 and v3 Bayer configs;
  - the Chromium "plays" checks never verify pixels.
- The main recommendation survives as a functional choice: FFV1 v3 (rice coder, gop 1) in MKV for 8-bit YUY2/NV12. Its KB/frame and cores/stream numbers come from one camera, are lower bounds, and change by up to 58% with the other real camera.

## Refuted

| # | claim (where) | evidence against | correction |
|---|---|---|---|
| R1 | §3.1 Chromium column: "x265 lossless ... E45 only" | measured (`verify_method/chromium_benched_configs_electron45.json`): the benched form, x265 lossless 4:2:2 (profile Rext, `chromium_benched_configs_probe.txt`), gives `PIPELINE_ERROR_DECODE` in Electron 45.2.3 and `DEMUXER_ERROR_NO_SUPPORTED_STREAMS` in 35.7.5. x265 lossless 4:2:0 (Rext) plays in E45. code: the original sample was x265 crf20 4:2:0 Main (`scripts/uncompressed_intra/make_chromium_samples.py`, `hevc_intra_420.mp4`) (corrected 2026-11-10, GF05: "Main" is wrong. ffprobe 9.0.2 on the file gives `profile=Rext`, `codec_tag=hvc1`, yuv420p, 8 frames, all `pict_type=I` (`results/chromium_codecs/gapfill/GF05_ffprobe_hevc_intra_420.txt`; intra_playback FINDINGS F16). Only the generator's declared codec string `hvc1.1.6.L120.90` says Main (`make_chromium_samples.py:46`); it does not match the stream) | "x265 lossless 4:2:2: fails in E35 and E45; 4:2:0 lossless plays in E45 only" |
| R2 | §2.7 and BENCH: "PyAV 19 vs 18: identical sizes; fps within spread (FFV1 s4 43.1 vs 43.4; mjpeg 168 vs 149)" | measured (bench JSON `stats`): mjpeg t1 is 149 (133-158) vs 168 (162-169). FFV1 s24 t0 is 266 (259-271) vs 226 (218-235). Neither pair of ranges overlaps. Whole-machine CPU during the reps also differed: mjpeg 49.5-71.5% (v18) vs 27.6-38.0% (v19); FFV1 37.5-40.4% vs 50.9-64.4% | "Sizes identical. Timings differ by +13% and -15%, outside the rep ranges and in opposite directions, and follow the background-load difference. No version effect can be read from this run." |
| R3 | §2.3: "no compressing encoder takes packed 4:2:2" | measured (`pyav_caps_18.0.0.json`): `encoders/hevc_qsv/video_formats` contains `yuyv422` | "None of the tested exact (lossless) configs accepts packed 4:2:2. hevc_qsv (lossy; QSV inactive here) lists yuyv422." |

## Weak (claim survives only with a caveat or a fix)

### Benchmark method
- **W1 Encoder start-up is timed in every rep.**
  - source: PyAV 18.0.0 wheel `av/codec/context.py:502` calls `self.open(strict=False)` from the first `encode()`; `av/container/output.py:611` writes the header at the first mux.
  - code: `scripts/uncompressed_intra/bench_intra.py:149-165` starts the clock before the first `encode()`.
  - measured: in rep 1 the slowest single call, as a share of encode wall time (bench JSON `latency_max` / `encode_wall_s`):
    - dnxhd t0: 404 ms of 539 ms (75%);
    - svtav1 p10: 54-56%;
    - svtav1 crf30 p12: 25-31%;
    - h264_nvenc NV12: 16%;
    - hevc_nvenc: 9-14%;
    - FFV1: 6%.
  - inferred: that slowest call is codec open. It makes short reps measure start-up rather than steady state: 24 frames for slow codecs, and under 1 s for 300 NVENC frames.
  - Affected comparisons:
    - svtav1 PyAV 19 NV12 396 fps vs PyAV 18 YUY2 266 fps;
    - dnxhd t0 vs t1;
    - h264 vs hevc NVENC;
    - all t0 rows of frame-threaded codecs, where 24 frames is fewer than the 28 threads.
  - Fix: open the codec and write the header before starting the clock (encode one frame first, or call `st.codec_context.open()`), and time at least 10 s per rep.
- **W2 The "t1 is more reliable" assumption ignores the hybrid CPU.**
  - measured (`verify_method/cpu_topology.txt`): 20 cores, 28 logical processors.
  - inferred: 8 hyper-threaded cores plus 12 single-threaded ones, i.e. P and E cores.
  - No affinity was set, so a t1 thread may run on either core type. Wide t1 ranges fit this: ffvhuff 147-209, x264 qp0 70-86, FFV1 range s24 26.6-32.5.
  - `system_cpu_percent_during_encode` also includes the bench's own load, so it cannot separate own load from background load.
  - Fix: pin t1 runs to one P core (`start /affinity`) and re-run on an idle machine.
- **W3 Warm caches.**
  - measured (`cpu_topology.txt`): L3 is 33792 KB and RAM is 68.4 GB.
  - The 8 unique 1080p frames total 33.2 MB, about the size of L3.
  - Each rep's output (90 x 4.1 MB for rawvideo) fits in the page cache, and decode reads the file just written.
  - inferred: the rawvideo encode figures (366 fps, about 1.5 GB/s) and all decode fps measure memory and page cache, not disk or fresh capture buffers.
  - Fix: label these rows; use `p12_disk_sustained.md` for disk numbers, as §4.4 already does.
- **W4 "FFV1 range misses 30 fps at t1" is not decisive.**
  - measured (`ffv1_l3_s24_crc_range_g1.mkv__yuyv422_1080p__t1__pyav18.0.0.json`): median 26.86, but the rep range is 26.61-32.48 with 30-43% system CPU.
  - Implication 4.1 (range coder "only if CPU is spare") rests on this number. See repro 1.

### Inputs and content
- **W5 One camera's content.**
  - measured (`verify_method/ffv1_size_by_camera.txt`, same FFV1 v3 s24 g1 settings, 8 frames each):
    - C930e real YUY2: 470.3 KB/f (matches the bench's 470);
    - C922 real YUY2: 740.7 KB/f (+58%).
  - Every KB/f, MB/s and (inferred) FFV1 fps figure comes from one camera and scene.
  - Fix: run both YUY2 sets and report the range.
- **W6 The 720p rows use decoded JPEGs.**
  - measured (same file): C930e 1080p decoded JPEGs give 325.1 KB/f, against 470.3 for real C930e YUY2 (-31%). These are different captures, so the comparison is partly confounded.
  - inferred: JPEG quantisation smooths the image, so the 720p FFV1 figures (130 KB/f, 117 fps t1) are probably flattered.
  - Fix: mark the 720p rows in §2.7 and the tables as "JPEG-decoded, not camera YUY2".
- **W7 The 12-bit sizes are dominated by the synthetic noise.** "Pessimistic" (§2.1) is not supported.
  - measured (`verify_method/cli_checks.txt` section 3, 1 frame, FFV1 v3), with and without the seeded noise:
    - quad split: 1,617,493 B with noise vs 504,260 B without;
    - mosaic: 2,347,875 B vs 1,219,858 B;
    - the 4 uniform noise bits alone carry 1,036,800 B of entropy per frame.
  - So about 69% (quad) and 48% (mosaic) of the 12-bit bytes come from the noise generator. The quad/mosaic ratio is 1.45x with noise and 2.42x without.
  - inferred: the high bits come from an ISP-processed image with 4:2:2-subsampled chroma, which is smoother than a real CFA. So the direction of the error against real raw data is unknown.
  - Fix:
    - give noise=False / noise=True bounds for every 10- and 12-bit size;
    - mark the Bayer codec rankings as depending on the noise model;
    - test real raw frames before choosing a storage layout by size.

### FFV1 coder confound (Bayer)
- **W8 FFV1 v3 forces the range coder above 8 bits.**
  - measured (`cli_checks.txt` section 1, ffmpeg 9.0.2):
    - for gray16le, at level 3 and level 4, `-coder 0` logs "high bits_per_raw_sample, forcing range coder", and coder 0 and coder 1 give identical bytes;
    - native `bayer_rggb16le` at level 4 does not force it: rice 1,588,642 B vs range 1,569,842 B, both bit-exact.
  - source (`ffv1_encoder_help_ffmpeg9.0.2.txt`): "-coder ... (default rice)".
  - Consequences:
    1. The Bayer12 rows `ffv1_l3_s24_crc_g1` and `ffv1_l3_s24_crc_range_g1` are the same encoder mode: bytes are 2349/2349 and 1647/1647 (`BENCH.md`).
    2. The v4 Bayer bench (opts with no `coder`) ran rice, while the v3 quad bench ran the forced range coder. So "v4 is about 2x the t1 speed of v3 quad at the same size" probably reflects the entropy coder, not the Bayer transform (inferred). See repro 2.
  - Fix: state the forced range coder in §2.6, §2.7 and §3.2, and drop or merge the duplicate "range" Bayer rows.
- **W9 Implication 4.6 does not weigh CPU.**
  - It recommends FFV1 v3 on the quad split: 2.00 cores/stream at t1 and 2.46 at t0 (`BENCH.md`).
  - ffvhuff on the quad split costs 0.18 cores/stream at 1829 KB/f, which is +11% size. That 11% gap is itself set by the noise model (W7).
  - Fix: present both and let CPU budget choose, or justify FFV1 with real raw data.

### Crash and truncation
- **W10 "trunc ok" is a single 50% cut of a finalized 4-frame file.**
  - code: `functional_matrix.py:403-410`.
  - Headers, sizes and the index were already final, so this is not a writer crash. `p11_crash_container.md` tested killed writers for MKV and MP4 only, not NUT or AVI, so "Agrees with p11" covers MKV only.
  - measured (`cli_checks.txt` section 2): an ffmpeg 9.0.2 writer was hard-killed (`timeout -s KILL`) after about 3 s at 30 fps, once per container:
    - utvideo.avi: 100 frames readable;
    - ffvhuff.nut: 102;
    - ffv1.mkv: 103;
    - utvideo.nut: 101;
    - ffv1.avi: 104.
  - The direction holds, but the evidence is thin.
  - measured (same): in AVI and NUT the partial last packet reaches the decoder and fails ("Incorrect slice size"; "slice count 0 is invalid"). MKV ends with "File ended prematurely". `functional_matrix_pyav18.0.0.json` shows the same in PyAV (`trunc50_error` ArgumentError / InvalidDataError for NUT and AVI). So a PyAV reader of AVI or NUT must catch an exception at the tail.
  - Fix: add these caveats and defer to the crash_resilience topic for kill tests with the PyAV writer.

### Chromium
- **W11 "Plays" does not mean correct pixels.**
  - code (`chromium_check/page.html`): the harness keeps only a weighted sum of a 64x36 `drawImage` copy.
  - measured (`verify_method/chromium_benched_configs_*.json`):
    - the same 4:2:2 lossless YUV renders as 1,968,455 (VP9 and AV1, study files) but as 1,990,009 (H.264 qp0 4:2:2, High 4:4:4 Intra), in both Electron versions;
    - a BT.601-tagged H.264 4:2:0 file gives the same sum as the untagged one (2,011,651).
  - measured (`verify_method/canvas_sum_hypotheses.txt`, frame 0, cv2 bilinear downscale):
    - predicted 4:2:0 sums are 1,999,356 (BT.601 limited) and 2,011,860 (BT.709 limited);
    - the observed 2,011,651 (E45 for all codecs; H.264 in E35) is within 0.01% of BT.709;
    - E35 AV1 lossless 1,999,082 is within 0.02% of BT.601;
    - the 4:2:2 sums match no standard matrix (BT.601/709/2020/240M/FCC limited: 1,994,305-2,013,740).
  - inferred: this explains the "cause NOT VERIFIED" in §2.10. E35 renders untagged VP9 and AV1 4:2:0 as BT.601, while E45 and H.264 render it as BT.709.
  - The change is not limited to AV1 lossless. Every E35 VP9 and AV1 4:2:0 sample changed in E45 (vp9 crf30 2,002,040 to 2,014,777; svt 2,003,012 to 2,015,986), while H.264 did not (study JSON).
  - Fix:
    - compare full-resolution `getImageData` against reference conversions;
    - test colour tags;
    - list colour fidelity as NOT VERIFIED in §2.10 and §3.4 (the Electron bump changes how VP9/AV1 4:2:0 is displayed).
- **W12 The Chromium cells name configs that were never tested.**
  - §3.1 "x264 qp0 .mkv: 4:2:0 lossless plays": the benched config is 4:2:2 in MKV. measured (verifier JSON): x264 qp0 4:2:2 plays in MKV and MP4 in both Electron versions.
  - §3.3 "h264_nvenc lossless plays" and "hevc_nvenc lossless E45 only": NVENC output was never loaded in Chromium. NOT VERIFIED.
  - Container: the benched svtav1 lossless in MKV plays in E35 and E45 (verifier JSON). H.264, AV1 and VP9 in `.mkv` play in E35 even though `canPlayType('video/x-matroska')` returns "". So MKV is not the blocker; the codec is.
  - Fix: name the exact file tested in each cell.

### Scope
- **W13 "Per 30 fps stream" for YUY2 1080p.**
  - measured (corpus `index.json`, source paths `pyav_ds_1920x1080_5`): both YUY2 sets were captured at 5 fps.
  - Cores/stream is fine as a normalisation. But no tested camera is shown to deliver 1080p30 YUY2, so implications that budget per-camera YUY2 1080p30 recording need a capable camera (NOT VERIFIED for these cameras).

## What survived scrutiny
- measured (study files, spot-checked): FFV1 at 470 KB/f for C930e reproduces (470.3, verifier).
- The PyAV Matroska gate, with its source quote, holds.
- The NVENC 4:2:2 and AV1 errors hold.
- FFV1 v4 Bayer is unreadable by FFmpeg 8.1.2.
- OpenCV Bayer naming (BG2BGR for RGGB) is backed by PSNR.
- MOV/MP4 decode 0 frames after truncation (consistent with p11).
- The FFV1 v3 coder test also showed that `-bits_per_raw_sample 12` does not shrink FFV1 output for 12-bit data in gray16le: 1,617,492 vs 1,617,493 B (measured: `verify_method/cli_checks.txt` section 4). So signalling 16 bits is not a size confounder.

## Repro requests (timed; run under the timing lock)
1. FFV1 rice vs range, YUY2 1080p, t1 and t0, 300 frames x 5 reps (W4, implication 4.1). Run from the repo root in bash:
   `for c in ffv1_l3_s24_crc_g1.mkv ffv1_l3_s24_crc_range_g1.mkv; do for t in 1 0; do .venv/Scripts/python.exe research/skellycam_recording/recording_upgrade/scripts/uncompressed_intra/bench_intra.py --config $c --source yuyv422 --res 1080p --threads $t --frames 300 --reps 5 --warmup-frames 20 --tag _verify; done; done`
   Expected if the claims hold: rice t1 median at least 40 fps and at most 0.75 cores/stream; range t1 below 30 fps in all 5 reps and at least 1.0 cores/stream; 470 / 370 KB per frame.
2. Is the v4 speed-up the coder or the Bayer transform (W8)? ffmpeg 9.0.2, single thread, 300 frames, null output:
   `cd C:/Users/Dom/Documents/skellycam-raw/skellycam_recording/recording_upgrade_20261109/uncompressed_intra/verify_method && for spec in "bayer_rggb16le bayer_rggb16le_noiseTrue 4 0" "bayer_rggb16le bayer_rggb16le_noiseTrue 4 1" "gray16le bayer16_quad_noiseTrue 3 1"; do set -- $spec; echo "pix=$1 src=$2 level=$3 coder=$4"; ffmpeg -hide_banner -nostats -benchmark -stream_loop 299 -f rawvideo -pix_fmt $1 -s 1920x1080 -r 30 -i $2.raw -c:v ffv1 -level $3 -strict experimental -slices 4 -slicecrc 1 -coder $4 -g 1 -threads 1 -f null - 2>&1 | grep bench; done`
   Expected if it is the coder: v4 coder=1 rtime is about the same as v3 quad coder=1, and both are about 2x v4 coder=0. If it is the Bayer transform: v4 coder=1 stays close to v4 coder=0.
